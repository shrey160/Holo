"""Region-only semantics, missing spans, source-frame transforms and immutable publication."""

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

try:
    import cv2
    import numpy as np
except ImportError as error:
    raise unittest.SkipTest("Install reconstruct extra") from error

from cozmo_ingestion.errors import IngestionError
from cozmo_ingestion.storage import sha256, write_json
from cozmo_reconstruction.boundaries.analysis import analyze_geometry, classify_samples
from cozmo_reconstruction.boundaries.geometry import (
    floor_frame,
    floor_uv,
    interval_runs,
    plane_intersection,
    supported_cells,
    wall_spans,
)
from cozmo_reconstruction.boundaries.models import BoundaryPolicy, BoundaryRequest
from cozmo_reconstruction.boundaries.pipeline import BoundaryPipeline, guard_output
from cozmo_reconstruction.boundaries.reviews import load_review, template
from cozmo_reconstruction.boundaries.verification import verify_boundaries
from cozmo_reconstruction.dense.models import DenseRequest
from cozmo_reconstruction.surfaces.models import SurfaceRequest


def marked(identity, view, role="FLOOR"):
    return template(identity) | {
        "reviewer": "analytic",
        "floor_plane_id": "P01",
        "regions": [
            view
            | {
                "id": "R01",
                "plane_id": "P01",
                "role": role,
                "reason": "Known analytic region",
                "polygon_dense": [[0, 0], [100, 0], [100, 80], [0, 80]],
            }
        ],
    }


class BoundaryTests(unittest.TestCase):
    def test_region_rejections_override_and_unmarked_points_stay_unknown(self):
        xs, ys, labels = np.array([5, 25, 65, 85]), np.full(4, 5), np.array([0, 0, 0, 1])
        floor = {
            "plane_id": "P01",
            "role": "FLOOR",
            "polygon_dense": [[0, 0], [50, 0], [50, 10], [0, 10]],
        }
        reject = {
            "plane_id": "P01",
            "role": "FURNITURE",
            "polygon_dense": [[20, 0], [30, 0], [30, 10], [20, 10]],
        }
        for regions in ([(0, floor), (1, reject)], [(1, reject), (0, floor)]):
            roles, lineage = classify_samples(xs, ys, labels, regions)
            self.assertEqual(roles.tolist(), [1, 3, 0, 0])
            self.assertEqual(lineage.tolist(), [0, 1, -1, -1])

    def test_tilted_frame_roundtrip_and_nonorthogonal_wall(self):
        plane = np.array([0.04, 1.0, -0.06, 0.8])
        plane /= np.linalg.norm(plane[:3])
        frame = floor_frame(plane, np.array([[0, -0.8, 0], [1, -0.84, 0], [0, -0.74, 1]]))
        transform = np.array(frame["world_from_floor"])
        np.testing.assert_allclose(transform @ frame["floor_from_world"], np.eye(4), atol=1e-12)
        uv = np.array([[0, 0], [1.2, -0.7]])
        xyz = np.c_[uv, np.zeros(2), np.ones(2)] @ transform.T
        np.testing.assert_allclose(floor_uv(xyz[:, :3], frame), uv, atol=1e-12)
        wall = np.array([0.3, 0, 1, -2.0])
        origin, direction = plane_intersection(wall, frame)
        self.assertAlmostEqual(float(origin @ plane[:3] + plane[3]), 0, places=10)
        self.assertAlmostEqual(float(origin @ wall[:3] + wall[3]), 0, places=10)
        self.assertAlmostEqual(float(direction @ wall[:3]), 0, places=10)
        self.assertIsNone(plane_intersection(plane, frame))

    def test_wall_gaps_and_junction_extrapolation_are_explicit(self):
        policy = BoundaryPolicy(min_points_per_view=3)
        frame = floor_frame([0, 1, 0, 0], np.array([[0, 0, 0], [0, 0, 1]]))
        xs = np.r_[np.linspace(0.01, 0.59, 45), np.linspace(1.21, 1.79, 45)]
        points = np.tile(np.c_[xs, np.full(len(xs), 0.8), np.full(len(xs), 2)], (3, 1))
        ranks = np.repeat(np.arange(3), len(xs))
        centers = {i: [i * 0.2, 1, 0] for i in range(3)}
        result = wall_spans(points, ranks, centers, [0, 0, 1, -2], frame, policy)
        self.assertEqual(len(result["segments"]), 2)
        self.assertEqual(interval_runs([0, 1, 4, 5]), [[0, 1], [4, 5]])
        self.assertEqual(result["segments"][0]["near_floor_observations"], 0)
        self.assertIn("not certified", result["segments"][0]["junction_status"])
        self.assertLess(result["segments"][0]["endpoints_floor_uv_m"][1][0], 1)
        result = wall_spans(
            points, ranks, {i: [0, 1, 0] for i in range(3)}, [0, 0, 1, -2], frame, policy
        )
        self.assertEqual(result["segments"], [])

    def test_floor_cells_do_not_fill_holes(self):
        policy = BoundaryPolicy(min_points_per_view=3)
        frame = floor_frame([0, 1, 0, 0], np.array([[0, 0, 0]]))
        point = np.array([[0.02, 0, -0.02]] * 5 + [[0.47, 0, -0.02]] * 5)
        points = np.tile(point, (3, 1))
        ranks = np.repeat(np.arange(3), len(point))
        cells = supported_cells(
            points, ranks, {i: [i * 0.2, 1, 0] for i in range(3)}, frame, policy
        )
        self.assertEqual([c["cell"] for c in cells], [[0, 0], [3, 0]])

    def test_no_floor_and_no_closed_polygon_even_with_walls(self):
        review = template({})
        arrays = {
            "xyz_m": np.array([[0, 1, 2], [0.1, 1, 2]]),
            "rank": np.array([0, 1]),
            "plane_index": np.array([0, 0]),
            "role": np.array([2, 2]),
        }
        report = analyze_geometry(
            [{"id": "P01", "equation_world": [0, 0, 1, -2]}],
            review,
            arrays,
            {},
            {0: [0, 1, 0], 1: [0.2, 1, 0]},
            BoundaryPolicy(),
        )
        self.assertEqual(report["supported_segments"], 0)
        self.assertEqual(report["walls"][0]["status"], "NO_SUPPORTED_FLOOR")
        self.assertIsNone(report["closed_room_polygon"])
        self.assertIsNone(report["room_area_m2"])
        self.assertFalse(report["scale_applied"])

    def test_invalid_review_and_changed_evidence(self):
        identity = {"source": "analytic"}
        view = {
            "rank": 0,
            "image": "000000.jpg",
            "image_size": [100, 80],
            "frame_id": "f0",
            "relative_seconds": "0",
            "source_rgb_sha256": "rgb",
            "observations_sha256": "obs",
            "evidence_overlay_sha256": "overlay",
        }
        planes = [{"id": "P01", "orientation": "horizontal"}]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "review.json"
            review = marked(identity, view)
            write_json(path, review)
            self.assertEqual(load_review(path, identity, planes, [view]), review)
            for mutate in (
                lambda r: r["regions"][0].update(source_rgb_sha256="changed"),
                lambda r: r["regions"][0].update(
                    polygon_dense=[[0, 0], [100, 80], [100, 0], [0, 80]]
                ),
                lambda r: r.update(human_confirmed=True),
                lambda r: r["regions"][0].update(role="WALL"),
            ):
                bad = json.loads(json.dumps(review))
                mutate(bad)
                write_json(path, bad)
                with self.assertRaises(IngestionError):
                    load_review(path, identity, planes, [view])

    def test_raw_and_review_output_overlap_rejected(self):
        upstream = DenseRequest(Path("sparse"), Path("prepared"), Path("bundle"), Path("dense"))
        request = BoundaryRequest(
            SurfaceRequest(upstream, Path("surfaces")),
            Path("new"),
            review=Path("reviews/file.json"),
        )
        reader = SimpleNamespace(roots={"capture": Path("raw").resolve()})
        with patch("cozmo_reconstruction.boundaries.pipeline.CaptureReader", return_value=reader):
            for output in (
                Path("raw/result"),
                Path("surfaces/result"),
                Path("reviews"),
                Path("dense"),
            ):
                with self.assertRaises(IngestionError):
                    guard_output(replace(request, output=output))
            guard_output(request)

    def test_publication_archived_review_and_forged_polygon_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            dense = root / "dense"
            surface = root / "surfaces"
            (dense / "workspace/images").mkdir(parents=True)
            (surface / "observations").mkdir(parents=True)
            (surface / "overlays").mkdir()
            image = dense / "workspace/images/000000.jpg"
            overlay = surface / "overlays/000000.jpg"
            cv2.imwrite(str(image), np.zeros((80, 100, 3), np.uint8))
            cv2.imwrite(str(overlay), np.zeros((80, 200, 3), np.uint8))
            np.savez_compressed(
                surface / "observations/000000.jpg.npz",
                x=np.array([4, 8, 12]),
                y=np.array([4, 8, 12]),
                plane_index=np.array([0, 0, 0]),
                dense_support=np.array([2, 2, 2]),
            )
            camera = {
                "rank": 0,
                "image": "000000.jpg",
                "image_size": [100, 80],
                "params": [100, 100, 50, 40],
                "camera_from_world": np.eye(4).tolist(),
                "center_m": [0, 0, 0],
            }
            write_json(dense / "cameras.json", [camera])
            view = {
                "rank": 0,
                "image": "000000.jpg",
                "image_size": [100, 80],
                "frame_id": "f0",
                "relative_seconds": "0",
                "source_rgb_sha256": sha256(image),
                "observations_sha256": sha256(surface / "observations/000000.jpg.npz"),
                "evidence_overlay_sha256": sha256(overlay),
            }
            identity = {"analytic": "fixture"}
            plane_report = {
                "planes": [
                    {"id": "P01", "orientation": "horizontal", "equation_world": [0, 1, 0, 1]}
                ]
            }
            review_path = root / "review.json"
            write_json(review_path, marked(identity, view))
            request = BoundaryRequest(
                SurfaceRequest(
                    DenseRequest(root / "sparse", root / "prepared", root / "bundle", dense),
                    surface,
                ),
                root / "result",
                review_path,
            )
            reader = SimpleNamespace(roots={"capture": root / "raw"})
            with (
                patch(
                    "cozmo_reconstruction.boundaries.pipeline.CaptureReader", return_value=reader
                ),
                patch("cozmo_reconstruction.boundaries.pipeline.source_audit"),
                patch("cozmo_reconstruction.boundaries.verification.source_audit"),
                patch(
                    "cozmo_reconstruction.boundaries.pipeline.inputs",
                    return_value=(identity, plane_report, [view]),
                ),
                patch(
                    "cozmo_reconstruction.boundaries.verification.inputs",
                    return_value=(identity, plane_report, [view]),
                ),
                patch(
                    "cozmo_reconstruction.boundaries.analysis.read_array",
                    return_value=np.ones((80, 100)),
                ),
            ):
                before = sha256(review_path)
                result = BoundaryPipeline().run(request)
                self.assertEqual(result["verification"]["status"], "VERIFIED")
                self.assertEqual(before, sha256(review_path))
                portable = replace(request, review=None)
                self.assertEqual(verify_boundaries(request.output, portable)["status"], "VERIFIED")
                path = request.output / "report.json"
                report = json.loads(path.read_text())
                report["closed_room_polygon"] = [[0, 0], [1, 0], [1, 1], [0, 0]]
                write_json(path, report)
                manifest = json.loads((request.output / "manifest.json").read_text())
                manifest["artifact_sha256"]["report.json"] = sha256(path)
                write_json(request.output / "manifest.json", manifest)
                with self.assertRaises(IngestionError) as caught:
                    verify_boundaries(request.output, portable)
                self.assertEqual(caught.exception.code, "BOUNDARY_REPORT_CHANGED")

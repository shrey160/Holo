"""Known planes, holes, semantic ambiguity and accepted-depth lineage."""

import json
import tempfile
import unittest
from dataclasses import asdict, replace
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
from cozmo_reconstruction.dense.models import DenseRequest
from cozmo_reconstruction.surfaces.analysis import analyze, plane_summary
from cozmo_reconstruction.surfaces.geometry import assign, fit_planes, occupied_patches
from cozmo_reconstruction.surfaces.models import SurfacePolicy, SurfaceRequest
from cozmo_reconstruction.surfaces.pipeline import (
    INPUT_POLICY,
    SCHEMA,
    guard_output,
    verify_surfaces,
)


class SurfaceTests(unittest.TestCase):
    def test_implicit_raw_root_and_all_ancestors_are_protected(self):
        raw = Path("raw-session").resolve()
        upstream = DenseRequest(Path("sparse"), Path("prepared"), Path("bundle"), Path("dense"))
        with patch(
            "cozmo_reconstruction.surfaces.pipeline.CaptureReader",
            return_value=SimpleNamespace(roots={"capture": raw}),
        ):
            for output in (raw / "result", raw.parent, Path("dense") / "result"):
                with self.assertRaises(IngestionError):
                    guard_output(SurfaceRequest(upstream, output))
            guard_output(SurfaceRequest(upstream, Path("separate-result")))

    def test_noisy_planes_outliers_and_determinism(self):
        rng = np.random.default_rng(7)
        uv = rng.uniform(-2, 2, (1600, 2))
        floor = np.c_[uv[:, 0], rng.normal(-1, 0.002, len(uv)), uv[:, 1]]
        wall = np.c_[rng.normal(2, 0.002, len(uv)), uv]
        cloud = np.r_[floor, wall, rng.uniform(-3, 3, (200, 3))]
        policy = SurfacePolicy(max_planes=2, iterations=96)
        planes = fit_planes(cloud, policy)
        np.testing.assert_array_equal(planes, fit_planes(cloud, policy))
        self.assertEqual(len(planes), 2)
        labels, errors = assign(cloud, planes, policy.distance_m)
        self.assertGreater(np.mean(labels[:3200] >= 0), 0.99)
        self.assertLess(np.median(errors[:3200]), 0.003)
        self.assertGreater(np.mean(labels[3200:] < 0), 0.9)

    def test_empty_degenerate_and_nonfinite_do_not_invent_planes(self):
        policy = SurfacePolicy(iterations=32)
        for cloud in (np.empty((0, 3)), np.zeros((300, 3))):
            self.assertEqual(fit_planes(cloud, policy).shape, (0, 4))
        with self.assertRaises(IngestionError):
            fit_planes(np.array([[0, np.nan, 0]]), policy)
        labels, _ = assign(np.array([[1, 2, 3]]), np.empty((0, 4)), 0.03)
        self.assertEqual(labels.tolist(), [-1])
        with self.assertRaises(IngestionError):
            SurfacePolicy(distance_m=float("nan"))

    def test_disconnected_patches_preserve_gap(self):
        points = np.array([[0.02, -1, 0.02], [0.03, -1, 0.03], [3, -1, 0]])
        patches = occupied_patches(points, np.array([0, 1, 0, 1]), 0.1)
        self.assertEqual(len(patches["components"]), 2)
        self.assertEqual(len(patches["cells"]), 2)
        self.assertEqual(sum(c[2] for c in patches["cells"]), 3)
        self.assertAlmostEqual(patches["occupied_grid_area_m2"], 0.02)

    def test_repeated_camera_positions_are_not_sufficient_evidence(self):
        uv = np.array(np.meshgrid(np.linspace(0, 2, 20), np.linspace(0, 2, 20))).reshape(2, -1).T
        points = np.c_[uv[:, 0], np.full(len(uv), -1), uv[:, 1]]
        centers = {str(i): [0, 0, 0] for i in range(3)}
        views = [{"image": str(i), "rank": i, "samples": 200} for i in range(3)]
        result = plane_summary(
            0,
            np.array([0, 1, 0, 1]),
            points,
            np.zeros(len(points)),
            views,
            centers,
            SurfacePolicy(),
        )
        self.assertEqual(result["evidence_status"], "WEAK")
        self.assertIn("INSUFFICIENT_CAMERA_BASELINE", result["flags"])

    def test_large_horizontal_furniture_is_not_confirmed_floor(self):
        uv = np.array(np.meshgrid(np.linspace(0, 2, 20), np.linspace(0, 2, 20))).reshape(2, -1).T
        points = np.c_[uv[:, 0], np.full(len(uv), -1), uv[:, 1]]
        centers = {str(i): [i * 0.2, 0, 0] for i in range(3)}
        views = [{"image": str(i), "rank": i, "samples": 200} for i in range(3)]
        result = plane_summary(
            0,
            np.array([0, 1, 0, 1]),
            points,
            np.zeros(len(points)),
            views,
            centers,
            SurfacePolicy(),
        )
        self.assertEqual(result["role_hypothesis"], "floor_or_furniture")
        self.assertEqual(result["evidence_status"], "MULTIVIEW_CANDIDATE")
        self.assertIn("UNCONFIRMED", result["semantic_status"])

    def test_depth_lineage_recompute_and_tamper(self):
        from cozmo_reconstruction.dense.geometry import world_points

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dense, stage = root / "dense", root / "stage"
            for path in ("workspace/stereo/depth_maps", "workspace/images", "masks"):
                (dense / path).mkdir(parents=True)
            stage.mkdir()
            camera = {
                "image": "000001.jpg",
                "rank": 1,
                "center_m": [0, 0, 0],
                "camera_from_world": np.eye(4).tolist(),
                "params": [80, 80, 40, 30],
                "image_size": [80, 60],
            }
            depth = np.full((60, 80), 2, dtype=np.float32)
            # COLMAP width&height&channels& followed by Fortran order values.
            (dense / "workspace/stereo/depth_maps/000001.jpg.geometric.bin").write_bytes(
                b"80&60&1&" + depth.T.tobytes(order="F")
            )
            mask = np.ones((60, 80), bool)
            mask[20:40, 20:40] = False
            np.savez_compressed(
                dense / "masks/000001.jpg.npz", accepted=mask, support=np.full((60, 80), 2)
            )
            cv2.imwrite(
                str(dense / "workspace/images/000001.jpg"), np.full((60, 80, 3), 200, np.uint8)
            )
            write_json(dense / "cameras.json", [camera])
            write_json(
                dense / "input_mapping.json",
                [
                    {
                        "image": camera["image"],
                        "rank": 1,
                        "relative_seconds": "0.1",
                        "frame_id": "source:1",
                    }
                ],
            )
            ys, xs = np.nonzero(mask)
            np.savez_compressed(dense / "cloud.npz", xyz_m=world_points(depth, camera, xs, ys))
            policy = replace(SurfacePolicy(), sample_stride=4)
            planes = np.array([[0, 0, 1, -2]])
            first = analyze(dense, planes, policy, stage=stage)
            self.assertEqual(first, analyze(dense, planes, policy, verify_samples=stage))
            self.assertEqual(first["confirmed_architectural_surfaces"], 0)
            with np.load(stage / "observations/000001.jpg.npz") as saved:
                values = {k: saved[k] for k in saved.files}
                self.assertFalse(
                    np.any(
                        (values["x"] >= 20)
                        & (values["x"] < 40)
                        & (values["y"] >= 20)
                        & (values["y"] < 40)
                    )
                )
            values["plane_index"][0] = -1
            np.savez_compressed(stage / "observations/000001.jpg.npz", **values)
            with self.assertRaises(IngestionError):
                analyze(dense, planes, policy, verify_samples=stage)
            self.assertEqual(
                json.loads((stage / "report.json").read_text())["floorplan"], "NOT_RUN"
            )
            # With upstream auditing stubbed only for this analytic fixture, a
            # rehashed forged report still fails independent geometry verification.
            values["plane_index"][0] = 0
            np.savez_compressed(stage / "observations/000001.jpg.npz", **values)
            write_json(dense / "manifest.json", {"analytic_fixture": True})
            write_json(stage / "planes.json", planes.tolist())
            write_json(stage / "policy.json", asdict(policy))
            manifest = {
                "schema": SCHEMA,
                "status": "SURFACE_HYPOTHESES_WITH_FINDINGS",
                "dense_manifest_sha256": sha256(dense / "manifest.json"),
                "policy": asdict(policy),
                "input_policy": INPUT_POLICY,
                "artifact_sha256": {
                    p.relative_to(stage).as_posix(): sha256(p)
                    for p in stage.rglob("*")
                    if p.is_file()
                },
            }
            write_json(stage / "manifest.json", manifest)
            request = SurfaceRequest(
                DenseRequest(root / "sparse", root / "prepared", root / "bundle", dense), stage
            )
            before = {
                p.relative_to(stage).as_posix(): sha256(p) for p in stage.rglob("*") if p.is_file()
            }
            with patch("cozmo_reconstruction.surfaces.pipeline.source_audit"):
                self.assertEqual(verify_surfaces(stage, request)["status"], "VERIFIED")
                self.assertEqual(
                    before,
                    {
                        p.relative_to(stage).as_posix(): sha256(p)
                        for p in stage.rglob("*")
                        if p.is_file()
                    },
                )
                forged = dict(first, confirmed_architectural_surfaces=1)
                write_json(stage / "report.json", forged)
                manifest["artifact_sha256"]["report.json"] = sha256(stage / "report.json")
                write_json(stage / "manifest.json", manifest)
                with self.assertRaises(IngestionError) as error:
                    verify_surfaces(stage, request)
                self.assertEqual(error.exception.code, "SURFACE_REPORT_CHANGED")

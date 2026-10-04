"""Geometry display and read-only HTTP integrity, independently of expensive source trials."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    import cv2
    import numpy as np
    from fastapi.testclient import TestClient
except ImportError as error:
    raise unittest.SkipTest("Install web and reconstruct extras") from error

from cozmo_ingestion.errors import IngestionError
from cozmo_ingestion.storage import sha256, write_json
from cozmo_reconstruction.boundaries.geometry import floor_frame
from cozmo_reconstruction.boundaries.models import BoundaryRequest
from cozmo_reconstruction.dense.models import DenseRequest
from cozmo_reconstruction.surfaces.models import SurfaceRequest
from cozmo_reconstruction.viewer.export import (
    candidate_spans,
    display_points,
    export_viewer,
    plan_raster,
)
from cozmo_web.app import create_app
from cozmo_web.config import Settings
from cozmo_web.reconstruction import ReconstructionCatalog


def signed(root):
    write_json(
        root / "manifest.json",
        {
            "artifact_sha256": {
                p.name: sha256(p)
                for p in root.iterdir()
                if p.is_file() and p.name != "manifest.json"
            }
        },
    )


def fixture(root):
    dense, surfaces, boundaries = [root / name for name in ("dense", "surfaces", "boundaries")]
    for path in (dense, surfaces, boundaries):
        path.mkdir()
    xyz = np.array([[1, 1, z] for z in np.linspace(0, 1, 120)])
    frame = floor_frame([0, 1, 0, 0], np.array([[0.0, 0.0, 0.0]]))
    np.savez(dense / "cloud.npz", xyz_m=xyz, rgb=np.tile([255, 128, 0], (120, 1)))
    write_json(dense / "cameras.json", [{"center_m": [0, 1, 0]}, {"center_m": [0, 1, 1]}])
    np.savez(surfaces / "cloud_labels.npz", plane_index=np.zeros(120, dtype=np.int16))
    write_json(
        surfaces / "report.json",
        {
            "planes": [
                {
                    "id": "P01",
                    "orientation": "vertical",
                    "evidence_status": "MULTIVIEW_CANDIDATE",
                    "equation_world": [1, 0, 0, -1],
                }
            ]
        },
    )
    write_json(
        boundaries / "report.json",
        {
            "floor_frame": frame,
            "walls": [],
            "local_floor": {"cells": []},
            "reference_calibration": "UNRESOLVED",
        },
    )
    write_json(boundaries / "policy.json", {"cell_m": 0.15})
    (boundaries / "plan.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"/>')
    for path in (dense, surfaces, boundaries):
        signed(path)
    return BoundaryRequest(
        SurfaceRequest(
            DenseRequest(root / "sparse", root / "prepared", root / "bundle", dense), surfaces
        ),
        boundaries,
    )


class ViewerTests(unittest.TestCase):
    def test_display_coordinates_preserve_distances_and_handedness(self):
        normal = np.array([0.1, 0.99, 0.05])
        normal /= np.linalg.norm(normal)
        frame = floor_frame(np.r_[normal, -0.2], np.array([[0.0, 0.2 / normal[1], 0.0]]))
        xyz = np.array([[0, 1, 0], [1, 2, 3], [2, 3, 4.0]])
        display = display_points(xyz, frame)
        np.testing.assert_allclose(
            np.linalg.norm(np.diff(display, axis=0), axis=1),
            np.linalg.norm(np.diff(xyz, axis=0), axis=1),
        )
        basis = display_points(np.eye(3), frame) - display_points(np.zeros((3, 3)), frame)
        self.assertAlmostEqual(np.linalg.det(basis), 1)

    def test_candidate_intervals_do_not_bridge_missing_bins(self):
        frame = floor_frame([0, 1, 0, 0], np.array([[0.0, 0.0, 0.0]]))
        points = np.array(
            [[1, 1, z] for z in (*np.linspace(0, 0.6, 300), *np.linspace(2, 2.6, 300))]
        )
        spans = candidate_spans(
            points,
            np.zeros(len(points), dtype=int),
            [
                {
                    "id": "P01",
                    "orientation": "vertical",
                    "evidence_status": "MULTIVIEW_CANDIDATE",
                    "equation_world": [1, 0, 0, -1],
                }
            ],
            frame,
        )
        self.assertEqual(len(spans), 2)
        self.assertTrue(all("may be furniture" in s["status"] for s in spans))
        self.assertGreater(min(abs(s["uv"][1][1] - t["uv"][0][1]) for s, t in [spans]), 1)

    def test_raster_keeps_empty_pixels_and_metric_aspect(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "plan.png"
            result = plan_raster(np.array([[0, 1, 0], [2, 1, -1], [1, 3, -0.5]]), path)
            image = cv2.imread(str(path))
            self.assertEqual(image.shape, (1000, 1400, 3))
            self.assertGreater((image == 250).all(axis=2).sum(), 1399990)
            self.assertGreater(result["scale_px_per_estimated_m"], 0)

    def test_publish_archive_layout_no_overwrite_and_http_tamper(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            request = fixture(root)
            output = root / "results/room-v1"
            original = {
                p: sha256(p)
                for source in (
                    request.output,
                    request.surfaces.output,
                    request.surfaces.upstream.output,
                )
                for p in source.iterdir()
            }
            with (
                patch("cozmo_reconstruction.viewer.export.guard_output"),
                patch(
                    "cozmo_reconstruction.viewer.export.verify_boundaries",
                    return_value={"status": "VERIFIED"},
                ),
            ):
                result = export_viewer(request, output, "Synthetic room", 1000)
                with self.assertRaises(IngestionError):
                    export_viewer(request, output, "Duplicate", 1000)
            self.assertEqual(result["display_points"], 120)
            self.assertTrue(all(sha256(path) == expected for path, expected in original.items()))
            self.assertEqual((output / "positions.bin").stat().st_size, 120 * 12)
            self.assertEqual((output / "colors.bin").stat().st_size, 120 * 3)
            self.assertIn(b"format binary_little_endian", (output / "cloud.ply").read_bytes())
            catalog = ReconstructionCatalog(output.parent)
            (output.parent / "room.failed-staging").mkdir()
            self.assertEqual(len(catalog.list()), 1)
            settings = Settings(data_root=root / "web", reconstruction_root=output.parent)
            with TestClient(create_app(settings)) as client:
                self.assertEqual(client.get("/api/reconstructions").json()[0]["id"], "room-v1")
                self.assertEqual(
                    client.get("/api/reconstructions/room-v1/positions.bin").status_code, 200
                )
                self.assertEqual(
                    client.get("/api/reconstructions/room-v1/manifest.json").status_code, 404
                )
                self.assertEqual(
                    client.get("/api/reconstructions/nope/scene.json").status_code, 404
                )
                self.assertEqual(
                    client.get("/api/reconstructions/room-v1/rough-room.svg").status_code, 404
                )
                # Optional completion is served only when hash-bound, old 8-asset bundles still work.
                import json

                (output / "rough-room.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"/>')
                manifest = json.loads((output / "manifest.json").read_text())
                manifest["artifact_sha256"]["rough-room.svg"] = sha256(output / "rough-room.svg")
                write_json(output / "manifest.json", manifest)
                self.assertEqual(
                    client.get("/api/reconstructions/room-v1/rough-room.svg").status_code, 200
                )
                (output / "rough-room.svg").write_text("tampered")
                self.assertEqual(
                    client.get("/api/reconstructions/room-v1/rough-room.svg").status_code, 409
                )
                # Restore so the subsequent independent binary tamper still exercises that asset.
                (output / "rough-room.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"/>')
                with (output / "positions.bin").open("ab") as stream:
                    stream.write(b"changed")
                self.assertEqual(
                    client.get("/api/reconstructions/room-v1/positions.bin").status_code, 409
                )

    def test_invalid_limits_reject_before_source_audit(self):
        with tempfile.TemporaryDirectory() as temp:
            request = fixture(Path(temp))
            with self.assertRaises(IngestionError):
                export_viewer(request, Path(temp) / "result", "", 1000)
            with self.assertRaises(IngestionError):
                export_viewer(request, Path(temp) / "result", "Room", 999)


if __name__ == "__main__":
    unittest.main()

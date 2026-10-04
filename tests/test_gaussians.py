"""Independent covariance/encoding checks and immutable publication/HTTP boundaries."""

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient

from cozmo_ingestion.errors import IngestionError
from cozmo_ingestion.storage import sha256, write_json
from cozmo_reconstruction.gaussians.format import encode_splats
from cozmo_reconstruction.gaussians.inputs import prepare
from cozmo_reconstruction.gaussians.publish import publish
from cozmo_web.app import create_app
from cozmo_web.config import Settings


def signed(root, schema, **extra):
    write_json(
        root / "manifest.json",
        {
            "schema": schema,
            **extra,
            "artifact_sha256": {
                p.name: sha256(p)
                for p in root.iterdir()
                if p.is_file() and p.name != "manifest.json"
            },
        },
    )


def gaussian_data(count=1000):
    return {
        "means": np.tile([1.0, 2.0, 3.0], (count, 1)),
        "scales": np.tile([0.03, 0.07, 0.11], (count, 1)),
        "quats": np.tile([1.0, 0.0, 0.0, 0.0], (count, 1)),
        "colors": np.tile([0.2, 0.4, 0.8], (count, 1)),
        "opacity": np.full(count, 0.8),
    }


def fixture(root):
    inputs, trial, viewer = [root / name for name in ("inputs", "trial", "reconstructions/room-v1")]
    for path in (inputs, trial, viewer):
        path.mkdir(parents=True)
    write_json(
        viewer / "scene.json",
        {
            "label": "Room",
            "camera_path": [[0, 1, 0]],
            "source_floor_frame": {"floor_from_world": np.eye(4).tolist()},
            "coordinates": "floor coordinates",
        },
    )
    signed(
        viewer,
        "holo-reconstruction-viewer-v1",
        source_manifest_sha256={"dense": "a", "boundaries": "b"},
    )
    np.savez(inputs / "inputs.npz", viewmats=np.eye(4)[None])
    signed(inputs, "holo-gsplat-inputs-v1", dense_manifest_sha256="a", boundary_manifest_sha256="b")
    np.savez(trial / "gaussians.npz", **gaussian_data())
    report = {
        "status": "EXPERIMENT_COMPLETE",
        "gaussians": 1000,
        "inputs_manifest_sha256": sha256(inputs / "manifest.json"),
        "pose_optimization": False,
        "scale_normalization": False,
        "validation_scope": "photometric holdout",
        "initial": [{"rank": 1, "psnr_db": 10}],
        "final": [{"rank": 1, "psnr_db": 13}],
    }
    write_json(trial / "report.json", report)
    for name in ("initial", "final"):
        (trial / f"{name}-000001.jpg").write_bytes(b"test-image")
    signed(trial, "holo-gsplat-trial-v1")
    return inputs, trial, viewer


class GaussianTests(unittest.TestCase):
    def test_rigid_export_rotates_anisotropic_covariance_and_positions(self):
        transform = np.array([[1.0, 0, 0, 4], [0, 0, 1, 5], [0, -1, 0, 6], [0, 0, 0, 1]])
        packed, positions = encode_splats(gaussian_data(1), transform)
        self.assertEqual(len(packed), 32)
        np.testing.assert_allclose(positions[0], [5, 8, 4])
        np.testing.assert_allclose(np.frombuffer(packed[:12], dtype="<f4"), positions[0])
        q = np.frombuffer(packed[28:], dtype=np.uint8).astype(float) / 127.5 - 1
        q /= np.linalg.norm(q)
        w, x, y, z = q
        rotation = np.array(
            [
                [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
            ]
        )
        diagonal = np.diag(np.array([0.03, 0.07, 0.11]) ** 2)
        np.testing.assert_allclose(
            rotation @ diagonal @ rotation.T,
            transform[:3, :3] @ diagonal @ transform[:3, :3].T,
            atol=0.00012,
        )

    def test_invalid_geometry_and_nonrigid_scale_are_rejected(self):
        for key, value in (("means", np.nan), ("scales", -1), ("colors", 2)):
            data = gaussian_data(1)
            data[key][:] = value
            with self.assertRaises(IngestionError):
                encode_splats(data, np.eye(4))
        with self.assertRaises(IngestionError):
            encode_splats(gaussian_data(1), np.diag([2, 2, 2, 1]))

    def test_budget_rejection_precedes_expensive_audit(self):
        with self.assertRaises(IngestionError):
            prepare(None, Path("unused"), points=99999999)

    def test_publish_preserves_parent_and_http_binds_hashes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            inputs, trial, viewer = fixture(root)
            preserved = {
                p: sha256(p)
                for source in (inputs, trial, viewer)
                for p in source.iterdir()
                if p.is_file()
            }
            output = root / "gaussians/room-v1"
            self.assertEqual(publish(inputs, trial, viewer, output)["gaussians"], 1000)
            self.assertEqual(preserved, {p: sha256(p) for p in preserved})
            with self.assertRaises(IngestionError):
                publish(inputs, trial, viewer, output)
            settings = Settings(
                data_root=root / "web",
                gaussian_root=root / "gaussians",
                reconstruction_root=root / "reconstructions",
            )
            client = TestClient(create_app(settings))
            self.assertEqual(
                client.get("/api/gaussians?reconstruction_id=room-v1").json()[0]["id"], "room-v1"
            )
            self.assertEqual(client.get("/api/gaussians?reconstruction_id=other").json(), [])
            self.assertEqual(client.get("/api/gaussians/room-v1/room.splat").status_code, 200)
            self.assertEqual(client.get("/api/gaussians/room-v1/manifest.json").status_code, 404)
            (output / "room.splat").write_bytes(b"changed")
            self.assertEqual(client.get("/api/gaussians/room-v1/room.splat").status_code, 409)

    def test_source_mismatch_and_failed_quality_withhold_publication(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            inputs, trial, viewer = fixture(root)
            manifest = json.loads((inputs / "manifest.json").read_text())
            manifest["dense_manifest_sha256"] = "different"
            write_json(inputs / "manifest.json", manifest)
            with self.assertRaises(IngestionError):
                publish(inputs, trial, viewer, root / "bad-result")
            self.assertFalse((root / "bad-result").exists())
            # Restore input identity, then independently exercise the appearance gate.
            manifest["dense_manifest_sha256"] = "a"
            write_json(inputs / "manifest.json", manifest)
            report = json.loads((trial / "report.json").read_text())
            report["final"][0]["psnr_db"] = 9
            write_json(trial / "report.json", report)
            signed(trial, "holo-gsplat-trial-v1")
            with self.assertRaises(IngestionError) as error:
                publish(inputs, trial, viewer, root / "bad-result")
            self.assertEqual(error.exception.code, "GAUSSIAN_QUALITY")

"""Automatic stage gating, source retention, and honest portable sparse publication."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    import numpy as np
    from fastapi.testclient import TestClient
except ImportError as error:
    raise unittest.SkipTest("Install web and reconstruct extras") from error

from cozmo_ingestion.adapters.sensor_recorder import ADAPTER
from cozmo_ingestion.errors import IngestionError
from cozmo_ingestion.storage import write_json, write_lines
from cozmo_reconstruction.models import ReconstructionRequest
from cozmo_reconstruction.viewer.automatic import publish_sparse, sparse_room
from cozmo_web.automatic import enqueue_reconstruction, finish_automatically
from cozmo_web.config import Settings
from cozmo_web.errors import WebError
from cozmo_web.reconstruction import ReconstructionCatalog
from cozmo_web.repository import JobRepository


def cloud():
    return np.random.default_rng(42).uniform([0, -1.3, 0], [4, 1.3, 3], (600, 3))


class AutomaticTests(unittest.TestCase):
    def test_upload_defaults_to_automatic_and_allows_ingestion_only(self):
        from test_web import WaitingRunner

        from cozmo_web.app import create_app

        with tempfile.TemporaryDirectory() as temp:
            with TestClient(create_app(Settings(data_root=Path(temp)), WaitingRunner())) as client:
                for data, expected in (({}, True), ({"automatic_reconstruction": "false"}, False)):
                    response = client.post(
                        "/api/jobs",
                        data=data,
                        files=[
                            ("files", ("session.zip", b"deferred validation", "application/zip"))
                        ],
                    )
                    self.assertEqual(response.status_code, 202)
                    job = client.get("/api/jobs/" + response.json()["id"]).json()
                    self.assertEqual(job["automatic_reconstruction"], expected)

    def test_preprocessing_worker_publishes_only_after_verified_preparation(self):
        from cozmo_web.worker import execute

        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            write_json(
                folder / "job.json", {"operation": "PREPROCESS", "automatic_reconstruction": True}
            )
            with (
                patch(
                    "cozmo_web.preprocessing.execute_preprocessing",
                    return_value={"verification": {"status": "PASSED"}},
                ),
                patch(
                    "cozmo_web.automatic.reconstruct", return_value={"id": "new-room"}
                ) as reconstruct,
            ):
                execute(folder, Settings())
                reconstruct.assert_called_once()
                self.assertEqual(
                    json.loads((folder / "phase.json").read_text(encoding="utf-8"))["state"],
                    "SUCCEEDED",
                )
            (folder / "result.json").unlink()
            with (
                patch(
                    "cozmo_web.preprocessing.execute_preprocessing",
                    side_effect=WebError("SOURCE_CHANGED", "bad source"),
                ),
                patch("cozmo_web.automatic.reconstruct") as reconstruct,
            ):
                with self.assertRaises(WebError):
                    execute(folder, Settings())
                reconstruct.assert_not_called()
                self.assertFalse((folder / "result.json").exists())

    def test_broken_partial_result_cannot_prevent_failure_or_restart_reconciliation(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = JobRepository(Path(temp), 4)
            job = repo.create("Room", None)
            repo.update(job["id"], state="RECONSTRUCTING")
            (repo.folder(job["id"]) / "result.json").write_text("broken", encoding="utf-8")
            repo.reconcile()
            failed = repo.get(job["id"])
            self.assertEqual(failed["state"], "FAILED")
            self.assertEqual(failed["failed_stage"], "RECONSTRUCTING")
            self.assertEqual(failed["error"]["code"], "INTERRUPTED")

    def test_reconstruction_failure_retains_preprocessing_for_retry(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            with (
                patch(
                    "cozmo_web.automatic.prepare_views",
                    return_value={"preprocessing": {"selected_count": 4}},
                ),
                patch(
                    "cozmo_web.automatic.reconstruct",
                    side_effect=WebError("BACKEND", "unavailable"),
                ),
            ):
                with self.assertRaises(WebError):
                    finish_automatically(
                        folder, Settings(), lambda _: None, {"manifest": {"adapter": ADAPTER}}
                    )
            saved = json.loads((folder / "result.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["preprocessing"]["selected_count"], 4)
            self.assertNotIn("reconstruction", saved)

    def test_floor_display_is_rigid_and_plan_orientation_matches_top(self):
        xyz = cloud()
        positions, cameras, frame, room = sparse_room(xyz, [[0, 0, 0], [1, 0, 1]])
        self.assertAlmostEqual(
            np.linalg.norm(xyz[0] - xyz[1]), np.linalg.norm(positions[0] - positions[1])
        )
        self.assertIn("not a verified floor", frame["authority"])
        np.testing.assert_allclose(positions[:, [0, 2]], xyz[:, [0, 2]])
        self.assertEqual(room["objects"], [])
        self.assertIsNone(room["ceiling_reference"])
        self.assertFalse(room["scale_corrected"])
        np.testing.assert_allclose(cameras[:, [0, 2]], [[0, 0], [1, 1]])

    def test_insufficient_or_degenerate_cloud_does_not_publish_a_room(self):
        for xyz in (cloud()[:99], np.zeros((500, 3)), np.full((500, 3), np.nan)):
            with self.subTest(shape=xyz.shape), self.assertRaises(IngestionError):
                sparse_room(xyz, [[0, 0, 0]])

    def test_unsupported_capture_is_verified_only_and_stages_are_ordered(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            with (
                patch("cozmo_web.automatic.prepare_views") as prepare,
                patch("cozmo_web.automatic.reconstruct") as reconstruct,
            ):
                result = finish_automatically(
                    folder, Settings(), lambda _: None, {"manifest": {"adapter": "stray"}}
                )
                self.assertEqual(result["automatic_reconstruction"]["status"], "SKIPPED")
                prepare.assert_not_called()
                reconstruct.assert_not_called()
                events = []
                prepare.side_effect = lambda *_: (
                    events.append("prepare") or {"preprocessing": {"selected_count": 4}}
                )
                reconstruct.side_effect = lambda *_: (
                    events.append("reconstruct") or {"id": "new-result"}
                )
                result = finish_automatically(
                    folder, Settings(), lambda _: None, {"manifest": {"adapter": ADAPTER}}
                )
                self.assertEqual(events, ["prepare", "reconstruct"])
                self.assertEqual(result["automatic_reconstruction"]["status"], "SUCCEEDED")
                self.assertIn(
                    "preprocessing",
                    json.loads((folder / "result.json").read_text(encoding="utf-8")),
                )

    def test_failed_preprocessing_does_not_start_geometry(self):
        with tempfile.TemporaryDirectory() as temp:
            with (
                patch(
                    "cozmo_web.automatic.prepare_views", side_effect=WebError("BAD", "bad input")
                ),
                patch("cozmo_web.automatic.reconstruct") as reconstruct,
            ):
                with self.assertRaises(WebError):
                    finish_automatically(
                        Path(temp), Settings(), lambda _: None, {"manifest": {"adapter": ADAPTER}}
                    )
                reconstruct.assert_not_called()

    def test_retry_requires_prepared_capture_and_deduplicates_pending_requests(self):
        with tempfile.TemporaryDirectory() as temp:
            settings = Settings(data_root=Path(temp))
            repo = JobRepository(settings.data_root, 4)
            parent = repo.create("Room", None)
            repo.update(parent["id"], state="SUCCEEDED")
            with self.assertRaises(WebError):
                enqueue_reconstruction(repo, settings, parent["id"])
            write_json(repo.folder(parent["id"]) / "preprocessing/manifest.json", {})
            first = enqueue_reconstruction(repo, settings, parent["id"])
            second = enqueue_reconstruction(repo, settings, parent["id"])
            self.assertEqual(first["id"], second["id"])
            self.assertEqual(repo.get(parent["id"])["state"], "SUCCEEDED")
            repo.fail(first["id"], "INTERRUPTED", "Interrupted")
            self.assertNotEqual(
                enqueue_reconstruction(repo, settings, parent["id"])["id"], first["id"]
            )

    def test_publication_source_audit_failure_leaves_catalog_empty(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            request = ReconstructionRequest(root / "prepared", root / "bundle", root / "sparse")
            with patch(
                "cozmo_reconstruction.viewer.automatic.verify_reconstruction",
                side_effect=IngestionError("SOURCE_CHANGED", "source changed"),
            ):
                with self.assertRaises(IngestionError):
                    publish_sparse(request, root / "catalog/result", "Room")
            self.assertEqual(ReconstructionCatalog(root / "catalog").list(), [])

    def test_sparse_publication_is_portable_hash_checked_and_does_not_fake_dense_geometry(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            sparse = root / "sparse"
            write_lines(
                sparse / "points.jsonl",
                [{"xyz_m": p.tolist(), "rgb": [120, 140, 160]} for p in cloud()],
            )
            write_json(
                sparse / "cameras.json",
                [{"center_m": [0, 0, 0]}, {"center_m": [1, 0, 1]}, {"center_m": [2, 0, 2]}],
            )
            write_json(sparse / "report.json", {"geometry_signal": "WEAK"})
            from test_reconstruction_viewer import signed

            signed(sparse)
            request = ReconstructionRequest(root / "prepared", root / "bundle", sparse)
            output = root / "generated/new-room"
            with patch(
                "cozmo_reconstruction.viewer.automatic.verify_reconstruction",
                return_value={"status": "VERIFIED"},
            ) as audit:
                result = publish_sparse(request, output, "New room")
                self.assertEqual(audit.call_count, 2)
            self.assertEqual(result["geometry_source"], "CPU_SPARSE_TRIANGULATION")
            catalog = ReconstructionCatalog(root / "reviewed", output.parent)
            self.assertEqual(catalog.list()[0]["id"], "new-room")
            scene = json.loads((output / "scene.json").read_text(encoding="utf-8"))
            self.assertEqual(scene["reviewed_spans"], [])
            self.assertEqual(scene["floor_cells"], [])
            self.assertEqual(scene["point_count"] * 12, (output / "positions.bin").stat().st_size)
            (output / "colors.bin").write_bytes(b"changed")
            with self.assertRaises(WebError):
                catalog.read("new-room")

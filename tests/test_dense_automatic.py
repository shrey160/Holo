"""Dense admission, floor selection, and failure containment in automatic jobs."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    import fastapi  # noqa: F401
    import numpy as np
    import pycolmap  # noqa: F401
except ImportError as error:
    raise unittest.SkipTest("Install web and reconstruct extras") from error

from cozmo_ingestion.errors import IngestionError
from cozmo_ingestion.storage import sha256, write_json, write_lines
from cozmo_reconstruction.viewer.dense_automatic import dense_room
from cozmo_web.automatic import dense_available, dense_support_selection, execute_retry, reconstruct
from cozmo_web.config import Settings
from cozmo_web.errors import WebError
from cozmo_web.repository import JobRepository


class DenseAutomaticTests(unittest.TestCase):
    def test_failed_retry_retains_owned_verification_and_parent_result(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            settings = Settings(data_root=root)
            repo = JobRepository(root, 4)
            parent = repo.create("Room", None)
            source = repo.folder(parent["id"])
            result = {
                "verification": {"status": "PASSED"},
                "preprocessing": {"selected_count": 4},
                "reconstruction": {"id": "old"},
            }
            write_json(source / "result.json", result)
            write_json(source / "preprocessing/manifest.json", {})
            child = repo.create("Retry", None)
            repo.update(child["id"], parent_id=parent["id"])
            folder = repo.folder(child["id"])
            with (
                patch("cozmo_web.automatic.verify"),
                patch("cozmo_web.automatic.verify_preprocessing"),
                patch("cozmo_web.automatic.read_reference_image"),
                patch("cozmo_web.automatic.reconstruct", side_effect=RuntimeError("stereo failed")),
            ):
                with self.assertRaisesRegex(RuntimeError, "stereo failed"):
                    execute_retry(folder, settings, lambda _: None)
            import json

            self.assertEqual(
                json.loads((folder / "verification.json").read_text()), result["verification"]
            )
            self.assertNotIn("reconstruction", json.loads((folder / "result.json").read_text()))
            self.assertEqual(json.loads((source / "result.json").read_text()), result)

    def test_dense_selection_keeps_opening_support_and_excludes_isolated_view(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            write_json(root / "input_mapping.json", [{"rank": i} for i in (0, 15, 30, 1755)])
            write_lines(
                root / "points.jsonl", [{"observations": [{"rank": i} for i in (0, 15, 30)]}]
            )
            write_json(
                root / "manifest.json",
                {
                    "artifact_sha256": {
                        name: sha256(root / name) for name in ("input_mapping.json", "points.jsonl")
                    }
                },
            )
            self.assertEqual(dense_support_selection(root), ((0, 15, 30), [1755]))
            (root / "points.jsonl").write_text("[]\n", encoding="utf-8")
            with self.assertRaises(IngestionError):
                dense_support_selection(root)

    def test_required_dense_does_not_downgrade_or_modify_prepared_input(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            write_json(root / "job.json", {"reconstruction_mode": "dense"})
            write_json(root / "result.json", {"preprocessing": "retained"})
            before = (root / "result.json").read_bytes()
            phases = []
            with (
                patch("cozmo_web.automatic.backend_available", return_value=True),
                patch("cozmo_web.automatic.dense_available", return_value=False),
                patch("cozmo_reconstruction.viewer.automatic.publish_sparse") as sparse,
            ):
                with self.assertRaises(WebError) as caught:
                    reconstruct(root, Settings(), phases.append)
            self.assertEqual(caught.exception.code, "DENSE_CUDA_UNAVAILABLE")
            sparse.assert_not_called()
            self.assertEqual(phases, [])
            self.assertEqual((root / "result.json").read_bytes(), before)
            self.assertFalse((root / "viewer").exists())

    def test_cuda_compilation_without_device_is_not_dense_readiness(self):
        with (
            patch("pycolmap.has_cuda", False),
            patch("cozmo_reconstruction.dense.runtime.executable_path", return_value=None),
            patch("ctypes.CDLL") as driver,
        ):
            self.assertFalse(dense_available())
            driver.assert_not_called()

    def test_dense_failure_does_not_publish_sparse_success(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            write_json(root / "job.json", {"label": "Room"})
            write_json(root / "preprocessing/manifest.json", {"artifact_sha256": {}})
            phases = []
            with (
                patch("cozmo_web.automatic.backend_available", return_value=True),
                patch("cozmo_web.automatic.dense_available", return_value=True),
                patch("cozmo_web.automatic.verify_preprocessing"),
                patch("cozmo_web.automatic.dense_support_selection", return_value=((0, 1, 2), [])),
                patch("cozmo_web.automatic.sha256", return_value="test-source"),
                patch("cozmo_web.automatic.BundleIntegrity.path", return_value=root / "views"),
                patch(
                    "cozmo_web.automatic.lines",
                    return_value=[{"rank": i, "tracking_state": "normal"} for i in range(106)],
                ),
                patch("cozmo_reconstruction.ReconstructionPipeline.run") as sparse_run,
                patch(
                    "cozmo_reconstruction.dense.pipeline.DensePipeline.run",
                    side_effect=RuntimeError("stereo failed"),
                ),
                patch("cozmo_reconstruction.viewer.automatic.publish_sparse") as publish,
            ):
                with self.assertRaisesRegex(RuntimeError, "stereo failed"):
                    reconstruct(root, Settings(data_root=root), phases.append)
            request = sparse_run.call_args.args[0]
            self.assertEqual(len(request.ranks), 100)
            self.assertEqual(request.ranks[0], 0)
            self.assertEqual(request.ranks[-1], 105)
            self.assertEqual(phases, ["VERIFYING", "RECONSTRUCTING", "DENSE_RECONSTRUCTING"])
            publish.assert_not_called()
            self.assertFalse((root / "viewer").exists())

    def test_lowest_broad_supported_plane_wins_over_table_without_height_reference(self):
        # World Y is vertical; floor and table both have multiview evidence.
        x, z = np.meshgrid(np.linspace(0, 3, 45), np.linspace(0, 4, 45))
        floor = np.column_stack((x.ravel(), np.zeros(x.size), z.ravel()))
        table = floor + [0, 0.7, 0]
        xyz = np.concatenate((table, floor))
        labels = np.repeat([0, 1], len(floor))
        planes = [
            {
                "id": name,
                "orientation": "horizontal",
                "evidence_status": "MULTIVIEW_CANDIDATE",
                "median_camera_height_above_patch_m": height,
                "largest_patch_span_m": [3, 4],
                "equation_world": [0, 1, 0, offset],
            }
            for name, height, offset in (("table", 0.8, -0.7), ("floor", 1.5, 0))
        ]
        spans = [
            {"plane_id": str(i), "uv": segment}
            for i, segment in enumerate(
                ([[0, 0], [3, 0]], [[3, 0], [3, 4]], [[3, 4], [0, 4]], [[0, 4], [0, 0]])
            )
        ]
        with patch(
            "cozmo_reconstruction.viewer.dense_automatic.candidate_spans", return_value=spans
        ):
            _, _, frame, room, _ = dense_room(xyz, labels, planes, [{"center_m": [1, 1.5, 1]}])
        self.assertEqual(frame["source_plane_id"], "floor")
        self.assertFalse(room["scale_corrected"])
        self.assertIsNone(room["ceiling_reference"])
        self.assertEqual(room["objects"], [])
        self.assertFalse(room["ceiling_estimate"]["external_reference_used"])
        self.assertIsNone(room["ceiling_estimate"]["height_estimated_m"])

    def test_no_supported_floor_fails_instead_of_fabricating_height(self):
        with self.assertRaises(IngestionError) as caught:
            dense_room(np.zeros((10, 3)), np.zeros(10), [], [])
        self.assertEqual(caught.exception.code, "DENSE_FLOOR_UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()

"""The command delegates the live worker and protects existing captures."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cozmo_web.capture_cli import run_capture
from cozmo_web.config import Settings


class CaptureCliTests(unittest.TestCase):
    def test_worker_failure_is_visible_and_owned_input_remains(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            capture = root / "export.zip"
            capture.write_bytes(b"retained bytes")
            with patch("cozmo_web.capture_cli.execute", side_effect=RuntimeError("dense failed")):
                with self.assertRaisesRegex(RuntimeError, "dense failed"):
                    run_capture(capture, root / "run", Settings(data_root=root))
            self.assertEqual((root / "run/incoming/export.zip").read_bytes(), capture.read_bytes())
            self.assertEqual(json.loads((root / "run/phase.json").read_text())["state"], "FAILED")
            self.assertTrue(
                json.loads((root / "run/job.json").read_text())["automatic_reconstruction"]
            )
            with self.assertRaises(ValueError):
                run_capture(capture, root / "run", Settings(data_root=root))

    def test_mode_and_result_are_forwarded_without_geometry_substitution(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            capture = root / "export.zip"
            capture.write_bytes(b"original")

            def worker(folder, settings):
                self.assertEqual(settings.data_root, root)
                self.assertEqual(
                    json.loads((folder / "job.json").read_text())["reconstruction_mode"], "preview"
                )
                (folder / "result.json").write_text(
                    json.dumps(
                        {
                            "verification": {"status": "PASSED"},
                            "reconstruction": {"quality": "SPARSE_PREVIEW_ONLY"},
                        }
                    )
                )

            with patch("cozmo_web.capture_cli.execute", side_effect=worker) as called:
                result = run_capture(capture, root / "run", Settings(data_root=root), "preview")
            called.assert_called_once()
            self.assertEqual(result["reconstruction"]["quality"], "SPARSE_PREVIEW_ONLY")


if __name__ == "__main__":
    unittest.main()

"""Native CUDA admission and upload quality selection without a physical GPU."""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from test_web import WaitingRunner

from cozmo_reconstruction.dense.models import DensePolicy
from cozmo_reconstruction.dense.pipeline import backend
from cozmo_reconstruction.dense.runtime import _probe_executable, executable_path, runtime_status
from cozmo_web.app import create_app
from cozmo_web.config import Settings


class NativeDenseTests(unittest.TestCase):
    def test_worker_timeout_kills_native_child_tree(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            process = Mock(pid=12345)
            process.wait.side_effect = [subprocess.TimeoutExpired("worker", 30), None]
            with (
                patch("cozmo_reconstruction.dense.pipeline.subprocess.Popen", return_value=process),
                patch("cozmo_reconstruction.dense.pipeline.os.name", "nt"),
                patch("cozmo_reconstruction.dense.pipeline.subprocess.run") as kill,
            ):
                with self.assertRaisesRegex(ValueError, "exceeded 30s"):
                    backend(root, root, DensePolicy(timeout_seconds=30))
                kill.assert_called_once_with(
                    ["taskkill", "/PID", "12345", "/T", "/F"], capture_output=True, check=False
                )

    def test_only_pinned_cuda_executable_is_admitted(self):
        for header, accepted in (
            ("COLMAP 4.2.1 (Commit x with CUDA)", True),
            ("COLMAP 4.2.1 (Commit x without CUDA)", False),
            ("COLMAP 4.2.10 (Commit x with CUDA)", False),
            ("COLMAP 4.1.0 (Commit x with CUDA)", False),
        ):
            _probe_executable.cache_clear()
            with patch(
                "subprocess.run", return_value=subprocess.CompletedProcess([], 0, header, "")
            ):
                self.assertEqual(_probe_executable("colmap.exe", 1, 1), accepted)

    def test_probe_timeout_does_not_claim_available(self):
        _probe_executable.cache_clear()
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("colmap", 10)):
            self.assertFalse(_probe_executable("missing", 1, 1))

    def test_native_cli_requires_gpu_as_well_as_valid_build(self):
        with tempfile.TemporaryDirectory() as temp:
            executable = Path(temp) / "colmap.exe"
            executable.write_bytes(b"test build")
            with (
                patch("pycolmap.has_cuda", False),
                patch(
                    "cozmo_reconstruction.dense.runtime.executable_path", return_value=executable
                ),
                patch("cozmo_reconstruction.dense.runtime._probe_executable", return_value=True),
                patch(
                    "cozmo_reconstruction.dense.runtime.cuda_device_available", return_value=False
                ),
            ):
                self.assertFalse(runtime_status()["available"])
                with patch(
                    "cozmo_reconstruction.dense.runtime.cuda_device_available", return_value=True
                ):
                    self.assertEqual(
                        runtime_status(),
                        {"available": True, "backend": "colmap_executable", "reason": None},
                    )

    def test_explicit_invalid_executable_never_uses_another_installation(self):
        with patch.dict(os.environ, {"COLMAP_EXECUTABLE": "missing/colmap.exe"}):
            with patch("shutil.which") as which:
                self.assertEqual(executable_path(), Path("missing/colmap.exe").resolve())
                which.assert_not_called()

    def test_upload_dense_mode_is_persisted_and_unavailable_dense_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            app = create_app(Settings(data_root=Path(temp)), WaitingRunner())
            with TestClient(app) as client:
                with patch("cozmo_web.app.dense_available", return_value=False):
                    response = client.post(
                        "/api/jobs",
                        files={"files": ("capture.zip", b"zip")},
                        data={"reconstruction_mode": "dense"},
                    )
                    self.assertEqual(response.status_code, 503)
                    self.assertEqual(client.get("/api/jobs").json(), [])
                with patch("cozmo_web.app.dense_available", return_value=True):
                    response = client.post(
                        "/api/jobs",
                        files={"files": ("capture.zip", b"zip")},
                        data={"reconstruction_mode": "dense"},
                    )
                    self.assertEqual(response.status_code, 202)
                    job = client.get("/api/jobs/" + response.json()["id"]).json()
                    self.assertEqual(job["reconstruction_mode"], "dense")

    def test_upload_invalid_quality_is_rejected_before_creating_job(self):
        with tempfile.TemporaryDirectory() as temp:
            with TestClient(create_app(Settings(data_root=Path(temp)), WaitingRunner())) as client:
                response = client.post(
                    "/api/jobs",
                    files={"files": ("capture.zip", b"zip")},
                    data={"reconstruction_mode": "other"},
                )
                self.assertEqual(response.status_code, 400)
                self.assertEqual(client.get("/api/jobs").json(), [])

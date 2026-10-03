"""Behavioral web boundaries; use real filesystem transactions and injected runners."""

import io
import json
import os
import stat
import subprocess
import sys
import tempfile
import time
import unittest
import zipfile
from pathlib import Path

try:
    from fastapi.testclient import TestClient
except ImportError as error:
    raise unittest.SkipTest("Install the web extra to exercise HTTP tests") from error

from fixtures import FakeVideoInspector, fixture

from cozmo_ingestion import CaptureReader, IngestionPipeline, IngestionRequest
from cozmo_ingestion.errors import IngestionError
from cozmo_ingestion.storage import sha256, write_json, write_lines
from cozmo_ingestion.verification import verify
from cozmo_web.app import create_app
from cozmo_web.config import Settings
from cozmo_web.errors import WebError
from cozmo_web.exports import ExportService
from cozmo_web.repository import DataLock, JobRepository
from cozmo_web.runner import terminate_tree
from cozmo_web.schemas import Reference
from cozmo_web.uploads import prepare_capture, safe_name, unpack_archive


class WaitingRunner:
    def run(self, folder, repository, stop):
        stop.wait()
        repository.fail(folder.name, "INTERRUPTED", "Run interrupted")


class FailedRunner:
    def run(self, folder, repository, stop):
        raise OSError("disk failure")


def zipped(entries):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        for name, value in entries:
            archive.writestr(name, value)
    return stream.getvalue()


class WebTests(unittest.TestCase):
    def test_shutdown_terminates_child_process_tree(self):
        with tempfile.TemporaryDirectory() as temp:
            pid_file = Path(temp) / "child.pid"
            program = "import subprocess,sys,time; from pathlib import Path; p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(90)']); Path(sys.argv[1]).write_text(str(p.pid)); time.sleep(90)"
            options = (
                {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
                if os.name == "nt"
                else {"start_new_session": True}
            )
            parent = subprocess.Popen([sys.executable, "-c", program, str(pid_file)], **options)
            try:
                deadline = time.monotonic() + 5
                while not pid_file.exists() and time.monotonic() < deadline:
                    time.sleep(0.02)
                self.assertTrue(pid_file.exists())
                child_pid = int(pid_file.read_text())
                terminate_tree(parent)
                self.assertIsNotNone(parent.poll())
                if os.name == "nt":
                    import ctypes
                    from ctypes import wintypes

                    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
                    kernel.OpenProcess.restype = wintypes.HANDLE
                    kernel.GetExitCodeProcess.argtypes = [
                        wintypes.HANDLE,
                        ctypes.POINTER(wintypes.DWORD),
                    ]
                    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
                    handle = kernel.OpenProcess(0x1000, False, child_pid)
                    if handle:
                        code = wintypes.DWORD()
                        kernel.GetExitCodeProcess(handle, ctypes.byref(code))
                        kernel.CloseHandle(handle)
                        self.assertNotEqual(code.value, 259)
                else:
                    state_file = Path(f"/proc/{child_pid}/stat")
                    if state_file.exists():
                        self.assertEqual(state_file.read_text().split()[2], "Z")
            finally:
                terminate_tree(parent)

    def test_serialization_uses_portable_newlines(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "record.json"
            write_json(path, {"a": 1})
            self.assertNotIn(b"\r", path.read_bytes())
            write_lines(path, [{"a": 1}])
            self.assertEqual(path.read_bytes(), b'{"a": 1}\n')

    def test_archive_traversal_cross_platform_names_and_collisions(self):
        for name in (
            "../escape",
            "/absolute",
            "C:\\escape",
            "a/../escape",
            "CON.txt",
            "a./x",
            "a//b",
        ):
            with self.subTest(name=name), self.assertRaises(WebError):
                safe_name(name)
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / "input.zip"
            archive.write_bytes(zipped([("meta.json", "{}"), ("META.json", "{}")]))
            with self.assertRaises(WebError):
                unpack_archive(archive, Path(temp) / "raw", Settings())

    def test_archive_symlink_and_expansion_limit(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / "input.zip"
            with zipfile.ZipFile(archive, "w") as zip_file:
                entry = zipfile.ZipInfo("linked")
                entry.external_attr = (stat.S_IFLNK | 0o777) << 16
                zip_file.writestr(entry, "../elsewhere")
            with self.assertRaises(WebError):
                unpack_archive(archive, Path(temp) / "raw", Settings())
            archive.write_bytes(zipped([("large", "12345")]))
            with self.assertRaises(WebError):
                unpack_archive(archive, Path(temp) / "raw", Settings(expanded_limit=4))

    def test_archive_parent_case_collision_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / "input.zip"
            archive.write_bytes(zipped([("Session/meta.json", "{}"), ("session/wide.mp4", "data")]))
            with self.assertRaises(WebError):
                unpack_archive(archive, Path(temp) / "raw", Settings())

    def test_export_checks_annotation_and_legacy_windows_hints(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            raw = folder / "raw"
            fixture(raw)
            annotation = folder / "annotations/reference.json"
            write_json(
                annotation,
                Reference(width_cm=21, height_cm=29.7).annotation(sha256(raw / "wide.mp4")),
            )
            result = IngestionPipeline(video_inspector=FakeVideoInspector()).run(
                IngestionRequest(raw, folder / "bundle", annotation)
            )
            write_json(folder / "verification.json", verify(result.output, raw))
            archive = ExportService().archive(folder)
            self.assertTrue(archive.is_file())
            sources_path = result.output / "sources.json"
            sources = json.loads(sources_path.read_text())
            sources["root_hints"] = {
                key: value.replace("/", "\\") for key, value in sources["root_hints"].items()
            }
            write_json(sources_path, sources)
            result.manifest["artifact_sha256"]["sources.json"] = sha256(sources_path)
            write_json(result.output / "manifest.json", result.manifest)
            reader = CaptureReader(result.output)
            self.assertEqual(reader.read_source("wide.mp4"), (raw / "wide.mp4").read_bytes())
            annotation.write_text("{}")
            with self.assertRaises(IngestionError):
                ExportService().archive(folder)

    def test_wrapped_capture_preserves_bytes_and_rejects_multiple_sessions(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            original = root / "original"
            fixture(original)
            folder = root / "job"
            (folder / "incoming").mkdir(parents=True)
            archive = folder / "incoming/capture.zip"
            with zipfile.ZipFile(archive, "w") as zip_file:
                for path in original.rglob("*"):
                    if path.is_file():
                        zip_file.write(path, "session/" + path.relative_to(original).as_posix())
            raw = prepare_capture(folder, Settings())
            for path in original.rglob("*"):
                if path.is_file():
                    self.assertEqual(
                        path.read_bytes(), (raw / path.relative_to(original)).read_bytes()
                    )
            bad = root / "bad/incoming"
            bad.mkdir(parents=True)
            (bad / "capture.zip").write_bytes(
                zipped([("one/meta.json", "{}"), ("two/meta.json", "{}")])
            )
            with self.assertRaises(WebError):
                prepare_capture(bad.parent, Settings())

    def test_reference_binding_and_ordered_finite_values(self):
        reference = Reference(width_cm=21, height_cm=29.7)
        annotation = reference.annotation("hash")
        self.assertEqual(annotation["source_video_sha256"], "hash")
        self.assertEqual(annotation["reference_objects"][0]["height_m"], 0.297)
        self.assertFalse(annotation["reference_objects"][0]["visibility_verified"])
        for values in (
            {"width_cm": float("nan"), "height_cm": 20},
            {"width_cm": 20, "height_cm": 20, "start_seconds": 5, "end_seconds": 4},
        ):
            with self.assertRaises(ValueError):
                Reference(**values)

    def test_repository_lock_restart_and_queue_capacity(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            held = DataLock(root)
            try:
                with self.assertRaises(RuntimeError):
                    DataLock(root)
            finally:
                held.close()
            released = DataLock(root)
            released.close()
            repository = JobRepository(root, 1)
            first = repository.create("first", None)
            repository.update(first["id"], state="INGESTING")
            second = repository.create("second", None)
            repository.update(second["id"], state="QUEUED")
            with self.assertRaises(WebError):
                repository.create("overflow", None)
            repository.reconcile()
            self.assertEqual(repository.get(first["id"])["error"]["code"], "INTERRUPTED")
            self.assertEqual(repository.get(second["id"])["state"], "QUEUED")

    def test_api_rejects_unsafe_inputs_and_unready_download(self):
        with (
            tempfile.TemporaryDirectory() as temp,
            TestClient(create_app(Settings(data_root=Path(temp)), WaitingRunner())) as client,
        ):
            response = client.post("/api/jobs", files={"files": ("../bad.mp4", b"bytes")})
            self.assertEqual(response.status_code, 400)
            response = client.post(
                "/api/jobs",
                files={"files": ("capture.zip", b"bytes")},
                headers={"Origin": "https://example.com"},
            )
            self.assertEqual(response.status_code, 403)
            response = client.post(
                "/api/jobs",
                files={"files": ("capture.zip", b"bytes")},
                data={"reference": '{"width_cm":-1,"height_cm":20}'},
            )
            self.assertEqual(response.status_code, 400)
            response = client.post("/api/jobs", files={"files": ("capture.zip", b"bytes")})
            self.assertEqual(response.status_code, 202)
            job_id = response.json()["id"]
            self.assertEqual(client.get(f"/api/jobs/{job_id}/download").status_code, 409)
            self.assertEqual(client.get("/api/jobs/../../escape").status_code, 404)
            self.assertEqual(client.get("/api/not-a-route").status_code, 404)

    def test_request_limit_counts_body_without_content_length(self):
        with (
            tempfile.TemporaryDirectory() as temp,
            TestClient(
                create_app(Settings(data_root=Path(temp), request_limit=180), WaitingRunner())
            ) as client,
        ):
            response = client.post("/api/jobs", files={"files": ("capture.zip", b"x" * 200)})
            self.assertEqual(response.status_code, 413)
            body = (
                b'--abc\r\nContent-Disposition: form-data; name="files"; filename="capture.zip"\r\n\r\n'
                + b"x" * 200
                + b"\r\n--abc--\r\n"
            )
            response = client.post(
                "/api/jobs",
                content=iter([body[:100], body[100:]]),
                headers={"Content-Type": "multipart/form-data; boundary=abc"},
            )
            self.assertEqual(response.status_code, 413)

    def test_runner_failure_remains_failed_and_survives_restart(self):
        with tempfile.TemporaryDirectory() as temp:
            settings = Settings(data_root=Path(temp))
            with TestClient(create_app(settings, FailedRunner())) as client:
                job_id = client.post(
                    "/api/jobs", files={"files": ("capture.zip", b"bytes")}
                ).json()["id"]
                deadline = time.monotonic() + 3
                while time.monotonic() < deadline:
                    job = client.get(f"/api/jobs/{job_id}").json()
                    if job["state"] == "FAILED":
                        break
                    time.sleep(0.03)
                self.assertEqual(job["state"], "FAILED")
                self.assertEqual(client.get(f"/api/jobs/{job_id}/report").status_code, 409)
            with TestClient(create_app(settings, FailedRunner())) as client:
                self.assertEqual(client.get(f"/api/jobs/{job_id}").json()["state"], "FAILED")

    def test_health_missing_tools_and_static_ui(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            static = root / "static"
            static.mkdir()
            (static / "index.html").write_text("<title>Capture workspace</title>")
            with TestClient(
                create_app(
                    Settings(
                        data_root=root / "data", ffmpeg=str(root / "absent"), static_root=static
                    ),
                    WaitingRunner(),
                )
            ) as client:
                self.assertEqual(client.get("/api/health").status_code, 503)
                self.assertIn("Capture workspace", client.get("/").text)
                self.assertEqual(client.get("/api/jobs/no-such-id").status_code, 404)

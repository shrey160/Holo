"""Derived web-run admission, portable ownership, previews and export integrity."""

import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

try:
    import cv2  # noqa: F401
    from fastapi.testclient import TestClient
except ImportError as error:
    raise unittest.SkipTest("Install the web extra") from error

from fixtures import FakeVideoInspector, fixture
from test_preprocessing import SyntheticDecoder
from test_web import WaitingRunner

from cozmo_ingestion import IngestionPipeline, IngestionRequest
from cozmo_ingestion.storage import write_json
from cozmo_ingestion.verification import verify
from cozmo_web.app import create_app
from cozmo_web.config import Settings
from cozmo_web.preprocessing import enqueue_preprocessing, execute_preprocessing
from cozmo_web.repository import JobRepository


def parent_capture(repository):
    job = repository.create("Original capture", None)
    folder = repository.folder(job["id"])
    fixture(folder / "raw")
    result = IngestionPipeline(video_inspector=FakeVideoInspector()).run(
        IngestionRequest(folder / "raw", folder / "bundle")
    )
    audit = verify(folder / "bundle", folder / "raw")
    write_json(
        folder / "result.json",
        {"manifest": result.manifest, "validation": result.report, "verification": audit},
    )
    write_json(folder / "verification.json", audit)
    repository.update(job["id"], state="SUCCEEDED")
    return job["id"]


class PreprocessingWebTests(unittest.TestCase):
    def test_admission_queues_separate_run_and_rejects_unready_origin_and_stray(self):
        with tempfile.TemporaryDirectory() as temp:
            settings = Settings(data_root=Path(temp))
            app = create_app(settings, WaitingRunner())
            parent_id = parent_capture(app.state.repository)
            with TestClient(app) as client:
                denied = client.post(
                    f"/api/jobs/{parent_id}/preprocess", headers={"Origin": "https://example.com"}
                )
                self.assertEqual(denied.status_code, 403)
                response = client.post(f"/api/jobs/{parent_id}/preprocess")
                self.assertEqual(response.status_code, 202)
                child = client.get(f"/api/jobs/{response.json()['id']}").json()
                self.assertEqual(child["parent_id"], parent_id)
                self.assertEqual(child["operation"], "PREPROCESS")
                self.assertEqual(client.get(f"/api/jobs/{parent_id}").json()["state"], "SUCCEEDED")
                self.assertEqual(
                    client.post(f"/api/jobs/{child['id']}/preprocess").status_code, 409
                )
                path = app.state.repository.folder(parent_id) / "bundle/manifest.json"
                manifest = json.loads(path.read_text())
                manifest["adapter"] = "stray-layout-supplied-v1"
                write_json(path, manifest)
                self.assertEqual(client.post(f"/api/jobs/{parent_id}/preprocess").status_code, 400)

    def test_worker_copy_verification_preview_and_portable_export(self):
        with tempfile.TemporaryDirectory() as temp:
            settings = Settings(data_root=Path(temp))
            repository = JobRepository(settings.data_root, settings.queue_limit)
            parent_id = parent_capture(repository)
            parent = repository.folder(parent_id)
            original = (parent / "bundle/manifest.json").read_bytes()
            child = enqueue_preprocessing(repository, settings, parent_id)
            folder = repository.folder(child["id"])
            with patch("cozmo_preprocessing.media.FFmpegFrameDecoder", SyntheticDecoder):
                result = execute_preprocessing(folder, settings, lambda phase: None)
            self.assertEqual(result["preprocessing_verification"]["status"], "PASSED")
            self.assertEqual((parent / "bundle/manifest.json").read_bytes(), original)
            self.assertEqual(
                (folder / "raw/wide.mp4").read_bytes(), (parent / "raw/wide.mp4").read_bytes()
            )
            write_json(folder / "result.json", result)
            write_json(folder / "verification.json", result["verification"])
            repository.update(child["id"], state="SUCCEEDED")
            with TestClient(create_app(settings, WaitingRunner())) as client:
                base = f"/api/jobs/{child['id']}"
                self.assertEqual(client.get(base + "/previews/0").status_code, 200)
                self.assertEqual(client.get(base + "/previews/999").status_code, 404)
                self.assertEqual(client.get(base + "/preprocessing-report").status_code, 200)
                response = client.get(base + "/download")
                self.assertEqual(response.status_code, 200)
                import io

                with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
                    self.assertIsNone(archive.testzip())
                    self.assertIn("preprocessing/views.jsonl", archive.namelist())
                    self.assertEqual(
                        archive.read("raw/wide.mp4"), (parent / "raw/wide.mp4").read_bytes()
                    )
                (folder / "preprocessing/images/000000.jpg").write_bytes(b"changed")
                self.assertEqual(client.get(base + "/download").status_code, 409)
                self.assertEqual(client.get(base + "/preprocessing-report").status_code, 409)

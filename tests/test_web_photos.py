"""HTTP photo-tier boundaries: modality, room uploads, reference, downloads and guards."""

import io
import json
import tempfile
import time
import unittest
import zipfile
from pathlib import Path

try:
    from fastapi.testclient import TestClient
except ImportError as error:
    raise unittest.SkipTest("Install the web extra to exercise HTTP tests") from error

from multimodal_fixtures import build_tiff, jpeg_bytes, png_bytes

from cozmo_web.app import create_app
from cozmo_web.config import Settings
from cozmo_web.repository import summarize
from cozmo_web.worker import execute


class InlineRunner:
    """Run the real worker in-process so photo jobs reach a verified terminal state."""

    def __init__(self, settings):
        self.settings = settings

    def run(self, folder, repository, stop):
        execute(folder, self.settings)
        result = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        repository.update(folder.name, state="SUCCEEDED", summary=summarize(result))


class WaitingRunner:
    def run(self, folder, repository, stop):
        stop.wait()
        repository.fail(folder.name, "INTERRUPTED", "Run interrupted")


def zipped(entries):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        for name, value in entries:
            archive.writestr(name, value)
    return stream.getvalue()


def wait_until(client, job_id, deadline=15):
    end = time.monotonic() + deadline
    job = {}
    while time.monotonic() < end:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["state"] in {"SUCCEEDED", "FAILED"}:
            return job
        time.sleep(0.05)
    raise AssertionError(f"job did not finish: {job}")


class PhotoWebTests(unittest.TestCase):
    def test_photos_roundtrip_report_and_portable_download(self):
        with tempfile.TemporaryDirectory() as temp:
            settings = Settings(data_root=Path(temp))
            with TestClient(create_app(settings, InlineRunner(settings))) as client:
                response = client.post(
                    "/api/jobs",
                    data={"modality": "photos", "label": "Room 1"},
                    files=[
                        ("files", ("a.jpg", jpeg_bytes(), "image/jpeg")),
                        (
                            "files",
                            (
                                "b.jpg",
                                jpeg_bytes(
                                    tiff=build_tiff(datetime_original="2026:10:04 12:41:59")
                                ),
                                "image/jpeg",
                            ),
                        ),
                    ],
                )
                self.assertEqual(response.status_code, 202)
                job_id = response.json()["id"]
                job = wait_until(client, job_id)
                self.assertEqual(job["state"], "SUCCEEDED", job.get("error"))
                self.assertEqual(job["modality"], "photos")
                self.assertEqual(job["summary"]["room_count"], 1)
                self.assertEqual(job["summary"]["image_count"], 2)
                self.assertNotIn("reconstruction", job["summary"])

                report = client.get(f"/api/jobs/{job_id}/report")
                self.assertEqual(report.status_code, 200)
                self.assertEqual(report.json()["manifest"]["schema"], "canonical-capture-2")
                self.assertEqual(
                    report.json()["manifest"]["reconstruction"],
                    "NOT_IMPLEMENTED_FOR_MODALITY",
                )

                download = client.get(f"/api/jobs/{job_id}/download")
                self.assertEqual(download.status_code, 200)
                with zipfile.ZipFile(io.BytesIO(download.content)) as archive:
                    names = set(archive.namelist())
                    self.assertIn("bundle/sources/a.jpg", names)
                    self.assertIn("raw/a.jpg", names)
                    self.assertIn("verification.json", names)

                preprocess = client.post(f"/api/jobs/{job_id}/preprocess")
                self.assertEqual(preprocess.status_code, 409)
                self.assertEqual(preprocess.json()["error"]["code"], "NOT_IMPLEMENTED_FOR_MODALITY")

    def test_photos_room_paths_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            settings = Settings(data_root=Path(temp))
            with TestClient(create_app(settings, InlineRunner(settings))) as client:
                response = client.post(
                    "/api/jobs",
                    data={"modality": "photos"},
                    files=[
                        ("files", ("roomA/a.jpg", jpeg_bytes(), "image/jpeg")),
                        ("files", ("roomB/b.png", png_bytes(), "image/png")),
                    ],
                )
                self.assertEqual(response.status_code, 202)
                job = wait_until(client, response.json()["id"])
                self.assertEqual(job["state"], "SUCCEEDED", job.get("error"))
                self.assertEqual(job["summary"]["room_count"], 2)
                self.assertEqual(job["summary"]["image_count"], 2)

    def test_photos_zip_with_wrapping_directory_is_unwrapped(self):
        with tempfile.TemporaryDirectory() as temp:
            settings = Settings(data_root=Path(temp))
            payload = zipped(
                [
                    ("Room-1/a.jpg", jpeg_bytes()),
                    (
                        "Room-1/b.jpg",
                        jpeg_bytes(tiff=build_tiff(datetime_original="2026:10:04 12:41:59")),
                    ),
                ]
            )
            with TestClient(create_app(settings, InlineRunner(settings))) as client:
                response = client.post(
                    "/api/jobs",
                    data={"modality": "photos"},
                    files=[("files", ("photos.zip", payload, "application/zip"))],
                )
                self.assertEqual(response.status_code, 202)
                job = wait_until(client, response.json()["id"])
                self.assertEqual(job["state"], "SUCCEEDED", job.get("error"))
                self.assertEqual(job["summary"]["room_count"], 1)
                download = client.get(f"/api/jobs/{job['id']}/download")
                with zipfile.ZipFile(io.BytesIO(download.content)) as archive:
                    names = set(archive.namelist())
                    self.assertIn("bundle/sources/a.jpg", names)
                    self.assertIn("bundle/sources/b.jpg", names)

    def test_photos_heic_rejected_with_actionable_message(self):
        with tempfile.TemporaryDirectory() as temp:
            settings = Settings(data_root=Path(temp))
            with TestClient(create_app(settings, InlineRunner(settings))) as client:
                response = client.post(
                    "/api/jobs",
                    data={"modality": "photos"},
                    files=[("files", ("IMG_0001.heic", b"payload", "image/heic"))],
                )
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json()["error"]["code"], "UNSUPPORTED_IMAGE_FORMAT")

    def test_photos_reference_binds_without_scale(self):
        with tempfile.TemporaryDirectory() as temp:
            settings = Settings(data_root=Path(temp))
            with TestClient(create_app(settings, InlineRunner(settings))) as client:
                reference = json.dumps(
                    {
                        "object_id": "a4-reference-1",
                        "width_m": 0.21,
                        "height_m": 0.297,
                        "reference_asset": "a.jpg",
                        "candidate_assets": ["b.jpg"],
                    }
                )
                response = client.post(
                    "/api/jobs",
                    data={"modality": "photos", "reference": reference},
                    files=[
                        ("files", ("a.jpg", jpeg_bytes(), "image/jpeg")),
                        (
                            "files",
                            (
                                "b.jpg",
                                jpeg_bytes(
                                    tiff=build_tiff(datetime_original="2026:10:04 12:41:59")
                                ),
                                "image/jpeg",
                            ),
                        ),
                    ],
                )
                self.assertEqual(response.status_code, 202)
                job = wait_until(client, response.json()["id"])
                self.assertEqual(job["state"], "SUCCEEDED", job.get("error"))
                self.assertEqual(
                    job["summary"]["capabilities"]["reference_dimensions"], "USER_DECLARED"
                )
                folder = settings.data_root / "jobs" / job["id"]
                references = json.loads((folder / "bundle/references.json").read_text())
                self.assertFalse(references["scale_applied"])
                self.assertEqual(references["objects"][0]["id"], "a4-reference-1")
                self.assertEqual(references["objects"][0]["scale_status"], "NOT_APPLIED")
                self.assertIsNone(references["objects"][0]["corners"])

    def test_video_is_the_default_modality(self):
        with tempfile.TemporaryDirectory() as temp:
            settings = Settings(data_root=Path(temp))
            with TestClient(create_app(settings, WaitingRunner())) as client:
                response = client.post(
                    "/api/jobs", files=[("files", ("capture.zip", b"bytes", "application/zip"))]
                )
                self.assertEqual(response.status_code, 202)
                job = client.get(f"/api/jobs/{response.json()['id']}").json()
                self.assertEqual(job["modality"], "video")


if __name__ == "__main__":
    unittest.main()

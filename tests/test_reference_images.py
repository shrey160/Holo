"""Reference-photo transport, source binding and download integrity."""

import asyncio
import io
import json
import struct
import subprocess
import tempfile
import unittest
import zipfile
import zlib
from pathlib import Path
from unittest.mock import patch

try:
    from fastapi.testclient import TestClient
    from starlette.datastructures import UploadFile
except ImportError as error:
    raise unittest.SkipTest("Install the web extra to exercise reference photos") from error

from fixtures import FakeVideoInspector, fixture
from test_web import WaitingRunner

from cozmo_ingestion import IngestionPipeline, IngestionRequest
from cozmo_ingestion.storage import sha256, write_json
from cozmo_ingestion.verification import verify
from cozmo_web.app import create_app
from cozmo_web.config import Settings
from cozmo_web.errors import WebError
from cozmo_web.exports import ExportService
from cozmo_web.reference_images import (
    bind_reference_image,
    read_reference_image,
    save_reference_image,
)


def png_photo() -> bytes:
    def chunk(kind, data):
        return (
            struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 4, 6, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress((b"\0" + b"\xff\xff\xff" * 4) * 6))
        + chunk(b"IEND", b"")
    )


class ReferenceImageTests(unittest.TestCase):
    def test_reference_photo_is_separate_optional_upload(self):
        with (
            tempfile.TemporaryDirectory() as temp,
            TestClient(create_app(Settings(data_root=Path(temp)), WaitingRunner())) as client,
        ):
            photo = png_photo()
            response = client.post(
                "/api/jobs",
                files=[
                    ("files", ("capture.zip", b"zip")),
                    ("reference_image", ("paper.png", photo, "image/png")),
                ],
            )
            self.assertEqual(response.status_code, 202)
            job_id = response.json()["id"]
            folder = Path(temp) / "jobs" / job_id
            self.assertEqual((folder / "reference/object.png").read_bytes(), photo)
            self.assertEqual([p.name for p in (folder / "incoming").iterdir()], ["capture.zip"])
            self.assertIsNone(client.get(f"/api/jobs/{job_id}").json()["reference"])
            self.assertEqual(client.get(f"/api/jobs/{job_id}/reference-image").status_code, 409)

    def test_reference_photo_rejects_disguised_files_and_size_overflow(self):
        for name, contents, status in (
            ("object.svg", b"<svg/>", 400),
            ("object.png", b"<html/>", 400),
            ("object.jpg", b"\xff\xd8\xff" + b"x" * (10 * 1024**2), 413),
        ):
            with tempfile.TemporaryDirectory() as temp:
                upload_file = UploadFile(io.BytesIO(contents), filename=name)
                with self.assertRaises(WebError) as error:
                    asyncio.run(save_reference_image(upload_file, Path(temp)))
                self.assertEqual(error.exception.status, status)

    def test_reference_photo_binding_export_and_tamper_detection(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            raw = folder / "raw"
            fixture(raw)
            photo = png_photo()
            image = asyncio.run(
                save_reference_image(UploadFile(io.BytesIO(photo), filename="paper.png"), folder)
            )
            write_json(folder / "job.json", {"reference_image": image})
            probe = subprocess.CompletedProcess(
                [], 0, json.dumps({"streams": [{"width": 4, "height": 6, "codec_name": "png"}]}), ""
            )
            decode = subprocess.CompletedProcess([], 0, b"", b"")
            with (
                patch(
                    "cozmo_web.reference_images.find_ffmpeg",
                    return_value=(Path("ffmpeg"), Path("ffprobe")),
                ),
                patch("cozmo_web.reference_images.subprocess.run", side_effect=[probe, decode]),
            ):
                bound = bind_reference_image(folder, sha256(raw / "wide.mp4"), Settings())
            self.assertEqual(bound["source_video_sha256"], sha256(raw / "wide.mp4"))
            write_json(folder / "job.json", {"reference_image": bound})
            result = IngestionPipeline(video_inspector=FakeVideoInspector()).run(
                IngestionRequest(raw, folder / "bundle")
            )
            write_json(folder / "verification.json", verify(result.output, raw))
            with zipfile.ZipFile(ExportService().archive(folder)) as archive:
                self.assertEqual(archive.read("reference/object.png"), photo)
                self.assertIn("reference/metadata.json", archive.namelist())
            self.assertEqual(read_reference_image(folder)[0].read_bytes(), photo)
            (folder / "reference/object.png").write_bytes(photo + b"changed")
            with self.assertRaises(WebError):
                ExportService().archive(folder)

    def test_reference_photo_rejects_invalid_decode_and_large_grid(self):
        for grid, invalid_decode in (([100000, 100000], False), ([4, 6], True)):
            with tempfile.TemporaryDirectory() as temp:
                folder = Path(temp)
                image = asyncio.run(
                    save_reference_image(
                        UploadFile(io.BytesIO(png_photo()), filename="paper.png"), folder
                    )
                )
                write_json(folder / "job.json", {"reference_image": image})
                probe = subprocess.CompletedProcess(
                    [],
                    0,
                    json.dumps(
                        {"streams": [{"width": grid[0], "height": grid[1], "codec_name": "png"}]}
                    ),
                    "",
                )
                calls = [probe]
                if invalid_decode:
                    calls.append(subprocess.CalledProcessError(1, ["ffmpeg"]))
                with (
                    patch(
                        "cozmo_web.reference_images.find_ffmpeg",
                        return_value=(Path("ffmpeg"), Path("ffprobe")),
                    ),
                    patch("cozmo_web.reference_images.subprocess.run", side_effect=calls),
                    self.assertRaises(WebError),
                ):
                    bind_reference_image(folder, "video-hash", Settings())

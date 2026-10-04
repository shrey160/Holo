"""Canonical-capture-2 foundation and photo-ingestion behavior checks."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from fixtures import FakeVideoInspector, fixture
from multimodal_fixtures import build_tiff, jpeg_bytes, png_bytes, write_room

from cozmo_ingestion import CaptureReader, IngestionError, IngestionPipeline, IngestionRequest
from cozmo_ingestion.multimodal.contracts import MODE_PHOTOS, MODE_VIDEO, MultimodalRequest
from cozmo_ingestion.multimodal.media import DefaultImageInspector
from cozmo_ingestion.multimodal.pipeline import PhotosIngestionPipeline
from cozmo_ingestion.multimodal.reader import MultimodalCaptureReader, open_capture
from cozmo_ingestion.multimodal.schema import safe_relative_path, validate_bundle_documents
from cozmo_ingestion.multimodal.verify import verify_v2


def room_request(source, output, **kwargs):
    return MultimodalRequest(source, output, MODE_PHOTOS, **kwargs)


class PhotoIngestionTests(unittest.TestCase):
    def test_exif_is_recorded_without_scale_or_invented_camera(self):
        with tempfile.TemporaryDirectory() as temp:
            raw = Path(temp) / "raw"
            write_room(
                raw,
                "",
                {
                    "20261004_124156.jpg": jpeg_bytes(4000, 3000, build_tiff(orientation=6)),
                    "20261004_124159.jpg": jpeg_bytes(4000, 3000, build_tiff(orientation=6)),
                },
            )
            out = Path(temp) / "out"
            result = PhotosIngestionPipeline().run(room_request(raw, out))
            reader = MultimodalCaptureReader(out)
            asset = reader.assets()[0]
            self.assertEqual((asset["width_px"], asset["height_px"]), (4000, 3000))
            self.assertEqual(asset["orientation"], 6)
            self.assertEqual(asset["exif"]["make"], "samsung")
            self.assertEqual(asset["exif"]["focal_length_35mm_mm"], 23)
            self.assertFalse(reader.references()["scale_applied"])
            self.assertEqual(reader.capabilities["camera_intrinsics"], "ABSENT")
            self.assertEqual(reader.capabilities["poses"], "ABSENT")
            self.assertEqual(reader.capabilities["rgb"], "VERIFIED_FORMAT")
            for row in reader.observations:
                self.assertIsNone(row["camera_K_ref"])
                self.assertIsNone(row["pose_ref"])
                self.assertEqual(row["processing_eligibility"], "INGESTION_ONLY")
            self.assertEqual(len(reader._read_lines("calibration.jsonl")), 0)
            self.assertEqual(len(reader._read_lines("poses.jsonl")), 0)
            self.assertEqual(result.manifest["preprocessing"], "NOT_IMPLEMENTED_FOR_MODALITY")

    def test_no_exif_png_is_acceptable(self):
        with tempfile.TemporaryDirectory() as temp:
            raw, out = Path(temp) / "raw", Path(temp) / "out"
            write_room(raw, "", {"a.png": png_bytes(), "b.png": png_bytes(color=(1, 2, 3))})
            result = PhotosIngestionPipeline().run(room_request(raw, out))
            codes = {finding["code"] for finding in result.report["findings"]}
            self.assertIn("MISSING_EXIF", codes)
            self.assertEqual(result.manifest["capabilities"]["exif"], "ABSENT")
            self.assertEqual(result.manifest["status"], "READY_WITH_FINDINGS")

    def test_corrupt_image_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            raw, out = Path(temp) / "raw", Path(temp) / "out"
            write_room(raw, "", {"a.jpg": b"\xff\xd8\xff\xe0\x00\x20short"})
            with self.assertRaises(IngestionError) as caught:
                PhotosIngestionPipeline().run(room_request(raw, out))
            self.assertEqual(caught.exception.code, "CORRUPT_IMAGE")
            self.assertFalse(out.exists())

    def test_unsupported_phone_format_is_rejected_not_converted(self):
        with tempfile.TemporaryDirectory() as temp:
            raw, out = Path(temp) / "raw", Path(temp) / "out"
            write_room(raw, "", {"IMG_0001.heic": b"heic payload", "a.jpg": jpeg_bytes()})
            with self.assertRaises(IngestionError) as caught:
                PhotosIngestionPipeline().run(room_request(raw, out))
            self.assertEqual(caught.exception.code, "UNSUPPORTED_IMAGE_FORMAT")

    def test_duplicate_bytes_share_asset_identity(self):
        with tempfile.TemporaryDirectory() as temp:
            raw, out = Path(temp) / "raw", Path(temp) / "out"
            payload = png_bytes(color=(7, 8, 9))
            write_room(raw, "", {"copy-a.png": payload, "copy-b.png": payload})
            result = PhotosIngestionPipeline().run(room_request(raw, out))
            self.assertEqual(result.manifest["image_count"], 2)
            self.assertEqual(result.manifest["distinct_image_count"], 1)
            codes = {finding["code"] for finding in result.report["findings"]}
            self.assertIn("DUPLICATE_IMAGE_CONTENT", codes)

    def test_filename_exif_time_discrepancy_is_recorded(self):
        with tempfile.TemporaryDirectory() as temp:
            raw, out = Path(temp) / "raw", Path(temp) / "out"
            tiff = build_tiff(datetime_original="2026:10:04 12:42:05")
            write_room(
                raw,
                "",
                {
                    "20261004_124206.jpg": jpeg_bytes(tiff=tiff),
                    "scene.jpg": jpeg_bytes(tiff=build_tiff()),
                },
            )
            result = PhotosIngestionPipeline().run(room_request(raw, out))
            mismatches = [
                f
                for f in result.report["findings"]
                if f["code"] == "FILENAME_EXIF_TIME_DISCREPANCY"
            ]
            self.assertEqual(len(mismatches), 1)
            self.assertEqual(mismatches[0]["details"]["filename_time"], "2026-10-04T12:42:06")

    def test_out_of_profile_counts_are_flagged_but_retained(self):
        with tempfile.TemporaryDirectory() as temp:
            raw, out = Path(temp) / "raw", Path(temp) / "out"
            write_room(raw, "", {"only.png": png_bytes()})
            result = PhotosIngestionPipeline().run(room_request(raw, out))
            self.assertEqual(result.manifest["profile"], "OUTSIDE_PHOTO_PROFILE")
            self.assertIn("OUTSIDE_PHOTO_PROFILE", {f["code"] for f in result.report["findings"]})

    def test_multi_room_membership_derived_from_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            raw, out = Path(temp) / "raw", Path(temp) / "out"
            write_room(
                raw,
                "roomA",
                {"a1.png": png_bytes(color=(1, 0, 0)), "a2.png": png_bytes(color=(2, 0, 0))},
            )
            write_room(raw, "roomB", {"b1.png": png_bytes(color=(3, 0, 0))})
            result = PhotosIngestionPipeline().run(room_request(raw, out))
            reader = MultimodalCaptureReader(out)
            self.assertEqual(result.manifest["room_count"], 2)
            self.assertEqual(reader.rooms_doc["membership"], "DERIVED_FROM_PATHS")
            labels = {room["label"] for room in reader.rooms()}
            self.assertEqual(labels, {"roomA", "roomB"})

    def test_reference_declaration_is_bound_without_applying_scale(self):
        with tempfile.TemporaryDirectory() as temp:
            raw, out = Path(temp) / "raw", Path(temp) / "out"
            write_room(
                raw,
                "",
                {
                    "a.jpg": jpeg_bytes(),
                    "b.jpg": jpeg_bytes(tiff=build_tiff(datetime_original="2026:10:04 12:41:59")),
                },
            )
            reference = Path(temp) / "reference.json"
            reference.write_text(
                json.dumps(
                    {
                        "object_id": "a4-reference-1",
                        "width_m": 0.21,
                        "height_m": 0.297,
                        "reference_asset": "a.jpg",
                        "candidate_assets": ["b.jpg"],
                    }
                )
            )
            result = PhotosIngestionPipeline().run(room_request(raw, out, reference=reference))
            reader = MultimodalCaptureReader(out)
            objects = reader.references()["objects"]
            self.assertEqual(len(objects), 1)
            self.assertEqual(objects[0]["id"], "a4-reference-1")
            self.assertEqual((objects[0]["width_m"], objects[0]["height_m"]), (0.21, 0.297))
            self.assertEqual(objects[0]["scale_status"], "NOT_APPLIED")
            self.assertIsNone(objects[0]["corners"])
            self.assertIsNotNone(objects[0]["reference_asset_id"])
            self.assertFalse(reader.references()["scale_applied"])
            self.assertEqual(
                result.manifest["capabilities"]["reference_dimensions"], "USER_DECLARED"
            )

    def test_unknown_reference_asset_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            raw, out = Path(temp) / "raw", Path(temp) / "out"
            write_room(
                raw,
                "",
                {
                    "a.jpg": jpeg_bytes(),
                    "b.jpg": jpeg_bytes(tiff=build_tiff(datetime_original="x")),
                },
            )
            reference = Path(temp) / "reference.json"
            reference.write_text(
                json.dumps(
                    {
                        "object_id": "a4-reference-1",
                        "width_m": 0.21,
                        "height_m": 0.297,
                        "reference_asset": "missing.jpg",
                    }
                )
            )
            with self.assertRaises(IngestionError) as caught:
                PhotosIngestionPipeline().run(room_request(raw, out, reference=reference))
            self.assertEqual(caught.exception.code, "UNKNOWN_REFERENCE_ASSET")

    def test_source_mutation_during_ingestion_is_rejected(self):
        class MutatingInspector(DefaultImageInspector):
            def inspect(self, path):
                result = super().inspect(path)
                path.write_bytes(path.read_bytes() + b"\x00")
                return result

        with tempfile.TemporaryDirectory() as temp:
            raw, out = Path(temp) / "raw", Path(temp) / "out"
            write_room(raw, "", {"a.jpg": jpeg_bytes(), "b.png": png_bytes()})
            with self.assertRaises(IngestionError) as caught:
                PhotosIngestionPipeline(inspector=MutatingInspector()).run(room_request(raw, out))
            self.assertEqual(caught.exception.code, "SOURCE_CHANGED")
            self.assertFalse(out.exists())

    def test_deterministic_manifest_and_portable_verification(self):
        with tempfile.TemporaryDirectory() as temp:
            raw = Path(temp) / "raw"
            write_room(raw, "", {"a.jpg": jpeg_bytes(), "b.png": png_bytes()})
            first, second = Path(temp) / "first", Path(temp) / "second"
            one = PhotosIngestionPipeline().run(room_request(raw, first))
            two = PhotosIngestionPipeline().run(room_request(raw, second))
            self.assertEqual(one.manifest, two.manifest)
            portable = Path(temp) / "portable"
            shutil.copytree(first, portable)
            summary = verify_v2(portable)
            self.assertEqual(summary["status"], "PASSED")
            self.assertTrue(summary["portable_bundle_verified"])
            source_file = next((portable / "sources").rglob("*.jpg"))
            source_file.write_bytes(source_file.read_bytes() + b"tamper")
            with self.assertRaises(IngestionError):
                verify_v2(portable)

    def test_output_inside_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            raw = Path(temp) / "raw"
            write_room(raw, "", {"a.jpg": jpeg_bytes(), "b.png": png_bytes()})
            with self.assertRaises(IngestionError) as caught:
                PhotosIngestionPipeline().run(room_request(raw, raw / "derived"))
            self.assertEqual(caught.exception.code, "OUTPUT_SOURCE_OVERLAP")

    def test_non_photo_mode_is_not_implemented(self):
        with tempfile.TemporaryDirectory() as temp:
            raw = Path(temp) / "raw"
            write_room(raw, "", {"a.jpg": jpeg_bytes()})
            request = MultimodalRequest(raw, Path(temp) / "out", MODE_VIDEO)
            with self.assertRaises(IngestionError) as caught:
                PhotosIngestionPipeline().run(request)
            self.assertEqual(caught.exception.code, "NOT_IMPLEMENTED_FOR_MODALITY")


class FoundationTests(unittest.TestCase):
    def test_unknown_schema_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / "bundle"
            folder.mkdir()
            (folder / "manifest.json").write_text(json.dumps({"schema": "canonical-capture-9"}))
            with self.assertRaises(IngestionError) as caught:
                open_capture(folder)
            self.assertEqual(caught.exception.code, "UNKNOWN_SCHEMA")

    def test_v1_bundle_still_dispatches_and_verifies(self):
        with tempfile.TemporaryDirectory() as temp:
            raw, out = Path(temp) / "raw", Path(temp) / "out"
            fixture(raw)
            IngestionPipeline(video_inspector=FakeVideoInspector()).run(IngestionRequest(raw, out))
            reader = open_capture(out)
            self.assertIsInstance(reader, CaptureReader)
            self.assertEqual(reader.verify_bundle(), len(reader.hashes))

    def test_referential_integrity_and_safe_paths(self):
        rooms = {
            "property_id": "p",
            "membership": "DERIVED_FROM_PATHS",
            "rooms": [
                {
                    "id": "room-1",
                    "label": "Room",
                    "source_path": ".",
                    "declared_connection_ids": [],
                    "image_count": 1,
                }
            ],
            "declared_connections": [],
        }
        assets = {
            "assets": [
                {
                    "id": "asset-1",
                    "role": "scene_photo",
                    "sha256": "a" * 64,
                    "bytes": 1,
                    "media_format": "jpeg",
                    "width_px": 1,
                    "height_px": 1,
                    "decode": "STRUCTURE_VERIFIED",
                    "source_paths": ["a.jpg"],
                    "room_ids": ["room-1"],
                }
            ]
        }
        observation = {
            "id": "obs-1",
            "asset_id": "asset-1",
            "room_id": "room-1",
            "source_path": "a.jpg",
            "native_frame_id": "a.jpg",
            "pixel_grid": [1, 1],
            "camera_K_ref": None,
            "pose_ref": None,
            "processing_eligibility": "INGESTION_ONLY",
        }
        references = {"scale_applied": False, "objects": []}
        validate_bundle_documents(rooms, assets, [observation], references, [])
        with self.assertRaises(IngestionError) as caught:
            validate_bundle_documents(
                rooms, assets, [{**observation, "asset_id": "asset-9"}], references, []
            )
        self.assertEqual(caught.exception.code, "DANGLING_ASSET_LINK")
        with self.assertRaises(IngestionError):
            validate_bundle_documents(
                rooms, assets, [{**observation, "source_path": "../escape.jpg"}], references, []
            )
        with self.assertRaises(IngestionError) as caught:
            validate_bundle_documents(
                rooms, assets, [observation, dict(observation)], references, []
            )
        self.assertEqual(caught.exception.code, "DUPLICATE_ID")
        with self.assertRaises(IngestionError):
            safe_relative_path("room/../escape")

    def test_missing_manifest_reports_cleanly(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(IngestionError) as caught:
                open_capture(Path(temp))
            self.assertEqual(caught.exception.code, "MISSING_MANIFEST")


class RealRoomOneTests(unittest.TestCase):
    ROOM = Path(__file__).resolve().parents[2] / "test_data" / "Room-1"

    @unittest.skipUnless(ROOM.is_dir(), "test_data/Room-1 is not present")
    def test_read_only_ingestion_preserves_all_eight_photos(self):
        originals = {path.name: path.read_bytes() for path in sorted(self.ROOM.iterdir())}
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "room1"
            result = PhotosIngestionPipeline().run(
                room_request(self.ROOM, out, room_label="Room 1")
            )
            reader = MultimodalCaptureReader(out)
            self.assertEqual(result.manifest["distinct_image_count"], 8)
            self.assertEqual(result.manifest["image_count"], 8)
            self.assertEqual(result.manifest["room_count"], 1)
            for asset in reader.assets():
                self.assertEqual((asset["width_px"], asset["height_px"]), (4000, 3000))
                self.assertEqual(asset["orientation"], 6)
                self.assertEqual(asset["exif"]["model"], "Galaxy S24")
            summary = verify_v2(out, self.ROOM)
            self.assertEqual(summary["originals_reverified"], 8)
            self.assertTrue(summary["scale_applied"] is False)
        self.assertEqual(
            {path.name: path.read_bytes() for path in sorted(self.ROOM.iterdir())}, originals
        )


if __name__ == "__main__":
    unittest.main()

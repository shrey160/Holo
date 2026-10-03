"""reader behavioral checks."""

import tempfile
from pathlib import Path

from fixtures import FixtureTestCase, fixture

from cozmo_ingestion import CaptureReader, IngestionError
from cozmo_ingestion.verification import verify


class Tests(FixtureTestCase):
    def test_rgb_and_assisted_readers_deny_reference_leakage(self):
        with tempfile.TemporaryDirectory() as temp:
            raw, out = Path(temp) / "raw", Path(temp) / "out"
            fixture(raw)
            self.run_fixture(raw, out)
            reader = CaptureReader(out)
            for asset in ["depth/0001.bin", "references/laser.csv"]:
                with self.assertRaises(IngestionError):
                    reader.read_source(asset)
            rgb = CaptureReader(out, "video_rgb")
            for kind in ["poses", "calibration", "annotations", "accelerometer"]:
                with self.assertRaises(IngestionError):
                    rgb.records(kind)
            self.assertNotIn("sensor_seconds", rgb.records("frames")[0])
            self.assertNotIn("pose_id", rgb.records("frames")[0])
            self.assertTrue(rgb.read_source("wide.mp4"))

    def test_reader_detects_artifact_and_source_modification(self):
        with tempfile.TemporaryDirectory() as temp:
            raw, out = Path(temp) / "raw", Path(temp) / "out"
            fixture(raw)
            self.run_fixture(raw, out)
            reader = CaptureReader(out)
            reader.records("calibration")
            (out / "calibration.jsonl").write_text("{}\n")
            with self.assertRaises(IngestionError):
                reader.records("calibration")
            (raw / "wide.mp4").write_bytes(b"changed")
            with self.assertRaises(IngestionError):
                reader.read_source("wide.mp4")

    def test_moved_bundle_accepts_explicit_verified_source_root(self):
        with tempfile.TemporaryDirectory() as temp:
            raw, out = Path(temp) / "raw", Path(temp) / "out"
            fixture(raw)
            self.run_fixture(raw, out)
            nested = Path(temp) / "new-location"
            nested.mkdir()
            moved = out.rename(nested / "capture")
            reader = CaptureReader(moved, source_root=raw)
            self.assertTrue(reader.read_source("wide.mp4"))
            self.assertEqual(verify(moved, raw)["status"], "PASSED")

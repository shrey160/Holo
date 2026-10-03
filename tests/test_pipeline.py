"""pipeline behavioral checks."""

import json
import tempfile
from pathlib import Path

from fixtures import FakeVideoInspector, FixtureTestCase, fixture, media

from cozmo_ingestion import CaptureReader, IngestionError, IngestionPipeline, IngestionRequest
from cozmo_ingestion.bundle import BundleWriter
from cozmo_ingestion.storage import sha256
from cozmo_ingestion.verification import verify


class Tests(FixtureTestCase):
    def test_complete_ingestion_preserves_raw_units_preroll_and_limited_rows(self):
        with tempfile.TemporaryDirectory() as temp:
            raw, out = Path(temp) / "raw", Path(temp) / "out"
            fixture(raw)
            manifest, report = self.run_fixture(raw, out)
            reader = CaptureReader(out)
            accel = reader.records("accelerometer")
            self.assertEqual(accel[0]["az_m_s2"], "9.80665")
            self.assertEqual(accel[0]["relative_seconds"], "-0.000010")
            frames = reader.records("frames")
            self.assertEqual(len(frames), 2)
            self.assertEqual(frames[0]["tracking_state"], "limited")
            self.assertEqual(frames[0]["pose_tracking_normal"], "False")
            self.assertEqual([p["source_frame_index"] for p in reader.records("poses")], [0, 1])
            self.assertFalse(manifest["scale"]["correction_applied"])
            self.assertFalse(report["readiness"]["raw_IMU_VIO"])
            self.assertEqual(verify(out, raw)["status"], "PASSED")

    def test_deterministic_replay_and_no_output_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            raw = Path(temp) / "raw"
            fixture(raw)
            a, b = Path(temp) / "a", Path(temp) / "b"
            self.run_fixture(raw, a)
            self.run_fixture(raw, b)
            self.assertTrue(verify(a, raw, b)["deterministic_replay_equal"])
            original = sha256(a / "manifest.json")
            with self.assertRaises(IngestionError):
                self.run_fixture(raw, a)
            self.assertEqual(sha256(a / "manifest.json"), original)
            with self.assertRaises(IngestionError):
                self.run_fixture(raw, raw / "derived")

    def test_missing_required_stream_leaves_failed_diagnostics(self):
        with tempfile.TemporaryDirectory() as temp:
            raw, out = Path(temp) / "raw", Path(temp) / "out"
            fixture(raw)
            (raw / "accelerometer.csv").unlink()
            with self.assertRaises(IngestionError):
                self.run_fixture(raw, out)
            self.assertFalse(out.exists())
            failed = list(Path(temp).glob("out.ingest-*/manifest.json"))
            self.assertEqual(json.loads(failed[0].read_text())["status"], "FAILED")
            with self.assertRaises(IngestionError):
                CaptureReader(failed[0].parent)

    def test_source_changed_during_ingestion_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            raw, out = Path(temp) / "raw", Path(temp) / "out"
            fixture(raw)

            def changing(*args):
                (raw / "wide.mp4").write_bytes(b"changed during probe")
                return media()

            inspector = FakeVideoInspector(on_inspect=changing)
            with self.assertRaises(IngestionError) as caught:
                IngestionPipeline(video_inspector=inspector).run(IngestionRequest(raw, out))
            self.assertEqual(caught.exception.code, "SOURCE_CHANGED")
            self.assertFalse(out.exists())

    def test_one_pipeline_reused_for_independent_transactions(self):
        with tempfile.TemporaryDirectory() as temp:
            raw = Path(temp) / "raw"
            fixture(raw)
            pipeline = IngestionPipeline(video_inspector=FakeVideoInspector())
            first = pipeline.run(IngestionRequest(raw, Path(temp) / "first"))
            second = pipeline.run(IngestionRequest(raw, Path(temp) / "second"))
            self.assertEqual(first.manifest, second.manifest)
            self.assertEqual(first.report, second.report)

    def test_storage_failure_cannot_publish_partial_bundle(self):
        class FailingWriter(BundleWriter):
            def write(self, stage, content, runtime):
                (stage / "partial.txt").write_text("partial write")
                raise OSError("simulated disk failure")

        with tempfile.TemporaryDirectory() as temp:
            raw, out = Path(temp) / "raw", Path(temp) / "out"
            fixture(raw)
            before = sha256(raw / "wide.mp4")
            pipeline = IngestionPipeline(
                video_inspector=FakeVideoInspector(), writer=FailingWriter()
            )
            with self.assertRaises(IngestionError) as caught:
                pipeline.run(IngestionRequest(raw, out))
            self.assertEqual(caught.exception.code, "INGESTION_FAILED")
            self.assertFalse(out.exists())
            diagnostic = next(Path(temp).glob("out.ingest-*/manifest.json"))
            self.assertEqual(json.loads(diagnostic.read_text())["status"], "FAILED")
            self.assertEqual(before, sha256(raw / "wide.mp4"))

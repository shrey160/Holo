"""Canonical-capture-2 LiDAR (raw-depth) admission checks."""

import tempfile
import unittest
from pathlib import Path

from multimodal_fixtures import gray_png_bytes, stray_lidar_fixture

from cozmo_ingestion import IngestionError
from cozmo_ingestion.multimodal.contracts import MODE_LIDAR, MultimodalRequest
from cozmo_ingestion.multimodal.lidar_pipeline import LiDARIngestionPipeline
from cozmo_ingestion.multimodal.reader import MultimodalCaptureReader
from cozmo_ingestion.multimodal.verify import verify_v2


class FakeRgbProbe:
    def __init__(self, frame_count=2, width=10, height=8):
        self.frame_count, self.width, self.height = frame_count, width, height

    def probe(self, clip):
        return {
            "width": self.width,
            "height": self.height,
            "codec": "h264",
            "frame_count": self.frame_count,
        }


def run_lidar(raw, out, frames=3, **kwargs):
    stray_lidar_fixture(raw, frames=frames, **kwargs)
    pipeline = LiDARIngestionPipeline(
        rgb_probe=FakeRgbProbe(frame_count=frames - 1), sample_frames=8
    )
    return pipeline.run(MultimodalRequest(raw, out, MODE_LIDAR))


class LidarIngestionTests(unittest.TestCase):
    def test_records_depth_poses_and_conventions(self):
        with tempfile.TemporaryDirectory() as temp:
            raw, out = Path(temp) / "raw", Path(temp) / "out"
            result = run_lidar(raw, out)
            self.assertEqual(result.manifest["schema"], "canonical-capture-2")
            self.assertEqual(result.manifest["mode"], "lidar")
            self.assertEqual(result.manifest["depth_frame_count"], 3)
            self.assertEqual(result.manifest["confidence_frame_count"], 3)
            self.assertEqual(result.report["geometry_readiness"], "CONVENTIONS_UNVERIFIED")
            reader = MultimodalCaptureReader(out)
            self.assertEqual(len(reader.pose_records()), 3)
            self.assertEqual(len(reader.calibration()), 3)
            self.assertEqual(len(reader.observations), 3)
            for row in reader.observations:
                self.assertIsNotNone(row["camera_K_ref"])
                self.assertIsNotNone(row["pose_ref"])
                self.assertEqual(row["processing_eligibility"], "INGESTION_ONLY")
            self.assertEqual(reader.capabilities["measured_depth"], "PRESENT_UNVERIFIED")
            summary = verify_v2(out, raw)
            self.assertEqual(summary["status"], "PASSED")
            self.assertGreaterEqual(summary["originals_reverified"], 3)

    def test_pose_and_intrinsics_values_are_preserved_without_axis_flip(self):
        with tempfile.TemporaryDirectory() as temp:
            raw, out = Path(temp) / "raw", Path(temp) / "out"
            run_lidar(raw, out)
            reader = MultimodalCaptureReader(out)
            poses = {p["native_frame_id"]: p for p in reader.pose_records()}
            self.assertEqual(poses["0"]["world_from_camera"]["t"], [0.0, 0.0, 0.0])
            self.assertAlmostEqual(poses["1"]["world_from_camera"]["t"][0], 0.1)
            self.assertAlmostEqual(poses["1"]["world_from_camera"]["t"][2], 0.2)
            self.assertEqual(poses["0"]["world_from_camera"]["q"], [1.0, 0.0, 0.0, 0.0])
            self.assertEqual(poses["0"]["quaternion_order"], "qw,qx,qy,qz")
            conventions = reader.manifest["conventions"]
            self.assertFalse(conventions["second_axis_flip_applied"])
            calibration = {c["native_frame_id"]: c for c in reader.calibration()}
            self.assertEqual(calibration["0"]["reference_grid"], [10, 8])

    def test_confidence_absent_is_explicit(self):
        with tempfile.TemporaryDirectory() as temp:
            raw, out = Path(temp) / "raw", Path(temp) / "out"
            result = run_lidar(raw, out, confidence=False)
            self.assertEqual(result.manifest["confidence_frame_count"], 0)
            self.assertEqual(result.manifest["capabilities"]["confidence"], "ABSENT")
            codes = {finding["code"] for finding in result.report["findings"]}
            self.assertIn("CONFIDENCE_ABSENT", codes)
            self.assertEqual(verify_v2(out, raw)["status"], "PASSED")

    def test_units_and_conventions_are_flagged_unverified(self):
        with tempfile.TemporaryDirectory() as temp:
            raw, out = Path(temp) / "raw", Path(temp) / "out"
            result = run_lidar(raw, out)
            codes = {finding["code"] for finding in result.report["findings"]}
            self.assertIn("DEPTH_UNITS_UNVERIFIED", codes)
            self.assertIn("CONVENTIONS_UNVERIFIED", codes)
            self.assertIn("millimetres", result.manifest["conventions"]["depth_units"])
            self.assertFalse(result.manifest["scale"]["correction_applied"])

    def test_invalid_depth_samples_are_counted(self):
        with tempfile.TemporaryDirectory() as temp:
            raw, out = Path(temp) / "raw", Path(temp) / "out"
            run_lidar(raw, out, depth_value=lambda x, y, index: 0 if index == 0 else 1000)
            reader = MultimodalCaptureReader(out)
            stats = reader.verification["depth_samples"]
            self.assertGreater(stats["invalid_values"], 0)
            self.assertIsNotNone(stats["valid_min_mm"])

    def test_missing_depth_map_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            raw, out = Path(temp) / "raw", Path(temp) / "out"
            stray_lidar_fixture(raw, frames=3)
            (raw / "depth/000001.png").unlink()
            with self.assertRaises(IngestionError) as caught:
                LiDARIngestionPipeline(rgb_probe=FakeRgbProbe(2)).run(
                    MultimodalRequest(raw, out, MODE_LIDAR)
                )
            self.assertEqual(caught.exception.code, "DEPTH_ID_MISMATCH")

    def test_mismatched_depth_grid_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            raw, out = Path(temp) / "raw", Path(temp) / "out"
            stray_lidar_fixture(raw, frames=3)
            (raw / "depth/000001.png").write_bytes(gray_png_bytes(5, 3, 16, fill=1000))
            with self.assertRaises(IngestionError) as caught:
                LiDARIngestionPipeline(rgb_probe=FakeRgbProbe(2)).run(
                    MultimodalRequest(raw, out, MODE_LIDAR)
                )
            self.assertEqual(caught.exception.code, "DEPTH_GRID_MISMATCH")

    def test_confidence_grid_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            raw, out = Path(temp) / "raw", Path(temp) / "out"
            stray_lidar_fixture(raw, frames=3)
            (raw / "confidence/000001.png").write_bytes(gray_png_bytes(5, 3, 8, fill=1))
            with self.assertRaises(IngestionError) as caught:
                LiDARIngestionPipeline(rgb_probe=FakeRgbProbe(2)).run(
                    MultimodalRequest(raw, out, MODE_LIDAR)
                )
            self.assertEqual(caught.exception.code, "CONFIDENCE_GRID_MISMATCH")

    def test_incomplete_confidence_map_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            raw, out = Path(temp) / "raw", Path(temp) / "out"
            stray_lidar_fixture(raw, frames=3)
            (raw / "confidence/000002.png").unlink()
            with self.assertRaises(IngestionError) as caught:
                LiDARIngestionPipeline(rgb_probe=FakeRgbProbe(2)).run(
                    MultimodalRequest(raw, out, MODE_LIDAR)
                )
            self.assertEqual(caught.exception.code, "CONFIDENCE_ID_MISMATCH")

    def test_wrong_depth_encoding_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            raw, out = Path(temp) / "raw", Path(temp) / "out"
            stray_lidar_fixture(raw, frames=2, depth_bit=8)
            with self.assertRaises(IngestionError) as caught:
                LiDARIngestionPipeline(rgb_probe=FakeRgbProbe(1)).run(
                    MultimodalRequest(raw, out, MODE_LIDAR)
                )
            self.assertEqual(caught.exception.code, "DEPTH_ENCODING_MISMATCH")


if __name__ == "__main__":
    unittest.main()

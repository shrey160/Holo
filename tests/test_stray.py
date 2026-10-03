"""Format isolation, discard association, raw preservation and input boundaries."""

import tempfile
import unittest
import zipfile
from pathlib import Path

from fixtures import FakeVideoInspector, fixture

from cozmo_ingestion import CaptureReader, IngestionPipeline, IngestionRequest
from cozmo_ingestion.adapters.selection import select_adapter
from cozmo_ingestion.adapters.stray import IMU_HEADER, ODOMETRY_HEADER
from cozmo_ingestion.errors import IngestionError
from cozmo_ingestion.storage import write_csv
from cozmo_ingestion.verification import verify
from cozmo_web.config import Settings
from cozmo_web.errors import WebError
from cozmo_web.uploads import prepare_capture


def stray_fixture(root):
    root.mkdir()
    (root / "rgb.mp4").write_bytes(b"synthetic media; inspector injected")
    (root / "camera_matrix.csv").write_text("100,0,49.5\n0,100,29.5\n0,0,1\n")
    rows = []
    for index in range(4):
        values = [
            str(100 + index * 0.1),
            f"{index:06d}",
            "0",
            "0",
            "0",
            "0",
            "0",
            "0",
            "1",
            "100",
            "100",
            "49.5",
            "29.5",
            "",
            "",
        ]
        rows.append(dict(zip(ODOMETRY_HEADER, values, strict=True)))
    write_csv(root / "odometry.csv", ODOMETRY_HEADER, rows)
    samples = [
        dict(zip(IMU_HEADER, values, strict=True))
        for values in [
            ["100.12", "0", "-1.00000001", "0", "0.25", "0", "0"],
            ["100.32", "0", "-1", "0", "0.125", "0", "0"],
        ]
    ]
    write_csv(root / "imu.csv", IMU_HEADER, samples)
    for directory in ("depth", "confidence"):
        (root / directory).mkdir()
        for index in range(4):
            (root / directory / f"{index:06d}.png").write_bytes(b"excluded opaque sensor payload")
    return rows


def stray_media(video):
    return {
        "stream": {"width": 100, "height": 60, "time_base": "1/1000"},
        "frames": [
            {"best_effort_timestamp": pts, "width": 100, "height": 60} for pts in (0, 100, 200)
        ],
        "discarded_packets": [{"pts": -100, "flags": "KD"}],
        "full_decode": "PASSED",
    }


class StrayTests(unittest.TestCase):
    def run_capture(self, root, output, inspector=stray_media):
        return IngestionPipeline(video_inspector=FakeVideoInspector(inspector)).run(
            IngestionRequest(root, output)
        )

    def test_native_values_discard_evidence_and_depth_boundary(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            source = base / "raw"
            stray_fixture(source)
            result = self.run_capture(source, base / "bundle")
            audit = verify(result.output, source)
            self.assertEqual(audit["frames_verified"], 3)
            self.assertEqual(audit["unassociated_source_frame_indices"], [0])
            reader = CaptureReader(result.output, source_root=source)
            frames = reader.records("frames")
            self.assertEqual([int(row["source_frame_index"]) for row in frames], [1, 2, 3])
            self.assertEqual(reader.records("native_imu")[0]["a_y"], "-1.00000001")
            self.assertEqual(reader.records("poses")[0]["tracking_state"], "unreported")
            self.assertEqual(reader.read_source("imu.csv"), (source / "imu.csv").read_bytes())
            for asset in ("depth/000000.png", "confidence/000001.png"):
                with self.assertRaises(IngestionError):
                    reader.read_source(asset)
            rgb = CaptureReader(result.output, "video_rgb", source)
            with self.assertRaises(IngestionError):
                rgb.records("native_imu")
            evaluation = CaptureReader(result.output, "evaluation", source)
            self.assertEqual(
                evaluation.read_source("confidence/000001.png"), b"excluded opaque sensor payload"
            )
            self.assertEqual(result.manifest["capabilities"]["measured_depth"], "EXCLUDED")
            replay = self.run_capture(source, base / "replay")
            self.assertTrue(
                verify(result.output, source, replay.output)["deterministic_replay_equal"]
            )

    def test_missing_or_late_discard_and_bad_clock_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            source = base / "raw"
            stray_fixture(source)
            for index, mutate in enumerate(
                [
                    lambda media: media.update(discarded_packets=[]),
                    lambda media: media.update(discarded_packets=[{"pts": 10}]),
                    lambda media: media["frames"][-1].update(best_effort_timestamp=500),
                ]
            ):

                def inspector(video, mutate=mutate):
                    data = stray_media(video)
                    mutate(data)
                    return data

                with self.subTest(index=index), self.assertRaises(IngestionError):
                    self.run_capture(source, base / f"invalid-{index}", inspector)

    def test_wrong_sensor_grid_and_incomplete_ids_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            source = base / "raw"
            stray_fixture(source)
            (source / "depth/000003.png").unlink()
            with self.assertRaises(IngestionError):
                self.run_capture(source, base / "invalid")

    def test_source_tampering_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            source = base / "raw"
            stray_fixture(source)
            result = self.run_capture(source, base / "bundle")
            (source / "confidence/000001.png").write_bytes(b"changed")
            with self.assertRaises(IngestionError):
                verify(result.output, source)

    def test_mixed_formats_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "raw"
            fixture(source)
            (source / "rgb.mp4").write_bytes(b"stray")
            (source / "odometry.csv").write_text("other format")
            (source / "camera_matrix.csv").write_text("other format")
            # Sensor fixture only supplies separate IMU: supply combined file for layout collision.
            (source / "imu.csv").write_text("other format")
            with self.assertRaises(IngestionError):
                select_adapter(source)

    def test_nested_zip_preserves_depth_and_accepts_many_members(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            source = base / "capture"
            stray_fixture(source)
            job = base / "job"
            incoming = job / "incoming"
            incoming.mkdir(parents=True)
            with zipfile.ZipFile(incoming / "capture.zip", "w") as archive:
                for path in source.rglob("*"):
                    if path.is_file():
                        archive.write(path, "session/id/" + path.relative_to(source).as_posix())
                for index in range(201):
                    archive.writestr(f"session/id/auxiliary/{index}.txt", "retained")
            raw = prepare_capture(job, Settings())
            self.assertEqual(
                (raw / "depth/000000.png").read_bytes(), b"excluded opaque sensor payload"
            )
            self.assertTrue((raw / "auxiliary/200.txt").is_file())

    def test_multiple_stray_sessions_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            incoming = Path(temp) / "incoming"
            incoming.mkdir()
            with zipfile.ZipFile(incoming / "multiple.zip", "w") as archive:
                archive.writestr("one/rgb.mp4", b"one")
                archive.writestr("two/rgb.mp4", b"two")
            with self.assertRaises(WebError):
                prepare_capture(Path(temp), Settings())

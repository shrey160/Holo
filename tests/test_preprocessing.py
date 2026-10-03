"""Preprocessing boundary, geometry, timing and visual-support behavior."""

import json
import tempfile
import unittest
from pathlib import Path

try:
    import cv2
    import numpy as np
except ImportError as error:
    raise unittest.SkipTest("Install the preprocess extra") from error

from fixtures import FakeVideoInspector, fixture

from cozmo_ingestion import CaptureReader, IngestionPipeline, IngestionRequest
from cozmo_ingestion.errors import IngestionError
from cozmo_ingestion.storage import sha256, write_json
from cozmo_preprocessing import PreprocessingPipeline, PreprocessingPolicy, PreprocessingRequest
from cozmo_preprocessing.analysis import SensorIndex, image_quality, pose_delta
from cozmo_preprocessing.matching import ViewMatcher
from cozmo_preprocessing.media import save_jpeg
from cozmo_preprocessing.selection import candidate_indices, choose_views
from cozmo_preprocessing.verification import lines, verify_preprocessing


class SyntheticDecoder:
    version = "synthetic pixels; no FFmpeg test"

    def __init__(self, on_decode=None):
        self.on_decode = on_decode

    def candidates(self, video, frames, indices, size):
        rng = np.random.default_rng(123)
        image = rng.integers(0, 256, (size[1], size[0], 3), dtype=np.uint8)
        for rank in indices:
            yield rank, image
        if self.on_decode:
            self.on_decode(video)


def prepared_fixture(root, decoder=None):
    fixture(root / "raw")
    IngestionPipeline(video_inspector=FakeVideoInspector()).run(
        IngestionRequest(root / "raw", root / "bundle")
    )
    pipeline = PreprocessingPipeline(decoder=decoder or SyntheticDecoder())
    report = pipeline.run(PreprocessingRequest(root / "bundle", root / "prepared", root / "raw"))
    return report


class PreprocessingTests(unittest.TestCase):
    def test_known_translation_rotation_and_pure_rotation(self):
        first = {"world_from_camera": np.eye(4).tolist()}
        matrix = np.eye(4)
        matrix[:3, :3] = [[0, -1, 0], [1, 0, 0], [0, 0, 1]]
        second = {"world_from_camera": matrix.tolist()}
        self.assertEqual(pose_delta(first, second), (0, 90))
        matrix[0, 3] = 3
        matrix[2, 3] = 4
        self.assertEqual(pose_delta(first, {"world_from_camera": matrix.tolist()}), (5, 90))

    def test_native_sensor_intervals_gaps_and_no_extrapolation(self):
        index = SensorIndex(
            [{"relative_seconds": str(t), "x": "3", "y": "4"} for t in (0.02, 0.1, 0.5)], ["x", "y"]
        )
        before = index.interval(0, 0.01)
        self.assertEqual(before["sample_count"], 0)
        self.assertFalse(before["boundary_covered"])
        covered = index.interval(0.02, 0.1)
        self.assertEqual(covered["sample_range"], [0, 2])
        self.assertEqual(covered["rms_magnitude"], 5)
        self.assertFalse(index.interval(0.1, 0.6)["boundary_covered"])

    def test_quality_detects_relative_blur_and_texture_loss(self):
        rng = np.random.default_rng(0)
        image = rng.integers(0, 256, (120, 160, 3), dtype=np.uint8)
        sharp = image_quality(image, 160)
        blurred = image_quality(cv2.GaussianBlur(image, (15, 15), 5), 160)
        blank = image_quality(np.zeros_like(image), 160)
        self.assertGreater(sharp["laplacian_variance"], blurred["laplacian_variance"] * 10)
        self.assertEqual(blank["texture_corners"], 0)
        self.assertEqual(blank["dark_fraction"], 1)

    def test_preprocessing_reader_denies_reference_and_depth(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fixture(root / "raw")
            IngestionPipeline(video_inspector=FakeVideoInspector()).run(
                IngestionRequest(root / "raw", root / "bundle")
            )
            reader = CaptureReader(root / "bundle", "ios_preprocessing")
            with self.assertRaises(IngestionError):
                reader.records("annotations")
            for asset_id in ("meta.json", "depth/0001.bin", "references/laser.csv"):
                with self.assertRaises(IngestionError):
                    reader.source_path(asset_id)

    def test_selected_geometry_sensor_values_traceability_and_tamper(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            report = prepared_fixture(root)
            self.assertEqual(report["selected_count"], 2)
            self.assertEqual(
                verify_preprocessing(root / "prepared", root / "bundle", root / "raw")["status"],
                "PASSED",
            )
            views = lines(root / "prepared/views.jsonl")
            self.assertEqual([v["source_frame_index"] for v in views], [0, 1])
            self.assertEqual(views[0]["pixel_transform"], np.eye(3, dtype=int).tolist())
            self.assertIn("NON_NORMAL_TRACKING", views[0]["flags"])
            usage = json.loads((root / "prepared/usage.json").read_text())
            self.assertNotIn("annotations.json", str(usage))
            (root / "prepared" / views[0]["image"]).write_bytes(b"changed")
            with self.assertRaises(IngestionError):
                verify_preprocessing(root / "prepared", root / "bundle", root / "raw")

    def test_changed_source_never_publishes_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with self.assertRaises(IngestionError):
                prepared_fixture(
                    root, SyntheticDecoder(lambda video: video.write_bytes(b"changed"))
                )
            self.assertFalse((root / "prepared").exists())
            self.assertEqual(len(list(root.glob("prepared.ingest-*/manifest.json"))), 1)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            prepared_fixture(root)
            with self.assertRaises(IngestionError):
                PreprocessingPipeline(decoder=SyntheticDecoder()).run(
                    PreprocessingRequest(root / "bundle", root / "prepared", root / "raw")
                )

    def test_policy_limits_and_source_adapter_are_explicit(self):
        for values in (
            {"candidate_fps": float("nan")},
            {"candidate_fps": 11},
            {"min_matches": 2.5},
            {"min_inlier_ratio": 1.1},
        ):
            with self.assertRaises(ValueError):
                PreprocessingPolicy(**values)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            prepared_fixture(root)
            manifest_path = root / "bundle/manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["adapter"] = "stray-layout-supplied-v1"
            write_json(manifest_path, manifest)
            with self.assertRaisesRegex(IngestionError, "Sensor Recorder"):
                PreprocessingPipeline(decoder=SyntheticDecoder()).run(
                    PreprocessingRequest(root / "bundle", root / "other", root / "raw")
                )

    def test_selection_coverage_normal_tracking_and_motion(self):
        frames = [{"relative_seconds": str(i / 4)} for i in range(17)]
        self.assertEqual(candidate_indices(frames, 2), list(range(0, 17, 2)))
        candidates, poses = [], {}
        for i in range(17):
            matrix = np.eye(4)
            matrix[0, 3] = i * 0.03
            poses[str(i)] = {"world_from_camera": matrix.tolist()}
            candidates.append(
                {
                    "rank": i,
                    "frame_id": str(i),
                    "seconds": i / 4,
                    "tracking_normal": i > 0,
                    "quality": {"score": 1 if i == 0 else 0.5},
                }
            )
        selected = sorted(choose_views(candidates, poses, PreprocessingPolicy()))
        self.assertEqual(selected[0], 0)
        self.assertEqual(selected[-1], 16)
        self.assertLessEqual(
            max((b - a) / 4 for a, b in zip(selected, selected[1:], strict=False)), 0.75
        )
        self.assertIn(1, selected)

    def test_visual_matching_weak_blank_and_supported_planar_overlap(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            rng = np.random.default_rng(7)
            image = rng.integers(0, 256, (360, 640, 3), dtype=np.uint8)
            for i, pixels in enumerate((image, image, np.zeros_like(image))):
                save_jpeg(root / f"{i:06d}.jpg", pixels)
            poses = {str(i): {"world_from_camera": np.eye(4).tolist()} for i in range(3)}
            ks = {str(i): {"K": [[300, 0, 319.5], [0, 300, 179.5], [0, 0, 1]]} for i in range(3)}
            matcher = ViewMatcher(root, ks, poses, PreprocessingPolicy())
            candidates = [{"rank": i, "frame_id": str(i), "seconds": i / 4} for i in range(3)]
            same = matcher.pair(candidates[0], candidates[1])
            self.assertEqual(same["visual_link"], "SUPPORTED")
            self.assertTrue(same["low_baseline"])
            self.assertEqual(matcher.pair(candidates[1], candidates[2])["visual_link"], "WEAK")

    def test_derived_geometry_tamper_with_rehashed_artifact_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            prepared_fixture(root)
            path = root / "prepared/poses.jsonl"
            content = lines(path)
            content[0]["world_from_camera"][0][3] = 123
            from cozmo_ingestion.storage import write_lines

            write_lines(path, content)
            manifest_path = root / "prepared/manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["artifact_sha256"]["poses.jsonl"] = sha256(path)
            write_json(manifest_path, manifest)
            with self.assertRaises(IngestionError):
                verify_preprocessing(root / "prepared", root / "bundle", root / "raw")

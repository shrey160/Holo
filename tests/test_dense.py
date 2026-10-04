"""Analytic stereo plane, zero parallax, occlusion and dense artifact contracts."""

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

try:
    import numpy as np
except ImportError as error:
    raise unittest.SkipTest("Install reconstruct or dense extra") from error

from cozmo_ingestion.errors import IngestionError
from cozmo_reconstruction.audit_numbers import equivalent
from cozmo_reconstruction.dense.geometry import (
    consistent_mask,
    neighbors,
    read_array,
    resample_depth,
    voxel_cloud,
    world_points,
)
from cozmo_reconstruction.dense.models import DensePolicy


def camera(center=0):
    pose = np.eye(4)
    pose[0, 3] = -center
    return {
        "params": [80, 80, 40, 30],
        "camera_from_world": pose.tolist(),
        "center_m": [center, 0, 0],
        "image_size": [80, 60],
    }


class DenseTests(unittest.TestCase):
    def test_grid_resampling_preserves_z_and_rejects_pose_change(self):
        source = camera()
        depth = np.full((60, 80), 2.0, dtype=np.float32)
        np.testing.assert_array_equal(resample_depth(depth, source, source), depth)
        target = dict(source, image_size=[40, 30], params=[40, 40, 20, 15])
        result = resample_depth(depth, source, target)
        self.assertEqual(result.shape, (30, 40))
        self.assertTrue((result == 2).all())
        with self.assertRaises(IngestionError):
            resample_depth(depth, source, camera(0.1))

    def test_numeric_audit_accepts_roundoff_but_rejects_changed_counts_or_metrics(self):
        self.assertTrue(equivalent({"angle": 11.163655513842452}, {"angle": 11.16365551384245}))
        self.assertFalse(equivalent({"count": 100}, {"count": 101}))
        self.assertFalse(equivalent(1, 1.0))
        self.assertFalse(equivalent(1.0, 1.001))
        self.assertFalse(equivalent(float("nan"), float("nan")))

    def test_plane_pixel_centers_depth_and_world_gauge(self):
        depth = np.full((60, 80), 2.0, dtype=np.float32)
        xyz = world_points(depth, camera(0.1), np.array([39]), np.array([29]))
        np.testing.assert_allclose(xyz, [[0.0875, -0.0125, 2]])
        valid, accepted, support = consistent_mask(
            depth, camera(), [depth, depth], [camera(0.1), camera(0.2)], DensePolicy()
        )
        self.assertTrue(valid.all())
        self.assertTrue(accepted[:, 8:].all())
        self.assertFalse(accepted[:, :8].any())
        self.assertTrue((support[:, 8:] == 2).all())

    def test_invalid_depth_occlusion_and_zero_parallax_do_not_create_surfaces(self):
        depth = np.full((60, 80), 2.0, dtype=np.float32)
        for targets, poses in [
            ([depth, depth], [camera(), camera()]),
            ([depth * 1.2, depth], [camera(0.1), camera(0.2)]),
            ([depth * np.nan, depth], [camera(0.1), camera(0.2)]),
        ]:
            _, accepted, _ = consistent_mask(depth, camera(), targets, poses, DensePolicy())
            self.assertFalse(accepted.any())
        invalid = np.array([[0, -1, np.nan, np.inf, 200]], dtype=float)
        valid, accepted, _ = consistent_mask(invalid, camera(), [], [], DensePolicy())
        self.assertFalse(valid.any())
        self.assertFalse(accepted.any())

    def test_voxel_averages_only_supplied_points(self):
        xyz, rgb = voxel_cloud(
            np.array([[0.001, 0, 0], [0.003, 0, 0], [0.2, 0, 0]]),
            np.array([[0, 0, 0], [100, 100, 100], [255, 255, 255]]),
            0.01,
        )
        np.testing.assert_allclose(xyz, [[0.002, 0, 0], [0.2, 0, 0]])
        np.testing.assert_array_equal(rgb, [[50, 50, 50], [255, 255, 255]])

    def test_colmap_array_layout_and_truncated_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "depth.bin"
            original = np.arange(12, dtype="<f4").reshape(3, 4)
            path.write_bytes(b"4&3&1&" + original.T.tobytes(order="F"))
            np.testing.assert_array_equal(read_array(path), original)
            path.write_bytes(b"4&1&1&" + np.arange(4, dtype="<f4").tobytes())
            self.assertEqual(read_array(path).shape, (1, 4))
            path.write_bytes(b"4&3&1&missing")
            with self.assertRaises((IngestionError, ValueError)):
                read_array(path)
            path.write_bytes(b"malformed")
            with self.assertRaises(IngestionError):
                read_array(path)

    def test_co_visibility_and_admission_bounds(self):
        points = [{"observations": [{"rank": r} for r in (1, 2, 3)]}]
        self.assertEqual(
            neighbors(points, {1: "a", 2: "b", 3: "c"}, 6),
            {"a": ["b", "c"], "b": ["a", "c"], "c": ["a", "b"]},
        )
        with self.assertRaises(IngestionError):
            neighbors(points, {1: "a", 2: "b", 4: "d"}, 6)
        for key, value in [
            ("max_image_size", 4000),
            ("min_support", 1),
            ("relative_depth_error", 0.2),
            ("timeout_seconds", 10000),
        ]:
            with self.assertRaises(IngestionError):
                replace(DensePolicy(), **{key: value})

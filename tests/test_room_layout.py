"""Ceiling independence, display handedness and source-bound object support."""

import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
from test_rough_room import rectangle

from cozmo_ingestion.storage import sha256
from cozmo_reconstruction.viewer.ceiling import estimate_ceiling
from cozmo_reconstruction.viewer.objects import approximate_objects, visible_projection
from cozmo_reconstruction.viewer.rough_room import complete_rough_room, rough_room_svg


class RoomLayoutTests(unittest.TestCase):
    def test_ceiling_rejects_singleton_outliers_and_ignores_user_reference(self):
        spans, path = rectangle()
        room = complete_rough_room(spans, [], path)
        rng = np.random.default_rng(7)
        xz = rng.uniform([0, 0], [4, 3], (50000, 2))
        heights = rng.normal(2.7, 0.008, len(xz))
        positions = np.column_stack([xz[:, 0], heights, -xz[:, 1]])
        positions = np.vstack([positions, [[1, 3.9, -1], [3, 3.8, -2], [2, 0.8, -1]]])
        first = estimate_ceiling(positions, room)
        room["ceiling_reference"] = {"value_m": 8.0}
        second = estimate_ceiling(positions, room)
        self.assertEqual(first, second)
        self.assertAlmostEqual(first["height_estimated_m"], 2.7, delta=0.03)
        self.assertFalse(first["external_reference_used"])
        self.assertFalse(first["ceiling_plane_verified"])

    def test_sparse_upper_coverage_cannot_produce_a_height(self):
        spans, path = rectangle()
        room = complete_rough_room(spans, [], path)
        result = estimate_ceiling(np.array([[1, 2.7, -1], [2, 0.5, -2]]), room)
        self.assertIsNone(result["height_estimated_m"])
        self.assertEqual(result["status"], "INSUFFICIENT_UPPER_COVERAGE")

    def test_entrance_is_drawn_on_bottom_half_of_left_wall_without_changing_coordinates(self):
        spans, path = rectangle()
        room = complete_rough_room(spans, [], path)
        before = room["polygon_floor_uv_m"][:]
        svg = ET.fromstring(rough_room_svg(room, []))
        entry = next(e for e in svg.iter() if e.tag.endswith("text") and e.text == "Entry?")
        self.assertGreater(float(entry.attrib["y"]), 400)
        self.assertLess(float(entry.attrib["x"]), 300)
        self.assertEqual(before, room["polygon_floor_uv_m"])

    def test_projection_discards_hidden_background_at_same_pixel(self):
        camera = {
            "camera_from_world": np.eye(4).tolist(),
            "params": [100, 100, 0, 0],
            "image_size": [100, 100],
        }
        uv, visible = visible_projection(
            np.array([[0.2, 0.2, 1], [0.4, 0.4, 2], [0, 0, -1]]), camera
        )
        np.testing.assert_allclose(uv[:2], [[20, 20], [20, 20]])
        self.assertEqual(visible.tolist(), [True, False, False])

    def test_object_review_binds_image_and_visible_geometry_with_explicit_prior(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            image = root / "workspace/images/000001.jpg"
            image.parent.mkdir(parents=True)
            image.write_bytes(b"fixture")
            camera = {
                "rank": 1,
                "image": "000001.jpg",
                "camera_from_world": np.eye(4).tolist(),
                "params": [100, 100, 0, 0],
                "image_size": [200, 100],
            }
            x = np.linspace(1, 2, 200)
            xyz = np.column_stack([x, np.full(200, 0.5), np.full(200, 2)])
            positions = np.column_stack([x, np.full(200, 0.5), np.full(200, -1)])
            spans, path = rectangle()
            room = complete_rough_room(spans, [], path)
            review = {
                "schema": "holo-object-regions-v1",
                "authority": "TEST",
                "objects": [
                    {
                        "id": "desk",
                        "label": "Desk",
                        "height_interval_m": [0.2, 1.0],
                        "minimum_footprint_m": [0.5, 0.5],
                        "regions": [
                            {
                                "rank": 1,
                                "image_sha256": sha256(image),
                                "image_size": [200, 100],
                                "polygon_px": [[40, 10], [110, 10], [110, 40], [40, 40]],
                            }
                        ],
                    }
                ],
            }
            result = approximate_objects(xyz, positions, [camera], root, room, review)[0]
            self.assertEqual(result["source_voxels"], 200)
            self.assertTrue(result["minimum_extent_prior_used"])
            self.assertEqual(result["footprint_floor_uv_m"][0], result["footprint_floor_uv_m"][-1])
            image.write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "identity changed"):
                approximate_objects(xyz, positions, [camera], root, room, review)


if __name__ == "__main__":
    unittest.main()

"""Rough completion is opt-in and remains separate from source-bound evidence."""

import copy
import unittest
import xml.etree.ElementTree as ET

import numpy as np

from cozmo_reconstruction.viewer.rough_room import complete_rough_room, rough_room_svg


def rectangle(angle=0):
    axes = np.array([[np.cos(angle), np.sin(angle)], [-np.sin(angle), np.cos(angle)]])
    corners = np.array([[0.0, 0.0], [4.0, 0.0], [4.0, 3.0], [0.0, 3.0], [0.0, 0.0]]) @ axes
    spans = [{"plane_id": f"P{i}", "uv": corners[i : i + 2].tolist()} for i in range(4)]
    path = np.array([[-1.0, 1.0], [0.5, 1.0], [2.0, 1.0]]) @ axes
    return spans, path.tolist()


class RoughRoomTests(unittest.TestCase):
    def test_closed_rectangle_and_entry_are_inferred_without_mutating_evidence(self):
        spans, path = rectangle()
        original = copy.deepcopy((spans, path))
        room = complete_rough_room(spans, [], path)
        np.testing.assert_allclose(room["dimensions_estimated_m"], [4, 3])
        self.assertAlmostEqual(room["area_estimated_m2"], 12)
        self.assertEqual(room["polygon_floor_uv_m"][0], room["polygon_floor_uv_m"][-1])
        self.assertTrue(all(w["status"] == "INFERRED" for w in room["walls"]))
        self.assertEqual(room["entry"]["wall_id"], "W4")
        self.assertEqual(room["entry"]["method"], "FIRST_CAPTURE_PATH_ENTRY_CROSSING")
        self.assertEqual((spans, path), original)

    def test_rotated_room_preserves_extent_and_does_not_change_scale_for_ceiling(self):
        spans, path = rectangle(np.deg2rad(43))
        ceiling = {"value_m": 2.6, "precision": "APPROXIMATE", "used_for_scale": False}
        room = complete_rough_room(spans, [], path, ceiling)
        np.testing.assert_allclose(room["dimensions_estimated_m"], [4, 3], atol=1e-10)
        self.assertFalse(room["scale_corrected"])
        self.assertIs(room["ceiling_reference"], ceiling)

    def test_reviewed_patch_survives_endpoint_trimming(self):
        spans, path = rectangle()
        review = [{"endpoints_floor_uv_m": [[-0.2, 0], [0.4, 0]]}]
        room = complete_rough_room(spans, review, path)
        self.assertLessEqual(room["bounds_in_room_axes_m"][0][0], -0.2)
        self.assertEqual(room["reviewed_patch_count"], 1)

    def test_degenerate_parallel_or_nonfinite_candidates_cannot_make_a_room(self):
        spans, path = rectangle()
        for bad in [
            spans[:2],
            [{"plane_id": f"P{i}", "uv": [[0, i], [4, i]]} for i in range(4)],
            [{"plane_id": "bad", "uv": [[float("nan"), 0], [1, 2]]}, *spans],
        ]:
            with self.assertRaises(ValueError):
                complete_rough_room(bad, [], path)

    def test_svg_identifies_inferred_walls_and_reference_and_is_valid_xml(self):
        spans, path = rectangle()
        room = complete_rough_room(spans, [], path, {"value_m": 2.6})
        svg = rough_room_svg(room, [])
        ET.fromstring(svg)
        self.assertIn("inferred", svg)
        self.assertIn("Ceiling ≈ 2.6 m", svg)
        self.assertIn("entrance width and swing are assumed", svg)


if __name__ == "__main__":
    unittest.main()

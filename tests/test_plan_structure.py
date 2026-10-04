"""Structure focus reduces clutter without closing gaps or admitting geometry as walls."""

import unittest
from dataclasses import replace

import numpy as np

from cozmo_reconstruction.boundaries.geometry import floor_frame
from cozmo_reconstruction.viewer.structure import (
    PlanPolicy,
    line_suggestions,
    persistent_cells,
    structure_plan,
)


def wall(z_values):
    return np.array([[1.02, y, z] for z in z_values for y in np.linspace(0.65, 2.3, 24)])


class StructurePlanTests(unittest.TestCase):
    def test_small_tall_noise_cluster_and_horizontal_plane_stay_out(self):
        cluster = np.array(
            [
                [x, y, z]
                for x in (1.02, 1.12)
                for z in (0.02, 0.12)
                for y in np.linspace(0.65, 2.3, 24)
            ]
        )
        cells, mask = persistent_cells(cluster, PlanPolicy())
        self.assertEqual(cells, [])
        self.assertFalse(mask.any())
        positions = wall(np.linspace(0, 1, 160))
        frame = floor_frame([0, 1, 0, 0], np.array([[0.0, 0, 0]]))
        planes = [
            {
                "id": "P01",
                "orientation": "horizontal",
                "evidence_status": "MULTIVIEW_CANDIDATE",
                "equation_world": [0, 1, 0, -1],
            }
        ]
        result = structure_plan(positions, np.zeros(len(positions)), planes, frame)
        self.assertEqual(result["cells"], [])
        self.assertEqual(result["suggested_spans"], [])

    def test_removes_bed_and_singleton_high_outliers(self):
        tall = wall(np.linspace(0, 1, 80))
        bed = np.array(
            [[2.02, y, z] for z in np.linspace(0, 1, 80) for y in np.linspace(0.65, 1.1, 24)]
        )
        outliers = np.array([[2.02, 2.3, z] for z in np.arange(0.01, 1, 0.1)])
        points = np.concatenate((tall, bed, outliers))
        cells, mask = persistent_cells(points, PlanPolicy())
        self.assertGreater(len(cells), 5)
        self.assertTrue(mask[: len(tall)].any())
        self.assertFalse(mask[len(tall) :].any())
        self.assertTrue(all(c["cell"][0] == 10 for c in cells))

    def test_empty_single_height_and_isolated_column_stay_absent(self):
        for points in (
            np.empty((0, 3)),
            wall([0.01]),
            np.array([[1, 1, z] for z in np.linspace(0, 2, 100)]),
        ):
            cells, mask = persistent_cells(points, PlanPolicy())
            self.assertEqual(cells, [])
            self.assertFalse(mask.any())

    def test_empty_gap_is_not_bridged_or_closed(self):
        positions = wall(np.r_[np.linspace(0, 1, 160), np.linspace(2, 3, 160)])
        frame = floor_frame([0, 1, 0, 0], np.array([[0.0, 0, 0]]))
        planes = [
            {
                "id": "P01",
                "orientation": "vertical",
                "evidence_status": "MULTIVIEW_CANDIDATE",
                "equation_world": [1, 0, 0, -1],
            }
        ]
        result = structure_plan(positions, np.zeros(len(positions)), planes, frame)
        self.assertEqual(len(result["suggested_spans"]), 2)
        for line in result["suggested_spans"]:
            endpoints = np.array(line["uv"])
            self.assertLess(np.ptp(endpoints[:, 1]), 1.1)
            self.assertLess(np.ptp(endpoints[:, 0]), 1e-4)
        self.assertIsNone(result["closed_room_polygon"])
        self.assertIsNone(result["room_area"])
        self.assertFalse(result["measured_ceiling_reference_used"])

    def test_refit_disagreement_with_source_is_withheld(self):
        positions = wall(np.linspace(0, 2, 320))
        frame = floor_frame([0, 1, 0, 0], np.array([[0.0, 0, 0]]))
        planes = [
            {
                "id": "P01",
                "orientation": "vertical",
                "evidence_status": "MULTIVIEW_CANDIDATE",
                "equation_world": [0, 0, 1, -1],
            }
        ]
        lines, rows = line_suggestions(
            positions,
            np.zeros(len(positions)),
            planes,
            frame,
            np.ones(len(positions), bool),
            PlanPolicy(),
        )
        self.assertEqual(lines, [])
        self.assertEqual(rows[0]["status"], "REFIT_DISAGREES_WITH_SOURCE_PLANE")

    def test_height_interval_excludes_floor_and_high_floating_points(self):
        points = wall(np.linspace(0, 1, 160))
        cells, mask = persistent_cells(
            points, replace(PlanPolicy(), height_min_m=3.0, height_max_m=4.0)
        )
        self.assertEqual(cells, [])
        self.assertFalse(mask.any())


if __name__ == "__main__":
    unittest.main()

"""Direct connections, short connector scans, revisits and room-local geometry."""

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from cozmo_reconstruction.models import ReconstructionRequest
from cozmo_reconstruction.viewer.automatic import publish_assets
from cozmo_reconstruction.viewer.dense_automatic import dense_evidence
from cozmo_reconstruction.viewer.export import display_points
from cozmo_reconstruction.viewer.local_rooms import _cell_keys, roomwise_plan
from cozmo_reconstruction.viewer.roomwise_svg import roomwise_svg
from cozmo_reconstruction.viewer.route import analyze_route
from cozmo_web.reconstruction import ReconstructionCatalog


def mapping(connector=False, revisit=False):
    centers = [[1.5, 2]] * 17
    centers += np.linspace([1.5, 2], [6.5, 2], 5)[1:].tolist()
    if connector:
        centers += [[4, 3]] * 3
        centers += np.linspace([4, 3], [6.5, 2], 5)[1:].tolist()
    centers += [[6.5, 2]] * 21
    if revisit:
        centers += np.linspace([6.5, 2], [1.5, 2], 5)[1:].tolist()
        centers += [[1.5, 2]] * 21
    rows = []
    for t, (x, z) in enumerate(centers):
        x += 0.2 * np.sin(t)
        z += 0.15 * np.cos(t)
        yaw = t * 0.4
        pose = np.array(
            [
                [np.cos(yaw), 0, np.sin(yaw), x],
                [0, 1, 0, 1.5],
                [-np.sin(yaw), 0, np.cos(yaw), z],
                [0, 0, 0, 1],
            ]
        )
        rows.append(
            {"rank": t, "relative_seconds": str(t), "pose": {"world_from_camera": pose.tolist()}}
        )
    return rows


class RouteTests(unittest.TestCase):
    def test_direct_room_connection_does_not_require_corridor_exit(self):
        rows = mapping()
        before = copy.deepcopy(rows)
        report = analyze_route(list(reversed(rows)))
        self.assertEqual(len(report["rooms"]), 2)
        self.assertEqual(len(report["transitions"]), 1)
        self.assertFalse(report["transitions"][0]["requires_exit_to_corridor"])
        self.assertIsNone(report["transitions"][0]["doorway_crossing_seconds"])
        self.assertIsNone(report["transitions"][0]["door_width_m"])
        self.assertEqual(rows, before)

    def test_brief_connector_scan_is_not_a_third_room(self):
        report = analyze_route(mapping(connector=True))
        self.assertEqual(len(report["rooms"]), 2)
        self.assertEqual(len(report["transitions"]), 1)

    def test_return_to_same_anchor_reuses_room_identity(self):
        report = analyze_route(mapping(revisit=True))
        self.assertEqual(len(report["rooms"]), 2)
        self.assertEqual([s["room_id"] for s in report["stays"]], ["R01", "R02", "R01"])

    def test_looking_at_doors_without_leaving_does_not_split_room(self):
        rows = mapping()
        for row in rows:
            row["pose"]["world_from_camera"][0][3] = 1.5
        self.assertEqual(len(analyze_route(rows)["rooms"]), 1)

    def test_duplicate_timestamps_rejected(self):
        rows = mapping()
        rows[2]["relative_seconds"] = rows[1]["relative_seconds"]
        with self.assertRaises(ValueError):
            analyze_route(rows)


class LocalRoomTests(unittest.TestCase):
    def test_dense_path_uses_capture_order_instead_of_backend_image_order(self):
        points = np.array([[0.0, 0.0, 0.0], [2.0, 0.0, 2.0], [2.0, 0.0, 0.0]])
        floor = {
            "id": "floor",
            "orientation": "horizontal",
            "evidence_status": "MULTIVIEW_CANDIDATE",
            "equation_world": [0, 1, 0, 0],
            "median_camera_height_above_patch_m": 1.5,
            "largest_patch_span_m": [2, 2],
        }
        cameras = [{"rank": rank, "center_m": [rank, 1.5, 0]} for rank in [2, 0, 1]]
        _, path, frame, _, _ = dense_evidence(points, np.zeros(3, dtype=int), [floor], cameras)
        np.testing.assert_allclose(
            path, display_points(np.array([[i, 1.5, 0] for i in range(3)]), frame)
        )

    def test_incomplete_rooms_publish_signed_partial_assets_without_room_measurements(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            request = ReconstructionRequest(root / "prepared", root / "bundle", root / "dense")
            request.output.mkdir()
            roomwise = {
                "status": "PARTIAL_ROOMWISE_EVIDENCE",
                "rooms": [{"id": "R01", "rough_room": None}, {"id": "R02", "rough_room": None}],
                "limitations": ["Room boundaries are incomplete"],
            }
            points = np.arange(300, dtype=float).reshape(-1, 3) / 100
            publish_assets(
                request,
                root / "catalog/result",
                "Partial rooms",
                points,
                points[:3],
                {},
                None,
                np.zeros_like(points),
                [],
                {"status": "VERIFIED"},
                {},
                {},
                "RGB_DENSE_STEREO",
                lambda: None,
                {"roomwise": roomwise},
                trim=False,
            )
            scene = json.loads((root / "catalog/result/scene.json").read_text())
            self.assertIsNone(scene["inferred_room_completion"])
            self.assertEqual(scene["roomwise_summary"]["completed_room_count"], 0)
            integrity, result = ReconstructionCatalog(root / "catalog").read("result")
            self.assertEqual(integrity.verify_all(), 9)
            self.assertEqual(result["geometry_source"], "RGB_DENSE_STEREO")

    def test_voxel_membership_uses_contributions_and_preserves_negative_cells(self):
        a = _cell_keys(np.array([[-0.015, 0, 0], [0.015, 0, 0]]), 0.01)
        b = _cell_keys(np.array([[-0.011, 0, 0]]), 0.01)
        np.testing.assert_array_equal(np.isin(a, b), [True, False])

    def test_two_room_surface_fits_use_separate_budgets_and_shared_coordinates(self):
        rows = mapping()
        pieces = []
        for shift in (0, 5):
            along, height = np.meshgrid(np.linspace(0, 3, 100), np.linspace(0.6, 2.4, 60))
            depth, h2 = np.meshgrid(np.linspace(0, 4, 120), np.linspace(0.6, 2.4, 60))
            pieces.append(
                np.concatenate(
                    [
                        np.column_stack(
                            (along.ravel() + shift, height.ravel(), np.zeros(along.size))
                        ),
                        np.column_stack(
                            (along.ravel() + shift, height.ravel(), np.full(along.size, 4))
                        ),
                        np.column_stack((np.full(depth.size, shift), h2.ravel(), depth.ravel())),
                        np.column_stack(
                            (np.full(depth.size, shift + 3), h2.ravel(), depth.ravel())
                        ),
                    ]
                )
            )
        xyz = np.concatenate(pieces)
        before = xyz.copy()
        cameras = [
            {
                "rank": r["rank"],
                "image": f"{r['rank']}.jpg",
                "center_m": np.asarray(r["pose"]["world_from_camera"])[:3, 3].tolist(),
            }
            for r in rows
        ]
        observations = [(c, pieces[0 if c["center_m"][0] < 4 else 1]) for c in cameras]
        frame = {
            "plane_world": [0, 1, 0, 0],
            "origin_world_m": [0, 0, 0],
            "floor_from_world": [[1, 0, 0, 0], [0, 0, 1, 0], [0, 1, 0, 0], [0, 0, 0, 1]],
            "u_world": [1, 0, 0],
            "v_world": [0, 0, 1],
        }
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "input_mapping.json").write_text(json.dumps(rows))
            (root / "policy.json").write_text(json.dumps({"sample_stride": 2}))
            with patch(
                "cozmo_reconstruction.viewer.local_rooms.source_observations",
                return_value=(observations, 0.01),
            ):
                report = roomwise_plan(root, xyz, cameras, frame)
        np.testing.assert_array_equal(xyz, before)
        self.assertEqual(len(report["rooms"]), 2)
        for room in report["rooms"]:
            self.assertIsNotNone(room["rough_room"], room.get("failure"))
            np.testing.assert_allclose(
                sorted(room["rough_room"]["dimensions_estimated_m"]), [3, 4], atol=0.1
            )
            self.assertFalse(room["rough_room"]["scale_corrected"])
            self.assertAlmostEqual(
                room["rough_room"]["ceiling_estimate"]["height_estimated_m"], 2.4
            )
            self.assertFalse(room["rough_room"]["ceiling_estimate"]["ceiling_plane_verified"])
        self.assertTrue(report["shared_coordinate_frame"])
        self.assertIn("doorway crossings unresolved", roomwise_svg(report, [[1.5, 2], [6.5, 2]]))


if __name__ == "__main__":
    unittest.main()

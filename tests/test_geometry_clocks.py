"""geometry clocks behavioral checks."""

from fixtures import FixtureTestCase, media, pose_row

from cozmo_ingestion import IngestionError
from cozmo_ingestion.clocks import associate
from cozmo_ingestion.contracts import IngestionPolicy
from cozmo_ingestion.models import VideoInspection
from cozmo_ingestion.numeric import quaternion_pose


class Tests(FixtureTestCase):
    def test_known_quaternion_direction_and_translation(self):
        row = pose_row()
        row.update(qw="0.7071067811865476", qz="0.7071067811865476", tx_m="2", ty_m="3", tz_m="4")
        transform, _ = quaternion_pose(row)
        # Camera +X rotates into world +Y, then receives world translation.
        point = [sum(transform[i][j] * [1, 0, 0, 1][j] for j in range(4)) for i in range(4)]
        for got, expected in zip(point, [2, 4, 4, 1], strict=True):
            self.assertAlmostEqual(got, expected)
        row["qw"] = "9"
        with self.assertRaisesRegex(IngestionError, "0"):
            quaternion_pose(row)

    def test_integer_pts_and_large_sensor_origin_preserve_microseconds(self):
        rows = [pose_row(), pose_row(1, 2, "1000000000.016667")]
        alignment, ticks = associate(rows, VideoInspection(**media()))
        self.assertEqual(alignment["maximum_residual_seconds"], 0)
        self.assertEqual(ticks, [0, 16667])
        self.assertEqual(alignment["media_timebase"], "1/1000000")

    def test_no_truncation_or_discard_shift(self):
        rows = [pose_row(), pose_row(1, 2, "1000000000.016667")]
        for modified in [
            dict(media(), frames=media()["frames"][:1]),
            dict(media(), discarded_packets=[{"flags": "D"}]),
        ]:
            with self.assertRaises(IngestionError):
                associate(rows, VideoInspection(**modified))

    def test_reject_clock_mismatch_and_duplicate_pts(self):
        rows = [pose_row(), pose_row(1, 2, "1000000000.016667")]
        for tick in [0, 20000]:
            video = media()
            video["frames"][1]["best_effort_timestamp"] = tick
            with self.assertRaises(IngestionError):
                associate(rows, VideoInspection(**video))

    def test_policy_rejects_invalid_tolerances_and_unimplemented_transforms(self):
        for value in [0, -1, float("nan"), float("inf")]:
            with self.assertRaises(IngestionError):
                IngestionPolicy(clock_tolerance_seconds=value)
        for options in [
            {"pose_refinement": True},
            {"scale_correction": True},
            {"image_transforms": "rotate"},
        ]:
            with self.assertRaises(IngestionError):
                IngestionPolicy(**options)

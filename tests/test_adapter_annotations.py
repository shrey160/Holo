"""adapter annotations behavioral checks."""

import copy
import tempfile
from decimal import Decimal
from pathlib import Path

from fixtures import FixtureTestCase, fixture, pose_row

from cozmo_ingestion import IngestionError
from cozmo_ingestion.adapters.sensor_recorder import validate_metadata
from cozmo_ingestion.annotations import normalize_annotations
from cozmo_ingestion.storage import encoded, inside


class Tests(FixtureTestCase):
    def test_reject_unsupported_axes_and_version(self):
        with tempfile.TemporaryDirectory() as temp:
            meta, _ = fixture(Path(temp) / "raw")
            for field, value in [
                ("recorded_camera", "raw ARKit camera"),
                ("quaternion_order", "qx,qy,qz,qw"),
            ]:
                altered = copy.deepcopy(meta)
                altered["coordinate_conventions"][field] = value
                with self.assertRaises(IngestionError):
                    validate_metadata(altered)
            meta["app"]["build"] = "unknown"
            with self.assertRaises(IngestionError):
                validate_metadata(meta)

    def test_path_escape_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(IngestionError):
                inside(Path(temp), "../escape")

    def test_scale_prior_bound_to_video_and_not_a_detection(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / "annotation.json"
            data = {
                "schema_version": 1,
                "source_video_sha256": "correct",
                "reference_objects": [
                    {
                        "id": "a4",
                        "width_m": 0.21,
                        "height_m": 0.297,
                        "dimensions_source": "USER_REPORTED",
                        "candidate_window_seconds": [0, 5],
                        "visibility_verified": False,
                    }
                ],
            }
            p.write_text(encoded(data))
            result = normalize_annotations(p, "correct", [pose_row()], Decimal("1000000000"))
            self.assertFalse(result["scale_applied"])
            self.assertEqual(result["reference_objects"][0]["candidate_source_frame_indices"], [0])
            self.assertIsNone(result["reference_objects"][0]["corner_coordinates"])
            with self.assertRaises(IngestionError):
                normalize_annotations(p, "different", [pose_row()], Decimal("1000000000"))

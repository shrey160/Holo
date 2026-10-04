"""Review identity, interval endpoint semantics and controlled fixed-camera diagnostics."""

import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from test_grounding import scene

from cozmo_ingestion.errors import IngestionError
from cozmo_ingestion.storage import sha256, write_json
from cozmo_reconstruction.grounding.analysis import analyze
from cozmo_reconstruction.grounding.confirmation import bottom_offset_interval, load_confirmation
from cozmo_reconstruction.grounding.diagnostics import refine_points
from cozmo_reconstruction.grounding.models import GroundingPolicy


def review_for(identity, annotations, digest):
    return {
        "schema": "holo-grounding-user-confirmation-v1",
        "source_video_sha256": identity["source_video_sha256"],
        "corner_proposals_sha256": digest,
        "reviewed_frame_ranks": [r["rank"] for r in annotations["observations"]],
        "corner_confirmation": {"authority": "USER_CONFIRMED_CHAT", "statement": "accurate"},
        "cover_thickness": {
            "authority": "USER_REPORTED_CHAT",
            "exact_thickness_m": None,
            "lower_bound_m": 0,
            "upper_bound_m": 0.01,
            "lower_bound_inclusive": True,
            "upper_bound_inclusive": False,
            "zero_thickness_assumed": False,
        },
    }


class GroundingReviewTests(unittest.TestCase):
    def test_interval_reversal_preserves_strict_endpoint(self):
        bound = review_for(*scene()[::3], "digest")["cover_thickness"]
        self.assertEqual(
            bottom_offset_interval(0.02, 1, bound),
            {
                "lower_m": 0.01,
                "upper_m": 0.02,
                "lower_inclusive": False,
                "upper_inclusive": True,
            },
        )
        result = bottom_offset_interval(-0.02, -1, bound)
        self.assertEqual(result["lower_m"], -0.02)
        self.assertEqual(result["upper_m"], -0.01)
        self.assertTrue(result["lower_inclusive"])
        self.assertFalse(result["upper_inclusive"])
        self.assertTrue(bottom_offset_interval(0.02, 0, bound)["lower_inclusive"])

    def test_review_binding_and_invalid_bounds(self):
        identity, _, views, annotations = scene()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "review.json"
            good = review_for(identity, annotations, "corners")
            write_json(path, good)
            self.assertEqual(load_confirmation(path, "corners", identity, annotations), good)
            for key, value in (
                ("corner_proposals_sha256", "changed"),
                ("source_video_sha256", "changed"),
                ("reviewed_frame_ranks", [0]),
            ):
                bad = deepcopy(good)
                bad[key] = value
                write_json(path, bad)
                with self.assertRaises(IngestionError):
                    load_confirmation(path, "corners", identity, annotations)
            for key, value in (
                ("upper_bound_m", 0),
                ("lower_bound_m", -1),
                ("upper_bound_m", True),
                ("exact_thickness_m", 0),
                ("zero_thickness_assumed", True),
                ("upper_bound_inclusive", 1),
            ):
                bad = deepcopy(good)
                bad["cover_thickness"][key] = value
                write_json(path, bad)
                with self.assertRaises(IngestionError):
                    load_confirmation(path, "corners", identity, annotations)
            write_json(path, good)
            annotations["cover_thickness_m"] = 0.01
            with self.assertRaises(IngestionError):
                load_confirmation(path, "corners", identity, annotations)

    def test_confirmation_does_not_override_disagreement(self):
        identity, reference, views, annotations = scene()
        annotations["observations"][2]["corners_native"][2][0] += 20
        before = deepcopy((views, annotations))
        report = analyze(
            views,
            reference,
            annotations,
            GroundingPolicy(),
            confirmation=review_for(identity, annotations, "corners"),
        )
        self.assertTrue(report["human_reviewed_corners"])
        self.assertEqual(report["geometry_state"], "DISAGREEMENT_REVIEW_REQUIRED")
        self.assertEqual(report["floor_comparison_status"], "WITHHELD")
        self.assertFalse(report["scale_applied"])
        self.assertEqual((views, annotations), before)
        diagnostic = report["mismatch_diagnostics"]
        self.assertEqual(diagnostic["dominant_residual"]["rank"], 2)
        self.assertEqual(diagnostic["dominant_residual"]["corner_index"], 2)
        self.assertGreater(diagnostic["pixel_objective_point_fit"]["reprojection_max_pixels"], 4)
        self.assertEqual(len(diagnostic["leave_one_view_out"]), len(views))

    def test_pixel_fit_known_scene_and_source_scale_preserved(self):
        import numpy as np

        identity, reference, views, annotations = scene(source_scale=1.2)
        baseline = analyze(views, reference, annotations, GroundingPolicy())
        initial = np.array(baseline["unconstrained_triangulation"]["corners_world_m"])
        candidate = refine_points(
            [v["camera"] for v in views],
            [np.array(r["corners_native"]) for r in annotations["observations"]],
            initial + [0.01, 0.01, 0.02],
        )
        self.assertLess(candidate["reprojection_max_pixels"], 1e-7)
        np.testing.assert_allclose(candidate["corners_world_m"], initial, atol=1e-8)
        report = analyze(
            views,
            reference,
            annotations,
            GroundingPolicy(),
            confirmation=review_for(identity, annotations, "corners"),
        )
        self.assertEqual(report["geometry_state"], "DISAGREEMENT_REVIEW_REQUIRED")
        self.assertFalse(report["scale_applied"])

    def test_reviewed_publication_portable_and_rehashed_false_bound(self):
        from types import SimpleNamespace
        from unittest.mock import patch

        import cv2
        import numpy as np

        from cozmo_reconstruction.grounding.models import GroundingRequest
        from cozmo_reconstruction.grounding.pipeline import GroundingPipeline
        from cozmo_reconstruction.grounding.verification import verify_grounding

        identity, reference, views, annotations = scene()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            prepared = root / "prepared"
            (prepared / "images").mkdir(parents=True)
            for v, row in zip(views, annotations["observations"], strict=True):
                image = prepared / v["image"]
                cv2.imwrite(str(image), np.zeros((240, 320, 3), np.uint8))
                v["image_sha256"] = row["image_sha256"] = sha256(image)
            corners, review = root / "corners.json", root / "review.json"
            write_json(corners, annotations)
            write_json(review, review_for(identity, annotations, sha256(corners)))
            request = GroundingRequest(
                prepared,
                root / "bundle",
                root / "result",
                annotations=corners,
                review_confirmation=review,
            )
            reader = SimpleNamespace(roots={"capture": root / "raw"})
            with (
                patch("cozmo_reconstruction.grounding.pipeline.CaptureReader", return_value=reader),
                patch("cozmo_reconstruction.grounding.pipeline.audit_source", return_value=reader),
                patch(
                    "cozmo_reconstruction.grounding.pipeline.inputs",
                    return_value=(identity, reference, views),
                ),
                patch(
                    "cozmo_reconstruction.grounding.verification.audit_source", return_value=reader
                ),
                patch(
                    "cozmo_reconstruction.grounding.verification.inputs",
                    return_value=(identity, reference, views),
                ),
            ):
                result = GroundingPipeline().run(request)
                self.assertEqual(result["verification"]["status"], "VERIFIED")
                portable = GroundingRequest(prepared, root / "bundle", request.output)
                self.assertEqual(verify_grounding(request.output, portable)["status"], "VERIFIED")
                report_path = request.output / "report.json"
                report = json.loads(report_path.read_text())
                report["cover_thickness_bound"]["upper_bound_m"] = 0
                write_json(report_path, report)
                manifest = json.loads((request.output / "manifest.json").read_text())
                manifest["artifact_sha256"]["report.json"] = sha256(report_path)
                write_json(request.output / "manifest.json", manifest)
                with self.assertRaises(IngestionError) as caught:
                    verify_grounding(request.output, portable)
                self.assertEqual(caught.exception.code, "GROUNDING_REPORT_CHANGED")

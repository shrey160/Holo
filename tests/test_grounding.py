"""Analytic reference geometry, weak evidence and independently audited publication."""

import json
import tempfile
import unittest
from dataclasses import asdict, replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

try:
    import cv2
    import numpy as np
except ImportError as error:
    raise unittest.SkipTest("Install reconstruct or dense extra") from error

from cozmo_ingestion.errors import IngestionError
from cozmo_ingestion.storage import sha256, write_json
from cozmo_reconstruction.grounding.analysis import analyze, supplemental
from cozmo_reconstruction.grounding.annotations import (
    display_to_native,
    load_annotations,
    template,
    validate_corners,
)
from cozmo_reconstruction.grounding.geometry import object_corners, project, triangulate
from cozmo_reconstruction.grounding.models import GroundingPolicy, GroundingRequest
from cozmo_reconstruction.grounding.pipeline import GroundingPipeline
from cozmo_reconstruction.grounding.verification import verify_grounding


def scene(baseline=0.3, source_scale=1.0):
    rotation = cv2.Rodrigues(np.array([0.25, 0.12, 0.03]))[0]
    points = object_corners(0.21, 0.297) @ rotation.T + [-0.1, -0.14, 1.5]
    views, observations = [], []
    identity = {
        "prepared_manifest_sha256": "p",
        "ingestion_manifest_sha256": "b",
        "source_video_sha256": "v",
        "sparse_manifest_sha256": None,
        "dense_manifest_sha256": None,
        "surfaces_manifest_sha256": None,
    }
    for i, center in enumerate(np.linspace(-baseline / 2, baseline / 2, 5)):
        transform = np.eye(4)
        transform[0, 3] = -center
        camera = {
            "K": [[500, 0, 160], [0, 500, 120], [0, 0, 1]],
            "camera_from_world": transform.tolist(),
            "center_m": [center, 0, 0],
        }
        xy, _ = project(camera, points)
        transform[0, 3] *= source_scale
        camera["camera_from_world"] = transform.tolist()
        camera["center_m"][0] *= source_scale
        view = {
            "rank": i,
            "frame_id": f"f{i}",
            "relative_seconds": str(i),
            "image": f"images/{i:06d}.jpg",
            "image_size": [320, 240],
            "image_sha256": f"image{i}",
            "camera": camera,
        }
        views.append(view)
        observations.append(
            {
                k: view[k]
                for k in ("rank", "frame_id", "relative_seconds", "image_sha256", "image_size")
            }
            | {"corners_native": xy.tolist()}
        )
    annotations = template(identity, "opening-a4-reference")
    annotations.update(annotator="ANALYTIC_FIXTURE", human_reviewed=True, observations=observations)
    reference = {
        "id": "opening-a4-reference",
        "width_m": 0.21,
        "height_m": 0.297,
        "dimensions_source": "USER_REPORTED",
        "dimension_uncertainty_m": None,
    }
    return identity, reference, views, annotations


class GroundingTests(unittest.TestCase):
    def test_rectangle_recovered_without_size_constraint(self):
        _, reference, views, annotations = scene()
        report = analyze(views, reference, annotations, GroundingPolicy())
        self.assertEqual(report["unconstrained_triangulation"]["state"], "TRIANGULATED")
        np.testing.assert_allclose(report["size_check"]["width_edges_m"], 0.21, atol=1e-9)
        np.testing.assert_allclose(report["size_check"]["height_edges_m"], 0.297, atol=1e-9)
        self.assertFalse(report["scale_applied"])
        self.assertEqual(report["floor_height"], "UNRESOLVED")
        self.assertEqual(report["reference"]["dimension_uncertainty_m"], None)
        self.assertEqual(report["supplemental"]["stereo"], [])

    def test_scale_error_detected_even_though_pnp_fits_known_size(self):
        _, reference, views, annotations = scene(source_scale=1.2)
        report = analyze(views, reference, annotations, GroundingPolicy())
        self.assertEqual(report["geometry_state"], "DISAGREEMENT_REVIEW_REQUIRED")
        np.testing.assert_allclose(report["size_check"]["width_edges_m"], 0.21 * 1.2, atol=1e-9)
        self.assertAlmostEqual(report["size_check"]["suggested_width_scale"], 1 / 1.2)
        self.assertLess(
            report["pose_check"]["views"][0]["solutions"][0]["reprojection_rms_pixels"], 1e-8
        )
        self.assertFalse(report["scale_applied"])

    def test_swapped_width_height_is_disagreement(self):
        _, reference, views, annotations = scene()
        for row in annotations["observations"]:
            row["corners_native"] = np.roll(row["corners_native"], -1, axis=0).tolist()
        report = analyze(views, reference, annotations, GroundingPolicy())
        self.assertEqual(report["geometry_state"], "DISAGREEMENT_REVIEW_REQUIRED")

    def test_rotation_or_tiny_translation_does_not_measure_scale(self):
        for baseline in (0, 1e-6):
            _, reference, views, annotations = scene(baseline=baseline)
            report = analyze(views, reference, annotations, GroundingPolicy())
            self.assertEqual(report["geometry_state"], "INSUFFICIENT_PARALLAX")
            self.assertIsNone(report["size_check"])
            self.assertEqual(report["sensitivity"]["status"], "NOT_RUN")

    def test_few_views_and_planar_alternatives_retained(self):
        _, reference, views, annotations = scene()
        annotations["observations"] = annotations["observations"][:1]
        report = analyze(views, reference, annotations, GroundingPolicy())
        self.assertEqual(report["geometry_state"], "INSUFFICIENT_OBSERVATIONS")
        self.assertEqual(len(report["pose_check"]["views"][0]["solutions"]), 2)

    def test_behind_camera_rejected(self):
        _, _, views, annotations = scene()
        cameras = [v["camera"] for v in views]
        for camera in cameras:
            # World mirror with retained projected observations: candidate points have negative Z.
            camera["center_m"][0] *= -1
            camera["camera_from_world"][0][3] *= -1
        tri = triangulate(
            cameras,
            [np.array(r["corners_native"]) for r in annotations["observations"]],
            GroundingPolicy(),
        )
        self.assertEqual(tri["state"], "DISAGREEMENT_REVIEW_REQUIRED")
        self.assertFalse(tri["positive_depth_all_views"])

    def test_coordinate_mapping_and_invalid_perimeters(self):
        np.testing.assert_allclose(
            display_to_native([[10, 20]], [640, 360], [1920, 1080]), [[30, 60]]
        )
        good = [[20, 20], [100, 20], [100, 160], [20, 160]]
        validate_corners(good, [320, 240])
        for bad in (
            [good[0], good[2], good[1], good[3]],
            [[20, 20]] * 4,
            [[-1, 20], *good[1:]],
            [[float("nan"), 20], *good[1:]],
        ):
            with self.assertRaises(IngestionError):
                validate_corners(bad, [320, 240])
        with self.assertRaises(IngestionError):
            GroundingPolicy(min_views=0)

    def test_source_bound_annotations_and_unknown_uncertainty(self):
        identity, _, views, annotations = scene()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "corners.json"
            write_json(path, annotations)
            loaded = load_annotations(path, identity, "opening-a4-reference", views)
            self.assertIsNone(loaded["corner_uncertainty_pixels"])
            annotations["observations"][0]["image_sha256"] = "changed"
            write_json(path, annotations)
            with self.assertRaises(IngestionError) as caught:
                load_annotations(path, identity, "opening-a4-reference", views)
            self.assertEqual(caught.exception.code, "GROUNDING_ANNOTATION_SOURCE_CHANGED")

    def test_missing_stereo_and_object_interior_separate_from_floor(self):
        _, reference, views, annotations = scene()
        report = analyze(views, reference, annotations, GroundingPolicy())
        camera = views[0]["camera"] | {
            "rank": 0,
            "image": "000000.jpg",
            "image_size": [320, 240],
            "scale_xy": [1, 1],
            "params": [500, 500, 160, 120],
        }
        with tempfile.TemporaryDirectory() as folder:
            dense = Path(folder)
            (dense / "masks").mkdir()
            write_json(dense / "cameras.json", [camera])
            request = SimpleNamespace(dense=dense, surfaces=None)
            np.savez(dense / "masks/000000.jpg.npz", accepted=np.zeros((240, 320), bool))
            result = supplemental(
                request, annotations, report["unconstrained_triangulation"], report["size_check"]
            )
            self.assertEqual(result["stereo"][0]["status"], "MISSING_STEREO_SUPPORT")
            self.assertEqual(result["stereo"][1]["status"], "NOT_SELECTED_IN_DENSE")
            accepted = np.zeros((240, 320), bool)
            # An accepted floor pixel outside the marked object never contributes.
            accepted[0, 0] = True
            xy = np.mean(annotations["observations"][0]["corners_native"], axis=0).astype(int)
            accepted[xy[1], xy[0]] = True
            np.savez(dense / "masks/000000.jpg.npz", accepted=accepted)
            with patch(
                "cozmo_reconstruction.grounding.analysis.read_array",
                return_value=np.full((240, 320), 1.5),
            ):
                result = supplemental(
                    request,
                    annotations,
                    report["unconstrained_triangulation"],
                    report["size_check"],
                )
            self.assertEqual(result["stereo"][0]["accepted_object_pixels"], 1)

    def test_analytic_publication_and_rehashed_false_report(self):
        identity, reference, views, annotations = scene()
        annotations["notes"] = "</script><script>alert('test')</script>"
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            prepared = root / "prepared"
            (prepared / "images").mkdir(parents=True)
            for view in views:
                image = prepared / view["image"]
                cv2.imwrite(str(image), np.zeros((240, 320, 3), np.uint8))
                view["image_sha256"] = sha256(image)
            for view, row in zip(views, annotations["observations"], strict=True):
                row["image_sha256"] = view["image_sha256"]
            corners = root / "corners.json"
            write_json(corners, annotations)
            request = GroundingRequest(
                prepared, root / "bundle", root / "result", annotations=corners
            )
            snapshot = sha256(corners)
            reader = SimpleNamespace(roots={"capture": root / "raw"})
            # Only source parsing/audits are replaced for this analytic fixture.
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
                self.assertEqual(sha256(corners), snapshot)
                html = (request.output / "index.html").read_text()
                self.assertNotIn("</script><script>alert('test')", html)
                before = {p: sha256(p) for p in request.output.rglob("*") if p.is_file()}
                verify_grounding(request.output, request)
                self.assertEqual(before, {p: sha256(p) for p in before})
                report_path = request.output / "report.json"
                report = json.loads(report_path.read_text())
                report["scale_applied"] = True
                write_json(report_path, report)
                manifest = json.loads((request.output / "manifest.json").read_text())
                manifest["artifact_sha256"]["report.json"] = sha256(report_path)
                write_json(request.output / "manifest.json", manifest)
                with self.assertRaises(IngestionError) as caught:
                    verify_grounding(request.output, request)
                self.assertEqual(caught.exception.code, "GROUNDING_REPORT_CHANGED")
                overlap = replace(request, output=prepared / "new")
                with self.assertRaises(IngestionError) as caught:
                    GroundingPipeline().run(overlap)
                self.assertEqual(caught.exception.code, "OUTPUT_SOURCE_OVERLAP")
            self.assertEqual(asdict(GroundingPolicy())["min_views"], 3)


if __name__ == "__main__":
    unittest.main()

"""Local diagnostics with explicit uncertainty, ambiguity and missing observations."""

import json

import cv2
import numpy as np

from cozmo_reconstruction.dense.geometry import read_array, world_points

from .confirmation import bottom_offset_interval
from .diagnostics import mismatch_diagnostics
from .geometry import pose_solutions, rectangle_metrics, triangulate


def supplemental(request, annotations, tri, metrics, confirmation=None, geometry_passed=True):
    stereo = []
    planes = []
    if request.dense is not None:
        cameras = {c["rank"]: c for c in json.loads((request.dense / "cameras.json").read_text())}
        for row in annotations["observations"]:
            camera = cameras.get(row["rank"])
            if camera is None:
                stereo.append(
                    {
                        "rank": row["rank"],
                        "status": "NOT_SELECTED_IN_DENSE",
                        "accepted_object_pixels": 0,
                    }
                )
                continue
            xy = np.array(row["corners_native"]) * camera["scale_xy"]
            width, height = camera["image_size"]
            polygon = np.zeros((height, width), np.uint8)
            cv2.fillConvexPoly(polygon, np.rint(xy - 0.5).astype(np.int32), 1)
            # Conservative interior excludes uncertain cover boundaries and nearby floor.
            polygon = cv2.erode(polygon, np.ones((7, 7), np.uint8))
            with np.load(request.dense / f"masks/{camera['image']}.npz") as masks:
                accepted = masks["accepted"] & (polygon != 0)
            ys, xs = np.nonzero(accepted)
            entry = {
                "rank": row["rank"],
                "accepted_object_pixels": len(xs),
                "object_interior_pixels": int(polygon.sum()),
                "status": "MISSING_STEREO_SUPPORT" if not len(xs) else "SUPPORTED_PIXELS_ONLY",
            }
            if (
                metrics is not None
                and tri["state"] == "TRIANGULATED"
                and len(xs)
                and geometry_passed
            ):
                depth = read_array(
                    request.dense / f"workspace/stereo/depth_maps/{camera['image']}.geometric.bin"
                )
                xyz = world_points(depth, camera, xs, ys)
                plane = np.array(metrics["plane_world"])
                residuals = xyz @ plane[:3] + plane[3]
                entry["object_plane_signed_distance_median_m"] = float(np.median(residuals))
                entry["object_plane_absolute_distance_p90_m"] = float(
                    np.percentile(np.abs(residuals), 90)
                )
            stereo.append(entry)
    if (
        request.surfaces is not None
        and metrics is not None
        and tri["state"] == "TRIANGULATED"
        and geometry_passed
    ):
        report = json.loads((request.surfaces / "report.json").read_text())
        corners = np.array(tri["corners_world_m"])
        normal = np.array(metrics["plane_world"][:3])
        for candidate in report["planes"]:
            if candidate["orientation"] != "horizontal":
                continue
            equation = np.array(candidate["equation_world"])
            offset = float(corners.mean(axis=0) @ equation[:3] + equation[3])
            thickness = annotations["cover_thickness_m"]
            planes.append(
                {
                    "id": candidate["id"],
                    "semantic_identity": "UNCONFIRMED",
                    "normal_angle_degrees": float(
                        np.degrees(np.arccos(np.clip(abs(normal @ equation[:3]), 0, 1)))
                    ),
                    "cover_center_signed_distance_m": offset,
                    "floor_offset_status": "THICKNESS_UNKNOWN"
                    if thickness is None
                    else "USER_THICKNESS_ASSUMPTION",
                    "assumed_bottom_signed_distance_m": None
                    if thickness is None
                    else offset - thickness * equation[1],
                }
            )
            if confirmation:
                planes[-1]["floor_offset_status"] = "CONDITIONAL_USER_THICKNESS_BOUND"
                planes[-1]["conditional_bottom_signed_distance_interval_m"] = (
                    bottom_offset_interval(offset, equation[1], confirmation["cover_thickness"])
                )
                planes[-1]["assumptions"] = (
                    "Cover flat, stationary and resting on floor; world +Y is vertical. Surface identity unconfirmed."
                )
    return {
        "stereo": stereo,
        "horizontal_surface_comparisons": planes,
        "scope": "Object interior only; shared poses/calibration, not independent truth",
    }


def analyze(views, reference, annotations, policy, request=None, confirmation=None):
    by_rank = {v["rank"]: v for v in views}
    rows = annotations["observations"]
    cameras = [by_rank[r["rank"]]["camera"] for r in rows]
    xy = [np.array(r["corners_native"], float) for r in rows]
    width, height = reference["width_m"], reference["height_m"]
    pose_views, best = [], []
    for row, camera, corners in zip(rows, cameras, xy, strict=True):
        solutions = pose_solutions(camera, corners, width, height, policy)
        usable = [s for s in solutions if s["usable"]]
        ambiguous = (
            len(usable) > 1
            and usable[1]["reprojection_rms_pixels"]
            <= usable[0]["reprojection_rms_pixels"] + policy.ambiguity_pixels
        )
        pose_views.append(
            {"rank": row["rank"], "solutions": solutions, "planar_ambiguity": ambiguous}
        )
        if usable:
            best.append(usable[0])
    pose_summary = {
        "views": pose_views,
        "ambiguous_views": sum(v["planar_ambiguity"] for v in pose_views),
        "usable_views": len(best),
        "size_check": "NOT_INDEPENDENT; declared dimensions are PnP inputs",
    }
    if best:
        centers = np.array([s["center_world_m"] for s in best])
        normals = np.array([s["normal_world"] for s in best])
        pose_summary["best_solution_center_spread_max_m"] = float(
            np.linalg.norm(centers[:, None] - centers, axis=2).max()
        )
        pose_summary["best_solution_normal_spread_max_degrees"] = float(
            np.degrees(np.arccos(np.clip(np.abs(normals @ normals.T), 0, 1))).max()
        )
    tri = triangulate(cameras, xy, policy)
    metrics = None
    sensitivity = {
        "status": "NOT_RUN",
        "interpretation": "Perturbation sensitivity, not a confidence interval",
        "assumed_perturbation_bound_pixels": policy.sensitivity_pixels,
        "corner_uncertainty_pixels": annotations["corner_uncertainty_pixels"],
    }
    state = tri["state"]
    if tri["corners_world_m"] is not None:
        metrics = rectangle_metrics(tri["corners_world_m"], width, height)
    if state == "TRIANGULATED":
        discrepancy = max(
            abs(v) for v in metrics["width_relative_errors"] + metrics["height_relative_errors"]
        )
        if (
            discrepancy > policy.size_relative_tolerance
            or len(best) != len(rows)
            or pose_summary.get("best_solution_center_spread_max_m", 0)
            > policy.max_pose_center_spread_m
            or pose_summary.get("best_solution_normal_spread_max_degrees", 0)
            > policy.max_pose_normal_spread_degrees
        ):
            state = "DISAGREEMENT_REVIEW_REQUIRED"
        elif pose_summary["ambiguous_views"]:
            state = "AMBIGUOUS_OBJECT_POSE"
        else:
            state = "CONSISTENT_LOCAL_REFERENCE"
        rng = np.random.default_rng(policy.seed)
        sizes = []
        for _ in range(policy.sensitivity_trials):
            perturbed = np.array(xy) + rng.uniform(
                -policy.sensitivity_pixels, policy.sensitivity_pixels, (len(xy), 4, 2)
            )
            candidate = triangulate(cameras, perturbed, policy)
            if candidate["state"] == "TRIANGULATED":
                m = rectangle_metrics(candidate["corners_world_m"], width, height)
                sizes.append([np.mean(m["width_edges_m"]), np.mean(m["height_edges_m"])])
        sensitivity.update(
            {
                "status": "COMPUTED",
                "trials": policy.sensitivity_trials,
                "usable_trials": len(sizes),
                "width_height_min_m": np.min(sizes, axis=0).tolist() if sizes else None,
                "width_height_max_m": np.max(sizes, axis=0).tolist() if sizes else None,
            }
        )
    report = {
        "status": "REVIEW_REQUIRED",
        "geometry_state": state,
        "annotated_views": len(rows),
        "candidate_views": len(views),
        "object_id": reference["id"],
        "reference": {
            k: reference.get(k)
            for k in ("width_m", "height_m", "dimensions_source", "dimension_uncertainty_m")
        },
        "human_reviewed_corners": annotations["human_reviewed"],
        "annotator": annotations["annotator"],
        "cover_thickness_m": annotations["cover_thickness_m"],
        "physical_accuracy": "UNVERIFIED",
        "scale_applied": False,
        "calibration": "Source K used numerically with image-edge coordinates; pixel centers/distortion physically unverified",
        "floor_height": "UNRESOLVED"
        if annotations["cover_thickness_m"] is None
        else "USER_THICKNESS_ASSUMPTION",
        "pose_check": pose_summary,
        "unconstrained_triangulation": tri,
        "size_check": metrics,
        "sensitivity": sensitivity,
        "uniform_scale_correction": "NOT_APPLIED; width/height ratios diagnostic only",
        "floorplan": "NOT_RUN",
    }
    report["supplemental"] = (
        supplemental(
            request,
            annotations,
            tri,
            metrics,
            confirmation,
            not confirmation or state == "CONSISTENT_LOCAL_REFERENCE",
        )
        if request
        else {"stereo": [], "horizontal_surface_comparisons": []}
    )
    if confirmation:
        report["human_reviewed_corners"] = True
        report["corner_review"] = confirmation["corner_confirmation"]
        report["cover_thickness_bound"] = confirmation["cover_thickness"]
        report["floor_height"] = (
            "UNRESOLVED; bounded thickness retained, geometry and floor identity required"
        )
        report["floor_comparison_status"] = (
            "CONDITIONAL_COMPARISON"
            if state == "CONSISTENT_LOCAL_REFERENCE" and request and request.surfaces
            else "WITHHELD"
        )
        report["mismatch_diagnostics"] = mismatch_diagnostics(
            cameras, xy, [r["rank"] for r in rows], width, height, tri, policy
        )
    return report

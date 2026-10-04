"""Controlled mismatch experiments; never replace accepted geometry or source poses."""

from copy import deepcopy

import cv2
import numpy as np

from .geometry import object_corners, project, triangulate


def refine_points(cameras, xy, initial):
    """Minimize pixel error independently for each corner with fixed source cameras.

    Deterministic damped Gauss-Newton with positive-depth backtracking. This is
    an exploratory point estimate, not camera BA, a rectangle fit or an acceptance gate.
    """
    points = np.asarray(initial, float).copy()
    for corner in range(4):
        point = points[corner].copy()
        for _ in range(40):
            residual, jacobian = [], []
            for camera, observed in zip(cameras, xy, strict=True):
                transform = np.asarray(camera["camera_from_world"])
                k = np.asarray(camera["K"])
                q = transform[:3, :3] @ point + transform[:3, 3]
                h = k @ q
                pixel = h[:2] / h[2]
                derivative = (k[:2] * h[2] - h[:2, None] * k[2]) / h[2] ** 2
                jacobian.extend(derivative @ transform[:3, :3])
                residual.extend(pixel - observed[corner])
            jacobian, residual = np.array(jacobian), np.array(residual)
            step = np.linalg.lstsq(jacobian, residual, rcond=None)[0]
            if np.linalg.norm(step) < 1e-12:
                break
            accepted = False
            for factor in (1, 0.5, 0.25, 0.125, 0.0625, 0.03125):
                candidate = point - factor * step
                cost = 0.0
                positive = True
                for camera, observed in zip(cameras, xy, strict=True):
                    pixel, depth = project(camera, candidate[None, :])
                    positive &= bool(depth[0] > 0 and np.isfinite(pixel).all())
                    cost += float(np.sum((pixel[0] - observed[corner]) ** 2))
                if positive and cost < float(residual @ residual):
                    point = candidate
                    accepted = True
                    break
            if not accepted:
                break
        points[corner] = point
    errors, positive = [], []
    for camera, observed in zip(cameras, xy, strict=True):
        pixel, depth = project(camera, points)
        errors.append(np.linalg.norm(pixel - observed, axis=1).tolist())
        positive.append(bool((depth > 0).all()))
    return {
        "corners_world_m": points.tolist(),
        "positive_depth_all_views": all(positive),
        "reprojection_errors_pixels": errors,
        "reprojection_max_pixels": float(np.max(errors)),
        "reprojection_rms_pixels": float(np.sqrt(np.mean(np.square(errors)))),
    }


def mismatch_diagnostics(cameras, xy, ranks, width, height, tri, policy):
    if tri["corners_world_m"] is None:
        return {"status": "INSUFFICIENT_GEOMETRY", "acceptance_changed": False}
    refined = []
    points = object_corners(width, height)
    for camera, observed, rank in zip(cameras, xy, ranks, strict=True):
        k = np.asarray(camera["K"])
        result = cv2.solvePnPGeneric(points, observed, k, None, flags=cv2.SOLVEPNP_IPPE)
        alternatives = []
        for index, (rotation, translation) in enumerate(zip(result[1], result[2], strict=True)):
            rotation, translation = cv2.solvePnPRefineLM(
                points,
                observed,
                k,
                None,
                rotation.copy(),
                translation.copy(),
                criteria=(cv2.TERM_CRITERIA_COUNT + cv2.TERM_CRITERIA_EPS, 100, 1e-12),
            )
            pixels = cv2.projectPoints(points, rotation, translation, k, None)[0].reshape(4, 2)
            depths = (points @ cv2.Rodrigues(rotation)[0].T + translation.ravel())[:, 2]
            rms = float(np.sqrt(np.mean(np.sum((pixels - observed) ** 2, axis=1))))
            alternatives.append(
                {
                    "ippe_initialization": index,
                    "reprojection_rms_pixels": rms,
                    "positive_depth": bool((depths > 0).all()),
                    "within_residual_limit": bool(
                        (depths > 0).all() and rms <= policy.max_reprojection_pixels
                    ),
                }
            )
        refined.append({"rank": rank, "alternatives": alternatives})
    shifts = []
    for shift in (-0.5, 0.5):
        shifted = deepcopy(cameras)
        for camera in shifted:
            camera["K"][0][2] += shift
            camera["K"][1][2] += shift
        candidate = triangulate(shifted, xy, policy)
        shifts.append(
            {
                "principal_point_shift_pixels": shift,
                "state": candidate["state"],
                "reprojection_max_pixels": candidate.get("reprojection_max_pixels"),
            }
        )
    holdouts = []
    if len(cameras) > policy.min_views:
        for i, rank in enumerate(ranks):
            training = [j for j in range(len(cameras)) if j != i]
            candidate = triangulate(
                [cameras[j] for j in training], [xy[j] for j in training], policy
            )
            if candidate["corners_world_m"] is None:
                holdouts.append({"held_out_rank": rank, "training_state": candidate["state"]})
                continue
            pixel, depth = project(cameras[i], candidate["corners_world_m"])
            errors = np.linalg.norm(pixel - xy[i], axis=1)
            holdouts.append(
                {
                    "held_out_rank": rank,
                    "training_state": candidate["state"],
                    "training_reprojection_max_pixels": candidate["reprojection_max_pixels"],
                    "held_out_errors_pixels": errors.tolist(),
                    "held_out_positive_depth": bool((depth > 0).all()),
                }
            )
    errors = np.array(tri["reprojection_errors_pixels"])
    worst = np.unravel_index(int(errors.argmax()), errors.shape)
    return {
        "status": "COMPUTED",
        "acceptance_changed": False,
        "residual_limit_pixels": policy.max_reprojection_pixels,
        "dominant_residual": {
            "rank": ranks[worst[0]],
            "corner_index": int(worst[1]),
            "pixels": float(errors[worst]),
        },
        "per_corner_rms_pixels": np.sqrt(np.mean(errors**2, axis=0)).tolist(),
        "refined_per_view_rectangle_poses": refined,
        "refinement_interpretation": "Object pose only; declared size is a fitted input. Refined alternatives may converge to the same pose; no ambiguity resolution claimed.",
        "pixel_center_hypotheses": shifts,
        "leave_one_view_out": holdouts,
        "pixel_objective_point_fit": refine_points(cameras, xy, tri["corners_world_m"]),
        "point_fit_interpretation": "Unconstrained pixel-error fit of points only. Source cameras, corner marks and acceptance result unchanged.",
        "cause": "UNRESOLVED; residuals do not identify camera, shape or calibration error uniquely",
    }

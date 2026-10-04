"""Planar pose alternatives and unconstrained fixed-camera ray triangulation."""

import cv2
import numpy as np


def object_corners(width, height):
    return np.array([[0, 0, 0], [width, 0, 0], [width, height, 0], [0, height, 0]], float)


def project(camera, xyz):
    xyz = np.asarray(xyz)
    transform = np.asarray(camera["camera_from_world"])
    optical = xyz @ transform[:3, :3].T + transform[:3, 3]
    pixels = optical @ np.asarray(camera["K"]).T
    return pixels[:, :2] / pixels[:, 2:3], optical[:, 2]


def pose_solutions(camera, xy, width, height, policy):
    points = object_corners(width, height)
    result = cv2.solvePnPGeneric(
        points, np.asarray(xy, float), np.asarray(camera["K"]), None, flags=cv2.SOLVEPNP_IPPE
    )
    solutions = []
    for rotation, translation in zip(result[1], result[2], strict=True):
        transform = np.eye(4)
        transform[:3, :3] = cv2.Rodrigues(rotation)[0]
        transform[:3, 3] = np.asarray(translation).ravel()
        world = np.linalg.inv(np.asarray(camera["camera_from_world"])) @ transform
        corners = points @ world[:3, :3].T + world[:3, 3]
        projected, depths = project(camera, corners)
        if not np.isfinite(projected).all() or not np.isfinite(world).all():
            continue
        rms = float(np.sqrt(np.mean(np.sum((projected - xy) ** 2, axis=1))))
        solutions.append(
            {
                "world_from_object": world.tolist(),
                "corners_world_m": corners.tolist(),
                "center_world_m": corners.mean(axis=0).tolist(),
                "normal_world": world[:3, 2].tolist(),
                "reprojection_rms_pixels": rms,
                "positive_depth": bool((depths > 0).all()),
                "usable": bool((depths > 0).all() and rms <= policy.max_reprojection_pixels),
            }
        )
    return sorted(solutions, key=lambda s: s["reprojection_rms_pixels"])


def triangulate(cameras, observations, policy):
    """Least-squares closest world rays; no known-size rectangle constraint."""
    if len(cameras) < policy.min_views:
        return {"state": "INSUFFICIENT_OBSERVATIONS", "corners_world_m": None}
    centers = np.array([c["center_m"] for c in cameras])
    rays = []
    for camera, xy in zip(cameras, observations, strict=True):
        optical = np.c_[xy, np.ones(4)] @ np.linalg.inv(np.asarray(camera["K"])).T
        world = optical @ np.asarray(camera["camera_from_world"])[:3, :3]
        rays.append(world / np.linalg.norm(world, axis=1)[:, None])
    rays = np.asarray(rays)
    angles, conditions, points = [], [], []
    for corner in range(4):
        directions = rays[:, corner]
        dots = np.clip(directions @ directions.T, -1, 1)
        # Parallel and antiparallel rays are both geometrically degenerate.
        angle = float(np.degrees(np.arccos(np.abs(dots))).max())
        projection = np.eye(3)[None, ...] - directions[:, :, None] * directions[:, None, :]
        matrix = projection.sum(axis=0)
        condition = float(np.linalg.cond(matrix))
        angles.append(angle)
        conditions.append(condition if np.isfinite(condition) else None)
        if angle < policy.min_angle_degrees or not np.isfinite(condition) or condition > 1e8:
            return {
                "state": "INSUFFICIENT_PARALLAX",
                "corners_world_m": None,
                "corner_max_ray_angles_degrees": angles,
                "ray_system_condition": conditions,
                "camera_baseline_m": float(
                    np.linalg.norm(centers[:, None] - centers, axis=2).max()
                ),
            }
        points.append(np.linalg.solve(matrix, np.einsum("nij,nj->i", projection, centers)))
    xyz = np.array(points)
    errors, positive = [], []
    for camera, xy in zip(cameras, observations, strict=True):
        pixels, depths = project(camera, xyz)
        errors.append(np.linalg.norm(pixels - xy, axis=1).tolist())
        positive.append(bool((depths > 0).all()))
    good = all(positive) and np.max(errors) <= policy.max_reprojection_pixels
    return {
        "state": "TRIANGULATED" if good else "DISAGREEMENT_REVIEW_REQUIRED",
        "corners_world_m": xyz.tolist(),
        "corner_max_ray_angles_degrees": angles,
        "ray_system_condition": conditions,
        "camera_baseline_m": float(np.linalg.norm(centers[:, None] - centers, axis=2).max()),
        "positive_depth_all_views": all(positive),
        "reprojection_errors_pixels": errors,
        "reprojection_max_pixels": float(np.max(errors)),
    }


def rectangle_metrics(corners, width, height):
    points = np.asarray(corners)
    lengths = np.linalg.norm(np.roll(points, -1, axis=0) - points, axis=1)
    widths, heights = lengths[[0, 2]], lengths[[1, 3]]
    normal = np.linalg.svd(points - points.mean(axis=0))[2][-1]
    if normal[1] < 0:
        normal = -normal
    plane = np.r_[normal, -normal @ points.mean(axis=0)]
    return {
        "width_edges_m": widths.tolist(),
        "height_edges_m": heights.tolist(),
        "diagonals_m": [
            float(np.linalg.norm(points[0] - points[2])),
            float(np.linalg.norm(points[1] - points[3])),
        ],
        "declared_diagonal_m": float(np.hypot(width, height)),
        "width_relative_errors": (widths / width - 1).tolist(),
        "height_relative_errors": (heights / height - 1).tolist(),
        "suggested_width_scale": float(width / widths.mean()),
        "suggested_height_scale": float(height / heights.mean()),
        "plane_world": plane.tolist(),
        "coplanarity_residual_max_m": float(np.abs(points @ normal + plane[3]).max()),
    }

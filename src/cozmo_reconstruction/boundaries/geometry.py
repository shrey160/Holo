"""Pixel regions, source-world floor basis and supported intervals with gaps intact."""

import numpy as np

from cozmo_ingestion.errors import require


def polygon_mask(xy, polygon):
    """Convex perimeter coverage, including its boundary; image-edge coordinates."""
    polygon = np.asarray(polygon, float)
    edge = np.roll(polygon, -1, axis=0) - polygon
    delta = np.asarray(xy)[:, None, :] - polygon[None, :, :]
    cross = edge[None, :, 0] * delta[:, :, 1] - edge[None, :, 1] * delta[:, :, 0]
    return (cross >= -1e-9).all(axis=1) | (cross <= 1e-9).all(axis=1)


def floor_frame(plane, points):
    plane = np.asarray(plane, float).copy()
    plane /= np.linalg.norm(plane[:3])
    if plane[1] < 0:
        plane *= -1
    normal = plane[:3]
    u = np.array([1.0, 0, 0]) - normal[0] * normal
    require(np.linalg.norm(u) > 1e-6, "BOUNDARY_FLOOR_INVALID", "Horizontal floor basis")
    u /= np.linalg.norm(u)
    v = np.cross(normal, u)
    origin = np.mean(points, axis=0)
    origin -= (origin @ normal + plane[3]) * normal
    transform = np.eye(4)
    transform[:3, :3] = np.column_stack((u, v, normal))
    transform[:3, 3] = origin
    return {
        "plane_world": plane.tolist(),
        "origin_world_m": origin.tolist(),
        "u_world": u.tolist(),
        "v_world": v.tolist(),
        "world_from_floor": transform.tolist(),
        "floor_from_world": np.linalg.inv(transform).tolist(),
        "authority": "REVIEWED_LOCAL_FLOOR_HYPOTHESIS; not a measured room datum",
    }


def floor_uv(points, frame):
    axes = np.array([frame["u_world"], frame["v_world"]])
    return (np.asarray(points) - frame["origin_world_m"]) @ axes.T


def plane_intersection(wall, frame):
    floor = np.asarray(frame["plane_world"])
    wall = np.asarray(wall)
    direction = np.cross(floor[:3], wall[:3])
    length = np.linalg.norm(direction)
    if length < 1e-6:
        return None
    direction /= length
    uv_direction = direction @ np.array([frame["u_world"], frame["v_world"]]).T
    first = np.flatnonzero(np.abs(uv_direction) > 1e-8)[0]
    if uv_direction[first] < 0:
        direction *= -1
    matrix = np.array([floor[:3], wall[:3], direction])
    origin = np.linalg.solve(matrix, [-floor[3], -wall[3], direction @ frame["origin_world_m"]])
    return origin, direction


def supported_views(ranks, centers, policy, minimum):
    unique, counts = np.unique(ranks, return_counts=True)
    views = unique[counts >= policy.min_points_per_view].tolist()
    positions = np.array([centers[int(rank)] for rank in views]).reshape(-1, 3)
    baseline = (
        float(np.linalg.norm(positions[:, None] - positions, axis=2).max())
        if len(positions)
        else 0.0
    )
    return len(views) >= minimum and baseline >= policy.min_baseline_m, views, baseline


def interval_runs(bins):
    """Only adjacent occupied bins join; no bridging empty bins."""
    runs = []
    for value in sorted(set(int(v) for v in bins)):
        if not runs or value != runs[-1][-1] + 1:
            runs.append([])
        runs[-1].append(value)
    return runs


def supported_cells(points, ranks, centers, frame, policy):
    uv = floor_uv(points, frame)
    indices = np.floor(uv / policy.cell_m).astype(np.int64)
    cells = []
    for cell in np.unique(indices, axis=0):
        mask = (indices == cell).all(axis=1)
        good, views, baseline = supported_views(ranks[mask], centers, policy, policy.min_cell_views)
        if good:
            cells.append(
                {
                    "cell": cell.tolist(),
                    "observations": int(mask.sum()),
                    "view_ranks": views,
                    "baseline_m": baseline,
                }
            )
    return cells


def wall_spans(points, ranks, centers, wall, frame, policy):
    line = plane_intersection(wall, frame)
    if line is None:
        return {"status": "PARALLEL_PLANES", "segments": []}
    origin, direction = line
    t = (points - origin) @ direction
    bins = np.floor(t / policy.cell_m).astype(np.int64)
    supported = []
    for cell in np.unique(bins):
        mask = bins == cell
        good, _, _ = supported_views(ranks[mask], centers, policy, policy.min_wall_views)
        if good:
            supported.append(int(cell))
    segments = []
    for run in interval_runs(supported):
        mask = np.isin(bins, run)
        # Endpoints use actual observed extent, not a full-cell envelope.
        start, end = float(t[mask].min()), float(t[mask].max())
        if end - start < policy.min_span_m:
            continue
        endpoints = origin + np.array([start, end])[:, None] * direction
        _, views, baseline = supported_views(ranks[mask], centers, policy, policy.min_wall_views)
        floor = np.array(frame["plane_world"])
        heights = points[mask] @ floor[:3] + floor[3]
        segments.append(
            {
                "bin_indices": run,
                "endpoints_world_m": endpoints.tolist(),
                "endpoints_floor_uv_m": floor_uv(endpoints, frame).tolist(),
                "projected_span_estimated_m": end - start,
                "reviewed_observations": int(mask.sum()),
                "view_ranks": views,
                "camera_baseline_m": baseline,
                "observed_height_range_above_floor_m": [float(heights.min()), float(heights.max())],
                "near_floor_observations": int((np.abs(heights) <= policy.near_floor_m).sum()),
                "junction_status": "PROJECTED_WALL_PATCH; floor-wall junction not certified",
                "endpoint_status": "OBSERVED_PROJECTED_EXTENT; not confirmed room corners",
            }
        )
    return {
        "status": "SUPPORTED_PARTIAL_SPANS" if segments else "INSUFFICIENT_SPAN_SUPPORT",
        "segments": segments,
        "line_origin_world_m": origin.tolist(),
        "line_direction_world": direction.tolist(),
        "supported_bins": supported,
        "bin_resolution_m": policy.cell_m,
        "gaps": "All absent/weak bins retained; no endpoint extension or corner closure",
    }

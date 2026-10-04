"""CPU plan derivatives: height persistence and bounded robust line suggestions."""

from collections import deque
from dataclasses import asdict, dataclass

import cv2
import numpy as np

from cozmo_reconstruction.boundaries.geometry import interval_runs, plane_intersection


@dataclass(frozen=True)
class PlanPolicy:
    cell_m: float = 0.1
    height_min_m: float = 0.6
    height_max_m: float = 2.4
    height_band_m: float = 0.4
    min_band_points: int = 4
    min_bands: int = 2
    min_height_span_m: float = 0.8
    min_neighbors: int = 2
    min_component_cells: int = 6
    min_component_span_m: float = 0.5
    line_bin_m: float = 0.15
    line_distance_m: float = 0.08
    min_line_bin_points: int = 20
    min_line_span_m: float = 0.45
    max_refit_angle_degrees: float = 15.0


def persistent_cells(points, policy):
    """Tall occupied columns only; never fill empty cells or certify wall identity."""
    keep = (points[:, 1] >= policy.height_min_m) & (points[:, 1] <= policy.height_max_m)
    subset = points[keep]
    if not len(subset):
        return [], np.zeros(len(points), dtype=bool)
    uv = subset[:, [0, 2]] * [1, -1]
    cells = np.floor(uv / policy.cell_m).astype(np.int64)
    bands = np.floor((subset[:, 1] - policy.height_min_m) / policy.height_band_m).astype(int)
    keys, inverse = np.unique(cells, axis=0, return_inverse=True)
    n_bands = int(np.floor((policy.height_max_m - policy.height_min_m) / policy.height_band_m)) + 1
    counts = np.zeros((len(keys), n_bands), dtype=np.int64)
    np.add.at(counts, (inverse, bands), 1)
    reliable = counts[inverse, bands] >= policy.min_band_points
    low, high = np.full(len(keys), np.inf), np.full(len(keys), -np.inf)
    np.minimum.at(low, inverse[reliable], subset[reliable, 1])
    np.maximum.at(high, inverse[reliable], subset[reliable, 1])
    qualifies = ((counts >= policy.min_band_points).sum(axis=1) >= policy.min_bands) & (
        high - low >= policy.min_height_span_m
    )
    occupied = {tuple(key) for key in keys[qualifies]}
    neighbors = np.array(
        [
            sum(
                (int(x) + dx, int(y) + dy) in occupied
                for dx in (-1, 0, 1)
                for dy in (-1, 0, 1)
                if dx or dy
            )
            for x, y in keys
        ]
    )
    qualifies &= neighbors >= policy.min_neighbors
    remaining = {tuple(key) for key in keys[qualifies]}
    retained = set()
    while remaining:
        first = min(remaining)
        remaining.remove(first)
        queue, component = deque([first]), []
        while queue:
            cell = queue.popleft()
            component.append(cell)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    neighbor = (cell[0] + dx, cell[1] + dy)
                    if neighbor in remaining:
                        remaining.remove(neighbor)
                        queue.append(neighbor)
        if (
            len(component) >= policy.min_component_cells
            and np.ptp(component, axis=0).max() * policy.cell_m >= policy.min_component_span_m
        ):
            retained.update(component)
    qualifies &= np.array([tuple(key) in retained for key in keys])
    result = [
        {
            "cell": key.tolist(),
            "height_range_m": [float(low[i]), float(high[i])],
            "height_bands": np.flatnonzero(counts[i] >= policy.min_band_points).tolist(),
            "voxel_points": int(counts[i][counts[i] >= policy.min_band_points].sum()),
        }
        for i, key in enumerate(keys)
        if qualifies[i]
    ]
    mask = np.zeros(len(points), dtype=bool)
    mask[np.flatnonzero(keep)] = qualifies[inverse] & reliable
    return result, mask


def line_suggestions(positions, labels, planes, frame, persistent, policy):
    """Refit 2D geometry without snapping, extrapolation, closure or semantic admission."""
    suggestions, diagnostics = [], []
    uv = positions[:, [0, 2]] * [1, -1]
    axes = np.array([frame["u_world"], frame["v_world"]])
    for i, plane in enumerate(planes):
        if plane["orientation"] != "vertical" or plane["evidence_status"] != "MULTIVIEW_CANDIDATE":
            continue
        selected = persistent & (labels == i)
        row = {"plane_id": plane["id"], "persistent_voxel_points": int(selected.sum())}
        diagnostics.append(row)
        line = plane_intersection(plane["equation_world"], frame)
        if selected.sum() < 100 or line is None:
            row["status"] = "INSUFFICIENT_HEIGHT_PERSISTENCE"
            continue
        original_direction = line[1] @ axes.T
        values = uv[selected]
        fit = cv2.fitLine(values.astype(np.float32), cv2.DIST_HUBER, 0, 0.001, 0.001).ravel()
        direction, origin = fit[:2].astype(float), fit[2:].astype(float)
        direction /= np.linalg.norm(direction)
        if direction @ original_direction < 0:
            direction *= -1
        angle = float(np.degrees(np.arccos(np.clip(abs(direction @ original_direction), 0, 1))))
        residual = np.abs((values - origin) @ np.array([-direction[1], direction[0]]))
        row.update(refit_angle_degrees=angle, residual_p90_m=float(np.quantile(residual, 0.9)))
        if angle > policy.max_refit_angle_degrees:
            row["status"] = "REFIT_DISAGREES_WITH_SOURCE_PLANE"
            continue
        inlier = residual <= policy.line_distance_m
        values, heights = values[inlier], positions[selected, 1][inlier]
        distance = (values - origin) @ direction
        bins = np.floor(distance / policy.line_bin_m).astype(int)
        support = []
        for cell in np.unique(bins):
            mask = bins == cell
            if (
                mask.sum() >= policy.min_line_bin_points
                and np.ptp(heights[mask]) >= policy.min_height_span_m
            ):
                support.append(int(cell))
        row["status"] = "NO_CONTIGUOUS_SUPPORTED_SPAN"
        for run in interval_runs(support):
            mask = np.isin(bins, run)
            start, end = float(distance[mask].min()), float(distance[mask].max())
            if end - start < policy.min_line_span_m:
                continue
            row["status"] = "GEOMETRIC_SUGGESTIONS_ONLY"
            suggestions.append(
                {
                    "plane_id": plane["id"],
                    "uv": (origin + np.array([start, end])[:, None] * direction).tolist(),
                    "status": "HEIGHT_PERSISTENT_GEOMETRY; architectural identity unverified",
                    "voxel_points": int(mask.sum()),
                    "bin_indices": run,
                    "refit_angle_degrees": angle,
                    "height_range_m": [float(heights[mask].min()), float(heights[mask].max())],
                }
            )
    return suggestions, diagnostics


def structure_plan(positions, labels, planes, frame):
    policy = PlanPolicy()
    vertical_indices = [
        i
        for i, p in enumerate(planes)
        if p["orientation"] == "vertical" and p["evidence_status"] == "MULTIVIEW_CANDIDATE"
    ]
    indices = np.flatnonzero(np.isin(labels, vertical_indices))
    cells, selected = persistent_cells(positions[indices], policy)
    mask = np.zeros(len(positions), dtype=bool)
    mask[indices] = selected
    suggestions, diagnostics = line_suggestions(positions, labels, planes, frame, mask, policy)
    return {
        "policy": asdict(policy),
        "cells": cells,
        "suggested_spans": suggestions,
        "plane_diagnostics": diagnostics,
        "input_voxel_points": len(positions),
        "vertical_candidate_voxel_points": len(indices),
        "retained_voxel_points": int(mask.sum()),
        "scope": "Height-persistent occupancy; tall furniture/curtains can remain. No semantic wall admission.",
        "closed_room_polygon": None,
        "room_area": None,
        "measured_ceiling_reference_used": False,
    }

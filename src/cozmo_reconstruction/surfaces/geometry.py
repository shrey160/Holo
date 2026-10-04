"""Deterministic RANSAC and occupied patches; never fill a plane's bounding box."""

from collections import deque

import numpy as np

from cozmo_ingestion.errors import require


def canonical(normal, offset):
    length = np.linalg.norm(normal)
    normal, offset = normal / length, offset / length
    if normal[np.argmax(np.abs(normal))] < 0:
        normal, offset = -normal, -offset
    return np.r_[normal, offset]


def refine(points):
    center = points.mean(axis=0)
    _, singular, vectors = np.linalg.svd(points - center, full_matrices=False)
    if len(singular) < 3 or singular[1] <= 1e-8:
        return None
    return canonical(vectors[-1], -vectors[-1] @ center)


def fit_planes(xyz, policy):
    require(
        xyz.ndim == 2 and xyz.shape[1] == 3 and np.isfinite(xyz).all(),
        "SURFACE_CLOUD_INVALID",
        "Finite Nx3 source-world cloud required",
    )
    rng = np.random.default_rng(policy.seed)
    index = np.sort(rng.choice(len(xyz), min(len(xyz), policy.fit_points), replace=False))
    remaining = xyz[index].copy()
    planes = []
    for _ in range(policy.max_planes):
        if len(remaining) < policy.min_fit_inliers:
            break
        best, best_count = None, 0
        for _ in range(policy.iterations):
            a, b, c = remaining[rng.choice(len(remaining), 3, replace=False)]
            normal = np.cross(b - a, c - a)
            if np.linalg.norm(normal) < 1e-8:
                continue
            plane = canonical(normal, -normal @ a)
            count = np.count_nonzero(np.abs(remaining @ plane[:3] + plane[3]) <= policy.distance_m)
            if count > best_count:
                best, best_count = plane, count
        if best_count < policy.min_fit_inliers:
            break
        for _ in range(3):
            mask = np.abs(remaining @ best[:3] + best[3]) <= policy.distance_m
            proposed = refine(remaining[mask])
            if proposed is None:
                break
            best = proposed
        mask = np.abs(remaining @ best[:3] + best[3]) <= policy.distance_m
        if mask.sum() < policy.min_fit_inliers:
            break
        planes.append(best)
        remaining = remaining[~mask]
    return np.asarray(planes).reshape(-1, 4)


def assign(xyz, planes, distance):
    """Assign to nearest candidate; -1 means no plane, including at empty input."""
    labels = np.full(len(xyz), -1, dtype=np.int16)
    residuals = np.full(len(xyz), np.inf)
    if len(planes):
        for start in range(0, len(xyz), 50000):
            values = np.abs(xyz[start : start + 50000] @ planes[:, :3].T + planes[:, 3])
            best = values.argmin(axis=1)
            error = values[np.arange(len(best)), best]
            labels[start : start + len(best)] = np.where(error <= distance, best, -1)
            residuals[start : start + len(best)] = error
    return labels, residuals


def basis(plane):
    normal = plane[:3]
    reference = np.eye(3)[np.argmin(np.abs(normal))]
    u = np.cross(normal, reference)
    u /= np.linalg.norm(u)
    return np.stack((u, np.cross(normal, u)))


def occupied_patches(points, plane, cell_size):
    """Connected occupied grid cells with observation counts, no hull closure."""
    axes = basis(plane)
    uv = points @ axes.T
    if not len(points):
        return {"basis_world": axes.tolist(), "cells": [], "components": [], "span_m": [0, 0]}
    cells, counts = np.unique(np.floor(uv / cell_size).astype(np.int64), axis=0, return_counts=True)
    remaining = {tuple(c) for c in cells.tolist()}
    components = []
    while remaining:
        first = min(remaining)
        remaining.remove(first)
        queue, found = deque([first]), []
        while queue:
            cell = queue.popleft()
            found.append(cell)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    neighbor = (cell[0] + dx, cell[1] + dy)
                    if neighbor in remaining:
                        remaining.remove(neighbor)
                        queue.append(neighbor)
        components.append(sorted(found))
    components.sort(key=lambda c: (-len(c), c[0]))
    return {
        "basis_world": axes.tolist(),
        "plane_origin_world_m": (-plane[3] * plane[:3]).tolist(),
        "cell_size_m": cell_size,
        "cells": [[int(a), int(b), int(n)] for (a, b), n in zip(cells, counts, strict=True)],
        "components": [[list(cell) for cell in component] for component in components],
        "span_m": np.ptp(uv, axis=0).tolist(),
        "bounds_uv_m": [uv.min(axis=0).tolist(), uv.max(axis=0).tolist()],
        "occupied_grid_area_m2": float(len(cells) * cell_size**2),
        "area_scope": "occupied coarse cells, not measured surface area; holes retained",
    }

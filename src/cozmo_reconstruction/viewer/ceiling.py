"""Provisional upper-envelope height, independently of external ceiling measurements."""

from dataclasses import asdict, dataclass

import numpy as np


@dataclass(frozen=True)
class CeilingPolicy:
    cell_m: float = 0.25
    upper_height_min_m: float = 1.8
    upper_height_max_m: float = 4.0
    min_upper_points_per_cell: int = 20
    cell_top_quantile: float = 0.98
    envelope_quantile: float = 0.90
    min_supported_cells: int = 12
    near_estimate_m: float = 0.08


def estimate_ceiling(positions, room):
    """Sparse upper coverage can estimate a height but cannot certify a ceiling plane."""
    policy = CeilingPolicy()
    axes = np.asarray(room["axes_in_floor_uv"])
    bounds = np.asarray(room["bounds_in_room_axes_m"])
    local = (positions[:, [0, 2]] * [1, -1]) @ axes.T
    eligible = (
        np.isfinite(positions).all(axis=1)
        & ((local >= bounds[0]) & (local <= bounds[1])).all(axis=1)
        & (positions[:, 1] >= policy.upper_height_min_m)
        & (positions[:, 1] <= policy.upper_height_max_m)
    )
    heights = positions[eligible, 1]
    cells = np.floor((local[eligible] - bounds[0]) / policy.cell_m).astype(int)
    keys, inverse = np.unique(cells, axis=0, return_inverse=True)
    order = np.argsort(inverse, kind="stable")
    groups = np.split(order, np.flatnonzero(np.diff(inverse[order])) + 1) if len(order) else []
    rows = []
    for indices in groups:
        if len(indices) >= policy.min_upper_points_per_cell:
            rows.append(
                {
                    "cell": keys[inverse[indices[0]]].tolist(),
                    "upper_voxels": len(indices),
                    "robust_top_m": float(np.quantile(heights[indices], policy.cell_top_quantile)),
                }
            )
    result = {
        "method": "spatially balanced robust upper envelope",
        "policy": asdict(policy),
        "status": "INSUFFICIENT_UPPER_COVERAGE",
        "height_estimated_m": None,
        "support_band_m": None,
        "supported_cells": rows,
        "upper_voxels": len(heights),
        "ceiling_plane_verified": False,
        "external_reference_used": False,
        "scale_corrected": False,
        "limitations": "Coverage termination, wall tops or tall objects can mimic a ceiling. Floor and scale remain provisional.",
    }
    if len(rows) < policy.min_supported_cells:
        return result
    tops = np.array([r["robust_top_m"] for r in rows])
    estimate = float(np.quantile(tops, policy.envelope_quantile))
    result.update(
        status="PROVISIONAL_UPPER_ENVELOPE",
        height_estimated_m=estimate,
        support_band_m=np.quantile(tops, [0.85, 0.95]).tolist(),
        support_band_kind="spread of upper tile heights, not a calibrated confidence interval",
        point_height_p999_m=float(np.quantile(heights, 0.999)),
        near_estimate_cells=int((np.abs(tops - estimate) <= policy.near_estimate_m).sum()),
    )
    result["near_estimate_area_fraction"] = (
        result["near_estimate_cells"] * policy.cell_m**2 / room["area_estimated_m2"]
    )
    return result

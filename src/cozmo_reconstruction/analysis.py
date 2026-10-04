"""Recompute track geometry from fixed cameras; quality signals are not accuracy claims."""

from collections import Counter
from itertools import combinations

import numpy as np

from .cameras import project


def point_metrics(point, cameras, policy):
    residuals, depths, directions = [], [], []
    ranks = []
    for observation in point["observations"]:
        rank = observation["rank"]
        camera = cameras[rank]
        pixel, depth = project(camera, point["xyz_m"])
        residuals.append(float(np.linalg.norm(pixel - observation["xy"])))
        depths.append(depth)
        direction = np.asarray(point["xyz_m"]) - np.asarray(camera["center_m"])
        norm = np.linalg.norm(direction)
        directions.append(direction / norm if norm > 1e-15 else np.zeros(3))
        ranks.append(rank)
    angles = [
        float(np.degrees(np.arccos(np.clip(a @ b, -1, 1)))) for a, b in combinations(directions, 2)
    ]
    reasons = []
    if len(set(ranks)) != len(ranks):
        reasons.append("DUPLICATE_IMAGE_IN_TRACK")
    if len(ranks) < policy.min_track_length:
        reasons.append("SHORT_TRACK")
    if not depths or min(depths) <= 0:
        reasons.append("NONPOSITIVE_DEPTH")
    if (
        not residuals
        or not np.isfinite(residuals).all()
        or max(residuals) > policy.max_reprojection_pixels
    ):
        reasons.append("REPROJECTION")
    if max(angles, default=0) < policy.min_angle_degrees:
        reasons.append("LOW_PARALLAX")
    return {
        "accepted": not reasons,
        "reasons": reasons,
        "residuals": residuals,
        "depths": depths,
        "max_angle_degrees": max(angles, default=0),
    }


def distribution(values):
    if not values:
        return {"count": 0, "median": None, "p90": None, "maximum": None}
    a = np.asarray(values)
    return {
        "count": len(values),
        "median": float(np.median(a)),
        "p90": float(np.percentile(a, 90)),
        "maximum": float(np.max(a)),
    }


def analyze(mapping, points, candidates, cameras, policy):
    by_rank = {c["rank"]: c for c in cameras}
    for c in by_rank.values():
        fx, fy, cx, cy = c["params"]
        c["K"] = [[fx, 0, cx], [0, fy, cy], [0, 0, 1]]
    rejected = Counter()
    for point in candidates:
        rejected.update(point_metrics(point, by_rank, policy)["reasons"])
    counts = Counter()
    errors, angles, depths, lengths = [], [], [], []
    parent = {v["rank"]: v["rank"] for v in mapping}

    def find(rank):
        while parent[rank] != rank:
            parent[rank] = parent[parent[rank]]
            rank = parent[rank]
        return rank

    for point in points:
        metrics = point_metrics(point, by_rank, policy)
        if not metrics["accepted"]:
            raise ValueError("Published point violates track geometry policy")
        observations = point["observations"]
        anchor = observations[0]["rank"]
        for observation in observations:
            rank = observation["rank"]
            counts[rank] += 1
            parent[find(rank)] = find(anchor)
        errors.extend(metrics["residuals"])
        depths.extend(metrics["depths"])
        angles.append(metrics["max_angle_degrees"])
        lengths.append(len(observations))
    components = Counter(find(rank) for rank in parent)
    largest = max(components.values(), default=0) if points else 0
    fraction = len(counts) / len(mapping)
    residual = distribution(errors)
    strong = (
        fraction >= 0.7
        and largest / len(mapping) >= 0.7
        and residual["median"] is not None
        and residual["median"] <= 2
        and residual["p90"] <= 4
    )
    return {
        "status": "SPARSE_RECONSTRUCTED_WITH_FINDINGS",
        "readiness": "REVIEW_REQUIRED",
        "geometry_signal": "SUPPORTED" if strong else "WEAK",
        "geometry_signal_thresholds": "Proposed: >=70% images/track component, median<=2px, p90<=4px",
        "input_views": len(mapping),
        "candidate_points": len(candidates),
        "accepted_points": len(points),
        "rejected_points": len(candidates) - len(points),
        "rejection_reason_counts": dict(rejected),
        "supported_images": len(counts),
        "supported_image_fraction": fraction,
        "track_component_sizes": sorted(components.values(), reverse=True),
        "largest_track_component_images": largest,
        "reprojection_native_pixels": residual,
        "track_length": distribution(lengths),
        "max_track_angle_degrees": distribution(angles),
        "optical_depth_m": distribution(depths),
        "image_support": [
            {
                "rank": v["rank"],
                "valid_track_count": counts[v["rank"]],
                "relative_seconds": v["relative_seconds"],
                "flags": v["flags"],
            }
            for v in mapping
        ],
        "camera_refinement": "NONE",
        "scale": "SOURCE_ARKIT_METRES_UNREFINED",
        "measurement_accuracy": "UNVERIFIED",
        "architecture_coverage": "MANUAL_REVIEW_REQUIRED",
        "floorplan": "NOT_RUN",
        "dense_surfaces": "NOT_RUN",
        "limitations": [
            "Source distortion and pixel-center convention remain unverified",
            "Sparse support may be on furniture, moving objects or reflections",
            "Reprojection consistency does not verify dimensions or complete walls",
        ],
    }

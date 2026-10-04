"""Restrict geometry to reviewed accepted samples, then project supported wall spans."""

import json

import numpy as np

from cozmo_ingestion.errors import require
from cozmo_reconstruction.dense.geometry import read_array, world_points

from .geometry import floor_frame, polygon_mask, supported_cells, supported_views, wall_spans
from .reviews import ROLES


def classify_samples(xs, ys, labels, regions):
    roles = np.zeros(len(xs), np.int8)
    selected = np.full(len(xs), -1, np.int16)
    rejection_priority = np.array([0, 0, 0, 3, 2, 1])
    xy = np.column_stack((xs + 0.5, ys + 0.5))
    # Rejections override architectural marks, independent of region order.
    for positive in (True, False):
        for index, row in regions:
            if (row["role"] in ("FLOOR", "WALL")) != positive:
                continue
            mask = polygon_mask(xy, row["polygon_dense"]) & (labels == int(row["plane_id"][1:]) - 1)
            role = ROLES.index(row["role"])
            if positive:
                require(
                    not np.any(mask & (roles != 0) & (roles != role)),
                    "BOUNDARY_REGION_CONFLICT",
                    "Conflicting floor/wall marks",
                )
            else:
                mask &= rejection_priority[role] > rejection_priority[roles]
            # Keep the first equal-role region for reproducible lineage.
            mask &= (roles == 0) | (roles != role)
            roles[mask], selected[mask] = role, index
    return roles, selected


def observations(request, review):
    surface = request.surfaces
    dense = surface.upstream.output
    cameras = sorted(json.loads((dense / "cameras.json").read_text()), key=lambda c: c["rank"])
    collected = {
        k: []
        for k in ("rank", "sample_index", "x", "y", "plane_index", "role", "region_index", "xyz_m")
    }
    counts = np.zeros(len(ROLES), np.int64)
    for camera in cameras:
        regions = [
            (i, row) for i, row in enumerate(review["regions"]) if row["rank"] == camera["rank"]
        ]
        with np.load(surface.output / f"observations/{camera['image']}.npz") as data:
            xs, ys, labels = data["x"], data["y"], data["plane_index"]
            roles, region_indices = classify_samples(xs, ys, labels, regions)
            counts += np.bincount(roles, minlength=len(ROLES))
            mask = roles != 0
            if not np.any(mask):
                continue
            depth = read_array(
                dense / f"workspace/stereo/depth_maps/{camera['image']}.geometric.bin"
            )
            xyz = world_points(depth, camera, xs[mask], ys[mask])
            values = {
                "rank": np.full(mask.sum(), camera["rank"], np.int64),
                "sample_index": np.flatnonzero(mask),
                "x": xs[mask],
                "y": ys[mask],
                "plane_index": labels[mask],
                "role": roles[mask],
                "region_index": region_indices[mask],
                "xyz_m": xyz,
            }
            for key, value in values.items():
                collected[key].append(value)
    arrays = {
        k: np.concatenate(v)
        if v
        else np.empty((0, 3) if k == "xyz_m" else (0,), dtype=float if k == "xyz_m" else np.int64)
        for k, v in collected.items()
    }
    centers = {c["rank"]: c["center_m"] for c in cameras}
    return arrays, dict(zip(ROLES, map(int, counts), strict=True)), centers


def analyze_geometry(planes, review, arrays, counts, centers, policy):
    by_plane = {p["id"]: p for p in planes}
    xyz, ranks, labels, roles = (arrays[k] for k in ("xyz_m", "rank", "plane_index", "role"))
    floor_id = review["floor_plane_id"]
    frame = None
    floor_result = {"plane_id": floor_id, "status": "NO_REVIEWED_FLOOR", "cells": []}
    if floor_id:
        mask = (roles == ROLES.index("FLOOR")) & (labels == int(floor_id[1:]) - 1)
        good, views, baseline = supported_views(
            ranks[mask], centers, policy, policy.min_floor_views
        )
        floor_result.update(
            status="INSUFFICIENT_FLOOR_SUPPORT",
            reviewed_observations=int(mask.sum()),
            view_ranks=views,
            camera_baseline_m=baseline,
        )
        if good:
            frame = floor_frame(by_plane[floor_id]["equation_world"], xyz[mask])
            floor_result["cells"] = supported_cells(xyz[mask], ranks[mask], centers, frame, policy)
            floor_result["status"] = (
                "SUPPORTED_LOCAL_FLOOR" if floor_result["cells"] else "INSUFFICIENT_CELL_SUPPORT"
            )
            if not floor_result["cells"]:
                frame = None
    walls = []
    for plane in planes:
        mask = (roles == ROLES.index("WALL")) & (labels == int(plane["id"][1:]) - 1)
        if not np.any(mask):
            continue
        good, views, baseline = supported_views(ranks[mask], centers, policy, policy.min_wall_views)
        result = {
            "plane_id": plane["id"],
            "reviewed_observations": int(mask.sum()),
            "view_ranks": views,
            "camera_baseline_m": baseline,
            "review_region_ids": [
                r["id"]
                for r in review["regions"]
                if r["plane_id"] == plane["id"] and r["role"] == "WALL"
            ],
            "status": "NO_SUPPORTED_FLOOR" if frame is None else "INSUFFICIENT_WALL_SUPPORT",
            "segments": [],
        }
        if frame is not None and good:
            result.update(
                wall_spans(xyz[mask], ranks[mask], centers, plane["equation_world"], frame, policy)
            )
        walls.append(result)
    segments = sum(len(w["segments"]) for w in walls)
    return {
        "status": "PARTIAL_BOUNDARY_HYPOTHESES" if segments else "INSUFFICIENT_BOUNDARY_SUPPORT",
        "floor_frame": frame,
        "local_floor": floor_result,
        "walls": walls,
        "supported_segments": segments,
        "review_counts": counts,
        "review_authority": review["authority"],
        "human_confirmed_regions": review["human_confirmed"],
        "semantic_scope": "Only marked image regions; no whole-plane architectural promotion",
        "units": "source ARKit estimated metres",
        "physical_accuracy": "UNVERIFIED",
        "closed_room_polygon": None,
        "room_area_m2": None,
        "verified_room_dimensions": None,
        "missing_spans": "Unreviewed, rejected, weak and absent bins remain unresolved; no closure or orthogonal snapping",
        "floor_coverage_scope": "Local occupied evidence cells, not room footprint or floor area",
        "scale_applied": False,
        "pose_refinement": False,
        "grounding_geometry_used": False,
    }


def analyze(request, review, plane_report, policy):
    arrays, counts, centers = observations(request, review)
    report = analyze_geometry(plane_report["planes"], review, arrays, counts, centers, policy)
    report["reference_calibration"] = (
        json.loads((request.grounding / "report.json").read_text())["geometry_state"]
        if request.grounding
        else "NOT_USED; physical scale unverified"
    )
    report["region_observations"] = [
        {
            "region_id": row["id"],
            "role": row["role"],
            "observations": int((arrays["region_index"] == index).sum()),
        }
        for index, row in enumerate(review["regions"])
    ]
    return report, arrays

"""Per-view accepted-depth evidence and provisional semantics for candidate planes."""

import json
from pathlib import Path

import cv2
import numpy as np

from cozmo_ingestion.errors import require
from cozmo_ingestion.storage import write_json
from cozmo_reconstruction.dense.geometry import read_array, world_points

from .geometry import assign, occupied_patches

PALETTE = np.array(
    [
        [220, 80, 55],
        [45, 180, 110],
        [60, 110, 235],
        [210, 150, 20],
        [175, 75, 215],
        [25, 190, 195],
        [235, 115, 170],
        [120, 170, 35],
        [90, 70, 175],
        [170, 125, 90],
        [50, 155, 235],
        [195, 70, 100],
    ],
    dtype=np.uint8,
)


def plane_summary(index, plane, points, residuals, views, centers, policy):
    patches = occupied_patches(points, plane, policy.patch_cell_m)
    upright = abs(float(plane[1]))
    limit = np.deg2rad(policy.orientation_degrees)
    orientation = (
        "horizontal"
        if upright >= np.cos(limit)
        else "vertical"
        if upright <= np.sin(limit)
        else "oblique"
    )
    qualified = [v for v in views if v["samples"] >= policy.min_view_samples]
    positions = np.array([centers[v["image"]] for v in qualified]).reshape(-1, 3)
    baseline = (
        float(np.max(np.linalg.norm(positions[:, None] - positions[None, :], axis=2)))
        if len(positions)
        else 0.0
    )
    camera_y = np.median(np.array(list(centers.values()))[:, 1])
    height = float(np.median(points[:, 1])) if len(points) else None
    delta = float(camera_y - height) if height is not None else None
    role = "oblique_or_nonarchitectural"
    if orientation == "vertical":
        role = "wall_or_furniture"
    elif orientation == "horizontal" and delta is not None:
        role = (
            "floor_or_furniture"
            if delta >= 0.5
            else "ceiling_or_other"
            if delta < -0.2
            else "furniture_or_other"
        )
    flags = []
    if len(qualified) < policy.min_views:
        flags.append("INSUFFICIENT_SELECTED_VIEW_SUPPORT")
    if baseline < policy.min_baseline_m:
        flags.append("INSUFFICIENT_CAMERA_BASELINE")
    largest = patches["components"][0] if patches["components"] else []
    patch_span = (
        (np.ptp(np.array(largest), axis=0) + 1) * policy.patch_cell_m if largest else np.zeros(2)
    )
    if min(patch_span) < policy.min_span_m:
        flags.append("SMALL_OR_NARROW_CONNECTED_PATCH")
    if orientation == "oblique":
        flags.append("NOT_GRAVITY_ALIGNED_ARCHITECTURAL_CANDIDATE")
    if role in ("furniture_or_other", "oblique_or_nonarchitectural"):
        flags.append("NONARCHITECTURAL_OR_AMBIGUOUS_HEIGHT")
    return {
        "id": f"P{index + 1:02d}",
        "equation_world": plane.tolist(),
        "equation_convention": "unit normal dot source-world xyz + d = 0",
        "color_rgb": PALETTE[index % len(PALETTE)].tolist(),
        "orientation": orientation,
        "role_hypothesis": role,
        "semantic_status": "UNCONFIRMED; requires source-image review",
        "evidence_status": "WEAK" if flags else "MULTIVIEW_CANDIDATE",
        "flags": flags,
        "voxel_points": len(points),
        "residual_median_m": float(np.median(residuals)) if len(points) else None,
        "residual_p90_m": float(np.percentile(residuals, 90)) if len(points) else None,
        "median_y_m": height,
        "median_camera_height_above_patch_m": delta,
        "qualified_views": len(qualified),
        "camera_baseline_m": baseline,
        "largest_patch_span_m": patch_span.tolist(),
        "views": sorted(views, key=lambda v: (-v["samples"], v["rank"])),
        "patches": patches,
    }


def observations(dense: Path, planes, policy, stage=None, verify_samples=None):
    """Only upstream accepted pixels at a declared stride supply plane evidence."""
    cameras = sorted(json.loads((dense / "cameras.json").read_text()), key=lambda c: c["rank"])
    mapping = {v["image"]: v for v in json.loads((dense / "input_mapping.json").read_text())}
    views = [[] for _ in planes]
    rows = []
    if stage:
        (stage / "observations").mkdir()
        (stage / "overlays").mkdir()
    for camera in cameras:
        name = camera["image"]
        depth = read_array(dense / f"workspace/stereo/depth_maps/{name}.geometric.bin")
        with np.load(dense / f"masks/{name}.npz") as masks:
            accepted = masks["accepted"]
            sampled = accepted[:: policy.sample_stride, :: policy.sample_stride]
            ys, xs = np.nonzero(sampled)
            xs, ys = xs * policy.sample_stride, ys * policy.sample_stride
            support = masks["support"][ys, xs]
        xyz = world_points(depth, camera, xs, ys)
        labels, residuals = assign(xyz, planes, policy.distance_m)
        if verify_samples:
            with np.load(verify_samples / f"observations/{name}.npz") as saved:
                require(
                    all(
                        np.array_equal(saved[k], value)
                        for k, value in {
                            "x": xs,
                            "y": ys,
                            "plane_index": labels,
                            "dense_support": support,
                        }.items()
                    ),
                    "SURFACE_OBSERVATIONS_CHANGED",
                    name,
                )
        if stage:
            np.savez_compressed(
                stage / f"observations/{name}.npz",
                x=xs,
                y=ys,
                plane_index=labels,
                dense_support=support,
            )
            rgb = cv2.imread(str(dense / f"workspace/images/{name}"))
            require(rgb is not None and rgb.shape[:2] == depth.shape, "SURFACE_RGB_INVALID", name)
            overlay = (rgb * 0.5).astype(np.uint8)
            for i in range(len(planes)):
                for x, y in zip(xs[labels == i], ys[labels == i], strict=True):
                    cv2.circle(
                        overlay,
                        (int(x), int(y)),
                        2,
                        tuple(int(c) for c in PALETTE[i % len(PALETTE), ::-1]),
                        -1,
                    )
            cv2.putText(
                overlay,
                f"rank {camera['rank']} | candidate observations only",
                (12, 28),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (255, 255, 255),
                1,
            )
            require(
                cv2.imwrite(
                    str(stage / f"overlays/{name}"), np.concatenate((rgb, overlay), axis=1)
                ),
                "SURFACE_OVERLAY_FAILED",
                name,
            )
        counts = []
        for i in range(len(planes)):
            mask = labels == i
            count = int(mask.sum())
            counts.append(count)
            if count:
                views[i].append(
                    {
                        "image": name,
                        "rank": camera["rank"],
                        "frame_id": mapping[name]["frame_id"],
                        "relative_seconds": mapping[name]["relative_seconds"],
                        "samples": count,
                        "fraction_of_sampled_accepted": count / len(xs),
                        "residual_median_m": float(np.median(residuals[mask])),
                        "residual_p90_m": float(np.percentile(residuals[mask], 90)),
                    }
                )
        rows.append(
            {
                "image": name,
                "rank": camera["rank"],
                "accepted_samples": len(xs),
                "plane_samples": counts,
                "unassigned_samples": int((labels < 0).sum()),
            }
        )
    return views, rows, {c["image"]: c["center_m"] for c in cameras}


def analyze(dense, planes, policy, stage=None, verify_samples=None):
    with np.load(dense / "cloud.npz") as cloud:
        xyz = cloud["xyz_m"]
    labels, errors = assign(xyz, planes, policy.distance_m)
    views, rows, centers = observations(dense, planes, policy, stage, verify_samples)
    candidates = [
        plane_summary(i, p, xyz[labels == i], errors[labels == i], views[i], centers, policy)
        for i, p in enumerate(planes)
    ]
    report = {
        "status": "REVIEW_REQUIRED",
        "planes": candidates,
        "units": "source ARKit estimated metres",
        "physical_accuracy": "UNVERIFIED",
        "gravity": "exporter-declared +Y up; not independently calibrated",
        "input_voxel_points": len(xyz),
        "unassigned_voxel_points": int((labels < 0).sum()),
        "selected_views": len(rows),
        "view_observations": rows,
        "multiview_candidates": sum(
            p["evidence_status"] == "MULTIVIEW_CANDIDATE" for p in candidates
        ),
        "confirmed_architectural_surfaces": 0,
        "floorplan": "NOT_RUN",
        "mesh": "NOT_RUN",
        "dimensions": "UNVALIDATED",
        "missing_spans": "No boundaries filled; occupied cells and rejected/unassigned observations retained",
        "furniture_rejection": "small/narrow/height/orientation flags only; semantic rejection requires image review",
    }
    if stage:
        write_json(stage / "report.json", report)
        np.savez_compressed(stage / "cloud_labels.npz", plane_index=labels)
    elif verify_samples:
        with np.load(verify_samples / "cloud_labels.npz") as saved:
            require(np.array_equal(saved["plane_index"], labels), "SURFACE_LABELS_CHANGED", "Cloud")
    return report

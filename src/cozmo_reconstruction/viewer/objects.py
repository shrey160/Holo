"""Source-bound visual object labels and approximate cloud-supported footprints."""

import cv2
import numpy as np

from cozmo_ingestion.storage import sha256


def visible_projection(xyz, camera, pixel_bin=3, depth_tolerance_m=0.12):
    transform = np.asarray(camera["camera_from_world"])
    local = xyz @ transform[:3, :3].T + transform[:3, 3]
    depth = local[:, 2]
    fx, fy, cx, cy = camera["params"]
    uv = local[:, :2] / np.maximum(depth[:, None], 1e-9) * [fx, fy] + [cx, cy]
    width, height = camera["image_size"]
    valid = (
        (depth > 0.05)
        & np.isfinite(uv).all(axis=1)
        & (uv[:, 0] >= 0)
        & (uv[:, 0] < width)
        & (uv[:, 1] >= 0)
        & (uv[:, 1] < height)
    )
    indices = np.flatnonzero(valid)
    keys = np.floor(uv[valid] / pixel_bin).astype(int)
    columns = int(np.ceil(width / pixel_bin))
    bins = keys[:, 1] * columns + keys[:, 0]
    nearest = np.full(columns * int(np.ceil(height / pixel_bin)), np.inf)
    np.minimum.at(nearest, bins, depth[valid])
    visible = np.zeros(len(xyz), dtype=bool)
    visible[indices] = depth[valid] <= nearest[bins] + depth_tolerance_m
    return uv, visible


def approximate_objects(xyz, positions, cameras, dense_root, room, review):
    if review.get("schema") != "holo-object-regions-v1":
        raise ValueError("Unsupported object region review")
    axes = np.asarray(room["axes_in_floor_uv"])
    bounds = np.asarray(room["bounds_in_room_axes_m"])
    local = (positions[:, [0, 2]] * [1, -1]) @ axes.T
    inside = ((local >= bounds[0]) & (local <= bounds[1])).all(axis=1)
    by_rank = {c["rank"]: c for c in cameras}
    projections, results = {}, []
    colors = ["#c0859a", "#bd9759", "#6b91b1", "#8a829d", "#a3a35f"]
    identities = set()
    for obj in review["objects"]:
        if obj["id"] in identities or not (1 <= len(obj["label"]) <= 60):
            raise ValueError("Invalid or duplicate object identity")
        identities.add(obj["id"])
        interval = np.asarray(obj["height_interval_m"], dtype=float)
        minimum = np.asarray(obj["minimum_footprint_m"], dtype=float)
        if (
            interval.shape != (2,)
            or minimum.shape != (2,)
            or not np.isfinite(np.r_[interval, minimum]).all()
            or not 0 <= interval[0] < interval[1] <= 4
            or np.any(minimum <= 0)
            or np.any(minimum > 2)
        ):
            raise ValueError("Invalid object height or minimum footprint prior")
        selected = np.zeros(len(xyz), dtype=bool)
        regions = []
        for region in obj["regions"]:
            camera = by_rank[region["rank"]]
            source = dense_root / "workspace" / "images" / camera["image"]
            if (
                sha256(source) != region["image_sha256"]
                or camera["image_size"] != region["image_size"]
            ):
                raise ValueError("Object review image identity changed")
            width, height = camera["image_size"]
            poly = np.asarray(region["polygon_px"], dtype=float)
            if (
                poly.ndim != 2
                or poly.shape[1] != 2
                or len(poly) < 3
                or not np.isfinite(poly).all()
                or np.any(poly < 0)
                or np.any(poly[:, 0] >= width)
                or np.any(poly[:, 1] >= height)
            ):
                raise ValueError("Object review polygon outside source RGB")
            if camera["rank"] not in projections:
                projections[camera["rank"]] = visible_projection(xyz, camera)
            uv, visible = projections[camera["rank"]]
            mask = np.zeros((height, width), dtype=np.uint8)
            cv2.fillPoly(mask, [np.rint(poly).astype(np.int32)], 1)
            pixel = np.floor(uv).astype(np.int64).clip([0, 0], [width - 1, height - 1])
            admitted = (
                visible
                & inside
                & (mask[pixel[:, 1], pixel[:, 0]] == 1)
                & (positions[:, 1] >= interval[0])
                & (positions[:, 1] <= interval[1])
            )
            selected |= admitted
            regions.append({**region, "admitted_voxels": int(admitted.sum())})
        if selected.sum() < 80:
            results.append(
                {
                    "id": obj["id"],
                    "label": obj["label"],
                    "status": "INSUFFICIENT_VISIBLE_SUPPORT",
                    "regions": regions,
                }
            )
            continue
        observed = np.quantile(local[selected], [0.05, 0.95], axis=0)
        center = observed.mean(axis=0)
        extent = np.maximum(observed[1] - observed[0], minimum)
        box = np.array([center - extent / 2, center + extent / 2])
        box = np.clip(box, bounds[0], bounds[1])
        x0, y0 = box[0]
        x1, y1 = box[1]
        corners = np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]])
        results.append(
            {
                "id": obj["id"],
                "label": obj["label"],
                "status": "APPROXIMATE_IMAGE_ASSISTED_FOOTPRINT",
                "authority": review.get("authority"),
                "bounds_in_room_axes_m": box.tolist(),
                "footprint_floor_uv_m": (corners @ axes).tolist(),
                "observed_bounds_in_room_axes_m": observed.tolist(),
                "minimum_extent_prior_used": bool(np.any(minimum > observed[1] - observed[0])),
                "clipped_to_room": bool(
                    np.any(box != np.array([center - extent / 2, center + extent / 2]))
                ),
                "height_range_estimated_m": np.quantile(
                    positions[selected, 1], [0.05, 0.95]
                ).tolist(),
                "source_voxels": int(selected.sum()),
                "regions": regions,
                "color": colors[len(results) % len(colors)],
                "scope": "Partial visible surfaces with class-size priors; identity/extent not independently verified",
            }
        )
    return results

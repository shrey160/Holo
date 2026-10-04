"""Explicitly inferred room completion, separate from certified structural evidence."""

from dataclasses import asdict, dataclass
from html import escape

import numpy as np


@dataclass(frozen=True)
class RoughRoomPolicy:
    endpoint_trim_quantile: float = 0.05
    assumed_entry_width_m: float = 0.8
    minimum_extent_m: float = 1.0


def complete_rough_room(candidate_spans, reviewed_spans, camera_path, ceiling=None):
    """Fit a rectangular hypothesis; never promote a candidate into reviewed geometry."""
    policy = RoughRoomPolicy()
    # One vote per source plane avoids repeatedly weighting fragmented intervals.
    by_plane = {}
    for span in candidate_spans:
        points = np.asarray(span["uv"], dtype=float)
        if points.shape != (2, 2) or not np.isfinite(points).all():
            raise ValueError("Rough room requires finite two-endpoint plane intervals")
        length = float(np.linalg.norm(points[1] - points[0]))
        if length < 0.3:
            continue
        if span["plane_id"] not in by_plane or length > by_plane[span["plane_id"]][0]:
            by_plane[span["plane_id"]] = (length, points)
    if len(by_plane) < 3:
        raise ValueError("Rough completion requires at least three source plane candidates")
    intervals = [value[1] for value in by_plane.values()]
    directions = np.array([p[1] - p[0] for p in intervals])
    angles = np.arctan2(directions[:, 1], directions[:, 0])
    seed = np.angle(np.mean(np.exp(4j * angles))) / 4
    deviations = (angles - seed + np.pi / 4) % (np.pi / 2) - np.pi / 4
    angle = float(seed + np.median(deviations))
    axes = np.array([[np.cos(angle), np.sin(angle)], [-np.sin(angle), np.cos(angle)]])
    alignment = np.abs((directions / np.linalg.norm(directions, axis=1)[:, None]) @ axes.T)
    if len(set(alignment.argmax(axis=1))) < 2:
        raise ValueError("Rough completion requires two differently oriented plane families")
    projected = np.concatenate(intervals) @ axes.T
    bounds = np.quantile(
        projected, [policy.endpoint_trim_quantile, 1 - policy.endpoint_trim_quantile], axis=0
    )
    # Do not trim away the few source-bound reviewed observations.
    reviewed = [p for s in reviewed_spans for p in s["endpoints_floor_uv_m"]]
    if reviewed:
        projected_review = np.asarray(reviewed) @ axes.T
        bounds[0] = np.minimum(bounds[0], projected_review.min(axis=0))
        bounds[1] = np.maximum(bounds[1], projected_review.max(axis=0))
    dimensions = bounds[1] - bounds[0]
    if np.any(dimensions < policy.minimum_extent_m):
        raise ValueError("Candidate coverage is too narrow for a rough room")
    x0, y0 = bounds[0]
    x1, y1 = bounds[1]
    corners = np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]])
    path = np.asarray(camera_path, dtype=float).reshape(-1, 2)
    if not np.isfinite(path).all():
        raise ValueError("Camera path must contain finite coordinates")
    local_path = path @ axes.T
    entry = inferred_entry(local_path, bounds, policy.assumed_entry_width_m)
    return {
        "status": "INFERRED_ROUGH_COMPLETION",
        "model": "single rectangular room; approximate orthogonal walls",
        "policy": asdict(policy),
        "axes_in_floor_uv": axes.tolist(),
        "bounds_in_room_axes_m": bounds.tolist(),
        "polygon_floor_uv_m": (corners @ axes).tolist(),
        "dimensions_estimated_m": dimensions.tolist(),
        "area_estimated_m2": float(np.prod(dimensions)),
        "walls": [
            {"id": f"W{i + 1}", "status": "INFERRED", "uv": (corners[i : i + 2] @ axes).tolist()}
            for i in range(4)
        ],
        "entry": entry,
        "source_plane_ids": sorted(by_plane),
        "reviewed_patch_count": len(reviewed_spans),
        "ceiling_reference": ceiling,
        "scale_corrected": False,
        "assumptions": [
            "Missing walls and corners are completed with a rectangle prior.",
            "Candidate planes may follow curtains or furniture; all four full walls are inferred.",
            "Entry position uses the capture path; width and swing symbol are assumed.",
            "Dimensions and area use unchanged source-estimated scale.",
            "Ceiling height, if supplied, is a separate user reference, not a scale calibration.",
        ],
    }


def inferred_entry(path, bounds, width):
    """First outside-to-inside crossing, otherwise a clearly stated nearest-edge guess."""
    if not len(path):
        return None
    inside = ((path >= bounds[0]) & (path <= bounds[1])).all(axis=1)
    point, method = path[0], "NEAREST_EDGE_TO_CAPTURE_START"
    for i in range(1, len(path)):
        if inside[i] and not inside[i - 1]:
            a, b = path[i - 1], path[i]
            intersections = []
            for axis in (0, 1):
                if abs(b[axis] - a[axis]) < 1e-12:
                    continue
                for value in bounds[:, axis]:
                    t = (value - a[axis]) / (b[axis] - a[axis])
                    q = a + t * (b - a)
                    if (
                        0 <= t <= 1
                        and np.all(q >= bounds[0] - 1e-9)
                        and np.all(q <= bounds[1] + 1e-9)
                    ):
                        intersections.append((t, q))
            if intersections:
                point = min(intersections, key=lambda row: row[0])[1]
                method = "FIRST_CAPTURE_PATH_ENTRY_CROSSING"
                break
    # W1 bottom, W2 right, W3 top, W4 left in the fitted room frame.
    distances = [
        abs(point[1] - bounds[0, 1]),
        abs(point[0] - bounds[1, 0]),
        abs(point[1] - bounds[1, 1]),
        abs(point[0] - bounds[0, 0]),
    ]
    side = int(np.argmin(distances))
    along = 0 if side in (0, 2) else 1
    width = min(width, float((bounds[1, along] - bounds[0, along]) * 0.6))
    center = float(
        np.clip(
            point[along], bounds[0, along] + width / 2 + 0.05, bounds[1, along] - width / 2 - 0.05
        )
    )
    return {
        "wall_id": f"W{side + 1}",
        "side_index": side,
        "center_along_room_axis_m": center,
        "width_assumed_m": width,
        "status": "INFERRED_POSITION_AND_ASSUMED_WIDTH",
        "method": method,
        "swing": "ILLUSTRATIVE_ONLY",
    }


def rough_room_svg(room, reviewed_spans):
    """Portable complete drawing; dashed walls keep inferred closure visible."""
    bounds = np.asarray(room["bounds_in_room_axes_m"])
    axes = np.asarray(room["axes_in_floor_uv"])
    width, depth = room["dimensions_estimated_m"]
    scale = min(540 / width, 520 / depth)
    left, top = (900 - width * scale) / 2, 150
    right, bottom = left + width * scale, top + depth * scale

    def pixel(local):
        # 3D Top looks down with floor v up; SVG screen y increases downward.
        return np.array([left, bottom]) + (np.asarray(local) - bounds[0]) * [scale, -scale]

    def coords(points):
        return " ".join(f"{x:.2f},{y:.2f}" for x, y in pixel(points))

    def text(x, y, value, size=17, color="#365650", anchor="middle"):
        return (
            f'<text x="{x:.2f}" y="{y:.2f}" font-size="{size}" '
            f'fill="{color}" text-anchor="{anchor}">{escape(value)}</text>'
        )

    body = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 860" role="img" aria-labelledby="title desc">',
        '<title id="title">Complete approximate room floor plan</title>',
        '<desc id="desc">Four inferred walls and an approximate entrance, fitted to source plane candidates. Physical dimensions are unverified.</desc>',
        '<rect width="900" height="860" fill="#fcfcf8"/>',
        '<g font-family="Arial, sans-serif">',
        text(450, 45, "SINGLE ROOM · ROUGH FLOOR PLAN", 24, "#163e37"),
        text(450, 76, "Complete outline · inferred walls and corners", 17),
        f'<rect x="{left:.2f}" y="{top:.2f}" width="{width * scale:.2f}" height="{depth * scale:.2f}" fill="#eaf1e8"/>',
        # Dashed rather than solid: completion is deliberately a hypothesis.
        f'<rect x="{left:.2f}" y="{top:.2f}" width="{width * scale:.2f}" height="{depth * scale:.2f}" fill="none" stroke="#1e6355" stroke-width="7" stroke-dasharray="16 7"/>',
        f'<path d="M{left:.2f} {top - 35:.2f} H{right:.2f} M{left:.2f} {top - 44:.2f} V{top - 26:.2f} M{right:.2f} {top - 44:.2f} V{top - 26:.2f}" fill="none" stroke="#47625a" stroke-width="2"/>',
        text(450, top - 47, f"≈ {width:.1f} m"),
        f'<path d="M{right + 38:.2f} {top:.2f} V{bottom:.2f} M{right + 29:.2f} {top:.2f} H{right + 47:.2f} M{right + 29:.2f} {bottom:.2f} H{right + 47:.2f}" fill="none" stroke="#47625a" stroke-width="2"/>',
        f'<text transform="translate({right + 65:.2f} {(top + bottom) / 2:.2f}) rotate(90)" text-anchor="middle" font-size="18" fill="#365650">≈ {depth:.1f} m</text>',
    ]
    ceiling = room.get("ceiling_reference")
    estimate = room.get("ceiling_estimate", {}).get("height_estimated_m")
    body.append(text(450, 700, f"Floor area ≈ {room['area_estimated_m2']:.0f} m²", 18))
    if estimate is not None:
        body.append(
            text(450, 770, f"Ceiling estimate ≈ {estimate:.2f} m · provisional upper envelope", 16)
        )
    if ceiling:
        body.append(
            text(450, 798, f"Ceiling ≈ {ceiling['value_m']:g} m · separate user measurement", 16)
        )
    if not room.get("objects"):
        body.append(text(450, (top + bottom) / 2, "ROOM", 25, "#21483f"))
    for obj in room.get("objects", []):
        if "bounds_in_room_axes_m" not in obj:
            continue
        box = np.asarray(obj["bounds_in_room_axes_m"])
        screen = pixel(box)
        x, y = screen.min(axis=0)
        w, h = np.ptp(screen, axis=0)
        cx, cy = x + w / 2, y + h / 2
        body.append(
            f'<rect x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}" rx="5" fill="{obj["color"]}" fill-opacity="0.35" stroke="{obj["color"]}" stroke-width="2"><title>{escape(obj["label"])}: approximate image-assisted placement</title></rect>'
        )
        if obj["id"] == "bed":
            body.append(
                f'<rect x="{x + 8:.2f}" y="{y + 8:.2f}" width="{max(w - 16, 1):.2f}" height="22" rx="6" fill="#ffffff88"/>'
            )
        if w < 95 and h > w:
            body.append(
                f'<text transform="translate({cx:.2f} {cy:.2f}) rotate(-90)" font-size="15" fill="#36413c" text-anchor="middle">{escape(obj["label"])}</text>'
            )
        elif len(obj["label"]) > 10 and w < 110:
            parts = obj["label"].split(" ", 1)
            body.extend([text(cx, cy - 4, parts[0], 14), text(cx, cy + 14, parts[-1], 14)])
        else:
            body.append(text(cx, cy + 5, obj["label"], 15))
    entry = room["entry"]
    if entry:
        side, center, half = (
            entry["side_index"],
            entry["center_along_room_axis_m"],
            entry["width_assumed_m"] / 2,
        )
        along = 0 if side in (0, 2) else 1
        normal = 1 - along
        edge = bounds[0 if side in (0, 3) else 1, normal]
        ends = np.zeros((2, 2))
        ends[:, along], ends[:, normal] = [center - half, center + half], edge
        a, b = pixel(ends)
        inward = np.zeros(2)
        inward[normal] = 1 if side in (0, 3) else -1
        screen_inward = inward * [1, -1]
        leaf = a + screen_inward * entry["width_assumed_m"] * scale
        body.extend(
            [
                f'<polyline points="{coords(ends)}" fill="none" stroke="#fcfcf8" stroke-width="12"/>',
                f'<path d="M{a[0]:.2f} {a[1]:.2f} L{leaf[0]:.2f} {leaf[1]:.2f} M{b[0]:.2f} {b[1]:.2f} Q{b[0] + screen_inward[0] * half * scale:.2f} {b[1] + screen_inward[1] * half * scale:.2f} {leaf[0]:.2f} {leaf[1]:.2f}" fill="none" stroke="#a67530" stroke-width="2.5"/>',
                text(
                    (a[0] + b[0]) / 2 + (-22 if side == 3 else 22 if side == 1 else 0),
                    (a[1] + b[1]) / 2 + (-20 if side == 0 else 30 if side == 2 else 0),
                    "Entry?",
                    17,
                    "#8c6025",
                    "end" if side == 3 else "start" if side == 1 else "middle",
                ),
            ]
        )
    # Small reviewed patches on top of completion, without snapping them onto it.
    for span in reviewed_spans:
        body.append(
            f'<polyline points="{coords(np.asarray(span["endpoints_floor_uv_m"]) @ axes.T)}" fill="none" stroke="#2173ad" stroke-width="6"/>'
        )
    body.extend(
        [
            text(
                450, 730, "Dashed green: inferred boundary · object footprints are approximate", 16
            ),
            text(450, 752, "Blue: reviewed patches · entrance width and swing are assumed", 15),
            text(450, 827, "Dimensions and object extents use estimated scale; allow errors.", 15),
            "</g></svg>",
        ]
    )
    return "\n".join(body)

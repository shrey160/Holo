"""Capture-route hypotheses from timestamped poses, never door measurements."""

from dataclasses import asdict, dataclass

import numpy as np


@dataclass(frozen=True)
class RoutePolicy:
    window_seconds: float = 8.0
    scan_radius_m: float = 0.85
    minimum_turn_degrees: float = 70.0
    minimum_scan_seconds: float = 4.0
    revisit_distance_m: float = 1.2
    max_gap_seconds: float = 2.0
    opening_seconds: float = 3.0


def analyze_route(mapping, policy=None):
    """Find sustained scanning stays, with unresolved movement between them.

    No outside/exit state is required: directly connected rooms and corridors
    use the same transition model. Brief doorway scans are not room stays.
    Position-based revisits are provisional until geometry/image confirmation.
    """
    policy = policy or RoutePolicy()
    rows = sorted(mapping, key=lambda v: float(v["relative_seconds"]))
    times = np.array([float(v["relative_seconds"]) for v in rows])
    matrices = np.asarray([v["pose"]["world_from_camera"] for v in rows], dtype=float)
    if len(rows) < 3:
        return _report(policy, [], [], [])
    if (
        matrices.shape != (len(rows), 4, 4)
        or not np.isfinite(matrices).all()
        or not np.isfinite(times).all()
        or np.any(np.diff(times) <= 0)
    ):
        raise ValueError("Route requires finite poses and strictly increasing unique timestamps")
    centers = matrices[:, [0, 2], 3]
    forward = matrices[:, [0, 2], 2]
    horizontal = np.linalg.norm(forward, axis=1) >= 0.35
    yaw = np.arctan2(forward[:, 1], forward[:, 0])
    half = policy.window_seconds / 2
    windows = []
    flags = np.zeros(len(rows), dtype=bool)
    for i, t in enumerate(times):
        selected = np.flatnonzero((times >= t - half) & (times <= t + half))
        if len(selected) < 5 or t < policy.opening_seconds + half:
            continue
        if times[selected[-1]] - times[selected[0]] < policy.window_seconds * 0.8:
            continue
        if np.max(np.diff(times[selected])) > policy.max_gap_seconds:
            continue
        points = centers[selected]
        radius = float(np.quantile(np.linalg.norm(points - np.median(points, axis=0), axis=1), 0.9))
        look = selected[horizontal[selected]]
        turn = float(np.degrees(np.ptp(np.unwrap(yaw[look])))) if len(look) >= 3 else 0.0
        flags[i] = radius <= policy.scan_radius_m and turn >= policy.minimum_turn_degrees
        windows.append(
            {
                "seconds": float(t),
                "radius_m": radius,
                "turn_degrees": turn,
                "scanning_candidate": bool(flags[i]),
            }
        )
    runs = []
    for i in np.flatnonzero(flags):
        if (
            not runs
            or i != runs[-1][-1] + 1
            or times[i] - times[runs[-1][-1]] > policy.max_gap_seconds
        ):
            runs.append([])
        runs[-1].append(int(i))
    stays, rooms = [], []
    for run in runs:
        start, end = times[run[0]], times[run[-1]]
        if end - start < policy.minimum_scan_seconds:
            continue
        lo, hi = max(policy.opening_seconds, start - half), min(times[-1], end + half)
        selected = (times >= lo) & (times <= hi)
        center = np.median(centers[selected], axis=0)
        distances = [np.linalg.norm(center - np.asarray(r["anchor_world_xz_m"])) for r in rooms]
        identity = (
            int(np.argmin(distances))
            if distances and min(distances) <= policy.revisit_distance_m
            else len(rooms)
        )
        if identity == len(rooms):
            rooms.append({"id": f"R{identity + 1:02d}", "anchor_world_xz_m": center.tolist()})
        stays.append(
            {
                "room_id": rooms[identity]["id"],
                "scan_seconds": [float(lo), float(hi)],
                "stable_center_seconds": [float(start), float(end)],
                "ranks": [r["rank"] for r, keep in zip(rows, selected, strict=True) if keep],
                "status": "PROVISIONAL_SCAN_STAY",
            }
        )
    transitions = []
    for a, b in zip(stays[:-1], stays[1:], strict=True):
        if a["room_id"] == b["room_id"]:
            continue
        lo, hi = a["scan_seconds"][1], b["scan_seconds"][0]
        selected = (times >= lo) & (times <= hi)
        transitions.append(
            {
                "from_room": a["room_id"],
                "to_room": b["room_id"],
                "seconds": [lo, hi],
                "path_world_xz_m": centers[selected].tolist(),
                "ranks": [r["rank"] for r, keep in zip(rows, selected, strict=True) if keep],
                "status": "UNRESOLVED_DOORWAY_OR_CONNECTOR",
                "doorway_crossing_seconds": None,
                "door_width_m": None,
                "requires_exit_to_corridor": False,
            }
        )
    return _report(policy, rooms, stays, transitions, windows)


def _report(policy, rooms, stays, transitions, windows=None):
    return {
        "schema": "holo-capture-route-v1",
        "status": "PROVISIONAL_ROUTE",
        "policy": asdict(policy),
        "rooms": rooms,
        "stays": stays,
        "transitions": transitions,
        "windows": windows or [],
        "doorway_detection": "NOT_IMPLEMENTED; movement is not a measured crossing",
        "scale_corrected": False,
        "pose_refinement": False,
        "limitations": [
            "Long pauses or scanning within a large room can resemble another room.",
            "Spatial revisits require image/geometry confirmation.",
            "The opening interval is excluded by protocol; no object is detected.",
            "A connector and a direct doorway are retained as unresolved alternatives.",
        ],
    }

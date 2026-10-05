"""Per-stay surface extraction from accepted stereo pixels with local provenance."""

import hashlib
import json
from dataclasses import asdict, dataclass

import numpy as np

from cozmo_reconstruction.dense.geometry import read_array, world_points
from cozmo_reconstruction.surfaces.analysis import plane_summary
from cozmo_reconstruction.surfaces.geometry import assign, fit_planes
from cozmo_reconstruction.surfaces.models import SurfacePolicy

from .ceiling import estimate_ceiling
from .export import display_points
from .rough_room import complete_rough_room
from .route import analyze_route
from .structure import structure_plan


@dataclass(frozen=True)
class RoomPolicy:
    approach_half_angle_degrees: float = 60.0
    path_margin_m: float = 0.2
    minimum_path_coverage: float = 0.8


def _cell_keys(points, size):
    cells = np.ascontiguousarray(np.floor(points / size).astype(np.int64))
    return cells.view(np.dtype((np.void, cells.dtype.itemsize * 3))).ravel()


def source_observations(dense, cameras):
    """Use exactly the upstream sampling grid and accepted masks; no new depth."""
    policy = json.loads((dense / "policy.json").read_text(encoding="utf-8"))
    stride = policy["sample_stride"]
    rows = []
    for c in sorted(cameras, key=lambda c: c["rank"]):
        name = c["image"]
        depth = read_array(dense / f"workspace/stereo/depth_maps/{name}.geometric.bin")
        with np.load(dense / f"masks/{name}.npz", allow_pickle=False) as mask:
            ys, xs = np.nonzero(mask["accepted"][::stride, ::stride])
        points = world_points(depth, c, xs * stride, ys * stride)
        rows.append((c, points))
    return rows, policy["voxel_size"]


def roomwise_plan(dense, xyz, cameras, frame, mapping=None):
    """Keep source voxels immutable; membership follows contributing scan views.

    A voxel can belong to both rooms if seen through a connecting opening.
    Approach views facing a stay anchor may supply geometry but do not define
    scanning occupancy or measured doors. These extra views remain explicit.
    """
    if mapping is None:
        mapping = json.loads((dense / "input_mapping.json").read_text(encoding="utf-8"))
    route = analyze_route(mapping)
    if len(route["rooms"]) < 2:
        return None
    poses = {v["rank"]: np.asarray(v["pose"]["world_from_camera"]) for v in mapping}
    for stay in route["stays"]:
        scan = display_points(np.asarray([poses[r][:3, 3] for r in stay["ranks"]]), frame)
        stay["path_floor_uv_m"] = (scan[:, [0, 2]] * [1, -1]).tolist()
    for transition in route["transitions"]:
        crossing = display_points(
            np.asarray([poses[r][:3, 3] for r in transition["ranks"]]).reshape(-1, 3), frame
        )
        transition["path_floor_uv_m"] = (crossing[:, [0, 2]] * [1, -1]).tolist()
    observations, size = source_observations(dense, cameras)
    cloud_keys = _cell_keys(xyz, size)
    room_policy = RoomPolicy()
    source_stride = json.loads((dense / "policy.json").read_text(encoding="utf-8"))["sample_stride"]
    # Match the original surface gate's sampling density. Finer native grids
    # require proportionally more samples; they cannot weaken view admission.
    policy = SurfacePolicy(
        sample_stride=source_stride,
        min_view_samples=int(
            np.ceil(SurfacePolicy().min_view_samples * max(1, 4 / source_stride) ** 2)
        ),
    )
    rooms = []
    for identity in route["rooms"]:
        rid = identity["id"]
        scan_ranks = {r for stay in route["stays"] if stay["room_id"] == rid for r in stay["ranks"]}
        ranks = set(scan_ranks)
        anchor = np.asarray(identity["anchor_world_xz_m"])
        for j, stay in enumerate(route["stays"]):
            if stay["room_id"] != rid:
                continue
            lower = (
                route["stays"][j - 1]["scan_seconds"][1]
                if j
                else route["policy"]["opening_seconds"]
            )
            for view in mapping:
                if not lower <= float(view["relative_seconds"]) < stay["scan_seconds"][0]:
                    continue
                pose = np.asarray(view["pose"]["world_from_camera"])
                direction = anchor - pose[[0, 2], 3]
                forward = pose[[0, 2], 2]
                denominator = np.linalg.norm(direction) * np.linalg.norm(forward)
                if denominator > 0 and forward @ direction / denominator >= np.cos(
                    np.deg2rad(room_policy.approach_half_angle_degrees)
                ):
                    ranks.add(view["rank"])
        samples = [(c, points) for c, points in observations if c["rank"] in ranks and len(points)]
        keys = (
            np.unique(np.concatenate([_cell_keys(p, size) for _, p in samples])) if samples else []
        )
        selected = np.flatnonzero(np.isin(cloud_keys, keys))
        points = xyz[selected]
        row = {
            "id": rid,
            "status": "INSUFFICIENT_ROOM_SUPPORT",
            "rough_room": None,
            "source_voxel_count": len(points),
            "source_ranks": sorted(ranks),
            "scanning_ranks": sorted(scan_ranks),
            "approach_ranks": sorted(ranks - scan_ranks),
            "source_voxel_index_sha256": hashlib.sha256(
                selected.astype("<i8").tobytes()
            ).hexdigest(),
            "surface_policy": asdict(policy),
            "room_policy": asdict(room_policy),
            "membership": "upstream voxel cells observed by scan-stay accepted pixels; rooms may share cells",
        }
        rooms.append(row)
        if len(points) < policy.min_fit_inliers:
            row["failure"] = "Too few source voxels in scanning stay"
            continue
        equations = fit_planes(points, policy)
        labels, errors = assign(points, equations, policy.distance_m)
        plane_views = [[] for _ in equations]
        centers = {c["image"]: c["center_m"] for c, _ in samples}
        for camera, observed in samples:
            lab, _ = assign(observed, equations, policy.distance_m)
            for i in range(len(equations)):
                count = int((lab == i).sum())
                if count:
                    plane_views[i].append(
                        {"image": camera["image"], "rank": camera["rank"], "samples": count}
                    )
        planes = [
            plane_summary(
                i,
                equation,
                points[labels == i],
                errors[labels == i],
                plane_views[i],
                centers,
                policy,
            )
            for i, equation in enumerate(equations)
        ]
        positions = display_points(points, frame)
        structure = structure_plan(positions, labels, planes, frame)
        row.update(planes=planes, structure=structure, unassigned_voxels=int((labels < 0).sum()))
        path = display_points(
            np.asarray([c["center_m"] for c, _ in samples if c["rank"] in scan_ranks]).reshape(
                -1, 3
            ),
            frame,
        )
        if not len(path):
            row["failure"] = "No dense-supported cameras inside the scanning stay"
            continue
        try:
            room = complete_rough_room(structure["suggested_spans"], [], path[:, [0, 2]] * [1, -1])
            local = (path[:, [0, 2]] * [1, -1]) @ np.asarray(room["axes_in_floor_uv"]).T
            bounds = np.asarray(room["bounds_in_room_axes_m"])
            contained = (
                (local >= bounds[0] - room_policy.path_margin_m)
                & (local <= bounds[1] + room_policy.path_margin_m)
            ).all(axis=1)
            row["fit_diagnostics"] = {"scanning_path_coverage": float(contained.mean())}
            if contained.mean() < room_policy.minimum_path_coverage:
                raise ValueError("Supported footprint excludes most of the room scanning path")
            room.update(
                status="PROVISIONAL_ROOMWISE_COMPLETION",
                objects=[],
                ceiling_estimate=estimate_ceiling(positions, room),
            )
            room["assumptions"].append(
                "Scanning stays are pose-based hypotheses; doorways and room identities are unconfirmed."
            )
            row.update(rough_room=room, status="PROVISIONAL_ROOMWISE_COMPLETION")
        except ValueError as error:
            row["failure"] = str(error)
    status = (
        "PARTIAL_ROOMWISE_EVIDENCE"
        if any(r["rough_room"] is None for r in rooms)
        else "PROVISIONAL_ROOMWISE_PLAN"
    )
    return {
        "status": status,
        "route": route,
        "rooms": rooms,
        "connections": route["transitions"],
        "source_voxel_size_m": size,
        "physical_accuracy": "UNVERIFIED",
        "shared_coordinate_frame": True,
        "pose_refinement": False,
        "scale_corrected": False,
        "limitations": [
            "Room identities and doorway crossings require image review.",
            "Local views can observe other rooms through openings.",
            "No measured doorway widths, resolved adjacency or drift correction.",
        ],
    }

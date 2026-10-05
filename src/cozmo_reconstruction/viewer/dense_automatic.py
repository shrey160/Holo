"""Automatic dense surface hypotheses, without importing human room annotations."""

import json

import numpy as np

from cozmo_ingestion.errors import require
from cozmo_ingestion.storage import BundleIntegrity, sha256
from cozmo_reconstruction.boundaries.geometry import floor_frame
from cozmo_reconstruction.models import ReconstructionRequest
from cozmo_reconstruction.surfaces.pipeline import verify_surfaces

from .automatic import publish_assets
from .ceiling import estimate_ceiling
from .export import candidate_spans, display_points
from .rough_room import complete_rough_room
from .route import analyze_route
from .structure import structure_plan


def dense_evidence(xyz, labels, planes, cameras):
    candidates = [
        (i, p)
        for i, p in enumerate(planes)
        if p["orientation"] == "horizontal"
        and p["evidence_status"] == "MULTIVIEW_CANDIDATE"
        and p.get("median_camera_height_above_patch_m") is not None
        and 0.3 <= p["median_camera_height_above_patch_m"] <= 2.5
        and min(p["largest_patch_span_m"]) >= 1
    ]
    require(
        bool(candidates), "DENSE_FLOOR_UNAVAILABLE", "No supported floor-height plane candidate"
    )
    index, floor = max(candidates, key=lambda item: item[1]["median_camera_height_above_patch_m"])
    frame = floor_frame(floor["equation_world"], xyz[labels == index])
    frame["authority"] = "AUTOMATIC_SUPPORTED_FLOOR_CANDIDATE; architectural identity unverified"
    frame["source_plane_id"] = floor["id"]
    positions = display_points(xyz, frame)
    # COLMAP image IDs need not follow capture time. Never connect the path in
    # backend dictionary order; source frame ranks retain chronological order.
    ordered = [
        c for _, c in sorted(enumerate(cameras), key=lambda item: item[1].get("rank", item[0]))
    ]
    path = display_points(np.asarray([c["center_m"] for c in ordered]), frame)
    spans = candidate_spans(xyz, labels, planes, frame)
    structure = structure_plan(positions, labels, planes, frame)
    return positions, path, frame, spans, structure


def dense_room(xyz, labels, planes, cameras):
    positions, path, frame, spans, structure = dense_evidence(xyz, labels, planes, cameras)
    # Raw plane intervals can extend along low furniture or disconnected floor-level
    # observations. Only height-persistent, source-aligned spans may size the room.
    supported_spans = structure["suggested_spans"]
    try:
        room = complete_rough_room(supported_spans, [], path[:, [0, 2]] * [1, -1])
    except ValueError as error:
        require(False, "DENSE_ROOM_SUPPORT_INSUFFICIENT", str(error))
    room["status"] = "AUTOMATIC_DENSE_SURFACE_HYPOTHESIS"
    room["boundary_support"] = {
        "method": "HEIGHT_PERSISTENT_SOURCE_ALIGNED_SPANS",
        "raw_candidate_span_count": len(spans),
        "supported_span_count": len(supported_spans),
        "retained_voxel_points": structure["retained_voxel_points"],
        "policy": structure["policy"],
        "limitations": "Tall furniture can remain; occluded wall ends can underestimate extent.",
    }
    room["ceiling_estimate"] = estimate_ceiling(positions, room)
    room["objects"] = []
    room["assumptions"].append(
        "Lowest broad supported plane below cameras supplies an unconfirmed floor hypothesis."
    )
    room["assumptions"].append(
        "Room fitting uses contiguous height-persistent source-aligned spans; raw projected "
        "plane endpoints are diagnostic only. Occluded ends can underestimate room extent."
    )
    return (
        positions,
        path,
        frame,
        room,
        {
            "candidate_spans": spans,
            "structure": structure,
        },
    )


def publish_dense(surface_request, output, label):
    audit = verify_surfaces(surface_request.output, surface_request)
    dense = surface_request.upstream
    hashes = {
        "dense": sha256(dense.output / "manifest.json"),
        "surfaces": sha256(surface_request.output / "manifest.json"),
    }
    for source in (dense.output, surface_request.output):
        require(
            not output.resolve().is_relative_to(source.resolve())
            and not source.resolve().is_relative_to(output.resolve()),
            "OUTPUT_SOURCE_OVERLAP",
            str(output),
        )
    manifest = json.loads((surface_request.output / "manifest.json").read_text(encoding="utf-8"))
    integrity = BundleIntegrity(surface_request.output, manifest["artifact_sha256"])
    report = json.loads(integrity.path("report.json").read_text(encoding="utf-8"))
    with np.load(dense.output / "cloud.npz") as cloud:
        xyz, colors = cloud["xyz_m"], cloud["rgb"]
    with np.load(integrity.path("cloud_labels.npz")) as stored:
        labels = stored["plane_index"]
    cameras = json.loads((dense.output / "cameras.json").read_text(encoding="utf-8"))
    mapping_file = dense.sparse / "input_mapping.json"
    mapping = json.loads(mapping_file.read_text(encoding="utf-8"))
    route = analyze_route(mapping)
    roomwise = None
    if len(route["rooms"]) >= 2:
        from .local_rooms import roomwise_plan

        positions, path, frame, spans, structure = dense_evidence(
            xyz, labels, report["planes"], cameras
        )
        roomwise = roomwise_plan(dense.output, xyz, cameras, frame, mapping)
        hashes["route_mapping"] = sha256(mapping_file)
        room = None
        plan_extra = {"candidate_spans": spans, "structure": structure, "roomwise": roomwise}
    else:
        positions, path, frame, room, plan_extra = dense_room(
            xyz, labels, report["planes"], cameras
        )

    def recheck():
        verify_surfaces(surface_request.output, surface_request)
        require(
            {name: value for name, value in hashes.items() if name != "route_mapping"}
            == {
                "dense": sha256(dense.output / "manifest.json"),
                "surfaces": sha256(surface_request.output / "manifest.json"),
            },
            "SOURCE_CHANGED",
            "Dense surface manifests",
        )
        if roomwise is not None:
            require(
                sha256(mapping_file) == hashes["route_mapping"], "SOURCE_CHANGED", "Route mapping"
            )

    request = ReconstructionRequest(dense.prepared, dense.bundle, dense.output, dense.source)
    result = publish_assets(
        request,
        output,
        label,
        positions,
        path,
        frame,
        room,
        colors,
        cameras,
        audit,
        hashes,
        report,
        "RGB_DENSE_STEREO",
        recheck,
        plan_extra,
        trim=False,
    )
    result.update(source_point_count=len(xyz), quality="DENSE_WITH_FINDINGS")
    if roomwise is not None:
        completed = sum(r["rough_room"] is not None for r in roomwise["rooms"])
        result.update(
            room_count=len(roomwise["rooms"]),
            completed_room_count=completed,
            quality="PARTIAL_ROOMWISE_EVIDENCE"
            if completed < len(roomwise["rooms"])
            else "PROVISIONAL_ROOMWISE_COMPLETION",
        )
    else:
        result.update(
            dimensions_estimated_m=room["dimensions_estimated_m"],
            ceiling_estimated_m=room["ceiling_estimate"]["height_estimated_m"],
        )
    return result

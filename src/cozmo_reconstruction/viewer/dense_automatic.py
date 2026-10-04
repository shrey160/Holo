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
from .structure import structure_plan


def dense_room(xyz, labels, planes, cameras):
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
    path = display_points(np.asarray([c["center_m"] for c in cameras]), frame)
    spans = candidate_spans(xyz, labels, planes, frame)
    room = complete_rough_room(spans, [], path[:, [0, 2]] * [1, -1])
    room["status"] = "AUTOMATIC_DENSE_SURFACE_HYPOTHESIS"
    room["ceiling_estimate"] = estimate_ceiling(positions, room)
    room["objects"] = []
    room["assumptions"].append(
        "Lowest broad supported plane below cameras supplies an unconfirmed floor hypothesis."
    )
    return (
        positions,
        path,
        frame,
        room,
        {
            "candidate_spans": spans,
            "structure": structure_plan(positions, labels, planes, frame),
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
    positions, path, frame, room, plan_extra = dense_room(xyz, labels, report["planes"], cameras)

    def recheck():
        verify_surfaces(surface_request.output, surface_request)
        require(
            hashes
            == {
                "dense": sha256(dense.output / "manifest.json"),
                "surfaces": sha256(surface_request.output / "manifest.json"),
            },
            "SOURCE_CHANGED",
            "Dense surface manifests",
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
    result.update(
        dimensions_estimated_m=room["dimensions_estimated_m"],
        ceiling_estimated_m=room["ceiling_estimate"]["height_estimated_m"],
        source_point_count=len(xyz),
        quality="DENSE_WITH_FINDINGS",
    )
    return result

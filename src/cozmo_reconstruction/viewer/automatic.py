"""Publish a portable sparse preview without transferring another room's review."""

import json
from pathlib import Path

import numpy as np

from cozmo_ingestion.bundle import BundleTransaction
from cozmo_ingestion.errors import require
from cozmo_ingestion.models import IngestionRequest
from cozmo_ingestion.storage import BundleIntegrity, sha256, write_json
from cozmo_preprocessing.verification import lines
from cozmo_reconstruction.verification import verify_reconstruction

from .export import display_points, plan_raster
from .rough_room import inferred_entry, rough_room_svg


def sparse_room(xyz, camera_centers):
    """Gravity-aligned display and trimmed PCA envelope; no certified walls/floor."""
    xyz = np.asarray(xyz, dtype=float)
    require(
        xyz.ndim == 2 and xyz.shape[1] == 3 and len(xyz) >= 100 and np.isfinite(xyz).all(),
        "RECONSTRUCTION_SUPPORT_INSUFFICIENT",
        "At least 100 finite triangulated points are needed for a room preview",
    )
    floor = float(np.quantile(xyz[:, 1], 0.02))
    frame = {
        "authority": "AUTOMATIC_LOWER_ENVELOPE; not a verified floor",
        "floor_from_world": [[1, 0, 0, 0], [0, 0, -1, 0], [0, 1, 0, -floor], [0, 0, 0, 1]],
    }
    positions = display_points(xyz, frame)
    uv = positions[:, [0, 2]] * [1, -1]
    limits = np.quantile(uv, [0.02, 0.98], axis=0)
    core = uv[((uv >= limits[0]) & (uv <= limits[1])).all(axis=1)]
    _, vectors = np.linalg.eigh(np.cov(core.T))
    direction = vectors[:, -1]
    if direction[0] < 0:
        direction = -direction
    axes = np.array([direction, [-direction[1], direction[0]]])
    bounds = np.quantile(core @ axes.T, [0.02, 0.98], axis=0)
    dimensions = bounds[1] - bounds[0]
    require(
        np.all(dimensions >= 0.5) and np.all(dimensions <= 50),
        "RECONSTRUCTION_SUPPORT_INSUFFICIENT",
        "Point coverage cannot support a bounded room envelope",
    )
    x0, y0 = bounds[0]
    x1, y1 = bounds[1]
    corners = np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]])
    cameras = display_points(np.asarray(camera_centers), frame)
    room = {
        "status": "AUTOMATIC_SPARSE_ENVELOPE",
        "model": "single rectangular coverage envelope; may include furniture or multiple rooms",
        "axes_in_floor_uv": axes.tolist(),
        "bounds_in_room_axes_m": bounds.tolist(),
        "polygon_floor_uv_m": (corners @ axes).tolist(),
        "dimensions_estimated_m": dimensions.tolist(),
        "area_estimated_m2": float(np.prod(dimensions)),
        "entry": inferred_entry(cameras[:, [0, 2]] * [1, -1] @ axes.T, bounds, 0.8),
        "ceiling_reference": None,
        "objects": [],
        "scale_corrected": False,
        "assumptions": [
            "RGB features are triangulated with fixed source ARKit poses and calibration.",
            "Floor is the 2nd percentile of observed point height, not a verified plane.",
            "Rectangle orientation is PCA of trimmed points; furniture can bias it.",
            "Bounds trim 2% per axis twice; missing walls, corridors and rooms can bias size.",
            "Entrance uses the camera path; width and swing are illustrative.",
            "LiDAR, grounding, measured ceiling and human object reviews are excluded.",
        ],
    }
    return positions, cameras, frame, room


def publish_sparse(request, output: Path, label: str):
    audit = verify_reconstruction(
        request.output, request.prepared, request.bundle, request.source_root
    )
    source_hash = sha256(request.output / "manifest.json")
    manifest = json.loads((request.output / "manifest.json").read_text(encoding="utf-8"))
    integrity = BundleIntegrity(request.output, manifest["artifact_sha256"])
    points = lines(integrity.path("points.jsonl"))
    cameras = json.loads(integrity.path("cameras.json").read_text(encoding="utf-8"))
    positions, path, frame, room = sparse_room(
        [p["xyz_m"] for p in points], [c["center_m"] for c in cameras]
    )

    def recheck():
        verify_reconstruction(request.output, request.prepared, request.bundle, request.source_root)
        require(
            sha256(request.output / "manifest.json") == source_hash,
            "SOURCE_CHANGED",
            "Sparse manifest",
        )

    return publish_assets(
        request,
        output,
        label,
        positions,
        path,
        frame,
        room,
        [p["rgb"] for p in points],
        cameras,
        audit,
        {"sparse": source_hash},
        json.loads(integrity.path("report.json").read_text(encoding="utf-8")),
        "CPU_SPARSE_TRIANGULATION",
        recheck,
    )


def publish_assets(
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
    source_hashes,
    report,
    geometry_source,
    recheck,
    plan_extra=None,
    trim=True,
):
    """Shared atomic encoding, without relaxing the upstream audit of either backend."""
    selected = np.arange(len(positions))
    if trim:
        low, high = np.quantile(positions, [0.005, 0.995], axis=0)
        selected = np.flatnonzero(((positions >= low) & (positions <= high)).all(axis=1))
    selected = selected[np.linspace(0, len(selected) - 1, min(len(selected), 120000), dtype=int)]
    sample = positions[selected].astype("<f4")
    rgb = np.round(colors).clip(0, 255).astype(np.uint8)[selected]
    output = output.resolve()
    for source in (request.output, request.prepared, request.bundle, request.source_root):
        if source is not None:
            source = source.resolve()
            require(
                not output.is_relative_to(source) and not source.is_relative_to(output),
                "OUTPUT_SOURCE_OVERLAP",
                str(output),
            )
    with BundleTransaction(IngestionRequest(request.output, output), "automatic-viewer") as tx:
        stage = tx.stage
        sample.tofile(stage / "positions.bin")
        rgb.tofile(stage / "colors.bin")
        raster = plan_raster(positions[selected], stage / "plan.png")
        plan = {
            "rough_room": room,
            "raster": raster,
            "floor_cells": [],
            "cell_m": 0.25,
            "reviewed_spans": [],
            "candidate_spans": [],
            "camera_path_uv_m": (path[:, [0, 2]] * [1, -1]).tolist(),
        }
        plan.update(plan_extra or {})
        svg = (
            rough_room_svg(room, [])
            .replace(
                "fitted to source plane candidates",
                "estimated from sparse point coverage"
                if trim
                else "fitted to dense surface candidates",
            )
            .replace(
                "Blue: reviewed patches",
                "Automatic sparse coverage envelope" if trim else "Automatic surface hypotheses",
            )
        )
        for name in ("rough-room.svg", "reviewed-plan.svg"):
            (stage / name).write_text(svg, encoding="utf-8")
        write_json(
            stage / "boundary-report.json",
            {
                "status": room["status"],
                "reviewed_walls": [],
                "assumptions": room["assumptions"],
                "geometry_diagnostics": report,
            },
        )
        write_json(stage / "plan.json", plan)
        write_json(
            stage / "scene.json",
            {
                "label": label[:120],
                "point_count": len(sample),
                "source_voxel_points": len(positions),
                "geometry_source": geometry_source,
                "selected_views": len(cameras),
                "coordinates": "floor u, floor height, -floor v",
                "units": "source estimated metres",
                "physical_accuracy": "UNVERIFIED",
                "positions": "positions.bin",
                "colors": "colors.bin",
                "bounds": [sample.min(axis=0).tolist(), sample.max(axis=0).tolist()],
                "camera_path": path.tolist(),
                "reviewed_spans": [],
                "floor_cells": [],
                "cell_m": 0.25,
                "source_floor_frame": frame,
                "source_audit": audit,
                "inferred_room_completion": room,
                "approximate_objects": [],
                "sampling": "evenly spaced subset; full source retained"
                + ("; 0.5% per-axis preview trim" if trim else ""),
                "mesh": "NOT_GENERATED; observed point cloud",
                "grounding": "NOT_APPLIED",
            },
        )
        packed = np.empty(len(sample), dtype=[("xyz", "<f4", (3,)), ("rgb", "u1", (3,))])
        packed["xyz"], packed["rgb"] = sample, rgb
        header = (
            f"ply\nformat binary_little_endian 1.0\nelement vertex {len(sample)}\n"
            "property float x\nproperty float y\nproperty float z\n"
            "property uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n"
        )
        (stage / "cloud.ply").write_bytes(header.encode() + packed.tobytes())
        recheck()
        hashes = {p.name: sha256(p) for p in stage.iterdir() if p.is_file()}
        write_json(
            stage / "manifest.json",
            {
                "schema": "holo-reconstruction-viewer-v1",
                "geometry_source": geometry_source,
                "source_manifest_sha256": source_hashes,
                "source_audit": audit,
                "physical_accuracy": "UNVERIFIED",
                "artifact_sha256": hashes,
            },
        )
        BundleIntegrity(stage, hashes).verify_all()
        tx.publish()
    return {
        "id": output.name,
        "point_count": len(sample),
        "selected_views": len(cameras),
        "status": "PUBLISHED",
        "geometry_source": geometry_source,
    }

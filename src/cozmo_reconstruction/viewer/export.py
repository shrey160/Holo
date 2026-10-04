"""Audit once, then publish bounded browser assets independently of source evidence."""

import json
import shutil
from pathlib import Path

import cv2
import numpy as np

from cozmo_ingestion.bundle import BundleTransaction
from cozmo_ingestion.errors import require
from cozmo_ingestion.models import IngestionRequest
from cozmo_ingestion.storage import BundleIntegrity, sha256, write_json
from cozmo_reconstruction.boundaries.geometry import floor_uv, interval_runs, plane_intersection
from cozmo_reconstruction.boundaries.pipeline import guard_output
from cozmo_reconstruction.boundaries.verification import verify_boundaries

from .ceiling import estimate_ceiling
from .objects import approximate_objects
from .rough_room import complete_rough_room, rough_room_svg
from .structure import structure_plan


def display_points(xyz, frame):
    """Right-handed browser coordinates: floor u, height, negative floor v."""
    transform = np.asarray(frame["floor_from_world"])
    local = xyz @ transform[:3, :3].T + transform[:3, 3]
    return local[:, [0, 2, 1]] * [1, 1, -1]


def candidate_spans(xyz, labels, planes, frame):
    """Occupied projected plane extents only, explicitly without semantic admission."""
    result = []
    for index, plane in enumerate(planes):
        if plane["orientation"] != "vertical" or plane["evidence_status"] != "MULTIVIEW_CANDIDATE":
            continue
        line = plane_intersection(plane["equation_world"], frame)
        points = xyz[labels == index]
        if line is None or not len(points):
            continue
        origin, direction = line
        distance = (points - origin) @ direction
        bins = np.floor(distance / 0.15).astype(int)
        occupied, counts = np.unique(bins, return_counts=True)
        for run in interval_runs(occupied[counts >= 20]):
            selected = np.isin(bins, run)
            start, end = float(distance[selected].min()), float(distance[selected].max())
            if end - start < 0.3:
                continue
            endpoints = origin + np.array([start, end])[:, None] * direction
            result.append(
                {
                    "plane_id": plane["id"],
                    "uv": floor_uv(endpoints, frame).tolist(),
                    "status": "GEOMETRIC_CANDIDATE; may be furniture or curtains",
                    "voxel_points": int(selected.sum()),
                }
            )
    return result


def plan_raster(points, path):
    """Unfilled orthographic occupancy: walls, furniture and missing samples coexist."""
    uv = points[:, [0, 2]] * [1, -1]
    bounds = np.array([uv.min(axis=0), uv.max(axis=0)])
    bounds += np.array([[-0.15, -0.15], [0.15, 0.15]])
    extent = np.maximum(bounds[1] - bounds[0], 0.3)
    width, height = 1400, 1000
    scale = min((width - 80) / extent[0], (height - 80) / extent[1])
    # Equal metric scale on both axes, centered within the fixed image.
    padding = (np.array([width, height]) - extent * scale) / 2
    pixel = np.floor((uv - bounds[0]) * scale + padding).astype(int)
    eligible = (points[:, 1] >= 0.1) & (points[:, 1] <= 2.2)
    density = np.zeros((height, width), dtype=np.int32)
    np.add.at(density, (pixel[eligible, 1], pixel[eligible, 0]), 1)
    raster = np.full((height, width, 3), 250, dtype=np.uint8)
    occupied = density > 0
    value = np.clip(228 - 28 * np.log1p(density[occupied]), 75, 230).astype(np.uint8)
    raster[occupied] = np.stack([value, value, value], axis=1)
    require(cv2.imwrite(str(path), raster), "VIEWER_IMAGE_FAILED", str(path))
    return {
        "width": width,
        "height": height,
        "bounds_uv_m": bounds.tolist(),
        "scale_px_per_estimated_m": float(scale),
        "padding_px": padding.tolist(),
        "height_interval_m": [0.1, 2.2],
        "scope": "Observed orthographic occupancy; furniture included, absent pixels unfilled",
    }


def export_viewer(
    request,
    output: Path,
    label: str,
    max_points=120000,
    *,
    rough_room=False,
    ceiling_reference=None,
    object_review=None,
):
    require(1 <= len(label.strip()) <= 120, "VIEWER_LABEL_INVALID", "Use a short label")
    require(
        type(max_points) is int and 1000 <= max_points <= 200000,
        "VIEWER_LIMIT_INVALID",
        "Display limit must be 1,000–200,000 points",
    )
    output = output.resolve()
    object_annotations, object_hash = None, None
    if object_review is not None:
        require(rough_room, "VIEWER_OBJECT_REVIEW_INVALID", "Object review requires --rough-room")
        object_review = object_review.resolve()
        require(not object_review.is_relative_to(output), "OUTPUT_SOURCE_OVERLAP", str(output))
        object_hash = sha256(object_review)
        object_annotations = json.loads(object_review.read_text(encoding="utf-8"))
    ceiling, ceiling_hash = None, None
    if ceiling_reference is not None:
        require(rough_room, "VIEWER_REFERENCE_INVALID", "Ceiling reference requires --rough-room")
        ceiling_reference = ceiling_reference.resolve()
        require(not ceiling_reference.is_relative_to(output), "OUTPUT_SOURCE_OVERLAP", str(output))
        ceiling_hash = sha256(ceiling_reference)
        reference = json.loads(ceiling_reference.read_text(encoding="utf-8"))
        height = reference.get("value_m")
        require(
            reference.get("quantity") == "ceiling_height"
            and type(height) in (int, float)
            and np.isfinite(height)
            and 1 <= height <= 10,
            "VIEWER_REFERENCE_INVALID",
            "Use a finite ceiling height in metres",
        )
        ceiling = {
            "value_m": height,
            "precision": reference.get("precision", "UNSPECIFIED"),
            "authority": reference.get("authority", "EXTERNAL_REFERENCE"),
            "source_sha256": ceiling_hash,
            "used_for_scale": False,
        }
    # Reuse the established raw/upstream overlap boundary for this new derivative.
    from dataclasses import replace

    guard_output(replace(request, output=output))
    require(
        not output.is_relative_to(request.output) and not request.output.is_relative_to(output),
        "OUTPUT_SOURCE_OVERLAP",
        str(output),
    )
    audit = verify_boundaries(request.output, request)
    dense = request.surfaces.upstream.output
    surfaces = request.surfaces.output
    inputs = {"dense": dense, "surfaces": surfaces, "boundaries": request.output}
    source_hashes = {name: sha256(root / "manifest.json") for name, root in inputs.items()}
    artifacts = {}
    for name, root in inputs.items():
        manifest = json.loads((root / "manifest.json").read_text())
        artifacts[name] = BundleIntegrity(root, manifest["artifact_sha256"])
    report = json.loads(artifacts["boundaries"].path("report.json").read_text())
    frame = report["floor_frame"]
    require(frame is not None, "VIEWER_FLOOR_UNAVAILABLE", "Review local floor evidence first")
    with np.load(artifacts["dense"].path("cloud.npz")) as cloud:
        xyz, rgb = cloud["xyz_m"], cloud["rgb"]
    with np.load(artifacts["surfaces"].path("cloud_labels.npz")) as stored:
        labels = stored["plane_index"]
    planes = json.loads(artifacts["surfaces"].path("report.json").read_text())["planes"]
    cameras = json.loads(artifacts["dense"].path("cameras.json").read_text())
    indices = np.linspace(0, len(xyz) - 1, min(max_points, len(xyz)), dtype=int)
    positions = display_points(xyz, frame)
    sample = positions[indices].astype("<f4")
    selected_rgb = np.round(rgb[indices]).clip(0, 255).astype(np.uint8)
    camera_points = display_points(np.array([c["center_m"] for c in cameras]), frame)
    with BundleTransaction(IngestionRequest(request.output, output), "viewer") as transaction:
        stage = transaction.stage
        sample.tofile(stage / "positions.bin")
        selected_rgb.tofile(stage / "colors.bin")
        raster = plan_raster(positions, stage / "plan.png")
        walls = [
            {"plane_id": wall["plane_id"], **segment}
            for wall in report["walls"]
            for segment in wall["segments"]
        ]
        plan = {
            "raster": raster,
            "floor_cells": report["local_floor"]["cells"],
            "cell_m": json.loads(artifacts["boundaries"].path("policy.json").read_text())["cell_m"],
            "reviewed_spans": walls,
            "candidate_spans": candidate_spans(xyz, labels, planes, frame),
            "camera_path_uv_m": (camera_points[:, [0, 2]] * [1, -1]).tolist(),
            "structure": structure_plan(positions, labels, planes, frame),
        }
        if rough_room:
            plan["rough_room"] = complete_rough_room(
                plan["candidate_spans"], walls, plan["camera_path_uv_m"], ceiling
            )
            room = plan["rough_room"]
            room["display_orientation"] = "u right, v up; matches aligned 3D top view"
            room["ceiling_estimate"] = estimate_ceiling(positions, room)
            if object_annotations is not None:
                room["objects"] = approximate_objects(
                    xyz, positions, cameras, dense, room, object_annotations
                )
                room["object_review"] = {"sha256": object_hash, "annotations": object_annotations}
            (stage / "rough-room.svg").write_text(
                rough_room_svg(plan["rough_room"], walls), encoding="utf-8"
            )
        write_json(stage / "plan.json", plan)
        scene = {
            "label": label.strip(),
            "point_count": len(sample),
            "source_voxel_points": len(xyz),
            "selected_views": len(cameras),
            "coordinates": "floor u, floor height, -floor v",
            "units": "source estimated metres",
            "physical_accuracy": "UNVERIFIED",
            "positions": "positions.bin",
            "colors": "colors.bin",
            "positions_encoding": "float32 little endian Nx3",
            "colors_encoding": "uint8 RGB Nx3",
            "bounds": [sample.min(axis=0).tolist(), sample.max(axis=0).tolist()],
            "camera_path": camera_points.tolist(),
            "reviewed_spans": walls,
            "floor_cells": plan["floor_cells"],
            "cell_m": plan["cell_m"],
            "grounding": report["reference_calibration"],
            "closed_room_polygon": None,
            "room_area": None,
            "mesh": "NOT_GENERATED; observed point cloud",
            "sampling": "deterministic evenly spaced source voxel indices",
            "source_floor_frame": frame,
            "source_audit": audit,
        }
        if rough_room:
            scene["inferred_room_completion"] = {
                "status": "INFERRED_ROUGH_COMPLETION",
                "asset": "rough-room.svg",
                "polygon_floor_uv_m": plan["rough_room"]["polygon_floor_uv_m"],
                "dimensions_estimated_m": plan["rough_room"]["dimensions_estimated_m"],
                "area_estimated_m2": plan["rough_room"]["area_estimated_m2"],
                "ceiling_reference": ceiling,
                "ceiling_estimate": room["ceiling_estimate"],
                "axes_in_floor_uv": room["axes_in_floor_uv"],
            }
            scene["approximate_objects"] = room.get("objects", [])
        write_json(stage / "scene.json", scene)
        shutil.copyfile(artifacts["boundaries"].path("plan.svg"), stage / "reviewed-plan.svg")
        shutil.copyfile(artifacts["boundaries"].path("report.json"), stage / "boundary-report.json")
        with (stage / "cloud.ply").open("wb") as stream:
            stream.write(
                (
                    f"ply\nformat binary_little_endian 1.0\ncomment display subset in floor coordinates\n"
                    f"element vertex {len(sample)}\nproperty float x\nproperty float y\nproperty float z\n"
                    "property uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n"
                ).encode()
            )
            packed = np.empty(len(sample), dtype=[("xyz", "<f4", (3,)), ("rgb", "u1", (3,))])
            packed["xyz"], packed["rgb"] = sample, selected_rgb
            stream.write(packed.tobytes())
        for name, root in inputs.items():
            require(sha256(root / "manifest.json") == source_hashes[name], "SOURCE_CHANGED", name)
            artifacts[name].verify_all()
        if ceiling_reference is not None:
            require(
                sha256(ceiling_reference) == ceiling_hash, "SOURCE_CHANGED", "ceiling reference"
            )
        if object_review is not None:
            require(sha256(object_review) == object_hash, "SOURCE_CHANGED", "object review")
        hashes = {p.name: sha256(p) for p in sorted(stage.iterdir()) if p.is_file()}
        write_json(
            stage / "manifest.json",
            {
                "schema": "holo-reconstruction-viewer-v1",
                "label": label.strip(),
                "source_manifest_sha256": source_hashes,
                "source_audit": audit,
                "physical_accuracy": "UNVERIFIED",
                "artifact_sha256": hashes,
            },
        )
        BundleIntegrity(stage, hashes).verify_all()
        transaction.publish()
    return {
        "status": "PUBLISHED",
        "display_points": len(sample),
        "source_voxel_points": len(xyz),
        "artifacts": len(hashes),
        "physical_accuracy": "UNVERIFIED",
    }

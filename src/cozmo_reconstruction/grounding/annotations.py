"""Audit the admitted RGB/K/poses, reference prior and native-grid corner identities."""

import json

import cv2
import numpy as np

from cozmo_ingestion import CaptureReader
from cozmo_ingestion.errors import require
from cozmo_ingestion.storage import BundleIntegrity, sha256
from cozmo_ingestion.verification import verify
from cozmo_preprocessing.verification import lines, verify_preprocessing
from cozmo_reconstruction.cameras import convert_camera
from cozmo_reconstruction.dense.models import DenseRequest
from cozmo_reconstruction.dense.pipeline import verify_dense
from cozmo_reconstruction.surfaces.models import SurfaceRequest
from cozmo_reconstruction.surfaces.pipeline import verify_surfaces

SCHEMA = "holo-grounding-corners-v1"
PIXELS = "native image edges; x right, y down; pixel center at (0.5,0.5)"
ORDER = "0->1 width, 1->2 height, 2->3 width, 3->0 height; same physical corners in every view"


def display_to_native(xy, display_size, native_size):
    values = np.asarray([*display_size, *native_size], dtype=float)
    require(
        np.isfinite(values).all() and (values > 0).all(),
        "GROUNDING_GRID_INVALID",
        "Positive finite dimensions",
    )
    return np.asarray(xy, dtype=float) * np.asarray(native_size) / np.asarray(display_size)


def validate_corners(corners, image_size):
    xy = np.asarray(corners, dtype=float)
    require(
        xy.shape == (4, 2) and np.isfinite(xy).all(),
        "GROUNDING_CORNERS_INVALID",
        "Four finite ordered native-grid corners",
    )
    require(
        (xy >= 0).all() and (xy < np.asarray(image_size)).all(),
        "GROUNDING_CORNERS_INVALID",
        "Corners inside native image",
    )
    edges = np.roll(xy, -1, axis=0) - xy
    cross = edges[:, 0] * np.roll(edges[:, 1], -1) - edges[:, 1] * np.roll(edges[:, 0], -1)
    require(
        (np.linalg.norm(edges, axis=1) >= 5).all() and ((cross > 1).all() or (cross < -1).all()),
        "GROUNDING_CORNERS_INVALID",
        "Require convex nondegenerate perimeter; no crossings",
    )
    return xy


def audit_source(request):
    reader = CaptureReader(request.bundle, "ios_assisted_rgb", request.source)
    verify(request.bundle, reader.roots["capture"])
    verify_preprocessing(request.prepared, request.bundle, reader.roots["capture"])
    if request.dense is not None:
        upstream = DenseRequest(
            request.sparse, request.prepared, request.bundle, request.dense, request.source
        )
        if request.surfaces is not None:
            verify_surfaces(request.surfaces, SurfaceRequest(upstream, request.surfaces))
        else:
            verify_dense(request.dense, upstream)
    return reader


def inputs(request, reader):
    manifest = json.loads((request.prepared / "manifest.json").read_text())
    integrity = BundleIntegrity(request.prepared, manifest["artifact_sha256"])
    declared = reader.records("annotations")
    objects = [o for o in declared["reference_objects"] if o["id"] == request.object_id]
    require(len(objects) == 1, "GROUNDING_OBJECT_INVALID", "One video-bound declared reference")
    reference = objects[0]
    require(
        0 < reference["width_m"] <= 2 and 0 < reference["height_m"] <= 2,
        "GROUNDING_OBJECT_INVALID",
        "Declared rectangle dimensions",
    )
    ks = {v["id"]: v for v in lines(integrity.path("calibration.jsonl"))}
    poses = {v["id"]: v for v in lines(integrity.path("poses.jsonl"))}
    start, end = reference["candidate_window_seconds"]
    selected = [
        v
        for v in lines(integrity.path("views.jsonl"))
        if start <= float(v["relative_seconds"]) <= end
    ]
    require(len(selected) <= 32, "GROUNDING_SELECTION_INVALID", "At most 32 prepared opening views")
    views = []
    for view in selected:
        path = integrity.path(view["image"])
        image = cv2.imread(str(path))
        require(
            image is not None and list(image.shape[1::-1]) == view["image_size"],
            "GROUNDING_GRID_INVALID",
            view["image"],
        )
        camera = convert_camera(ks[view["calibration_id"]], poses[view["pose_id"]], 0)
        views.append(
            {
                "rank": view["rank"],
                "frame_id": view["frame_id"],
                "relative_seconds": view["relative_seconds"],
                "image": view["image"],
                "image_sha256": sha256(path),
                "image_size": view["image_size"],
                "camera": camera,
            }
        )
    identity = {
        "prepared_manifest_sha256": sha256(request.prepared / "manifest.json"),
        "ingestion_manifest_sha256": sha256(request.bundle / "manifest.json"),
        "source_video_sha256": manifest["source_video_sha256"],
    }
    for name in ("sparse", "dense", "surfaces"):
        folder = getattr(request, name)
        identity[f"{name}_manifest_sha256"] = sha256(folder / "manifest.json") if folder else None
    return identity, reference, views


def template(identity, object_id):
    return {
        "schema": SCHEMA,
        **identity,
        "object_id": object_id,
        "pixel_convention": PIXELS,
        "corner_order": ORDER,
        "annotator": "",
        "human_reviewed": False,
        "corner_uncertainty_pixels": None,
        "cover_thickness_m": None,
        "notes": "",
        "observations": [],
    }


def load_annotations(path, identity, object_id, views):
    require(path.stat().st_size <= 512 * 1024, "GROUNDING_ANNOTATION_INVALID", "At most 512 KiB")
    data = json.loads(path.read_text(encoding="utf-8"))
    require(
        data["schema"] == SCHEMA
        and data["object_id"] == object_id
        and data["pixel_convention"] == PIXELS
        and data["corner_order"] == ORDER
        and all(data[k] == value for k, value in identity.items()),
        "GROUNDING_ANNOTATION_SOURCE_CHANGED",
        "Schema/grid/source identities",
    )
    require(
        isinstance(data["annotator"], str)
        and 0 < len(data["annotator"]) <= 200
        and type(data["human_reviewed"]) is bool
        and isinstance(data["notes"], str)
        and len(data["notes"]) <= 5000,
        "GROUNDING_ANNOTATION_INVALID",
        "Annotation provenance",
    )
    for key, limit in (("corner_uncertainty_pixels", 30), ("cover_thickness_m", 0.2)):
        value = data[key]
        require(
            value is None
            or (type(value) in (int, float) and np.isfinite(value) and 0 <= value <= limit),
            "GROUNDING_ANNOTATION_INVALID",
            key,
        )
    observations = data["observations"]
    require(
        isinstance(observations, list) and len(observations) <= 12,
        "GROUNDING_SELECTION_INVALID",
        "At most 12 marked views",
    )
    by_rank = {v["rank"]: v for v in views}
    ranks = []
    for row in observations:
        rank = row["rank"]
        require(type(rank) is int and rank in by_rank, "GROUNDING_SELECTION_INVALID", str(rank))
        view = by_rank[rank]
        require(
            all(
                row[k] == view[k]
                for k in ("frame_id", "relative_seconds", "image_sha256", "image_size")
            ),
            "GROUNDING_ANNOTATION_SOURCE_CHANGED",
            str(rank),
        )
        validate_corners(row["corners_native"], view["image_size"])
        ranks.append(rank)
    require(ranks == sorted(set(ranks)), "GROUNDING_SELECTION_INVALID", "Unique ascending ranks")
    return data

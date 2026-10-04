"""Exact image/observation identity and per-region semantics, never whole-plane promotion."""

import json

import numpy as np

from cozmo_ingestion.errors import require
from cozmo_ingestion.storage import sha256
from cozmo_reconstruction.grounding.models import GroundingRequest
from cozmo_reconstruction.grounding.verification import verify_grounding
from cozmo_reconstruction.surfaces.pipeline import verify_surfaces

SCHEMA = "holo-surface-region-review-v1"
ROLES = ("UNREVIEWED", "FLOOR", "WALL", "FURNITURE", "MIXED", "UNKNOWN")


def source_audit(request):
    surface = request.surfaces
    verify_surfaces(surface.output, surface)
    if request.grounding:
        upstream = surface.upstream
        verify_grounding(
            request.grounding,
            GroundingRequest(
                upstream.prepared,
                upstream.bundle,
                request.grounding,
                upstream.source,
                sparse=upstream.sparse,
                dense=upstream.output,
                surfaces=surface.output,
            ),
        )


def inputs(request):
    surface = request.surfaces
    upstream = surface.upstream
    identity = {
        "surface_manifest_sha256": sha256(surface.output / "manifest.json"),
        "dense_manifest_sha256": sha256(upstream.output / "manifest.json"),
        "prepared_manifest_sha256": sha256(upstream.prepared / "manifest.json"),
        "ingestion_manifest_sha256": sha256(upstream.bundle / "manifest.json"),
        "sparse_manifest_sha256": sha256(upstream.sparse / "manifest.json"),
        "source_video_sha256": json.loads((upstream.prepared / "manifest.json").read_text())[
            "source_video_sha256"
        ],
        "grounding_manifest_sha256": sha256(request.grounding / "manifest.json")
        if request.grounding
        else None,
    }
    report = json.loads((surface.output / "report.json").read_text())
    mapping = {
        v["image"]: v for v in json.loads((upstream.output / "input_mapping.json").read_text())
    }
    views = []
    for camera in sorted(
        json.loads((upstream.output / "cameras.json").read_text()), key=lambda c: c["rank"]
    ):
        name = camera["image"]
        views.append(
            {
                "rank": camera["rank"],
                "image": name,
                "image_size": camera["image_size"],
                "frame_id": mapping[name]["frame_id"],
                "relative_seconds": mapping[name]["relative_seconds"],
                "source_rgb_sha256": sha256(upstream.output / f"workspace/images/{name}"),
                "observations_sha256": sha256(surface.output / f"observations/{name}.npz"),
                "evidence_overlay_sha256": sha256(surface.output / f"overlays/{name}"),
            }
        )
    return identity, report, views


def template(identity):
    return {
        "schema": SCHEMA,
        "identity": identity,
        "reviewer": "UNREVIEWED",
        "authority": "ASSISTANT_VISUAL_REVIEW",
        "human_confirmed": False,
        "floor_plane_id": None,
        "coordinate_convention": "dense image edges; pixel center x+0.5,y+0.5; no rotation",
        "regions": [],
    }


def load_review(path, identity, planes, views):
    require(path.stat().st_size <= 512 * 1024, "BOUNDARY_REVIEW_INVALID", "At most 512 KiB")
    data = json.loads(path.read_text(encoding="utf-8"))
    require(
        data["schema"] == SCHEMA
        and data["identity"] == identity
        and data["coordinate_convention"] == template(identity)["coordinate_convention"],
        "BOUNDARY_REVIEW_SOURCE_CHANGED",
        "Exact source/configuration/grid identities",
    )
    require(
        isinstance(data["reviewer"], str)
        and 0 < len(data["reviewer"]) <= 200
        and data["authority"] in ("ASSISTANT_VISUAL_REVIEW", "USER_VISUAL_REVIEW")
        and type(data["human_confirmed"]) is bool
        and (not data["human_confirmed"] or data["authority"] == "USER_VISUAL_REVIEW"),
        "BOUNDARY_REVIEW_INVALID",
        "Review provenance; no assistant human certification",
    )
    by_rank = {v["rank"]: v for v in views}
    by_plane = {p["id"]: p for p in planes}
    regions = data["regions"]
    require(
        isinstance(regions, list) and len(regions) <= 200,
        "BOUNDARY_REVIEW_INVALID",
        "At most 200 regions",
    )
    ids = []
    for row in regions:
        require(
            isinstance(row["id"], str)
            and 0 < len(row["id"]) <= 80
            and type(row["rank"]) is int
            and row["rank"] in by_rank
            and row["plane_id"] in by_plane
            and row["role"] in ROLES[1:]
            and isinstance(row["reason"], str)
            and 0 < len(row["reason"]) <= 2000,
            "BOUNDARY_REVIEW_INVALID",
            "Unique region/rank/plane/role/reason",
        )
        view = by_rank[row["rank"]]
        require(
            all(
                row[k] == view[k]
                for k in (
                    "image",
                    "image_size",
                    "frame_id",
                    "relative_seconds",
                    "source_rgb_sha256",
                    "observations_sha256",
                    "evidence_overlay_sha256",
                )
            ),
            "BOUNDARY_REVIEW_SOURCE_CHANGED",
            row["id"],
        )
        polygon = np.asarray(row["polygon_dense"], float)
        require(
            polygon.ndim == 2
            and polygon.shape[1] == 2
            and 3 <= len(polygon) <= 16
            and np.isfinite(polygon).all()
            and (polygon >= 0).all()
            and (polygon <= np.array(view["image_size"])).all(),
            "BOUNDARY_REGION_INVALID",
            "Finite image-edge polygon",
        )
        edge = np.roll(polygon, -1, axis=0) - polygon
        cross = edge[:, 0] * np.roll(edge[:, 1], -1) - edge[:, 1] * np.roll(edge[:, 0], -1)
        require(
            (np.linalg.norm(edge, axis=1) >= 2).all()
            and ((cross > 1e-6).all() or (cross < -1e-6).all()),
            "BOUNDARY_REGION_INVALID",
            "Strict convex perimeter; no crossings",
        )
        plane = by_plane[row["plane_id"]]
        require(
            row["role"] != "FLOOR" or plane["orientation"] == "horizontal",
            "BOUNDARY_REGION_INVALID",
            "Floor needs horizontal source plane",
        )
        require(
            row["role"] != "WALL" or plane["orientation"] == "vertical",
            "BOUNDARY_REGION_INVALID",
            "Wall needs vertical source plane",
        )
        ids.append(row["id"])
    require(ids == sorted(set(ids)), "BOUNDARY_REVIEW_INVALID", "Unique sorted region IDs")
    floor = data["floor_plane_id"]
    require(
        floor is None
        or (
            floor in by_plane
            and any(r["plane_id"] == floor and r["role"] == "FLOOR" for r in regions)
        ),
        "BOUNDARY_FLOOR_INVALID",
        "Floor reference must have reviewed floor regions",
    )
    return data

"""Application service for canonical-capture-2 photo ingestion."""

import hashlib
import time
from pathlib import Path

from ..bundle import BundleTransaction
from ..contracts import DEFAULT_POLICY, IngestionPolicy
from ..errors import require
from ..models import IngestionResult
from ..storage import pipeline_fingerprint, sha256
from .adapters.photos import (
    ADAPTER,
    PHOTO_SOURCE_FORMAT,
    content_identity,
    filename_timestamp,
    parse_reference,
    resolve_rooms,
)
from .bundle import MultimodalBundleWriter
from .contracts import (
    CAPABILITY_ABSENT,
    CAPABILITY_PRESENT_UNVERIFIED,
    CAPABILITY_USER_DECLARED,
    CAPABILITY_VERIFIED_FORMAT,
    MODE_PHOTOS,
    PHOTO_PROFILE_MAX,
    PHOTO_PROFILE_MIN,
    SCHEMA_V2,
    MultimodalRequest,
)
from .media import DefaultImageInspector
from .models import CaptureBundleContent
from .schema import validate_bundle_documents

LIMITATIONS = [
    "Photos carry no depth or poses; camera intrinsics and world frame remain unknown.",
    "Reference dimensions are user-declared metadata; no scale is applied or localized.",
    "Downstream photo preprocessing/reconstruction is NOT_IMPLEMENTED_FOR_MODALITY.",
]


class PhotosIngestionPipeline:
    def __init__(
        self,
        inspector=None,
        writer: MultimodalBundleWriter | None = None,
        policy: IngestionPolicy = DEFAULT_POLICY,
    ) -> None:
        self.inspector = inspector if inspector is not None else DefaultImageInspector()
        self.writer = writer if writer is not None else MultimodalBundleWriter()
        self.policy = policy

    def run(self, request: MultimodalRequest) -> IngestionResult:
        require(request.mode == MODE_PHOTOS, "NOT_IMPLEMENTED_FOR_MODALITY", str(request.mode))
        request = MultimodalRequest(
            Path(request.source).resolve(),
            Path(request.output).resolve(),
            MODE_PHOTOS,
            request.source_format or PHOTO_SOURCE_FORMAT,
            request.room_label,
            Path(request.reference).resolve() if request.reference else None,
            request.declared_connections,
        )
        reference_decl = parse_reference(request.reference) if request.reference else None
        rooms, photos = resolve_rooms(
            request.source, request.room_label, request.declared_connections
        )
        started = time.perf_counter()
        with BundleTransaction(request, ADAPTER, schema=SCHEMA_V2) as transaction:
            findings: list[dict] = []
            records = []
            for photo in photos:
                digest = sha256(photo.absolute)
                inspection = self.inspector.inspect(photo.absolute)
                records.append(
                    {
                        "source_path": photo.source_path,
                        "absolute": photo.absolute,
                        "room_id": photo.room_id,
                        "role": photo.role,
                        "sha256": digest,
                        "inspection": inspection,
                    }
                )
                findings.extend(_photo_findings(photo.source_path, inspection))
            assets = _build_assets(records)
            asset_id_by_hash = {asset["sha256"]: asset["id"] for asset in assets}
            observations = _build_observations(records, asset_id_by_hash)
            findings.extend(_duplicate_findings(assets))
            distinct = len(assets)
            tier = (
                "PHOTO_PROFILE"
                if PHOTO_PROFILE_MIN <= distinct <= PHOTO_PROFILE_MAX
                else "OUTSIDE_PHOTO_PROFILE"
            )
            if tier != "PHOTO_PROFILE":
                findings.append(
                    {
                        "code": "OUTSIDE_PHOTO_PROFILE",
                        "details": {"distinct_photos": distinct, "profile": [2, 8]},
                    }
                )
            capabilities, references_doc, associations = _reference_documents(
                records, observations, reference_decl
            )
            readiness = {
                "ingestion_integrity": "PASSED",
                "tier_profile": tier,
                "consumer_readiness": {
                    "preprocessing": "NOT_IMPLEMENTED_FOR_MODALITY",
                    "reconstruction": "NOT_IMPLEMENTED_FOR_MODALITY",
                },
                "metric_accuracy": "UNVERIFIED",
            }
            identity = content_identity(
                [
                    {
                        "source_path": record["source_path"],
                        "sha256": record["sha256"],
                        "bytes": record["absolute"].stat().st_size,
                    }
                    for record in records
                ]
            )
            property_id = "property-" + identity[:16]
            rooms_doc = {
                "property_id": property_id,
                "membership": "DERIVED_FROM_PATHS",
                "rooms": [
                    {
                        "id": room.id,
                        "label": room.label,
                        "source_path": room.source_path,
                        "declared_connection_ids": list(room.declared_connection_ids),
                        "image_count": sum(1 for row in observations if row["room_id"] == room.id),
                    }
                    for room in rooms
                ],
                "declared_connections": [],
            }
            assets_doc = {"assets": assets}
            verification = {
                "status": "PASSED",
                "integrity": "PASSED",
                "profile": tier,
                "capabilities": capabilities,
                "readiness": readiness,
                "findings": findings,
                "independent_accuracy": "UNVERIFIED",
                "assets": distinct,
                "observations": len(observations),
                "rooms": len(rooms),
            }
            validate_bundle_documents(
                rooms_doc, assets_doc, observations, references_doc, associations
            )
            manifest_base = {
                "schema": SCHEMA_V2,
                "capture_id": "photos-" + identity[:16],
                "mode": MODE_PHOTOS,
                "source_format": request.source_format,
                "adapter": ADAPTER,
                "status": "READY_WITH_FINDINGS",
                "policy": self.policy.to_dict(),
                "property_id": property_id,
                "room_count": len(rooms),
                "image_count": len(observations),
                "distinct_image_count": distinct,
                "source_identity_sha256": identity,
                "scale": {
                    "source": "none",
                    "independently_validated": False,
                    "correction_applied": False,
                },
                "capabilities": capabilities,
                "readiness": readiness,
                "profile": tier,
                "preprocessing": "NOT_IMPLEMENTED_FOR_MODALITY",
                "reconstruction": "NOT_IMPLEMENTED_FOR_MODALITY",
                "pipeline_source_sha256": pipeline_fingerprint(),
                "limitations": LIMITATIONS,
            }
            content = CaptureBundleContent(
                request=request,
                manifest_base=manifest_base,
                rooms_doc=rooms_doc,
                assets_doc=assets_doc,
                observations=observations,
                associations=associations,
                references_doc=references_doc,
                verification=verification,
                copies=tuple((record["source_path"], record["absolute"]) for record in records),
            )
            runtime = {"started": started, "inspector": type(self.inspector).__name__}
            manifest, report = self.writer.write(transaction.stage, content, runtime)
            for asset in assets:
                for relative in asset["source_paths"]:
                    bundled = transaction.stage / "sources" / relative
                    require(
                        sha256(bundled) == asset["sha256"],
                        "SOURCE_CHANGED",
                        f"Source changed before publication: {relative}",
                    )
                    origin = next(
                        record["absolute"]
                        for record in records
                        if record["source_path"] == relative
                    )
                    require(
                        sha256(origin) == asset["sha256"],
                        "SOURCE_CHANGED",
                        f"Source changed during ingestion: {relative}",
                    )
            transaction.publish()
        return IngestionResult(manifest, report, request.output)


def _photo_findings(source_path: str, inspection) -> list[dict]:
    findings: list[dict] = []
    if not inspection.exif:
        findings.append({"code": "MISSING_EXIF", "details": {"source_path": source_path}})
    timestamp = (inspection.exif.get("timestamp") or {}).get("value")
    if not timestamp:
        findings.append(
            {"code": "MISSING_CAPTURE_TIMESTAMP", "details": {"source_path": source_path}}
        )
    else:
        from_name = filename_timestamp(Path(source_path).stem)
        if from_name and from_name != timestamp[:19]:
            findings.append(
                {
                    "code": "FILENAME_EXIF_TIME_DISCREPANCY",
                    "details": {
                        "source_path": source_path,
                        "filename_time": from_name,
                        "exif_time": timestamp,
                    },
                }
            )
    if inspection.orientation not in (None, 1):
        findings.append(
            {
                "code": "EXIF_ORIENTATION_NOT_APPLIED",
                "details": {"source_path": source_path, "orientation": inspection.orientation},
            }
        )
    return findings


def _build_assets(records: list[dict]) -> list[dict]:
    by_hash: dict[str, list[dict]] = {}
    for record in records:
        by_hash.setdefault(record["sha256"], []).append(record)
    assets = []
    for digest, group in by_hash.items():
        first = group[0]
        inspection = first["inspection"]
        assets.append(
            {
                "id": "asset-" + digest[:16],
                "role": first["role"],
                "sha256": digest,
                "bytes": first["absolute"].stat().st_size,
                "media_format": inspection.media_format,
                "width_px": inspection.width,
                "height_px": inspection.height,
                "orientation": inspection.orientation,
                "decode": inspection.decode,
                "exif": inspection.exif,
                "source_paths": sorted(record["source_path"] for record in group),
                "room_ids": sorted({record["room_id"] for record in group}),
            }
        )
    assets.sort(key=lambda asset: asset["source_paths"][0])
    return assets


def _build_observations(records: list[dict], asset_id_by_hash: dict[str, str]) -> list[dict]:
    observations = []
    for record in sorted(records, key=lambda item: item["source_path"]):
        inspection = record["inspection"]
        exif = inspection.exif
        timestamp = exif.get("timestamp") or {
            "value": None,
            "timezone": None,
            "source": "ABSENT",
            "domain": "unknown",
        }
        observations.append(
            {
                "id": "obs-" + hashlib.sha256(record["source_path"].encode()).hexdigest()[:16],
                "asset_id": asset_id_by_hash[record["sha256"]],
                "room_id": record["room_id"],
                "source_path": record["source_path"],
                "native_frame_id": Path(record["source_path"]).name,
                "pixel_grid": [inspection.width, inspection.height],
                "exif_orientation": inspection.orientation,
                "capture_timestamp": timestamp,
                "camera_K_ref": None,
                "pose_ref": None,
                "processing_eligibility": "INGESTION_ONLY",
            }
        )
    return observations


def _duplicate_findings(assets: list[dict]) -> list[dict]:
    return [
        {
            "code": "DUPLICATE_IMAGE_CONTENT",
            "details": {"asset_id": asset["id"], "paths": asset["source_paths"]},
        }
        for asset in assets
        if len(asset["source_paths"]) > 1
    ]


def _reference_documents(records, observations, reference_decl):
    has_exif = any(record["inspection"].exif for record in records)
    has_timestamp = any(
        (record["inspection"].exif.get("timestamp") or {}).get("value") for record in records
    )
    capabilities = {
        "rgb": CAPABILITY_VERIFIED_FORMAT,
        "exif": CAPABILITY_PRESENT_UNVERIFIED if has_exif else CAPABILITY_ABSENT,
        "timestamps": CAPABILITY_PRESENT_UNVERIFIED if has_timestamp else CAPABILITY_ABSENT,
        "camera_intrinsics": CAPABILITY_ABSENT,
        "poses": CAPABILITY_ABSENT,
        "calibration": CAPABILITY_ABSENT,
        "measured_depth": CAPABILITY_ABSENT,
        "confidence": CAPABILITY_ABSENT,
        "imu": CAPABILITY_ABSENT,
        "photo_rooms": CAPABILITY_PRESENT_UNVERIFIED,
        "reference_dimensions": CAPABILITY_USER_DECLARED if reference_decl else CAPABILITY_ABSENT,
    }
    references_doc = {"scale_applied": False, "objects": []}
    associations: list[dict] = []
    if reference_decl is None:
        return capabilities, references_doc, associations
    reference_asset_id = _resolve_asset(reference_decl.reference_asset, observations)
    candidate_ids = [
        _resolve_asset(candidate, observations) for candidate in reference_decl.candidate_assets
    ]
    references_doc["objects"].append(
        {
            "id": reference_decl.object_id,
            "kind": "planar_reference",
            "width_m": reference_decl.width_m,
            "height_m": reference_decl.height_m,
            "provenance": reference_decl.provenance,
            "geometry": "NOT_LOCALIZED",
            "corners": None,
            "scale_status": "NOT_APPLIED",
            "reference_asset_id": reference_asset_id,
            "candidate_asset_ids": [candidate for candidate in candidate_ids if candidate],
        }
    )
    associations.append(
        {
            "id": "assoc-" + hashlib.sha256(reference_decl.object_id.encode()).hexdigest()[:16],
            "kind": "reference_object",
            "method": "USER_DECLARED",
            "object_id": reference_decl.object_id,
            "reference_asset_id": reference_asset_id,
            "candidate_asset_ids": [candidate for candidate in candidate_ids if candidate],
            "residual": None,
            "evidence": "declared association; object identity across candidates not verified",
        }
    )
    return capabilities, references_doc, associations


def _resolve_asset(reference: str | None, observations: list[dict]) -> str | None:
    if reference is None:
        return None
    normalized = reference.replace("\\", "/")
    for row in observations:
        if row["source_path"] == normalized or row["native_frame_id"] == normalized:
            return row["asset_id"]
    for row in observations:
        if row["source_path"].endswith("/" + normalized):
            return row["asset_id"]
    require(False, "UNKNOWN_REFERENCE_ASSET", reference)
    return None

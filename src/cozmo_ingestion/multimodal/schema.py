"""Internal JSON Schema for canonical-capture-2 and a small structural validator.

The validator is deliberately narrow: types, finite numbers, enums, required fields,
unique IDs, reference integrity and safe relative paths. Format verification is not a
physical-accuracy claim.
"""

import math
import re
from pathlib import PurePosixPath

from ..errors import require
from .contracts import CAPABILITY_VALUES, MODES, SCHEMA_V2

_HEX64 = r"^[0-9a-f]{64}$"
_CAPTURE_ID = r"^[a-z][a-z0-9]*-[0-9a-f]{16}$"

MANIFEST_SCHEMA = {
    "type": "object",
    "required": [
        "schema",
        "capture_id",
        "mode",
        "source_format",
        "adapter",
        "status",
        "policy",
        "artifact_sha256",
        "capabilities",
        "readiness",
        "scale",
        "room_count",
        "image_count",
        "distinct_image_count",
        "property_id",
        "source_identity_sha256",
        "pipeline_source_sha256",
    ],
    "properties": {
        "schema": {"const": SCHEMA_V2},
        "capture_id": {"type": "string", "pattern": _CAPTURE_ID},
        "mode": {"enum": list(MODES)},
        "source_format": {"type": "string", "minLength": 1},
        "adapter": {"type": "string", "minLength": 1},
        "status": {"enum": ["READY_WITH_FINDINGS"]},
        "artifact_sha256": {
            "type": "object",
            "additionalProperties": {"type": "string", "pattern": _HEX64},
        },
        "capabilities": {
            "type": "object",
            "additionalProperties": {"enum": list(CAPABILITY_VALUES)},
        },
        "scale": {
            "type": "object",
            "required": ["source", "independently_validated", "correction_applied"],
            "properties": {
                "independently_validated": {"type": "boolean"},
                "correction_applied": {"type": "boolean", "const": False},
            },
        },
        "room_count": {"type": "integer", "minimum": 1},
        "image_count": {"type": "integer", "minimum": 1},
        "distinct_image_count": {"type": "integer", "minimum": 1},
        "property_id": {"type": "string", "minLength": 1},
        "source_identity_sha256": {"type": "string", "pattern": _HEX64},
        "pipeline_source_sha256": {"type": "string", "pattern": _HEX64},
    },
    "additionalProperties": True,
}

ROOMS_SCHEMA = {
    "type": "object",
    "required": ["property_id", "membership", "rooms", "declared_connections"],
    "properties": {
        "membership": {"enum": ["DERIVED_FROM_PATHS", "USER_DECLARED", "UNSEGMENTED"]},
        "rooms": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": [
                    "id",
                    "label",
                    "source_path",
                    "declared_connection_ids",
                    "image_count",
                ],
                "properties": {
                    "id": {"type": "string", "minLength": 1},
                    "label": {"type": "string", "minLength": 1},
                    "source_path": {"type": "string"},
                    "declared_connection_ids": {"type": "array", "items": {"type": "string"}},
                    "image_count": {"type": "integer", "minimum": 0},
                },
            },
        },
        "declared_connections": {"type": "array"},
    },
    "additionalProperties": True,
}

ASSETS_SCHEMA = {
    "type": "object",
    "required": ["assets"],
    "properties": {
        "assets": {
            "type": "array",
            "items": {
                "type": "object",
                "required": [
                    "id",
                    "role",
                    "sha256",
                    "bytes",
                    "media_format",
                    "source_paths",
                ],
                "properties": {
                    "id": {"type": "string", "minLength": 1},
                    "role": {
                        "enum": [
                            "scene_photo",
                            "reference_photo",
                            "walkthrough_rgb",
                            "lidar_depth",
                            "confidence",
                            "pose_calibration",
                            "imu_native",
                            "metadata",
                        ]
                    },
                    "sha256": {"type": "string", "pattern": _HEX64},
                    "bytes": {"type": "integer", "minimum": 1},
                    "media_format": {"enum": ["jpeg", "png", "video", "csv", "json"]},
                    "width_px": {"type": "integer", "minimum": 1},
                    "height_px": {"type": "integer", "minimum": 1},
                    "orientation": {"type": ["integer", "null"], "minimum": 1, "maximum": 8},
                    "decode": {"enum": ["STRUCTURE_VERIFIED", "FULL_DECODE"]},
                    "source_paths": {
                        "type": "array",
                        "minItems": 1,
                        "items": {"type": "string", "minLength": 1},
                    },
                    "room_ids": {"type": "array", "items": {"type": "string"}},
                },
            },
        }
    },
    "additionalProperties": True,
}


OBSERVATION_SCHEMA = {
    "type": "object",
    "required": [
        "id",
        "asset_id",
        "room_id",
        "source_path",
        "native_frame_id",
        "pixel_grid",
        "camera_K_ref",
        "pose_ref",
        "processing_eligibility",
    ],
    "properties": {
        "id": {"type": "string", "minLength": 1},
        "asset_id": {"type": "string", "minLength": 1},
        "room_id": {"type": "string", "minLength": 1},
        "source_path": {"type": "string", "minLength": 1},
        "native_frame_id": {"type": "string", "minLength": 1},
        "pixel_grid": {
            "type": "array",
            "minItems": 2,
            "maxItems": 2,
            "items": {"type": "integer", "minimum": 1},
        },
        "camera_K_ref": {"type": ["string", "null"]},
        "pose_ref": {"type": ["string", "null"]},
        "processing_eligibility": {"type": "string", "minLength": 1},
    },
    "additionalProperties": True,
}

REFERENCE_SCHEMA = {
    "type": "object",
    "required": ["scale_applied", "objects"],
    "properties": {
        "scale_applied": {"type": "boolean", "const": False},
        "objects": {
            "type": "array",
            "items": {
                "type": "object",
                "required": [
                    "id",
                    "kind",
                    "width_m",
                    "height_m",
                    "provenance",
                    "geometry",
                    "corners",
                    "scale_status",
                    "reference_asset_id",
                    "candidate_asset_ids",
                ],
                "properties": {
                    "id": {"type": "string", "minLength": 1},
                    "kind": {"enum": ["planar_reference"]},
                    "width_m": {"type": "number", "minimum": 0},
                    "height_m": {"type": "number", "minimum": 0},
                    "provenance": {"enum": ["USER_DECLARED"]},
                    "geometry": {"enum": ["NOT_LOCALIZED"]},
                    "corners": {"const": None},
                    "scale_status": {"enum": ["NOT_APPLIED"]},
                    "reference_asset_id": {"type": ["string", "null"]},
                    "candidate_asset_ids": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
    },
    "additionalProperties": False,
}

ASSOCIATION_SCHEMA = {
    "type": "object",
    "required": ["id", "kind", "method"],
    "properties": {
        "id": {"type": "string", "minLength": 1},
        "kind": {"type": "string", "minLength": 1},
        "method": {"type": "string", "minLength": 1},
    },
    "additionalProperties": True,
}

VERIFICATION_SCHEMA = {
    "type": "object",
    "required": ["status", "integrity", "profile", "capabilities", "readiness", "findings"],
    "properties": {
        "status": {"enum": ["PASSED"]},
        "integrity": {"enum": ["PASSED"]},
        "profile": {"type": "string", "minLength": 1},
        "capabilities": {
            "type": "object",
            "additionalProperties": {"enum": list(CAPABILITY_VALUES)},
        },
        "findings": {"type": "array"},
    },
    "additionalProperties": True,
}

POSE_SCHEMA = {
    "type": "object",
    "required": [
        "id",
        "native_frame_id",
        "world_from_camera",
        "pose_direction",
        "quaternion_order",
        "axes",
        "translation_units",
        "source",
    ],
    "properties": {
        "id": {"type": "string", "minLength": 1},
        "native_frame_id": {"type": "string", "minLength": 1},
        "world_from_camera": {
            "type": "object",
            "required": ["t", "q"],
            "properties": {
                "t": {"type": "array", "minItems": 3, "maxItems": 3, "items": {"type": "number"}},
                "q": {"type": "array", "minItems": 4, "maxItems": 4, "items": {"type": "number"}},
            },
        },
        "pose_direction": {"type": "string", "minLength": 1},
        "quaternion_order": {"type": "string", "minLength": 1},
        "axes": {"type": "string", "minLength": 1},
        "translation_units": {"type": "string", "minLength": 1},
        "source": {"type": "string", "minLength": 1},
    },
    "additionalProperties": True,
}

CALIBRATION_SCHEMA = {
    "type": "object",
    "required": ["id", "native_frame_id", "K", "reference_grid", "source"],
    "properties": {
        "id": {"type": "string", "minLength": 1},
        "native_frame_id": {"type": "string", "minLength": 1},
        "K": {
            "type": "array",
            "minItems": 3,
            "maxItems": 3,
            "items": {
                "type": "array",
                "minItems": 3,
                "maxItems": 3,
                "items": {"type": "number"},
            },
        },
        "reference_grid": {
            "type": "array",
            "minItems": 2,
            "maxItems": 2,
            "items": {"type": "integer", "minimum": 1},
        },
        "source": {"type": "string", "minLength": 1},
    },
    "additionalProperties": True,
}

DOCUMENT_SCHEMAS = {
    "manifest": MANIFEST_SCHEMA,
    "rooms": ROOMS_SCHEMA,
    "assets": ASSETS_SCHEMA,
    "observation": OBSERVATION_SCHEMA,
    "reference": REFERENCE_SCHEMA,
    "association": ASSOCIATION_SCHEMA,
    "verification": VERIFICATION_SCHEMA,
    "pose": POSE_SCHEMA,
    "calibration": CALIBRATION_SCHEMA,
}


def _type_matches(kind: str, value) -> bool:
    if kind == "null":
        return value is None
    if kind == "boolean":
        return isinstance(value, bool)
    if kind == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if kind == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if kind == "string":
        return isinstance(value, str)
    if kind == "array":
        return isinstance(value, list)
    if kind == "object":
        return isinstance(value, dict)
    return False


def validate_document(name: str, value, path: str | None = None) -> None:
    """Validate one document against its internal schema; raise INVALID_DOCUMENT on failure."""
    require(name in DOCUMENT_SCHEMAS, "UNKNOWN_SCHEMA_NAME", name)
    _validate(DOCUMENT_SCHEMAS[name], value, path or name)


def _validate(schema: dict, value, path: str) -> None:
    if schema.get("nullable") and value is None:
        return
    if "const" in schema:
        require(value == schema["const"], "INVALID_DOCUMENT", f"{path}: const mismatch")
    if "enum" in schema:
        require(value in schema["enum"], "INVALID_DOCUMENT", f"{path}: not in enum")
    kind = schema.get("type")
    if kind is None:
        return
    kinds = kind if isinstance(kind, list) else [kind]
    require(
        any(_type_matches(k, value) for k in kinds),
        "INVALID_DOCUMENT",
        f"{path}: expected {kind}",
    )
    if value is None:
        return
    if "number" in kinds or "integer" in kinds:
        require(math.isfinite(value), "INVALID_DOCUMENT", f"{path}: non-finite number")
        if "minimum" in schema:
            require(value >= schema["minimum"], "INVALID_DOCUMENT", f"{path}: below minimum")
        if "maximum" in schema:
            require(value <= schema["maximum"], "INVALID_DOCUMENT", f"{path}: above maximum")
    if isinstance(value, str):
        if "pattern" in schema:
            require(
                re.match(schema["pattern"], value) is not None,
                "INVALID_DOCUMENT",
                f"{path}: pattern mismatch",
            )
        if "minLength" in schema:
            require(len(value) >= schema["minLength"], "INVALID_DOCUMENT", f"{path}: too short")
    if isinstance(value, list):
        if "minItems" in schema:
            require(len(value) >= schema["minItems"], "INVALID_DOCUMENT", f"{path}: too few items")
        if "maxItems" in schema:
            require(len(value) <= schema["maxItems"], "INVALID_DOCUMENT", f"{path}: too many items")
        if "items" in schema:
            for index, item in enumerate(value):
                _validate(schema["items"], item, f"{path}[{index}]")
    if isinstance(value, dict):
        for key in schema.get("required", []):
            require(key in value, "INVALID_DOCUMENT", f"{path}: missing {key}")
        properties = schema.get("properties", {})
        additional = schema.get("additionalProperties", True)
        for key, item in value.items():
            if key in properties:
                _validate(properties[key], item, f"{path}.{key}")
            elif additional is False:
                require(False, "INVALID_DOCUMENT", f"{path}: unexpected {key}")
            elif isinstance(additional, dict):
                _validate(additional, item, f"{path}.{key}")


def safe_relative_path(value: str) -> None:
    """Reject absolute, parent-escaping or backslash paths in portable bundles."""
    normalized = value.replace("\\", "/")
    path = PurePosixPath(normalized)
    require(
        normalized == value
        and not path.is_absolute()
        and bool(path.parts)
        and all(part not in {"", ".", ".."} for part in path.parts),
        "UNSAFE_BUNDLE_PATH",
        value,
    )


def validate_bundle_documents(
    rooms_doc: dict,
    assets_doc: dict,
    observations: list[dict],
    references_doc: dict,
    associations: list[dict],
    calibrations: list[dict] | None = None,
    poses: list[dict] | None = None,
) -> None:
    """Unique IDs, safe paths, room/asset referential integrity and finite dimensions."""
    calibrations = calibrations or []
    poses = poses or []
    validate_document("rooms", rooms_doc)
    validate_document("assets", assets_doc)
    validate_document("reference", references_doc)
    room_ids = [room["id"] for room in rooms_doc["rooms"]]
    require(len(set(room_ids)) == len(room_ids), "DUPLICATE_ID", "rooms")
    connection_targets = {
        connection for room in rooms_doc["rooms"] for connection in room["declared_connection_ids"]
    }
    require(connection_targets <= set(room_ids), "DANGLING_ROOM_LINK", "declared connections")
    asset_ids = [asset["id"] for asset in assets_doc["assets"]]
    require(len(set(asset_ids)) == len(asset_ids), "DUPLICATE_ID", "assets")
    for asset in assets_doc["assets"]:
        for source_path in asset["source_paths"]:
            safe_relative_path(source_path)
        require(
            set(asset.get("room_ids", [])) <= set(room_ids),
            "DANGLING_ROOM_LINK",
            asset["id"],
        )
    calibration_ids = [row["id"] for row in calibrations]
    require(len(set(calibration_ids)) == len(calibration_ids), "DUPLICATE_ID", "calibration")
    for row in calibrations:
        validate_document("calibration", row)
    pose_ids = [row["id"] for row in poses]
    require(len(set(pose_ids)) == len(pose_ids), "DUPLICATE_ID", "poses")
    for row in poses:
        validate_document("pose", row)
    observation_ids = [row["id"] for row in observations]
    require(len(set(observation_ids)) == len(observation_ids), "DUPLICATE_ID", "observations")
    for row in observations:
        validate_document("observation", row)
        require(row["asset_id"] in asset_ids, "DANGLING_ASSET_LINK", row["id"])
        require(row["room_id"] in room_ids, "DANGLING_ROOM_LINK", row["id"])
        safe_relative_path(row["source_path"])
        for key, value in row.items():
            if value is not None and key.endswith("_asset_id") and value not in asset_ids:
                require(False, "DANGLING_ASSET_LINK", f"{row['id']}:{key}")
        if row.get("camera_K_ref") is not None:
            require(row["camera_K_ref"] in calibration_ids, "DANGLING_CALIBRATION_LINK", row["id"])
        if row.get("pose_ref") is not None:
            require(row["pose_ref"] in pose_ids, "DANGLING_POSE_LINK", row["id"])
    association_ids = [row["id"] for row in associations]
    require(len(set(association_ids)) == len(association_ids), "DUPLICATE_ID", "associations")
    for row in associations:
        validate_document("association", row)

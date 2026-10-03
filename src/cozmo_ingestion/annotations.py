"""Bind user scale declarations to source identity without estimating scale."""

import json
from decimal import Decimal
from pathlib import Path

from .errors import require
from .numeric import number
from .storage import sha256


def normalize_annotations(
    path: Path | None, video_hash: str, rows: list[dict], origin: Decimal
) -> dict:
    """Record source-bound declarations and candidate frames; never infer visibility."""
    if path is None:
        return {"status": "ABSENT", "reference_objects": [], "scale_applied": False}
    data = json.loads(path.read_text(encoding="utf-8"))
    require(
        data.get("schema_version") == 1 and data.get("source_video_sha256") == video_hash,
        "ANNOTATION_SOURCE_MISMATCH",
        "Scale annotation must name the exact source video SHA-256",
    )
    objects = data.get("reference_objects", [])
    require(isinstance(objects, list), "INVALID_ANNOTATION", "reference_objects must be a list")
    normalized, seen = [], set()
    for obj in objects:
        object_id = obj.get("id")
        require(
            isinstance(object_id, str) and object_id and object_id not in seen,
            "INVALID_ANNOTATION",
            "Unique reference object IDs required",
        )
        seen.add(object_id)
        require(
            number(obj["width_m"]) > 0 and number(obj["height_m"]) > 0,
            "INVALID_ANNOTATION",
            "Positive dimensions required",
        )
        require(
            obj.get("dimensions_source") == "USER_REPORTED"
            and obj.get("visibility_verified") is False,
            "UNSUPPORTED_ANNOTATION",
            "v1 accepts user declarations, not detected corner/scale outputs",
        )
        window = obj["candidate_window_seconds"]
        require(
            len(window) == 2 and 0 <= number(window[0]) < number(window[1]),
            "INVALID_ANNOTATION",
            "Ordered candidate time window required",
        )
        candidate = [
            int(r["frame_index"])
            for r in rows
            if number(window[0]) <= number(r["sensor_sec"]) - origin <= number(window[1])
        ]
        require(
            bool(candidate),
            "INVALID_ANNOTATION",
            "Candidate window does not intersect this capture",
        )
        normalized.append(
            {
                **obj,
                "candidate_source_frame_indices": candidate,
                "corner_coordinates": None,
                "localization_status": "NOT_RUN",
                "scale_estimation_status": "NOT_RUN",
            }
        )
    return {
        "status": "USER_DECLARED_PRIOR",
        "source_annotation_sha256": sha256(path),
        "reference_objects": normalized,
        "scale_applied": False,
        "usage": "optional human scale assistance; not independent evaluation ground truth",
    }

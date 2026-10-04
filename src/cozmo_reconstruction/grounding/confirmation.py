"""Bind a separate human review and a thickness interval to exact corner inputs."""

import json

import numpy as np

from cozmo_ingestion.errors import require


def load_confirmation(path, annotation_sha256, identity, annotations):
    require(path.stat().st_size <= 64 * 1024, "GROUNDING_REVIEW_INVALID", "Review at most 64 KiB")
    data = json.loads(path.read_text(encoding="utf-8"))
    require(
        data["schema"] == "holo-grounding-user-confirmation-v1"
        and data["source_video_sha256"] == identity["source_video_sha256"]
        and data["corner_proposals_sha256"] == annotation_sha256
        and data["reviewed_frame_ranks"] == [r["rank"] for r in annotations["observations"]]
        and len(annotations["observations"]) > 0,
        "GROUNDING_REVIEW_SOURCE_CHANGED",
        "Review binds the exact original corners, source video and all marked ranks",
    )
    require(
        data["corner_confirmation"]["authority"] == "USER_CONFIRMED_CHAT"
        and isinstance(data["corner_confirmation"]["statement"], str)
        and 0 < len(data["corner_confirmation"]["statement"]) <= 5000,
        "GROUNDING_REVIEW_INVALID",
        "Explicit human confirmation",
    )
    bound = data["cover_thickness"]
    lower, upper = bound["lower_bound_m"], bound["upper_bound_m"]
    require(
        all(type(v) in (int, float) and np.isfinite(v) for v in (lower, upper))
        and 0 <= lower < upper <= 0.2
        and type(bound["lower_bound_inclusive"]) is bool
        and type(bound["upper_bound_inclusive"]) is bool
        and bound["authority"] == "USER_REPORTED_CHAT"
        and bound["exact_thickness_m"] is None
        and bound["zero_thickness_assumed"] is False,
        "GROUNDING_REVIEW_INVALID",
        "Finite nonempty bounded thickness; no exact or zero assumption",
    )
    exact = annotations["cover_thickness_m"]
    require(
        exact is None
        or (
            (exact > lower or (bound["lower_bound_inclusive"] and exact == lower))
            and (exact < upper or (bound["upper_bound_inclusive"] and exact == upper))
        ),
        "GROUNDING_REVIEW_INVALID",
        "Exact annotation thickness must agree with the reviewed interval",
    )
    return data


def bottom_offset_interval(offset, normal_y, bound):
    """Signed plane-distance interval for cover center minus thickness along world +Y.

    Only a conditional flat, floor-resting interpretation; neither semantic identity
    nor the source world's gravity alignment is established by this calculation.
    """
    values = [offset - normal_y * bound[k] for k in ("lower_bound_m", "upper_bound_m")]
    inclusive = [bound["lower_bound_inclusive"], bound["upper_bound_inclusive"]]
    if normal_y < 0:
        return dict(
            lower_m=values[0],
            upper_m=values[1],
            lower_inclusive=inclusive[0],
            upper_inclusive=inclusive[1],
        )
    if normal_y == 0:
        return dict(lower_m=offset, upper_m=offset, lower_inclusive=True, upper_inclusive=True)
    return dict(
        lower_m=values[1],
        upper_m=values[0],
        lower_inclusive=inclusive[1],
        upper_inclusive=inclusive[0],
    )

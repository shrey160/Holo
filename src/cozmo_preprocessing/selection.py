"""Conservative temporal/motion selection with explicit coverage safeguards."""

import math

from .analysis import pose_delta
from .models import PreprocessingPolicy


def candidate_indices(frames: list[dict], fps: float) -> list[int]:
    indices, last_bucket = [], -1
    for i, row in enumerate(frames):
        bucket = math.floor(float(row["relative_seconds"]) * fps + 1e-8)
        if bucket > last_bucket:
            indices.append(i)
            last_bucket = bucket
    if indices[-1] != len(frames) - 1:
        indices.append(len(frames) - 1)
    return indices


def choose_views(
    candidates: list[dict], poses: dict, policy: PreprocessingPolicy
) -> dict[int, list[str]]:
    selected = {candidates[0]["rank"]: ["START_BOUNDARY"], candidates[-1]["rank"]: ["END_BOUNDARY"]}
    # Best normal-tracking observation in every bounded temporal bin.
    bins = {}
    for c in candidates:
        bucket = math.floor(c["seconds"] / (policy.max_gap_seconds / 2))
        bins.setdefault(bucket, []).append(c)
    for values in bins.values():
        best = max(values, key=lambda c: (c["tracking_normal"], c["quality"]["score"], -c["rank"]))
        selected.setdefault(best["rank"], []).append("TEMPORAL_COVERAGE")
    anchor = candidates[0]
    for c in candidates[1:]:
        distance, angle = pose_delta(poses[anchor["frame_id"]], poses[c["frame_id"]])
        changed_tracking = c["tracking_normal"] != anchor["tracking_normal"]
        if distance >= policy.translation_m or angle >= policy.rotation_degrees or changed_tracking:
            reasons = []
            if distance >= policy.translation_m:
                reasons.append("TRANSLATION")
            if angle >= policy.rotation_degrees:
                reasons.append("ROTATION")
            if changed_tracking:
                reasons.append("TRACKING_TRANSITION")
            selected.setdefault(c["rank"], []).extend(reasons)
            anchor = c
        elif c["rank"] in selected:
            anchor = c
    return selected

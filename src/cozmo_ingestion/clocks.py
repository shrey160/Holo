"""Exact media association and native-stream coverage statistics."""

from decimal import Decimal
from fractions import Fraction

from .contracts import DEFAULT_POLICY, IngestionPolicy
from .errors import require
from .models import VideoInspection
from .numeric import integer, number


def associate(
    rows: list[dict], video: VideoInspection, policy: IngestionPolicy = DEFAULT_POLICY
) -> tuple[dict, list[int]]:
    """Require one-to-one source indices and relative presentation-clock agreement."""
    frames = video.frames
    require(
        len(rows) == len(frames),
        "FRAME_COUNT_MISMATCH",
        f"{len(rows)} rows vs {len(frames)} decoded frames",
    )
    require(
        not video.discarded_packets,
        "UNSUPPORTED_DISCARD",
        "No initial-discard offset is allowed for this adapter",
    )
    times = [Fraction(r["sensor_sec"]) for r in rows]
    require(
        all(b > a for a, b in zip(times, times[1:], strict=False)),
        "NONMONOTONIC_TIME",
        "Camera timestamps",
    )
    require(
        [integer(r["frame_index"]) for r in rows] == list(range(len(rows))),
        "FRAME_ID_MISMATCH",
        "Require sequential frame indices",
    )
    slots = [integer(r["record_slot"]) for r in rows]
    require(
        all(b > a for a, b in zip(slots, slots[1:], strict=False)),
        "NONMONOTONIC_SLOT",
        "Recording slots",
    )
    timebase = Fraction(video.stream["time_base"])
    require(timebase > 0, "INVALID_TIMEBASE", "Media timebase must be positive")
    ticks = [integer(r["best_effort_timestamp"]) for r in frames]
    require(
        all(b > a for a, b in zip(ticks, ticks[1:], strict=False)),
        "NONMONOTONIC_PTS",
        "Video presentation timestamps",
    )
    pts = [tick * timebase for tick in ticks]
    errors = [(t - times[0]) - (p - pts[0]) for t, p in zip(times, pts, strict=True)]
    maximum = max(abs(e) for e in errors)
    require(
        maximum <= Fraction(str(policy.clock_tolerance_seconds)),
        "FRAME_CLOCK_MISMATCH",
        f"Maximum residual {float(maximum)} s",
    )
    return {
        "method": "decoded presentation rank i -> source frame_index i; validated constant clock offset",
        "media_timebase": str(timebase),
        "maximum_residual_seconds": float(maximum),
        "sensor_minus_media_origin_seconds": str(
            number(rows[0]["sensor_sec"]) - Decimal(pts[0].numerator) / Decimal(pts[0].denominator)
        ),
        "physical_synchronization": "UNVERIFIED",
    }, ticks


def timing(rows: list[dict], origin: Decimal) -> dict:
    """Describe native stream coverage; no interpolation or boundary extrapolation."""
    times = [number(r["sensor_sec"]) for r in rows]
    delta = sorted(b - a for a, b in zip(times, times[1:], strict=False))
    result = {
        "samples": len(times),
        "relative_start_seconds": str(times[0] - origin),
        "relative_end_seconds": str(times[-1] - origin),
        "native_clock": "sensor_sec",
        "strictly_increasing": True,
    }
    if delta:
        middle = len(delta) // 2
        median = delta[middle] if len(delta) % 2 else (delta[middle - 1] + delta[middle]) / 2
        result.update(
            median_interval_seconds=str(median),
            maximum_interval_seconds=str(delta[-1]),
            effective_rate_hz=float(Decimal(len(times) - 1) / (times[-1] - times[0])),
        )
    return result

"""Exact decimal parsing and source quaternion geometry."""

import math
from decimal import Decimal

from .contracts import DEFAULT_POLICY, IngestionPolicy
from .errors import IngestionError, require


def number(value: str | int | float | Decimal) -> Decimal:
    """Parse finite source values without losing decimal timestamp precision."""
    try:
        result = Decimal(str(value))
    except Exception as error:
        raise IngestionError("INVALID_NUMBER", str(value)) from error
    require(result.is_finite(), "NONFINITE_VALUE", str(value))
    return result


def integer(value: str | int | float | Decimal) -> int:
    """Reject fractional indices instead of silently rounding them."""
    n = number(value)
    require(n == n.to_integral_value(), "INVALID_INTEGER", str(value))
    return int(n)


def quaternion_pose(row: dict, policy: IngestionPolicy = DEFAULT_POLICY) -> tuple[list, float]:
    """Construct parent-from-child geometry, retaining rounded source values elsewhere."""
    q = [float(number(row[k])) for k in ["qw", "qx", "qy", "qz"]]
    norm = math.sqrt(sum(v * v for v in q))
    require(
        abs(norm - 1) <= policy.quaternion_norm_tolerance, "INVALID_QUATERNION", row["frame_index"]
    )
    w, x, y, z = [v / norm for v in q]
    rotation = [
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ]
    position = [float(number(row[k])) for k in ["tx_m", "ty_m", "tz_m"]]
    return [rotation[i] + [position[i]] for i in range(3)] + [[0.0, 0.0, 0.0, 1.0]], norm

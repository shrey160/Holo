"""Canonical schema identity and immutable ingestion policy."""

from dataclasses import asdict, dataclass
from math import isfinite

from .errors import require


@dataclass(frozen=True)
class IngestionPolicy:
    """Explicit tolerances; ingestion never refines geometry or pixels."""

    clock_tolerance_seconds: float = 0.000002
    quaternion_norm_tolerance: float = 0.0001
    apparent_pose_speed_warning_m_s: float = 3.0
    pose_refinement: bool = False
    image_transforms: str = "identity; native pixels retained"
    scale_correction: bool = False

    def __post_init__(self) -> None:
        for value in (
            self.clock_tolerance_seconds,
            self.quaternion_norm_tolerance,
            self.apparent_pose_speed_warning_m_s,
        ):
            require(
                isfinite(value) and value > 0,
                "INVALID_POLICY",
                "Tolerances must be finite and positive",
            )
        require(
            not self.pose_refinement
            and not self.scale_correction
            and self.image_transforms == "identity; native pixels retained",
            "UNSUPPORTED_POLICY",
            "Ingestion preserves source geometry and pixels",
        )

    def to_dict(self) -> dict:
        return asdict(self)


DEFAULT_POLICY = IngestionPolicy()
SCHEMA = "canonical-capture-1"

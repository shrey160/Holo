"""Immutable requests and bounded diagnostic thresholds."""

from dataclasses import dataclass
from pathlib import Path

from cozmo_ingestion.errors import require


@dataclass(frozen=True)
class GroundingPolicy:
    min_views: int = 3
    min_angle_degrees: float = 1.5
    max_reprojection_pixels: float = 4.0
    size_relative_tolerance: float = 0.05
    ambiguity_pixels: float = 1.0
    max_pose_center_spread_m: float = 0.03
    max_pose_normal_spread_degrees: float = 15.0
    sensitivity_pixels: float = 3.0
    sensitivity_trials: int = 32
    seed: int = 17

    def __post_init__(self):
        require(
            type(self.min_views) is int
            and 3 <= self.min_views <= 12
            and 0.1 <= self.min_angle_degrees <= 15
            and 0.1 <= self.max_reprojection_pixels <= 20
            and 0 < self.size_relative_tolerance <= 0.2
            and 0 <= self.ambiguity_pixels <= 5
            and 0.005 <= self.max_pose_center_spread_m <= 0.2
            and 1 <= self.max_pose_normal_spread_degrees <= 45
            and 0 < self.sensitivity_pixels <= 10
            and type(self.sensitivity_trials) is int
            and 8 <= self.sensitivity_trials <= 64
            and type(self.seed) is int
            and 0 <= self.seed < 2**32,
            "GROUNDING_POLICY_INVALID",
            "Bounded diagnostic policy",
        )


@dataclass(frozen=True)
class GroundingRequest:
    prepared: Path
    bundle: Path
    output: Path
    source: Path | None = None
    annotations: Path | None = None
    object_id: str = "opening-a4-reference"
    sparse: Path | None = None
    dense: Path | None = None
    surfaces: Path | None = None
    review_confirmation: Path | None = None

    def __post_init__(self):
        require(
            bool(self.object_id) and len(self.object_id) <= 100,
            "GROUNDING_OBJECT_INVALID",
            "Object ID",
        )
        require(
            (self.sparse is None) == (self.dense is None)
            and (self.surfaces is None or self.dense is not None),
            "GROUNDING_UPSTREAM_INVALID",
            "Dense requires sparse; surfaces requires dense",
        )

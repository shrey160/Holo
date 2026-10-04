"""Bounded extraction policy and immutable upstream associations."""

from dataclasses import dataclass
from pathlib import Path

from cozmo_ingestion.errors import require
from cozmo_reconstruction.dense.models import DenseRequest


@dataclass(frozen=True)
class SurfacePolicy:
    distance_m: float = 0.035
    fit_points: int = 12000
    iterations: int = 384
    max_planes: int = 12
    min_fit_inliers: int = 150
    seed: int = 17
    sample_stride: int = 4
    patch_cell_m: float = 0.15
    min_view_samples: int = 150
    min_views: int = 3
    min_baseline_m: float = 0.15
    min_span_m: float = 0.75
    orientation_degrees: float = 15.0

    def __post_init__(self):
        require(
            0.005 <= self.distance_m <= 0.1
            and 1000 <= self.fit_points <= 30000
            and 32 <= self.iterations <= 1000
            and 1 <= self.max_planes <= 20
            and 30 <= self.min_fit_inliers <= self.fit_points
            and type(self.seed) is int
            and 0 <= self.seed <= 2**32 - 1
            and 1 <= self.sample_stride <= 8
            and 0.05 <= self.patch_cell_m <= 0.5
            and 10 <= self.min_view_samples <= 10000
            and 2 <= self.min_views <= 100
            and 0.05 <= self.min_baseline_m <= 2
            and 0.2 <= self.min_span_m <= 3
            and 1 <= self.orientation_degrees <= 30,
            "SURFACE_POLICY_INVALID",
            "Bounded metric diagnostic thresholds",
        )


@dataclass(frozen=True)
class SurfaceRequest:
    upstream: DenseRequest
    output: Path

    @property
    def dense(self):
        return self.upstream.output

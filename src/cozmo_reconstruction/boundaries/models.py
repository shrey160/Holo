"""Frozen source chain and bounded support requirements."""

from dataclasses import dataclass
from math import isfinite
from pathlib import Path

from cozmo_ingestion.errors import require
from cozmo_reconstruction.surfaces.models import SurfaceRequest


@dataclass(frozen=True)
class BoundaryPolicy:
    cell_m: float = 0.15
    min_points_per_view: int = 8
    min_floor_views: int = 3
    min_wall_views: int = 3
    min_cell_views: int = 2
    min_baseline_m: float = 0.15
    min_span_m: float = 0.30
    near_floor_m: float = 0.10

    def __post_init__(self):
        require(
            all(
                type(v) in (int, float) and isfinite(v)
                for v in (self.cell_m, self.min_baseline_m, self.min_span_m, self.near_floor_m)
            )
            and 0.05 <= self.cell_m <= 0.5
            and type(self.min_points_per_view) is int
            and 3 <= self.min_points_per_view <= 200
            and all(
                type(v) is int and 2 <= v <= 12
                for v in (self.min_floor_views, self.min_wall_views, self.min_cell_views)
            )
            and 0.05 <= self.min_baseline_m <= 1
            and self.cell_m <= self.min_span_m <= 2
            and 0.02 <= self.near_floor_m <= 0.2,
            "BOUNDARY_POLICY_INVALID",
            "Finite bounded support policy",
        )


@dataclass(frozen=True)
class BoundaryRequest:
    surfaces: SurfaceRequest
    output: Path
    review: Path | None = None
    grounding: Path | None = None

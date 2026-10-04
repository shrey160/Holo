"""Immutable application policy and request."""

import math
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ReconstructionPolicy:
    max_features: int = 4096
    threads: int = 4
    seed: int = 42
    timeout_seconds: int = 600
    max_views: int = 300
    temporal_window: int = 8
    revisit_neighbors: int = 6
    min_track_length: int = 3
    min_angle_degrees: float = 1.5
    max_reprojection_pixels: float = 4.0
    principal_point_shift: float = 0.0

    def __post_init__(self):
        for key in (
            "max_features",
            "threads",
            "timeout_seconds",
            "max_views",
            "temporal_window",
            "revisit_neighbors",
            "min_track_length",
        ):
            value = getattr(self, key)
            if type(value) is not int or value <= 0:
                raise ValueError(f"{key} must be a positive integer")
        if type(self.seed) is not int or self.seed < 0:
            raise ValueError("seed must be a nonnegative integer")
        if self.min_track_length < 3 or self.max_views > 300 or self.threads > 32:
            raise ValueError("Require >=3-view tracks, <=300 views and <=32 threads")
        for key in ("min_angle_degrees", "max_reprojection_pixels"):
            if not math.isfinite(getattr(self, key)) or getattr(self, key) <= 0:
                raise ValueError(f"{key} must be positive and finite")
        if self.principal_point_shift not in (0.0, 0.5):
            raise ValueError("Explicit pixel convention hypotheses are 0 or +0.5 pixels")


@dataclass(frozen=True)
class ReconstructionRequest:
    prepared: Path
    bundle: Path
    output: Path
    source_root: Path | None = None
    ranks: tuple[int, ...] | None = None

"""Bounded immutable dense contracts, independent of CLI or CUDA."""

from dataclasses import dataclass
from pathlib import Path

from cozmo_ingestion.errors import require


@dataclass(frozen=True)
class DensePolicy:
    max_image_size: int = 960
    neighbors: int = 6
    iterations: int = 3
    threads: int = 4
    timeout_seconds: int = 1800
    min_support: int = 2
    relative_depth_error: float = 0.02
    roundtrip_pixels: float = 1.0
    min_angle_degrees: float = 1.0
    min_depth: float = 0.1
    max_depth: float = 20.0
    voxel_size: float = 0.01
    sample_stride: int = 2

    def __post_init__(self):
        require(
            320 <= self.max_image_size <= 1920
            and 2 <= self.neighbors <= 12
            and 1 <= self.iterations <= 5
            and 1 <= self.threads <= 16
            and 30 <= self.timeout_seconds <= 7200
            and 2 <= self.min_support <= self.neighbors
            and 0 < self.relative_depth_error <= 0.05
            and 0 < self.roundtrip_pixels <= 3
            and 0.1 <= self.min_angle_degrees <= 10
            and 0 < self.min_depth < self.max_depth <= 100
            and 0 < self.voxel_size <= 0.1
            and 1 <= self.sample_stride <= 8,
            "DENSE_POLICY_INVALID",
            "Runtime and consistency bounds",
        )


@dataclass(frozen=True)
class DenseRequest:
    sparse: Path
    prepared: Path
    bundle: Path
    output: Path
    source: Path | None = None
    ranks: tuple[int, ...] | None = None

"""Immutable policy and application request, independent of presentation."""

import math
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PreprocessingPolicy:
    candidate_fps: float = 4.0
    max_gap_seconds: float = 0.75
    translation_m: float = 0.10
    rotation_degrees: float = 10.0
    pose_speed_warning_m_s: float = 3.0
    gyro_warning_rad_s: float = 1.5
    analysis_width: int = 640
    min_matches: int = 20
    min_inlier_ratio: float = 0.35
    max_frames: int = 36000
    max_candidates: int = 2400

    def __post_init__(self):
        for value in vars(self).values():
            if not math.isfinite(value) or value <= 0:
                raise ValueError("Preprocessing limits must be positive and finite")
        if self.candidate_fps > 10 or self.min_inlier_ratio > 1:
            raise ValueError("Candidate rate must be <=10 Hz and inlier ratio <=1")
        for name in ("analysis_width", "min_matches", "max_frames", "max_candidates"):
            if type(getattr(self, name)) is not int:
                raise ValueError(f"{name} must be an integer")


@dataclass(frozen=True)
class PreprocessingRequest:
    bundle: Path
    output: Path
    source_root: Path | None = None

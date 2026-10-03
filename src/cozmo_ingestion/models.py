"""Typed boundaries between source parsing, normalization and publication."""

from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

from .contracts import IngestionPolicy

Record = dict[str, Any]


@dataclass(frozen=True)
class IngestionRequest:
    source: Path
    output: Path
    annotations: Path | None = None


@dataclass
class SourceCapture:
    root: Path
    metadata: Record
    streams: Record
    camera_rows: list[Record]
    camera_comments: list[Record]
    sensor_rows: dict[str, list[Record]]
    sensor_comments: dict[str, list[Record]]

    @property
    def origin(self) -> Decimal:
        return Decimal(self.camera_rows[0]["sensor_sec"])


@dataclass
class VideoInspection:
    stream: Record
    frames: list[Record]
    discarded_packets: list[Record]
    full_decode: str
    probe_command: list[str] = field(default_factory=list)
    decode_command: list[str] = field(default_factory=list)


@dataclass
class CanonicalObservations:
    frames: list[Record]
    calibration: list[Record]
    poses: list[Record]
    sensors: dict[str, list[Record]]
    stream_statistics: Record
    limited_frames: list[int]
    findings: list[Record]


@dataclass
class CameraObservations:
    frames: list[Record]
    calibration: list[Record]
    poses: list[Record]
    limited_frames: list[int]
    findings: list[Record]


@dataclass
class SensorObservations:
    rows: dict[str, list[Record]]
    statistics: Record
    findings: list[Record]


@dataclass(frozen=True)
class BundleContent:
    """Validated content passed to storage, excluding execution-specific details."""

    request: IngestionRequest
    capture: SourceCapture
    observations: CanonicalObservations
    video: VideoInspection
    assets: list[Record]
    source_hashes: dict[str, str]
    association: Record
    annotations: Record
    source_identity: str
    capture_id: str
    adapter_name: str
    stream_headers: dict[str, list[str]]
    policy: IngestionPolicy


@dataclass(frozen=True)
class RunMetadata:
    started: float
    ffmpeg_version: str


@dataclass(frozen=True)
class IngestionResult:
    manifest: Record
    report: Record
    output: Path

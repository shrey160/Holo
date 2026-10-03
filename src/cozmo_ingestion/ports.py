"""Small structural interfaces for replaceable source and video boundaries."""

from pathlib import Path
from typing import Protocol

from .contracts import IngestionPolicy
from .models import SourceCapture, VideoInspection


class CaptureAdapter(Protocol):
    name: str
    stream_headers: dict[str, list[str]]

    def inventory(self, source: Path) -> list[dict]: ...
    def load(self, source: Path, asset_hashes: dict[str, str]) -> SourceCapture: ...
    def associate(
        self, capture: SourceCapture, video: VideoInspection, policy: IngestionPolicy
    ) -> tuple[dict, list[int]]: ...


class VideoInspector(Protocol):
    def inspect(self, video: Path) -> VideoInspection: ...
    def version(self) -> str: ...

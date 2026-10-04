"""Validated content passed to the v2 writer."""

from dataclasses import dataclass, field
from pathlib import Path

from .contracts import MultimodalRequest


@dataclass(frozen=True)
class CaptureBundleContent:
    request: MultimodalRequest
    manifest_base: dict
    rooms_doc: dict
    assets_doc: dict
    observations: list[dict]
    associations: list[dict]
    references_doc: dict
    verification: dict
    copies: tuple[tuple[str, Path], ...]
    calibrations: list[dict] = field(default_factory=list)
    poses: list[dict] = field(default_factory=list)

"""Modality-neutral canonical capture v2 (foundation + photos)."""

from .contracts import (
    MODE_LIDAR,
    MODE_PHOTOS,
    MODE_VIDEO,
    MODES,
    SCHEMA_V2,
    MultimodalRequest,
    ReferenceDeclaration,
    RoomSpec,
)
from .lidar_pipeline import LiDARIngestionPipeline
from .media import DefaultImageInspector, ImageInspection
from .pipeline import PhotosIngestionPipeline
from .reader import MultimodalCaptureReader, open_capture
from .verify import verify_v2

__all__ = [
    "MODE_LIDAR",
    "MODE_PHOTOS",
    "MODE_VIDEO",
    "MODES",
    "SCHEMA_V2",
    "DefaultImageInspector",
    "ImageInspection",
    "LiDARIngestionPipeline",
    "MultimodalCaptureReader",
    "MultimodalRequest",
    "PhotosIngestionPipeline",
    "ReferenceDeclaration",
    "RoomSpec",
    "open_capture",
    "verify_v2",
]

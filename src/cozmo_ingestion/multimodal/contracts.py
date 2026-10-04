"""Immutable modality-neutral contracts for canonical-capture-2."""

from dataclasses import dataclass, field
from pathlib import Path

SCHEMA_V2 = "canonical-capture-2"

MODE_VIDEO = "video"
MODE_PHOTOS = "photos"
MODE_LIDAR = "lidar"
MODES = (MODE_VIDEO, MODE_PHOTOS, MODE_LIDAR)

CAPABILITY_ABSENT = "ABSENT"
CAPABILITY_PRESENT_UNVERIFIED = "PRESENT_UNVERIFIED"
CAPABILITY_VERIFIED_FORMAT = "VERIFIED_FORMAT"
CAPABILITY_USER_DECLARED = "USER_DECLARED"
CAPABILITY_EXCLUDED = "EXCLUDED"
CAPABILITY_VALUES = (
    CAPABILITY_ABSENT,
    CAPABILITY_PRESENT_UNVERIFIED,
    CAPABILITY_VERIFIED_FORMAT,
    CAPABILITY_USER_DECLARED,
    CAPABILITY_EXCLUDED,
)

PHOTO_ADAPTER = "photos-jpeg-png-v1"
PHOTO_SOURCE_FORMAT = "standard-image-folder"
PHOTO_ROLE = "scene_photo"
REFERENCE_ROLE = "reference_photo"
PHOTO_PROFILE_MIN = 2
PHOTO_PROFILE_MAX = 8

# Modalities with a downstream worker today. Everything else must stop honestly.
IMPLEMENTED_CONSUMERS: dict[str, dict[str, str]] = {
    MODE_VIDEO: {"preprocessing": "ios_rgb_arkit_pose", "reconstruction": "fixed_pose_sparse"},
    MODE_PHOTOS: {"preprocessing": "NOT_IMPLEMENTED_FOR_MODALITY"},
    MODE_LIDAR: {"preprocessing": "NOT_IMPLEMENTED_FOR_MODALITY"},
}


@dataclass(frozen=True)
class RoomSpec:
    """A declared property member; folder order never implies physical adjacency."""

    id: str
    label: str
    source_path: str
    declared_connection_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReferenceDeclaration:
    object_id: str
    width_m: float
    height_m: float
    reference_asset: str | None = None
    candidate_assets: tuple[str, ...] = ()
    provenance: str = CAPABILITY_USER_DECLARED


@dataclass(frozen=True)
class MultimodalRequest:
    source: Path
    output: Path
    mode: str
    source_format: str | None = None
    room_label: str | None = None
    reference: Path | None = None
    declared_connections: dict[str, tuple[str, ...]] = field(default_factory=dict)

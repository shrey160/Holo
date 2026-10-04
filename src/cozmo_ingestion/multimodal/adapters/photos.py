"""Per-room still-photo inventory, EXIF evidence and room membership.

Folder order never establishes physical adjacency. Unsupported phone formats fail
admission with an actionable message rather than being silently converted.
"""

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from ...errors import require
from ..contracts import (
    CAPABILITY_USER_DECLARED,
    PHOTO_ADAPTER,
    PHOTO_ROLE,
    PHOTO_SOURCE_FORMAT,
    ReferenceDeclaration,
    RoomSpec,
)
from ..media import KNOWN_IMAGE_SUFFIXES, OTHER_IMAGE_SUFFIXES

_FILENAME_TIME = re.compile(r"^(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})$")
_SLUG = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class DiscoveredPhoto:
    source_path: str
    absolute: Path
    room_id: str
    role: str = PHOTO_ROLE


def slugify(value: str, fallback: str = "room") -> str:
    slug = _SLUG.sub("-", value.casefold()).strip("-")
    return slug or fallback


def filename_timestamp(stem: str):
    match = _FILENAME_TIME.match(stem)
    if not match:
        return None
    year, month, day, hour, minute, second = (int(part) for part in match.groups())
    return f"{year:04d}-{month:02d}-{day:02d}T{hour:02d}:{minute:02d}:{second:02d}"


def _image_files(source: Path) -> tuple[list[Path], list[Path]]:
    known, unsupported = [], []
    for path in sorted(source.rglob("*")):
        if not path.is_file():
            continue
        suffix = path.suffix.casefold()
        if suffix in KNOWN_IMAGE_SUFFIXES:
            known.append(path)
        elif suffix in OTHER_IMAGE_SUFFIXES:
            unsupported.append(path)
    return known, unsupported


def resolve_rooms(
    source: Path,
    room_label: str | None,
    declared_connections: dict[str, tuple[str, ...]] | None = None,
) -> tuple[list[RoomSpec], list[DiscoveredPhoto]]:
    require(source.is_dir(), "SOURCE_NOT_FOUND", str(source))
    known, unsupported = _image_files(source)
    require(
        not unsupported,
        "UNSUPPORTED_IMAGE_FORMAT",
        "Photo tier accepts JPEG/PNG only; export HEIC/HEIF to JPEG first: "
        + ", ".join(path.name for path in unsupported),
    )
    require(known, "SOURCE_HAS_NO_PHOTOS", "No JPEG/PNG images found")
    by_dir: dict[str, list[Path]] = {}
    for path in known:
        by_dir.setdefault(_relative_parent(path, source), []).append(path)
    unique_dirs = sorted(by_dir)
    used_ids: set[str] = set()
    room_by_parent: dict[str, RoomSpec] = {}
    for parent in unique_dirs:
        base = Path(parent).name if parent else source.name
        base = base or "room"
        label = room_label if (room_label and len(unique_dirs) == 1) else base
        room_id = slugify(label)
        index = 2
        while room_id in used_ids:
            room_id = f"{slugify(label)}-{index}"
            index += 1
        used_ids.add(room_id)
        connections = (declared_connections or {}).get(parent, ())
        room_by_parent[parent] = RoomSpec(room_id, label, parent or ".", tuple(connections))
    id_by_parent = {parent: room.id for parent, room in room_by_parent.items()}
    resolved_rooms = [
        RoomSpec(
            room.id,
            room.label,
            room.source_path,
            tuple(
                id_by_parent[target]
                for target in room.declared_connection_ids
                if target in id_by_parent
            ),
        )
        for room in room_by_parent.values()
    ]
    photos = [
        DiscoveredPhoto(
            path.relative_to(source).as_posix(),
            path,
            id_by_parent[_relative_parent(path, source)],
        )
        for path in known
    ]
    return resolved_rooms, photos


def _relative_parent(path: Path, source: Path) -> str:
    relative = path.parent.relative_to(source).as_posix()
    return "" if relative == "." else relative


def parse_reference(path: Path) -> ReferenceDeclaration:
    require(path.is_file(), "REFERENCE_NOT_FOUND", str(path))
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError) as error:
        require(False, "INVALID_REFERENCE", f"Reference JSON is unreadable: {error}")
    require(isinstance(raw, dict), "INVALID_REFERENCE", "Reference JSON must be an object")
    for field in ("object_id", "width_m", "height_m"):
        require(field in raw, "INVALID_REFERENCE", f"Reference is missing {field}")
    width = float(raw["width_m"])
    height = float(raw["height_m"])
    require(
        width > 0 and height > 0,
        "INVALID_REFERENCE",
        "Reference dimensions must be positive",
    )
    reference_asset = raw.get("reference_asset")
    candidates = tuple(raw.get("candidate_assets", ()))
    return ReferenceDeclaration(
        str(raw["object_id"]),
        width,
        height,
        str(reference_asset) if reference_asset else None,
        candidates,
        str(raw.get("provenance", CAPABILITY_USER_DECLARED)),
    )


def content_identity(records: list[dict]) -> str:
    payload = json.dumps(sorted(records, key=lambda item: item["source_path"]), sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


ADAPTER = PHOTO_ADAPTER
SOURCE_FORMAT = PHOTO_SOURCE_FORMAT

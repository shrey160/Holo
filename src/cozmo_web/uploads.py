"""Cross-platform archive names and bounded, byte-preserving capture extraction."""

import json
import shutil
import stat
import zipfile
from pathlib import Path, PurePosixPath

from cozmo_ingestion.adapters.selection import select_adapter
from cozmo_ingestion.errors import IngestionError
from cozmo_ingestion.multimodal.media import KNOWN_IMAGE_SUFFIXES, OTHER_IMAGE_SUFFIXES

from .config import Settings
from .errors import WebError

RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def safe_name(name: str) -> PurePosixPath:
    normalized = name.replace("\\", "/")
    path = PurePosixPath(normalized)
    pieces = normalized.rstrip("/").split("/")
    if (
        path.is_absolute()
        or not pieces
        or any(
            not part
            or part in {".", ".."}
            or part.endswith((".", " "))
            or any(ord(c) < 32 or c in ':<>"|?*' for c in part)
            or part.split(".")[0].upper() in RESERVED
            for part in pieces
        )
    ):
        raise WebError("UNSAFE_FILENAME", "Export contains an unsafe file path")
    return path


def unpack_archive(archive: Path, destination: Path, settings: Settings):
    try:
        with zipfile.ZipFile(archive) as zipped:
            members = zipped.infolist()
            if len(members) > settings.member_limit:
                raise WebError("TOO_MANY_FILES", "Export contains too many archive entries")
            expected = sum(member.file_size for member in members if not member.is_dir())
            if expected > settings.expanded_limit:
                raise WebError("CAPTURE_TOO_LARGE", "Expanded capture exceeds the limit", 413)
            if shutil.disk_usage(destination.parent).free < expected + 10 * 1024**2:
                raise WebError("STORAGE_FULL", "Not enough storage to extract this capture", 507)
            seen, prefixes, total = set(), {}, 0
            for member in members:
                relative = safe_name(member.filename)
                key = relative.as_posix().casefold()
                for index in range(1, len(relative.parts) + 1):
                    prefix = "/".join(relative.parts[:index])
                    folded = prefix.casefold()
                    if folded in prefixes and prefixes[folded] != prefix:
                        raise WebError("UNSAFE_ARCHIVE", "Archive paths collide across platforms")
                    prefixes[folded] = prefix
                mode = member.external_attr >> 16
                if key in seen or stat.S_ISLNK(mode) or member.flag_bits & 1:
                    raise WebError("UNSAFE_ARCHIVE", "Duplicate, linked or encrypted ZIP entry")
                seen.add(key)
                if member.is_dir():
                    continue
                if member.file_size > settings.expanded_limit:
                    raise WebError("CAPTURE_TOO_LARGE", "Expanded capture exceeds the limit", 413)
                target = destination / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                with zipped.open(member) as source, target.open("xb") as output:
                    while chunk := source.read(1024 * 1024):
                        total += len(chunk)
                        if total > settings.expanded_limit:
                            raise WebError(
                                "CAPTURE_TOO_LARGE", "Expanded capture exceeds the limit", 413
                            )
                        output.write(chunk)
    except (zipfile.BadZipFile, RuntimeError, FileExistsError) as error:
        raise WebError("INVALID_ARCHIVE", "ZIP is corrupt or has conflicting entries") from error


def _photo_files(root: Path) -> tuple[list[Path], list[Path]]:
    known, unsupported = [], []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        suffix = path.suffix.casefold()
        if suffix in KNOWN_IMAGE_SUFFIXES:
            known.append(path)
        elif suffix in OTHER_IMAGE_SUFFIXES:
            unsupported.append(path)
    return known, unsupported


def _has_photo(directory: Path) -> bool:
    return any(
        path.is_file() and path.suffix.casefold() in KNOWN_IMAGE_SUFFIXES
        for path in directory.rglob("*")
    )


def prepare_photos(folder: Path, settings: Settings) -> Path:
    """Admit a single room folder, per-room folders or a ZIP preserving that layout."""
    incoming = folder / "incoming"
    files = list(incoming.iterdir())
    raw = folder / "raw"
    if len(files) == 1 and files[0].suffix.lower() == ".zip":
        extracted = folder / "extracted"
        extracted.mkdir()
        unpack_archive(files[0], extracted, settings)
        top_files = [path for path in extracted.iterdir() if path.is_file()]
        directories = [path for path in extracted.iterdir() if path.is_dir()]
        source = extracted
        if not top_files and len(directories) == 1 and _has_photo(directories[0]):
            source = directories[0]
        if source != extracted:
            outside = [
                path
                for path in extracted.rglob("*")
                if path.is_file() and not path.is_relative_to(source)
            ]
            if outside:
                raise WebError("AMBIGUOUS_CAPTURE", "ZIP contains files outside the photo set")
            source.rename(raw)
            shutil.rmtree(extracted, ignore_errors=True)
        else:
            extracted.rename(raw)
    else:
        incoming.rename(raw)
    known, unsupported = _photo_files(raw)
    if unsupported:
        raise WebError(
            "UNSUPPORTED_IMAGE_FORMAT",
            "Photo tier accepts JPEG/PNG only; export HEIC/HEIF to JPEG first",
        )
    if not known:
        raise WebError("INVALID_INPUT", "No JPEG/PNG photos found in the selection")
    if (
        sum(path.stat().st_size for path in raw.rglob("*") if path.is_file())
        > settings.expanded_limit
    ):
        raise WebError("CAPTURE_TOO_LARGE", "Photo set exceeds the expanded limit", 413)
    shutil.rmtree(incoming, ignore_errors=True)
    return raw


def prepare_capture(folder: Path, settings: Settings) -> Path:
    incoming = folder / "incoming"
    files = list(incoming.iterdir())
    raw = folder / "raw"
    if len(files) == 1 and files[0].suffix.lower() == ".zip":
        extracted = folder / "extracted"
        extracted.mkdir()
        unpack_archive(files[0], extracted, settings)
        roots = {path.parent for path in extracted.rglob("meta.json")}
        roots.update(path.parent for path in extracted.rglob("rgb.mp4"))
        if len(roots) != 1:
            raise WebError("AMBIGUOUS_CAPTURE", "ZIP must contain exactly one exported session")
        source = next(iter(roots))
        # Allow only one containing directory; do not silently discard unrelated payloads.
        outside = [p for p in extracted.rglob("*") if p.is_file() and not p.is_relative_to(source)]
        if outside:
            raise WebError("AMBIGUOUS_CAPTURE", "ZIP contains files outside its session directory")
        source.rename(raw)
    else:
        incoming.rename(raw)
    try:
        adapter = select_adapter(raw)
    except IngestionError as error:
        raise WebError(
            "INCOMPLETE_EXPORT", "Select one complete Sensor Recorder or Stray-style export"
        ) from error
    if adapter.name != "stray-layout-supplied-v1":
        if not (raw / "wide.mp4").is_file():
            raise WebError("INCOMPLETE_EXPORT", "Sensor Recorder export requires wide.mp4")
        try:
            metadata = json.loads((raw / "meta.json").read_text(encoding="utf-8"))
        except (ValueError, UnicodeError) as error:
            raise WebError("INVALID_METADATA", "meta.json is not valid UTF-8 JSON") from error
        if not isinstance(metadata, dict):
            raise WebError("INVALID_METADATA", "meta.json must contain an object")
    total = sum(p.stat().st_size for p in raw.rglob("*") if p.is_file())
    if total > settings.expanded_limit:
        raise WebError("CAPTURE_TOO_LARGE", "Capture exceeds the expanded limit", 413)
    shutil.rmtree(incoming, ignore_errors=True)
    return raw

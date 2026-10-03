"""Cross-platform archive names and bounded, byte-preserving capture extraction."""

import json
import shutil
import stat
import zipfile
from pathlib import Path, PurePosixPath

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


def prepare_capture(folder: Path, settings: Settings) -> Path:
    incoming = folder / "incoming"
    files = list(incoming.iterdir())
    raw = folder / "raw"
    if len(files) == 1 and files[0].suffix.lower() == ".zip":
        extracted = folder / "extracted"
        extracted.mkdir()
        unpack_archive(files[0], extracted, settings)
        roots = list(extracted.rglob("meta.json"))
        if len(roots) != 1:
            raise WebError("AMBIGUOUS_CAPTURE", "ZIP must contain exactly one exported session")
        source = roots[0].parent
        # Allow only one containing directory; do not silently discard unrelated payloads.
        outside = [p for p in extracted.rglob("*") if p.is_file() and not p.is_relative_to(source)]
        if outside:
            raise WebError("AMBIGUOUS_CAPTURE", "ZIP contains files outside its session directory")
        source.rename(raw)
    else:
        incoming.rename(raw)
    if not (raw / "meta.json").is_file() or not (raw / "wide.mp4").is_file():
        raise WebError(
            "INCOMPLETE_EXPORT", "Select the complete export including meta.json and wide.mp4"
        )
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

"""Optional reference photos, separate from immutable capture observations."""

import json
import subprocess
from pathlib import Path

from cozmo_ingestion.media import find_ffmpeg
from cozmo_ingestion.storage import sha256, write_json

from .config import Settings
from .errors import WebError
from .uploads import safe_name

MAX_IMAGE_BYTES = 10 * 1024**2
MAX_IMAGE_PIXELS = 40_000_000
FORMATS = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}


async def save_reference_image(upload, folder: Path) -> dict:
    name = safe_name(upload.filename or "")
    if len(name.parts) != 1 or name.suffix.lower() not in FORMATS:
        raise WebError("INVALID_REFERENCE_IMAGE", "Choose a JPEG or PNG object photo")
    suffix = ".png" if name.suffix.lower() == ".png" else ".jpg"
    root = folder / "reference"
    root.mkdir()
    path = root / ("object" + suffix)
    size, header = 0, b""
    with path.open("xb") as output:
        while chunk := await upload.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_IMAGE_BYTES:
                raise WebError(
                    "REFERENCE_IMAGE_TOO_LARGE", "Object photo must be at most 10 MiB", 413
                )
            if not header:
                header = chunk[:8]
            output.write(chunk)
    valid = (
        header.startswith(b"\x89PNG\r\n\x1a\n")
        if suffix == ".png"
        else header.startswith(b"\xff\xd8\xff")
    )
    if not valid:
        raise WebError("INVALID_REFERENCE_IMAGE", "The file must contain a JPEG or PNG image")
    return {
        "filename": path.name,
        "original_name": name.name,
        "media_type": FORMATS[suffix],
        "size_bytes": size,
        "sha256": sha256(path),
    }


def bind_reference_image(folder: Path, video_hash: str, settings: Settings) -> dict | None:
    job = json.loads((folder / "job.json").read_text(encoding="utf-8"))
    image = job.get("reference_image")
    if not image:
        return None
    path = folder / "reference" / image["filename"]
    if path.is_symlink() or sha256(path) != image["sha256"]:
        raise WebError("REFERENCE_IMAGE_CHANGED", "Object photo changed before validation")
    ffmpeg, ffprobe = find_ffmpeg(settings.ffmpeg)
    try:
        probe = subprocess.run(
            [
                str(ffprobe),
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=codec_name,width,height",
                "-of",
                "json",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
        streams = json.loads(probe.stdout)["streams"]
        stream = streams[0]
        width, height = int(stream["width"]), int(stream["height"])
        expected = "png" if image["media_type"] == "image/png" else "mjpeg"
        if (
            len(streams) != 1
            or stream["codec_name"] != expected
            or not (0 < width * height <= MAX_IMAGE_PIXELS and width > 0 and height > 0)
        ):
            raise ValueError("Unsupported image grid or encoding")
        decode = subprocess.run(
            [
                str(ffmpeg),
                "-v",
                "error",
                "-xerror",
                "-nostdin",
                "-threads",
                "2",
                "-i",
                str(path),
                "-frames:v",
                "1",
                "-f",
                "null",
                "-",
            ],
            capture_output=True,
            timeout=10,
            check=True,
        )
        if probe.stderr.strip() or decode.stderr.strip():
            raise ValueError("Image could not decode cleanly")
    except (subprocess.SubprocessError, ValueError, KeyError, IndexError) as error:
        raise WebError(
            "INVALID_REFERENCE_IMAGE",
            "Object photo must decode as JPEG/PNG with at most 40 million pixels",
        ) from error
    if sha256(path) != image["sha256"]:
        raise WebError("REFERENCE_IMAGE_CHANGED", "Object photo changed during validation")
    image = {**image, "width": width, "height": height, "source_video_sha256": video_hash}
    metadata = folder / "reference" / "metadata.json"
    write_json(
        metadata,
        {
            "schema_version": 1,
            "image": image,
            "usage": "user-supplied opening object photo; detection and scale estimation NOT_RUN",
        },
    )
    return {**image, "metadata_sha256": sha256(metadata)}


def read_reference_image(folder: Path) -> tuple[Path, dict] | None:
    job_path = folder / "job.json"
    job = json.loads(job_path.read_text(encoding="utf-8")) if job_path.is_file() else {}
    image = job.get("reference_image")
    root = folder / "reference"
    if not image:
        if root.exists():
            raise WebError(
                "REFERENCE_IMAGE_CHANGED", "Untracked object photo in capture storage", 409
            )
        return None
    if image.get("filename") not in {"object.jpg", "object.png"}:
        raise WebError("REFERENCE_IMAGE_CHANGED", "Stored object photo is invalid", 409)
    path, metadata = root / image["filename"], root / "metadata.json"
    expected = {image["filename"], "metadata.json"}
    if (
        root.is_symlink()
        or not root.is_dir()
        or {p.name for p in root.iterdir()} != expected
        or any(p.is_symlink() or not p.is_file() for p in (path, metadata))
        or sha256(path) != image["sha256"]
        or sha256(metadata) != image.get("metadata_sha256")
        or sha256(folder / "raw/wide.mp4") != image["source_video_sha256"]
    ):
        raise WebError(
            "REFERENCE_IMAGE_CHANGED", "Stored object photo failed integrity verification", 409
        )
    return path, image

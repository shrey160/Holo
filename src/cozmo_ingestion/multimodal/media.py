"""Image media boundary: content-based JPEG/PNG detection, structural decode and EXIF.

No third-party codec is required. JPEG/PNG identity is decided from magic bytes, not
file extensions. PNG payloads are fully inflated with the standard library; JPEG is
parsed segment-by-segment through EOI. When Pillow is importable an additional full
pixel decode is attempted, but its absence never silently downgrades a failure.
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Protocol

from ..errors import require

JPEG_SUFFIXES = {".jpg", ".jpeg"}
PNG_SUFFIXES = {".png"}
KNOWN_IMAGE_SUFFIXES = JPEG_SUFFIXES | PNG_SUFFIXES
OTHER_IMAGE_SUFFIXES = {".heic", ".heif", ".webp", ".tif", ".tiff", ".bmp", ".gif", ".avif"}

_SOF_MARKERS = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
_STANDALONE_MARKERS = {0x01, *range(0xD0, 0xD8)}


@dataclass(frozen=True)
class ImageInspection:
    media_format: str
    width: int
    height: int
    decode: str
    exif: dict = field(default_factory=dict)
    orientation: int | None = None

    @property
    def capped_dimensions(self) -> tuple[int, int]:
        return self.width, self.height


class ImageInspector(Protocol):
    def inspect(self, path: Path) -> ImageInspection: ...


def _u16(data: bytes, offset: int, endian: str) -> int:
    require(offset + 2 <= len(data), "INVALID_EXIF", "Truncated EXIF short")
    return struct.unpack_from(endian + "H", data, offset)[0]


def _u32(data: bytes, offset: int, endian: str) -> int:
    require(offset + 4 <= len(data), "INVALID_EXIF", "Truncated EXIF long")
    return struct.unpack_from(endian + "I", data, offset)[0]


_TIFF_TYPE_SIZE = {
    1: 1,
    2: 1,
    3: 2,
    4: 4,
    5: 8,
    6: 1,
    7: 1,
    8: 2,
    9: 4,
    10: 8,
    11: 4,
    12: 8,
}


def _decode_value(data: bytes, type_id: int, count: int, value_offset: int, endian: str):
    size = _TIFF_TYPE_SIZE.get(type_id)
    require(size is not None, "INVALID_EXIF", f"Unknown EXIF type {type_id}")
    total = size * count
    if total <= 4:
        raw = data[value_offset : value_offset + total]
    else:
        pointer = _u32(data, value_offset, endian)
        require(pointer + total <= len(data), "INVALID_EXIF", "EXIF value outside segment")
        raw = data[pointer : pointer + total]
    require(len(raw) == total, "INVALID_EXIF", "Truncated EXIF value")
    if type_id == 2:
        return raw.split(b"\x00", 1)[0].decode("ascii", "replace")
    if type_id in (1, 7, 6):
        values = list(raw)
    elif type_id == 3:
        values = list(struct.unpack(endian + f"{count}H", raw))
    elif type_id == 4:
        values = list(struct.unpack(endian + f"{count}I", raw))
    elif type_id == 9:
        values = list(struct.unpack(endian + f"{count}i", raw))
    elif type_id in (5, 10):
        prefix = endian + ("I" if type_id == 5 else "i")
        values = []
        for index in range(count):
            numerator = struct.unpack_from(prefix, raw, index * 8)[0]
            denominator = struct.unpack_from(prefix, raw, index * 8 + 4)[0]
            values.append((numerator, denominator))
    else:  # 8, 11, 12
        fmt = {8: "h", 11: "f", 12: "d"}[type_id]
        values = list(struct.unpack(endian + f"{count}{fmt}", raw))
    return values[0] if count == 1 else values


def _read_ifd(data: bytes, offset: int, endian: str, tags: dict, depth: int = 0) -> None:
    require(depth <= 4, "INVALID_EXIF", "Nested EXIF IFD depth exceeded")
    require(offset + 2 <= len(data), "INVALID_EXIF", "Truncated IFD")
    count = _u16(data, offset, endian)
    for index in range(count):
        entry = offset + 2 + index * 12
        require(entry + 12 <= len(data), "INVALID_EXIF", "Truncated IFD entry")
        tag = _u16(data, entry, endian)
        type_id = _u16(data, entry + 2, endian)
        item_count = _u32(data, entry + 4, endian)
        if tag == 0x8769 and type_id == 4 and item_count == 1:
            _read_ifd(data, _u32(data, entry + 8, endian), endian, tags, depth + 1)
            continue
        if tag in {0x8825, 0xA005}:
            continue
        tags[tag] = _decode_value(data, type_id, item_count, entry + 8, endian)
    # Some encoders place DateTimeOriginal in IFD0; already captured by tag number.


def parse_exif(payload: bytes) -> dict:
    """Parse a raw Exif TIFF payload (without the 'Exif\\x00\\x00' prefix)."""
    require(len(payload) >= 8, "INVALID_EXIF", "Exif payload too small")
    endian = {"II": "<", "MM": ">"}.get(payload[:2].decode("ascii", "replace"))
    require(endian is not None, "INVALID_EXIF", f"Unknown TIFF byte order {payload[:2]!r}")
    require(_u16(payload, 2, endian) == 42, "INVALID_EXIF", "Missing TIFF magic 42")
    tags: dict = {}
    _read_ifd(payload, _u32(payload, 4, endian), endian, tags)
    return _normalize_exif(tags)


def _rational(value) -> float | None:
    if isinstance(value, tuple) and len(value) == 2:
        denominator = value[1]
        if denominator == 0:
            return None
        return value[0] / denominator
    return None


def _normalize_exif(tags: dict) -> dict:
    exif: dict = {}
    if 0x010F in tags:
        exif["make"] = tags[0x010F]
    if 0x0110 in tags:
        exif["model"] = tags[0x0110]
    if 0x0112 in tags:
        exif["orientation"] = int(tags[0x0112])
    if 0x0132 in tags:
        exif["datetime"] = tags[0x0132]
    if 0x9003 in tags:
        exif["datetime_original"] = tags[0x9003]
    if 0x9011 in tags:
        exif["offset_time_original"] = tags[0x9011]
    focal = _rational(tags.get(0x920A))
    if focal is not None:
        exif["focal_length_mm"] = focal
    if 0xA405 in tags:
        exif["focal_length_35mm_mm"] = int(tags[0xA405])
    if 0xA002 in tags:
        exif["pixel_x"] = int(tags[0xA002])
    if 0xA003 in tags:
        exif["pixel_y"] = int(tags[0xA003])
    if "datetime_original" in exif or "datetime" in exif:
        exif["timestamp"] = _exif_timestamp(exif)
    return exif


def _exif_timestamp(exif: dict) -> dict:
    raw = exif.get("datetime_original") or exif.get("datetime")
    source = "EXIF_DateTimeOriginal" if exif.get("datetime_original") else "EXIF_DateTime"
    parsed = None
    for pattern in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            parsed = datetime.strptime(raw, pattern)
            break
        except (TypeError, ValueError):
            continue
    if parsed is None:
        return {"value": None, "timezone": None, "source": source, "domain": "unknown"}
    offset = exif.get("offset_time_original")
    if isinstance(offset, str) and _valid_offset(offset):
        return {
            "value": parsed.strftime("%Y-%m-%dT%H:%M:%S") + offset,
            "timezone": offset,
            "source": source,
            "domain": "local_clock",
        }
    return {
        "value": parsed.strftime("%Y-%m-%dT%H:%M:%S"),
        "timezone": None,
        "source": source,
        "domain": "local_clock_unknown_offset",
    }


def _valid_offset(value: str) -> bool:
    return (
        len(value) == 6
        and value[0] in "+-"
        and value[1:3].isdigit()
        and value[3] == ":"
        and value[4:6].isdigit()
    )


def inspect_jpeg(data: bytes) -> dict:
    require(data[:2] == b"\xff\xd8", "UNSUPPORTED_IMAGE", "Not a JPEG stream")
    index = 2
    width = height = None
    exif_payload = None
    reached_eoi = False
    while index + 1 < len(data):
        require(data[index] == 0xFF, "CORRUPT_IMAGE", "JPEG marker expected")
        while index < len(data) and data[index] == 0xFF:
            index += 1
        marker = data[index]
        index += 1
        if marker == 0xD9:
            reached_eoi = True
            break
        if marker in _STANDALONE_MARKERS:
            continue
        require(index + 2 <= len(data), "CORRUPT_IMAGE", "Truncated JPEG segment length")
        length = int.from_bytes(data[index : index + 2], "big")
        require(length >= 2 and index + length <= len(data), "CORRUPT_IMAGE", "Bad JPEG length")
        segment = data[index + 2 : index + length]
        if marker == 0xE1 and segment[:6] == b"Exif\x00\x00":
            exif_payload = segment[6:]
        elif marker in _SOF_MARKERS:
            require(len(segment) >= 5, "CORRUPT_IMAGE", "Truncated JPEG frame header")
            height = int.from_bytes(segment[1:3], "big")
            width = int.from_bytes(segment[3:5], "big")
        index += length
        if marker == 0xDA:  # entropy-coded data: find the next EOI
            end = data.find(b"\xff\xd9", index)
            require(end != -1, "CORRUPT_IMAGE", "JPEG missing EOI")
            reached_eoi = True
            break
    require(width and height, "CORRUPT_IMAGE", "JPEG frame dimensions missing")
    require(reached_eoi, "CORRUPT_IMAGE", "JPEG did not terminate")
    return {"width": width, "height": height, "exif_payload": exif_payload}


def _png_chunk(data: bytes, offset: int) -> tuple[str, bytes, int]:
    require(offset + 12 <= len(data), "CORRUPT_IMAGE", "Truncated PNG chunk")
    length = int.from_bytes(data[offset : offset + 4], "big")
    kind = data[offset + 4 : offset + 8]
    body = data[offset + 8 : offset + 8 + length]
    require(len(body) == length, "CORRUPT_IMAGE", "Truncated PNG payload")
    crc = int.from_bytes(data[offset + 8 + length : offset + 12 + length], "big")
    require(zlib.crc32(kind + body) & 0xFFFFFFFF == crc, "CORRUPT_IMAGE", "PNG CRC mismatch")
    return kind.decode("ascii", "replace"), body, offset + 12 + length


def inspect_png(data: bytes) -> dict:
    require(data[:8] == b"\x89PNG\r\n\x1a\n", "UNSUPPORTED_IMAGE", "Not a PNG stream")
    offset = 8
    width = height = None
    exif_payload = None
    idat = bytearray()
    header = None
    seen_iend = False
    while offset < len(data):
        kind, body, offset = _png_chunk(data, offset)
        if kind == "IHDR":
            require(len(body) == 13, "CORRUPT_IMAGE", "Bad IHDR length")
            width = int.from_bytes(body[0:4], "big")
            height = int.from_bytes(body[4:8], "big")
            header = body
        elif kind == "IDAT":
            idat.extend(body)
        elif kind == "eXIf":
            exif_payload = body
        elif kind == "IEND":
            seen_iend = True
            break
    require(width and height and header is not None, "CORRUPT_IMAGE", "PNG missing IHDR")
    require(seen_iend, "CORRUPT_IMAGE", "PNG missing IEND")
    _validate_png_scanlines(header, bytes(idat), width, height)
    return {"width": width, "height": height, "exif_payload": exif_payload}


def _validate_png_scanlines(header: bytes, idat: bytes, width: int, height: int) -> None:
    bit_depth, color_type, _, _, interlace = (
        header[8],
        header[9],
        header[10],
        header[11],
        header[12],
    )
    require(interlace == 0, "UNSUPPORTED_IMAGE", "Interlaced PNG is not admitted")
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(color_type)
    require(channels is not None, "CORRUPT_IMAGE", "Unknown PNG color type")
    try:
        raw = zlib.decompress(idat)
    except zlib.error:
        require(False, "CORRUPT_IMAGE", "PNG inflate failed")
        return
    stride = (width * channels * bit_depth + 7) // 8
    require(len(raw) == height * (stride + 1), "CORRUPT_IMAGE", "PNG scanline size mismatch")


class DefaultImageInspector:
    """Content-detected inspector; Pillow is used for pixel decode only when available."""

    def inspect(self, path: Path) -> ImageInspection:
        data = path.read_bytes()
        if data[:2] == b"\xff\xd8":
            parsed = inspect_jpeg(data)
            media_format = "jpeg"
        elif data[:8] == b"\x89PNG\r\n\x1a\n":
            parsed = inspect_png(data)
            media_format = "png"
        else:
            require(False, "UNSUPPORTED_IMAGE", f"Unsupported image content: {path.name}")
            return ImageInspection("unknown", 0, 0, "FAILED")
        exif = parse_exif(parsed["exif_payload"]) if parsed["exif_payload"] else {}
        decode = "STRUCTURE_VERIFIED"
        if self._pillow_available():
            self._pillow_decode(path)
            decode = "FULL_DECODE"
        return ImageInspection(
            media_format,
            int(parsed["width"]),
            int(parsed["height"]),
            decode,
            exif,
            exif.get("orientation"),
        )

    @staticmethod
    def _pillow_available() -> bool:
        try:
            import PIL.Image  # noqa: F401
        except Exception:
            return False
        return True

    @staticmethod
    def _pillow_decode(path: Path) -> None:
        from PIL import Image

        with Image.open(path) as image:
            image.load()

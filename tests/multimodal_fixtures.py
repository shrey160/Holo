"""Synthetic JPEG/PNG and EXIF builders for the v2 ingestion tests."""

import struct
import zlib

_TIFF_SIZE = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 7: 1, 9: 4, 10: 8}


def _segment(marker: int, payload: bytes) -> bytes:
    return bytes([0xFF, marker]) + struct.pack(">H", len(payload) + 2) + payload


def build_tiff(
    orientation: int = 1,
    make: str = "samsung",
    model: str = "Galaxy S24",
    datetime_original: str = "2026:10:04 12:41:56",
    offset: str = "+05:30",
    focal: tuple[int, int] = (54, 10),
    focal_35mm: int = 23,
) -> bytes:
    """Little-endian Exif TIFF with the tags the photo inspector reads."""
    endian = "<"
    extra = bytearray()

    def ascii_bytes(text: str) -> tuple[bytes, int]:
        return text.encode("ascii") + b"\x00", len(text) + 1

    def emit(tag: int, type_id: int, count: int, value: bytes, data_base: int) -> bytes:
        total = _TIFF_SIZE[type_id] * count
        if total <= 4:
            return struct.pack(endian + "HHI", tag, type_id, count) + value + b"\x00" * (4 - total)
        offset = data_base + len(extra)
        extra.extend(value)
        return struct.pack(endian + "HHI", tag, type_id, count) + struct.pack(endian + "I", offset)

    make_b, make_c = ascii_bytes(make)
    model_b, model_c = ascii_bytes(model)
    dt_b, dt_c = ascii_bytes(datetime_original)
    offset_b, offset_c = ascii_bytes(offset)
    n0, n1 = 4, 4
    ifd0_offset = 8
    ifd0_size = 2 + 12 * n0 + 4
    exif_offset = ifd0_offset + ifd0_size
    exif_size = 2 + 12 * n1 + 4
    data_base = exif_offset + exif_size

    ifd0 = struct.pack(endian + "H", n0)
    ifd0 += emit(0x010F, 2, make_c, make_b, data_base)
    ifd0 += emit(0x0110, 2, model_c, model_b, data_base)
    ifd0 += emit(0x0112, 3, 1, struct.pack(endian + "H", orientation), data_base)
    ifd0 += emit(0x8769, 4, 1, struct.pack(endian + "I", exif_offset), data_base)
    ifd0 += struct.pack(endian + "I", 0)

    ifd1 = struct.pack(endian + "H", n1)
    ifd1 += emit(0x9003, 2, dt_c, dt_b, data_base)
    ifd1 += emit(0x9011, 2, offset_c, offset_b, data_base)
    ifd1 += emit(0x920A, 5, 1, struct.pack(endian + "II", focal[0], focal[1]), data_base)
    ifd1 += emit(0xA405, 3, 1, struct.pack(endian + "H", focal_35mm), data_base)
    ifd1 += struct.pack(endian + "I", 0)

    return (
        b"II"
        + struct.pack(endian + "H", 42)
        + struct.pack(endian + "I", ifd0_offset)
        + ifd0
        + ifd1
        + bytes(extra)
    )


def jpeg_bytes(width: int = 4000, height: int = 3000, tiff: bytes | None = None) -> bytes:
    out = b"\xff\xd8"
    out += _segment(0xE0, b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00")
    if tiff is not None:
        out += _segment(0xE1, b"Exif\x00\x00" + tiff)
    sof = (
        bytes([8])
        + struct.pack(">HH", height, width)
        + bytes([3])
        + b"\x01\x11\x00\x02\x11\x01\x03\x11\x01"
    )
    out += _segment(0xC0, sof)
    sos = bytes([3]) + b"\x01\x00\x02\x00\x03\x00" + bytes([0, 63, 0])
    out += _segment(0xDA, sos) + b"\x00" + b"\xff\xd9"
    return out


def _chunk(kind: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + kind
        + data
        + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    )


def png_bytes(width: int = 4, height: int = 3, color: tuple[int, int, int] = (10, 20, 30)) -> bytes:
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    raw = b"".join(b"\x00" + bytes(color) * width for _ in range(height))
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", zlib.compress(raw))
        + _chunk(b"IEND", b"")
    )


def gray_png_bytes(width, height, bit_depth, values=None, fill=0):
    ihdr = struct.pack(">IIBBBBB", width, height, bit_depth, 0, 0, 0, 0)
    bpp = 2 if bit_depth == 16 else 1
    raw = bytearray()
    for y in range(height):
        raw.append(0)
        for x in range(width):
            value = values(x, y) if callable(values) else fill
            if bpp == 2:
                raw += bytes([(value >> 8) & 0xFF, value & 0xFF])
            else:
                raw.append(value & 0xFF)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", zlib.compress(bytes(raw)))
        + _chunk(b"IEND", b"")
    )


ODOMETRY_HEADER = [
    "timestamp",
    "frame",
    "x",
    "y",
    "z",
    "qx",
    "qy",
    "qz",
    "qw",
    "fx",
    "fy",
    "cx",
    "cy",
    "distortion_center_x",
    "distortion_center_y",
]
IMU_HEADER = ["timestamp", "a_x", "a_y", "a_z", "alpha_x", "alpha_y", "alpha_z"]


def stray_lidar_fixture(
    root,
    frames=3,
    width=4,
    height=3,
    confidence=True,
    depth_bit=16,
    depth_value=None,
):
    """Build a minimal Stray-style raw-depth export for tests."""
    import csv as _csv

    root.mkdir(parents=True, exist_ok=True)
    (root / "rgb.mp4").write_bytes(b"fake rgb")
    odometry = []
    for index in range(frames):
        odometry.append(
            {
                "timestamp": f"{1000 + index}",
                "frame": str(index),
                "x": str(0.1 * index),
                "y": "0.0",
                "z": str(0.2 * index),
                "qx": "0",
                "qy": "0",
                "qz": "0",
                "qw": "1",
                "fx": "100",
                "fy": "100",
                "cx": str(width / 2),
                "cy": str(height / 2),
                "distortion_center_x": "",
                "distortion_center_y": "",
            }
        )
    with (root / "odometry.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = _csv.DictWriter(stream, fieldnames=ODOMETRY_HEADER, lineterminator="\n")
        writer.writeheader()
        writer.writerows(odometry)
    last = odometry[-1]
    with (root / "camera_matrix.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = _csv.writer(stream, lineterminator="\n")
        writer.writerow([last["fx"], 0, last["cx"]])
        writer.writerow([0, last["fy"], last["cy"]])
        writer.writerow([0, 0, 1])
    with (root / "imu.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = _csv.DictWriter(stream, fieldnames=IMU_HEADER, lineterminator="\n")
        writer.writeheader()
        writer.writerow(
            {
                "timestamp": "1000",
                "a_x": "0",
                "a_y": "0",
                "a_z": "9.8",
                "alpha_x": "0",
                "alpha_y": "0",
                "alpha_z": "0",
            }
        )

    def depth(x, y, index):
        if depth_value is not None:
            return depth_value(x, y, index)
        return 1000 + index * 10 + x + y

    (root / "depth").mkdir()
    for index in range(frames):
        (root / "depth" / f"{index:06d}.png").write_bytes(
            gray_png_bytes(width, height, depth_bit, values=lambda x, y, i=index: depth(x, y, i))
        )
    if confidence:
        (root / "confidence").mkdir()
        for index in range(frames):
            (root / "confidence" / f"{index:06d}.png").write_bytes(
                gray_png_bytes(width, height, 8, values=lambda x, y: (x + y) % 3)
            )
    return root


def write_room(root, name, images: dict[str, bytes]):
    room = root / name if name else root
    room.mkdir(parents=True, exist_ok=True)
    for filename, payload in images.items():
        (room / filename).write_bytes(payload)
    return room

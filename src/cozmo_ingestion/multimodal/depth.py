"""Bounded grayscale-PNG decoding for raw-depth admission.

Only grayscale PNG (8- or 16-bit) is decoded, one image at a time. Values are
returned for statistics/validity checks; no pixel map is retained across frames.
"""

import zlib

from ..errors import require


def _chunks(data: bytes):
    require(data[:8] == b"\x89PNG\r\n\x1a\n", "UNSUPPORTED_IMAGE", "Not a PNG stream")
    offset = 8
    while offset < len(data):
        require(offset + 12 <= len(data), "CORRUPT_IMAGE", "Truncated PNG chunk")
        length = int.from_bytes(data[offset : offset + 4], "big")
        kind = data[offset + 4 : offset + 8]
        body = data[offset + 8 : offset + 8 + length]
        require(len(body) == length, "CORRUPT_IMAGE", "Truncated PNG payload")
        crc = int.from_bytes(data[offset + 8 + length : offset + 12 + length], "big")
        require(zlib.crc32(kind + body) & 0xFFFFFFFF == crc, "CORRUPT_IMAGE", "PNG CRC mismatch")
        yield kind, body
        offset += 12 + length


def png_gray_header(data: bytes) -> dict:
    width = height = bit_depth = color_type = None
    idat = bytearray()
    for kind, body in _chunks(data):
        if kind == b"IHDR":
            require(len(body) == 13, "CORRUPT_IMAGE", "Bad IHDR length")
            width = int.from_bytes(body[0:4], "big")
            height = int.from_bytes(body[4:8], "big")
            bit_depth, color_type = body[8], body[9]
        elif kind == b"IDAT":
            idat.extend(body)
        elif kind == b"IEND":
            break
    require(width and height, "CORRUPT_IMAGE", "PNG missing IHDR")
    require(color_type == 0, "CORRUPT_IMAGE", "Depth/confidence PNG must be grayscale")
    require(bit_depth in (8, 16), "CORRUPT_IMAGE", "Unsupported grayscale bit depth")
    return {
        "width": width,
        "height": height,
        "bit_depth": bit_depth,
        "color_type": color_type,
        "idat": bytes(idat),
    }


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    return b if pb <= pc else c


def decode_png_gray(data: bytes) -> tuple[int, int, int, list[int]]:
    info = png_gray_header(data)
    width, height, bit_depth = info["width"], info["height"], info["bit_depth"]
    bpp = 2 if bit_depth == 16 else 1
    stride = width * bpp
    try:
        raw = zlib.decompress(info["idat"])
    except zlib.error:
        require(False, "CORRUPT_IMAGE", "PNG inflate failed")
        return width, height, bit_depth, []
    require(
        len(raw) == height * (stride + 1),
        "CORRUPT_IMAGE",
        "PNG scanline size mismatch",
    )
    previous = bytearray(stride)
    out = bytearray()
    position = 0
    for _ in range(height):
        filter_type = raw[position]
        position += 1
        line = bytearray(raw[position : position + stride])
        position += stride
        if filter_type == 1:
            for i in range(bpp, stride):
                line[i] = (line[i] + line[i - bpp]) & 0xFF
        elif filter_type == 2:
            for i in range(stride):
                line[i] = (line[i] + previous[i]) & 0xFF
        elif filter_type == 3:
            for i in range(stride):
                left = line[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + ((left + previous[i]) >> 1)) & 0xFF
        elif filter_type == 4:
            for i in range(stride):
                left = line[i - bpp] if i >= bpp else 0
                upper = previous[i]
                corner = previous[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + _paeth(left, upper, corner)) & 0xFF
        elif filter_type != 0:
            require(False, "CORRUPT_IMAGE", f"Unknown PNG filter {filter_type}")
        out.extend(line)
        previous = line
    if bpp == 2:
        values = [(out[i] << 8) | out[i + 1] for i in range(0, len(out), 2)]
    else:
        values = list(out)
    return width, height, bit_depth, values

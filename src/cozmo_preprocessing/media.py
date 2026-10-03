"""Sequential FFmpeg decoding by original rank, with native grids and no autorotation."""

import subprocess
import tempfile
from pathlib import Path

import cv2
import numpy as np

from cozmo_ingestion.errors import require
from cozmo_ingestion.media import find_ffmpeg


class FFmpegFrameDecoder:
    def __init__(self, executable: str | Path | None = None):
        self.executable = executable
        self.version = "NOT_RUN"

    def candidates(self, video: Path, frames: list[dict], indices: list[int], size: list[int]):
        """Yield only requested ranks, but decode/count the entire validated stream."""
        ffmpeg, _ = find_ffmpeg(self.executable)
        self.version = subprocess.check_output([str(ffmpeg), "-version"], text=True).splitlines()[0]
        width, height = size
        command = [
            str(ffmpeg),
            "-v",
            "error",
            "-xerror",
            "-threads",
            "2",
            "-noautorotate",
            "-i",
            str(video),
            "-map",
            "0:v:0",
            "-fps_mode",
            "passthrough",
            "-pix_fmt",
            "bgr24",
            "-f",
            "rawvideo",
            "pipe:1",
        ]
        selected = set(indices)
        with tempfile.TemporaryFile() as diagnostics:
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=diagnostics)
            try:
                count = 0
                while True:
                    chunk = bytearray()
                    while len(chunk) < width * height * 3:
                        part = process.stdout.read(width * height * 3 - len(chunk))
                        if not part:
                            break
                        chunk.extend(part)
                    if not chunk:
                        break
                    require(len(chunk) == width * height * 3, "TRUNCATED_PIXELS", str(count))
                    require(count < len(frames), "DECODE_COUNT_CHANGED", str(count))
                    if count in selected:
                        yield count, np.frombuffer(chunk, dtype=np.uint8).reshape(height, width, 3)
                    count += 1
                code = process.wait(timeout=30)
                diagnostics.seek(0)
                require(
                    code == 0 and not diagnostics.read().strip(),
                    "PREPROCESS_DECODE_FAILED",
                    video.name,
                )
                require(count == len(frames), "DECODE_COUNT_CHANGED", str(count))
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=10)
                process.stdout.close()


def save_jpeg(path: Path, image: np.ndarray):
    # imencode + Path also supports Unicode filesystem paths on Windows.
    ok, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 95])
    require(ok, "IMAGE_ENCODING_FAILED", path.name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encoded.tobytes())


def read_image(path: Path) -> np.ndarray:
    image = cv2.imdecode(np.frombuffer(path.read_bytes(), dtype=np.uint8), cv2.IMREAD_COLOR)
    require(image is not None, "IMAGE_DECODE_FAILED", path.name)
    return image

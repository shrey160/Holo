"""FFmpeg process boundary: tool discovery, timestamp inspection and full decoding."""

import json
import shutil
import subprocess
from pathlib import Path

from .errors import require
from .models import VideoInspection


def find_ffmpeg(explicit: str | Path | None = None) -> tuple[Path, Path]:
    executable = str(explicit) if explicit else shutil.which("ffmpeg")
    require(
        bool(executable), "FFMPEG_NOT_FOUND", "Install FFmpeg; place it on PATH or supply --ffmpeg"
    )
    ffmpeg = Path(executable).resolve()
    sibling = ffmpeg.with_name("ffprobe.exe" if ffmpeg.suffix.lower() == ".exe" else "ffprobe")
    ffprobe = sibling if sibling.is_file() else Path(shutil.which("ffprobe") or sibling)
    require(
        ffmpeg.is_file() and ffprobe.is_file(), "FFMPEG_NOT_FOUND", "Require FFmpeg and FFprobe"
    )
    return ffmpeg, ffprobe


def inspect_video(video: Path, ffmpeg: Path, ffprobe: Path) -> VideoInspection:
    command = [
        str(ffprobe),
        "-v",
        "error",
        "-threads",
        "4",
        "-select_streams",
        "v:0",
        "-show_frames",
        "-show_packets",
        "-show_streams",
        "-show_entries",
        "frame=best_effort_timestamp,width,height:packet=pts,flags:stream=width,height,codec_name,time_base,avg_frame_rate,side_data_list",
        "-of",
        "json",
        str(video),
    ]
    probe = subprocess.run(command, capture_output=True, text=True)
    require(probe.returncode == 0 and not probe.stderr.strip(), "VIDEO_PROBE_FAILED", probe.stderr)
    parsed = json.loads(probe.stdout)
    mixed = parsed.get("packets_and_frames", [])
    frames = parsed.get("frames", [r for r in mixed if r.get("type") == "frame"])
    packets = parsed.get("packets", [r for r in mixed if r.get("type") == "packet"])
    require(
        len(parsed.get("streams", [])) == 1 and bool(frames), "EMPTY_OR_AMBIGUOUS_VIDEO", video.name
    )
    stream = parsed["streams"][0]
    require(
        not stream.get("side_data_list"),
        "UNSUPPORTED_MEDIA_TRANSFORM",
        "Native untransformed media grid required",
    )
    decode_command = [
        str(ffmpeg),
        "-v",
        "error",
        "-xerror",
        "-err_detect",
        "explode",
        "-threads",
        "4",
        "-noautorotate",
        "-i",
        str(video),
        "-map",
        "0:v:0",
        "-f",
        "null",
        "-",
    ]
    decoded = subprocess.run(decode_command, capture_output=True, text=True)
    require(
        decoded.returncode == 0 and not decoded.stderr.strip(),
        "VIDEO_DECODE_FAILED",
        decoded.stderr,
    )
    return VideoInspection(
        stream,
        frames,
        [r for r in packets if "D" in r.get("flags", "")],
        "PASSED",
        command,
        decode_command,
    )


class FFmpegVideoInspector:
    """Resolve external tools lazily so source errors do not require FFmpeg."""

    def __init__(self, executable: str | Path | None = None) -> None:
        self.executable = executable
        self._tools: tuple[Path, Path] | None = None

    def inspect(self, video: Path) -> VideoInspection:
        self._tools = find_ffmpeg(self.executable)
        return inspect_video(video, *self._tools)

    def version(self) -> str:
        require(
            self._tools is not None,
            "MEDIA_NOT_INSPECTED",
            "Inspect a video before requesting the tool version",
        )
        return subprocess.check_output([str(self._tools[0]), "-version"], text=True).splitlines()[0]

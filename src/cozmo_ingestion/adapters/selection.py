"""Select an inspected export layout without guessing from filenames alone."""

from pathlib import Path

from ..errors import require
from .sensor_recorder import SensorRecorderAdapter
from .stray import StrayAdapter


def select_adapter(source: Path):
    sensor = (source / "meta.json").is_file()
    stray = all((source / name).is_file() for name in StrayAdapter.required_files)
    require(not (sensor and stray), "AMBIGUOUS_CAPTURE", "Mixed export formats")
    if sensor:
        return SensorRecorderAdapter()
    require(
        stray, "UNSUPPORTED_CAPTURE", "Require a Sensor Recorder or complete Stray-style export"
    )
    return StrayAdapter()


def video_filename(source: Path) -> str:
    return "rgb.mp4" if select_adapter(source).name == StrayAdapter.name else "wide.mp4"

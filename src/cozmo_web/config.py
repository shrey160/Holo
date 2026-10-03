"""Shared native/container settings, independent of developer paths."""

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_root: Path = Path("outputs/web-data")
    ffmpeg: str | None = None
    request_limit: int = 1024**3
    expanded_limit: int = 2 * 1024**3
    member_limit: int = 200
    queue_limit: int = 4
    deadline: int = 600
    static_root: Path = Path(__file__).parent / "static"

    def __post_init__(self):
        for value in (
            self.request_limit,
            self.expanded_limit,
            self.member_limit,
            self.queue_limit,
            self.deadline,
        ):
            if value <= 0:
                raise ValueError("Resource limits must be positive")

    @classmethod
    def from_env(cls):
        defaults = cls()
        return cls(
            data_root=Path(os.getenv("DATA_ROOT", str(defaults.data_root))).resolve(),
            ffmpeg=os.getenv("FFMPEG_PATH") or None,
            request_limit=int(os.getenv("MAX_UPLOAD_BYTES", defaults.request_limit)),
            expanded_limit=int(os.getenv("MAX_EXPANDED_BYTES", defaults.expanded_limit)),
            member_limit=int(os.getenv("MAX_ARCHIVE_MEMBERS", defaults.member_limit)),
            queue_limit=int(os.getenv("MAX_QUEUED_JOBS", defaults.queue_limit)),
            deadline=int(os.getenv("JOB_TIMEOUT_SECONDS", defaults.deadline)),
            static_root=Path(os.getenv("STATIC_ROOT", str(defaults.static_root))).resolve(),
        )

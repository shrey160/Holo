"""Native and container server startup; development reload is opt-in."""

import argparse
import os
import tempfile
from pathlib import Path

import uvicorn

from .config import Settings


def main():
    parser = argparse.ArgumentParser(description="Serve the local capture-ingestion application")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true")
    parser.add_argument("--ffmpeg", help="FFmpeg path; FFprobe must also be available")
    args = parser.parse_args()
    if args.ffmpeg:
        os.environ["FFMPEG_PATH"] = args.ffmpeg
    upload_temp = Settings.from_env().data_root / "tmp"
    upload_temp.mkdir(parents=True, exist_ok=True)
    tempfile.tempdir = str(upload_temp.resolve())
    os.environ["TMPDIR"] = tempfile.tempdir
    built_frontend = Path("frontend/dist").resolve()
    if "STATIC_ROOT" not in os.environ and built_frontend.is_dir():
        os.environ["STATIC_ROOT"] = str(built_frontend)
    uvicorn.run(
        "cozmo_web.app:factory",
        factory=True,
        host=args.host,
        port=args.port,
        reload=args.reload,
        reload_dirs=[str(Path(__file__).parent.parent)] if args.reload else None,
    )


if __name__ == "__main__":
    main()

"""Thin command-line entry points; all domain work lives in services."""

import argparse
import json
import sys
from pathlib import Path

from .errors import IngestionError
from .pipeline import ingest
from .verification import verify


def ingest_main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a Sensor Recorder ARKit export and publish a canonical capture."
    )
    parser.add_argument(
        "--source", type=Path, required=True, help="Complete original session folder"
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="New output folder; existing folders are never overwritten",
    )
    parser.add_argument(
        "--annotations", type=Path, help="Optional JSON scale declaration bound to this video hash"
    )
    parser.add_argument(
        "--ffmpeg", help="FFmpeg executable path; defaults to PATH (FFprobe also required)"
    )
    args = parser.parse_args()
    try:
        manifest, report = ingest(args.source, args.output, args.annotations, args.ffmpeg)
        print(
            json.dumps(
                {
                    "status": manifest["status"],
                    "frames": manifest["frame_count"],
                    "findings": [f["code"] for f in report["findings"]],
                    "output": str(args.output.resolve()),
                }
            )
        )
    except (IngestionError, OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


def verify_main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit a canonical capture against raw source values and optional replay."
    )
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--replay", type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(verify(args.capture, args.source, args.replay)))
        return 0
    except (IngestionError, OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1

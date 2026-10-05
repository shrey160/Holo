"""One-command local capture processing using the same audited worker as Holo."""

import argparse
import json
import shutil
import sys
import time
from dataclasses import replace
from pathlib import Path

from cozmo_ingestion.storage import write_json

from .config import Settings
from .worker import execute


def run_capture(capture: Path, output: Path, settings: Settings, mode="dense", ingest_only=False):
    capture, output = capture.resolve(), output.resolve()
    if not capture.is_file() or capture.suffix.lower() != ".zip":
        raise ValueError("Capture must be a complete original export ZIP")
    if output.exists() or capture.is_relative_to(output):
        raise ValueError("Use a new output folder outside the input")
    if not 1 <= len(output.name) <= 60 or any(
        c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-"
        for c in output.name
    ):
        raise ValueError("Output folder name must be 1-60 letters, digits, underscores or hyphens")
    if mode not in {"auto", "dense", "preview"}:
        raise ValueError("Mode must be auto, dense or preview")
    if capture.stat().st_size > settings.request_limit:
        raise ValueError("Capture exceeds configured upload byte limit")
    settings = replace(settings, data_root=output.parent)
    output.mkdir(parents=True)
    incoming = output / "incoming"
    incoming.mkdir()
    shutil.copyfile(capture, incoming / capture.name)
    write_json(
        output / "job.json",
        {
            "id": output.name,
            "label": output.name,
            "modality": "video",
            "reference": None,
            "reference_image": None,
            "automatic_reconstruction": not ingest_only,
            "reconstruction_mode": mode,
            "input_files": [capture.name],
        },
    )
    started = time.monotonic()
    try:
        execute(output, settings)
    except Exception as error:
        write_json(
            output / "error.json",
            {"code": getattr(error, "code", "PROCESSING_FAILED"), "message": str(error)},
        )
        write_json(output / "phase.json", {"state": "FAILED"})
        raise
    result = json.loads((output / "result.json").read_text(encoding="utf-8"))
    summary = {
        "status": "SUCCEEDED",
        "output": str(output),
        "elapsed_seconds": time.monotonic() - started,
        "verification": result["verification"],
        "reconstruction": result.get("reconstruction"),
    }
    write_json(output / "run-summary.json", summary)
    return summary


def main():
    parser = argparse.ArgumentParser(
        description="Process one original video export into audited Holo results"
    )
    parser.add_argument("capture", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mode", choices=("auto", "dense", "preview"), default="dense")
    parser.add_argument("--ingest-only", action="store_true")
    parser.add_argument("--ffmpeg")
    args = parser.parse_args()
    settings = Settings.from_env()
    if args.ffmpeg:
        settings = replace(settings, ffmpeg=args.ffmpeg)
    try:
        print(
            json.dumps(
                run_capture(args.capture, args.output, settings, args.mode, args.ingest_only),
                indent=2,
            )
        )
    except Exception as error:
        print(f"{getattr(error, 'code', 'CAPTURE_FAILED')}: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

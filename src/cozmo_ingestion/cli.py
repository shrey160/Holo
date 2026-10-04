"""Thin command-line entry points; all domain work lives in services."""

import argparse
import json
import sys
from pathlib import Path

from .errors import IngestionError
from .multimodal.contracts import (
    MODE_LIDAR,
    MODE_PHOTOS,
    MODE_VIDEO,
    MODES,
    SCHEMA_V2,
    MultimodalRequest,
)
from .multimodal.lidar_pipeline import FFmpegRgbProbe, LiDARIngestionPipeline
from .multimodal.pipeline import PhotosIngestionPipeline
from .multimodal.verify import verify_v2
from .pipeline import ingest
from .verification import verify


def ingest_main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a Sensor Recorder/Stray export or a room photo set into a canonical capture."
    )
    parser.add_argument(
        "--source", type=Path, required=True, help="Complete original session/room folder"
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="New output folder; existing folders are never overwritten",
    )
    parser.add_argument(
        "--mode",
        choices=MODES,
        help="Explicit modality; omit for the legacy auto-selected video export",
    )
    parser.add_argument("--room-label", help="Label for a single loose photo folder")
    parser.add_argument(
        "--reference",
        type=Path,
        help="Optional user-declared reference object JSON; dimensions are not applied",
    )
    parser.add_argument("--source-format", help="Explicit source-format identifier")
    parser.add_argument(
        "--annotations", type=Path, help="Optional JSON scale declaration bound to this video hash"
    )
    parser.add_argument(
        "--ffmpeg", help="FFmpeg executable path; defaults to PATH (FFprobe also required)"
    )
    args = parser.parse_args()
    try:
        if args.mode == MODE_PHOTOS:
            result = PhotosIngestionPipeline().run(
                MultimodalRequest(
                    args.source,
                    args.output,
                    MODE_PHOTOS,
                    args.source_format,
                    args.room_label,
                    args.reference,
                )
            )
            print(
                json.dumps(
                    {
                        "status": result.manifest["status"],
                        "schema": result.manifest["schema"],
                        "mode": result.manifest["mode"],
                        "rooms": result.manifest["room_count"],
                        "images": result.manifest["image_count"],
                        "distinct_images": result.manifest["distinct_image_count"],
                        "findings": [f["code"] for f in result.report["findings"]],
                        "output": str(args.output.resolve()),
                    }
                )
            )
            return 0
        if args.mode == MODE_LIDAR:
            probe = FFmpegRgbProbe(args.ffmpeg) if args.ffmpeg else None
            result = LiDARIngestionPipeline(rgb_probe=probe).run(
                MultimodalRequest(args.source, args.output, MODE_LIDAR, args.source_format)
            )
            print(
                json.dumps(
                    {
                        "status": result.manifest["status"],
                        "schema": result.manifest["schema"],
                        "mode": result.manifest["mode"],
                        "frames": result.manifest["frame_count"],
                        "depth_frames": result.manifest["depth_frame_count"],
                        "confidence_frames": result.manifest["confidence_frame_count"],
                        "geometry_readiness": result.report["geometry_readiness"],
                        "findings": [f["code"] for f in result.report["findings"]],
                        "output": str(args.output.resolve()),
                    }
                )
            )
            return 0
        if args.mode == MODE_VIDEO:
            raise IngestionError(
                "NOT_IMPLEMENTED_FOR_MODALITY",
                "Plain video ingestion is not implemented; use the default export path",
            )
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
    parser.add_argument("--source", type=Path)
    parser.add_argument("--replay", type=Path)
    args = parser.parse_args()
    try:
        manifest_path = args.capture / "manifest.json"
        schema = json.loads(manifest_path.read_text(encoding="utf-8")).get("schema")
        if schema == SCHEMA_V2:
            print(json.dumps(verify_v2(args.capture, args.source, args.replay)))
            return 0
        if args.source is None:
            raise IngestionError("SOURCE_REQUIRED", "v1 verification requires --source")
        print(json.dumps(verify(args.capture, args.source, args.replay)))
        return 0
    except (IngestionError, OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1

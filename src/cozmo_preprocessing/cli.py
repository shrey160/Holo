"""Portable native preprocessing and verification entry point."""

import argparse
import json
from pathlib import Path

from cozmo_ingestion.errors import IngestionError

from .media import FFmpegFrameDecoder
from .models import PreprocessingPolicy, PreprocessingRequest
from .pipeline import PreprocessingPipeline
from .verification import verify_preprocessing


def main():
    parser = argparse.ArgumentParser(
        description="Prepare Sensor Recorder RGB/pose/IMU views without LiDAR or grounding"
    )
    parser.add_argument("bundle", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--ffmpeg")
    parser.add_argument("--candidate-fps", type=float, default=4)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    try:
        if not args.verify_only:
            PreprocessingPipeline(
                PreprocessingPolicy(candidate_fps=args.candidate_fps),
                FFmpegFrameDecoder(args.ffmpeg),
            ).run(PreprocessingRequest(args.bundle, args.output, args.source))
        print(json.dumps(verify_preprocessing(args.output, args.bundle, args.source), indent=2))
    except (IngestionError, ValueError) as error:
        parser.exit(1, f"{getattr(error, 'code', 'INVALID_POLICY')}: {error}\n")


if __name__ == "__main__":
    main()

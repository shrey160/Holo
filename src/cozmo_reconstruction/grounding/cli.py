"""Offline native/container annotation preparation, diagnostics and verification."""

import argparse
import json
from pathlib import Path

from cozmo_ingestion.errors import IngestionError

from .models import GroundingRequest
from .pipeline import GroundingPipeline
from .verification import verify_grounding


def main():
    parser = argparse.ArgumentParser(
        description="Known-size reference diagnostic; source scale unchanged"
    )
    for name in ("prepared", "bundle", "output"):
        parser.add_argument(name, type=Path)
    for name in ("source", "annotations", "sparse", "dense", "surfaces", "review_confirmation"):
        parser.add_argument(f"--{name.replace('_', '-')}", type=Path)
    parser.add_argument("--object-id", default="opening-a4-reference")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    try:
        kwargs = {
            name: getattr(args, name).resolve() if getattr(args, name) else None
            for name in (
                "source",
                "annotations",
                "sparse",
                "dense",
                "surfaces",
                "review_confirmation",
            )
        }
        request = GroundingRequest(
            args.prepared.resolve(),
            args.bundle.resolve(),
            args.output.resolve(),
            object_id=args.object_id,
            **kwargs,
        )
        result = (
            verify_grounding(request.output, request)
            if args.verify_only
            else GroundingPipeline().run(request)
        )
        print(json.dumps(result, indent=2))
    except (IngestionError, ValueError, OSError, KeyError, ImportError, RuntimeError) as error:
        parser.exit(1, f"{getattr(error, 'code', 'GROUNDING_FAILED')}: {error}\n")


if __name__ == "__main__":
    main()

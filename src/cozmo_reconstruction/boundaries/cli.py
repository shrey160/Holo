"""Native and CPU-container entry point for reviewed partial evidence."""

import argparse
import json
from pathlib import Path

from cozmo_ingestion.errors import IngestionError
from cozmo_reconstruction.dense.models import DenseRequest
from cozmo_reconstruction.surfaces.models import SurfaceRequest

from .models import BoundaryRequest
from .pipeline import BoundaryPipeline
from .verification import verify_boundaries


def main():
    parser = argparse.ArgumentParser(
        description="Region-reviewed partial boundaries; no closed room or scale correction"
    )
    parser.add_argument("surfaces", type=Path)
    parser.add_argument("output", type=Path)
    for name in ("sparse", "prepared", "bundle", "dense"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    for name in ("source", "review", "grounding"):
        parser.add_argument(f"--{name}", type=Path)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    try:
        upstream = DenseRequest(
            args.sparse.resolve(),
            args.prepared.resolve(),
            args.bundle.resolve(),
            args.dense.resolve(),
            args.source.resolve() if args.source else None,
        )
        request = BoundaryRequest(
            SurfaceRequest(upstream, args.surfaces.resolve()),
            args.output.resolve(),
            args.review.resolve() if args.review else None,
            args.grounding.resolve() if args.grounding else None,
        )
        result = (
            verify_boundaries(request.output, request)
            if args.verify_only
            else BoundaryPipeline().run(request)
        )
        print(json.dumps(result, indent=2))
    except (IngestionError, ValueError, OSError, KeyError, ImportError, RuntimeError) as error:
        parser.exit(1, f"{getattr(error, 'code', 'BOUNDARY_FAILED')}: {error}\n")


if __name__ == "__main__":
    main()

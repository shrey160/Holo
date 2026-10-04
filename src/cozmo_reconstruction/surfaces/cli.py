"""Native CPU surface evidence; also available in either reconstruction container."""

import argparse
import json
from pathlib import Path

from cozmo_ingestion.errors import IngestionError
from cozmo_reconstruction.dense.models import DenseRequest

from .models import SurfacePolicy, SurfaceRequest
from .pipeline import SurfacePipeline, verify_surfaces


def main():
    parser = argparse.ArgumentParser(
        description="Conservative floor/wall hypotheses with RGB evidence"
    )
    for name in ("sparse", "prepared", "bundle", "dense", "output"):
        parser.add_argument(name, type=Path)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--distance", type=float, default=0.035)
    parser.add_argument("--max-planes", type=int, default=12)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    try:
        request = SurfaceRequest(
            DenseRequest(
                args.sparse.resolve(),
                args.prepared.resolve(),
                args.bundle.resolve(),
                args.dense.resolve(),
                args.source.resolve() if args.source else None,
            ),
            args.output.resolve(),
        )
        policy = SurfacePolicy(distance_m=args.distance, max_planes=args.max_planes)
        result = (
            verify_surfaces(request.output, request)
            if args.verify_only
            else SurfacePipeline(policy).run(request)
        )
        print(json.dumps(result, indent=2))
    except (IngestionError, ValueError, OSError, KeyError, ImportError, RuntimeError) as error:
        parser.exit(1, f"{getattr(error, 'code', 'SURFACE_FAILED')}: {error}\n")


if __name__ == "__main__":
    main()

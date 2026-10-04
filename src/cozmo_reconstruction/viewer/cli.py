"""Publish portable assets for Holo's reconstruction tab after a full source audit."""

import argparse
import json
from pathlib import Path

from cozmo_ingestion.errors import IngestionError
from cozmo_reconstruction.boundaries.models import BoundaryRequest
from cozmo_reconstruction.dense.models import DenseRequest
from cozmo_reconstruction.surfaces.models import SurfaceRequest

from .export import export_viewer


def main():
    parser = argparse.ArgumentParser(description="Publish audited rough plan / 3D viewer assets")
    parser.add_argument("boundaries", type=Path)
    parser.add_argument("output", type=Path)
    for name in ("surfaces", "sparse", "prepared", "bundle", "dense"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    for name in ("source", "grounding"):
        parser.add_argument(f"--{name}", type=Path)
    parser.add_argument("--label", default="Room reconstruction")
    parser.add_argument("--max-points", type=int, default=120000)
    parser.add_argument(
        "--rough-room", action="store_true", help="Complete an explicitly inferred rectangular room"
    )
    parser.add_argument(
        "--ceiling-reference",
        type=Path,
        help="Optional external ceiling-height JSON; no scale correction",
    )
    parser.add_argument(
        "--object-review",
        type=Path,
        help="Source-bound RGB object regions for approximate footprints",
    )
    args = parser.parse_args()
    try:
        dense = DenseRequest(
            args.sparse.resolve(),
            args.prepared.resolve(),
            args.bundle.resolve(),
            args.dense.resolve(),
            args.source.resolve() if args.source else None,
        )
        request = BoundaryRequest(
            SurfaceRequest(dense, args.surfaces.resolve()),
            args.boundaries.resolve(),
            grounding=args.grounding.resolve() if args.grounding else None,
        )
        print(
            json.dumps(
                export_viewer(
                    request,
                    args.output,
                    args.label,
                    args.max_points,
                    rough_room=args.rough_room,
                    ceiling_reference=args.ceiling_reference,
                    object_review=args.object_review,
                ),
                indent=2,
            )
        )
    except (IngestionError, ValueError, OSError, KeyError, RuntimeError) as error:
        parser.exit(1, f"{getattr(error, 'code', 'VIEWER_FAILED')}: {error}\n")


if __name__ == "__main__":
    main()

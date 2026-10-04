"""CPU input preparation/publication; training runs in an isolated CUDA environment."""

import argparse
import json
from pathlib import Path

from cozmo_reconstruction.boundaries.models import BoundaryRequest
from cozmo_reconstruction.dense.models import DenseRequest
from cozmo_reconstruction.surfaces.models import SurfaceRequest

from .inputs import prepare
from .publish import publish


def main():
    parser = argparse.ArgumentParser(
        description="Prepare/publish a bounded Gaussian appearance experiment"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    inputs = commands.add_parser("prepare")
    inputs.add_argument("boundaries", type=Path)
    inputs.add_argument("output", type=Path)
    for name in ("surfaces", "sparse", "prepared", "bundle", "dense"):
        inputs.add_argument(f"--{name}", type=Path, required=True)
    for name in ("source", "grounding"):
        inputs.add_argument(f"--{name}", type=Path)
    inputs.add_argument("--points", type=int, default=100000)
    inputs.add_argument("--width", type=int, default=640)
    output = commands.add_parser("publish")
    for name in ("inputs", "trial", "viewer", "output"):
        output.add_argument(name, type=Path)
    args = parser.parse_args()
    try:
        if args.command == "prepare":
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
            result = prepare(request, args.output, args.points, args.width)
        else:
            result = publish(args.inputs, args.trial, args.viewer, args.output)
        print(json.dumps(result, indent=2))
    except (ValueError, OSError, RuntimeError, KeyError) as error:
        parser.exit(1, f"{getattr(error, 'code', 'GAUSSIAN_FAILED')}: {error}\n")


if __name__ == "__main__":
    main()

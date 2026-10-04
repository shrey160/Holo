"""Dense CLI, usable natively for CPU verification or with a CUDA COLMAP build."""

import argparse
import json
from pathlib import Path

from cozmo_ingestion.errors import IngestionError, require
from cozmo_ingestion.storage import sha256

from .models import DensePolicy, DenseRequest
from .pipeline import DensePipeline, verify_dense
from .runtime import runtime_status


def main():
    parser = argparse.ArgumentParser(
        description="Fixed-pose RGB stereo depth; CUDA worker required for inference"
    )
    for name in ("sparse", "prepared", "bundle", "output"):
        parser.add_argument(name, type=Path)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--ranks-file", type=Path)
    parser.add_argument("--max-image-size", type=int, default=960)
    parser.add_argument("--neighbors", type=int, default=6)
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    try:
        if not args.verify_only:
            runtime = runtime_status()
            require(
                runtime["available"],
                "DENSE_CUDA_UNAVAILABLE",
                str(runtime["reason"]),
            )
        ranks = None
        if args.ranks_file:
            proposal = json.loads(args.ranks_file.read_text())
            if isinstance(proposal, dict):
                if proposal.get(
                    "sparse_manifest_sha256", sha256(args.sparse / "manifest.json")
                ) != sha256(args.sparse / "manifest.json"):
                    raise ValueError("Ranks belong to a different sparse capture")
                proposal = proposal["ranks"]
            ranks = tuple(proposal)
        request = DenseRequest(
            args.sparse.resolve(),
            args.prepared.resolve(),
            args.bundle.resolve(),
            args.output.resolve(),
            args.source.resolve() if args.source else None,
            ranks,
        )
        policy = DensePolicy(
            max_image_size=args.max_image_size,
            neighbors=args.neighbors,
            iterations=args.iterations,
            timeout_seconds=args.timeout,
        )
        result = (
            verify_dense(request.output, request)
            if args.verify_only
            else DensePipeline(policy).run(request)
        )
        print(json.dumps(result, indent=2))
    except (IngestionError, ValueError, OSError, KeyError, ImportError, RuntimeError) as error:
        parser.exit(1, f"{getattr(error, 'code', 'DENSE_FAILED')}: {error}\n")


if __name__ == "__main__":
    main()

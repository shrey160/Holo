"""Native/container reconstruction CLI and independent verification."""

import argparse
import json
from pathlib import Path

from cozmo_ingestion.errors import IngestionError
from cozmo_ingestion.storage import sha256

from .models import ReconstructionPolicy, ReconstructionRequest
from .pipeline import ReconstructionPipeline
from .verification import verify_reconstruction


def main():
    parser = argparse.ArgumentParser(
        description="Fixed-pose iOS sparse geometry; no LiDAR or grounding"
    )
    parser.add_argument("prepared", type=Path)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--source", type=Path)
    parser.add_argument(
        "--ranks-file", type=Path, help="JSON list or object containing --ranks-key"
    )
    parser.add_argument("--ranks-key", default="ranks")
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--features", type=int, default=4096)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument(
        "--principal-point-shift",
        type=float,
        choices=(0.0, 0.5),
        default=0.0,
        help="Recorded source pixel-center hypothesis; physical convention unverified",
    )
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    try:
        ranks = None
        if args.ranks_file:
            proposal = json.loads(args.ranks_file.read_text(encoding="utf-8"))
            if isinstance(proposal, dict):
                if "source_manifest_sha256" in proposal:
                    if proposal["source_manifest_sha256"] != sha256(
                        args.prepared / "manifest.json"
                    ):
                        raise ValueError("Rank proposal belongs to a different prepared capture")
                proposal = proposal[args.ranks_key]
            ranks = tuple(proposal)
        policy = ReconstructionPolicy(
            max_features=args.features,
            threads=args.threads,
            timeout_seconds=args.timeout,
            principal_point_shift=args.principal_point_shift,
        )
        if args.verify_only:
            result = verify_reconstruction(args.output, args.prepared, args.bundle, args.source)
        else:
            result = ReconstructionPipeline(policy).run(
                ReconstructionRequest(args.prepared, args.bundle, args.output, args.source, ranks)
            )
        print(json.dumps(result, indent=2))
    except (IngestionError, ValueError, OSError, KeyError, ImportError) as error:
        parser.exit(1, f"{getattr(error, 'code', 'RECONSTRUCTION_FAILED')}: {error}\n")


if __name__ == "__main__":
    main()

"""Audit and republish an existing dense job; never rerun stereo or replace a result."""

import argparse
import json
from pathlib import Path

from cozmo_reconstruction.dense.models import DenseRequest
from cozmo_reconstruction.surfaces.models import SurfaceRequest
from cozmo_reconstruction.viewer.dense_automatic import publish_dense


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--label", default="Room-wise dense review")
    args = parser.parse_args()
    job = args.job.resolve()
    dense = DenseRequest(
        job / "reconstruction", job / "preprocessing", job / "bundle", job / "dense", job / "raw"
    )
    print(
        json.dumps(
            publish_dense(
                SurfaceRequest(dense, job / "surfaces"), args.output.resolve(), args.label
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

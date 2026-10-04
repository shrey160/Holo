"""CPU-only PyCOLMAP worker entry point."""

import json
import sys
from pathlib import Path

from .colmap import run_colmap
from .models import ReconstructionPolicy


def main():
    stage = Path(sys.argv[1]).resolve()
    config = json.loads((stage / "policy.json").read_text(encoding="utf-8"))
    run_colmap(stage, ReconstructionPolicy(**config))


if __name__ == "__main__":
    main()

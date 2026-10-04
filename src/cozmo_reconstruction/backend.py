"""Bounded isolated CPU backend; native extension crashes cannot publish partial output."""

import os
import subprocess
import sys
from pathlib import Path

from cozmo_ingestion.errors import IngestionError, require

from .models import ReconstructionPolicy


class PyCOLMAPBackend:
    def run(self, stage: Path, policy: ReconstructionPolicy) -> None:
        env = os.environ.copy()
        env.update({"OMP_NUM_THREADS": str(policy.threads), "OPENBLAS_NUM_THREADS": "1"})
        with (stage / "backend.log").open("w", encoding="utf-8") as log:
            try:
                completed = subprocess.run(
                    [sys.executable, "-m", "cozmo_reconstruction.worker", str(stage)],
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    timeout=policy.timeout_seconds,
                    env=env,
                    check=False,
                )
            except subprocess.TimeoutExpired as error:
                raise IngestionError(
                    "RECONSTRUCTION_TIMEOUT", "Backend killed at configured timeout"
                ) from error
        require(
            completed.returncode == 0,
            "RECONSTRUCTION_BACKEND_FAILED",
            f"Exit {completed.returncode}; inspect backend.log",
        )

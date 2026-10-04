"""Backend lifecycle boundary, independent of CLI/HTTP."""

from pathlib import Path
from typing import Protocol

from .models import ReconstructionPolicy


class ReconstructionBackend(Protocol):
    def run(self, stage: Path, policy: ReconstructionPolicy) -> None: ...

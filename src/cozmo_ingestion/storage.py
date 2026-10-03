"""Deterministic file encoding, safe paths and artifact integrity."""

import csv
import hashlib
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .errors import require


def sha256(path: str | Path) -> str:
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def encoded(value: Any) -> str:
    return json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n"


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(encoded(value), encoding="utf-8", newline="\n")


def write_lines(path: Path, records: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(r, sort_keys=True, allow_nan=False) + "\n" for r in records),
        encoding="utf-8",
        newline="\n",
    )


def write_csv(path: Path, fields: list[str], rows: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\r\n")
        writer.writeheader()
        writer.writerows(rows)


def inside(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    require(path.is_relative_to(root.resolve()), "SOURCE_PATH_ESCAPE", str(relative))
    return path


class BundleIntegrity:
    """Verify declared artifact identities on every access, including audit reads."""

    def __init__(self, folder: Path, hashes: dict[str, str]) -> None:
        self.folder = folder
        self.hashes = hashes

    def path(self, name: str) -> Path:
        require(name in self.hashes, "MISSING_ARTIFACT", name)
        path = inside(self.folder, name)
        require(path.is_file(), "MISSING_ARTIFACT", name)
        require(sha256(path) == self.hashes[name], "ARTIFACT_CHANGED", name)
        return path

    def verify_all(self) -> int:
        for name in self.hashes:
            self.path(name)
        return len(self.hashes)


def pipeline_fingerprint() -> str:
    """Hash all package modules, independent of checkout line endings/root path."""
    root = Path(__file__).parent
    sources = {
        p.relative_to(root).as_posix(): hashlib.sha256(
            p.read_text(encoding="utf-8").encode()
        ).hexdigest()
        for p in sorted(root.rglob("*.py"))
    }
    return hashlib.sha256(encoded(sources).encode()).hexdigest()

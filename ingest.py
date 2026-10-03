"""Compatibility entry point; use the installed cozmo_ingestion package."""

from cozmo_ingestion.cli import ingest_main
from cozmo_ingestion.pipeline import ingest

__all__ = ["ingest"]

if __name__ == "__main__":
    raise SystemExit(ingest_main())

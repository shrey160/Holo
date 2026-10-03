"""Compatibility entry point; use the installed cozmo_ingestion package."""

from cozmo_ingestion.cli import verify_main
from cozmo_ingestion.verification import verify

__all__ = ["verify"]

if __name__ == "__main__":
    raise SystemExit(verify_main())

"""Isolated execution using the installed domain APIs, with persisted phases."""

import argparse
import json
from pathlib import Path

from cozmo_ingestion import IngestionRequest
from cozmo_ingestion.errors import IngestionError
from cozmo_ingestion.media import FFmpegVideoInspector
from cozmo_ingestion.pipeline import IngestionPipeline
from cozmo_ingestion.storage import sha256, write_json
from cozmo_ingestion.verification import verify

from .config import Settings
from .errors import WebError
from .reference_images import bind_reference_image
from .repository import atomic_json
from .schemas import Reference
from .uploads import prepare_capture


def execute(folder: Path, settings: Settings):
    def phase(name):
        atomic_json(folder / "phase.json", {"state": name})

    phase("VALIDATING_INPUT")
    raw = prepare_capture(folder, settings)
    job = json.loads((folder / "job.json").read_text(encoding="utf-8"))
    image = bind_reference_image(folder, sha256(raw / "wide.mp4"), settings)
    annotation = None
    if job["reference"]:
        annotation = folder / "annotations/reference.json"
        write_json(
            annotation,
            Reference.model_validate(job["reference"]).annotation(sha256(raw / "wide.mp4")),
        )
    phase("INGESTING")
    result = IngestionPipeline(video_inspector=FFmpegVideoInspector(settings.ffmpeg)).run(
        IngestionRequest(raw, folder / "bundle", annotation)
    )
    phase("VERIFYING")
    audit = verify(result.output, raw)
    write_json(folder / "verification.json", audit)
    write_json(
        folder / "result.json",
        {
            "manifest": result.manifest,
            "validation": result.report,
            "verification": audit,
            "reference_image": image,
        },
    )
    phase("SUCCEEDED")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("folder", type=Path)
    args = parser.parse_args()
    try:
        execute(args.folder, Settings.from_env())
    except Exception as error:
        code = error.code if isinstance(error, (WebError, IngestionError)) else "PROCESSING_FAILED"
        # Full exception details stay in the local log; avoid exposing host filesystem paths.
        message = (
            str(error)
            if isinstance(error, WebError)
            else "Capture validation failed. Check the complete original export."
        )
        write_json(args.folder / "error.json", {"code": code, "message": message})
        raise


if __name__ == "__main__":
    main()

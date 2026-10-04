"""Verified portable exports with the raw/bundle relative layout preserved."""

import json
import threading
import uuid
import zipfile
from pathlib import Path

from cozmo_ingestion import CaptureReader
from cozmo_ingestion.multimodal.verify import verify_v2
from cozmo_ingestion.storage import encoded
from cozmo_ingestion.verification import verify

from .automatic import verify_automatic
from .errors import WebError
from .reference_images import read_reference_image


class ExportService:
    def __init__(self):
        self.lock = threading.Lock()

    def _audit(self, folder: Path) -> dict:
        bundle = folder / "bundle"
        manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
        if manifest.get("schema") == "canonical-capture-2":
            raw = folder / "raw"
            return verify_v2(bundle, raw if raw.is_dir() else None)
        verify_automatic(folder)
        audit = verify(bundle, folder / "raw")
        read_reference_image(folder)
        if (folder / "preprocessing").is_dir():
            from cozmo_preprocessing.verification import verify_preprocessing

            verify_preprocessing(folder / "preprocessing", bundle, folder / "raw")
        reader = CaptureReader(bundle)
        for asset_id, asset in reader.assets.items():
            if asset["root"] == "annotations":
                reader.read_source(asset_id)
        return audit

    def archive(self, folder: Path) -> Path:
        with self.lock:
            audit = self._audit(folder)
            export_root = folder / "exports"
            export_root.mkdir(exist_ok=True)
            target = export_root / (uuid.uuid4().hex + ".zip")
            temporary = target.with_suffix(".tmp")
            try:
                with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_STORED) as archive:
                    for directory in (
                        "raw",
                        "annotations",
                        "reference",
                        "bundle",
                        "preprocessing",
                        "reconstruction",
                        "dense",
                        "surfaces",
                        "viewer",
                    ):
                        for path in sorted((folder / directory).rglob("*")):
                            if path.is_symlink():
                                raise WebError("EXPORT_CHANGED", "Capture storage has changed", 409)
                            if path.is_file():
                                archive.write(path, path.relative_to(folder).as_posix())
                    archive.writestr("verification.json", encoded(audit))
                self._audit(folder)
                temporary.replace(target)
            finally:
                temporary.unlink(missing_ok=True)
            return target

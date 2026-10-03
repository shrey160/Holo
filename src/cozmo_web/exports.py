"""Verified portable exports with the raw/bundle relative layout preserved."""

import threading
import uuid
import zipfile
from pathlib import Path

from cozmo_ingestion import CaptureReader
from cozmo_ingestion.verification import verify

from .errors import WebError
from .reference_images import read_reference_image


class ExportService:
    def __init__(self):
        self.lock = threading.Lock()

    def archive(self, folder: Path) -> Path:
        with self.lock:
            verify(folder / "bundle", folder / "raw")
            read_reference_image(folder)
            reader = CaptureReader(folder / "bundle")
            for asset_id, asset in reader.assets.items():
                if asset["root"] == "annotations":
                    reader.read_source(asset_id)
            export_root = folder / "exports"
            export_root.mkdir(exist_ok=True)
            target = export_root / (uuid.uuid4().hex + ".zip")
            temporary = target.with_suffix(".tmp")
            try:
                with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_STORED) as archive:
                    for directory in ("raw", "annotations", "reference", "bundle"):
                        for path in sorted((folder / directory).rglob("*")):
                            if path.is_symlink():
                                raise WebError("EXPORT_CHANGED", "Capture storage has changed", 409)
                            if path.is_file():
                                archive.write(path, path.relative_to(folder).as_posix())
                    archive.write(folder / "verification.json", "verification.json")
                verify(folder / "bundle", folder / "raw")
                read_reference_image(folder)
                for asset_id, asset in reader.assets.items():
                    if asset["root"] == "annotations":
                        reader.read_source(asset_id)
                temporary.replace(target)
            finally:
                temporary.unlink(missing_ok=True)
            return target

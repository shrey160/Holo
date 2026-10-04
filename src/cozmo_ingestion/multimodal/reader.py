"""Validated canonical-capture-2 reader plus schema-dispatching catalog opener."""

import json
from pathlib import Path

from ..contracts import SCHEMA
from ..errors import IngestionError, require
from ..storage import BundleIntegrity, inside
from .contracts import MODES, SCHEMA_V2
from .schema import validate_bundle_documents, validate_document

V2_ADAPTERS = {"photos-jpeg-png-v1", "stray-raw-depth-v1"}


class MultimodalCaptureReader:
    """Read admitted v2 observations with artifact hashing and structural validation."""

    def __init__(self, folder: str | Path) -> None:
        self.folder = Path(folder).resolve()
        manifest_path = self.folder / "manifest.json"
        require(manifest_path.is_file(), "MISSING_MANIFEST", str(self.folder))
        self.manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        require(
            self.manifest.get("schema") == SCHEMA_V2,
            "UNKNOWN_SCHEMA",
            str(self.manifest.get("schema")),
        )
        require(
            self.manifest.get("status") == "READY_WITH_FINDINGS",
            "CAPTURE_NOT_READY",
            str(self.folder),
        )
        require(
            self.manifest.get("mode") in MODES,
            "UNKNOWN_MODALITY",
            str(self.manifest.get("mode")),
        )
        require(
            self.manifest.get("adapter") in V2_ADAPTERS,
            "UNKNOWN_ADAPTER",
            str(self.manifest.get("adapter")),
        )
        validate_document("manifest", self.manifest)
        self.hashes = self.manifest["artifact_sha256"]
        self.integrity = BundleIntegrity(self.folder, self.hashes)
        self.rooms_doc = self._read_json("rooms.json")
        self.assets_doc = self._read_json("assets.json")
        self.references_doc = self._read_json("references.json")
        self.verification = self._read_json("verification.json")
        self.observations = self._read_lines("observations.jsonl")
        self.associations = self._read_lines("associations.jsonl")
        self.calibrations = self._read_lines("calibration.jsonl")
        self.poses = self._read_lines("poses.jsonl")
        validate_document("verification", self.verification)
        validate_bundle_documents(
            self.rooms_doc,
            self.assets_doc,
            self.observations,
            self.references_doc,
            self.associations,
            self.calibrations,
            self.poses,
        )
        self._assets = {asset["id"]: asset for asset in self.assets_doc["assets"]}

    def _read_json(self, name: str) -> dict:
        return json.loads(self.integrity.path(name).read_text(encoding="utf-8"))

    def _read_lines(self, name: str) -> list[dict]:
        text = self.integrity.path(name).read_text(encoding="utf-8")
        return [json.loads(line) for line in text.splitlines() if line]

    @property
    def modality(self) -> str:
        return self.manifest["mode"]

    @property
    def capabilities(self) -> dict:
        return self.manifest["capabilities"]

    def rooms(self) -> list[dict]:
        return list(self.rooms_doc["rooms"])

    def assets(self) -> list[dict]:
        return list(self.assets_doc["assets"])

    def references(self) -> dict:
        return self.references_doc

    def calibration(self) -> list[dict]:
        return list(self.calibrations)

    def pose_records(self) -> list[dict]:
        return list(self.poses)

    def asset(self, asset_id: str) -> dict:
        require(asset_id in self._assets, "UNKNOWN_ASSET", asset_id)
        return self._assets[asset_id]

    def source_path(self, asset_id: str) -> Path:
        asset = self.asset(asset_id)
        relative = asset["source_paths"][0]
        path = inside(self.folder / "sources", relative)
        require(path.is_file(), "MISSING_ARTIFACT", relative)
        return path

    def read_source(self, asset_id: str) -> bytes:
        return self.source_path(asset_id).read_bytes()

    def verify_bundle(self) -> int:
        return self.integrity.verify_all()

    def usage(self) -> dict:
        return {
            "schema": SCHEMA_V2,
            "mode": self.modality,
            "capabilities": self.capabilities,
            "boundary": "use this reader rather than arbitrary file IO",
        }


def open_capture(folder: str | Path, source_root: str | Path | None = None):
    """Dispatch a bundle by its declared schema; admit v2 only through its own validator."""
    path = Path(folder).resolve()
    manifest_path = path / "manifest.json"
    require(manifest_path.is_file(), "MISSING_MANIFEST", str(path))
    schema = json.loads(manifest_path.read_text(encoding="utf-8")).get("schema")
    if schema == SCHEMA:
        from ..reader import CaptureReader

        return CaptureReader(path, source_root=source_root)
    if schema == SCHEMA_V2:
        require(
            source_root is None,
            "SOURCE_ROOT_UNSUPPORTED",
            "v2 bundles carry their own portable sources",
        )
        return MultimodalCaptureReader(path)
    raise IngestionError("UNKNOWN_SCHEMA", str(schema))

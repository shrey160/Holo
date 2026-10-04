"""Separate immutable appearance catalog, bound to an existing reconstruction."""

import json
import re
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

from cozmo_ingestion.storage import BundleIntegrity, sha256

from .errors import WebError

ASSETS = {
    "scene.json": "application/json",
    "report.json": "application/json",
    "room.splat": "application/octet-stream",
    "initial.jpg": "image/jpeg",
    "final.jpg": "image/jpeg",
}
ID = r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}"


class GaussianCatalog:
    def __init__(self, root: Path, reconstructions: Path):
        self.root, self.reconstructions = root.resolve(), reconstructions.resolve()

    def read(self, result_id):
        if not re.fullmatch(ID, result_id):
            raise WebError("NOT_FOUND", "Gaussian result not found", 404)
        folder = (self.root / result_id).resolve()
        if not folder.is_relative_to(self.root) or not (folder / "manifest.json").is_file():
            raise WebError("NOT_FOUND", "Gaussian result not found", 404)
        try:
            manifest = json.loads((folder / "manifest.json").read_text())
            if manifest["schema"] != "holo-gaussian-viewer-v1" or set(
                manifest["artifact_sha256"]
            ) != set(ASSETS):
                raise ValueError("Unsupported Gaussian assets")
            integrity = BundleIntegrity(folder, manifest["artifact_sha256"])
            integrity.verify_all()
            scene = json.loads(integrity.path("scene.json").read_text())
            parent_id = scene["reconstruction_id"]
            if not re.fullmatch(ID, parent_id):
                raise ValueError("Invalid parent")
            parent = (self.reconstructions / parent_id).resolve()
            if (
                not parent.is_relative_to(self.reconstructions)
                or sha256(parent / "manifest.json") != scene["viewer_manifest_sha256"]
            ):
                raise ValueError("Parent reconstruction changed")
            return integrity, {"id": result_id, **scene}
        except (OSError, KeyError, ValueError) as error:
            raise WebError("GAUSSIAN_INVALID", "Stored Gaussian result is invalid", 409) from error

    def list(self, reconstruction_id=None):
        if not self.root.is_dir():
            return []
        rows = [
            self.read(p.name)[1]
            for p in sorted(self.root.iterdir())
            if p.is_dir() and re.fullmatch(ID, p.name) and (p / "manifest.json").is_file()
        ]
        return [
            r
            for r in rows
            if reconstruction_id is None or r["reconstruction_id"] == reconstruction_id
        ]


def gaussian_router(root, reconstructions):
    catalog = GaussianCatalog(root, reconstructions)
    router = APIRouter(prefix="/api/gaussians")

    @router.get("")
    def results(reconstruction_id: str | None = None):
        return catalog.list(reconstruction_id)

    @router.get("/{result_id}/{asset}")
    def asset(result_id: str, asset: str):
        if asset not in ASSETS:
            raise WebError("NOT_FOUND", "Gaussian asset not found", 404)
        integrity, _ = catalog.read(result_id)
        return FileResponse(
            integrity.path(asset), media_type=ASSETS[asset], headers={"Cache-Control": "no-store"}
        )

    return router

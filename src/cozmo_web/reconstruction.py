"""Read-only, hash-checked viewer catalog; no machine paths or geometry engines in HTTP."""

import json
import re
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

from cozmo_ingestion.storage import BundleIntegrity

from .errors import WebError

ASSETS = {
    "scene.json": "application/json",
    "plan.json": "application/json",
    "positions.bin": "application/octet-stream",
    "colors.bin": "application/octet-stream",
    "plan.png": "image/png",
    "reviewed-plan.svg": "image/svg+xml",
    "boundary-report.json": "application/json",
    "cloud.ply": "application/octet-stream",
}
OPTIONAL_ASSETS = {"rough-room.svg": "image/svg+xml"}


class ReconstructionCatalog:
    def __init__(self, root: Path, generated_root: Path | None = None):
        self.root = root.resolve()
        self.roots = list(dict.fromkeys([self.root, (generated_root or root).resolve()]))

    def read(self, result_id):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", result_id):
            raise WebError("NOT_FOUND", "Reconstruction not found", 404)
        folder = next(
            (
                (root / result_id).resolve()
                for root in self.roots
                if (root / result_id).resolve().is_relative_to(root)
                and (root / result_id / "manifest.json").is_file()
            ),
            None,
        )
        if folder is None:
            raise WebError("NOT_FOUND", "Reconstruction not found", 404)
        try:
            manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
            if manifest["schema"] != "holo-reconstruction-viewer-v1":
                raise ValueError("Unsupported viewer schema")
            names = set(manifest["artifact_sha256"])
            if not set(ASSETS) <= names or not names <= set(ASSETS) | set(OPTIONAL_ASSETS):
                raise ValueError("Unexpected assets")
            integrity = BundleIntegrity(folder, manifest["artifact_sha256"])
            integrity.verify_all()
            scene = json.loads(integrity.path("scene.json").read_text(encoding="utf-8"))
            return integrity, {
                "id": result_id,
                "label": scene["label"],
                "point_count": scene["point_count"],
                "source_voxel_points": scene["source_voxel_points"],
                "selected_views": scene["selected_views"],
                "geometry_source": scene.get("geometry_source", "RGB_DENSE_STEREO"),
                "physical_accuracy": "UNVERIFIED",
            }
        except (KeyError, ValueError, OSError) as error:
            raise WebError(
                "RECONSTRUCTION_INVALID", "Stored viewer result is invalid", 409
            ) from error

    def list(self):
        folders = [
            path
            for root in self.roots
            if root.is_dir()
            for path in root.iterdir()
            if path.is_dir()
            and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", path.name)
            and (path / "manifest.json").is_file()
        ]
        return [
            self.read(path.name)[1]
            for path in sorted(
                folders,
                key=lambda p: ((p / "manifest.json").stat().st_mtime_ns, p.name),
                reverse=True,
            )
        ]


def reconstruction_router(root, generated_root=None):
    catalog = ReconstructionCatalog(root, generated_root)
    router = APIRouter(prefix="/api/reconstructions")

    @router.get("")
    def results():
        return catalog.list()

    @router.get("/{result_id}/{asset}")
    def asset(result_id: str, asset: str):
        if asset not in ASSETS and asset not in OPTIONAL_ASSETS:
            raise WebError("NOT_FOUND", "Viewer asset not found", 404)
        integrity, _ = catalog.read(result_id)
        if asset not in integrity.hashes:
            raise WebError("NOT_FOUND", "Viewer asset not found", 404)
        return FileResponse(
            integrity.path(asset),
            media_type=(ASSETS | OPTIONAL_ASSETS)[asset],
            headers={"Cache-Control": "no-store"},
        )

    return router

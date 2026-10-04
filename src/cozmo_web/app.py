"""HTTP boundary and app lifecycle. Domain work is delegated to job services."""

import json
import shutil
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated
from urllib.parse import urlparse

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import ValidationError
from starlette.background import BackgroundTask
from starlette.exceptions import HTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware

from cozmo_ingestion.errors import IngestionError
from cozmo_ingestion.media import find_ffmpeg
from cozmo_ingestion.multimodal.verify import verify_v2
from cozmo_ingestion.storage import BundleIntegrity, sha256
from cozmo_ingestion.verification import verify

from .automatic import backend_available, dense_available, enqueue_reconstruction, verify_automatic
from .config import Settings
from .errors import WebError
from .exports import ExportService
from .gaussians import gaussian_router
from .jobs import JobService
from .preprocessing import enqueue_preprocessing
from .reconstruction import reconstruction_router
from .reference_images import read_reference_image, save_reference_image
from .repository import DataLock, JobRepository
from .runner import ProcessRunner
from .schemas import PhotosReference, Reference
from .uploads import safe_name


class BodyLimitMiddleware:
    """Count ASGI body bytes before multipart parsing/spooling consumes them."""

    def __init__(self, app, limit: int, root: Path):
        self.app, self.limit, self.root = app, limit, root

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = dict(scope["headers"])
        try:
            declared = int(headers.get(b"content-length", b"0"))
        except ValueError:
            declared = self.limit + 1
        if declared < 0 or declared > self.limit:
            return await JSONResponse(
                {
                    "error": {
                        "code": "UPLOAD_TOO_LARGE",
                        "message": "Upload exceeds the configured limit",
                    }
                },
                status_code=413,
            )(scope, receive, send)
        if scope["method"] == "POST" and scope["path"] == "/api/jobs":
            if shutil.disk_usage(self.root).free < (declared or self.limit) * 2 + 10 * 1024**2:
                return await JSONResponse(
                    {"error": {"code": "STORAGE_FULL", "message": "Not enough upload storage"}},
                    status_code=507,
                )(scope, receive, send)
        used = 0

        async def limited_receive():
            nonlocal used
            message = await receive()
            used += len(message.get("body", b""))
            if used > self.limit:
                raise HTTPException(413, "Upload exceeds the configured limit")
            return message

        await self.app(scope, limited_receive, send)


def create_app(settings: Settings | None = None, runner=None) -> FastAPI:
    settings = settings or Settings.from_env()
    repository = JobRepository(settings.data_root, settings.queue_limit)
    jobs = JobService(repository, runner or ProcessRunner(settings))
    exports = ExportService()

    @asynccontextmanager
    async def lifespan(app):
        lock = DataLock(settings.data_root)
        jobs.start()
        try:
            yield
        finally:
            jobs.close()
            lock.close()

    app = FastAPI(title="Holo capture ingestion", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.repository, app.state.jobs = repository, jobs
    app.include_router(
        gaussian_router(
            settings.gaussian_root or settings.data_root / "gaussians",
            settings.reconstruction_root or settings.data_root / "reconstructions",
        )
    )
    app.include_router(
        reconstruction_router(
            settings.reconstruction_root or settings.data_root / "reconstructions",
            settings.data_root / "reconstructions",
        )
    )
    app.add_middleware(BodyLimitMiddleware, limit=settings.request_limit, root=settings.data_root)
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "testserver"]
    )

    @app.exception_handler(WebError)
    async def web_error(request, error):
        return JSONResponse(
            {"error": {"code": error.code, "message": error.message}}, status_code=error.status
        )

    @app.exception_handler(IngestionError)
    async def ingestion_error(request, error):
        return JSONResponse(
            {
                "error": {
                    "code": error.code,
                    "message": "Stored capture failed integrity verification",
                }
            },
            status_code=409,
        )

    @app.exception_handler(HTTPException)
    async def http_error(request, error):
        return JSONResponse(
            {"error": {"code": "REQUEST_REJECTED", "message": str(error.detail)}},
            status_code=error.status_code,
        )

    @app.get("/api/health")
    def health():
        try:
            ffmpeg, ffprobe = find_ffmpeg(settings.ffmpeg)
            probe = settings.data_root / (".health-" + uuid.uuid4().hex)
            probe.write_bytes(b"ok")
            probe.unlink()
            from cozmo_reconstruction.dense.runtime import runtime_status

            runtime = runtime_status()
            return {
                "status": "ready",
                "ffmpeg": ffmpeg.name,
                "ffprobe": ffprobe.name,
                "max_upload_bytes": settings.request_limit,
                "max_queue": settings.queue_limit,
                "automatic_reconstruction": backend_available(),
                "dense_reconstruction": runtime["available"],
                "dense_backend": runtime["backend"],
                "dense_unavailable_reason": runtime["reason"],
                "reconstruction_mode": settings.reconstruction_mode,
                "photos_available": True,
            }
        except (OSError, IngestionError):
            return JSONResponse(
                {
                    "status": "unavailable",
                    "message": "FFmpeg/FFprobe and writable data storage are required",
                },
                status_code=503,
            )

    @app.post("/api/jobs", status_code=202)
    async def submit(
        request: Request,
        files: Annotated[list[UploadFile], File()],
        label: Annotated[str, Form()] = "",
        modality: Annotated[str, Form()] = "video",
        reference: Annotated[str, Form()] = "",
        reference_image: Annotated[UploadFile | None, File()] = None,
        automatic_reconstruction: Annotated[bool, Form()] = True,
        reconstruction_mode: Annotated[str, Form()] = "auto",
    ):
        origin = request.headers.get("origin")
        if origin and urlparse(origin).hostname not in {"localhost", "127.0.0.1"}:
            raise WebError("ORIGIN_DENIED", "Upload from an unsupported origin", 403)
        if modality not in {"video", "photos"}:
            raise WebError("INVALID_MODALITY", "Select video or photos", 400)
        if reconstruction_mode not in {"auto", "dense", "preview"}:
            raise WebError("INVALID_RECONSTRUCTION_MODE", "Select auto, dense or preview", 400)
        if (
            modality == "video"
            and automatic_reconstruction
            and reconstruction_mode == "dense"
            and not dense_available()
        ):
            raise WebError(
                "DENSE_CUDA_UNAVAILABLE",
                "Dense reconstruction is unavailable. Check system readiness before uploading.",
                503,
            )
        if len(label) > 120 or not files or len(files) > settings.member_limit:
            raise WebError("INVALID_INPUT", "Use a short label and one complete export")
        declared_reference = None
        if modality == "photos":
            if reference:
                try:
                    declared_reference = PhotosReference.model_validate_json(
                        reference
                    ).declaration()
                except ValidationError as error:
                    raise WebError(
                        "INVALID_REFERENCE", "Reference dimensions must be positive"
                    ) from error
            if reference_image is not None:
                raise WebError(
                    "INVALID_INPUT",
                    "Choose the reference from the uploaded room photos",
                    400,
                )
        elif reference:
            try:
                declared_reference = Reference.model_validate_json(reference).model_dump()
            except ValidationError as error:
                raise WebError(
                    "INVALID_REFERENCE",
                    "Reference dimensions and time interval must be positive and ordered",
                ) from error
        names, seen = [], set()
        for upload in files:
            relative = safe_name(upload.filename or "")
            if modality == "video" and len(relative.parts) != 1:
                raise WebError(
                    "INVALID_SELECTION", "Select files from one export without duplicate names"
                )
            if modality == "photos" and not relative.name.casefold().endswith(
                (".jpg", ".jpeg", ".png", ".zip")
            ):
                raise WebError(
                    "UNSUPPORTED_IMAGE_FORMAT",
                    "Photo tier accepts JPEG/PNG only; export HEIC/HEIF to JPEG first",
                )
            key = relative.as_posix().casefold()
            if key in seen:
                raise WebError(
                    "INVALID_SELECTION", "Select files from one export without duplicate names"
                )
            names.append(relative.as_posix())
            seen.add(key)
        if any(n.lower().endswith(".zip") for n in names) and len(names) != 1:
            raise WebError("INVALID_SELECTION", "Select one ZIP or the exported files, not both")
        estimated = int(request.headers.get("content-length", settings.request_limit))
        if shutil.disk_usage(settings.data_root).free < estimated * 2 + 10 * 1024**2:
            raise WebError("STORAGE_FULL", "Not enough storage for this capture", 507)
        job = repository.create(label.strip(), declared_reference, modality)
        folder = repository.folder(job["id"])
        total = 0
        try:
            for upload, name in zip(files, names, strict=True):
                target = folder / "incoming" / Path(name)
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open("xb") as destination:
                    while chunk := await upload.read(1024 * 1024):
                        total += len(chunk)
                        if total > settings.request_limit:
                            raise WebError(
                                "UPLOAD_TOO_LARGE", "Upload exceeds the configured limit", 413
                            )
                        destination.write(chunk)
            image = await save_reference_image(reference_image, folder) if reference_image else None
            total += image["size_bytes"] if image else 0
            repository.update(
                job["id"],
                state="QUEUED",
                input_files=names,
                upload_bytes=total,
                reference_image=image,
                automatic_reconstruction=automatic_reconstruction if modality == "video" else False,
                reconstruction_mode=settings.reconstruction_mode
                if reconstruction_mode == "auto"
                else reconstruction_mode,
            )
        except Exception:
            repository.fail(
                job["id"], "UPLOAD_FAILED", "Upload failed. Submit the complete export again."
            )
            shutil.rmtree(folder / "incoming", ignore_errors=True)
            raise
        finally:
            for upload in files:
                await upload.close()
            if reference_image:
                await reference_image.close()
        return {"id": job["id"], "state": "QUEUED"}

    @app.get("/api/jobs")
    def list_jobs():
        return repository.list()

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str):
        return repository.get(job_id)

    @app.post("/api/jobs/{job_id}/preprocess", status_code=202)
    def preprocess(
        job_id: str, request: Request, automatic_reconstruction: Annotated[bool, Form()] = True
    ):
        origin = request.headers.get("origin")
        if origin and urlparse(origin).hostname not in {"localhost", "127.0.0.1"}:
            raise WebError("ORIGIN_DENIED", "Request from an unsupported origin", 403)
        if repository.get(job_id).get("modality", "video") != "video":
            raise WebError(
                "NOT_IMPLEMENTED_FOR_MODALITY",
                "Photo jobs stop after verified ingestion; preprocessing is not available",
                409,
            )
        job = enqueue_preprocessing(
            repository, settings, job_id, automatic_reconstruction=automatic_reconstruction
        )
        return {"id": job["id"], "state": job["state"]}

    def completed(job_id: str) -> Path:
        job = repository.get(job_id)
        if job["state"] != "SUCCEEDED" and not (job["state"] == "FAILED" and job.get("summary")):
            raise WebError("RESULT_NOT_READY", "A verified result is not available yet", 409)
        return repository.folder(job_id)

    @app.post("/api/jobs/{job_id}/reconstruct", status_code=202)
    def reconstruct(job_id: str, request: Request, reconstruction_mode: str = Form("auto")):
        origin = request.headers.get("origin")
        if origin and urlparse(origin).hostname not in {"localhost", "127.0.0.1"}:
            raise WebError("ORIGIN_DENIED", "Request from an unsupported origin", 403)
        if repository.get(job_id).get("modality", "video") != "video":
            raise WebError(
                "NOT_IMPLEMENTED_FOR_MODALITY",
                "Photo reconstruction is not available; the job stops after ingestion",
                409,
            )
        job = enqueue_reconstruction(repository, settings, job_id, reconstruction_mode)
        return {"id": job["id"], "state": job["state"]}

    def prepared(job_id: str) -> Path:
        from cozmo_preprocessing.verification import verify_preprocessing

        folder = completed(job_id)
        if not (folder / "preprocessing/manifest.json").is_file():
            raise WebError("RESULT_NOT_READY", "Preprocessing has not run for this capture", 409)
        verify_preprocessing(folder / "preprocessing", folder / "bundle", folder / "raw")
        return folder / "preprocessing"

    @app.get("/api/jobs/{job_id}/preprocessing-report")
    def preprocessing_report(job_id: str):
        return FileResponse(
            prepared(job_id) / "report.json",
            media_type="application/json",
            filename="preprocessing-report.json",
        )

    @app.get("/api/jobs/{job_id}/previews/{rank}")
    def preview(job_id: str, rank: int):
        from cozmo_preprocessing.verification import lines

        folder = completed(job_id) / "preprocessing"
        if not (folder / "manifest.json").is_file():
            raise WebError("RESULT_NOT_READY", "Preprocessing has not run", 409)
        # Verify only the preview and its source-bound manifest/index on image reads.
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        if manifest["source_manifest_sha256"] != sha256(folder.parent / "bundle/manifest.json"):
            raise WebError("SOURCE_CHANGED", "Capture storage has changed", 409)
        integrity = BundleIntegrity(folder, manifest["artifact_sha256"])
        views = lines(integrity.path("views.jsonl"))
        view = next((v for v in views if v["rank"] == rank), None)
        if view is None:
            raise WebError("NOT_FOUND", "Selected frame not found", 404)
        return FileResponse(
            integrity.path(view["thumbnail"]),
            media_type="image/jpeg",
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/api/jobs/{job_id}/report")
    def report(job_id: str):
        folder = completed(job_id)
        manifest = json.loads((folder / "bundle/manifest.json").read_text(encoding="utf-8"))
        if manifest.get("schema") == "canonical-capture-2":
            verify_v2(folder / "bundle", folder / "raw" if (folder / "raw").is_dir() else None)
        else:
            verify(folder / "bundle", folder / "raw")
            read_reference_image(folder)
            if (folder / "preprocessing").is_dir():
                prepared(job_id)
            verify_automatic(folder)
        return FileResponse(
            folder / "result.json", media_type="application/json", filename="validation-report.json"
        )

    @app.get("/api/jobs/{job_id}/download")
    def download(job_id: str):
        folder = completed(job_id)
        archive = exports.archive(folder)
        return FileResponse(
            archive,
            media_type="application/zip",
            filename=f"capture-{job_id[:8]}.zip",
            background=BackgroundTask(archive.unlink, missing_ok=True),
        )

    @app.get("/api/jobs/{job_id}/reference-image")
    def reference_photo(job_id: str):
        image = read_reference_image(completed(job_id))
        if image is None:
            raise WebError("NOT_FOUND", "No object photo was attached", 404)
        path, info = image
        return FileResponse(
            path,
            media_type=info["media_type"],
            filename=info["original_name"],
            content_disposition_type="inline",
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str):
        if path == "api" or path.startswith("api/"):
            raise WebError("NOT_FOUND", "API endpoint not found", 404)
        root = settings.static_root.resolve()
        target = (root / path).resolve()
        if not target.is_relative_to(root):
            raise WebError("NOT_FOUND", "Page not found", 404)
        if path and target.is_file():
            return FileResponse(target)
        if (root / "index.html").is_file():
            return FileResponse(root / "index.html")
        return JSONResponse(
            {"message": "API ready. Start the Vite frontend, or build frontend assets."},
            status_code=404,
        )

    return app


def factory():
    return create_app()

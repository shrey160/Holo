"""HTTP boundary and app lifecycle. Domain work is delegated to job services."""

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
from cozmo_ingestion.verification import verify

from .config import Settings
from .errors import WebError
from .exports import ExportService
from .jobs import JobService
from .reference_images import read_reference_image, save_reference_image
from .repository import DataLock, JobRepository
from .runner import ProcessRunner
from .schemas import Reference
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
            return {
                "status": "ready",
                "ffmpeg": ffmpeg.name,
                "ffprobe": ffprobe.name,
                "max_upload_bytes": settings.request_limit,
                "max_queue": settings.queue_limit,
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
        reference: Annotated[str, Form()] = "",
        reference_image: Annotated[UploadFile | None, File()] = None,
    ):
        origin = request.headers.get("origin")
        if origin and urlparse(origin).hostname not in {"localhost", "127.0.0.1"}:
            raise WebError("ORIGIN_DENIED", "Upload from an unsupported origin", 403)
        if len(label) > 120 or not files or len(files) > settings.member_limit:
            raise WebError("INVALID_INPUT", "Use a short label and one complete export")
        declared_reference = None
        if reference:
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
            if len(relative.parts) != 1 or relative.name.casefold() in seen:
                raise WebError(
                    "INVALID_SELECTION", "Select files from one export without duplicate names"
                )
            names.append(relative.name)
            seen.add(relative.name.casefold())
        if any(n.lower().endswith(".zip") for n in names) and len(names) != 1:
            raise WebError("INVALID_SELECTION", "Select one ZIP or the exported files, not both")
        estimated = int(request.headers.get("content-length", settings.request_limit))
        if shutil.disk_usage(settings.data_root).free < estimated * 2 + 10 * 1024**2:
            raise WebError("STORAGE_FULL", "Not enough storage for this capture", 507)
        job = repository.create(label.strip(), declared_reference)
        folder = repository.folder(job["id"])
        total = 0
        try:
            for upload, name in zip(files, names, strict=True):
                with (folder / "incoming" / name).open("xb") as destination:
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

    def completed(job_id: str) -> Path:
        if repository.get(job_id)["state"] != "SUCCEEDED":
            raise WebError("RESULT_NOT_READY", "A verified result is not available yet", 409)
        return repository.folder(job_id)

    @app.get("/api/jobs/{job_id}/report")
    def report(job_id: str):
        folder = completed(job_id)
        verify(folder / "bundle", folder / "raw")
        read_reference_image(folder)
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

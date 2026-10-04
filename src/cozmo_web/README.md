# Holo web service

**Current automatic workflow (2026-10-04):** `automatic.py` owns bounded orchestration, prepared-capture retry admission and source-bound download audits. New uploads accept multipart `automatic_reconstruction` (default true); unsupported adapters remain ingestion-only with a skip reason. `POST /api/jobs/{id}/reconstruct` queues an immutable child from verified prepared data, including retained prepared data after a later failure. GPU progress adds RECONSTRUCTING/DENSE_RECONSTRUCTING/EXTRACTING_SURFACES/ESTIMATING_ROOM/PUBLISHING. `RECONSTRUCTION_MODE` selects auto/dense/preview; required dense never silently falls back. Health reports usable CUDA; existing sparse results can start a separate dense child. Failed later-stage jobs can download verified inputs and retry. Catalogs combine read-only historical assets with writable generated results. [Detailed contract](../../AUTOMATIC_RECONSTRUCTION.md).


Preprocessing uses `preprocessing.py` to admit and execute independent child jobs from successful Sensor Recorder captures. `POST /api/jobs/{id}/preprocess` uses the existing queue/process/deadline; it never runs algorithms inside the HTTP request. Parents retain their original state/files. Child runs own portable copies plus a separate `preprocessing/` directory. Report/export endpoints run the derived audit; thumbnail routes verify source-bound selected IDs and hashes. [Contract and commands](../../PREPROCESSING.md).

Optional FastAPI service around the [ingestion core](../cozmo_ingestion/README.md). HTTP handlers receive files and query jobs; an isolated Python worker performs ingestion and source-value verification. Install with `web` and `reconstruct` extras for the automatic workflow. Native and Docker commands are in [WEB_SETUP.md](../../WEB_SETUP.md).

## Module ownership

| Module | Responsibility |
|---|---|
| `app.py` | App factory, lifecycle, HTTP routes, request limits and static frontend serving |
| `config.py`, `schemas.py`, `errors.py` | Validated settings/reference form and stable user-facing errors |
| `uploads.py` | Bound copying/extraction; reject unsafe paths, links, collisions and ambiguous sessions |
| `repository.py` | Atomic persisted job records, queue admission and single-instance data lock |
| `jobs.py` | One active processing slot, queued jobs and restart reconciliation |
| `runner.py` | Start isolated workers, poll phases, enforce deadlines and stop process trees |
| `worker.py` | Prepare raw input, bind annotations, run core ingestion and verify source values |
| `preprocessing.py` | Admit child jobs, audit/copy the parent capture and run/verify derived preprocessing |
| `reference_images.py` | Bound JPEG/PNG uploads, probe/decode checks, video/hash binding and integrity-checked image access |
| `exports.py` | Verify stored integrity and assemble portable downloads |
| `cli.py` | `cozmo-web` startup, optional reload, temporary storage and native static-root discovery |

## HTTP contract

| Method and route | Result |
|---|---|
| `GET /api/health` | Tool/storage readiness and admission limits |
| `POST /api/jobs` | Multipart `files`, optional `label` and JSON-string `reference`; accepted job ID/state with HTTP 202 |
| `GET /api/jobs` | Most recent 50 jobs |
| `GET /api/jobs/{id}` | Persisted job state, findings/summary or failure |
| `GET /api/jobs/{id}/report` | Verified result JSON attachment |
| `GET /api/jobs/{id}/download` | Verified raw/annotation/reference/bundle ZIP attachment |
| `GET /api/jobs/{id}/reference-image` | Integrity-checked photo for a completed job; 404 when absent |
| `POST /api/jobs/{id}/preprocess` | Queue an independent child of a successful Sensor Recorder capture; HTTP 202 |
| `GET /api/jobs/{id}/preprocessing-report` | Verified derived preprocessing report attachment |
| `GET /api/jobs/{id}/previews/{rank}` | Integrity-checked thumbnail for an admitted selected source frame rank |

`POST /api/jobs` also accepts a separate optional `reference_image` multipart file. It is not mixed into the original export or supplied as a geometry observation. JPEG/PNG uploads are limited to 10 MiB and 40 million pixels; [FFprobe](https://ffmpeg.org/ffprobe-all.html) inspects the grid/codec, then FFmpeg checks decoding in the isolated worker. `reference/metadata.json` binds the retained image bytes to the source video; job records retain its metadata hash. Old jobs without photos remain supported.

Reference form fields are `width_cm`, `height_cm`, `start_seconds`, `end_seconds` and `placement`. The worker converts dimensions to metres and binds the declaration to the video hash; it does not detect corners or apply scale. [Reference annotations](../../capture_annotations/README.md).

Normal state progression: `RECEIVING` Ã¢â€ â€™ `QUEUED` Ã¢â€ â€™ `VALIDATING_INPUT` Ã¢â€ â€™ `INGESTING` Ã¢â€ â€™ `VERIFYING` Ã¢â€ â€™ `SUCCEEDED`. Failures become `FAILED`. Success requires the worker to exit with a verified result. Unfinished jobs return 409; a failed later stage with a verified retained result can download its audited inputs.

Preprocessing jobs use `QUEUED` Ã¢â€ â€™ `VERIFYING` (parent audit) Ã¢â€ â€™ `PREPROCESSING` Ã¢â€ â€™ `VERIFYING` (derived audit) Ã¢â€ â€™ `SUCCEEDED`, with failures reported as `FAILED`. Their result summary includes review readiness separately from job success: a verified run can still require review before reconstruction. Portable downloads include the child-owned source layout and `preprocessing/` artifacts.

## Storage and operations

Native storage defaults to `outputs/web-data`; Docker uses `/data` in the named capture volume. Each `jobs/<id>/` directory holds its atomic `job.json`, original input/raw files, optional annotations, published `bundle/`, worker phase/log records and result/verification JSON. Temporary download archives are removed after the response completes.

Run one server/one Uvicorn worker per `DATA_ROOT`. Startup fails if another process owns the data lock; interrupted receiving/processing jobs become failed, untouched queued jobs resume, and completed records persist. Resubmission creates a fresh job. Shutdown and deadlines stop the worker/media process tree. Completed and failed storage has no automatic retention policy.

The default limits are 1 GiB per HTTP request, 2 GiB expanded input, 25,000 file/archive members (needed for supplied depth/confidence ZIPs), four waiting jobs plus one active slot, and 600 seconds for ingestion-only workers or 3600 seconds for automatic/reconstruction workers. See [configuration](../../WEB_SETUP.md#configuration-and-boundaries) before changing them. Limits are not long-capture capacity benchmarks.

The app is a local prototype with loopback host ports and no multi-user authentication. Keep processing rules in the core, queue/storage rules here and presentation rules in the [frontend](../../frontend/README.md). [Tests](../../tests/README.md) cover these boundaries.
# Read-only reconstruction presentation

`reconstruction.py` owns a source-independent published-asset catalog and router at `/api/reconstructions`. It validates result IDs, exact schema/asset allowlist, path confinement and artifact hashes; no raw directories or geometry backend are exposed through HTTP. `RECONSTRUCTION_ROOT` configures an optional read-only asset directory, otherwise `DATA_ROOT/reconstructions` is used. [Publication and native/Docker viewer setup](../../RECONSTRUCTION_VIEWER.md).

## Optional Gaussian appearance

See [Gaussian experiment](../../GAUSSIANS.md) for audited input preparation, isolated GPU training, a separately published hash-bound scene and Holo browser viewing. Structural boundaries and physical calibration remain unchanged.


The reconstruction catalog requires the original eight signed assets and optionally admits signed `rough-room.svg` for complete approximate plans. Missing optional assets return 404; unknown names and tampered assets remain denied. [Rough-plan publication](../../FLOORPLAN_OPTIMIZATION.md).

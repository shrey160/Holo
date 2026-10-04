# Docker and capture workspace verification

Current extension P2MODAL-002 (2026-10-04) adds the Holo **Photos** modality for the [three-modality plan](../../INPUT_MODALITIES_PLAN.md): Video/Photos selector, room folder/loose JPEG-PNG/ZIP upload preserving room names, EXIF/orientation evidence, optional declared reference, a photos result view and portable download. Photo jobs stop after verified ingestion (`NOT_IMPLEMENTED_FOR_MODALITY` for preprocessing/reconstruction); the legacy video path is unchanged. Observed: native HTTP upload of the real eight `test_data/Room-1` photos produced a `canonical-capture-2` bundle whose `sources/` hashes equal both the CLI bundle and the originals; Docker CLI and Docker HTTP uploads matched the same hashes (HTTP download 200, 62,322,533 bytes); a real legacy video export ingested through the API (1,756 frames, `canonical-capture-1`). Six new web tests; full suite 168. HEIC/HEIF is rejected with an actionable message; no Pillow dependency was added. Automatic video reconstruction was not re-run end-to-end this turn (covered by the automatic-workflow tests).

Current extension P2PRE-001 is delivered: [RGB/pose/IMU preprocessing](../ingestion/PREPROCESSING.md), 53 Windows/Linux tests, two native/Docker child runs, gallery/pagination and verified portable downloads. Historical milestone statements below retain their original scope and test counts.

2026-10-03 (Asia/Calcutta). P2W-002 implementation complete for the existing Sensor Recorder iOS ingestion contract. [Setup](WEB_SETUP.md), [architecture](../architecture/ARCHITECTURE.md), [research plan](DOCKER_WEB_PLAN.md).

## Delivered

Follow-up P2PHOTO-001 (2026-10-03): guide now uses one object at the video opening only and recommends iPhone 15 and above without naming the test phone in the UI. Added an optional independent JPEG/PNG photo picker with preview/removal. Worker validates encoding, pixel grid and decode; original bytes and metadata hashes are bound to the capture video. Results display the photo and portable downloads include `reference/`. No dimensions, detection or scale are inferred from uploading an image.

The current 34-test suite passed on Windows and Linux (four additional photo transport/format/limit/binding/export-integrity cases). A browser upload of the real single-room ZIP plus a JPEG extracted from its opening succeeded without a dimension declaration: 1,756 source frames and all 16 artifacts verified. The saved-photo endpoint returned identical bytes; the downloaded ZIP passed CRC, retained the exact JPEG/video binding and reverified against raw values after extraction. Native FFmpeg also validated a synthetic PNG. [Photo validation ledger](../../outputs/reference-photo-evidence/ledger.json). The JPEG test fixture is an opening video frame, not a newly captured independent object photograph. Historical P2W-002 evidence below remains preserved.

- React/TypeScript/Vite frontend with capture-guide and input/validation tabs. The guide reads `capture.md`; settings/protocol are not maintained in a second source. Complete ZIP/multi-file uploads, optional centimetre/time-window reference declarations, upload progress, persisted job history, findings and verified report/capture downloads.
- Optional FastAPI web package around the existing ingestion APIs. Bounded multipart/extraction, cross-platform path/link/collision checks, disk checks, one isolated job slot, atomic job records, single-instance data lock, interruption reconciliation, worker deadlines and process-tree shutdown.
- Digest-pinned multi-stage Docker image: compiled frontend, Python/uv-installed non-editable package, FFmpeg/FFprobe, non-root UID/GID 10001. One Compose service with loopback port, health check, child reaping and persistent named capture volume. Native uv/Vite and native compiled modes remain available.
- Portable UTF-8/LF canonical JSON/JSONL/Markdown and POSIX root hints. CSV remains explicitly CRLF; readers accept historical Windows hints. No observation normalization, geometry scale or source bytes were changed.

## Checks and evidence

Thirty Python behavioral tests passed on Windows/Python 3.12.14 and the Linux Docker checks stage with locked dependencies. These include the original 17 core cases plus archive traversal/case collisions/links/expansion limits, no-Content-Length request limits, reference binding, storage lock/queue/restart behavior, unready downloads, annotation integrity, legacy hints and actual child-process-tree termination. Ruff lint/format and frontend type checking/build/format passed.

Both real captures passed native HTTP and Docker HTTP upload, full ingestion, independent source-value verification and portable archive extraction/reverification:

| Capture | RGB/K/pose records | Windows vs Linux content | Downloaded archive |
|---|---:|---|---|
| `single_room` | 1,756 | All 16 artifact hashes and manifests identical | ZIP CRC and verifier passed |
| `double_room` | 3,949 | All 16 artifact hashes and manifests identical | ZIP CRC and verifier passed |

Native used FFmpeg 8.1.2; Linux runtime used Debian FFmpeg 5.1.9. Native single-room used ZIP selection; native double-room used separate exported files. Docker used both ZIPs. Per-frame intrinsics/poses, all sensor values and source hashes are preserved; reference remains a declaration with localization/scale correction NOT_RUN. Both malformed-ZIP jobs failed and download attempts returned 409.

An actual browser upload through Vite's proxy to the native API succeeded with 1,756 frames; guide navigation, reference form, status/findings, draft preservation across tabs and a validation-JSON browser download were checked. Phone-sized layout was checked for horizontal overflow. UI screenshots are retained in ignored `outputs/`. Docker recreation preserved both successful jobs and manifests; their report/archive endpoints passed again with the updated service. Container ran as UID/GID 10001 and was healthy.

Existing CLI commands also ingested both recordings with their original annotation files. The historical P2I-001 bundles still passed verification. All 16 artifacts retain equal parsed/text content when universal newlines and path-hint separators are normalized. Ten historical artifacts per capture intentionally changed bytes due to LF serialization/root hints; historical outputs were preserved. Current core fingerprint: `8b34506a8565fe3eb67f40028881ad10d5fc7ef365e75fd464792f078b05822a`.

Wheel and source archive audits exclude captures, generated outputs, environments, caches and frontend dependencies. The source archive includes frontend source/lockfile, Docker configuration, guide and setup documentation. Its extracted copy independently installed into its own uv environment, passed all 30 tests and built the frontend using the locked npm dependencies. [Packaging ledger](../../outputs/web-packaging-validation.json).

Local evidence (generated/ignored, not shipped as test captures):

- [Native HTTP runs](../../outputs/native-evidence/ledger.json), [Docker HTTP runs](../../outputs/docker-evidence/ledger.json), [cross-platform equality](../../outputs/cross-platform-validation.json).
- [Historical compatibility](../../outputs/legacy-compatibility.json), [recreation/download checks](../../outputs/docker-restart-validation.json).
- `outputs/verify_web.py` and `outputs/compare_baseline.py` reproduce the local real-data checks. Unit tests ship under `tests/`; Docker's `checks` stage reproduces Linux test execution without embedding real captures.

## Limits

Validated on Windows and Linux amd64 with the supplied short captures. macOS, ARM images, large/long captures, sustained multi-client load, uncached clean-machine setup, automatic retention and distributed execution are untested or outside this prototype. Admission limits are not capacity benchmarks. API storage is single-instance/local; host ports bind to loopback. Runtime apt package resolution remains repository-dependent even though base images and application dependency lockfiles are pinned.

Warm local upload/ingestion/download checks completed in about 7 seconds for single-room and 14 seconds for double-room; these are observations, not performance guarantees. Starlette currently emits a deprecation notice for the locked httpx test adapter; the tests pass on both systems.

No physical calibration/registration/synchronization, metric accuracy, grounding algorithm, preprocessing, reconstruction, Android or new capture-tier support is established by this work. Raw inputs/prototype-1 and historical bundles are preserved. Implementation/photo verification occurred before the user-authorized local milestone commit. No push, publication or third-party capture upload.

## Provided dataset extension â€” P2DATA-001

Holo now accepts the original three Stray-style capture ZIPs from `test_data/drive_download`, preserving native CSVs and depth/confidence while excluding measured depth from assisted RGB. Seven source/association/role/archive tests extend the Windows/Linux suite to 41. Source-format behavior and actual capture/browser evidence are recorded in [SUPPLIED_DATA.md](../ingestion/SUPPLIED_DATA.md). Older 30/34-test and Sensor Recorder capture evidence above remain historical.
## Preprocessing extension: 2026-10-03

P2PRE-001 adds independent Sensor Recorder preprocessing jobs, selected-frame previews, pagination, reports and portable derived exports. All 53 tests pass on Windows/Linux; TypeScript/Vite and Ruff checks pass. Both native/Docker runs retain 106/240 selected views, 98/209 supported links and 7/30 unresolved links, without LiDAR or grounding measurements. Browser-submitted child jobs succeeded and their parent captures remained intact. Downloaded double-room ZIP passed CRC and raw/source/derived audits; K/pose/native-IMU/interval hashes match native outputs. [Full evidence and limitations](../ingestion/PREPROCESSING.md), [screenshot](../../outputs/holo-preprocessing.png).

Earlier results below retain their original verification counts and preprocessing boundaries.

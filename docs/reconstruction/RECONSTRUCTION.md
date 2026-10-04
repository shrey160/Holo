# Fixed-pose sparse reconstruction

**Current automatic workflow (2026-10-04):** The established fixed-pose sparse pipeline now also runs inside Holo automatic jobs with up to 80 views after the opening five seconds. Audited geometry is published as a sparse 3D preview and coarse rectangular coverage envelope. [Workflow and executed evidence](../../AUTOMATIC_RECONSTRUCTION.md).


Implemented 2026-10-03 after [the research plan](RECONSTRUCTION_PLAN.md). This stage consumes verified Sensor Recorder preprocessing and produces inspectable sparse geometry with source-bound feature/track audits. Dense depth, floorplan extraction and Holo reconstruction jobs are subsequent stages. The existing Holo ingestion/preprocessing app remains unchanged.

## Run natively

From `proto-2`:

```shell
uv sync --locked --extra reconstruct
uv run --locked --extra reconstruct cozmo-reconstruct --help
uv run --locked --extra reconstruct cozmo-reconstruct outputs/single-room-preprocessing-final outputs/single-room-cli-v2 outputs/single-room-sparse --source ../test_data/iphn-17/single_room
```

Arguments are prepared bundle, original ingestion bundle and a **new** output folder. `--source` rebases the raw capture; otherwise ingestion root hints apply. Only selected prepared views are admitted. Default selection uses all prepared views (3â€“300); disconnected views remain explicit. A JSON ascending list can select ranks with `--ranks-file selection.json`. An object can supply a list via `--ranks-key ranks`. If the object declares `source_manifest_sha256`, it must match the preprocessing manifest.

For the recorded research selections, the ignored local proposal has `seed_ranks` (24) and `full_trial_component_ranks` (100). Example:

```shell
uv run --locked --extra reconstruct cozmo-reconstruct outputs/single-room-preprocessing-final outputs/single-room-cli-v2 outputs/single-room-sparse-100 --source ../test_data/iphn-17/single_room --ranks-file outputs/preconstruction-review-v1/single-trial-input-proposal.json --ranks-key full_trial_component_ranks
uv run --locked --extra reconstruct cozmo-reconstruct outputs/single-room-preprocessing-final outputs/single-room-cli-v2 outputs/single-room-sparse-100 --source ../test_data/iphn-17/single_room --verify-only
```

The proposal and recordings are private local evidence, not shipped sample data. On another machine ingest/preprocess its own complete export, then use all prepared views or its own rank selection. See [preprocessing setup](../ingestion/PREPROCESSING.md).

Use `--extra web --extra reconstruct` when one environment needs both features; a later uv sync with fewer extras can remove optional dependencies. PyCOLMAP is pinned to 4.2.1 in `uv.lock`. Executed platforms use Python 3.12; broader interpreter/platform metadata is not a tested guarantee.

## CPU Docker CLI

```shell
docker build --target reconstruction -t holo-reconstruction:0.2.0 .
```

The image includes the optional CPU backend and CLI, independently of the running web service. Mount the workspace/captures read-only at `/workspace` and a new writable results folder at `/results`, then pass container paths. For example, with a PowerShell variable pointing to the resolved assignment workspace and an existing `proto-2/outputs/docker-results` folder:

```powershell
$captureWorkspace = (Resolve-Path ..).Path
$captureResults = (Resolve-Path outputs/docker-results).Path
docker run --rm --mount "type=bind,source=$captureWorkspace,target=/workspace,readonly" --mount "type=bind,source=$captureResults,target=/results" holo-reconstruction:0.2.0 /workspace/proto-2/outputs/single-room-preprocessing-final /workspace/proto-2/outputs/single-room-cli-v2 /results/single-room-sparse --source /workspace/test_data/iphn-17/single_room
```

No GPU is required. The reconstruction target is a batch CLI; it does not run Holo or expose a port. Existing `docker compose` behavior and stored captures are preserved. Neither native nor Docker CPU wheels establish a usable CUDA dense-stereo path.

## System design and input contract

The sibling [reconstruction package](../../src/cozmo_reconstruction/README.md) has no HTTP/frontend imports. A typed immutable request/policy and injected backend separate source admission, camera conversion, backend lifecycle, geometric analysis and publication.

1. `PreparedInput` audits all original/canonical observations and derived identities. It admits selected JPEG pixels, exact source K/optical camera-to-world records and existing flags/gyro statistics for diagnostics. It never supplies capture depth/confidence, reference dimensions/photo or evaluation geometry to the backend. IMU is not re-integrated.
2. Camera conversion inverts the canonical optical camera-to-world matrix once. The PINHOLE approximation preserves per-frame focal lengths/principal points and source metre/world gauge, with distinct camera records. No extra ARKit axis flip, pose optimization, room recentering or scale fit runs.
3. CPU SIFT extraction at the native grid, capped at 4,096 features per image, precedes temporal/revisit matching. Up to 24 views use exhaustive matching; larger sets use an eight-view forward window and up to six pose-compatible revisits per view (>=2 seconds apart, <2 m and <40 degrees). These are bounded heuristics, not exhaustive loop closure. Four CPU threads and seed 42 are recorded.
4. PyCOLMAP runs in a separate process with a default 600-second total backend timeout. The pinned options fix existing frames, cameras and rigs, disable camera/sensor refinement and intrinsic refinement, and snapshot cameras before/after. Unexpected camera movement prevents publication. Image IDs can differ with parallel extraction; source rank/name mappings are authoritative.
5. Preserve all backend candidate tracks, then accept only unique-image tracks with at least three observations, positive optical depth, >=1.5-degree maximum pairwise ray angle and <=4-pixel error for every observation. Rejected counts/reasons remain inspectable. These filters select a consistent subset; low residuals on that subset do not establish correctness of all scene content.
6. Re-audit sources, verify binary camera/point records and exact database keypoint lineage, recompute geometry reports and publish atomically. Existing outputs are rejected. Crashes/timeouts leave failed staging diagnostics and no published result.

The source export's exact pixel-center convention and distortion remain **UNVERIFIED**. Default `--principal-point-shift 0` preserves exported numerical principal points while treating them as COLMAP corner-origin coordinates. `--principal-point-shift 0.5` is an explicitly recorded alternate OpenCV-center hypothesis, not automatic calibration. Analytic projection tests exercise conversion; physical phone calibration remains absent. The executed trials below use shift 0.

## Outputs and review

- `manifest.json`, `policy.json`, `input_mapping.json`: source hashes, exact original K/poses, selection, input boundary and source-code fingerprint.
- `images/`: byte-identical copies of admitted prepared JPEGs; no new crop, rescale, orientation change or encoding.
- `database.db`, `pairs.txt`, `pair_geometry.json`: native features, candidate schedule and backend two-view geometry classifications.
- `initial_model/`, `model/`, `cameras_before.json`, `cameras.json`: supplied and triangulated models, fixed-camera audit evidence; final model has binary and text exports.
- `candidate_points.jsonl`, `points.jsonl`, `cloud.ply`: candidate/accepted track partition, contributing image/keypoint IDs and pixels, source-world coloured points.
- `report.json`, `preview.svg`, `backend.json`, `backend.log`: geometric quality, orthogonal camera/point views, options/versions/timings and native backend diagnostics.

`SUPPORTED` means the proposed image/track signal passes >=70% image support and largest-component coverage, median residual <=2 px and p90 <=4 px. It does **not** mean a room is complete or accurately measured. All results remain `REVIEW_REQUIRED`. View previews together with source images; matching on furniture/reflections/moving objects and sparse blank walls require architectural review. SVG central-98% display clipping does not alter the PLY/model.

## Executed single-room evidence

| Trial | Valid points / candidates | Images with valid tracks | Largest track component | Median / p90 residual | Backend time |
|---|---:|---:|---:|---:|---:|
| Windows 24-view smoke | 338 / 476 | 13 / 24 | 6 / 24 | 1.99 / 3.42 px | 20.9 s |
| Windows 100-view component | 15,141 / 19,421 | 100 / 100 | 100 / 100 | 1.21 / 2.76 px | 102.9 s |
| Docker Linux 100-view component | 15,171 / 19,461 | 100 / 100 | 100 / 100 | 1.21 / 2.76 px | 51.6 s |

Final v2 reruns overlapped native/Docker work, so timings reflect shared CPU contention and are not a platform speed comparison. Times measure the backend, not total source auditing/copying/publication or a clean-machine benchmark. CPU implementation/order and platform differences change IDs/matches/point counts; cross-platform byte equality is not claimed. Both actual 100-view models pass source, camera, accepted-track and feature-lineage verification. The 24-view set is too sparse to maintain full connected geometry; nearby prepared frames resolve this in the 100-view trial. Six excluded research ranks are 855, 1695, 1710, 1725, 1740 and 1755; original/prepared observations remain unchanged.

Orthogonal visual review shows useful spatial structure and surface fragments, with incomplete architectural boundaries. No wall/ceiling dimensions, openings, floor polygons or dense-surface accuracy were inferred. The next geometry milestone is a bounded dense single-room experiment; the double-room connection follows after interpreting its architectural support.

One initial Windows attempt failed after triangulation while collecting statistics because `Database.num_keypoints` is a method in the pinned API. The adapter was corrected and rerun in a new stage; the failed evidence was retained. A sandbox temporary-directory restriction affected an initial test invocation; fixtures passed outside that restriction. No input repair or deletion was needed.

Local evidence: [Windows smoke](../../outputs/single-room-sparse-24-v2/report.json), [Windows full](../../outputs/single-room-sparse-100-v2/report.json), [Linux full](../../outputs/linux-reconstruction/single-room-sparse-100-v2/report.json), [preview PNG](../../outputs/reconstruction-evidence/single-room-sparse-100.png). These ignored outputs/private inputs are not distributed in source packages.

Meaningful tests cover optical transforms and pixel shifts, nonrigid/invalid cameras, pure rotation/negative depth/conflicting tracks, source tampering/selection boundaries, failed atomic publication, revisit pairing, policy/camera-movement rejection, analytic recovery of 50 known points by the actual triangulator, and a zero-parallax end-to-end result plus repeated byte-preserving verification and overwrite/export-tamper rejection. [Test guide](../../tests/README.md).

The complete **62-test suite passes on Windows and Docker Linux** (53 earlier cases plus nine reconstruction cases). Ruff lint/format passes; wheel/source builds succeed. Packaging keeps original captures, outputs, environments and dependency caches excluded. No frontend behavior was changed or new browser reconstruction flow claimed.

Final read-back found that opening published databases through PyCOLMAP changes database bytes. Verification now uses read-only SQLite and explicitly closes the handle before publication; it rechecks all artifact hashes afterward. Fresh v2 outputs passed repeated verification with every output byte unchanged. Earlier v1 outputs remain preserved as superseded diagnostic evidence and must not be used as verified deliverables. [Final audit ledger](../../outputs/reconstruction-evidence/validation.json).

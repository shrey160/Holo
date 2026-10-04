**Modality ingestion checks (2026-10-04):** Nineteen cases in `test_multimodal.py` cover the canonical-capture-2 foundation and photo ingestion: unknown-schema rejection, v1 catalog dispatch, null K/pose documents, referential integrity, safe paths, source mutation, deterministic manifests, output/path guards, EXIF/orientation recording, no-EXIF JPEG/PNG, corrupt images, unsupported phone formats, duplicate-content identity, filename/EXIF time discrepancy, out-of-profile counts, derived multi-room membership, declared reference binding without scale, portable re-verification and the real read-only `test_data/Room-1` fixture. Six cases in `test_web_photos.py` cover the Holo photo tier. Ten cases in `test_lidar.py` cover raw-depth admission: convention provenance, preserved poses/K without a second axis flip, absent confidence, units flags, invalid-sample counts, missing depth maps, mismatched depth/confidence grids, incomplete confidence and wrong depth encoding. Full suite: 178 cases. Real image/depth inspection uses synthetic builders; real photo/LiDAR/video and Docker runs are recorded separately.

**Dense automation regression checks (2026-10-04):** Seven cases cover usable CUDA admission, no silent downgrade, dense failure containment, source-bound track support pruning, floor/table selection and missing-floor rejection. Real GPU inference is checked separately from synthetic/mocked tests.

Current automatic-workflow suite: **136 cases pass on Windows and Linux**. Eleven new cases cover automatic upload opt-out, verified preprocessing handoff, stage ordering/failure gating, unsupported formats, prepared retries/idempotency, restart failure persistence, source retention, sparse rigid coordinates, insufficient support and source-bound portable publication/tamper rejection. Real Docker/native HTTP trials are recorded separately in [AUTOMATIC_RECONSTRUCTION.md](../AUTOMATIC_RECONSTRUCTION.md). Earlier counts below are historical milestones.

Current furnished-plan suite: **125 cases**. Five new cases cover ceiling/reference independence, sparse upper coverage, plan vertical orientation, front/background visibility and source-bound object footprint priors.

Current rough-room completion suite: **120 cases pass on Windows/Linux**. Five additional cases cover inferred closed rectangles, rotated extents, entry crossing, ceiling/scale separation, degenerate inputs and valid SVG. HTTP checks also cover optional SVG admission and tamper rejection.

Current floorplan-stage suite: **115 cases** including six checks for low furniture, isolated/compact tall noise, weak height support, horizontal-plane exclusion, refit disagreement and preserved empty spans.

# Behavioral tests

Gaussian-stage suite: **109 cases passed on Windows and Linux**. Five Gaussian cases check covariance/encoding, source identity, quality admission, immutable publication and bounded hash-checked HTTP. [Experiment contract](../GAUSSIANS.md).

The viewer milestone extends the suite to **104 passing cases on Windows/Linux**. Five additional cases check rigid right-handed coordinate preservation, disconnected candidate extents, empty occupancy pixels, bounded atomic publication/original input preservation, binary layout, fixed HTTP asset admission and post-publication tamper rejection. [Real viewer results](../RECONSTRUCTION_VIEWER.md). Earlier counts below are milestone snapshots.

Historical boundary-stage suite: **99 cases passed on Windows and Linux**. Eight boundary cases cover pixel-region exclusions and precedence, tilted floor transforms, unsnapped plane intersections, gaps, absent floor support, repeated poses, review/source identity and polygon admission, overlap guards, portable archived reviews and rejection of a rehashed invented room polygon. [Partial-boundary contract and real trial](../PARTIAL_BOUNDARIES.md). Synthetic checks establish implementation behavior; physical room accuracy remains unverified.

Grounding and separate review diagnostics extend the complete suite to **91 cases**: unconstrained known rectangles, injected scale disagreement despite fitting PnP, width/height order, insufficient translation, multiple planar solutions, negative depth, coordinates, corner/review source bindings, strict thickness interval endpoints, preserved fixed-camera point fitting, object/floor separation, portable review archives and rehashed-report audits. [Grounding workflow](../GROUNDING.md), [reviewed diagnostic limits](../GROUNDING_DIAGNOSTICS.md). Analytic fixtures do not validate the actual notebook dimensions or room accuracy.

Current surface milestone: **76 tests pass on Windows/Linux**. Seven surface cases exercise known noisy planes, rejected outliers/degeneracy, disconnected patches, duplicate camera positions, floor/furniture ambiguity, raw-source overlap and accepted-depth/rehashed-report audits. Real single-room source audits and focused RGB review are separate evidence. [Surface contract/results](../SURFACES.md).

The suite uses Python's standard-library `unittest`. Install both `web` and `reconstruct` extras for the complete suite (99 cases after region-reviewed boundaries). Core-only installation skips optional modules. Commands run from `proto-2`:

```shell
uv sync --locked --extra web --extra reconstruct
uv run --locked --extra web --extra reconstruct python -m unittest discover -s tests -v
uv run --locked --extra web --extra reconstruct ruff check .
uv run --locked --extra web --extra reconstruct ruff format --check .
```

| File | Coverage |
|---|---|
| `fixtures.py` | Synthetic export builder, fake media inspector and temporary test directories |
| `test_adapter_annotations.py` | Unsupported format/conventions, path escape and hash-bound user declarations |
| `test_geometry_clocks.py` | Quaternion direction, precise timestamps, frame/count/clock mismatches and policy validation |
| `test_pipeline.py` | Observation preservation, deterministic replay, no overwrite, source mutation and transactional failure |
| `test_preprocessing.py` | Native-grid and exact K/pose/IMU retention, role exclusions, quality/motion/selection, geometric image links, policy limits and transaction/tamper rejection |
| `test_preprocessing_web.py` | Independent child admission/ownership, previews, source-preserving portable exports and HTTP tamper rejection |
| `test_reconstruction.py` | Optical/pixel conventions, degeneracy, selection/source/transaction boundaries, fixed cameras, actual analytic triangulation and zero-parallax publication/tamper |
| `test_dense.py` | Analytic multi-view plane, pixel centers, occlusion/invalid depth/zero parallax rejection, dense array shape/layout, bounded admission, voxel averages, grid resampling and portable numeric audits |
| `test_surfaces.py` | Noisy known planes/outliers, degenerate/empty geometry, gap preservation, camera baseline, furniture ambiguity, implicit source overlap, depth-label lineage and rehashed-report tamper rejection |
| `test_grounding.py` | Independent size/pose checks, scale/order/low-baseline/negative-depth states, coordinates, annotation lineage, object/floor separation, unknown uncertainty, preserved inputs and forged-report rejection |
| `test_grounding_review.py` | Exact review identity, invalid/contradictory bounds, strict interval reversal, controlled fixed-camera point fitting, no disagreement override, portable reviewed publication and forged-bound rejection |
| `test_boundaries.py` | Image-region exclusions, floor transforms, non-orthogonal intersections, weak/gapped coverage, source-bound polygon admission, overlap guards and portable publication/tamper rejection |
| `test_reconstruction_viewer.py` | Rigid display transform, gapped candidate extents, unfilled plan raster, portable publication/binary layout, source preservation and HTTP tamper rejection |
| `test_reader.py` | Input-profile boundaries, modified artifacts/raw files and source-root rebasing |
| `test_reference_images.py` | Separate optional photo upload, format/byte/grid/decode limits, source binding, archive preservation and tamper rejection |
| `test_multimodal.py` | v2 catalog/schema dispatch, photo EXIF/room/reference ingestion, duplicate identity, source-mutation and portable verification |
| `test_web_photos.py` | Holo photo modality: room/ZIP upload, HEIC rejection, reference binding, report/download dispatch and preprocessing guard |
| `test_lidar.py` | Raw-depth admission: conventions, preserved poses/K, optional confidence, invalid samples and stream/grid mismatch rejection |
| `test_stray.py` | Provided source layout, initial discard/clock association, native values, depth/confidence exclusion, replay and nested archives |
| `test_web.py` | Upload/extraction limits and paths, reference/API/storage boundaries, restart/queue behavior, legacy hints and process-tree termination |

Run a focused module with discovery rather than assuming `tests` is an installed package:

```shell
uv run --locked --extra web python -m unittest discover -s tests -p "test_web.py" -v
```

For Linux checks with Docker available:

```shell
docker build --target checks -t cozmo-ingestion-checks:0.2.0 .
```

Thirty cases passed at P2W-002; the 34-case reference-photo suite passed on Windows and Linux. Seven supplied-data tests in `test_stray.py` extend the suite to 41 cases, covering initial discard/count/clock failures, native-value preservation, replay, source tampering, role exclusion, mixed formats and nested/multi-session ZIPs. Unit tests mostly use synthetic data and injected media/job services; the process-tree test also launches a temporary child process to verify shutdown. Real FFmpeg ingestion, browser behavior, portable downloads and native/Linux content equality were checked separately on both supplied recordings. See [WEB_RESULTS.md](../WEB_RESULTS.md) for evidence and limitations.

Test files ship in the source archive. Private recordings and generated evidence do not. Use new temporary fixtures for meaningful behavior checks; do not put real capture media or expected machine-specific paths in this directory.

The preprocessing milestone had **53 passing Windows/Linux tests** (41 earlier cases plus 12 new domain/web checks). Real native and Docker preprocessing use the two user-recorded captures separately from synthetic tests. [Preprocessing evidence and limitations](../PREPROCESSING.md).

The reconstruction extension brings the complete suite to **62 passing Windows/Linux tests**. Nine additional cases include an actual analytic PyCOLMAP triangulation and an end-to-end zero-parallax result that stays weak, plus input/model/transaction/tamper safeguards. Actual single-room runs and their limitations are recorded in [RECONSTRUCTION.md](../RECONSTRUCTION.md).

The dense milestone extends this to **69 cases on Windows/Linux**. Real 18/100-view CUDA inference and independent CPU depth/model/mask/cloud audits are separate from the analytic fixtures. [Dense results/limitations](../DENSE_RECONSTRUCTION.md). The learned comparison uses existing offline assets separately; unit tests do not certify model accuracy or complete-room coverage.

# Behavioral tests

The suite uses Python's standard-library `unittest`. Install the `web` extra, which includes preprocessing dependencies, for all 53 cases. Core-only installation skips optional preprocessing/web modules. Commands run from `proto-2`:

```shell
uv sync --locked --extra web
uv run --locked --extra web python -m unittest discover -s tests -v
uv run --locked --extra web ruff check .
uv run --locked --extra web ruff format --check .
```

| File | Coverage |
|---|---|
| `fixtures.py` | Synthetic export builder, fake media inspector and temporary test directories |
| `test_adapter_annotations.py` | Unsupported format/conventions, path escape and hash-bound user declarations |
| `test_geometry_clocks.py` | Quaternion direction, precise timestamps, frame/count/clock mismatches and policy validation |
| `test_pipeline.py` | Observation preservation, deterministic replay, no overwrite, source mutation and transactional failure |
| `test_preprocessing.py` | Native-grid and exact K/pose/IMU retention, role exclusions, quality/motion/selection, geometric image links, policy limits and transaction/tamper rejection |
| `test_preprocessing_web.py` | Independent child admission/ownership, previews, source-preserving portable exports and HTTP tamper rejection |
| `test_reader.py` | Input-profile boundaries, modified artifacts/raw files and source-root rebasing |
| `test_reference_images.py` | Separate optional photo upload, format/byte/grid/decode limits, source binding, archive preservation and tamper rejection |
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

The current preprocessing extension has **53 passing Windows/Linux tests** (41 earlier cases plus 12 new domain/web checks). Real native and Docker preprocessing use the two user-recorded captures separately from synthetic tests. [Preprocessing evidence and limitations](../PREPROCESSING.md).

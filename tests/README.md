# Behavioral tests

The suite uses Python's standard-library `unittest`. Install the optional web dependencies for the complete suite; core-only installation skips the web module. Commands run from `proto-2`:

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
| `test_reader.py` | Input-profile boundaries, modified artifacts/raw files and source-root rebasing |
| `test_reference_images.py` | Separate optional photo upload, format/byte/grid/decode limits, source binding, archive preservation and tamper rejection |
| `test_web.py` | Upload/extraction limits and paths, reference/API/storage boundaries, restart/queue behavior, legacy hints and process-tree termination |

Run a focused module with discovery rather than assuming `tests` is an installed package:

```shell
uv run --locked --extra web python -m unittest discover -s tests -p "test_web.py" -v
```

For Linux checks with Docker available:

```shell
docker build --target checks -t cozmo-ingestion-checks:0.2.0 .
```

Thirty cases passed at P2W-002; the current 34-case suite, including reference-photo checks, passed on Windows and Linux. Unit tests mostly use synthetic data and injected media/job services; the process-tree test also launches a temporary child process to verify shutdown. Real FFmpeg ingestion, browser behavior, portable downloads and native/Linux content equality were checked separately on both supplied recordings. See [WEB_RESULTS.md](../WEB_RESULTS.md) for evidence and limitations.

Test files ship in the source archive. Private recordings and generated evidence do not. Use new temporary fixtures for meaningful behavior checks; do not put real capture media or expected machine-specific paths in this directory.

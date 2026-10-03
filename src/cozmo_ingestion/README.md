# Ingestion core

This package converts one supported Sensor Recorder Pro 1.5/build 5 ARKit export into a canonical capture bundle. It preserves native observations, calibration, source poses and timestamps; it does not reconstruct a floor plan or estimate reference-object scale.

## Module ownership

| Module | Responsibility |
|---|---|
| `pipeline.py` | `IngestionPipeline`: coordinate one request and its transaction |
| `models.py`, `contracts.py` | Typed records, schema identity and immutable validated policy |
| `ports.py` | Adapter and media-inspection protocols for injected implementations |
| [adapters/](adapters/README.md) | Source-format parsing, supported headers and validation |
| `media.py` | FFmpeg/FFprobe discovery, media inspection and full decode |
| `clocks.py`, `numeric.py` | Exact frame/time association, finite numbers and quaternion conversion |
| `annotations.py` | Bind user reference declarations to the source video hash |
| `normalization.py` | Build camera/sensor records and explicit quality findings |
| `bundle.py`, `storage.py` | Transactional publication, deterministic serialization and integrity checks |
| `reader.py` | Profile-controlled downstream access and admitted-input audit |
| `verification.py` | Compare canonical records with raw source values and optional replay |
| `errors.py`, `cli.py` | Stable validation errors and CLI presentation |

## Processing contract

`IngestionRequest` → fresh staging folder → source adapter → media inspection → exact frame association → normalization → bundle writer → publish by rename. A failure retains staging diagnostics and never publishes a partial final bundle. Existing output folders and source/output overlap are rejected.

The core references the raw video instead of copying or exporting image frames. Transport raw files with the bundle, or provide a verified `source_root` to `CaptureReader`. `video_rgb` permits RGB/media records; `ios_assisted_rgb` additionally permits calibration, supplied poses, independent sensor streams and declared reference metadata. Measured depth and evaluation references are excluded from those input profiles.

Canonical JSON/JSONL/Markdown use UTF-8/LF, CSV uses explicit CRLF, and raw-root hints use POSIX separators. Historical Windows hints remain readable. Source values are preserved; serialization portability can intentionally change historical artifact byte hashes.

## Using and changing the package

See [CLI and Python examples](../../README.md), [full architecture](../../ARCHITECTURE.md) and [tests](../../tests/README.md). Commands run from `proto-2`:

```shell
uv run --locked cozmo-ingest --help
uv run --locked cozmo-verify --help
uv run --locked python -m unittest discover -s tests -p "test_pipeline.py" -v
```

Inject implementations through the protocols instead of adding format detection or web state to the pipeline. Schema changes require corresponding writer, reader and verifier changes. The manifest fingerprints package Python source; presentation code and these README files are outside that fingerprint. Geometry algorithms belong to a later stage.

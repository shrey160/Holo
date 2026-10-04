# Multimodal ingestion (`canonical-capture-2`)

Modality-neutral ingestion alongside the unchanged `canonical-capture-1` video path. Implemented: the v2 foundation/legacy bridge, JPEG/PNG photos (CLI + Holo) and LiDAR raw-depth admission (CLI). Holo LiDAR upload and photo reconstruction are not implemented.

| File | Responsibility |
|---|---|
| `contracts.py` | Schema/modality constants, capability states, request and room/reference dataclasses |
| `schema.py` | Internal JSON Schema plus type/enum/referential/safe-path validation |
| `media.py` | Content-based JPEG/PNG detection, structural decode and a standard-library EXIF/TIFF parser |
| `depth.py` | Bounded grayscale-PNG decode (8/16-bit) for raw-depth statistics and validity |
| `adapters/photos.py` | Per-room JPEG/PNG inventory, EXIF evidence, room membership and reference parsing |
| `adapters/stray_lidar.py` | Stray-style raw-depth source parsing, stream/ID/grid checks and convention provenance |
| `bundle.py` | Deterministic v2 artifact serialization and portable `sources/` copies |
| `pipeline.py` | Photo ingestion service, capability/profile reporting and source-preservation checks |
| `lidar_pipeline.py` | Raw-depth ingestion: depth/confidence framing, supplied K/poses, conventions and readiness |
| `reader.py` | `MultimodalCaptureReader` and `open_capture` schema dispatch (v1 → existing reader) |
| `verify.py` | Portable bundle verification and optional original re-hashing/re-inspection |

## Layout

`manifest.json`, `rooms.json`, `assets.json`, `observations.jsonl`, `associations.jsonl`, `calibration.jsonl` (empty for photos), `poses.jsonl` (empty for photos), `references.json`, `verification.json` and `sources/`. Still photos invent no FPS, sensor clock, video index or camera trajectory; K/pose references are null.

## Commands

```shell
uv run --locked cozmo-ingest --mode photos --source ../test_data/Room-1 \
  --output outputs/photos-room1 --room-label "Room 1" --reference outputs/a4-reference.json
uv run --locked cozmo-verify --capture outputs/photos-room1 --source ../test_data/Room-1
uv run --locked cozmo-verify --capture outputs/photos-room1   # portable bundle only

# LiDAR raw-depth (inspected Stray-style layout)
uv run --locked cozmo-ingest --mode lidar --source ../test_data/drive_download/single_room/c00a170fe1 \
  --output outputs/lidar-single-room --ffmpeg /path/to/ffmpeg
uv run --locked cozmo-verify --capture outputs/lidar-single-room
```

## Boundaries

- No third-party image codec is required or added; Pillow is used for a full pixel decode only if it happens to be importable. Do not claim full JPEG pixel decode without it.
- HEIC/HEIF and other phone formats fail admission with an actionable message; export to JPEG first.
- Reference dimensions are `USER_DECLARED` metadata only: geometry is `NOT_LOCALIZED`, scale is `NOT_APPLIED` and no video annotations are transferred.
- Ingestion integrity, tier profile, consumer readiness and metric accuracy are separate report fields; none is a physical-accuracy claim.
- LiDAR depth units/definition, confidence meaning and pose/K conventions stay `FORMAT_REFERENCE_ASSUMED` / `CONVENTIONS_UNVERIFIED`; no unit conversion, axis flip or fusion is applied, and no live-phone LiDAR export has been validated.

Tests: [test_multimodal.py](../../../tests/test_multimodal.py) · Plan: [INPUT_MODALITIES_PLAN.md](../../../INPUT_MODALITIES_PLAN.md) · Core: [cozmo_ingestion](../README.md)

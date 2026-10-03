# Preprocessing package

See [contract, commands and evidence](../../PREPROCESSING.md). This package consumes verified Sensor Recorder RGB/K/pose/independent-IMU observations through the restricted ingestion reader and writes separate derived outputs. It excludes LiDAR, confidence and known-size references.

| Module | Ownership |
|---|---|
| `models.py` | Immutable validated policy and request |
| `pipeline.py` | `PreprocessingPipeline` application service, source/transaction boundaries and output contract |
| `media.py` | Injected sequential FFmpeg decoder, Unicode-safe image encoding/reading |
| `analysis.py` | Image quality, pose deltas and indexed native sensor statistics |
| `selection.py` | Timestamp-based candidate sampling and coverage/motion keyframes |
| `matching.py` | Cached SIFT features, image geometry and qualified source-pose diagnostics |
| `verification.py` | Artifact/source identities, exact geometry/sensor retention and input-use audit |
| `cli.py` | Native preprocessing/verification entry point |

Classes own lifecycle or indexed/cache state; pure scoring/selection transformations remain functions. The pipeline accepts an injected decoder so tests can exercise geometry/transactions with synthetic pixels without mocking domain state. Native/Docker runs exercise real FFmpeg separately. The web wrapper queues independent child runs; this package imports no HTTP or frontend code.

To add a new source format, first resolve its coordinate/time/unit contract and add an explicit input-policy/reader boundary. Do not silently enable the supplied Stray combined IMU or read raw depth. Reconstruction adapters should consume `views.jsonl`, selected `images/`, K/poses and the qualified native sensor intervals; quality thumbnails do not define a new camera calibration.

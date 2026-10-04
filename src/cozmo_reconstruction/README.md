# Reconstruction package

This package owns fixed-pose sparse geometry and RGB stereo depth, independently of the Holo API/frontend. Read [sparse setup/results](../../RECONSTRUCTION.md), [dense setup/results](../../DENSE_RECONSTRUCTION.md), [dense module ownership](dense/README.md) and [the wider staged plan](../../RECONSTRUCTION_PLAN.md).

| Module | Responsibility |
|---|---|
| `models.py` | Immutable validated request/policy |
| `audit_numbers.py` | Narrow portable report roundoff tolerance; counts and categorical decisions stay exact |
| `dense/` | Separate bounded CUDA stereo worker, derived-grid cameras, independent multi-view masks/clouds and CLI |
| `surfaces/` | CPU plane proposals, accepted-depth/source-image evidence, occupied patches and independent verification; [ownership](surfaces/README.md), [results](../../SURFACES.md) |
| `boundaries/` | Source-bound image-region decisions, explicit exclusions, local floor cells and supported wall projections; [ownership](boundaries/README.md), [contract/results](../../PARTIAL_BOUNDARIES.md) |
| `viewer/` | Full-chain audited, immutable display assets for rough occupancy plans and RGB point clouds; [ownership](viewer/README.md), [workflow](../../RECONSTRUCTION_VIEWER.md) |
| `grounding/` | Offline corner editor, IPPE/independent size checks, separate human review/thickness intervals and controlled mismatch experiments; [ownership](grounding/README.md), [workflow](../../GROUNDING.md), [reviewed findings](../../GROUNDING_DIAGNOSTICS.md) |
| `inputs.py` | Original/prepared audits, restricted image/K/pose admission and source snapshots |
| `cameras.py` | Pure optical pose inversion, projection and temporal/revisit pair proposal |
| `ports.py` | Backend protocol for injection without inheritance/global state |
| `backend.py` | Isolated worker process, CPU limits, timeout and log boundary |
| `worker.py` | Subprocess composition entry point |
| `colmap.py` | Pinned 4.2.1 API, feature database, fixed cameras/rigs, triangulation and model/track exports |
| `analysis.py` | Independent projection, depth/parallax/track filtering and quality signals |
| `preview.py` | Offline orthogonal source-world point/camera SVG |
| `pipeline.py` | Transactional coordinator, source rechecks and artifact publication |
| `verification.py` | Source/selection hashes, fixed cameras, binary-model/database lineage and recomputed reports |
| `cli.py` | Native/container arguments, JSON presentation and stable errors |

Classes own configuration, source state or lifecycle; mathematical transformations and report computations remain functions. The sparse application injects a backend through a protocol; dense coordination injects its worker callable. Default pipelines do not import prototype-1, web state or frontend code. The separately invoked learned experiment loads existing pinned prototype-1 assets lazily. Optional reconstruction extras supply numerical/backend dependencies; ingestion stays dependency-free.

To change camera conventions, update conversion, analytic fixtures and the recorded input contract together. To add a dense backend, implement a separately auditable depth convention/calibration/output contract; do not overload sparse tracks or silently read capture depth. UI integration should call this application boundary through an isolated job, not contain reconstruction algorithms in routes.

## Optional Gaussian appearance

See [Gaussian experiment](../../GAUSSIANS.md) for audited input preparation, isolated GPU training, a separately published hash-bound scene and Holo browser viewing. Structural boundaries and physical calibration remain unchanged.

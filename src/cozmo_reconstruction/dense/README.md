# Dense stereo modules

This subpackage extends [fixed-pose sparse reconstruction](../README.md) with bounded RGB stereo depth and conservative point fusion. [Setup, contracts and results](../../../docs/reconstruction/DENSE_RECONSTRUCTION.md).

| Module | Responsibility |
|---|---|
| `models.py` | Immutable bounded request/policy; no CUDA imports |
| `pipeline.py` | Source-chain audit, selection, injected timeout worker, atomic publish and independent verifier |
| `worker.py` | Pinned CUDA PatchMatch adapter; derived image-grid/model camera checks |
| `runtime.py` | Pinned CUDA binding/native executable discovery, cached build probe and live device readiness |
| `geometry.py` | Dense array parser, co-visibility, pixel-center backprojection, multi-view depth/reprojection/parallax tests and voxel averaging |
| `analysis.py` | Recomputable masks/cloud/coverage/sparse-depth diagnostics and offline previews |
| `cli.py` | Native/container argument parsing and verify-only mode |
| `learned_compare.py` | Bounded offline comparison with separately pinned existing proto-1 assets; model cameras diagnostic only |

The default pipeline has no HTTP or learning-framework dependencies. CPU geometry and result verification run without CUDA. Stereo inference requires a compatible CUDA-enabled COLMAP build. Reference photos, captured depth/confidence, grounding dimensions and IMU integration are not geometric inputs. Derived depth is explicitly RGB stereo; estimated ARKit metre scale is retained without physical accuracy certification.

Windows may use CPU PyCOLMAP for undistortion/model/audits and the official COLMAP 4.2.1 CUDA executable for stereo. Native executable identity is recorded in the backend provenance; the independent geometry verifier is shared with the CUDA Python path. [Native setup](../../../NATIVE_DENSE.md).

`learned_compare.py` imports Torch/model code lazily only when the separately configured experiment is invoked. It requires the existing pinned proto-1 assets/runtime, reads them without modification and writes an experiment contract distinct from default COLMAP dense bundles. It is not part of default inference dependencies or HTTP jobs.

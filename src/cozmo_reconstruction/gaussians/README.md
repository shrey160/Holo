# Gaussian appearance modules

Optional source-bound visual reconstruction. [Design, setup and limitations](../../../docs/appearance/GAUSSIANS.md).

| Module | Responsibility |
|---|---|
| `inputs.py` | Full upstream audit, bounded RGB/K/fixed-pose export and explicit photometric split |
| `format.py` | Rigid position/covariance transform and standard 32-byte splat encoding |
| `publish.py` | Completed-trial/source/quality admission and atomic portable scene publication |
| `cli.py` | CPU prepare/publish commands; no GPU dependency in ordinary Holo |

GPU training lives in the separately locked [experiment](../../../experiments/gsplat/pyproject.toml). HTTP catalog ownership lives in [web](../../cozmo_web/README.md), browser rendering in [the frontend](../../../frontend/src/features/reconstruction/README.md). Gaussian appearance is not admitted as measured wall/floor evidence.

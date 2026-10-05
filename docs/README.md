# Holo documentation

Reference documentation lives here, grouped by topic. Entry points remain at the repository root: [main README](../README.md) and [prototype handoff](../CONTEXT.md). The [capture protocol](../capture.md) stays at the root because the frontend imports it at build time.

| Folder | Contents |
|---|---|
| [architecture/](architecture/ARCHITECTURE.md) | Package boundaries, lifecycles and extension points |
| [ingestion/](ingestion/PREPROCESSING.md) | Ingestion results, provided-data contract and RGB/pose/IMU preprocessing |
| [reconstruction/](reconstruction/RECONSTRUCTION.md) | Sparse/dense reconstruction, surfaces, partial boundaries, floorplan refinement and the 3D viewer |
| [appearance/](appearance/GAUSSIANS.md) | Optional Gaussian appearance experiment |
| [grounding/](grounding/GROUNDING.md) | Opening-reference corner diagnostic and its reviewed investigation |
| [web/](web/WEB_SETUP.md) | Docker/native setup, web evidence and the Docker/web plan |
| [archive/](archive/Overview.md) | Historical planning, refactor and report notes |
| [regressions/](regressions/native-dense-2026-10-04/README.md) | Frozen native dense error baseline and corrected comparison |

Preserve failing baselines when later fixes add comparison results. [Current prototype handoff](../CONTEXT.md).

Latest experiment: [room-wise capture-route analysis](reconstruction/ROOMWISE_PLAN.md), with
[two-room partial-result evidence](regressions/roomwise-2026-10-06/README.md).

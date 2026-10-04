# Reconstruction tab

**Current automatic workflow (2026-10-04):** The catalog refreshes every five seconds while mounted. Capture-result links select the exact reconstruction through `?reconstruction=<id>#reconstruction`. CPU sparse results use point labels and coverage-envelope explanations; reviewed dense/furnished results retain their existing layers. [Automatic flow](../../../../AUTOMATIC_RECONSTRUCTION.md).

`Reconstruction.tsx` loads the catalog/selected immutable result with abortable requests and explicit empty/loading/error states. `RoomPlan.tsx` composes orthographic occupancy, reviewed cells/spans, the capture path and optional unreviewed plane candidates. `PointCloudViewer.tsx` owns Three.js RGB point rendering, orbit/reset/top/front navigation, display controls and cleanup of network/animation/observer/GPU resources. `types.ts` documents the asset contract and shared read helper. The feature is lazy-loaded from the app tab.

The selector labels dense versus sparse results and persists the selected capture in the URL. A compact overview shows geometry quality, provisional room dimensions and ceiling height. Catalog connection errors have separate state from asset errors, retain the loaded view, and clear on a successful refresh.

All assets come from the local read-only reconstruction API. The browser does not reconstruct or correct poses/scale. Optional rough completion is an offline hypothesis, separately labeled from observed evidence. [Setup and interpretation](../../../../RECONSTRUCTION_VIEWER.md).

## Optional Gaussian appearance

The plan viewer also supports a structure-focused layer, fitting to its evidence extent and comparison with all observed occupancy. Robust line suggestions remain optional and unreviewed. Older plan bundles continue to display normally. [CPU refinement](../../../../FLOORPLAN_OPTIMIZATION.md).

See [Gaussian experiment](../../../../GAUSSIANS.md) for audited input preparation, isolated GPU training, a separately published hash-bound scene and Holo browser viewing. Structural boundaries and physical calibration remain unchanged.

`CompleteRoomPlan.tsx` renders the new downloadable complete SVG and its estimate/reference summary. `RoomPlan.tsx` defaults to this layer for opt-in completed bundles and retains evidence/occupancy comparison. Completion occurs offline as an explicitly inferred rectangle; browser code does not change geometry. [Rough completion](../../../../FLOORPLAN_OPTIMIZATION.md).

The furnished plan includes separately identified geometry ceiling estimate and user reference, approximate furniture SVG, and corresponding optional 3D floor outlines. The 3D estimated-height shortcut clips the existing cloud; it does not detect a ceiling. Top view and evidence layers use upward floor-v orientation. [Method and uncertainty](../../../../FLOORPLAN_OPTIMIZATION.md).

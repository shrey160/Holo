# Holo rough plan and interactive 3D

**Current automatic workflow (2026-10-04):** GPU Sensor Recorder ARKit uploads publish dense RGB/surface-derived rough plans, provisional ceiling estimates and interactive 3D under writable `DATA_ROOT/reconstructions`. CPU runtimes publish labelled sparse previews. The optional read-only historical catalog is combined with generated results; offline reviewed/furnished publication remains separate. [Automatic workflow and GPU setup](../../AUTOMATIC_RECONSTRUCTION.md).


Holo has a **Reconstruction** tab with a capture selector, rough top-down plan and interactive RGB point cloud. Open [the local app](http://localhost:8000/#reconstruction). Automatic processing continues after verified ingestion/preprocessing when enabled; an ingestion-only capture needs the separate prepare/reconstruct action. [Upstream geometry](DENSE_RECONSTRUCTION.md), [region-reviewed structural contract](PARTIAL_BOUNDARIES.md).

## What the views mean

The rough plan is an equal-scale orthographic occupancy image of existing dense points between 0.1 and 2.2 source-estimated metres above the local floor hypothesis. It includes furniture, preserves absent pixels and adds the source camera path, 11 reviewed floor cells and the supported wall-patch projection. Gray occupancy is not a wall classifier. Optional amber dashed plane candidates are geometric suggestions and may follow furniture or curtains; they are off by default and cannot certify architectural identities. Candidate intervals use occupied 15 cm bins with at least 20 source voxels, join adjacent bins only and retain gaps. They do not pass the stronger image-region wall admission gate.

The 3D view displays 120,000 deterministic source voxel samples from the 878,459-point RGB stereo result. Colours are retained; browser RGB colours are converted to linear rendering values. Coordinates are a rigid, right-handed display transform: local floor u, height, negative floor v. Exported scene metadata retains the source floor transform. Distances and source scale are unchanged. This is a point cloud, not a completed watertight mesh.

- Drag to orbit; right-drag or two fingers to pan; wheel/pinch to zoom. Focus the canvas for keyboard panning.
- Reset, Top and Front choose useful viewpoints. Point size, height slice, camera-path and reviewed-evidence controls affect display only.
- Plan zoom and observed-geometry/path/candidate toggles help inspect coverage.
- Downloads provide occupancy PNG, display-subset binary PLY, reviewed partial SVG and boundary evidence JSON. The PNG is the occupancy background, not the browser's composed overlays. PLY contains the displayed subset in documented floor coordinates, not every original voxel.

Physical accuracy remains **UNVERIFIED**; grounding remains **DISAGREEMENT_REVIEW_REQUIRED**. The reviewed 0.599 m wall-patch extent is source estimated and does not establish total wall length, floorâ€“wall junction or room corners. No closed room polygon, surveyed area, doorway detector, scale correction, pose optimization or LiDAR processing is introduced.

## Publish a result

From the project root, install `uv sync --locked --extra web --extra reconstruct`. Publish to a **new** folder, using the same source chain and optional grounding report as the boundary result:

```shell
cozmo-publish-reconstruction outputs/single-room-boundaries-v1 outputs/holo-reconstruction/single-room-v1 --surfaces outputs/single-room-surfaces-v2 --sparse outputs/single-room-sparse-100-v2 --prepared outputs/single-room-preprocessing-final --bundle outputs/single-room-cli-v2 --dense outputs/linux-reconstruction/single-room-dense-100-v1 --source ../test_data/iphn-17/single_room --grounding outputs/single-room-grounding-v4 --label "Single room Â· RGB reconstruction"
```

The publisher performs the full ingestion/prepared/sparse/dense/surface/boundary and optional grounding audit. It restricts display sampling to existing dense voxels, archives a scene/plan description, binds all three parent manifests and hashes eight assets. It rechecks parent artifacts before atomic publication; existing results and source-overlap destinations are rejected. A failed staging folder remains diagnostic and is excluded from the catalog. No external upload is made. New captures need their own reconstruction and published viewer bundle; the selector admits multiple immutable bundles under the configured root.

## Native development

In PowerShell, after publishing and building the frontend:

```powershell
uv sync --locked --extra web --extra reconstruct
cd frontend
npm ci
npm run build
cd ..
$env:RECONSTRUCTION_ROOT = (Resolve-Path outputs/holo-reconstruction).Path
uv run --locked --extra web cozmo-web --port 8006
```

Use port 8000 if available. Pass `--ffmpeg path/to/ffmpeg.exe` when needed; FFprobe must be alongside or on PATH. Without `RECONSTRUCTION_ROOT`, viewer results are read from `DATA_ROOT/reconstructions`. Vite development remains supported: run the API, then `API_TARGET` for its port and `npm run dev`. Native preview for this trial is http://127.0.0.1:8006/#reconstruction. [General setup](../web/WEB_SETUP.md).

## Docker

Published assets remain outside the image and mount read-only:

```shell
docker compose -f compose.yaml -f compose.reconstruction.yaml up --build --detach --wait
```

The optional override mounts `./outputs/holo-reconstruction` at `/reconstructions` and sets `RECONSTRUCTION_ROOT`. Set `RECONSTRUCTION_ASSETS` to a different host directory if needed. The ordinary captures volume remains intact. Publish the assets first; capture media and outputs are excluded from the image. The default `compose.yaml` alone serves an empty Reconstruction tab unless viewer bundles are provided in its configured data root. Python web runtime needs no PyCOLMAP/CUDA to display published results; numerical dependencies are needed only for offline publication/reconstruction. JavaScript and Three.js are bundled locally, with no runtime CDN fetch.

For offline publication in Docker, build `docker build --target viewer -t holo-publisher:0.2.0 .`, mount the workspace read-only at `/workspace` and a separate writable result directory at `/results`, then run this image with the publisher arguments above translated to those container paths. The image entry point is `cozmo-publish-reconstruction`; use `docker run --rm holo-publisher:0.2.0 --help` for its argument contract. Do not write viewer assets into raw/upstream or previously published result directories.

## System boundaries and evidence

[Publisher ownership](../../src/cozmo_reconstruction/viewer/README.md) isolates auditing/derivation from read-only [HTTP catalog](../../src/cozmo_web/README.md) and [frontend viewers](../../frontend/src/features/reconstruction/README.md). The HTTP service exposes a fixed eight-asset allowlist, validates result IDs and resolves paths inside the catalog root, checks hashes on reads and returns integrity failures as errors. It does not accept arbitrary host paths or start reconstruction jobs. [Three.js OrbitControls](https://threejs.org/docs/pages/OrbitControls.html), [BufferGeometry](https://threejs.org/docs/pages/BufferGeometry.html) and [WebGLRenderer lifecycle](https://threejs.org/docs/pages/WebGLRenderer.html) inform the local viewer; renderer, controls, observers, animation and GPU resources are disposed on tab/result changes.

104 behavioral cases pass on Windows and Linux, including five display/publishing/HTTP cases. Native and Docker catalogs serve the same audited eight-asset trial. Browser review exercised plan candidates, Top/reset/orbit/zoom/height controls and verified loaded WebGL geometry without console errors. Existing Holo capture history is unchanged after container recreation. The prior boundary result also passes Linux read-only full-chain verification for 81 artifacts. Package assets, generated evidence and physical accuracy are separate claims; none of these tests establishes a surveyed room plan.

## Subsequent floorplan refinement

New viewer bundles include the optional [CPU structure-focused layer](FLOORPLAN_OPTIMIZATION.md), comparison with full observed occupancy, extent fitting and gap-preserving robust line suggestions. Existing eight-asset bundles remain compatible and immutable. External measurement references remain separate from geometry.


## Complete rough draft

The opt-in publisher now completes an approximate rectangular room with inferred entrance, estimated dimensions/area and the separate user ceiling reference. Holo defaults to that SVG for `single-room-complete-v1`; observed evidence and unchanged RGB 3D remain available. The original eight required assets plus optional signed `rough-room.svg` preserve earlier bundles. All full walls/corners are inferred, not certified. [Algorithm, limitations and command](FLOORPLAN_OPTIMIZATION.md).

# Source-linked surface hypotheses

Subsequent stages now include the separate [reviewed grounding investigation](GROUNDING_DIAGNOSTICS.md) and [region-reviewed partial projections](PARTIAL_BOUNDARIES.md). These preserve this surface result unchanged; unresolved calibration and architectural identities remain explicit. [Staged plan](GROUNDING_PLAN.md).

This CPU stage proposes planes from verified RGB stereo geometry and links them to accepted depth observations and source RGB. It preserves the source world, calibration and estimated metre scale. It does not confirm walls/floors, infer closed boundaries or produce a dimensioned floorplan. LiDAR/captured depth, grounding dimensions/photo, new IMU integration and pose refinement remain excluded.

## Native and Docker use

From `proto-2`, install the existing reconstruction extra; there is no additional numerical dependency:

```shell
uv sync --locked --extra reconstruct
uv run --locked --extra reconstruct cozmo-surfaces outputs/single-room-sparse-100-v2 outputs/single-room-preprocessing-final outputs/single-room-cli-v2 outputs/linux-reconstruction/single-room-dense-100-v1 outputs/my-surfaces --source ../test_data/iphn-17/single_room
```

Append `--verify-only` to audit an existing result. Default controls are `--distance 0.035` and `--max-planes 12`; other bounded policy values are in [models.py](src/cozmo_reconstruction/surfaces/models.py). Thresholds are engineering choices, not measurement uncertainty. Keep `--extra web` too when using the same venv for Holo. Windows can execute this stage without Docker or CUDA; it needs the previously generated dense bundle and complete source chain.

```shell
docker build --target surfaces -t holo-surfaces:0.2.0 .
docker run --rm --mount "type=bind,source=C:/Shrey_Projs/Recruitements_comp/tkh_cozmo,target=/workspace,readonly" --mount "type=bind,source=C:/Shrey_Projs/Recruitements_comp/tkh_cozmo/proto-2/outputs/linux-reconstruction,target=/results" holo-surfaces:0.2.0 /workspace/proto-2/outputs/single-room-sparse-100-v2 /workspace/proto-2/outputs/single-room-preprocessing-final /workspace/proto-2/outputs/single-room-cli-v2 /workspace/proto-2/outputs/linux-reconstruction/single-room-dense-100-v1 /results/my-surfaces --source /workspace/test_data/iphn-17/single_room
```

Use a new output path; existing outputs and ancestors/descendants of any input, including implicitly resolved raw sources, are rejected. Open `index.html` locally. Holo remains separate; reconstruction has no HTTP job integration yet.

## System design

`SurfaceRequest` binds the dense/sparse/prepared/ingested/raw chain. `SurfacePipeline` guards paths, audits upstream geometry, fits deterministic candidates, writes evidence in a transaction and independently verifies it before publication. Gravity must be the supported iOS exporter-declared +Y up; it is not independently measured or newly estimated.

1. Seeded RANSAC samples at most 12,000 voxel points, uses 384 trials per candidate and extracts up to 12 planes. SVD refines supported candidates; degenerate samples and insufficient support stop extraction. No orientation constraint rotates or repairs geometry.
2. All cloud points are assigned to the nearest candidate within 3.5 cm. Unassigned points stay explicit; equations have unit normals in source world coordinates.
3. Occupied 15 cm tangent-plane cells form connected patches. Counts and disconnected components are exported. Empty cells stay empty; occupied-cell area is a coarse diagnostic, not true surface area or room footprint.
4. For every verified view, every fourth accepted depth pixel on each axis is backprojected with exact derived K and fixed source pose. Its label, dense neighbor support and image coordinates are saved. Rejected depth pixels supply no observations.
5. Multi-view candidates require at least 150 samples in each of three selected views, at least 15 cm maximum camera-center separation, a connected patch spanning at least 75 cm on both tangent axes, and plausible orientation/height. These views share reconstruction inputs and are not independent ground truth. Normal angle to declared up classifies horizontal/vertical/oblique within 15 degrees. Height only proposes floor/furniture, ceiling/other or ambiguous roles.
6. Small/narrow, low-baseline, insufficient-view, oblique and ambiguous-height candidates receive flags. Furniture can satisfy geometric criteria: **multi-view support never confirms architectural identity**. Source RGB review is required; confirmed architectural surface count stays zero.

[Module ownership](src/cozmo_reconstruction/surfaces/README.md). RANSAC is a standard plane-proposal method illustrated by [Open3D's official documentation](https://www.open3d.org/docs/release/tutorial/geometry/pointcloud.html#plane-segmentation); this implementation uses existing NumPy rather than adding Open3D.

## Outputs and audits

- `planes.json`, `policy.json`, `manifest.json`: equations, policy, dense manifest binding, module fingerprint and artifact hashes.
- `cloud_labels.npz`: index for each source voxel; -1 means unassigned.
- `observations/*.npz`: sampled x/y, plane index and dense neighbor support per source-linked view.
- `overlays/*.jpg`: source-derived RGB beside all candidate observations.
- `candidate_overlays/*.jpg`: focused evidence for one plane in up to three temporally separated high-support views.
- `report.json`: residuals, rank/frame/time lineage, baselines, height, occupied cells/components and unconfirmed roles.
- `index.html`, `preview.png`: offline review and three source-axis projections. Outer 1% is clipped for display only; no source observations are removed.

Verification reaudits the upstream chain, verifies hashes, recomputes seeded planes, every source-pixel label/support array, cloud labels, residuals and connected patches. Counts/labels/categories stay exact; floats permit only the existing tiny roundoff tolerance. It rechecks hashes afterward. Failed stages retain diagnostics, not successful results. Manual report changes invalidate verification; later review decisions must be separate provenance-bound evidence.

## Single-room findings

Current local result: `outputs/single-room-surfaces-v2`, derived from `single-room-dense-100-v1`. Twelve planes were proposed: eight pass the multi-view diagnostic and four are weak. Of 878,459 source voxels, 480,423 are assigned and 398,036 unassigned. Proximity to fitted planes is not correct room-surface coverage.

Focused RGB review is essential. **P01 follows the bed and must be rejected as a floor**, despite being the largest supported horizontal plane. P02 follows the opening floor area; this is a local floor hypothesis, not proof of the entire room floor/footprint. Other candidates overlap furniture, curtains and edges; plain architectural surfaces remain under-observed. Do not promote vertical planes or close corners from support counts alone. The opening object is visible in RGB but its dimensions/photo are not used for recognition or scaling.

Seventy-six tests pass on Windows/Linux, including seven surface fixtures. Native and container CLIs, package builds, independent Linux read-only verification and repeated Windows byte-preservation audits pass. The final result has 242 hashed artifacts. Local evidence lives in `outputs/surfaces-evidence/validation.json`; generated artifacts stay excluded from Git/distribution. Dimensions, missing-boundary completion, double-room geometry and a property plan remain unvalidated/unimplemented. Next: bind image-reviewed identities and rejected furniture observations, then form supported wall segments/floor projections with unknown spans explicit.

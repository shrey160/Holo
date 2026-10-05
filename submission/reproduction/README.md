# Reproduction bundle

The repository ships the complete example raw export at `example_data/video/single_room.zip`, dependency locks, code, a pinned CUDA installer, a hash-bound derived RGB stereo/surface cache, the room-stage replay script and fix evidence. No model weights or candidate service are required for the completed path.

**Live path:** `holo-run` in the [runbook](../RUNBOOK.md) executes uncached RGB reconstruction from a new ZIP. The same worker completed the recorded native dense HTTP run. The new command delegates that worker; its fresh CPU preview run is separately recorded. Required dense never falls back to sparse.

**Cache path:** `scripts/replay-submission.py` validates the original ZIP hash and every cache artifact, then runs current `dense_room` twice. It separately recreates the pre-fix estimator by calling `complete_rough_room` on raw spans, with the original ceiling algorithm. Sizes, areas and ceiling values are checked against the frozen comparison at absolute tolerance 1e-9 in the tested runtime. The replay produces its own JSON/SVG and elapsed time. All cached points keep original source scale; no similarity alignment is applied.

Cache contents: `native-room.npz` (source xyz/RGB and independently verified surface plane labels), `planes.json` (plane report), `cameras.json` (accepted stereo cameras), `provenance.json` (raw and source-manifest identities plus cache hashes). The publisher independently audited this dense/surface chain before cache extraction. Lightweight cache replay does **not** re-audit every stereo depth map or pretend to be raw inference; full live processing does those checks.

The baseline/fixed native geometry numbers, source point/view count and repeat delta regenerate from this cache. Raw frame/sensor counts and ingest findings regenerate from the raw ZIP through the live command. Historical latency values are measurements tied to saved logs; another machine produces new timings, not identical elapsed seconds. GPU stereo output may vary by platform/run; exact historical clouds require this supplied cache. Repeat determinism was tested on the development runtime, not guaranteed bit-for-bit on every OpenCV/platform build.

The [manifest](manifest.json) lists shipped inputs and evidence hashes. [benchmark ledger](../benchmark/results.json) distinguishes replayed numbers from original timing observations and unavailable metrics. Legacy engineering notes include additional historical experiments; they are not added to the submission's measured benchmark claim set.

Unavailable reproduction components are stated in [raw-data ledger](../RAW_DATA.md): instrumented ground truth, independent repeated acquisition, all-tier matched properties, staged damage and consumer-app exports were not acquired. This bundle cannot regenerate measurements that never existed.

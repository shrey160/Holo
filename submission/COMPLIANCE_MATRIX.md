# Compliance matrix

Source: supplied Applied AI Case Study, physical PDF pages 2-6 (Aug 2026). The remaining Round 1 contract and published evaluator schema were not supplied. Status convention: **PASS** = observed bounded behavior; **PARTIAL** = a usable subset; **FAIL** = a known unmet implementation requirement; **NOT_RUN** = insufficient evaluation evidence. A passing ingestion audit is not a passing dimensional gate.

| Requirement | Repository file path | Artifact / evidence | Status |
|---|---|---|---|
| Stock capture route, literal one page | `submission/CAPTURE_PROTOCOL.md` | `output/pdf/capture-protocol.pdf`; supported original app export in example ZIP | PARTIAL: route provided; novice transfer/install rehearsal not timed |
| Device/tier/accuracy matrix | `submission/DEVICE_MATRIX.md` | Named tested device/export, GPU/CPU boundaries | PASS for disclosure; cross-device accuracy NOT_RUN |
| Photos: 2-8 stills/room, no depth/poses | `src/cozmo_ingestion/multimodal/pipeline.py` | Photo ingestion tests; historical eight-photo trial | PARTIAL: validation only; reconstruction/stitching FAIL |
| Video: handheld clip, iPhone 15+ | `src/cozmo_web/worker.py`, `src/cozmo_web/capture_cli.py` | Included Sensor Recorder export; native dense result; live command test | PARTIAL against brief: assisted export works; MP4-only without poses is unsupported |
| LiDAR: depth + poses + intrinsics on Pro device | `src/cozmo_ingestion/multimodal/lidar_pipeline.py` | CLI adapter/tests; supplied Stray-style convention warnings | PARTIAL: ingestion only; fresh Pro capture, fusion and reconstruction NOT_RUN |
| Dimensioned walls, ceiling, area, openings | `src/cozmo_reconstruction/viewer/dense_automatic.py` | `docs/regressions/native-dense-2026-10-04/fix/`; SVG/JSON | PARTIAL: rough rectangle/ceiling/area; doorway location inferred, width assumed |
| Whole-property placement and adjacency, every tier | `src/cozmo_reconstruction/viewer/rough_room.py` | Explicit single rectangular room prior | FAIL: multi-room stitch absent |
| Surface damage class and metric extent | `submission/TECHNICAL_REPORT.md` | Recorded gap, no output manufactured | FAIL |
| Concealed-damage flags with fired rule | `submission/TECHNICAL_REPORT.md` | Recorded gap | FAIL |
| Scope line items keyed to surfaces | `submission/TECHNICAL_REPORT.md` | Recorded gap | FAIL |
| Calibrated interval on every measurement | `src/cozmo_reconstruction/viewer/ceiling.py` | Upper-tile spread explicitly not a confidence interval | FAIL: measurement intervals/calibration absent |
| JSON to evaluator's published schema | `src/cozmo_ingestion/multimodal/schema.json`, viewer schema in `automatic.py` | Internal capture/viewer schemas only | NOT_RUN: evaluator schema not available |
| One command per fresh capture | `src/cozmo_web/capture_cli.py` | `holo-run`; command result/log in reproduction evidence | PASS for assisted video; incomplete for remaining tiers |
| Clean machine to fresh capture in <15 min | `submission/RUNBOOK.md` | Exact prerequisites/commands; ~415 MB CUDA download disclosure | NOT_RUN: no clean-machine timed trial |
| Regenerate reported geometry numbers | `scripts/replay-submission.py` | Included hash-bound raw/cache; before/after JSON/SVG | PASS on development runtime; live CUDA need disclosed; timing itself varies |
| No candidate-owned infrastructure | `Dockerfile`, `src/cozmo_web/worker.py` | Local processing; binary download from official sources | PASS for implemented path; third-party installs require network |
| Opening <=2 cm on >=85%, misses/phantoms included | `submission/BENCHMARK_REPORT.md` | No measured opening ledger; width is assumed | FAIL for measurement implementation; gate NOT_RUN |
| Ceiling <=1.5 cm; repeat spread <=1 cm | `submission/BENCHMARK_REPORT.md` | 2.573 m provisional estimate; ~2.6 m user reference only | NOT_RUN: no instrumented truth or independent repeat |
| Repeat per-wall <=1 cm or 0.5% | `scripts/replay-submission.py` | Identical same-cache repeats, not separate room acquisitions | NOT_RUN for required repeat-capture gate |
| Drift correction with on/off stitched-footprint ablation | `src/cozmo_reconstruction/dense/pipeline.py` | Fixed source ARKit poses; no loop closure | FAIL, as specified for unchanged poses |
| Photos walls/footprint +/-8%, calibrated adjacency/no overlap | `submission/BENCHMARK_REPORT.md` | Photos stop at ingestion | FAIL implementation; accuracy NOT_RUN |
| Video walls +/-3% + calibration | `submission/BENCHMARK_REPORT.md` | Rough source-scale sizes; no per-wall reference ledger | NOT_RUN for error; calibration FAIL |
| LiDAR vs named/versioned consumer app, 2 rooms, >=70% shared dims | `submission/BENCHMARK_REPORT.md` | Explicit empty head-to-head table / missing exports ledger | NOT_RUN |
| >=3 rooms + connector, staged damage 2 classes, same rooms 3 tiers | `submission/RAW_DATA.md` | One submitted video example; full benchmark composition missing | FAIL composition |
| Fix declaration, shipped repair, regenerable before/after/diff | `submission/fix_loop/` | `d9723e2` baseline, `b789117` fix; cached replay and real publisher audits | PARTIAL: repair reproducible; formal declaration retrospective and worst measured gate unavailable |
| Raw sensor logs, ground truth, consumer app exports | `example_data/video/single_room.zip`, `submission/raw/` | Eight original export files; honest missing-data ledger | PARTIAL: logs present, instrumented truth/app exports absent |
| Technical report <=6 pages | `submission/TECHNICAL_REPORT.md` | `output/pdf/technical-report.pdf` | PASS after page-count and visual checks |
| Mirrors/glass/wet look/low light coverage | `submission/TECHNICAL_REPORT.md` | Failure analysis; no condition-labelled challenge benchmark | NOT_RUN |
| Authentic incremental process history | Git history; `submission/fix_loop/code.diff` | Original commits retained; separate error/fix checkpoints | PASS for available history; earlier accumulated checkpoint disclosed |

Submission scope statement from the author: available hardware supported the video/intrinsics branch; photo and LiDAR input pipelines were added but their reconstruction could not be completed on time. This explains project prioritization and does not waive the mandatory tiers.

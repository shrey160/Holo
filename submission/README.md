# Holo submission bundle

Prepared 4 October 2026. This submission delivers the **assisted video + intrinsics + ARKit poses** path through a rough single-room plan and interactive RGB reconstruction. Photo and raw LiDAR ingestion exist, but their reconstruction pipelines could not be completed in the available time. Video development hardware was available; no fresh Pro-device LiDAR acquisition or all-tier accuracy benchmark was completed.

| Requested deliverable | File / artifact | Delivery boundary |
|---|---|---|
| 1. Compliance matrix | [COMPLIANCE_MATRIX.md](COMPLIANCE_MATRIX.md) | Requirement-by-requirement evidence; missing gates visible |
| 2. Capture route + device matrix | [capture protocol PDF](../output/pdf/capture-protocol.pdf), [editable protocol](CAPTURE_PROTOCOL.md), [DEVICE_MATRIX.md](DEVICE_MATRIX.md) | Stock-app assisted video route; one page; no custom iOS build |
| 3. Repository + fresh-capture command | [main README](../README.md), [RUNBOOK.md](RUNBOOK.md), `holo-run` | Live video command; clean-machine under-15-minute gate NOT_RUN |
| 4. Reproduction bundle | [reproduction/README.md](reproduction/README.md), [manifest](reproduction/manifest.json) | Raw video + derived geometry cache; live path and deterministic room replay |
| 5. Benchmark report | [BENCHMARK_REPORT.md](BENCHMARK_REPORT.md), [machine-readable ledger](benchmark/results.json) | Development evidence; all-tier reference benchmark incomplete |
| 6. Fix-loop bundle | [fix_loop/README.md](fix_loop/README.md), [declaration](fix_loop/DECLARATION.md), [code diff](fix_loop/code.diff) | Real before/after repair; no scored worst-gate claim |
| 7. Technical report | [six-page PDF](../output/pdf/technical-report.pdf), [editable report](TECHNICAL_REPORT.md) | Architecture, tiers/devices, drift, errors, calibration, fix and limitations |
| 8. Raw benchmark data | [RAW_DATA.md](RAW_DATA.md), [example ZIP](../example_data/video/single_room.zip), [references](raw/ground-truth.json), [missing data ledger](raw/missing-data.json) | Raw video/sensors included; laser/tape ledger and consumer-app exports absent |

Demo: [Holo walkthrough](https://youtu.be/N7grapMf2BA). The video is a demonstration, not independent accuracy evidence.

Statuses describe actual capability and verification. Document existence does not make an unmet case-study requirement pass. The six-page report is a partial-engineering submission, not an assertion of complete three-tier compliance.

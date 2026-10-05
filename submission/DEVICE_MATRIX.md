# Device and capability matrix

Accuracy is **unverified** for all tiers. Source timestamps, hashes and geometry integrity are verified where stated; these do not establish dimensional accuracy.

| Capture hardware / tier | Input contract | Implemented output | Observed evidence | Accuracy / readiness |
|---|---|---|---|---|
| iPhone 15+ recommended, assisted video | Sensor Recorder ARKit RGB, per-frame K, camera-to-world poses; IMU retained | Verified ingest/preprocess; sparse or dense geometry; rough plan/ceiling with CUDA | Tested non-LiDAR iPhone export, model `iPhone18,3`, iOS 26.6.1, app 1.5/build 5 | Working development path; other models/app exports NOT_RUN; no surveyed accuracy |
| iPhone 15+ photos, 2-8 per room | JPEG/PNG per-room folders, no K/poses/depth required | Validation and canonical capture only | JPEG/PNG tests; real photo fixture was from a Galaxy S24, not iPhone | Reconstruction/stitch/scale unfinished; iPhone still capture NOT_RUN |
| Pro-class iPhone LiDAR | Depth/confidence, intrinsics, poses, versioned conventions | CLI raw-data ingestion only | Supplied Stray-style fixtures; conventions explicitly unverified | Fresh Pro capture, depth fusion, app upload and plan generation unfinished |
| Ordinary camera video (MP4 only) | No supplied K/poses | Unsupported reconstruction | Visible format rejection; no silently invented poses | NOT_IMPLEMENTED |
| Android assisted capture | New validated adapter required | Deferred | Photo files can be validated independent of manufacturer | No Android video/reconstruction claim |

| Processing machine | Path | Requirements / measured development configuration |
|---|---|---|
| Windows x64 + NVIDIA CUDA | Full assisted-video dense workflow | Development: Windows 11 10.0.26200; ASUS TUF A14; Ryzen AI 9 HX 370 (12 cores/24 threads), ~31.1 GiB usable RAM, RTX 4060 Laptop GPU; driver 610.74; PyCOLMAP 4.2.1 CPU + official COLMAP 4.2.1 CUDA executable |
| CPU-only Windows/Linux | Ingestion, preprocessing, fixed-camera sparse preview; no ceiling estimate | Python 3.12 via uv; FFmpeg/FFprobe; web/reconstruct extras |
| Linux native NVIDIA | Dense Python CUDA path | `dense` extra, usable compatible NVIDIA driver; Windows fix shares estimator |
| Docker CPU / GPU | Container frontend/API and isolated processing | CPU compose is sparse; GPU overlay requires NVIDIA runtime support. Docker was not rerun for the current correction |

The native CUDA executable archive (~415 MB) is fetched by a checksum-pinned script, not vendored. No candidate-owned service is required. Node 24 is needed to build the optional web UI, not to run the capture CLI. Sensor/driver/runtime versions are recorded as evidence, not compatibility guarantees for untested machines.

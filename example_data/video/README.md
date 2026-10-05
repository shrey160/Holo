# Example assisted-video capture

`single_room.zip` is the complete original Sensor Recorder Pro ARKit session supplied by the author. It contains RGB, intrinsics/poses, IMU/motion/magnetometer logs and metadata; no LiDAR is used. [Asset checksums](manifest.json), [capture route](../../submission/CAPTURE_PROTOCOL.md), [one-command run](../../submission/RUNBOOK.md).

```shell
uv run --locked --extra web --extra reconstruct holo-run example_data/video/single_room.zip --output outputs/example-room --mode dense
```

Dense requires a usable CUDA backend. Use `--mode preview` for a CPU sparse preview without a ceiling estimate. Use a new output folder each time. The A4 object appears only in the opening seconds; reference measurements are not applied in automatic reconstruction.

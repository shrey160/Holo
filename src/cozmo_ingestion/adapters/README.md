# Source adapters

Adapters translate an inspected export format into the core `SourceCapture` contract. This folder currently supports **Sensor Recorder Pro 1.5/build 5 ARKit**, a single rear-wide-camera iOS session. It does not support generic MP4 input, Android exports or LiDAR sessions.

| File | Responsibility |
|---|---|
| `sensor_recorder.py` | Inventory/hash assets, parse metadata and CSV records, validate a finished compatible session |
| `sensor_recorder_schema.py` | Accepted stream headers, source-format identity and role declarations |

The supplied exports contain `meta.json`, `wide.mp4`, `arkit_pose.csv` and enabled sensor sidecars. Preserve all original files together; metadata and schema validation determine required streams. Unsupported versions, units, axes or stream layouts fail explicitly rather than being guessed.

## Adding support

1. Inspect a real export and establish headers, units, timestamps, pose direction and camera conventions.
2. Implement the protocol in [ports.py](../ports.py), producing the typed source records in [models.py](../models.py).
3. Configure/inject the adapter explicitly in the pipeline. Adapt canonical contracts and reader profiles if the new source requires different capabilities.
4. Add meaningful malformed/valid-format tests and run real-source ingestion plus verification. A parser alone does not establish support.

Run the existing adapter/annotation tests from `proto-2`:

```shell
uv run --locked python -m unittest discover -s tests -p "test_adapter_annotations.py" -v
```

[Core package guide](../README.md) · [Architecture](../../../ARCHITECTURE.md)

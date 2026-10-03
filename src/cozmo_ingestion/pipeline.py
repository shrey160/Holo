"""Application service coordinating format parsing, validation and publication."""

import hashlib
import time
from pathlib import Path

from .adapters.sensor_recorder import SensorRecorderAdapter
from .annotations import normalize_annotations
from .bundle import BundleTransaction, BundleWriter
from .contracts import DEFAULT_POLICY, IngestionPolicy
from .errors import require
from .media import FFmpegVideoInspector
from .models import BundleContent, IngestionRequest, IngestionResult, RunMetadata
from .normalization import normalize
from .ports import CaptureAdapter, VideoInspector
from .storage import encoded, sha256


class IngestionPipeline:
    """Dependencies are injected; every run has its own transaction and state."""

    def __init__(
        self,
        adapter: CaptureAdapter | None = None,
        video_inspector: VideoInspector | None = None,
        writer: BundleWriter | None = None,
        policy: IngestionPolicy = DEFAULT_POLICY,
    ) -> None:
        self.adapter = adapter if adapter is not None else SensorRecorderAdapter()
        self.video_inspector = (
            video_inspector if video_inspector is not None else FFmpegVideoInspector()
        )
        self.writer = writer if writer is not None else BundleWriter()
        self.policy = policy

    def run(self, request: IngestionRequest) -> IngestionResult:
        """Validate an immutable capture and publish one complete output bundle."""
        request = IngestionRequest(
            Path(request.source).resolve(),
            Path(request.output).resolve(),
            Path(request.annotations).resolve() if request.annotations else None,
        )
        started = time.perf_counter()
        with BundleTransaction(request, self.adapter.name) as transaction:
            assets = self.adapter.inventory(request.source)
            before = {asset["id"]: asset["sha256"] for asset in assets}
            capture = self.adapter.load(request.source, before)
            video = self.video_inspector.inspect(request.source / "wide.mp4")
            association, ticks = self.adapter.associate(capture, video, self.policy)
            annotated = normalize_annotations(
                request.annotations, before["wide.mp4"], capture.camera_rows, capture.origin
            )
            if request.annotations:
                assets.append(
                    {
                        "id": "capture_annotation",
                        "root": "annotations",
                        "path": request.annotations.name,
                        "role": "user_scale_prior",
                        "bytes": request.annotations.stat().st_size,
                        "sha256": annotated["source_annotation_sha256"],
                    }
                )
            identity = hashlib.sha256(encoded(before).encode()).hexdigest()
            capture_id = "sr-" + identity[:16]
            observations = normalize(
                capture,
                video,
                ticks,
                capture_id,
                annotated,
                self.adapter.stream_headers,
                self.policy,
            )
            after = {
                asset["id"]: asset["sha256"] for asset in self.adapter.inventory(request.source)
            }
            require(before == after, "SOURCE_CHANGED", "Source assets changed during ingestion")
            if request.annotations:
                require(
                    sha256(request.annotations) == annotated["source_annotation_sha256"],
                    "SOURCE_CHANGED",
                    "Annotation changed during ingestion",
                )
            content = BundleContent(
                request=request,
                capture=capture,
                observations=observations,
                video=video,
                assets=assets,
                source_hashes=before,
                association=association,
                annotations=annotated,
                source_identity=identity,
                capture_id=capture_id,
                adapter_name=self.adapter.name,
                stream_headers=self.adapter.stream_headers,
                policy=self.policy,
            )
            runtime = RunMetadata(started, self.video_inspector.version())
            manifest, report = self.writer.write(transaction.stage, content, runtime)
            transaction.publish()
        return IngestionResult(manifest, report, request.output)


def ingest(
    source: str | Path,
    output: str | Path,
    annotations: str | Path | None = None,
    ffmpeg: str | Path | None = None,
) -> tuple[dict, dict]:
    """Convenience API for callers that do not need injected dependencies."""
    result = IngestionPipeline(video_inspector=FFmpegVideoInspector(ffmpeg)).run(
        IngestionRequest(Path(source), Path(output), Path(annotations) if annotations else None)
    )
    return result.manifest, result.report

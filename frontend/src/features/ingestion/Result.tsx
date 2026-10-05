import { useState } from "react";
import {
  downloadResult,
  preprocess,
  reconstruct,
  stateLabel,
  type Job,
} from "../../api/client";
import { PreprocessingResult } from "../preprocessing/PreprocessingResult";
import { PipelineProgress } from "./PipelineProgress";

const explanations: Record<string, string> = {
  INITIAL_RGB_DISCARD:
    "The video omits its first source observation during decoding. Decoded frames are matched to odometry from frame 1; the unmatched pose is retained.",
  STRAY_CONVENTIONS_UNVERIFIED:
    "This supplied export uses a Stray-style layout. Exporter identity and acceleration units remain unverified; raw values are preserved. Depth is excluded from assisted RGB.",
  NON_NORMAL_TRACKING:
    "ARKit tracking was limited in some frames. Every original observation is retained.",
  APPARENT_POSE_SPEED:
    "A supplied camera-pose step exceeds the speed threshold. This finding does not establish drift or measurement error.",
  EXPOSURE_EXCEEDS_REQUESTED_CAP:
    "Some recorded frames exceed the requested exposure limit, including startup frames.",
  PARTIAL_IMU_BOUNDARY_COVERAGE:
    "Some camera frames fall outside the IMU time range. No sensor values are extrapolated.",
  SCALE_PRIOR_NOT_LOCALIZED:
    "Reference dimensions are recorded. Object corners and scale have not been estimated.",
  PHYSICAL_CALIBRATION_UNVERIFIED:
    "Physical camera/IMU registration and measurement accuracy remain unverified.",
  INITIAL_EXPOSURE_EXCEEDS_REQUESTED_CAP:
    "Some startup frames exceed the requested exposure limit.",
  POSE_SPEED_OUTLIER:
    "A supplied-pose step exceeds the speed threshold. This is a quality finding, not a drift diagnosis.",
  INITIAL_LIMITED_TRACKING:
    "ARKit tracking was limited at the beginning of this recording.",
  LIMITED_TRACKING:
    "Some frames have limited ARKit tracking. Their source records are retained.",
  RECORD_SLOT_DISCONTINUITY:
    "The recorder skipped a slot number. Check timestamps before interpreting this as a missing image.",
  POSE_SPEED:
    "The supplied camera poses contain an apparent speed jump. Geometry accuracy has not been verified.",
};

export function Result({
  job,
  onPrepared,
  denseAvailable = false,
}: {
  job: Job;
  onPrepared: (id: string) => Promise<void>;
  denseAvailable?: boolean;
}) {
  const [error, setError] = useState("");
  const [downloading, setDownloading] = useState(false);
  const [preparing, setPreparing] = useState(false);
  const result = job.summary;
  async function prepare() {
    setError("");
    setPreparing(true);
    try {
      const run = await preprocess(job.id);
      await onPrepared(run.id);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setPreparing(false);
    }
  }
  async function buildReconstruction(dense = false) {
    setError("");
    setPreparing(true);
    try {
      const run = await reconstruct(job.id, dense);
      await onPrepared(run.id);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setPreparing(false);
    }
  }
  async function save(kind: "report" | "download") {
    setError("");
    setDownloading(true);
    try {
      await downloadResult(job.id, kind);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setDownloading(false);
    }
  }
  return (
    <section className="panel section result" aria-live="polite">
      <div className="result-header">
        <div>
          <span className="eyebrow">CAPTURE RESULT</span>
          <h2>{job.label}</h2>
        </div>
        <span className={`status ${job.state.toLowerCase()}`}>
          {stateLabel(job.state)}
        </span>
      </div>
      {job.error && (
        <div role="alert" className="notice error">
          <strong>{job.error.code}</strong>
          <p>{job.error.message}</p>
          {job.failed_stage && (
            <p>Stopped during: {stateLabel(job.failed_stage)}.</p>
          )}
        </div>
      )}
      {!["SUCCEEDED", "FAILED"].includes(job.state) && (
        <PipelineProgress job={job} />
      )}
      {result && result.modality === "photos" && (
        <div className="photo-result">
          <div className="metrics">
            <div>
              <strong>{result.distinct_image_count ?? 0}</strong>
              <span>Distinct photos</span>
            </div>
            <div>
              <strong>{result.room_count ?? 0}</strong>
              <span>Rooms detected</span>
            </div>
            <div>
              <strong>{result.verification.artifacts_verified}</strong>
              <span>Artifacts verified</span>
            </div>
          </div>
          <div className="notice">
            Input verified. The photo tier has no camera intrinsics or poses by
            design; no scale was applied.
            {result.profile === "OUTSIDE_PHOTO_PROFILE" &&
              " This set is outside the 2–8 photo profile."}
            {" Photo preprocessing and reconstruction are not implemented yet."}
          </div>
          <h3>Available input evidence</h3>
          <div className="stream-list">
            {Object.entries(result.capabilities).map(([name, value]) => (
              <span key={name}>
                {name.replaceAll("_", " ")}{" "}
                <b>{value.replaceAll("_", " ").toLowerCase()}</b>
              </span>
            ))}
          </div>
          <h3>Findings ({result.findings.length})</h3>
          {result.findings.map((finding, index) => (
            <details key={index} className="finding">
              <summary>
                {explanations[finding.code] ||
                  finding.code.replaceAll("_", " ").toLowerCase()}
              </summary>
              <code>{finding.code}</code>
              <pre>{JSON.stringify(finding.details, null, 2)}</pre>
            </details>
          ))}
          <p className="caption">
            Declared reference dimensions are metadata only; object corners are
            not localized and scale remains unapplied.
          </p>
          <div className="actions">
            <button
              className="primary"
              disabled={downloading}
              onClick={() => save("download")}
            >
              {downloading ? "Preparing download…" : "Download photo bundle ↓"}
            </button>
            <button
              className="secondary"
              disabled={downloading}
              onClick={() => save("report")}
            >
              Validation JSON ↓
            </button>
          </div>
          <p className="caption">
            The portable archive includes the original photos and the canonical
            capture bundle with preserved EXIF and room membership.
          </p>
        </div>
      )}
      {result && result.modality !== "photos" && (
        <>
          <div className="metrics">
            <div>
              <strong>{result.frame_count.toLocaleString()}</strong>
              <span>RGB frames retained</span>
            </div>
            <div>
              <strong>{result.verification.artifacts_verified}</strong>
              <span>Artifacts verified</span>
            </div>
            <div>
              <strong>Preserved</strong>
              <span>Original source values</span>
            </div>
          </div>
          <div className="notice">
            Input verified. Physical measurement accuracy remains unverified.
            {result.reconstruction
              ? result.reconstruction.quality === "PARTIAL_ROOMWISE_EVIDENCE"
                ? " Dense geometry and room-wise evidence are ready; the room outlines are incomplete."
                : result.reconstruction.geometry_source === "RGB_DENSE_STEREO"
                  ? " Dense RGB reconstruction is ready."
                  : " Sparse preview only; dense reconstruction has not run."
              : " Reconstruction has not completed."}
            {!result.preprocessing && " Preprocessing has not run."}
          </div>
          {result.automatic_reconstruction?.status === "SKIPPED" && (
            <p className="notice">{result.automatic_reconstruction.reason}</p>
          )}
          {result.reconstruction ? (
            <div className="preprocessing-start">
              <h3>
                {result.reconstruction.quality === "PARTIAL_ROOMWISE_EVIDENCE"
                  ? "Room-wise evidence ready; plan incomplete"
                  : result.reconstruction.geometry_source === "RGB_DENSE_STEREO"
                    ? "Dense reconstruction ready"
                    : "Sparse preview"}
              </h3>
              <p>
                {result.reconstruction.point_count.toLocaleString()} display
                points from {result.reconstruction.selected_views} RGB views.
                The plan is an approximate hypothesis; it is not a surveyed
                plan.
              </p>
              <div className="metrics reconstruction-summary">
                <div>
                  <strong>
                    {result.reconstruction.geometry_source ===
                    "RGB_DENSE_STEREO"
                      ? "Dense RGB"
                      : "Sparse preview"}
                  </strong>
                  <span>Reconstruction quality</span>
                </div>
                <div>
                  <strong>
                    {result.reconstruction.room_count != null
                      ? `${result.reconstruction.completed_room_count}/${result.reconstruction.room_count} outlines`
                      : result.reconstruction.dimensions_estimated_m
                          ?.map((n) => n.toFixed(2))
                          .join(" × ") || "Preview only"}
                    {result.reconstruction.dimensions_estimated_m ? " m" : ""}
                  </strong>
                  <span>Approximate room size</span>
                </div>
                <div>
                  <strong>
                    {result.reconstruction.ceiling_estimated_m != null
                      ? `${result.reconstruction.ceiling_estimated_m.toFixed(2)} m`
                      : "Unavailable"}
                  </strong>
                  <span>Provisional ceiling height</span>
                </div>
              </div>
              {result.reconstruction.geometry_source !== "RGB_DENSE_STEREO" && (
                <p className="caption">
                  This is a sparse preview. Ceiling estimation requires dense
                  geometry and sufficient upper-room coverage.
                </p>
              )}
              <a
                className="primary"
                href={`/?reconstruction=${encodeURIComponent(result.reconstruction.id)}#reconstruction`}
              >
                Open plan &amp; interactive 3D →
              </a>
              {denseAvailable &&
                result.reconstruction.geometry_source !==
                  "RGB_DENSE_STEREO" && (
                  <button
                    className="secondary"
                    disabled={preparing}
                    onClick={() => buildReconstruction(true)}
                  >
                    {preparing
                      ? "Starting…"
                      : "Generate dense reconstruction →"}
                  </button>
                )}
            </div>
          ) : (
            result.preprocessing &&
            ["SUCCEEDED", "FAILED"].includes(job.state) && (
              <div className="preprocessing-start">
                <h3>Generate reconstruction</h3>
                <p>
                  Use this verified prepared capture. A separate run preserves
                  the input and allows retries.
                </p>
                <button
                  className="primary"
                  disabled={preparing}
                  onClick={() => buildReconstruction()}
                >
                  {preparing
                    ? "Starting…"
                    : job.state === "FAILED"
                      ? "Retry reconstruction →"
                      : "Reconstruct room →"}
                </button>
              </div>
            )
          )}
          {result.preprocessing ? (
            <PreprocessingResult jobId={job.id} result={result.preprocessing} />
          ) : (
            result.capabilities.pose === "EXPORTER_DECLARED" && (
              <div className="preprocessing-start">
                <h3>Prepare views &amp; reconstruct</h3>
                <p>
                  Select useful RGB frames, preserve calibration and poses, and
                  check image overlap and native IMU coverage. LiDAR and
                  grounding measurements are excluded.
                </p>
                <button
                  className="primary"
                  disabled={preparing || job.state !== "SUCCEEDED"}
                  onClick={prepare}
                >
                  {preparing ? "Starting…" : "Prepare & reconstruct →"}
                </button>
                <p className="caption">
                  Creates a separate run and reconstructs after preprocessing.
                  Your verified capture remains available.
                </p>
              </div>
            )
          )}
          {job.reference_image && (
            <div className="reference-photo">
              <h3>Grounding object photo</h3>
              <img
                src={`/api/jobs/${job.id}/reference-image`}
                alt="Uploaded grounding object"
              />
              <span>{job.reference_image.original_name}</span>
              <p className="caption">
                Saved with this capture and included in its download. Object
                detection and scale estimation have not run.
              </p>
            </div>
          )}
          <h3>Available input streams</h3>
          <div className="stream-list">
            {Object.entries(result.capabilities).map(([name, value]) => (
              <span key={name}>
                {name === "grounding_object"
                  ? "reference dimensions"
                  : name.replaceAll("_", " ")}{" "}
                <b>{value.replaceAll("_", " ").toLowerCase()}</b>
              </span>
            ))}
          </div>
          <h3>Tracking</h3>
          <p>
            {Object.entries(result.tracking_states)
              .map(([name, count]) => `${count.toLocaleString()} ${name}`)
              .join(" · ")}
          </p>
          <h3>Findings ({result.findings.length})</h3>
          {result.findings.map((finding, index) => (
            <details key={index} className="finding">
              <summary>
                {explanations[finding.code] ||
                  finding.code.replaceAll("_", " ").toLowerCase()}
              </summary>
              <code>{finding.code}</code>
              <pre>{JSON.stringify(finding.details, null, 2)}</pre>
            </details>
          ))}
          <div className="actions">
            <button
              className="primary"
              disabled={downloading}
              onClick={() => save("download")}
            >
              {downloading
                ? "Preparing download…"
                : "Download capture bundle ↓"}
            </button>
            <button
              className="secondary"
              disabled={downloading}
              onClick={() => save("report")}
            >
              Validation JSON ↓
            </button>
          </div>
          <p className="caption">
            The portable archive includes original files, annotations,
            {job.reference_image ? " the object photo," : ""} and the canonical
            bundle.
            {result.reconstruction &&
              " It also includes audited geometry and the portable plan/3D viewer."}
          </p>
        </>
      )}
      {error && (
        <p role="alert" className="error-text">
          {error}
        </p>
      )}
    </section>
  );
}

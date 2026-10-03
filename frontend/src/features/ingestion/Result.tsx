import { useState } from "react";
import { downloadResult, stateLabel, type Job } from "../../api/client";

const explanations: Record<string, string> = {
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

export function Result({ job }: { job: Job }) {
  const [error, setError] = useState("");
  const [downloading, setDownloading] = useState(false);
  const result = job.summary;
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
        </div>
      )}
      {!result && !job.error && (
        <p className="processing">
          <span className="spinner" />
          Your original export is being checked. Processing time depends on the
          capture.
        </p>
      )}
      {result && (
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
            Ingestion verified. Measurement accuracy is unverified; grounding,
            preprocessing and reconstruction have not run.
          </div>
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

import { useState } from "react";
import type { Preprocessing } from "../../api/client";

export function PreprocessingResult({
  jobId,
  result,
}: {
  jobId: string;
  result: Preprocessing;
}) {
  const [page, setPage] = useState(0);
  const pages = Math.ceil(result.previews.length / 12);
  return (
    <section className="preprocessing-result">
      <span className="eyebrow">RECONSTRUCTION VIEWS</span>
      <h3>Prepared for review</h3>
      <div className="metrics">
        <div>
          <strong>{result.selected_count}</strong>
          <span>Selected views</span>
        </div>
        <div>
          <strong>{result.supported_links}</strong>
          <span>Supported neighboring links</span>
        </div>
        <div>
          <strong>{result.weak_links.length}</strong>
          <span>Weak links to review</span>
        </div>
      </div>
      <p>
        Selected from {result.candidate_count} candidates and{" "}
        {result.source_frame_count.toLocaleString()} original frames. Maximum
        gap: {result.maximum_selected_gap_seconds.toFixed(2)} seconds. Native
        calibration, poses and IMU samples are retained. LiDAR and grounding
        measurements are excluded.
      </p>
      <div className="notice">
        {result.readiness === "REVIEW_REQUIRED"
          ? "Review required before reconstruction."
          : "Ready for a reconstruction trial."}{" "}
        {result.low_baseline_links} links have little camera translation. Visual
        overlap does not establish depth or dimensional accuracy. Review doorway
        transitions in the gallery.
      </div>
      {result.pose_speed_events.length > 0 && (
        <p>
          Pose motion findings:{" "}
          {result.pose_speed_events
            .map(
              (e) =>
                `${e.seconds.toFixed(2)} s (${e.speed_m_s.toFixed(2)} m/s)`,
            )
            .join(" · ")}
          . Source poses were not corrected.
        </p>
      )}
      {result.weak_links.length > 0 && (
        <details className="finding">
          <summary>
            Inspect weak visual connections ({result.weak_links.length})
          </summary>
          <p>
            These intervals remain in the output. The selection already includes
            additional intervening candidates where available.
          </p>
          <ul>
            {result.weak_links.map((p) => (
              <li key={`${p.first_rank}-${p.second_rank}`}>
                Frames {p.first_rank} → {p.second_rank} ·{" "}
                {p.time_gap_seconds.toFixed(2)} s
              </li>
            ))}
          </ul>
        </details>
      )}
      <div className="view-gallery">
        {result.previews.slice(page * 12, (page + 1) * 12).map((view) => (
          <figure key={view.rank}>
            <img
              src={`/api/jobs/${jobId}/previews/${view.rank}`}
              alt={`Selected frame ${view.rank} at ${view.seconds.toFixed(2)} seconds`}
              loading="lazy"
            />
            <figcaption>
              <strong>
                {view.seconds.toFixed(2)} s · frame {view.rank}
              </strong>
              <span>Quality score {view.score.toFixed(2)}</span>
              {view.flags.length > 0 && (
                <small>
                  {view.flags
                    .map((f) => f.replaceAll("_", " ").toLowerCase())
                    .join(" · ")}
                </small>
              )}
            </figcaption>
          </figure>
        ))}
      </div>
      <div className="actions">
        <button
          className="secondary"
          disabled={page === 0}
          onClick={() => setPage((p) => p - 1)}
        >
          ← Previous views
        </button>
        <span>
          Page {page + 1} / {pages}
        </span>
        <button
          className="secondary"
          disabled={page + 1 >= pages}
          onClick={() => setPage((p) => p + 1)}
        >
          Next views →
        </button>
      </div>
      <p>
        <a
          href={`/api/jobs/${jobId}/preprocessing-report`}
          download="preprocessing-report.json"
        >
          Download preprocessing report ↓
        </a>
      </p>
      <p className="caption">
        The capture download now includes selected native-grid JPEGs, per-frame
        calibration and poses, original IMU samples, candidate scores,
        image-pair diagnostics and input usage. No room labels or floorplan have
        been generated.
      </p>
    </section>
  );
}

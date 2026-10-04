import { lazy, Suspense, useEffect, useState } from "react";
import { readAsset } from "./types";

export type GaussianResult = {
  id: string;
  gaussians: number;
  camera_position: number[];
  camera_target: number[];
  initial_psnr_db: number;
  final_psnr_db: number;
};

const SplatCanvas = lazy(() => import("./SplatCanvas"));

export function GaussianViewer({
  reconstructionId,
}: {
  reconstructionId: string;
}) {
  const [rows, setRows] = useState<GaussianResult[]>([]),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(true),
    [open, setOpen] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    setRows([]);
    setError("");
    setLoading(true);
    setOpen(false);
    readAsset<GaussianResult[]>(
      `/api/gaussians?reconstruction_id=${encodeURIComponent(reconstructionId)}`,
      controller.signal,
    )
      .then(setRows)
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [reconstructionId]);
  if (!rows.length && !error && !loading) return null;
  return (
    <section className="panel section gaussian-section">
      <p className="eyebrow">GAUSSIAN APPEARANCE / EXPERIMENTAL</p>
      <h2>Explore the captured room.</h2>
      <p>
        Trained RGB appearance with fixed cameras and scale. Unseen viewpoints
        can blur or tear. Coverage remains incomplete; this view does not
        establish room dimensions or wall boundaries.
      </p>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {loading && <p role="status">Checking for Gaussian reconstruction…</p>}
      {rows[0] && (
        <>
          <p>
            {rows[0].gaussians.toLocaleString()} Gaussians · Photometric
            holdout: {rows[0].initial_psnr_db.toFixed(1)} →{" "}
            {rows[0].final_psnr_db.toFixed(1)} dB.
          </p>
          <p className="viewer-note">
            Validation images were excluded from appearance training. Stereo
            initialization used all source views; this is not an independent
            geometry benchmark.
          </p>
          <button
            className="primary"
            onClick={() => setOpen((current) => !current)}
            aria-expanded={open}
          >
            {open ? "Close Gaussian view" : "Open Gaussian view"}
          </button>
          {open && (
            <Suspense
              fallback={<p role="status">Loading Gaussian renderer…</p>}
            >
              <SplatCanvas result={rows[0]} />
            </Suspense>
          )}
          <div className="gaussian-comparison">
            <figure>
              <img
                src={`/api/gaussians/${rows[0].id}/initial.jpg`}
                alt="Withheld source image on the left; initial Gaussian rendering on the right"
                loading="lazy"
              />
              <figcaption>Source / before training</figcaption>
            </figure>
            <figure>
              <img
                src={`/api/gaussians/${rows[0].id}/final.jpg`}
                alt="The same withheld source image on the left; trained Gaussian rendering on the right"
                loading="lazy"
              />
              <figcaption>Source / after training</figcaption>
            </figure>
          </div>
          <div className="reconstruction-downloads">
            <a href={`/api/gaussians/${rows[0].id}/room.splat`} download>
              Download Gaussian scene
            </a>
            <a href={`/api/gaussians/${rows[0].id}/report.json`} download>
              Experiment report
            </a>
          </div>
        </>
      )}
    </section>
  );
}

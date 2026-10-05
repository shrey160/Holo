import { useEffect, useState } from "react";
import { PointCloudViewer } from "./PointCloudViewer";
import { RoomPlan } from "./RoomPlan";
import { GaussianViewer } from "./GaussianViewer";
import { readAsset, type Plan, type Result, type Scene } from "./types";

export function Reconstruction() {
  const [results, setResults] = useState<Result[]>([]),
    [selected, setSelected] = useState(
      new URLSearchParams(window.location.search).get("reconstruction") || "",
    ),
    [loaded, setLoaded] = useState<{ scene: Scene; plan: Plan } | null>(null),
    [error, setError] = useState(""),
    [listError, setListError] = useState(""),
    [listing, setListing] = useState(true),
    [retry, setRetry] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setListing(true);
    setListError("");
    readAsset<Result[]>("/api/reconstructions", controller.signal)
      .then((rows) => {
        setResults(rows);
        setListError("");
        setSelected((current) =>
          rows.some((r) => r.id === current) ? current : rows[0]?.id || "",
        );
      })
      .catch((e) => {
        if (e.name !== "AbortError")
          setListError(
            "Cannot refresh results. Check the server connection and try again.",
          );
      })
      .finally(() => {
        if (!controller.signal.aborted) setListing(false);
      });
    const timer = setInterval(() => {
      readAsset<Result[]>("/api/reconstructions", controller.signal)
        .then((rows) => {
          setResults(rows);
          setListError("");
          setSelected((current) => current || rows[0]?.id || "");
        })
        .catch((e) => {
          if (e.name !== "AbortError")
            setListError(
              "Cannot refresh results. Showing the last loaded reconstruction.",
            );
        });
    }, 5000);
    return () => {
      clearInterval(timer);
      controller.abort();
    };
  }, [retry]);
  useEffect(() => {
    if (!selected) return;
    const controller = new AbortController();
    setLoaded(null);
    setError("");
    const url = new URL(window.location.href);
    url.searchParams.set("reconstruction", selected);
    window.history.replaceState(null, "", url);
    const base = `/api/reconstructions/${encodeURIComponent(selected)}`;
    Promise.all([
      readAsset<Scene>(`${base}/scene.json`, controller.signal),
      readAsset<Plan>(`${base}/plan.json`, controller.signal),
    ])
      .then(([scene, plan]) => setLoaded({ scene, plan }))
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    return () => controller.abort();
  }, [selected, retry]);
  const base = `/api/reconstructions/${encodeURIComponent(selected)}`;
  return (
    <div className="reconstruction-workspace">
      <section className="reconstruction-intro">
        <p className="eyebrow">RECONSTRUCTION / OBSERVED SPACE</p>
        <h1>Your room, taking shape.</h1>
        <p>Explore a rough generated plan and the reconstructed room in 3D.</p>
      </section>
      <section className="panel reconstruction-selection">
        <label htmlFor="reconstruction-select">Capture reconstruction</label>
        <select
          id="reconstruction-select"
          value={selected}
          onChange={(e) => setSelected(e.target.value)}
          disabled={!results.length}
        >
          {results.map((r) => (
            <option key={r.id} value={r.id}>
              {r.label} ·{" "}
              {r.geometry_source === "CPU_SPARSE_TRIANGULATION"
                ? "Sparse preview"
                : "Dense RGB"}
            </option>
          ))}
        </select>
        <button onClick={() => setRetry((n) => n + 1)}>Refresh results</button>
      </section>
      {listError && (
        <p className="notice" role="status">
          {listError}
        </p>
      )}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {listing && <p role="status">Loading reconstruction results…</p>}
      {!listing && !error && !listError && !results.length && (
        <section className="panel section">
          <h2>No reconstruction published yet</h2>
          <p>
            Upload a Sensor Recorder ARKit capture with automatic reconstruction
            enabled. Its rough plan and interactive 3D will appear here after
            verification and processing.
          </p>
        </section>
      )}
      {selected && !loaded && !error && (
        <p role="status">Loading plan and geometry…</p>
      )}
      {loaded && (
        <>
          <div className="reconstruction-metrics">
            <div>
              <strong>{loaded.scene.selected_views}</strong>
              <span>source views</span>
            </div>
            <div>
              <strong>
                {loaded.scene.source_voxel_points.toLocaleString()}
              </strong>
              <span>
                {loaded.scene.geometry_source === "CPU_SPARSE_TRIANGULATION"
                  ? "triangulated RGB points"
                  : "RGB stereo voxels"}
              </span>
            </div>
            <div>
              <strong>{loaded.scene.reviewed_spans.length}</strong>
              <span>reviewed wall patches</span>
            </div>
            <div>
              <strong>Unverified</strong>
              <span>physical dimensions</span>
            </div>
          </div>
          <div className="reconstruction-overview panel">
            <span>
              <b>
                {loaded.scene.geometry_source === "CPU_SPARSE_TRIANGULATION"
                  ? "Sparse preview"
                  : "Dense RGB reconstruction"}
              </b>
              <small>Geometry quality</small>
            </span>
            <span>
              <b>
                {loaded.plan.roomwise
                  ? `${loaded.plan.roomwise.rooms.length} room candidates`
                  : loaded.plan.rough_room?.dimensions_estimated_m
                      .map((n) => n.toFixed(2))
                      .join(" × ") || "Unavailable"}
                {loaded.plan.rough_room ? " m" : ""}
              </b>
              <small>
                {loaded.plan.roomwise
                  ? "Capture route"
                  : "Approximate room size"}
              </small>
            </span>
            <span>
              <b>
                {loaded.plan.rough_room?.ceiling_estimate?.height_estimated_m !=
                null
                  ? `${loaded.plan.rough_room.ceiling_estimate.height_estimated_m.toFixed(2)} m`
                  : "Unavailable"}
              </b>
              <small>Provisional ceiling height</small>
            </span>
          </div>
          <p className="viewer-note reconstruction-caveat">
            {loaded.scene.geometry_source === "CPU_SPARSE_TRIANGULATION"
              ? "Automatic sparse preview: a rectangle estimates observed coverage. Furniture and missing walls can bias it; multiple rooms are not segmented. Poses and source scale are unchanged."
              : loaded.plan.roomwise
                ? "Room-wise evidence separates scanning stays and fits supported walls locally. Doorways and connectors remain unresolved; some room outlines may be unavailable."
                : loaded.plan.rough_room
                  ? "The complete floor plan is an approximate room hypothesis. Physical dimensions remain unverified; source geometry and scale are unchanged."
                  : "Room coverage is incomplete. Reference calibration remains unresolved; poses and estimated scale are unchanged. Assistant architectural decisions remain hypotheses."}
          </p>
          <RoomPlan key={selected} plan={loaded.plan} base={base} />
          <PointCloudViewer scene={loaded.scene} base={base} />
          {loaded.scene.geometry_source !== "CPU_SPARSE_TRIANGULATION" && (
            <GaussianViewer reconstructionId={selected} />
          )}
          <div className="reconstruction-downloads">
            <a href={`${base}/boundary-report.json`} download>
              Boundary evidence JSON
            </a>
            <a href={`${base}/reviewed-plan.svg`} download>
              Plan evidence SVG
            </a>
          </div>
        </>
      )}
    </div>
  );
}

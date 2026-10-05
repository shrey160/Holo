import { useState } from "react";
import type { Plan, RoomwiseReport } from "./types";

const colors = ["#146f60", "#7659a5", "#a76a20"];
const explainFailure = (message = "") =>
  message.includes("three source plane")
    ? "Too few independently supported wall surfaces."
    : message.includes("differently oriented")
      ? "Missing wall evidence in another direction."
      : message.includes("too narrow")
        ? "Wall evidence covers too narrow an area."
        : message.includes("scanning path")
          ? "The proposed outline does not cover the scanning region."
          : "Too little supported room geometry.";

export function RoomwisePlan({
  plan,
  report,
  base,
  selector,
}: {
  plan: Plan;
  report: RoomwiseReport;
  base: string;
  selector: React.ReactNode;
}) {
  const [selected, setSelected] = useState("all");
  const rooms = report.rooms.filter(
    (r) => selected === "all" || r.id === selected,
  );
  const points = [
    ...plan.camera_path_uv_m,
    ...rooms.flatMap(
      (r) => r.structure?.suggested_spans.flatMap((s) => s.uv) || [],
    ),
    ...rooms.flatMap((r) => r.rough_room?.polygon_floor_uv_m || []),
  ];
  const low = [0, 1].map((i) => Math.min(...points.map((p) => p[i])) - 0.5);
  const high = [0, 1].map((i) => Math.max(...points.map((p) => p[i])) + 0.5);
  const scale = Math.min(820 / (high[0] - low[0]), 500 / (high[1] - low[1]));
  const coordinates = (uv: number[][]) =>
    uv
      .map(
        ([u, v]) =>
          `${40 + (u - low[0]) * scale},${550 - (v - low[1]) * scale}`,
      )
      .join(" ");
  return (
    <section className="reconstruction-view panel">
      <div className="reconstruction-view-heading">
        <div>
          <p className="eyebrow">01 / ROOM-WISE PLAN</p>
          <h2>Rooms along your capture route</h2>
        </div>
        <a href={`${base}/rough-room.svg`} download>
          Download room evidence SVG
        </a>
      </div>
      <p className="muted">
        Scanning stays suggest separate rooms. Doorway crossings and connectors
        need review. Colored lines are supported geometric candidates; furniture
        can remain. A closed outline appears only when its support checks pass.
      </p>
      <div className="viewer-controls">
        {selector}
        <label>
          Room{" "}
          <select
            aria-label="Room evidence"
            value={selected}
            onChange={(e) => setSelected(e.target.value)}
          >
            <option value="all">All rooms</option>
            {report.rooms.map((r) => (
              <option key={r.id} value={r.id}>
                {r.id}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="room-plan-scroll">
        <svg
          className="room-plan"
          viewBox="0 0 900 600"
          role="img"
          aria-label="Room scanning paths and provisional wall evidence in shared coordinates"
        >
          <rect width="900" height="600" fill="#fcfcf8" />
          <polyline
            points={coordinates(plan.camera_path_uv_m)}
            fill="none"
            stroke="#a9b3af"
            strokeWidth="2"
            strokeDasharray="5 6"
          />
          {report.route.transitions.map((t, i) => (
            <polyline
              key={`transition-${i}`}
              points={coordinates(t.path_floor_uv_m)}
              fill="none"
              stroke="#a76a20"
              strokeWidth="3"
              strokeDasharray="10 6"
            >
              <title>
                {t.from_room} to {t.to_room}: doorway or connector unresolved
              </title>
            </polyline>
          ))}
          {rooms.map((r) => {
            const color = colors[report.rooms.indexOf(r) % colors.length];
            return (
              <g key={r.id}>
                {r.structure?.suggested_spans.map((s, i) => (
                  <polyline
                    key={`span-${i}`}
                    points={coordinates(s.uv)}
                    fill="none"
                    stroke={color}
                    strokeWidth="5"
                  >
                    <title>
                      {r.id} / {s.plane_id}: {s.status}
                    </title>
                  </polyline>
                ))}
                {r.rough_room && (
                  <polygon
                    points={coordinates(r.rough_room.polygon_floor_uv_m)}
                    fill={color}
                    fillOpacity="0.06"
                    stroke={color}
                    strokeWidth="3"
                    strokeDasharray="12 8"
                  />
                )}
                {report.route.stays
                  .filter((s) => s.room_id === r.id)
                  .map((s, i) => (
                    <polyline
                      key={`stay-${i}`}
                      points={coordinates(s.path_floor_uv_m)}
                      fill="none"
                      stroke={color}
                      strokeWidth="2"
                    >
                      <title>
                        {r.id}: scanning{" "}
                        {s.scan_seconds.map((t) => t.toFixed(1)).join("–")} s
                      </title>
                    </polyline>
                  ))}
              </g>
            );
          })}
          <path d={`M40 575 H${40 + scale}`} stroke="#3e5650" strokeWidth="3" />
          <text x="40" y="596" fontSize="14">
            1 source-estimated metre
          </text>
        </svg>
      </div>
      {rooms.map((r) => (
        <div key={r.id} className="viewer-note">
          <strong
            style={{ color: colors[report.rooms.indexOf(r) % colors.length] }}
          >
            {r.id}
          </strong>
          {" · "}
          {report.route.stays
            .filter((s) => s.room_id === r.id)
            .map(
              (s) => s.scan_seconds.map((t) => t.toFixed(1)).join("–") + " s",
            )
            .join(", ")}
          {" · "}
          {r.source_voxel_count.toLocaleString()} source voxels ·{" "}
          {r.structure?.suggested_spans.length || 0} supported wall spans across{" "}
          {
            new Set(r.structure?.suggested_spans.map((s) => s.plane_id) || [])
              .size
          }{" "}
          surfaces
          {r.rough_room ? (
            <p>
              Approximate size{" "}
              {r.rough_room.dimensions_estimated_m
                .map((n) => n.toFixed(2))
                .join(" × ")}{" "}
              m. Ceiling{" "}
              {r.rough_room.ceiling_estimate?.height_estimated_m?.toFixed(2) ??
                "unavailable"}{" "}
              m.
            </p>
          ) : (
            <p>Outline unavailable: {explainFailure(r.failure)}</p>
          )}
        </div>
      ))}
      <p className="viewer-note">
        Rooms share the source coordinate frame. Adjacency, doorway widths,
        physical dimensions and drift remain unverified.{" "}
        <a href={`${base}/plan.json`} download>
          Download route and room evidence
        </a>
      </p>
    </section>
  );
}

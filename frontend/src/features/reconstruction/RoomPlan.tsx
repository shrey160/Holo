import { useState } from "react";
import type { Plan } from "./types";
import { CompleteRoomPlan } from "./CompleteRoomPlan";
import { RoomwisePlan } from "./RoomwisePlan";

export function RoomPlan({ plan, base }: { plan: Plan; base: string }) {
  const [candidates, setCandidates] = useState(false),
    [layer, setLayer] = useState(
      plan.roomwise
        ? "rooms"
        : plan.rough_room
          ? "rough"
          : plan.structure
            ? "structure"
            : "observations",
    ),
    [fit, setFit] = useState(Boolean(plan.structure)),
    [path, setPath] = useState(true),
    [occupancy, setOccupancy] = useState(true),
    [zoom, setZoom] = useState(1);
  const selector = (
    <label>
      Plan layer{" "}
      <select
        aria-label="Plan layer"
        value={layer}
        onChange={(e) => setLayer(e.target.value)}
      >
        {plan.rough_room && <option value="rough">Complete rough plan</option>}
        {plan.roomwise && (
          <option value="rooms">Room-wise capture evidence</option>
        )}
        {plan.structure && (
          <option value="structure">Structure-focused evidence</option>
        )}
        <option value="observations">All observations</option>
      </select>
    </label>
  );
  if (layer === "rooms" && plan.roomwise)
    return (
      <RoomwisePlan
        plan={plan}
        report={plan.roomwise}
        base={base}
        selector={selector}
      />
    );
  if (layer === "rough" && plan.rough_room)
    return (
      <CompleteRoomPlan
        room={plan.rough_room}
        base={base}
        selector={selector}
      />
    );
  const { raster } = plan,
    scale = raster.scale_px_per_estimated_m;
  const point = (uv: number[]) =>
    uv.map((n, i) => {
      const pixel =
        (n - raster.bounds_uv_m[0][i]) * scale + raster.padding_px[i];
      return i === 1 ? raster.height - pixel : pixel;
    });
  const coordinates = (points: number[][]) =>
    points.map((p) => point(p).join(",")).join(" ");
  const focused = layer === "structure" && plan.structure;
  const spans = focused ? focused.suggested_spans : plan.candidate_spans;
  const extentPoints = focused
    ? [
        ...focused.cells.map((c) =>
          c.cell.map((n) => (n + 0.5) * focused.policy.cell_m),
        ),
        ...plan.reviewed_spans.flatMap((s) => s.endpoints_floor_uv_m),
        ...plan.floor_cells.map((c) => c.cell.map((n) => n * plan.cell_m)),
      ].map(point)
    : [];
  const bounds = extentPoints.length
    ? [0, 1].map((i) => [
        Math.min(...extentPoints.map((p) => p[i])) - 45,
        Math.max(...extentPoints.map((p) => p[i])) + 45,
      ])
    : [
        [0, raster.width],
        [0, raster.height],
      ];
  const viewBox =
    fit && focused
      ? `${bounds[0][0]} ${bounds[1][0]} ${bounds[0][1] - bounds[0][0]} ${bounds[1][1] - bounds[1][0] + 80}`
      : `0 0 ${raster.width} ${raster.height}`;
  return (
    <section className="reconstruction-view panel">
      <div className="reconstruction-view-heading">
        <div>
          <p className="eyebrow">01 / PLAN VIEW</p>
          <h2>Rough room plan</h2>
        </div>
        <a href={`${base}/plan.png`} download>
          Download occupancy PNG
        </a>
      </div>
      <p className="muted">
        {focused
          ? "Structure-focused view reduces low furniture and isolated noise using vertical-plane support across multiple heights. Tall furniture and curtains can remain."
          : "Top-down observed geometry includes walls and furniture."}{" "}
        Empty areas are unknown. Blue shows reviewed wall patches; green shows
        local floor evidence.
      </p>
      <div className="viewer-controls">
        {plan.structure && (
          <>
            {selector}
            <label>
              <input
                type="checkbox"
                checked={fit}
                onChange={(e) => setFit(e.target.checked)}
              />{" "}
              Fit structure
            </label>
          </>
        )}
        <label>
          <input
            type="checkbox"
            checked={occupancy}
            onChange={(e) => setOccupancy(e.target.checked)}
          />{" "}
          Observed geometry
        </label>
        <label>
          <input
            type="checkbox"
            checked={path}
            onChange={(e) => setPath(e.target.checked)}
          />{" "}
          Capture path
        </label>
        <label>
          <input
            type="checkbox"
            checked={candidates}
            onChange={(e) => setCandidates(e.target.checked)}
          />{" "}
          {focused
            ? "Unreviewed line suggestions"
            : "Unreviewed plane candidates"}
        </label>
        <label>
          Plan zoom{" "}
          <input
            type="range"
            min="1"
            max="3"
            step="0.25"
            value={zoom}
            onChange={(e) => setZoom(Number(e.target.value))}
          />
        </label>
      </div>
      {candidates && (
        <p className="viewer-note">
          Amber dashed candidates may follow furniture or curtains. They are
          geometric suggestions, not confirmed room walls.
        </p>
      )}
      <div className="room-plan-scroll">
        <svg
          className="room-plan"
          style={{
            width: `${zoom * 100}%`,
            maxWidth: "none",
            height: fit && focused ? `${600 * zoom}px` : undefined,
          }}
          viewBox={viewBox}
          role="img"
          aria-label="Rough room plan with observed geometry and explicit gaps"
        >
          <rect width={raster.width} height={raster.height} fill="#fafafa" />
          {occupancy && !focused && (
            <image
              href={`${base}/plan.png`}
              width={raster.width}
              height={raster.height}
              transform={`translate(0 ${raster.height}) scale(1 -1)`}
            />
          )}
          {occupancy &&
            focused &&
            focused.cells.map((cell, i) => {
              const [x, y] = point(
                cell.cell.map((n) => n * focused.policy.cell_m),
              );
              return (
                <rect
                  key={`structure-${i}`}
                  x={x}
                  y={y - scale * focused.policy.cell_m}
                  width={scale * focused.policy.cell_m}
                  height={scale * focused.policy.cell_m}
                  fill="#8c9993"
                  fillOpacity="0.65"
                >
                  <title>
                    Height-persistent occupancy,{" "}
                    {cell.height_range_m.map((n) => n.toFixed(2)).join("–")}{" "}
                    estimated m; wall identity unverified
                  </title>
                </rect>
              );
            })}
          {plan.floor_cells.map(({ cell }, i) => {
            const [x, y] = point(cell.map((n) => n * plan.cell_m));
            return (
              <rect
                key={i}
                x={x}
                y={y - scale * plan.cell_m}
                width={scale * plan.cell_m}
                height={scale * plan.cell_m}
                fill="#67b39966"
                stroke="#237867"
                strokeWidth="1"
              />
            );
          })}
          {path && (
            <polyline
              points={coordinates(plan.camera_path_uv_m)}
              fill="none"
              stroke="#7762a7"
              strokeWidth="3"
              strokeDasharray="7 7"
            >
              <title>
                Source camera path; doorway positions are not detected
              </title>
            </polyline>
          )}
          {candidates &&
            spans.map((s, i) => (
              <g key={i}>
                <polyline
                  points={coordinates(s.uv)}
                  fill="none"
                  stroke="#bb8333"
                  strokeWidth="4"
                  strokeDasharray="12 8"
                >
                  <title>
                    {s.plane_id}: {s.status}
                  </title>
                </polyline>
                <text
                  x={point(s.uv[0])[0]}
                  y={point(s.uv[0])[1] - 8}
                  fill="#886024"
                  fontSize="17"
                >
                  {s.plane_id}?
                </text>
              </g>
            ))}
          {plan.reviewed_spans.map((s, i) => (
            <g key={i}>
              <polyline
                points={coordinates(s.endpoints_floor_uv_m)}
                fill="none"
                stroke="#2173ad"
                strokeWidth="7"
              >
                <title>
                  {s.plane_id}: {s.projected_span_estimated_m.toFixed(2)}{" "}
                  estimated m; junction and corners unverified
                </title>
              </polyline>
              <text
                x={point(s.endpoints_floor_uv_m[0])[0]}
                y={point(s.endpoints_floor_uv_m[0])[1] - 12 - i * 24}
                fill="#18547f"
                fontSize="18"
              >
                {s.plane_id} · {s.projected_span_estimated_m.toFixed(2)} m patch
              </text>
            </g>
          ))}
          <g
            transform={`translate(${fit && focused ? bounds[0][0] + 15 : 55} ${fit && focused ? bounds[1][1] + 25 : raster.height - 45})`}
          >
            <path
              d={`M0 -8 V0 H${scale} V-8`}
              fill="none"
              stroke="#3e5650"
              strokeWidth="3"
            />
            <text x="0" y="25" fill="#3e5650" fontSize="17">
              1 source-estimated metre
            </text>
          </g>
        </svg>
      </div>
      {focused && (
        <p className="viewer-note">
          {focused.cells.length.toLocaleString()} height-persistent cells ·{" "}
          {focused.retained_voxel_points.toLocaleString()} source voxels. Line
          suggestions are robust fits; gaps stay open and identities require
          image review.{" "}
          <a href={`${base}/plan.json`} download>
            Download plan evidence
          </a>
        </p>
      )}
      <p className="viewer-note">
        Open spans stay open. No closed footprint, room area, doorway locations
        or survey dimensions are established.
      </p>
    </section>
  );
}

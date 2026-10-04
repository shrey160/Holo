import { useState, type ReactNode } from "react";
import type { Plan } from "./types";

export function CompleteRoomPlan({
  room,
  base,
  selector,
}: {
  room: NonNullable<Plan["rough_room"]>;
  base: string;
  selector: ReactNode;
}) {
  const [zoom, setZoom] = useState(1);
  return (
    <section className="reconstruction-view panel">
      <div className="reconstruction-view-heading">
        <div>
          <p className="eyebrow">01 / PLAN VIEW</p>
          <h2>Complete rough floor plan</h2>
        </div>
        <a href={`${base}/rough-room.svg`} download>
          Download floor plan SVG
        </a>
      </div>
      <p className="muted">
        {room.status === "AUTOMATIC_SPARSE_ENVELOPE"
          ? "An approximate rectangular outline of sparse point coverage. Floor level and orientation are inferred from point distribution; furniture, missing views and corridors can bias the outline. Multiple rooms are not segmented."
          : "An approximate rectangular room completed from the available wall candidates."}{" "}
        Dashed walls and corners are inferred. The entrance follows the capture
        path; door width and swing are illustrative.
      </p>
      <div className="viewer-controls">
        {selector}
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
      <div className="room-plan-scroll">
        <img
          src={`${base}/rough-room.svg`}
          style={{ width: `${zoom * 100}%`, maxWidth: "none" }}
          alt={`Complete approximate room floor plan, ${room.dimensions_estimated_m.map((n) => n.toFixed(1)).join(" by ")} source-estimated metres, inferred entrance and four walls.`}
        />
      </div>
      <p className="viewer-note">
        Size ≈{" "}
        {room.dimensions_estimated_m.map((n) => n.toFixed(1)).join(" × ")} m ·
        area ≈ {room.area_estimated_m2.toFixed(0)} m².
        {room.ceiling_reference && (
          <>
            {" "}
            Ceiling ≈ {room.ceiling_reference.value_m} m is your supplied
            measurement.
          </>
        )}{" "}
        Allow errors in the outline, entrance and dimensions. The source
        reconstruction is unchanged.
      </p>
      {room.ceiling_estimate?.height_estimated_m != null && (
        <p className="viewer-note">
          Geometry ceiling estimate:{" "}
          <strong>
            ≈ {room.ceiling_estimate.height_estimated_m.toFixed(2)} m
          </strong>
          . Low confidence: upper point coverage is sparse and a ceiling plane
          is not verified. Your measured height was not used to calculate this
          estimate.
        </p>
      )}
      {!!room.objects?.length && (
        <p className="viewer-note">
          Approximate objects:{" "}
          {room.objects
            .filter((o) => o.footprint_floor_uv_m)
            .map((o) => o.label)
            .join(", ")}
          . Placements use visually marked source images and visible RGB
          geometry; partial footprints can have errors.
        </p>
      )}
      <a href={`${base}/plan.json`} download>
        Download plan assumptions and evidence
      </a>
    </section>
  );
}

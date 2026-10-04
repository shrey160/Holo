"""Offline partial projection and review images; no closed room or invented measurements."""

import html
import shutil

import cv2
import numpy as np

from cozmo_ingestion.errors import require

from .geometry import floor_uv
from .reviews import ROLES

COLORS = {
    "FLOOR": (60, 165, 105),
    "WALL": (35, 120, 220),
    "FURNITURE": (200, 80, 65),
    "MIXED": (180, 140, 30),
    "UNKNOWN": (130, 130, 130),
}


def plot(stage, report, policy):
    cells = report["local_floor"]["cells"]
    frame = report["floor_frame"]
    points = []
    for cell in cells:
        uv = np.array(cell["cell"]) * policy.cell_m
        points.extend([uv, uv + policy.cell_m])
    for wall in report["walls"]:
        for segment in wall["segments"]:
            points.extend(segment["endpoints_floor_uv_m"])
    bounds = (
        np.array([[-1.0, -1.0], [1.0, 1.0]])
        if not points
        else np.array([np.min(points, axis=0), np.max(points, axis=0)])
    )
    span = np.maximum(bounds[1] - bounds[0], 0.2)
    scale = min(850 / span[0], 500 / span[1])

    def pixels(uv):
        uv = (np.asarray(uv) - bounds[0]) * scale
        return np.c_[uv[..., 0] + 65, 640 - uv[..., 1]].reshape(-1, 2)

    canvas = np.full((760, 1000, 3), 248, np.uint8)
    svg = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 760" role="img" aria-label="Partial wall projections and local floor coverage">',
        '<rect width="1000" height="760" fill="#fafaf6"/>',
        '<text x="40" y="42" font-family="sans-serif" font-size="24">Holo · partial structural evidence</text>',
        '<text x="40" y="74" font-family="sans-serif" font-size="16">Unverified source metres · no closed polygon · unknown spans retained</text>',
        '<g id="floor-cells">',
    ]
    cv2.putText(
        canvas,
        "Holo: partial structural evidence",
        (40, 42),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (35, 60, 50),
        2,
    )
    cv2.putText(
        canvas,
        "Unverified source metres | no closed polygon | unknown spans retained",
        (40, 74),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        (60, 60, 60),
        1,
    )
    for cell in cells:
        corners = np.array(cell["cell"]) * policy.cell_m + np.array(
            [[0, 0], [policy.cell_m, 0], [policy.cell_m, policy.cell_m], [0, policy.cell_m]]
        )
        xy = pixels(corners)
        cv2.fillConvexPoly(canvas, np.rint(xy).astype(np.int32), (215, 235, 220))
        cv2.polylines(canvas, [np.rint(xy).astype(np.int32)], True, (130, 175, 145), 1)
        vertices = " ".join(f"{x:.3f},{y:.3f}" for x, y in xy)
        svg.append(
            f'<polygon points="{vertices}" fill="#dceadd" stroke="#82b093"><title>Local floor cell {cell["cell"]}; reviewed ranks {cell["view_ranks"]}</title></polygon>'
        )
    svg.append('</g><g id="wall-spans">')
    for wall in report["walls"]:
        for index, segment in enumerate(wall["segments"]):
            xy = pixels(segment["endpoints_floor_uv_m"])
            a, b = np.rint(xy).astype(int)
            cv2.line(canvas, tuple(a), tuple(b), (175, 100, 35), 4)
            cv2.putText(
                canvas,
                f"{wall['plane_id']} S{index + 1}",
                tuple(a + [5, -8]),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (110, 65, 25),
                1,
            )
            svg.append(
                f'<a href="#plane-{wall["plane_id"]}"><line x1="{xy[0, 0]:.3f}" y1="{xy[0, 1]:.3f}" x2="{xy[1, 0]:.3f}" y2="{xy[1, 1]:.3f}" stroke="#2475b9" stroke-width="5"><title>{wall["plane_id"]} span {index + 1}: {segment["projected_span_estimated_m"]:.3f} estimated m; projected wall patch, junction unconfirmed; ranks {segment["view_ranks"]}</title></line></a>'
            )
    svg.append("</g>")
    if frame:
        uv = floor_uv(np.array([frame["origin_world_m"]]), frame)
        xy = pixels(uv)[0]
        svg.append(
            f'<circle cx="{xy[0]:.3f}" cy="{xy[1]:.3f}" r="4" fill="#555"><title>Local floor frame origin; not a surveyed datum</title></circle>'
        )
    else:
        svg.append(
            '<text x="80" y="220" font-family="sans-serif" font-size="22">No supported floor reference; boundary projection withheld.</text>'
        )
        cv2.putText(
            canvas,
            "No supported floor reference: projection withheld",
            (50, 200),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (70, 70, 70),
            1,
        )
    svg.append(
        f'<text x="40" y="700" font-family="sans-serif" font-size="16">Green: local floor evidence cells · blue: wall projections</text><text x="40" y="728" font-family="sans-serif" font-size="14">Floor UV extent: u {bounds[0, 0]:.2f} to {bounds[1, 0]:.2f}; v {bounds[0, 1]:.2f} to {bounds[1, 1]:.2f}. Source estimated m.</text></svg>'
    )
    cv2.putText(
        canvas,
        "Green: local floor cells | blue: projected wall patches",
        (40, 700),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        (45, 70, 55),
        1,
    )
    require(
        cv2.imwrite(str(stage / "preview.png"), canvas), "BOUNDARY_PREVIEW_FAILED", "Partial plan"
    )
    content = "".join(svg)
    (stage / "plan.svg").write_text(content, encoding="utf-8")
    return content


def write_review(stage, request, views, review, report, arrays, policy):
    for folder in ("images", "source_overlays", "review_overlays"):
        (stage / folder).mkdir()
    dense = request.surfaces.upstream.output
    by_rank = {v["rank"]: v for v in views}
    for rank in sorted({r["rank"] for r in review["regions"]}):
        view = by_rank[rank]
        name = f"{rank:06d}.jpg"
        shutil.copyfile(dense / f"workspace/images/{view['image']}", stage / "images" / name)
        shutil.copyfile(
            request.surfaces.output / f"overlays/{view['image']}", stage / "source_overlays" / name
        )
        rgb = cv2.imread(str(stage / "images" / name))
        for row in review["regions"]:
            if row["rank"] != rank:
                continue
            polygon = np.rint(np.array(row["polygon_dense"]) - 0.5).astype(np.int32)
            cv2.polylines(rgb, [polygon], True, COLORS[row["role"]][::-1], 2)
        mask = arrays["rank"] == rank
        for x, y, role in zip(
            arrays["x"][mask], arrays["y"][mask], arrays["role"][mask], strict=True
        ):
            cv2.circle(rgb, (int(x), int(y)), 1, COLORS[ROLES[int(role)]][::-1], -1)
        require(
            cv2.imwrite(str(stage / "review_overlays" / name), rgb), "BOUNDARY_PREVIEW_FAILED", name
        )
    svg = plot(stage, report, policy)
    blocks = []
    for plane_id in sorted({r["plane_id"] for r in review["regions"]}):
        rows = [r for r in review["regions"] if r["plane_id"] == plane_id]
        text = "".join(
            f"<li>{html.escape(r['id'])} · frame {r['rank']} · <b>{r['role']}</b>: {html.escape(r['reason'])}</li>"
            for r in rows
        )
        images = "".join(
            f'<figure><img loading="lazy" src="review_overlays/{rank:06d}.jpg" alt="Region polygons and classified observations at frame {rank}"><figcaption>Frame {rank}. <a href="images/{rank:06d}.jpg">Original RGB</a> · <a href="source_overlays/{rank:06d}.jpg">Original surface samples</a></figcaption></figure>'
            for rank in sorted({r["rank"] for r in rows})
        )
        blocks.append(
            f'<section id="plane-{plane_id}"><h2>{plane_id}: region evidence</h2><ul>{text}</ul><details><summary>Show source-linked region images</summary>{images}</details></section>'
        )
    document = (
        '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Holo · partial room evidence</title>'
        "<style>body{font:16px system-ui;color:#243e35;background:#f6f7f2;margin:0}main{max-width:1100px;margin:auto;padding:24px}section,.panel{background:white;border:1px solid #d6e1d8;padding:20px;border-radius:12px;margin:20px 0}svg,img{width:100%;height:auto}figure{margin:16px 0}a{color:#146c63}summary{cursor:pointer}button,label{margin:8px}pre{white-space:pre-wrap}</style><main>"
        "<h1>Holo · partial room evidence</h1>"
        f'<div class="panel"><p><b>{report["status"]}</b> · {report["supported_segments"]} supported projected spans.</p>'
        "<p>Image regions reviewed by the assistant; architectural identities remain hypotheses. Physical dimensions are unverified. No closed room polygon or room area is produced.</p>"
        f"<p>Reference calibration: {html.escape(report['reference_calibration'])}. Camera poses and scale are unchanged.</p>"
        '<p><a href="report.json">Detailed evidence</a> · <a href="review.json">Region review JSON</a> · <a href="manifest.json">Provenance</a> · <a href="plan.svg">Export SVG</a></p></div>'
        '<div class="panel"><h2>Supported partial projection</h2><p>Hover a span for its estimated extent and source frames; click it to review its image regions. White space is unresolved coverage. Projected wall spans do not certify floor-wall junctions or room corners.</p>'
        '<label><input type="checkbox" id="floorToggle" checked>Local floor cells</label><label><input type="checkbox" id="wallToggle" checked>Wall projections</label>'
        + svg
        + "</div><h2>Region decisions and excluded evidence</h2><p>Green: floor. Blue: wall. Red: furniture/object. Amber: mixed. Gray: unknown. Rejections override architectural marks within overlapping regions. Unmarked samples supply no architectural identity.</p>"
        + "".join(blocks)
        + '<script>document.getElementById("floorToggle").onchange=e=>document.getElementById("floor-cells").style.display=e.target.checked?"":"none";document.getElementById("wallToggle").onchange=e=>document.getElementById("wall-spans").style.display=e.target.checked?"":"none";</script></main></html>'
    )
    (stage / "index.html").write_text(document, encoding="utf-8")

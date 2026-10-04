"""Local image-linked review, with no inferred room polygon or filled surfaces."""

import html
import json

import cv2
import numpy as np

from cozmo_ingestion.errors import require

from .analysis import PALETTE


def write_review(stage, dense, report):
    with np.load(dense / "cloud.npz") as cloud:
        xyz = cloud["xyz_m"]
    with np.load(stage / "cloud_labels.npz") as cloud:
        labels = cloud["plane_index"]
    cameras = json.loads((dense / "cameras.json").read_text())
    positions = np.array([c["center_m"] for c in sorted(cameras, key=lambda c: c["rank"])])
    canvas = np.full(
        (max(960, 815 + ((len(report["planes"]) + 2) // 3) * 35), 1500, 3), 248, dtype=np.uint8
    )
    cv2.putText(
        canvas,
        "Holo: candidate planes in source coordinates | NOT a floorplan",
        (25, 32),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (45, 45, 45),
        2,
    )
    cv2.putText(
        canvas,
        "Display clips outer 1% per axis; all observations remain in the source cloud.",
        (25, 58),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        (65, 65, 65),
        1,
    )
    step = max(1, len(xyz) // 40000)
    sampled, selected = xyz[::step], labels[::step]
    for panel, (a, b) in enumerate(((0, 2), (0, 1), (2, 1))):
        offset = panel * 500
        bounds = (
            np.percentile(xyz[:, [a, b]], [1, 99], axis=0)
            if len(xyz)
            else np.array([[0, 0], [1, 1]])
        )
        bounds[0] = np.minimum(bounds[0], positions[:, [a, b]].min(axis=0))
        bounds[1] = np.maximum(bounds[1], positions[:, [a, b]].max(axis=0))
        span = np.maximum(bounds[1] - bounds[0], 0.01)
        scale = min(430 / span[0], 620 / span[1])

        def pixels(points, a=a, b=b, bounds=bounds, scale=scale, offset=offset):
            uv = (points[:, [a, b]] - bounds[0]) * scale
            return np.c_[uv[:, 0] + offset + 35, 735 - uv[:, 1]].astype(int)

        cv2.rectangle(canvas, (offset + 30, 90), (offset + 470, 740), (160, 160, 160), 1)
        inside = np.all(
            (sampled[:, [a, b]] >= bounds[0]) & (sampled[:, [a, b]] <= bounds[1]), axis=1
        )
        for (x, y), label in zip(pixels(sampled[inside]), selected[inside], strict=True):
            color = (
                (190, 190, 190)
                if label < 0
                else tuple(int(v) for v in PALETTE[label % len(PALETTE), ::-1])
            )
            cv2.circle(canvas, (int(x), int(y)), 1, color, -1)
        cv2.polylines(canvas, [pixels(positions)], False, (30, 80, 30), 1)
        cv2.putText(
            canvas,
            f"{'XYZ'[a]} / {'XYZ'[b]} (estimated m)",
            (offset + 35, 80),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (30, 30, 30),
            1,
        )
        cv2.putText(
            canvas,
            f"ranges {bounds[0, 0]:.2f}..{bounds[1, 0]:.2f} / {bounds[0, 1]:.2f}..{bounds[1, 1]:.2f}",
            (offset + 35, 765),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (30, 30, 30),
            1,
        )
    for i, plane in enumerate(report["planes"]):
        x, y = (i % 3) * 500 + 25, 800 + (i // 3) * 35
        color = tuple(int(v) for v in plane["color_rgb"][::-1])
        cv2.rectangle(canvas, (x, y - 12), (x + 14, y + 2), color, -1)
        cv2.putText(
            canvas,
            f"{plane['id']} {plane['role_hypothesis']}",
            (x + 22, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.43,
            (30, 30, 30),
            1,
        )
    require(cv2.imwrite(str(stage / "preview.png"), canvas), "SURFACE_PREVIEW_FAILED", "Cloud")
    blocks = []
    (stage / "candidate_overlays").mkdir()
    for plane in report["planes"]:
        rgb = ",".join(map(str, plane["color_rgb"]))
        chosen = []
        for view in plane["views"]:
            if all(
                abs(float(view["relative_seconds"]) - float(v["relative_seconds"])) >= 1
                for v in chosen
            ):
                chosen.append(view)
            if len(chosen) == 3:
                break
        for view in chosen:
            name = view["image"]
            source = cv2.imread(str(dense / f"workspace/images/{name}"))
            require(source is not None, "SURFACE_RGB_INVALID", name)
            focused = (source * 0.4).astype(np.uint8)
            with np.load(stage / f"observations/{name}.npz") as samples:
                mask = samples["plane_index"] == int(plane["id"][1:]) - 1
                xs, ys = samples["x"][mask], samples["y"][mask]
            for x, y in zip(xs, ys, strict=True):
                cv2.circle(
                    focused,
                    (int(x), int(y)),
                    2,
                    tuple(int(c) for c in plane["color_rgb"][::-1]),
                    -1,
                )
            cv2.putText(
                focused,
                f"{plane['id']} | rank {view['rank']} | candidate only",
                (12, 28),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (255, 255, 255),
                1,
            )
            require(
                cv2.imwrite(
                    str(stage / f"candidate_overlays/{plane['id']}-{name}"),
                    np.concatenate((source, focused), axis=1),
                ),
                "SURFACE_OVERLAY_FAILED",
                name,
            )
        images = "".join(
            f'<figure><a href="candidate_overlays/{plane["id"]}-{html.escape(v["image"])}"><img loading="lazy" src="candidate_overlays/{plane["id"]}-{html.escape(v["image"])}"></a>'
            f"<figcaption>rank {v['rank']}, {html.escape(v['relative_seconds'])} s; "
            f"{v['samples']} sampled observations</figcaption></figure>"
            for v in chosen
        )
        blocks.append(
            f'<section><h2 style="border-left:12px solid rgb({rgb});padding-left:12px">{plane["id"]}: {plane["role_hypothesis"]}</h2>'
            f"<p>{plane['evidence_status']}; {plane['qualified_views']} qualified views; baseline {plane['camera_baseline_m']:.2f} estimated m.</p>"
            f"<p>Flags: {html.escape(', '.join(plane['flags']) or 'none; semantics still require review')}</p>"
            "<p>Check whether colored observations belong to the floor/wall or furniture, curtains or an edge. "
            "Coplanarity does not establish architectural identity. Black/uncolored regions provide no plane evidence.</p>"
            f"{images}</section>"
        )
    (stage / "index.html").write_text(
        '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        "<title>Holo surface evidence</title><style>body{font:16px system-ui;margin:32px auto;max-width:1100px;padding:0 20px;"
        "color:#233b36;background:#fafbf8}img{width:100%;height:auto}section{border-top:1px solid #bac9c1;margin-top:32px}"
        "figure{margin:24px 0}figcaption{font-size:14px}a{color:#087567}</style>"
        "<h1>Single-room surface hypotheses</h1><p>REVIEW REQUIRED. Source estimated metres; physical accuracy unverified. "
        "Zero confirmed architectural surfaces. This is not a floorplan.</p>"
        "<p>Left: source-derived RGB. Right: accepted depth samples near candidate planes; colors match the legend. "
        "Missing observations are retained, with no forced walls or closed polygon.</p>"
        '<p><a href="report.json">Complete report and occupied patches</a> · <a href="manifest.json">Provenance</a></p>'
        '<img src="preview.png" alt="Three source-axis projections of plane candidates and camera path">'
        + "".join(blocks)
        + "</html>",
        encoding="utf-8",
        newline="\n",
    )

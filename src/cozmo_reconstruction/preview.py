"""Offline SVG orthogonal views; display clipping never edits exported geometry."""

from html import escape

import numpy as np


def write_preview(path, mapping, points, report, layer="sparse"):
    centers = np.array([v["pose"]["world_from_camera"] for v in mapping])[:, :3, 3]
    xyz = np.array([p["xyz_m"] for p in points]).reshape(-1, 3)
    colors = [p["rgb"] for p in points]
    content = [
        "<svg xmlns='http://www.w3.org/2000/svg' width='1500' height='600' viewBox='0 0 1500 600'>",
        "<rect width='1500' height='600' fill='#f5f7f2'/>",
        "<style>text{font:14px sans-serif;fill:#213c35}</style>",
        f"<text x='20' y='28'>Holo · fixed-camera {escape(layer)} reconstruction · REVIEW REQUIRED</text>",
        f"<text x='20' y='52'>{len(mapping)} cameras · {len(points)} displayed {escape(layer)} points · "
        f"{escape(report['geometry_signal'])} image/track signal · dimensions unverified</text>",
    ]
    for panel, (axes, title) in enumerate(
        [((0, 2), "Source X/Z"), ((0, 1), "Source X/Y"), ((2, 1), "Source Z/Y")]
    ):
        data = np.concatenate([xyz[:, axes], centers[:, axes]], axis=0)
        low, high = np.percentile(data, [1, 99], axis=0)
        span = max(float(np.max(high - low)), 0.1)

        def screen(row, axes=axes, low=low, high=high, span=span, panel=panel):
            pair = (row[list(axes)] - (low + high) / 2) * (420 / span)
            return panel * 500 + 250 + pair[0], 325 - pair[1]

        content.append(
            f"<text x='{panel * 500 + 20}' y='85'>{title} · central 98% display range</text>"
        )
        content.append(
            f"<rect x='{panel * 500 + 10}' y='100' width='480' height='450' fill='white' stroke='#c7d3cc'/>"
        )
        for point, rgb in zip(xyz, colors, strict=True):
            x, y = screen(point)
            if panel * 500 + 10 < x < panel * 500 + 490 and 100 < y < 550:
                content.append(
                    f"<circle cx='{x:.2f}' cy='{y:.2f}' r='1.2' fill='rgb({rgb[0]},{rgb[1]},{rgb[2]})'/>"
                )
        coordinates = [screen(c) for c in centers]
        line = " ".join(f"{x:.2f},{y:.2f}" for x, y in coordinates)
        content.append(f"<polyline points='{line}' stroke='#0d8376' fill='none' stroke-width='1'/>")
        for i, (x, y) in enumerate(coordinates):
            content.append(
                f"<circle cx='{x:.2f}' cy='{y:.2f}' r='2.5' fill='#0d8376'><title>rank {mapping[i]['rank']}</title></circle>"
            )
    content.append(
        "<text x='20' y='583'>Camera path: green. Full untrimmed geometry: cloud.ply. No wall/floor fitting or scale correction applied.</text></svg>"
    )
    path.write_text("\n".join(content), encoding="utf-8", newline="\n")

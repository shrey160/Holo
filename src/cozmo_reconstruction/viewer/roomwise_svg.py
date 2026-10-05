"""Common-coordinate presentation of provisional stays, not invented doorways."""

from html import escape

import numpy as np


def roomwise_svg(report, path):
    points = list(path)
    for room in report["rooms"]:
        points.extend(
            p for span in room.get("structure", {}).get("suggested_spans", []) for p in span["uv"]
        )
        if room.get("rough_room"):
            points.extend(room["rough_room"]["polygon_floor_uv_m"])
    bounds = np.asarray([np.min(points, axis=0) - 0.5, np.max(points, axis=0) + 0.5])
    scale = min(860 / (bounds[1, 0] - bounds[0, 0]), 580 / (bounds[1, 1] - bounds[0, 1]))

    def coords(values):
        xy = (np.asarray(values) - bounds[0]) * scale + [40, 100]
        return " ".join(f"{x:.2f},{780 - y:.2f}" for x, y in xy)

    body = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 940 800">',
        '<rect width="940" height="800" fill="#fcfcf8"/>',
        '<g font-family="Arial, sans-serif">',
        '<text x="30" y="35" font-size="23">Room-wise capture evidence</text>',
        '<text x="30" y="65" font-size="15">Room identities provisional; connectors and doorway crossings unresolved.</text>',
        f'<polyline points="{coords(path)}" fill="none" stroke="#89929c" stroke-width="2" stroke-dasharray="6 5"/>',
    ]
    for i, room in enumerate(report["rooms"]):
        color = ["#146f60", "#7659a5", "#a76a20"][i % 3]
        for span in room.get("structure", {}).get("suggested_spans", []):
            body.append(
                f'<polyline points="{coords(span["uv"])}" fill="none" stroke="{color}" stroke-width="4"><title>{escape(room["id"])}: unconfirmed wall or furniture</title></polyline>'
            )
        if room.get("rough_room"):
            body.append(
                f'<polyline points="{coords(room["rough_room"]["polygon_floor_uv_m"])}" fill="none" stroke="{color}" stroke-width="3" stroke-dasharray="12 8"/>'
            )
        label = (
            room["id"]
            + ": "
            + ("approximate outline" if room.get("rough_room") else "outline unavailable")
        )
        body.append(
            f'<text x="30" y="{725 + i * 22}" font-size="16" fill="{color}">{escape(label)}</text>'
        )
    body.append("</g></svg>")
    return "\n".join(body)

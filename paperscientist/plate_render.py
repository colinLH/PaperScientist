"""Assemble a conceptual framework from normalized parts. Run the bundled file to redraw offline."""

from __future__ import annotations

import json
import math
from pathlib import Path

import matplotlib as mpl
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.patches import ConnectionPatch, FancyArrowPatch, Rectangle
from PIL import Image


def geometry(spec, font_size):
    width, height = map(float, spec["size"])
    count = len(spec["panels"])
    cols = spec["columns"]
    rows = math.ceil(count / cols)
    gap_x, gap_y = 0.18, 0.19
    cell_w = (width - 0.10 - (cols - 1) * gap_x) / cols
    cell_h = (height - 0.10 - (rows - 1) * gap_y) / rows
    header = (font_size + 2) / 72 + 0.12
    if cell_w < 0.8 or cell_h - header < 0.50:
        raise ValueError(
            "Panel cells are too small at manuscript size; change columns or split the figure"
        )
    return [
        (
            (0.05 + i % cols * (cell_w + gap_x)) / width,
            1 - (0.05 + i // cols * (cell_h + gap_y) + cell_h) / height,
            cell_w / width,
            cell_h / height,
            header / height,
        )
        for i in range(count)
    ]


def render(spec, folder, minimum_font=7.0):
    """Fit each illustration in its own cell. Label coordinates refer to the actual image."""
    size = spec["size"]
    with mpl.rc_context(
        {
            "svg.fonttype": "none",
            "pdf.fonttype": 42,
            "font.family": "DejaVu Sans",
            "text.usetex": False,
            "text.parse_math": False,
        }
    ):
        fig = Figure(figsize=size, dpi=110, facecolor="white")
        renderer = FigureCanvasAgg(fig).get_renderer()
        cells = geometry(spec, minimum_font)
        bg = ("#EDF5F6", "#F1F3FA", "#FBF1E8", "#EEF5ED")
        ids = {}
        for i, (panel, bounds) in enumerate(zip(spec["panels"], cells)):
            x, y, w, h, head = bounds
            ids[panel["id"]] = bounds
            fig.add_artist(
                Rectangle(
                    (x, y),
                    w,
                    h,
                    transform=fig.transFigure,
                    facecolor="white",
                    edgecolor="#A4B4BC",
                    linewidth=0.55,
                    zorder=-2,
                )
            )
            fig.add_artist(
                Rectangle(
                    (x, y + h - head),
                    w,
                    head,
                    transform=fig.transFigure,
                    facecolor=bg[i % len(bg)],
                    edgecolor="none",
                    zorder=-1,
                )
            )
            title = fig.text(
                x + 0.045 / size[0],
                y + h - head / 2,
                f"({chr(97 + i)})  {panel['title']}",
                ha="left",
                va="center",
                fontsize=minimum_font + 0.6,
                weight="semibold",
                color="#192F3B",
            )
            if (
                title.get_window_extent(renderer).x1
                > fig.transFigure.transform((x + w, y))[0] - 2
            ):
                raise ValueError(
                    f"Shorten the title for panel {panel['id']} at this width"
                )
            art_h = h - head - 0.02 / size[1]
            zoom = panel.get("zoom")
            zoom_h = art_h * 0.32 if zoom else 0
            ax = fig.add_axes(
                [
                    x + 0.012 / size[0],
                    y + 0.01 / size[1] + zoom_h,
                    w - 0.024 / size[0],
                    art_h - zoom_h,
                ]
            )
            with Image.open(folder / "parts" / (panel["id"] + ".png")) as im:
                ax.imshow(
                    im,
                    extent=(0, im.width / im.height, 0, 1),
                    interpolation="antialiased",
                )
                ratio = im.width / im.height
                if zoom:
                    left, top, right, bottom = zoom
                    box = (
                        math.floor(left * im.width),
                        math.floor(top * im.height),
                        math.ceil(right * im.width),
                        math.ceil(bottom * im.height),
                    )
                    detail = fig.add_axes(
                        [
                            x + w * 0.10,
                            y + 0.025 / size[1],
                            w * 0.80,
                            zoom_h - 0.04 / size[1],
                        ]
                    )
                    detail.imshow(im.crop(box), interpolation="antialiased")
                    detail.set_xticks([])
                    detail.set_yticks([])
                    for spine in detail.spines.values():
                        spine.set(color="#597782", linewidth=0.65)
                    ax.add_patch(
                        Rectangle(
                            (left * ratio, 1 - bottom),
                            (right - left) * ratio,
                            bottom - top,
                            facecolor="none",
                            edgecolor="#597782",
                            linewidth=0.7,
                            linestyle="--",
                        )
                    )
                    fig.add_artist(
                        ConnectionPatch(
                            ((left + right) * ratio / 2, 1 - bottom),
                            (0.5, 1),
                            coordsA=ax.transData,
                            coordsB=detail.transAxes,
                            linewidth=0.55,
                            color="#597782",
                            linestyle=":",
                        )
                    )
            ax.set_axis_off()
            ax.apply_aspect()
            labels = []
            for item in panel.get("labels", []):
                label = ax.text(
                    item["x"] * ratio,
                    1 - item["y"],
                    item["text"],
                    fontsize=minimum_font,
                    ha="center",
                    va="center",
                    color="#162E39",
                    bbox={
                        "facecolor": "white",
                        "edgecolor": "none",
                        "pad": 1.2,
                        "alpha": 0.94,
                    },
                )
                box = label.get_window_extent(renderer).padded(1.2 * fig.dpi / 72)
                if (
                    not ax.bbox.contains(*box.min)
                    or not ax.bbox.contains(*box.max)
                    or any(box.overlaps(b) for b in labels)
                ):
                    raise ValueError(
                        f"Move overlapping or clipped labels in panel {panel['id']}"
                    )
                labels.append(box)
        for source, target in spec.get("links", []):
            x, y, w, h, _ = ids[source]
            u, v, w2, h2, _ = ids[target]
            if abs(y - v) < 1e-9:
                start, end = (
                    ((x + w, y + h / 2), (u, v + h2 / 2))
                    if u > x
                    else ((x, y + h / 2), (u + w2, v + h2 / 2))
                )
            else:
                start, end = (
                    ((x + w / 2, y), (u + w2 / 2, v + h2))
                    if v < y
                    else ((x + w / 2, y + h), (u + w2 / 2, v))
                )
            fig.add_artist(
                FancyArrowPatch(
                    start,
                    end,
                    transform=fig.transFigure,
                    arrowstyle="-|>",
                    mutation_scale=7,
                    linewidth=0.8,
                    color="#284452",
                    shrinkA=0.5,
                    shrinkB=0.5,
                )
            )
        for ext in ("pdf", "svg", "png"):
            fig.savefig(folder / ("figure." + ext), dpi=300, facecolor="white")


if __name__ == "__main__":
    root = Path(__file__).resolve().parent
    spec = json.loads((root / "spec.json").read_text(encoding="utf-8"))
    contract = json.loads((root / "figure_contract.json").read_text(encoding="utf-8"))
    render(spec, root, contract["minimum_font_pt"])

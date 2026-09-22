#!/usr/bin/env python3
"""plot-fig-timeline.py -- new optional figure: a compact timeline of the six
measurement campaigns with cell counts, so a reviewer can grasp scale at a
glance instead of reading tab:campaigns as a table.

Not data-driven from a per-run TSV: the six campaign definitions and cell
counts are the adjudicated totals already printed in tab:campaigns / the
methodology summary. This script only re-presents those numbers -- it must
never recompute a cell count.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

import jsa_style as style

# Source of record: tab:campaigns in main-jsa.tex / the methodology summary
# doc. (name, cells, color) -- descriptive names only, no internal F-number
# or Tier-A/B/C codenames anywhere on the figure (ground rule: the figure
# must stand alone with no internal repository labels).
CAMPAIGNS = [
    ("cross-deployment campaign", 1008, style.ORANGE),
    ("colocation campaign", 1440, style.SKY_BLUE),
    ("cadence sweep", 432, style.BLUISH_GREEN),
    ("real applications", 288, style.REDDISH_PURPLE),
    ("microservices (DeathStarBench)", 72, style.VERMILLION),
    ("overhead campaign", 162, style.BLUE),
]
TOTAL = sum(c for _, c, _ in CAMPAIGNS)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--png", default=None)
    args = ap.parse_args()

    style.apply()
    fig, ax = plt.subplots(figsize=(style.TEXT_WIDTH, 2.05))
    ax.set_xlim(0, TOTAL)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.grid(False)

    # One proportional stacked bar gives the "grasp scale at a glance"
    # reading; per-segment floating labels collide badly once a campaign
    # (Tier-C, 72 cells = 2% of the axis) is too narrow to hold its own
    # label, so names/counts move to an evenly spaced legend row below
    # instead of sitting on top of their segment.
    bar_y0, bar_h = 0.56, 0.30
    x = 0
    for name, cells, color in CAMPAIGNS:
        w = cells
        ax.add_patch(FancyBboxPatch(
            (x, bar_y0), w, bar_h,
            boxstyle="round,pad=0,rounding_size=1.5",
            facecolor=color + "55", edgecolor=color, linewidth=1.0))
        if w / TOTAL > 0.10:
            ax.text(x + w / 2, bar_y0 + bar_h / 2, f"{cells}", ha="center",
                     va="center", fontsize=style.ANNOT - 1.0,
                     color=color, fontweight="bold")
        x += w

    ax.text(0, bar_y0 + bar_h + 0.06,
             f"one-third-host footprint, 12 repetitions × 120 s per "
             f"cell · total {TOTAL:,} measurement cells",
             ha="left", va="bottom", fontsize=style.ANNOT - 0.5,
             style="italic", color="#444444")

    # Legend row: 2 columns x 3 rows, swatch + name + cell count.
    ncol, nrow = 2, 3
    col_w = TOTAL / ncol
    row_h = 0.42 / nrow
    for i, (name, cells, color) in enumerate(CAMPAIGNS):
        col, row = divmod(i, nrow)
        lx = col * col_w
        ly = 0.38 - row * row_h
        ax.add_patch(plt.Rectangle((lx, ly - 0.03), col_w * 0.025, 0.10,
                                    facecolor=color + "55", edgecolor=color,
                                    linewidth=0.8, transform=ax.transData))
        ax.text(lx + col_w * 0.04, ly + 0.02,
                 f"{name} — {cells} cells",
                 ha="left", va="center", fontsize=style.ANNOT - 0.7)

    out = Path(args.out)
    spec = style.FigSpec(style.TEXT_WIDTH, 2.05, "fig:timeline")
    w_, h_ = style.save(fig, out, spec)
    print(f"wrote {out} ({w_:.2f} x {h_:.2f} in)")
    if args.png:
        fig.savefig(args.png, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""plot-fig-pipeline.py -- new optional figure: the experiment-automation
pipeline, for the reproducibility subsection.

Hand-drawn schematic (no data), left to right: the per-OS/per-engine
entrypoints, the campaign driver, the bench-engine stages, the per-cell
artifacts each run writes, the adjudicators, and the figure renderers.
Names match the repository's actual script/stage names (from
figure-improvement-brief.md's own description and the methodology summary),
not internal codenames.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

import jsa_style as style


def box(ax, xy, w, h, text, *, fc="white", ec=style.BLACK, lw=0.8,
        fontsize=None, fontweight="normal"):
    x, y = xy
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h, boxstyle="round,pad=0.006,rounding_size=0.010",
        facecolor=fc, edgecolor=ec, linewidth=lw))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center",
             fontsize=fontsize or style.BODY, fontweight=fontweight)


def arrow(ax, p0, p1, *, lw=0.9):
    ax.add_patch(FancyArrowPatch(
        p0, p1, arrowstyle="-|>", mutation_scale=7, linewidth=lw,
        color=style.BLACK, shrinkA=1, shrinkB=1))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--png", default=None)
    args = ap.parse_args()

    style.apply()
    fig, ax = plt.subplots(figsize=(style.TEXT_WIDTH, 2.15))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.grid(False)

    stages = [
        ("entrypoints", style.ORANGE,
         "ub22run.sh\nub24run.sh\ncontainerun24.sh"),
        ("campaign driver", style.SKY_BLUE,
         "run-big-batch.sh\nenv × variant ×\nworkload × rep"),
        ("bench engine", style.BLUISH_GREEN,
         "run-intp-bench.sh\ndetect → build → solo →\npairwise → overhead →\ntimeseries → report"),
        ("per-cell artifacts", style.REDDISH_PURPLE,
         "profiler.tsv\ngroundtruth.tsv\nrun.json"),
        ("adjudicators", style.VERMILLION,
         "analyze-faithfulness.py\nanalyze-cross-\ndeployment.py\n"
         "analyze-cadence.py …"),
        ("figure renderers", style.BLUE,
         "bench/plot/*.py\n→ figures/"),
    ]
    n = len(stages)
    margin = 0.01
    gap = 0.018
    bw = (1 - 2 * margin - (n - 1) * gap) / n
    y0, h = 0.30, 0.42
    for i, (title, color, body) in enumerate(stages):
        x = margin + i * (bw + gap)
        box(ax, (x, y0), bw, h, body, fc=color + "1f", ec=color,
            fontsize=style.ANNOT - 1.0)
        ax.text(x + bw / 2, y0 + h + 0.04, title, ha="center", va="bottom",
                 fontsize=style.ANNOT - 0.3, fontweight="bold", color=color)
        if i < n - 1:
            arrow(ax, (x + bw + 0.002, y0 + h / 2),
                  (x + bw + gap - 0.002, y0 + h / 2))

    ax.text(0.5, 0.06,
             "one command end to end — index.tsv is the single source of "
             "truth; resume is idempotent gap-filling keyed on CAMPAIGN_OUT",
             ha="center", va="center", fontsize=style.ANNOT - 0.7,
             style="italic", color="#444444")

    out = Path(args.out)
    spec = style.FigSpec(style.TEXT_WIDTH, 2.15, "fig:pipeline")
    w_, h_ = style.save(fig, out, spec)
    print(f"wrote {out} ({w_:.2f} x {h_:.2f} in)")
    if args.png:
        fig.savefig(args.png, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

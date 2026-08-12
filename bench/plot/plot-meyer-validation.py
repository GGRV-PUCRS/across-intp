#!/usr/bin/env python3
"""plot-meyer-validation.py -- F14 + F15 (Meyer-validation figure set).

F14  K-Means level-threshold map (Meyer 2021 Fig. 9 form): per class, the
     three centroid values on the class's level-defining metric, for the
     shipped ``R/`` classifier vs the 50k-retrained one, over the published
     utilization bands (CCPE Table 2 / JSA Table 1: 1-20 / 21-50 / 51-100 %).
     Shows C14 (bands never implemented; levels are centroid ranks) and V5
     (the retrained centroids saturate the defining metric for cpu/mem/net,
     so rank labels are tie-break artifacts on Meyer's own data).

F15  Degradation tables (IADA 2022 Fig. 6 form): response-time multiplier by
     class x level, fork (JSS empirical) vs paper (CCPE/JSA printed) table --
     the two published tables `-Diada.degTable` selects between (N1/E5/W2.3).

Inputs: `IADA-second-born/meyer-validation/kmeans-centers.tsv` (extracted from
the .rda sets; provenance in results/PROVENANCE.md) and the tables hardcoded
in `CloudSimInterference/src/cloudsim/interference/Degradation.java`.
"""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).parent))
import p2_figio  # noqa: E402
import paper_style  # noqa: E402

CENTERS = Path.home() / "Desktop/intpismo/IADA-second-born/meyer-validation/kmeans-centers.tsv"
OUT = Path(__file__).parents[2] / "results/figures/p2-meyer-validation"

# predict.kmeans level-defining column per class (CLASSIFIER-INTERNALS §4).
LEVEL_COL = {"cpu": "cpu", "mem": "mbw", "disk": "blk", "net": "netp", "cache": "llcocc"}
CLASS_ORDER = ["cpu", "mem", "disk", "cache", "net"]

# Ordered level -> sequential steps of one hue (magnitude job, not identity).
LEVEL_COLORS = {"low": "#c6dbef", "mod": "#6baed6", "hig": "#2171b5"}
LEVELS = ["low", "mod", "hig"]

# Degradation.java (fork = JSS 2022 empirical; paper = CCPE 2019/JSA 2021).
# Order: (low, mod, hig); the leading 1.00 "absent" entry is omitted.
TABLES = {
    "fork (JSS 2022 empirical)": {
        "cpu": (1.05, 1.17, 1.38), "mem": (1.10, 1.67, 1.79),
        "disk": (1.21, 1.92, 2.31), "cache": (1.12, 1.24, 1.32),
        "net": (1.13, 1.43, 1.62),
    },
    "paper (CCPE 2019 / JSA 2021)": {
        "cpu": (1.03, 1.15, 1.33), "mem": (1.07, 1.62, 1.74),
        "disk": (1.12, 1.82, 2.25), "cache": (1.07, 1.18, 1.26),
        "net": (1.05, 1.32, 1.57),
    },
}


def load_centers():
    per = defaultdict(list)  # (source, class) -> [defining-metric values]
    with CENTERS.open() as f:
        for row in csv.DictReader(f, delimiter="\t"):
            per[(row["source"], row["class"])].append(float(row[LEVEL_COL[row["class"]]]))
    return per


def fig14(per):
    fig, axes = plt.subplots(1, 2, figsize=(paper_style.COLUMN_WIDTH * 2, 2.1),
                             sharey=True, sharex=True)
    panels = [("shipped", "shipped (R/forced-trained)"),
              ("rda50k", "retrained on published 50k")]
    ys = {cls: i for i, cls in enumerate(reversed(CLASS_ORDER))}
    for ax, (src, title) in zip(axes, panels):
        # Published utilization bands (never implemented in the artifact -- C14).
        for lo, hi, shade in ((1, 20, "#f5f5f5"), (21, 50, "#ebebeb"), (51, 100, "#e0e0e0")):
            ax.axvspan(lo, hi, color=shade, zorder=0, linewidth=0)
        for x, lab in ((10.5, "low"), (35.5, "mod"), (75.5, "hig")):
            ax.text(x, len(CLASS_ORDER) - 0.45, lab, ha="center", va="top",
                    fontsize=paper_style.ANNOT, color="#888888", style="italic")
        for cls in CLASS_ORDER:
            vals = sorted(per[(src, cls)])
            y = ys[cls]
            ax.plot([min(vals), max(vals)], [y, y], lw=0.8, color="#bbbbbb", zorder=2)
            for lvl, v in zip(LEVELS, vals):
                ax.scatter([v], [y], s=16, color=LEVEL_COLORS[lvl],
                           edgecolor="#333333", linewidth=0.5, zorder=3)
            # Annotate the spread (or its collapse) once per class row.
            spread = max(vals) - min(vals)
            note = f"{min(vals):.0f}–{max(vals):.0f}" if spread >= 3 else f"≈{vals[1]:.0f} (tied)"
            ax.text(101.5, y, note, va="center", ha="left",
                    fontsize=paper_style.ANNOT, color="#222222")
        ax.set_title(title, fontsize=paper_style.TITLE)
        ax.set_xlim(0, 118)
        ax.set_ylim(-0.6, len(CLASS_ORDER) - 0.4)
        ax.set_xticks([0, 20, 50, 100])
        ax.set_xlabel("level-defining metric value (0–100)")
        ax.tick_params(axis="y", length=0)
        for spine in ("top", "right", "left"):
            ax.spines[spine].set_visible(False)
    axes[0].set_yticks(list(ys.values()),
                       [f"{c} ({LEVEL_COL[c]})" for c in reversed(CLASS_ORDER)])
    handles = [plt.Line2D([0], [0], marker="o", ls="", markersize=4.5,
                          markerfacecolor=LEVEL_COLORS[l], markeredgecolor="#333333",
                          markeredgewidth=0.5, label=f"{l} (centroid rank)") for l in LEVELS]
    fig.legend(handles=handles, loc="lower center", ncol=3, frameon=False,
               fontsize=paper_style.LEGEND, bbox_to_anchor=(0.5, -0.16))
    p2_figio.save(fig, OUT, "F14-kmeans-threshold-map")
    plt.close(fig)


def fig15():
    fig, axes = plt.subplots(1, 2, figsize=(paper_style.COLUMN_WIDTH * 2, 2.2),
                             sharey=True)
    width = 0.26
    for ax, (name, table) in zip(axes, TABLES.items()):
        for li, lvl in enumerate(LEVELS):
            xs = [i + (li - 1) * width for i in range(len(CLASS_ORDER))]
            vals = [table[c][li] for c in CLASS_ORDER]
            ax.bar(xs, [v - 1.0 for v in vals], width * 0.92, bottom=1.0,
                   color=LEVEL_COLORS[lvl], edgecolor="white", linewidth=0.5,
                   label=lvl)
            for x, v in zip(xs, vals):
                ax.text(x, v + 0.015, f"{v:.2f}", ha="center", va="bottom",
                        fontsize=paper_style.ANNOT, color="#222222", rotation=90)
        ax.set_title(name, fontsize=paper_style.TITLE)
        ax.set_xticks(range(len(CLASS_ORDER)), CLASS_ORDER)
        ax.set_ylim(1.0, 2.62)
        ax.axhline(1.0, color="#444444", lw=0.8)
        for spine in ("top", "right"):
            ax.spines[spine].set_visible(False)
    axes[0].set_ylabel("response-time multiplier (solo = 1.00)")
    axes[1].legend(frameon=False, fontsize=paper_style.LEGEND, title="level",
                   title_fontsize=paper_style.LEGEND, loc="upper right")
    p2_figio.save(fig, OUT, "F15-degradation-tables")
    plt.close(fig)


def main():
    paper_style.apply()
    per = load_centers()
    fig14(per)
    fig15()
    print(f"wrote F14 + F15 under {OUT}/{{png,pdf}}/")


if __name__ == "__main__":
    main()

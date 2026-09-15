#!/usr/bin/env python3
"""plot-fig-transfergate.py -- new optional figure: the domain-transfer gate
as bars instead of only Table 3 (tab:transfer-gate) in the manuscript.

Not data-driven from a campaign TSV: the numbers are the adjudicated
transfer-gate results already printed in tab:transfer-gate / Table 3 of
main-jsa.tex (5-fold CV host/VM accuracy, and host-to-VM accuracy + memory-
class recall for the three classifier tiers). This script only re-presents
those already-adjudicated numbers as a chart; it must never recompute them.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt

import jsa_style as style

# Source of record: tab:transfer-gate in main-jsa.tex / the methodology
# summary doc. Do not recompute -- only re-present.
TIERS = ["canonical-7", "proxy-swap", "full-fingerprint"]
CV_HOST = [1.000, 0.999, 1.000]
CV_VM = [0.999, 0.999, 1.000]
XFER_ACC = [0.507, 0.426, 0.780]
XFER_RECALL = [0.41, 0.25, 1.00]

COLORS = [style.ORANGE, style.SKY_BLUE, style.BLUISH_GREEN]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--png", default=None)
    args = ap.parse_args()

    style.apply()
    fig, (ax1, ax2) = plt.subplots(
        1, 2, figsize=(style.TEXT_WIDTH, 2.35),
        gridspec_kw={"width_ratios": [1, 1]})

    x = np.arange(len(TIERS))
    w = 0.35

    # Panel 1: within-domain CV (host vs VM), the "before crossing" baseline.
    ax1.bar(x - w / 2, CV_HOST, w, label="host", color=style.BLUE,
            edgecolor="black", linewidth=0.4)
    ax1.bar(x + w / 2, CV_VM, w, label="VM", color=style.VERMILLION,
            edgecolor="black", linewidth=0.4, hatch="//")
    ax1.set_ylim(0, 1.15)
    ax1.set_ylabel("5-fold CV accuracy")
    ax1.set_xticks(x)
    ax1.set_xticklabels(TIERS, rotation=20, ha="right")
    ax1.axhline(1.0, color="grey", lw=0.5, ls=":")
    for xi, (h, v) in enumerate(zip(CV_HOST, CV_VM)):
        ax1.text(xi - w / 2, h + 0.03, f"{h:.3f}", ha="center",
                  fontsize=style.ANNOT - 1.0)
        ax1.text(xi + w / 2, v + 0.03, f"{v:.3f}", ha="center",
                  fontsize=style.ANNOT - 1.0)
    style.compact_legend(ax1, *ax1.get_legend_handles_labels(), ncol=2)

    # Panel 2: host-to-VM transfer, no retraining -- the actual gate. Memory-
    # class recall annotated on top of each bar (a second, harder-hit metric,
    # not a duplicate encoding of the accuracy bar itself).
    bars = ax2.bar(x, XFER_ACC, 0.5, color=COLORS, edgecolor="black",
                    linewidth=0.5)
    ax2.set_ylim(0, 1.15)
    ax2.set_ylabel("host→VM accuracy (no retraining)")
    ax2.set_xticks(x)
    ax2.set_xticklabels(TIERS, rotation=20, ha="right")
    ax2.axhline(1.0, color="grey", lw=0.5, ls=":")
    for xi, (a, r) in enumerate(zip(XFER_ACC, XFER_RECALL)):
        ax2.text(xi, a + 0.03, f"acc {a:.3f}\nmem. recall {r:.2f}",
                  ha="center", va="bottom", fontsize=style.ANNOT - 1.0)

    for ax in (ax1, ax2):
        ax.set_axisbelow(True)

    out = Path(args.out)
    spec = style.FigSpec(style.TEXT_WIDTH, 2.35, "fig:transfergate")
    w_, h_ = style.save(fig, out, spec)
    print(f"wrote {out} ({w_:.2f} x {h_:.2f} in)")
    if args.png:
        fig.savefig(args.png, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

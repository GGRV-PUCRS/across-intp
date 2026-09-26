#!/usr/bin/env python3
"""plot-figA1-jsa.py -- JSA redraw of fig:a1 (Figure_A1), the host-count
sweep. Source: results/IADA-second-born/sim-experiments-20260811/
e3-hosts-{9,14,19,23,28}.tsv, mean idi_avg per tier per host count -- no
statistic recomputed differently than the sim-experiments campaign already
produced. No in-figure title (caption policy): the caption already explains
why the curve is flat (strict-swap SA operators, per-host occupancy
invariant). Tier codenames renamed to canonical-7/proxy-swap/full-fingerprint
per the brief; marker shape added per tier so the red/green pair (tier
T1/B in the old palette) is not the only distinguishing channel.
"""
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt

import jsa_style as style

TIER_LABEL = {"T1": "canonical-7", "A": "proxy-swap", "B": "full-fingerprint"}
TIER_COLOR = {"T1": style.ORANGE, "A": style.SKY_BLUE, "B": style.BLUISH_GREEN}
TIER_MARKER = {"T1": "o", "A": "^", "B": "s"}
TIER_ORDER = ["T1", "A", "B"]
HOSTS = [9, 14, 19, 23, 28]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    style.apply()
    means = {t: [] for t in TIER_ORDER}
    for h in HOSTS:
        idi = defaultdict(list)
        for r in csv.DictReader(
                (args.data_dir / f"e3-hosts-{h}.tsv").open(), delimiter="\t"):
            if r.get("idi_avg") in (None, "", "FAIL"):
                continue
            idi[r["tier"]].append(float(r["idi_avg"]))
        for t in TIER_ORDER:
            means[t].append(sum(idi[t]) / len(idi[t]))

    width = style.COLUMN_WIDTH * 1.5
    height = 2.5
    fig, ax = plt.subplots(figsize=(width, height), layout="constrained")
    for t in TIER_ORDER:
        ax.plot(HOSTS, means[t], marker=TIER_MARKER[t], color=TIER_COLOR[t],
                ms=5, lw=1.3, label=TIER_LABEL[t])
    ax.set_xticks(HOSTS)
    ax.set_xlabel("hosts in the simulated cluster")
    ax.set_ylabel("interference-degradation index")
    ax.set_ylim(0, max(max(v) for v in means.values()) * 1.15)
    ax.legend(fontsize=style.LEGEND, loc="upper right", ncol=3,
              handlelength=1.3)

    spec = style.FigSpec(width, height, "fig:a1")
    w, h = style.save(fig, args.out / "Figure_A1.pdf", spec)
    plt.close(fig)
    print(f"wrote {args.out / 'Figure_A1.pdf'} ({w:.2f} x {h:.2f} in)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

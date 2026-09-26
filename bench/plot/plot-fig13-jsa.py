#!/usr/bin/env python3
"""plot-fig13-jsa.py -- JSA redraw of fig:tiers (Figure_13), the closed-loop
IDI per classifier configuration.

Source of record: results/IADA-second-born/sim-experiments-20260811/
gate-default.tsv (vm condition, host-trained classifier, 5 sim reps per
tier) -- the BANKED gate numbers, not the S8 psp-rebank arm (that re-key's
"adoption is pending an owner decision" per the methodology write-up, so the
figure must still show the numbers the manuscript caption states: T1=6400,
A=3622, B=5753). CI convention is p2_ci.rep_ci (10000-resample rep-level
bootstrap, shared with the rest of the P2 figure set) -- no statistic is
recomputed by hand.

Single panel only (the manuscript caption discusses idi_avg, not
migrations-triggered; a second panel would assert a claim the caption never
makes). No in-figure title/subtitle/footer prose per the 2026-09-15 caption
policy -- the caption already states the reading; this figure keeps only the
bars, the CI whiskers, the tier labels, and the in-plot percent-reduction
callouts (which carry data, so they stay).
"""
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt

import jsa_style as style
import p2_ci

TIER_LABEL = {"T1": "canonical-7", "A": "proxy-swap", "B": "full-fingerprint"}
TIER_COLOR = {"T1": style.ORANGE, "A": style.SKY_BLUE, "B": style.BLUISH_GREEN}
TIER_ORDER = ["T1", "A", "B"]


def read_reps(tsv: Path, env: str = "vm"):
    idi = defaultdict(list)
    for r in csv.DictReader(tsv.open(), delimiter="\t"):
        if r.get("idi_avg") in (None, "", "FAIL"):
            continue
        if r.get("env") and r["env"] != env:
            continue
        idi[r["tier"]].append(float(r["idi_avg"]))
    return idi


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("tsv", nargs="?", type=Path,
                     default=Path("results/IADA-second-born/"
                                  "sim-experiments-20260811/gate-default.tsv"))
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    style.apply()
    idi = read_reps(args.tsv)

    expect = {"T1": 6400, "A": 3622, "B": 5753}
    for t, exp in expect.items():
        got = sum(idi[t]) / len(idi[t])
        if abs(got - exp) > 5:
            raise SystemExit(
                f"tier {t}: computed mean {got:.1f} != banked {exp} "
                f"(tol 5) -- check {args.tsv} still holds the pre-S8-rekey "
                f"gate-default rows, not a mixed/rekeyed source")

    width = style.COLUMN_WIDTH * 1.35
    height = 2.6
    fig, ax = plt.subplots(figsize=(width, height), layout="constrained")
    means, los, his = [], [], []
    for i, t in enumerate(TIER_ORDER):
        mean, lo, hi = p2_ci.rep_ci(idi[t], seed_offset=i)
        means.append(mean)
        los.append(mean - lo)
        his.append(hi - mean)
        ax.bar(i, mean, color=TIER_COLOR[t], width=0.6,
               yerr=[[mean - lo], [hi - mean]], capsize=3,
               error_kw=dict(lw=1.0, color="black"))
        ax.text(i, mean + (hi - mean) + means[0] * 0.02, f"{mean:.0f}",
                ha="center", va="bottom", fontsize=style.BODY,
                fontweight="bold")

    base = means[0]
    for i, t in enumerate(TIER_ORDER[1:], start=1):
        pct = 100 * (base - means[i]) / base
        ax.text(i, means[i] * 0.5, f"{pct:.0f}%\nlower", ha="center",
                va="center", fontsize=style.ANNOT, color="white",
                fontweight="bold")

    ax.set_xticks(range(len(TIER_ORDER)))
    ax.set_xticklabels([TIER_LABEL[t] for t in TIER_ORDER],
                        fontsize=style.BODY)
    ax.set_ylabel("interference-degradation index\n(lower = better placement)")
    ax.set_ylim(0, max(his[i] + means[i] for i in range(3)) * 1.15)

    spec = style.FigSpec(width, height, "fig:tiers")
    w, h = style.save(fig, args.out / "Figure_13.pdf", spec)
    plt.close(fig)
    print(f"wrote {args.out / 'Figure_13.pdf'} ({w:.2f} x {h:.2f} in); "
          f"T1={means[0]:.0f} A={means[1]:.0f} B={means[2]:.0f} "
          f"(banked check passed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

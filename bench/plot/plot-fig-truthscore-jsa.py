#!/usr/bin/env python3
"""plot-fig-truthscore-jsa.py -- fig_truthscore.pdf (fig:truthscore, \\figph{S1}).

Known-class yardstick re-score of the final placements, per classifier
configuration, from the S16/S1 rerun (bench/iada/DECISIONS-sim-experiments.md
S1 entry): the five-class (Y5, regime labelled CPU so every configuration is
priced on the same classes) and six-class (Y6, regime priced) variants side by
side. IASA (the paper's own search) has n=20 per configuration; CIAPA's
two-phase annealing search has n=10; EVEN is a single deterministic
round-robin placement whose score does not depend on any classifier, so it is
drawn as a horizontal reference line (identical across tiers, zero-width CI
by construction, confirmed by the S1 runs reading EXACTLY the same value under
all three tiers).

Sources of record (no value recomputed beyond the CIs, which use the shared
p2_ci rep-level bootstrap convention):
  s1-truthscore.tsv         per-rep scores (IASA n=20, CIAPA n=10, both
                            yardsticks; 'full' and 'final6th' windows are
                            identical in this campaign)
  s1-truthscore-summary.tsv EVEN's scores and the adjudicated means, used to
                            cross-check the per-rep aggregates

    python3 bench/plot/plot-fig-truthscore-jsa.py --data-root DIR --out DIR
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jsa_style as style  # noqa: E402
import p2_ci  # noqa: E402  (shared rep-level bootstrap CI convention, N=10000 seed=20260607)

TIER_DESC = {"T1": "canonical-7", "A": "proxy-swap", "B": "full-fingerprint"}
TIER_ORDER = ["T1", "A", "B"]
TIER_COLOR = {"T1": style.SKY_BLUE, "A": style.REDDISH_PURPLE, "B": style.ORANGE}
YARDSTICK_DESC = {"Y5": "five-class yardstick (Y5)", "Y6": "six-class yardstick (Y6)"}
YARDSTICK_ORDER = ["Y5", "Y6"]
# s1-truthscore.tsv carries both windows; S1 verified they are identical in
# this campaign (stable stress-ng traces land every sample in the same
# tertile bucket), so the figure uses 'full' and notes it in the printout.
WINDOW = "full"


def _read_scores(tsv: Path) -> dict[tuple[str, str], list[float]]:
    """(approach, tier, yardstick) -> rep scores, for the chosen window."""
    out: dict[tuple[str, str, str], list[float]] = defaultdict(list)
    for r in csv.DictReader(tsv.open(), delimiter="\t"):
        if r["window"] != WINDOW:
            continue
        v = r.get("score")
        if v in (None, "", "FAIL"):
            continue
        out[(r["approach"], r["tier"], r["yardstick"])].append(float(v))
    return out


def _read_even(tsv: Path) -> dict[str, float]:
    """yardstick -> EVEN score (mean over tiers; identical by construction)."""
    out: dict[str, list[float]] = defaultdict(list)
    for r in csv.DictReader(tsv.open(), delimiter="\t"):
        if r["approach"] == "EVEN" and r["window"] == WINDOW:
            out[r["yardstick"]].append(float(r["mean"]))
    return {y: float(np.mean(vs)) for y, vs in out.items()}


def fig_truthscore(data_root: Path, out: Path) -> None:
    scores = _read_scores(data_root / "s1-truthscore.tsv")
    even = _read_even(data_root / "s1-truthscore-summary.tsv")
    if not scores:
        print("fig_truthscore: no usable rows in s1-truthscore.tsv, skipped")
        return

    width = style.TEXT_WIDTH
    height = 2.55
    fig, axes = plt.subplots(1, 2, figsize=(width, height), sharey=True,
                             layout="constrained")

    bar_w = 0.30
    x = np.arange(len(TIER_ORDER))
    for ax, ystick in zip(axes, YARDSTICK_ORDER):
        for xi, tier in enumerate(TIER_ORDER):
            # IASA main bars: n=20, tier color, solid.
            vals = np.asarray(scores.get(("IASA", tier, ystick), []), dtype=float)
            if vals.size:
                m, lo, hi = p2_ci.rep_ci(vals, seed_offset=10 + xi)
                ax.bar(xi - bar_w / 2, m, bar_w, yerr=p2_ci.yerr(m, lo, hi),
                       capsize=2.2, color=TIER_COLOR[tier], alpha=0.88,
                       edgecolor="black", linewidth=0.4, zorder=2)
                ax.text(xi - bar_w / 2, hi + 40, f"{m:.0f}", ha="center",
                        va="bottom", fontsize=style.ANNOT)
            # CIAPA bars: n=10, same tier color, hatched (approach channel).
            vals = np.asarray(scores.get(("CIAPA", tier, ystick), []), dtype=float)
            if vals.size:
                m, lo, hi = p2_ci.rep_ci(vals, seed_offset=20 + xi)
                ax.bar(xi + bar_w / 2, m, bar_w, yerr=p2_ci.yerr(m, lo, hi),
                       capsize=2.2, color=TIER_COLOR[tier], alpha=0.88,
                       edgecolor="black", linewidth=0.4, hatch="//", zorder=2)
                ax.text(xi + bar_w / 2, hi + 40, f"{m:.0f}", ha="center",
                        va="bottom", fontsize=style.ANNOT)
        # EVEN: deterministic, tier-independent -- a reference line, not bars.
        ev = even.get(ystick)
        if ev is not None:
            ax.axhline(ev, color="black", lw=0.9, ls=(0, (4, 2)), zorder=3)
            ax.text(-0.40, ev + 60, f"EVEN {ev:.0f}",
                    ha="left", va="bottom", fontsize=style.ANNOT)
        ax.set_title(YARDSTICK_DESC[ystick], fontsize=style.BODY)
        ax.set_xticks(x)
        ax.set_xticklabels([TIER_DESC[t] for t in TIER_ORDER], fontsize=style.BODY)
        ax.grid(axis="y", ls=":", alpha=0.3)
        ax.set_axisbelow(True)

    top = max(float(np.nanmax(p2_ci.rep_ci(
        np.asarray(scores[("IASA", t, y)], dtype=float), seed_offset=0)[2]))
        for t in TIER_ORDER for y in YARDSTICK_ORDER)
    axes[0].set_ylim(0, top * 1.24)
    axes[0].set_ylabel("known-class yardstick score\n(lower = better placement)",
                       fontsize=style.BODY)

    handles = [Patch(facecolor=TIER_COLOR[t], edgecolor="black", linewidth=0.4,
                     label=f"{TIER_DESC[t]} (n=20)")
               for t in TIER_ORDER]
    handles.append(Patch(facecolor="white", edgecolor="black", linewidth=0.4,
                         hatch="//", label="CIAPA (n=10)"))
    handles.append(Line2D([0], [0], color="black", lw=0.9, ls=(0, (4, 2)),
                          label="EVEN (deterministic)"))
    style.compact_legend(fig, handles, [h.get_label() for h in handles], ncol=5)

    # Cross-check the plotted means against the adjudicated summary, and print
    # the key values so the one-shot render log carries them.
    summary = {}
    for r in csv.DictReader((data_root / "s1-truthscore-summary.tsv").open(),
                            delimiter="\t"):
        if r["window"] == WINDOW and r["approach"] in ("IASA", "CIAPA"):
            summary[(r["approach"], r["tier"], r["yardstick"])] = float(r["mean"])
    for appr in ("IASA", "CIAPA"):
        for y in YARDSTICK_ORDER:
            got = []
            for t in TIER_ORDER:
                vals = np.asarray(scores.get((appr, t, y), []), dtype=float)
                got.append(float(vals.mean()) if vals.size else float("nan"))
            print(f"truthscore {y} {appr} means: "
                  + " ".join(f"{TIER_DESC[t]}={m:.0f}" for t, m in zip(TIER_ORDER, got)))
            ref = [summary.get((appr, t, y)) for t in TIER_ORDER]
            if all(v is not None and abs(v - m) < 1.0
                   for v, m in zip(ref, got) if not np.isnan(m)):
                print(f"VALIDATION OK: {y} {appr} means match "
                      "s1-truthscore-summary.tsv")
            else:
                print(f"VALIDATION WARN: {y} {appr} means differ from summary "
                      f"(plotted {got}, summary {ref})")
    print(f"truthscore EVEN: " + " ".join(f"{y}={even[y]:.0f}" for y in YARDSTICK_ORDER))

    spec = style.FigSpec(width, height, "fig:truthscore")
    style.save(fig, out / "fig_truthscore.pdf", spec)
    plt.close(fig)
    print(f"wrote {out / 'fig_truthscore.pdf'}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-root", type=Path,
                    default=Path("bench/iada/results/sim-experiments-20260917-s16"))
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    style.apply()
    args.out.mkdir(parents=True, exist_ok=True)
    fig_truthscore(args.data_root, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

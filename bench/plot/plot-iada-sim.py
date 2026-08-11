#!/usr/bin/env python3
"""plot-iada-sim.py — F13 (scheduling axis): per-tier CloudSim interference-aware
scheduling outcome in the VM, where the canonical RDT metrics are unavailable.

Consumes the rep TSV (run-tier-sim-reps.sh → tier-sim-reps.tsv): N reps per tier
of the IADA SA scheduler. Plots the mean interference degradation index
(interference + migration cost — IADA's headline metric) per tier, with a 95 %
rep-level bootstrap CI. Lower = better placement. PNG + PDF.

Note on vocabulary: the index plotted here is IADA's response-time interference
DEGRADATION index. It is a different quantity from the profiler-side
interference DISCRIMINATION index of the Paper 1 fig11 set, which measures the
signed pairwise-minus-solo delta per resource family. Both abbreviate to IDI in
their own paper, so the titles here spell the word out and never use the bare
`idi_avg` column name.

    python3 bench/plot/plot-iada-sim.py [tier-sim-reps.tsv] [--out DIR]
"""
from __future__ import annotations

import argparse, csv, statistics as st, sys
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parent))
import p2_ci      # noqa: E402  (shared rep-level bootstrap CI convention)
import p2_figio   # noqa: E402  (shared {png,pdf} output layout)

TIER_DESC = {"T1": "Canonical 7-metric\n(RDT — IADA baseline)",
             "A": "Proxy-swap\n(portable mem proxy)",
             "B": "Full 15-metric\n(+ regime class)"}
TIER_ORDER = ["T1", "A", "B"]
COLOR = {"T1": "#c0392b", "A": "#2980b9", "B": "#27ae60"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("tsv", nargs="?", type=Path, default="results/iada-sim/tier-sim-reps.tsv")
    ap.add_argument("--out", type=Path, default="results/figures/p2-iada-tiers")
    args = ap.parse_args()
    idi = defaultdict(list); mig = defaultdict(list)
    for r in csv.DictReader(args.tsv.open(), delimiter="\t"):
        if r.get("idi_avg") in (None, "", "FAIL"):
            continue
        idi[r["tier"]].append(float(r["idi_avg"]))
        if r.get("migrations") not in (None, ""):
            mig[r["tier"]].append(float(r["migrations"]))
    tiers = [t for t in TIER_ORDER if t in idi]
    args.out.mkdir(parents=True, exist_ok=True)

    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(11, 4.8))
    # Bars stay at the plain sample mean; only the whisker changes from an SD to
    # the 95 % rep-level bootstrap CI (p2_ci), so no bar height moves.
    cis = [p2_ci.rep_ci(idi[t], seed_offset=i) for i, t in enumerate(tiers)]
    means = [m for m, _, _ in cis]
    xs = range(len(tiers))
    ax.bar(xs, means, yerr=p2_ci.yerr_many(cis), capsize=6,
           color=[COLOR[t] for t in tiers], alpha=0.88, zorder=2)
    for x, (m, _lo, hi) in zip(xs, cis):
        ax.text(x, hi + max(means) * 0.02, f"{m:.0f}", ha="center", va="bottom", fontsize=10, fontweight="bold")
    ax.set_xticks(list(xs)); ax.set_xticklabels([TIER_DESC[t] for t in tiers], fontsize=9)
    ax.set_ylabel("interference degradation index\n— lower = better placement —", fontsize=9)
    # State n on the figure: these are simulator reps, and a percentile CI over
    # so few of them is coarse -- the reader should see what it rests on.
    nrep = min(len(idi[t]) for t in tiers)
    ax.set_title(f"Scheduling quality in the VM (mean, {p2_ci.CI_TAG}, n={nrep} sim reps)",
                 fontsize=10)
    ax.grid(axis="y", ls=":", alpha=0.3)
    # Headroom for the value labels: they now sit above the CI cap, which reaches
    # higher than the old SD whisker did, and would otherwise run into the frame.
    ax.set_ylim(0, max(hi for _m, _lo, hi in cis) * 1.10)
    # annotate the improvement vs T1
    if "T1" in idi and len(tiers) > 1:
        base = st.mean(idi["T1"])
        for x, t in zip(xs, tiers):
            if t == "T1":
                continue
            d = 100 * (base - st.mean(idi[t])) / base
            lab = (f"{d:.0f}% lower IDI\nvs canonical" if d >= 0
                   else f"{-d:.0f}% higher IDI\nvs canonical")
            ax.text(x, st.mean(idi[t]) / 2, lab, ha="center", va="center",
                    fontsize=9, color="white", fontweight="bold")

    mtiers = [t for t in tiers if mig.get(t)]
    # Offset the seed stream past the idi panel so the two panels do not share
    # one resample draw.
    mcis = [p2_ci.rep_ci(mig[t], seed_offset=len(tiers) + i) for i, t in enumerate(mtiers)]
    ax2.bar(range(len(mtiers)), [m for m, _, _ in mcis],
            yerr=p2_ci.yerr_many(mcis), capsize=6,
            color=[COLOR[t] for t in mtiers], alpha=0.88)
    ax2.set_xticks(range(len(mtiers))); ax2.set_xticklabels([TIER_DESC[t] for t in mtiers], fontsize=9)
    ax2.set_ylabel("migrations (total)", fontsize=9)
    ax2.set_title(f"Migrations triggered (mean, {p2_ci.CI_TAG})", fontsize=10)
    ax2.grid(axis="y", ls=":", alpha=0.3)

    fig.suptitle("Closed-loop scheduling outcome per classifier tier, inside a KVM guest\n"
                 "the canonical RDT set is memory-blind in the VM; the portable metrics restore it",
                 fontsize=12, fontweight="bold")
    fig.text(0.5, -0.07,
             "Canonical-7 (T1) and proxy-swap (A) share the same 5-class interference model, so their interference degradation "
             "index is\ndirectly comparable: replacing the VM-blind RDT memory metric with its portable proxy cuts that index by "
             "~43% in the guest.\nFull-15 (B) adds a 6th 'oversubscription regime' class the canonical fingerprint cannot represent "
             "(T1 mislabels that workload as\n'mem'); B carries an extra degradation factor, so its still-lower-than-canonical IDI is "
             "achieved WHILE modeling interference the others miss.",
             ha="center", va="top", fontsize=8.5, style="italic")
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    p2_figio.save(fig, args.out, "F13-tier-scheduling-idi", dpi=150)
    print(p2_figio.describe(args.out, "F13-tier-scheduling-idi"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

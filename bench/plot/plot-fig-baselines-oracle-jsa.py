#!/usr/bin/env python3
"""plot-fig-baselines-oracle-jsa.py -- two new, exploratory JSA figures from
this session's Phase 3.2/3.4 follow-up work (jsa-repo-fix-brief.md):

  fig_baselines.pdf (fig:baselines) -- IASA (the paper's own scheduler) vs.
    CIAPA vs. EVEN, per tier. Both baselines were promised in
    sec:methodology:pipeline ("against EVEN, CIAPA, and Segmented
    baselines") but never actually run before this session (the `approach`
    branch was a hardcoded literal). Log-scale y-axis: EVEN's blind
    round-robin placement is 6.7-16.2x worse than IASA's search, which
    would flatten IASA/CIAPA to invisible bars on a linear axis.

  fig_oracle.pdf (fig:oracle) -- each tier's own self-reported IDI vs. a
    common (tier B) classifier's re-score of the SAME converged placement,
    both over an identical (full-trace) classification window. T1's own
    (RDT-blind) classifier reads its own placements as significantly worse
    than the common yardstick does; A is statistically indistinguishable
    from it; B is an exact self-consistency check by construction (the
    same classifier scoring itself).

Sources of record (no value recomputed here, only re-presented):
  bench/iada/results/sim-experiments-20260916/{even,ciapa}-baseline-t1ab-n10.tsv
  bench/iada/results/sim-experiments-20260916/gate-{B-psp-n20,T1-A-n10}.tsv
  bench/iada/results/sim-experiments-20260916/oracle-t1ab-n10.tsv
  bench/iada/DECISIONS-sim-experiments.md S10, S12, S13 (numbers cross-checked)

    python3 bench/plot/plot-fig-baselines-oracle-jsa.py --data-root DIR --out DIR
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean

import numpy as np
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jsa_style as style  # noqa: E402
import p2_ci  # noqa: E402  (shared rep-level bootstrap CI convention, N=10000 seed=20260607)

TIER_DESC = {"T1": "Canonical 7-metric", "A": "Proxy-swap", "B": "Full 15-metric"}
TIER_ORDER = ["T1", "A", "B"]
APPROACH_COLOR = {"IASA": style.BLUISH_GREEN, "CIAPA": style.ORANGE, "EVEN": style.VERMILLION}


def _read_idi(tsv: Path, col: str = "idi_avg") -> dict[str, list[float]]:
    out = defaultdict(list)
    for r in csv.DictReader(tsv.open(), delimiter="\t"):
        v = r.get(col)
        if v in (None, "", "FAIL"):
            continue
        out[r["tier"]].append(float(v))
    return out


def fig_baselines(data_root: Path, out: Path) -> None:
    iasa_gate = _read_idi(data_root / "gate-T1-A-n10.tsv")
    iasa_gate["B"] = _read_idi(data_root / "gate-B-psp-n20.tsv")["B"]
    even = _read_idi(data_root / "even-baseline-t1ab-n10.tsv", col="interference_avg")
    ciapa = _read_idi(data_root / "ciapa-baseline-t1ab-n10.tsv")

    approaches = ["IASA", "CIAPA", "EVEN"]
    data = {"IASA": iasa_gate, "CIAPA": ciapa, "EVEN": even}

    width = style.TEXT_WIDTH
    height = 2.4
    fig, ax = plt.subplots(figsize=(width, height), layout="constrained")

    n_tiers = len(TIER_ORDER)
    n_app = len(approaches)
    group_w = 0.8
    bar_w = group_w / n_app
    x0 = np.arange(n_tiers)

    global_max = 0.0
    for ai, appr in enumerate(approaches):
        xs = x0 + (ai - (n_app - 1) / 2) * bar_w
        means, los, his = [], [], []
        for t in TIER_ORDER:
            vals = data[appr].get(t, [])
            if not vals:
                means.append(0); los.append(0); his.append(0)
                continue
            if len(vals) > 1 and len(set(vals)) > 1:
                m, lo, hi = p2_ci.rep_ci(np.array(vals), seed_offset=hash((appr, t)) % 1000)
            else:
                m = mean(vals)
                lo = hi = m  # EVEN is deterministic -- zero-width CI, not an error
            means.append(m); los.append(lo); his.append(hi)
        global_max = max(global_max, max(means))
        yerr = [[m - lo for m, lo in zip(means, los)], [hi - m for m, hi in zip(means, his)]]
        ax.bar(xs, means, bar_w * 0.92, yerr=yerr, capsize=2.5,
               color=APPROACH_COLOR[appr], alpha=0.88,
               edgecolor="black", linewidth=0.4, label=appr, zorder=2)
        for x, m in zip(xs, means):
            if m > 0:
                ax.text(x, m * 1.03, f"{m:.0f}", ha="center", va="bottom",
                        fontsize=style.ANNOT - 1.0, rotation=90)

    ax.set_yscale("log")
    ax.set_ylim(top=global_max * 3.2)  # headroom for rotated bar labels + legend row
    ax.set_xticks(x0)
    ax.set_xticklabels([TIER_DESC[t] for t in TIER_ORDER], fontsize=style.BODY)
    ax.set_ylabel("interference cost (log scale)\n— lower = better placement —",
                  fontsize=style.BODY)
    ax.grid(axis="y", ls=":", alpha=0.3, which="both")
    style.compact_legend(ax, *ax.get_legend_handles_labels(), ncol=3)

    spec = style.FigSpec(width, height, "fig:baselines")
    style.save(fig, out / "fig_baselines.pdf", spec)
    plt.close(fig)
    print(f"wrote {out / 'fig_baselines.pdf'}")


def fig_oracle(data_root: Path, out: Path) -> None:
    self_v = defaultdict(list)
    oracle_v = defaultdict(list)
    for r in csv.DictReader((data_root / "oracle-t1ab-n10.tsv").open(), delimiter="\t"):
        if r.get("self_idi") in (None, "", "FAIL"):
            continue
        self_v[r["tier"]].append(float(r["self_idi"]))
        oracle_v[r["tier"]].append(float(r["oracle_idi"]))

    width = style.TEXT_WIDTH * 0.62
    height = 2.4
    fig, ax = plt.subplots(figsize=(width, height), layout="constrained")

    x = np.arange(len(TIER_ORDER))
    w = 0.32

    self_m, self_lo, self_hi = [], [], []
    oracle_m, oracle_lo, oracle_hi = [], [], []
    sig_label = {}
    for ti, t in enumerate(TIER_ORDER):
        s, o = np.array(self_v[t]), np.array(oracle_v[t])
        sm, slo, shi = p2_ci.rep_ci(s, seed_offset=ti * 2)
        om, olo, ohi = p2_ci.rep_ci(o, seed_offset=ti * 2 + 1)
        self_m.append(sm); self_lo.append(slo); self_hi.append(shi)
        oracle_m.append(om); oracle_lo.append(olo); oracle_hi.append(ohi)
        if np.allclose(s, o):
            sig_label[t] = "self-check\n(Δ=0)"
            continue
        rng = np.random.default_rng(p2_ci.BOOTSTRAP_SEED + ti)
        d = (rng.choice(o, (p2_ci.BOOTSTRAP_N, len(o))).mean(1)
             - rng.choice(s, (p2_ci.BOOTSTRAP_N, len(s))).mean(1))
        dlo, dhi = np.percentile(d, list(p2_ci.CI_PCTILES))
        sig_label[t] = "*" if not (dlo <= 0 <= dhi) else "n.s."

    self_err = p2_ci.yerr_many(list(zip(self_m, self_lo, self_hi)))
    oracle_err = p2_ci.yerr_many(list(zip(oracle_m, oracle_lo, oracle_hi)))

    ax.bar(x - w / 2, self_m, w, yerr=self_err, capsize=2.5, color=style.BLUE,
           alpha=0.88, edgecolor="black", linewidth=0.4, label="self (own classifier)")
    ax.bar(x + w / 2, oracle_m, w, yerr=oracle_err, capsize=2.5, color=style.ORANGE,
           alpha=0.88, edgecolor="black", linewidth=0.4, label="oracle (tier B classifier)")

    ymax = max(max(self_hi), max(oracle_hi))
    for xi, t in enumerate(TIER_ORDER):
        ax.text(xi, ymax * 1.10, sig_label[t], ha="center", va="bottom",
                fontsize=style.ANNOT, fontweight="bold" if sig_label[t] == "*" else "normal")

    ax.set_ylim(0, ymax * 1.28)
    ax.set_xticks(x)
    ax.set_xticklabels([TIER_DESC[t] for t in TIER_ORDER], fontsize=style.BODY)
    ax.set_ylabel("interference degradation index\n(full-window re-score)", fontsize=style.BODY)
    ax.grid(axis="y", ls=":", alpha=0.3)
    style.compact_legend(ax, *ax.get_legend_handles_labels(), ncol=2)

    spec = style.FigSpec(width, height, "fig:oracle")
    style.save(fig, out / "fig_oracle.pdf", spec)
    plt.close(fig)
    print(f"wrote {out / 'fig_oracle.pdf'}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-root", type=Path,
                    default=Path("bench/iada/results/sim-experiments-20260916"))
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    style.apply()
    args.out.mkdir(parents=True, exist_ok=True)
    fig_baselines(args.data_root, args.out)
    fig_oracle(args.data_root, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

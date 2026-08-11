#!/usr/bin/env python3
"""plot-cadence-curves.py — F8: profiler fidelity & sample density vs cadence.

Consumes the analyzer TSV (bench/analyze-cadence.py --tsv, default
<sweep>/cadence-fidelity.tsv), NOT raw captures. Emits two figures, each as
PNG + PDF, under results/figures/p2-cadence-sweep/:

  F8-cadence-fidelity   — Δref(%) vs sampling interval (log-x) per workload for
                          the metrics that respond (the cadence-knee shape), plus
                          a sample-density panel. v2.1 solid / v3.3 dashed; the
                          shaded ±10% band is the fidelity tolerance.
  F8-cadence-sensitivity — heatmap of max|Δref| per metric × (workload·variant):
                          the compact "which metrics need fine sampling" view
                          (covers ALL metrics with a reading, not just the few
                          drawn as curves).

    python3 bench/plot/plot-cadence-curves.py [tsv] [--out DIR]
"""
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parent))
import p2_figio  # noqa: E402  (shared {png,pdf} output layout)
import numpy as np

THRESH = 0.05          # min max|Δref| for a metric to be drawn as a curve
BAND = 0.10            # ±10% fidelity tolerance band
FLOOR = 2.0            # skip near-zero metrics (relative Δref is noise there)
# metric display order by claim-class family (for the heatmap rows)
ORDER = ["netp", "nets", "blk", "mbw", "llcmr", "llcocc", "cpu",
         "schedlat", "psi_mem", "membw_est", "psi_io", "schedthr", "steal",
         "psp", "idle_preempt"]
COLORS = ["#d62728", "#1f77b4", "#ff7f0e", "#2ca02c", "#9467bd", "#8c564b",
          "#17becf", "#bcbd22", "#e377c2", "#7f7f7f"]
MARKERS = ["o", "s", "^", "D", "v", "P", "X", "*", "h", "<"]


def load(tsv: Path):
    fid = defaultdict(dict)      # (variant,wl,metric) -> {interval: dref%}
    dens = defaultdict(dict)     # (variant,wl) -> {interval: rows}
    med = defaultdict(dict)      # (variant,wl,metric) -> {interval: median}
    cls = {}
    with tsv.open() as fh:
        for r in csv.DictReader(fh, delimiter="\t"):
            v, w, m = r["variant"], r["workload"], r["metric"]
            iv = float(r["interval_s"])
            if m == "_density_rows_":
                dens[(v, w)][iv] = float(r["median"]); continue
            cls[m] = r["class"]
            med[(v, w, m)][iv] = float(r["median"])
            if r["dref"] != "":
                fid[(v, w, m)][iv] = float(r["dref"]) * 100.0
    return fid, dens, cls, med


def save(fig, out: Path, name: str):
    p2_figio.save(fig, out, name, dpi=140)
    plt.close(fig)
    print(p2_figio.describe(out, name))


def fig_fidelity(fid, dens, cls, med, variants, workloads, fine, out):
    ncol = len(workloads) + 1
    fig, axes = plt.subplots(1, ncol, figsize=(5.0 * ncol, 4.4))
    style = {variants[0]: "-"}
    if len(variants) > 1:
        style[variants[1]] = "--"
    # stable color+marker per metric (assigned over the union of drawn metrics)
    drawn_metrics = []
    for w in workloads:
        for m in ORDER:
            if m in drawn_metrics:
                continue
            ref_mag = max((abs(med.get((v, w, m), {}).get(fine, 0)) for v in variants), default=0)
            maxd = max((abs(d) for v in variants for d in fid.get((v, w, m), {}).values()), default=0)
            if ref_mag >= FLOOR and maxd >= THRESH * 100:
                drawn_metrics.append(m)
    cmap = {m: COLORS[i % len(COLORS)] for i, m in enumerate(drawn_metrics)}
    mmap = {m: MARKERS[i % len(MARKERS)] for i, m in enumerate(drawn_metrics)}

    for wi, w in enumerate(workloads):
        ax = axes[wi]
        ax.axhspan(-BAND * 100, BAND * 100, color="green", alpha=0.08, zorder=0)
        ax.axhline(0, color="grey", lw=0.6, zorder=1)
        for m in drawn_metrics:
            for v in variants:
                if abs(med.get((v, w, m), {}).get(fine, 0)) < FLOOR:
                    continue  # this variant's metric is near-zero here -> Δref is noise
                series = fid.get((v, w, m), {})
                if not series:
                    continue
                xs = sorted(series); ys = [series[x] for x in xs]
                ax.plot(xs, ys, style.get(v, "-"), marker=mmap[m], ms=4,
                        color=cmap[m], lw=1.6, alpha=0.9)
        ax.set_xscale("log")
        ax.set_xticks([0.1, 0.25, 0.5, 1, 2, 5])
        ax.set_xticklabels(["0.1", "0.25", "0.5", "1", "2", "5"], fontsize=8)
        ax.set_xlabel("sampling interval (s)")
        ax.set_ylabel("Δref from 0.1s (%)" if wi == 0 else "")
        ax.set_title(w.replace("_", " "), fontsize=10)
        ax.grid(True, which="both", ls=":", alpha=0.3)

    # density panel — the 4 series are ~identical (1/interval), so draw one + note
    axd = axes[-1]
    (v0, w0), d0 = next(iter(sorted(dens.items())))
    xs = sorted(d0); ys = [d0[x] for x in xs]
    axd.plot(xs, ys, "-o", color="#333333", ms=4, lw=1.6)
    axd.set_xscale("log"); axd.set_yscale("log")
    axd.set_xticks([0.1, 0.25, 0.5, 1, 2, 5])
    axd.set_xticklabels(["0.1", "0.25", "0.5", "1", "2", "5"], fontsize=8)
    axd.set_xlabel("sampling interval (s)")
    axd.set_ylabel("sample density (rows/rep)")
    axd.set_title("sample density (all series ~identical, ≈1/interval)", fontsize=9)
    axd.grid(True, which="both", ls=":", alpha=0.3)
    for x, y in zip(xs, ys):
        axd.annotate(f"{int(y)}", (x, y), fontsize=7, ha="left", va="bottom")

    # one shared legend BELOW the figure (no data overlap)
    handles = [plt.Line2D([0], [0], color=cmap[m], marker=mmap[m], lw=1.6,
                          label=f"{m} ({cls.get(m,'?')})") for m in drawn_metrics]
    handles += [plt.Line2D([0], [0], color="k", ls="-", label=f"{variants[0]} (solid)")]
    if len(variants) > 1:
        handles += [plt.Line2D([0], [0], color="k", ls="--", label=f"{variants[1]} (dashed)")]
    fig.legend(handles=handles, loc="lower center", ncol=min(len(handles), 6),
               fontsize=8, frameon=True, bbox_to_anchor=(0.5, -0.02))
    fig.suptitle("Profiler fidelity and sample density versus sampling cadence\n"
                 "shaded band = ±10% fidelity", fontsize=11)
    fig.tight_layout(rect=(0, 0.045, 1, 0.985))
    save(fig, out, "F8-cadence-fidelity")


def fig_sensitivity(fid, cls, med, variants, workloads, fine, out):
    # rows = metrics that have a reading (non-near-zero) in any (w,v); value = max|Δref|%
    cols = [(w, v) for w in workloads for v in variants]
    rows = [m for m in ORDER
            if any(abs(med.get((v, w, m), {}).get(fine, 0)) >= FLOOR for (w, v) in cols)]
    M = np.full((len(rows), len(cols)), np.nan)
    for ri, m in enumerate(rows):
        for ci, (w, v) in enumerate(cols):
            if abs(med.get((v, w, m), {}).get(fine, 0)) < FLOOR:
                continue
            vals = [abs(d) for d in fid.get((v, w, m), {}).values()]
            M[ri, ci] = max(vals) if vals else 0.0

    fig, ax = plt.subplots(figsize=(1.4 * len(cols) + 2.5, 0.42 * len(rows) + 2))
    im = ax.imshow(M, aspect="auto", cmap="YlOrRd", vmin=0, vmax=100)
    ax.set_xticks(range(len(cols)))
    ax.set_xticklabels([f"{w.replace('_',' ')}\n{v}" for (w, v) in cols], fontsize=8)
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([f"{m} ({cls.get(m,'?')})" for m in rows], fontsize=8)
    for ri in range(len(rows)):
        for ci in range(len(cols)):
            if not np.isnan(M[ri, ci]):
                v = M[ri, ci]
                ax.text(ci, ri, f"{v:.0f}", ha="center", va="center", fontsize=7,
                        color="white" if v > 55 else "black")
    cb = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cb.set_label("max |Δref| vs 0.1s (%)", fontsize=8)
    ax.set_title("Which metrics need fine sampling\n"
                 "largest fidelity loss per metric relative to the finest cadence\n"
                 "(hot = degrades quickly as sampling coarsens; blank = metric near zero)",
                 fontsize=10)
    fig.tight_layout()
    save(fig, out, "F8-cadence-sensitivity")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("tsv", nargs="?", type=Path,
                    default="results/p2-cadence-sweep/cadence-fidelity.tsv")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    fid, dens, cls, med = load(args.tsv)
    variants = sorted({v for (v, _, _) in fid})
    workloads = sorted({w for (_, w, _) in fid})
    fine = min((iv for d in med.values() for iv in d), default=0.1)
    out = args.out or Path("results/figures/p2-cadence-sweep")
    out.mkdir(parents=True, exist_ok=True)
    fig_fidelity(fid, dens, cls, med, variants, workloads, fine, out)
    fig_sensitivity(fid, cls, med, variants, workloads, fine, out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

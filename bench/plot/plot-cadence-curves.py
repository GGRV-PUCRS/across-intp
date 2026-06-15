#!/usr/bin/env python3
"""plot-cadence-curves.py — F8: fidelity & sample-density vs sampling cadence.

Consumes the analyzer TSV (bench/analyze-cadence.py --tsv, default
<sweep>/cadence-fidelity.tsv), NOT raw captures. Renders, per workload:

  * left/middle panels — Δref(%) vs sampling interval (log-x): the relative
    deviation of each metric's median from the finest-cadence (0.1s) reference.
    A metric whose curve leaves the shaded ±10% fidelity band as the interval
    coarsens "needs fine sampling" — that exit point is the cadence knee. Only
    metrics with a meaningful response (max|Δref| >= THRESH) are drawn; the rest
    are cadence-robust and listed in the caption. v2.1 solid / v3.3 dashed.
  * right panel — sample density (rows/rep) vs interval, log-log (the ~1/interval
    relationship that sets the floor on what fine cadence costs).

    python3 bench/plot/plot-cadence-curves.py [tsv] [--out DIR]
"""
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

THRESH = 0.05          # min max|Δref| for a metric to be drawn (else "robust")
BAND = 0.10            # ±10% fidelity tolerance band
FLOOR = 2.0            # skip near-zero metrics (relative Δref is meaningless there)
# stable per-metric colors (the cadence-sensitive ones); others cycle
METRIC_COLOR = {
    "psp": "#d62728", "schedlat": "#9467bd", "llcocc": "#ff7f0e",
    "llcmr": "#8c564b", "membw_est": "#1f77b4", "mbw": "#2ca02c", "cpu": "#000000",
}


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
                dens[(v, w)][iv] = float(r["median"])
                continue
            cls[m] = r["class"]
            med[(v, w, m)][iv] = float(r["median"])
            if r["dref"] != "":
                fid[(v, w, m)][iv] = float(r["dref"]) * 100.0  # -> %
    return fid, dens, cls, med


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("tsv", nargs="?", default="results/p2-cadence-sweep/cadence-fidelity.tsv",
                    type=Path)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    fid, dens, cls, med = load(args.tsv)

    variants = sorted({v for (v, _, _) in fid})
    workloads = sorted({w for (_, w, _) in fid})
    fine = min((iv for d in med.values() for iv in d), default=0.1)  # finest cadence
    out = args.out or Path("results/figures/p2-cadence-sweep")
    out.mkdir(parents=True, exist_ok=True)

    ncol = len(workloads) + 1
    fig, axes = plt.subplots(1, ncol, figsize=(5.0 * ncol, 4.2))
    style = {variants[0]: "-"}
    if len(variants) > 1:
        style[variants[1]] = "--"

    candidates, drawn_any = set(), set()   # metrics with Δref data; those drawn in >=1 panel
    for wi, w in enumerate(workloads):
        ax = axes[wi]
        ax.axhspan(-BAND * 100, BAND * 100, color="green", alpha=0.08, zorder=0)
        ax.axhline(0, color="grey", lw=0.6, zorder=1)
        # which metrics respond for this workload (across variants)
        mets = sorted({m for (v, ww, m) in fid if ww == w})
        drawn = []
        for m in mets:
            ref_mag = max((abs(med.get((v, w, m), {}).get(fine, 0)) for v in variants), default=0)
            if ref_mag < FLOOR:
                continue  # near-zero metric: relative Δref is noise, not signal
            candidates.add(m)
            maxd = max((abs(d) for v in variants for d in fid.get((v, w, m), {}).values()), default=0)
            if maxd < THRESH * 100:
                continue
            drawn.append(m); drawn_any.add(m)
            for v in variants:
                series = fid.get((v, w, m), {})
                if not series:
                    continue
                xs = sorted(series)
                ys = [series[x] for x in xs]
                ax.plot(xs, ys, style.get(v, "-"), marker="o", ms=3,
                        color=METRIC_COLOR.get(m, None),
                        label=f"{m} ({cls.get(m,'?')})" if v == variants[0] else None)
        ax.set_xscale("log")
        ax.set_xticks([0.1, 0.25, 0.5, 1, 2, 5])
        ax.set_xticklabels(["0.1", "0.25", "0.5", "1", "2", "5"], fontsize=8)
        ax.set_xlabel("sampling interval (s)")
        ax.set_ylabel("Δref from 0.1s (%)" if wi == 0 else "")
        ax.set_title(w.replace("_", " "), fontsize=10)
        if drawn:
            ax.legend(fontsize=7, loc="lower left", framealpha=0.9)
        ax.grid(True, which="both", ls=":", alpha=0.3)

    # density panel
    axd = axes[-1]
    for (v, w), d in sorted(dens.items()):
        xs = sorted(d)
        ys = [d[x] for x in xs]
        axd.plot(xs, ys, style.get(v, "-"), marker="s", ms=3,
                 label=f"{v} — {w.replace('_',' ')}")
    axd.set_xscale("log"); axd.set_yscale("log")
    axd.set_xticks([0.1, 0.25, 0.5, 1, 2, 5])
    axd.set_xticklabels(["0.1", "0.25", "0.5", "1", "2", "5"], fontsize=8)
    axd.set_xlabel("sampling interval (s)")
    axd.set_ylabel("sample density (rows/rep)")
    axd.set_title("sample density", fontsize=10)
    axd.legend(fontsize=7, loc="upper right", framealpha=0.9)
    axd.grid(True, which="both", ls=":", alpha=0.3)

    fig.suptitle("F8 — profiler fidelity & sample density vs sampling cadence "
                 "(1/3 footprint; shaded = ±10% fidelity band; v2.1 solid / v3.3 dashed)",
                 fontsize=11)
    robust = sorted(candidates - drawn_any)   # below threshold in EVERY workload
    cap = ("Cadence-robust metrics (max|Δref|<5% in all workloads, omitted from the Δref panels): "
           + ", ".join(robust)) if robust else ""
    if cap:
        fig.text(0.5, 0.005, cap, ha="center", fontsize=7, color="#444")
    fig.tight_layout(rect=(0, 0.03, 1, 0.95))
    dest = out / "F8-cadence-fidelity.png"
    fig.savefig(dest, dpi=140)
    print(f"wrote {dest}")
    print(f"drawn metrics per workload; robust (omitted): {sorted(robust)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

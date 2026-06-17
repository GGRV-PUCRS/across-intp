#!/usr/bin/env python3
"""plot-iada-tier-table.py — F13 headline table with descriptive (non-jargon)
labels, screenshot-ready (PNG + PDF). Consumes the within-env CV results
(bench/iada/scripts/eval-tiers.R → tier-eval.tsv).

    python3 bench/plot/plot-iada-tier-table.py [tier-eval.tsv] [--out DIR]
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

TIER_DESC = {
    "T1": "Canonical 7-metric\n(RDT — IADA baseline)",
    "A":  "Proxy-swap\n(portable mem proxy)",
    "B":  "Full 15-metric\n(+ regime class)",
}
TIER_ORDER = ["T1", "A", "B"]
ENV_ORDER = ["host", "vm"]
ENV_DESC = {"host": "Host\n(bare + container)", "vm": "Virtual machine\n(KVM guest)"}


def load(tsv: Path):
    v = {}            # (tier, env, metric) -> value
    for r in csv.DictReader(tsv.open(), delimiter="\t"):
        if r["metric"] in ("accuracy", "macro_f1"):
            v[(r["tier"], r["env"], r["metric"])] = float(r["value"])
    return v


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("tsv", nargs="?", type=Path,
                    default="results/iada-trainsets/tier-eval.tsv")
    ap.add_argument("--out", type=Path, default="results/figures/p2-iada-tiers")
    args = ap.parse_args()
    v = load(args.tsv)
    args.out.mkdir(parents=True, exist_ok=True)

    col_labels = ["Interference-classifier\nmetric set"]
    for env in ENV_ORDER:
        col_labels += [f"{ENV_DESC[env]}\n— Accuracy —",
                       f"{ENV_DESC[env]}\n— Macro-F1 —"]
    cells, row_labels = [], []
    for t in TIER_ORDER:
        row_labels.append(TIER_DESC[t])
        row = [""]
        for env in ENV_ORDER:
            acc = v.get((t, env, "accuracy")); f1 = v.get((t, env, "macro_f1"))
            row += [f"{acc:.3f}" if acc is not None else "—",
                    f"{f1:.3f}" if f1 is not None else "—"]
        cells.append(row)

    fig, ax = plt.subplots(figsize=(12.5, 3.6))
    ax.axis("off")
    tbl = ax.table(cellText=[[r[0]] + r[1:] for r in cells],
                   rowLabels=None, colWidths=[0.30, 0.175, 0.175, 0.175, 0.175],
                   colLabels=col_labels, cellLoc="center", loc="center")
    # put the tier description in the first column (rowLabels render awkwardly)
    for i, t in enumerate(TIER_ORDER):
        tbl[(i + 1, 0)].get_text().set_text(TIER_DESC[t])
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(10)
    tbl.scale(1, 2.6)
    # style: header row bold, first column left-ish, shade best row (B)
    for (r, c), cell in tbl.get_celld().items():
        if r == 0:
            cell.set_facecolor("#2c3e50"); cell.get_text().set_color("white")
            cell.get_text().set_fontweight("bold"); cell.set_height(0.30)
        elif c == 0:
            cell.get_text().set_fontweight("bold"); cell.set_facecolor("#f2f4f6")
        if r == 3:                       # the full-15 tier
            if c != 0:
                cell.set_facecolor("#e8f5e9")
    fig.suptitle("IADA interference-classifier portability across deployments\n"
                 "(within-deployment 5-fold cross-validation; identical SVM per tier)",
                 fontsize=13, fontweight="bold", y=1.02)
    fig.text(0.5, -0.06,
             "Resource-class identification stays near-perfect for every metric set in "
             "both deployments — including inside the VM, where the\nRDT memory/cache "
             "metrics are unavailable. The cross-deployment gap is therefore not in "
             "classifying the workload, but in estimating the\ninterference severity "
             "(degradation level) that drives scheduling — which the canonical set "
             "cannot read in the VM and the portable metrics restore.",
             ha="center", va="top", fontsize=9, style="italic", wrap=True)
    for ext in ("png", "pdf"):
        fig.savefig(args.out / f"F13-tier-portability-table.{ext}", dpi=150,
                    bbox_inches="tight")
    print(f"wrote {args.out}/F13-tier-portability-table.png + .pdf")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

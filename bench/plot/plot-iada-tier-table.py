#!/usr/bin/env python3
"""plot-iada-tier-table.py — F13 headline table with descriptive (non-jargon)
labels, screenshot-ready (PNG + PDF). Consumes the within-env CV results
(bench/iada/scripts/eval-tiers.R → tier-eval.tsv).

    python3 bench/plot/plot-iada-tier-table.py [tier-eval.tsv] [--out DIR]
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parent))
import p2_figio  # noqa: E402  (shared {png,pdf} output layout)

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


def load_transfer(tsv: Path):
    v = {}            # (tier, metric, class) -> value
    for r in csv.DictReader(tsv.open(), delimiter="\t"):
        v[(r["tier"], r["metric"], r["class"])] = float(r["value"])
    return v


def render_transfer(tsv: Path, out: Path):
    v = load_transfer(tsv)
    col_labels = ["Interference-classifier\nmetric set",
                  "VM classification\naccuracy", "VM\nMacro-F1",
                  "Memory-class\nrecall in VM"]
    cells = []
    for t in TIER_ORDER:
        cells.append([TIER_DESC[t],
                      f"{v.get((t,'accuracy','-'),float('nan')):.3f}",
                      f"{v.get((t,'macro_f1','-'),float('nan')):.3f}",
                      f"{v.get((t,'recall','mem'),float('nan')):.2f}"])
    fig, ax = plt.subplots(figsize=(11, 3.4)); ax.axis("off")
    tbl = ax.table(cellText=cells, colWidths=[0.34, 0.22, 0.22, 0.22],
                   colLabels=col_labels, cellLoc="center", loc="center")
    tbl.auto_set_font_size(False); tbl.set_fontsize(11); tbl.scale(1, 2.8)
    for (r, c), cell in tbl.get_celld().items():
        if r == 0:
            cell.set_facecolor("#2c3e50"); cell.get_text().set_color("white")
            cell.get_text().set_fontweight("bold"); cell.set_height(0.26)
        elif c == 0:
            cell.get_text().set_fontweight("bold"); cell.set_facecolor("#f2f4f6")
        if r == 3 and c != 0:
            cell.set_facecolor("#e8f5e9")          # full-15 row
        if r in (1, 2) and c != 0:
            cell.set_facecolor("#fdecea")          # canonical / proxy-swap rows
    fig.suptitle("Applying a HOST-trained interference classifier directly inside the VM\n"
                 "(cross-deployment transfer, no per-domain retraining)",
                 fontsize=13, fontweight="bold", y=1.04)
    fig.text(0.5, -0.10,
             "When the classifier is moved across the deployment boundary without retraining, only the full 15-metric set "
             "transfers:\nit keeps 78% accuracy and recovers the memory class perfectly (1.00), while the canonical 7-metric "
             "set collapses to 51%\n(memory recall 0.41) because its RDT memory/cache inputs read zero in the VM. The naive "
             "proxy-swap is worse (43%) — the\nmemory proxy's absolute value is ~10x larger in the VM than on the host, so the "
             "host-trained boundary misreads it. Takeaway:\nthe richer portable set is what survives a deployment change; a "
             "single substituted metric is not enough.",
             ha="center", va="top", fontsize=9, style="italic")
    p2_figio.save(fig, out, "F13-tier-transfer-table", dpi=150)
    print(p2_figio.describe(out, "F13-tier-transfer-table"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("tsv", nargs="?", type=Path,
                    default="results/iada-trainsets/tier-eval.tsv")
    ap.add_argument("--out", type=Path, default="results/figures/p2-iada-tiers")
    ap.add_argument("--transfer", action="store_true",
                    help="render the host->VM transfer table from tier-eval-transfer.tsv")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    if args.transfer:
        t = args.tsv if "transfer" in str(args.tsv) else \
            Path(str(args.tsv).replace(".tsv", "-transfer.tsv"))
        render_transfer(t, args.out)
        return 0
    v = load(args.tsv)

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
    p2_figio.save(fig, args.out, "F13-tier-portability-table", dpi=150)
    print(p2_figio.describe(args.out, "F13-tier-portability-table"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

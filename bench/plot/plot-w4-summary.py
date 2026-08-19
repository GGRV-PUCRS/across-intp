#!/usr/bin/env python3
"""plot-w4-summary.py — w4-summary: the W4 faithfulness headline in two panels.

Consumes the adjudicated W4 report (default docs/reports/W4-faithfulness-r2.md),
the source of record for the campaign's verdicts: bench/analyze-faithfulness.py
emits the adjudication as a markdown report (there is no verdict TSV), so this
renderer parses the adjudicated numbers straight out of the committed report:

  w4-summary — left: the cpu profiler/GT ratios of every FAITHFUL cell (both
      variants) rendered as the observed-ratio band around the 1.0 parity
      line, with the faithful/adjudicable cell count from the report's CPU
      summary; right: the directional llcmr Spearman rho per variant, the
      load-bearing faithfulness measure of report section 1b.

Emits png + pdf under results/figures/w4-faithfulness/ (p2_figio layout).
The stem is deliberately not an F-number: the figure was produced for the
Seminario de Andamento document (fig/w4-summary), not for the P2 paper set.

The regexes track the markdown format emitted by analyze-faithfulness.py; if
the analyzer's report format changes, update them here.

    python3 bench/plot/plot-w4-summary.py [W4-faithfulness-r2.md] [--out DIR]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parent))
import p2_figio  # noqa: E402  (shared {png,pdf} output layout)

VARIANT_LABELS = {"v2.1": "C-ABI v2.1", "v3.3": "eBPF-CORE v3.3"}
BAR_COLOR = {"v2.1": "#8aa9cf", "v3.3": "#2e5d8c"}
BAND_COLOR = "#b7dfb7"


def parse(report: Path):
    """Extract the adjudicated numbers from the W4 report markdown."""
    text = report.read_text()

    # Section 1 rows carry "| ... | FAITHFUL (1.02) [cliff=...] | ..." verdicts.
    cpu_ratios = [float(m) for m in
                  re.findall(r"FAITHFUL \((\d+\.\d+)\)", text)]
    if not cpu_ratios:
        sys.exit("no FAITHFUL (ratio) cells found in report")

    # CPU summary lines: "- v2.1: 20 faithful, 0 under, 0 over"
    cells = {}
    for m in re.finditer(
            r"- (v[\d.]+): (\d+) faithful, (\d+) under, (\d+) over", text):
        f, u, o = int(m.group(2)), int(m.group(3)), int(m.group(4))
        cells[m.group(1)] = (f, f + u + o)
    if cells and len({total for _, total in cells.values()}) != 1:
        sys.exit(f"per-variant adjudicable cell counts disagree: {cells}")

    # Spearman lines: "- v2.1: rho=0.66 (p=3.2e-04, n=25 cells)"
    rho, pval = {}, {}
    for m in re.finditer(r"- (v[\d.]+): rho=([\d.]+) \(p=([\deE.+-]+)", text):
        rho[m.group(1)] = float(m.group(2))
        pval[m.group(1)] = float(m.group(3))
    if len(rho) != 2:
        sys.exit(f"expected 2 Spearman lines, got {len(rho)}")
    return cpu_ratios, cells, rho, pval


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("report", type=Path, nargs="?",
                    default="docs/reports/W4-faithfulness-r2.md")
    ap.add_argument("--out", type=Path,
                    default=Path("results/figures/w4-faithfulness"))
    args = ap.parse_args()

    ratios, cells, rho, pval = parse(args.report)
    lo, hi = min(ratios), max(ratios)
    variants = sorted(rho)
    faithful, total = cells[variants[0]] if cells else \
        (len(ratios) // 2, len(ratios) // 2)
    pmax = max(pval.values())
    ptext = "p < 0.001" if pmax < 0.001 else f"p = {pmax:.1e}"
    print(f"cpu ratios: n={len(ratios)} min={lo:.2f} max={hi:.2f} "
          f"cells={faithful}/{total}")
    print(f"spearman  : {rho} ({ptext})")

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(7.2, 2.3))

    # Left: cpu absolute faithfulness band
    ax1.axhspan(lo, hi, color=BAND_COLOR, alpha=0.55,
                label="observed ratio range")
    ax1.axhline(1.0, ls="--", lw=1.0, color="black")
    ax1.set_ylim(0.80, 1.10)
    ax1.set_yticks([0.8, 0.9, 1.0, 1.1])
    ax1.set_xticks([])
    ax1.set_ylabel("profiler / ground truth")
    ax1.set_title(f"cpu: absolute faithfulness\n"
                  f"({faithful}/{total} env x variant cells)", fontsize=9)
    ax1.legend(loc="lower right", fontsize=8, framealpha=0.9)

    # Right: llcmr directional faithfulness
    xs = range(len(variants))
    vals = [rho[v] for v in variants]
    ax2.bar(xs, vals, width=0.55, edgecolor="black", lw=0.6,
            color=[BAR_COLOR[v] for v in variants])
    for x, v in zip(xs, vals):
        ax2.text(x, v + 0.02, f"{v:.2f}", ha="center", fontsize=9)
    ax2.set_xticks(list(xs))
    ax2.set_xticklabels([VARIANT_LABELS.get(v, v) for v in variants],
                        fontsize=9)
    ax2.set_ylim(0.0, 1.0)
    ax2.set_ylabel(r"Spearman $\rho$ vs. ground truth")
    ax2.set_title(f"llcmr: directional faithfulness\n({ptext})", fontsize=9)

    fig.tight_layout()
    args.out.mkdir(parents=True, exist_ok=True)
    p2_figio.save(fig, args.out, "w4-summary", dpi=160)
    print(p2_figio.describe(args.out, "w4-summary"))
    return 0


if __name__ == "__main__":
    sys.exit(main())

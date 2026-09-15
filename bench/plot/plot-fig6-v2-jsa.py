#!/usr/bin/env python3
"""plot-fig6-v2-jsa.py -- Figure_6_v2.pdf: the brief's additive two-panel
merge of fig:w4ratio (Figure_6) + fig:w4faith (Figure_7), suggested label
fig:w4combined. Standalone option only: main-jsa.tex is NOT repointed; the
standalone Figure_6.pdf / Figure_7.pdf stay as they are.

Top row: the per-workload ratio-vs-bare strip, drawn by the same code path
as plot-fig2-3-4-6-8-jsa.py's fig_ratio (same cross-deployment.tsv, same
corridor, same markers -- imported, not copied, so the numbers cannot drift).
Bottom row: the W4 faithfulness summary (observed-ratio band + per-variant
llcmr Spearman rho bars) parsed from the adjudicated
results/_final/reports/W4-faithfulness-r2.md by plot-w4-summary.py's own
parse() (imported via importlib; that filename is not a valid module name).

    python3 bench/plot/plot-fig6-v2-jsa.py results/p2-15metric-xdeploy-1of3 \
        --out /mnt/c/Users/sacil/Downloads/figs
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jsa_style as style  # noqa: E402

_PLOT_DIR = Path(__file__).resolve().parent


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ratio_mod = _load_module("plot_fig23468_jsa",
                         _PLOT_DIR / "plot-fig2-3-4-6-8-jsa.py")
w4_mod = _load_module("plot_w4_summary",
                      _PLOT_DIR / "plot-w4-summary.py")

ENV_ORDER = ratio_mod.ENV_ORDER
ENV_SHORT = ratio_mod.ENV_SHORT


def draw_ratio_row(fig, subgrid, d: pd.DataFrame) -> None:
    """fig_ratio's panels, drawn into a row of the merged figure.

    Identical marks to the standalone Figure_6: same corridor span, same
    per-env errorbars, same axis ranges. Only the titles gain a panel tag
    and the shared env legend moves to the figure bottom (below both rows).
    """
    metrics = sorted(d.metric.unique())
    variants = sorted(d.variant.unique())
    axes = fig.add_subplot(subgrid)  # placeholder, replaced below
    axes.remove()
    sub = subgrid.subgridspec(1, len(metrics) * len(variants), wspace=0.08)
    axs = [fig.add_subplot(sub[0, i]) for i in range(len(metrics) * len(variants))]
    env_markers = {"container": "o", "container-podman": "s",
                   "container-lxc": "^", "container-k8s": "D",
                   "vm-guest": "P"}
    col = 0
    for m in metrics:
        for var in variants:
            ax = axs[col]
            col += 1
            s0 = d[(d.variant == var) & (d.metric == m)]
            wls = sorted(s0.workload.unique())
            ax.axhspan(0.8, 1.25, color=style.BLUISH_GREEN, alpha=0.14,
                       zorder=0)
            ax.axhline(1.0, color="k", lw=0.6, ls=":", zorder=1)
            for i, env in enumerate(ENV_ORDER):
                s = s0[s0.env == env].set_index("workload").reindex(wls)
                x = np.arange(len(wls)) + (i - 2) * 0.14
                lo = np.clip(s.ratio - s.ci_lo, 0, None)
                hi = np.clip(s.ci_hi - s.ratio, 0, None)
                ax.errorbar(x, s.ratio, yerr=[lo.fillna(0), hi.fillna(0)],
                            fmt=env_markers.get(env, "o"), ms=4,
                            color=style.OKABE_ITO[i % len(style.OKABE_ITO)],
                            capsize=2, label=ENV_SHORT[env], zorder=2)
            ax.text(0.02, 1.245, "0.8–1.25× equivalence corridor",
                    transform=ax.get_yaxis_transform(),
                    fontsize=style.ANNOT - 0.5, color="#2f6b4f",
                    ha="left", va="top")
            ax.set_xticks(range(len(wls)))
            ax.set_xticklabels([w.split("_")[0] for w in wls],
                               fontsize=style.ANNOT, rotation=30, ha="right")
            ax.set_ylim(0, 3.6)
            ax.set_title(f"{ratio_mod.vlabel(var)}\n{m}",
                         fontsize=style.TITLE)
            if col == 1:
                ax.set_ylabel("ratio vs bare metal")
    return axs


def draw_faith_row(fig, subgrid, ratios, rho) -> None:
    """plot-w4-summary's SA cut, re-geometryed to jsa_style: band + bars."""
    sub = subgrid.subgridspec(1, 2, width_ratios=[0.62, 1.0], wspace=0.25)
    ax1 = fig.add_subplot(sub[0, 0])
    ax2 = fig.add_subplot(sub[0, 1])

    lo, hi = min(ratios), max(ratios)
    ax1.axhspan(lo, hi, color=w4_mod.BAND_COLOR, alpha=0.55,
                label="observed ratio range")
    ax1.axhline(1.0, ls="--", lw=1.0, color="black")
    ax1.set_ylim(0.80, 1.10)
    ax1.set_yticks([0.8, 0.9, 1.0, 1.1])
    ax1.set_xticks([])
    ax1.set_ylabel("profiler / ground truth")
    ax1.legend(loc="lower right", fontsize=style.LEGEND, framealpha=0.9,
               handlelength=1.2)

    variants = sorted(rho)
    vals = [rho[v] for v in variants]
    xs = range(len(variants))
    ax2.bar(xs, vals, width=0.55, edgecolor="black", lw=0.6,
            color=[w4_mod.BAR_COLOR[v] for v in variants])
    for x, v in zip(xs, vals):
        ax2.text(x, v + 0.02, f"{v:.2f}", ha="center", fontsize=style.BODY)
    ax2.set_xticks(list(xs))
    ax2.set_xticklabels([w4_mod.VARIANT_LABELS.get(v, v) for v in variants],
                        rotation=20, ha="right", rotation_mode="anchor",
                        fontsize=style.BODY)
    ax2.set_ylim(0.0, 1.0)
    ax2.set_ylabel(r"Spearman $\rho$ vs. ground truth")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("campaign_dir", type=Path)
    ap.add_argument("--report", type=Path,
                    default=Path("results/_final/reports/W4-faithfulness-r2.md"))
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    style.apply()
    args.out.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(args.campaign_dir / "cross-deployment.tsv", sep="\t")
    for c in ("ratio", "ci_lo", "ci_hi", "cliffs_delta"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    d = df[df.claim_class == "absolute"].copy()

    ratios, cells, rho, pval = w4_mod.parse(args.report)

    width = style.TEXT_WIDTH
    height = 5.1
    fig = plt.figure(figsize=(width, height))
    grid = fig.add_gridspec(2, 1, height_ratios=[1.0, 0.72],
                            hspace=0.55, left=0.055, right=0.995,
                            top=0.93, bottom=0.16)

    axs = draw_ratio_row(fig, grid[0], d)
    draw_faith_row(fig, grid[1], ratios, rho)

    axs[0].text(-0.10, 1.02, "(a)", transform=axs[0].transAxes,
                fontsize=style.TITLE, fontweight="bold", va="bottom",
                ha="left")
    fig.text(0.055, 0.42, "(b)", fontsize=style.TITLE, fontweight="bold",
             va="bottom", ha="left")

    handles, labels = axs[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center",
               ncol=len(ENV_ORDER), fontsize=style.LEGEND, frameon=False,
               handlelength=1.2, bbox_to_anchor=(0.5, 0.0))

    spec = style.FigSpec(width, height, "fig:w4combined")
    w, h = style.save(fig, args.out / "Figure_6_v2.pdf", spec)
    plt.close(fig)
    print(f"wrote {args.out / 'Figure_6_v2.pdf'} ({w:.2f} x {h:.2f} in)")
    print(f"  faith cells {cells}, rho {rho}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

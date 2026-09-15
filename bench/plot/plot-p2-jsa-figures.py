#!/usr/bin/env python3
"""plot-p2-jsa-figures.py -- JSA print redraws of six P2-15metric figures.

Reuses the data-loading/scanning functions from plot-p2-15metric.py (via
importlib, since that module's filename is not a valid identifier) so the
underlying numbers are computed exactly once, by the same code the
exploratory PNG/PDF set uses. Only presentation changes here: layout,
sizing, annotations, colorblind-safe palette, per jsa_style.py and the
JSA figure-improvement brief.

Figures (all from campaign p2-15metric-xdeploy-1of3):
  Figure_2.pdf   fig:availability  -- bigger cells, rotated env labels,
                                       side legend spelling out metric names
  Figure_8.pdf   fig:claimclass    -- + shading-intensity (significance) legend
  Figure_3.pdf   fig:psi           -- two-panel membw_est/psi_mem, saturation
                                       callout
  Figure_4.pdf   fig:membwproxy    -- rho in-plot, estimator-formula
                                       reference line, marker+color per variant
  Figure_6.pdf   fig:w4ratio       -- equivalence corridor labeled in-plot
  Figure_14.pdf  fig:preempt       -- (renamed from the F6-involuntary-...
                                       internal-label filename) grouped
                                       bar chart, log y, replacing the
                                       Cliff's-delta-only heatmap so the raw
                                       33,008-420,922 events/s range on
                                       app11_sort_net is readable

Usage:
    python3 plot-p2-jsa-figures.py <campaign_dir> --out DIR
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

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import jsa_style as style  # noqa: E402

try:
    from scipy.stats import spearmanr
except ImportError:
    spearmanr = None

# ---- import plot-p2-15metric.py (hyphenated filename) ---------------------
_spec = importlib.util.spec_from_file_location(
    "p2_15metric", HERE / "plot-p2-15metric.py")
p2 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(p2)

ENV_ORDER = p2.ENV_ORDER
ENV_SHORT = p2.ENV_SHORT
METRICS_PORTABLE = p2.METRICS_PORTABLE
METRICS_REGIME = p2.METRICS_REGIME
vlabel = p2.vlabel
cell_median = p2.cell_median
load_capture = p2.load_capture
gt_llc_miss = p2.gt_llc_miss

METRIC_FULLNAME = {
    "netp": "NIC utilization",
    "nets": "network stack service time",
    "blk": "block device busy %",
    "mbw": "LLC-DRAM bandwidth (RDT)",
    "llcmr": "LLC miss ratio (RDT)",
    "llcocc": "LLC occupancy (RDT)",
    "cpu": "CPU user + system %",
    "schedlat": "run-queue latency",
    "psi_mem": "PSI memory pressure",
    "membw_est": "est. DRAM bandwidth",
    "psi_io": "PSI I/O pressure",
    "schedthr": "CFS throttling (guard)",
    "steal": "hypervisor steal (guard)",
    "psp": "preemptions per second",
    "idle_preempt": "idle-task preemptions (eBPF)",
}

ENV_COLOR = {
    "bare": style.BLACK,
    "container": style.BLUE,
    "container-podman": style.SKY_BLUE,
    "container-lxc": style.BLUISH_GREEN,
    "container-k8s": style.ORANGE,
    "vm-guest": style.VERMILLION,
}


# ── Figure_2: availability grid ─────────────────────────────────────────────

def fig_availability(cells, out: Path):
    metrics = METRICS_PORTABLE + METRICS_REGIME + ["mbw", "llcocc", "llcmr"]
    variants = sorted({k[1] for k in cells})
    envs = ["bare"] + ENV_ORDER
    OK, GONE = style.BLUISH_GREEN, style.GREY

    fig = plt.figure(figsize=(style.TEXT_WIDTH - 0.45, 3.55))
    gs = fig.add_gridspec(1, len(variants) + 1,
                           width_ratios=[2.5, 2.5, 2.55], wspace=0.30,
                           left=0.095, right=0.98, top=0.90, bottom=0.20)
    axes = [fig.add_subplot(gs[0, c]) for c in range(len(variants))]

    for ax, var in zip(axes, variants):
        for yi, env in enumerate(envs):
            reps = [r for (e, v, _w), rl in cells.items()
                    if e == env and v == var for r in rl]
            for xi, m in enumerate(metrics):
                ok = any(m in r for r in reps)
                ax.add_patch(plt.Rectangle((xi, yi), 0.92, 0.92,
                                            color=OK if ok else GONE))
        ax.set_xlim(0, len(metrics))
        ax.set_ylim(0, len(envs))
        ax.set_xticks(np.arange(len(metrics)) + 0.46)
        ax.set_xticklabels(metrics, rotation=40, ha="right",
                            rotation_mode="anchor", fontsize=style.BODY - 0.5)
        ax.set_yticks(np.arange(len(envs)) + 0.46)
        ax.set_yticklabels([ENV_SHORT[e] for e in envs], fontsize=style.BODY)
        ax.tick_params(length=0)
        ax.invert_yaxis()
        ax.axvline(len(METRICS_PORTABLE) + len(METRICS_REGIME),
                   color="k", lw=1.0)
        ax.set_title(vlabel(var), fontsize=style.TITLE)
        ax.grid(False)

    # side legend: metric code -> full name (code column right-aligned so
    # the description column starts at a fixed offset regardless of code
    # length -- "idle_preempt" is the longest and sets the split)
    lax = fig.add_subplot(gs[0, 2])
    lax.axis("off")
    handles = [plt.Rectangle((0, 0), 1, 1, color=OK),
               plt.Rectangle((0, 0), 1, 1, color=GONE)]
    lax.legend(handles, ["available", "unavailable"], loc="upper left",
               ncol=1, frameon=False, fontsize=style.LEGEND,
               bbox_to_anchor=(-0.02, 1.06), handlelength=1.1,
               handletextpad=0.4, borderaxespad=0.0)
    for i, m in enumerate(metrics):
        y = 0.78 - (i + 0.5) / len(metrics) * 0.78
        lax.text(0.50, y, m, fontsize=style.ANNOT - 0.5, family="monospace",
                  va="center", ha="right", transform=lax.transAxes)
        lax.text(0.56, y, METRIC_FULLNAME[m], fontsize=style.ANNOT - 0.5,
                  va="center", ha="left", transform=lax.transAxes)

    style.save(fig, out / "Figure_2.pdf",
               style.FigSpec(style.TEXT_WIDTH, 3.55, "fig:availability"))
    plt.close(fig)


# ── Figure_8: claim-class matrix ────────────────────────────────────────────

def fig_claimclass(df: pd.DataFrame, out: Path):
    variants = sorted(df.variant.unique())
    cls_color = {"absolute": style.BLUE, "directional": style.ORANGE,
                 "descriptive": style.GREY}
    all_metrics = sorted(df.metric.unique())
    fig, axes = plt.subplots(1, len(variants),
                              figsize=(style.TEXT_WIDTH, 4.6), squeeze=False)
    for c, var in enumerate(variants):
        ax = axes[0][c]
        sub = df[df.variant == var]
        for yi, m in enumerate(all_metrics):
            for xi, env in enumerate(ENV_ORDER):
                s = sub[(sub.metric == m) & (sub.env == env)]
                if s.empty:
                    continue
                cls = s.claim_class.iloc[0]
                best = max((p2.SIG_ORDER.get(x, 0) for x in s.signif),
                           default=0)
                ax.add_patch(plt.Rectangle(
                    (xi, yi), 0.94, 0.94,
                    color=cls_color.get(cls, "#eeeeee"),
                    alpha=0.30 + 0.23 * min(best, 3)))
        ax.set_xlim(0, len(ENV_ORDER))
        ax.set_ylim(0, len(all_metrics))
        ax.set_xticks(np.arange(len(ENV_ORDER)) + 0.5)
        ax.set_xticklabels([ENV_SHORT[e] for e in ENV_ORDER],
                            rotation=30, ha="right", fontsize=style.BODY)
        ax.set_yticks(np.arange(len(all_metrics)) + 0.5)
        ax.set_yticklabels(all_metrics, fontsize=style.BODY)
        ax.set_title(vlabel(var), fontsize=style.TITLE)
        ax.invert_yaxis()
        ax.grid(False)

    class_handles = [plt.Rectangle((0, 0), 1, 1, color=v, alpha=0.75)
                      for v in cls_color.values()]
    class_labels = list(cls_color.keys()) + []
    blank_handle = plt.Rectangle((0, 0), 1, 1, facecolor="white",
                                  edgecolor="#999999")
    leg1 = fig.legend(class_handles + [blank_handle],
                       class_labels + ["unavailable"],
                       loc="lower left", ncol=4, frameon=False,
                       fontsize=style.LEGEND, bbox_to_anchor=(0.02, -0.04))
    fig.add_artist(leg1)

    sig_alphas = [0.30, 0.53, 0.76, 0.99]
    sig_labels = ["n.s.", "*", "**", "***"]
    sig_handles = [plt.Rectangle((0, 0), 1, 1, color=style.BLUE, alpha=a)
                   for a in sig_alphas]
    fig.legend(sig_handles, sig_labels, loc="lower right", ncol=4,
               frameon=False, fontsize=style.LEGEND,
               title="shading = significance", title_fontsize=style.LEGEND,
               bbox_to_anchor=(0.98, -0.055))

    fig.tight_layout(rect=(0, 0.06, 1, 1))
    style.save(fig, out / "Figure_8.pdf",
               style.FigSpec(style.TEXT_WIDTH, 4.6, "fig:claimclass"))
    plt.close(fig)


# ── Figure_3: PSI falsification, two-panel ──────────────────────────────────

def fig_psi(cells, out: Path):
    variants = sorted({k[1] for k in cells})
    envs = ["bare"] + ENV_ORDER
    fig, (axl, axr) = plt.subplots(
        1, 2, figsize=(style.TEXT_WIDTH, 2.5), sharex=True)
    width = 0.38
    mb_by = {}
    for vi, var in enumerate(variants):
        mb, psi = [], []
        for env in envs:
            mb.append(cell_median(cells, env, var, "app05_streaming",
                                   "membw_est") or 0)
            psi.append(cell_median(cells, env, var, "app05_streaming",
                                    "psi_mem") or 0)
        mb_by[var] = mb
        x = np.arange(len(envs)) + (vi - 0.5) * width
        c = style.VARIANT_COLOR.get(var, style.BLUE)
        m = style.VARIANT_MARKER.get(var, "o")
        axl.bar(x, mb, width * 0.9, label=style.VARIANT_LABEL.get(var, var),
                color=c)
        # psi_mem is exactly 0 in every cell (the falsification result), so
        # a bar would be invisible; a marker on the zero line stays visible
        # and still reads as "measured 0", not "no data".
        axr.scatter(x, psi, s=16, color=c, marker=m, zorder=3)

    axl.set_yscale("log")
    axl.set_ylim(top=axl.get_ylim()[1] * 3.0)
    # matplotlib's default log-scale exponent glyph renders at ~0.7x the
    # tick label size (mathtext superscript), which would drop below the
    # 6.5 pt annotation floor (after the manuscript's 1.3x figscale) at the
    # jsa_style BODY=7pt base -- bump the base so the shrunk exponent clears.
    axl.tick_params(axis="y", labelsize=8.5)
    axl.set_ylabel("membw_est on app05_streaming\n(MB/s, log)")
    axr.axhline(0, color="#bbbbbb", lw=0.6, zorder=1)
    axr.set_ylabel("psi_mem on app05_streaming\n(share of time stalled, %)")
    axr.set_ylim(-1, 10)
    for ax in (axl, axr):
        ax.set_xticks(np.arange(len(envs)))
        ax.set_xticklabels([ENV_SHORT[e] for e in envs], fontsize=style.BODY,
                            rotation=30, ha="right")
    axl.legend(fontsize=style.LEGEND, loc="upper left")

    # saturation-point callout: the highest membw_est bar, annotated on the
    # left panel and cross-referenced on the right where psi_mem reads 0.
    best_var = max(variants, key=lambda v: max(mb_by[v]))
    best_i = int(np.argmax(mb_by[best_var]))
    best_x = best_i + (variants.index(best_var) - 0.5) * width
    axl.annotate("saturation point\n(psi_mem = 0 here)",
                 xy=(best_x, mb_by[best_var][best_i]),
                 xytext=(best_x - 2.3, mb_by[best_var][best_i] * 1.6),
                 fontsize=style.ANNOT,
                 arrowprops=dict(arrowstyle="-|>", lw=0.8,
                                  color=style.BLACK))

    style.save(fig, out / "Figure_3.pdf",
               style.FigSpec(style.TEXT_WIDTH, 3.0, "fig:psi"))
    plt.close(fig)


# ── Figure_4: membw_est validation scatter ──────────────────────────────────

def fig_membwproxy(base: Path, cells, out: Path):
    variants = sorted({k[1] for k in cells})
    fig, ax = plt.subplots(figsize=(style.COLUMN_WIDTH * 1.55, 3.3))
    all_x = []
    rho_text = []
    for var in variants:
        xs, ys = [], []
        import glob
        for f in glob.glob(str(base / "*/v*/solo/*/rep*/portable.tsv")):
            p = Path(f)
            env, v, wl = p.parts[-6], p.parts[-5], p.parts[-3]
            if v != var or env == "vm-guest":
                continue
            cap = load_capture(p)
            gt = gt_llc_miss(p.parent)
            if gt and cap.get("membw_est", 0) > 0:
                xs.append(gt)
                ys.append(cap["membw_est"])
        if not xs:
            continue
        all_x += xs
        rho = spearmanr(xs, ys)[0] if spearmanr else float("nan")
        rho_text.append(f"{style.VARIANT_LABEL.get(var, var)}: "
                         f"ρ={rho:.2f} (n={len(xs)})")
        ax.scatter(xs, ys, s=12, alpha=0.55,
                   color=style.VARIANT_COLOR.get(var, style.BLUE),
                   marker=style.VARIANT_MARKER.get(var, "o"),
                   label=style.VARIANT_LABEL.get(var, var))

    ax.set_xscale("log")
    ax.set_yscale("log")
    # See fig_psi's comment: bump the log-axis tick base so the mathtext
    # exponent glyph still clears the annotation floor after x1.3 upscale.
    ax.tick_params(axis="both", labelsize=8.5)
    if all_x:
        xr = np.array([min(all_x) * 0.7, max(all_x) * 1.4])
        # estimator formula, not a statistical fit: membw_est is defined as
        # LLC misses x 64 bytes per (1 s) interval, so this line is the
        # deterministic conversion the proxy is built from, not a trend line.
        ax.plot(xr, xr * 64.0 / 1e6, ls="--", lw=0.9, color=style.BLACK,
                label="64 B × LLC misses/s\n(estimator formula)")
    ax.set_xlabel("ground truth: LLC misses/s (host perf, rep median)")
    ax.set_ylabel("membw_est (MB/s,\nrep median)")
    ax.legend(fontsize=style.LEGEND - 0.3, loc="upper left",
              handlelength=1.3)
    ax.text(0.98, 0.04, "\n".join(rho_text), transform=ax.transAxes,
            ha="right", va="bottom", fontsize=style.ANNOT,
            bbox=dict(fc="white", ec="#cccccc", lw=0.5, pad=2.0))

    style.save(fig, out / "Figure_4.pdf",
               style.FigSpec(style.COLUMN_WIDTH * 1.55, 3.3,
                              "fig:membwproxy"))
    plt.close(fig)


# ── Figure_6: absolute ratio-vs-bare with labeled corridor ──────────────────

def fig_w4ratio(df: pd.DataFrame, out: Path):
    d = df[df.claim_class == "absolute"].copy()
    metrics = sorted(d.metric.unique())
    variants = sorted(d.variant.unique())
    fig, axes = plt.subplots(1, len(variants) * len(metrics),
                              figsize=(style.TEXT_WIDTH,
                                       2.6 if len(metrics) * len(variants) <= 2
                                       else 2.9),
                              sharey=True, squeeze=False)
    col = 0
    for m in metrics:
        for var in variants:
            ax = axes[0][col]
            col += 1
            sub = d[(d.variant == var) & (d.metric == m)]
            wls = sorted(sub.workload.unique())
            for i, env in enumerate(ENV_ORDER):
                s = sub[sub.env == env].set_index("workload").reindex(wls)
                x = np.arange(len(wls)) + (i - 2) * 0.14
                lo = np.clip(s.ratio - s.ci_lo, 0, None)
                hi = np.clip(s.ci_hi - s.ratio, 0, None)
                ax.errorbar(x, s.ratio, yerr=[lo.fillna(0), hi.fillna(0)],
                            fmt="o", ms=3.5, capsize=1.5,
                            color=ENV_COLOR[env], label=ENV_SHORT[env])
            ax.axhspan(0.8, 1.25, color=style.BLUISH_GREEN, alpha=0.14)
            ax.axhline(1.0, color="k", lw=0.7, ls=":")
            ax.text(0.03, 1.25 - 0.03, "0.8–1.25× equivalence",
                    transform=ax.get_yaxis_transform(), ha="left", va="top",
                    fontsize=style.ANNOT - 1.0, color="#2c6e49")
            ax.set_xticks(range(len(wls)))
            ax.set_xticklabels([w.split("_")[0] for w in wls],
                                fontsize=style.ANNOT, rotation=30, ha="right")
            ax.set_ylim(0, 3.8)
            ax.set_title(f"{vlabel(var)}\n{m}", fontsize=style.TITLE - 0.5)
            if col == 1:
                ax.set_ylabel("ratio vs bare")
    handles, labels = axes[0][0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=len(ENV_ORDER),
               fontsize=style.LEGEND, frameon=False,
               bbox_to_anchor=(0.5, -0.06))
    fig.tight_layout(rect=(0, 0.08, 1, 1))
    style.save(fig, out / "Figure_6.pdf",
               style.FigSpec(style.TEXT_WIDTH, 2.9, "fig:w4ratio"))
    plt.close(fig)


# ── Figure_14 (was F6-involuntary-...): psp events/s, log scale ────────────

def fig_preempt(df: pd.DataFrame, out: Path):
    d = df[df.metric == "psp"].copy()
    d["env_median"] = pd.to_numeric(d["env_median"], errors="coerce")
    d["bare_median"] = pd.to_numeric(d["bare_median"], errors="coerce")
    variants = sorted(d.variant.unique())
    fig, axes = plt.subplots(1, len(variants),
                              figsize=(style.TEXT_WIDTH, 3.3), squeeze=False,
                              sharey=True)
    bars = ["bare"] + ENV_ORDER
    for c, var in enumerate(variants):
        ax = axes[0][c]
        sub = d[d.variant == var]
        wls = sorted(sub.workload.unique())
        n = len(bars)
        w = 0.8 / n
        for i, b in enumerate(bars):
            vals, sig = [], []
            for wl in wls:
                row = sub[sub.workload == wl]
                if b == "bare":
                    vals.append(row.bare_median.iloc[0] if not row.empty
                                else np.nan)
                    sig.append(False)
                else:
                    r = row[row.env == b]
                    vals.append(r.env_median.iloc[0] if not r.empty
                                else np.nan)
                    sig.append(bool(len(r) and r.signif.iloc[0] not in
                                     ("n.s.", "n/a")))
            x = np.arange(len(wls)) + (i - (n - 1) / 2) * w
            ax.bar(x, vals, w * 0.92, color=ENV_COLOR[b],
                   label=ENV_SHORT[b] if c == 0 else None)
            for xi, (v, s) in zip(x, zip(vals, sig)):
                if s and np.isfinite(v):
                    ax.text(xi, v * 1.08, "*", ha="center", va="bottom",
                            fontsize=style.ANNOT, fontweight="bold")
        ax.set_yscale("log")
        # See fig_psi's comment: bump the log-axis tick base so the
        # mathtext exponent glyph still clears the floor after x1.3 upscale.
        ax.tick_params(axis="y", labelsize=8.5)
        ax.set_xticks(range(len(wls)))
        ax.set_xticklabels([w.split("_")[0] for w in wls],
                            fontsize=style.BODY, rotation=30, ha="right")
        ax.set_title(vlabel(var), fontsize=style.TITLE)
        if c == 0:
            ax.set_ylabel("psp: involuntary\npreemptions/s (log)")
    handles, labels = axes[0][0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=len(bars),
               fontsize=style.LEGEND, frameon=False,
               bbox_to_anchor=(0.5, -0.05),
               title="* = significant vs bare (BH-FDR)",
               title_fontsize=style.LEGEND)
    fig.tight_layout(rect=(0, 0.10, 1, 1))
    style.save(fig, out / "Figure_14.pdf",
               style.FigSpec(style.TEXT_WIDTH, 3.3, "fig:preempt"))
    plt.close(fig)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("campaign_dir", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    base = args.campaign_dir
    args.out.mkdir(parents=True, exist_ok=True)

    tsv = base / "cross-deployment.tsv"
    df = pd.read_csv(tsv, sep="\t")
    for col in ("ratio", "ci_lo", "ci_hi", "cliffs_delta"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    cells = p2.scan_cells(base)

    style.apply()
    fig_availability(cells, args.out)
    fig_claimclass(df, args.out)
    fig_psi(cells, args.out)
    fig_membwproxy(base, cells, args.out)
    fig_w4ratio(df, args.out)
    fig_preempt(df, args.out)
    for f in sorted(args.out.glob("Figure_*.pdf")):
        print("wrote", f)
    return 0


if __name__ == "__main__":
    sys.exit(main())

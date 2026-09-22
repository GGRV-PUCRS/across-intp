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
import fig_names  # noqa: E402  (figure naming registry)
import p2_figio  # noqa: E402  (shared {png,pdf} output layout)
import sa_style  # noqa: E402  (Seminario de Andamento printed geometry)
import jsa_style  # noqa: E402  (JSA manuscript printed geometry)
import numpy as np

# The SA deck embeds the PNG siblings of these PDFs.

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


def load_byenv(tsv: Path):
    """Per-environment sibling of load(): consumes analyze-cadence.py
    --by-env --tsv output (leading env column). Density rows are skipped --
    the density panel comes from the pooled TSV."""
    fid = defaultdict(dict)      # (env,variant,wl,metric) -> {interval: dref%}
    med = defaultdict(dict)      # (env,variant,wl,metric) -> {interval: median}
    cls = {}
    with tsv.open() as fh:
        for r in csv.DictReader(fh, delimiter="\t"):
            e, v, w, m = r["env"], r["variant"], r["workload"], r["metric"]
            if m == "_density_rows_":
                continue
            iv = float(r["interval_s"])
            cls[m] = r["class"]
            med[(e, v, w, m)][iv] = float(r["median"])
            if r["dref"] != "":
                fid[(e, v, w, m)][iv] = float(r["dref"]) * 100.0
    return fid, cls, med


ENV_ORDER = ["bare", "container", "vm-guest"]
ENV_STYLE = {"bare": "-", "container": "--", "vm-guest": ":"}
ENV_LABEL = {"bare": "bare metal", "container": "Docker container",
             "vm-guest": "KVM guest"}


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


def sa_sensitivity(fid, cls, med, variants, workloads, fine, out: Path) -> None:
    """F8-cadence-sensitivity at the SA's printed width.

    Was 7.98 in scaled to 0.42, so its 7 pt tick labels printed at 2.92 pt --
    the second worst in the set. At the 3.36 in column the heatmap is the same
    matrix with the same numbers; what changes is that the three-line title
    moves to the LaTeX caption (it was reading instructions, not data) and the
    cell numbers sit at ANNOT_FLOOR, which is what dense in-cell annotations
    are allowed.
    """
    spec = sa_style.spec_for("F8-cadence-sensitivity")
    sa_style.apply()

    cols = [(w, v) for w in workloads for v in variants]
    rows = [m for m in ORDER
            if any(abs(med.get((v, w, m), {}).get(fine, 0)) >= FLOOR
                   for (w, v) in cols)]
    M = np.full((len(rows), len(cols)), np.nan)
    for ri, m in enumerate(rows):
        for ci, (w, v) in enumerate(cols):
            if abs(med.get((v, w, m), {}).get(fine, 0)) < FLOOR:
                continue
            vals = [abs(d) for d in fid.get((v, w, m), {}).values()]
            M[ri, ci] = max(vals) if vals else 0.0

    fig, ax = plt.subplots(figsize=(spec.width, spec.height),
                           layout="constrained")
    im = ax.imshow(M, aspect="auto", cmap="YlOrRd", vmin=0, vmax=100)
    # Two-level x axis. The exploratory cut stacks "<workload>\n<variant>" on
    # every column, which repeats each workload name once per variant; at the
    # 0.47 in column pitch those repeats overlap into each other. Naming the
    # workload once, centred under its variant pair, is the same information
    # in half the ink -- and the QA gate sees only a duplicate disappearing,
    # never a new string.
    ax.set_xticks(range(len(cols)))
    ax.set_xticklabels([v for (_w, v) in cols], fontsize=sa_style.BODY)
    span = len(variants)
    for i, w in enumerate(workloads):
        ax.text(i * span + (span - 1) / 2.0, -0.14, w.replace("_", " "),
                transform=ax.get_xaxis_transform(), ha="center", va="top",
                fontsize=sa_style.BODY)
        if i:
            ax.axvline(i * span - 0.5, color="black", lw=0.8)
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([f"{m} ({cls.get(m,'?')})" for m in rows],
                       fontsize=sa_style.BODY)
    ax.tick_params(length=0)
    for ri in range(len(rows)):
        for ci in range(len(cols)):
            if not np.isnan(M[ri, ci]):
                v = M[ri, ci]
                ax.text(ci, ri, f"{v:.0f}", ha="center", va="center",
                        fontsize=sa_style.ANNOT,
                        color="white" if v > 55 else "black")
    cb = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.03)
    cb.set_label("max |Δref| vs 0.1s (%)", size=sa_style.BODY)
    cb.ax.tick_params(labelsize=sa_style.BODY)
    cb.outline.set_linewidth(0.5)
    ax.grid(False)

    p2_figio.save_flat(fig, out, "F8-cadence-sensitivity", spec)


def _sensitivity_matrix(fid, cls, med, variants, workloads, fine):
    cols = [(w, v) for w in workloads for v in variants]
    rows = [m for m in ORDER
            if any(abs(med.get((v, w, m), {}).get(fine, 0)) >= FLOOR
                   for (w, v) in cols)]
    M = np.full((len(rows), len(cols)), np.nan)
    for ri, m in enumerate(rows):
        for ci, (w, v) in enumerate(cols):
            if abs(med.get((v, w, m), {}).get(fine, 0)) < FLOOR:
                continue
            vals = [abs(d) for d in fid.get((v, w, m), {}).values()]
            M[ri, ci] = max(vals) if vals else 0.0
    return cols, rows, M


def _draw_sensitivity(ax, cb_ax, cols, rows, M, cls, variants, workloads,
                      fontsize, annot_fontsize):
    im = ax.imshow(M, aspect="auto", cmap="YlOrRd", vmin=0, vmax=100)
    ax.set_xticks(range(len(cols)))
    ax.set_xticklabels([v for (_w, v) in cols], fontsize=fontsize)
    span = len(variants)
    for i, w in enumerate(workloads):
        ax.text(i * span + (span - 1) / 2.0, -0.16, jsa_style.wl_label(w),
                transform=ax.get_xaxis_transform(), ha="center", va="top",
                fontsize=fontsize)
        if i:
            ax.axvline(i * span - 0.5, color="black", lw=0.8)
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([f"{m} ({cls.get(m,'?')})" for m in rows],
                       fontsize=fontsize)
    ax.tick_params(length=0)
    for ri in range(len(rows)):
        for ci in range(len(cols)):
            if not np.isnan(M[ri, ci]):
                v = M[ri, ci]
                ax.text(ci, ri, f"{v:.0f}", ha="center", va="center",
                        fontsize=annot_fontsize,
                        color="white" if v > 55 else "black")
    ax.grid(False)
    cb = ax.figure.colorbar(im, cax=cb_ax) if cb_ax is not None else \
        ax.figure.colorbar(im, ax=ax, fraction=0.046, pad=0.03)
    cb.set_label("max |Δref| vs 0.1s (%)", size=fontsize)
    cb.ax.tick_params(labelsize=fontsize)
    cb.outline.set_linewidth(0.5)
    return im


def jsa_sensitivity(fid, cls, med, variants, workloads, fine, out_path):
    """F8-cadence-sensitivity for the JSA manuscript (fig:whichmetrics /
    figs/Figure_15.pdf). Same matrix as sa_sensitivity(); JSA geometry."""
    jsa_style.apply()
    cols, rows, M = _sensitivity_matrix(fid, cls, med, variants, workloads, fine)
    fig, ax = plt.subplots(figsize=(jsa_style.TEXT_WIDTH, 0.30 * len(rows) + 1.3),
                           layout="constrained")
    _draw_sensitivity(ax, None, cols, rows, M, cls, variants, workloads,
                      jsa_style.BODY, jsa_style.ANNOT)
    spec = jsa_style.FigSpec(jsa_style.TEXT_WIDTH, 0.30 * len(rows) + 1.3,
                             "fig:whichmetrics")
    w, h = jsa_style.save(fig, Path(out_path), spec)
    plt.close(fig)
    print(f"wrote {out_path} ({w:.2f} x {h:.2f} in)")


def jsa_fidelity(fid, dens, cls, med, variants, workloads, fine, out_path):
    """F8-cadence-fidelity for the JSA manuscript (fig:fidelitycadence /
    figs/Figure_16.pdf). Same curves as fig_fidelity(); JSA geometry, no
    in-figure title (the caption already states the shaded-band definition
    and the cadence-knee reading)."""
    jsa_style.apply()
    ncol = len(workloads) + 1
    fig, axes = plt.subplots(1, ncol, figsize=(jsa_style.TEXT_WIDTH, 2.35),
                             layout="constrained")
    _draw_fidelity_panels(fig, axes, fid, dens, cls, med, variants, workloads,
                          fine, jsa_style.BODY, jsa_style.LEGEND)
    spec = jsa_style.FigSpec(jsa_style.TEXT_WIDTH, 2.35, "fig:fidelitycadence")
    w, h = jsa_style.save(fig, Path(out_path), spec)
    plt.close(fig)
    print(f"wrote {out_path} ({w:.2f} x {h:.2f} in)")


def _draw_fidelity_panels(fig, axes, fid, dens, cls, med, variants, workloads,
                          fine, fontsize, legend_fontsize, legend_ax=None):
    style = {variants[0]: "-"}
    if len(variants) > 1:
        style[variants[1]] = "--"
    marker = {variants[0]: jsa_style.VARIANT_MARKER.get(variants[0], "o")}
    if len(variants) > 1:
        marker[variants[1]] = jsa_style.VARIANT_MARKER.get(variants[1], "^")

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
                    continue
                series = fid.get((v, w, m), {})
                if not series:
                    continue
                xs = sorted(series); ys = [series[x] for x in xs]
                ax.plot(xs, ys, style.get(v, "-"), marker=mmap[m], ms=3.6,
                        color=cmap[m], lw=1.3, alpha=0.9)
        ax.set_xscale("log")
        ax.set_xticks([0.1, 0.25, 0.5, 1, 2, 5])
        ax.set_xticklabels(["0.1", "0.25", "0.5", "1", "2", "5"], fontsize=fontsize)
        ax.set_xlabel("sampling interval (s)", fontsize=fontsize)
        ax.set_ylabel("Δref from 0.1s (%)" if wi == 0 else "", fontsize=fontsize)
        ax.set_title(jsa_style.wl_label(w), fontsize=fontsize)
        ax.grid(True, which="both", ls=":", alpha=0.3)
        ax.tick_params(which="both", labelsize=fontsize)
        # explicit major ticks/labels already carry every value that matters;
        # matplotlib's auto minor-tick labels on a log axis render their
        # exponent as a reduced-size mathtext superscript that falls below
        # the annotation floor even after the manuscript's 1.3x upscale.
        ax.xaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())

    axd = axes[-1]
    (v0, w0), d0 = next(iter(sorted(dens.items())))
    xs = sorted(d0); ys = [d0[x] for x in xs]
    axd.plot(xs, ys, "-o", color="#333333", ms=3.6, lw=1.3)
    axd.set_xscale("log"); axd.set_yscale("log")
    axd.set_xticks([0.1, 0.25, 0.5, 1, 2, 5])
    axd.set_xticklabels(["0.1", "0.25", "0.5", "1", "2", "5"], fontsize=fontsize)
    axd.set_xlabel("sampling interval (s)", fontsize=fontsize)
    axd.set_ylabel("sample density (rows/rep)", fontsize=fontsize)
    axd.set_title("sample density", fontsize=fontsize)
    axd.grid(True, which="both", ls=":", alpha=0.3)
    axd.tick_params(which="both", labelsize=fontsize)
    # log-scale y tick labels render as "10^n" with the exponent as a
    # reduced-size mathtext superscript (~0.7x); bump the base size so that
    # reduced glyph still clears the annotation floor after the manuscript's
    # 1.3x display upscale.
    axd.tick_params(axis="y", which="both", labelsize=fontsize + 2)
    axd.xaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())
    axd.yaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())
    for x, y in zip(xs, ys):
        axd.annotate(f"{int(y)}", (x, y), fontsize=fontsize - 1, ha="left", va="bottom")

    handles = [plt.Line2D([0], [0], color=cmap[m], marker=mmap[m], lw=1.3,
                          label=f"{m} ({cls.get(m,'?')})") for m in drawn_metrics]
    for v in variants:
        handles.append(plt.Line2D([0], [0], color="k", ls=style.get(v, "-"),
                                  marker=marker.get(v, "o"),
                                  label=jsa_style.VARIANT_LABEL.get(v, v)))
    if legend_ax is not None:
        legend_ax.axis("off")
        legend_ax.legend(handles=handles, loc="center",
                         ncol=min(len(handles), 6), fontsize=legend_fontsize,
                         frameon=False, handlelength=1.2, handletextpad=0.4,
                         columnspacing=0.9)
        return
    fig.legend(handles=handles, loc="outside lower center",
              ncol=min(len(handles), 6), fontsize=legend_fontsize,
              frameon=False, handlelength=1.2, handletextpad=0.4,
              columnspacing=0.9)


def jsa_merged(fid, dens, cls, med, variants, workloads, fine, out_path,
               env=None):
    """Additive two-panel merge of Figure_15 (sensitivity) + Figure_16
    (fidelity/density) into figs/Figure_15_v2.pdf. Suggested pairing:
    \\label{fig:cadence}, one caption covering both panels -- see the
    brief's note that the two separate floats "waste space".

    With env=(efid, ecls, emed) from load_byenv(), a per-environment
    deviation panel row is inserted directly under the pooled fidelity
    row (same workload columns), drawing exactly the (metric, variant)
    series whose environments disagree -- the pooled view hides these
    (sign-flipping guest effects), which is what the R2 rerun documents.
    The pooled legend moves into its own strip row so it still groups
    with the pooled panels; the sensitivity heatmap becomes the last row."""
    jsa_style.apply()
    cols, rows, M = _sensitivity_matrix(fid, cls, med, variants, workloads, fine)
    ncol = len(workloads) + 1
    heat_h = 0.30 * len(rows) + 0.9
    if env is None:
        height = 2.35 + heat_h + 0.2
        fig = plt.figure(figsize=(jsa_style.TEXT_WIDTH, height),
                         layout="constrained")
        gs = fig.add_gridspec(2, ncol, height_ratios=[2.35, heat_h])
        axes = [fig.add_subplot(gs[0, i]) for i in range(ncol)]
        _draw_fidelity_panels(fig, axes, fid, dens, cls, med, variants,
                              workloads, fine, jsa_style.BODY, jsa_style.LEGEND)
        ax2 = fig.add_subplot(gs[1, :])
        _draw_sensitivity(ax2, None, cols, rows, M, cls, variants, workloads,
                          jsa_style.BODY, jsa_style.ANNOT)
    else:
        efid, ecls, emed = env
        env_h = 2.3
        height = 2.35 + 0.55 + env_h + heat_h + 0.2
        fig = plt.figure(figsize=(jsa_style.TEXT_WIDTH, height),
                         layout="constrained")
        gs = fig.add_gridspec(4, ncol,
                              height_ratios=[2.35, 0.55, env_h, heat_h])
        axes = [fig.add_subplot(gs[0, i]) for i in range(ncol)]
        _draw_fidelity_panels(fig, axes, fid, dens, cls, med, variants,
                              workloads, fine, jsa_style.BODY, jsa_style.LEGEND,
                              legend_ax=fig.add_subplot(gs[1, :]))
        eaxes = [fig.add_subplot(gs[2, i]) for i in range(len(workloads))]
        _draw_env_panels(fig, eaxes, efid, ecls, emed, variants, workloads,
                         fine, jsa_style.BODY, jsa_style.LEGEND,
                         legend_ax=fig.add_subplot(gs[2, -1]))
        ax2 = fig.add_subplot(gs[3, :])
        _draw_sensitivity(ax2, None, cols, rows, M, cls, variants, workloads,
                          jsa_style.BODY, jsa_style.ANNOT)
    spec = jsa_style.FigSpec(jsa_style.TEXT_WIDTH, height, "fig:cadence")
    w, h = jsa_style.save(fig, Path(out_path), spec)
    plt.close(fig)
    print(f"wrote {out_path} ({w:.2f} x {h:.2f} in) -- suggested "
          f"\\label{{fig:cadence}}, merges fig:whichmetrics + fig:fidelitycadence")


def _divergent_env_series(efid, emed, variants, workloads, fine):
    """Select the (wl, metric, variant) series whose per-environment
    deviations disagree: a >=20-point spread between the per-environment
    signed extreme deviations, or a sign flip with both sides >=10%.
    Everything else reads the same pooled or per environment, so drawing
    it would only repeat the top panel."""
    sel = defaultdict(list)    # wl -> [(metric, variant), ...]
    for w in workloads:
        for m in ORDER:
            for v in variants:
                ext = []
                for e in ENV_ORDER:
                    if abs(emed.get((e, v, w, m), {}).get(fine, 0)) < FLOOR:
                        continue
                    series = efid.get((e, v, w, m), {})
                    if series:
                        ext.append(max(series.values(), key=abs))
                if len(ext) < 2:
                    continue
                if max(ext) - min(ext) >= 20 or (max(ext) >= 10 and min(ext) <= -10):
                    sel[w].append((m, v))
    return sel


def _draw_env_panels(fig, axes, efid, ecls, emed, variants, workloads, fine,
                     fontsize, legend_fontsize, legend_ax=None):
    """Per-environment deviation panel row (R2): one panel per workload,
    only the environment-divergent (metric, variant) series. Colour =
    metric (Okabe-Ito), linestyle = environment, marker = variant. The
    symlog y axis keeps the +-10% band linear while leaving room for the
    in-guest v3.3 cpu climb (~+1000%)."""
    sel = _divergent_env_series(efid, emed, variants, workloads, fine)
    cmap = {}
    for w in workloads:
        for m, _v in sel.get(w, []):
            if m not in cmap:
                cmap[m] = jsa_style.OKABE_ITO[len(cmap) % len(jsa_style.OKABE_ITO)]

    for wi, w in enumerate(workloads):
        ax = axes[wi]
        ax.axhspan(-BAND * 100, BAND * 100, color="green", alpha=0.08, zorder=0)
        ax.axhline(0, color="grey", lw=0.6, zorder=1)
        ymax = 15.0
        ymin = -15.0
        for m, v in sel.get(w, []):
            for e in ENV_ORDER:
                if abs(emed.get((e, v, w, m), {}).get(fine, 0)) < FLOOR:
                    continue
                series = efid.get((e, v, w, m), {})
                if not series:
                    continue
                xs = sorted(series); ys = [series[x] for x in xs]
                ymax = max(ymax, max(ys))
                ymin = min(ymin, min(ys))
                ax.plot(xs, ys, ENV_STYLE[e], color=cmap[m],
                        marker=jsa_style.VARIANT_MARKER.get(v, "o"), ms=3.2,
                        lw=1.3, alpha=0.9)
                if abs(ys[-1]) > 100:
                    ax.annotate(f"{ys[-1]:+.0f}%", (xs[-1], ys[-1]),
                                fontsize=fontsize - 1, ha="right", va="top",
                                color=cmap[m])
        ax.set_xscale("log")
        ax.set_yscale("symlog", linthresh=10)
        ax.set_ylim(ymin * 1.3, ymax * 1.15)
        ax.set_yticks([t for t in (-1000, -100, -10, 0, 10, 100, 1000)
                       if ymin * 1.3 <= t <= ymax * 1.15])
        ax.set_xticks([0.1, 0.25, 0.5, 1, 2, 5])
        ax.set_xticklabels(["0.1", "0.25", "0.5", "1", "2", "5"],
                           fontsize=fontsize)
        ax.set_xlabel("sampling interval (s)", fontsize=fontsize)
        ax.set_ylabel("Δref from 0.1s (%)" if wi == 0 else "", fontsize=fontsize)
        ax.set_title("per environment", fontsize=fontsize)
        ax.grid(True, which="both", ls=":", alpha=0.3)
        ax.tick_params(which="both", labelsize=fontsize)
        ax.xaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())
        ax.yaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())

    if legend_ax is not None:
        handles = [plt.Line2D([0], [0], color=cmap[m], lw=1.3,
                              label=f"{m} ({ecls.get(m,'?')})")
                   for m in cmap]
        handles += [plt.Line2D([0], [0], color="k", ls=ENV_STYLE[e],
                               label=ENV_LABEL[e]) for e in ENV_ORDER]
        handles += [plt.Line2D([0], [0], color="k", ls="none",
                               marker=jsa_style.VARIANT_MARKER.get(v, "o"),
                               label=jsa_style.VARIANT_LABEL.get(v, v))
                    for v in variants]
        legend_ax.axis("off")
        legend_ax.legend(handles=handles, loc="center left",
                         fontsize=legend_fontsize, frameon=False,
                         handlelength=1.4, handletextpad=0.5)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("tsv", nargs="?", type=Path,
                    default="results/p2-cadence-sweep/cadence-fidelity.tsv")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--sa-style", action="store_true",
                    help="render only F8-cadence-sensitivity, at the "
                         "Seminario de Andamento's exact printed width")
    ap.add_argument("--jsa-sensitivity", default=None,
                    help="also render fig:whichmetrics for the JSA "
                         "manuscript to this exact PDF path (Figure_15.pdf)")
    ap.add_argument("--jsa-fidelity", default=None,
                    help="also render fig:fidelitycadence for the JSA "
                         "manuscript to this exact PDF path (Figure_16.pdf)")
    ap.add_argument("--jsa-merged", default=None,
                    help="also render the additive two-panel merge "
                         "(suggested fig:cadence) to this exact PDF path "
                         "(Figure_15_v2.pdf)")
    ap.add_argument("--by-env-tsv", type=Path, default=None,
                    help="per-environment analyzer TSV (analyze-cadence.py "
                    "--by-env); with --jsa-merged, appends a per-environment "
                    "deviation panel row to the merged figure")
    fig_names.add_dataset_arg(ap)
    args = ap.parse_args()
    p2_figio.set_dataset(args.dataset or fig_names.dataset_tag(args.tsv))
    fid, dens, cls, med = load(args.tsv)
    variants = sorted({v for (v, _, _) in fid})
    workloads = sorted({w for (_, w, _) in fid})
    fine = min((iv for d in med.values() for iv in d), default=0.1)
    out = args.out or Path("results/figures/p2-cadence-sweep")
    out.mkdir(parents=True, exist_ok=True)
    if args.jsa_sensitivity:
        jsa_sensitivity(fid, cls, med, variants, workloads, fine, args.jsa_sensitivity)
    if args.jsa_fidelity:
        jsa_fidelity(fid, dens, cls, med, variants, workloads, fine, args.jsa_fidelity)
    if args.jsa_merged:
        env = None
        if args.by_env_tsv:
            env = load_byenv(args.by_env_tsv)
        jsa_merged(fid, dens, cls, med, variants, workloads, fine,
                   args.jsa_merged, env=env)
    if args.jsa_sensitivity or args.jsa_fidelity or args.jsa_merged:
        return 0
    if args.sa_style:
        sa_sensitivity(fid, cls, med, variants, workloads, fine, out)
        return 0
    fig_fidelity(fid, dens, cls, med, variants, workloads, fine, out)
    fig_sensitivity(fid, cls, med, variants, workloads, fine, out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

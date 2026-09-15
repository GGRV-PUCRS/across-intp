#!/usr/bin/env python3
"""plot-fig2-3-4-6-8-jsa.py -- JSA redraws of five figures from the
cross-deployment P2 campaign, all sourced from plot-p2-15metric.py's own
loaders (copied here rather than imported -- that filename is not a valid
Python module name) against the same TSV / raw-capture source of record:
results/p2-15metric-xdeploy-1of3/cross-deployment.tsv and portable.tsv
captures. No statistic is recomputed differently than
bench/analyze-cross-deployment.py already produced.

  Figure_2.pdf (fig:availability, F3) -- bigger cells, env rows unrotated
    (already short), metric columns rotated, PLUS a spelled-out side legend
    mapping each metric code to its full name (the brief's actual ask:
    "spell out metric names" -- the existing SA cut already rotates labels
    but leaves codes unexplained).
  Figure_8.pdf (fig:claimclass, F2) -- adds a caption-independent legend for
    the four claim classes / shading intensity.
  Figure_3.pdf (fig:psi, F5) -- two-panel redesign: membw_est (log) and
    psi_mem on comparable, directly-labeled axes, with an in-plot
    "saturation point" callout on the flat psi_mem line.
  Figure_4.pdf (fig:membwproxy, F4) -- rho printed in-plot, y=x identity
    line, v2.1/v3.3 distinguished by marker shape + color.
  Figure_6.pdf (fig:w4ratio, F1) -- the 0.8-1.25 equivalence corridor shaded
    AND labeled inside the plot, not only in the caption.
"""
from __future__ import annotations

import argparse
import glob
import statistics
import textwrap
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib.colors import SymLogNorm
import numpy as np
import pandas as pd

try:
    from scipy.stats import spearmanr
except ImportError:
    spearmanr = None

import jsa_style as style

VARIANT_LABELS = {"v2.1": "c-abi-cgroup", "v3.3": "ebpf-core-cgroup"}
ENV_ORDER = ["container", "container-podman", "container-lxc",
             "container-k8s", "vm-guest"]
ENV_SHORT = {"container": "docker", "container-podman": "podman",
             "container-lxc": "lxc/incus", "container-k8s": "k8s",
             "vm-guest": "kvm-guest", "bare": "bare"}
METRICS_PORTABLE = ["schedlat", "psi_mem", "membw_est", "psi_io",
                     "schedthr", "steal"]
METRICS_REGIME = ["psp", "idle_preempt"]

METRIC_FULL = {
    "schedlat": "run-queue (scheduling) latency",
    "psi_mem": "PSI memory pressure",
    "membw_est": "estimated memory bandwidth",
    "psi_io": "PSI I/O pressure",
    "schedthr": "CFS throttling (confound guard)",
    "steal": "hypervisor steal time (confound guard)",
    "psp": "involuntary preemptions/s",
    "idle_preempt": "idle-task preemption rate (eBPF-only)",
    "mbw": "memory bandwidth (RDT)",
    "llcocc": "LLC occupancy (RDT)",
    "llcmr": "LLC miss ratio",
}


def vlabel(v: str) -> str:
    return VARIANT_LABELS.get(v, v)


def _plain_log_fmt(v, _pos=None) -> str:
    """Log-axis tick label without a scientific-notation exponent glyph.

    matplotlib's default LogFormatterSciNotation renders the exponent in a
    smaller mathtext script size (~0.7x) that ignores the rcParams tick-label
    floor entirely, so a 7 pt axis prints a 4.9 pt "4" in "10^4" -- invisible
    to the QA gate's rcParams check but real in the saved PDF. Flat digits
    avoid the issue outright and are no less readable here.
    """
    if v <= 0:
        return ""
    if v >= 1000:
        return f"{v/1000:g}k"
    return f"{v:g}"


def load_capture(path: Path) -> dict[str, float]:
    hdr, cols = None, {}
    for line in path.open(encoding="utf-8", errors="replace"):
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        f = s.split("\t")
        if f[0] == "netp":
            hdr = f
            continue
        if hdr is None:
            continue
        off = len(f) - len(hdr)
        for i, m in enumerate(hdr):
            v = f[off + i]
            if v != "--":
                try:
                    cols.setdefault(m, []).append(float(v))
                except ValueError:
                    pass
    return {m: statistics.median(vs) for m, vs in cols.items() if vs}


def scan_cells(base: Path):
    cells: dict[tuple, list[dict]] = {}
    for f in glob.glob(str(base / "*/v*/solo/*/rep*/portable.tsv")):
        p = Path(f)
        env, var, wl = p.parts[-6], p.parts[-5], p.parts[-3]
        cells.setdefault((env, var, wl), []).append(load_capture(p))
    return cells


def cell_median(cells, env, var, wl, metric):
    reps = cells.get((env, var, wl), [])
    vals = [r[metric] for r in reps if metric in r]
    return statistics.median(vals) if vals else None


def gt_llc_miss(rep_dir: Path) -> float | None:
    gt = rep_dir / "groundtruth.tsv"
    if not gt.exists():
        return None
    vals, idx = [], None
    for line in gt.open(encoding="utf-8", errors="replace"):
        f = line.rstrip("\n").split("\t")
        if idx is None:
            if "llc_miss" in f:
                idx = f.index("llc_miss")
            continue
        try:
            v = float(f[idx])
            if v > 0:
                vals.append(v)
        except (ValueError, IndexError):
            pass
    return statistics.median(vals) if vals else None


# ---------------------------------------------------------------------
# Figure_2 / fig:availability
# ---------------------------------------------------------------------

def fig_availability(cells, out: Path) -> None:
    metrics = METRICS_PORTABLE + METRICS_REGIME + ["mbw", "llcocc", "llcmr"]
    variants = sorted({k[1] for k in cells})
    envs = ["bare"] + ENV_ORDER
    OK, GONE = style.BLUISH_GREEN, style.GREY

    width = style.TEXT_WIDTH
    height = 3.6
    fig, axes = plt.subplots(1, len(variants), figsize=(width, height))
    fig.subplots_adjust(left=0.075, right=0.685, top=0.86, bottom=0.30,
                         wspace=0.12)
    if len(variants) == 1:
        axes = [axes]
    for ai, (ax, var) in enumerate(zip(axes, variants)):
        for yi, env in enumerate(envs):
            reps = [r for (e, v, _w), rl in cells.items()
                    if e == env and v == var for r in rl]
            for xi, m in enumerate(metrics):
                ok = any(m in r for r in reps)
                ax.add_patch(plt.Rectangle(
                    (xi, yi), 0.94, 0.94,
                    facecolor=OK if ok else GONE,
                    edgecolor="white", linewidth=0.6,
                    hatch=None if ok else "////"))
        ax.set_xlim(0, len(metrics))
        ax.set_ylim(0, len(envs))
        ax.set_xticks(np.arange(len(metrics)) + 0.47)
        ax.set_xticklabels(metrics, rotation=40, ha="right",
                            rotation_mode="anchor", fontsize=style.BODY)
        ax.set_yticks(np.arange(len(envs)) + 0.47)
        ax.set_yticklabels([ENV_SHORT[e] for e in envs], fontsize=style.BODY)
        # Env labels on the left panel only: with wspace this tight the right
        # panel's labels land on the left panel's llcocc/llcmr columns.
        ax.yaxis.set_tick_params(labelleft=(ai == 0))
        ax.invert_yaxis()
        ax.axvline(len(METRICS_PORTABLE) + len(METRICS_REGIME), color="black",
                   lw=1.1)
        ax.set_title(vlabel(var), fontsize=style.TITLE)
        for s in ax.spines.values():
            s.set_visible(False)
        ax.tick_params(length=0)

    handles = [
        plt.Rectangle((0, 0), 1, 1, fc=OK, label="available"),
        plt.Rectangle((0, 0), 1, 1, fc=GONE, hatch="////",
                      label="structurally unavailable"),
    ]
    axes[0].legend(handles=handles, loc="upper left",
                   bbox_to_anchor=(0.0, -0.32), frameon=False,
                   fontsize=style.LEGEND, ncol=1, handlelength=1.3)

    # Side legend: metric code -> full name, so the figure decodes itself.
    # Wrapped to the narrow right-margin column so it never runs past the
    # figure's own right edge. Continuation lines hang at a fixed small
    # indent so every entry starts flush left on the same grid.
    lines = []
    for m in metrics:
        wrapped = textwrap.wrap(f"{m}: {METRIC_FULL.get(m, m)}", width=34,
                                subsequent_indent="  ",
                                break_long_words=False,
                                break_on_hyphens=False)
        lines.append("\n".join(wrapped))
    fig.text(0.70, 0.90, "\n".join(lines), ha="left", va="top",
             fontsize=style.ANNOT, family="monospace", linespacing=1.6,
             multialignment="left")

    spec = style.FigSpec(width, height, "fig:availability")
    w, h = style.save(fig, out / "Figure_2.pdf", spec)
    plt.close(fig)
    print(f"wrote {out / 'Figure_2.pdf'} ({w:.2f} x {h:.2f} in)")


# ---------------------------------------------------------------------
# Figure_8 / fig:claimclass
# ---------------------------------------------------------------------

def fig_claimclass(df: pd.DataFrame, out: Path) -> None:
    SIG_ORDER = {"***": 3, "**": 2, "*": 1, "n.s.": 0, "n/a": -1}
    cls_color = {"absolute": style.BLUE, "directional": style.ORANGE,
                 "descriptive": style.GREY}
    variants = sorted(df.variant.unique())
    all_metrics = sorted(df.metric.unique())

    width = style.TEXT_WIDTH
    height = 3.8
    fig, axes = plt.subplots(1, len(variants), figsize=(width, height))
    fig.subplots_adjust(left=0.10, right=0.98, top=0.86, bottom=0.30,
                         wspace=0.12)
    if len(variants) == 1:
        axes = [axes]
    for ai, (ax, var) in enumerate(zip(axes, variants)):
        sub = df[df.variant == var]
        for yi, m in enumerate(all_metrics):
            for xi, env in enumerate(ENV_ORDER):
                s = sub[(sub.metric == m) & (sub.env == env)]
                if s.empty:
                    continue
                cls = s.claim_class.iloc[0]
                best = max((SIG_ORDER.get(x, 0) for x in s.signif), default=0)
                ax.add_patch(plt.Rectangle(
                    (xi, yi), 0.94, 0.94,
                    color=cls_color.get(cls, "#eeeeee"),
                    alpha=0.30 + 0.23 * min(best, 3) / 3))
        ax.set_xlim(0, len(ENV_ORDER))
        ax.set_ylim(0, len(all_metrics))
        ax.set_xticks(np.arange(len(ENV_ORDER)) + 0.5)
        ax.set_xticklabels([ENV_SHORT[e] for e in ENV_ORDER],
                            rotation=30, ha="right", fontsize=style.BODY)
        ax.set_yticks(np.arange(len(all_metrics)) + 0.5)
        ax.set_yticklabels(all_metrics, fontsize=style.BODY)
        # Metric labels on the left panel only: the right panel's would land
        # on the left panel's kvm-guest column at this wspace.
        ax.yaxis.set_tick_params(labelleft=(ai == 0))
        ax.set_title(vlabel(var), fontsize=style.TITLE)
        ax.invert_yaxis()
        for s in ax.spines.values():
            s.set_visible(False)
        ax.tick_params(length=0)

    handles = [plt.Rectangle((0, 0), 1, 1, color=c, alpha=0.55)
               for c in cls_color.values()]
    labels = list(cls_color.keys())
    handles.append(plt.Rectangle((0, 0), 1, 1, facecolor="white",
                                  edgecolor="#999999"))
    labels.append("unavailable (blank)")
    # Shading-intensity legend: three alpha steps of one class colour.
    shade_handles = [plt.Rectangle((0, 0), 1, 1, color=style.BLUE,
                                    alpha=0.30 + 0.23 * k / 3)
                      for k in (0, 2, 3)]
    shade_labels = ["not significant", "significant (*/**)", "significant (***)"]
    fig.legend(handles, labels, loc="lower center", ncol=len(labels),
               fontsize=style.LEGEND, frameon=False,
               bbox_to_anchor=(0.5, 0.11), handlelength=1.3)
    fig.legend(shade_handles, shade_labels, loc="lower center",
               ncol=len(shade_labels), fontsize=style.LEGEND, frameon=False,
               bbox_to_anchor=(0.5, 0.0), handlelength=1.3)

    spec = style.FigSpec(width, height, "fig:claimclass")
    w, h = style.save(fig, out / "Figure_8.pdf", spec)
    plt.close(fig)
    print(f"wrote {out / 'Figure_8.pdf'} ({w:.2f} x {h:.2f} in)")


# ---------------------------------------------------------------------
# Figure_3 / fig:psi -- two-panel, saturation-point callout
# ---------------------------------------------------------------------

def fig_psi(cells, out: Path) -> None:
    variants = sorted({k[1] for k in cells})
    envs = ["bare"] + ENV_ORDER

    width = style.TEXT_WIDTH
    height = 2.9
    fig, (ax_bw, ax_psi) = plt.subplots(1, 2, figsize=(width, height),
                                         sharex=True, layout="constrained")
    x = np.arange(len(envs))
    bw_width = 0.38
    for vi, var in enumerate(variants):
        mb, psi = [], []
        for env in envs:
            mb.append(cell_median(cells, env, var, "app05_streaming",
                                   "membw_est") or 0)
            psi.append(cell_median(cells, env, var, "app05_streaming",
                                    "psi_mem") or 0)
        off = (vi - (len(variants) - 1) / 2) * bw_width
        color = style.VARIANT_COLOR.get(var, style.BLUE)
        ax_bw.bar(x + off, mb, bw_width * 0.92, color=color,
                  label=style.VARIANT_LABEL.get(var, var))
        ax_psi.plot(x, psi, marker=style.VARIANT_MARKER.get(var, "o"),
                    color=color, label=style.VARIANT_LABEL.get(var, var),
                    ms=5)
    ax_bw.set_yscale("log")
    ax_bw.yaxis.set_major_formatter(mticker.FuncFormatter(_plain_log_fmt))
    ax_bw.yaxis.set_minor_formatter(mticker.NullFormatter())
    ax_bw.set_xticks(x)
    ax_bw.set_xticklabels([ENV_SHORT[e] for e in envs], rotation=30,
                           ha="right", fontsize=style.BODY)
    ax_bw.set_ylabel("membw_est, app05_streaming (MB/s, log)")
    # Upper left is the only empty quadrant: the kvm-guest bars fill the
    # right side to the top of the log axis.
    ax_bw.legend(fontsize=style.LEGEND, loc="upper left")

    ax_psi.set_xticks(x)
    ax_psi.set_xticklabels([ENV_SHORT[e] for e in envs], rotation=30,
                            ha="right", fontsize=style.BODY)
    ax_psi.set_ylabel("psi_mem, app05_streaming")
    ax_psi.set_ylim(-0.08, 1.0)
    ax_psi.axhline(0, color="#999999", lw=0.7)
    # Saturation-point callout: bandwidth is high everywhere (left panel)
    # while psi_mem stays flat at 0 (right panel) -- point at the flat line.
    mid = len(envs) // 2
    ax_psi.annotate("saturation point:\nbandwidth saturated,\npsi_mem stays 0",
                     xy=(mid, 0.0), xytext=(mid - 0.3, 0.55),
                     fontsize=style.ANNOT,
                     arrowprops=dict(arrowstyle="-|>", lw=0.8,
                                     color=style.VERMILLION),
                     color=style.VERMILLION)
    ax_psi.legend(fontsize=style.LEGEND, loc="upper right")

    spec = style.FigSpec(width, height, "fig:psi")
    w, h = style.save(fig, out / "Figure_3.pdf", spec)
    plt.close(fig)
    print(f"wrote {out / 'Figure_3.pdf'} ({w:.2f} x {h:.2f} in)")


# ---------------------------------------------------------------------
# Figure_4 / fig:membwproxy
# ---------------------------------------------------------------------

def fig_membw(base: Path, cells, out: Path) -> None:
    variants = sorted({k[1] for k in cells})

    width = style.TEXT_WIDTH * 0.55
    height = 3.5
    fig, ax = plt.subplots(figsize=(width, height), layout="constrained")
    all_xy = []
    for var in variants:
        xs, ys = [], []
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
        all_xy += list(zip(xs, ys))
        rho = spearmanr(xs, ys)[0] if spearmanr else float("nan")
        color = style.VARIANT_COLOR.get(var, style.BLUE)
        marker = style.VARIANT_MARKER.get(var, "o")
        ax.scatter(xs, ys, s=13, alpha=0.55, color=color, marker=marker,
                   edgecolors="none",
                   label=f"{style.VARIANT_LABEL.get(var, var)}  "
                         f"ρ={rho:.2f} (n={len(xs)})")

    if all_xy:
        lo = min(min(x, y) for x, y in all_xy)
        hi = max(max(x, y) for x, y in all_xy)
        ax.plot([lo, hi], [lo, hi], color="black", lw=0.8, ls="--",
                label="y = x (identity)")

    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(_plain_log_fmt))
    ax.xaxis.set_minor_formatter(mticker.NullFormatter())
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(_plain_log_fmt))
    ax.yaxis.set_minor_formatter(mticker.NullFormatter())
    ax.set_xlabel("ground truth: LLC misses/s (host perf)")
    ax.set_ylabel("estimated bandwidth,\nmembw_est (MB/s)")
    ax.legend(fontsize=style.LEGEND, loc="upper left", handlelength=1.3)
    ax.grid(alpha=0.25, which="both")

    spec = style.FigSpec(width, height, "fig:membwproxy")
    w, h = style.save(fig, out / "Figure_4.pdf", spec)
    plt.close(fig)
    print(f"wrote {out / 'Figure_4.pdf'} ({w:.2f} x {h:.2f} in)")


# ---------------------------------------------------------------------
# Figure_6 / fig:w4ratio -- shaded + labeled equivalence corridor
# ---------------------------------------------------------------------

def fig_ratio(df: pd.DataFrame, out: Path) -> None:
    d = df[df.claim_class == "absolute"].copy()
    metrics = sorted(d.metric.unique())
    variants = sorted(d.variant.unique())

    width = style.TEXT_WIDTH
    ncols = len(metrics) * len(variants)
    height = 3.3
    fig, axes = plt.subplots(1, ncols, figsize=(width, height), sharey=True,
                              layout="constrained")
    if ncols == 1:
        axes = [axes]
    col = 0
    env_markers = {"container": "o", "container-podman": "s",
                   "container-lxc": "^", "container-k8s": "D",
                   "vm-guest": "P"}
    for m in metrics:
        for var in variants:
            ax = axes[col]
            col += 1
            sub = d[(d.variant == var) & (d.metric == m)]
            wls = sorted(sub.workload.unique())
            ax.axhspan(0.8, 1.25, color=style.BLUISH_GREEN, alpha=0.14,
                       zorder=0)
            ax.axhline(1.0, color="k", lw=0.6, ls=":", zorder=1)
            for i, env in enumerate(ENV_ORDER):
                s = sub[sub.env == env].set_index("workload").reindex(wls)
                x = np.arange(len(wls)) + (i - 2) * 0.14
                lo = np.clip(s.ratio - s.ci_lo, 0, None)
                hi = np.clip(s.ci_hi - s.ratio, 0, None)
                ax.errorbar(x, s.ratio, yerr=[lo.fillna(0), hi.fillna(0)],
                            fmt=env_markers.get(env, "o"), ms=4,
                            color=style.OKABE_ITO[i % len(style.OKABE_ITO)],
                            capsize=2, label=ENV_SHORT[env], zorder=2)
            ax.text(0.02, 1.245, "0.8–1.25× equivalence corridor",
                    transform=ax.get_yaxis_transform(), fontsize=style.ANNOT - 0.5,
                    color="#2f6b4f", ha="left", va="top")
            ax.set_xticks(range(len(wls)))
            ax.set_xticklabels([w.split("_")[0] for w in wls],
                                fontsize=style.ANNOT, rotation=30, ha="right")
            ax.set_ylim(0, 3.6)
            ax.set_title(f"{vlabel(var)}\n{m}", fontsize=style.TITLE)
            if col == 1:
                ax.set_ylabel("ratio vs bare metal")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="outside lower center",
               ncol=len(ENV_ORDER), fontsize=style.LEGEND, frameon=False,
               handlelength=1.2)

    spec = style.FigSpec(width, height, "fig:w4ratio")
    w, h = style.save(fig, out / "Figure_6.pdf", spec)
    plt.close(fig)
    print(f"wrote {out / 'Figure_6.pdf'} ({w:.2f} x {h:.2f} in)")


# ---------------------------------------------------------------------
# Figure_14 / fig:preempt (renamed off "F6-involuntary-..." -- internal
# F-number in the old filename leaked into the manuscript's supplementary
# zip). Colour now encodes signed log magnitude of the raw delta, not just
# Cliff's delta: the 33 008-420 922 events/s range saturates a linear or
# bounded [-1,1] color scale into "everything is red", losing exactly the
# magnitude story the caption's 33 008 -> 420 922 number tells.
# ---------------------------------------------------------------------

def _fmt_delta(d: float) -> str:
    if abs(d) >= 10000:
        return f"{d/1000:+.0f}k"
    if abs(d) >= 1000:
        return f"{d/1000:+.1f}k"
    return f"{d:+.0f}"


def fig_preempt(df: pd.DataFrame, out: Path) -> None:
    d = df[df.metric == "psp"].copy()
    d["delta"] = pd.to_numeric(d["delta"], errors="coerce")
    variants = sorted(d.variant.unique())

    width = style.TEXT_WIDTH
    height = 3.5
    fig, axes = plt.subplots(1, len(variants), figsize=(width, height),
                              layout="constrained")
    if len(variants) == 1:
        axes = [axes]
    norm = SymLogNorm(linthresh=100, vmin=-5e5, vmax=5e5, base=10)
    im = None
    for ax, var in zip(axes, variants):
        sub = d[d.variant == var]
        wls = sorted(sub.workload.unique())
        grid = np.full((len(wls), len(ENV_ORDER)), np.nan)
        for yi, wl in enumerate(wls):
            for xi, env in enumerate(ENV_ORDER):
                s = sub[(sub.workload == wl) & (sub.env == env)]
                if not s.empty:
                    grid[yi, xi] = s.delta.iloc[0]
        im = ax.imshow(grid, cmap="RdBu_r", norm=norm, aspect="auto")
        for yi, wl in enumerate(wls):
            for xi, env in enumerate(ENV_ORDER):
                s = sub[(sub.workload == wl) & (sub.env == env)]
                if s.empty:
                    continue
                sig = s.signif.iloc[0] not in ("n.s.", "n/a")
                val = (_fmt_delta(s.delta.iloc[0])
                       if pd.notna(s.delta.iloc[0]) else "?")
                ax.text(xi, yi, val, ha="center", va="center",
                        fontsize=style.ANNOT,
                        fontweight="bold" if sig else "normal",
                        color="white" if abs(grid[yi, xi]) > 4e4 else "black")
        ax.set_xticks(range(len(ENV_ORDER)))
        ax.set_xticklabels([ENV_SHORT[e] for e in ENV_ORDER], rotation=30,
                            ha="right", fontsize=style.BODY)
        ax.set_yticks(range(len(wls)))
        ax.set_yticklabels([w.replace("_", " ") for w in wls],
                            fontsize=style.BODY)
        ax.set_title(vlabel(var), fontsize=style.TITLE)

    cb = fig.colorbar(im, ax=axes, fraction=0.035, pad=0.02)
    cb.set_label("involuntary preemptions/s, Δ vs bare metal "
                 "(symlog scale)", fontsize=style.LEGEND)
    cb.ax.tick_params(labelsize=style.ANNOT)
    tick_locs = [-5e5, -1e4, -1e2, 0, 1e2, 1e4, 5e5]
    cb.set_ticks(tick_locs)
    cb.set_ticklabels([_fmt_delta(t).lstrip("+") for t in tick_locs])

    spec = style.FigSpec(width, height, "fig:preempt")
    w, h = style.save(fig, out / "Figure_14.pdf", spec)
    plt.close(fig)
    print(f"wrote {out / 'Figure_14.pdf'} ({w:.2f} x {h:.2f} in)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("campaign_dir", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    style.apply()
    base = args.campaign_dir
    args.out.mkdir(parents=True, exist_ok=True)

    tsv = base / "cross-deployment.tsv"
    df = pd.read_csv(tsv, sep="\t")
    for c in ("ratio", "ci_lo", "ci_hi", "cliffs_delta"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    cells = scan_cells(base)

    fig_availability(cells, args.out)
    fig_claimclass(df, args.out)
    fig_psi(cells, args.out)
    fig_membw(base, cells, args.out)
    fig_ratio(df, args.out)
    fig_preempt(df, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

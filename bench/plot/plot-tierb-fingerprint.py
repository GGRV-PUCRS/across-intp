#!/usr/bin/env python3
"""plot-tierb-fingerprint.py — F12: real-app 15-metric fingerprints are MIXED.

Consumes the analyzer TSV (bench/analyze-tierb.py, default
results/p2-tierb/fingerprints.tsv), NOT raw captures. Emits two figures, each as
PNG + PDF, under results/figures/p2-tierb-realapps/:

  F12-fingerprint        — per-metric-normalized heatmap (apps × 15 metrics,
                           grouped by resource class) for each variant on a host
                           env, plus a vm-guest panel: every real app lights up
                           several class blocks at once. Raw medians annotated.
  F12-class-activation    — the punchline: apps × 5 IADA classes (cpu/mem/cache/
                           disk/net) activation (absolute floors) + #classes —
                           no real app reduces to a single class.

    python3 bench/plot/plot-tierb-fingerprint.py [tsv] [--out DIR] [--env container]
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

# metric display order, grouped by IADA resource class (consumption metrics
# first within each class), then the cross-cutting scheduling-regime block.
CLASS_ORDER = ["cpu", "mem", "cache", "disk", "net", "regime"]
ORDER = ["cpu", "schedlat",            # cpu
         "mbw", "membw_est", "psi_mem",  # mem
         "llcmr", "llcocc",            # cache
         "blk", "psi_io",              # disk
         "netp", "nets",               # net
         "psp", "idle_preempt", "schedthr", "steal"]  # regime
# absolute noise floors (mirror analyze-tierb.py) for the activation panel
FLOOR = {"netp": 10, "nets": 10, "blk": 1, "mbw": 1, "llcmr": 5, "llcocc": 5,
         "cpu": 5, "schedlat": 5, "psi_mem": 1, "membw_est": 50, "psi_io": 1,
         "schedthr": 1, "steal": 1, "psp": 5, "idle_preempt": 50}
CLASS_METRICS = {"cpu": ["cpu", "schedlat"], "mem": ["mbw", "membw_est", "psi_mem"],
                 "cache": ["llcmr", "llcocc"], "disk": ["blk", "psi_io"],
                 "net": ["netp", "nets"]}
CLASS_COLOR = {"cpu": "#1f77b4", "mem": "#2ca02c", "cache": "#9467bd",
               "disk": "#8c564b", "net": "#d62728", "regime": "#7f7f7f"}


def load(tsv: Path):
    med = defaultdict(dict)     # (env,var,app) -> {metric: median}
    cls = {}                    # metric -> class
    apps, envs, variants = [], [], []
    with tsv.open() as fh:
        for r in csv.DictReader(fh, delimiter="\t"):
            e, v, a, m = r["env"], r["variant"], r["app"], r["metric"]
            cls[m] = r["class"]
            if r["median"] != "":
                med[(e, v, a)][m] = float(r["median"])
            for lst, x in ((apps, a), (envs, e), (variants, v)):
                if x not in lst:
                    lst.append(x)
    return med, cls, sorted(apps), envs, sorted(variants)


def save(fig, out: Path, name: str):
    p2_figio.save(fig, out, name, dpi=140)
    plt.close(fig)
    print(p2_figio.describe(out, name))


def short(a):
    return a.replace("app", "").replace("_", " ")


def is_low_drive(med, envs_show, variants, a):
    """App under-driven on every host env (cpu<5, no net, membw_est<50) — its low
    class-count is a load-gen artifact, flagged with ⚠ (mirrors analyze-tierb)."""
    hosts = [e for e in envs_show if e not in ("vm-guest", "vm")] or envs_show
    for e in hosts:
        for v in variants:
            g = med[(e, v, a)].get
            if (g("cpu") or 0) >= 5 or max(g("netp") or 0, g("nets") or 0) >= 10 \
               or (g("membw_est") or 0) >= 50:
                return False
    return True


def alabel(med, envs_show, variants, a):
    return short(a) + (" ⚠" if is_low_drive(med, envs_show, variants, a) else "")


_CLS = {}
def _class_of(m):
    return _CLS.get(m, "regime")


def _class_spans(metrics):
    """Yield (center_pos, class, left_idx, span) for each class block in order."""
    i = 0
    for c in CLASS_ORDER:
        ms = [m for m in metrics if _class_of(m) == c]
        if not ms:
            continue
        yield (i + len(ms) / 2 - 0.5, c, i, len(ms))
        i += len(ms)


def heatmap_panel(ax, med, key, apps, applabels, metrics, norm_max,
                  show_y, show_x, show_classlabels):
    """One env·variant heatmap: apps (rows) × metrics (cols). Colour normalized
    per metric to norm_max[metric] (env-scoped). Label visibility is controlled
    by the grid position so nothing overlaps: class labels only on the top row,
    metric ticks only on the bottom row, app ticks only on the left column."""
    env, var = key
    M = np.full((len(apps), len(metrics)), np.nan)
    raw = np.full((len(apps), len(metrics)), np.nan)
    for ri, a in enumerate(apps):
        for ci, m in enumerate(metrics):
            v = med[(env, var, a)].get(m)
            if v is None:
                continue
            raw[ri, ci] = v
            mx = norm_max.get(m, 0)
            M[ri, ci] = (abs(v) / mx) if mx > 0 else 0.0
    im = ax.imshow(M, aspect="auto", cmap="YlOrRd", vmin=0, vmax=1)
    ax.set_xticks(range(len(metrics)))
    ax.set_xticklabels(metrics if show_x else [""] * len(metrics),
                       rotation=90, fontsize=7)
    ax.set_yticks(range(len(apps)))
    ax.set_yticklabels(applabels if show_y else [""] * len(apps), fontsize=8)
    for ri in range(len(apps)):
        for ci in range(len(metrics)):
            if not np.isnan(raw[ri, ci]):
                txt = f"{raw[ri,ci]:.0f}" if abs(raw[ri, ci]) >= 1 else "0"
                ax.text(ci, ri, txt, ha="center", va="center", fontsize=6,
                        color="white" if M[ri, ci] > 0.6 else "black")
            else:
                ax.text(ci, ri, "—", ha="center", va="center", fontsize=6, color="grey")
    for _, c, left, span in _class_spans(metrics):
        if left > 0:
            ax.axvline(left - 0.5, color="black", lw=1.0)
    if show_classlabels:
        for pos, c, _, _ in _class_spans(metrics):
            ax.text(pos, -0.85, c, ha="center", va="bottom", fontsize=8,
                    color=CLASS_COLOR.get(c, "k"), fontweight="bold")
    return im


def fig_fingerprint(med, cls, apps, envs_show, variants, out):
    """2×2 (environment × variant) grid: each env is a row-band, each variant a
    column. Colour is normalized per (env, metric) so each environment band is
    internally comparable; raw medians annotated in every cell."""
    global _CLS
    _CLS = cls
    metrics = [m for m in ORDER if m in cls]
    # env-scoped per-metric normalization (both variants of an env share a scale)
    norm_max = {}
    for e in envs_show:
        for m in metrics:
            vals = [med[(e, v, a)].get(m) for v in variants for a in apps]
            norm_max[(e, m)] = max([abs(x) for x in vals if x is not None], default=0.0)
    applabels = [alabel(med, envs_show, variants, a) for a in apps]
    nr, nc = len(envs_show), len(variants)
    fig, axes = plt.subplots(nr, nc, squeeze=False,
                             figsize=(0.52 * len(metrics) * nc + 2.5, 2.6 * nr + 1.6))
    im = None
    for ri, e in enumerate(envs_show):
        for ci, v in enumerate(variants):
            ax = axes[ri][ci]
            nm = {m: norm_max[(e, m)] for m in metrics}
            im = heatmap_panel(ax, med, (e, v), apps, applabels, metrics, nm,
                               show_y=(ci == 0), show_x=(ri == nr - 1),
                               show_classlabels=(ri == 0))
            if ri == 0:                      # variant column header (above class row)
                ax.annotate(v, xy=(0.5, 1.16), xycoords="axes fraction",
                            ha="center", va="bottom", fontsize=12, fontweight="bold")
        # environment row label, left of the app ticks
        axes[ri][0].annotate(e, xy=(-0.42, 0.5), xycoords="axes fraction",
                             ha="center", va="center", rotation=90,
                             fontsize=12, fontweight="bold", color="#333333")
    cb = fig.colorbar(im, ax=axes, fraction=0.018, pad=0.02)
    cb.set_label("intensity (per metric, ÷ max across apps within environment)", fontsize=8)
    fig.suptitle("Real applications stress several resource classes at once when adequately driven\n"
                 "(rows = environment, columns = "
                 "profiler variant; cell = raw median; colour normalized per metric "
                 "within each environment; ⚠ = under-driven at the 1/3 footprint; "
                 "solo)", fontsize=11)
    fig.subplots_adjust(left=0.12, right=0.9, top=0.86, bottom=0.14,
                        hspace=0.30, wspace=0.06)
    save(fig, out, "F12-fingerprint")


def fig_activation(med, apps, envs_show, variants, out):
    """2×2 (environment × variant) grid of IADA-class activation. In vm-guest the
    fully-RDT metrics (mbw/llcocc) are blind, but the cache class survives via
    llcmr and the mem class via membw_est, so the class count is still fair."""
    classes = list(CLASS_METRICS)
    nr, nc = len(envs_show), len(variants)
    fig, axes = plt.subplots(nr, nc, squeeze=False,
                             figsize=(2.4 * nc + 2.0, 0.5 * len(apps) * nr + 1.8))
    for ri, e in enumerate(envs_show):
        for ci, var in enumerate(variants):
            ax = axes[ri][ci]
            M = np.zeros((len(apps), len(classes)))
            ncls = []
            for ai, a in enumerate(apps):
                cnt = 0
                for cj, c in enumerate(classes):
                    act = any((med[(e, var, a)].get(m) is not None
                               and abs(med[(e, var, a)][m]) >= FLOOR[m])
                              for m in CLASS_METRICS[c])
                    M[ai, cj] = 1.0 if act else 0.0
                    cnt += int(act)
                ncls.append(cnt)
            ax.imshow(M, aspect="auto", cmap="Greens", vmin=0, vmax=1.4)
            ax.set_xticks(range(len(classes)))
            ax.set_xticklabels(classes if ri == nr - 1 else [""] * len(classes),
                               fontsize=9, rotation=30, ha="right")
            ax.set_yticks(range(len(apps)))
            ax.set_yticklabels([alabel(med, envs_show, variants, a) for a in apps]
                               if ci == 0 else [""] * len(apps), fontsize=8)
            for ai in range(len(apps)):
                for cj in range(len(classes)):
                    ax.text(cj, ai, "✓" if M[ai, cj] else "·", ha="center",
                            va="center", fontsize=11,
                            color="white" if M[ai, cj] else "#999999")
            for ai, n in enumerate(ncls):
                ax.text(len(classes) - 0.3, ai, f" {n}", ha="left", va="center",
                        fontsize=9, fontweight="bold")
            ax.set_xlim(-0.5, len(classes) + 0.5)
            if ri == 0:
                ax.annotate(var, xy=(0.5, 1.08), xycoords="axes fraction",
                            ha="center", va="bottom", fontsize=12, fontweight="bold")
        axes[ri][0].annotate(e, xy=(-0.5, 0.5), xycoords="axes fraction",
                             ha="center", va="center", rotation=90,
                             fontsize=12, fontweight="bold", color="#333333")
    # Keep the longest line close to the pre-retitle width: the title is wider
    # than the axes, so it sets the tight-bbox width and hence the aspect the
    # seminar deck was laid out against.
    fig.suptitle("Every adequately-driven real application activates at least two IADA resource "
                 "classes, so a single-class label cannot describe it\n"
                 "(rows = environment, columns = profiler variant; ✓ = class active; "
                 "trailing number = classes activated; ⚠ = under-driven)", fontsize=10)
    fig.subplots_adjust(left=0.16, right=0.97, top=0.90, bottom=0.12,
                        hspace=0.22, wspace=0.08)
    save(fig, out, "F12-class-activation")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("tsv", nargs="?", type=Path,
                    default="results/p2-tierb/fingerprints.tsv")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--envs", default="container,vm-guest",
                    help="comma-separated environments to show as row-bands")
    args = ap.parse_args()
    med, cls, apps, envs, variants = load(args.tsv)
    want = [e.strip() for e in args.envs.split(",")]
    envs_show = [e for e in want if e in envs] or \
                [e for e in ("container", "vm-guest", "bare") if e in envs] or envs
    out = args.out or Path("results/figures/p2-tierb-realapps")
    out.mkdir(parents=True, exist_ok=True)
    fig_fingerprint(med, cls, apps, envs_show, variants, out)
    fig_activation(med, apps, envs_show, variants, out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

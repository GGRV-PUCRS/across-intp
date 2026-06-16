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
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
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
    for ext in ("png", "pdf"):
        fig.savefig(out / f"{name}.{ext}", dpi=140, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {out}/{name}.png + .pdf")


def short(a):
    return a.replace("app", "").replace("_", " ")


def heatmap_panel(ax, med, panels_apps, metrics, title, norm_max):
    """panels_apps: list of (label, (env,var)). One row per app, normalized per
    metric column to norm_max[metric]."""
    rows = [lab for lab, _ in panels_apps]
    M = np.full((len(rows), len(metrics)), np.nan)
    raw = np.full((len(rows), len(metrics)), np.nan)
    for ri, (_, key) in enumerate(panels_apps):
        for ci, m in enumerate(metrics):
            v = med[key].get(m)
            if v is None:
                continue
            raw[ri, ci] = v
            mx = norm_max.get(m, 0)
            M[ri, ci] = (abs(v) / mx) if mx > 0 else 0.0
    im = ax.imshow(M, aspect="auto", cmap="YlOrRd", vmin=0, vmax=1)
    ax.set_xticks(range(len(metrics)))
    ax.set_xticklabels(metrics, rotation=90, fontsize=7)
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels(rows, fontsize=8)
    for ri in range(len(rows)):
        for ci in range(len(metrics)):
            if not np.isnan(raw[ri, ci]):
                txt = f"{raw[ri,ci]:.0f}" if abs(raw[ri, ci]) >= 1 else "0"
                ax.text(ci, ri, txt, ha="center", va="center", fontsize=6,
                        color="white" if M[ri, ci] > 0.6 else "black")
            else:
                ax.text(ci, ri, "—", ha="center", va="center", fontsize=6, color="grey")
    # class separators + colored class labels along the top
    boundaries, pos, lab = [], [], []
    i = 0
    for c in CLASS_ORDER:
        ms = [m for m in metrics if m in [x for x in ORDER] and _class_of(m) == c]
        if not ms:
            continue
        span = len(ms)
        pos.append(i + span / 2 - 0.5); lab.append(c)
        i += span
        if i < len(metrics):
            ax.axvline(i - 0.5, color="black", lw=1.0)
    for p, c in zip(pos, lab):
        ax.text(p, -0.9, c, ha="center", va="bottom", fontsize=8,
                color=CLASS_COLOR.get(c, "k"), fontweight="bold")
    ax.set_title(title, fontsize=10, pad=18)
    return im


_CLS = {}
def _class_of(m):
    return _CLS.get(m, "regime")


def fig_fingerprint(med, cls, apps, host_env, variants, out, ge):
    global _CLS
    _CLS = cls
    metrics = [m for m in ORDER if m in cls]
    # per-metric normalization max over the host-env apps of BOTH variants
    norm_max = {}
    for m in metrics:
        vals = [med[(host_env, v, a)].get(m) for v in variants for a in apps]
        norm_max[m] = max([abs(x) for x in vals if x is not None], default=0.0)
    panels = [(f"{host_env} · {v}", v) for v in variants]
    if ge:
        panels.append((f"{ge} · {variants[-1]}", (ge, variants[-1])))
    n = len(panels)
    fig, axes = plt.subplots(n, 1, figsize=(0.55 * len(metrics) + 3, 2.4 * n + 1.2))
    if n == 1:
        axes = [axes]
    im = None
    for ax, (lab, key) in zip(axes, panels):
        ev = key if isinstance(key, tuple) else (host_env, key)
        papps = [(short(a), (ev[0], ev[1], a)) for a in apps]
        im = heatmap_panel(ax, med, papps, metrics, lab, norm_max)
    cb = fig.colorbar(im, ax=axes, fraction=0.025, pad=0.02)
    cb.set_label("intensity (per-metric, ÷ max across apps)", fontsize=8)
    fig.suptitle("F12 — real-application 15-metric fingerprints are MIXED across "
                 "resource classes\n(cell = raw median; column-normalized colour; "
                 "1/3 footprint, solo)", fontsize=11)
    save(fig, out, "F12-fingerprint")


def fig_activation(med, apps, host_env, variants, out):
    classes = list(CLASS_METRICS)
    fig, axes = plt.subplots(1, len(variants),
                             figsize=(2.2 * len(variants) + 2.5, 0.5 * len(apps) + 2))
    if len(variants) == 1:
        axes = [axes]
    for ax, var in zip(axes, variants):
        M = np.zeros((len(apps), len(classes)))
        ncls = []
        for ri, a in enumerate(apps):
            cnt = 0
            for ci, c in enumerate(classes):
                act = any((med[(host_env, var, a)].get(m) is not None
                           and abs(med[(host_env, var, a)][m]) >= FLOOR[m])
                          for m in CLASS_METRICS[c])
                M[ri, ci] = 1.0 if act else 0.0
                cnt += int(act)
            ncls.append(cnt)
        ax.imshow(M, aspect="auto", cmap="Greens", vmin=0, vmax=1.4)
        ax.set_xticks(range(len(classes)))
        ax.set_xticklabels(classes, fontsize=9, rotation=30, ha="right")
        ax.set_yticks(range(len(apps)))
        ax.set_yticklabels([short(a) for a in apps], fontsize=8)
        for ri in range(len(apps)):
            for ci in range(len(classes)):
                ax.text(ci, ri, "✓" if M[ri, ci] else "·", ha="center",
                        va="center", fontsize=11,
                        color="white" if M[ri, ci] else "#999999")
        # #classes annotation on the right
        for ri, n in enumerate(ncls):
            ax.text(len(classes) - 0.3, ri, f"  → {n}", ha="left", va="center",
                    fontsize=9, fontweight="bold")
        ax.set_title(f"{host_env} · {var}", fontsize=10)
        ax.set_xlim(-0.5, len(classes) + 0.6)
    fig.suptitle("F12 — IADA resource-class activation (absolute floors): no real "
                 "app reduces to one class\n(→N = number of classes activated)",
                 fontsize=10)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    save(fig, out, "F12-class-activation")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("tsv", nargs="?", type=Path,
                    default="results/p2-tierb/fingerprints.tsv")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--env", default="container", help="host env for the panels")
    args = ap.parse_args()
    med, cls, apps, envs, variants = load(args.tsv)
    host_env = args.env if args.env in envs else ("container" if "container" in envs else envs[0])
    ge = "vm-guest" if "vm-guest" in envs else ("vm" if "vm" in envs else None)
    out = args.out or Path("results/figures/p2-tierb-realapps")
    out.mkdir(parents=True, exist_ok=True)
    fig_fingerprint(med, cls, apps, host_env, variants, out, ge)
    fig_activation(med, apps, host_env, variants, out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

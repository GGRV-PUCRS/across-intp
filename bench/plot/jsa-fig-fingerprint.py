#!/usr/bin/env python3
"""jsa-fig-fingerprint.py -- JSA print of Figure_10 (fig:fingerprint), the
15-metric real-app fingerprint combining Tier-B (Redis, CloudSuite) and
Tier-C (DeathStarBench) apps, plus two additive options:

  Figure_10.pdf                 primary redraw (same content/statistics as
                                 plot-tierb-fingerprint.py's F12-fingerprint;
                                 load() copied verbatim from there)
  Figure_10_v2.pdf               the same fingerprint split into two stacked
                                 panels (grayscale-print-safe alternative)
  Figure_10_smallmultiples_v1.pdf small multiples per deployment (bare /
                                 container / vm-guest), one more fallback if
                                 the single/split cuts still read poorly in
                                 grayscale

Fix over the original: "unavailable" cells were previously blank (NaN -> no
imshow fill) with a grey em-dash overlaid -- indistinguishable in print from
a genuinely low-but-present cell at the pale end of the sequential colormap.
Here unavailable cells get an explicit mid-grey fill plus a diagonal hatch,
and the intensity scale uses viridis (perceptually uniform, colorblind-safe)
so grey reads as a third, distinct channel rather than "very light yellow".

    python3 jsa-fig-fingerprint.py [tsv] --out DIR
"""
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import numpy as np

import jsa_style as style

CLASS_ORDER = ["cpu", "mem", "cache", "disk", "net", "regime"]
ORDER = ["cpu", "schedlat",
         "mbw", "membw_est", "psi_mem",
         "llcmr", "llcocc",
         "blk", "psi_io",
         "netp", "nets",
         "psp", "idle_preempt", "schedthr", "steal"]
CLASS_COLOR = {"cpu": style.BLUE, "mem": style.BLUISH_GREEN,
               "cache": style.REDDISH_PURPLE, "disk": style.VERMILLION,
               "net": style.ORANGE, "regime": "#555555"}
CMAP = "viridis"


def load(tsv: Path):
    med = defaultdict(dict)
    cls = {}
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


def short(a: str) -> str:
    return a.replace("app", "").replace("_", " ")


def _class_spans(metrics, cls):
    i = 0
    for c in CLASS_ORDER:
        ms = [m for m in metrics if cls.get(m, "regime") == c]
        if not ms:
            continue
        yield (i + len(ms) / 2 - 0.5, c, i, len(ms))
        i += len(ms)


# Regime counts run into the tens of thousands (events/s) while every other
# column is a 0-3 digit percent-of-max -- a uniform grid gives them the same
# cell width and their digits collide with the neighboring cell. These two
# columns get extra width (WIDE_COL_METRICS) and their values are abbreviated
# with a k-suffix; every other column keeps its original share.
WIDE_COL_METRICS = {"psp", "idle_preempt"}
WIDE_COL_WEIGHT = 2.3


def _fmt_count(v: float) -> str:
    a = abs(v)
    if a >= 10000:
        return f"{v/1000:.0f}k"
    if a >= 1000:
        return f"{v/1000:.1f}k"
    if a >= 1:
        return f"{v:.0f}"
    return "0"


def _col_edges(metrics):
    """Cumulative x-edges giving WIDE_COL_METRICS extra width; total span
    stays len(metrics) (starting at -0.5, as the original uniform grid did),
    so the panel's overall footprint is unchanged -- only the per-column
    share shifts."""
    weights = [WIDE_COL_WEIGHT if m in WIDE_COL_METRICS else 1.0
              for m in metrics]
    scale = len(metrics) / sum(weights)
    edges = [-0.5]
    for w in weights:
        edges.append(edges[-1] + w * scale)
    return np.array(edges)


def heatmap_panel(ax, med, key, apps, metrics, cls, norm_max, *,
                  show_y, show_x, show_classlabels, applabels=None):
    env, var = key
    applabels = applabels or [short(a) for a in apps]
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

    xedges = _col_edges(metrics)
    yedges = np.arange(len(apps) + 1) - 0.5
    im = ax.pcolormesh(xedges, yedges, M, cmap=CMAP, vmin=0, vmax=1,
                       shading="flat")
    xcenters = (xedges[:-1] + xedges[1:]) / 2
    colw = np.diff(xedges)
    for ri in range(len(apps)):
        for ci in range(len(metrics)):
            x0, x1 = xedges[ci], xedges[ci + 1]
            if np.isnan(raw[ri, ci]):
                # Unavailable: explicit grey fill + hatch, distinct from any
                # point on the viridis scale -- not just a pale/blank cell.
                ax.add_patch(Rectangle(
                    (x0, ri - 0.5), x1 - x0, 1, facecolor=style.GREY,
                    edgecolor="white", hatch="////", linewidth=0.4,
                    zorder=2))
            else:
                txt = _fmt_count(raw[ri, ci])
                fs = (style.ANNOT - 0.5 if metrics[ci] not in WIDE_COL_METRICS
                     else style.ANNOT - 0.2)
                ax.text(xcenters[ci], ri, txt, ha="center", va="center",
                       fontsize=fs,
                       color="white" if M[ri, ci] > 0.55 else "black",
                       zorder=3)
    ax.set_xticks(xcenters)
    ax.set_xticklabels(metrics if show_x else [""] * len(metrics),
                       rotation=90, fontsize=style.ANNOT)
    ax.set_yticks(range(len(apps)))
    ax.set_yticklabels(applabels if show_y else [""] * len(apps),
                       fontsize=style.BODY)
    for _, c, left, span in _class_spans(metrics, cls):
        if left > 0:
            ax.axvline(xedges[left], color=style.BLACK, lw=0.8, zorder=4)
    if show_classlabels:
        for pos, c, left, span in _class_spans(metrics, cls):
            cx = (xedges[left] + xedges[left + span]) / 2
            ax.text(cx, -0.9, c, ha="center", va="bottom",
                   fontsize=style.ANNOT, color=CLASS_COLOR.get(c, "k"),
                   fontweight="bold")
    ax.set_xlim(xedges[0], xedges[-1])
    ax.set_ylim(len(apps) - 0.5, -0.5)
    return im


def norm_for_envs(med, envs_show, variants, apps, metrics):
    norm_max = {}
    for e in envs_show:
        for m in metrics:
            vals = [med[(e, v, a)].get(m) for v in variants for a in apps]
            norm_max[(e, m)] = max([abs(x) for x in vals if x is not None],
                                   default=0.0)
    return norm_max


def render_grid(med, cls, apps, envs_show, variants, metrics, *,
                width, row_h, out_path, label):
    style.apply()
    nr, nc = len(envs_show), len(variants)
    norm_max = norm_for_envs(med, envs_show, variants, apps, metrics)
    fig, axes = plt.subplots(nr, nc, squeeze=False,
                             figsize=(width, row_h * nr + 1.0),
                             layout="constrained")
    im = None
    for ri, e in enumerate(envs_show):
        for ci, v in enumerate(variants):
            ax = axes[ri][ci]
            ax.grid(False)
            nm = {m: norm_max[(e, m)] for m in metrics}
            im = heatmap_panel(ax, med, (e, v), apps, metrics, cls, nm,
                               show_y=(ci == 0), show_x=(ri == nr - 1),
                               show_classlabels=(ri == 0))
            if ri == 0:
                ax.annotate(v, xy=(0.5, 1.20), xycoords="axes fraction",
                           ha="center", va="bottom", fontsize=style.TITLE,
                           fontweight="bold")
        axes[ri][0].annotate(e, xy=(-0.48, 0.5), xycoords="axes fraction",
                            ha="center", va="center", rotation=90,
                            fontsize=style.TITLE, fontweight="bold")
    cb = fig.colorbar(im, ax=axes, shrink=0.7, pad=0.012, aspect=25)
    cb.set_label("intensity (÷ max within environment)",
                 fontsize=style.ANNOT)
    cb.ax.tick_params(labelsize=style.ANNOT)
    # Legend for the "unavailable" hatch -- direct labeling (the hatch
    # pattern) can't say what grey *means* on its own.
    unavail = Rectangle((0, 0), 1, 1, facecolor=style.GREY,
                        edgecolor="white", hatch="////", label="unavailable")
    fig.legend(handles=[unavail], loc="outside lower center", ncol=1,
              fontsize=style.LEGEND, frameon=False)

    spec = style.FigSpec(width, row_h * nr + 1.0, label)
    w, h = style.save(fig, out_path, spec)
    plt.close(fig)
    print(f"wrote {out_path} ({w:.2f} x {h:.2f} in)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("tsv", nargs="?", type=Path,
                    default="results/p2-realapps-combined/fingerprints.tsv")
    ap.add_argument("--out", type=Path,
                    default=Path("/mnt/c/Users/sacil/Downloads/figs"))
    ap.add_argument("--envs", default="container,vm-guest")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    med, cls, apps, envs, variants = load(args.tsv)
    want = [e.strip() for e in args.envs.split(",")]
    envs_show = [e for e in want if e in envs] or envs
    metrics = [m for m in ORDER if m in cls]

    # Primary: full grid, one figure -- same (env, variant) cut as the
    # banked figure (container, vm-guest x v2.1, v3.3).
    render_grid(med, cls, apps, envs_show, variants, metrics,
               width=style.TEXT_WIDTH, row_h=1.55,
               out_path=args.out / "Figure_10.pdf", label="fig:fingerprint")

    # _v2: the ground rule's "split, don't replace" option -- the same two
    # env-bands as two SEPARATE floats instead of one crowded figure, each
    # full width so its own class labels and annotations get more room.
    # Suggested pairing: two \begin{figure} blocks, labels fig:fingerprint-a
    # (container) and fig:fingerprint-b (vm-guest), captions splitting the
    # existing fig:fingerprint caption's sentences by panel.
    for tag, e in zip("ab", envs_show):
        render_grid(med, cls, apps, [e], variants, metrics,
                   width=style.TEXT_WIDTH, row_h=1.9,
                   out_path=args.out / f"Figure_10_v2{tag}.pdf",
                   label=f"fig:fingerprint-{tag} ({e})")

    # Small multiples: brief item 4 explicitly names bare/container/guest,
    # a wider cut than the primary figure's (container, vm-guest) -- kept
    # as a distinct additive option, not a silent change to the primary.
    sm_envs = [e for e in ("bare", "container", "vm-guest") if e in envs]
    for e in sm_envs:
        render_grid(med, cls, apps, [e], variants, metrics,
                   width=style.TEXT_WIDTH, row_h=1.65,
                   out_path=args.out / f"Figure_10_smallmultiples_v1_{e}.pdf",
                   label=f"fig:fingerprint (small multiples, {e})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

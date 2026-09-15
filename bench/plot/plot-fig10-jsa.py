#!/usr/bin/env python3
"""plot-fig10-jsa.py -- JSA redraw of fig:fingerprint (Figure_10), the
15-metric real-application fingerprint (F12 in docs/FIGURES-PLAN.md).

Same source of record and aggregation as plot-tierb-fingerprint.py's
fig_fingerprint() (kept here rather than imported -- that script's filename
is not a valid Python module name): the per-(env,variant,app,metric) medians
in results/p2-realapps-combined/fingerprints.tsv, normalized per (env,
metric) across apps -- no statistic recomputed.

Fix from the brief: the "metric unavailable in this deployment" grey must be
visually distinct in print from a low-activation-strength cell. The original
YlOrRd colormap's low end is near-white, which is easy to confuse with an
unpainted (NaN) cell at a glance. Here the sequential colormap's floor is
lifted (vmin offset) so even the faintest *present* reading is a visible
tint, and every unavailable cell is filled flat mid-grey with a diagonal
hatch plus a centered "unavailable" glyph -- three redundant cues (fill,
hatch, text) so it survives grayscale conversion and color-vision deficiency
alike.

Emits:
  Figure_10.pdf    -- the combined heatmap (all 5 apps, container + vm-guest
                       row-bands x both variants), matching the manuscript.
  Figure_10_v2.pdf -- additive split variant: two stacked panels, Tier-B real
                       apps (redis, data-caching, web-search,
                       in-memory-analytics) above Tier-C DeathStarBench, so
                       the figure holds up at a narrower column width or in
                       grayscale print. Suggested label: fig:fingerprint-split.
"""
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
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
               "cache": style.REDDISH_PURPLE, "disk": style.ORANGE,
               "net": style.VERMILLION, "regime": "#555555"}

TIER_B = ["app18_redis_kv", "app19_cs_datacaching", "app20_cs_websearch",
          "app21_cs_imanalytics"]
TIER_C = ["app22_dsb_socialnet"]

# Sequential colormap whose floor is a visible tint, not near-white, so a
# present-but-low-activation cell never reads as "no data" the way NaN does.
_CMAP = mcolors.LinearSegmentedColormap.from_list(
    "jsa_seq", ["#fff0cc", style.ORANGE, "#7a2e00"])


def load(tsv: Path):
    med = defaultdict(dict)
    cls = {}
    apps, envs, variants = [], [], []
    for r in csv.DictReader(tsv.open(), delimiter="\t"):
        e, v, a, m = r["env"], r["variant"], r["app"], r["metric"]
        cls[m] = r["class"]
        if r["median"] != "":
            med[(e, v, a)][m] = float(r["median"])
        for lst, x in ((apps, a), (envs, e), (variants, v)):
            if x not in lst:
                lst.append(x)
    return med, cls, apps, envs, sorted(variants)


def short(a: str) -> str:
    return a.replace("app", "").replace("_", " ")


def _fmt(v: float) -> str:
    """Compact cell annotation: full precision under 10k, "N.Nk" above --
    values like 70946 otherwise overflow the narrow heatmap cell width and
    visually bleed into the neighboring column."""
    av = abs(v)
    if av < 1:
        return "0"
    if av >= 10000:
        return f"{v/1000:.1f}k"
    return f"{v:.0f}"


def class_spans(metrics, cls):
    i = 0
    for c in CLASS_ORDER:
        ms = [m for m in metrics if cls.get(m, "regime") == c]
        if not ms:
            continue
        yield (i + len(ms) / 2 - 0.5, c, i, len(ms))
        i += len(ms)


def heatmap_panel(ax, med, key, apps, metrics, cls, norm_max,
                   show_y, show_x, show_classlabels):
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

    ax.imshow(M, aspect="auto", cmap=_CMAP, vmin=0, vmax=1)
    # Unavailable cells: flat grey + hatch + label, three redundant cues.
    for ri in range(len(apps)):
        for ci in range(len(metrics)):
            if np.isnan(raw[ri, ci]):
                ax.add_patch(plt.Rectangle(
                    (ci - 0.5, ri - 0.5), 1, 1, facecolor=style.GREY,
                    edgecolor="white", linewidth=0.4, hatch="////",
                    zorder=2))
                ax.text(ci, ri, "–", ha="center", va="center",
                        fontsize=style.ANNOT, color="white", zorder=3)
            else:
                txt = _fmt(raw[ri, ci])
                ax.text(ci, ri, txt, ha="center", va="center",
                        fontsize=style.ANNOT - 0.5 if len(txt) <= 4
                        else style.ANNOT - 1.0,
                        color="white" if M[ri, ci] > 0.55 else "black",
                        zorder=3)
    ax.set_xticks(range(len(metrics)))
    ax.set_xticklabels(metrics if show_x else [""] * len(metrics),
                        rotation=90, fontsize=style.ANNOT)
    ax.set_yticks(range(len(apps)))
    ax.set_yticklabels([short(a) for a in apps] if show_y else [""] * len(apps),
                        fontsize=style.BODY)
    for _, _c, left, _span in class_spans(metrics, cls):
        if left > 0:
            ax.axvline(left - 0.5, color="black", lw=0.8, zorder=4)
    if show_classlabels:
        for pos, c, _, _ in class_spans(metrics, cls):
            ax.text(pos, -1.35, c, ha="center", va="bottom",
                    fontsize=style.ANNOT, color=CLASS_COLOR.get(c, "k"),
                    fontweight="bold")


def _draw_group(fig, axes, med, cls, apps, envs_show, variants,
                 group_title: str):
    """Draw one env x variant heatmap grid into a pre-made axes array
    (rows=envs_show, cols=variants). Headers use fig.text at explicit
    figure-fraction coordinates (derived from each axes' own bbox) rather
    than axes-fraction annotate, which does not compose across independent
    subplot groups sharing one figure."""
    metrics = [m for m in ORDER if m in cls]
    norm_max = {}
    for e in envs_show:
        for m in metrics:
            vals = [med[(e, v, a)].get(m) for v in variants for a in apps]
            norm_max[(e, m)] = max([abs(x) for x in vals if x is not None],
                                    default=0.0)
    nr, nc = len(envs_show), len(variants)
    for ri, e in enumerate(envs_show):
        for ci, v in enumerate(variants):
            ax = axes[ri][ci]
            nm = {m: norm_max[(e, m)] for m in metrics}
            heatmap_panel(ax, med, (e, v), apps, metrics, cls, nm,
                          show_y=(ci == 0), show_x=(ri == nr - 1),
                          show_classlabels=(ri == 0))

    fig.canvas.draw()
    fig_h_in = fig.get_figheight()
    fig_w_in = fig.get_figwidth()
    dy_title = 0.34 / fig_h_in      # inches -> figure fraction, height-independent
    dy_var = 0.14 / fig_h_in
    dx_env = 0.42 / fig_w_in
    top_left = axes[0][0].get_position()
    fig.text(top_left.x0, top_left.y1 + dy_title, group_title,
              ha="left", va="bottom", fontsize=style.TITLE, fontweight="bold")
    for ci, v in enumerate(variants):
        pos = axes[0][ci].get_position()
        fig.text((pos.x0 + pos.x1) / 2, pos.y1 + dy_var, v, ha="center",
                  va="bottom", fontsize=style.TITLE, fontweight="bold")
    for ri, e in enumerate(envs_show):
        pos = axes[ri][0].get_position()
        fig.text(pos.x0 - dx_env, (pos.y0 + pos.y1) / 2, e, ha="center",
                  va="center", rotation=90, fontsize=style.TITLE,
                  fontweight="bold", color="#333333")


def render(med, cls, apps, envs_show, variants, out_path: Path,
           width: float, height: float, label: str):
    nr, nc = len(envs_show), len(variants)
    fig, axes = plt.subplots(nr, nc, squeeze=False, figsize=(width, height))
    fig.subplots_adjust(left=0.105, right=0.955, top=0.82, bottom=0.16,
                         hspace=0.34, wspace=0.06)
    _draw_group(fig, axes, med, cls, apps, envs_show, variants, "")

    handles = [plt.Rectangle((0, 0), 1, 1, fc=style.GREY, hatch="////",
                              ec="white", label="unavailable in deployment")]
    fig.legend(handles=handles, loc="lower center", ncol=1, frameon=False,
               fontsize=style.LEGEND, handlelength=1.4,
               bbox_to_anchor=(0.5, 0.0))

    spec = style.FigSpec(width, height, label)
    w, h = style.save(fig, out_path, spec)
    plt.close(fig)
    print(f"wrote {out_path} ({w:.2f} x {h:.2f} in)")


def render_split(med, cls, apps_top, apps_bot, envs_show, variants,
                  out_path: Path, width: float):
    """Figure_10_v2: Tier-B (top) and Tier-C (bottom) as one stacked figure,
    two independent subplot grids on one figure with explicit height
    fractions (row count proportional, plus fixed per-group header/margin
    budgets) rather than constrained_layout, which does not coordinate two
    unrelated subplot groups sharing a figure."""
    nr_t, nr_b, nc = len(envs_show), len(envs_show), len(variants)
    row_in = 0.62                      # inches per app row
    # header_in is a one-time cost per group (title + variant header + class
    # row, drawn once above that group's own first subplot row -- reserved
    # explicitly in the group's own top boundary, not borrowed from the
    # inter-group gap). row_gap_in covers hspace between stacked env-rows.
    header_in, row_gap_in = 1.0, 0.30
    gap_in = 0.5                        # pure whitespace between groups
    margin_top_in, margin_bot_in = 0.15, 1.0
    top_axes_h = nr_t * len(apps_top) * row_in + (nr_t - 1) * row_gap_in
    bot_axes_h = nr_b * len(apps_bot) * row_in + (nr_b - 1) * row_gap_in
    height = (margin_top_in + header_in + top_axes_h + gap_in +
              header_in + bot_axes_h + margin_bot_in)

    # Absolute inch boundaries, top of figure downward.
    y = height - margin_top_in
    y -= header_in
    top_axes_top = y
    y -= top_axes_h
    top_axes_bot = y
    y -= gap_in
    y -= header_in
    bot_axes_top = y
    y -= bot_axes_h
    bot_axes_bot = y

    fig = plt.figure(figsize=(width, height))
    gs_top = fig.add_gridspec(nr_t, nc, left=0.105, right=0.955,
                               top=top_axes_top / height,
                               bottom=top_axes_bot / height,
                               hspace=0.55, wspace=0.06)
    gs_bot = fig.add_gridspec(nr_b, nc, left=0.105, right=0.955,
                               top=bot_axes_top / height,
                               bottom=bot_axes_bot / height,
                               hspace=0.9, wspace=0.06)
    axes_top = [[fig.add_subplot(gs_top[r, c]) for c in range(nc)]
                for r in range(nr_t)]
    axes_bot = [[fig.add_subplot(gs_bot[r, c]) for c in range(nc)]
                for r in range(nr_b)]

    _draw_group(fig, axes_top, med, cls, apps_top, envs_show, variants,
                "Tier-B: real applications")
    _draw_group(fig, axes_bot, med, cls, apps_bot, envs_show, variants,
                "Tier-C: DeathStarBench (microservices)")

    handles = [plt.Rectangle((0, 0), 1, 1, fc=style.GREY, hatch="////",
                              ec="white", label="unavailable in deployment")]
    fig.legend(handles=handles, loc="lower center", ncol=1, frameon=False,
               fontsize=style.LEGEND, handlelength=1.4,
               bbox_to_anchor=(0.5, 0.0))

    spec = style.FigSpec(width, height, "fig:fingerprint-split")
    w, h = style.save(fig, out_path, spec)
    plt.close(fig)
    print(f"wrote {out_path} ({w:.2f} x {h:.2f} in)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("tsv", nargs="?", type=Path,
                     default=Path("results/p2-realapps-combined/"
                                  "fingerprints.tsv"))
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--envs", default="container,vm-guest")
    args = ap.parse_args()

    style.apply()
    med, cls, apps_seen, envs, variants = load(args.tsv)
    envs_show = [e for e in args.envs.split(",") if e in envs]
    args.out.mkdir(parents=True, exist_ok=True)

    apps_all = [a for a in TIER_B + TIER_C if a in apps_seen]
    render(med, cls, apps_all, envs_show, variants,
           args.out / "Figure_10.pdf", style.TEXT_WIDTH, 5.6, "fig:fingerprint")

    tb = [a for a in TIER_B if a in apps_seen]
    tc = [a for a in TIER_C if a in apps_seen]
    render_split(med, cls, tb, tc, envs_show, variants,
                 args.out / "Figure_10_v2.pdf", style.TEXT_WIDTH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

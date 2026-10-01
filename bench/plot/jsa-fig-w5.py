#!/usr/bin/env python3
"""jsa-fig-w5.py -- JSA prints of Figure_11 (fig:victim) and Figure_12
(fig:vmproxy), redrawn from the same W5 victim-delta TSV as
plot-w5-victim-delta.py's F10/F11 (load()/agg() copied verbatim from there;
this file only changes typography, layout and annotation, never the
statistics).

Figure_11 (fig:victim): forest plot, one panel per environment, Cliff's delta
of each metric under a noisy neighbour vs solo. delta=1.0 (saturated) points
get a black ring halo in addition to their fill, so the saturated cells stay
distinguishable in a grayscale render, not just by color intensity.

Figure_12 (fig:vmproxy): the vm-guest paired before/after (solo vs
colocated) medians for the canonical RDT metrics (unavailable) against the
portable proxies (still see the contention), guest panel visually emphasized.

    python3 jsa-fig-w5.py [tsv] --out DIR
"""
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path
from statistics import median

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import jsa_style as style

ORDER = ["netp", "nets", "blk", "mbw", "llcmr", "llcocc", "cpu",
         "schedlat", "psi_mem", "membw_est", "psi_io", "schedthr", "steal",
         "psp", "idle_preempt"]
CANON = {"netp", "nets", "blk", "mbw", "llcmr", "llcocc", "cpu"}
PORTABLE = {"schedlat", "psi_mem", "membw_est", "psi_io", "schedthr", "steal"}
GUARD = {"schedthr", "steal"}
ENVS = ["bare", "container", "vm-guest"]
NEGLIGIBLE = 0.147
SIG = {"-", "n/a", ""}
SATURATED = 0.98

GROUP_COLOR = {"guard": style.VERMILLION, "portable": style.BLUISH_GREEN,
               "canon": style.BLUE}


def group_of(m: str) -> str:
    return "guard" if m in GUARD else "portable" if m in PORTABLE else "canon"


def load(tsv: Path):
    cells = defaultdict(list)
    present = defaultdict(set)
    variants = set()
    for r in csv.DictReader(tsv.open(), delimiter="\t"):
        env, var, m = r["env"], r["variant"], r["metric"]
        variants.add(var)
        present[env].add(m)
        try:
            cd = float(r["cliffs_delta"])
        except ValueError:
            continue
        cells[(env, var, m)].append((cd, r["signif"] not in SIG))
    return cells, present, sorted(variants)


def agg(cells, env, var, m):
    xs = cells.get((env, var, m))
    if not xs:
        return None
    return median(c for c, _ in xs), sum(s for _, s in xs) / len(xs)


def fig_11_forest(cells, present, variants, out: Path) -> None:
    metrics = [m for m in ORDER if any(m in present[e] for e in ENVS)]
    envs = [e for e in ENVS if e in present]
    style.apply()
    fig, axes = plt.subplots(1, len(envs),
                             figsize=(style.TEXT_WIDTH, 3.6),
                             sharey=True, squeeze=False, layout="constrained")
    axes = axes[0]
    y = {m: i for i, m in enumerate(reversed(metrics))}
    for ax, env in zip(axes, envs):
        ax.grid(False)
        ax.axvspan(-NEGLIGIBLE, NEGLIGIBLE, color=style.GREY, alpha=0.15,
                   zorder=0)
        ax.axvline(0, color=style.GREY, lw=0.6, zorder=1)
        for m in metrics:
            yc = y[m]
            col = GROUP_COLOR[group_of(m)]
            for var in variants:
                a = agg(cells, env, var, m)
                if a is None:
                    if m not in present[env]:
                        ax.text(0, yc, "n/a (RDT)"
                                if m in {"mbw", "llcocc", "llcmr"} else "—",
                                fontsize=style.ANNOT, color=style.GREY,
                                ha="center", va="center")
                    continue
                cd, fs = a
                off = 0.16 if var == variants[0] else -0.16
                mk = style.VARIANT_MARKER.get(var, "o")
                if abs(cd) >= SATURATED:
                    # Saturated-cell halo: a plain black ring behind the
                    # marker, visible whether or not color survives print.
                    ax.plot(cd, yc + off, "o", ms=10, mfc="none",
                            mec=style.BLACK, mew=1.4, zorder=2.5)
                ax.plot(cd, yc + off, mk, ms=5.5, color=col,
                        mfc=(col if fs >= 0.5 else "white"), mec=col,
                        mew=1.1, zorder=3)
        ax.set_xlim(-1.15, 1.15)
        ax.set_title(env, fontsize=style.TITLE)
        ax.set_xlabel("Cliff's $\\delta$ (pairwise − solo)")
    axes[0].set_yticks(range(len(metrics)))
    axes[0].set_yticklabels([m for m in reversed(metrics)], fontsize=style.BODY)
    for t, m in zip(axes[0].get_yticklabels(), reversed(metrics)):
        t.set_color(GROUP_COLOR[group_of(m)])

    handles = [
        plt.Line2D([0], [0], marker="o", color=GROUP_COLOR["canon"], ls="",
                   label="canonical-7"),
        plt.Line2D([0], [0], marker="o", color=GROUP_COLOR["portable"], ls="",
                   label="portable"),
        plt.Line2D([0], [0], marker="o", color=GROUP_COLOR["guard"], ls="",
                   label="guard (expect flat)"),
        plt.Line2D([0], [0], marker="o", color=style.BLACK, mfc=style.BLACK,
                   ls="", label="majority signif. (filled)"),
        plt.Line2D([0], [0], marker="o", color=style.BLACK, mfc="white",
                   ls="", label="not signif. (open)"),
        plt.Line2D([0], [0], marker="o", color=style.BLACK, mfc="none",
                   mew=1.4, ms=8, ls="", label="saturated $|\\delta|\\geq 0.98$"),
    ]
    if len(variants) > 1:
        handles += [
            plt.Line2D([0], [0], marker=style.VARIANT_MARKER[variants[0]],
                       color=style.BLACK, ls="", label=variants[0]),
            plt.Line2D([0], [0], marker=style.VARIANT_MARKER[variants[1]],
                       color=style.BLACK, ls="", label=variants[1]),
        ]
    fig.legend(handles=handles, loc="outside lower center",
              ncol=4, fontsize=style.LEGEND, frameon=False,
              handlelength=1.1, handletextpad=0.4, columnspacing=0.9)

    spec = style.FigSpec(style.TEXT_WIDTH, 3.6, "fig:victim")
    path = out / "Figure_11.pdf"
    w, h = style.save(fig, path, spec)
    plt.close(fig)
    print(f"wrote {path} ({w:.2f} x {h:.2f} in)")


def fig_12_vmguest_paired(cells, present, variants, out: Path) -> None:
    """Paired before/after (solo vs colocated) medians, vm-guest emphasized.

    Left: bare + container (host envs), collapsed to one summary strip each,
    for scale reference. Right (wider, shaded panel): vm-guest, the punchline
    -- canonical RDT reads n/a while membw_est/psi_mem/schedlat/psi_io still
    move.
    """
    style.apply()
    groups = [("canonical RDT\n(mem / cache)", ["mbw", "llcocc", "llcmr"]),
              ("portable proxies", ["membw_est", "psi_mem", "schedlat",
                                     "psi_io"])]
    all_metrics = [m for _, ms in groups for m in ms]

    fig = plt.figure(figsize=(style.TEXT_WIDTH, 2.9), layout="constrained")
    gs = fig.add_gridspec(1, 3, width_ratios=[1, 1, 1.6])
    axes = [fig.add_subplot(gs[0, i]) for i in range(3)]
    envs_shown = [e for e in ("bare", "container", "vm-guest") if e in present]

    for ax, env in zip(axes, envs_shown):
        is_guest = env == "vm-guest"
        if is_guest:
            ax.set_facecolor(style.SKY_BLUE + "14")
        y = 0
        yticks, yticklabels = [], []
        for gname, ms in groups:
            for m in ms:
                best = None
                for var in variants:
                    a = agg(cells, env, var, m)
                    if a and (best is None or abs(a[0]) > abs(best[0])):
                        best = a
                col = style.BLUE if m in CANON else style.BLUISH_GREEN
                if best is None:
                    note = ("n/a" if m not in present.get(env, set())
                            else "≈ 0")
                    ax.barh(y, 0, color=style.GREY)
                    ax.text(0.03, y, note, va="center", ha="left",
                           fontsize=style.ANNOT, color=style.GREY)
                else:
                    v, fs = best
                    ax.barh(y, v, color=col,
                           alpha=1.0 if fs >= 0.5 else 0.45, zorder=2)
                    if abs(v) >= 0.30:
                        # Long bar: annotate inside, near the tip, in white
                        # -- outside placement would run past the axis
                        # limit on a narrow panel and collide with the
                        # y-tick labels.
                        ax.text(v - (0.05 if v >= 0 else -0.05), y,
                               f"{v:+.2f}", va="center",
                               ha="right" if v >= 0 else "left",
                               fontsize=style.ANNOT - 0.5, color="white",
                               fontweight="bold", zorder=3)
                    else:
                        ax.text(v + (0.05 if v >= 0 else -0.05), y,
                               f"{v:+.2f}", va="center",
                               ha="left" if v >= 0 else "right",
                               fontsize=style.ANNOT - 0.5)
                yticks.append(y)
                yticklabels.append(m)
                y -= 1
        ax.axvspan(-NEGLIGIBLE, NEGLIGIBLE, color=style.GREY, alpha=0.15,
                  zorder=0)
        ax.axvline(0, color=style.GREY, lw=0.6)
        ax.set_yticks(yticks)
        ax.set_yticklabels(yticklabels if ax is axes[0] else [""] * len(yticklabels),
                          fontsize=style.BODY)
        for t, m in zip(ax.get_yticklabels(), all_metrics):
            t.set_color(style.BLUE if m in CANON else style.BLUISH_GREEN)
        ax.set_xlim(-1.15, 1.15)
        ax.set_title(env + ("  (emphasized)" if is_guest else ""),
                    fontsize=style.TITLE,
                    fontweight="bold" if is_guest else "normal")
        ax.set_xlabel("Cliff's $\\delta$", fontsize=style.BODY)
        ax.grid(False)

    handles = [
        plt.Line2D([0], [0], marker="s", color=style.BLUE, ls="",
                   label="canonical RDT (mbw / llcocc / llcmr)"),
        plt.Line2D([0], [0], marker="s", color=style.BLUISH_GREEN, ls="",
                   label="portable proxy"),
    ]
    fig.legend(handles=handles, loc="outside lower center", ncol=2,
              fontsize=style.LEGEND, frameon=False)

    spec = style.FigSpec(style.TEXT_WIDTH, 2.9, "fig:vmproxy")
    path = out / "Figure_12.pdf"
    w, h = style.save(fig, path, spec)
    plt.close(fig)
    print(f"wrote {path} ({w:.2f} x {h:.2f} in)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("tsv", nargs="?", type=Path,
                    default="results/p2-15metric-xdeploy-1of3-w5/w5-victim-delta.tsv")
    ap.add_argument("--out", type=Path,
                    default=Path("figs"))
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    cells, present, variants = load(args.tsv)
    fig_11_forest(cells, present, variants, args.out)
    fig_12_vmguest_paired(cells, present, variants, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

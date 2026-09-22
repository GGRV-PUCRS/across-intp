#!/usr/bin/env python3
"""plot-fig11-fig12-jsa.py -- JSA redraws of fig:victim (Figure_11) and
fig:vmproxy (Figure_12) from the W5 colocation TSV.

Reuses the same load()/agg() aggregation as plot-w5-victim-delta.py (kept
here rather than imported -- that script's filename is not a valid Python
module name) against the same source of record:
results/p2-15metric-xdeploy-1of3-w5/w5-victim-delta.tsv. No statistic here is
recomputed differently than bench/analyze-cross-deployment.py --w5 already
produced; this file only re-lays-out the same medians/significance flags.

Figure_11 (fig:victim): forest plot, same design as F10 (env-faceted, metric
rows, v2.1 circle / v3.3 square, filled = majority BH-FDR significant), with
saturated |Cliff's delta| = 1.0 markers ringed in black so they read as
distinct from near-1 markers under color alone or in grayscale.

Figure_12 (fig:vmproxy): the P2 punchline, redrawn as a paired host-vs-guest
bar panel. Canonical RDT metrics (mbw, llcocc, llcmr) are structurally
absent in the guest -- shown as a grey "unavailable" hatch bar, not a zero --
while the portable proxies (membw_est, psi_mem, schedlat, psi_io) report in
both panels, so the loss and the substitute are directly comparable side by
side. The guest panel carries a light background tint since it is the
headline result.
"""
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path
from statistics import median

import matplotlib.pyplot as plt

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

FAM_COLOR = {"guard": style.VERMILLION, "portable": style.BLUISH_GREEN,
             "canon": style.BLUE}


def family(m: str) -> str:
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
        # status ("OK"/"PROXY"/"UNAVAILABLE") is only present with
        # --tag-status (bench/analyze-cross-deployment.py); absent otherwise.
        cells[(env, var, m)].append((cd, r["signif"] not in SIG, r.get("status", "OK")))
    return cells, present, sorted(variants)


def agg(cells, env, var, m):
    xs = cells.get((env, var, m))
    if not xs:
        return None
    # status is deterministic per (env,var,metric) -- verified across the
    # full campaign, 2026-09-16 -- so any entry's value is authoritative.
    return (median(c for c, _, _ in xs), sum(s for _, s, _ in xs) / len(xs),
            xs[0][2])


def fig_victim(cells, present, variants, out: Path) -> None:
    metrics = [m for m in ORDER if any(m in present[e] for e in ENVS)]
    envs = [e for e in ENVS if e in present]
    mark = {variants[0]: "o"}
    if len(variants) > 1:
        mark[variants[1]] = "s"

    width = style.TEXT_WIDTH
    height = 3.55
    fig, axes = plt.subplots(1, len(envs), figsize=(width, height),
                              sharey=True, squeeze=False,
                              layout="constrained")
    axes = axes[0]
    y = {m: i for i, m in enumerate(reversed(metrics))}
    for ax, env in zip(axes, envs):
        ax.axvspan(-NEGLIGIBLE, NEGLIGIBLE, color="grey", alpha=0.12, zorder=0)
        ax.axvline(0, color="grey", lw=0.6, zorder=1)
        for m in metrics:
            yc = y[m]
            col = FAM_COLOR[family(m)]
            for var in variants:
                a = agg(cells, env, var, m)
                if a is None:
                    if m not in present[env]:
                        ax.text(0, yc,
                                "absent (RDT n/a)"
                                if m in {"mbw", "llcocc", "llcmr"} else "—",
                                fontsize=style.AXIS_FLOOR, color="grey",
                                ha="center", va="center")
                    continue
                cd, fs, st = a
                off = 0.16 if var == variants[0] else -0.16
                saturated = abs(cd) >= 0.995
                # Saturated |delta|=1.0 cells get a black outline ring behind
                # the marker so they read as distinct under color alone or
                # in grayscale -- not just a darker/more-opaque dot.
                if saturated:
                    ax.plot(cd, yc + off, mark.get(var, "o"), ms=10.5,
                            mfc="none", mec="black", mew=1.1, zorder=2.5)
                # PROXY: a real reading via a substitute backend (e.g. v2.1
                # vm-guest llcocc's miss-ratio fallback) -- a colored ring
                # distinct from the saturation ring so it composes with it.
                if st == "PROXY":
                    ax.plot(cd, yc + off, "o", ms=13, mfc="none",
                            mec=style.VERMILLION, mew=1.0, zorder=2.4)
                ax.plot(cd, yc + off, mark.get(var, "o"), ms=6,
                        color=col, mfc=(col if fs >= 0.5 else "white"),
                        mec=col, mew=1.2, zorder=3)
        ax.set_xlim(-1.25, 1.25)
        ax.set_title(env, fontsize=style.TITLE)
        ax.set_xlabel("Cliff's δ (pairwise − solo)")
        ax.grid(axis="x", ls=":", alpha=0.3)
    axes[0].set_yticks(range(len(metrics)))
    axes[0].set_yticklabels([m for m in reversed(metrics)], fontsize=style.BODY)
    for t, m in zip(axes[0].get_yticklabels(), reversed(metrics)):
        t.set_color(FAM_COLOR[family(m)])

    handles = [
        plt.Line2D([0], [0], marker="o", color=FAM_COLOR["canon"], ls="",
                   ms=5.5, label="canonical-7"),
        plt.Line2D([0], [0], marker="o", color=FAM_COLOR["portable"], ls="",
                   ms=5.5, label="portable"),
        plt.Line2D([0], [0], marker="o", color=FAM_COLOR["guard"], ls="",
                   ms=5.5, label="guard (expect flat)"),
        plt.Line2D([0], [0], marker="o", color="k", mfc="k", ls="",
                   ms=5.5, label="majority signif. (filled)"),
        plt.Line2D([0], [0], marker="o", color="k", mfc="white", ls="",
                   ms=5.5, label="not signif. (open)"),
        plt.Line2D([0], [0], marker="o", color="k", mfc="none", mec="black",
                   mew=1.1, ls="", ms=9, label="saturated |δ|=1.0"),
        plt.Line2D([0], [0], marker="o", color="k", mfc="none",
                   mec=style.VERMILLION, mew=1.0, ls="", ms=11,
                   label="proxy backend"),
    ]
    if len(variants) > 1:
        handles += [
            plt.Line2D([0], [0], marker=mark[variants[0]], color="k", ls="",
                       ms=5.5, label=style.VARIANT_LABEL.get(variants[0], variants[0])),
            plt.Line2D([0], [0], marker=mark[variants[1]], color="k", ls="",
                       ms=5.5, label=style.VARIANT_LABEL.get(variants[1], variants[1]))]
    fig.legend(handles=handles, loc="outside lower center", ncol=4,
               frameon=False, fontsize=style.LEGEND, handlelength=1.1,
               handletextpad=0.4, columnspacing=0.9)

    spec = style.FigSpec(width, height, "fig:victim")
    w, h = style.save(fig, out / "Figure_11.pdf", spec)
    plt.close(fig)
    print(f"wrote {out / 'Figure_11.pdf'} ({w:.2f} x {h:.2f} in)")


def fig_vmproxy(cells, present, variants, out: Path) -> None:
    canon_ms = ["mbw", "llcocc", "llcmr"]
    portable_ms = ["membw_est", "psi_mem", "schedlat", "psi_io"]
    labels = canon_ms + portable_ms

    def best(env, m):
        b = None
        for var in variants:
            a = agg(cells, env, var, m)
            if a and (b is None or abs(a[0]) > abs(b[0])):
                b = a
        return b

    width = style.TEXT_WIDTH
    height = 2.55
    fig, (ax_h, ax_g) = plt.subplots(1, 2, figsize=(width, height),
                                      sharey=True, layout="constrained")
    ax_g.set_facecolor("#fdf2ec")  # light tint: this is the headline panel

    for ax, env, title in ((ax_h, "bare", "host (bare metal)"),
                            (ax_g, "vm-guest", "vm-guest")):
        yy = list(range(len(labels)))
        vals, cols, hatch, notes = [], [], [], []
        for m in labels:
            fam = "canon" if m in canon_ms else "portable"
            unavailable = m not in present.get(env, set())
            b = best(env, m)
            if unavailable or b is None:
                vals.append(0.02)
                cols.append(style.GREY)
                hatch.append("////")
                notes.append("unavailable" if unavailable else "n/a")
            else:
                cd, fs, st = b
                vals.append(cd)
                cols.append(FAM_COLOR[fam] if fam != "canon" else style.BLUE)
                # PROXY: the bar IS real data, but from a substitute backend
                # (e.g. v2.1 vm-guest llcocc's miss-ratio fallback) -- distinct
                # from both a genuine reading (no hatch) and a structurally
                # absent one ("////" above).
                hatch.append("...." if st == "PROXY" else None)
                note = "signif." if fs >= 0.5 else "n.s."
                notes.append(note + " (proxy)" if st == "PROXY" else note)
        bars = ax.barh(yy, vals, color=cols, alpha=0.9, zorder=2,
                        edgecolor="black", linewidth=0.3)
        for b, h in zip(bars, hatch):
            if h:
                b.set_hatch(h)
        ax.axvspan(-NEGLIGIBLE, NEGLIGIBLE, color="grey", alpha=0.10, zorder=0)
        ax.axvline(0, color="grey", lw=0.6)
        ax.set_xlim(-1.25, 1.25)
        ax.set_title(title, fontsize=style.TITLE)
        ax.set_xlabel("Cliff's δ (pairwise − solo)")
        for i, (v, n) in enumerate(zip(vals, notes)):
            ax.text(v + (0.05 if v >= 0 else -0.05), i, n, va="center",
                    ha="left" if v >= 0 else "right",
                    fontsize=style.ANNOT, color="#333333")
    ax_h.set_yticks(range(len(labels)))
    ax_h.set_yticklabels(labels, fontsize=style.BODY)
    ax_h.invert_yaxis()
    for t, m in zip(ax_h.get_yticklabels(), labels):
        t.set_color(style.BLUE if m in canon_ms else style.BLUISH_GREEN)

    handles = [
        plt.Rectangle((0, 0), 1, 1, fc=style.BLUE, label="canonical RDT"),
        plt.Rectangle((0, 0), 1, 1, fc=style.BLUISH_GREEN, label="portable proxy"),
        plt.Rectangle((0, 0), 1, 1, fc=style.GREY, hatch="////",
                      label="unavailable in this deployment"),
        plt.Rectangle((0, 0), 1, 1, fc=style.BLUE, hatch="....",
                      label="reading via substitute backend"),
    ]
    fig.legend(handles=handles, loc="outside lower center", ncol=4,
               frameon=False, fontsize=style.LEGEND, handlelength=1.2,
               handletextpad=0.4, columnspacing=1.0)

    spec = style.FigSpec(width, height, "fig:vmproxy")
    w, h = style.save(fig, out / "Figure_12.pdf", spec)
    plt.close(fig)
    print(f"wrote {out / 'Figure_12.pdf'} ({w:.2f} x {h:.2f} in)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("tsv", nargs="?", type=Path,
                    default=Path("results/p2-15metric-xdeploy-1of3-w5/"
                                 "w5-victim-delta.tsv"))
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    style.apply()
    cells, present, variants = load(args.tsv)
    args.out.mkdir(parents=True, exist_ok=True)
    fig_victim(cells, present, variants, args.out)
    fig_vmproxy(cells, present, variants, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

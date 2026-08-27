#!/usr/bin/env python3
"""plot-w5-victim-delta.py — F10/F11: colocation victim-delta (W5).

Consumes the analyzer TSV (bench/analyze-cross-deployment.py --w5, default
results/p2-15metric-xdeploy-1of3-w5/w5-victim-delta.tsv), NOT raw captures.
Emits two figures, png + pdf, under results/figures/p2-w5-victim-delta/:

  F10-victim-delta-forest — forest plot of the victim's metric shift under a
      noisy neighbour (Cliff's delta of pairwise vs solo) per env. The portable
      contention signals (membw_est, schedlat, ...) rise; the guards
      (schedthr, steal) stay flat. v2.1 circle / v3.3 square; filled = the
      majority of victim pairs are BH-FDR significant.
  F11-vmguest-portable-vs-canonical — the P2 punchline: in the VM the canonical
      RDT mem/cache signals are unavailable (mbw absent) or muted, while the
      portable proxy membw_est still captures the contention (Cliff's = +1).

    python3 bench/plot/plot-w5-victim-delta.py [tsv] [--out DIR]
"""
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
import sys
from pathlib import Path
from statistics import median

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parent))
import p2_figio  # noqa: E402  (shared {png,pdf} output layout)
import sa_style  # noqa: E402  (Seminario de Andamento printed geometry)
import numpy as np

# The SA deck embeds the PNG siblings of these PDFs.
SA_PNG_DPI = 300

ORDER = ["netp", "nets", "blk", "mbw", "llcmr", "llcocc", "cpu",
         "schedlat", "psi_mem", "membw_est", "psi_io", "schedthr", "steal",
         "psp", "idle_preempt"]
CANON = {"netp", "nets", "blk", "mbw", "llcmr", "llcocc", "cpu"}
PORTABLE = {"schedlat", "psi_mem", "membw_est", "psi_io", "schedthr", "steal"}
GUARD = {"schedthr", "steal"}            # should stay flat under contention
ENVS = ["bare", "container", "vm-guest"]
NEGLIGIBLE = 0.147                        # |Cliff's delta| below this = negligible
SIG = {"-", "n/a", ""}                    # non-significant markers


def load(tsv: Path):
    # cells[(env,var,metric)] = list of (cliffs, is_sig); present tracks metrics seen
    cells = defaultdict(list)
    present = defaultdict(set)            # env -> set(metric) that have ANY row
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
    """median Cliff's + fraction of victim pairs significant; None if absent."""
    xs = cells.get((env, var, m))
    if not xs:
        return None
    return median(c for c, _ in xs), sum(s for _, s in xs) / len(xs)


def save(fig, out: Path, name: str):
    p2_figio.save(fig, out, name, dpi=140)
    plt.close(fig)
    print(p2_figio.describe(out, name))


def fig_forest(cells, present, variants, out):
    metrics = [m for m in ORDER if any(m in present[e] for e in ENVS)]
    envs = [e for e in ENVS if e in present]
    mark = {variants[0]: "o"}
    if len(variants) > 1:
        mark[variants[1]] = "s"
    fig, axes = plt.subplots(1, len(envs), figsize=(3.6 * len(envs) + 1.5, 6.2),
                             sharey=True, squeeze=False)
    axes = axes[0]
    y = {m: i for i, m in enumerate(reversed(metrics))}   # top-to-bottom in ORDER
    for ax, env in zip(axes, envs):
        ax.axvspan(-NEGLIGIBLE, NEGLIGIBLE, color="grey", alpha=0.12, zorder=0)
        ax.axvline(0, color="grey", lw=0.7, zorder=1)
        for m in metrics:
            yc = y[m]
            col = ("#d62728" if m in GUARD else
                   "#2ca02c" if m in PORTABLE else "#1f77b4")  # guard/portable/canon
            for var in variants:
                a = agg(cells, env, var, m)
                if a is None:
                    if m not in present[env]:
                        ax.text(0, yc, "absent (RDT n/a)" if m in {"mbw", "llcocc", "llcmr"} else "—",
                                fontsize=6, color="grey", ha="center", va="center")
                    continue
                cd, fs = a
                off = 0.16 if var == variants[0] else -0.16
                ax.plot(cd, yc + off, mark.get(var, "o"), ms=6,
                        color=col, mfc=(col if fs >= 0.5 else "white"),
                        mec=col, mew=1.3, zorder=3)
        ax.set_xlim(-1.15, 1.15)
        ax.set_title(env, fontsize=11)
        ax.set_xlabel("Cliff's δ  (pairwise − solo)")
        ax.grid(axis="x", ls=":", alpha=0.3)
    axes[0].set_yticks(range(len(metrics)))
    axes[0].set_yticklabels([m for m in reversed(metrics)], fontsize=8)
    # colour the y-tick labels by family
    for t, m in zip(axes[0].get_yticklabels(), reversed(metrics)):
        t.set_color("#d62728" if m in GUARD else "#2ca02c" if m in PORTABLE else "#1f77b4")
    handles = [
        plt.Line2D([0], [0], marker="o", color="#1f77b4", ls="", label="canonical-7"),
        plt.Line2D([0], [0], marker="o", color="#2ca02c", ls="", label="portable"),
        plt.Line2D([0], [0], marker="o", color="#d62728", ls="", label="guard (expect flat)"),
        plt.Line2D([0], [0], marker="o", color="k", mfc="k", ls="", label="majority signif (filled)"),
        plt.Line2D([0], [0], marker="o", color="k", mfc="white", ls="", label="not signif (open)"),
    ]
    if len(variants) > 1:
        handles += [plt.Line2D([0], [0], marker=mark[variants[0]], color="k", ls="", label=variants[0]),
                    plt.Line2D([0], [0], marker=mark[variants[1]], color="k", ls="", label=variants[1])]
    fig.legend(handles=handles, loc="lower center", ncol=4, fontsize=8,
               frameon=True, bbox_to_anchor=(0.5, -0.04))
    fig.suptitle("How a victim's metrics shift under a noisy neighbour\n"
                 "grey band = negligible effect.  The portable contention signals rise; "
                 "the guard metrics stay flat", fontsize=11)
    fig.tight_layout(rect=(0, 0.035, 1, 0.985))
    save(fig, out, "F10-victim-delta-forest")


def fig_vmguest(cells, present, variants, out):
    """F11: vm-guest — canonical RDT mem/cache vs portable proxies."""
    ge = "vm-guest"
    groups = [("canonical RDT\n(mem / cache)", ["mbw", "llcocc", "llcmr"], "#1f77b4"),
              ("portable proxies", ["membw_est", "psi_mem", "schedlat", "psi_io"], "#2ca02c")]
    labels, vals, cols, notes = [], [], [], []
    for gname, ms, col in groups:
        for m in ms:
            best = None
            for var in variants:
                a = agg(cells, ge, var, m)
                if a and (best is None or abs(a[0]) > abs(best[0])):
                    best = a
            labels.append(m)
            cols.append(col)
            if best is None:
                vals.append(0.0)
                notes.append("absent — RDT n/a in guest" if m not in present.get(ge, set()) else "≈0")
            else:
                vals.append(best[0])
                notes.append("signif" if best[1] >= 0.5 else "n.s.")
    fig, ax = plt.subplots(figsize=(8.2, 0.5 * len(labels) + 2.2))
    yy = range(len(labels))
    ax.barh(list(yy), vals, color=cols, alpha=0.85, zorder=2)
    ax.axvspan(-NEGLIGIBLE, NEGLIGIBLE, color="grey", alpha=0.12, zorder=0)
    ax.axvline(0, color="grey", lw=0.7)
    ax.set_yticks(list(yy)); ax.set_yticklabels(labels, fontsize=9)
    ax.invert_yaxis()
    ax.set_xlim(-1.15, 1.15)
    ax.set_xlabel("Cliff's δ  (pairwise − solo), vm-guest")
    for i, (v, n) in enumerate(zip(vals, notes)):
        ax.text(v + (0.04 if v >= 0 else -0.04), i, n, va="center",
                ha="left" if v >= 0 else "right", fontsize=7, color="#333333")
    handles = [plt.Line2D([0], [0], marker="s", color="#1f77b4", ls="", label="canonical RDT (mbw/llcocc/llcmr)"),
               plt.Line2D([0], [0], marker="s", color="#2ca02c", ls="", label="portable proxy")]
    ax.legend(handles=handles, loc="lower right", fontsize=8, frameon=True)
    ax.set_title("Inside the VM the canonical memory-bandwidth metric is unavailable,\n"
                 "yet its portable proxy still captures the contention under a noisy neighbour",
                 fontsize=10)
    fig.tight_layout()
    save(fig, out, "F11-vmguest-portable-vs-canonical")


# ── Seminario de Andamento cuts ─────────────────────────────────────────────

def _sa_write(fig, out: Path, stem: str, spec) -> None:
    out.mkdir(parents=True, exist_ok=True)
    w, h = sa_style.save(fig, out / f"{stem}.pdf", spec)
    fig.savefig(out / f"{stem}.png", dpi=SA_PNG_DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {out}/{stem}.{{pdf,png}} ({w:.2f} x {h:.2f} in)")


def sa_forest(cells, present, variants, out: Path) -> None:
    """F10 at the SA's printed width.

    Was 12.19 in wide scaled to 0.55, so its 6 pt "absent (RDT n/a)" cell text
    printed at 3.31 pt. At 7.03 in the fifteen metric rows get about 0.17 in
    of pitch each, which holds 7 pt comfortably; what pays for them is the
    two-line suptitle, which moves to the LaTeX caption, and the legend, which
    collapses from two rows to one.

    Same markers, same colours, same aggregation -- only the page changed.
    """
    spec = sa_style.spec_for("F10-victim-delta-forest")
    sa_style.apply()

    metrics = [m for m in ORDER if any(m in present[e] for e in ENVS)]
    envs = [e for e in ENVS if e in present]
    mark = {variants[0]: "o"}
    if len(variants) > 1:
        mark[variants[1]] = "s"

    fig, axes = plt.subplots(
        1, len(envs), figsize=(spec.width, spec.height),
        sharey=True, squeeze=False, layout="constrained")
    axes = axes[0]
    y = {m: i for i, m in enumerate(reversed(metrics))}
    for ax, env in zip(axes, envs):
        ax.axvspan(-NEGLIGIBLE, NEGLIGIBLE, color="grey", alpha=0.12, zorder=0)
        ax.axvline(0, color="grey", lw=0.7, zorder=1)
        for m in metrics:
            yc = y[m]
            col = ("#d62728" if m in GUARD else
                   "#2ca02c" if m in PORTABLE else "#1f77b4")
            for var in variants:
                a = agg(cells, env, var, m)
                if a is None:
                    if m not in present[env]:
                        # Structural text, not a dense in-cell annotation:
                        # it is the only thing that says why the row is empty,
                        # so it holds AXIS_FLOOR like the tick labels do.
                        ax.text(0, yc,
                                "absent (RDT n/a)"
                                if m in {"mbw", "llcocc", "llcmr"} else "—",
                                fontsize=sa_style.AXIS_FLOOR, color="grey",
                                ha="center", va="center")
                    continue
                cd, fs = a
                off = 0.16 if var == variants[0] else -0.16
                ax.plot(cd, yc + off, mark.get(var, "o"), ms=3.4,
                        color=col, mfc=(col if fs >= 0.5 else "white"),
                        mec=col, mew=0.9, zorder=3)
        ax.set_xlim(-1.15, 1.15)
        # No explicit locator: the default one picks the same ticks the wide
        # cut had, so the content diff stays a pure subset instead of showing
        # "-1.0" leave and "-1" arrive.
        ax.set_title(env, fontsize=sa_style.TITLE)
        ax.set_xlabel("Cliff's δ  (pairwise − solo)")
        ax.grid(axis="x", ls=":", alpha=0.3)
    axes[0].set_yticks(range(len(metrics)))
    axes[0].set_yticklabels([m for m in reversed(metrics)],
                            fontsize=sa_style.BODY)
    for t, m in zip(axes[0].get_yticklabels(), reversed(metrics)):
        t.set_color("#d62728" if m in GUARD
                    else "#2ca02c" if m in PORTABLE else "#1f77b4")

    handles = [
        plt.Line2D([0], [0], marker="o", color="#1f77b4", ls="", ms=3.4,
                   label="canonical-7"),
        plt.Line2D([0], [0], marker="o", color="#2ca02c", ls="", ms=3.4,
                   label="portable"),
        plt.Line2D([0], [0], marker="o", color="#d62728", ls="", ms=3.4,
                   label="guard (expect flat)"),
        plt.Line2D([0], [0], marker="o", color="k", mfc="k", ls="", ms=3.4,
                   label="majority signif (filled)"),
        plt.Line2D([0], [0], marker="o", color="k", mfc="white", ls="",
                   ms=3.4, label="not signif (open)"),
    ]
    if len(variants) > 1:
        handles += [
            plt.Line2D([0], [0], marker=mark[variants[0]], color="k", ls="",
                       ms=3.4, label=variants[0]),
            plt.Line2D([0], [0], marker=mark[variants[1]], color="k", ls="",
                       ms=3.4, label=variants[1])]
    # One row: at 7.03 in and 7 pt the seven entries fit, and a second row
    # would cost as much height as two metric rows.
    fig.legend(handles=handles, loc="outside lower center",
               ncol=len(handles), frameon=False, fontsize=sa_style.LEGEND,
               handlelength=1.0, handletextpad=0.35, columnspacing=0.9)
    _sa_write(fig, out, "F10-victim-delta-forest", spec)


def sa_vmguest(cells, present, variants, out: Path) -> None:
    """F11 at the SA's printed width.

    The worst offender in the set: 8.06 in scaled to 0.41, so 7 pt printed at
    2.90 pt. At the 3.36 in column the seven bars keep their labels at 7 pt
    and the per-bar verdicts sit at ANNOT_FLOOR, which is what §4 allows them.
    The two-line in-figure title moves to the LaTeX caption.
    """
    spec = sa_style.spec_for("F11-vmguest-portable-vs-canonical")
    sa_style.apply()

    ge = "vm-guest"
    groups = [("canonical RDT\n(mem / cache)", ["mbw", "llcocc", "llcmr"],
               "#1f77b4"),
              ("portable proxies",
               ["membw_est", "psi_mem", "schedlat", "psi_io"], "#2ca02c")]
    labels, vals, cols, notes = [], [], [], []
    for _gname, ms, col in groups:
        for m in ms:
            best = None
            for var in variants:
                a = agg(cells, ge, var, m)
                if a and (best is None or abs(a[0]) > abs(best[0])):
                    best = a
            labels.append(m)
            cols.append(col)
            if best is None:
                vals.append(0.0)
                notes.append("absent — RDT n/a in guest"
                             if m not in present.get(ge, set()) else "≈0")
            else:
                vals.append(best[0])
                notes.append("signif" if best[1] >= 0.5 else "n.s.")

    fig, ax = plt.subplots(figsize=(spec.width, spec.height),
                           layout="constrained")
    yy = range(len(labels))
    ax.barh(list(yy), vals, color=cols, alpha=0.85, zorder=2)
    ax.axvspan(-NEGLIGIBLE, NEGLIGIBLE, color="grey", alpha=0.12, zorder=0)
    ax.axvline(0, color="grey", lw=0.7)
    ax.set_yticks(list(yy))
    ax.set_yticklabels(labels, fontsize=sa_style.BODY)
    ax.invert_yaxis()
    # Kept at the wide cut's ±1.15. Widening it to make room for the "absent
    # — RDT n/a in guest" verdict would hand the locator two ticks the wide
    # cut never had, and new tick strings are exactly what the gate's content
    # diff is there to catch. The verdict fits inside 1.15 at ANNOT_FLOOR.
    ax.set_xlim(-1.15, 1.15)
    ax.set_xlabel("Cliff's δ  (pairwise − solo), vm-guest")
    for i, (v, n) in enumerate(zip(vals, notes)):
        ax.text(v + (0.05 if v >= 0 else -0.05), i, n, va="center",
                ha="left" if v >= 0 else "right",
                fontsize=sa_style.ANNOT, color="#333333")
    handles = [plt.Line2D([0], [0], marker="s", color="#1f77b4", ls="", ms=3.4,
                          label="canonical RDT (mbw/llcocc/llcmr)"),
               plt.Line2D([0], [0], marker="s", color="#2ca02c", ls="", ms=3.4,
                          label="portable proxy")]
    fig.legend(handles=handles, loc="outside lower center", ncol=2,
               frameon=False, fontsize=sa_style.LEGEND,
               handlelength=1.0, handletextpad=0.35, columnspacing=0.9)
    _sa_write(fig, out, "F11-vmguest-portable-vs-canonical", spec)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("tsv", nargs="?", type=Path,
                    default="results/p2-15metric-xdeploy-1of3-w5/w5-victim-delta.tsv")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--sa-style", action="store_true",
                    help="render F10 and F11 at the Seminario de Andamento's "
                         "exact printed widths (sa_style geometry)")
    args = ap.parse_args()
    cells, present, variants = load(args.tsv)
    out = args.out or Path("results/figures/p2-w5-victim-delta")
    out.mkdir(parents=True, exist_ok=True)
    if args.sa_style:
        sa_forest(cells, present, variants, out)
        sa_vmguest(cells, present, variants, out)
        return 0
    fig_forest(cells, present, variants, out)
    fig_vmguest(cells, present, variants, out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

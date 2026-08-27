#!/usr/bin/env python3
"""analyze-cadence-overhead.py — F9: profiler overhead vs sampling cadence.

The overhead-stage cadence sweep (bench/run-cadence-sweep.sh --stages overhead
--overhead-volpert) runs a reference workload under three arms — _baseline (no
profiler), v2.1, v3.3 — at each sampling interval. The profiler's runtime cost
is the *throughput displacement* of the reference workload under a profiler arm
vs the baseline arm (Volpert D), measured within the same cadence so any drift
cancels.

This reads <sweep>/cadence-*/overhead/<env>/<arm>/<ref>/rep*/throughput.tsv
(bogo_ops_per_s_real), computes overhead% = (baseline − arm)/baseline × 100 per
(env, variant, ref, interval), writes overhead-vs-cadence.tsv + a short report,
and renders F9 (overhead% vs sampling interval, per variant) as PNG + PDF.

    python3 bench/analyze-cadence-overhead.py <sweep_dir> [--out report.md]
"""
from __future__ import annotations

import argparse
import glob
import os
import sys
from collections import defaultdict
from pathlib import Path
from statistics import median

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "plot"))
import p2_ci     # noqa: E402  (shared rep-level bootstrap CI convention)
import p2_figio  # noqa: E402  (shared {png,pdf} output layout)
import sa_style  # noqa: E402  (Seminario de Andamento printed geometry)

# The SA deck embeds the PNG siblings of these PDFs.
SA_PNG_DPI = 300

THPT_KEY = "bogo_ops_per_s_real"
REFS = ["ref_cpu", "ref_stream", "ref_disk"]
# ref_disk throughput (hdd writes) is I/O-variance-dominated (±7-9% run-to-run,
# swamping the ~1-2% profiler overhead) -> kept in the table for transparency
# but excluded from the F9 curve, where cpu/stream are the reliable probes.
FIG_REFS = ["ref_cpu", "ref_stream"]
REF_COLOR = {"ref_cpu": "#1f77b4", "ref_stream": "#2ca02c", "ref_disk": "#d62728"}


def read_manifest(sweep_dir):
    man = os.path.join(sweep_dir, "sweep-manifest.tsv")
    rows = []
    with open(man) as fh:
        next(fh)
        for line in fh:
            p = line.rstrip("\n").split("\t")
            if len(p) >= 2:
                rows.append((float(p[0]), p[1]))
    return sorted(rows)


def thpt(cell):
    f = os.path.join(cell, "throughput.tsv")
    try:
        for line in open(f):
            k, _, v = line.partition("\t")
            if k == THPT_KEY:
                return float(v)
    except (OSError, ValueError):
        pass
    return None


def render_sa(ov, ci, intervals, variants, env0, figdir):
    """F9 at the Seminario de Andamento's printed width.

    Was 7.39 in scaled to 0.45, so its 8 pt tick labels printed at 3.61 pt.
    Two things pay for the column width: the three-line title, which was the
    error-bar definition and the reading instructions and belongs in the LaTeX
    caption, and the legend, which drops from a two-column block to one row of
    the same four entries.

    The curve itself, its points, and its bootstrap CIs are untouched -- this
    is the same figure on a narrower page.
    """
    spec = sa_style.spec_for("F9-overhead-vs-cadence")
    sa_style.apply()

    fig, ax = plt.subplots(figsize=(spec.width, spec.height),
                           layout="constrained")
    style = {variants[0]: "-"}
    if len(variants) > 1:
        style[variants[1]] = "--"
    ax.axhline(0, color="grey", lw=0.6)
    for var in variants:
        for ref in FIG_REFS:
            d = ov.get((env0, var, ref), {})
            if not d:
                continue
            xs = sorted(d)
            ys = [d[x] for x in xs]
            c = ci.get((env0, var, ref), {})
            lo = [max(0.0, y - c[x][1]) if x in c and c[x][1] == c[x][1] else 0.0
                  for x, y in zip(xs, ys)]
            hi = [max(0.0, c[x][2] - y) if x in c and c[x][2] == c[x][2] else 0.0
                  for x, y in zip(xs, ys)]
            ax.errorbar(xs, ys, yerr=[lo, hi], fmt=style.get(var, "-"),
                        marker="o", ms=2.6, color=REF_COLOR[ref], lw=1.0,
                        alpha=0.9, capsize=1.8, elinewidth=0.7)
    ax.set_xscale("log")
    ax.set_xticks(intervals)
    ax.set_xticklabels([f"{iv:g}" for iv in intervals],
                       fontsize=sa_style.BODY)
    ax.set_xlabel("sampling interval (s)  —  finer cadence ←")
    ax.set_ylabel("profiler overhead\n(% throughput loss vs baseline)")
    ax.grid(True, which="both", ls=":", alpha=0.3)

    handles = [plt.Line2D([0], [0], color=REF_COLOR[r], marker="o", lw=1.0,
                          ms=2.6, label=r.replace("ref_", "ref:"))
               for r in FIG_REFS]
    handles += [plt.Line2D([0], [0], color="k", ls="-",
                           label=f"{variants[0]} (solid)")]
    if len(variants) > 1:
        handles += [plt.Line2D([0], [0], color="k", ls="--",
                               label=f"{variants[1]} (dashed)")]
    # 2 refs + 2 variants on one row. The handles and the inter-column gap are
    # trimmed because four entries at 7 pt only just fit the 3.36 in column.
    fig.legend(handles=handles, loc="outside lower center", ncol=len(handles),
               frameon=False, fontsize=sa_style.LEGEND, handlelength=0.9,
               handletextpad=0.3, columnspacing=0.6)

    os.makedirs(figdir, exist_ok=True)
    stem = "F9-overhead-vs-cadence"
    w, h = sa_style.save(fig, Path(figdir) / f"{stem}.pdf", spec)
    fig.savefig(os.path.join(figdir, f"{stem}.png"), dpi=SA_PNG_DPI,
                bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {figdir}/{stem}.{{pdf,png}} ({w:.2f} x {h:.2f} in)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("sweep_dir", nargs="?", default="results/p2-cadence-overhead")
    ap.add_argument("--out", default="docs/reports/p2-cadence-overhead.md")
    ap.add_argument("--tsv", default=None)
    ap.add_argument("--fig", default="results/figures/p2-cadence-sweep")
    ap.add_argument("--sa-style", action="store_true",
                    help="render F9 at the Seminario de Andamento's exact "
                         "printed width (sa_style geometry). The TSV and the "
                         "report are still written, so point --tsv/--out at a "
                         "scratch path to leave a campaign snapshot untouched.")
    args = ap.parse_args()
    man = read_manifest(args.sweep_dir)

    # th[(interval, env, arm, ref)] = [throughput per rep]
    th = defaultdict(list)
    envs, variants = set(), set()
    for iv, tag in man:
        for cell in glob.glob(os.path.join(args.sweep_dir, f"cadence-{tag}",
                                            "overhead", "*", "*", "*", "rep*")):
            parts = cell.split(os.sep)
            env, arm, ref = parts[-4], parts[-3], parts[-2]
            v = thpt(cell)
            if v is None or v <= 0:
                continue
            th[(iv, env, arm, ref)].append(v)
            envs.add(env)
            if arm != "_baseline":
                variants.add(arm)
    envs, variants = sorted(envs), sorted(variants)
    intervals = [iv for iv, _ in man]

    # overhead% per (env, variant, ref, interval); + aggregate over refs
    # ci_lo/ci_hi are APPENDED to the historical column set: the leading columns
    # and every value in them are byte-identical to what this analyzer wrote
    # before the CI existed, so an older reader keeps working.
    rows = ["env\tvariant\tref\tinterval_s\tbaseline_thpt\tarm_thpt\toverhead_pct\treps"
            "\tci_lo\tci_hi"]
    ov = defaultdict(dict)        # (env,variant,ref) -> {interval: overhead%}
    ci = defaultdict(dict)        # (env,variant,ref) -> {interval: (pct, lo, hi)}
    cell = 0                      # deterministic per-cell bootstrap stream
    for env in envs:
        for iv in intervals:
            base = th.get((iv, env, "_baseline", ""), None)
            for ref in REFS:
                b = th.get((iv, env, "_baseline", ref))
                if not b:
                    continue
                bmed = median(b)
                for var in variants:
                    a = th.get((iv, env, var, ref))
                    if not a:
                        continue
                    amed = median(a)
                    pct = (bmed - amed) / bmed * 100.0
                    _p, lo, hi = p2_ci.ratio_ci(b, a, seed_offset=cell)
                    cell += 1
                    ov[(env, var, ref)][iv] = pct
                    ci[(env, var, ref)][iv] = (pct, lo, hi)
                    rows.append(f"{env}\t{var}\t{ref}\t{iv:g}\t{bmed:.1f}\t{amed:.1f}\t{pct:.3f}\t{len(a)}"
                                f"\t{lo:.3f}\t{hi:.3f}")
    tsv_path = args.tsv or os.path.join(args.sweep_dir, "overhead-vs-cadence.tsv")
    with open(tsv_path, "w") as fh:
        fh.write("\n".join(rows) + "\n")
    print(f"[wrote {tsv_path} ({len(rows)-1} rows)]")

    # ---- report ----
    L = [f"# Profiler overhead vs sampling cadence (F9) — {args.sweep_dir}\n",
         "Overhead = throughput displacement of the reference workload under a "
         "profiler arm vs the _baseline arm (Volpert D), within each cadence. "
         "Reference = stress-ng bogo-ops/s. Positive % = the profiler slowed the "
         f"workload. Env(s): {', '.join(envs)}; variants: {', '.join(variants)}.\n"]
    for env in envs:
        L.append(f"## {env} — overhead % by sampling interval\n")
        hdr = "| variant · ref | " + " | ".join(f"{iv:g}s" for iv in intervals) + " | max |"
        L.append(hdr); L.append("|---" * (len(intervals) + 2) + "|")
        for var in variants:
            for ref in REFS:
                d = ov.get((env, var, ref), {})
                if not d:
                    continue
                cells = [f"{d[iv]:+.2f}" if iv in d else "—" for iv in intervals]
                mx = max((abs(x) for x in d.values()), default=0)
                L.append(f"| {var} · {ref.replace('ref_','')} | " + " | ".join(cells) + f" | {mx:.2f} |")
        L.append("")
    # headline: mean overhead at the finest vs coarsest cadence, per variant
    fine, coarse = intervals[0], intervals[-1]
    L.append("## Headline\n")
    L.append("_Headline uses the throughput-stable cpu/stream refs; ref_disk is "
             "I/O-variance-dominated (±7-9% run-to-run) and is shown in the table "
             "but excluded from the F9 curve + this summary._\n")
    for var in variants:
        fvals = [ov[(envs[0], var, r)][fine] for r in FIG_REFS if fine in ov.get((envs[0], var, r), {})]
        cvals = [ov[(envs[0], var, r)][coarse] for r in FIG_REFS if coarse in ov.get((envs[0], var, r), {})]
        if fvals and cvals:
            L.append(f"- **{var}** ({envs[0]}): mean overhead {sum(fvals)/len(fvals):+.2f}% at "
                     f"{fine:g}s (finest) → {sum(cvals)/len(cvals):+.2f}% at {coarse:g}s (coarsest).")
    report = "\n".join(L) + "\n"
    with open(args.out, "w") as fh:
        fh.write(report)
    print(f"[wrote {args.out}]")

    # ---- F9 figure ----
    os.makedirs(args.fig, exist_ok=True)
    env0 = envs[0]
    if args.sa_style:
        return render_sa(ov, ci, intervals, variants, env0, args.fig)
    fig, ax = plt.subplots(figsize=(7.5, 4.8))
    style = {variants[0]: "-"}
    if len(variants) > 1:
        style[variants[1]] = "--"
    ax.axhline(0, color="grey", lw=0.6)
    for var in variants:
        for ref in FIG_REFS:
            d = ov.get((env0, var, ref), {})
            if not d:
                continue
            xs = sorted(d); ys = [d[x] for x in xs]
            # Points stay at the median-based overhead%; the whisker is the 95 %
            # rep-level bootstrap CI of that same statistic.
            c = ci.get((env0, var, ref), {})
            lo = [max(0.0, y - c[x][1]) if x in c and c[x][1] == c[x][1] else 0.0
                  for x, y in zip(xs, ys)]
            hi = [max(0.0, c[x][2] - y) if x in c and c[x][2] == c[x][2] else 0.0
                  for x, y in zip(xs, ys)]
            ax.errorbar(xs, ys, yerr=[lo, hi], fmt=style.get(var, "-"), marker="o", ms=4,
                        color=REF_COLOR[ref], lw=1.6, alpha=0.9,
                        capsize=3, elinewidth=0.9)
    ax.set_xscale("log")
    ax.set_xticks(intervals); ax.set_xticklabels([f"{iv:g}" for iv in intervals], fontsize=8)
    ax.set_xlabel("sampling interval (s)  —  finer cadence ←")
    ax.set_ylabel("profiler overhead (% throughput loss vs baseline)")
    ax.grid(True, which="both", ls=":", alpha=0.3)
    handles = [plt.Line2D([0], [0], color=REF_COLOR[r], marker="o", lw=1.6,
                          label=r.replace("ref_", "ref:")) for r in FIG_REFS]
    handles += [plt.Line2D([0], [0], color="k", ls="-", label=f"{variants[0]} (solid)")]
    if len(variants) > 1:
        handles += [plt.Line2D([0], [0], color="k", ls="--", label=f"{variants[1]} (dashed)")]
    ax.legend(handles=handles, fontsize=8, ncol=2, frameon=True)
    ax.set_title("What the profiler costs at each sampling cadence\n"
                 "throughput lost by a reference workload when the profiler is attached\n"
                 f"error bars: {p2_ci.CI_TAG}, bootstrapped over repetitions",
                 fontsize=10)
    fig.tight_layout()
    p2_figio.save(fig, args.fig, "F9-overhead-vs-cadence", dpi=140)
    plt.close(fig)
    print(p2_figio.describe(args.fig, "F9-overhead-vs-cadence"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

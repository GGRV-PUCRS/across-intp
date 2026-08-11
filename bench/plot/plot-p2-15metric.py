#!/usr/bin/env python3
"""plot-p2-15metric.py — P2 validation figure set from a 15-metric campaign.

Renders the FIGURES-PLAN.md "ready today" set from a cross-deployment
campaign directory:

  F0  per-(env, variant) 15-metric workload fingerprint heatmaps — the
      direct extension of the SBAC-PAD paper's Figs. 1/2 across the
      deployment stack                                    <- portable.tsv scan
  F1  cpu ratio-vs-bare dot+CI panel (absolute metrics)   <- cross-deployment.tsv
  F2  claim-class x significance matrix                   <- cross-deployment.tsv
  F3  availability grid with in-figure WHY footnotes      <- portable.tsv scan
  F4  membw_est validation scatter vs ground truth        <- portable+groundtruth
  F5  PSI bandwidth-blindness falsification (app05)       <- portable.tsv scan
  F6  psp delta-vs-bare heatmap (values + effect size)    <- cross-deployment.tsv

Stats come from the analyzer TSV wherever one exists (never recomputed here);
the raw-capture scans only take medians. Variant tags map to the canonical
descriptive labels. The C34 caveat (v2.1 mbw invalid pre-re-run) renders as
red-bordered cells so it travels with the figure.

Usage:
    python3 bench/plot/plot-p2-15metric.py <campaign_dir> [--out DIR]
"""
from __future__ import annotations

import argparse
import glob
import statistics
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parent))
import p2_figio  # noqa: E402  (shared {png,pdf} output layout)
import numpy as np
import pandas as pd

try:
    from scipy.stats import spearmanr
except ImportError:
    spearmanr = None

VARIANT_LABELS = {
    "v2.1": "c-abi-cgroup",
    "v3.3": "ebpf-core-cgroup",
}
ENV_ORDER = ["container", "container-podman", "container-lxc", "container-k8s", "vm-guest"]
ENV_SHORT = {"container": "docker", "container-podman": "podman", "container-lxc": "lxc/incus",
             "container-k8s": "k8s", "vm-guest": "kvm-guest", "bare": "bare"}
METRICS_CANON = ["netp", "nets", "blk", "mbw", "llcmr", "llcocc", "cpu"]
METRICS_PORTABLE = ["schedlat", "psi_mem", "membw_est", "psi_io", "schedthr", "steal"]
METRICS_REGIME = ["psp", "idle_preempt"]
# C34: v2.1 mbw predated the D12 scope fix; the targeted re-run (2026-06-13)
# replaced those cells with correctly-scoped values, so no cells are invalid.
C34_INVALID = set()

SIG_ORDER = {"***": 3, "**": 2, "*": 1, "n.s.": 0, "n/a": -1}


def vlabel(v: str) -> str:
    return VARIANT_LABELS.get(v, v)


# ── capture parsing ──────────────────────────────────────────────────────────

def load_capture(path: Path) -> dict[str, float]:
    """Median per metric of one portable.tsv (header-mapped, ts-offset aware).
    '--' columns are absent from the result (metric unavailable)."""
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
    """(env, variant, workload) -> list of per-rep metric-median dicts."""
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
    """Median GT llc_miss/s over the rep window (groundtruth.tsv)."""
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


# ── F0: 15-metric fingerprint heatmaps (paper Fig. 1/2 style) ───────────────

def fig_fingerprint(cells, out: Path):
    """Workload x metric heatmap with inline values, one panel per (env,
    variant); the SBAC-PAD Figs. 1/2 layout extended to 15 metrics and the
    deployment stack. %-metrics are raw; membw_est and psp (different units)
    are normalized to the panel maximum and flagged with '*'."""
    envs = ["bare", "container", "vm-guest"]
    variants = sorted({k[1] for k in cells})
    wls = sorted({k[2] for k in cells})
    metrics = METRICS_CANON + METRICS_PORTABLE + METRICS_REGIME
    norm_only = {"membw_est", "psp"}   # not 0-100-clamped -> panel-normalized

    fig, axes = plt.subplots(len(variants), len(envs),
                             figsize=(7.6 * len(envs), 0.52 * len(wls) * len(variants) + 3.6),
                             squeeze=False,
                             gridspec_kw={"wspace": 0.06, "hspace": 0.18})
    for r, var in enumerate(variants):
        for c, env in enumerate(envs):
            ax = axes[r][c]
            grid = np.full((len(wls), len(metrics)), np.nan)
            raw = {}
            for yi, wl in enumerate(wls):
                for xi, m in enumerate(metrics):
                    v = cell_median(cells, env, var, wl, m)
                    if v is not None:
                        raw[(yi, xi)] = v
            # normalize the unbounded metrics to panel max -> 0-100
            for xi, m in enumerate(metrics):
                if m in norm_only:
                    col = [raw[(yi, xi)] for yi in range(len(wls)) if (yi, xi) in raw]
                    mx = max(col) if col else 1.0
                    for yi in range(len(wls)):
                        if (yi, xi) in raw:
                            grid[yi, xi] = 100.0 * raw[(yi, xi)] / mx if mx > 0 else 0.0
                else:
                    for yi in range(len(wls)):
                        if (yi, xi) in raw:
                            grid[yi, xi] = min(raw[(yi, xi)], 100.0)
            masked = np.ma.masked_invalid(grid)
            cmap = plt.cm.Blues.copy()
            cmap.set_bad("#d9d9d9")    # grey = metric unavailable ('--')
            im = ax.imshow(masked, cmap=cmap, vmin=0, vmax=100, aspect="auto")
            for yi in range(len(wls)):
                for xi in range(len(metrics)):
                    if not np.isnan(grid[yi, xi]):
                        v = grid[yi, xi]
                        if v >= 1:
                            ax.text(xi, yi, f"{v:.0f}", ha="center", va="center",
                                    fontsize=6.5,
                                    color="white" if v > 55 else "#08306b")
                    # C34 invalid cells: red border
                    if (var, metrics[xi]) in C34_INVALID:
                        ax.add_patch(plt.Rectangle((xi - 0.5, yi - 0.5), 1, 1,
                                     fill=False, edgecolor="crimson", lw=1.2))
            # outer-edge tick labels only, so panels never collide
            ax.set_xticks(range(len(metrics)))
            if r == len(variants) - 1:
                labels = [m + ("*" if m in norm_only else "") for m in metrics]
                ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=7)
            else:
                ax.set_xticklabels([])
            ax.set_yticks(range(len(wls)))
            if c == 0:
                ax.set_yticklabels([w.replace("_", " ") for w in wls], fontsize=7)
            else:
                ax.set_yticklabels([])
            ax.set_title(f"{ENV_SHORT[env]} / {vlabel(var)}", fontsize=10)
            ax.axvline(6.5, color="k", lw=1.0)
            ax.axvline(12.5, color="k", lw=1.0)
    cbar = fig.colorbar(im, ax=axes, fraction=0.015, pad=0.01)
    cbar.set_label("interference (%)")
    fig.suptitle("15-metric interference fingerprint per workload, across the deployment stack\n"
                 "canonical 7 | portable 6 | scheduling-regime 2.  "
                 "Grey = metric unavailable in this deployment;  "
                 "* = normalized to the panel maximum (estimated memory bandwidth, preemptions/s)",
                 fontsize=11)
    p2_figio.save(fig, out, "F0-fingerprint-heatmap", dpi=160)
    plt.close(fig)


# ── F1: cpu ratio vs bare (absolute) ────────────────────────────────────────

def fig_ratio(df: pd.DataFrame, out: Path):
    d = df[df.claim_class == "absolute"].copy()
    metrics = sorted(d.metric.unique())
    variants = sorted(d.variant.unique())
    # one row, variants side by side (per review: no column stacking)
    fig, axes = plt.subplots(1, len(variants) * len(metrics),
                             figsize=(5.4 * len(variants) * len(metrics), 3.6),
                             sharey=True, squeeze=False)
    col = 0
    for m in metrics:
        for var in variants:
            ax = axes[0][col]; col += 1
            sub = d[(d.variant == var) & (d.metric == m)]
            wls = sorted(sub.workload.unique())
            for i, env in enumerate(ENV_ORDER):
                s = sub[sub.env == env].set_index("workload").reindex(wls)
                x = np.arange(len(wls)) + (i - 2) * 0.14
                lo = np.clip(s.ratio - s.ci_lo, 0, None)
                hi = np.clip(s.ci_hi - s.ratio, 0, None)
                ax.errorbar(x, s.ratio, yerr=[lo.fillna(0), hi.fillna(0)],
                            fmt="o", ms=4.5, capsize=2, label=ENV_SHORT[env])
            ax.axhspan(0.8, 1.25, color="green", alpha=0.10)
            ax.axhline(1.0, color="k", lw=0.7, ls=":")
            ax.set_xticks(range(len(wls)))
            ax.set_xticklabels([w.split("_")[0] for w in wls], fontsize=8)
            ax.set_ylim(0, 3.8)
            ax.set_title(f"{vlabel(var)} — {m}", fontsize=10)
            if col == 1:
                ax.set_ylabel("ratio vs bare (1.0 = identical)")
    handles, labels = axes[0][0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=len(ENV_ORDER),
               fontsize=8, frameon=False, bbox_to_anchor=(0.5, -0.04))
    fig.suptitle("Absolute metrics: ratio to bare metal, with 95% bootstrap CI\n"
                 "green band = the 0.8–1.25x equivalence corridor", fontsize=11)
    fig.tight_layout(rect=(0, 0.04, 1, 0.94))
    p2_figio.save(fig, out, "F1-ratio-vs-bare", dpi=160)
    plt.close(fig)


# ── F2: claim-class x significance matrix ───────────────────────────────────

def fig_claimclass(df: pd.DataFrame, out: Path):
    variants = sorted(df.variant.unique())
    fig, axes = plt.subplots(1, len(variants), figsize=(7.2 * len(variants), 5.0), squeeze=False)
    cls_color = {"absolute": "#2c7fb8", "directional": "#fdae61", "descriptive": "#bdbdbd"}
    all_metrics = sorted(df.metric.unique())
    for c, var in enumerate(variants):
        ax = axes[0][c]
        sub = df[df.variant == var]
        for yi, m in enumerate(all_metrics):
            for xi, env in enumerate(ENV_ORDER):
                s = sub[(sub.metric == m) & (sub.env == env)]
                if s.empty:
                    continue   # blank = metric unavailable in this env ('--')
                cls = s.claim_class.iloc[0]
                best = max((SIG_ORDER.get(x, 0) for x in s.signif), default=0)
                if (var, m) in C34_INVALID:
                    ax.add_patch(plt.Rectangle((xi, yi), 0.94, 0.94,
                                               facecolor="white", edgecolor="crimson",
                                               hatch="///", lw=0.8))
                else:
                    ax.add_patch(plt.Rectangle((xi, yi), 0.94, 0.94,
                                               color=cls_color.get(cls, "#eeeeee"),
                                               alpha=0.35 + 0.2 * min(best, 3) / 3))
        ax.set_xlim(0, len(ENV_ORDER)); ax.set_ylim(0, len(all_metrics))
        ax.set_xticks(np.arange(len(ENV_ORDER)) + 0.5)
        ax.set_xticklabels([ENV_SHORT[e] for e in ENV_ORDER], fontsize=8)
        ax.set_yticks(np.arange(len(all_metrics)) + 0.5)
        ax.set_yticklabels(all_metrics, fontsize=8)
        ax.set_title(f"{vlabel(var)}", fontsize=10)
        ax.invert_yaxis()
    handles = ([plt.Rectangle((0, 0), 1, 1, color=v, alpha=0.55) for v in cls_color.values()]
               + [plt.Rectangle((0, 0), 1, 1, facecolor="white", edgecolor="#999999")])
    labels = list(cls_color.keys()) + ["blank = metric unavailable in this deployment"]
    fig.legend(handles, labels, loc="lower center", ncol=3, fontsize=8, frameon=False,
               bbox_to_anchor=(0.5, -0.02))
    fig.suptitle("Claim class per deployment and metric\n"
                 "shading intensity = strength of the evidence against bare metal", fontsize=11)
    fig.tight_layout(rect=(0, 0.05, 1, 0.92))
    p2_figio.save(fig, out, "F2-claim-class-matrix", dpi=160)
    plt.close(fig)


# ── F3: availability grid with WHY footnotes ────────────────────────────────

def fig_availability(cells, out: Path):
    metrics = METRICS_PORTABLE + METRICS_REGIME + ["mbw", "llcocc", "llcmr"]
    variants = sorted({k[1] for k in cells})
    envs = ["bare"] + ENV_ORDER
    fig, axes = plt.subplots(1, len(variants), figsize=(6.8 * len(variants), 4.6), squeeze=False)
    for c, var in enumerate(variants):
        ax = axes[0][c]
        for yi, env in enumerate(envs):
            for xi, m in enumerate(metrics):
                reps = [r for (e, v, _w), rl in cells.items() if e == env and v == var for r in rl]
                ok = any(m in r for r in reps)
                color = "#41ab5d" if ok else "#d9d9d9"
                ax.add_patch(plt.Rectangle((xi, yi), 0.92, 0.92, color=color))
                ax.text(xi + 0.46, yi + 0.46, "ok" if ok else "--",
                        ha="center", va="center",
                        fontsize=7.5, color="white" if ok else "#636363")
        ax.set_xlim(0, len(metrics)); ax.set_ylim(0, len(envs))
        ax.set_xticks(np.arange(len(metrics)) + 0.5)
        ax.set_xticklabels(metrics, rotation=45, ha="right", fontsize=8)
        ax.set_yticks(np.arange(len(envs)) + 0.5)
        ax.set_yticklabels([ENV_SHORT[e] for e in envs], fontsize=8)
        ax.invert_yaxis()
        ax.axvline(8, color="k", lw=1.2)
        ax.set_title(f"{vlabel(var)}   (left: portable + regime | right: RDT canonicals)", fontsize=9)
    fig.suptitle("Metric availability across the deployment stack\n"
                 "the portable set keeps reporting numbers inside the VM guest, where the "
                 "RDT-backed canonical metrics stop reporting at all", fontsize=11)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    p2_figio.save(fig, out, "F3-availability-grid", dpi=160)
    plt.close(fig)


# ── F4: validation scatter ──────────────────────────────────────────────────

def fig_validation(base: Path, cells, out: Path):
    variants = sorted({k[1] for k in cells})
    fig, ax = plt.subplots(figsize=(6.4, 4.8))
    for var in variants:
        xs, ys = [], []
        for f in glob.glob(str(base / "*/v*/solo/*/rep*/portable.tsv")):
            p = Path(f)
            env, v, wl = p.parts[-6], p.parts[-5], p.parts[-3]
            if v != var or env == "vm-guest":   # GT is host-side; guest rows excluded
                continue
            cap = load_capture(p)
            gt = gt_llc_miss(p.parent)
            if gt and cap.get("membw_est", 0) > 0:
                xs.append(gt); ys.append(cap["membw_est"])
        if xs:
            rho = spearmanr(xs, ys)[0] if spearmanr else float("nan")
            ax.scatter(xs, ys, s=14, alpha=0.55, label=f"{vlabel(var)}   ρ = {rho:.2f}  (n={len(xs)} reps)")
    ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_xlabel("ground truth: LLC misses/s seen by host perf (median of the rep window)")
    ax.set_ylabel("estimated memory bandwidth, membw_est (MB/s, median of the rep window)")
    ax.set_title("The estimated memory bandwidth tracks true memory traffic\n"
                 "each point = one rep (host envs, all 7 workloads); ρ = Spearman rank correlation;\n"
                 "log-log because the workloads span three decades of memory intensity", fontsize=10)
    ax.legend(fontsize=9)
    ax.grid(alpha=0.2, which="both")
    fig.tight_layout()
    p2_figio.save(fig, out, "F4-membw-validation", dpi=160)
    plt.close(fig)


# ── F5: PSI falsification ───────────────────────────────────────────────────

def fig_psi(cells, out: Path):
    variants = sorted({k[1] for k in cells})
    envs = ["bare"] + ENV_ORDER
    fig, ax = plt.subplots(figsize=(7.6, 4.4))
    width = 0.38
    psi_all_zero = True
    for vi, var in enumerate(variants):
        mb = []
        for env in envs:
            mb.append(cell_median(cells, env, var, "app05_streaming", "membw_est") or 0)
            psi = cell_median(cells, env, var, "app05_streaming", "psi_mem")
            if psi and psi > 0.5:
                psi_all_zero = False
        x = np.arange(len(envs)) + (vi - 0.5) * width
        ax.bar(x, mb, width * 0.9, label=f"{vlabel(var)}")
    ax.set_yscale("log")
    ax.set_xticks(np.arange(len(envs)))
    ax.set_xticklabels([ENV_SHORT[e] for e in envs], fontsize=9)
    ax.set_ylabel("estimated memory bandwidth, membw_est,\non app05_streaming (MB/s, log)")
    ax.legend(fontsize=9, loc="upper left")
    ax.set_title("PSI memory pressure cannot see bandwidth saturation\n"
                 "(app05_streaming pins the memory channels; psi_mem only reacts to CAPACITY reclaim)",
                 fontsize=10)
    fig.tight_layout()
    p2_figio.save(fig, out, "F5-psi-bandwidth-blindness", dpi=160)
    plt.close(fig)


# ── F6: psp directional heatmap with values ─────────────────────────────────

def _fmt_delta(d: float) -> str:
    if abs(d) >= 10000:
        return f"{d/1000:+.0f}k"
    if abs(d) >= 1000:
        return f"{d/1000:+.1f}k"
    return f"{d:+.0f}"


def fig_psp(df: pd.DataFrame, out: Path):
    d = df[df.metric == "psp"].copy()
    if d.empty:
        return
    d["delta"] = pd.to_numeric(d["delta"], errors="coerce")
    variants = sorted(d.variant.unique())
    fig, axes = plt.subplots(1, len(variants), figsize=(6.4 * len(variants), 4.4), squeeze=False)
    for c, var in enumerate(variants):
        ax = axes[0][c]
        sub = d[d.variant == var]
        wls = sorted(sub.workload.unique())
        grid = np.full((len(wls), len(ENV_ORDER)), np.nan)
        for yi, wl in enumerate(wls):
            for xi, env in enumerate(ENV_ORDER):
                s = sub[(sub.workload == wl) & (sub.env == env)]
                if not s.empty:
                    grid[yi, xi] = s.cliffs_delta.iloc[0]
        im = ax.imshow(grid, cmap="RdBu_r", vmin=-1, vmax=1, aspect="auto")
        for yi, wl in enumerate(wls):
            for xi, env in enumerate(ENV_ORDER):
                s = sub[(sub.workload == wl) & (sub.env == env)]
                if s.empty:
                    continue
                sig = s.signif.iloc[0] != "n.s." and s.signif.iloc[0] != "n/a"
                val = _fmt_delta(s.delta.iloc[0]) if pd.notna(s.delta.iloc[0]) else "?"
                ax.text(xi, yi, val, ha="center", va="center", fontsize=9,
                        fontweight="bold" if sig else "normal",
                        color="white" if abs(grid[yi, xi]) > 0.6 else "black")
        ax.set_xticks(range(len(ENV_ORDER)))
        ax.set_xticklabels([ENV_SHORT[e] for e in ENV_ORDER], fontsize=8)
        ax.set_yticks(range(len(wls)))
        ax.set_yticklabels([w.replace("_", " ") for w in wls], fontsize=8)
        ax.set_title(f"{vlabel(var)}", fontsize=10)
        cb = fig.colorbar(im, ax=ax, fraction=0.045)
        cb.set_label("Cliff's δ (effect size of env vs bare)", fontsize=8)
    fig.suptitle("Scheduling-regime metric: involuntary preemptions per second of the profiled workload\n"
                 "cell = median Δ vs bare in events/s (bold = statistically significant); "
                 "red = MORE preemptions than bare, blue = fewer",
                 fontsize=10)
    fig.tight_layout(rect=(0, 0, 1, 0.88))
    p2_figio.save(fig, out, "F6-psp-directional", dpi=160)
    plt.close(fig)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("campaign_dir", type=Path)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    base = args.campaign_dir
    out = args.out or (base.parent / "figures" / base.name)
    out.mkdir(parents=True, exist_ok=True)

    tsv = base / "cross-deployment.tsv"
    if not tsv.exists():
        sys.exit(f"missing {tsv} — run bench/analyze-cross-deployment.py first")
    df = pd.read_csv(tsv, sep="\t")
    for col in ("ratio", "ci_lo", "ci_hi", "cliffs_delta"):
        df[col] = pd.to_numeric(df[col], errors="coerce")

    cells = scan_cells(base)
    fig_fingerprint(cells, out)
    fig_ratio(df, out)
    fig_claimclass(df, out)
    fig_availability(cells, out)
    fig_validation(base, cells, out)
    fig_psi(cells, out)
    fig_psp(df, out)
    for f in sorted(out.glob("*.png")):
        print(f)
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""plot-p2-15metric.py — P2 validation figure set from a 15-metric campaign.

Renders the FIGURES-PLAN.md "ready today" set (F1-F6) from a cross-deployment
campaign directory:

  F1  ratio-vs-bare (absolute metrics) dot+CI panel        <- cross-deployment.tsv
  F2  claim-class x significance matrix                    <- cross-deployment.tsv
  F3  availability grid (portable vs RDT canonicals)       <- portable.tsv scan
  F4  membw_est vs GT LLC-miss scatter + Spearman rho      <- portable+groundtruth
  F5  PSI bandwidth-blindness falsification (app05)        <- portable.tsv scan
  F6  psp directional delta heatmap (Cliff's delta + sig)  <- cross-deployment.tsv

Stats come from the analyzer TSV wherever one exists (never recomputed here);
the raw-capture scans (F3-F5) only take medians. Variant tags map to the
canonical descriptive labels. The C34 caveat (v2.1 mbw invalid pre-re-run) is
rendered as a hatched overlay on affected cells, so a reader cannot miss it.

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
import numpy as np
import pandas as pd

try:
    from scipy.stats import spearmanr
except ImportError:  # rho panel degrades gracefully
    spearmanr = None

VARIANT_LABELS = {
    "v2.1": "c-abi-cgroup",
    "v3.3": "ebpf-core-cgroup",
}
ENV_ORDER = ["container", "container-podman", "container-lxc", "container-k8s", "vm-guest"]
ENV_SHORT = {"container": "docker", "container-podman": "podman", "container-lxc": "lxc/incus",
             "container-k8s": "k8s", "vm-guest": "kvm-guest", "bare": "bare"}
# C34: v2.1 mbw values predate the D12 scope fix -> render hatched/annotated.
C34_INVALID = {("v2.1", "mbw")}

SIG_ORDER = {"***": 3, "**": 2, "*": 1, "n.s.": 0, "n/a": -1}


def vlabel(v: str) -> str:
    return VARIANT_LABELS.get(v, v)


def load_capture(path: Path) -> dict[str, float]:
    """Median per metric of one portable.tsv (header-mapped, ts-offset aware)."""
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


def gt_llc_miss(rep_dir: Path) -> float | None:
    """Median GT llc_miss/s for the rep (groundtruth.tsv: ts cpu_busy_pct ...
    llc_ref llc_miss ...; median over the window, robust to warmup spill)."""
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


# ── F1: ratio vs bare (absolute) ────────────────────────────────────────────

def fig_ratio(df: pd.DataFrame, out: Path):
    d = df[df.claim_class == "absolute"].copy()
    metrics = sorted(d.metric.unique())
    variants = sorted(d.variant.unique())
    fig, axes = plt.subplots(len(variants), len(metrics),
                             figsize=(3.2 * len(metrics), 3.0 * len(variants)),
                             sharey=True, squeeze=False)
    for r, var in enumerate(variants):
        for c, m in enumerate(metrics):
            ax = axes[r][c]
            sub = d[(d.variant == var) & (d.metric == m)]
            for i, env in enumerate(ENV_ORDER):
                s = sub[sub.env == env]
                if s.empty:
                    continue
                x = np.arange(len(s)) + i * 0.13 - 0.26
                # The bootstrap CI can exclude the point ratio (median-of-
                # medians vs resampled); clamp the bar arms at 0 for render.
                lo = np.clip(s.ratio - s.ci_lo, 0, None)
                hi = np.clip(s.ci_hi - s.ratio, 0, None)
                ax.errorbar(x, s.ratio, yerr=[lo, hi],
                            fmt="o", ms=4, capsize=2, label=ENV_SHORT[env])
            ax.axhspan(0.8, 1.25, color="green", alpha=0.08)
            ax.axhline(1.0, color="k", lw=0.6, ls=":")
            ax.set_yscale("log")
            ax.set_title(f"{vlabel(var)} — {m}", fontsize=9)
            wls = sorted(sub.workload.unique())
            ax.set_xticks(range(len(wls)))
            ax.set_xticklabels([w.split("_")[0] for w in wls], rotation=45, fontsize=7)
            if (var, m) in C34_INVALID:
                ax.text(0.5, 0.5, "C34: INVALID\n(pre-D12 scope)", transform=ax.transAxes,
                        ha="center", va="center", fontsize=11, color="crimson",
                        bbox=dict(facecolor="white", alpha=0.85), rotation=15)
            if r == 0 and c == len(metrics) - 1:
                ax.legend(fontsize=6, loc="upper left")
    fig.suptitle("F1 — Overhead vs bare, ABSOLUTE metrics (ratio + bootstrap CI; band = W4 0.8–1.25x)", y=1.0)
    fig.tight_layout()
    fig.savefig(out / "F1-ratio-vs-bare.png", dpi=160, bbox_inches="tight")
    plt.close(fig)


# ── F2: claim-class x significance matrix ───────────────────────────────────

def fig_claimclass(df: pd.DataFrame, out: Path):
    variants = sorted(df.variant.unique())
    fig, axes = plt.subplots(1, len(variants), figsize=(7.2 * len(variants), 4.6), squeeze=False)
    cls_color = {"absolute": "#2c7fb8", "directional": "#fdae61", "descriptive": "#bdbdbd"}
    for c, var in enumerate(variants):
        ax = axes[0][c]
        sub = df[df.variant == var]
        metrics = sorted(sub.metric.unique())
        for yi, m in enumerate(metrics):
            for xi, env in enumerate(ENV_ORDER):
                s = sub[(sub.metric == m) & (sub.env == env)]
                if s.empty:
                    continue
                cls = s.claim_class.iloc[0]
                best = max((SIG_ORDER.get(x, 0) for x in s.signif), default=0)
                ax.add_patch(plt.Rectangle((xi, yi), 0.94, 0.94,
                                           color=cls_color.get(cls, "#eeeeee"),
                                           alpha=0.35 + 0.2 * min(best, 3) / 3))
                stars = {3: "***", 2: "**", 1: "*", 0: "n.s.", -1: ""}[best]
                txt = stars
                if (var, m) in C34_INVALID:
                    txt = "C34!"
                ax.text(xi + 0.47, yi + 0.47, txt, ha="center", va="center", fontsize=8)
        ax.set_xlim(0, len(ENV_ORDER)); ax.set_ylim(0, len(metrics))
        ax.set_xticks(np.arange(len(ENV_ORDER)) + 0.5)
        ax.set_xticklabels([ENV_SHORT[e] for e in ENV_ORDER], fontsize=8)
        ax.set_yticks(np.arange(len(metrics)) + 0.5)
        ax.set_yticklabels(metrics, fontsize=8)
        ax.set_title(f"{vlabel(var)}", fontsize=10)
        ax.invert_yaxis()
    handles = [plt.Rectangle((0, 0), 1, 1, color=v, alpha=0.55) for v in cls_color.values()]
    axes[0][-1].legend(handles, cls_color.keys(), fontsize=7, loc="upper right",
                       bbox_to_anchor=(1.0, -0.08), ncol=3)
    fig.suptitle("F2 — Claim class x best vs-bare significance (env x metric); 'C34!' = v2.1 mbw invalid pre-re-run")
    fig.tight_layout()
    fig.savefig(out / "F2-claim-class-matrix.png", dpi=160, bbox_inches="tight")
    plt.close(fig)


# ── F3: availability grid ───────────────────────────────────────────────────

def fig_availability(cells, out: Path):
    metrics = ["schedlat", "psi_mem", "membw_est", "psi_io", "schedthr", "steal",
               "psp", "idle_preempt", "mbw", "llcocc", "llcmr"]
    variants = sorted({k[1] for k in cells})
    envs = ["bare"] + ENV_ORDER
    fig, axes = plt.subplots(1, len(variants), figsize=(6.4 * len(variants), 3.6), squeeze=False)
    for c, var in enumerate(variants):
        ax = axes[0][c]
        for yi, env in enumerate(envs):
            for xi, m in enumerate(metrics):
                reps = [r for (e, v, _w), rl in cells.items() if e == env and v == var for r in rl]
                ok = any(m in r for r in reps)
                color = "#41ab5d" if ok else "#d9d9d9"
                ax.add_patch(plt.Rectangle((xi, yi), 0.92, 0.92, color=color))
                ax.text(xi + 0.46, yi + 0.46, "ok" if ok else "--",
                        ha="center", va="center", fontsize=7,
                        color="white" if ok else "#636363")
        ax.set_xlim(0, len(metrics)); ax.set_ylim(0, len(envs))
        ax.set_xticks(np.arange(len(metrics)) + 0.5)
        ax.set_xticklabels(metrics, rotation=45, ha="right", fontsize=8)
        ax.set_yticks(np.arange(len(envs)) + 0.5)
        ax.set_yticklabels([ENV_SHORT[e] for e in envs], fontsize=8)
        ax.invert_yaxis()
        ax.axvline(8, color="k", lw=1.2)
        ax.set_title(f"{vlabel(var)}   (left: portable+regime | right: RDT canonicals)", fontsize=9)
    fig.suptitle("F3 — Availability: the portable set stays numeric in kvm-guest where the RDT canonicals go '--'")
    fig.tight_layout()
    fig.savefig(out / "F3-availability-grid.png", dpi=160, bbox_inches="tight")
    plt.close(fig)


# ── F4/F5: faithfulness + PSI falsification ─────────────────────────────────

def fig_faithfulness(base: Path, cells, out: Path):
    variants = sorted({k[1] for k in cells})
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.4))

    ax = axes[0]
    for var in variants:
        xs, ys = [], []
        for f in glob.glob(str(base / "*/v*/solo/*/rep*/portable.tsv")):
            p = Path(f)
            env, v, wl = p.parts[-6], p.parts[-5], p.parts[-3]
            if v != var or env == "vm-guest":   # host-side GT only (scope caveat)
                continue
            cap = load_capture(p)
            gt = gt_llc_miss(p.parent)
            if gt and cap.get("membw_est", 0) > 0:
                xs.append(gt); ys.append(cap["membw_est"])
        if xs:
            rho = spearmanr(xs, ys)[0] if spearmanr else float("nan")
            ax.scatter(xs, ys, s=12, alpha=0.55, label=f"{vlabel(var)}  ρ={rho:.3f} (n={len(xs)})")
    ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_xlabel("GT cache-misses (host perf, per rep)"); ax.set_ylabel("membw_est (MB/s)")
    ax.set_title("F4 — membw_est vs ground truth")
    ax.legend(fontsize=8)

    ax = axes[1]
    envs = ["bare"] + ENV_ORDER
    width = 0.38
    for vi, var in enumerate(variants):
        mb, psi = [], []
        for env in envs:
            reps = cells.get((env, var, "app05_streaming"), [])
            mb.append(statistics.median([r.get("membw_est", 0) for r in reps]) if reps else 0)
            psi.append(statistics.median([r.get("psi_mem", 0) for r in reps]) if reps else 0)
        x = np.arange(len(envs)) + (vi - 0.5) * width
        ax.bar(x, mb, width * 0.9, label=f"{vlabel(var)} membw_est")
        for xi, p in zip(x, psi):
            ax.text(xi, max(mb) * 1.02, f"psi={p:.0f}", rotation=90, fontsize=6, ha="center")
    ax.set_yscale("log")
    ax.set_xticks(np.arange(len(envs)))
    ax.set_xticklabels([ENV_SHORT[e] for e in envs], fontsize=8)
    ax.set_ylabel("membw_est MB/s (log)")
    ax.set_title("F5 — PSI bandwidth-blindness (app05): membw_est high, psi_mem flat")
    ax.legend(fontsize=7)

    fig.tight_layout()
    fig.savefig(out / "F4F5-faithfulness-psi.png", dpi=160, bbox_inches="tight")
    plt.close(fig)


# ── F6: psp directional heatmap ─────────────────────────────────────────────

def fig_psp(df: pd.DataFrame, out: Path):
    d = df[df.metric == "psp"].copy()
    if d.empty:
        return
    variants = sorted(d.variant.unique())
    fig, axes = plt.subplots(1, len(variants), figsize=(5.6 * len(variants), 3.8), squeeze=False)
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
                if not s.empty:
                    ax.text(xi, yi, s.signif.iloc[0], ha="center", va="center", fontsize=7)
        ax.set_xticks(range(len(ENV_ORDER)))
        ax.set_xticklabels([ENV_SHORT[e] for e in ENV_ORDER], fontsize=8)
        ax.set_yticks(range(len(wls)))
        ax.set_yticklabels([w.split("_")[0] for w in wls], fontsize=8)
        ax.set_title(f"{vlabel(var)}", fontsize=10)
        fig.colorbar(im, ax=ax, label="Cliff's δ (psp vs bare)")
    fig.suptitle("F6 — Scheduling-regime psp: direction/effect of env vs bare (cells = BH-FDR significance)")
    fig.tight_layout()
    fig.savefig(out / "F6-psp-directional.png", dpi=160, bbox_inches="tight")
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
    fig_ratio(df, out)
    fig_claimclass(df, out)
    fig_availability(cells, out)
    fig_faithfulness(base, cells, out)
    fig_psp(df, out)
    for f in sorted(out.glob("*.png")):
        print(f)
    return 0


if __name__ == "__main__":
    sys.exit(main())

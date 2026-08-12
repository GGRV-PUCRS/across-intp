#!/usr/bin/env python3
"""plot-sim-experiments.py -- the E1-E5 simulation-parameter campaign, rendered.

Two panels over the arm TSVs written by run-sim-experiments.sh:

  F-simexp-deltas  forest of each arm's IDI shift against the gate arm (same
                   tier, rel8 defaults). This is the "which knobs matter"
                   view: the cost-model knobs (regime term, degradation
                   table, ramp magnitude) move the index by thousands while
                   the simulation-physics knobs (startup delay, host count)
                   barely move it -- which is itself the finding.
  F-simexp-hosts   the ratio-matched host sweep as a curve per tier, gate arm
                   included as the 12-host point.

Colour follows the tier throughout (bench/plot/plot-iada-sim.py mapping);
arm identity is carried by the y-axis labels, not by hue. CIs are rep-level
bootstrap per p2_ci's convention; the arm-vs-gate interval resamples the two
groups independently (they are independent SA runs).

    python3 bench/plot/plot-sim-experiments.py --exp-dir <dir> [--out-set p2-sim-experiments]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parent))
import p2_ci                      # noqa: E402
import p2_figio                   # noqa: E402
import paper_style                # noqa: E402

COLOR = {"T1": "#c0392b", "A": "#2980b9", "B": "#27ae60"}
TIERS = ["T1", "A", "B"]

# Display order and reader-facing labels for the delta forest. e3 has its own
# panel; listing it here too would say "hosts moved nothing" twice.
ARMS = [
    ("e1-startup-0",      "startup 0 s"),
    ("e1-startup-10",     "startup 10 s"),
    ("e1-startup-50",     "startup 50 s"),
    ("e2-regime-off",     "regime term off"),
    ("e4-ramp-step",      "ramp step 1.90/1.93/1.95"),
    ("e4-ramp-convex",    "ramp convex 1.07/1.55/1.95"),
    ("e4-ramp-measured",  "ramp measured 1.10/1.25/1.41"),
    ("e5-degtable-paper", "Meyer Table 2"),
]
GROUP_OF = {"e1": "E1 co-execution window", "e2": "E2 ablation",
            "e4": "E4 ramp shape", "e5": "E5 degradation table"}
HOSTS_GATE = 12


def load(path: Path) -> pd.DataFrame:
    d = pd.read_csv(path, sep="\t")
    d["idi_avg"] = pd.to_numeric(d["idi_avg"], errors="coerce")
    return d.dropna(subset=["idi_avg"])


def diff_ci(a, b, seed_offset=0, n=p2_ci.BOOTSTRAP_N):
    a = np.asarray(a, float); b = np.asarray(b, float)
    point = float(b.mean() - a.mean())
    if len(a) < 2 or len(b) < 2:
        return point, point, point
    rng = np.random.default_rng(p2_ci.BOOTSTRAP_SEED + seed_offset)
    d = (rng.choice(b, (n, len(b))).mean(1) - rng.choice(a, (n, len(a))).mean(1))
    lo, hi = np.nanpercentile(d, list(p2_ci.CI_PCTILES))
    return point, float(lo), float(hi)


def fig_deltas(entries, outdir):
    fig, ax = plt.subplots(figsize=(paper_style.TEXT_WIDTH * 0.62, 3.1))
    ax.axvline(0, color="#444444", lw=0.8, zorder=1)

    ypos, ylabels, group_bounds = [], [], {}
    y = 0.0
    last_group = None
    for e in entries:                      # entries arrive top-to-bottom
        if e["group"] != last_group:
            y -= 0.95                      # gap row that also hosts the group tag
            last_group = e["group"]
            group_bounds.setdefault(e["group"], []).append(y)
        ax.plot([e["lo"], e["hi"]], [y, y], lw=1.3, color=COLOR[e["tier"]],
                solid_capstyle="round", zorder=3)
        ax.scatter([e["point"]], [y], s=11, color=COLOR[e["tier"]],
                   edgecolor="white", linewidth=0.5, zorder=4)
        if not (e["lo"] <= 0 <= e["hi"]):
            ax.text(e["point"], y + 0.34, f"{e['point']:+.0f}", ha="center",
                    va="bottom", fontsize=paper_style.ANNOT, color="#222222")
        ypos.append(y); ylabels.append(e["label"])
        group_bounds[e["group"]].append(y)
        y -= 1.0

    ax.set_yticks(ypos); ax.set_yticklabels(ylabels)
    # Horizontal group tags in the gap row above each block: the rotated
    # right-margin version collided as soon as a group had fewer rows than
    # its label needed.
    # Right-aligned: the gap rows are empty on the right, while the left is
    # where the big negative intervals and their value tags live.
    for g, ys in group_bounds.items():
        ax.text(0.99, max(ys) + 0.62, g, transform=ax.get_yaxis_transform(),
                ha="right", va="center", fontsize=paper_style.LEGEND,
                color="#555555", style="italic")
    ax.set_xlabel("IDI shift vs the all-defaults gate arm (same tier)")
    ax.set_title("Cost-model knobs move the index by thousands; "
                 "simulation-physics knobs do not", pad=3)
    handles = [plt.Line2D([0], [0], lw=1.6, color=COLOR[t], label=f"tier {t}")
               for t in TIERS]
    # Upper left: the E1 block hugs zero, so the far-left of the top rows is
    # the one region no interval, tag, or annotation reaches.
    ax.legend(handles=handles, loc="upper left", handlelength=1.3)
    ax.grid(axis="y", visible=False)
    ax.margins(y=0.04)

    p2_figio.save(fig, outdir, "F-simexp-deltas")
    print(p2_figio.describe(outdir, "F-simexp-deltas"))
    plt.close(fig)


def fig_hosts(curves, outdir):
    fig, ax = plt.subplots(figsize=(paper_style.COLUMN_WIDTH, 2.0))
    for tier in TIERS:
        pts = curves[tier]                 # [(hosts, mean, lo, hi)]
        xs = [p[0] for p in pts]
        ax.fill_between(xs, [p[2] for p in pts], [p[3] for p in pts],
                        color=COLOR[tier], alpha=0.12, linewidth=0)
        ax.plot(xs, [p[1] for p in pts], lw=1.4, color=COLOR[tier],
                marker="o", markersize=3.2, markeredgecolor="white",
                markeredgewidth=0.5, label=f"tier {tier}")
    ax.axvline(28, color="#888888", lw=0.7, ls=(0, (2.5, 1.5)))
    ax.text(27.6, 200, "1 container/host", ha="right", va="bottom",
            fontsize=paper_style.ANNOT, color="#666666", rotation=90)
    ax.set_xlabel("hosts (apps/host 3.0 → 1.0, Meyer 2021 ratios)")
    ax.set_ylabel("interference degradation index")
    ax.set_title("The index is flat across the host sweep — placement cost is\n"
                 "trace-driven, so consolidation pressure never enters it", pad=3)
    ax.set_xticks([9, 12, 14, 19, 23, 28])
    ax.legend(loc="lower left", ncol=3, handlelength=1.2, columnspacing=0.9)
    ax.set_ylim(0, None)

    p2_figio.save(fig, outdir, "F-simexp-hosts")
    print(p2_figio.describe(outdir, "F-simexp-hosts"))
    plt.close(fig)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--exp-dir", required=True, type=Path)
    ap.add_argument("--out-set", default="p2-sim-experiments")
    ap.add_argument("--figures-root", type=Path, default=Path("results/figures"))
    args = ap.parse_args()

    gate = load(args.exp_dir / "gate-default.tsv")
    gate_by_tier = {t: gate[gate.tier == t].idi_avg.to_numpy() for t in TIERS}

    entries, table = [], []
    for ai, (stem, label) in enumerate(ARMS):
        p = args.exp_dir / f"{stem}.tsv"
        if not p.exists():
            print(f"[skip] {stem}: no TSV", file=sys.stderr)
            continue
        arm = load(p)
        group = GROUP_OF[stem.split("-")[0]]
        for ti, tier in enumerate(TIERS):
            vals = arm[arm.tier == tier].idi_avg.to_numpy()
            if not len(vals):
                continue
            point, lo, hi = diff_ci(gate_by_tier[tier], vals,
                                    seed_offset=300 + ai * 10 + ti)
            row_label = label if len(arm.tier.unique()) == 1 else f"{label} · {tier}"
            entries.append({"tier": tier, "label": row_label, "group": group,
                            "point": point, "lo": lo, "hi": hi})
            table.append({"arm": stem, "tier": tier, "n": len(vals),
                          "idi_mean": round(float(vals.mean()), 2),
                          "delta_vs_gate": round(point, 2),
                          "ci_lo": round(lo, 2), "ci_hi": round(hi, 2),
                          "excludes_zero": not (lo <= 0 <= hi)})

    curves = {t: [] for t in TIERS}
    for hosts in (9, 12, 14, 19, 23, 28):
        d = gate if hosts == HOSTS_GATE else None
        if d is None:
            p = args.exp_dir / f"e3-hosts-{hosts}.tsv"
            if not p.exists():
                continue
            d = load(p)
        for ti, tier in enumerate(TIERS):
            vals = d[d.tier == tier].idi_avg.to_numpy()
            mean, lo, hi = p2_ci.rep_ci(vals, seed_offset=500 + hosts + ti)
            curves[tier].append((hosts, mean, lo, hi))
            table.append({"arm": f"e3-hosts-{hosts}" if hosts != HOSTS_GATE
                          else "gate-default", "tier": tier, "n": len(vals),
                          "idi_mean": round(mean, 2), "delta_vs_gate": None,
                          "ci_lo": round(lo, 2), "ci_hi": round(hi, 2),
                          "excludes_zero": None})

    outdir = args.figures_root / args.out_set
    outdir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(table).to_csv(outdir / "summary.tsv", sep="\t", index=False)

    paper_style.apply()
    fig_deltas(entries, outdir)
    fig_hosts(curves, outdir)
    print(pd.DataFrame([t for t in table if t["excludes_zero"]]).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

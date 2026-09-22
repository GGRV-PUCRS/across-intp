#!/usr/bin/env python3
"""plot-fig-idi-decomp-jsa.py -- fig_idi_decomp.pdf (fig:idi_decomp, \\figph{S2}).

Decomposition of the interference-degradation index inside the KVM guest, per
classifier configuration (canonical-7 = T1, proxy-swap = A, full-fingerprint =
B; n=10). Left panel: the six per-interval SAO costs -- interval 1 is
fillInitialSolution's output before any stochastic SA swap, so it is
deterministic (identical across all 10 reps) and is drawn as the marked
"pre-search" point; the overlaid diamond is the closed-form prediction from
the per-application geometric-mean costs (sum over hosts of per-host products
of cost*Hpe/Cpe, /6), which S2 validated against the actual first interval
within 4.4% for every tier. Right panel: the final-interval index, mean with
rep-level 95% bootstrap CI, tagged with the first-to-final change.

Sources of record (no value recomputed beyond CIs, which use the shared p2_ci
rep-level bootstrap convention):
  s2-decomp.tsv    per-rep first/last interval costs (endpoint check)
  s2-summary.tsv   closed-form values, geometric means, adjudicated CIs

Intervals 2-5 are NOT in those TSVs; they are re-parsed from the S3 gate
campaign's cloudsim.log files ("Algorithm: SAO" blocks, same n=10/tier runs),
either from --intervals-tsv (tier/rep/interval/cost, pre-extracted) or
directly from --s3-work-root. Parsed endpoints are validated against
s2-decomp.tsv before anything is plotted; without any interval source the
figure degrades to the two endpoints and says so in the log.

    python3 bench/plot/plot-fig-idi-decomp-jsa.py \
        --data-root DIR --out DIR [--intervals-tsv TSV | --s3-work-root DIR]

"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jsa_style as style  # noqa: E402
import p2_ci  # noqa: E402  (shared rep-level bootstrap CI convention, N=10000 seed=20260607)

TIER_DESC = {"T1": "canonical-7", "A": "proxy-swap", "B": "full-fingerprint"}
TIER_ORDER = ["T1", "A", "B"]
TIER_COLOR = {"T1": style.SKY_BLUE, "A": style.REDDISH_PURPLE, "B": style.ORANGE}
N_INTERVALS = 6


def _read_endpoints(tsv: Path) -> dict[str, dict[str, list[float]]]:
    """tier -> {'first': [...], 'last': [...]} per rep, in file order."""
    out: dict[str, dict[str, list[float]]] = {}
    for r in csv.DictReader(tsv.open(), delimiter="\t"):
        d = out.setdefault(r["tier"], {"first": [], "last": []})
        d["first"].append(float(r["first_interval_actual"]))
        d["last"].append(float(r["last_interval_actual"]))
    return out


def _read_summary(tsv: Path) -> dict[str, dict]:
    out = {}
    for r in csv.DictReader(tsv.open(), delimiter="\t"):
        if r["tier"] in TIER_ORDER and r.get("closed_form_first"):
            out[r["tier"]] = r
    return out


def _parse_sao_intervals(log_text: str) -> list[float]:
    parts = log_text.split("Algorithm: SAO")
    if len(parts) < 2:
        return []
    blk = parts[1].split("Migrations:")[0]
    return [float(x) for x in re.findall(r"^\s*([\d.]+)\s*$", blk, re.M)]


def _read_intervals_from_logs(work_root: Path) -> dict[tuple[str, str], list[float]]:
    """(tier, rep) -> 6 interval costs, from the S3 gate cloudsim.log files."""
    out = {}
    for tier in TIER_ORDER:
        logs = sorted((work_root / f"s3-gate-{tier}" / tier / "v3.3" / "vm-guest")
                      .glob("rep*/cloudsim.log"))
        for lp in logs:
            iv = _parse_sao_intervals(lp.open(errors="ignore").read())
            if len(iv) != N_INTERVALS:
                print(f"WARN: {lp} has {len(iv)} SAO intervals, "
                      f"expected {N_INTERVALS} -- skipped")
                continue
            out[(tier, lp.parent.name)] = iv
    return out


def _read_intervals_tsv(tsv: Path) -> dict[tuple[str, str], list[float]]:
    by_rep: dict[tuple[str, str], dict[int, float]] = defaultdict(dict)
    for r in csv.DictReader(tsv.open(), delimiter="\t"):
        by_rep[(r["tier"], r["rep"])][int(r["interval"])] = float(r["cost"])
    out = {}
    for key, d in by_rep.items():
        if sorted(d) == list(range(1, N_INTERVALS + 1)):
            out[key] = [d[i] for i in range(1, N_INTERVALS + 1)]
        else:
            print(f"WARN: {key} has intervals {sorted(d)}, "
                  f"expected 1..{N_INTERVALS} -- skipped")
    return out


def fig_idi_decomp(data_root: Path, out: Path,
                   intervals: dict[tuple[str, str], list[float]]) -> None:
    endpoints = _read_endpoints(data_root / "s2-decomp.tsv")
    summary = _read_summary(data_root / "s2-summary.tsv")

    # Validate any parsed interval source against the endpoint source of record
    # before trusting it for the shape of intervals 2-5.
    if intervals:
        for tier in TIER_ORDER:
            reps = [iv for (t, _r), iv in intervals.items() if t == tier]
            if not reps:
                continue
            firsts = sorted(iv[0] for iv in reps)
            lasts = sorted(iv[-1] for iv in reps)
            if (np.allclose(firsts, sorted(endpoints[tier]["first"]), atol=0.01)
                    and np.allclose(lasts, sorted(endpoints[tier]["last"]), atol=0.01)):
                print(f"VALIDATION OK: interval source endpoints match "
                      f"s2-decomp.tsv for {TIER_DESC[tier]} (n={len(reps)})")
            else:
                print(f"VALIDATION WARN: interval source endpoints differ from "
                      f"s2-decomp.tsv for {TIER_DESC[tier]} "
                      f"(firsts {firsts} vs {sorted(endpoints[tier]['first'])})")
        full_trajectories = True
    else:
        intervals = {(tier, f"rep{i}"): [f, l]
                     for tier in TIER_ORDER
                     for i, (f, l) in enumerate(
                         zip(endpoints[tier]["first"], endpoints[tier]["last"]))}
        full_trajectories = False
        print("WARN: no interval source (logs/--intervals-tsv); "
              "plotting endpoints 1 and 6 only")

    width = style.TEXT_WIDTH
    height = 2.55
    fig, (axL, axR) = plt.subplots(
        1, 2, figsize=(width, height), layout="constrained",
        gridspec_kw={"width_ratios": [1.55, 1.0]})

    # ---- Left panel: interval-cost trajectories -----------------------------
    xs = np.arange(1, N_INTERVALS + 1)
    top = 0.0
    for ti, tier in enumerate(TIER_ORDER):
        reps = np.asarray([iv for (t, _r), iv in intervals.items() if t == tier],
                          dtype=float)
        if reps.size == 0:
            continue
        ms, los, his = [], [], []
        for i in range(reps.shape[1]):
            m, lo, hi = p2_ci.rep_ci(reps[:, i], seed_offset=50 + ti * 10 + i)
            ms.append(m); los.append(lo); his.append(hi)
        top = max(top, max(his), float(summary[tier]["closed_form_first"]))
        axL.fill_between(xs, los, his, color=TIER_COLOR[tier], alpha=0.15,
                         linewidth=0, zorder=1)
        axL.plot(xs, ms, color=TIER_COLOR[tier], lw=1.1, marker="o",
                 markersize=3.2, markeredgecolor="white", markeredgewidth=0.5,
                 zorder=2)
        # Interval 1 is the pre-search placement (deterministic): mark it.
        axL.plot(xs[0], ms[0], marker="D", markersize=5.5, markerfacecolor="white",
                 markeredgecolor=TIER_COLOR[tier], markeredgewidth=1.1, zorder=4)
        # Closed-form prediction for the first interval: a distinct marker at
        # x=1, offset so it never hides the actual point.
        cf = float(summary[tier]["closed_form_first"])
        axL.plot(xs[0] - 0.16, cf, marker="v", markersize=5.0,
                 markerfacecolor="black", markeredgecolor="black", zorder=5)
        axL.annotate(f"{cf:.0f}", (xs[0] - 0.16, cf), textcoords="offset points",
                     xytext=(-2, 5), ha="right", fontsize=style.ANNOT)
        print(f"idi_decomp {TIER_DESC[tier]}: interval means "
              + " ".join(f"{m:.0f}" for m in ms)
              + f"; closed form {cf:.0f}")

    axL.set_xticks(xs)
    axL.set_xlabel("analysis interval", fontsize=style.BODY)
    axL.set_ylabel("interval cost (search objective)", fontsize=style.BODY)
    axL.set_xlim(0.6, N_INTERVALS + 0.4)
    axL.set_ylim(0, top * 1.20)
    axL.grid(axis="y", ls=":", alpha=0.3)
    axL.set_axisbelow(True)
    if full_trajectories:
        axL.annotate("interval 1 = pre-search placement",
                     xy=(0.03, 0.97), xycoords="axes fraction",
                     ha="left", va="top", fontsize=style.ANNOT)

    # ---- Right panel: final-interval index ----------------------------------
    bw = 0.55
    final_tags = []
    for ti, tier in enumerate(TIER_ORDER):
        vals = np.asarray(endpoints[tier]["last"], dtype=float)
        m, lo, hi = p2_ci.rep_ci(vals, seed_offset=60 + ti)
        axR.bar(ti, m, bw, yerr=p2_ci.yerr(m, lo, hi), capsize=2.5,
                color=TIER_COLOR[tier], alpha=0.88, edgecolor="black",
                linewidth=0.4, zorder=2)
        axR.text(ti, hi + top * 0.015, f"{m:.0f}", ha="center", va="bottom",
                 fontsize=style.ANNOT)
        first = float(np.mean(endpoints[tier]["first"]))
        pct = (m - first) / first * 100.0
        final_tags.append((ti, hi + top * 0.085, f"{pct:+.0f}%"))
        ref = summary[tier]
        if abs(m - float(ref["actual_last_mean"])) < 1.0:
            print(f"VALIDATION OK: {TIER_DESC[tier]} final mean {m:.1f} matches "
                  f"s2-summary.tsv")
        else:
            print(f"VALIDATION WARN: {TIER_DESC[tier]} final mean {m:.1f} vs "
                  f"summary {ref['actual_last_mean']}")
        print(f"idi_decomp {TIER_DESC[tier]} final: mean {m:.0f} "
              f"(CI {lo:.0f}-{hi:.0f}), {pct:+.1f}% vs interval 1")
    for ti, y, tag in final_tags:
        axR.text(ti, y, tag, ha="center", va="bottom",
                 fontsize=style.ANNOT, color="black")
    axR.annotate("tag = change vs interval 1",
                 xy=(0.03, 0.97), xycoords="axes fraction",
                 ha="left", va="top", fontsize=style.ANNOT)
    axR.set_xticks(range(len(TIER_ORDER)))
    axR.set_xticklabels([TIER_DESC[t] for t in TIER_ORDER], fontsize=style.BODY)
    axR.set_ylim(0, top * 1.20)
    axR.set_ylabel("final-interval index\n(mean, rep-level 95% CI)",
                   fontsize=style.BODY)
    axR.grid(axis="y", ls=":", alpha=0.3)
    axR.set_axisbelow(True)

    handles = [Line2D([0], [0], color=TIER_COLOR[t], lw=1.1, marker="o",
                      markersize=3.2, markeredgecolor="white",
                      label=TIER_DESC[t]) for t in TIER_ORDER]
    handles.append(Line2D([0], [0], marker="D", markersize=5.0, lw=0,
                          markerfacecolor="white", markeredgecolor="black",
                          label="interval 1 (pre-search)"))
    handles.append(Line2D([0], [0], marker="v", markersize=5.0, lw=0,
                          markerfacecolor="black", markeredgecolor="black",
                          label="closed-form prediction (interval 1)"))
    style.compact_legend(fig, handles, [h.get_label() for h in handles], ncol=5)

    spec = style.FigSpec(width, height, "fig:idi_decomp")
    style.save(fig, out / "fig_idi_decomp.pdf", spec)
    plt.close(fig)
    print(f"wrote {out / 'fig_idi_decomp.pdf'}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-root", type=Path,
                    default=Path("bench/iada/results/sim-experiments-20260917-s16"))
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--intervals-tsv", type=Path, default=None,
                    help="pre-extracted tier/rep/interval/cost TSV; wins over "
                         "--s3-work-root")
    ap.add_argument("--s3-work-root", type=Path, default=Path("/tmp/s3-work"),
                    help="dir holding s3-gate-<tier>/.../rep*/cloudsim.log; "
                         "intervals 2-5 source when no --intervals-tsv")
    args = ap.parse_args()
    style.apply()
    args.out.mkdir(parents=True, exist_ok=True)

    intervals: dict[tuple[str, str], list[float]] = {}
    if args.intervals_tsv is not None:
        intervals = _read_intervals_tsv(args.intervals_tsv)
    elif args.s3_work_root is not None and args.s3_work_root.exists():
        intervals = _read_intervals_from_logs(args.s3_work_root)
    fig_idi_decomp(args.data_root, args.out, intervals)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

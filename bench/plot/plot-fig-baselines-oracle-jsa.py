#!/usr/bin/env python3
"""plot-fig-baselines-oracle-jsa.py -- two new, exploratory JSA figures from
this session's Phase 3.2/3.4 follow-up work (jsa-repo-fix-brief.md):

  fig_baselines.pdf (fig:baselines) -- IASA (the paper's own scheduler) vs.
    CIAPA vs. EVEN, per tier. Both baselines were promised in
    sec:methodology:pipeline ("against EVEN, CIAPA, and Segmented
    baselines") but never actually run before this session (the `approach`
    branch was a hardcoded literal). Log-scale y-axis: EVEN's blind
    round-robin placement is 6.7-16.2x worse than IASA's search, which
    would flatten IASA/CIAPA to invisible bars on a linear axis.

  fig_oracle.pdf (fig:oracle) -- each tier's own self-reported IDI vs. a
    common (tier B) classifier's re-score of the SAME converged placement,
    both over an identical (full-trace) classification window. Significance
    is a paired rep-level bootstrap of (oracle - self): T1's own classifier
    reads its placements as markedly worse than the common yardstick does,
    A's as slightly better; B is an exact self-consistency check by
    construction (the same classifier scoring itself).

Sources of record (no value recomputed here, only re-presented):
  bench/iada/results/sim-experiments-20260916/{even,ciapa}-baseline-t1ab-n10.tsv
  bench/iada/results/sim-experiments-20260916/gate-{B-psp-n20,T1-A-n10}.tsv
  bench/iada/results/sim-experiments-20260916/oracle-t1ab-n10.tsv
  bench/iada/DECISIONS-sim-experiments.md S10, S12, S13 (numbers cross-checked)

    python3 bench/plot/plot-fig-baselines-oracle-jsa.py --data-root DIR --out DIR
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean

import numpy as np
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jsa_style as style  # noqa: E402
import p2_ci  # noqa: E402  (shared rep-level bootstrap CI convention, N=10000 seed=20260607)

TIER_DESC = {"T1": "Canonical 7-metric", "A": "Proxy-swap", "B": "Full 15-metric"}
TIER_ORDER = ["T1", "A", "B"]
APPROACH_COLOR = {"IASA": style.BLUISH_GREEN, "CIAPA": style.ORANGE, "EVEN": style.VERMILLION}


def _read_idi(tsv: Path, col: str = "idi_avg") -> dict[str, list[float]]:
    out = defaultdict(list)
    for r in csv.DictReader(tsv.open(), delimiter="\t"):
        v = r.get(col)
        if v in (None, "", "FAIL"):
            continue
        out[r["tier"]].append(float(v))
    return out


def fig_baselines(data_root: Path, out: Path) -> None:
    iasa_gate = _read_idi(data_root / "gate-T1-A-n10.tsv")
    iasa_gate["B"] = _read_idi(data_root / "gate-B-psp-n20.tsv")["B"]
    even = _read_idi(data_root / "even-baseline-t1ab-n10.tsv", col="interference_avg")
    ciapa = _read_idi(data_root / "ciapa-baseline-t1ab-n10.tsv")

    approaches = ["IASA", "CIAPA", "EVEN"]
    data = {"IASA": iasa_gate, "CIAPA": ciapa, "EVEN": even}

    width = style.TEXT_WIDTH
    height = 2.4
    fig, ax = plt.subplots(figsize=(width, height), layout="constrained")

    n_tiers = len(TIER_ORDER)
    n_app = len(approaches)
    group_w = 0.8
    bar_w = group_w / n_app
    x0 = np.arange(n_tiers)

    global_max = 0.0
    for ai, appr in enumerate(approaches):
        xs = x0 + (ai - (n_app - 1) / 2) * bar_w
        means, los, his = [], [], []
        for t in TIER_ORDER:
            vals = data[appr].get(t, [])
            if not vals:
                means.append(0); los.append(0); his.append(0)
                continue
            if len(vals) > 1 and len(set(vals)) > 1:
                m, lo, hi = p2_ci.rep_ci(np.array(vals), seed_offset=hash((appr, t)) % 1000)
            else:
                m = mean(vals)
                lo = hi = m  # EVEN is deterministic -- zero-width CI, not an error
            means.append(m); los.append(lo); his.append(hi)
        global_max = max(global_max, max(means))
        yerr = [[m - lo for m, lo in zip(means, los)], [hi - m for m, hi in zip(means, his)]]
        ax.bar(xs, means, bar_w * 0.92, yerr=yerr, capsize=2.5,
               color=APPROACH_COLOR[appr], alpha=0.88,
               edgecolor="black", linewidth=0.4, label=appr, zorder=2)
        for x, m in zip(xs, means):
            if m > 0:
                ax.text(x, m * 1.03, f"{m:.0f}", ha="center", va="bottom",
                        fontsize=style.ANNOT - 1.0, rotation=90)

    ax.set_yscale("log")
    ax.set_ylim(top=global_max * 3.2)  # headroom for rotated bar labels + legend row
    ax.set_xticks(x0)
    ax.set_xticklabels([TIER_DESC[t] for t in TIER_ORDER], fontsize=style.BODY)
    ax.set_ylabel("interference cost (log scale)\n— lower = better placement —",
                  fontsize=style.BODY)
    ax.grid(axis="y", ls=":", alpha=0.3, which="both")
    style.compact_legend(ax, *ax.get_legend_handles_labels(), ncol=3)

    spec = style.FigSpec(width, height, "fig:baselines")
    style.save(fig, out / "fig_baselines.pdf", spec)
    plt.close(fig)
    print(f"wrote {out / 'fig_baselines.pdf'}")


def fig_oracle(data_root: Path, out: Path) -> None:
    self_v = defaultdict(list)
    oracle_v = defaultdict(list)
    rows = [r for r in csv.DictReader((data_root / "oracle-t1ab-n10.tsv").open(), delimiter="\t")
            if r.get("self_idi") not in (None, "", "FAIL")]
    # self and oracle score the same placement per rep, so keep rep order aligned for pairing
    for r in sorted(rows, key=lambda r: (r["tier"], int(r["rep"]))):
        self_v[r["tier"]].append(float(r["self_idi"]))
        oracle_v[r["tier"]].append(float(r["oracle_idi"]))

    width = style.TEXT_WIDTH * 0.62
    height = 2.4
    fig, ax = plt.subplots(figsize=(width, height), layout="constrained")

    x = np.arange(len(TIER_ORDER))
    w = 0.32

    self_m, self_lo, self_hi = [], [], []
    oracle_m, oracle_lo, oracle_hi = [], [], []
    sig_label = {}
    for ti, t in enumerate(TIER_ORDER):
        s, o = np.array(self_v[t]), np.array(oracle_v[t])
        sm, slo, shi = p2_ci.rep_ci(s, seed_offset=ti * 2)
        om, olo, ohi = p2_ci.rep_ci(o, seed_offset=ti * 2 + 1)
        self_m.append(sm); self_lo.append(slo); self_hi.append(shi)
        oracle_m.append(om); oracle_lo.append(olo); oracle_hi.append(ohi)
        if np.allclose(s, o):
            sig_label[t] = "self-check\n(Δ=0)"
            continue
        _, dlo, dhi = p2_ci.rep_ci(o - s, seed_offset=100 + ti)
        sig_label[t] = "*" if not (dlo <= 0 <= dhi) else "n.s."

    self_err = p2_ci.yerr_many(list(zip(self_m, self_lo, self_hi)))
    oracle_err = p2_ci.yerr_many(list(zip(oracle_m, oracle_lo, oracle_hi)))

    ax.bar(x - w / 2, self_m, w, yerr=self_err, capsize=2.5, color=style.BLUE,
           alpha=0.88, edgecolor="black", linewidth=0.4, label="self (own classifier)")
    ax.bar(x + w / 2, oracle_m, w, yerr=oracle_err, capsize=2.5, color=style.ORANGE,
           alpha=0.88, edgecolor="black", linewidth=0.4, label="oracle (tier B classifier)")

    ymax = max(max(self_hi), max(oracle_hi))
    for xi, t in enumerate(TIER_ORDER):
        ax.text(xi, ymax * 1.10, sig_label[t], ha="center", va="bottom",
                fontsize=style.ANNOT, fontweight="bold" if sig_label[t] == "*" else "normal")

    ax.set_ylim(0, ymax * 1.28)
    ax.set_xticks(x)
    ax.set_xticklabels([TIER_DESC[t] for t in TIER_ORDER], fontsize=style.BODY)
    ax.set_ylabel("interference degradation index\n(full-window re-score)", fontsize=style.BODY)
    ax.grid(axis="y", ls=":", alpha=0.3)
    style.compact_legend(ax, *ax.get_legend_handles_labels(), ncol=2)

    spec = style.FigSpec(width, height, "fig:oracle")
    style.save(fig, out / "fig_oracle.pdf", spec)
    plt.close(fig)
    print(f"wrote {out / 'fig_oracle.pdf'}")


REF_COLOR = {"T1": style.SKY_BLUE, "A": style.REDDISH_PURPLE, "B": style.ORANGE}


def fig_oracle_matrix(data_root: Path, s15_root: Path, out: Path) -> None:
    """fig:oracle_matrix -- the full placement-tier x reference-classifier matrix.

    fig_oracle() shows one column of this matrix (reference = tier B), which
    favours B by construction: B's search optimized against the very classifier
    that then scores it. S15 completes the other two columns, so the reader can
    see whether any placement ordering survives a change of reference.

    Grouped bars: one group per PLACEMENT tier, one bar per REFERENCE
    classifier. The tier's own self score (its classifier, same full window)
    is drawn as a tick on each bar, so the self-vs-oracle gap is visible per
    cell. Diagonal cells (placement == reference) are exact self-consistency
    checks and are tagged as such rather than starred.

    No value is recomputed here beyond the CIs, which use the same rep-level
    bootstrap convention as every other figure in the set.
    """
    sources = {
        "B": data_root / "oracle-t1ab-n10.tsv",
        "T1": s15_root / "oracle-refT1-t1ab-n10.tsv",
        "A": s15_root / "oracle-refA-t1ab-n10.tsv",
    }
    refs = [r for r in TIER_ORDER if sources[r].exists()]
    if not refs:
        print("fig_oracle_matrix: no oracle TSVs found, skipped")
        return

    self_v, oracle_v = {}, {}
    for r in refs:
        self_v[r] = _read_idi(sources[r], col="self_idi")
        oracle_v[r] = _read_idi(sources[r], col="oracle_idi")

    width = style.TEXT_WIDTH
    height = 2.6
    fig, ax = plt.subplots(figsize=(width, height), layout="constrained")

    x0 = np.arange(len(TIER_ORDER))
    group_w = 0.8
    bar_w = group_w / len(refs)

    top = 0.0
    for ri, r in enumerate(refs):
        means, errs_lo, errs_hi, tags, selfs, diag = [], [], [], [], [], []
        for ti, t in enumerate(TIER_ORDER):
            o = np.asarray(oracle_v[r].get(t, []), dtype=float)
            s_ = np.asarray(self_v[r].get(t, []), dtype=float)
            if o.size == 0:
                means.append(np.nan); errs_lo.append(np.nan); errs_hi.append(np.nan)
                tags.append(""); selfs.append(np.nan)
                continue
            om, olo, ohi = p2_ci.rep_ci(o, seed_offset=200 + ri * 10 + ti)
            means.append(om); errs_lo.append(olo); errs_hi.append(ohi)
            selfs.append(float(s_.mean()) if s_.size else np.nan)
            if s_.size == o.size and np.allclose(s_, o):
                tags.append(r"$\Delta{=}0$")  # diagonal: exact self-consistency check
                diag.append(len(means) - 1)
            else:
                # paired bootstrap of (oracle - self): same placement, same rep.
                _, dlo, dhi = p2_ci.rep_ci(o - s_, seed_offset=400 + ri * 10 + ti)
                tags.append("*" if not (dlo <= 0 <= dhi) else "n.s.")
            top = max(top, ohi)

        xs = x0 - group_w / 2 + bar_w * (ri + 0.5)
        yerr = [[max(0.0, m - lo) for m, lo in zip(means, errs_lo)],
                [max(0.0, hi - m) for m, hi in zip(means, errs_hi)]]
        bars = ax.bar(xs, means, bar_w * 0.9, yerr=yerr, capsize=2.0,
                      color=REF_COLOR[r], alpha=0.88, edgecolor="black", linewidth=0.4,
                      label=f"reference: {TIER_DESC[r].lower()}")
        # Diagonal cells (placement == reference) are the exact self-consistency
        # check, not a measurement: hatch them so they read as structurally
        # different from the six off-diagonal comparisons.
        for di in diag:
            bars[di].set_hatch("////")
        # Self-score tick. Deliberately narrower than the bar: at full bar width
        # the ticks of adjacent bars abut and read as one continuous rule across
        # the group, which is exactly the wrong reading -- each tick belongs to
        # its own run.
        for xi, sv, m in zip(xs, selfs, means):
            if np.isnan(sv):
                continue
            # Dotted stem from the bar top to the self tick: the quantity the
            # starred paired test is about IS this gap, so draw it rather than
            # leaving the tick floating free of the bar it belongs to.
            ax.plot([xi, xi], [m, sv], ls=":", lw=0.8, color="black", zorder=5)
            ax.plot([xi - bar_w * 0.30, xi + bar_w * 0.30], [sv, sv],
                    color="black", lw=1.1, zorder=6, solid_capstyle="butt")
        for xi, hi, sv, tag in zip(xs, errs_hi, selfs, tags):
            if tag:
                y = hi if np.isnan(sv) else max(hi, sv)
                ax.text(xi, y + top * 0.03, tag, ha="center", va="bottom",
                        fontsize=style.ANNOT_FLOOR,
                        fontweight="bold" if tag == "*" else "normal")

    ax.set_ylim(0, top * 1.34)
    ax.set_xticks(x0)
    ax.set_xticklabels([f"{TIER_DESC[t]}\nplacements" for t in TIER_ORDER],
                       fontsize=style.BODY)
    ax.set_ylabel("interference degradation index\n(full-window re-score)",
                  fontsize=style.BODY)
    ax.grid(axis="y", ls=":", alpha=0.3)
    # One extra handle explaining the tick and the diagonal tag, so the caption
    # does not have to carry them.
    from matplotlib.lines import Line2D
    handles, labels = ax.get_legend_handles_labels()
    handles.append(Line2D([0], [0], color="black", lw=1.1))
    labels.append("self score (own classifier); hatched = self-check")
    style.compact_legend(ax, handles, labels, ncol=2)

    spec = style.FigSpec(width, height, "fig:oracle_matrix")
    style.save(fig, out / "fig_oracle_matrix.pdf", spec)
    plt.close(fig)
    print(f"wrote {out / 'fig_oracle_matrix.pdf'}")


DENSITY_TIMEOUT_S = 400  # per-rep timeout of the density sweep (DENSITY-SWEEP.md)


def fig_density(data_root: Path, out: Path, density_tsv: Path | None = None) -> None:
    if density_tsv is not None:
        # S16/S5 two-line version: interference-only and total index, n=10
        # per density, early-exit sweep (s5-density.tsv). No timeouts in this
        # campaign, so the "timed out" marker logic does not apply.
        fig_density_s5(density_tsv, out)
        return
    by_ratio = defaultdict(list)
    for r in csv.DictReader((data_root / "density-sweep" / "density-sweep-combined.tsv").open(),
                            delimiter="\t"):
        by_ratio[float(r["ratio"])].append((float(r["idi_avg"]), float(r["elapsed"])))

    xs, ms, los, his, conv = [], [], [], [], []
    for i, ratio in enumerate(sorted(by_ratio)):
        vals = [v for v, _ in by_ratio[ratio]]
        m, lo, hi = p2_ci.rep_ci(vals, seed_offset=700 + i)
        xs.append(ratio); ms.append(m); los.append(lo); his.append(hi)
        conv.append(not all(e >= DENSITY_TIMEOUT_S for _, e in by_ratio[ratio]))

    width, height = style.TEXT_WIDTH * 0.62, 2.2
    fig, ax = plt.subplots(figsize=(width, height), layout="constrained")
    color = "#27ae60"  # tier B, matches plot-iada-sim.py
    ax.fill_between(xs, los, his, color=color, alpha=0.15, linewidth=0)
    ax.plot(xs, ms, color=color, lw=1.2, marker="o", markersize=3.5,
            markeredgecolor="white", markeredgewidth=0.5, label="converged search")
    bad = [(x, m) for x, m, c in zip(xs, ms, conv) if not c]
    if bad:
        ax.plot(*zip(*bad), ls="none", marker="x", markersize=6, color=style.VERMILLION,
                label="timed out (initial placement only)", zorder=5)
    top = max(his)
    for x, m in zip(xs, ms):
        ax.text(x, m + top * 0.04, f"{m:.0f}", ha="center", va="bottom", fontsize=style.ANNOT)
    ax.set_ylim(0, top * 1.18)
    ax.set_xticks(xs)
    ax.set_xticklabels([f"{x:g}" for x in xs])
    ax.set_xlabel("applications per host")
    ax.set_ylabel("interference degradation index")
    style.compact_legend(ax, *ax.get_legend_handles_labels(), ncol=2)

    style.save(fig, out / "figA_density.pdf", style.FigSpec(width, height, "fig:a4"))
    plt.close(fig)
    print(f"wrote {out / 'figA_density.pdf'}")


def fig_density_s5(density_tsv: Path, out: Path) -> None:
    """S16/S5 (jsa-repo-fix-brief Step 6): density sweep with early exit.

    Two lines over the 7 densities (48/containerPes applications per host),
    n=10 reps each, 95% bootstrap band per line (same p2_ci.rep_ci convention
    as the rest of the paper): the interference-only component and the total
    index (interference + migration). Source: s5-density.tsv.
    """
    by_ratio_i = defaultdict(list)
    by_ratio_t = defaultdict(list)
    for r in csv.DictReader(density_tsv.open(), delimiter="\t"):
        d = float(r["apps_per_host"])
        by_ratio_i[d].append(float(r["interference_avg"]))
        by_ratio_t[d].append(float(r["idi_avg"]))

    xs = sorted(by_ratio_t)
    series = []
    for i, (by_ratio, color, label, marker) in enumerate([
            (by_ratio_t, "#27ae60", "total index", "o"),
            (by_ratio_i, style.BLUE, "interference only", "s")]):
        ms, los, his = [], [], []
        for j, d in enumerate(xs):
            m, lo, hi = p2_ci.rep_ci(by_ratio[d], seed_offset=700 + 10 * i + j)
            ms.append(m); los.append(lo); his.append(hi)
        series.append((ms, los, his, color, label, marker))

    width, height = style.TEXT_WIDTH * 0.62, 2.2
    fig, ax = plt.subplots(figsize=(width, height), layout="constrained")
    for ms, los, his, color, label, marker in series:
        ax.fill_between(xs, los, his, color=color, alpha=0.15, linewidth=0)
        ax.plot(xs, ms, color=color, lw=1.2, marker=marker, markersize=3.5,
                markeredgecolor="white", markeredgewidth=0.5, label=label)
    top = max(hi for _m, _l, his, _c, _lb, _mk in series for hi in his)
    for x, m in zip(xs, series[0][0]):
        ax.text(x, m + top * 0.04, f"{m:.0f}", ha="center", va="bottom",
                fontsize=style.ANNOT)
    ax.set_ylim(0, top * 1.18)
    ax.set_xticks(xs)
    ax.set_xticklabels([f"{x:g}" for x in xs])
    ax.set_xlabel("applications per host")
    ax.set_ylabel("interference degradation index")
    ax.grid(axis="y", ls=":", alpha=0.3)
    style.compact_legend(ax, *ax.get_legend_handles_labels(), ncol=2)

    style.save(fig, out / "figA_density.pdf", style.FigSpec(width, height, "fig:a4"))
    plt.close(fig)
    print(f"wrote {out / 'figA_density.pdf'}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-root", type=Path,
                    default=Path("bench/iada/results/sim-experiments-20260916"))
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--s15-root", type=Path, default=None,
                    help="S15 rerun results dir; enables fig_oracle_matrix. "
                         "fig_oracle.pdf is left unchanged either way.")
    ap.add_argument("--density-tsv", type=Path, default=None,
                    help="S16/S5 s5-density.tsv; when set, figA_density.pdf "
                         "uses it and draws interference-only + total lines.")
    args = ap.parse_args()
    style.apply()
    args.out.mkdir(parents=True, exist_ok=True)
    fig_baselines(args.data_root, args.out)
    fig_oracle(args.data_root, args.out)
    fig_density(args.data_root, args.out, density_tsv=args.density_tsv)
    if args.s15_root is not None:
        fig_oracle_matrix(args.data_root, args.s15_root, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

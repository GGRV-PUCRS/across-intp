#!/usr/bin/env python3
"""analyze-s15.py -- S15 rerun analysis: phase tables + summary-s15.tsv.

Reads only TSVs from the new results directory (and, for the B reference, the
banked gate-B-psp-n20.tsv of sim-experiments-20260916), applies the house
statistics conventions via s15_stats, and writes:

  <new>/summary-s15.tsv     one row per arm x tier (invariant: every number in
                            TEX-PATCH-S15.md is traceable to a row here)
  stdout                    the per-phase tables reproduced in DECISIONS S15

    python3 bench/iada/scripts/analyze-s15.py --new DIR --banked DIR
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from s15_stats import (  # noqa: E402
    read_tsv, col, mean_sd, unpaired_diff_ci, paired_diff_ci, sig, fmt,
)

TIERS = ["T1", "A", "B"]
SUMMARY_COLS = [
    "arm", "tier", "n", "mean", "sd", "ref_mean", "delta", "ci_lo", "ci_hi",
    "welch_p", "pct_of_default",
    "oracle_ref", "self_mean", "oracle_mean", "paired_delta",
    "paired_ci_lo", "paired_ci_hi",
]


def load(d: Path, name: str):
    p = d / name
    return read_tsv(p) if p.exists() else None


def row(**kw):
    return {c: kw.get(c, "") for c in SUMMARY_COLS}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--new", type=Path, required=True)
    ap.add_argument("--banked", type=Path,
                    default=Path("bench/iada/results/sim-experiments-20260916"))
    args = ap.parse_args()
    new, banked = args.new, args.banked
    out_rows = []
    seed = 0

    def nxt():
        nonlocal seed
        seed += 1
        return seed

    # ---------------- Phase 1: preflight gate --------------------------------
    print("=" * 78)
    print("PHASE 1 -- preflight gate (tier B, all defaults)")
    print("=" * 78)
    gate_new = load(new, "gate-B-psp-rerun-n10.tsv")
    gate_bank = load(banked, "gate-B-psp-n20.tsv")
    b_new, n_new, f_new = col(gate_new, "idi_avg", tier="B")
    b_bank, n_bank, f_bank = col(gate_bank, "idi_avg", tier="B")
    m_new, sd_new = mean_sd(b_new)
    m_bank, sd_bank = mean_sd(b_bank)
    d, lo, hi, p = unpaired_diff_ci(b_bank, b_new, seed_offset=nxt())
    passed = lo <= 0 <= hi
    print(f"  banked gate-B-psp-n20 : {fmt(m_bank)} +/- {fmt(sd_bank)}  (n={len(b_bank)}, failed={f_bank})")
    print(f"  rerun  gate-B-psp-n10 : {fmt(m_new)} +/- {fmt(sd_new)}  (n={len(b_new)}, failed={f_new})")
    print(f"  delta (rerun - banked): {fmt(d)} [{fmt(lo)}, {fmt(hi)}] Welch p={p:.3g}  -> "
          f"{'PASS (CI covers zero)' if passed else 'FAIL (CI excludes zero)'}")
    out_rows.append(row(arm="gate-B-psp-rerun-n10", tier="B", n=len(b_new),
                        mean=fmt(m_new, 2), sd=fmt(sd_new, 2), ref_mean=fmt(m_bank, 2),
                        delta=fmt(d, 2), ci_lo=fmt(lo, 2), ci_hi=fmt(hi, 2),
                        welch_p=f"{p:.4g}", pct_of_default=fmt(100.0 * m_new / m_bank, 2)))
    if not passed:
        print("\n!! GATE FAILED -- stopping per brief section 2. No arm below is interpretable.")
        return 1

    # Pooled B reference (brief section 2: banked n=20 pooled with the preflight,
    # given they agree -- which the gate above just established).
    b_ref = np.concatenate([b_bank, b_new])
    m_ref, sd_ref = mean_sd(b_ref)
    print(f"\n  POOLED B reference used for every B delta below: {fmt(m_ref)} +/- {fmt(sd_ref)} (n={len(b_ref)})")

    # T1/A reference: this toolchain's own rerun, with the banked one reported too.
    ta_new = load(new, "gate-T1-A-rerun-n10.tsv")
    ta_bank = load(banked, "gate-T1-A-n10.tsv")
    ref = {"B": b_ref}
    print("\n  T1/A gate, this toolchain vs banked:")
    for t in ("T1", "A"):
        v_new, _, f_t = col(ta_new, "idi_avg", tier=t) if ta_new else (np.array([]), 0, 0)
        v_bank, _, _ = col(ta_bank, "idi_avg", tier=t) if ta_bank else (np.array([]), 0, 0)
        ref[t] = v_new if v_new.size else v_bank
        mn, sdn = mean_sd(v_new)
        mb, sdb = mean_sd(v_bank)
        dd, dlo, dhi, dp = unpaired_diff_ci(v_bank, v_new, seed_offset=nxt())
        print(f"    {t:<2}: rerun {fmt(mn)} +/- {fmt(sdn)} (n={len(v_new)}, failed={f_t}) | "
              f"banked {fmt(mb)} +/- {fmt(sdb)} | delta {fmt(dd)} [{fmt(dlo)}, {fmt(dhi)}] {sig(dlo, dhi)}")
        out_rows.append(row(arm="gate-T1-A-rerun-n10", tier=t, n=len(v_new),
                            mean=fmt(mn, 2), sd=fmt(sdn, 2), ref_mean=fmt(mb, 2),
                            delta=fmt(dd, 2), ci_lo=fmt(dlo, 2), ci_hi=fmt(dhi, 2),
                            welch_p=f"{dp:.4g}"))

    ref_mean = {t: float(np.mean(v)) for t, v in ref.items() if len(v)}

    # ---------------- Phases 2/3/5: single-flag arms -------------------------
    arms = [
        ("PHASE 2 -- E4 ramp shape (tier B, psp-keyed)", [
            ("e4-ramp-step-B-psp-n10", ["B"]),
            ("e4-ramp-measured-B-psp-n10", ["B"]),
            ("e4-ramp-convex-B-psp-n10", ["B"]),
        ]),
        ("PHASE 3 -- E5 published degradation table", [
            ("e5-degtable-paper-B-psp-n10", ["B"]),
            ("e5-degtable-paper-T1A-n10", ["T1", "A"]),
        ]),
        ("PHASE 5 -- E1 startup delay", [
            ("e1-startup-0-B-psp-n10", ["B"]),
            ("e1-startup-10-B-psp-n10", ["B"]),
            ("e1-startup-50-B-psp-n10", ["B"]),
            ("e1-startup-0-T1A-n10", ["T1", "A"]),
            ("e1-startup-10-T1A-n10", ["T1", "A"]),
            ("e1-startup-50-T1A-n10", ["T1", "A"]),
        ]),
    ]
    for title, specs in arms:
        printed = False
        for name, tiers in specs:
            rows = load(new, f"{name}.tsv")
            if rows is None:
                continue
            if not printed:
                print("\n" + "=" * 78); print(title); print("=" * 78)
                print(f"  {'arm':<32} {'tier':<4} {'n':>3} {'mean':>9} {'sd':>8} "
                      f"{'delta':>9} {'95% CI':>22} {'p':>9} {'%def':>7}")
                printed = True
            for t in tiers:
                v, ntot, nfail = col(rows, "idi_avg", tier=t)
                if not len(v):
                    continue
                m, sd = mean_sd(v)
                d, lo, hi, p = unpaired_diff_ci(ref[t], v, seed_offset=nxt())
                pct = 100.0 * m / ref_mean[t]
                print(f"  {name:<32} {t:<4} {len(v):>3} {fmt(m):>9} {fmt(sd):>8} "
                      f"{fmt(d):>9} {'[' + fmt(lo) + ', ' + fmt(hi) + ']':>22} "
                      f"{p:>9.3g} {fmt(pct):>6}% {sig(lo, hi)}"
                      + (f"   ({nfail} FAILED reps)" if nfail else ""))
                out_rows.append(row(arm=name, tier=t, n=len(v), mean=fmt(m, 2), sd=fmt(sd, 2),
                                    ref_mean=fmt(ref_mean[t], 2), delta=fmt(d, 2),
                                    ci_lo=fmt(lo, 2), ci_hi=fmt(hi, 2), welch_p=f"{p:.4g}",
                                    pct_of_default=fmt(pct, 2)))

    # ---------------- Phase 4: oracle matrix ---------------------------------
    oracle_files = {
        "B": (banked / "oracle-t1ab-n10.tsv", "B"),
        "T1": (new / "oracle-refT1-t1ab-n10.tsv", "T1"),
        "A": (new / "oracle-refA-t1ab-n10.tsv", "A"),
    }
    have = {k: v for k, v in oracle_files.items() if v[0].exists()}
    if have:
        print("\n" + "=" * 78)
        print("PHASE 4 -- oracle re-score matrix (placement tier x reference classifier)")
        print("=" * 78)
        oracle_by_ref = {}
        for refname, (path, _) in have.items():
            rows = read_tsv(path)
            print(f"\n  reference classifier = tier {refname}   ({path.name})")
            print(f"    {'placement':<10} {'n':>3} {'self mean':>11} {'sd':>8} "
                  f"{'oracle mean':>12} {'sd':>8} {'paired d':>10} {'95% CI':>22} {'p':>9}")
            per_tier = {}
            for t in TIERS:
                s, _, sf = col(rows, "self_idi", tier=t)
                o, _, of = col(rows, "oracle_idi", tier=t)
                if not len(s) or len(s) != len(o):
                    continue
                sm, ssd = mean_sd(s)
                om, osd = mean_sd(o)
                d, lo, hi, p, dsd = paired_diff_ci(s, o, seed_offset=nxt())
                exact = bool(np.allclose(s, o))
                tag = "  EXACT self-check" if exact else f"  {sig(lo, hi)}"
                print(f"    {t:<10} {len(s):>3} {fmt(sm):>11} {fmt(ssd):>8} "
                      f"{fmt(om):>12} {fmt(osd):>8} {fmt(d):>10} "
                      f"{'[' + fmt(lo) + ', ' + fmt(hi) + ']':>22} "
                      f"{('n/a' if np.isnan(p) else f'{p:.3g}'):>9}{tag}"
                      + (f"   ({sf + of} FAILED)" if (sf or of) else ""))
                per_tier[t] = o
                out_rows.append(row(arm=f"oracle-ref{refname}", tier=t, n=len(s),
                                    mean=fmt(om, 2), sd=fmt(osd, 2),
                                    oracle_ref=refname, self_mean=fmt(sm, 2),
                                    oracle_mean=fmt(om, 2), paired_delta=fmt(d, 2),
                                    paired_ci_lo=fmt(lo, 2), paired_ci_hi=fmt(hi, 2),
                                    welch_p=("" if np.isnan(p) else f"{p:.4g}")))
            oracle_by_ref[refname] = per_tier

        print("\n  Cross-tier placement comparisons under each reference "
              "(unpaired bootstrap of the difference, Welch p):")
        print(f"    {'reference':<10} {'comparison':<16} {'delta':>9} {'95% CI':>22} {'p':>9}")
        for refname in ("B", "T1", "A"):
            pt = oracle_by_ref.get(refname, {})
            for lhs, rhs, label in (("T1", "A", "A - T1"), ("T1", "B", "B - T1"), ("A", "B", "B - A")):
                if lhs not in pt or rhs not in pt:
                    continue
                d, lo, hi, p = unpaired_diff_ci(pt[lhs], pt[rhs], seed_offset=nxt())
                print(f"    {refname:<10} {label:<16} {fmt(d):>9} "
                      f"{'[' + fmt(lo) + ', ' + fmt(hi) + ']':>22} {p:>9.3g}  {sig(lo, hi)}")

    # ---------------- summary TSV --------------------------------------------
    out = new / "summary-s15.tsv"
    with out.open("w", encoding="utf-8") as fh:
        fh.write("\t".join(SUMMARY_COLS) + "\n")
        for r in out_rows:
            fh.write("\t".join(str(r[c]) for c in SUMMARY_COLS) + "\n")
    print(f"\n[wrote {out}]  ({len(out_rows)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

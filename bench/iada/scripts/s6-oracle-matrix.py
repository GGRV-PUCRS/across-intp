#!/usr/bin/env python3
"""s6-oracle-matrix.py -- S16/Step 7: oracle re-scoring matrix at n=20.

Reuses the S1 campaign's saved final placements (s1-placements/IASA/, n=20 per
tier) and re-scores EACH placement under all three reference classifiers, so
the three matrix columns share placements and the batching caveat of the n=10
pass disappears. This is the brief's PREFERRED design; it needs no simulator
run because:

  * the placement of every rep is already on disk (S1);
  * the reference classification is placement-independent -- oracleRescore
    classifies cloudlet k's trace from the REFERENCE's own tree with the
    REFERENCE's model (validated: s6-refclass.R reproduces the simulator's
    own CLS log lines exactly on two windows, 420/420);
  * the cost + aggregation mirror Solution.getTotalInterferenceCostOracle
    literally: per-cloudlet MLCResult.getCloudletCost() (degradation fork
    table, floor 1, regime term only for the 6-class B model), per host the
    product over co-resident cloudlets of cost * hostPe/clPe (48/12 in every
    S1 gate rep), single-occupancy hosts excluded and floored to 0, total
    scaled by (end-start)/ttime = 18/119 of the final IASA interval
    (start=101, end=119, ttime=119 -- identical for every IASA rep).

Statistics (house conventions, s15_stats.py / p2_ci.py):
  * self vs reference per cell: PERMUTATION test on the paired differences
    (sign flips, 10000, seed 20260607) + paired percentile bootstrap CI.
  * cross-tier under each reference: unpaired PERMUTATION test (label
    shuffle, 10000, seed 20260607) + unpaired bootstrap CI, Holm correction
    across all 9 comparisons. Significance labels follow the Holm p, never
    the CI.

Outputs under $OUT:
  s6-oracle-matrix.tsv   per-rep scores, wide (self + one column per ref)
  s6-oracle-scores.tsv   same data long, in the S15 oracle-*.tsv schema
                         (tier/env/rep/self_idi/oracle_idi/oracle_ref) so the
                         figure renderer consumes it unchanged
  s6-selfref.tsv         paired self-vs-reference stats per off-diagonal cell
  s6-cross-tier.tsv      the 9 cross-tier comparisons with Holm p values
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import numpy as np

AX = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(AX / "bench/iada/scripts"))
import s15_stats  # noqa: E402

TIERS = ["T1", "A", "B"]
PERMS = 10000
SEED = 20260607
# Final IASA solution's (start, end, ttime) = (101, 119, 119) for every rep;
# the scale factor is identical across reps and cancels in every paired diff.
TIME_SCALE = (119 - 101) / 119
PE_RATIO = 48.0 / 12.0  # hostPe/clPe, constant across all 60 S1 gate reps


def load_ref_costs(path):
    cost = {}
    with open(path) as f:
        for r in csv.DictReader(f, delimiter="\t"):
            cost.setdefault(r["ref"], {})[int(r["cloudlet"])] = float(r["cost"])
    return cost


def oracle_total(placement, costs):
    """Literal port of Solution.getTotalInterferenceCostOracle."""
    by_host = {}
    for cloudlet, host in placement:
        by_host.setdefault(host, []).append(cloudlet)
    total = 0.0
    for host, cls in by_host.items():
        if len(cls) == 1:  # runninginOnlyOneHost -> hostCost stays 1 -> 0
            continue
        host_cost = 1.0
        for cl in cls:
            host_cost *= costs[cl] / (1.0 / PE_RATIO)  # cost * hostPe/clPe
        total += host_cost
    return total * TIME_SCALE


def perm_paired_p(diff, seed_offset, n=PERMS):
    """Permutation p for mean(d) == 0 via random sign flips of paired diffs."""
    diff = np.asarray(diff, dtype=float)
    if np.allclose(diff, 0.0):
        return float("nan")
    rng = np.random.default_rng(SEED + seed_offset)
    signs = rng.choice([-1.0, 1.0], size=(n, diff.size))
    nulls = np.abs((signs * diff).mean(1))
    return float((np.sum(nulls >= abs(diff.mean())) + 1) / (n + 1))


def perm_unpaired_p(a, b, seed_offset, n=PERMS):
    """Permutation p for mean(a) == mean(b) via label shuffling."""
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    rng = np.random.default_rng(SEED + seed_offset)
    pooled = np.concatenate([a, b])
    obs = abs(a.mean() - b.mean())
    count = 0
    for i in range(n):
        idx = rng.permutation(pooled.size)
        count += abs(pooled[idx[:a.size]].mean() - pooled[idx[a.size:]].mean()) >= obs
    return float((count + 1) / (n + 1))


def holm(pvals):
    """Holm-adjusted p values; NaN entries (diagonal/degenerate) are skipped."""
    keys = [k for k, p in pvals.items() if not (isinstance(p, float) and np.isnan(p))]
    m = len(keys)
    order = sorted(keys, key=lambda k: pvals[k])
    adj = {}
    running = 0.0
    for rank, k in enumerate(order):
        val = min(1.0, (m - rank) * pvals[k])
        running = max(running, val)
        adj[k] = running
    for k in pvals:
        if k not in adj:
            adj[k] = float("nan")
    return adj


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-root", required=True, type=Path)
    ap.add_argument("--refcosts", required=True, type=Path)
    ap.add_argument("--placements", required=True, type=Path,
                    help="dir holding <tier>-rep<k>.tsv with cloudletId, hostId")
    ap.add_argument("--reps", type=int, default=20)
    args = ap.parse_args()

    costs = load_ref_costs(args.refcosts)

    # ---- per-rep scores --------------------------------------------------
    scores = {}  # (tier, rep) -> {ref: score}
    for tier in TIERS:
        for rep in range(1, args.reps + 1):
            pf = args.placements / f"{tier}-rep{rep}.tsv"
            with open(pf) as f:
                rows = list(csv.DictReader(f, delimiter="\t"))
            placement = [(int(r["cloudletId"]), int(r["hostId"])) for r in rows]
            assert len(placement) == 28, f"{pf}: {len(placement)} cloudlets"
            scores[(tier, rep)] = {ref: oracle_total(placement, costs[ref])
                                   for ref in TIERS}

    out = args.out_root
    with open(out / "s6-oracle-matrix.tsv", "w", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["tier", "rep", "self", "ref_T1", "ref_A", "ref_B"])
        for tier in TIERS:
            for rep in range(1, args.reps + 1):
                s = scores[(tier, rep)]
                w.writerow([tier, rep, f"{s[tier]:.4f}",
                            f"{s['T1']:.4f}", f"{s['A']:.4f}", f"{s['B']:.4f}"])

    # long form, S15 oracle TSV schema (figure renderer input)
    with open(out / "s6-oracle-scores.tsv", "w", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["tier", "env", "rep", "self_idi", "oracle_idi", "oracle_ref"])
        for tier in TIERS:
            for rep in range(1, args.reps + 1):
                for ref in TIERS:
                    w.writerow([tier, "vm", rep,
                                f"{scores[(tier, rep)][tier]:.4f}",
                                f"{scores[(tier, rep)][ref]:.4f}", ref])

    # ---- self vs reference (paired on reps) ------------------------------
    selfref_rows = []
    for tier in TIERS:
        for ref in TIERS:
            if ref == tier:
                continue  # diagonal: exact 0 by construction
            off = 1000 + 10 * TIERS.index(tier) + TIERS.index(ref)
            s = np.array([scores[(tier, r)][tier] for r in range(1, args.reps + 1)])
            o = np.array([scores[(tier, r)][ref] for r in range(1, args.reps + 1)])
            d = o - s
            delta, lo, hi, _, sd_d = s15_stats.paired_diff_ci(s, o, seed_offset=off)
            p = perm_paired_p(d, seed_offset=off)
            selfref_rows.append((tier, ref, delta, lo, hi, sd_d, p))
    with open(out / "s6-selfref.tsv", "w", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["tier", "reference", "delta", "ci_lo", "ci_hi", "sd_diff",
                    "perm_p", "n"])
        for tier, ref, delta, lo, hi, sd_d, p in selfref_rows:
            w.writerow([tier, ref, f"{delta:.4f}", f"{lo:.4f}", f"{hi:.4f}",
                        f"{sd_d:.4f}", f"{p:.6f}", args.reps])

    # ---- cross-tier under each reference (Holm across all 9) -------------
    raw_p = {}
    cells = {}
    for ref in TIERS:
        for a, b in (("T1", "A"), ("T1", "B"), ("A", "B")):
            va = np.array([scores[(a, r)][ref] for r in range(1, args.reps + 1)])
            vb = np.array([scores[(b, r)][ref] for r in range(1, args.reps + 1)])
            off = 2000 + 10 * TIERS.index(ref) + 3 * TIERS.index(a) + TIERS.index(b)
            delta, lo, hi, welch = s15_stats.unpaired_diff_ci(va, vb, seed_offset=off)
            p = perm_unpaired_p(vb, va, seed_offset=off)  # delta = mean(B) - mean(A)
            key = (ref, a, b)
            raw_p[key] = p
            cells[key] = (va.mean(), vb.mean(), delta, lo, hi, welch, p)
    adj = holm(raw_p)

    with open(out / "s6-cross-tier.tsv", "w", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["reference", "base", "arm", "mean_base", "mean_arm", "delta",
                    "ci_lo", "ci_hi", "welch_p", "perm_p", "holm_p", "significant", "n"])
        for ref in TIERS:
            for a, b in (("T1", "A"), ("T1", "B"), ("A", "B")):
                ma, mb, delta, lo, hi, welch, p = cells[(ref, a, b)]
                hp = adj[(ref, a, b)]
                w.writerow([ref, a, b, f"{ma:.4f}", f"{mb:.4f}", f"{delta:.4f}",
                            f"{lo:.4f}", f"{hi:.4f}", f"{welch:.6f}", f"{p:.6f}",
                            f"{hp:.6f}",
                            "yes" if (not np.isnan(hp) and hp < 0.05) else "no",
                            args.reps])

    # ---- console summary --------------------------------------------------
    print("cell means (own-ref / T1 / A / B):")
    for tier in TIERS:
        ms = [np.mean([scores[(tier, r)][tier] for r in range(1, args.reps + 1)])] + \
             [np.mean([scores[(tier, r)][ref] for r in range(1, args.reps + 1)])
              for ref in TIERS]
        sds = [np.std([scores[(tier, r)][tier] for r in range(1, args.reps + 1)], ddof=1)] + \
              [np.std([scores[(tier, r)][ref] for r in range(1, args.reps + 1)], ddof=1)
               for ref in TIERS]
        print(f"  {tier} placements: self {ms[0]:.1f}±{sds[0]:.1f} | "
              f"T1 {ms[1]:.1f}±{sds[1]:.1f} | A {ms[2]:.1f}±{sds[2]:.1f} | B {ms[3]:.1f}±{sds[3]:.1f}")
    print("self vs reference (paired):")
    for tier, ref, delta, lo, hi, sd_d, p in selfref_rows:
        print(f"  {tier} under {ref}: {delta:+.1f} [{lo:.1f},{hi:.1f}] perm p={p:.5f}")
    print("cross-tier (delta = arm - base):")
    for ref in TIERS:
        for a, b in (("T1", "A"), ("T1", "B"), ("A", "B")):
            ma, mb, delta, lo, hi, welch, p = cells[(ref, a, b)]
            print(f"  ref {ref}: {b}-{a} {delta:+.1f} [{lo:.1f},{hi:.1f}] "
                  f"perm p={p:.5f} holm={adj[(ref, a, b)]:.5f}")
    print(f"wrote {out}/s6-oracle-matrix.tsv, s6-oracle-scores.tsv, "
          f"s6-selfref.tsv, s6-cross-tier.tsv")


if __name__ == "__main__":
    main()

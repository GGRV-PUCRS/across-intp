#!/usr/bin/env python3
"""s1-pairwise-stats.py -- S16/S1, pairwise permutation tests between tiers.

Per the brief: 10000 permutations, fixed seed 20260607, Holm correction
across the 3 pairwise tier comparisons (T1-A, T1-B, A-B), per yardstick.
Reports mean, SD, difference, bootstrap 95% CI, and the Holm-adjusted p.
"""
import argparse
import random
import statistics as st


def read_scores(path, approach, tiers, yardstick, window):
    by_tier = {t: [] for t in tiers}
    with open(path) as f:
        header = next(f).rstrip("\n").split("\t")
        idx = {name: i for i, name in enumerate(header)}
        for line in f:
            p = line.rstrip("\n").split("\t")
            if p[idx["approach"]] != approach:
                continue
            if p[idx["yardstick"]] != yardstick or p[idx["window"]] != window:
                continue
            tier = p[idx["tier"]]
            if tier in by_tier:
                by_tier[tier].append(float(p[idx["score"]]))
    return by_tier


def permutation_test(a, b, n_perm, rng):
    """Two-sided permutation test on the difference of means."""
    obs_diff = st.mean(a) - st.mean(b)
    pooled = a + b
    na = len(a)
    count = 0
    for _ in range(n_perm):
        rng.shuffle(pooled)
        pa = pooled[:na]
        pb = pooled[na:]
        diff = st.mean(pa) - st.mean(pb)
        if abs(diff) >= abs(obs_diff):
            count += 1
        pooled = list(pooled)  # rng.shuffle is in place; keep pooled a fresh list each time
    p = (count + 1) / (n_perm + 1)  # add-one smoothing, standard for permutation tests
    return obs_diff, p


def bootstrap_ci(a, b, n_boot, rng, alpha=0.05):
    diffs = []
    for _ in range(n_boot):
        ra = [rng.choice(a) for _ in a]
        rb = [rng.choice(b) for _ in b]
        diffs.append(st.mean(ra) - st.mean(rb))
    diffs.sort()
    lo_idx = int((alpha / 2) * n_boot)
    hi_idx = int((1 - alpha / 2) * n_boot) - 1
    return diffs[lo_idx], diffs[hi_idx]


def holm_correct(pvals):
    """pvals: list of (label, p). Returns dict label -> adjusted p."""
    order = sorted(range(len(pvals)), key=lambda i: pvals[i][1])
    m = len(pvals)
    adjusted = [None] * m
    running_max = 0.0
    for rank, idx in enumerate(order):
        label, p = pvals[idx]
        adj = min(1.0, (m - rank) * p)
        running_max = max(running_max, adj)
        adjusted[idx] = running_max
    return {pvals[i][0]: adjusted[i] for i in range(m)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--truthscore", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--approach", default="IASA")
    ap.add_argument("--tiers", nargs="+", default=["T1", "A", "B"])
    ap.add_argument("--yardsticks", nargs="+", default=["Y5", "Y6"])
    ap.add_argument("--window", default="full")
    ap.add_argument("--n-perm", type=int, default=10000)
    ap.add_argument("--n-boot", type=int, default=10000)
    ap.add_argument("--seed", type=int, default=20260607)
    args = ap.parse_args()

    pairs = [("T1", "A"), ("T1", "B"), ("A", "B")]

    lines = ["yardstick\ttier1\ttier2\tmean1\tsd1\tmean2\tsd2\tdiff\tci_lo\tci_hi\tp_raw\tp_holm"]
    for yardstick in args.yardsticks:
        by_tier = read_scores(args.truthscore, args.approach, args.tiers, yardstick, args.window)
        for t in args.tiers:
            print(f"{yardstick} {t}: n={len(by_tier[t])} mean={st.mean(by_tier[t]):.1f} "
                  f"sd={st.stdev(by_tier[t]) if len(by_tier[t]) > 1 else 0:.1f}")

        raw_results = {}
        for (t1, t2) in pairs:
            rng_p = random.Random(args.seed)
            diff, p = permutation_test(list(by_tier[t1]), list(by_tier[t2]), args.n_perm, rng_p)
            rng_b = random.Random(args.seed + 1)
            ci_lo, ci_hi = bootstrap_ci(by_tier[t1], by_tier[t2], args.n_boot, rng_b)
            raw_results[(t1, t2)] = (diff, p, ci_lo, ci_hi)

        holm_in = [(f"{t1}-{t2}", raw_results[(t1, t2)][1]) for (t1, t2) in pairs]
        holm_out = holm_correct(holm_in)

        for (t1, t2) in pairs:
            diff, p, ci_lo, ci_hi = raw_results[(t1, t2)]
            p_holm = holm_out[f"{t1}-{t2}"]
            m1, s1 = st.mean(by_tier[t1]), st.stdev(by_tier[t1])
            m2, s2 = st.mean(by_tier[t2]), st.stdev(by_tier[t2])
            lines.append(f"{yardstick}\t{t1}\t{t2}\t{m1:.4f}\t{s1:.4f}\t{m2:.4f}\t{s2:.4f}\t"
                         f"{diff:.4f}\t{ci_lo:.4f}\t{ci_hi:.4f}\t{p:.5f}\t{p_holm:.5f}")
            sig = "SIGNIFICANT" if p_holm < 0.05 else "not significant"
            print(f"  {yardstick} {t1} vs {t2}: diff={diff:.1f} CI=[{ci_lo:.1f},{ci_hi:.1f}] "
                  f"p_raw={p:.5f} p_holm={p_holm:.5f} ({sig})")

    with open(args.out, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()

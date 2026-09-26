#!/usr/bin/env python3
"""decompose-idi.py -- S16/S2 (jsa-repo-fix-brief), index decomposition and closed form.

Generalizes validate_jsa.py's c16_idi_closed_form() to all repetitions (that
function only reads logs[0] for the cost table and geo-mean, and only prints
means, no CIs). Reuses S3's cloudsim.log files (same n=10/tier campaign,
-Diada.logClasses=on has no effect on this parse), no new simulation.

Per rep, extracts:
  - the FIRST "Cloudlet Host  Hpe  Cpe CloudletCost" table (28 rows, one per
    cloudlet, from BEFORE any SA swap -- this is fillInitialSolution's output,
    bounded by the first "=====" divider after it, exactly like
    validate_jsa.py's c16 split)
  - the "Algorithm: SAO" block: six per-interval total costs, bounded by the
    next "Migrations:" marker

Per tier, computes:
  - geometric mean cloudlet cost (from rep1's table -- deterministic across
    reps, like S3's per-cloudlet classification, since it depends only on
    each cloudlet's own trace/classifier output, not the SA search path;
    verified by comparing rep1 vs rep2's table below before trusting this)
  - closed-form first interval: sum over hosts of the product, over that
    host's cloudlets in the INITIAL table, of (cost * Hpe / Cpe), divided by 6
  - mean/SD of the ACTUAL first-interval and final-interval SAO costs across
    all n reps
  - predicted T1->A ratio (gm_A / gm_T1) ** 4
  - final-interval gap: T1-A and T1-B (mean final interval, absolute and %)
"""
import argparse
import glob
import math
import os
import re
import statistics as st


def parse_first_cost_table(log_text):
    """Return list of (cloudlet, host, hpe, cpe, cost) from the FIRST table."""
    parts = log_text.split("Cloudlet Host  Hpe  Cpe CloudletCost")
    if len(parts) < 2:
        return []
    tab = parts[1].split("=====")[0]
    rows = []
    for line in tab.strip().splitlines():
        f = line.split()
        if len(f) != 5:
            continue
        try:
            cloudlet, host, hpe, cpe, cost = (float(x) for x in f)
        except ValueError:
            continue
        rows.append((cloudlet, host, hpe, cpe, cost))
    return rows


def parse_sao_intervals(log_text):
    """Return list of the 6 per-interval SAO costs (floats)."""
    parts = log_text.split("Algorithm: SAO")
    if len(parts) < 2:
        return []
    blk = parts[1].split("Migrations:")[0]
    return [float(x) for x in re.findall(r"^\s*([\d.]+)\s*$", blk, re.M)]


def closed_form_first_interval(rows):
    by_host = {}
    for cloudlet, host, hpe, cpe, cost in rows:
        by_host.setdefault(host, []).append(cost * hpe / cpe)
    total = 0.0
    for host, vals in by_host.items():
        prod = 1.0
        for v in vals:
            prod *= v
        total += prod
    return total / 6.0


def geo_mean(costs):
    return math.exp(st.mean(math.log(c) for c in costs if c > 0))


def mean_ci95(vals):
    if len(vals) < 2:
        return (vals[0] if vals else float("nan")), 0.0, (0.0, 0.0)
    m = st.mean(vals)
    sd = st.stdev(vals)
    se = sd / math.sqrt(len(vals))
    lo, hi = m - 1.96 * se, m + 1.96 * se
    return m, sd, (lo, hi)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work-root", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--tiers", nargs="+", default=["T1", "A", "B"])
    ap.add_argument("--reps", type=int, default=10)
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    decomp_path = os.path.join(args.out, "s2-decomp.tsv")
    summary_path = os.path.join(args.out, "s2-summary.tsv")

    per_tier = {}
    with open(decomp_path, "w") as df:
        df.write("tier\trep\tfirst_interval_actual\tlast_interval_actual\n")
        for tier in args.tiers:
            logs = sorted(glob.glob(os.path.join(
                args.work_root, f"s3-gate-{tier}", tier, "v3.3", "vm-guest", "rep*", "cloudsim.log")))
            if not logs:
                print(f"WARN: no logs for {tier}")
                continue

            rep1_rows = parse_first_cost_table(open(logs[0], errors="ignore").read())
            rep2_rows = parse_first_cost_table(open(logs[1], errors="ignore").read()) if len(logs) > 1 else []
            same_across_reps = (rep1_rows == rep2_rows) if rep2_rows else None

            costs = [c for (_, _, _, _, c) in rep1_rows]
            gm = geo_mean(costs)
            closed_first = closed_form_first_interval(rep1_rows)

            firsts, lasts = [], []
            for log_path in logs:
                iv = parse_sao_intervals(open(log_path, errors="ignore").read())
                if len(iv) != 6:
                    print(f"WARN: {log_path} has {len(iv)} SAO intervals, expected 6")
                    continue
                firsts.append(iv[0])
                lasts.append(iv[-1])
                rep_n = os.path.basename(os.path.dirname(log_path))
                df.write(f"{tier}\t{rep_n}\t{iv[0]:.4f}\t{iv[-1]:.4f}\n")

            first_m, first_sd, first_ci = mean_ci95(firsts)
            last_m, last_sd, last_ci = mean_ci95(lasts)
            closed_form_err_pct = abs(closed_first - first_m) / first_m * 100 if first_m else float("nan")

            per_tier[tier] = dict(
                gm=gm, closed_first=closed_first, first_m=first_m, first_sd=first_sd, first_ci=first_ci,
                last_m=last_m, last_sd=last_sd, last_ci=last_ci, closed_form_err_pct=closed_form_err_pct,
                same_across_reps=same_across_reps, n=len(firsts),
            )
            print(f"{tier}: gm_cost={gm:.3f} closed_first={closed_first:.1f} "
                  f"actual_first_mean={first_m:.1f} (err {closed_form_err_pct:.1f}%) "
                  f"actual_last_mean={last_m:.1f} n={len(firsts)} "
                  f"table_stable_across_reps={same_across_reps}")

    with open(summary_path, "w") as sf:
        sf.write("tier\tgeomean_cost\tclosed_form_first\tactual_first_mean\tactual_first_sd\t"
                  "actual_first_ci_lo\tactual_first_ci_hi\tclosed_form_err_pct\t"
                  "actual_last_mean\tactual_last_sd\tactual_last_ci_lo\tactual_last_ci_hi\tn\n")
        for tier, d in per_tier.items():
            sf.write(f"{tier}\t{d['gm']:.4f}\t{d['closed_first']:.4f}\t{d['first_m']:.4f}\t{d['first_sd']:.4f}\t"
                      f"{d['first_ci'][0]:.4f}\t{d['first_ci'][1]:.4f}\t{d['closed_form_err_pct']:.2f}\t"
                      f"{d['last_m']:.4f}\t{d['last_sd']:.4f}\t{d['last_ci'][0]:.4f}\t{d['last_ci'][1]:.4f}\t{d['n']}\n")

        if "T1" in per_tier and "A" in per_tier:
            ratio = (per_tier["A"]["gm"] / per_tier["T1"]["gm"]) ** 4
            sf.write(f"\npredicted_T1_to_A_ratio_(gmA/gmT1)^4\t{ratio:.4f}\n")
        for other in ("A", "B"):
            if "T1" in per_tier and other in per_tier:
                t1_last = per_tier["T1"]["last_m"]
                o_last = per_tier[other]["last_m"]
                gap_abs = t1_last - o_last
                gap_pct = gap_abs / t1_last * 100 if t1_last else float("nan")
                sf.write(f"final_interval_gap_T1_minus_{other}\t{gap_abs:.4f}\t{gap_pct:.2f}%\n")

    print(f"wrote {decomp_path}\nwrote {summary_path}")


if __name__ == "__main__":
    main()

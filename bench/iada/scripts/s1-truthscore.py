#!/usr/bin/env python3
"""s1-truthscore.py -- S16/S1 (jsa-repo-fix-brief), known-class yardstick.

Scores each rep's FINAL placement (the last "Cloudlet Host Hpe Cpe
CloudletCost" table printed in cloudsim.log -- .print() is called once per
analysis interval, so the last occurrence is the converged, final-interval
placement) against the true workload class and the tertile-based degradation
level defined in CONFORMANCE.md Sec 7 / s1-level-rule.py, in place of the
classifier's predicted class+level. No new Java code or R/JRI interaction is
needed: the final placement is already printed by existing code, and the
truth-labeled cost model is reimplemented here in Python (deliberately, so it
can be unit-tested against known cases before trusting it -- unlike the
JRI/R path, which is hard to verify independently).

Cost model mirrors MLCResult.getCloudletCost() / Degradation.java exactly:
cost = getCpu(level_cpu) * getMem(level_mem) * getDisk(level_disk) *
       getCache(level_cache) * getNet(level_net) [* getRegime(level_regime)
       if Y6 and cloudlet's true class is regime], floored at 1. Every class
other than the cloudlet's true one stays "abs" (multiplier 1).

Placement aggregation mirrors decompose-idi.py's validated closed form
(matches the brief's own C16 formula, confirmed within 4.4% of the actual
first-interval cost for every tier in the S2 pass): score = sum over hosts
of the product, over that host's cloudlets, of (cost * Hpe / Cpe).
"""
import argparse
import glob
import math
import os
import re
import statistics as st

# Degradation.java's fork table (PAPER_TABLE=off, the default; matches every
# other S16 computation this session, which never set -Diada.degTable=paper).
DEG = {
    "cpu":    {"abs": 1.00, "low": 1.05, "mod": 1.17, "hig": 1.38},
    "mem":    {"abs": 1.00, "low": 1.10, "mod": 1.67, "hig": 1.79},
    "disk":   {"abs": 1.00, "low": 1.21, "mod": 1.92, "hig": 2.31},
    "cache":  {"abs": 1.00, "low": 1.12, "mod": 1.24, "hig": 1.32},
    "net":    {"abs": 1.00, "low": 1.13, "mod": 1.43, "hig": 1.62},
    "regime": {"abs": 1.00, "low": 1.20, "mod": 1.55, "hig": 1.95},
}

APPS_SORTED = [
    "app01_ml_llc", "app05_streaming", "app10_search", "app11_sort_net",
    "app13_query_scan", "app16_cpu_oversub", "app17_mem_pressure",
]
TRUE_CLASS = {
    "app10_search": "cpu", "app05_streaming": "mem", "app17_mem_pressure": "mem",
    "app13_query_scan": "disk", "app11_sort_net": "net", "app01_ml_llc": "cache",
    "app16_cpu_oversub": "regime",
}

ALL = ["netp", "nets", "blk", "mbw", "llcmr", "llcocc", "cpu", "schedlat",
       "psi_mem", "membw_est", "psi_io", "schedthr", "steal", "psp", "idle_preempt"]
IDX = {name: i for i, name in enumerate(ALL)}
DOMINANT = {"cpu": "cpu", "mem": "membw_est", "disk": "blk", "cache": "llcmr", "regime": "psp"}


def cloudlet_to_workload(cloudlet_id):
    idx = (cloudlet_id - 1) // 4
    return APPS_SORTED[idx] if 0 <= idx < len(APPS_SORTED) else None


def load_level_rule(path):
    rule = {}
    with open(path) as f:
        next(f)
        for line in f:
            cls, dom, mean, sd, cut_lo, cut_hi, cut_lo_z, cut_hi_z = line.rstrip("\n").split("\t")
            rule[cls] = dict(mean=float(mean), sd=float(sd),
                              cut_lo_z=float(cut_lo_z), cut_hi_z=float(cut_hi_z))
    return rule


def metric_value(row, name):
    if name == "net":
        return max(row[IDX["netp"]], row[IDX["nets"]])
    return row[IDX[name]]


def read_trace_csv(path):
    rows = []
    for line in open(path):
        line = line.strip()
        if not line:
            continue
        rows.append([float(x) for x in line.split(";")[:15]])
    return rows


def level_for(cls, raw_value, rule):
    r = rule[cls]
    z = (raw_value - r["mean"]) / r["sd"] if r["sd"] else 0.0
    if z < r["cut_lo_z"]:
        return "low"
    if z >= r["cut_hi_z"]:
        return "hig"
    return "mod"


def truth_cost(true_cls, level, yardstick):
    """yardstick: 'Y5' (regime->cpu, 5 classes) or 'Y6' (regime priced)."""
    cls = true_cls
    if yardstick == "Y5" and cls == "regime":
        cls = "cpu"
    levels = {"cpu": "abs", "mem": "abs", "disk": "abs", "cache": "abs", "net": "abs"}
    regime_level = "abs"
    if cls == "regime":
        regime_level = level
    else:
        levels[cls] = level
    cost = DEG["cpu"][levels["cpu"]] * DEG["mem"][levels["mem"]] * DEG["disk"][levels["disk"]] \
        * DEG["cache"][levels["cache"]] * DEG["net"][levels["net"]]
    if yardstick == "Y6":
        cost *= DEG["regime"][regime_level]
    return max(cost, 1.0)


def parse_last_placement(log_text):
    """Return list of (cloudlet, host, hpe, cpe, cost) from the LAST table."""
    parts = log_text.split("Cloudlet Host  Hpe  Cpe CloudletCost")
    if len(parts) < 2:
        return []
    tab = parts[-1].split("=====")[0]
    rows = []
    for line in tab.strip().splitlines():
        f = line.split()
        if len(f) != 5:
            continue
        try:
            cloudlet, host, hpe, cpe, cost = (float(x) for x in f)
        except ValueError:
            continue
        rows.append((int(cloudlet), int(host), hpe, cpe, cost))
    return rows


def score_placement(placement_rows, cloudlet_truth_costs):
    """sum over hosts of product over that host's cloudlets of (cost*Hpe/Cpe)."""
    by_host = {}
    for cloudlet, host, hpe, cpe, _old_cost in placement_rows:
        tc = cloudlet_truth_costs.get(cloudlet)
        if tc is None:
            continue
        by_host.setdefault(host, []).append(tc * hpe / cpe)
    total = 0.0
    for host, vals in by_host.items():
        prod = 1.0
        for v in vals:
            prod *= v
        total += prod
    return total


def compute_cloudlet_truth_costs(canonical_trace_dir, rule, yardstick, window):
    """window: 'full' (mean over whole trace) or 'final6th' (mean over the
    last 1/6 of the trace, matching the final analysis interval)."""
    trace_files = []
    for app in APPS_SORTED:
        app_dir = os.path.join(canonical_trace_dir, app)
        for pattern in sorted(os.listdir(app_dir)):
            trace_files.append(os.path.join(app_dir, pattern))
    trace_files.sort()  # matches Arrays.sort() two-level order (subdir, then file)
    # subdir sort is already APPS_SORTED order; re-sort files within each app dir
    ordered = []
    for app in APPS_SORTED:
        app_dir = os.path.join(canonical_trace_dir, app)
        files = sorted(os.listdir(app_dir))
        for fn in files:
            ordered.append(os.path.join(app_dir, fn))

    costs = {}
    for i, path in enumerate(ordered, start=1):
        wl = cloudlet_to_workload(i)
        true_cls = TRUE_CLASS[wl]
        rows = read_trace_csv(path)
        dom = "net" if true_cls == "net" else DOMINANT[true_cls if true_cls != "regime" or yardstick == "Y6" else "cpu"]
        if true_cls == "regime" and yardstick == "Y5":
            dom = DOMINANT["cpu"]
        if window == "final6th":
            n = len(rows)
            seg = rows[max(0, n - max(1, n // 6)):]
        else:
            seg = rows
        vals = [metric_value(r, dom) for r in seg]
        raw = st.mean(vals) if vals else 0.0
        score_cls = "cpu" if (true_cls == "regime" and yardstick == "Y5") else true_cls
        level = level_for(score_cls, raw, rule)
        costs[i] = truth_cost(true_cls, level, yardstick)
    return costs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work-root", required=True)
    ap.add_argument("--canonical-trace-dir", required=True,
                     help="tier B's vm-guest/v3.3/source tree (canonical metric source)")
    ap.add_argument("--level-rule", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--tiers", nargs="+", default=["T1", "A", "B"])
    ap.add_argument("--reps", type=int, default=20)
    ap.add_argument("--work-subdir-prefix", default="s1-gate-")
    ap.add_argument("--approach", default="IASA", help="IASA|EVEN|CIAPA, tags every row")
    ap.add_argument("--append", action="store_true",
                     help="append to existing s1-truthscore.tsv instead of overwriting")
    args = ap.parse_args()

    rule = load_level_rule(args.level_rule)
    os.makedirs(args.out, exist_ok=True)

    truthscore_path = os.path.join(args.out, "s1-truthscore.tsv")
    placements_dir = os.path.join(args.out, "s1-placements", args.approach)
    os.makedirs(placements_dir, exist_ok=True)

    scores = {}  # (tier, yardstick, window) -> [values]
    write_header = not (args.append and os.path.exists(truthscore_path))
    with open(truthscore_path, "a" if args.append else "w") as sf:
        if write_header:
            sf.write("approach\ttier\trep\tyardstick\twindow\tscore\n")
        for tier in args.tiers:
            subdir = args.work_subdir_prefix.format(tier=tier)
            pattern = os.path.join(args.work_root, subdir, tier, "v3.3", "vm-guest", "rep*", "cloudsim.log")
            logs = sorted(glob.glob(pattern))
            if not logs:
                print(f"WARN: no logs matched {pattern}")
            for log_path in logs:
                rep = os.path.basename(os.path.dirname(log_path))
                rows = parse_last_placement(open(log_path, errors="ignore").read())
                if not rows:
                    print(f"WARN: no final placement table in {log_path}")
                    continue
                with open(os.path.join(placements_dir, f"{tier}-{rep}.tsv"), "w") as pf:
                    pf.write("cloudletId\thostId\n")
                    for cloudlet, host, _hpe, _cpe, _cost in rows:
                        pf.write(f"{cloudlet}\t{host}\n")
                for yardstick in ("Y5", "Y6"):
                    for window in ("full", "final6th"):
                        costs = compute_cloudlet_truth_costs(
                            args.canonical_trace_dir, rule, yardstick, window)
                        score = score_placement(rows, costs)
                        scores.setdefault((tier, yardstick, window), []).append(score)
                        sf.write(f"{args.approach}\t{tier}\t{rep}\t{yardstick}\t{window}\t{score:.4f}\n")

    summary_path = os.path.join(args.out, "s1-truthscore-summary.tsv")
    summary_rows = {}
    if args.append and os.path.exists(summary_path):
        with open(summary_path) as f:
            next(f)
            for line in f:
                p = line.rstrip("\n").split("\t")
                summary_rows[(p[0], p[1], p[2], p[3])] = line
    for (tier, yardstick, window), vals in scores.items():
        mean = st.mean(vals)
        sd = st.stdev(vals) if len(vals) > 1 else 0.0
        summary_rows[(args.approach, tier, yardstick, window)] = \
            f"{args.approach}\t{tier}\t{yardstick}\t{window}\t{mean:.4f}\t{sd:.4f}\t{len(vals)}\n"
    with open(summary_path, "w") as f:
        f.write("approach\ttier\tyardstick\twindow\tmean\tsd\tn\n")
        for key in sorted(summary_rows):
            f.write(summary_rows[key])
    for (tier, yardstick, window), vals in sorted(scores.items()):
        mean = st.mean(vals)
        sd = st.stdev(vals) if len(vals) > 1 else 0.0
        print(f"[{args.approach}] {tier} {yardstick} {window}: mean={mean:.1f} sd={sd:.1f} n={len(vals)}")
    print(f"wrote {truthscore_path}\nwrote {summary_path}\nplacements in {placements_dir}")


if __name__ == "__main__":
    main()

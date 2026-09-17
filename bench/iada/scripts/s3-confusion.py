#!/usr/bin/env python3
"""s3-confusion.py -- S16/S3 (jsa-repo-fix-brief), class confusion inside the simulation.

Parses the "CLS <tier> <interval> <cloudletId> <predClass> <level>" lines
(-Diada.logClasses=on) out of each rep's cloudsim.log, maps cloudletId to its
workload via the fixed two-level sort xxIntExample.java itself uses when
building cloudletList (sorted app subdirs, sorted pattern files within each --
confirmed by reading createIntContainerCloudletList), and compares against
the brief's truth map.

We score the FINAL interval only (the last CLS line seen for each cloudlet in
a rep) as "the predicted class for that cloudlet's placement" -- CLS lines
accumulate once per getMLClass call, which fires many times per cloudlet
across the SA search; the final placement's classification is what the
degradation-cost placements table brief Step 2/S2 reads, so this is the
same readout S2 needs downstream.
"""
import argparse
import glob
import os
import re
import statistics as st
from collections import defaultdict

# 7 apps in the tree, in the SAME alphabetical order Arrays.sort() gives
# their directory names, each contributing 4 cloudlets (con, dec, inc, osc --
# also alphabetical). Cloudlet ids are 1-based in that flattened order.
APPS_SORTED = [
    "app01_ml_llc", "app05_streaming", "app10_search", "app11_sort_net",
    "app13_query_scan", "app16_cpu_oversub", "app17_mem_pressure",
]

TRUTH = {
    "app10_search": "cpu",
    "app05_streaming": "mem",
    "app17_mem_pressure": "mem",
    "app13_query_scan": "disk",
    "app11_sort_net": "net",
    "app01_ml_llc": "cache",
    # app16_cpu_oversub: regime for tier B, cpu for T1/A -- resolved per-tier below.
}


def cloudlet_to_workload(cloudlet_id):
    idx = (cloudlet_id - 1) // 4
    if idx < 0 or idx >= len(APPS_SORTED):
        return None
    return APPS_SORTED[idx]


def true_class(workload, tier):
    if workload == "app16_cpu_oversub":
        return "regime" if tier == "B" else "cpu"
    return TRUTH.get(workload)


CLS_RE = re.compile(r"^CLS (\S+) (\d+) (\d+) (\S+) (\S+)$")


def parse_log(path):
    """Return {cloudlet_id: (last_interval, predClass, level)}."""
    last = {}
    for line in open(path, errors="ignore"):
        m = CLS_RE.match(line.strip())
        if not m:
            continue
        tier, interval, cid, pred, level = m.groups()
        cid = int(cid)
        interval = int(interval)
        prev = last.get(cid)
        if prev is None or interval >= prev[0]:
            last[cid] = (interval, pred, level)
    return last


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work-root", required=True, help="WORK dir used by run-sim-arm.sh")
    ap.add_argument("--out", required=True)
    ap.add_argument("--tiers", nargs="+", default=["T1", "A", "B"])
    ap.add_argument("--reps", type=int, default=10)
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    class_log_path = os.path.join(args.out, "s3-class-log.tsv")
    confusion_path = os.path.join(args.out, "s3-confusion.tsv")
    summary_path = os.path.join(args.out, "s3-summary.tsv")

    confusion = defaultdict(int)  # (tier, true, pred) -> count
    per_class_correct = defaultdict(int)
    per_class_total = defaultdict(int)
    correct_per_rep = defaultdict(list)  # tier -> [correct count per rep]

    with open(class_log_path, "w") as clf:
        clf.write("tier\trep\tcloudlet_id\tworkload\ttrue_class\tpred_class\tlevel\tcorrect\n")
        for tier in args.tiers:
            for rep in range(1, args.reps + 1):
                log_path = os.path.join(args.work_root, f"s3-gate-{tier}", tier,
                                          "v3.3", "vm-guest", f"rep{rep}", "cloudsim.log")
                if not os.path.exists(log_path):
                    print(f"WARN: missing {log_path}")
                    continue
                last = parse_log(log_path)
                n_correct = 0
                n_scored = 0
                for cid, (interval, pred, level) in sorted(last.items()):
                    wl = cloudlet_to_workload(cid)
                    if wl is None:
                        continue
                    tc = true_class(wl, tier)
                    if tc is None:
                        continue
                    correct = int(pred == tc)
                    n_correct += correct
                    n_scored += 1
                    confusion[(tier, tc, pred)] += 1
                    per_class_total[(tier, tc)] += 1
                    per_class_correct[(tier, tc)] += correct
                    clf.write(f"{tier}\t{rep}\t{cid}\t{wl}\t{tc}\t{pred}\t{level}\t{correct}\n")
                correct_per_rep[tier].append(n_correct)

    with open(confusion_path, "w") as cf:
        cf.write("tier\ttrue\tpredicted\tcount\n")
        for (tier, tc, pred), n in sorted(confusion.items()):
            cf.write(f"{tier}\t{tc}\t{pred}\t{n}\n")

    with open(summary_path, "w") as sf:
        sf.write("tier\tmean_correct_of_28\tsd\tn_reps\n")
        for tier in args.tiers:
            vals = correct_per_rep[tier]
            if not vals:
                continue
            mean = st.mean(vals)
            sd = st.stdev(vals) if len(vals) > 1 else 0.0
            sf.write(f"{tier}\t{mean:.2f}\t{sd:.2f}\t{len(vals)}\n")
        sf.write("\nclass\ttier\taccuracy\tn\n")
        for (tier, tc), total in sorted(per_class_total.items()):
            acc = per_class_correct[(tier, tc)] / total if total else 0.0
            sf.write(f"{tc}\t{tier}\t{acc:.3f}\t{total}\n")

    for tier in args.tiers:
        vals = correct_per_rep[tier]
        if vals:
            print(f"{tier}: mean {st.mean(vals):.2f}/28 correct "
                  f"(sd {st.stdev(vals) if len(vals) > 1 else 0:.2f}, n={len(vals)})")
    print(f"wrote {class_log_path}\nwrote {confusion_path}\nwrote {summary_path}")


if __name__ == "__main__":
    main()

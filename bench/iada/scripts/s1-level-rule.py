#!/usr/bin/env python3
"""s1-level-rule.py -- S16/S1 (jsa-repo-fix-brief), classifier-free degradation
level rule. MUST be run and its output written to CONFORMANCE.md BEFORE any
placement is scored (brief: "Define it before looking at any results").

Design decision (documented here and in CONFORMANCE.md): tier B's train/ split
is the ONLY host-trained source that carries all six dominant metrics this
rule needs (T1 and A's own 7-column feature sets do not include membw_est or
psp at all). Using B's train split as the single canonical source for BOTH
the tertile cut points AND, in the scoring step, the per-cloudlet raw metric
values (from B's guest tree, which shares the same 28 (workload,pattern)
traces in the same sorted order as T1's and A's trees -- verified in the S10
DECISIONS entry) makes the yardstick a single fixed ruler, independent of
which tier produced the placement being scored -- exactly what the brief's
accept test requires (identical placements score identically regardless of
tier).

ALL metric order (matches generate-iada-tree.py / campaign-to-trainsets.py):
  netp,nets,blk,mbw,llcmr,llcocc,cpu,schedlat,psi_mem,membw_est,psi_io,
  schedthr,steal,psp,idle_preempt
"""
import argparse
import glob
import os
import statistics as st

ALL = ["netp", "nets", "blk", "mbw", "llcmr", "llcocc", "cpu", "schedlat",
       "psi_mem", "membw_est", "psi_io", "schedthr", "steal", "psp", "idle_preempt"]
IDX = {name: i for i, name in enumerate(ALL)}

CLASS_FILE = {"cpu": "cpu100.csv", "mem": "memory100.csv", "disk": "disk100.csv",
              "net": "net100.csv", "cache": "cache100.csv", "regime": "regime100.csv"}

# Dominant metric per class, per the brief.
DOMINANT = {"cpu": "cpu", "mem": "membw_est", "disk": "blk", "cache": "llcmr", "regime": "psp"}
# net's dominant metric is max(netp, nets); handled specially below.


def read_csv(path):
    rows = []
    for line in open(path):
        line = line.strip()
        if not line:
            continue
        f = line.split(";")
        vals = [float(x) for x in f[:15]]
        rows.append(vals)
    return rows


def metric_value(row, name):
    if name == "net":
        return max(row[IDX["netp"]], row[IDX["nets"]])
    return row[IDX[name]]


def tertiles(values):
    """Two cut points dividing sorted values into three equal-count groups."""
    s = sorted(values)
    n = len(s)
    lo = s[n // 3]
    hi = s[(2 * n) // 3]
    return lo, hi


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trainset-root", default=os.path.expanduser("~/iada-trainsets/B/train"))
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    all_rows_by_class = {}
    for cls, fname in CLASS_FILE.items():
        path = os.path.join(args.trainset_root, fname)
        all_rows_by_class[cls] = read_csv(path)

    # Pooled host mean/sd per metric, over ALL rows of ALL classes (the general
    # baseline used to standardize both cut points and guest raw values).
    pooled_rows = [r for rows in all_rows_by_class.values() for r in rows]
    metrics_for_meansd = set(DOMINANT.values()) | {"netp", "nets"}
    mean_sd = {}
    for m in metrics_for_meansd:
        vals = [metric_value(r, m) for r in pooled_rows]
        mean_sd[m] = (st.mean(vals), st.pstdev(vals) or 1.0)  # avoid div-by-0

    # For "net" (max of two columns), standardize on the max-of-two series itself.
    net_vals = [metric_value(r, "net") for r in pooled_rows]
    mean_sd["net"] = (st.mean(net_vals), st.pstdev(net_vals) or 1.0)

    rule = {}
    lines = ["class\tdominant_metric\thost_mean\thost_sd\tcut_lo_raw\tcut_hi_raw\tcut_lo_z\tcut_hi_z"]
    for cls in ["cpu", "mem", "disk", "net", "cache", "regime"]:
        dom = "net" if cls == "net" else DOMINANT[cls]
        own_rows = all_rows_by_class[cls]
        own_vals = [metric_value(r, dom) for r in own_rows]
        cut_lo, cut_hi = tertiles(own_vals)
        mean, sd = mean_sd[dom]
        cut_lo_z, cut_hi_z = (cut_lo - mean) / sd, (cut_hi - mean) / sd
        rule[cls] = dict(dominant=dom, mean=mean, sd=sd, cut_lo=cut_lo, cut_hi=cut_hi,
                          cut_lo_z=cut_lo_z, cut_hi_z=cut_hi_z)
        lines.append(f"{cls}\t{dom}\t{mean:.4f}\t{sd:.4f}\t{cut_lo:.4f}\t{cut_hi:.4f}\t"
                      f"{cut_lo_z:.4f}\t{cut_hi_z:.4f}")
        print(f"{cls:8s} dominant={dom:10s} host_mean={mean:8.3f} host_sd={sd:8.3f} "
              f"cut_z=({cut_lo_z:+.3f}, {cut_hi_z:+.3f})")

    out_path = os.path.join(args.out, "s1-level-rule.tsv")
    with open(out_path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()

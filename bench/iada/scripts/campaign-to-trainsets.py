#!/usr/bin/env python3
"""campaign-to-trainsets.py — adapt our 15-metric campaign into IADA classifier
training/test sets for the 3-tier comparison (Tier-1 canonical-7, Approach A
proxy-swap, Approach B full-15+regime).

Our micro-benchmarks are each built to stress one resource, so they ARE the
labelled per-class samples the IADA classifier (Meyer 2021) trains on:
  app10_search→cpu  app05_streaming/app17_mem_pressure→mem  app13_query_scan→disk
  app11_sort_net→net  app01_ml_llc→cache  app16_cpu_oversub→regime (B only)

Each portable.tsv data row (one sampling interval) is one training sample. We
pool host envs (bare/container) for TRAINING and hold out vm-guest for the
portability TEST — in the VM mbw/llcmr/llcocc arrive as 0/'--', which is exactly
where Tier-1 goes blind and A/B must recover.

Emits, per config, retrain.R's legacy flat layout (semicolon, no header):
  <out>/<config>/train/{cpu100,memory100,disk100,net100,cache100[,regime100]}.csv
  <out>/<config>/test-vm/{...}.csv

  python3 campaign-to-trainsets.py <campaign_dir> --out-root DIR [--variant v3.3]
"""
from __future__ import annotations

import argparse
import glob
import os
from collections import defaultdict

# canonical portable.tsv column order (15 metrics)
ALL = ["netp", "nets", "blk", "mbw", "llcmr", "llcocc", "cpu",
       "schedlat", "psi_mem", "membw_est", "psi_io", "schedthr", "steal",
       "psp", "idle_preempt"]

# the three tier configs: ordered output columns. retrain.R reads positionally
# with col.names=FEATURES, so T1/A keep 7 wide and A simply puts membw_est where
# mbw was (mem level-col stays index 4) — a pure input swap, no classifier change.
CONFIGS = {
    "T1": ["netp", "nets", "blk", "mbw", "llcmr", "llcocc", "cpu"],
    "A":  ["netp", "nets", "blk", "membw_est", "llcmr", "llcocc", "cpu"],
    "B":  ALL,
}
# class -> exemplar workload(s); regime only used by B
CLASS_WL = {
    "cpu":    ["app10_search"],
    "mem":    ["app05_streaming", "app17_mem_pressure"],
    "disk":   ["app13_query_scan"],
    "net":    ["app11_sort_net"],
    "cache":  ["app01_ml_llc"],
    "regime": ["app16_cpu_oversub"],
}
CSV_NAME = {"cpu": "cpu100.csv", "mem": "memory100.csv", "disk": "disk100.csv",
            "net": "net100.csv", "cache": "cache100.csv", "regime": "regime100.csv"}


def parse_portable(path, rep_id=None):
    """yield dict(metric->float) per data row; '--'/missing -> 0.0. If rep_id is
    given, it's stamped onto every row under '_rep_id' (kept out of the feature
    set consumed downstream -- see write_csv/eval-tiers.R's cv_eval grouping)."""
    hdr = None
    for line in open(path, errors="ignore"):
        line = line.rstrip("\n")
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if hdr is None:
            if parts[0] == "netp":          # the header row (15 metric names)
                hdr = parts
                continue
            hdr = ALL                        # headerless fallback
        # data rows carry a leading wall-clock ts column absent from the header
        # (16 fields vs 15) -> drop the extra leading column(s).
        off = len(parts) - len(hdr)
        if off < 0:
            continue
        row = {}
        for i, m in enumerate(hdr):
            v = parts[i + off]
            try:
                row[m] = float(v) if v not in ("--", "") else 0.0
            except ValueError:
                row[m] = 0.0
        if rep_id is not None:
            row["_rep_id"] = rep_id
        yield row


def gather(campaign, variant, envs, workloads):
    """all sample rows (list of metric-dicts) for the given workloads/envs.
    Each row carries '_rep_id' = env|variant|workload|repN -- adjacent seconds
    of the same repetition are highly correlated, so this is the grouping key
    a leakage-free CV must fold on (see eval-tiers.R cv_eval's `group` mode)."""
    rows = []
    for env in envs:
        for wl in workloads:
            for f in glob.glob(os.path.join(campaign, env, variant, "solo", wl,
                                            "rep*", "portable.tsv")):
                rep = os.path.basename(os.path.dirname(f))   # "repN"
                rep_id = f"{env}|{variant}|{wl}|{rep}"
                rows.extend(parse_portable(f, rep_id=rep_id))
    return rows


def fmt(v):
    return str(int(v)) if float(v).is_integer() else f"{v:.4g}"


def write_csv(path, rows, cols):
    """Feature columns first (retrain.R's legacy fixed-width layout, unchanged
    -- retrain.R and the iada-tier-rda/*/forced/ datasets never read from this
    output root, only eval-tiers.R does), then '_rep_id' as one extra trailing
    column. eval-tiers.R's read_split() knows to split it back off before
    building the feature matrix."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        for r in rows:
            feat = ";".join(fmt(r.get(c, 0.0)) for c in cols)
            fh.write(f"{feat};{r.get('_rep_id', '')}\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("campaign")
    ap.add_argument("--out-root", default="results/iada-trainsets")
    ap.add_argument("--variant", default="v3.3")
    ap.add_argument("--train-envs", default="bare,container")
    ap.add_argument("--test-env", default="vm-guest")
    args = ap.parse_args()
    train_envs = args.train_envs.split(",")

    summary = []
    for cfg, cols in CONFIGS.items():
        classes = list(CLASS_WL) if cfg == "B" else [c for c in CLASS_WL if c != "regime"]
        for split, envs in (("train", train_envs), ("test-vm", [args.test_env])):
            for cls in classes:
                rows = gather(args.campaign, args.variant, envs, CLASS_WL[cls])
                out = os.path.join(args.out_root, cfg, split, CSV_NAME[cls])
                write_csv(out, rows, cols)
                summary.append((cfg, split, cls, len(rows), len(cols)))
    # report
    print(f"{'config':6} {'split':8} {'class':7} {'samples':>8} {'cols':>5}")
    for cfg, split, cls, n, ncol in summary:
        print(f"{cfg:6} {split:8} {cls:7} {n:8d} {ncol:5d}")
    print(f"\n[wrote {args.out_root}/{{T1,A,B}}/{{train,test-vm}}/*.csv]")


if __name__ == "__main__":
    main()

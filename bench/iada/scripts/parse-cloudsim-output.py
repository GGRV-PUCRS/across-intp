#!/usr/bin/env python3
"""Parse CloudSim/IADA stdout into a single-row TSV of scheduling metrics.

Output format produced by IntContainerDataCenter (line ~1240-1270):

    ======================================
    Cloudlet Host  Hpe  Cpe CloudletCost
       1.0   1.0  48.0  12.0    1.60
       2.0   1.0  48.0  12.0    1.60
       ...
       192.0  48.0  48.0  12.0    2.07
    ======================================

    <N>                  # number of intervals/solutions
    Algorithm: SAO
    <iv1>                # TotalInterferenceCost per interval (N values)
    <iv2>
    ...

    Migrations:
    <m1>                 # migrations between consecutive intervals (N-1 values)
    <m2>
    ...

    interf with mig :
    <idi1>               # IDI = interference + migrations*migvalue (N values)
    <idi2>
    ...

    End of Simulation ... (X min - Y sec)

Metrics extracted (per the IADA paper, Sec V):
  - cloudlets_total              # of apps in placement table
  - cloudletcost_avg/sum         placement cost (proxy for response degradation)
  - intervals_count              N (CPD-detected intervals)
  - interference_avg/sum         per-interval mean & total interference
  - migrations_total             sum of all migrations
  - migrations_avg               mean per interval transition
  - idi_avg/sum/max              the main IADA paper metric (interf+mig cost)
  - sim_wallclock_minutes        wall-clock duration
  - sim_finished                 1 if "End of Simulation" was logged
  - classifier_calls             # of MLClassifier R invocations
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path
from statistics import mean

# Lines like "    12.0   3.0  48.0  12.0    1.60"
PLACEMENT_RE = re.compile(
    r"^\s*(\d+\.\d+)\s+(\d+\.\d+)\s+(\d+\.\d+)\s+(\d+\.\d+)\s+(\d+\.\d+)\s*$"
)
NUM_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*$")
END_RE = re.compile(r"End of Simulation.*\((\d+)\s*min\s*-\s*(\d+)\s*sec\)")
MIN_SEC_RE = re.compile(r"^\s*(\d+)\s*min\s*-\s*(\d+)\s*sec\s*$")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--log", required=True, type=Path)
    p.add_argument("--variant", required=True)
    p.add_argument("--env", required=True)
    p.add_argument("--workload-mix", required=True)
    p.add_argument("--output", required=True, type=Path)
    args = p.parse_args()

    if not args.log.exists():
        print(f"FATAL: log not found: {args.log}", file=sys.stderr)
        return 2

    placements: list[tuple[float, float, float, float, float]] = []
    interference: list[float] = []
    migrations: list[float] = []
    idi: list[float] = []
    self_score: list[float] = []
    oracle: list[float] = []

    section = None  # 'placement' | 'interference' | 'migrations' | 'idi' | 'self' | 'oracle'
    sim_finished = False
    sim_wallclock_min = 0
    classifier_calls = 0

    with args.log.open(errors="replace") as f:
        for raw in f:
            line = raw.rstrip("\n")

            # Section transitions
            if "Cloudlet Host" in line and "CloudletCost" in line:
                section = "placement"
                # Reset: placement table is reprinted per interval; keep only last
                placements = []
                continue
            if line.startswith("Algorithm:"):
                section = "interference"
                continue
            if line.strip() == "Migrations:" or line.strip().startswith("Migrations"):
                section = "migrations"
                continue
            if "interf with mig" in line:
                section = "idi"
                continue
            if "self re-score" in line:
                section = "self"
                continue
            if "oracle re-score" in line:
                section = "oracle"
                continue
            if line.startswith("======"):
                if section == "placement":
                    section = None
                continue

            # End of simulation marker
            m = END_RE.search(line)
            if m:
                sim_finished = True
                sim_wallclock_min = int(m.group(1))
                continue

            # Per-classifier-call timing (each MLClassifier invocation logs this)
            if MIN_SEC_RE.match(line) and section is None:
                classifier_calls += 1
                continue

            # Section content
            if section == "placement":
                pm = PLACEMENT_RE.match(line)
                if pm:
                    placements.append(tuple(float(x) for x in pm.groups()))
            elif section in ("interference", "migrations", "idi", "self", "oracle"):
                nm = NUM_RE.match(line)
                if nm:
                    val = float(nm.group(1))
                    if section == "interference":
                        interference.append(val)
                    elif section == "migrations":
                        migrations.append(val)
                    elif section == "idi":
                        idi.append(val)
                    elif section == "self":
                        self_score.append(val)
                        section = None  # single value, not per-interval
                    elif section == "oracle":
                        oracle.append(val)
                        section = None  # single value, not per-interval -- don't
                                        # keep swallowing unrelated numbers after it

    cloudlet_costs = [t[4] for t in placements]
    n_int = len(interference)

    row = {
        "variant": args.variant,
        "env": args.env,
        "workload_mix": args.workload_mix,
        "cloudlets_total": len(placements),
        "cloudletcost_avg": round(mean(cloudlet_costs), 4) if cloudlet_costs else 0,
        "cloudletcost_sum": round(sum(cloudlet_costs), 4),
        "intervals_count": n_int,
        "interference_avg": round(mean(interference), 4) if interference else 0,
        "interference_sum": round(sum(interference), 4),
        "interference_max": round(max(interference), 4) if interference else 0,
        "migrations_total": int(sum(migrations)),
        "migrations_avg": round(mean(migrations), 4) if migrations else 0,
        "idi_avg": round(mean(idi), 4) if idi else 0,
        "idi_sum": round(sum(idi), 4),
        "idi_max": round(max(idi), 4) if idi else 0,
        # -Diada.oracleLabels=on only (jsa-repo-fix-brief Phase 3.2): the final
        # converged solution re-scored twice, both over the SAME full-trace
        # window (idi_avg above used the search's own narrow per-interval
        # windows, not comparable to either of these on window alone):
        # self_idi = this tier's own classifier; oracle_idi = tier B's. The
        # self_idi vs oracle_idi gap isolates classifier width; empty/"" when
        # the flag was off (nothing printed to parse).
        "self_idi": round(self_score[0], 4) if self_score else "",
        "oracle_idi": round(oracle[0], 4) if oracle else "",
        "sim_wallclock_min": sim_wallclock_min,
        "sim_finished": int(sim_finished),
        "classifier_calls": classifier_calls,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(row.keys()), delimiter="\t")
        writer.writeheader()
        writer.writerow(row)

    print(
        f"[{args.variant}/{args.env}/{args.workload_mix}] "
        f"finished={row['sim_finished']} "
        f"cloudlets={row['cloudlets_total']} "
        f"intervals={row['intervals_count']} "
        f"idi_avg={row['idi_avg']} "
        f"migrations={row['migrations_total']} "
        f"wall={row['sim_wallclock_min']}min"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

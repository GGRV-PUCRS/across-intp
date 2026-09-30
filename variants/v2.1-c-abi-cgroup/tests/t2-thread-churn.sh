#!/usr/bin/env bash
# T2 (C38): under continuous thread churn (every worker exits after CHURN_MS and
# is replaced) no v2.1 schedlat/psp interval may collapse to 0, and no interval
# may show a uint64-underflow spike.
#
# Uses --output json for 3-decimal values (the TSV rounds to integers).
# Short-lived threads that are born AND exit between two samples are never seen
# by a /proc sampler, so the absolute level is below v3.3's; this test checks
# the no-collapse / no-underflow properties only.
#
#   tests/t2-thread-churn.sh        T2_SECS=20 T2_THREADS=4 T2_CPUS=0 T2_CHURN_MS=100
#   INTP_V33_BIN=/path/intp-ebpf-core-cgroup   (root) -> v3.3 samples the same
#       cgroup concurrently and its schedlat median is printed as the level
#       reference. A v2.1 schedlat interval at 0 passes as QUIET only when
#       v3.3 also reads < 10 % of its own median in that interval; otherwise
#       it stays a FAIL.
#
# Known false failure (C38, logs/c38-local-root-20260930-172435): the slots
# churn nearly in lockstep, so a sample taken just after a worker turnover sees
# only newborn threads and can read schedlat 0 (about 0.7 % of instants). v3.3
# does not dip then, so such a zero still fails.
set -euo pipefail
. "$(dirname "$0")/lib-portable.sh"

SECS=${T2_SECS:-20}
NTHR=${T2_THREADS:-4}
CPUS=${T2_CPUS:-0}
CHURN=${T2_CHURN_MS:-100}
build_helper

read -r PID CG < <(spawn_in_cgroup t2 taskset -c "$CPUS" "$MT_SPIN" "$NTHR" $((SECS + 10)) "$CHURN")
note "mt_spin pid=$PID threads=$NTHR churn=${CHURN}ms cgroup=$CG"

for tgt in cg pid; do
    if [ $tgt = cg ]; then args=(--cgroup "$CG"); else args=(--pids "$PID"); fi
    "$NEW_BIN" "${args[@]}" --portable-metrics --interval 1 --duration "$SECS" \
        --output json >"$WORK/new-$tgt.json" 2>"$WORK/new-$tgt.err" &
done
if [ -n "$V33_BIN" ] && [ "$(id -u)" = 0 ]; then
    "$V33_BIN" --cgroup "$CG" --portable-metrics --interval 1 --duration "$SECS" \
        --output json >"$WORK/v33-cg.json" 2>"$WORK/v33-cg.err" &
fi
wait

python3 - "$WORK" <<'EOF'
import json, os, re, statistics, sys
work = sys.argv[1]

# v3.3 emits its canonical fields with %.2f, so an unavailable one (mbw
# without RDT) prints as a bare nan, which is not JSON (C38 observation).
def loads33(line):
    return json.loads(re.sub(r'(?<=:)-?nan\b', 'null', line))
rc = 0

def val(x):
    return x.get("v") if isinstance(x, dict) else x

v33 = None
if os.path.exists(f"{work}/v33-cg.json"):
    rows33 = [loads33(l) for l in open(f"{work}/v33-cg.json") if l.startswith("{")]
    v33 = [val(r.get("schedlat")) for r in rows33]
    ok33 = [v for v in v33[1:] if v is not None]
    med33 = statistics.median(ok33) if ok33 else float("nan")
    print(f"v33 schedlat median={med33:.3f} n={len(ok33)}")

for tgt in ("cg", "pid"):
    rows = [json.loads(l) for l in open(f"{work}/new-{tgt}.json") if l.startswith("{")]
    if len(rows) < 3:
        print(f"FAIL: {tgt}: only {len(rows)} samples"); rc = 1; continue
    for m, bound in (("schedlat", 100.0), ("psp", 1e7)):
        vals = [r[m]["v"] for r in rows[1:]]          # skip the warm-up sample
        zero = [i for i, v in enumerate(vals, 2) if v is None or v <= 0]
        huge = [i for i, v in enumerate(vals, 2) if v is not None and v > bound]
        print(f"{tgt:3} {m:8} min={min(v or 0 for v in vals):.3f} "
              f"max={max(v or 0 for v in vals):.3f} n={len(vals)}")
        if zero and m == "schedlat" and v33 is not None:
            quiet = [i for i in zero if i - 1 < len(v33) and v33[i - 1] is not None
                     and v33[i - 1] < 0.1 * med33]
            for i in quiet:
                print(f"QUIET: {tgt} {m} 0 at sample {i}; v3.3 reads "
                      f"{v33[i - 1]:.3f} there (median {med33:.3f}): workload did not contend")
            zero = [i for i in zero if i not in quiet]
        if zero: print(f"FAIL: {tgt} {m} collapsed to 0 at samples {zero}"); rc = 1
        if huge: print(f"FAIL: {tgt} {m} underflow-sized spike at samples {huge}"); rc = 1
print("T2: OK" if rc == 0 else "T2: FAILED")
sys.exit(rc)
EOF

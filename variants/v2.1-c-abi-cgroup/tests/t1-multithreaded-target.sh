#!/usr/bin/env bash
# T1 (C38): v2.1 schedlat/psp must count the WORKER threads of a multi-threaded
# target, not only its thread-group leader.
#
# mt_spin's leader sleeps while NTHREADS workers spin on fewer CPUs, so all the
# run-queue wait and involuntary preemption happens on non-leader threads.
#
#   tests/t1-multithreaded-target.sh
#   INTP_OLD_BIN=/path/pre-fix/intp-c-abi-cgroup  -> also assert the old binary reads ~0
#   INTP_V33_BIN=/path/intp-ebpf-core-cgroup       -> also assert v2.1/v3.3 in 0.5-2 (root)
#   T1_SECS=30 T1_THREADS=8 T1_CPUS=0-1            -> shape (defaults shown)
set -euo pipefail
. "$(dirname "$0")/lib-portable.sh"

SECS=${T1_SECS:-30}
NTHR=${T1_THREADS:-8}
CPUS=${T1_CPUS:-0-1}
build_helper

read -r PID CG < <(spawn_in_cgroup t1 taskset -c "$CPUS" "$MT_SPIN" "$NTHR" $((SECS + 10)))
note "mt_spin pid=$PID threads=$NTHR cpus=$CPUS cgroup=$CG"

# All profilers sample the same window concurrently (the portable metrics are
# read-only /proc and BPF; no RMID contention).
run_intp "$NEW_BIN" "$WORK/new-cg.tsv"  "$SECS" --cgroup "$CG" --portable-metrics &
run_intp "$NEW_BIN" "$WORK/new-pid.tsv" "$SECS" --pids "$PID"  --portable-metrics &
[ -n "$OLD_BIN" ] && run_intp "$OLD_BIN" "$WORK/old-cg.tsv" "$SECS" --cgroup "$CG" --portable-metrics &
[ -n "$V33_BIN" ] && run_intp "$V33_BIN" "$WORK/v33-cg.tsv" "$SECS" --cgroup "$CG" --portable-metrics &
wait

rc=0
for m in schedlat psp; do
    for tgt in cg pid; do
        v=$(tsv_median "$WORK/new-$tgt.tsv" "$m")
        echo "new  $tgt  $m median=$v"
        gt "$v" 0 || { echo "FAIL: new v2.1 $m on $tgt target is not > 0"; rc=1; }
    done
    if [ -n "$OLD_BIN" ]; then
        o=$(tsv_median "$WORK/old-cg.tsv" "$m")
        echo "old  cg   $m median=$o (expected ~0: leader-only)"
        n=$(tsv_median "$WORK/new-cg.tsv" "$m")
        # "~0": below 5 % of the fixed reading.
        gt "$(python3 -c "print($n*0.05)")" "$o" \
            || { echo "FAIL: old binary is not ~0 for $m -- F1 regression check did not reproduce"; rc=1; }
    fi
    if [ -n "$V33_BIN" ]; then
        n=$(tsv_median "$WORK/new-cg.tsv" "$m")
        e=$(tsv_median "$WORK/v33-cg.tsv" "$m")
        echo -n "v3.3 cg   $m median=$e  v2.1/v3.3 "
        ratio_in "$n" "$e" 0.5 2 || { echo "FAIL: v2.1/v3.3 $m outside 0.5-2"; rc=1; }
    fi
done
[ $rc = 0 ] && echo "T1: OK"
exit $rc

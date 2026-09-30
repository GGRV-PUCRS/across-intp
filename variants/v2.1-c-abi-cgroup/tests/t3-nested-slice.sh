#!/usr/bin/env bash
# T3 (C38): v2.1 resctrl enrollment must descend into child cgroups.
#
# A parent cgroup holds NO processes (cgroup v2 no-internal-processes rule, the
# compose-suite parent slice); two child cgroups run a cache-heavy stress-ng.
# Profiling the PARENT, v2.1 llcocc and mbw must be non-zero and agree with
# v3.3 within the W4 ratio band (0.8-1.25).
#
# Needs root, a mounted /sys/fs/resctrl with L3 monitoring, and stress-ng.
# Profilers run ONE AT A TIME: a task can be in only one RMID, so concurrent
# runs would steal each other's tasks.
#
# Run it against the OLD binary first to confirm F2 (plan section 1.3):
#   INTP_OLD_BIN=/path/pre-fix/intp-c-abi-cgroup tests/t3-nested-slice.sh
# If the old binary is NOT ~0 the script exits 3: F2 is not the cause of the
# compose-suite zeros; stop and report before re-running anything.
#
#   INTP_V33_BIN=/path/intp-ebpf-core-cgroup   -> agreement check (recommended)
#   T3_SECS=30 T3_WORKERS=4                    -> shape (defaults shown)
set -euo pipefail
. "$(dirname "$0")/lib-portable.sh"

SECS=${T3_SECS:-30}
WORKERS=${T3_WORKERS:-4}
[ "$(id -u)" = 0 ] || fail "T3 needs root (resctrl + cgroup creation)"
[ -d /sys/fs/resctrl/info/L3_MON ] || fail "resctrl L3 monitoring not mounted"
command -v stress-ng >/dev/null || fail "stress-ng not installed"

PARENT=/sys/fs/cgroup/intp-c38/t3
mkdir -p "$PARENT/a" "$PARENT/b"
TOTAL=$(( 3 * (SECS + 10) + 30 ))
for c in a b; do
    sh -c 'echo $$ > "$0/cgroup.procs"; shift; exec "$@"' "$PARENT/$c" _ \
        stress-ng --cache "$WORKERS" --timeout "${TOTAL}s" --quiet &
done
sleep 3
[ -z "$(cat "$PARENT/cgroup.procs")" ] || fail "parent cgroup is not empty"
note "parent=$PARENT children: a=$(wc -l <"$PARENT/a/cgroup.procs") b=$(wc -l <"$PARENT/b/cgroup.procs") procs"

run_one() {   # run_one LABEL BIN
    run_intp "$2" "$WORK/$1.tsv" "$SECS" --cgroup "$PARENT"
    for m in llcocc mbw; do
        eval "${1}_$m=$(tsv_median "$WORK/$1.tsv" "$m")"
    done
    sleep 2   # let the mon_group be removed before the next profiler
}

if [ -n "$OLD_BIN" ]; then
    run_one old "$OLD_BIN"
    echo "old  llcocc=$old_llcocc mbw=$old_mbw (expected 0: non-recursive enrollment)"
fi
run_one new "$NEW_BIN"
echo "new  llcocc=$new_llcocc mbw=$new_mbw"
if [ -n "$V33_BIN" ]; then
    run_one v33 "$V33_BIN"
    echo "v3.3 llcocc=$v33_llcocc mbw=$v33_mbw"
fi

rc=0
if [ -n "$OLD_BIN" ] && { gt "$old_llcocc" 0 || gt "$old_mbw" 0; }; then
    echo "STOP: the OLD binary reads non-zero llcocc/mbw on a nested slice."
    echo "      F2 is not the cause of the compose-suite zeros; investigate the"
    echo "      target resolution in mbw.c/llcocc.c before re-running (plan section 8)."
    exit 3
fi
gt "$new_llcocc" 0 || { echo "FAIL: new v2.1 llcocc is 0 on the nested slice"; rc=1; }
gt "$new_mbw" 0    || { echo "FAIL: new v2.1 mbw is 0 on the nested slice"; rc=1; }
if [ -n "$V33_BIN" ]; then
    for m in llcocc mbw; do
        n=new_$m; e=v33_$m
        echo -n "$m v2.1/v3.3 "
        ratio_in "${!n}" "${!e}" 0.8 1.25 || { echo "FAIL: $m outside the W4 band 0.8-1.25"; rc=1; }
    done
fi
[ $rc = 0 ] && echo "T3: OK"
exit $rc

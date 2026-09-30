#!/usr/bin/env bash
# run-c38-all.sh -- run every C38 test and keep the logs in the repository.
#
#   sudo tests/run-c38-all.sh [LABEL]
#
# Runs, in order: the unit tests, T1 (with the pre-fix regression leg and, as
# root, the v2.1/v3.3 agreement leg), T2, and T3 (old binary first, then the
# fixed one and v3.3). A test whose prerequisites are missing is recorded as
# SKIPPED with the reason, never as passed. Logs land in
# tests/logs/c38-<LABEL>-<timestamp>/, one file per test plus SUMMARY.txt and
# ENV.txt. LABEL defaults to "local"; use e.g. "testbed" so no hostname is
# written into the logs.
#
# The pre-fix binary is built from tag v0.2.0 (INTP_OLD_BIN overrides). That
# tree predates 2ab09e1, so it is built without -Werror. The v3.3 binary is
# variants/v3.3-ebpf-core-cgroup/intp-ebpf-core-cgroup (INTP_V33_BIN overrides).
set -uo pipefail

TESTS_DIR=$(cd "$(dirname "$0")" && pwd)
V21_DIR=$(cd "$TESTS_DIR/.." && pwd)
REPO=$(cd "$V21_DIR/../.." && pwd)
LABEL=${1:-local}
LOGDIR=$TESTS_DIR/logs/c38-$LABEL-$(date +%Y%m%d-%H%M%S)
mkdir -p "$LOGDIR"
SUMMARY=$LOGDIR/SUMMARY.txt
GIT=(git -c safe.directory='*' -C "$REPO")
IS_ROOT=0; [ "$(id -u)" = 0 ] && IS_ROOT=1
RESCTRL=0; [ -d /sys/fs/resctrl/info/L3_MON ] && RESCTRL=1
rc_all=0

record() { printf '%-8s %-7s %s\n' "$1" "$2" "${3:-}" | tee -a "$SUMMARY"; }

run_test() {   # run_test NAME CMD...
    local name=$1; shift
    echo "==> $name" >&2
    ( cd "$V21_DIR" && "$@" ) >"$LOGDIR/$name.log" 2>&1
    local rc=$?
    if [ $rc = 0 ]; then record "$name" PASS; else record "$name" FAIL "rc=$rc, see $name.log"; rc_all=1; fi
}

{
    echo "date:      $(date -Is)"
    echo "commit:    $("${GIT[@]}" rev-parse HEAD) ($("${GIT[@]}" describe --tags --always --dirty))"
    echo "kernel:    $(uname -r)"
    echo "cpu:       $(lscpu | sed -n 's/^Model name: *//p')"
    echo "online:    $(nproc) CPUs"
    echo "root:      $IS_ROOT"
    echo "resctrl:   $([ $RESCTRL = 1 ] && echo "L3_MON mounted" || echo absent)"
    echo "stress-ng: $(stress-ng --version 2>/dev/null || echo absent)"
} >"$LOGDIR/ENV.txt"

# Binaries: fixed v2.1, pre-fix v2.1 (v0.2.0), v3.3.
make -C "$V21_DIR" -s >"$LOGDIR/build.log" 2>&1 || { record build FAIL "see build.log"; exit 1; }
OLD_BIN=${INTP_OLD_BIN:-}
if [ -z "$OLD_BIN" ]; then
    OLD_SRC=$(mktemp -d /tmp/intp-c38-prefix-XXXXXX)
    "${GIT[@]}" archive v0.2.0 variants/v2.1-c-abi-cgroup | tar x -C "$OLD_SRC"
    if make -C "$OLD_SRC/variants/v2.1-c-abi-cgroup" -s \
            CFLAGS="-std=c99 -Wall -O2 -D_GNU_SOURCE -Iinclude -Isrc" >>"$LOGDIR/build.log" 2>&1; then
        OLD_BIN=$OLD_SRC/variants/v2.1-c-abi-cgroup/intp-c-abi-cgroup
    else
        record build-old FAIL "pre-fix v0.2.0 binary did not build, see build.log"; rc_all=1
    fi
fi
V33_BIN=${INTP_V33_BIN:-$REPO/variants/v3.3-ebpf-core-cgroup/intp-ebpf-core-cgroup}
[ -x "$V33_BIN" ] || make -C "$REPO/variants/v3.3-ebpf-core-cgroup" -s >>"$LOGDIR/build.log" 2>&1
[ -x "$V33_BIN" ] || V33_BIN=
echo "old v2.1:  ${OLD_BIN:-none} (built from v0.2.0)" >>"$LOGDIR/ENV.txt"
echo "v3.3:      ${V33_BIN:+${V33_BIN#"$REPO"/}}" >>"$LOGDIR/ENV.txt"

run_test unit make run-tests

# T1: the agreement leg reads v3.3 through BPF, so it needs root.
if [ $IS_ROOT = 1 ] && [ -n "$V33_BIN" ]; then
    run_test T1 env INTP_OLD_BIN="$OLD_BIN" INTP_V33_BIN="$V33_BIN" tests/t1-multithreaded-target.sh
else
    run_test T1 env INTP_OLD_BIN="$OLD_BIN" tests/t1-multithreaded-target.sh
    record T1-v33 SKIPPED "$([ $IS_ROOT = 1 ] && echo "no v3.3 binary" || echo "needs root")"
fi

if [ $IS_ROOT = 1 ] && [ -n "$V33_BIN" ]; then
    run_test T2 env INTP_V33_BIN="$V33_BIN" tests/t2-thread-churn.sh
else
    run_test T2 tests/t2-thread-churn.sh
fi

# T3: resctrl monitoring, root and stress-ng; old binary first (exit 3 = F2
# is not the cause, see the script header).
if [ $IS_ROOT = 1 ] && [ $RESCTRL = 1 ] && command -v stress-ng >/dev/null; then
    run_test T3 env INTP_OLD_BIN="$OLD_BIN" INTP_V33_BIN="$V33_BIN" tests/t3-nested-slice.sh
else
    why=()
    [ $IS_ROOT = 1 ] || why+=("needs root")
    [ $RESCTRL = 1 ] || why+=("no resctrl L3 monitoring on this CPU/kernel")
    command -v stress-ng >/dev/null || why+=("stress-ng not installed")
    record T3 SKIPPED "$(IFS=';'; echo "${why[*]}")"
fi

[ -n "${SUDO_UID:-}" ] && chown -R "$SUDO_UID:${SUDO_GID:-$SUDO_UID}" "$LOGDIR"
echo "logs: $LOGDIR" >&2
exit $rc_all

# lib-portable.sh -- shared helpers for the C38 integration tests (T1-T3).
# Sourced, not executed.

TESTS_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
V21_DIR=$(cd "$TESTS_DIR/.." && pwd)
NEW_BIN=${INTP_BIN:-$V21_DIR/intp-c-abi-cgroup}
OLD_BIN=${INTP_OLD_BIN:-}          # optional: pre-fix v2.1 binary (regression check)
V33_BIN=${INTP_V33_BIN:-}          # optional: v3.3 binary (agreement check, root)
MT_SPIN=$TESTS_DIR/helpers/mt_spin
WORK=$(mktemp -d /tmp/intp-c38-XXXXXX)

fail() { echo "FAIL: $*" >&2; exit 1; }
note() { echo "--- $*"; }

build_helper() {
    [ -x "$MT_SPIN" ] && [ "$MT_SPIN" -nt "$MT_SPIN.c" ] && return 0
    ${CC:-gcc} -O2 -Wall -Wextra -o "$MT_SPIN" "$TESTS_DIR/helpers/mt_spin.c" -lpthread \
        || fail "cannot build mt_spin"
}

# Run a profiler: run_intp BIN OUT.tsv SECONDS TARGET-ARGS...
run_intp() {
    local bin=$1 out=$2 secs=$3; shift 3
    "$bin" "$@" --interval 1 --duration "$secs" --output tsv >"$out" 2>"$out.err" \
        || fail "$bin exited non-zero (see $out.err)"
}

# Column values of a profiler TSV, one per line ("--" -> "nan"):
#   tsv_col FILE COLUMN
tsv_col() {
    python3 - "$1" "$2" <<'EOF'
import sys
path, col = sys.argv[1], sys.argv[2]
hdr = None
for line in open(path):
    if line.startswith('#') or not line.strip():
        continue
    f = line.rstrip('\n').split('\t')
    if hdr is None:
        hdr = f
        if col not in hdr:
            sys.exit(f"column {col} not in {path}")
        continue
    v = f[hdr.index(col)]
    print('nan' if v == '--' else v)
EOF
}

# Median of a column, ignoring the first sample (warm-up): tsv_median FILE COL
tsv_median() {
    tsv_col "$1" "$2" | tail -n +2 | python3 -c '
import sys, math, statistics
v = [float(x) for x in sys.stdin if not math.isnan(float(x))]
print(statistics.median(v) if v else "nan")'
}

# gt A B -> exit 0 when A > B (floats, nan is never greater)
gt() { python3 -c "import sys,math; a,b=float('$1'),float('$2'); sys.exit(0 if not math.isnan(a) and a>b else 1)"; }

# ratio_in A B LO HI -> exit 0 when LO <= A/B <= HI
ratio_in() {
    python3 -c "
import sys, math
a, b, lo, hi = map(float, ('$1', '$2', '$3', '$4'))
r = a / b if b > 0 else float('nan')
print(f'ratio={r:.3f}')
sys.exit(0 if not math.isnan(r) and lo <= r <= hi else 1)"
}

# Place a command in its own cgroup; prints "PID CGROUP_DIR".
#   root: a fresh cgroup under /sys/fs/cgroup/intp-c38/<name>
#   user: a delegated systemd --user scope (no root needed for /proc metrics)
spawn_in_cgroup() {
    local name=$1; shift
    local pid cg
    if [ "$(id -u)" = 0 ]; then
        cg=/sys/fs/cgroup/intp-c38/$name
        mkdir -p "$cg"
        sh -c 'echo $$ > "$0/cgroup.procs"; shift; exec "$@"' "$cg" _ "$@" &
        pid=$!
    else
        systemd-run --user --scope --quiet --unit="intp-c38-$name-$$" "$@" &
        pid=$!
        sleep 0.5
        # systemd-run execs the command in place, so $! is the workload.
    fi
    echo "$pid" >>"$WORK/spawned"   # killed by finish(); we run in a subshell
    sleep 0.5
    cg=/sys/fs/cgroup$(sed -n 's/^0:://p' "/proc/$pid/cgroup")
    echo "$pid $cg"
}

cleanup_cgroups() {
    [ "$(id -u)" = 0 ] || return 0
    [ -d /sys/fs/cgroup/intp-c38 ] || return 0
    find /sys/fs/cgroup/intp-c38 -depth -type d -exec rmdir {} \; 2>/dev/null || true
}

finish() {
    local rc=$?
    set +e
    jobs -p | xargs -r kill 2>/dev/null
    [ -f "$WORK/spawned" ] && xargs -r kill <"$WORK/spawned" 2>/dev/null
    wait 2>/dev/null
    cleanup_cgroups
    if [ $rc = 0 ]; then rm -rf "$WORK"; else echo "outputs kept in $WORK" >&2; fi
    exit $rc
}
trap finish EXIT

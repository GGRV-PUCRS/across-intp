#!/bin/bash
# test-metrics-equivalence.sh -- V2.1 vs V3.3 head-to-head numeric check.
#
# Runs both profilers back-to-back over the same workload (stress-ng
# --vm 4 --vm-bytes 1G, 30s) and verifies the per-cgroup metrics agree.
#
# WHAT IS GATED (must agree within tolerance):
#   cpu, blk, llcmr        -- the per-cgroup cross-check the paper relies on.
#   netp, mbw, llcocc      -- also compared and gated (canonical, see notes).
#
# WHAT IS EXEMPT (reported but NOT gating):
#   nets  -- DIVERGENT BY DESIGN (C2). V3.3's per-cgroup nets is a byte-share
#            PROXY: nets_sys * bytes(cgroup) / bytes_total. V2.1's nets is the
#            system-wide softirq fraction. The two are NOT expected to match;
#            the trailing diagnostic nets_sys column (suppressed here by
#            --no-diag-cols) is what would carry the v2.1-comparable value.
#
# NOTES ON THE COMPARED METRICS:
#   netp  -- we compare the CANONICAL per-cgroup netp column (column 1), i.e.
#            the container/cgroup-scoped value, NOT the trailing netp_dev
#            diagnostic (device-level host-wide netp, the v3.2 cross-check).
#            netp_dev is suppressed here by --no-diag-cols.
#   cpu/blk/llcmr -- the load-bearing per-cgroup agreement check.
#
# Each metric agrees within ABS_TOL absolute percentage points when both
# medians are below NEAR_ZERO, OR within REL_TOL fractional tolerance when
# above.
#
# This is a smoke check, not a measurement: the two profilers see slightly
# different sample windows and probe sites, so we accept 15% by default.
# The cross-variant statistical validation lives in
# shared/validate-cross-variant.sh.

set -eu

# Sibling variant under variants/; this test is run with CWD = the v3.3
# variant root (where ./intp-ebpf-core-cgroup sits), so the sibling is one level up.
V21_BIN=${V21_BIN:-../v2.1-c-abi-cgroup/intp-c-abi-cgroup}
V33_BIN=${V33_BIN:-./intp-ebpf-core-cgroup}
DUR=${DUR:-30}
REL_TOL=${REL_TOL:-0.15}    # 15% fractional tolerance
ABS_TOL=${ABS_TOL:-5}       # 5 percentage points when median is near zero
NEAR_ZERO=${NEAR_ZERO:-2}   # below this, switch from REL to ABS tolerance

# nets is divergent by design (C2); list any other expected-divergent metric
# here to exempt it from the pass/fail gate while still reporting it.
EXEMPT_METRICS=${EXEMPT_METRICS:-nets}

if [ ! -x "$V33_BIN" ]; then
    echo "ERROR: $V33_BIN not built"
    exit 1
fi
if [ ! -x "$V21_BIN" ]; then
    echo "SKIP: $V21_BIN not built (run 'make' in variants/v2.1-c-abi-cgroup first)"
    exit 77
fi
if [ "$(id -u)" -ne 0 ]; then
    echo "ERROR: must run as root"
    exit 1
fi
if ! command -v stress-ng >/dev/null 2>&1; then
    echo "SKIP: stress-ng not installed"
    exit 77
fi

V21_OUT=$(mktemp)
V33_OUT=$(mktemp)
STRESS_LOG=$(mktemp)
trap 'rm -f "$V21_OUT" "$V33_OUT" "$STRESS_LOG"' EXIT

# run_once LABEL BIN OUT EXTRA_ARGS...
#   V3.3 takes --no-resctrl and --no-diag-cols (C13: keep the captured TSV to
#   leading-ts + the 7 canonical columns, mirroring how v3.2 is run with
#   --no-raw-mbw). V2.1 (intp-c-abi) supports neither flag and has no
#   diagnostic columns, so it is invoked with the canonical flags only.
run_once() {
    local label="$1"; local bin="$2"; local out="$3"; shift 3
    echo "[$label] starting stress-ng --vm 4 --vm-bytes 1G --timeout $((DUR+10))s"
    stress-ng --vm 4 --vm-bytes 1G --timeout $((DUR + 10))s \
        > "$STRESS_LOG" 2>&1 &
    local sp=$!
    sleep 3
    echo "[$label] profiling $bin for ${DUR}s"
    timeout $((DUR + 5)) "$bin" --interval 1 --duration "$DUR" "$@" \
        > "$out" 2>/dev/null || true
    kill "$sp" 2>/dev/null || true
    wait "$sp" 2>/dev/null || true
    sleep 2
}

run_once "V2.1" "$V21_BIN" "$V21_OUT"
run_once "V3.3" "$V33_BIN" "$V33_OUT" --no-resctrl --no-diag-cols

# Awk-based median across the 7 canonical columns.
medians() {
    # Skip header lines starting with # and the column-header line.
    awk -F'\t' '
        /^#/      { next }
        /^[a-z]/  { next }      # column header
        NF >= 7   {
            for (i = 1; i <= 7; i++) v[i, n[i]++] = $i + 0
        }
        END {
            for (i = 1; i <= 7; i++) {
                m = n[i]
                if (m == 0) { printf "0"; if (i<7) printf "\t"; continue }
                # crude sort + middle
                for (a = 0; a < m; a++)
                    for (b = a+1; b < m; b++)
                        if (v[i,b] < v[i,a]) {
                            t = v[i,a]; v[i,a] = v[i,b]; v[i,b] = t
                        }
                printf "%.2f", (m % 2 == 1) ? v[i, int(m/2)]
                                            : (v[i, m/2 - 1] + v[i, m/2]) / 2.0
                if (i < 7) printf "\t"
            }
            print ""
        }
    ' "$1"
}

V21_MED=$(medians "$V21_OUT")
V33_MED=$(medians "$V33_OUT")

echo
echo "metric   V2.1     V3.3     |diff|   tol"
printf "header   netp nets blk mbw llcmr llcocc cpu\n"
echo "V2.1     $V21_MED"
echo "V3.3     $V33_MED"

names=(netp nets blk mbw llcmr llcocc cpu)
fail=0
for i in 1 2 3 4 5 6 7; do
    v21=$(echo "$V21_MED" | cut -f"$i")
    v33=$(echo "$V33_MED" | cut -f"$i")
    name="${names[i-1]}"

    # Expected-divergent metrics (C2: nets) are reported but never gate.
    case " $EXEMPT_METRICS " in
        *" $name "*)
            echo "  $name $v21 vs $v33  -- EXEMPT (divergent by design, C2)"
            continue
            ;;
    esac

    pass=$(awk -v a="$v21" -v b="$v33" -v rt="$REL_TOL" -v at="$ABS_TOL" -v nz="$NEAR_ZERO" \
           'BEGIN {
                d = (a > b) ? a - b : b - a;
                max = (a > b) ? a : b;
                # near-zero: use abs tolerance
                if (max < nz) { print (d <= at) ? "ok" : "fail" }
                # otherwise: relative tolerance
                else { print (d / max <= rt) ? "ok" : "fail" }
            }')
    if [ "$pass" = "ok" ]; then
        echo "  $name $v21 vs $v33  -- ok"
    else
        echo "  $name $v21 vs $v33  -- FAIL"
        fail=1
    fi
done

if [ $fail -ne 0 ]; then
    echo
    echo "FAIL: V2.1 / V3.3 medians diverge beyond tolerance on at least one"
    echo "      GATED metric (nets is exempt by design, C2)"
    exit 1
fi
echo
echo "PASS: V2.1 and V3.3 medians agree within tolerance on all gated metrics"
echo "      (nets exempt: V3.3 per-cgroup nets is a byte-share PROXY, C2)"

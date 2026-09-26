#!/usr/bin/env bash
# Self-test for validate-attribution.sh parse + assertion logic. Sources the
# (guarded) harness and feeds synthetic v2.1 JSON output -- no root/lxd needed.
# Run: bench/test-validate-attribution.sh
set -uo pipefail
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
HARNESS="$SCRIPT_DIR/validate-attribution.sh"
# shellcheck disable=SC1090
source "$HARNESS"

command -v jq >/dev/null 2>&1 || { echo "SKIP: jq not installed"; exit 0; }

WORKDIR=$(mktemp -d -t intp-vtest.XXXXXX)
trap 'rm -rf "$WORKDIR"' EXIT
WARMUP=2; IDLE_MAX=5; RATIO_MIN=8; CONSERVE_TOL=0.25; EQ_TOL=0.20; DRY_RUN=0

T_PASS=0; T_FAIL=0
ok()   { printf '  ok   %s\n' "$1"; T_PASS=$((T_PASS+1)); }
bad()  { printf '  FAIL %s\n' "$1"; T_FAIL=$((T_FAIL+1)); }
check(){ [ "$2" = "$3" ] && ok "$1 (=$3)" || bad "$1 (want $3, got $2)"; }

# One JSON sample line. Pass numeric values, or the literal token null.
jline() { # t netp nets blk mbw llcmr llcocc cpu
  printf '{"t":%s,"netp":{"v":%s,"status":"ok","backend":"cgroup"},"nets":{"v":%s,"status":"ok","backend":"procfs"},"blk":{"v":%s,"status":"ok","backend":"io_stat"},"mbw":{"v":%s,"status":"ok","backend":"resctrl"},"llcmr":{"v":%s,"status":"ok","backend":"perf"},"llcocc":{"v":%s,"status":"ok","backend":"resctrl"},"cpu":{"v":%s,"status":"ok","backend":"cpu_stat"}}\n' "$@"
}

# 2 warmup lines (value 0) then 4 steady lines at the target values.
mkfile() { # FILE netp nets blk mbw llcmr llcocc cpu
  local f="$1"; shift
  : > "$f"
  jline 0.0 0 0 0 0 0 0 0 >> "$f"
  jline 1.0 0 0 0 0 0 0 0 >> "$f"
  local k; for k in 2 3 4 5; do jline "$k.0" "$@" >> "$f"; done
}

H="$WORKDIR/h.json" I="$WORKDIR/i.json" Tt="$WORKDIR/t.json" N="$WORKDIR/null.json"
#       netp nets blk mbw llcmr llcocc cpu
mkfile "$H"  12 3  50 40 30 25 80
mkfile "$I"  12 3   0  1  1  1  2
mkfile "$Tt" 12 3  50 41 31 26 82
# null-mbw file: metric unavailable on this host.
: > "$N"; jline 0 0 0 0 0 0 0 0 >> "$N"; jline 1 0 0 0 0 0 0 0 >> "$N"
k=2; while [ $k -le 5 ]; do jline "$k" 12 3 50 null 30 25 80 >> "$N"; k=$((k+1)); done

echo "== mean_metric (WARMUP skip + null drop) =="
check "mean cpu heavy"        "$(mean_metric "$H" cpu)"      "80"
check "mean blk idle"         "$(mean_metric "$I" blk)"      "0"
check "mean netp total"       "$(mean_metric "$Tt" netp)"    "12"
check "mean mbw null->na"     "$(mean_metric "$N" mbw)"      "na"
check "mean cpu null-file ok" "$(mean_metric "$N" cpu)"      "80"
check "mean missing file na"  "$(mean_metric "$WORKDIR/nope.json" cpu)" "na"

echo "== backend_of =="
check "backend netp"          "$(backend_of "$H" netp)"      "cgroup"
check "backend mbw"           "$(backend_of "$H" mbw)"       "resctrl"

# Helper: read the RESULT token (5th |-field) of the last recorded row.
last() { echo "${RESULTS[-1]##*|}"; }

echo "== separable-metric assertions (intra/inter shape) =="
RESULTS=(); N_FAIL=0
assert_track_and_ratio x cpu 80 2 ; check "track cpu 80vs2"      "$(last)" "PASS"
assert_track_and_ratio x cpu 80 20; check "track cpu 80vs20(r=4)" "$(last)" "FAIL"
assert_track_and_ratio x blk 50 0 ; check "track blk 50vs0"      "$(last)" "PASS"
assert_track_and_ratio x mbw na 1 ; check "track mbw na->skip"   "$(last)" "SKIP"
assert_track_and_ratio x cpu 3 1  ; check "track cpu below floor" "$(last)" "FAIL"

assert_idle x cpu 2  ; check "idle cpu 2<=5"      "$(last)" "PASS"
assert_idle x cpu 10 ; check "idle cpu 10>5"      "$(last)" "FAIL"
assert_idle x mbw na ; check "idle mbw na->skip"  "$(last)" "SKIP"

assert_conserve x cpu 82 80 2  ; check "conserve exact"        "$(last)" "PASS"
assert_conserve x cpu 100 80 2 ; check "conserve 18% in tol"   "$(last)" "PASS"
assert_conserve x cpu 200 80 2 ; check "conserve 59% out tol"  "$(last)" "FAIL"
assert_conserve x mbw na 40 1  ; check "conserve total na"     "$(last)" "SKIP"
assert_conserve x cpu 0 0 0    ; check "conserve both ~0"      "$(last)" "SKIP"

echo "== intra netp/nets limit (must be LIMIT[v3.3], not a false PASS/FAIL) =="
RESULTS=(); N_FAIL=0
assert_unsplittable netp 12 12   ; check "netp equal->LIMIT"      "$(last)" "LIMIT[v3.3]"
assert_unsplittable nets 3 3     ; check "nets equal->LIMIT"      "$(last)" "LIMIT[v3.3]"
assert_unsplittable netp 50 10   ; check "netp differ->FAIL"      "$(last)" "FAIL"
assert_unsplittable netp na na   ; check "netp na->SKIP[v3.3]"    "$(last)" "SKIP[v3.3]"
assert_unsplittable netp 0 0     ; check "netp both0->SKIP[v3.3]" "$(last)" "SKIP[v3.3]"

echo "== N_FAIL bookkeeping =="
RESULTS=(); N_FAIL=0
assert_idle x cpu 10   # one FAIL
assert_idle x cpu 2    # one PASS
check "N_FAIL counts 1 fail" "$N_FAIL" "1"

echo
printf 'TEST TOTAL: %d ok, %d FAIL\n' "$T_PASS" "$T_FAIL"
[ "$T_FAIL" -eq 0 ]

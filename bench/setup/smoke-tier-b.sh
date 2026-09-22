#!/usr/bin/env bash
#
# smoke-tier-b.sh -- small/fast pre-flight for the Tier-B suite stack, run on the
# host AFTER staging (setup-cloudsuite-workload.sh + setup-redis-workload.sh) and
# BEFORE the full Tier-B campaign. It drives the REAL harness path
# (run-intp-bench.sh -> launch_redis_workload / launch_compose_workload) for one
# short rep per suite and asserts the profiler actually sampled the workload
# (portable.tsv.samples > 0 and a non-all-zero row). A failure here means a suite
# did not come up / the profiler never attached -- catch it in minutes, not after
# committing ~1.5 days of campaign.
#
# Fast by default: container env, v3.3, 1 rep, 45 s, and the INDEX-FREE suites
# (redis + data-caching + in-memory-analytics). web-search needs the 14 GB Solr
# index (minutes to load) so it is opt-in via --with-websearch.
#
#   cd <repo-root> && bash bench/setup/smoke-tier-b.sh
#       [--with-websearch] [--env container] [--variant v3.3] [--duration 45]
#
# Run from the repo root (uses ./bench/run-intp-bench.sh). Exit 0 = PASS.
set -uo pipefail

ENVN="container"; VAR="v3.3"; DUR="45"; WITH_WS=0
while [ $# -gt 0 ]; do
    case "$1" in
        --with-websearch) WITH_WS=1 ;;
        --env)            ENVN="$2"; shift ;;
        --variant)        VAR="$2"; shift ;;
        --duration)       DUR="$2"; shift ;;
        -h|--help)        sed -n '2,20p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "unknown flag: $1" >&2; exit 2 ;;
    esac
    shift
done

[ -x ./bench/run-intp-bench.sh ] || { echo "FATAL: run from the repo root (./bench/run-intp-bench.sh not found)" >&2; exit 2; }

WL="app18_redis_kv,app19_cs_datacaching,app21_cs_imanalytics"
[ "$WITH_WS" = 1 ] && WL="$WL,app20_cs_websearch"

OUT="$(mktemp -d /tmp/tierb-smoke.XXXXXX)"
echo "[smoke-tier-b] env=$ENVN variant=$VAR dur=${DUR}s reps=1 workloads=$WL"
echo "[smoke-tier-b] throwaway output: $OUT  (NOT a campaign dir)"

./bench/run-intp-bench.sh --portable-metrics --variants "$VAR" --env "$ENVN" \
    --stages solo --workloads "$WL" --reps 1 --duration "$DUR" \
    --output-dir "$OUT" 2>&1 | tail -40

echo "[smoke-tier-b] === results ==="
rc=0
IFS=',' read -r -a WLS <<< "$WL"
for w in "${WLS[@]}"; do
    cell="$OUT/$ENVN/$VAR/solo/$w/rep1"
    samp="$cell/portable.tsv.samples"
    tsv="$cell/portable.tsv"
    n="$(cat "$samp" 2>/dev/null || echo 0)"
    nz="no"
    # a non-all-zero data row (past the header) = the profiler saw real activity
    if [ -f "$tsv" ] && tail -n +2 "$tsv" 2>/dev/null | grep -qvP '^0(\t0)+$'; then nz="yes"; fi
    if [ "${n:-0}" -gt 0 ] 2>/dev/null && [ "$nz" = "yes" ]; then
        echo "  PASS  $w  (samples=$n, nonzero row=yes)"
    else
        echo "  FAIL  $w  (samples=${n:-0}, nonzero row=$nz, cell=$cell)"
        rc=1
    fi
done

if [ "$rc" = 0 ]; then
    echo "[smoke-tier-b] PASS -- suites came up and the profiler sampled them. Safe to launch the full Tier-B campaign."
    rm -rf "$OUT"
else
    echo "[smoke-tier-b] FAIL -- a suite did not validate. Inspect $OUT and the .setup.log files; do NOT launch the full campaign yet." >&2
fi
exit "$rc"

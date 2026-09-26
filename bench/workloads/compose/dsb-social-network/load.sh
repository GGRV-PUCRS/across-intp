#!/bin/bash
# Host-side load for DSB social-network: seed the social graph (fresh DBs every
# rep — the harness tears down with `down -v`), then loop wrk2 with the chosen
# lua profile until the run window ends. Pinned to the host third (CPUSET_LOAD)
# so the client never pollutes the profiled fingerprint.
#
# Env from the harness: PROJECT SUITE_DIR DURATION CPUSET_LOAD LOAD_PROFILE
# LOAD_EXTRA NETWORK. wrk2 + the clone are provisioned by
# bench/setup/setup-dsb-workload.sh.
set -u
DSB="${INTP_DSB_ROOT:-/opt/DeathStarBench}"
SN="$DSB/socialNetwork"
WRK="$DSB/wrk2/wrk"
LUA="$SN/wrk2/scripts/social-network/${LOAD_PROFILE:-mixed-workload}.lua"
GRAPH="${DSB_GRAPH:-socfb-Reed98}"

[ -x "$WRK" ] || { echo "wrk2 missing at $WRK (run bench/setup/setup-dsb-workload.sh)"; exit 1; }
[ -f "$LUA" ] || { echo "lua profile missing: $LUA"; exit 1; }

PIN=()
[ -n "${CPUSET_LOAD:-}" ] && PIN=(taskset -c "$CPUSET_LOAD")

# wrk2's vendored LuaJIT does not search the Debian multiarch lua-5.1 dirs
# where apt's lua-socket lands (mixed-workload.lua requires "socket").
export LUA_PATH="/usr/share/lua/5.1/?.lua;/usr/share/lua/5.1/?/init.lua;;"
export LUA_CPATH="/usr/lib/x86_64-linux-gnu/lua/5.1/?.so;/usr/lib/lua/5.1/?.so;;"

wrk_pid=""
_cleanup() { [ -n "$wrk_pid" ] && kill "$wrk_pid" 2>/dev/null; exit 0; }
trap _cleanup TERM INT

# Graph init (idempotent against an empty stack; retry while services settle).
ok=0
for _ in 1 2 3 4 5 6 7 8 9 10; do
    if ( cd "$SN" && "${PIN[@]}" python3 scripts/init_social_graph.py --graph="$GRAPH" ); then
        ok=1; break
    fi
    sleep 5
done
[ "$ok" = 1 ] || echo "WARN: social-graph init failed; wrk2 will drive an unseeded app"

# Continuous wrk2 in bounded chunks (background + wait so TERM reaps it).
EXTRA="${LOAD_EXTRA:--t 4 -c 64 -R 500}"
while true; do
    # shellcheck disable=SC2086
    "${PIN[@]}" "$WRK" -D exp $EXTRA -d 60 -L -s "$LUA" "http://127.0.0.1:8080" &
    wrk_pid=$!
    wait "$wrk_pid" || sleep 2
done

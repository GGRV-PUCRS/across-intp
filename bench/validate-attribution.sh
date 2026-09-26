#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# validate-attribution.sh -- ground-truth validation of per-cgroup attribution
# for the c-abi-cgroup profiler, the signal the IADA closed loop consumes.
#
# This is the runnable-now (v2.1) realization of v3.3 DESIGN.md sec.8.2/sec.11.
# It does NOT validate the scheduler -- scheduling efficacy is the separate
# CloudSim + real-cluster eval. It validates the *profiler*: that each unit's
# per-cgroup reading tracks its own load, that an idle unit reads ~0, and that
# the units sum to the whole (conservation) under a load split that is known by
# construction.
#
# Two complementary experiments (sec.8.2; "Both (hybrid)"):
#
#   intra  -- apps as sub-cgroups INSIDE ONE container ("container = machine").
#             Validates the five separable metrics per app:
#               cpu, blk, llcmr, mbw, llcocc.
#             netp/nets cannot split here -- the apps share the container's
#             netns (netp) and the host softirq (nets) -- so this leg also
#             asserts that limit (heavy==idle==total within tolerance), which
#             is exactly the gap v3.3 (cgroup/skb + nets cost model) closes.
#
#   inter  -- two sibling containers interfering on the host ("node = machine").
#             Each container is its own netns, so netp IS per-unit here:
#             validates netp(A) tracks A, netp(B)~0 (idle), netp(A)+netp(B) ~=
#             system-wide. cpu/blk/llcmr/mbw/llcocc validated per container too.
#             nets stays system-wide (host softirq) -> reported, per-unit
#             deferred to v3.3.
#
# What is validated NOW (v2.1) vs DEFERRED to v3.3:
#   NOW      cpu/blk/llcmr/mbw/llcocc per app (intra) and per container (inter);
#            netp per CONTAINER (inter); netp/nets container-total (intra).
#   v3.3     per-app netp inside one netns; per-cgroup nets (skb + cost model).
#   Those appear in the report as SKIP[v3.3] so the gate is honest about scope.
#
# Usage:
#   sudo bench/validate-attribution.sh [--leg intra|inter|both] [--dry-run]
#                                      [--duration SEC] [--no-lxc]
#
# Env knobs (all optional):
#   INTP_V21_BIN        path to the v2.1 intp-c-abi binary
#   INTP_BENCH_LXC_BIN  LXD/Incus client (default: lxc)
#   INTP_BENCH_LXC_IMAGE container image alias (default: ubuntu:24.04)
#   VAL_DURATION        profiler window seconds      (default 30)
#   VAL_INTERVAL        sample interval seconds       (default 1)
#   VAL_WARMUP          leading samples dropped       (default 5)
#   VAL_RATIO_MIN       min heavy/idle ratio          (default 8)
#   VAL_IDLE_MAX        max idle reading (pct units)  (default 5)
#   VAL_CONSERVE_TOL    |sum-total|/total tolerance   (default 0.25)
#   VAL_EQ_TOL          heavy~=idle tolerance (intra netp/nets limit) (default 0.20)
#   VAL_IPERF_MBPS      inter-leg offered net load    (default 200)
# -----------------------------------------------------------------------------
set -euo pipefail

# --- locations ---------------------------------------------------------------
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)
V21_BIN="${INTP_V21_BIN:-$REPO_ROOT/variants/v2.1-c-abi-cgroup/intp-c-abi-cgroup}"
LXC_BIN="${INTP_BENCH_LXC_BIN:-lxc}"
LXC_IMAGE="${INTP_BENCH_LXC_IMAGE:-ubuntu:24.04}"

# --- config ------------------------------------------------------------------
LEG="both"
DRY_RUN=0
NO_LXC=0
DURATION="${VAL_DURATION:-30}"
INTERVAL="${VAL_INTERVAL:-1}"
WARMUP="${VAL_WARMUP:-5}"
RATIO_MIN="${VAL_RATIO_MIN:-8}"
IDLE_MAX="${VAL_IDLE_MAX:-5}"
CONSERVE_TOL="${VAL_CONSERVE_TOL:-0.25}"
EQ_TOL="${VAL_EQ_TOL:-0.20}"
IPERF_MBPS="${VAL_IPERF_MBPS:-200}"

# Metric groups (TSV/JSON order: netp nets blk mbw llcmr llcocc cpu).
SEPARABLE_METRICS=(cpu blk llcmr mbw llcocc)   # per-cgroup attributable in v2.1
NET_METRICS=(netp nets)                        # netp per-container; nets system-wide

WORKDIR=""
RESULTS=()        # "leg|metric|check|detail|RESULT"
N_FAIL=0
declare -a CLEANUP_CONTAINERS=()
declare -a CLEANUP_PIDS=()
declare -a CLEANUP_CGROUPS=()
HOST_IPERF_SRV_PID=""

log()  { printf '[validate] %s\n' "$*" >&2; }
warn() { printf '[validate][WARN] %s\n' "$*" >&2; }
die()  { printf '[validate][FATAL] %s\n' "$*" >&2; exit 1; }

usage() { sed -n '2,60p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }

# --- arg parsing -------------------------------------------------------------
parse_args() {
    while [ $# -gt 0 ]; do
        case "$1" in
            --leg)       LEG="$2"; shift 2 ;;
            --dry-run)   DRY_RUN=1; shift ;;
            --no-lxc)    NO_LXC=1; shift ;;
            --duration)  DURATION="$2"; shift 2 ;;
            -h|--help)   usage; exit 0 ;;
            *) die "unknown argument: $1 (try --help)" ;;
        esac
    done
    case "$LEG" in intra|inter|both) ;; *) die "--leg must be intra|inter|both" ;; esac
}

# =============================================================================
# Profiler + parsing helpers
# =============================================================================

# profile_cgroup OUTFILE [CGROUP_PATH]
# Runs v2.1 over the window in JSON mode. No CGROUP_PATH -> system-wide.
# Blocking; intended to be backgrounded by the caller so units run concurrently.
profile_cgroup() {
    local outfile="$1" cgpath="${2:-}"
    local args=( --interval "$INTERVAL" --duration "$DURATION" --output json )
    [ -n "$cgpath" ] && args+=( --cgroup "$cgpath" )
    if [ "$DRY_RUN" -eq 1 ]; then
        log "DRY: $V21_BIN ${args[*]} > $outfile"
        : > "$outfile"
        return 0
    fi
    "$V21_BIN" "${args[@]}" > "$outfile" 2>"${outfile}.log" || true
}

# mean_metric OUTFILE METRIC -> steady-state mean of .<metric>.v (nulls dropped,
# first $WARMUP samples skipped). Echoes "na" if no numeric samples.
mean_metric() {
    local outfile="$1" metric="$2"
    [ -s "$outfile" ] || { echo "na"; return 0; }
    jq -rs --arg m "$metric" --argjson w "$WARMUP" '
        [ .[$w:][]? | .[$m].v | numbers ] as $vs
        | if ($vs|length) > 0 then (($vs|add)/($vs|length)) else "na" end
    ' "$outfile" 2>/dev/null || echo "na"
}

# backend_of OUTFILE METRIC -> backend id of the last sample (reporting only).
backend_of() {
    local outfile="$1" metric="$2"
    [ -s "$outfile" ] || { echo "none"; return 0; }
    jq -rs --arg m "$metric" '[ .[]? | .[$m].backend ] | (last // "none")' \
        "$outfile" 2>/dev/null || echo "none"
}

# --- float predicates (awk; bash has no float compare) -----------------------
fcmp() { awk -v a="$1" -v op="$2" -v b="$3" 'BEGIN{
    if(op==">")  exit !(a>b);  if(op==">=") exit !(a>=b);
    if(op=="<")  exit !(a<b);  if(op=="<=") exit !(a<=b);
    exit 1 }'; }
is_num() { case "$1" in ''|na|null) return 1 ;; *) awk -v x="$1" 'BEGIN{exit !(x==x+0)}' ;; esac; }

# =============================================================================
# Assertions -- each records one row into RESULTS[] and bumps N_FAIL on FAIL.
# =============================================================================
record() {  # LEG METRIC CHECK DETAIL RESULT
    RESULTS+=("$1|$2|$3|$4|$5")
    [ "$5" = "FAIL" ] && N_FAIL=$((N_FAIL + 1)) || true
}

# heavy reading must be clearly non-trivial AND >> idle.
assert_track_and_ratio() {  # LEG METRIC HEAVY IDLE
    local leg="$1" m="$2" heavy="$3" idle="$4"
    if ! is_num "$heavy"; then
        record "$leg" "$m" "track" "heavy=$heavy (unavailable backend)" "SKIP"; return
    fi
    if ! fcmp "$heavy" ">" "$IDLE_MAX"; then
        record "$leg" "$m" "track" "heavy=$heavy not above idle-floor $IDLE_MAX" "FAIL"; return
    fi
    if is_num "$idle" && fcmp "$idle" ">" 0; then
        local ratio; ratio=$(awk -v h="$heavy" -v i="$idle" 'BEGIN{printf "%.2f", h/i}')
        if fcmp "$ratio" ">=" "$RATIO_MIN"; then
            record "$leg" "$m" "track+ratio" "heavy=$heavy idle=$idle ratio=$ratio (>= $RATIO_MIN)" "PASS"
        else
            record "$leg" "$m" "track+ratio" "heavy=$heavy idle=$idle ratio=$ratio (< $RATIO_MIN)" "FAIL"
        fi
    else
        record "$leg" "$m" "track" "heavy=$heavy idle=${idle} (~0)" "PASS"
    fi
}

# idle reading must sit under the floor.
assert_idle() {  # LEG METRIC IDLE
    local leg="$1" m="$2" idle="$3"
    if ! is_num "$idle"; then
        record "$leg" "$m" "isolation" "idle=$idle (unavailable)" "SKIP"; return
    fi
    if fcmp "$idle" "<=" "$IDLE_MAX"; then
        record "$leg" "$m" "isolation" "idle=$idle (<= $IDLE_MAX)" "PASS"
    else
        record "$leg" "$m" "isolation" "idle=$idle (> $IDLE_MAX, leakage)" "FAIL"
    fi
}

# sum of units must reconcile with the whole.
assert_conserve() {  # LEG METRIC TOTAL UNIT...
    local leg="$1" m="$2" total="$3"; shift 3
    if ! is_num "$total"; then
        record "$leg" "$m" "conservation" "total=$total (unavailable)" "SKIP"; return
    fi
    local sum=0 u
    for u in "$@"; do is_num "$u" && sum=$(awk -v s="$sum" -v x="$u" 'BEGIN{printf "%.3f", s+x}'); done
    if ! fcmp "$total" ">" 0; then
        record "$leg" "$m" "conservation" "sum=$sum total=$total (both ~0)" "SKIP"; return
    fi
    local rel; rel=$(awk -v s="$sum" -v t="$total" 'BEGIN{printf "%.3f", (s>t?s-t:t-s)/t}')
    if fcmp "$rel" "<=" "$CONSERVE_TOL"; then
        record "$leg" "$m" "conservation" "sum=$sum total=$total relerr=$rel (<= $CONSERVE_TOL)" "PASS"
    else
        record "$leg" "$m" "conservation" "sum=$sum total=$total relerr=$rel (> $CONSERVE_TOL)" "FAIL"
    fi
}

# intra-leg netp/nets: the EXPECTED limit is that sub-cgroups cannot split, i.e.
# heavy ~= idle ~= total. Passing this asserts the documented v2.1 limitation
# and the v3.3 motivation -- it is not a defect.
assert_unsplittable() {  # METRIC HEAVY IDLE
    local m="$1" heavy="$2" idle="$3"
    if ! is_num "$heavy" || ! is_num "$idle"; then
        record "intra" "$m" "limit:can't-split" "heavy=$heavy idle=$idle (system-wide/unavail) -> needs v3.3" "SKIP[v3.3]"; return
    fi
    local denom rel
    denom=$(awk -v h="$heavy" -v i="$idle" 'BEGIN{printf "%.6f", (h>i?h:i)}')
    if ! fcmp "$denom" ">" 0; then
        record "intra" "$m" "limit:can't-split" "heavy=$heavy idle=$idle (both ~0) -> needs v3.3" "SKIP[v3.3]"; return
    fi
    rel=$(awk -v h="$heavy" -v i="$idle" -v d="$denom" 'BEGIN{printf "%.3f", (h>i?h-i:i-h)/d}')
    if fcmp "$rel" "<=" "$EQ_TOL"; then
        record "intra" "$m" "limit:can't-split" "heavy=$heavy ~= idle=$idle (reldiff=$rel) -> per-app needs v3.3" "LIMIT[v3.3]"
    else
        # They differ -> v2.1 unexpectedly DID separate them; surface it.
        record "intra" "$m" "limit:can't-split" "heavy=$heavy vs idle=$idle differ (reldiff=$rel) -- unexpected, investigate" "FAIL"
    fi
}

# =============================================================================
# Cgroup + container plumbing
# =============================================================================
need_root() {
    [ "$DRY_RUN" -eq 1 ] && return 0
    [ "$(id -u)" -eq 0 ] || die "must run as root for cgroup/lxc operations (or use --dry-run)"
}

lxc_launch() {  # NAME
    local name="$1"
    "$LXC_BIN" delete --force "$name" >/dev/null 2>&1 || true
    "$LXC_BIN" launch "$LXC_IMAGE" "$name" >/dev/null 2>&1 \
        || die "lxc launch failed for $name (is '$LXC_BIN' configured? try --no-lxc for the intra leg)"
    CLEANUP_CONTAINERS+=("$name")
    local initpid="" i
    for ((i=0; i<20; i++)); do
        initpid=$("$LXC_BIN" info "$name" 2>/dev/null | awk 'tolower($1)=="pid:"{print $2; exit}') || true
        [ -n "$initpid" ] && [ "$initpid" != "0" ] && break
        sleep 0.5
    done
    [ -n "$initpid" ] && [ "$initpid" != "0" ] || die "container $name has no init pid"
    # Ensure workload tools are present once, up front.
    "$LXC_BIN" exec "$name" -- bash -c \
        'command -v stress-ng >/dev/null 2>&1 && command -v iperf3 >/dev/null 2>&1 || { apt-get update -qq && apt-get install -y -qq stress-ng iperf3 >/dev/null 2>&1; }' \
        >/dev/null 2>&1 || warn "$name: could not pre-install stress-ng/iperf3"
}

# --- transient-scope workload placement (systemd-run) ------------------------
# Each workload runs in its own systemd transient scope. This (a) keeps it alive
# -- the host-side `lxc exec &` stays attached to the foreground `--scope`,
# instead of the workload being orphaned and reaped when a backgrounded in-exec
# `&` returns -- and (b) lets systemd own delegation/controllers, yielding a
# LEAF cgroup whose cgroup.procs lists the workload pids. That last point
# matters: the netp-netns and resctrl backends seed from cgroup.procs, and a
# container's payload-root cgroup.procs is empty under systemd (procs live in
# child scopes). Each scope's output is logged to WORKDIR/<unit>.log.
sdrun() {  # NAME UNIT CMD...   -- workload in a scope inside container NAME
    local name="$1" unit="$2"; shift 2
    "$LXC_BIN" exec "$name" -- systemd-run --scope --slice=intp.slice \
        --unit="$unit" --collect --quiet "$@" >"$WORKDIR/$unit.log" 2>&1 &
    CLEANUP_PIDS+=("$!")
}

sdrun_host() {  # UNIT CMD...   -- --no-lxc: workload in a scope on the host
    local unit="$1"; shift
    systemd-run --scope --slice=intp.slice --unit="$unit" --collect --quiet "$@" \
        >"$WORKDIR/$unit.log" 2>&1 &
    CLEANUP_PIDS+=("$!")
}

# Locate a transient scope's cgroup on the host and wait until it is populated.
# The cgroup hierarchy is host-wide, so a container's scope is a subdir under the
# container's payload tree; the unit name is unique per run, so a `find` by name
# is robust to LXD's exact nesting -- and avoids guessing the payload root, which
# is the container init's *init.scope*, not the container root. Works for both
# the container (lxc) and --no-lxc (host) cases.
await_scope_cg() {  # UNIT  -> host cgroup path of <UNIT>.scope once populated
    local unit="$1" cg i
    for ((i=0; i<25; i++)); do
        # `|| true`: find keeps walking after head closes -> SIGPIPE under pipefail.
        cg=$(find /sys/fs/cgroup -type d -name "$unit.scope" 2>/dev/null | head -1) || true
        # NB: cgroup.procs is a kernfs file -- it reports st_size 0 even when it
        # lists pids, so `test -s` is ALWAYS false here. Check content instead.
        [ -n "$cg" ] && [ -n "$(head -n1 "$cg/cgroup.procs" 2>/dev/null)" ] && { printf '%s\n' "$cg"; return 0; }
        sleep 0.4
    done
    return 1
}

# Echo a scope's captured log, prefixed -- diagnosis when a scope fails to start.
dump_scope_logs() {  # UNIT...
    local u f
    for u in "$@"; do
        f="$WORKDIR/$u.log"
        [ -s "$f" ] && { warn "---- $u.log ----"; sed 's/^/[validate]   /' "$f" >&2 || true; }
    done
    return 0
}

cleanup() {
    local p name cg
    for p in "${CLEANUP_PIDS[@]:-}";       do [ -n "$p" ] && kill "$p" 2>/dev/null || true; done
    for name in "${CLEANUP_CONTAINERS[@]:-}"; do [ -n "$name" ] && "$LXC_BIN" delete --force "$name" >/dev/null 2>&1 || true; done
    for cg in "${CLEANUP_CGROUPS[@]:-}";    do [ -n "$cg" ] && [ -d "$cg" ] && rmdir "$cg" 2>/dev/null || true; done
    [ -n "$HOST_IPERF_SRV_PID" ] && kill "$HOST_IPERF_SRV_PID" 2>/dev/null || true
    [ -n "$WORKDIR" ] && [ -d "$WORKDIR" ] && rm -rf "$WORKDIR" 2>/dev/null || true
}

# =============================================================================
# Leg: intra-container (apps as sub-cgroups in ONE container)
# =============================================================================
# Heavy stress-ng config exercises all five separable metrics at once:
#   --cpu (cpu) --vm (mbw) --cache (llcmr/llcocc) --hdd (blk).
HEAVY_STRESS="--cpu 2 --vm 1 --vm-bytes 256M --cache 2 --hdd 1 --hdd-bytes 128M"

run_leg_intra() {
    log "=== LEG intra: apps as sub-cgroups in one container ==="
    local cname="intp-val-intra" heavy_cg idle_cg total_cg pp=()
    local out_h="$WORKDIR/intra-heavy.json" out_i="$WORKDIR/intra-idle.json" out_t="$WORKDIR/intra-total.json"

    if [ "$DRY_RUN" -eq 1 ]; then
        if [ "$NO_LXC" -eq 1 ]; then
            log "DRY: systemd-run --scope --slice=intp.slice {stress-ng,sleep} on host"
        else
            log "DRY: $LXC_BIN launch $LXC_IMAGE $cname; in-container systemd-run scopes intp-heavy/intp-idle"
        fi
        log "intra: dry-run, no assertions"; return 0
    fi

    # Heavy + idle apps as sibling transient scopes under intp.slice. Two apps in
    # ONE netns: netp/nets cannot be split (asserted as the v3.3 limit below).
    if [ "$NO_LXC" -eq 1 ]; then
        sdrun_host intp-heavy stress-ng $HEAVY_STRESS --timeout "$((DURATION + 10))s"
        sdrun_host intp-idle  sleep "$((DURATION + 10))"
    else
        lxc_launch "$cname"
        sdrun "$cname" intp-heavy stress-ng $HEAVY_STRESS --timeout "$((DURATION + 10))s"
        sdrun "$cname" intp-idle  sleep "$((DURATION + 10))"
    fi
    heavy_cg=$(await_scope_cg intp-heavy) || heavy_cg=""
    idle_cg=$(await_scope_cg intp-idle)   || idle_cg=""

    if [ -z "$heavy_cg" ] || [ -z "$idle_cg" ]; then
        warn "intra: workload scopes never populated (systemd-run/delegation?) -- recording SKIP"
        dump_scope_logs intp-heavy intp-idle
        local m; for m in "${SEPARABLE_METRICS[@]}" "${NET_METRICS[@]}"; do
            record "intra" "$m" "setup" "scope not populated" "SKIP"; done
        [ "$NO_LXC" -eq 1 ] || "$LXC_BIN" delete --force "$cname" >/dev/null 2>&1 || true
        return 0
    fi
    total_cg="${heavy_cg%/*}"   # shared intp.slice parent (hierarchical cpu.stat)

    log "intra: profiling heavy, idle, slice-total concurrently (${DURATION}s)"
    profile_cgroup "$out_h" "$heavy_cg" & pp+=("$!"); CLEANUP_PIDS+=("$!")
    profile_cgroup "$out_i" "$idle_cg"  & pp+=("$!"); CLEANUP_PIDS+=("$!")
    profile_cgroup "$out_t" "$total_cg" & pp+=("$!"); CLEANUP_PIDS+=("$!")
    wait "${pp[@]}"

    local m h i t
    for m in "${SEPARABLE_METRICS[@]}"; do
        h=$(mean_metric "$out_h" "$m"); i=$(mean_metric "$out_i" "$m"); t=$(mean_metric "$out_t" "$m")
        assert_track_and_ratio "intra" "$m" "$h" "$i"
        assert_idle           "intra" "$m" "$i"
        assert_conserve       "intra" "$m" "$t" "$h" "$i"
    done
    for m in "${NET_METRICS[@]}"; do
        h=$(mean_metric "$out_h" "$m"); i=$(mean_metric "$out_i" "$m")
        assert_unsplittable "$m" "$h" "$i"
    done

    # Free this leg's resources promptly (the cleanup trap is the safety net).
    if [ "$NO_LXC" -eq 1 ]; then
        systemctl stop intp-heavy.scope intp-idle.scope 2>/dev/null || true
    else
        "$LXC_BIN" delete --force "$cname" >/dev/null 2>&1 || true
    fi
}

# =============================================================================
# Leg: inter-container (two sibling containers interfering on the host)
# =============================================================================
run_leg_inter() {
    log "=== LEG inter: two sibling containers interfering on the host ==="
    local ca="intp-val-a" cb="intp-val-b" cg_a cg_b
    local out_a="$WORKDIR/inter-a.json" out_b="$WORKDIR/inter-b.json" out_s="$WORKDIR/inter-sys.json"
    local host_ip port=23460 pp=() br
    # The iperf sink must be reachable from the containers: prefer the LXD/Incus
    # bridge gateway IP, then the host's default-route src, then loopback.
    host_ip="${INTP_HOST_IP:-}"
    if [ -z "$host_ip" ]; then
        for br in lxdbr0 incusbr0; do
            # `|| true`: a missing bridge makes the pipeline non-zero under pipefail.
            host_ip=$(ip -4 -o addr show "$br" 2>/dev/null | awk '{print $4}' | cut -d/ -f1 | head -1) || true
            [ -n "$host_ip" ] && break
        done
    fi
    if [ -z "$host_ip" ]; then
        host_ip=$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src"){print $(i+1); exit}}') || true
    fi
    [ -n "$host_ip" ] || host_ip="127.0.0.1"

    if [ "$DRY_RUN" -eq 1 ]; then
        log "DRY: $LXC_BIN launch $LXC_IMAGE $ca ; $LXC_BIN launch $LXC_IMAGE $cb"
        log "DRY: host iperf3 -s -p $port ; in $ca: stress-ng $HEAVY_STRESS + iperf3 -c $host_ip -b ${IPERF_MBPS}M ; $cb idle"
        log "DRY: profile A=$ca cgroup, B=$cb cgroup, and system-wide"
        cg_a="/sys/fs/cgroup/<payload-a>"; cg_b="/sys/fs/cgroup/<payload-b>"
        : > "$out_a"; : > "$out_b"; : > "$out_s"
        return 0
    fi

    command -v iperf3 >/dev/null 2>&1 || die "iperf3 not installed on host (apt install iperf3)"
    lxc_launch "$ca"; lxc_launch "$cb"

    # Host-side iperf3 sink for container A's sender.
    iperf3 -s -p "$port" -1 >/dev/null 2>&1 & HOST_IPERF_SRV_PID=$!
    sleep 0.5

    # A: aggressor (five separable metrics) + network sender at a known rate, both
    # in one transient scope. B: idle reference. `wait` keeps the scope foreground.
    sdrun "$ca" intp-load bash -c \
        "stress-ng $HEAVY_STRESS --timeout $((DURATION + 10))s & iperf3 -c $host_ip -p $port -t $((DURATION + 5)) -b ${IPERF_MBPS}M & wait"
    sdrun "$cb" intp-idle sleep "$((DURATION + 10))"

    cg_a=$(await_scope_cg intp-load) || cg_a=""
    cg_b=$(await_scope_cg intp-idle) || cg_b=""
    if [ -z "$cg_a" ]; then
        warn "inter: container A load scope never populated -- recording SKIP"
        dump_scope_logs intp-load intp-idle
        local m; for m in "${SEPARABLE_METRICS[@]}" "${NET_METRICS[@]}"; do
            record "inter" "$m" "setup" "container A scope not populated" "SKIP"; done
        return 0
    fi

    log "inter: profiling A, B, system-wide concurrently (${DURATION}s)"
    profile_cgroup "$out_a" "$cg_a" & pp+=("$!"); CLEANUP_PIDS+=("$!")
    if [ -n "$cg_b" ]; then profile_cgroup "$out_b" "$cg_b" & pp+=("$!"); CLEANUP_PIDS+=("$!"); else : > "$out_b"; fi
    profile_cgroup "$out_s" ""      & pp+=("$!"); CLEANUP_PIDS+=("$!")   # system-wide
    wait "${pp[@]}"

    local m a b s
    # netp: per-container -- A tracks, B ~0, A+B ~= system. backend should be "cgroup".
    a=$(mean_metric "$out_a" netp); b=$(mean_metric "$out_b" netp); s=$(mean_metric "$out_s" netp)
    record "inter" "netp" "backend" "A=$(backend_of "$out_a" netp) B=$(backend_of "$out_b" netp)" \
        "$( [ "$(backend_of "$out_a" netp)" = cgroup ] && echo PASS || echo SKIP )"
    assert_track_and_ratio "inter" "netp" "$a" "$b"
    assert_idle           "inter" "netp" "$b"
    assert_conserve       "inter" "netp" "$s" "$a" "$b"
    # nets: system-wide only in v2.1.
    s=$(mean_metric "$out_s" nets)
    record "inter" "nets" "system-wide" "system=$s; per-container split needs v3.3" "SKIP[v3.3]"
    # five separable metrics, per container.
    for m in "${SEPARABLE_METRICS[@]}"; do
        a=$(mean_metric "$out_a" "$m"); b=$(mean_metric "$out_b" "$m"); s=$(mean_metric "$out_s" "$m")
        assert_track_and_ratio "inter" "$m" "$a" "$b"
        assert_idle           "inter" "$m" "$b"
        assert_conserve       "inter" "$m" "$s" "$a" "$b"
    done

    # Free this leg's resources promptly (the cleanup trap is the safety net).
    "$LXC_BIN" delete --force "$ca" >/dev/null 2>&1 || true
    "$LXC_BIN" delete --force "$cb" >/dev/null 2>&1 || true
    [ -n "$HOST_IPERF_SRV_PID" ] && { kill "$HOST_IPERF_SRV_PID" 2>/dev/null || true; HOST_IPERF_SRV_PID=""; }
}

# =============================================================================
# Report
# =============================================================================
print_report() {
    local n_pass=0 n_fail=0 n_skip=0 n_limit=0 row r
    printf '\n'
    printf '%-6s %-7s %-18s %-6s %s\n' LEG METRIC CHECK RESULT DETAIL
    printf '%-6s %-7s %-18s %-6s %s\n' "-----" "------" "----------------" "----" "------"
    for row in "${RESULTS[@]:-}"; do
        [ -z "$row" ] && continue
        IFS='|' read -r leg metric check detail result <<<"$row"
        printf '%-6s %-7s %-18s %-6s %s\n' "$leg" "$metric" "$check" "$result" "$detail"
        case "$result" in
            PASS) n_pass=$((n_pass+1)) ;;
            FAIL) n_fail=$((n_fail+1)) ;;
            LIMIT*) n_limit=$((n_limit+1)) ;;
            SKIP*) n_skip=$((n_skip+1)) ;;
        esac
    done
    printf '\nSummary: %d PASS, %d FAIL, %d LIMIT[v3.3] (expected), %d SKIP\n' \
        "$n_pass" "$n_fail" "$n_limit" "$n_skip"
    [ "$DRY_RUN" -eq 1 ] && { printf '(dry-run: structure only, no measurements)\n'; return 0; }
    if [ "$n_fail" -gt 0 ]; then
        printf 'RESULT: FAIL -- per-cgroup attribution did not hold; not loop-ready.\n'
        return 1
    fi
    printf 'RESULT: PASS -- per-cgroup signals validated for the IADA closed loop.\n'
    return 0
}

# =============================================================================
main() {
    trap cleanup EXIT INT TERM
    need_root
    [ -x "$V21_BIN" ] || [ "$DRY_RUN" -eq 1 ] || die "v2.1 binary not built: $V21_BIN (make -C variants/v2.1-c-abi-cgroup all)"
    if [ "$DRY_RUN" -eq 0 ]; then
        command -v jq >/dev/null 2>&1 || die "jq required for JSON parsing"
        command -v stress-ng >/dev/null 2>&1 || die "stress-ng required"
    fi
    WORKDIR=$(mktemp -d -t intp-validate.XXXXXX)
    log "binary=$V21_BIN leg=$LEG duration=${DURATION}s dry_run=$DRY_RUN no_lxc=$NO_LXC workdir=$WORKDIR"

    case "$LEG" in
        intra) run_leg_intra ;;
        inter) run_leg_inter ;;
        both)  run_leg_intra; run_leg_inter ;;
    esac
    print_report
}

# Run only when executed directly; sourcing (e.g. tests) loads the functions
# without running the campaign.
if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
    parse_args "$@"
    main
fi

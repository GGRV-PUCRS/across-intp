#!/usr/bin/env bash
#
# stage-next-campaigns.sh -- ONE idle-window command that provisions everything
# the Tier-B/C campaigns need on the testbed (C32/C33): suite images + datasets
# (CloudSuite), the DeathStarBench clone + wrk2, and the WITH_SUITES bench VM
# image for the vm-guest legs. Designed for the gap BETWEEN campaigns: it
# REFUSES to run while a benchmark is in flight, and it is safe to re-run
# (every step is an idempotent installer or a presence check).
#
#     sudo bash bench/setup/stage-next-campaigns.sh [--skip-vm] [--check-only]
#
#   --skip-vm      skip the WITH_SUITES qcow2 (e.g. when only host-compose
#                  campaigns are queued next; the build is the slow step)
#   --check-only   offline verification only; prints the readiness manifest
#                  and exits nonzero on gaps (no network, no builds)
#
# Optional inputs (used when present, otherwise everything is fetched):
#   /var/lib/intp/staging/*.tar           docker image tars -> docker load
#   /var/lib/intp/staging/intp-bench-vm-suites.qcow2.zst (+ .sha256)
#                                          pre-built suites image -> install
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STAGING="/var/lib/intp/staging"
SUITES_IMG="/var/lib/intp/intp-bench-vm-suites.qcow2"

SKIP_VM=0 CHECK_ONLY=0
for a in "$@"; do
    case "$a" in
        --skip-vm)    SKIP_VM=1 ;;
        --check-only) CHECK_ONLY=1 ;;
        *) echo "unknown flag: $a" >&2; exit 2 ;;
    esac
done

say()  { echo "[stage] $*"; }
fail() { echo "[stage] ERROR: $*" >&2; exit 1; }

# ── 1. Preflight: NEVER touch a busy box (the campaign must not be perturbed)
busy="$(pgrep -af 'run-intp-bench|run-cadence-sweep|stress-ng|qemu-system' 2>/dev/null | grep -v "stage-next-campaigns" || true)"
if [ -n "$busy" ]; then
    echo "[stage] REFUSING: benchmark activity detected on this host:" >&2
    echo "$busy" | head -5 | sed 's/^/    /' >&2
    exit 3
fi
say "preflight ok: host is idle"

# Provisioning (installers, /var/lib/intp, VM build) needs root; the
# --check-only path is read-only and runs as any docker-capable user.
[ "$CHECK_ONLY" = 1 ] || [ "$(id -u)" = 0 ] \
    || fail "run as root (docker volumes, /var/lib/intp, VM build)"

# ── 2. Staged inputs (optional)
if [ "$CHECK_ONLY" = 0 ] && [ -d "$STAGING" ]; then
    for tar in "$STAGING"/*.tar; do
        [ -e "$tar" ] || break
        say "docker load < $(basename "$tar")"
        docker load -i "$tar" >/dev/null || say "WARN: docker load failed for $tar"
    done
fi

# ── 3. Suite installers (offline-check first; fill gaps only when needed)
overall=0
for inst in setup-cloudsuite-workload.sh setup-dsb-workload.sh; do
    if bash "$SCRIPT_DIR/$inst" --offline-check >/dev/null 2>&1; then
        say "$inst: already complete"
    elif [ "$CHECK_ONLY" = 1 ]; then
        say "$inst: GAPS (would install)"; overall=1
    else
        say "$inst: provisioning..."
        bash "$SCRIPT_DIR/$inst" || fail "$inst failed"
    fi
done

# ── 4. WITH_SUITES bench VM image (vm-guest legs of Tier-B/C)
if [ "$SKIP_VM" = 0 ]; then
    if [ -f "$SUITES_IMG" ]; then
        say "suites VM image present: $SUITES_IMG ($(du -h "$SUITES_IMG" | cut -f1))"
    elif [ "$CHECK_ONLY" = 1 ]; then
        say "suites VM image MISSING: $SUITES_IMG"; overall=1
    elif [ -f "$STAGING/intp-bench-vm-suites.qcow2.zst" ]; then
        say "installing transferred suites image"
        if [ -f "$STAGING/intp-bench-vm-suites.qcow2.zst.sha256" ]; then
            ( cd "$STAGING" && sha256sum -c intp-bench-vm-suites.qcow2.zst.sha256 ) \
                || fail "staged qcow2 fails its sha256"
        fi
        zstd -d -f "$STAGING/intp-bench-vm-suites.qcow2.zst" -o "$SUITES_IMG" \
            || fail "zstd decompress failed"
    else
        # On-box build: the box has the full qemu stack and the fat pipe makes
        # the in-guest suite pulls fast. Testbed-grade in-guest sizing.
        say "building suites VM image on-box (~20-40 min)"
        WITH_SUITES=1 GUEST_SOLR_HEAP=12g GUEST_SPARK_MEM=6g \
            bash "$SCRIPT_DIR/build-bench-vm.sh" || fail "WITH_SUITES VM build failed"
    fi
fi

# ── 5. Verify everything a campaign will touch
say "verifying..."
ok=1
for inst in setup-cloudsuite-workload.sh setup-dsb-workload.sh; do
    bash "$SCRIPT_DIR/$inst" --offline-check >/dev/null 2>&1 \
        || { say "VERIFY FAIL: $inst --offline-check"; ok=0; }
done
DRIVERS="$SCRIPT_DIR/../workloads/compose"
for suite in cloudsuite-data-caching cloudsuite-web-search cloudsuite-in-memory-analytics dsb-social-network; do
    sdir="$DRIVERS/$suite"
    # shellcheck disable=SC1091
    ( COMPOSE_FILES=""; . "$sdir/meta.env"
      fargs=()
      for f in $COMPOSE_FILES; do case "$f" in /*) ;; *) f="$sdir/$f" ;; esac; fargs+=( -f "$f" ); done
      docker compose "${fargs[@]}" config -q ) \
        || { say "VERIFY FAIL: compose config $suite"; ok=0; }
done
if [ "$SKIP_VM" = 0 ] && [ ! -f "$SUITES_IMG" ] && [ "$CHECK_ONLY" = 0 ]; then
    say "VERIFY FAIL: $SUITES_IMG missing"; ok=0
fi
[ "$ok" = 1 ] || overall=1

# ── 6. READY manifest
echo
echo "================= STAGING MANIFEST ================="
echo "docker images (suites):"
docker images --format '  {{.Repository}}:{{.Tag}}  {{.Size}}' 2>/dev/null \
    | grep -E 'cloudsuite|deathstarbench|jaeger|mongo|redis|memcached|yg397' | sort -u
echo "volumes:"
for v in intp-cs-movielens intp-cs-websearch-index; do
    docker volume inspect "$v" >/dev/null 2>&1 && echo "  $v: present" || echo "  $v: MISSING"
done
echo "DSB: root=${INTP_DSB_ROOT:-/opt/DeathStarBench} commit=$(cut -c1-12 "${INTP_DSB_ROOT:-/opt/DeathStarBench}/.intp-dsb-commit" 2>/dev/null || echo '?')"
[ "$SKIP_VM" = 0 ] && echo "suites qcow2: $( [ -f "$SUITES_IMG" ] && du -h "$SUITES_IMG" | cut -f1 || echo MISSING )  ($SUITES_IMG)"
echo "disk: $(df -h /var/lib | awk 'NR==2{print $4" free of "$2}')"
echo
echo "next-campaign launch commands (Tier-B then Tier-C, 3 classes, fixed 1 s):"
cat <<'CMDS'
  # Tier-B (Redis 3-class + CloudSuite 3-label)
  ./bench/run-intp-bench.sh --portable-metrics --variants v2.1,v3.3 \
      --env bare,container,vm-guest --stages solo \
      --workloads app18_redis_kv,app19_cs_datacaching,app20_cs_websearch,app21_cs_imanalytics \
      --reps 12 --duration 120 --vm-image /var/lib/intp/intp-bench-vm-suites.qcow2 \
      --output-dir /root/across-intp/results/p2-tierb-realworld

  # Tier-C (DSB social-network)
  ./bench/run-intp-bench.sh --portable-metrics --variants v2.1,v3.3 \
      --env bare,container,vm-guest --stages solo \
      --workloads app22_dsb_socialnet \
      --reps 12 --duration 120 --vm-image /var/lib/intp/intp-bench-vm-suites.qcow2 \
      --output-dir /root/across-intp/results/p3-tierc-dsb
CMDS
echo "===================================================="
if [ "$overall" = 0 ]; then say "READY"; else say "GAPS FOUND (see above)"; fi
exit "$overall"

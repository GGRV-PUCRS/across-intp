#!/usr/bin/env bash
#
# setup-cloudsuite-workload.sh -- provision the CloudSuite Tier-B suite deps
# (C32/C33): images for data-caching, web-search, in-memory-analytics, the
# external dataset volumes that survive the harness's per-rep `down -v`, and
# the per-host .env sizing files the compose drivers interpolate.
#
# Idempotent; safe to re-run (existing volumes/files are kept). Network is
# touched only for missing pieces. NEVER run on the testbed while a campaign
# is in flight -- stage-next-campaigns.sh wraps this with an idle preflight.
#
#     bash bench/setup/setup-cloudsuite-workload.sh [--offline-check]
#         [--guest] [--with-websearch-index] [--solr-heap 12g] [--spark-mem 6g]
#
#   --offline-check        verify only (images/volumes/.env); exit 1 on gaps,
#                          no network, no writes
#   --guest                guest-image provisioning profile: skips the 14 GB
#                          web-search index by default (qcow2 size; opt back
#                          in with --with-websearch-index)
#   --with-websearch-index force the web-search index volume download
#   --solr-heap / --spark-mem
#                          override the auto-sizing (testbed-grade defaults on
#                          >=64 GiB hosts, smoke-grade below)
set -euo pipefail

IMAGES=(
    cloudsuite/data-caching:server
    cloudsuite/data-caching:client
    cloudsuite/web-search:server
    cloudsuite/web-search:client
    cloudsuite/web-search:dataset
    cloudsuite/in-memory-analytics:latest
    cloudsuite/movielens-dataset:latest
)
WS_VOLUME="intp-cs-websearch-index"
ML_VOLUME="intp-cs-movielens"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DRIVERS="$(cd "$SCRIPT_DIR/../workloads/compose" && pwd)"

OFFLINE=0 GUEST=0 WANT_WS_INDEX=""
SOLR_HEAP="" SPARK_MEM=""
while [ $# -gt 0 ]; do
    case "$1" in
        --offline-check)       OFFLINE=1 ;;
        --guest)               GUEST=1 ;;
        --with-websearch-index) WANT_WS_INDEX=1 ;;
        --solr-heap)           SOLR_HEAP="$2"; shift ;;
        --spark-mem)           SPARK_MEM="$2"; shift ;;
        *) echo "unknown flag: $1" >&2; exit 2 ;;
    esac
    shift
done

say()  { echo "[setup-cloudsuite] $*"; }
fail() { echo "[setup-cloudsuite] ERROR: $*" >&2; exit 1; }

command -v docker >/dev/null 2>&1 || fail "docker not installed"
docker compose version >/dev/null 2>&1 || fail "docker compose v2 not available"

# Auto-sizing: testbed-grade on big hosts, smoke-grade on the dev machine.
# FABAN_*: web-search client pressure (CycleTime mode; C33) -- the CloudSuite
# think-time defaults idle the server (<1% cpu, verified in the app20 micro).
mem_gib=$(( $(awk '/MemTotal/{print $2}' /proc/meminfo) / 1024 / 1024 ))
if [ "$mem_gib" -ge 64 ]; then
    : "${SOLR_HEAP:=12g}"; : "${SPARK_MEM:=6g}"; IMA_DATASET="/data/ml-latest"
    # C33: 32 workers x 100-200ms CycleTime idled Solr at ~2% cpu on the 1/3
    # footprint (16 cores) -- under-driven. Drive harder so web-search clears the
    # activation floors (cpu/net/mem) for a representative multi-class fingerprint.
    FABAN_WORKERS=128; FABAN_IMIN=20; FABAN_IMAX=50
else
    : "${SOLR_HEAP:=4g}";  : "${SPARK_MEM:=3g}"; IMA_DATASET="/data/ml-latest-small"
    FABAN_WORKERS=16; FABAN_IMIN=200; FABAN_IMAX=400
fi

# web-search index policy: required on hosts (the campaign needs it), skipped
# in --guest builds unless forced (it would add ~14 GB to the qcow2).
NEED_WS_INDEX=1
[ "$GUEST" = 1 ] && [ -z "$WANT_WS_INDEX" ] && NEED_WS_INDEX=0

vol_populated() {
    # $1 = volume, $2 = path that must exist inside it
    docker volume inspect "$1" >/dev/null 2>&1 || return 1
    docker run --rm -v "$1":/check:ro --entrypoint bash \
        cloudsuite/data-caching:client -c "test -e /check/$2" >/dev/null 2>&1
}

missing=0
for img in "${IMAGES[@]}"; do
    if docker image inspect "$img" >/dev/null 2>&1; then
        say "image ok: $img"
    elif [ "$OFFLINE" = 1 ]; then
        say "MISSING image: $img"; missing=1
    else
        say "pulling $img"
        docker pull -q "$img" >/dev/null || fail "pull failed: $img"
    fi
done

# Driver .env files FIRST (compose interpolation; sized for THIS host): they
# gate `docker compose config`, so they must exist even while the long
# downloads below are still running (the harness fails cleanly without them,
# but ordering them first makes a partially-provisioned host usable sooner).
if [ "$OFFLINE" = 1 ]; then
    for f in cloudsuite-web-search cloudsuite-in-memory-analytics; do
        [ -f "$DRIVERS/$f/.env" ] && say ".env ok: $f" || { say "MISSING .env: $f"; missing=1; }
    done
else
    cat > "$DRIVERS/cloudsuite-web-search/.env" <<EOF
# written by setup-cloudsuite-workload.sh (host-sized; re-run to refresh)
SOLR_HEAP=$SOLR_HEAP
INDEX_MOUNT=/download
FABAN_WORKERS=$FABAN_WORKERS
FABAN_STEADY=600
FABAN_INTERVAL_MIN=$FABAN_IMIN
FABAN_INTERVAL_MAX=$FABAN_IMAX
EOF
    cat > "$DRIVERS/cloudsuite-in-memory-analytics/.env" <<EOF
# written by setup-cloudsuite-workload.sh (host-sized; re-run to refresh)
IMA_DATASET_DIR=$IMA_DATASET
IMA_RATINGS_FILE=/data/myratings.csv
SPARK_MEM=$SPARK_MEM
EOF
    say "wrote driver .env files (SOLR_HEAP=$SOLR_HEAP SPARK_MEM=$SPARK_MEM dataset=$IMA_DATASET)"
fi

# movielens dataset volume: docker copies the image's /data into an empty
# named volume on first container creation with that mount.
if vol_populated "$ML_VOLUME" "myratings.csv"; then
    say "volume ok: $ML_VOLUME"
elif [ "$OFFLINE" = 1 ]; then
    say "MISSING volume: $ML_VOLUME"; missing=1
else
    say "populating $ML_VOLUME from cloudsuite/movielens-dataset"
    docker volume create "$ML_VOLUME" >/dev/null
    cid=$(docker create -v "$ML_VOLUME":/data cloudsuite/movielens-dataset:latest /bin/true 2>/dev/null \
          || docker create -v "$ML_VOLUME":/data cloudsuite/movielens-dataset:latest)
    docker rm "$cid" >/dev/null
    vol_populated "$ML_VOLUME" "myratings.csv" || fail "$ML_VOLUME population failed"
fi

# web-search index volume: the dataset image DOWNLOADS index_14GB.tar.gz from
# datasets.epfl.ch at run time (verified entrypoint; the server throttles to
# <1 MB/s -> hours) -- so prefer restoring a staged tarball of an
# already-populated volume when one exists (export from a provisioned host:
#   docker run --rm -v intp-cs-websearch-index:/d:ro ubuntu:24.04 \
#       tar cf - -C /d . | zstd -T0 > intp-cs-websearch-index.tar.zst
# and drop it under /var/lib/intp/staging/). Falls back to the slow download.
# The server expects /download/index_14GB/data (INDEX_MOUNT=/download).
WS_VOL_TAR="${INTP_STAGING_DIR:-/var/lib/intp/staging}/intp-cs-websearch-index.tar.zst"
if [ "$NEED_WS_INDEX" = 1 ]; then
    if vol_populated "$WS_VOLUME" "index_14GB/data"; then
        say "volume ok: $WS_VOLUME"
    elif [ "$OFFLINE" = 1 ]; then
        say "MISSING volume: $WS_VOLUME"; missing=1
    elif [ -f "$WS_VOL_TAR" ]; then
        say "restoring $WS_VOLUME from staged tarball ($(du -h "$WS_VOL_TAR" | cut -f1))"
        docker volume create "$WS_VOLUME" >/dev/null
        zstd -dc "$WS_VOL_TAR" | docker run --rm -i -v "$WS_VOLUME":/d ubuntu:24.04 tar xf - -C /d \
            || fail "staged index restore failed"
        vol_populated "$WS_VOLUME" "index_14GB/data" || fail "$WS_VOLUME restore left no index"
    else
        say "downloading the web-search index into $WS_VOLUME (~14 GB; EPFL throttles -- hours)"
        docker volume create "$WS_VOLUME" >/dev/null
        docker run --rm -v "$WS_VOLUME":/download cloudsuite/web-search:dataset \
            || fail "web-search index download failed"
        vol_populated "$WS_VOLUME" "index_14GB/data" || fail "$WS_VOLUME population failed"
    fi
else
    say "skipping web-search index (guest profile; --with-websearch-index to force)"
fi

if [ "$OFFLINE" = 1 ] && [ "$missing" = 1 ]; then
    fail "offline check found gaps (run without --offline-check to fill)"
fi

ws_state="present"; [ "$NEED_WS_INDEX" = 0 ] && ws_state="skipped(guest)"
disk=$(docker system df --format '{{.Size}}' 2>/dev/null | head -1 || echo "?")
say "READY cloudsuite images=${#IMAGES[@]} volumes=$ML_VOLUME,$WS_VOLUME($ws_state) docker-disk=$disk"

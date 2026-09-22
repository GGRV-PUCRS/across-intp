#!/usr/bin/env bash
#
# setup-dsb-workload.sh -- provision DeathStarBench social-network (Tier-C,
# C32/C33): the pinned clone, its docker images, the wrk2 load generator, and
# the graph-init python dep. Idempotent; safe to re-run. NEVER run on the
# testbed mid-campaign -- stage-next-campaigns.sh wraps this with an idle
# preflight.
#
#     bash bench/setup/setup-dsb-workload.sh [--offline-check] [--guest]
#
#   --offline-check  verify only (clone/commit, wrk2 binary, images, aiohttp);
#                    exit 1 on gaps, no network, no writes
#   --guest          guest-image provisioning profile (same work; kept as an
#                    explicit flag so cloud-init logs read unambiguously)
#
# Env: INTP_DSB_ROOT (default /opt/DeathStarBench), INTP_DSB_COMMIT (pin; the
# first install records HEAD into $ROOT/.intp-dsb-commit and later runs hold it).
set -euo pipefail

DSB_REPO="https://github.com/delimitrou/DeathStarBench.git"
DSB_ROOT="${INTP_DSB_ROOT:-/opt/DeathStarBench}"
SN="$DSB_ROOT/socialNetwork"
WRK="$DSB_ROOT/wrk2/wrk"
# lua-socket: mixed-workload.lua does `require("socket")` (verified); the apt
# package targets the lua-5.1 ABI, which wrk2's vendored LuaJIT loads.
WRK_DEPS=(build-essential libssl-dev zlib1g-dev luajit libluajit-5.1-dev python3-aiohttp lua-socket)

OFFLINE=0
while [ $# -gt 0 ]; do
    case "$1" in
        --offline-check) OFFLINE=1 ;;
        --guest)         : ;;   # same provisioning; flag only labels the log
        *) echo "unknown flag: $1" >&2; exit 2 ;;
    esac
    shift
done

say()  { echo "[setup-dsb] $*"; }
fail() { echo "[setup-dsb] ERROR: $*" >&2; exit 1; }
SUDO=""; [ "$(id -u)" != 0 ] && SUDO="sudo"

command -v docker >/dev/null 2>&1 || fail "docker not installed"
docker compose version >/dev/null 2>&1 || fail "docker compose v2 not available"

missing=0

# 1. Pinned clone
if [ -d "$SN" ]; then
    say "clone ok: $DSB_ROOT ($(git -C "$DSB_ROOT" rev-parse --short HEAD 2>/dev/null || echo '?'))"
elif [ "$OFFLINE" = 1 ]; then
    say "MISSING clone: $DSB_ROOT"; missing=1
else
    say "cloning DeathStarBench -> $DSB_ROOT"
    parent="$(dirname "$DSB_ROOT")"
    if mkdir -p "$parent" 2>/dev/null && [ -w "$parent" ]; then
        git clone --depth 50 "$DSB_REPO" "$DSB_ROOT"
    else
        $SUDO mkdir -p "$parent"
        $SUDO git clone --depth 50 "$DSB_REPO" "$DSB_ROOT"
        $SUDO chown -R "$(id -u):$(id -g)" "$DSB_ROOT" 2>/dev/null || true
    fi
fi
# wrk2 vendors LuaJIT as a SUBMODULE (verified: the make fails without it).
if [ -d "$DSB_ROOT/.git" ] && [ "$OFFLINE" = 0 ] && [ ! -f "$DSB_ROOT/wrk2/deps/luajit/src/Makefile" ]; then
    say "initializing wrk2/deps/luajit submodule"
    git -C "$DSB_ROOT" submodule update --init --depth 1 wrk2/deps/luajit
fi
if [ -d "$DSB_ROOT/.git" ] && [ "$OFFLINE" = 0 ]; then
    if [ -n "${INTP_DSB_COMMIT:-}" ]; then
        git -C "$DSB_ROOT" checkout -q "$INTP_DSB_COMMIT"
    fi
    # Record the pin so every host/guest provisions the SAME tree.
    git -C "$DSB_ROOT" rev-parse HEAD > "$DSB_ROOT/.intp-dsb-commit" 2>/dev/null || true
fi

# 2. wrk2 build deps + binary (DSB ships its own wrk2 fork; luajit headers
#    required). python3-aiohttp rides along (init_social_graph.py).
if [ -x "$WRK" ]; then
    say "wrk2 ok: $WRK"
elif [ "$OFFLINE" = 1 ]; then
    say "MISSING wrk2: $WRK"; missing=1
else
    # wrk2 vendors LuaJIT, so try the build first; fall back to apt deps
    # (needs root/sudo) only if it fails.
    say "building wrk2"
    if ! make -C "$DSB_ROOT/wrk2" -j"$(nproc)" >/dev/null 2>&1; then
        command -v apt-get >/dev/null 2>&1 || fail "wrk2 build failed and apt-get absent"
        say "wrk2 build failed; installing deps (${WRK_DEPS[*]}) and retrying"
        export DEBIAN_FRONTEND=noninteractive
        $SUDO apt-get update -qq
        $SUDO apt-get install -y -qq "${WRK_DEPS[@]}" >/dev/null
        make -C "$DSB_ROOT/wrk2" -j"$(nproc)" >/dev/null || fail "wrk2 build failed"
    fi
    [ -x "$WRK" ] || fail "wrk2 build produced no $WRK"
fi
if [ ! -e /usr/lib/x86_64-linux-gnu/lua/5.1/socket/core.so ] && [ ! -e /usr/lib/lua/5.1/socket/core.so ]; then
    if [ "$OFFLINE" = 1 ]; then
        say "MISSING lua-socket (wrk2 lua profiles)"; missing=1
    else
        $SUDO apt-get install -y -qq lua-socket >/dev/null 2>&1 \
            || say "WARN: lua-socket install failed; wrk2 lua profiles degrade to plain GETs"
    fi
fi
if ! python3 -c 'import aiohttp' 2>/dev/null; then
    if [ "$OFFLINE" = 1 ]; then
        say "MISSING python3-aiohttp (graph init)"; missing=1
    else
        # PEP 668: Ubuntu 24.04 python is externally managed -> a plain
        # `pip --user` is refused; this is a user-scoped lib, not a system one.
        $SUDO apt-get install -y -qq python3-aiohttp >/dev/null 2>&1 \
            || pip3 install --user --quiet --break-system-packages aiohttp 2>/dev/null \
            || fail "aiohttp install failed (apt and pip both unavailable)"
    fi
fi

# 3. Suite images (everything the socialNetwork compose file references)
if [ -f "$SN/docker-compose.yml" ]; then
    mapfile -t imgs < <(docker compose -f "$SN/docker-compose.yml" config --images 2>/dev/null | sort -u)
    [ "${#imgs[@]}" -gt 0 ] || fail "could not resolve images from $SN/docker-compose.yml"
    for img in "${imgs[@]}"; do
        if docker image inspect "$img" >/dev/null 2>&1; then
            say "image ok: $img"
        elif [ "$OFFLINE" = 1 ]; then
            say "MISSING image: $img"; missing=1
        else
            say "pulling $img"
            docker pull -q "$img" >/dev/null || fail "pull failed: $img"
        fi
    done
else
    [ "$OFFLINE" = 1 ] || fail "compose file missing: $SN/docker-compose.yml"
    missing=1
fi

if [ "$OFFLINE" = 1 ] && [ "$missing" = 1 ]; then
    fail "offline check found gaps (run without --offline-check to fill)"
fi

n_imgs="${imgs[*]:+${#imgs[@]}}"
say "READY dsb-social-network root=$DSB_ROOT commit=$(cut -c1-12 "$DSB_ROOT/.intp-dsb-commit" 2>/dev/null || echo '?') images=${n_imgs:-?} wrk2=$( [ -x "$WRK" ] && echo ok || echo missing )"

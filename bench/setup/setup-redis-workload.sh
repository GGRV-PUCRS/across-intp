#!/usr/bin/env bash
#
# setup-redis-workload.sh -- provision the Redis (Tier-B real-world) workload deps.
#
# Idempotent. Installs redis-server + redis-tools (redis-benchmark -- the portable,
# apt-native load generator that works identically on bare metal, inside containers,
# and inside the KVM bench guest). Optionally pulls the memtier_benchmark docker
# image (--with-memtier; a higher-fidelity multi-threaded load generator, available
# on bare/container hosts that have docker) for runs that prefer it over
# redis-benchmark.
#
# Part of the reproducibility tooling (C32): run-intp-bench.sh's Redis workload
# (app18_redis_kv) calls this automatically when redis-server is absent, and it is
# safe to run standalone to provision a host / container image / VM guest ahead of
# a campaign:
#     bash bench/setup/setup-redis-workload.sh [--with-memtier]
set -euo pipefail

WITH_MEMTIER=0
[ "${1:-}" = "--with-memtier" ] && WITH_MEMTIER=1

have() { command -v "$1" >/dev/null 2>&1; }

if have redis-server && have redis-benchmark; then
    echo "[setup-redis] redis-server + redis-benchmark already present"
else
    if have apt-get; then
        echo "[setup-redis] installing redis-server + redis-tools via apt"
        export DEBIAN_FRONTEND=noninteractive
        apt-get update -qq
        apt-get install -y -qq redis-server redis-tools >/dev/null
    else
        echo "[setup-redis] ERROR: apt-get not found; install redis-server + redis-tools manually" >&2
        exit 1
    fi
fi

# The Debian/Ubuntu package starts a system redis on :6379 via systemd. The
# workload uses a DEDICATED port (so there is no port clash), but disable the
# system unit anyway so a stray system instance never confounds the cgroup scope.
if have systemctl; then
    systemctl disable --now redis-server 2>/dev/null || true
fi

if [ "$WITH_MEMTIER" = "1" ]; then
    if have docker; then
        echo "[setup-redis] pulling memtier_benchmark image (higher-fidelity load)"
        if docker pull -q redislabs/memtier_benchmark:latest >/dev/null 2>&1; then
            echo "[setup-redis]   memtier image ready"
        else
            echo "[setup-redis]   WARN: memtier pull failed; redis-benchmark stays the default"
        fi
    else
        echo "[setup-redis] --with-memtier requested but docker absent; skipping (redis-benchmark default)"
    fi
fi

echo "[setup-redis] OK: $(redis-server --version 2>/dev/null | head -1)"

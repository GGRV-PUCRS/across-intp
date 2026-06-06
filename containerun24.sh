#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# containerun24.sh -- one-shot container campaign for the cgroup-native variants.
#
# The paper-#2 counterpart of ub24run.sh: instead of the bare-metal SBAC-PAD
# legs (ub24run.sh -> v1.1,v2,v3.2 ; ub22run.sh -> v0.2), this launcher runs the
# CGROUP-NATIVE variants inside an LXC/LXD (Incus) system container, with the
# profiler on the host attached to the container's cgroup. That is the
# "a container is a cgroup" path v2.1 (and the future eBPF-native v3.3) are
# built for, and it matches the LXC provenance of the IADA classifier's
# training data (Meyer 2021, Node-Tiers).
#
# It pins the container-lxc execution environment and drives run-big-batch.sh
# (the same engine ub24run.sh reaches through run-os-campaign.sh). The stress-ng
# bench leg runs; HiBench is OFF by default because a container HiBench launcher
# is not wired yet (set RUN_HIBENCH=1 once it is, and it will run system-wide).
#
# The "24" denotes the Ubuntu 24.04 host and the default ubuntu:24.04 LXD image.
#
# Variants (both are first-class measured cgroup-native endpoints, paper #2):
#   v2.1   cgroup-native hybrid-C (no eBPF) -- per-cgroup via cpu.stat/io.stat
#          + perf cgroup-mode
#   v3.3   eBPF-native per-cgroup -- cgroup_skb netp + cgroup-id counter maps
# Both run by default. To measure just one, pass --variants:
#   sudo bash containerun24.sh --variants v2.1        # cgroup-native only
#   sudo bash containerun24.sh --variants v3.3        # eBPF cgroup-native only
#
# Usage:
#   sudo bash containerun24.sh                      # full container stress-ng campaign (v2.1,v3.3)
#   sudo bash containerun24.sh --variants v2.1      # restrict to one endpoint
#   bash containerun24.sh --dry-run                 # print resolved config, run nothing
#   sudo REPS=3 DURATION=60 bash containerun24.sh   # quick sizing run
#
# Requires: the LXD/Incus `lxc` client + a running daemon (override the binary
# with INTP_BENCH_LXC_BIN, the image with INTP_BENCH_LXC_IMAGE), and root for
# the host-side profiler (PMU/resctrl/cgroup access). Every run-big-batch.sh
# env knob (REPS, DURATION, BENCH_WORKLOADS, BENCH_CPUS, BENCH_MEM, RESUME_DIR,
# RUN_PLOTS, ...) is honoured.
# -----------------------------------------------------------------------------

set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

DRY_RUN=0
while [ $# -gt 0 ]; do
    case "$1" in
        --variants) BENCH_VARIANTS="$2"; shift 2 ;;
        --dry-run)  DRY_RUN=1; shift ;;
        -h|--help)  sed -n '3,/^# ---/p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "containerun24.sh: unknown option: $1 (see --help)" >&2; exit 2 ;;
    esac
done

# ---- pinned container-campaign configuration --------------------------------
# container-lxc is THE point of this launcher: workload in an LXC/LXD container,
# host-side profiler on the container cgroup. Pinned (not overridable here) -- to
# mix environments, drive run-big-batch.sh directly.
export BENCH_ENVS="container-lxc"
# Cgroup-native endpoints. Both v2.1 and v3.3 run by default; restrict via
# --variants (parsed above into BENCH_VARIANTS, which this :- default respects).
export BENCH_VARIANTS="${BENCH_VARIANTS:-v2.1,v3.3}"
# stress-ng leg on; HiBench-in-LXC not wired yet -> keep OFF so it cannot
# silently fall back to a host-wide HiBench run under a container campaign.
export RUN_STRESS_BENCH="${RUN_STRESS_BENCH:-1}"
export RUN_HIBENCH="${RUN_HIBENCH:-0}"
export RUN_PLOTS="${RUN_PLOTS:-1}"
# LXD/Incus engine knobs flow straight through to run-intp-bench's launcher.
export INTP_BENCH_LXC_BIN="${INTP_BENCH_LXC_BIN:-lxc}"
export INTP_BENCH_LXC_IMAGE="${INTP_BENCH_LXC_IMAGE:-ubuntu:24.04}"

BIG_BATCH="$SCRIPT_DIR/run-big-batch.sh"
[ -f "$BIG_BATCH" ] || { echo "containerun24.sh: run-big-batch.sh not found at $BIG_BATCH" >&2; exit 1; }

echo "==================================================================="
echo " IntP container campaign (cgroup-native)"
echo "   env           = $BENCH_ENVS"
echo "   variants      = $BENCH_VARIANTS"
echo "   lxc engine    = $INTP_BENCH_LXC_BIN   image = $INTP_BENCH_LXC_IMAGE"
echo "   stress-ng     = $RUN_STRESS_BENCH     hibench = $RUN_HIBENCH     plots = $RUN_PLOTS"
echo "   reps          = ${REPS:-<run-big-batch default>}   duration = ${DURATION:-<default>}s"
echo "==================================================================="

if [ "$DRY_RUN" -eq 1 ]; then
    echo "[dry-run] would exec: BENCH_ENVS=$BENCH_ENVS BENCH_VARIANTS=$BENCH_VARIANTS \\"
    echo "                      RUN_STRESS_BENCH=$RUN_STRESS_BENCH RUN_HIBENCH=$RUN_HIBENCH \\"
    echo "                      bash $BIG_BATCH"
    echo "[dry-run] per-rep profiler dispatch can be previewed directly with:"
    echo "          bash bench/run-intp-bench.sh --dry-run --env container-lxc \\"
    echo "               --variants $BENCH_VARIANTS --stage solo --workloads app01_ml_llc"
    exit 0
fi

exec bash "$BIG_BATCH"

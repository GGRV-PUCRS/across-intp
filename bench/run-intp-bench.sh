#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# run-intp-bench.sh -- Comprehensive IntP benchmark orchestrator.
#
# Reproduces the SBAC-PAD 2022 (Xavier & De Rose) experimental methodology
# across all seven IntP variants in this repository and across the three
# execution environments described in the dissertation Phase 3 plan
# (bare-metal, containerised, virtualised).
#
# Stages (each can be run in isolation via --stage NAME, multiple stages can
# be requested as a comma-separated list, default is "all"):
#
#   detect      Hardware capability detection + version manifest. Always run.
#   build       Build v2 / v3.1 / v3 binaries that are missing.
#   solo        SBAC-PAD "1-after-1" methodology -- single workload, no
#               co-runner. Reproduces Fig.3 (time series), Fig.4 (per-app bars),
#               Fig.5 (PCA + k-means).
#   pairwise    Antagonist + victim co-located -- ground truth for
#               cross-application interference, complementing Fig.8 of the
#               original paper. Captures both the profiler reading AND the victim's
#               throughput delta vs. its solo baseline.
#   overhead   Profiler runtime overhead (system-wide impact of running the
#               IntP profiler in real time on top of a deterministic workload).
#               Three layers of measurement, all on the same workload run with
#               and without each profiler attached:
#                 (A) workload throughput delta -- bogo ops/s parsed from
#                     stress-ng --metrics-brief.
#                 (B) profiler self-cost -- system-wide CPU jiffies delta from
#                     /proc/stat plus per-arm cgroup cpu.stat (when cgroup
#                     targeting is on).
#                 (C) Volpert-flavoured scheduler perturbation -- system-wide
#                     perf stat counts of context-switches, cpu-migrations and
#                     sched:sched_{wakeup,switch}, gated behind the
#                     --overhead-volpert flag.
#               Each rep shuffles the (ref x arm) order deterministically
#               from --seed so thermal/cache drift is averaged out across
#               reps. The first OVH_WARMUP seconds of every workload run are
#               head-start (profiler and gauges only sample the steady-state
#               window); both arms include the same warm-up so the delta
#               itself is unbiased.
#   timeseries  Long capture (default 10 min) per variant for a fixed mixed
#               workload, used for time-series figures.
#   report      Consolidate every run into TSVs ready for plot-intp-bench.py.
#
# All stages may be replayed inside containers or virtual machines via
# --env=bare,container,vm (default: bare). Environments with missing
# tooling are skipped and recorded in the run index; the script never lies
# about a result it could not produce.
#
# Designed for the Xeon Gold 5412U-class (Sapphire Rapids, 24C/48T,
# ~45 MB L3, 8 x DDR5-4800 ECC, 2 x 1.92 TB NVMe, 1 GbE) but does NOT assume
# specific device names -- everything is autodetected via shared/intp-detect.sh.
#
# Usage:
#   sudo ./run-intp-bench.sh                           # default full run
#   sudo ./run-intp-bench.sh --stage solo,report
#   sudo ./run-intp-bench.sh --variants v1,v2,v3 --env bare,container
#   sudo ./run-intp-bench.sh --duration 90 --reps 3
#   sudo ./run-intp-bench.sh --dry-run
#
# Output layout:
#   results/intp-bench-<ts>/
#       metadata.txt                # host/kernel/cpu/memory snapshot
#       capabilities.env            # eval'd output of intp-detect.sh
#       index.tsv                   # one row per (env,variant,stage,workload,rep)
#       <env>/<variant>/<stage>/<workload>/rep<R>/
#           profiler.tsv            # profiler output (7 metrics + ts)
#           groundtruth.tsv         # perf stat + resctrl + diskstat + netdev
#           workload.log            # workload stdout/err
#           run.json                # per-run metadata (durations, rc, samples)
# -----------------------------------------------------------------------------

set -euo pipefail

# -----------------------------------------------------------------------------
# 1. Paths and defaults
# -----------------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SHARED_DIR="$REPO_ROOT/shared"
DETECT_SH="$SHARED_DIR/intp-detect.sh"
RESCTRL_HELPER="$SHARED_DIR/intp-resctrl-helper.sh"

V0_STP="$REPO_ROOT/variants/v0-stap-2022/intp.stp"
V0_TEMPLATE="$REPO_ROOT/variants/v0-stap-2022/intp.stp.template"
V0_GENERATOR="$REPO_ROOT/variants/v0-stap-2022/generate-stp.sh"
V0_RECAL_STP="$REPO_ROOT/variants/v0-stap-2022/intp.recal.stp"
V0_1_STP="$REPO_ROOT/variants/v0.1-stap-nollc/intp-6.8.stp"
V0_2_TEMPLATE="$REPO_ROOT/variants/v0.2-legacy-intp-baseline/intp.stp.template"
V0_2_GENERATOR="$REPO_ROOT/variants/v0.2-legacy-intp-baseline/generate-stp.sh"
V0_2_RECAL_STP="$REPO_ROOT/variants/v0.2-legacy-intp-baseline/intp.recal.stp"
V0_2_HELPER="$REPO_ROOT/variants/v0.2-legacy-intp-baseline/intp-helper"
V1_STP="$REPO_ROOT/variants/v1-stap-nohelper/intp-resctrl.stp"
V1_1_STP="$REPO_ROOT/variants/v1.1-stap-modern/intp-v1.1.stp"
V1_1_HELPER="$REPO_ROOT/variants/v1.1-stap-modern/intp-helper"
V2_BIN="$REPO_ROOT/variants/v2-c-abi/intp-c-abi"
V2_1_BIN="$REPO_ROOT/variants/v2.1-c-abi-cgroup/intp-c-abi-cgroup"
V3_1_RUNNER="$REPO_ROOT/variants/v3.1-bpftrace/run-intp-bpftrace.sh"
V3_BIN="$REPO_ROOT/variants/v3-ebpf-ring/intp-ebpf-ring"
V3_2_BIN="$REPO_ROOT/variants/v3.2-ebpf-core/intp-ebpf-core"
V3_3_BIN="$REPO_ROOT/variants/v3.3-ebpf-core-cgroup/intp-ebpf-core-cgroup"

DEFAULT_STAGES="detect,build,solo,pairwise,overhead,timeseries,report"
DEFAULT_VARIANTS="v0,v0.1,v0.2,v1,v1.1,v2,v2.1,v3.1,v3,v3.2"
# Seven execution environments form three nested axes:
#   • where the WORKLOAD runs (host / container / VM)
#   • where the PROFILER runs (host-observer or in-guest)
#   • where the SUPPORTING STACK runs (HDFS+Spark on host vs in-container/VM)
#
#   bare              workload + profiler on host (HDFS + Spark on host)
#   container         workload in Docker, profiler on host (--pid=host)
#   container-podman  workload in rootful Podman (daemonless, OCI), profiler on
#                     host (--pid=host); host-visible cgroups => attributed like
#                     the docker env. No daemon to start or keep alive.
#   container-k8s     workload in a Kubernetes Pod (k3s), profiler on host; the
#                     DEEPEST cgroup nesting (kubepods.slice/.../cri-containerd-
#                     <id>.scope). Launcher resolves the in-pod stress-ng host
#                     PID via crictl; C17 self-resolves the deep cgroup. k3s is
#                     opt-in heavy (setup-host.sh --with-k8s) and DAEMON-FUL.
#   container-lxc     workload in an LXC/LXD (Incus) system container, profiler
#                     on host attached to the container CGROUP (the c-abi-cgroup
#                     path v2.1 / future v3.3 are built for); HDFS+Spark on host
#   container-guest   workload + profiler inside container (own PID namespace);
#                     HDFS + Spark still on host
#   container-full    workload + profiler + HDFS + Spark all inside one image
#                     (intp-full:latest); host-side HDFS/YARN MUST be paused
#                     via bench/deploy/host-services.sh pause
#   vm                workload in VM, profiler on host (measures qemu PID)
#   vm-guest          workload + profiler inside VM, results scp'd back;
#                     HDFS + Spark still on host
#   vm-full           workload + profiler + HDFS + Spark inside the VM;
#                     host-side HDFS/YARN MUST be paused
DEFAULT_ENVS="bare,container,vm"

STAGES_CSV="$DEFAULT_STAGES"
VARIANTS_CSV="$DEFAULT_VARIANTS"
ENVS_CSV="bare"   # bare only by default; user opts in to container/vm explicitly
WORKLOAD_FILTER=""
# Defaults are the SBAC-PAD campaign parameters (paper §IV-C): 12 reps, 90 s
# steady-state, 15 s warmup, 10 s cooldown, 600 s timeseries, 90 s overhead.
# run-big-batch.sh passes these explicitly; keeping them as the standalone
# defaults means a direct invocation reproduces the campaign setup.
DURATION=90
WARMUP=15
COOLDOWN=10
INTERVAL=1
REPS=12
TIMESERIES_DURATION=600
OVERHEAD_DURATION=90
# Head-start applied at the beginning of every overhead-stage workload run
# before any gauge starts sampling. Both baseline and with-profiler arms get
# the same head-start, so the steady-state delta is unbiased; the absolute
# bogo ops/s figure is conservative (averages over warm-up + steady-state).
OVH_WARMUP="${INTP_BENCH_OVH_WARMUP:-10}"
# Volpert-flavoured perf stat measurement (context-switches, cpu-migrations,
# sched:sched_{wakeup,switch}) is opt-in: it adds one perf process per arm.
OVERHEAD_VOLPERT=0
# Seed for reproducible per-rep shuffle of (ref x arm) order. Empty -> filled
# from $(date +%s) at start; persisted to metadata.txt for replay.
RUN_SEED="${INTP_BENCH_SEED:-}"
DRY_RUN=0
SKIP_BUILD=0
ALLOW_V0_ON_NEW_KERNEL=0
OUTPUT_DIR=""
# --portable-metrics (C26 / DESIGN §10): a SEPARATE benchmark that captures the
# 6 VM-portable metrics (schedlat psi_mem membw_est psi_io schedthr steal) into
# portable.tsv (instead of profiler.tsv) and aggregates them, header-aware, into
# aggregate-portable-means.tsv. The canonical 7-metric capture is untouched;
# only v2.1 and v3.3 implement --portable-metrics, so pair this with
# `--variants v2.1,v3.3`. Analyze with bench/analyze-portable.py.
PORTABLE_METRICS=0
W5=0

CONTAINER_IMAGE="${INTP_BENCH_CONTAINER:-ubuntu:24.04}"
# Podman (rootful, daemonless) engine for the container-podman env. PODMAN_BIN
# is the client (`podman`); PODMAN_IMAGE mirrors CONTAINER_IMAGE. Run as root
# (the harness runs as root) podman places containers in HOST-VISIBLE cgroup v2
# cgroups, so the host-side profiler attributes them exactly like docker.
PODMAN_BIN="${INTP_BENCH_PODMAN_BIN:-podman}"
PODMAN_IMAGE="${INTP_BENCH_PODMAN_IMAGE:-ubuntu:24.04}"
# Kubernetes (k3s) engine for the container-k8s env. KUBECTL is the API client
# (`kubectl`; on a k3s-only host `k3s kubectl` works as a fallback). CRICTL is
# the CRI client (`crictl`, bundled with k3s) used to resolve the in-pod
# stress-ng host-PID-namespace PID via `crictl inspect .info.pid`. K8S_IMAGE is
# the pod image; K8S_NS the namespace. This is the DEEPEST cgroup nesting
# (kubepods.slice/kubepods-<qos>.slice/kubepods-<qos>-pod<uid>.slice/
# cri-containerd-<id>.scope) -- C17's resolve_pid_cgroup() reads /proc/<pid>/
# cgroup so it self-resolves that deep path from the returned PID exactly as it
# does for docker/podman. k3s is opt-in heavy (see setup-host.sh --with-k8s);
# never installed by default.
KUBECTL="${INTP_BENCH_KUBECTL:-kubectl}"
CRICTL="${INTP_BENCH_CRICTL:-crictl}"
K8S_IMAGE="${INTP_BENCH_K8S_IMAGE:-docker.io/library/ubuntu:24.04}"
K8S_NS="${INTP_BENCH_K8S_NS:-intp-bench}"
# LXC/LXD (Incus) engine for the container-lxc env. Prefer incus (the modern,
# apt-installable LXD continuation) over the /usr/sbin/lxc LXD-snap shim: on
# Ubuntu 24.04 LXD is snap-only/bloated and frequently uninitialized (empty
# storage pool => instance creation fails "No root device could be found"),
# while incus ships via apt with the same client CLI. incus uses the 'images:'
# remote (LXD's 'ubuntu:' alias is absent), so pick the matching image. The
# launcher resolves the workload cgroup from /proc/<initpid>/cgroup, so it is
# agnostic to the engine's cgroup layout (lxc.payload.* etc.). Override with
# INTP_BENCH_LXC_BIN / INTP_BENCH_LXC_IMAGE.
# Resolve the engine FIRST (explicit override > prefer incus > lxc), THEN pick the
# default image off the RESOLVED engine, so an explicit INTP_BENCH_LXC_BIN=incus
# (without INTP_BENCH_LXC_IMAGE) still gets incus's 'images:' remote rather than
# LXD's absent 'ubuntu:' alias (which would fail to resolve).
if [ -n "${INTP_BENCH_LXC_BIN:-}" ]; then
    LXC_BIN="$INTP_BENCH_LXC_BIN"
elif command -v incus >/dev/null 2>&1; then
    LXC_BIN="incus"
else
    LXC_BIN="lxc"
fi
case "$LXC_BIN" in
    *incus*) LXC_IMAGE="${INTP_BENCH_LXC_IMAGE:-images:ubuntu/24.04}" ;;
    *)       LXC_IMAGE="${INTP_BENCH_LXC_IMAGE:-ubuntu:24.04}" ;;
esac
VM_IMAGE="${INTP_BENCH_VM_IMAGE:-}"           # qcow2 path, optional
# VM_CPUS / VM_MEM remain back-compat knobs; if unset they inherit
# BENCH_CPUS / BENCH_MEM (computed by _compute_default_resources). The
# env-var-defaulting form below preserves explicit overrides from the
# operator (INTP_BENCH_VM_CPUS=...) without trampling the cross-env
# parity values for the bare/container envs.
VM_MEM="${INTP_BENCH_VM_MEM:-}"
VM_CPUS="${INTP_BENCH_VM_CPUS:-}"
# Cross-env resource parity knobs. Defaults intentionally leave
# ~1/3 of host resources for the profiler, kernel, qemu/docker
# daemons, and IO buffers. Override per campaign as needed; the
# computed values flow into bare cgroups, container --cpus/--memory,
# and qemu -smp/-m so the three envs see the same theoretical
# resource pool.
BENCH_CPUS="${INTP_BENCH_CPUS:-}"     # vCPU count (all envs)
BENCH_MEM="${INTP_BENCH_MEM:-}"       # memory size, e.g. 192G (all envs)
# All-in-one image for env=container-full / vm-full (HDFS+Spark+IntP baked).
# Built via bench/deploy/build-full-image.sh.
INTP_FULL_IMAGE="${INTP_BENCH_FULL_IMAGE:-intp-full:latest}"
INTP_FULL_VM_IMAGE="${INTP_BENCH_FULL_VM_IMAGE:-}"  # qcow2 with full stack baked
# v2/v3 PID filtering against launcher PID tends to miss child workers and
# softirq-context activity; default to system-wide for representative samples.
V_USE_PID_FILTER="${INTP_BENCH_V_PID_FILTER:-0}"
# Run bare-metal workloads inside a dedicated cgroup and point v2/v3 to it.
# This improves attribution for child workers and resctrl-backed metrics.
USE_CGROUP_TARGETING="${INTP_BENCH_USE_CGROUP_TARGETING:-1}"
# Pin the CPU governor to 'performance' for every run by default -- frequency
# scaling is a top source of cross-rep variance, and run-hibench-subset.sh
# already does this unconditionally. setup_cpu_env saves the original
# governors and restore_cpu_env puts them back on exit. Set
# INTP_BENCH_SET_CPU_GOVERNOR=0 to disable on the rare Intel pstate host where
# sysfs governor writes can stall under load / RCU pressure.
SET_CPU_GOVERNOR="${INTP_BENCH_SET_CPU_GOVERNOR:-1}"
WAIT_TIMEOUT_S="${INTP_BENCH_WAIT_TIMEOUT_S:-45}"
SYSTEMTAP_READ_TIMEOUT_S="${INTP_BENCH_SYSTEMTAP_READ_TIMEOUT_S:-2}"
# Memory-bandwidth ceiling (bytes/sec) handed to v3/v3.2 via --mem-bw-max-bps
# so they normalise mbw correctly. Empty = derive from capabilities.env /
# shared/intp-detect.sh at first use (resolve_mem_bw_max_bps). The binaries do
# NOT convert units: --mem-bw-max-bps is bytes/sec while intp-detect.sh reports
# INTP_MEM_BW_MBPS in MB/s, so the ×1e6 conversion is done here, in the script.
MEM_BW_MAX_BPS="${INTP_BENCH_MEM_BW_MAX_BPS:-}"
_MEM_BW_MAX_BPS_RESOLVED=""

ACTIVE_RESCTRL_HELPER=0
CURRENT_WORKLOAD_CGROUP=""
# Set to the host tap interface name (intp-tap-<name>) while a VM workload is
# running under the optional tap-netdev path (INTP_BENCH_VM_TAP=1). Empty when
# the default SLIRP user-net is in use, in which case v3.3/v2.1 VM netp degrades
# to a system-wide observation.
CURRENT_VM_TAP_IFACE=""
# V1-specific: count stap runs and do a deep kernel-module cleanup every N
# runs to prevent stap_ module accumulation from draining the systemd DBus
# session budget (pam_systemd creates a scope per SSH login; if stap_ modules
# keep the previous session scope alive, DBus object counts grow unboundedly
# over a long campaign and eventually stall all new logins).
V3_RUN_COUNT=0
V3_DEEP_CLEANUP_EVERY="${INTP_BENCH_V3_DEEP_CLEANUP_EVERY:-5}"
# V0 (legacy classic stap) is at least as fragile as V1 — module accumulation
# and stapio orphans destabilise systemd-logind faster on 5.15 GA. Default to
# the periodic deep pause every rep (override with INTP_BENCH_V0_DEEP_CLEANUP_EVERY).
V0_RUN_COUNT=0
V0_DEEP_CLEANUP_EVERY="${INTP_BENCH_V0_DEEP_CLEANUP_EVERY:-1}"
_ORIG_GOVERNORS=""
_ORIG_AUTOGROUP=""

# -----------------------------------------------------------------------------
# 2. Workload matrix -- 15 workloads aligned with SBAC-PAD Table II.
#
# Format: id|category|stress-ng args
#
# Workers are sized for 24 physical cores. Stream and matrix workers are
# capped at 12 because each saturates a memory channel; cache_l3 and
# cpu_compute are scaled to 24 to drive full LLC and core pressure.
# -----------------------------------------------------------------------------

WORKLOADS=(
    "app01_ml_llc|LLC|--cache 24 --cache-level 3"
    "app02_ml_llc|LLC|--l1cache 24 --cache 12"
    "app03_ml_llc|LLC|--matrix 12 --matrix-size 1024"
    "app04_streaming|LLC/memory|--stream 12 --stream-madvise hugepage"
    "app05_streaming|LLC/memory|--stream 8 --vm 4 --vm-bytes 16G"
    "app06_ordering|memory|--qsort 16 --qsort-size 1048576"
    "app07_ordering|memory|--malloc 8 --malloc-bytes 16G"
    "app08_classification|CPU/memory|--vecmath 12 --vm 4 --vm-bytes 8G"
    "app09_classification|CPU/memory|--cpu 12 --cpu-method fft --vm 4 --vm-bytes 16G"
    "app10_search|CPU|--cpu 24 --cpu-method matrixprod"
    "app11_sort_net|network|--sock 16 --sock-port 23420"
    "app12_sort_net|network|--udp 16 --udp-port 23430"
    "app13_query_scan|disk|--hdd 8 --hdd-bytes 4G --hdd-write-size 1M"
    "app14_query_join|disk|--hdd 8 --hdd-bytes 2G --hdd-write-size 4K"
    "app15_query_merge|disk|--iomix 8 --iomix-bytes 2G"

    # ── scheduling-regime + memory-pressure profiles (C32): exercise the new
    #    dimensions of the 15-metric extended set that the resource-class spine
    #    under-drives. app16 OVERSUBSCRIBES the cores (96 >> 48 logical) so tasks
    #    are forced off while runnable -> psp / schedlat / idle_preempt fire in
    #    SOLO (not only under W5 colocation). app17 sustains a large anon
    #    footprint -> psi_mem reclaim WHEN run under a cgroup memory cap
    #    (container / colocation legs); ~0 uncapped on a 256G host (expected).
    "app16_cpu_oversub|CPU/sched|--cpu 96 --cpu-method matrixprod"
    "app17_mem_pressure|memory/psi|--vm 8 --vm-bytes 4G --vm-keep --vm-method all"

    # ── veth-routed network workloads (require setup-netns-pair.sh active) ──
    # Args format: VETH:<proto>:<port>:<extra iperf3 client args>
    # The launcher starts iperf3 server inside netns intp-net (10.42.0.2:<port>,
    # -1 = auto-exit on first client disconnect), then runs iperf3 client on
    # the host targeting 10.42.0.2. Traffic crosses intp-veth-h, generating
    # nonzero netp/nets in V2/V3/V3.1 (which filter `lo` but not `intp-veth-h`).
    "app11b_tcp_veth|network|VETH:tcp:23420:-P 16"
    "app12b_udp_veth|network|VETH:udp:23430:-P 16 -b 0"

    # ── Tier-B real-world: Redis key-value store (C32). Profiled = redis-server
    #    (the victim whose 15-metric fingerprint we measure); load = redis-benchmark
    #    driving it continuously (the noisy client, NOT profiled). apt-native on
    #    bare/container/vm-guest (no docker), so it runs in all three deployment
    #    classes. Exercises schedlat/psp/idle_preempt (request-driven wakeups +
    #    preemption) + netp/nets + cpu -- the IADA latency-sensitive narrative.
    #    Deps auto-provisioned by bench/setup/setup-redis-workload.sh.
    #    Format: REDIS:<port>:<redis-benchmark extra args>.
    "app18_redis_kv|kv-store|REDIS:7000:-c 50 -d 64 -t get,set,incr -P 8"
)

# Pairwise victim+antagonist pairs (id|victim_args|antagonist_args|expected_pressure)
# Victim is the lighter workload whose throughput we measure; antagonist
# saturates a specific resource so we can compute the resulting interference.
PAIRWISE=(
    "cpu_v_cache|--cpu 8 --cpu-method matrixprod|--cache 16 --cache-level 3|llc"
    "stream_v_stream|--stream 6|--stream 12|mbw"
    "disk_v_disk|--hdd 4 --hdd-bytes 2G --hdd-write-size 4K|--hdd 12 --hdd-bytes 4G --hdd-write-size 1M|blk"
    "net_v_net|--sock 8 --sock-port 23440|--sock 16 --sock-port 23450|netp"
    "cpu_v_mixed|--cpu 4 --cpu-method matrixprod|--cpu 8 --vm 4 --vm-bytes 16G --hdd 4 --hdd-bytes 2G|mixed"

    # Veth-routed pairwise: victim and antagonist hit different ports so they
    # coexist on the same veth without colliding. Both produce real NIC-side
    # traffic the V2+ probes can observe.
    "tcp_v_tcp_veth|VETH:tcp:23440:-P 8|VETH:tcp:23441:-P 16|netp"
)

# W5 colocation matrix (C29, --w5). Each spine VICTIM is co-located with the
# app05_streaming MEM-BANDWIDTH aggressor (the universal noisy neighbour). The
# pair id is `<victim_wl>__vs__<aggressor>` and the victim_args are IDENTICAL to
# that victim's solo WORKLOADS entry, so analyze-cross-deployment.py --w5 pairs
# pairwise/<id> against solo/<victim_wl> and reports victim-delta = pairwise-solo
# per metric (schedlat/psi_*/membw_est = primary contention signals). Run with
# `--w5 --stages pairwise --env bare,container,vm-guest` (portable metrics auto-on).
W5_PAIRWISE=(
    "app01_ml_llc__vs__app05_membw|--cache 24 --cache-level 3|--stream 8 --vm 4 --vm-bytes 16G|mbw"
    "app07_ordering__vs__app05_membw|--malloc 8 --malloc-bytes 16G|--stream 8 --vm 4 --vm-bytes 16G|mbw"
    "app10_search__vs__app05_membw|--cpu 24 --cpu-method matrixprod|--stream 8 --vm 4 --vm-bytes 16G|mbw"
    "app11_sort_net__vs__app05_membw|--sock 16 --sock-port 23420|--stream 8 --vm 4 --vm-bytes 16G|mbw"
    "app13_query_scan__vs__app05_membw|--hdd 8 --hdd-bytes 4G --hdd-write-size 1M|--stream 8 --vm 4 --vm-bytes 16G|mbw"
)

# Reference workloads for overhead measurement. These are deterministic, time-
# bounded, and produce a "throughput" number (op rate or MB/s) we can compare
# with vs. without the profiler attached.
OVERHEAD_REFS=(
    "ref_cpu|--cpu 24 --cpu-method matrixprod --metrics-brief"
    "ref_stream|--stream 12 --stream-madvise hugepage --metrics-brief"
    "ref_disk|--hdd 8 --hdd-bytes 1G --hdd-write-size 1M --metrics-brief"
)

# -----------------------------------------------------------------------------
# 3. Logging helpers
# -----------------------------------------------------------------------------

log()  { printf '[%s] %s\n' "$(date +%H:%M:%S)" "$*"; }
warn() { log "WARN: $*" >&2; }
die()  { log "FATAL: $*" >&2; exit 1; }

run_or_dry() {
    if [ "$DRY_RUN" -eq 1 ]; then
        log "DRY: $*"
    else
        "$@"
    fi
}

wait_pid_timeout() {
    # $1 pid, $2 timeout_s, $3 label
    local pid="$1" timeout_s="$2" label="${3:-process}"
    [ "$DRY_RUN" -eq 1 ] && return 0
    case "$pid" in
        ''|0|*[!0-9]*) return 0 ;;
    esac

    local end=$((SECONDS + timeout_s))
    while kill -0 "$pid" 2>/dev/null; do
        if [ "$SECONDS" -ge "$end" ]; then
            warn "[$label] timeout waiting for pid=$pid after ${timeout_s}s"
            return 1
        fi
        sleep 1
    done
    wait "$pid" 2>/dev/null || true
    return 0
}

terminate_pid_gracefully() {
    # $1 pid, $2 label
    local pid="$1" label="${2:-process}"
    [ "$DRY_RUN" -eq 1 ] && return 0
    case "$pid" in
        ''|0|*[!0-9]*) return 0 ;;
    esac

    kill -TERM "$pid" 2>/dev/null || true
    if wait_pid_timeout "$pid" "$WAIT_TIMEOUT_S" "$label/term"; then
        return 0
    fi

    warn "[$label] escalating to SIGKILL pid=$pid"
    kill -KILL "$pid" 2>/dev/null || true
    if wait_pid_timeout "$pid" 10 "$label/kill"; then
        return 2
    fi

    warn "[$label] could not reap pid=$pid after SIGKILL"
    return 3
}

# -----------------------------------------------------------------------------
# 4. CLI parsing
# -----------------------------------------------------------------------------

usage() {
    cat <<EOF
Usage: sudo $0 [options]

Stages (--stage CSV, default: $DEFAULT_STAGES):
  detect, build, solo, pairwise, overhead, timeseries, report

Selection:
  --variants CSV           Variants to run (default: $DEFAULT_VARIANTS)
  --env CSV                Execution environments (default: bare;
                           allowed: bare,container,container-podman,container-k8s,container-lxc,vm,...)
  --workloads CSV          Workload IDs (default: all)

Timing:
  --duration SECONDS       Per-workload sampling duration (default: $DURATION)
  --warmup SECONDS         Warmup before sampling (default: $WARMUP)
  --cooldown SECONDS       Cooldown between runs (default: $COOLDOWN)
  --interval SECONDS       Sampling interval, fractional allowed e.g. 0.5 (default: $INTERVAL)
  --reps N                 Repetitions per (env,variant,workload) (default: $REPS)
  --timeseries-duration S  Long-trace duration (default: $TIMESERIES_DURATION)
  --overhead-duration S    Overhead-microbench steady-state window (default: $OVERHEAD_DURATION)
  --overhead-warmup S      Head-start before sampling (default: $OVH_WARMUP)
  --overhead-volpert       Enable Volpert-flavoured perf stat (context-switches,
                           cpu-migrations, sched:sched_{wakeup,switch}) per arm
  --seed N                 Seed for per-rep shuffle of (ref x arm) order
                           (default: \$INTP_BENCH_SEED or wall clock)

Other:
  --output-dir DIR         Override output dir
  --container-image IMG    Container image (default: $CONTAINER_IMAGE)
  --vm-image PATH          qcow2 image for VM env (required when env=vm)
  --vm-mem SIZE            VM memory (default: inherits --bench-mem)
  --vm-cpus N              VM CPU count (default: inherits --bench-cpus)
  --bench-cpus N           Parity knob: vCPUs visible to bare (cgroup cpu.max),
                           container (--cpus), and VM (-smp). Defaults to
                           floor(nproc * 2/3). Honors INTP_BENCH_CPUS env.
  --bench-mem SIZE         Parity knob: memory cap for bare (cgroup memory.max),
                           container (--memory), and VM (-m). Defaults to
                           floor(MemTotal * 2/3). Honors INTP_BENCH_MEM env.
    env INTP_BENCH_SET_CPU_GOVERNOR=0
                                                    Disable governor pinning (default: on -> 'performance')
  --skip-build             Do not auto-build missing variants
  --allow-v0               Allow V0 on kernel >= 6.8 (will fail at runtime)
  --portable-metrics       SEPARATE VM-portable benchmark (C26): capture the 6
                           portable metrics (schedlat psi_mem membw_est psi_io
                           schedthr steal) into portable.tsv + aggregate-portable-
                           means.tsv. Canonical 7-metric capture untouched. Only
                           v2.1 / v3.3 implement it -> use --variants v2.1,v3.3.
                           Analyze with bench/analyze-portable.py.
  --w5                     W5 colocation campaign (C29): replace the pairwise matrix
                           with each spine victim co-located against the app05_streaming
                           mem-bandwidth aggressor (pairs <victim>__vs__app05_membw);
                           implies --portable-metrics. Run into the SOLO campaign dir
                           with `--w5 --stages pairwise --env bare,container,vm-guest
                           --variants v2.1,v3.3`. Analyze with
                           bench/analyze-cross-deployment.py --w5 (victim-delta vs solo).
  --dry-run                Print actions without executing
  -h, --help               Show this help

Examples:
  sudo $0
  sudo $0 --stage solo,report --variants v2,v3.1,v3
  sudo $0 --env bare,container --workloads app01_ml_llc,app10_search
  sudo $0 --stage overhead --reps 5
  sudo $0 --portable-metrics --variants v2.1,v3.3 --env bare,container,vm-guest \\
          --stage solo,report
EOF
}

split_csv() {
    local csv="$1"
    local -n out_ref="$2"
    local IFS_BAK="$IFS"
    IFS=',' read -r -a out_ref <<< "$csv"
    IFS="$IFS_BAK"
}

validate_positive_int() {
    local name="$1" value="$2"
    case "$value" in
        ''|*[!0-9]*)
            die "Invalid --$name value: '$value' (must be a positive integer, e.g. --$name 30)"
            ;;
        0)
            die "Invalid --$name value: '$value' (must be >= 1)"
            ;;
    esac
}

# Like validate_positive_int but accepts a positive DECIMAL (e.g. 0.1, 0.25, 1.5)
# as well as integers. Used for --interval so the cadence sweep can request
# sub-second sampling; the profiler binaries take a fractional interval_sec, and
# sleep / the ms conversion both handle floats.
validate_positive_number() {
    local name="$1" value="$2"
    awk -v v="$value" 'BEGIN { if (v ~ /^[0-9]+(\.[0-9]+)?$/ && v+0 > 0) exit 0; exit 1 }' \
        || die "Invalid --$name value: '$value' (must be a positive number, e.g. --$name 0.5 or 30)"
}

parse_args() {
    while [ $# -gt 0 ]; do
        case "$1" in
            --stage|--stages)        STAGES_CSV="$2"; shift 2 ;;
            --variants)              VARIANTS_CSV="$2"; shift 2 ;;
            --env|--envs)            ENVS_CSV="$2"; shift 2 ;;
            --workloads)             WORKLOAD_FILTER="$2"; shift 2 ;;
            --duration)              DURATION="$2"; shift 2 ;;
            --warmup)                WARMUP="$2"; shift 2 ;;
            --cooldown)              COOLDOWN="$2"; shift 2 ;;
            --interval)              INTERVAL="$2"; shift 2 ;;
            --reps)                  REPS="$2"; shift 2 ;;
            --timeseries-duration)   TIMESERIES_DURATION="$2"; shift 2 ;;
            --overhead-duration)     OVERHEAD_DURATION="$2"; shift 2 ;;
            --overhead-warmup)       OVH_WARMUP="$2"; shift 2 ;;
            --overhead-volpert)      OVERHEAD_VOLPERT=1; shift ;;
            --seed)                  RUN_SEED="$2"; shift 2 ;;
            --output-dir)            OUTPUT_DIR="$2"; shift 2 ;;
            --container-image)       CONTAINER_IMAGE="$2"; shift 2 ;;
            --vm-image)              VM_IMAGE="$2"; shift 2 ;;
            --vm-mem)                VM_MEM="$2"; shift 2 ;;
            --vm-cpus)               VM_CPUS="$2"; shift 2 ;;
            --bench-cpus)            BENCH_CPUS="$2"; shift 2 ;;
            --bench-mem)             BENCH_MEM="$2"; shift 2 ;;
            --skip-build)            SKIP_BUILD=1; shift ;;
            --allow-v0)              ALLOW_V0_ON_NEW_KERNEL=1; shift ;;
            --portable-metrics)      PORTABLE_METRICS=1; shift ;;
            --w5)                    W5=1; PORTABLE_METRICS=1; shift ;;
            --dry-run)               DRY_RUN=1; shift ;;
            -h|--help)               usage; exit 0 ;;
            *) die "Unknown option: $1" ;;
        esac
    done

    if [ "$W5" = "1" ]; then
        PAIRWISE=( "${W5_PAIRWISE[@]}" )
        log "W5 colocation mode: ${#PAIRWISE[@]} victim-vs-aggressor pairs (mem-bandwidth neighbour), portable metrics ON"
    fi

    validate_positive_int duration "$DURATION"
    validate_positive_int warmup "$WARMUP"
    validate_positive_int cooldown "$COOLDOWN"
    validate_positive_number interval "$INTERVAL"
    validate_positive_int reps "$REPS"
    validate_positive_int timeseries-duration "$TIMESERIES_DURATION"
    validate_positive_int overhead-duration "$OVERHEAD_DURATION"
    case "$OVH_WARMUP" in
        ''|*[!0-9]*) die "Invalid --overhead-warmup value: '$OVH_WARMUP' (non-negative integer)" ;;
    esac
    # VM_CPUS may be empty here; it is resolved to BENCH_CPUS by
    # _compute_default_resources before any launcher reads it. Validate the
    # explicit-override path only.
    if [ -n "$VM_CPUS" ]; then validate_positive_int vm-cpus "$VM_CPUS"; fi
    if [ -n "$BENCH_CPUS" ]; then validate_positive_int bench-cpus "$BENCH_CPUS"; fi
    if [ -z "$RUN_SEED" ]; then RUN_SEED="$(date +%s)"; fi
    case "$RUN_SEED" in
        ''|*[!0-9]*) die "Invalid --seed value: '$RUN_SEED' (must be a non-negative integer)" ;;
    esac

    split_csv "$STAGES_CSV" STAGES
    split_csv "$VARIANTS_CSV" VARIANTS
    split_csv "$ENVS_CSV" ENVS
    if [ -n "$WORKLOAD_FILTER" ]; then
        split_csv "$WORKLOAD_FILTER" WORKLOAD_NAMES
    else
        WORKLOAD_NAMES=()
    fi
}

stage_enabled() {
    local s
    for s in "${STAGES[@]}"; do
        [ "$s" = "$1" ] && return 0
        [ "$s" = "all" ] && return 0
    done
    return 1
}

variant_selected() {
    local v
    for v in "${VARIANTS[@]}"; do
        [ "$v" = "$1" ] && return 0
    done
    return 1
}

workload_selected() {
    [ ${#WORKLOAD_NAMES[@]} -eq 0 ] && return 0
    local w
    for w in "${WORKLOAD_NAMES[@]}"; do
        [ "$w" = "$1" ] && return 0
    done
    return 1
}

# -----------------------------------------------------------------------------
# 5. Preflight
# -----------------------------------------------------------------------------

ensure_root() {
    [ "$DRY_RUN" -eq 1 ] && return 0
    [ "$(id -u)" = "0" ] || die "Must be run as root (profilers need PMU/resctrl/perf access)"
}

ensure_basic_deps() {
    [ "$DRY_RUN" -eq 1 ] && return 0
    for cmd in stress-ng awk grep sed jq; do
        command -v "$cmd" >/dev/null 2>&1 || die "Missing dependency: $cmd"
    done
    command -v perf >/dev/null 2>&1 || warn "perf not found -- groundtruth.tsv will be partial"
    command -v iostat >/dev/null 2>&1 || warn "sysstat (iostat) not found -- some side-channel data will be missing"
}

ensure_perf_paranoid() {
    [ "$DRY_RUN" -eq 1 ] && return 0
    local p
    p=$(cat /proc/sys/kernel/perf_event_paranoid 2>/dev/null || echo 4)
    if [ "$p" -gt -1 ]; then
        log "Lowering perf_event_paranoid from $p to -1 (required for IMC uncore counters)"
        echo -1 > /proc/sys/kernel/perf_event_paranoid
    fi
}

# Compute cross-env CPU / memory budget and pipe it through to the bare,
# container, and VM launchers. Honors operator overrides (CLI flag,
# INTP_BENCH_CPUS / INTP_BENCH_MEM env, INTP_BENCH_VM_CPUS / VM_MEM env)
# and defaults to 2/3 of the host, leaving ~1/3 for the profiler, kernel,
# qemu/docker daemons, and IO buffers.
_compute_default_resources() {
    if [ -z "$BENCH_CPUS" ]; then
        local nproc_total
        nproc_total=$(nproc 2>/dev/null || echo 1)
        BENCH_CPUS=$(( nproc_total * 2 / 3 ))
        [ "$BENCH_CPUS" -lt 1 ] && BENCH_CPUS=1
    fi
    if [ -z "$BENCH_MEM" ]; then
        local mem_kb mem_gb
        mem_kb=$(awk '/^MemTotal:/ {print $2; exit}' /proc/meminfo 2>/dev/null || echo 0)
        mem_gb=$(( mem_kb / 1024 / 1024 ))
        local budget_gb=$(( mem_gb * 2 / 3 ))
        [ "$budget_gb" -lt 2 ] && budget_gb=2
        BENCH_MEM="${budget_gb}G"
    fi
    # Validate BENCH_CPUS as positive int; BENCH_MEM is forwarded verbatim
    # to docker --memory / qemu -m so we let those tools validate the suffix.
    case "$BENCH_CPUS" in
        ''|*[!0-9]*) die "BENCH_CPUS must be a positive integer (got '$BENCH_CPUS')" ;;
        0)           die "BENCH_CPUS must be >= 1" ;;
    esac
    # Back-compat alias: VM_CPUS / VM_MEM inherit BENCH_* unless the operator
    # set them explicitly via --vm-cpus / --vm-mem / INTP_BENCH_VM_*.
    [ -z "$VM_CPUS" ] && VM_CPUS="$BENCH_CPUS"
    [ -z "$VM_MEM" ]  && VM_MEM="$BENCH_MEM"
    case "$VM_CPUS" in
        ''|*[!0-9]*) die "VM_CPUS must be a positive integer (got '$VM_CPUS')" ;;
        0)           die "VM_CPUS must be >= 1" ;;
    esac
    log "[resources] BENCH_CPUS=$BENCH_CPUS BENCH_MEM=$BENCH_MEM (VM_CPUS=$VM_CPUS VM_MEM=$VM_MEM)"
}

setup_cpu_env() {
    [ "$DRY_RUN" -eq 1 ] && return 0
    if [ "$SET_CPU_GOVERNOR" != "1" ]; then
        log "[cpu_env] governor pinning disabled via INTP_BENCH_SET_CPU_GOVERNOR=0 (default is on -> performance)"
    else
    local gov_path gov count=0
    for gov_path in /sys/devices/system/cpu/cpu[0-9]*/cpufreq/scaling_governor; do
        [ -f "$gov_path" ] || continue
        gov=$(cat "$gov_path" 2>/dev/null || echo unknown)
        _ORIG_GOVERNORS="${_ORIG_GOVERNORS}${gov_path}=${gov}
"
        echo performance > "$gov_path" 2>/dev/null || true
        count=$((count+1))
    done
    if [ "$count" -gt 0 ]; then
        local first_gov
        first_gov=$(printf '%s\n' "$_ORIG_GOVERNORS" | head -1 | cut -d= -f2)
        log "[cpu_env] governor → performance (was: $first_gov on $count cpus)"
    else
        log "[cpu_env] no cpufreq sysfs — governor unchanged"
    fi
    fi
    _ORIG_AUTOGROUP=$(cat /proc/sys/kernel/sched_autogroup_enabled 2>/dev/null || echo 1)
    if [ "$_ORIG_AUTOGROUP" = "1" ]; then
        echo 0 > /proc/sys/kernel/sched_autogroup_enabled 2>/dev/null || true
        log "[cpu_env] sched_autogroup_enabled → 0"
    fi
}

restore_cpu_env() {
    [ "$DRY_RUN" -eq 1 ] && return 0
    local entry gov_path gov
    while IFS= read -r entry; do
        [ -z "$entry" ] && continue
        gov_path="${entry%%=*}"
        gov="${entry#*=}"
        [ -f "$gov_path" ] && echo "$gov" > "$gov_path" 2>/dev/null || true
    done <<< "$_ORIG_GOVERNORS"
    [ -n "$_ORIG_GOVERNORS" ] && log "[cpu_env] governor restored"
    [ -n "$_ORIG_AUTOGROUP" ] && echo "$_ORIG_AUTOGROUP" > /proc/sys/kernel/sched_autogroup_enabled 2>/dev/null || true
}

prepare_output_dir() {
    if [ -z "$OUTPUT_DIR" ]; then
        OUTPUT_DIR="$REPO_ROOT/results/intp-bench-$(date +%Y%m%d_%H%M%S)"
    fi
    mkdir -p "$OUTPUT_DIR"
    INDEX="$OUTPUT_DIR/index.tsv"
    if [ ! -f "$INDEX" ]; then
        printf 'env\tvariant\tstage\tworkload\trep\tstart_iso\tduration_s\trc\tsamples\tprofiler_path\tgroundtruth_path\tnotes\ttarget_scope\n' > "$INDEX"
    fi
}

write_metadata() {
    {
        echo "# intp-bench metadata"
        echo "date=$(date -Iseconds)"
        echo "host=$(hostname)"
        echo "kernel=$(uname -r)"
        echo "os=$(. /etc/os-release 2>/dev/null && echo "${PRETTY_NAME:-unknown}")"
        echo "cpu=$(lscpu 2>/dev/null | awk -F: '/Model name/{print $2}' | xargs | head -1)"
        echo "sockets=$(lscpu 2>/dev/null | awk -F: '/^Socket/{print $2}' | xargs)"
        echo "cores_online=$(nproc)"
        echo "mem_total_gb=$(awk '/MemTotal/{printf "%.0f\n",$2/1024/1024}' /proc/meminfo)"
        echo "stress_ng_version=$(stress-ng --version 2>/dev/null | head -1 || echo missing)"
        echo "stages=$STAGES_CSV"
        echo "variants=$VARIANTS_CSV"
        echo "envs=$ENVS_CSV"
        echo "workloads=${WORKLOAD_FILTER:-all}"
        echo "duration=$DURATION warmup=$WARMUP cooldown=$COOLDOWN interval=$INTERVAL reps=$REPS"
        echo "timeseries_duration=$TIMESERIES_DURATION overhead_duration=$OVERHEAD_DURATION"
        echo "overhead_warmup=$OVH_WARMUP overhead_volpert=$OVERHEAD_VOLPERT run_seed=$RUN_SEED"
        echo "container_image=$CONTAINER_IMAGE"
        echo "vm_image=${VM_IMAGE:-none} vm_mem=$VM_MEM vm_cpus=$VM_CPUS"
        echo "set_cpu_governor=$SET_CPU_GOVERNOR"
    } > "$OUTPUT_DIR/metadata.txt"

    if [ -x "$DETECT_SH" ]; then
        "$DETECT_SH" > "$OUTPUT_DIR/capabilities.env" || true
    fi

    # Per-variant version manifest (helps detect tooling drift across runs)
    {
        printf '# variant manifest\n'
        printf 'variant\tpath\tsha256\tmtime\n'
        for v in v0 v0.1 v0.2 v1 v1.1 v2 v2.1 v3.1 v3 v3.2 v3.3; do
            local p
            case "$v" in
                v0) p="$V0_STP" ;;
                v0.1) p="$V0_1_STP" ;;
                v0.2) p="$V0_2_TEMPLATE" ;;
                v1) p="$V1_STP" ;;
                v1.1) p="$V1_1_STP" ;;
                v2) p="$V2_BIN" ;;
                v2.1) p="$V2_1_BIN" ;;
                v3.1) p="$V3_1_RUNNER" ;;
                v3) p="$V3_BIN" ;;
                v3.2) p="$V3_2_BIN" ;;
                v3.3) p="$V3_3_BIN" ;;
            esac
            if [ -f "$p" ] || [ -x "$p" ]; then
                printf '%s\t%s\t%s\t%s\n' "$v" "$p" \
                    "$(sha256sum "$p" 2>/dev/null | awk '{print $1}')" \
                    "$(stat -c %y "$p" 2>/dev/null)"
            else
                printf '%s\t%s\t-\t-\n' "$v" "$p"
            fi
        done
    } > "$OUTPUT_DIR/variants.manifest"
}

# -----------------------------------------------------------------------------
# 6. Build stage
# -----------------------------------------------------------------------------

stage_build() {
    log "== build =="
    if [ "$SKIP_BUILD" -eq 1 ]; then
        log "  --skip-build set; nothing to do"
        return 0
    fi
    if variant_selected v2 && [ ! -x "$V2_BIN" ]; then
        log "Building v2..."
        run_or_dry make -C "$REPO_ROOT/variants/v2-c-abi"
    fi
    if variant_selected v2.1 && [ ! -x "$V2_1_BIN" ]; then
        log "Building v2.1 (c-abi-cgroup)..."
        run_or_dry make -C "$REPO_ROOT/variants/v2.1-c-abi-cgroup"
    fi
    if variant_selected v3.2 && [ ! -x "$V3_2_BIN" ]; then
        log "Building v3.2 (eBPF in-kernel aggregating)…"
        run_or_dry make -C "$REPO_ROOT/variants/v3.2-ebpf-core"
    fi
    if variant_selected v3.3 && [ ! -x "$V3_3_BIN" ]; then
        log "Building v3.3 (eBPF c-abi-cgroup)…"
        run_or_dry make -C "$REPO_ROOT/variants/v3.3-ebpf-core-cgroup"
    fi
    if variant_selected v3 && [ ! -x "$V3_BIN" ]; then
        log "Building v3..."
        run_or_dry make -C "$REPO_ROOT/variants/v3-ebpf-ring"
    fi
    if variant_selected v1.1 && [ ! -x "$V1_1_HELPER" ]; then
        log "Building v1.1 helper..."
        run_or_dry make -C "$REPO_ROOT/variants/v1.1-stap-modern"
    fi
    if variant_selected v0.2 && [ ! -x "$V0_2_HELPER" ]; then
        log "Building v0.2 helper..."
        run_or_dry make -C "$REPO_ROOT/variants/v0.2-legacy-intp-baseline"
    fi
    if variant_selected v0 && [ ! -f "$V0_STP" ]; then warn "v0 selected but $V0_STP missing"; fi
    if variant_selected v0 && [ ! -f "$V0_TEMPLATE" ]; then warn "v0 selected but $V0_TEMPLATE missing"; fi
    if variant_selected v0 && [ ! -x "$V0_GENERATOR" ]; then warn "v0 selected but $V0_GENERATOR not executable"; fi
    if variant_selected v0.1 && [ ! -f "$V0_1_STP" ]; then warn "v0.1 selected but $V0_1_STP missing"; fi
    if variant_selected v0.2 && [ ! -f "$V0_2_TEMPLATE" ]; then warn "v0.2 selected but $V0_2_TEMPLATE missing"; fi
    if variant_selected v0.2 && [ ! -x "$V0_2_GENERATOR" ]; then warn "v0.2 selected but $V0_2_GENERATOR not executable"; fi
    if variant_selected v1 && [ ! -f "$V1_STP" ]; then warn "v1 selected but $V1_STP missing"; fi
    if variant_selected v1.1 && [ ! -f "$V1_1_STP" ]; then warn "v1.1 selected but $V1_1_STP missing"; fi
    if variant_selected v3.1 && [ ! -x "$V3_1_RUNNER" ]; then warn "v3.1 selected but runner $V3_1_RUNNER not executable"; fi
    if variant_selected v3.3 && [ ! -x "$V3_3_BIN" ]; then warn "v3.3 selected but $V3_3_BIN missing (build failed or not built)"; fi
}

# -----------------------------------------------------------------------------
# 7. Variant gating -- which kernel/env combinations are valid
# -----------------------------------------------------------------------------

_kernel_ge() {
    # _kernel_ge MAJOR MINOR  →  return 0 if running kernel ≥ MAJOR.MINOR
    local want_maj="$1" want_min="$2"
    local k cur_maj cur_min
    k=$(uname -r | cut -d. -f1-2)
    cur_maj=${k%.*}; cur_min=${k#*.}
    [ "$cur_maj" -gt "$want_maj" ] && return 0
    [ "$cur_maj" -eq "$want_maj" ] && [ "$cur_min" -ge "$want_min" ] && return 0
    return 1
}

_kernel_lt() {
    # _kernel_lt MAJOR MINOR  →  return 0 if running kernel < MAJOR.MINOR
    ! _kernel_ge "$@"
}

variant_kernel_ok() {
    # Per-variant kernel-version compatibility gate. Returns 0 (OK) or 1 (skip).
    # Floor and ceiling reflect tested support; degraded operation outside the
    # window is possible but not promised.
    local variant="$1"
    local k; k=$(uname -r)
    case "$variant" in
        v0)
            # SystemTap with embedded C calling perf_event_create_kernel_counter
            # broke on kernel ≥6.8 (cqm_rmid removed, MSR header relocations).
            # Floor 4.19 — original IntP development era.
            if [ "$ALLOW_V0_ON_NEW_KERNEL" -eq 1 ]; then return 0; fi
            if _kernel_lt 4 19; then warn "v0 needs kernel ≥4.19 (have $k)"; return 1; fi
            if _kernel_ge 6 8;  then warn "v0 incompatible with kernel ≥6.8 (have $k); use v0.1"; return 1; fi
            ;;
        v0.1)
            # Kernel-6.8 port of v0; same 4.19 floor.
            if _kernel_lt 4 19; then warn "v0.1 needs kernel ≥4.19 (have $k)"; return 1; fi
            ;;
        v0.2)
            # V0 semantics with userspace helper for the RCU-unsafe IMC/RDT
            # operations. Target kernel is 5.15 GA (Ubuntu 22.04). On kernel
            # ≥6.8 cqm_rmid is gone -- but v0.2 doesn't use cqm_rmid (resctrl
            # path via the helper), so technically it could run there. Cap at
            # <6.0 anyway: the entire point of v0.2 is to be the U22/5.15 leg
            # of the experiment; on 6.x v1.1 is the right variant.
            if _kernel_lt 5 10; then warn "v0.2 needs kernel ≥5.10 (have $k)"; return 1; fi
            if _kernel_ge 6 0;  then warn "v0.2 targets U22/5.15 GA; on kernel ≥6.0 use v1.1"; return 1; fi
            ;;
        v1)
            # Native SystemTap module; same floor as v0, same ceiling.
            if _kernel_lt 4 19; then warn "v1 needs kernel ≥4.19 (have $k)"; return 1; fi
            if _kernel_ge 6 8;  then warn "v1 incompatible with kernel ≥6.8 (have $k); use v1.1"; return 1; fi
            ;;
        v1.1)
            # Helper-bridged stap; perf_event_open via userspace helper avoids
            # the kernel-≥6.8 RCU stall path. Floor still 4.19 for SystemTap.
            if _kernel_lt 4 19; then warn "v1.1 needs kernel ≥4.19 (have $k)"; return 1; fi
            ;;
        v2)
            # Hybrid procfs+resctrl+perf_event_open. Floor 5.8 because
            # CAP_PERFMON (and unprivileged perf_event_open) were introduced
            # in 5.8 — earlier kernels need root or paranoid≤1.
            if _kernel_lt 5 8;  then warn "v2 needs kernel ≥5.8 (CAP_PERFMON)"; return 1; fi
            ;;
        v2.1)
            # V2 + continuous c-abi-cgroup attribution (cpu.stat, io.stat,
            # perf cgroup mode). Same 5.8 floor as v2 (CAP_PERFMON), and needs
            # the cgroup v2 unified hierarchy for cpu.stat / io.stat.
            if _kernel_lt 5 8;  then warn "v2.1 needs kernel ≥5.8 (CAP_PERFMON + cgroup v2)"; return 1; fi
            ;;
        v3)
            # libbpf + CO-RE eBPF with BTF. Practical floor 5.10 for stable
            # libbpf + reliable kfunc/tp_btf attach.
            if _kernel_lt 5 10; then warn "v3 needs kernel ≥5.10 (libbpf+CO-RE)"; return 1; fi
            if [ ! -f /sys/kernel/btf/vmlinux ]; then
                warn "v3 needs CONFIG_DEBUG_INFO_BTF=y (no /sys/kernel/btf/vmlinux)"
                return 1
            fi
            ;;
        v3.1)
            # bpftrace ≥0.13 over kernel ≥5.4 (tracepoints + BPF maps stable).
            if _kernel_lt 5 4;  then warn "v3.1 needs kernel ≥5.4 (bpftrace tracepoints)"; return 1; fi
            ;;
        v3.2)
            # Same kernel constraints as v3: libbpf + CO-RE eBPF with BTF.
            # The in-kernel aggregation maps (PERCPU_ARRAY, HASH with
            # __sync_fetch_and_add) have been available since 5.4; we
            # keep the 5.10 floor for consistency with v3.
            if _kernel_lt 5 10; then warn "v3.2 needs kernel ≥5.10 (libbpf+CO-RE)"; return 1; fi
            if [ ! -f /sys/kernel/btf/vmlinux ]; then
                warn "v3.2 needs CONFIG_DEBUG_INFO_BTF=y (no /sys/kernel/btf/vmlinux)"
                return 1
            fi
            ;;
        v3.3)
            # eBPF c-abi-cgroup. cgroup/skb + cgroup BPF attach is stable from
            # 5.8 (matching the v2.1 cgroup-v2 floor); CO-RE needs BTF. The
            # per-cgroup netp tap attach wants CAP_NET_ADMIN, but that is a
            # soft requirement: without it netp degrades, so warn (don't fail).
            if _kernel_lt 5 8;  then warn "v3.3 needs kernel ≥5.8 (cgroup-BPF + cgroup v2)"; return 1; fi
            if [ ! -f /sys/kernel/btf/vmlinux ]; then
                warn "v3.3 needs CONFIG_DEBUG_INFO_BTF=y (no /sys/kernel/btf/vmlinux)"
                return 1
            fi
            if command -v capsh >/dev/null 2>&1; then
                if ! capsh --print 2>/dev/null | grep -q 'cap_net_admin'; then
                    warn "v3.3: CAP_NET_ADMIN not present; per-cgroup netp tap attach may degrade"
                fi
            elif [ "$(id -u)" -ne 0 ]; then
                warn "v3.3: not root and capsh unavailable; CAP_NET_ADMIN unverified, netp may degrade"
            fi
            ;;
    esac
    return 0
}

variant_env_ok() {
    local variant="$1" env="$2"
    case "$env" in
        vm|container|container-podman|container-k8s|container-lxc)
            # Host-observer modes: profiler runs on host attached to qemu /
            # container PID or cgroup. Any variant works (container-lxc is
            # cgroup-first: c-abi-cgroup variants attach to the container
            # cgroup, --pids-only variants to the container init PID).
            # container-podman is the docker analog on a daemonless, OCI runtime:
            # rootful podman puts the container in host-visible cgroups, so the
            # profiler attributes its PID/cgroup exactly like the docker env.
            # container-k8s is a k3s Pod: the deepest cgroup nesting (kubepods
            # .slice/.../cri-containerd-<id>.scope). The launcher resolves the
            # in-pod stress-ng host PID via crictl; C17's resolve_pid_cgroup
            # self-resolves that deep cgroup for v3.3, v2.1/v3.2 use --pids.
            return 0
            ;;
        container-guest)
            # In-container profiler: needs CAP_BPF/CAP_PERFMON for v2/v3,
            # CAP_SYS_ADMIN + host kernel modules for stap. Already plumbed
            # in launch_workload_container_guest. Allow all variants and
            # let the run fail if the host kernel doesn't expose what's
            # needed (already filtered upstream by variant_kernel_ok).
            return 0
            ;;
        vm-guest)
            # In-guest profiler runs inside the VM. RDT (mbw, llcocc) is
            # typically unavailable to the guest unless the host configures
            # vRDT pass-through, so v2 metrics may degrade. v3 requires the
            # qcow2 to expose BTF (most cloud images do). v0/v0.1/v1 stap
            # need kernel-headers in guest -- skip unless explicitly opted
            # via INTP_VMG_ALLOW_STAP=1.
            case "$variant" in
                v0|v0.1|v0.2|v1)
                    if [ "${INTP_VMG_ALLOW_STAP:-0}" != "1" ]; then
                        warn "$variant on vm-guest needs guest-side stap+headers; "\
"set INTP_VMG_ALLOW_STAP=1 if your qcow2 has them"
                        return 1
                    fi
                    ;;
            esac
            return 0
            ;;
    esac
    return 0
}

# -----------------------------------------------------------------------------
# 8. Ground-truth side-channel capture
#
# For each profiler sample window we also collect the reference signals the
# profiler is meant to estimate. Plot script computes per-metric absolute
# error and Pearson correlation against this ground truth.
# -----------------------------------------------------------------------------

start_groundtruth() {
    # $1 outdir, $2 duration, $3 target_pid (0 = system-wide)
    local outdir="$1" duration="$2" target_pid="${3:-0}"
    local gt="$outdir/groundtruth.tsv"
    mkdir -p "$outdir"

    if [ "$DRY_RUN" -eq 1 ]; then
        log "DRY: groundtruth capture in $outdir for ${duration}s (pid=$target_pid)"
        : > "$gt"
        printf '0\n' > "$outdir/.gt.pid"
        return 0
    fi

    {
        printf 'ts\tcpu_busy_pct\tdisk_read_mb\tdisk_write_mb\tnet_rx_mb\tnet_tx_mb\tinstr\tcycles\tllc_ref\tllc_miss\tresctrl_mbw_bps\tresctrl_llcocc_bytes\n'
        local prev_d_r=0 prev_d_w=0 prev_n_r=0 prev_n_t=0 prev_cpu_idle=0 prev_cpu_total=0
        local end=$(($(date +%s) + duration))
        while [ "$(date +%s)" -lt "$end" ]; do
            local ts; ts=$(date +%s.%N)

            # /proc/stat -- cpu busy fraction
            read -r _ user nice system idle iowait irq softirq steal _ < /proc/stat
            local total=$((user+nice+system+idle+iowait+irq+softirq+steal))
            local idle_now=$((idle+iowait))
            local d_total=$((total-prev_cpu_total))
            local d_idle=$((idle_now-prev_cpu_idle))
            local cpu_busy="--"
            if [ "$d_total" -gt 0 ]; then
                cpu_busy=$(awk -v t=$d_total -v i=$d_idle 'BEGIN{printf "%.2f",100*(t-i)/t}')
            fi
            prev_cpu_total=$total; prev_cpu_idle=$idle_now

            # /proc/diskstats -- delta MB read/written across non-loop devices
            local d_r=0 d_w=0
            while read -r _ _ name r_ios _ r_sec _ w_ios _ w_sec _; do
                case "$name" in loop*|ram*|sr*|fd*) continue ;; esac
                d_r=$((d_r + r_sec)); d_w=$((d_w + w_sec))
            done < <(awk '{print $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11}' /proc/diskstats)
            local mb_r mb_w
            mb_r=$(awk -v c=$d_r -v p=$prev_d_r 'BEGIN{printf "%.2f",(c-p)*512/1048576}')
            mb_w=$(awk -v c=$d_w -v p=$prev_d_w 'BEGIN{printf "%.2f",(c-p)*512/1048576}')
            prev_d_r=$d_r; prev_d_w=$d_w

            # /proc/net/dev -- rx/tx bytes over all non-lo ifaces
            local n_r=0 n_t=0
            while read -r line; do
                local iface bytes_r bytes_t
                iface=$(echo "$line" | awk -F: '{print $1}' | xargs)
                [ "$iface" = "lo" ] && continue
                bytes_r=$(echo "$line" | awk -F: '{print $2}' | awk '{print $1}')
                bytes_t=$(echo "$line" | awk -F: '{print $2}' | awk '{print $9}')
                n_r=$((n_r + bytes_r)); n_t=$((n_t + bytes_t))
            done < <(grep ':' /proc/net/dev | tail -n +3)
            local mb_n_r mb_n_t
            mb_n_r=$(awk -v c=$n_r -v p=$prev_n_r 'BEGIN{printf "%.2f",(c-p)/1048576}')
            mb_n_t=$(awk -v c=$n_t -v p=$prev_n_t 'BEGIN{printf "%.2f",(c-p)/1048576}')
            prev_n_r=$n_r; prev_n_t=$n_t

            # resctrl direct counters (the ground truth for mbw and llcocc)
            local mbw_bps="--" llcocc_bytes="--"
            if [ -d /sys/fs/resctrl/intp-bench/mon_data ]; then
                # Sum across L3 monitoring domains
                mbw_bps=$(cat /sys/fs/resctrl/intp-bench/mon_data/mon_L3_*/mbm_total_bytes 2>/dev/null | awk '{s+=$1}END{printf "%d",s}')
                llcocc_bytes=$(cat /sys/fs/resctrl/intp-bench/mon_data/mon_L3_*/llc_occupancy 2>/dev/null | awk '{s+=$1}END{printf "%d",s}')
            fi

            # perf counters: filled in at end via perf stat -- empty here
            printf '%s\t%s\t%s\t%s\t%s\t%s\t--\t--\t--\t--\t%s\t%s\n' \
                "$ts" "$cpu_busy" "$mb_r" "$mb_w" "$mb_n_r" "$mb_n_t" "$mbw_bps" "$llcocc_bytes"
            sleep "$INTERVAL"
        done
    } > "$gt" 2>/dev/null &
    echo $! > "$outdir/.gt.pid"

    # Interval-mode, system-wide perf for the per-interval GT perf columns
    # (instr/cycles/llc_ref/llc_miss). System-wide (-a) so it captures the
    # tenant's forked workers; for SOLO runs the tenant is the only significant
    # load, so this is its ground truth (like cpu_busy_pct, it is system-wide).
    # '-x; -I <ms>' emits one CSV line per (interval, event); merged into
    # groundtruth.tsv afterward by merge_perf_into_groundtruth (stop_groundtruth).
    if command -v perf >/dev/null 2>&1; then
        local iv_ms; iv_ms=$(awk -v s="$INTERVAL" 'BEGIN{v=s*1000; printf "%d", (v<100?100:v)}')
        perf stat -x';' -I "$iv_ms" -a \
            -e instructions,cycles,cache-references,cache-misses \
            -- sleep "$duration" > "$outdir/perf-stat.txt" 2>&1 &
        echo $! > "$outdir/.perf.pid"
    fi
}

# Merge interval-mode perf counts (perf-stat.txt) into the groundtruth.tsv perf
# columns (instr/cycles/llc_ref/llc_miss), which start_groundtruth wrote as '--'
# (perf runs as a separate process, so its counters must be folded in here). perf
# '-x; -I' emits one CSV line per (interval,event): time;value;unit;event;...
# Group by interval (time-ordered) and fill GT data rows by index; this makes the
# llcmr ground truth (llc_miss/llc_ref) adjudicable. resctrl_mbw_bps/
# resctrl_llcocc_bytes stay as-is: resctrl CMT is exclusive per-task, so while the
# profiler-under-test holds the tenant's RMID an independent occupancy read is not
# possible -- the profiler's own direct resctrl read is the occupancy GT.
merge_perf_into_groundtruth() {
    local outdir="$1"
    local gt="$outdir/groundtruth.tsv" pf="$outdir/perf-stat.txt"
    [ -f "$gt" ] && [ -f "$pf" ] && command -v python3 >/dev/null 2>&1 || return 0
    python3 - "$gt" "$pf" <<'PY' 2>/dev/null || true
import sys, collections
gt, pf = sys.argv[1], sys.argv[2]
ev = {"instructions": 0, "cycles": 1, "cache-references": 2, "cache-misses": 3}
per = collections.OrderedDict()           # interval-time -> [instr,cycles,ref,miss]
for line in open(pf):
    s = line.strip()
    if not s or s[0] == '#':
        continue
    f = s.split(';')
    if len(f) < 4:
        continue
    name = f[3].strip()
    if name not in ev:
        continue
    try:
        val = float(f[1])
    except ValueError:
        continue
    per.setdefault(f[0].strip(), [None, None, None, None])[ev[name]] = val
rows = list(per.values())
lines = open(gt).read().splitlines()
if not lines:
    sys.exit(0)
out, di = [lines[0]], 0
def fmt(x): return ("%d" % x) if x is not None else "--"
for ln in lines[1:]:
    c = ln.split('\t')
    if len(c) >= 12 and di < len(rows):
        r = rows[di]
        c[6], c[7], c[8], c[9] = fmt(r[0]), fmt(r[1]), fmt(r[2]), fmt(r[3])
        ln = '\t'.join(c); di += 1
    out.append(ln)
open(gt, 'w').write('\n'.join(out) + '\n')
PY
}

stop_groundtruth() {
    local outdir="$1"
    [ "$DRY_RUN" -eq 1 ] && return 0
    [ -f "$outdir/.gt.pid" ] && {
        terminate_pid_gracefully "$(cat "$outdir/.gt.pid")" "groundtruth/collector" || true
        rm -f "$outdir/.gt.pid"
    }
    [ -f "$outdir/.perf.pid" ] && {
        wait_pid_timeout "$(cat "$outdir/.perf.pid")" "$WAIT_TIMEOUT_S" "groundtruth/perf" || true
        rm -f "$outdir/.perf.pid"
    }
    merge_perf_into_groundtruth "$outdir"
}

# -----------------------------------------------------------------------------
# 9. Workload launcher (env-aware: bare/container/vm)
#
# Returns the PID of the *target process* the profiler should attach to.
# For container env, this is the PID of the container root process on the
# host (PID namespace is shared with host because we use --pid=host so
# SystemTap and eBPF can see the workload). For VM env, it is the qemu PID.
# -----------------------------------------------------------------------------

launch_veth_workload() {
    # VETH:<proto>:<port>:<extra_iperf3_client_args>
    # Starts iperf3 server in netns intp-net (10.42.0.2:<port>, -1 = auto-exit
    # on first client disconnect), then runs the iperf3 client on the host
    # bound to 10.42.0.1, targeting 10.42.0.2. All traffic crosses intp-veth-h
    # so V3/V3.1 (filter `lo` only) and V2 (softirq counts veth) observe it.
    #
    # Returns the iperf3 client wrapper PID (cgroup-targeted when enabled).
    local logfile="$1" duration="$2" veth_spec="$3" name="$4"
    local netns="${INTP_NETNS_NAME:-intp-net}"
    local guest_ip="${INTP_NETNS_GUEST_IP:-10.42.0.2}"
    local host_ip="${INTP_NETNS_HOST_IP:-10.42.0.1}"

    # Parse VETH:<proto>:<port>:<extra>
    local proto port extra
    IFS=':' read -r _ proto port extra <<< "$veth_spec"
    local proto_flag=""
    case "$proto" in
        tcp) proto_flag="" ;;
        udp) proto_flag="-u" ;;
        *) die "launch_veth_workload: unknown proto '$proto' (use tcp or udp)" ;;
    esac
    [[ "$port" =~ ^[0-9]+$ ]] || die "launch_veth_workload: bad port '$port'"

    # Verify netns is up before we waste a duration window on it.
    if ! ip netns list 2>/dev/null | awk '{print $1}' | grep -qx "$netns"; then
        warn "launch_veth_workload: netns '$netns' missing; run bench/setup/setup-netns-pair.sh"
        echo 0; return 1
    fi

    # Server in netns, auto-exits after first client done.
    ip netns exec "$netns" iperf3 -s -B "$guest_ip" -p "$port" -1 \
        > "${logfile%.log}.server.log" 2>&1 &
    local srv_pid=$!

    # Brief settle for bind. iperf3 binds in <100ms typically.
    sleep 0.5
    if ! kill -0 "$srv_pid" 2>/dev/null; then
        warn "launch_veth_workload: iperf3 server in netns failed to start (see ${logfile%.log}.server.log)"
        echo 0; return 1
    fi

    # Client args: -c target, -p port, -t duration, -B host_ip to bind, $proto_flag, $extra
    local cli_args=( -c "$guest_ip" -p "$port" -t "$duration" -B "$host_ip" -i 0 --connect-timeout 2000 )
    [ -n "$proto_flag" ] && cli_args+=( "$proto_flag" )
    # Append user extras (e.g. "-P 16", "-b 100M")
    # shellcheck disable=SC2206
    local extra_arr=( $extra )
    cli_args+=( "${extra_arr[@]}" )

    # Wrap in cgroup so the profiler tracks the whole client subtree.
    if [ "$USE_CGROUP_TARGETING" = "1" ] && [ -d /sys/fs/cgroup ] && [ -w /sys/fs/cgroup ]; then
        local cg="/sys/fs/cgroup/intp-bench-$name"
        mkdir -p "$cg"
        CURRENT_WORKLOAD_CGROUP="$cg"
        _apply_bench_caps_to_cgroup "$cg"
        bash -c "echo \$\$ > '$cg/cgroup.procs'; exec iperf3 ${cli_args[*]}" \
            > "$logfile" 2>&1 &
        echo $!
        return 0
    fi
    iperf3 "${cli_args[@]}" > "$logfile" 2>&1 &
    echo $!
}

# Apply BENCH_CPUS/BENCH_MEM caps to a bare-metal cgroup. Best-effort:
# if cpu/memory controllers are not delegated to this cgroup, log a warn
# (do NOT die) — the experiment still runs, it just lacks parity for
# this rep, which is far better than silently aborting a long campaign.
_apply_bench_caps_to_cgroup() {
    local cg="$1"
    [ -z "$cg" ] && return 0
    [ -d "$cg" ] || return 0
    # No parity caps requested -> leave CURRENT_CAPS_APPLIED unset (run_one
    # records "n/a").
    [ -n "$BENCH_CPUS$BENCH_MEM" ] || return 0
    # Track whether the caps actually landed. A missing controller file means
    # the controller was not delegated to this cgroup => the cap silently
    # would NOT apply; record that as caps not applied (P2 audit), do not die.
    local ok=1
    if [ -n "$BENCH_CPUS" ]; then
        if [ -f "$cg/cpu.max" ]; then
            # cpu.max format: "<quota> <period>"; quota = N * period gives N cpus.
            printf '%d 100000\n' "$(( BENCH_CPUS * 100000 ))" \
                > "$cg/cpu.max" 2>/dev/null \
                || { warn "[parity/bare] cpu.max write failed for $cg"; ok=0; }
        else
            warn "[parity/bare] cpu.max absent for $cg (cpu controller not delegated)"
            ok=0
        fi
    fi
    if [ -n "$BENCH_MEM" ]; then
        if [ -f "$cg/memory.max" ]; then
            local bytes
            bytes=$(numfmt --from=iec "$BENCH_MEM" 2>/dev/null || echo "")
            if [ -n "$bytes" ]; then
                printf '%s\n' "$bytes" > "$cg/memory.max" 2>/dev/null \
                    || { warn "[parity/bare] memory.max write failed for $cg"; ok=0; }
            else
                warn "[parity/bare] could not parse BENCH_MEM='$BENCH_MEM' as IEC size"
                ok=0
            fi
        else
            warn "[parity/bare] memory.max absent for $cg (memory controller not delegated)"
            ok=0
        fi
    fi
    [ "$ok" = 1 ] && CURRENT_CAPS_APPLIED="yes" || CURRENT_CAPS_APPLIED="no"
}

launch_redis_workload() {
    # REDIS:<port>:<redis-benchmark extra args>. Profiled process = redis-server
    # (placed in the bench cgroup when cgroup-targeting is on, so v2.1/v3.3 scope
    # it); the load = redis-benchmark run continuously for the whole window (warmup
    # + measure + cooldown + slack), NOT profiled. Returns the redis-server PID.
    # Deps (redis-server + redis-benchmark) are provisioned on demand via
    # bench/setup/setup-redis-workload.sh (reproducibility automation, C32).
    local logfile="$1" duration="$2" spec="$3" name="$4"
    local port rb_extra
    IFS=':' read -r _ port rb_extra <<< "$spec"
    [[ "$port" =~ ^[0-9]+$ ]] || die "launch_redis_workload: bad port '$port'"

    if ! command -v redis-server >/dev/null 2>&1 || ! command -v redis-benchmark >/dev/null 2>&1; then
        bash "$SCRIPT_DIR/setup/setup-redis-workload.sh" >> "${logfile%.log}.setup.log" 2>&1 \
            || { warn "launch_redis_workload: dep install failed (see ${logfile%.log}.setup.log)"; echo 0; return 1; }
    fi

    local redis_pid
    if [ "$USE_CGROUP_TARGETING" = "1" ] && [ -d /sys/fs/cgroup ] && [ -w /sys/fs/cgroup ]; then
        local cg="/sys/fs/cgroup/intp-bench-$name"
        mkdir -p "$cg"
        CURRENT_WORKLOAD_CGROUP="$cg"
        _apply_bench_caps_to_cgroup "$cg"
        _publish_caps_applied "$logfile" "${CURRENT_CAPS_APPLIED:-n/a}"
        bash -c "echo \$\$ > '$cg/cgroup.procs'; exec redis-server --port $port --save '' --appendonly no --protected-mode no --maxmemory 2gb --maxmemory-policy allkeys-lru" > "$logfile" 2>&1 &
        redis_pid=$!
    else
        redis-server --port "$port" --save '' --appendonly no --protected-mode no \
            --maxmemory 2gb --maxmemory-policy allkeys-lru > "$logfile" 2>&1 &
        redis_pid=$!
        _publish_caps_applied "$logfile" "n/a"
    fi

    local i ready=0
    for i in $(seq 1 50); do
        if redis-cli -p "$port" ping 2>/dev/null | grep -q PONG; then ready=1; break; fi
        sleep 0.1
    done
    if [ "$ready" != "1" ]; then
        warn "launch_redis_workload: redis-server not ready on :$port (see $logfile)"
        kill "$redis_pid" 2>/dev/null; echo 0; return 1
    fi

    # Continuous load (not profiled); exits when redis dies (stop_workload kills
    # redis_pid -> the `while redis-cli ping` loop breaks) or the slack timeout.
    local total=$(( duration + WARMUP + COOLDOWN + 10 ))
    # shellcheck disable=SC2086
    setsid timeout "$total" sh -c \
        "while redis-cli -p $port ping >/dev/null 2>&1; do redis-benchmark -p $port -q -n 1000000 $rb_extra >/dev/null 2>&1 || break; done" \
        > "${logfile%.log}.load.log" 2>&1 < /dev/null &

    echo "$redis_pid"
}

launch_workload_bare() {
    local logfile="$1" duration="$2" args="$3" name="$4"
    CURRENT_WORKLOAD_CGROUP=""

    # Redis KV workload (args starts with REDIS:<port>:...)
    if [[ "$args" == REDIS:* ]]; then
        if [ "$DRY_RUN" -eq 1 ]; then
            log "DRY: redis-server + redis-benchmark load for $name spec=$args duration=${duration}s -> $logfile"
            [ "$USE_CGROUP_TARGETING" = "1" ] && CURRENT_WORKLOAD_CGROUP="/sys/fs/cgroup/intp-bench-$name"
            echo $$
            return 0
        fi
        launch_redis_workload "$logfile" "$duration" "$args" "$name"
        return $?
    fi

    # Veth-routed network workload (args starts with VETH:<proto>:<port>:...)
    if [[ "$args" == VETH:* ]]; then
        if [ "$DRY_RUN" -eq 1 ]; then
            log "DRY: veth workload $name spec=$args duration=${duration}s -> $logfile"
            [ "$USE_CGROUP_TARGETING" = "1" ] && CURRENT_WORKLOAD_CGROUP="/sys/fs/cgroup/intp-bench-$name"
            echo $$
            return 0
        fi
        launch_veth_workload "$logfile" "$duration" "$args" "$name"
        return $?
    fi

    if [ "$DRY_RUN" -eq 1 ]; then
        if [ "$USE_CGROUP_TARGETING" = "1" ]; then
            CURRENT_WORKLOAD_CGROUP="/sys/fs/cgroup/intp-bench-$name"
        fi
        if [ "$USE_CGROUP_TARGETING" = "1" ]; then
            log "DRY: stress-ng in dedicated cgroup for $name: $args --timeout ${duration}s > $logfile"
        else
            log "DRY: stress-ng $args --timeout ${duration}s > $logfile"
        fi
        echo $$
        return 0
    fi

    if [ "$USE_CGROUP_TARGETING" = "1" ] && [ -d /sys/fs/cgroup ] && [ -w /sys/fs/cgroup ]; then
        local cg="/sys/fs/cgroup/intp-bench-$name"
        mkdir -p "$cg"
        CURRENT_WORKLOAD_CGROUP="$cg"
        _apply_bench_caps_to_cgroup "$cg"
        _publish_caps_applied "$logfile" "${CURRENT_CAPS_APPLIED:-n/a}"
        # shellcheck disable=SC2086
        bash -c "echo \$\$ > '$cg/cgroup.procs'; exec stress-ng $args --timeout '${duration}s' --metrics-brief" > "$logfile" 2>&1 &
        echo $!
        return 0
    fi

    # shellcheck disable=SC2086
    stress-ng $args --timeout "${duration}s" --metrics-brief > "$logfile" 2>&1 &
    echo $!
}

launch_workload_container() {
    local logfile="$1" duration="$2" args="$3" name="$4"
    CURRENT_WORKLOAD_CGROUP=""
    if [ "$DRY_RUN" -eq 1 ]; then
        if [[ "$args" == VETH:* ]]; then
            log "DRY: docker veth $name spec=$args -> in-container iperf3 client (--network host) + host netns server"
        else
            log "DRY: docker run ... stress-ng $args"
        fi
        echo $$
        return 0
    fi
    if ! command -v docker >/dev/null 2>&1; then
        warn "docker not installed -- container launch failed"
        echo 0; return 1
    fi
    docker rm -f "$name" >/dev/null 2>&1 || true

    # Veth-routed network workload IN a container. With --network host the
    # container shares the host root netns, so an in-container iperf3 client
    # reaches the netns server (10.42.0.2) over intp-veth-h exactly as the bare
    # host client does (launch_veth_workload) -> real-NIC netp/nets inside the
    # container, not loopback. Server runs on the host in netns intp-net; the
    # host-side profiler (--pid=host) attributes the container's iperf3 PID
    # (cgroup self-resolved, C17). Mirrors launch_workload_bare's VETH branch.
    if [[ "$args" == VETH:* ]]; then
        local netns="${INTP_NETNS_NAME:-intp-net}"
        local guest_ip="${INTP_NETNS_GUEST_IP:-10.42.0.2}"
        local host_ip="${INTP_NETNS_HOST_IP:-10.42.0.1}"
        local _p proto port extra
        IFS=':' read -r _p proto port extra <<< "$args"
        local proto_flag=""
        [ "$proto" = "udp" ] && proto_flag="-u"
        if ! ip netns list 2>/dev/null | awk '{print $1}' | grep -qx "$netns"; then
            warn "container veth: netns '$netns' missing; run bench/setup/setup-netns-pair.sh"
            echo 0; return 1
        fi
        ip netns exec "$netns" iperf3 -s -B "$guest_ip" -p "$port" -1 \
            > "${logfile%.log}.server.log" 2>&1 &
        local srv_pid=$!
        sleep 0.5
        if ! kill -0 "$srv_pid" 2>/dev/null; then
            warn "container veth: iperf3 server in netns failed (see ${logfile%.log}.server.log)"
            echo 0; return 1
        fi
        docker run --rm -d --name "$name" --pid=host --network host \
            "$CONTAINER_IMAGE" \
            bash -c "apt-get update -qq && apt-get install -y -qq iperf3 >/dev/null && iperf3 -c $guest_ip -p $port -t $duration -B $host_ip $proto_flag -i 0 --connect-timeout 2000 $extra" \
            > "$logfile" 2>&1 \
            || { warn "container veth: docker run (iperf3 client) failed"; echo 0; return 1; }
        _publish_caps_applied "$logfile" "n/a"
        local cpid
        cpid=$(docker inspect -f '{{.State.Pid}}' "$name" 2>/dev/null || echo 0)
        echo "$cpid"
        return 0
    fi

    # Capability matrix:
    #   --pid=host       so the host-side profiler can see the workload PID
    #   --network=host   so net traffic counters reflect the same NIC the host sees
    #   SYS_NICE         stress-ng affinity / nice() calls
    # When INTP_CONTAINER_INGUEST_PROFILER=1 (future in-guest profiler hook),
    # the container also needs perf/BPF capabilities. Defaults stay minimal so
    # the current host-attached path doesn't request privileges it doesn't use.
    local extra_caps=()
    if [ "${INTP_CONTAINER_INGUEST_PROFILER:-0}" = "1" ]; then
        extra_caps+=(--cap-add CAP_PERFMON --cap-add CAP_BPF --cap-add CAP_SYS_RESOURCE)
        # resctrl bind mount is required for v2/v3/v3.1 RDT metrics in-container
        if [ -d /sys/fs/resctrl ]; then
            extra_caps+=(-v /sys/fs/resctrl:/sys/fs/resctrl)
        fi
    fi

    # Parity caps. If --cpus / --memory are rejected (e.g. unsupported
    # cgroup mode on a legacy host) docker exits non-zero; warn and retry
    # without the caps so the rep still produces a measurement.
    local parity_args=()
    [ -n "$BENCH_CPUS" ] && parity_args+=( --cpus="$BENCH_CPUS" )
    [ -n "$BENCH_MEM" ]  && parity_args+=( --memory="$BENCH_MEM" )

    local caps_status="n/a"
    [ -n "$BENCH_CPUS$BENCH_MEM" ] && caps_status="yes"
    docker run --rm -d --name "$name" \
        --pid=host --cap-add SYS_NICE \
        --network host \
        "${parity_args[@]}" \
        "${extra_caps[@]}" \
        "$CONTAINER_IMAGE" \
        bash -c "apt-get update -qq && apt-get install -y -qq stress-ng >/dev/null && stress-ng $args --timeout ${duration}s --metrics-brief" \
        > "$logfile" 2>&1 \
        || {
            warn "[parity/container] docker run with --cpus/--memory failed; retrying without parity caps"
            [ -n "$BENCH_CPUS$BENCH_MEM" ] && caps_status="no"
            docker run --rm -d --name "$name" \
                --pid=host --cap-add SYS_NICE \
                --network host \
                "${extra_caps[@]}" \
                "$CONTAINER_IMAGE" \
                bash -c "apt-get update -qq && apt-get install -y -qq stress-ng >/dev/null && stress-ng $args --timeout ${duration}s --metrics-brief" \
                > "$logfile" 2>&1
        }
    _publish_caps_applied "$logfile" "$caps_status"
    # Get the PID of the in-container stress-ng on the host PID namespace
    local cpid
    cpid=$(docker inspect -f '{{.State.Pid}}' "$name" 2>/dev/null || echo 0)
    echo "$cpid"
}

# Workload in a rootful Podman container, profiler on host (--pid=host). Podman
# is DAEMONLESS and OCI-compatible: there is no daemon to start, and run as root
# it places the container in HOST-VISIBLE cgroup v2 cgroups, so the host-side
# profiler attributes it EXACTLY like docker. This is a verbatim clone of
# launch_workload_container (the docker env) with `docker` -> `$PODMAN_BIN` and
# CONTAINER_IMAGE -> PODMAN_IMAGE: same parity caps, same apt-install+stress-ng
# inside, same dry-run branch, same logfile, and the in-container stress-ng host
# PID returned via `inspect -f {{.State.Pid}}`. No profiler change is needed:
# C17's run_profiler_v3_3 self-resolves the cgroup from the returned PID, and
# v2.1/v2/v3.2 take the PID via --pids -- identical to the docker path.
#
# Quiesce note: because podman has no persistent daemon, a container-podman
# campaign keeps NO runtime daemon alive. run-big-batch.sh's keep-set only adds
# `docker` for container/-guest/-full and `lxd incus` for container-lxc;
# container-podman matches neither => empty keep-set => docker+lxd+incus all get
# quiesced and nothing is kept (correct -- there is no podman daemon to keep).
launch_workload_container_podman() {
    local logfile="$1" duration="$2" args="$3" name="$4"
    CURRENT_WORKLOAD_CGROUP=""
    if [ "$DRY_RUN" -eq 1 ]; then
        log "DRY: $PODMAN_BIN run ... stress-ng $args"
        echo $$
        return 0
    fi
    if ! command -v "$PODMAN_BIN" >/dev/null 2>&1; then
        warn "podman not installed -- container-podman launch failed"
        echo 0; return 1
    fi
    "$PODMAN_BIN" rm -f "$name" >/dev/null 2>&1 || true

    # Capability matrix (mirrors the docker launcher):
    #   --pid=host       so the host-side profiler can see the workload PID
    #   --network=host   so net traffic counters reflect the same NIC the host sees
    #   SYS_NICE         stress-ng affinity / nice() calls
    # When INTP_CONTAINER_INGUEST_PROFILER=1 (future in-guest profiler hook),
    # the container also needs perf/BPF capabilities. Defaults stay minimal so
    # the current host-attached path doesn't request privileges it doesn't use.
    local extra_caps=()
    if [ "${INTP_CONTAINER_INGUEST_PROFILER:-0}" = "1" ]; then
        extra_caps+=(--cap-add CAP_PERFMON --cap-add CAP_BPF --cap-add CAP_SYS_RESOURCE)
        # resctrl bind mount is required for v2/v3/v3.1 RDT metrics in-container
        if [ -d /sys/fs/resctrl ]; then
            extra_caps+=(-v /sys/fs/resctrl:/sys/fs/resctrl)
        fi
    fi

    # Parity caps. If --cpus / --memory are rejected (e.g. unsupported
    # cgroup mode on a legacy host) podman exits non-zero; warn and retry
    # without the caps so the rep still produces a measurement.
    local parity_args=()
    [ -n "$BENCH_CPUS" ] && parity_args+=( --cpus="$BENCH_CPUS" )
    [ -n "$BENCH_MEM" ]  && parity_args+=( --memory="$BENCH_MEM" )

    local caps_status="n/a"
    [ -n "$BENCH_CPUS$BENCH_MEM" ] && caps_status="yes"
    "$PODMAN_BIN" run --rm -d --name "$name" \
        --pid=host --cap-add SYS_NICE \
        --network host \
        "${parity_args[@]}" \
        "${extra_caps[@]}" \
        "$PODMAN_IMAGE" \
        bash -c "apt-get update -qq && apt-get install -y -qq stress-ng >/dev/null && stress-ng $args --timeout ${duration}s --metrics-brief" \
        > "$logfile" 2>&1 \
        || {
            warn "[parity/container-podman] $PODMAN_BIN run with --cpus/--memory failed; retrying without parity caps"
            [ -n "$BENCH_CPUS$BENCH_MEM" ] && caps_status="no"
            "$PODMAN_BIN" run --rm -d --name "$name" \
                --pid=host --cap-add SYS_NICE \
                --network host \
                "${extra_caps[@]}" \
                "$PODMAN_IMAGE" \
                bash -c "apt-get update -qq && apt-get install -y -qq stress-ng >/dev/null && stress-ng $args --timeout ${duration}s --metrics-brief" \
                > "$logfile" 2>&1
        }
    _publish_caps_applied "$logfile" "$caps_status"
    # Get the PID of the in-container stress-ng on the host PID namespace
    local cpid
    cpid=$("$PODMAN_BIN" inspect -f '{{.State.Pid}}' "$name" 2>/dev/null || echo 0)
    echo "$cpid"
}

# Workload in a Kubernetes Pod (backed by k3s), profiler on host. This is the
# DEEPEST cgroup nesting of any env: the stress-ng process lands in
# kubepods.slice/kubepods-<qos>.slice/kubepods-<qos>-pod<uid>.slice/
# cri-containerd-<id>.scope. It is the hardest test of v3.3's ancestor-cgid
# gate + target_level, yet needs NO profiler change: we resolve the in-pod
# stress-ng HOST-PID-namespace PID via crictl and echo it (same stdout contract
# as docker/podman). C17's resolve_pid_cgroup() reads the unified line of
# /proc/<pid>/cgroup, so it self-resolves that deep kubepods path; v2.1/v3.2
# take the PID via --pids. Mirrors launch_workload_container's shape: dry-run
# branch, `command -v` guards, stale-pod pre-clean, parity caps from
# BENCH_CPUS/BENCH_MEM (like docker --cpus/--memory), on-the-fly apt install of
# stress-ng inside the pod (importing bench/setup/Dockerfile.bench into k3s via
# `k3s ctr image import`, or pulling from ghcr.io via bench/.../publish-images.sh,
# avoids the per-run install -- point INTP_BENCH_K8S_IMAGE at the pre-baked
# image then drop the apt-get prefix). On any failure echo 0 + warn, like docker.
#
# Quiesce note: k3s.service is DAEMON-FUL (kubelet + containerd + control plane);
# for non-k8s campaigns it is heavy idle interference and MUST be stopped
# (host-services.sh quiesce), and a container-k8s campaign keeps it
# (run-big-batch.sh keep-set).
launch_workload_container_k8s() {
    local logfile="$1" duration="$2" args="$3" name="$4"
    CURRENT_WORKLOAD_CGROUP=""
    # k8s object names must be RFC 1123 labels (lowercase alnum + '-', <=63 chars,
    # start/end alnum). The bench run name contains '_' (app10_search) and '.'
    # (v2.1) which are invalid, so sanitize: lowercase, map any non-[a-z0-9-] to
    # '-', collapse/trim dashes, and cap length keeping the unique tail.
    local pod
    pod=$(printf 'intp-k8s-%s' "$name" | tr '[:upper:]' '[:lower:]' \
            | tr -c 'a-z0-9-' '-' | sed -E 's/-+/-/g; s/^-+//; s/-+$//')
    # Cap to the 63-char RFC 1123 limit (keep the unique tail) ONLY if over.
    # Avoid bash "${x: -n}", which empties strings shorter than n on bash 5.2.
    [ "${#pod}" -gt 63 ] && pod=$(printf '%s' "$pod" | tail -c 63 | sed -E 's/^-+//')
    if [ "$DRY_RUN" -eq 1 ]; then
        log "DRY: $KUBECTL apply -f - (Pod/$pod ns=$K8S_NS image=$K8S_IMAGE) stress-ng $args --timeout ${duration}s"
        log "DRY:   resolve host PID via $CRICTL inspect (.info.pid)"
        echo $$
        return 0
    fi
    if ! command -v "$KUBECTL" >/dev/null 2>&1; then
        warn "kubectl not installed -- container-k8s launch failed (try INTP_BENCH_KUBECTL='k3s kubectl')"
        echo 0; return 1
    fi
    if ! command -v "$CRICTL" >/dev/null 2>&1; then
        warn "crictl not installed -- container-k8s launch failed (bundled with k3s)"
        echo 0; return 1
    fi

    # Pre-clean any stale pod from a prior aborted rep (mirrors docker rm -f).
    "$KUBECTL" delete pod "$pod" -n "$K8S_NS" --force --grace-period=0 \
        >/dev/null 2>&1 || true

    # Create the namespace if absent (idempotent; ignore "already exists").
    "$KUBECTL" get namespace "$K8S_NS" >/dev/null 2>&1 \
        || "$KUBECTL" create namespace "$K8S_NS" >/dev/null 2>&1 || true

    # Parity caps from BENCH_CPUS/BENCH_MEM -> resources.limits, like docker's
    # --cpus / --memory. Omit the resources block entirely when both are unset
    # (an empty limits map is rejected by the API server). Built as indented
    # YAML lines so the heredoc below stays a valid Pod manifest either way.
    local limits_yaml=""
    if [ -n "$BENCH_CPUS" ] || [ -n "$BENCH_MEM" ]; then
        limits_yaml="      resources:
        limits:"
        [ -n "$BENCH_CPUS" ] && limits_yaml="$limits_yaml
          cpu: \"$BENCH_CPUS\""
        [ -n "$BENCH_MEM" ]  && limits_yaml="$limits_yaml
          memory: \"$BENCH_MEM\""
    fi

    # In-pod command mirrors the docker on-the-fly install: try stress-ng, else
    # apt-get install it, then exec it. exec replaces the shell so the host PID
    # we resolve below is stress-ng itself (the profiler's target).
    local podcmd="command -v stress-ng || (apt-get update -qq && apt-get install -y -qq stress-ng); exec stress-ng $args --timeout ${duration}s --metrics-brief"

    # Single-container Pod, restartPolicy Never (one-shot like docker --rm).
    if ! "$KUBECTL" apply -f - >>"$logfile" 2>&1 <<YAML
apiVersion: v1
kind: Pod
metadata:
  name: $pod
  namespace: $K8S_NS
  labels:
    app: intp-bench
    intp-pod: $pod
spec:
  restartPolicy: Never
  containers:
    - name: stress-ng
      image: $K8S_IMAGE
      command: ["sh", "-c"]
      args:
        - |
          $podcmd
$limits_yaml
YAML
    then
        warn "container-k8s: '$KUBECTL apply' failed for $pod (see $logfile)"
        echo 0; return 1
    fi

    # Wait for the pod container to be running. kubectl wait for Ready is the
    # primary path; fall back to a Running-phase poll because a one-shot pod
    # may never report Ready (no readiness probe) yet still be Running.
    "$KUBECTL" wait --for=condition=Ready "pod/$pod" -n "$K8S_NS" \
        --timeout=120s >>"$logfile" 2>&1 || {
        local phase
        for _ in $(seq 1 60); do
            phase=$("$KUBECTL" get "pod/$pod" -n "$K8S_NS" \
                -o jsonpath='{.status.phase}' 2>/dev/null || echo "")
            [ "$phase" = "Running" ] && break
            sleep 2
        done
    }

    # Resolve the in-pod stress-ng HOST-PID-namespace PID via crictl:
    #   1. crictl ps -q --label/--name to get the container id for this pod
    #   2. crictl inspect <id> | .info.pid  (the host-visible PID)
    # crictl talks to k3s's containerd over CRI; the same socket the kubelet
    # uses. The pod label set above (intp-pod=$pod) scopes the lookup.
    local cid hostpid=""
    for _ in $(seq 1 30); do
        cid=$("$CRICTL" ps -q --state Running --label "intp-pod=$pod" 2>/dev/null \
            | head -1)
        [ -z "$cid" ] && cid=$("$CRICTL" ps -q --state Running --name stress-ng 2>/dev/null \
            | head -1)
        if [ -n "$cid" ]; then
            # .info.pid is the container init PID in the HOST pid namespace.
            # Prefer jq (a bench dependency) for a precise .info.pid path -- the
            # crictl JSON also contains runtimeSpec namespaces with {"type":"pid"}
            # entries, so a naive grep '"pid"' can match the wrong line if the
            # field order ever changes. Fall back to grep+sed only if jq is absent.
            if command -v jq >/dev/null 2>&1; then
                hostpid=$("$CRICTL" inspect "$cid" 2>/dev/null \
                    | jq -r '.info.pid // empty' 2>/dev/null)
            else
                hostpid=$("$CRICTL" inspect "$cid" 2>/dev/null \
                    | grep -m1 '"pid"' | sed -E 's/[^0-9]//g')
            fi
            [ -n "$hostpid" ] && [ "$hostpid" != "0" ] && break
        fi
        sleep 2
    done

    if [ -z "$hostpid" ] || [ "$hostpid" = "0" ]; then
        warn "container-k8s: could not resolve in-pod stress-ng host PID for $pod (see $logfile)"
        echo 0; return 1
    fi
    # Echo the host-PID-namespace PID. C17's resolve_pid_cgroup self-resolves the
    # deep kubepods cgroup from it for v3.3; v2.1/v3.2 use it via --pids.
    echo "$hostpid"
}

# launch_workload runs in a $( ... | tail -1 ) subshell, so a global it sets
# (the cgroup it resolves only after launch) cannot reach run_one. Hand it back
# through a per-rep sidecar in the workload's output dir (dirname of logfile);
# run_one reads and removes it. Only container-lxc needs this -- the bare env
# precomputes its predictable cgroup path in the parent shell.
_lxc_publish_cgroup() {
    local logfile="$1"
    [ -n "${CURRENT_WORKLOAD_CGROUP:-}" ] || return 0
    printf '%s\n' "$CURRENT_WORKLOAD_CGROUP" \
        > "$(dirname "$logfile")/.workload-cgroup" 2>/dev/null || true
}

# Publish whether the parity CPU/RAM caps actually applied for this rep (P2
# audit). Same subshell rationale as _lxc_publish_cgroup: launch_workload runs
# in a $(... | tail -1) subshell, so the launcher writes a sidecar that run_one
# folds into run.json. Status: yes|no (bare/docker/podman, verified) or n/a (no
# caps requested). lxc/k8s/vm leave no sidecar => run_one records "engine"
# (caps requested + passed to the engine, not independently verified here).
_publish_caps_applied() {
    local logfile="$1" status="$2"
    [ -n "$status" ] || return 0
    printf '%s\n' "$status" \
        > "$(dirname "$logfile")/.caps-applied" 2>/dev/null || true
}

# Publish vm-guest SSH connection state for run_one -> run_profiler_inguest_vm.
# launch_workload runs in a $(... | tail -1) subshell, so the launcher's
# `export INTP_VMG_*` is lost to run_one and the in-guest profiler was skipped
# ("vm-guest state not exported"). Hand it back via a per-rep sidecar that
# run_one sources before dispatching the profiler.
_vmg_publish_state() {
    local logfile="$1" tmpdir="$2" sshport="$3" gpid="$4" guest_cg="${5:-}"
    { printf 'INTP_VMG_TMPDIR=%q\n'      "$tmpdir"
      printf 'INTP_VMG_SSHPORT=%q\n'     "$sshport"
      printf 'INTP_VMG_GUEST_PID=%q\n'   "$gpid"
      printf 'INTP_VMG_GUEST_CGROUP=%q\n' "$guest_cg"
    } > "$(dirname "$logfile")/.vmg-state" 2>/dev/null || true
}

# Start the in-guest stress-ng workload over SSH into an ALREADY-BOOTED vm-guest.
# SPLIT from the boot (vs the old inline start) so the pairwise path can boot both
# VMs idle and start the aggressor's attack ONLY AFTER the victim is up + measuring
# -- a saturating aggressor started at its own boot starves the victim VM's boot
# (sshd refused, no data; the documented vm-guest pairwise failure). Echoes the
# in-guest workload PID. guest_cg scopes the in-guest profiler (T1).
_vmg_start_workload() {
    local tmpdir="$1" sshport="$2" guest_cg="$3" args="$4" duration="$5"
    ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
        -i "$tmpdir/key" -p "$sshport" intp@127.0.0.1 "cat > /tmp/intp-wl-launch.sh" <<EOF || warn "vm-guest: staging workload launcher failed"
#!/bin/sh
sudo mkdir -p $guest_cg 2>/dev/null
sudo sh -c 'echo \$\$ > $guest_cg/cgroup.procs 2>/dev/null; exec stress-ng $args --timeout ${duration}s --metrics-brief' > /tmp/wl.log 2>&1 &
echo \$! > /tmp/intp-wl.pid
EOF
    ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
        -i "$tmpdir/key" -p "$sshport" intp@127.0.0.1 \
        "nohup sh /tmp/intp-wl-launch.sh >/dev/null 2>&1 &" \
        || warn "ssh stress-ng dispatch failed"
    sleep 1
    ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
        -i "$tmpdir/key" -p "$sshport" intp@127.0.0.1 'cat /tmp/intp-wl.pid 2>/dev/null' 2>/dev/null || echo 0
}

# Incus/LXD instance names allow only [a-zA-Z0-9-] (NO '.'/'_', unlike docker),
# must start with a letter, and are <=63 chars. The per-run name carries the
# variant ('v2.1' -> '.') and workload ('app10_search' -> '_'), which incus
# rejects ("Invalid instance name ... can only contain alphanumeric and hyphen"),
# silently dropping container-lxc to system-wide profiling (llcocc pinned, GT
# host-idle). Sanitize like the k8s pod-name fix (C21): map invalid chars to '-',
# collapse repeats, cap with `tail -c 63` (NOT `${x: -63}`, which empties short
# names on bash 5.2), and guarantee a leading letter. Used by BOTH the launcher
# and stop_workload so they delete/exec the same name.
_lxc_instance_name() {
    local n
    n=$(printf '%s' "$1" | tr -c 'a-zA-Z0-9-' '-' | tr -s '-' | tail -c 63)
    case "$n" in [!a-zA-Z]*) n="x$n" ;; esac
    printf '%s' "$n"
}

# Workload in an LXC/LXD (Incus) system container; the profiler stays on the
# host and attaches to the container's CGROUP -- the c-abi-cgroup attribution
# path v2.1 (and future v3.3) are designed for ("a container is a cgroup").
# CURRENT_WORKLOAD_CGROUP is set to the container's unified cgroup, resolved
# from /proc/<initpid>/cgroup so we don't hardcode LXD's layout. Echoes the
# container init PID on the host as a liveness signal and a --pids fallback for
# the older PID-only variants. Mirrors launch_workload_container's dry-run,
# parity-cap, and best-effort semantics.
#
# Caveat: cpu.stat and perf cgroup-mode aggregate descendants, so targeting the
# container's top cgroup attributes the whole container; io.stat is per-cgroup
# (non-recursive) in cgroup v2, so blk reflects I/O charged at the container
# cgroup itself -- adequate for stress-ng workloads charged at that level.
launch_workload_container_lxc() {
    local logfile="$1" duration="$2" args="$3" name="$4"
    name="$(_lxc_instance_name "$name")"   # incus name rules (see _lxc_instance_name)
    CURRENT_WORKLOAD_CGROUP=""
    if [ "$DRY_RUN" -eq 1 ]; then
        log "DRY: $LXC_BIN launch $LXC_IMAGE $name && $LXC_BIN exec $name -- stress-ng $args --timeout ${duration}s"
        [ "$USE_CGROUP_TARGETING" = "1" ] && CURRENT_WORKLOAD_CGROUP="/sys/fs/cgroup/lxc.payload.$name"
        _lxc_publish_cgroup "$logfile"
        echo $$
        return 0
    fi
    if ! command -v "$LXC_BIN" >/dev/null 2>&1; then
        warn "$LXC_BIN (LXD/Incus client) not installed -- container-lxc launch failed"
        echo 0; return 1
    fi
    "$LXC_BIN" delete --force "$name" >/dev/null 2>&1 || true

    # Parity caps -> LXD limits.cpu (integer vCPU count) / limits.memory (bytes;
    # LXD accepts a raw integer). Retry without them if the host rejects the
    # limit, mirroring the Docker launcher, so the rep still yields a sample.
    local parity_args=()
    [ -n "$BENCH_CPUS" ] && parity_args+=( -c "limits.cpu=$BENCH_CPUS" )
    if [ -n "$BENCH_MEM" ]; then
        local membytes; membytes=$(numfmt --from=iec "$BENCH_MEM" 2>/dev/null || echo "")
        [ -n "$membytes" ] && parity_args+=( -c "limits.memory=$membytes" )
    fi

    if ! "$LXC_BIN" launch "$LXC_IMAGE" "$name" "${parity_args[@]}" >>"$logfile" 2>&1; then
        warn "[parity/container-lxc] launch with limits failed; retrying without parity caps"
        "$LXC_BIN" launch "$LXC_IMAGE" "$name" >>"$logfile" 2>&1 \
            || { warn "container-lxc: '$LXC_BIN launch' failed (see $logfile)"; echo 0; return 1; }
    fi

    # Wait for init to obtain a host PID.
    local initpid="" tries
    for tries in 1 2 3 4 5 6 7 8 9 10; do
        # `|| true`: awk's early `exit` SIGPIPEs `lxc info`, fatal under pipefail.
        initpid=$("$LXC_BIN" info "$name" 2>/dev/null | awk 'tolower($1)=="pid:"{print $2; exit}') || true
        [ -n "$initpid" ] && [ "$initpid" != "0" ] && break
        sleep 0.5
    done
    if [ -z "$initpid" ] || [ "$initpid" = "0" ]; then
        warn "container-lxc: could not resolve init PID for $name"
        "$LXC_BIN" delete --force "$name" >/dev/null 2>&1 || true
        echo 0; return 1
    fi

    # Resolve the container's unified (cgroup v2) cgroup from the host view.
    if [ "$USE_CGROUP_TARGETING" = "1" ]; then
        local cgrel
        cgrel=$(awk -F: '/^0::/{print $3; exit}' "/proc/$initpid/cgroup" 2>/dev/null)
        if [ -n "$cgrel" ] && [ -d "/sys/fs/cgroup$cgrel" ]; then
            CURRENT_WORKLOAD_CGROUP="/sys/fs/cgroup$cgrel"
        else
            warn "container-lxc: could not resolve cgroup for $name (initpid=$initpid); profiler falls back to --pids/system-wide"
        fi
    fi
    _lxc_publish_cgroup "$logfile"

    # Ensure stress-ng is present, then run the workload inside the container.
    # Backgrounded: the launcher returns once the workload is running and the
    # container cgroup already scopes it for the host-side profiler.
    "$LXC_BIN" exec "$name" -- bash -c \
        "command -v stress-ng >/dev/null 2>&1 || { apt-get update -qq && apt-get install -y -qq stress-ng >/dev/null 2>&1; }; exec stress-ng $args --timeout ${duration}s --metrics-brief" \
        >>"$logfile" 2>&1 &

    echo "$initpid"
}

# Tracks tmpdirs created by launch_workload_vm so they can be reaped.
# Cleaned by _vm_cleanup_tmpdirs (registered as EXIT trap by parse_args).
VM_TMPDIRS=()

# Tracks host-side qemu PIDs spawned by launch_workload_vm*.
# Drained by stop_workload (normal path) and reaped by
# _vm_kill_orphan_qpids on EXIT/INT/TERM (safety net).
# OPERATOR: validate trap under real SIGINT mid-rep
VM_HOST_PIDS=()

_vm_cleanup_tmpdirs() {
    local d
    for d in "${VM_TMPDIRS[@]:-}"; do
        [ -n "$d" ] && [ -d "$d" ] && rm -rf "$d" 2>/dev/null
    done
    VM_TMPDIRS=()
}

_vm_forget_host_pid() {
    # Filter $1 out of VM_HOST_PIDS in-place. O(n) but n is small (one entry
    # per concurrent VM workload). No-op if the pid is not tracked.
    local target="$1" p
    local -a kept=()
    for p in "${VM_HOST_PIDS[@]:-}"; do
        [ -z "$p" ] && continue
        [ "$p" = "$target" ] && continue
        kept+=("$p")
    done
    VM_HOST_PIDS=("${kept[@]:-}")
}

_vm_kill_orphan_qpids() {
    # Reap any qemu host PIDs still alive at trap time. Idempotent.
    local p
    for p in "${VM_HOST_PIDS[@]:-}"; do
        [ -z "$p" ] && continue
        kill -0 "$p" 2>/dev/null || continue
        # Soft kill first; SIGTERM gives qemu a chance to flush.
        kill -TERM "$p" 2>/dev/null || true
    done
    # Wait up to 5 s for SIGTERM to take effect.
    local i any_alive
    for i in 1 2 3 4 5; do
        any_alive=0
        for p in "${VM_HOST_PIDS[@]:-}"; do
            [ -z "$p" ] && continue
            kill -0 "$p" 2>/dev/null && { any_alive=1; break; }
        done
        [ "$any_alive" -eq 0 ] && break
        sleep 1
    done
    # Hard kill any survivor.
    for p in "${VM_HOST_PIDS[@]:-}"; do
        [ -z "$p" ] && continue
        kill -0 "$p" 2>/dev/null || continue
        kill -KILL "$p" 2>/dev/null || true
    done
    VM_HOST_PIDS=()
}

launch_workload_container_guest() {
    # Workload + profiler both run INSIDE the container (own PID namespace).
    # The host script later launches the profiler via `docker exec` (see
    # run_profiler_inguest_container) so it inherits the container's namespaces.
    #
    # Bind mounts:
    #   /opt/intp        ← repo root (binaries; read-only)
    #   /sys/fs/resctrl  ← RDT control fs (RW; profiler creates groups)
    #   /sys/kernel/btf  ← BTF for v3 (read-only)
    # Capabilities:
    #   CAP_PERFMON      perf_event_open without paranoid<-1
    #   CAP_BPF          load eBPF programs (5.8+)
    #   CAP_SYS_RESOURCE bump RLIMIT_MEMLOCK for BPF maps
    #   CAP_SYS_ADMIN    SystemTap module load (v0/v0.1/v1/v1.1)
    #   CAP_NET_ADMIN    bpftrace tracepoints touching net
    local logfile="$1" duration="$2" args="$3" name="$4"
    CURRENT_WORKLOAD_CGROUP=""
    if [ "$DRY_RUN" -eq 1 ]; then
        log "DRY: docker run (in-guest profiler) ... stress-ng $args"
        echo $$
        return 0
    fi
    if ! command -v docker >/dev/null 2>&1; then
        warn "docker not installed -- container-guest launch failed"
        echo 0; return 1
    fi
    docker rm -f "$name" >/dev/null 2>&1 || true

    local extra_caps=(
        --cap-add CAP_PERFMON --cap-add CAP_BPF
        --cap-add CAP_SYS_RESOURCE --cap-add CAP_SYS_ADMIN
        --cap-add CAP_SYS_NICE --cap-add CAP_NET_ADMIN
    )
    local extra_mounts=(
        -v "$REPO_ROOT:/opt/intp:ro"
    )
    if [ -d /sys/fs/resctrl ]; then
        extra_mounts+=(-v /sys/fs/resctrl:/sys/fs/resctrl)
    fi
    if [ -d /sys/kernel/btf ]; then
        extra_mounts+=(-v /sys/kernel/btf:/sys/kernel/btf:ro)
    fi
    if [ -d /usr/lib/modules ]; then
        # SystemTap variants need access to host kernel modules
        extra_mounts+=(-v /usr/lib/modules:/usr/lib/modules:ro)
    fi
    if [ -d /lib/modules ] && [ ! -L /lib/modules ]; then
        extra_mounts+=(-v /lib/modules:/lib/modules:ro)
    fi

    # Parity caps applied at the docker layer; same warn-and-retry fallback
    # as launch_workload_container in case the host cgroup driver rejects them.
    local parity_args=()
    [ -n "$BENCH_CPUS" ] && parity_args+=( --cpus="$BENCH_CPUS" )
    [ -n "$BENCH_MEM" ]  && parity_args+=( --memory="$BENCH_MEM" )

    docker run --rm -d --name "$name" \
        --network host \
        "${parity_args[@]}" \
        "${extra_caps[@]}" \
        "${extra_mounts[@]}" \
        "$CONTAINER_IMAGE" \
        bash -c "set -e
            apt-get update -qq && apt-get install -y -qq \
                stress-ng systemtap bpftrace linux-tools-generic >/dev/null 2>&1 || true
            stress-ng $args --timeout ${duration}s --metrics-brief &
            echo \$! > /tmp/intp-wl.pid
            wait \$!" \
        > "$logfile" 2>&1 \
        || {
            warn "[parity/container-guest] docker run with --cpus/--memory failed; retrying without parity caps"
            docker run --rm -d --name "$name" \
                --network host \
                "${extra_caps[@]}" \
                "${extra_mounts[@]}" \
                "$CONTAINER_IMAGE" \
                bash -c "set -e
                    apt-get update -qq && apt-get install -y -qq \
                        stress-ng systemtap bpftrace linux-tools-generic >/dev/null 2>&1 || true
                    stress-ng $args --timeout ${duration}s --metrics-brief &
                    echo \$! > /tmp/intp-wl.pid
                    wait \$!" \
                > "$logfile" 2>&1
        }
    # Wait briefly for stress-ng to start, then return its container-local PID
    local cpid="" attempt
    for attempt in 1 2 3 4 5 6 7 8 9 10; do
        cpid=$(docker exec "$name" cat /tmp/intp-wl.pid 2>/dev/null || true)
        [ -n "$cpid" ] && break
        sleep 0.5
    done
    [ -z "$cpid" ] && cpid=0
    echo "$cpid"
}

launch_workload_vm() {
    local logfile="$1" duration="$2" args="$3" name="$4"
    CURRENT_WORKLOAD_CGROUP=""
    # Default SLIRP user-net path leaves the tap iface empty; the optional
    # tap-netdev path below sets it. Reset here so a prior VM run's tap iface
    # never leaks into this run's profiler dispatch.
    CURRENT_VM_TAP_IFACE=""
    if [ "$DRY_RUN" -eq 1 ]; then
        if [ "${INTP_BENCH_VM_TAP:-0}" = "1" ]; then
            CURRENT_VM_TAP_IFACE="intp-tap-$name"
            log "DRY: qemu-system-x86_64 -enable-kvm ... -netdev tap,ifname=$CURRENT_VM_TAP_IFACE ... stress-ng $args"
        else
            log "DRY: qemu-system-x86_64 -enable-kvm ... -netdev user ... stress-ng $args"
        fi
        echo $$
        return 0
    fi
    # Hard-fail on missing prereqs. Previously these were warn+continue, which
    # produced "successful" runs that measured an empty qemu host process and
    # silently polluted the dataset. For paper-grade results, fail loud.
    if [ -z "$VM_IMAGE" ] || [ ! -f "$VM_IMAGE" ]; then
        die "VM env requested but VM_IMAGE is not set or file missing: '$VM_IMAGE'"
    fi
    if [ ! -e /dev/kvm ]; then
        die "/dev/kvm not present -- VM env unavailable. Install qemu-kvm and ensure /dev/kvm is accessible."
    fi
    if ! command -v qemu-system-x86_64 >/dev/null 2>&1; then
        die "qemu-system-x86_64 not in PATH. Install qemu-system-x86 (apt: qemu-system-x86)."
    fi
    if ! command -v cloud-localds >/dev/null 2>&1; then
        die "cloud-localds not in PATH. Install cloud-image-utils (apt: cloud-image-utils)."
    fi

    # Caveat documented for the operator:
    # ------------------------------------------------------------------------
    # SEMANTICS: The PID returned here is the qemu-system-x86_64 host process.
    # IntP profilers attach to that PID and observe the *host-side* view of
    # the VM (CPU time spent in qemu, memory bandwidth on host, host LLC
    # contention, host NIC traffic for SLIRP/TAP, host block I/O for the
    # qcow2 backing). They do NOT see the guest's per-process metrics —
    # those would require running a profiler INSIDE the guest and shipping
    # results back over SSH. Use INTP_VM_IN_GUEST=1 with INTP_VM_GUEST_SSH
    # to enable that path (currently a documented TODO; falls back to
    # host-observer mode otherwise).
    # ------------------------------------------------------------------------
    if [ "${INTP_VM_IN_GUEST:-0}" = "1" ]; then
        warn "INTP_VM_IN_GUEST=1 set but in-guest profiler hook not yet implemented; falling back to host-observer mode"
    fi

    local tmpdir; tmpdir="$(mktemp -d -t intp-vm-XXXXXX)"
    VM_TMPDIRS+=("$tmpdir")

    cat > "$tmpdir/user-data" <<EOF
#cloud-config
package_update: true
packages: [stress-ng]
runcmd:
  - [ bash, -lc, "stress-ng $args --timeout ${duration}s --metrics-brief; poweroff" ]
EOF
    cat > "$tmpdir/meta-data" <<EOF
instance-id: intp-bench-$name
local-hostname: intp-bench
EOF
    cloud-localds "$tmpdir/seed.iso" "$tmpdir/user-data" "$tmpdir/meta-data" \
        || die "cloud-localds failed to build seed.iso for $name"

    # Per-instance qcow2 overlay over the read-only base (see launch_workload_vm_guest):
    # qemu write-locks the image it opens, so concurrent VMs must each use their own
    # overlay rather than open $VM_IMAGE directly.
    local overlay="$tmpdir/overlay.qcow2"
    qemu-img create -q -f qcow2 -b "$VM_IMAGE" -F qcow2 "$overlay" \
        || die "qemu-img overlay create failed for $name (base: $VM_IMAGE)"

    # Networking: default to SLIRP user-net (no host tap, requires no setup).
    # Opt into a host tap interface with INTP_BENCH_VM_TAP=1 so the host can
    # observe per-VM NIC traffic on intp-tap-<name>; v3.3 (and v2.1) then pass
    # --target-vm "$CURRENT_VM_TAP_IFACE". Without the tap there is no host-side
    # per-VM netp signal and VM netp degrades to a system-wide observation.
    # The tap device must already exist / be creatable for the qemu user
    # (script=no,downscript=no means qemu will NOT bring it up itself); set up
    # the bridge/tap out of band. Falls back to SLIRP if creation is impossible.
    local netdev_args=( -netdev "user,id=n0" -device "virtio-net-pci,netdev=n0" )
    if [ "${INTP_BENCH_VM_TAP:-0}" = "1" ]; then
        local tapif="intp-tap-$name"
        netdev_args=( -netdev "tap,id=n0,ifname=$tapif,script=no,downscript=no"
                      -device "virtio-net-pci,netdev=n0" )
        CURRENT_VM_TAP_IFACE="$tapif"
        log "  VM tap path enabled: host tap iface=$tapif (v3.3/v2.1 will use --target-vm $tapif)"
    fi

    qemu-system-x86_64 -enable-kvm -nographic \
        -name "$name" \
        -smp "$VM_CPUS" -m "$VM_MEM" \
        -drive "file=$overlay,if=virtio,format=qcow2" \
        -drive "file=$tmpdir/seed.iso,if=virtio,format=raw" \
        "${netdev_args[@]}" \
        > "$logfile" 2>&1 &
    local qpid=$!
    VM_HOST_PIDS+=("$qpid")
    echo "$qpid"
}

# Tracks ephemeral SSH keys + per-VM ports for vm-guest cleanup.
VM_GUEST_KEYS=()
VM_GUEST_PORTS=()

_vm_guest_cleanup() {
    local k
    for k in "${VM_GUEST_KEYS[@]:-}"; do
        [ -n "$k" ] && [ -f "$k" ] && rm -f "$k" "$k.pub"
    done
    VM_GUEST_KEYS=()
    VM_GUEST_PORTS=()
}

# Allocate a free TCP port in 12200–12299 for SSH forward to a vm-guest VM.
_vm_alloc_port() {
    local p used
    for p in $(seq 12200 12299); do
        used=$(ss -tln 2>/dev/null | awk -v p=":$p$" '$4 ~ p {print}' | wc -l)
        if [ "$used" -eq 0 ] && ! printf '%s\n' "${VM_GUEST_PORTS[@]:-}" | grep -qx "$p"; then
            echo "$p"; return 0
        fi
    done
    echo ""
    return 1
}

launch_workload_vm_guest() {
    # Workload + profiler run INSIDE the guest. Cloud-init provisions an
    # ephemeral SSH keypair so the host can scp the profiler binary in,
    # launch it via SSH, and scp results back. Requires the qcow2 to have
    # cloud-init + sshd + (kernel headers for stap variants OR libbpf for
    # eBPF variants); pre-installing IntP build dependencies in the qcow2
    # is RECOMMENDED to keep launch latency tractable.
    #
    # The function exports VM_GUEST_SSH_PORT, VM_GUEST_SSH_KEY, VM_GUEST_NAME
    # so run_profiler_inguest_vm() can use them. Returns qemu host PID.
    local logfile="$1" duration="$2" args="$3" name="$4"
    CURRENT_WORKLOAD_CGROUP=""
    if [ "$DRY_RUN" -eq 1 ]; then
        log "DRY: qemu-system-x86_64 -enable-kvm -cpu host,pmu=on + cloud-init SSH ... stress-ng $args"
        echo $$
        return 0
    fi
    [ -z "$VM_IMAGE" ] || [ ! -f "$VM_IMAGE" ] && die "vm-guest needs VM_IMAGE: '$VM_IMAGE'"
    [ -e /dev/kvm ] || die "/dev/kvm absent — vm-guest unavailable"
    command -v qemu-system-x86_64 >/dev/null 2>&1 || die "qemu-system-x86_64 not in PATH"
    command -v cloud-localds >/dev/null 2>&1 || die "cloud-localds not in PATH"
    command -v ssh >/dev/null 2>&1 || die "ssh client missing (apt: openssh-client)"

    local tmpdir; tmpdir="$(mktemp -d -t intp-vmg-XXXXXX)"
    VM_TMPDIRS+=("$tmpdir")
    local sshport; sshport=$(_vm_alloc_port)
    [ -z "$sshport" ] && die "no free TCP port in 12200-12299 for vm-guest SSH"
    VM_GUEST_PORTS+=("$sshport")

    # Ephemeral keypair, deleted on EXIT trap (_vm_guest_cleanup)
    ssh-keygen -t ed25519 -N '' -q -f "$tmpdir/key"
    VM_GUEST_KEYS+=("$tmpdir/key")
    local pubkey; pubkey=$(cat "$tmpdir/key.pub")

    cat > "$tmpdir/user-data" <<EOF
#cloud-config
package_update: true
packages: [stress-ng, openssh-server]
users:
  - name: intp
    ssh_authorized_keys: ["$pubkey"]
    sudo: ALL=(ALL) NOPASSWD:ALL
    shell: /bin/bash
    groups: [sudo]
runcmd:
  - [ systemctl, enable, --now, ssh ]
EOF
    cat > "$tmpdir/meta-data" <<EOF
instance-id: intp-bench-$name
local-hostname: intp-bench
EOF
    cloud-localds "$tmpdir/seed.iso" "$tmpdir/user-data" "$tmpdir/meta-data" \
        || die "cloud-localds failed for vm-guest $name"

    # Per-instance qcow2 OVERLAY backed by the read-only base image. qemu
    # write-locks the image it opens, so two concurrent VMs (pairwise: aggressor +
    # victim) cannot both open $VM_IMAGE directly -- the 2nd fails to start and its
    # sshd is unreachable ("port refused"). A copy-on-write overlay per VM lets any
    # number of VMs share the base read-only (the vpmu-probe.sh pattern). Used for
    # solo too (one code path); cleaned with $tmpdir on EXIT.
    local overlay="$tmpdir/overlay.qcow2"
    qemu-img create -q -f qcow2 -b "$VM_IMAGE" -F qcow2 "$overlay" \
        || die "qemu-img overlay create failed for vm-guest $name (base: $VM_IMAGE)"

    # -cpu host,pmu=on (C25/P5): expose the host CPU model + a virtual PMU to
    # the guest so the in-guest profiler can read perf LLC counters => llcmr is
    # measurable in vm-guest (directional). Requires KVM (-enable-kvm, present).
    # Without it the guest gets qemu64 with no PMU and llcmr degrades to 0.
    # (Real-NIC netp/nets via a TAP device is wired with the cross-env-net
    # dispatch; vm-guest keeps -netdev user for the SSH-based profiler launch.)
    qemu-system-x86_64 -enable-kvm -nographic \
        -name "$name" \
        -cpu host,pmu=on \
        -smp "$VM_CPUS" -m "$VM_MEM" \
        -drive "file=$overlay,if=virtio,format=qcow2" \
        -drive "file=$tmpdir/seed.iso,if=virtio,format=raw" \
        -netdev user,id=n0,hostfwd=tcp::${sshport}-:22 \
        -device virtio-net-pci,netdev=n0 \
        > "$logfile" 2>&1 &
    local qpid=$!
    VM_HOST_PIDS+=("$qpid")

    # Wait up to 120 s for sshd. Cloud images usually boot in 30-60 s.
    local i
    for i in $(seq 1 60); do
        if ssh -o BatchMode=yes -o ConnectTimeout=2 -o StrictHostKeyChecking=no \
               -o UserKnownHostsFile=/dev/null \
               -i "$tmpdir/key" -p "$sshport" intp@127.0.0.1 'true' >/dev/null 2>&1; then
            break
        fi
        sleep 2
    done

    # Persist the per-run state for run_profiler_inguest_vm()
    echo "$sshport"   > "$tmpdir/.sshport"
    echo "$tmpdir"    > "$tmpdir/.tmpdir"
    export INTP_VMG_TMPDIR="$tmpdir"
    export INTP_VMG_SSHPORT="$sshport"

    # Start stress-ng inside the guest, in a DEDICATED guest cgroup, so the in-guest
    # profiler scopes to the whole stress-ng tree via --cgroup instead of --pids on
    # the (idle) supervisor PID (T1). NEW (vm-guest pairwise reorder): the workload
    # start is SPLIT out into _vmg_start_workload and SKIPPED under INTP_VMG_BOOT_ONLY
    # so the pairwise path can boot the aggressor VM idle, boot the victim VM cleanly,
    # and only then trigger the aggressor attack (see stage_pairwise / run_one). For
    # solo + the victim, the workload still starts here, right after boot.
    local guest_cg="/sys/fs/cgroup/intp-vmg-wl"
    local gpid=0
    if [ "${INTP_VMG_BOOT_ONLY:-0}" = "1" ]; then
        log "  vm-guest $name: booted idle (boot-only); workload deferred to the attack trigger"
    else
        gpid=$(_vmg_start_workload "$tmpdir" "$sshport" "$guest_cg" "$args" "$duration")
    fi
    # Return host-side qemu PID so the existing stop_workload path can kill it. The
    # guest workload cgroup (profiler scoping) + PID (informational) are published.
    export INTP_VMG_GUEST_PID="$gpid"
    export INTP_VMG_GUEST_CGROUP="$guest_cg"
    # C25/P5: the exports above are lost across the launch_workload subshell; publish
    # the vm-guest state (incl. for boot-only, so the caller can trigger the attack).
    _vmg_publish_state "$logfile" "$tmpdir" "$sshport" "$gpid" "$guest_cg"
    echo "$qpid"
}

launch_workload_container_full() {
    # All-in-one container: HDFS + Spark + workload + profiler INSIDE.
    # Host-side HDFS/YARN must already be paused (host-services.sh pause).
    # This is the deployment-isolated mode for paper-grade comparisons.
    #
    # The variant is read from $CURRENT_VARIANT (set by run_one before launch).
    # Output: profiler.tsv lands in the bind-mounted $RUN_OUTDIR via
    # /opt/results inside the container.
    local logfile="$1" duration="$2" args="$3" name="$4"
    CURRENT_WORKLOAD_CGROUP=""
    if [ "$DRY_RUN" -eq 1 ]; then
        log "DRY: container-full $INTP_FULL_IMAGE run-stressng $CURRENT_VARIANT $args (${duration}s)"
        echo $$
        return 0
    fi
    if ! command -v docker >/dev/null 2>&1; then
        warn "docker not installed -- container-full launch failed"
        echo 0; return 1
    fi
    if ! docker image inspect "$INTP_FULL_IMAGE" >/dev/null 2>&1; then
        warn "image '$INTP_FULL_IMAGE' not found — build with bench/deploy/build-full-image.sh"
        echo 0; return 1
    fi
    docker rm -f "$name" >/dev/null 2>&1 || true

    # Detect host-services pause status and warn loudly if HDFS/YARN still up
    # (port 9000 collision would fail HDFS startup inside container).
    if ss -tln 2>/dev/null | awk '{print $4}' | grep -qE ':9000$'; then
        warn "host port 9000 is still bound — pause host services first:"
        warn "  bash bench/deploy/host-services.sh pause"
    fi

    # The container needs SYS_ADMIN for SystemTap variants and CAP_BPF/PERFMON
    # for v3/v3.1; we grant the union since one image handles all variants.
    docker run --rm -d --name "$name" \
        --network host \
        --cap-add SYS_ADMIN --cap-add SYS_RESOURCE --cap-add SYS_NICE \
        --cap-add NET_ADMIN --cap-add CAP_PERFMON --cap-add CAP_BPF \
        -v "$REPO_ROOT:/opt/intp:ro" \
        -v "$RUN_OUTDIR:/opt/results" \
        -v /sys/kernel/btf:/sys/kernel/btf:ro \
        -v /sys/fs/resctrl:/sys/fs/resctrl \
        -v /usr/lib/modules:/usr/lib/modules:ro \
        -e "INTP_DURATION=$duration" \
        -e "INTP_INTERVAL=$INTERVAL" \
        "$INTP_FULL_IMAGE" \
        bash -lc "intp-entrypoint start-hdfs && \
                  intp-entrypoint run-stressng $CURRENT_VARIANT $args" \
        > "$logfile" 2>&1
    # Return container's host PID (qemu/main process) for stop_workload tracking.
    local cpid
    cpid=$(docker inspect -f '{{.State.Pid}}' "$name" 2>/dev/null || echo 0)
    echo "$cpid"
}

launch_workload_vm_full() {
    # All-in-one VM: HDFS + Spark + workload + profiler INSIDE the guest.
    # Requires INTP_FULL_VM_IMAGE pointing at a qcow2 produced by
    # bench/deploy/build-full-vm.sh. SSH key + 9p share scaffolded by
    # cloud-init as in launch_workload_vm_guest, but the entrypoint is the
    # baked-in /usr/local/bin/intp-entrypoint script.
    local logfile="$1" duration="$2" args="$3" name="$4"
    CURRENT_WORKLOAD_CGROUP=""
    if [ "$DRY_RUN" -eq 1 ]; then
        log "DRY: vm-full $INTP_FULL_VM_IMAGE boot + intp-entrypoint run-stressng $CURRENT_VARIANT $args"
        echo $$
        return 0
    fi
    [ -z "$INTP_FULL_VM_IMAGE" ] || [ ! -f "$INTP_FULL_VM_IMAGE" ] && \
        die "vm-full needs INTP_FULL_VM_IMAGE (build via bench/deploy/build-full-vm.sh): '$INTP_FULL_VM_IMAGE'"
    [ -e /dev/kvm ] || die "/dev/kvm absent — vm-full unavailable"
    command -v qemu-system-x86_64 >/dev/null 2>&1 || die "qemu-system-x86_64 not in PATH"
    command -v cloud-localds >/dev/null 2>&1 || die "cloud-localds not in PATH"

    local tmpdir; tmpdir="$(mktemp -d -t intp-vmf-XXXXXX)"
    VM_TMPDIRS+=("$tmpdir")
    local sshport; sshport=$(_vm_alloc_port)
    [ -z "$sshport" ] && die "no free TCP port for vm-full SSH"
    VM_GUEST_PORTS+=("$sshport")

    ssh-keygen -t ed25519 -N '' -q -f "$tmpdir/key"
    VM_GUEST_KEYS+=("$tmpdir/key")
    local pubkey; pubkey=$(cat "$tmpdir/key.pub")

    cat > "$tmpdir/user-data" <<EOF
#cloud-config
users:
  - name: intp
    ssh_authorized_keys: ["$pubkey"]
    sudo: ALL=(ALL) NOPASSWD:ALL
    shell: /bin/bash
    groups: [sudo]
runcmd:
  - [ systemctl, enable, --now, ssh ]
  - [ bash, -lc, "intp-entrypoint start-hdfs >> /var/log/intp-bootstrap.log 2>&1 &" ]
EOF
    cat > "$tmpdir/meta-data" <<EOF
instance-id: intp-bench-$name
local-hostname: intp-bench
EOF
    cloud-localds "$tmpdir/seed.iso" "$tmpdir/user-data" "$tmpdir/meta-data" \
        || die "cloud-localds failed for vm-full $name"

    # Per-instance qcow2 overlay over the read-only base (see launch_workload_vm_guest):
    # qemu write-locks the image, so concurrent VMs each need their own overlay.
    local overlay="$tmpdir/overlay.qcow2"
    qemu-img create -q -f qcow2 -b "$INTP_FULL_VM_IMAGE" -F qcow2 "$overlay" \
        || die "qemu-img overlay create failed for vm-full $name (base: $INTP_FULL_VM_IMAGE)"

    qemu-system-x86_64 -enable-kvm -nographic \
        -name "$name" \
        -smp "$VM_CPUS" -m "$VM_MEM" \
        -drive "file=$overlay,if=virtio,format=qcow2" \
        -drive "file=$tmpdir/seed.iso,if=virtio,format=raw" \
        -netdev user,id=n0,hostfwd=tcp::${sshport}-:22 \
        -device virtio-net-pci,netdev=n0 \
        > "$logfile" 2>&1 &
    local qpid=$!
    VM_HOST_PIDS+=("$qpid")

    # Wait for sshd
    local i
    for i in $(seq 1 90); do
        if ssh -o BatchMode=yes -o ConnectTimeout=2 -o StrictHostKeyChecking=no \
               -o UserKnownHostsFile=/dev/null \
               -i "$tmpdir/key" -p "$sshport" intp@127.0.0.1 'true' >/dev/null 2>&1; then
            break
        fi
        sleep 2
    done

    export INTP_VMG_TMPDIR="$tmpdir"
    export INTP_VMG_SSHPORT="$sshport"

    # Launch workload+profiler via the baked-in entrypoint, results land in
    # /opt/results inside guest; we scp profiler.tsv back via run_profiler
    # (vm-full reuses the vm-guest profiler-fetch path).
    ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
        -i "$tmpdir/key" -p "$sshport" intp@127.0.0.1 \
        "sudo bash -lc 'INTP_DURATION=$duration INTP_INTERVAL=$INTERVAL \
            intp-entrypoint run-stressng $CURRENT_VARIANT $args > /tmp/wl.log 2>&1 &'" \
        || warn "ssh dispatch to vm-full failed for $name"
    sleep 1
    echo "$qpid"
}

launch_workload() {
    # $1 env, $2 logfile, $3 duration, $4 stress_args, $5 unique_name
    # Clear the VM tap iface before every workload; only launch_workload_vm
    # under INTP_BENCH_VM_TAP=1 re-sets it. Prevents a prior VM-tap run from
    # leaking --target-vm into a later bare/container/SLIRP run.
    CURRENT_VM_TAP_IFACE=""
    case "$1" in
        bare)             launch_workload_bare            "$2" "$3" "$4" "$5" ;;
        container)        launch_workload_container       "$2" "$3" "$4" "$5" ;;
        container-podman) launch_workload_container_podman "$2" "$3" "$4" "$5" ;;
        container-k8s)    launch_workload_container_k8s   "$2" "$3" "$4" "$5" ;;
        container-lxc)    launch_workload_container_lxc   "$2" "$3" "$4" "$5" ;;
        container-guest)  launch_workload_container_guest "$2" "$3" "$4" "$5" ;;
        container-full)   launch_workload_container_full  "$2" "$3" "$4" "$5" ;;
        vm)               launch_workload_vm              "$2" "$3" "$4" "$5" ;;
        vm-guest)         launch_workload_vm_guest        "$2" "$3" "$4" "$5" ;;
        vm-full)          launch_workload_vm_full         "$2" "$3" "$4" "$5" ;;
        *) die "Unknown env: $1" ;;
    esac
}

stop_workload() {
    local env="$1" pid="$2" name="$3" cgroup_path="${4:-}"
    [ "$DRY_RUN" -eq 1 ] && return 0
    case "$env" in
        bare)
            terminate_pid_gracefully "$pid" "stop_workload/bare/$name"
            if [ -n "$cgroup_path" ] && [ -d "$cgroup_path" ]; then
                rmdir "$cgroup_path" 2>/dev/null || true
            fi
            ;;
        container|container-guest|container-full)
            docker rm -f "$name" >/dev/null 2>&1 || true
            ;;
        container-podman)
            # Mirrors the docker arm; --rm already reaps a finished container,
            # this force-removes a still-running one. Best-effort, never aborts.
            "$PODMAN_BIN" rm -f "$name" >/dev/null 2>&1 || true
            ;;
        container-k8s)
            # Mirrors the docker/podman arm: force-delete the pod (and its
            # containerd scope cgroup) whether finished or still Running.
            # restartPolicy Never means it won't relaunch. Best-effort.
            "$KUBECTL" delete pod "intp-k8s-$name" -n "$K8S_NS" \
                --force --grace-period=0 >/dev/null 2>&1 || true
            ;;
        container-lxc)
            # Deleting the instance stops it and reaps its cgroup; --force
            # covers a still-running container. Sanitize to the same name the
            # launcher used (incus name rules). Best-effort, never aborts.
            "$LXC_BIN" delete --force "$(_lxc_instance_name "$name")" >/dev/null 2>&1 || true
            ;;
        vm|vm-full)
            terminate_pid_gracefully "$pid" "stop_workload/$env/$name"
            _vm_forget_host_pid "$pid"
            ;;
        vm-guest)
            # Best-effort guest-side cleanup before host-side qemu kill.
            if [ -n "${INTP_VMG_TMPDIR:-}" ] && [ -d "$INTP_VMG_TMPDIR" ]; then
                local sshport="${INTP_VMG_SSHPORT:-}"
                if [ -n "$sshport" ]; then
                    ssh -o BatchMode=yes -o ConnectTimeout=3 -o StrictHostKeyChecking=no \
                        -o UserKnownHostsFile=/dev/null \
                        -i "$INTP_VMG_TMPDIR/key" -p "$sshport" intp@127.0.0.1 \
                        'sudo poweroff' 2>/dev/null || true
                fi
            fi
            sleep 2
            terminate_pid_gracefully "$pid" "stop_workload/vm-guest/$name"
            _vm_forget_host_pid "$pid"
            ;;
    esac
}

# -----------------------------------------------------------------------------
# 10. Profiler launchers (one per variant)
#
# All write their output to $outfile in a normalised TSV: 7 metrics per row,
# whitespace-separated, optionally with a `# header` line. The plot script
# treats `--` as missing.
# -----------------------------------------------------------------------------

start_resctrl_helper() {
    [ "$ACTIVE_RESCTRL_HELPER" -eq 1 ] && return 0
    [ "$DRY_RUN" -eq 1 ] && { ACTIVE_RESCTRL_HELPER=1; return 0; }
    if [ -x "$RESCTRL_HELPER" ]; then
        "$RESCTRL_HELPER" start >/dev/null 2>&1 || true
    fi
    # Also create our own monitoring group "intp-bench" so groundtruth can
    # read the same numbers the profiler sees. Resctrl is reference-counted.
    if [ -d /sys/fs/resctrl ] && [ ! -d /sys/fs/resctrl/intp-bench ]; then
        mkdir -p /sys/fs/resctrl/intp-bench 2>/dev/null || true
    fi
    ACTIVE_RESCTRL_HELPER=1
}

stop_resctrl_helper() {
    [ "$ACTIVE_RESCTRL_HELPER" -eq 0 ] && return 0
    [ "$DRY_RUN" -eq 1 ] && { ACTIVE_RESCTRL_HELPER=0; return 0; }
    rmdir /sys/fs/resctrl/intp-bench 2>/dev/null || true
    [ -x "$RESCTRL_HELPER" ] && "$RESCTRL_HELPER" stop >/dev/null 2>&1 || true
    ACTIVE_RESCTRL_HELPER=0
}

# Force-unload all lingering stap_ kernel modules with retry + exponential
# backoff.  Called before every V1 stap launch and periodically between runs.
# Prevents the module-accumulation pattern that drains systemd DBus budget
# and stalls pam_systemd scope creation on the next SSH login.
stap_deep_cleanup() {
    local context="${1:-cleanup}"
    pkill -9 -f stapio  2>/dev/null || true
    pkill -9 -f staprun 2>/dev/null || true
    sleep 1
    local attempt mods
    for attempt in 1 2 3 4 5; do
        mods=$(lsmod | awk '/^stap_/ {print $1}')
        [ -z "$mods" ] && break
        for m in $mods; do
            rmmod "$m" 2>/dev/null || true
        done
        sleep "$attempt"
    done
    local remaining
    remaining=$(lsmod | awk '/^stap_/ {print $1}' | wc -l)
    if [ "$remaining" -gt 0 ]; then
        warn "[stap_deep_cleanup/$context] $remaining stap_ module(s) still loaded after 5 attempts; systemd may degrade"
    else
        log "[stap_deep_cleanup/$context] OK (0 stap_ modules in kernel)"
    fi
}

# Resolve the comm-name to attach SystemTap probes against. The launch wrapper
# is `bash -c '...; exec stress-ng'`, so during a small race window
# /proc/$pid/comm reads as "bash" before exec. If we trace "bash" we end up
# self-monitoring the orchestration scripts, which creates recursive probe
# pressure and can deadlock the kernel under load. Wait briefly for exec to
# land, and refuse to ever target shell wrappers.
_detect_stap_target() {
    local pid="$1"
    local target="stress-ng"
    if [ -n "$pid" ] && [ "$pid" != "0" ] && [ -d "/proc/$pid" ]; then
        local _try
        for _try in 1 2 3 4 5 6 7 8 9 10; do
            target=$(awk '{print $2}' /proc/$pid/stat 2>/dev/null | tr -d '()')
            case "$target" in
                bash|sh|dash|"") sleep 0.5 ;;
                *) break ;;
            esac
        done
        case "$target" in
            bash|sh|dash|"") target="stress-ng" ;;
        esac
    fi
    printf '%s' "$target"
}

run_profiler_systemtap() {
    # $1 variant, $2 stp_path, $3 outfile, $4 duration, $5 target_pid
    local variant="$1" stp="$2" outfile="$3" duration="$4" pid="$5"
    local stap_log="${outfile%.tsv}.stap.log"
    if [ "$DRY_RUN" -eq 1 ]; then
        log "DRY: stap -g $stp <target> for ${duration}s -> $outfile"
        printf 'netp\tnets\tblk\tmbw\tllcmr\tllcocc\tcpu\n' > "$outfile"
        echo 0 > "$outfile.samples"
        return 0
    fi

    # SystemTap pre-run: increment run counter, clean any modules left from the
    # previous run, and do a full deep pause every V3_DEEP_CLEANUP_EVERY runs so
    # the kernel fully reclaims resources before loading the next stap_ module.
    # Applies to all stap-based variants (v0, v0.1, v1, v1.1) since any of them can
    # leak modules under load if a stapio orphan survives.
    case "$variant" in
        v0)
            V0_RUN_COUNT=$((V0_RUN_COUNT + 1))
            stap_deep_cleanup "pre-run-${variant}-${V0_RUN_COUNT}"
            if [ "$V0_RUN_COUNT" -gt 1 ] && [ $(( (V0_RUN_COUNT - 1) % V0_DEEP_CLEANUP_EVERY )) -eq 0 ]; then
                log "[$variant] periodic deep pause at run ${V0_RUN_COUNT} (every ${V0_DEEP_CLEANUP_EVERY} runs) — sleeping 8s"
                sleep 8
            fi
            ;;
        v0.1|v1|v1.1)
            V3_RUN_COUNT=$((V3_RUN_COUNT + 1))
            stap_deep_cleanup "pre-run-${variant}-${V3_RUN_COUNT}"
            if [ "$V3_RUN_COUNT" -gt 1 ] && [ $(( (V3_RUN_COUNT - 1) % V3_DEEP_CLEANUP_EVERY )) -eq 0 ]; then
                log "[$variant] periodic deep pause at run ${V3_RUN_COUNT} (every ${V3_DEEP_CLEANUP_EVERY} runs) — sleeping 8s"
                sleep 8
            fi
            ;;
    esac
    if [ "$variant" = "v1" ]; then
        start_resctrl_helper
    fi

    local target
    target=$(_detect_stap_target "$pid")
    log "  [$variant] stap target=$target (pid=$pid)"

    # Variant-specific stap globals (v1.1 takes NIC line rate via -G so the
    # netphy denominator adapts to 1/10/25/40/100 GbE without recompiling).
    # `capabilities.env` was written at orchestrator startup but not eval'd
    # into this shell; sourcing it here is cheap and keeps the function
    # self-contained.
    local extra_stap_args=()
    if [ "$variant" = "v1.1" ]; then
        local nic_mbps="${INTP_NIC_SPEED_MBPS:-}"
        if [ -z "$nic_mbps" ] && [ -f "$OUTPUT_DIR/capabilities.env" ]; then
            nic_mbps=$(awk -F= '/^INTP_NIC_SPEED_MBPS=/{print $2}' "$OUTPUT_DIR/capabilities.env" | head -1)
        fi
        if [ -n "$nic_mbps" ] && [ "$nic_mbps" -gt 0 ] 2>/dev/null; then
            extra_stap_args+=(-G "nic_bytes_per_sec=$((nic_mbps * 125000))")
        fi
    fi

    stap --suppress-handler-errors -g \
        -B CONFIG_MODVERSIONS=y \
        -DMAXSKIPPED=1000000 \
        -DSTP_OVERLOAD_THRESHOLD=2000000000LL \
        -DSTP_OVERLOAD_INTERVAL=1000000000LL \
        "${extra_stap_args[@]}" \
        "$stp" "$target" > "$stap_log" 2>&1 &
    local stap_pid=$!

    # Wait for /proc/.../intestbench
    local intestbench=""
    for _ in $(seq 1 30); do
        intestbench=$(find /proc/systemtap -name intestbench 2>/dev/null | head -1)
        [ -n "$intestbench" ] && break
        sleep 1
    done

    {
        printf '# variant=%s probe=%s pid=%s\n' "$variant" "$target" "$pid"
        printf 'ts\tnetp\tnets\tblk\tmbw\tllcmr\tllcocc\tcpu\n'
    } > "$outfile"

    if [ -z "$intestbench" ]; then
        warn "[$variant] /proc/systemtap/intestbench did not appear after 30s"
        terminate_pid_gracefully "$stap_pid" "stap/startup-timeout" || true
        stap_deep_cleanup "startup-timeout"
        echo 0 > "$outfile.samples"
        return 1
    fi

    local end=$(($(date +%s) + duration))
    while [ "$(date +%s)" -lt "$end" ]; do
        local ts; ts=$(date +%s.%N)
        local line
        line=$(timeout "$SYSTEMTAP_READ_TIMEOUT_S" awk '/^[0-9]/{l=$0}END{print l}' "$intestbench" 2>/dev/null || true)
        if [ -n "$line" ]; then
            printf '%s\t%s\n' "$ts" "$line" >> "$outfile"
        else
            warn "[$variant] sample read timeout/empty at ts=$ts"
        fi
        sleep "$INTERVAL"
    done

    terminate_pid_gracefully "$stap_pid" "stap/post-run" || true
    stap_deep_cleanup "post-run"

    awk '/^[0-9]/{n++}END{print n+0}' "$outfile" > "$outfile.samples"
}

run_profiler_systemtap_v0() {
    # V0 wraps run_profiler_systemtap with a per-run recalibration step plus
    # the forensic stall watchdog. The 2022 baseline embeds NIC/LLC/IMC/CMT/
    # MEM-BW constants for the original PUCRS dev machine; on any other host
    # they would produce garbage normalisation. generate-stp.sh sources
    # shared/intp-detect.sh, substitutes placeholders in intp.stp.template,
    # and writes intp.recal.stp. v0-stall-monitor.sh runs in parallel and
    # captures dmesg / sysrq evidence the moment stall indicators trip.
    local outfile="$1" duration="$2" pid="$3"
    local kv_log="${outfile%.tsv}.v0-calibration.kv"
    local monitor_dir
    monitor_dir="$(dirname -- "$outfile")/stall-monitor"
    local monitor_pid=""

    _v0_stop_monitor() {
        if [ -n "$monitor_pid" ] && kill -0 "$monitor_pid" 2>/dev/null; then
            kill -TERM "$monitor_pid" 2>/dev/null || true
            wait "$monitor_pid" 2>/dev/null || true
        fi
    }

    if [ "$DRY_RUN" -eq 1 ]; then
        log "DRY: $V0_GENERATOR -> $V0_RECAL_STP ; v0-stall-monitor.sh -> $monitor_dir ; stap $V0_RECAL_STP <target> for ${duration}s -> $outfile"
        : > "$kv_log"
        run_profiler_systemtap v0 "$V0_RECAL_STP" "$outfile" "$duration" "$pid"
        return $?
    fi

    if [ ! -x "$V0_GENERATOR" ]; then
        warn "[v0] generator not executable ($V0_GENERATOR)"
        return 1
    fi
    if ! "$V0_GENERATOR" > "$kv_log" 2>"${kv_log%.kv}.err"; then
        warn "[v0] generate-stp.sh failed (rc=$?); see ${kv_log%.kv}.err"
        cat "${kv_log%.kv}.err" >&2 || true
        return 1
    fi

    mkdir -p "$monitor_dir"
    if [ -x "$REPO_ROOT/bench/v0-stall-monitor.sh" ]; then
        OUT_DIR="$monitor_dir" TARGET_PID=AUTO \
            "$REPO_ROOT/bench/v0-stall-monitor.sh" \
            >"$monitor_dir/monitor.log" 2>&1 &
        monitor_pid=$!
    else
        warn "[v0] v0-stall-monitor.sh missing/not exec; running without forensic capture"
    fi

    # Ensure the monitor is reaped on timeout / crash / normal exit.
    trap '_v0_stop_monitor' EXIT
    run_profiler_systemtap v0 "$V0_RECAL_STP" "$outfile" "$duration" "$pid"
    local rc=$?
    _v0_stop_monitor
    trap - EXIT
    return $rc
}

run_profiler_systemtap_v0_2() {
    # v0.2 = V0-faithful stap + userspace helper, targeting kernel 5.15 GA.
    # The stap script keeps V0's probe set for netp/nets/blk/llcmr/cpu and
    # reads mbw/llcocc from /tmp/intp-v0.2-hw-data which intp-helper writes
    # once per second via perf_event_open(2) + resctrl mon_groups -- bypassing
    # V0's RCU-unsafe in-probe operations that destabilise stap on Ubuntu
    # 22.04's 5.15 kernel.
    #
    # This wrapper combines V0's per-rep recalibration + stall watchdog with
    # V1.1's helper-launch pattern. Helper env knobs (DRAM_BW_MBPS, L3_SIZE_KB,
    # IMC_PMU_TYPE) come from shared/intp-detect.sh output captured into the
    # calibration KV log.
    local outfile="$1" duration="$2" pid="$3"
    local kv_log="${outfile%.tsv}.v0.2-calibration.kv"
    local helper_log="${outfile%.tsv}.helper.log"
    local monitor_dir
    monitor_dir="$(dirname -- "$outfile")/stall-monitor"
    local monitor_pid=""
    local helper_pid=""

    _v0_2_stop_monitor() {
        if [ -n "$monitor_pid" ] && kill -0 "$monitor_pid" 2>/dev/null; then
            kill -TERM "$monitor_pid" 2>/dev/null || true
            wait "$monitor_pid" 2>/dev/null || true
        fi
    }
    _v0_2_stop_helper() {
        if [ -n "$helper_pid" ] && kill -0 "$helper_pid" 2>/dev/null; then
            kill -TERM "$helper_pid" 2>/dev/null || true
            local _try
            for _try in 1 2 3 4 5; do
                kill -0 "$helper_pid" 2>/dev/null || break
                sleep 0.5
            done
            kill -KILL "$helper_pid" 2>/dev/null || true
        fi
        wait "$helper_pid" 2>/dev/null || true
    }

    if [ "$DRY_RUN" -eq 1 ]; then
        log "DRY: $V0_2_GENERATOR -> $V0_2_RECAL_STP ; $V0_2_HELPER <target> & ; v0-stall-monitor.sh -> $monitor_dir ; stap $V0_2_RECAL_STP <target> for ${duration}s -> $outfile"
        : > "$kv_log"
        run_profiler_systemtap v0.2 "$V0_2_RECAL_STP" "$outfile" "$duration" "$pid"
        return $?
    fi

    if [ ! -x "$V0_2_GENERATOR" ]; then
        warn "[v0.2] generator not executable ($V0_2_GENERATOR)"
        return 1
    fi
    if [ ! -x "$V0_2_HELPER" ]; then
        warn "[v0.2] helper not built ($V0_2_HELPER); run 'make -C $REPO_ROOT/variants/v0.2-legacy-intp-baseline'"
        return 1
    fi
    if ! "$V0_2_GENERATOR" > "$kv_log" 2>"${kv_log%.kv}.err"; then
        warn "[v0.2] generate-stp.sh failed (rc=$?); see ${kv_log%.kv}.err"
        cat "${kv_log%.kv}.err" >&2 || true
        return 1
    fi

    # Pipe the matching subset of intp-detect.sh output to the helper via env.
    # Variables already eval'd above by generate-stp.sh; re-source here so we
    # can pass DRAM_BW, L3_SIZE, IMC_PMU_TYPE that the .stp side does not need.
    local detect_out
    detect_out="$("$REPO_ROOT/shared/intp-detect.sh" 2>/dev/null || true)"
    # shellcheck disable=SC2046
    eval "$(echo "$detect_out" | grep -E '^INTP_[A-Z0-9_]+=' || true)"

    local target
    target=$(_detect_stap_target "$pid")

    mkdir -p "$monitor_dir"
    if [ -x "$REPO_ROOT/bench/v0-stall-monitor.sh" ]; then
        OUT_DIR="$monitor_dir" TARGET_PID=AUTO \
            "$REPO_ROOT/bench/v0-stall-monitor.sh" \
            >"$monitor_dir/monitor.log" 2>&1 &
        monitor_pid=$!
    else
        warn "[v0.2] v0-stall-monitor.sh missing/not exec; running without forensic capture"
    fi

    rm -f /tmp/intp-v0.2-hw-data
    # IMC_PMU_TYPE_FIRST/LAST come from intp-detect.sh's filtered scan of
    # /sys/devices/uncore_imc_<N>/type (free_running pseudos excluded). The
    # helper iterates the full range so multi-channel hosts (SPR: 8 real
    # channels, types 73-80) get accurate mbw; without this it falls back
    # to a single type and undercounts by channel_count×. Parent-env
    # overrides take precedence.
    INTP_HELPER_DRAM_BW_MBPS="${INTP_MEM_BW_MBPS:-}" \
    INTP_HELPER_L3_SIZE_KB="${INTP_LLC_SIZE_KB:-}" \
    INTP_HELPER_IMC_PMU_TYPE="${INTP_IMC_PMU_TYPE:-}" \
    INTP_HELPER_IMC_PMU_TYPE_FIRST="${INTP_HELPER_IMC_PMU_TYPE_FIRST:-${INTP_IMC_PMU_TYPE_FIRST:-}}" \
    INTP_HELPER_IMC_PMU_TYPE_LAST="${INTP_HELPER_IMC_PMU_TYPE_LAST:-${INTP_IMC_PMU_TYPE_LAST:-}}" \
    INTP_HELPER_DATA_FILE="/tmp/intp-v0.2-hw-data" \
        "$V0_2_HELPER" "$target" >"$helper_log" 2>&1 &
    helper_pid=$!
    sleep 0.3

    # Reap helper + monitor on any exit path.
    trap '_v0_2_stop_helper; _v0_2_stop_monitor' EXIT
    run_profiler_systemtap v0.2 "$V0_2_RECAL_STP" "$outfile" "$duration" "$pid"
    local rc=$?
    _v0_2_stop_helper
    _v0_2_stop_monitor
    trap - EXIT
    return $rc
}

run_profiler_systemtap_v1_1() {
    # v1.1 = stap script + userspace helper. Helper owns the RCU-unsafe
    # operations (uncore IMC perf events, resctrl mon_group); the stap
    # script reads /tmp/intp-hw-data from a procfs read probe.
    local outfile="$1" duration="$2" pid="$3"
    local helper_log="${outfile%.tsv}.helper.log"

    if [ "$DRY_RUN" -eq 1 ]; then
        log "DRY: $V1_1_HELPER <target> & ; stap $V1_1_STP <target> for ${duration}s -> $outfile"
        printf 'netp\tnets\tblk\tmbw\tllcmr\tllcocc\tcpu\n' > "$outfile"
        echo 0 > "$outfile.samples"
        return 0
    fi

    if [ ! -x "$V1_1_HELPER" ]; then
        warn "[v1.1] helper not built ($V1_1_HELPER); run 'make -C $REPO_ROOT/variants/v1.1-stap-modern'"
        return 1
    fi

    local target
    target=$(_detect_stap_target "$pid")

    rm -f /tmp/intp-hw-data
    "$V1_1_HELPER" "$target" >"$helper_log" 2>&1 &
    local helper_pid=$!
    sleep 0.3   # give the helper a moment to open events and write the first line

    run_profiler_systemtap v1.1 "$V1_1_STP" "$outfile" "$duration" "$pid"
    local rc=$?

    if kill -0 "$helper_pid" 2>/dev/null; then
        kill -TERM "$helper_pid" 2>/dev/null || true
        local _try
        for _try in 1 2 3 4 5; do
            kill -0 "$helper_pid" 2>/dev/null || break
            sleep 0.5
        done
        kill -KILL "$helper_pid" 2>/dev/null || true
    fi
    wait "$helper_pid" 2>/dev/null || true

    return "$rc"
}

run_profiler_v2() {
    local outfile="$1" duration="$2" pid="$3" cgroup_path="${4:-}"
    if [ "$DRY_RUN" -eq 1 ]; then
        if [ -n "$cgroup_path" ]; then
            log "DRY: $V2_BIN --interval $INTERVAL --duration $duration --cgroup $cgroup_path -> $outfile"
        elif [ "$V_USE_PID_FILTER" = "1" ] && [ -n "$pid" ] && [ "$pid" != "0" ]; then
            log "DRY: $V2_BIN --interval $INTERVAL --duration $duration --pids $pid -> $outfile"
        else
            log "DRY: $V2_BIN --interval $INTERVAL --duration $duration (system-wide) -> $outfile"
        fi
        printf 'netp\tnets\tblk\tmbw\tllcmr\tllcocc\tcpu\n' > "$outfile"
        echo 0 > "$outfile.samples"
        return 0
    fi
    local args=( --interval "$INTERVAL" --duration "$duration" --output tsv )
    local scope="system-wide"
    if [ -n "$cgroup_path" ]; then
        args+=( --cgroup "$cgroup_path" )
        scope="cgroup=$cgroup_path"
    elif [ "$V_USE_PID_FILTER" = "1" ] && [ -n "$pid" ] && [ "$pid" != "0" ]; then
        args+=( --pids "$pid" )
        scope="pid=$pid"
    fi
    # Prefix every line with a wallclock timestamp via awk so all profilers
    # share the same (ts, metrics...) layout in their TSVs.
    {
        printf '# variant=v2 scope=%s\n' "$scope"
        "$V2_BIN" "${args[@]}" 2>"${outfile%.tsv}.v2.log" \
            | awk 'BEGIN{cmd="date +%s.%N"} /^#/||/^netp/{print;next} {cmd|getline ts;close(cmd); print ts"\t"$0}'
    } > "$outfile" || true
    awk '/^[0-9]/{n++}END{print n+0}' "$outfile" > "$outfile.samples"
}

# v2.1 is the c-abi-cgroup sibling of v2: same intp-c-abi CLI, but its
# cpu/blk/llcmr backends attribute per-cgroup (continuous) when --cgroup is
# given, and blk self-detects disk bandwidth. Pass --disk-bw-max-bps here if a
# measured per-host value is ever wired in (binary self-detects otherwise).
run_profiler_v2_1() {
    local outfile="$1" duration="$2" pid="$3" cgroup_path="${4:-}"
    if [ "$DRY_RUN" -eq 1 ]; then
        if [ -n "$cgroup_path" ]; then
            log "DRY: $V2_1_BIN --interval $INTERVAL --duration $duration --cgroup $cgroup_path -> $outfile"
        elif [ "$V_USE_PID_FILTER" = "1" ] && [ -n "$pid" ] && [ "$pid" != "0" ]; then
            log "DRY: $V2_1_BIN --interval $INTERVAL --duration $duration --pids $pid -> $outfile"
        elif [ -n "$pid" ] && [ "$pid" != "0" ]; then
            log "DRY: $V2_1_BIN --interval $INTERVAL --duration $duration --cgroup \$(resolve_pid_cgroup $pid) -> $outfile"
        else
            log "DRY: $V2_1_BIN --interval $INTERVAL --duration $duration (system-wide) -> $outfile"
        fi
        if [ "$PORTABLE_METRICS" = "1" ]; then
            printf 'netp\tnets\tblk\tmbw\tllcmr\tllcocc\tcpu\tschedlat\tpsi_mem\tmembw_est\tpsi_io\tschedthr\tsteal\n' > "$outfile"
            printf '0\t0\t0\t0\t0\t0\t0\t0\t0\t0\t0\t0\t0\n' >> "$outfile"
        else
            printf 'netp\tnets\tblk\tmbw\tllcmr\tllcocc\tcpu\n' > "$outfile"
        fi
        echo 0 > "$outfile.samples"
        return 0
    fi
    local args=( --interval "$INTERVAL" --duration "$duration" --output tsv )
    # Portable benchmark (C26): append the 6 VM-portable columns. Canonical 7
    # stay byte-identical; the capture lands in portable.tsv (run_one).
    [ "$PORTABLE_METRICS" = "1" ] && args+=( --portable-metrics )
    local scope="system-wide"
    if [ -n "$cgroup_path" ]; then
        args+=( --cgroup "$cgroup_path" )
        scope="cgroup=$cgroup_path"
    elif [ "$V_USE_PID_FILTER" = "1" ] && [ -n "$pid" ] && [ "$pid" != "0" ]; then
        args+=( --pids "$pid" )
        scope="pid=$pid"
    elif [ -n "$pid" ] && [ "$pid" != "0" ]; then
        # C25/P7 (T3 fix): for PID-launched envs (docker/podman hand a PID, not
        # a cgroup) resolve the PID's cgroup v2 path and scope v2.1 to it,
        # exactly as run_profiler_v3_3 does. Without this v2.1 falls to its
        # system-wide <root> resctrl mon_group and reports whole-machine L3
        # occupancy (llcocc ~97 in-container vs ~2 on bare; T3). --cgroup gives
        # the tenant's mon_group so occupancy attributes the tenant. The
        # residual incus(lxc) whole-container-cgroup scope artifact is not
        # addressed by this (it passes an explicit cgroup_path) and stays a
        # documented caveat.
        local cg21; cg21=$(resolve_pid_cgroup "$pid")
        if [ -n "$cg21" ]; then
            args+=( --cgroup "$cg21" )
            scope="cgroup=$cg21 (resolved from pid=$pid)"
        else
            warn "v2.1: could not resolve cgroup for pid=$pid; running system-wide"
        fi
    fi
    # When the optional VM tap path is active (INTP_BENCH_VM_TAP=1), point v2.1
    # at the per-VM tap iface too, mirroring run_profiler_v3_3, so the
    # v2.1<->v3.3 VM comparison observes the same NIC. Empty otherwise (SLIRP).
    if [ -n "${CURRENT_VM_TAP_IFACE:-}" ]; then
        args+=( --target-vm "$CURRENT_VM_TAP_IFACE" )
        scope="$scope tap=$CURRENT_VM_TAP_IFACE"
    fi
    {
        printf '# variant=v2.1 scope=%s\n' "$scope"
        "$V2_1_BIN" "${args[@]}" 2>"${outfile%.tsv}.v2.1.log" \
            | awk 'BEGIN{cmd="date +%s.%N"} /^#/||/^netp/{print;next} {cmd|getline ts;close(cmd); print ts"\t"$0}'
    } > "$outfile" || true
    awk '/^[0-9]/{n++}END{print n+0}' "$outfile" > "$outfile.samples"
}

run_profiler_v3_1() {
    local outfile="$1" duration="$2" pid="$3"
    if [ "$DRY_RUN" -eq 1 ]; then
        log "DRY: $V3_1_RUNNER --interval $INTERVAL --duration $duration --pid $pid -> $outfile"
        printf 'netp\tnets\tblk\tmbw\tllcmr\tllcocc\tcpu\n' > "$outfile"
        echo 0 > "$outfile.samples"
        return 0
    fi
    local args=( --interval "$INTERVAL" --duration "$duration" --header )
    if [ -n "$pid" ] && [ "$pid" != "0" ]; then args+=( --pid "$pid" ); fi
    {
        printf '# variant=v3.1 pid=%s\n' "$pid"
        "$V3_1_RUNNER" "${args[@]}" 2>"${outfile%.tsv}.v3.1.log" \
            | awk 'BEGIN{cmd="date +%s.%N"} /^#/||/^netp/{print;next} {cmd|getline ts;close(cmd); print ts"\t"$0}'
    } > "$outfile" || true
    awk '/^[0-9]/{n++}END{print n+0}' "$outfile" > "$outfile.samples"
}

# Resolve the bytes/sec memory-bandwidth ceiling to pass to v3/v3.2 as
# --mem-bw-max-bps. Cached after first call. Precedence:
#   1. explicit MEM_BW_MAX_BPS (env INTP_BENCH_MEM_BW_MAX_BPS) -- used as-is;
#   2. INTP_MEM_BW_MBPS from the capabilities.env written at the detect stage;
#   3. a direct shared/intp-detect.sh invocation.
# Cases 2/3 report MB/s, so they are multiplied by 1e6 -- the v3/v3.2 binaries
# expect bytes/sec and do NOT convert. Echoes the value (empty if undetermined).
resolve_mem_bw_max_bps() {
    if [ -n "$_MEM_BW_MAX_BPS_RESOLVED" ]; then
        printf '%s\n' "$_MEM_BW_MAX_BPS_RESOLVED"; return 0
    fi
    local bps="$MEM_BW_MAX_BPS" mbps=""
    if [ -z "$bps" ]; then
        if [ -n "${OUTPUT_DIR:-}" ] && [ -f "$OUTPUT_DIR/capabilities.env" ]; then
            mbps=$(awk -F= '/^INTP_MEM_BW_MBPS=/{v=$2} END{print v}' "$OUTPUT_DIR/capabilities.env" || true)
        fi
        # `|| true` and the END-print awk (no early `exit`) keep this safe
        # under `set -o pipefail` -- an early awk exit would SIGPIPE detect.
        if [ -z "$mbps" ] && [ -x "$DETECT_SH" ]; then
            mbps=$("$DETECT_SH" 2>/dev/null | awk -F= '/^INTP_MEM_BW_MBPS=/{v=$2} END{print v}' || true)
        fi
        case "$mbps" in
            ''|*[!0-9]*) bps="" ;;
            *)           bps=$(( mbps * 1000000 )) ;;   # MB/s -> B/s
        esac
        # log to stderr -- stdout is this function's return channel.
        [ -n "$bps" ] && log "mbw ceiling: ${bps} B/s (derived: ${mbps} MB/s × 1e6 from intp-detect.sh)" >&2
    else
        log "mbw ceiling: ${bps} B/s (explicit override)" >&2
    fi
    _MEM_BW_MAX_BPS_RESOLVED="$bps"
    printf '%s\n' "$bps"
}

run_profiler_v3() {
    local outfile="$1" duration="$2" pid="$3" cgroup_path="${4:-}"
    if [ "$DRY_RUN" -eq 1 ]; then
        if [ -n "$cgroup_path" ]; then
            log "DRY: $V3_BIN --interval $INTERVAL --duration $duration --cgroup $cgroup_path -> $outfile"
        elif [ "$V_USE_PID_FILTER" = "1" ] && [ -n "$pid" ] && [ "$pid" != "0" ]; then
            log "DRY: $V3_BIN --interval $INTERVAL --duration $duration --pids $pid -> $outfile"
        else
            log "DRY: $V3_BIN --interval $INTERVAL --duration $duration (system-wide) -> $outfile"
        fi
        printf 'netp\tnets\tblk\tmbw\tllcmr\tllcocc\tcpu\n' > "$outfile"
        echo 0 > "$outfile.samples"
        return 0
    fi
    local args=( --interval "$INTERVAL" --duration "$duration" --output tsv )
    local scope="system-wide"
    if [ -n "$cgroup_path" ]; then
        args+=( --cgroup "$cgroup_path" )
        scope="cgroup=$cgroup_path"
    elif [ "$V_USE_PID_FILTER" = "1" ] && [ -n "$pid" ] && [ "$pid" != "0" ]; then
        args+=( --pids "$pid" )
        scope="pid=$pid"
    fi
    local mbw_bps; mbw_bps="$(resolve_mem_bw_max_bps)"
    [ -n "$mbw_bps" ] && args+=( --mem-bw-max-bps "$mbw_bps" )
    {
        printf '# variant=v3 scope=%s\n' "$scope"
        "$V3_BIN" "${args[@]}" 2>"${outfile%.tsv}.v3.log" \
            | awk 'BEGIN{cmd="date +%s.%N"} /^#/||/^netp/{print;next} {cmd|getline ts;close(cmd); print ts"\t"$0}'
    } > "$outfile" || true
    awk '/^[0-9]/{n++}END{print n+0}' "$outfile" > "$outfile.samples"
}

run_profiler_v3_2() {
    # V3.2 (eBPF in-kernel aggregating). Same shape as run_profiler_v3
    # but invokes V3_2_BIN and passes --no-raw-mbw so the captured TSV
    # remains 7-column (compatible with the rest of the pipeline). The
    # mbw_raw_mbps diagnostic stream is opt-in -- analysts can re-run
    # outside the bench harness if they need it.
    local outfile="$1" duration="$2" pid="$3" cgroup_path="${4:-}"
    if [ "$DRY_RUN" -eq 1 ]; then
        if [ -n "$cgroup_path" ]; then
            log "DRY: $V3_2_BIN --interval $INTERVAL --duration $duration --cgroup $cgroup_path --no-raw-mbw -> $outfile"
        elif [ "$V_USE_PID_FILTER" = "1" ] && [ -n "$pid" ] && [ "$pid" != "0" ]; then
            log "DRY: $V3_2_BIN --interval $INTERVAL --duration $duration --pids $pid --no-raw-mbw -> $outfile"
        else
            log "DRY: $V3_2_BIN --interval $INTERVAL --duration $duration --no-raw-mbw (system-wide) -> $outfile"
        fi
        printf 'netp\tnets\tblk\tmbw\tllcmr\tllcocc\tcpu\n' > "$outfile"
        echo 0 > "$outfile.samples"
        return 0
    fi
    local args=( --interval "$INTERVAL" --duration "$duration"
                 --output tsv --no-raw-mbw )
    local scope="system-wide"
    if [ -n "$cgroup_path" ]; then
        args+=( --cgroup "$cgroup_path" )
        scope="cgroup=$cgroup_path"
    elif [ "$V_USE_PID_FILTER" = "1" ] && [ -n "$pid" ] && [ "$pid" != "0" ]; then
        args+=( --pids "$pid" )
        scope="pid=$pid"
    fi
    local mbw_bps; mbw_bps="$(resolve_mem_bw_max_bps)"
    [ -n "$mbw_bps" ] && args+=( --mem-bw-max-bps "$mbw_bps" )
    {
        printf '# variant=v3.2 scope=%s\n' "$scope"
        "$V3_2_BIN" "${args[@]}" 2>"${outfile%.tsv}.v3.2.log" \
            | awk 'BEGIN{cmd="date +%s.%N"} /^#/||/^netp/{print;next} {cmd|getline ts;close(cmd); print ts"\t"$0}'
    } > "$outfile" || true
    awk '/^[0-9]/{n++}END{print n+0}' "$outfile" > "$outfile.samples"
}

# Resolve a PID's cgroup v2 path (host view) to /sys/fs/cgroup<rel>, for the
# cgroup-only v3.3 profiler when a workload is launched by PID (docker/podman
# container, vm-guest) rather than in a pre-created cgroup. Empty if unresolvable.
resolve_pid_cgroup() {
    local pid="$1" cgrel
    [ -n "$pid" ] && [ "$pid" != "0" ] || return 0
    cgrel=$(awk -F: '/^0::/{print $3; exit}' "/proc/$pid/cgroup" 2>/dev/null)
    [ -n "$cgrel" ] && [ -d "/sys/fs/cgroup$cgrel" ] && printf '%s\n' "/sys/fs/cgroup$cgrel"
}

run_profiler_v3_3() {
    # V3.3 (eBPF c-abi-cgroup). Cloned verbatim from run_profiler_v3_2 but
    # invokes V3_3_BIN and passes --no-diag-cols EXACTLY where v3.2 passes
    # --no-raw-mbw (C13). This keeps the captured TSV at leading-ts + EXACTLY
    # the 7 canonical columns; the v3.3 diagnostic columns (netp_dev, nets_sys,
    # mbw_raw_mbps, blk_MBps) are emitted only WITHOUT --no-diag-cols and would
    # otherwise leak into stage_report's off=n-7 metric window. Do not drop the
    # --no-diag-cols flag from any capture site here.
    #
    # VM tap: when launch_workload_vm ran under INTP_BENCH_VM_TAP=1 it exports
    # CURRENT_VM_TAP_IFACE=intp-tap-<name>; we hand it to --target-vm so netp
    # reflects the per-VM tap. Without the tap (default SLIRP) the var is empty
    # and netp degrades to the system-wide observation.
    local outfile="$1" duration="$2" pid="$3" cgroup_path="${4:-}"
    if [ "$DRY_RUN" -eq 1 ]; then
        if [ -n "$cgroup_path" ]; then
            log "DRY: $V3_3_BIN --interval $INTERVAL --duration $duration --cgroup $cgroup_path --no-diag-cols -> $outfile"
        elif [ -n "$pid" ] && [ "$pid" != "0" ]; then
            log "DRY: $V3_3_BIN --interval $INTERVAL --duration $duration --cgroup \$(resolve_pid_cgroup $pid) --no-diag-cols -> $outfile"
        else
            log "DRY: $V3_3_BIN --interval $INTERVAL --duration $duration --no-diag-cols (system-wide) -> $outfile"
        fi
        [ -n "${CURRENT_VM_TAP_IFACE:-}" ] && log "DRY:   v3.3 --target-vm $CURRENT_VM_TAP_IFACE (tap active)"
        if [ "$PORTABLE_METRICS" = "1" ]; then
            printf 'netp\tnets\tblk\tmbw\tllcmr\tllcocc\tcpu\tschedlat\tpsi_mem\tmembw_est\tpsi_io\tschedthr\tsteal\n' > "$outfile"
            printf '0\t0\t0\t0\t0\t0\t0\t0\t0\t0\t0\t0\t0\n' >> "$outfile"
        else
            printf 'netp\tnets\tblk\tmbw\tllcmr\tllcocc\tcpu\n' > "$outfile"
        fi
        echo 0 > "$outfile.samples"
        return 0
    fi
    # --no-diag-cols (C13): captured TSV stays leading-ts + exactly 7 metrics.
    local args=( --interval "$INTERVAL" --duration "$duration"
                 --output tsv --no-diag-cols )
    # Portable benchmark (C26): append the 6 VM-portable columns AFTER the 7
    # canonical (--no-diag-cols still suppresses the 4 diag cols, so the row is
    # leading-ts + 7 canonical + 6 portable = 14 fields). Capture -> portable.tsv.
    [ "$PORTABLE_METRICS" = "1" ] && args+=( --portable-metrics )
    local scope="system-wide"
    if [ -n "$cgroup_path" ]; then
        args+=( --cgroup "$cgroup_path" )
        scope="cgroup=$cgroup_path"
    elif [ -n "$pid" ] && [ "$pid" != "0" ]; then
        # v3.3 is cgroup-id only (no --pids path). Resolve the target PID's
        # cgroup v2 path so PID-launched envs (docker/podman container,
        # vm-guest) get per-cgroup attribution instead of silently degrading to
        # system-wide -- the docker container launcher hands us a PID, not a
        # cgroup (W3 found v3.3 ran system-wide => all-zero in the container).
        local cg33; cg33=$(resolve_pid_cgroup "$pid")
        if [ -n "$cg33" ]; then
            args+=( --cgroup "$cg33" )
            scope="cgroup=$cg33 (resolved from pid=$pid)"
        else
            warn "v3.3: could not resolve cgroup for pid=$pid; running system-wide"
        fi
    fi
    if [ -n "${CURRENT_VM_TAP_IFACE:-}" ]; then
        args+=( --target-vm "$CURRENT_VM_TAP_IFACE" )
        scope="$scope tap=$CURRENT_VM_TAP_IFACE"
    fi
    local mbw_bps; mbw_bps="$(resolve_mem_bw_max_bps)"
    [ -n "$mbw_bps" ] && args+=( --mem-bw-max-bps "$mbw_bps" )
    {
        printf '# variant=v3.3 scope=%s\n' "$scope"
        "$V3_3_BIN" "${args[@]}" 2>"${outfile%.tsv}.v3.3.log" \
            | awk 'BEGIN{cmd="date +%s.%N"} /^#/||/^netp/{print;next} {cmd|getline ts;close(cmd); print ts"\t"$0}'
    } > "$outfile" || true
    awk '/^[0-9]/{n++}END{print n+0}' "$outfile" > "$outfile.samples"
}

# Map a variant to the profiler invocation as it appears INSIDE the guest.
# Inside the container, /opt/intp/ is the bind-mounted REPO_ROOT (read-only);
# inside the VM, /home/intp/intp is assumed (scp'd by run_profiler_inguest_vm).
_inguest_profiler_cmd() {
    # _inguest_profiler_cmd <variant> <pid> <duration> <interval> <prefix> [cgroup]
    # For the c-abi-cgroup variants (v2.1/v3.3) prefer --cgroup when the
    # in-guest workload was placed in a dedicated cgroup: --pids on the idle
    # stress-ng supervisor misses the worker children (cpu/llcmr ~0). T1.
    local variant="$1" pid="$2" duration="$3" interval="$4" prefix="$5" cgroup="${6:-}"
    # Portable benchmark (C26): the in-guest v2.1/v3.3 invocations also append
    # the 6 VM-portable columns. This is the path that recovers the
    # memory/scheduling dimensions in-guest where mbw/llcocc/llcmr are gapped.
    local pm=""
    [ "$PORTABLE_METRICS" = "1" ] && pm=" --portable-metrics"
    case "$variant" in
        v2)   echo "$prefix/variants/v2-c-abi/intp-c-abi --pid $pid --interval $interval --duration $duration --no-prom" ;;
        v2.1) if [ -n "$cgroup" ]; then
                  echo "$prefix/variants/v2.1-c-abi-cgroup/intp-c-abi-cgroup --cgroup $cgroup --interval $interval --duration $duration$pm"
              else
                  echo "$prefix/variants/v2.1-c-abi-cgroup/intp-c-abi-cgroup --pids $pid --interval $interval --duration $duration$pm"
              fi ;;
        v3)   echo "$prefix/variants/v3-ebpf-ring/intp-ebpf-ring --pid $pid --interval $interval --duration $duration" ;;
        v3.1) echo "bash $prefix/variants/v3.1-bpftrace/run-intp-bpftrace.sh --pid $pid --interval $interval --duration $duration" ;;
        v3.2) echo "$prefix/variants/v3.2-ebpf-core/intp-ebpf-core --pids $pid --interval $interval --duration $duration --no-raw-mbw" ;;
        v3.3) if [ -n "$cgroup" ]; then
                  echo "$prefix/variants/v3.3-ebpf-core-cgroup/intp-ebpf-core-cgroup --cgroup $cgroup --interval $interval --duration $duration --no-diag-cols$pm"
              else
                  echo "$prefix/variants/v3.3-ebpf-core-cgroup/intp-ebpf-core-cgroup --pids $pid --interval $interval --duration $duration --no-diag-cols$pm"
              fi ;;
        v1.1) echo "stap -DMAXACTION=8192 -DSTP_NO_OVERLOAD --suppress-handler-errors $prefix/variants/v1.1-stap-modern/intp-v1.1.stp -x $pid --target-pid=$pid -F" ;;
        v0|v0.1|v1) echo "stap -DMAXACTION=8192 --suppress-handler-errors $prefix/variants/v0.1-stap-nollc/intp-6.8.stp -x $pid -F" ;;
        *) echo ""; return 1 ;;
    esac
}

run_profiler_inguest_container() {
    # Launches profiler inside the running container via docker exec.
    local variant="$1" outfile="$2" duration="$3" pid="$4" cname="$5"
    local cmd
    cmd=$(_inguest_profiler_cmd "$variant" "$pid" "$duration" "$INTERVAL" "/opt/intp")
    [ -z "$cmd" ] && { warn "no in-guest cmd for variant=$variant"; return 1; }
    if [ "$DRY_RUN" -eq 1 ]; then
        log "DRY: docker exec $cname bash -lc '$cmd' -> $outfile"
        : > "$outfile"; echo 0 > "$outfile.samples"
        return 0
    fi
    log "    [in-guest container] $cmd"
    # shellcheck disable=SC2086
    docker exec "$cname" bash -lc "$cmd" > "$outfile" 2>&1 &
    local prof_pid=$!
    wait_pid_timeout "$prof_pid" $((duration + 30)) "in-guest-container/$variant" || true
    awk '/^[0-9]/{n++}END{print n+0}' "$outfile" > "$outfile.samples" 2>/dev/null || true
}

run_profiler_inguest_vm() {
    # Launches profiler inside the booted VM via SSH; results scp'd back.
    local variant="$1" outfile="$2" duration="$3" pid="$4"
    if [ "$DRY_RUN" -eq 1 ]; then
        log "DRY: rsync IntP into vm-guest, ssh launch profiler $variant pid=$pid duration=${duration}s, scp profiler.tsv back -> $outfile"
        : > "$outfile"; echo 0 > "$outfile.samples"
        return 0
    fi
    local tmpdir="${INTP_VMG_TMPDIR:-}" sshport="${INTP_VMG_SSHPORT:-}"
    if [ -z "$tmpdir" ] || [ -z "$sshport" ]; then
        warn "vm-guest state not exported (INTP_VMG_TMPDIR/SSHPORT) — skipping"
        return 1
    fi
    # Stage IntP checkout into guest if not already present.
    ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
        -i "$tmpdir/key" -p "$sshport" intp@127.0.0.1 \
        'test -d /home/intp/intp || mkdir -p /home/intp/intp' || true
    rsync -az --delete -e "ssh -o BatchMode=yes -o StrictHostKeyChecking=no \
        -o UserKnownHostsFile=/dev/null -i $tmpdir/key -p $sshport" \
        --exclude='.git' --exclude='results' --exclude='*.o' \
        "$REPO_ROOT/" intp@127.0.0.1:/home/intp/intp/ 2>/dev/null || \
        warn "rsync of IntP checkout into vm-guest failed"

    # Target the GUEST-LOCAL workload PID (INTP_VMG_GUEST_PID, propagated via
    # the .vmg-state sidecar), NOT the $pid arg -- $pid is the host-side qemu
    # PID and is meaningless inside the guest PID namespace, so the profiler
    # attributes no activity (cpu/llcmr read 0). T1 target-PID fix.
    local gpid="${INTP_VMG_GUEST_PID:-}" gcg="${INTP_VMG_GUEST_CGROUP:-}"
    if [ -z "$gcg" ] && { [ -z "$gpid" ] || [ "$gpid" = "0" ]; }; then
        warn "vm-guest: no guest-local workload cgroup or PID -- profiler would mis-target; skipping"
        return 1
    fi
    local cmd
    cmd=$(_inguest_profiler_cmd "$variant" "$gpid" "$duration" "$INTERVAL" "/home/intp/intp" "$gcg")
    [ -z "$cmd" ] && { warn "no in-guest cmd for variant=$variant"; return 1; }
    log "    [in-guest vm] $cmd  (guest cgroup=${gcg:-none} pid=$gpid)"
    ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
        -i "$tmpdir/key" -p "$sshport" intp@127.0.0.1 \
        "sudo bash -lc '$cmd > /tmp/profiler.tsv 2>&1'" &
    local prof_pid=$!
    wait_pid_timeout "$prof_pid" $((duration + 60)) "in-guest-vm/$variant" || true
    scp -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
        -i "$tmpdir/key" -P "$sshport" \
        intp@127.0.0.1:/tmp/profiler.tsv "$outfile" 2>/dev/null \
        || warn "scp of profiler.tsv from vm-guest failed"
    awk '/^[0-9]/{n++}END{print n+0}' "$outfile" > "$outfile.samples" 2>/dev/null || true
}

run_profiler() {
    local variant="$1" outfile="$2" duration="$3" pid="$4" cgroup_path="${5:-}"
    # In-guest envs propagate the env name through CURRENT_ENV (set in run_one).
    case "${CURRENT_ENV:-}" in
        container-guest)
            run_profiler_inguest_container "$variant" "$outfile" "$duration" "$pid" "${CURRENT_CONTAINER_NAME:-}"
            return $?
            ;;
        vm-guest)
            run_profiler_inguest_vm "$variant" "$outfile" "$duration" "$pid"
            return $?
            ;;
        container-full)
            # Profiler runs INSIDE the container, launched by the entrypoint.
            # The container's /opt/results is bind-mounted to host outdir, so
            # profiler.tsv lands directly. Host just waits for completion.
            log "    [$CURRENT_ENV] profiler runs inside container; host waits up to ${duration}s"
            if [ "$DRY_RUN" -eq 1 ]; then
                : > "$outfile"; echo 0 > "$outfile.samples"
                return 0
            fi
            local end=$((SECONDS + duration + 30))
            while [ $SECONDS -lt $end ]; do
                if [ -s "$outfile.samples" ]; then break; fi
                sleep 2
            done
            [ -s "$outfile.samples" ] || { warn "$CURRENT_ENV did not produce samples"; echo 0 > "$outfile.samples"; }
            return 0
            ;;
        vm-full)
            # Profiler runs INSIDE the VM. Host waits then scp's profiler.tsv
            # back from /opt/results/profiler.tsv inside the guest.
            log "    [$CURRENT_ENV] profiler runs inside VM; host waits up to ${duration}s then scp back"
            if [ "$DRY_RUN" -eq 1 ]; then
                : > "$outfile"; echo 0 > "$outfile.samples"
                return 0
            fi
            local tmpdir="${INTP_VMG_TMPDIR:-}" sshport="${INTP_VMG_SSHPORT:-}"
            [ -z "$tmpdir" ] || [ -z "$sshport" ] && { warn "vm-full state missing"; echo 0 > "$outfile.samples"; return 1; }
            sleep "$duration"
            sleep 5  # allow profiler to flush
            scp -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
                -i "$tmpdir/key" -P "$sshport" \
                intp@127.0.0.1:/opt/results/profiler.tsv "$outfile" 2>/dev/null \
                || warn "scp profiler.tsv from vm-full failed"
            awk '/^[0-9]/{n++}END{print n+0}' "$outfile" > "$outfile.samples" 2>/dev/null || true
            return 0
            ;;
    esac
    case "$variant" in
        v0) run_profiler_systemtap_v0 "$outfile" "$duration" "$pid" ;;
        v0.1) run_profiler_systemtap v0.1 "$V0_1_STP" "$outfile" "$duration" "$pid" ;;
        v0.2) run_profiler_systemtap_v0_2 "$outfile" "$duration" "$pid" ;;
        v1) run_profiler_systemtap v1 "$V1_STP" "$outfile" "$duration" "$pid" ;;
        v1.1) run_profiler_systemtap_v1_1 "$outfile" "$duration" "$pid" ;;
        v2) run_profiler_v2 "$outfile" "$duration" "$pid" "$cgroup_path" ;;
        v2.1) run_profiler_v2_1 "$outfile" "$duration" "$pid" "$cgroup_path" ;;
        v3.1) run_profiler_v3_1 "$outfile" "$duration" "$pid" ;;
        v3) run_profiler_v3 "$outfile" "$duration" "$pid" "$cgroup_path" ;;
        v3.2) run_profiler_v3_2 "$outfile" "$duration" "$pid" "$cgroup_path" ;;
        v3.3) run_profiler_v3_3 "$outfile" "$duration" "$pid" "$cgroup_path" ;;
        *) die "Unknown variant: $variant" ;;
    esac
}

# -----------------------------------------------------------------------------
# 11. One run = (env, variant, workload, rep)
# -----------------------------------------------------------------------------

run_one() {
    local stage="$1" env="$2" variant="$3" wl_id="$4" wl_args="$5" rep="$6" duration="$7"
    local notes=""
    local run_rc=0

    # Capture basename: portable mode (C26) lands in portable.tsv, canonical
    # mode in profiler.tsv. Computed once so the resume guard and the actual
    # capture path (below) can never disagree.
    local _capture="profiler.tsv"
    [ "$PORTABLE_METRICS" = "1" ] && _capture="portable.tsv"
    # ── Resume guard: skip run if the capture file already has samples ───────
    local _outdir_check="$OUTPUT_DIR/$env/$variant/$stage/$wl_id/rep$rep"
    local _prof_check="$_outdir_check/$_capture"
    local _samples_check=0
    if [ -f "$_prof_check.samples" ]; then
        _samples_check=$(cat "$_prof_check.samples" 2>/dev/null || echo 0)
    elif [ -f "$_prof_check" ]; then
        _samples_check=$(awk '/^[0-9]/{n++}END{print n+0}' "$_prof_check" 2>/dev/null || echo 0)
    fi
    if [ "$_samples_check" -gt 0 ]; then
        log "  skip [$env/$variant/$stage/$wl_id rep=$rep]: already_done (samples=$_samples_check)"
        return 0
    fi
    # ─────────────────────────────────────────────────────────────────────────

    if ! variant_kernel_ok "$variant"; then
        notes="kernel_too_new_for_$variant"
        log "  skip [$env/$variant/$stage/$wl_id rep=$rep]: $notes"
        record_index "$env" "$variant" "$stage" "$wl_id" "$rep" 0 0 0 "" "" "$notes" "skip"
        return 0
    fi
    if ! variant_env_ok "$variant" "$env"; then
        notes="${variant}_unsupported_in_${env}"
        log "  skip [$env/$variant/$stage/$wl_id rep=$rep]: $notes"
        record_index "$env" "$variant" "$stage" "$wl_id" "$rep" 0 0 0 "" "" "$notes" "skip"
        return 0
    fi

    local outdir="$OUTPUT_DIR/$env/$variant/$stage/$wl_id/rep$rep"
    mkdir -p "$outdir"
    # Portable benchmark (C26) captures into portable.tsv so the canonical
    # profiler.tsv schema (and its off=n-7 report) is never disturbed; the
    # portable report aggregates portable.tsv separately, header-aware.
    local prof="$outdir/$_capture"
    local wl_log="$outdir/workload.log"
    local cname="intp-bench-${env}-${variant}-${wl_id}-${rep}-$$"
    local total=$((WARMUP + duration + COOLDOWN))
    local start_iso; start_iso=$(date -Iseconds)
    local t0; t0=$(date +%s)

    log "  run [$env/$variant/$stage/$wl_id rep=$rep duration=${duration}s]"

    local wl_cgroup=""
    local target_scope
    if [ "$env" = "bare" ] && [ "$USE_CGROUP_TARGETING" = "1" ]; then
        wl_cgroup="/sys/fs/cgroup/intp-bench-$cname"
    fi

    # Export per-run state BEFORE launch_workload so full-deployment launchers
    # (container-full, vm-full) can read CURRENT_VARIANT and RUN_OUTDIR for
    # bind-mounting and entrypoint dispatch.
    export CURRENT_ENV="$env"
    export CURRENT_VARIANT="$variant"
    export CURRENT_CONTAINER_NAME="$cname"
    export RUN_OUTDIR="$outdir"

    local wl_pid
    wl_pid=$(launch_workload "$env" "$wl_log" "$total" "$wl_args" "$cname" 2>&1 | tail -1 || echo 0)
    if [ "$wl_pid" = "0" ] || [ -z "$wl_pid" ]; then
        notes="workload_launch_failed"
        record_index "$env" "$variant" "$stage" "$wl_id" "$rep" "$start_iso" 0 1 "" "" "$notes" "skip"
        return 0
    fi

    # Envs that resolve their cgroup only after launch (container-lxc) publish
    # it via a per-rep sidecar, since launch_workload runs in a subshell.
    if [ -z "$wl_cgroup" ] && [ "$USE_CGROUP_TARGETING" = "1" ] && [ -f "$outdir/.workload-cgroup" ]; then
        wl_cgroup=$(cat "$outdir/.workload-cgroup" 2>/dev/null || echo "")
        rm -f "$outdir/.workload-cgroup" 2>/dev/null || true
    fi

    # vm-guest publishes its SSH connection state (tmpdir/sshport/guest PID) via
    # a per-rep sidecar, same subshell rationale as the cgroup sidecar above:
    # launch_workload_vm_guest exports them but the $(... | tail -1) subshell
    # drops them, so run_profiler_inguest_vm saw nothing and skipped. Source it
    # here, before run_profiler dispatches, so the in-guest launch has the key.
    if [ "$env" = "vm-guest" ] && [ -f "$outdir/.vmg-state" ]; then
        # shellcheck disable=SC1090
        . "$outdir/.vmg-state"
        export INTP_VMG_TMPDIR INTP_VMG_SSHPORT INTP_VMG_GUEST_PID INTP_VMG_GUEST_CGROUP
        rm -f "$outdir/.vmg-state" 2>/dev/null || true
    fi

    # Parity caps audit (P2): launchers publish whether the CPU/RAM caps
    # actually applied. Default "n/a" if no caps were requested; "engine" if
    # caps were requested but this env applied them through the engine without
    # a harness-verified sidecar (lxc/k8s/vm). bare/docker/podman publish a
    # verified yes|no. A run with caps_applied!=yes is excluded from parity
    # comparisons downstream.
    local caps_applied="n/a"
    [ -n "$BENCH_CPUS$BENCH_MEM" ] && caps_applied="engine"
    if [ -f "$outdir/.caps-applied" ]; then
        caps_applied=$(cat "$outdir/.caps-applied" 2>/dev/null || echo "$caps_applied")
        rm -f "$outdir/.caps-applied" 2>/dev/null || true
    fi

    if [ -n "$wl_cgroup" ]; then
        target_scope="cgroup:$wl_cgroup"
    elif [ "${V_USE_PID_FILTER:-0}" = "1" ]; then
        target_scope="pid:$wl_pid"
    else
        target_scope="system-wide"
    fi

    # VM pairwise reorder: the victim VM is up and its workload running; NOW launch
    # the aggressor's attack into the (idle, pre-booted) aggressor VM so contention
    # is present through WARMUP + the measurement -- the aggressor never competed
    # with the victim's boot. (Set by stage_pairwise for vm-guest pairwise only.)
    if [ "$env" = "vm-guest" ] && [ "$DRY_RUN" -eq 0 ] && [ -n "${INTP_VMG_ATTACK_SSHPORT:-}" ]; then
        log "  vm-guest pairwise: victim up -> launching aggressor attack"
        _vmg_start_workload "$INTP_VMG_ATTACK_TMPDIR" "$INTP_VMG_ATTACK_SSHPORT" \
            "$INTP_VMG_ATTACK_CG" "$INTP_VMG_ATTACK_ARGS" "$INTP_VMG_ATTACK_DURATION" \
            >/dev/null 2>&1 || warn "vm-guest aggressor attack dispatch failed"
    fi

    [ "$DRY_RUN" -eq 0 ] && sleep "$WARMUP"

    # Propagate env / variant / outdir / container name so launch_workload and
    # run_profiler can dispatch to in-guest / full deployments without changing
    # the existing caller signatures.
    export CURRENT_ENV="$env"
    export CURRENT_VARIANT="$variant"
    export CURRENT_CONTAINER_NAME="$cname"
    export RUN_OUTDIR="$outdir"

    start_groundtruth "$outdir" "$duration" "$wl_pid"
    run_profiler "$variant" "$prof" "$duration" "$wl_pid" "$wl_cgroup" || true
    stop_groundtruth "$outdir"

    [ "$DRY_RUN" -eq 0 ] && sleep "$COOLDOWN"
    local stop_rc=0
    stop_workload "$env" "$wl_pid" "$cname" "$wl_cgroup" || stop_rc=$?
    if [ "$stop_rc" -ne 0 ]; then
        run_rc=1
        if [ -n "$notes" ]; then
            notes="$notes;teardown_failed_rc=$stop_rc"
        else
            notes="teardown_failed_rc=$stop_rc"
        fi
    fi

    local samples=0
    [ -f "$prof.samples" ] && samples=$(cat "$prof.samples")
    local elapsed=$(( $(date +%s) - t0 ))

    if [ "$samples" -eq 0 ]; then
        run_rc=1
        if [ -n "$notes" ]; then
            notes="$notes;profiler_no_samples"
        else
            notes="profiler_no_samples"
        fi
    fi

    # Per-run JSON envelope (helps debugging; also consumed by the plotter)
    cat > "$outdir/run.json" <<EOF
{
  "env": "$env",
  "variant": "$variant",
  "stage": "$stage",
  "workload": "$wl_id",
  "rep": $rep,
  "start_iso": "$start_iso",
  "duration_target_s": $duration,
  "duration_observed_s": $elapsed,
  "samples": $samples,
  "workload_pid": "$wl_pid",
  "bench_cpus": "$BENCH_CPUS",
  "bench_mem": "$BENCH_MEM",
  "caps_applied": "$caps_applied",
  "notes": "$notes"
}
EOF

    record_index "$env" "$variant" "$stage" "$wl_id" "$rep" "$start_iso" "$elapsed" "$run_rc" "$samples" "$prof" "$outdir/groundtruth.tsv" "$notes" "$target_scope"
}

record_index() {
    # env variant stage workload rep start dur rc samples prof gt notes target_scope
    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$@" >> "$INDEX"
}

# -----------------------------------------------------------------------------
# 12. Stage: solo (= SBAC-PAD 1-after-1)
# -----------------------------------------------------------------------------

stage_solo() {
    log "== solo (1-after-1, SBAC-PAD reproduction) =="
    local env variant entry name cat args r
    for env in "${ENVS[@]}"; do
        for variant in "${VARIANTS[@]}"; do
            for entry in "${WORKLOADS[@]}"; do
                IFS='|' read -r name cat args <<< "$entry"
                workload_selected "$name" || continue
                for r in $(seq 1 "$REPS"); do
                    run_one solo "$env" "$variant" "$name" "$args" "$r" "$DURATION"
                done
            done
        done
    done
}

# -----------------------------------------------------------------------------
# 13. Stage: pairwise (true cross-application interference)
#
# Two stress-ng processes co-located. The profiler attaches to the VICTIM,
# so each row of profiler.tsv reports the metric the *victim* is exposed to
# under contention. We additionally record the antagonist-only ground truth
# and the victim-solo baseline so the plotter can compute interference
# directly as (paired - solo) per metric, with proper attribution.
# -----------------------------------------------------------------------------

stage_pairwise() {
    log "== pairwise (cross-application interference, ground truth) =="
    local env variant entry name vargs aargs press r
    for env in "${ENVS[@]}"; do
        for variant in "${VARIANTS[@]}"; do
            for entry in "${PAIRWISE[@]}"; do
                IFS='|' read -r name vargs aargs press <<< "$entry"
                workload_selected "$name" || continue
                for r in $(seq 1 "$REPS"); do
                    local outdir="$OUTPUT_DIR/$env/$variant/pairwise/$name/rep$r"
                    mkdir -p "$outdir"
                    local antag_log="$outdir/antagonist.log"
                    local cname_a="intp-bench-antag-$$-$r"
                    log "  pair [$env/$variant/$name press=$press rep=$r] antagonist up"
                    local antag_pid
                    local antag_dur=$((DURATION + WARMUP + COOLDOWN + 10))
                    if [ "$env" = "vm-guest" ]; then
                        # VM reorder (boot everything, THEN attack): boot the aggressor
                        # VM IDLE (boot-only), then let run_one boot the victim VM into a
                        # QUIET machine; run_one triggers the aggressor's attack only once
                        # the victim is up + measuring (a saturating aggressor started at
                        # its own boot starves the victim VM's boot -> sshd refused).
                        antag_pid=$(INTP_VMG_BOOT_ONLY=1 launch_workload "$env" "$antag_log" "$antag_dur" "$aargs" "$cname_a" 2>&1 | tail -1 || echo 0)
                        # The aggressor VM's SSH conn info is in $outdir/.vmg-state (written
                        # by its boot); capture it for run_one BEFORE the victim launch
                        # overwrites that file. INTP_VMG_ATTACK_* tells run_one to fire the
                        # attack into this VM after the victim profiler starts.
                        if [ "$DRY_RUN" -eq 0 ] && [ -f "$outdir/.vmg-state" ]; then
                            # shellcheck disable=SC1090,SC1091
                            . "$outdir/.vmg-state"
                            export INTP_VMG_ATTACK_TMPDIR="$INTP_VMG_TMPDIR" \
                                   INTP_VMG_ATTACK_SSHPORT="$INTP_VMG_SSHPORT" \
                                   INTP_VMG_ATTACK_CG="$INTP_VMG_GUEST_CGROUP" \
                                   INTP_VMG_ATTACK_ARGS="$aargs" \
                                   INTP_VMG_ATTACK_DURATION="$antag_dur"
                        fi
                    else
                        antag_pid=$(launch_workload "$env" "$antag_log" "$antag_dur" "$aargs" "$cname_a" || echo 0)
                        [ "$DRY_RUN" -eq 0 ] && sleep 3
                    fi
                    # Now run the victim measurement -- profiler attaches to victim
                    run_one pairwise "$env" "$variant" "$name" "$vargs" "$r" "$DURATION"
                    unset INTP_VMG_ATTACK_TMPDIR INTP_VMG_ATTACK_SSHPORT INTP_VMG_ATTACK_CG \
                          INTP_VMG_ATTACK_ARGS INTP_VMG_ATTACK_DURATION
                    stop_workload "$env" "$antag_pid" "$cname_a"
                done
            done
        done
    done
}

# -----------------------------------------------------------------------------
# 14. Stage: overhead (system-wide profiler runtime cost)
#
# For each (env, ref, rep) the script runs a deterministic stress-ng workload
# for OVH_WARMUP + OVERHEAD_DURATION seconds. The first OVH_WARMUP seconds are
# discarded (head-start so caches/thermals stabilise); the steady-state window
# is when each arm's gauges actually sample.
#
# Three layers of measurement, all symmetric across baseline and each variant:
#   (A) Throughput   bogo ops + bogo ops/s parsed from stress-ng --metrics-brief
#                    (workload.log -> throughput.tsv)
#   (B) Self-cost    /proc/stat jiffies delta over the steady-state window
#                    (cpu_stat.tsv) plus cgroup cpu.stat delta when cgroup
#                    targeting is active (cgroup_cpu_stat.tsv).
#   (C) Volpert      perf stat -a context-switches, cpu-migrations,
#                    sched:sched_{wakeup,switch} (perf_stat.csv) — opt-in via
#                    --overhead-volpert.
#
# Per-rep ordering of (refs x arms) is shuffled with a seed derived from
# RUN_SEED so thermal/cache drift is averaged out across reps. Output paths
# are independent of order, so resume keeps working across reseed/rerun.
# -----------------------------------------------------------------------------

# Derive a 32-bit unsigned subseed from RUN_SEED + a key string so different
# (env, rep) buckets shuffle independently and reproducibly.
_overhead_subseed() {
    printf '%s-%s' "$RUN_SEED" "$1" | cksum | awk '{print $1}'
}

# Fisher-Yates shuffle of an array, deterministic for a given seed.
_overhead_shuffle_into() {
    # $1 seed, $2 output-array name, rest = items
    local __seed="$1" __out_name="$2"; shift 2
    local __items=("$@")
    local __n=${#__items[@]}
    local -n __out_ref="$__out_name"
    if [ "$__n" -le 1 ]; then
        __out_ref=("${__items[@]}")
        return 0
    fi
    local __order
    __order=$(awk -v n="$__n" -v s="$__seed" 'BEGIN{
        srand(s)
        for (i=0; i<n; i++) a[i]=i
        for (i=n-1; i>0; i--) {
            j = int(rand()*(i+1))
            t = a[i]; a[i] = a[j]; a[j] = t
        }
        for (i=0; i<n; i++) printf "%d ", a[i]
    }')
    __out_ref=()
    local __idx
    for __idx in $__order; do
        __out_ref+=("${__items[$__idx]}")
    done
}

# Snapshot of /proc/stat aggregate cpu line as space-separated jiffies:
# user nice system idle iowait irq softirq steal guest guest_nice
_overhead_proc_stat_snapshot() {
    awk '/^cpu / { for (i=2; i<=11; i++) printf "%s%s", $i, (i==11?"\n":" "); exit }' /proc/stat
}

# Snapshot of cgroup-v2 cpu.stat as: usage_usec nr_periods nr_throttled throttled_usec
_overhead_cgroup_cpustat_snapshot() {
    local cg="$1"
    if [ -z "$cg" ] || [ ! -r "$cg/cpu.stat" ]; then
        echo "0 0 0 0"
        return 0
    fi
    awk '
        $1=="usage_usec"     { u  = $2 }
        $1=="nr_periods"     { np = $2 }
        $1=="nr_throttled"   { nt = $2 }
        $1=="throttled_usec" { tu = $2 }
        END { printf "%d %d %d %d\n", u+0, np+0, nt+0, tu+0 }
    ' "$cg/cpu.stat"
}

# TSV delta from two /proc/stat snapshots (one labelled jiffies row each).
_overhead_proc_stat_delta_tsv() {
    awk -v b="$1" -v a="$2" '
    BEGIN {
        nb = split(b, B, " "); na = split(a, A, " ")
        labels[1]="user";    labels[2]="nice";   labels[3]="system";  labels[4]="idle"
        labels[5]="iowait";  labels[6]="irq";    labels[7]="softirq"; labels[8]="steal"
        labels[9]="guest";   labels[10]="guest_nice"
        printf "metric\tjiffies\n"
        if (nb != 10 || na != 10) {
            printf "error\tincomplete_snapshot\n"
            exit 0
        }
        busy = 0; total = 0
        for (i=1; i<=10; i++) {
            d = A[i] - B[i]
            printf "%s\t%d\n", labels[i], d
            total += d
            # Standard "non-idle" busy: exclude idle (4) and iowait (5).
            if (i != 4 && i != 5) busy += d
        }
        printf "busy\t%d\n",  busy
        printf "total\t%d\n", total
    }'
}

# TSV delta from two cgroup cpu.stat snapshots.
_overhead_cgroup_cpustat_delta_tsv() {
    awk -v b="$1" -v a="$2" '
    BEGIN {
        split(b, B, " "); split(a, A, " ")
        printf "metric\tvalue\n"
        printf "usage_usec\t%d\n",     A[1] - B[1]
        printf "nr_periods\t%d\n",     A[2] - B[2]
        printf "nr_throttled\t%d\n",   A[3] - B[3]
        printf "throttled_usec\t%d\n", A[4] - B[4]
    }'
}

# Parse stress-ng --metrics-brief output. One row per stressor; we sum bogo
# ops and per-second figures across stressors and take the max real time
# (stressors run concurrently). Tolerant of stress-ng version differences:
# we only require that field 5 of a data row is numeric.
_overhead_parse_stressng() {
    awk '
        # stress-ng prints the --metrics-brief table under the "metrc:" tag on
        # newer builds (>=0.15) and under "info:" on the 0.13.x line shipped
        # here; accept both. A genuine per-stressor data row has numeric
        # bogo-ops ($5), real-time ($6) and bogo-ops/s-real ($9). Guarding on
        # all three excludes the two header rows AND the stream stressor extra
        # "memory rate (MB|Mflop per sec)" lines (non-numeric $6/$9), which
        # would otherwise inflate the bogo-ops total.
        ($2 == "info:" || $2 == "metrc:") &&
        $5 ~ /^[0-9]+(\.[0-9]+)?$/ &&
        $6 ~ /^[0-9]+(\.[0-9]+)?$/ &&
        $9 ~ /^[0-9]+(\.[0-9]+)?$/ {
            ops    += $5
            if ($6 + 0 > rt) rt = $6 + 0
            ops_r  += $9
            ops_us += $10
            n++
        }
        END {
            if (n == 0) { print "NA\tNA\tNA\tNA"; exit 0 }
            printf "%d\t%.3f\t%.3f\t%.3f\n", ops, rt, ops_r, ops_us
        }' "$1"
}

# One arm of one (env, ref, rep). Caller already enforced kernel/env gating.
_overhead_run_arm() {
    local env="$1" arm="$2" rid="$3" rargs="$4" r="$5"
    local outroot="$OUTPUT_DIR/overhead"
    local subdir
    if [ "$arm" = "_baseline" ]; then
        subdir="$outroot/$env/_baseline/$rid/rep$r"
    else
        subdir="$outroot/$env/$arm/$rid/rep$r"
    fi

    # Resume guard: if elapsed_s exists, this (env, arm, rid, rep) was completed.
    if [ -f "$subdir/elapsed_s" ]; then
        log "  skip [overhead $env $arm $rid rep=$r]: already_done"
        return 0
    fi

    mkdir -p "$subdir"
    local wl_log="$subdir/workload.log"
    local prof="$subdir/profiler.tsv"
    local cname="intp-bench-ovh-${arm}-${rid}-${r}-$$"
    local total=$(( OVH_WARMUP + OVERHEAD_DURATION ))
    log "  overhead [$env $arm $rid rep=$r] total=${total}s warmup=${OVH_WARMUP}s window=${OVERHEAD_DURATION}s"

    local t0; t0=$(date +%s.%N)
    local wpid
    wpid=$(launch_workload "$env" "$wl_log" "$total" "$rargs" "$cname" 2>&1 | tail -1 || echo 0)
    if [ -z "$wpid" ] || [ "$wpid" = "0" ]; then
        warn "[overhead/$arm/$rid] workload launch failed"
        record_index "$env" "$arm" overhead "$rid" "$r" "$(date -Iseconds)" 0 1 "" "" "" "launch_failed" "system-wide"
        return 0
    fi
    local wl_cgroup="${CURRENT_WORKLOAD_CGROUP:-}"

    # Head-start: let the workload reach steady state before any sampling.
    [ "$DRY_RUN" -eq 0 ] && [ "$OVH_WARMUP" -gt 0 ] && sleep "$OVH_WARMUP"

    # Snapshots opening the steady-state window.
    local ss_before cg_before
    ss_before=$(_overhead_proc_stat_snapshot)
    cg_before=$(_overhead_cgroup_cpustat_snapshot "$wl_cgroup")

    # (C) Optional Volpert perf-stat: bounded to OVERHEAD_DURATION via sleep.
    local perf_pid=""
    if [ "$OVERHEAD_VOLPERT" -eq 1 ] && [ "$DRY_RUN" -eq 0 ] && command -v perf >/dev/null 2>&1; then
        perf stat -a -x , \
            -e context-switches,cpu-migrations,sched:sched_wakeup,sched:sched_switch \
            -o "$subdir/perf_stat.csv" \
            -- sleep "$OVERHEAD_DURATION" >/dev/null 2>&1 &
        perf_pid=$!
    fi

    # The sampling window itself: profiler in a variant arm; idle sleep in
    # baseline. Both consume exactly OVERHEAD_DURATION seconds.
    if [ "$arm" = "_baseline" ]; then
        [ "$DRY_RUN" -eq 0 ] && sleep "$OVERHEAD_DURATION"
        : > "$prof"   # empty marker; baseline arm has no profiler output
        echo 0 > "$prof.samples"
    else
        run_profiler "$arm" "$prof" "$OVERHEAD_DURATION" "$wpid" "$wl_cgroup" || true
    fi

    # Wait for perf stat (same window length) before snapping the closing CPU.
    if [ -n "$perf_pid" ]; then
        wait "$perf_pid" 2>/dev/null || true
    fi

    local ss_after cg_after
    ss_after=$(_overhead_proc_stat_snapshot)
    cg_after=$(_overhead_cgroup_cpustat_snapshot "$wl_cgroup")

    # The workload exits on its own --timeout; this waits for the residual.
    [ "$DRY_RUN" -eq 0 ] && wait_pid_timeout "$wpid" "$WAIT_TIMEOUT_S" "overhead/$arm/$rid" || true
    stop_workload "$env" "$wpid" "$cname" "$wl_cgroup"

    local elapsed
    elapsed=$(awk -v t0="$t0" 'BEGIN{cmd="date +%s.%N";cmd|getline t1;close(cmd);printf "%.3f",t1-t0}')

    # (A) Throughput from stress-ng metrics-brief.
    local thr bo rt opr opu
    thr=$(_overhead_parse_stressng "$wl_log" 2>/dev/null || true)
    [ -z "$thr" ] && thr=$'NA\tNA\tNA\tNA'
    IFS=$'\t' read -r bo rt opr opu <<< "$thr"
    {
        printf 'metric\tvalue\n'
        printf 'bogo_ops_total\t%s\n'        "$bo"
        printf 'real_time_s\t%s\n'           "$rt"
        printf 'bogo_ops_per_s_real\t%s\n'   "$opr"
        printf 'bogo_ops_per_s_usrsys\t%s\n' "$opu"
    } > "$subdir/throughput.tsv"

    # (B) System-wide CPU jiffies delta and cgroup cpu.stat delta.
    _overhead_proc_stat_delta_tsv "$ss_before" "$ss_after" > "$subdir/cpu_stat.tsv"
    if [ -n "$wl_cgroup" ]; then
        _overhead_cgroup_cpustat_delta_tsv "$cg_before" "$cg_after" > "$subdir/cgroup_cpu_stat.tsv"
    fi

    {
        printf 'arm=%s\nrid=%s\nrep=%d\nseed=%s\nwarmup_s=%s\nwindow_s=%s\ntotal_s=%s\nelapsed_s=%s\nwl_pid=%s\nwl_cgroup=%s\nvolpert=%s\n' \
            "$arm" "$rid" "$r" "$RUN_SEED" "$OVH_WARMUP" "$OVERHEAD_DURATION" "$total" "$elapsed" "$wpid" "${wl_cgroup:-}" "$OVERHEAD_VOLPERT"
    } > "$subdir/run.meta"
    echo "$elapsed" > "$subdir/elapsed_s"

    local note prof_path
    if [ "$arm" = "_baseline" ]; then
        note="no_profiler"; prof_path=""
    else
        note="with_profiler"; prof_path="$prof"
    fi
    record_index "$env" "$arm" overhead "$rid" "$r" "$(date -Iseconds)" "$elapsed" 0 "" "$prof_path" "" "$note" "system-wide"
}

stage_overhead() {
    log "== overhead (system-wide profiler runtime cost) =="
    log "   warmup=${OVH_WARMUP}s window=${OVERHEAD_DURATION}s seed=${RUN_SEED} volpert=${OVERHEAD_VOLPERT}"
    local outroot="$OUTPUT_DIR/overhead"
    mkdir -p "$outroot"

    if [ "$OVERHEAD_VOLPERT" -eq 1 ] && ! command -v perf >/dev/null 2>&1; then
        warn "--overhead-volpert: 'perf' not found; perf-stat data will be skipped"
    fi

    # Build the kernel-OK arm pool once. Baseline is also an arm so that all
    # five (or however many) arms compete on equal footing in the shuffle.
    local arms_pool=("_baseline")
    local v
    for v in "${VARIANTS[@]}"; do
        if variant_kernel_ok "$v"; then arms_pool+=("$v"); fi
    done

    local env r entry rid rargs arm
    for env in "${ENVS[@]}"; do
        for r in $(seq 1 "$REPS"); do
            local refs_seed
            refs_seed=$(_overhead_subseed "refs-$env-$r")
            local refs_order=()
            _overhead_shuffle_into "$refs_seed" refs_order "${OVERHEAD_REFS[@]}"

            mkdir -p "$outroot/$env"
            local rep_log="$outroot/$env/rep$r.order.txt"
            : > "$rep_log"
            printf 'seed=%s rep=%d refs_order=%s\n' "$RUN_SEED" "$r" "${refs_order[*]/|*/}" >> "$rep_log"

            for entry in "${refs_order[@]}"; do
                IFS='|' read -r rid rargs <<< "$entry"
                workload_selected "$rid" || [ ${#WORKLOAD_NAMES[@]} -eq 0 ] || continue

                local arms_seed
                arms_seed=$(_overhead_subseed "arms-$env-$r-$rid")
                local arms_order=()
                _overhead_shuffle_into "$arms_seed" arms_order "${arms_pool[@]}"
                printf '  ref=%s arms_order=%s\n' "$rid" "${arms_order[*]}" >> "$rep_log"

                for arm in "${arms_order[@]}"; do
                    _overhead_run_arm "$env" "$arm" "$rid" "$rargs" "$r"
                done
            done
        done
    done
}

# -----------------------------------------------------------------------------
# 15. Stage: timeseries (long capture, mixed workload)
# -----------------------------------------------------------------------------

stage_timeseries() {
    log "== timeseries (long capture, mixed workload) =="
    local mixed_args="--cpu 8 --vm 4 --vm-bytes 16G --hdd 4 --hdd-bytes 2G --sock 4"
    local env variant
    for env in "${ENVS[@]}"; do
        for variant in "${VARIANTS[@]}"; do
            run_one timeseries "$env" "$variant" "mixed_long" "$mixed_args" 1 "$TIMESERIES_DURATION"
        done
    done
}

# -----------------------------------------------------------------------------
# 16. Stage: report
# -----------------------------------------------------------------------------

stage_report() {
    log "== report =="
    local agg="$OUTPUT_DIR/aggregate-means.tsv"
    {
        printf 'env\tvariant\tstage\tworkload\trep\tnetp\tnets\tblk\tmbw\tllcmr\tllcocc\tcpu\n'
        find "$OUTPUT_DIR" -name profiler.tsv | while read -r f; do
            # Path layout: .../<env>/<variant>/<stage>/<workload>/rep<R>/profiler.tsv
            local env variant stage wl rep
            env=$(echo "$f" | awk -F/ '{print $(NF-5)}')
            variant=$(echo "$f" | awk -F/ '{print $(NF-4)}')
            stage=$(echo "$f" | awk -F/ '{print $(NF-3)}')
            wl=$(echo "$f" | awk -F/ '{print $(NF-2)}')
            rep=$(echo "$f" | awk -F/ '{print $(NF-1)}' | sed 's/rep//')
            awk -v E="$env" -v V="$variant" -v S="$stage" -v W="$wl" -v R="$rep" '
                /^#/ || /^ts/ || /^netp/ || NF == 0 { next }
                /^[0-9]/ {
                    # 7 metrics live in the last 7 columns regardless of prefix:
                    #   V0/V0.1 (stap):    7 cols (no time_ms, no host ts)         → off=0
                    #   V2/V2.1/V3/V3.1:   8 cols (host ts + 7 metrics)            → off=1
                    #   V3.2/V3.3:         8 cols (host ts + 7 metrics)            → off=1
                    #   V1/V1.1 (stap):    9 cols (host ts + time_ms + 7 metrics)  → off=2
                    # INVARIANT: run_profiler_v3_2 (--no-raw-mbw) and
                    # run_profiler_v3_3 (--no-diag-cols) MUST suppress all
                    # diagnostic columns so the captured row is leading-ts + the
                    # 7 canonical metrics ONLY. A leaked diag column (v3.3:
                    # netp_dev/nets_sys/mbw_raw_mbps/blk_MBps) would push off
                    # past the real metric window and be mis-read here. off=n-7
                    # below assumes exactly 7 trailing metrics — do not relax it.
                    n=NF; off=n-7
                    if (off < 0) next
                    for(i=1;i<=7;i++){
                        if($(i+off) == "--") continue
                        s[i]+=$(i+off); c[i]++
                    }
                }
                END {
                    printf "%s\t%s\t%s\t%s\t%s",E,V,S,W,R
                    for(i=1;i<=7;i++){
                        if(c[i]>0) printf "\t%.3f",s[i]/c[i]
                        else printf "\t--"
                    }
                    printf "\n"
                }
            ' "$f"
        done
    } > "$agg"
    log "  wrote $agg"

    # Console summary table
    log ""
    log "Aggregate means (head):"
    head -20 "$agg" | column -t -s $'\t' | sed 's/^/  /'
    log ""
    log "Total rows in index: $(wc -l < "$INDEX")"
    log "Total profiler.tsv files: $(find "$OUTPUT_DIR" -name profiler.tsv | wc -l)"
    log ""
    log "To produce plots:"
    log "  python3 $SCRIPT_DIR/plot/plot-intp-bench.py $OUTPUT_DIR"
}

# Portable benchmark report (C26 / DESIGN §10). Aggregates the per-rep
# portable.tsv captures into aggregate-portable-means.tsv. HEADER-AWARE, NOT
# off=n-7: the 6 portable columns are located by NAME from the column-header
# line (so a leaked diagnostic column can never shift the window), then averaged
# across the rep's data rows. '--' (source unavailable) is skipped, not summed.
stage_report_portable() {
    log "== report (portable) =="
    # The portable capture (portable.tsv) carries the 13-metric SUPERSET (7
    # canonical + 6 portable). Emit the full 13-col aggregate-means.tsv so the
    # SAME campaign feeds the cross-env omnibus (plot-cross-environment.py reads
    # the 7 it knows) AND the cross-deployment paired-delta generator; then derive
    # the 6-col portable view. HEADER-AWARE (locate each metric by name, robust to
    # a leaked diag column) and ts-agnostic (off = NF - header field count: 1 for
    # host-observer captures, 0 for in-guest docker-exec/ssh captures). NOT off=n-7.
    local agg="$OUTPUT_DIR/aggregate-means.tsv"
    local pagg="$OUTPUT_DIR/aggregate-portable-means.tsv"
    {
        printf 'env\tvariant\tstage\tworkload\trep\tnetp\tnets\tblk\tmbw\tllcmr\tllcocc\tcpu\tschedlat\tpsi_mem\tmembw_est\tpsi_io\tschedthr\tsteal\n'
        find "$OUTPUT_DIR" -name portable.tsv | while read -r f; do
            local env variant stage wl rep
            env=$(echo "$f" | awk -F/ '{print $(NF-5)}')
            variant=$(echo "$f" | awk -F/ '{print $(NF-4)}')
            stage=$(echo "$f" | awk -F/ '{print $(NF-3)}')
            wl=$(echo "$f" | awk -F/ '{print $(NF-2)}')
            rep=$(echo "$f" | awk -F/ '{print $(NF-1)}' | sed 's/rep//')
            awk -v E="$env" -v V="$variant" -v S="$stage" -v W="$wl" -v R="$rep" '
                BEGIN { split("netp nets blk mbw llcmr llcocc cpu schedlat psi_mem membw_est psi_io schedthr steal", P, " ") }
                /^netp/ { for (i=1;i<=NF;i++) col[$i]=i; hdr_nf=NF; haveh=1; next }
                /^#/ || NF==0 { next }
                /^[0-9]/ {
                    if (!haveh) next
                    off = NF - hdr_nf                    # 1 = leading ts present, 0 = none
                    if (off < 0 || off > 1) next
                    for (k=1;k<=13;k++) {
                        ci = col[P[k]]
                        if (ci == "") continue           # column absent (e.g. other variant)
                        val = $(ci + off)
                        if (val == "--" || val == "") continue
                        s[k]+=val; c[k]++
                    }
                }
                END {
                    printf "%s\t%s\t%s\t%s\t%s",E,V,S,W,R
                    for (k=1;k<=13;k++) {
                        if (c[k]>0) printf "\t%.3f",s[k]/c[k]
                        else        printf "\t--"
                    }
                    printf "\n"
                }
            ' "$f"
        done
    } > "$agg"
    # 6-col portable view: keys (cols 1-5) + the 6 portable metrics (cols 13-18).
    cut -f1-5,13-18 "$agg" > "$pagg"
    log "  wrote $agg (13-metric) + $pagg (portable view)"
    log ""
    log "Aggregate means (head):"
    head -20 "$agg" | column -t -s $'\t' | sed 's/^/  /'
    log ""
    log "Total portable.tsv files: $(find "$OUTPUT_DIR" -name portable.tsv | wc -l)"
    log ""
    log "To adjudicate / report:"
    log "  python3 $SCRIPT_DIR/analyze-portable.py $OUTPUT_DIR            # portable-vs-GT + falsification"
    log "  python3 $SCRIPT_DIR/analyze-cross-deployment.py $OUTPUT_DIR    # paired delta-vs-bare (13 metrics)"
}

# -----------------------------------------------------------------------------
# 17. Driver
# -----------------------------------------------------------------------------

main() {
    parse_args "$@"
    ensure_root
    ensure_basic_deps
    ensure_perf_paranoid
    _compute_default_resources
    setup_cpu_env
    prepare_output_dir
    write_metadata

    trap 'restore_cpu_env; stop_resctrl_helper; _vm_kill_orphan_qpids; _vm_cleanup_tmpdirs; _vm_guest_cleanup' EXIT INT TERM

    log "== intp-bench =="
    log "output: $OUTPUT_DIR"
    log "stages: $STAGES_CSV"
    log "variants: $VARIANTS_CSV"
    log "envs: $ENVS_CSV"
    log "workloads: ${WORKLOAD_FILTER:-all}"

    stage_enabled detect && log "detect: capabilities written to $OUTPUT_DIR/capabilities.env"
    stage_enabled build      && stage_build
    stage_enabled solo       && stage_solo
    stage_enabled pairwise   && stage_pairwise
    stage_enabled overhead   && stage_overhead
    stage_enabled timeseries && stage_timeseries
    # Portable benchmark (C26) is a SEPARATE capture (portable.tsv) with its own
    # header-aware report; the canonical profiler.tsv aggregation is skipped in
    # that mode since no profiler.tsv files are produced.
    if stage_enabled report; then
        if [ "$PORTABLE_METRICS" = "1" ]; then stage_report_portable; else stage_report; fi
    fi

    log "done. results: $OUTPUT_DIR"
}

main "$@"

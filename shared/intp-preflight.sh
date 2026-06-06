#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# intp-preflight.sh -- Verify a host has every hardware/software interface
# required to build and run all IntP variants (V0, V0.1, V0.2, V1, V1.1, V2,
# V2.1, V3.1, V3, V3.2, V3.3) and the bench harness in bench/run-intp-bench.sh.
#
# Output is a per-variant matrix (BUILD + RUN) with a per-metric coverage map.
# Each check is OK / DEGRADED / MISSING with the underlying reason. The script
# never installs anything, never mounts resctrl, never changes sysctls.
#
# Usage:
#   ./intp-preflight.sh                    # check every variant
#   ./intp-preflight.sh --variants v2,v3   # check only the listed variants
#   ./intp-preflight.sh --json             # machine-readable summary
#   ./intp-preflight.sh --strict           # exit 2 if any selected variant is
#                                          # not fully runnable (default exits
#                                          # 0 unless every variant is broken)
#   ./intp-preflight.sh --quiet            # only the final summary
#
# Variant selectors: v0 v0.1 v0.2 v1 v1.1 v2 v2.1 v3.1 v3 v3.2 v3.3 bench
# (harness deps). v2.1/v3.3 are the cgroup-native (container/VM) endpoints.
# -----------------------------------------------------------------------------

set -u
# Note: do NOT use `set -e`. Most checks intentionally tolerate missing tools
# and account for that in the verdict. A hard-fail on any failing command would
# abort the script halfway through the matrix.

# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------

ALL_VARIANTS=(v0 v0.1 v0.2 v1 v1.1 v2 v2.1 v3.1 v3 v3.2 v3.3 bench)
SELECTED=()
JSON=0
STRICT=0
QUIET=0

usage() {
    sed -n '2,/^# ---$/p' "$0" | sed 's/^# \?//; /^---$/q'
}

while [ $# -gt 0 ]; do
    case "$1" in
        --variants)
            IFS=',' read -r -a SELECTED <<< "$2"; shift 2 ;;
        --json)    JSON=1; shift ;;
        --strict)  STRICT=1; shift ;;
        --quiet)   QUIET=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) echo "unknown option: $1" >&2; usage >&2; exit 64 ;;
    esac
done

[ ${#SELECTED[@]} -eq 0 ] && SELECTED=("${ALL_VARIANTS[@]}")

# -----------------------------------------------------------------------------
# Output helpers
# -----------------------------------------------------------------------------

if [ -t 1 ] && [ "$JSON" -eq 0 ]; then
    C_RED=$'\033[31m'; C_YEL=$'\033[33m'; C_GRN=$'\033[32m'
    C_DIM=$'\033[2m';  C_BLD=$'\033[1m';  C_RST=$'\033[0m'
else
    C_RED=""; C_YEL=""; C_GRN=""; C_DIM=""; C_BLD=""; C_RST=""
fi

# Each check writes one line to a temp file with the format:
#   <category>\t<key>\t<status>\t<detail>
# where status is OK | DEGRADED | MISSING | INFO. Variant verdicts are
# computed at the end from this table.
RESULTS=$(mktemp -t intp-preflight.XXXXXX)
trap 'rm -f "$RESULTS"' EXIT

record() {
    # record <category> <key> <status> <detail...>
    local cat="$1" key="$2" status="$3"; shift 3
    printf '%s\t%s\t%s\t%s\n' "$cat" "$key" "$status" "$*" >> "$RESULTS"
}

emit() {
    [ "$QUIET" -eq 1 ] && return 0
    [ "$JSON" -eq 1 ]  && return 0
    local status="$1"; shift
    local color
    case "$status" in
        OK)       color="$C_GRN" ;;
        DEGRADED) color="$C_YEL" ;;
        MISSING)  color="$C_RED" ;;
        *)        color="$C_DIM" ;;
    esac
    printf '  %s%-9s%s %s\n' "$color" "[$status]" "$C_RST" "$*"
}

section() {
    [ "$QUIET" -eq 1 ] && return 0
    [ "$JSON" -eq 1 ]  && return 0
    printf '\n%s== %s ==%s\n' "$C_BLD" "$1" "$C_RST"
}

# Look up a (category,key) status from RESULTS. Echoes status or empty string.
status_of() {
    awk -F '\t' -v c="$1" -v k="$2" '$1==c && $2==k {print $3; exit}' "$RESULTS"
}
detail_of() {
    awk -F '\t' -v c="$1" -v k="$2" '$1==c && $2==k {print $4; exit}' "$RESULTS"
}

want_variant() {
    local v="$1" w
    for w in "${SELECTED[@]}"; do [ "$w" = "$v" ] && return 0; done
    return 1
}

# -----------------------------------------------------------------------------
# Generic helpers (tools, kernel, sysfs)
# -----------------------------------------------------------------------------

check_cmd() {
    # check_cmd <category> <key> <command> <human label>
    local cat="$1" key="$2" cmd="$3" label="$4"
    if command -v "$cmd" >/dev/null 2>&1; then
        local ver=""
        case "$cmd" in
            stap)     ver=$("$cmd" --version 2>&1 | head -1) ;;
            bpftrace) ver=$("$cmd" --version 2>&1 | head -1) ;;
            clang|gcc|cc) ver=$("$cmd" --version 2>&1 | head -1) ;;
            python3)  ver=$("$cmd" --version 2>&1 | head -1) ;;
            make)     ver=$("$cmd" --version 2>&1 | head -1) ;;
            bpftool)  ver=$("$cmd" --version 2>&1 | head -1 || echo bpftool) ;;
            *)        ver="$(command -v "$cmd")" ;;
        esac
        record "$cat" "$key" OK "$label: $ver"
        emit OK "$label ($ver)"
        return 0
    fi
    record "$cat" "$key" MISSING "$label: command '$cmd' not in PATH"
    emit MISSING "$label -- '$cmd' not in PATH"
    return 1
}

# Compare a kernel release string of the form X.Y[.Z][-suffix] against X.Y.
# Returns 0 if running kernel >= required; 1 otherwise.
KREL=$(uname -r 2>/dev/null || echo 0.0)
KMAJ=$(echo "$KREL" | awk -F'[.-]' '{print $1+0}')
KMIN=$(echo "$KREL" | awk -F'[.-]' '{print $2+0}')

kernel_ge() {
    local rmaj="$1" rmin="$2"
    if [ "$KMAJ" -gt "$rmaj" ]; then return 0; fi
    if [ "$KMAJ" -eq "$rmaj" ] && [ "$KMIN" -ge "$rmin" ]; then return 0; fi
    return 1
}
kernel_le() {
    local rmaj="$1" rmin="$2"
    if [ "$KMAJ" -lt "$rmaj" ]; then return 0; fi
    if [ "$KMAJ" -eq "$rmaj" ] && [ "$KMIN" -le "$rmin" ]; then return 0; fi
    return 1
}

# -----------------------------------------------------------------------------
# A. Kernel + CPU + sysfs surface (shared by every variant)
# -----------------------------------------------------------------------------

check_kernel_and_cpu() {
    section "Kernel + CPU"

    record kernel release INFO "running $KREL ($KMAJ.$KMIN)"
    emit INFO "kernel $KREL"

    local arch; arch=$(uname -m 2>/dev/null || echo unknown)
    record kernel arch INFO "$arch"
    emit INFO "arch $arch"

    local vendor=""
    if [ -r /proc/cpuinfo ]; then
        vendor=$(awk -F: '/^vendor_id/ {gsub(/ /,"",$2); print $2; exit}' /proc/cpuinfo)
        [ -z "$vendor" ] && vendor=$(awk -F: '/^CPU implementer/ {print "ARM"; exit}' /proc/cpuinfo)
    fi
    vendor="${vendor:-unknown}"
    record kernel vendor INFO "$vendor"
    emit INFO "cpu vendor $vendor"

    if [ -r /proc/cpuinfo ]; then
        record kernel cpuinfo OK "/proc/cpuinfo readable"
    else
        record kernel cpuinfo MISSING "/proc/cpuinfo unreadable"
        emit MISSING "/proc/cpuinfo unreadable"
    fi

    # ftrace / tracepoints (used by stap probe kernel.* and BPF tracepoints)
    if [ -d /sys/kernel/tracing ] || [ -d /sys/kernel/debug/tracing ]; then
        record kernel tracefs OK "tracing fs available"
        emit OK "tracefs"
    else
        record kernel tracefs MISSING "neither /sys/kernel/tracing nor /sys/kernel/debug/tracing exists"
        emit MISSING "tracefs (kernel tracepoints) -- nets/blk/cpu probes will not work"
    fi

    # perf_event_paranoid -- profilers that open IMC counters need <= 0,
    # ideally -1.
    if [ -r /proc/sys/kernel/perf_event_paranoid ]; then
        local p; p=$(cat /proc/sys/kernel/perf_event_paranoid 2>/dev/null || echo 4)
        if [ "$p" -le -1 ]; then
            record kernel perf_paranoid OK "perf_event_paranoid=$p"
            emit OK "perf_event_paranoid=$p"
        elif [ "$p" -le 0 ]; then
            record kernel perf_paranoid DEGRADED "perf_event_paranoid=$p (mbw/llcmr need -1 for IMC uncore)"
            emit DEGRADED "perf_event_paranoid=$p (set to -1 for full IMC access)"
        else
            record kernel perf_paranoid MISSING "perf_event_paranoid=$p (>=1 blocks PMU access)"
            emit MISSING "perf_event_paranoid=$p (set to -1 to allow PMU access)"
        fi
    else
        record kernel perf_paranoid MISSING "/proc/sys/kernel/perf_event_paranoid not readable"
        emit MISSING "perf_event_paranoid not readable"
    fi
}

# -----------------------------------------------------------------------------
# B. RDT / resctrl (mbw, llcocc)
# -----------------------------------------------------------------------------

check_rdt() {
    section "Intel RDT / AMD PQoS / resctrl"

    local flags=""
    [ -r /proc/cpuinfo ] && flags=$(awk -F: '/^flags/ {print $2; exit}' /proc/cpuinfo)
    local has_cqm=0 has_occup=0 has_mbm=0
    echo "$flags" | grep -qw cqm           && has_cqm=1
    echo "$flags" | grep -qw cqm_occup_llc && has_occup=1
    echo "$flags" | grep -qw cqm_mbm_total && has_mbm=1

    if [ "$has_cqm" -eq 1 ]; then
        record rdt cpu_flag_cqm OK "cqm flag present"
        emit OK "cpuid cqm flag"
    else
        record rdt cpu_flag_cqm MISSING "cqm flag absent (no RDT support exposed)"
        emit MISSING "cpuid cqm flag (host has no RDT)"
    fi
    [ "$has_occup" -eq 1 ] && emit OK "cqm_occup_llc (llcocc capable)" \
        && record rdt cpu_flag_cqm_occup OK "cqm_occup_llc present" \
        || { emit DEGRADED "cqm_occup_llc absent (no llcocc)"; \
             record rdt cpu_flag_cqm_occup MISSING "cqm_occup_llc absent"; }
    [ "$has_mbm" -eq 1 ] && emit OK "cqm_mbm_total (mbw via resctrl capable)" \
        && record rdt cpu_flag_cqm_mbm OK "cqm_mbm_total present" \
        || { emit DEGRADED "cqm_mbm_total absent (mbw must use perf_uncore_imc)"; \
             record rdt cpu_flag_cqm_mbm MISSING "cqm_mbm_total absent"; }

    if grep -q resctrl /proc/filesystems 2>/dev/null; then
        record rdt resctrl_compiled OK "resctrl compiled in (CONFIG_X86_CPU_RESCTRL)"
        emit OK "resctrl compiled into kernel"
    else
        record rdt resctrl_compiled MISSING "resctrl missing from /proc/filesystems"
        emit MISSING "resctrl not compiled in"
    fi

    if mountpoint -q /sys/fs/resctrl 2>/dev/null; then
        record rdt resctrl_mounted OK "/sys/fs/resctrl mounted"
        emit OK "/sys/fs/resctrl mounted"
        if [ -r /sys/fs/resctrl/info/L3_MON/mon_features ]; then
            local feat; feat=$(tr '\n' ' ' < /sys/fs/resctrl/info/L3_MON/mon_features)
            record rdt resctrl_features INFO "L3_MON: $feat"
            emit INFO "L3_MON features: $feat"
        fi
    else
        record rdt resctrl_mounted DEGRADED "not mounted (mount -t resctrl resctrl /sys/fs/resctrl)"
        emit DEGRADED "/sys/fs/resctrl not mounted (run 'mount -t resctrl resctrl /sys/fs/resctrl')"
    fi
}

# -----------------------------------------------------------------------------
# C. NIC (netp)
# -----------------------------------------------------------------------------

check_nic() {
    section "NIC (netp)"
    local found=""
    if [ ! -d /sys/class/net ]; then
        record nic any MISSING "/sys/class/net not present (not running on Linux?)"
        emit MISSING "/sys/class/net not present"
        return
    fi
    for d in /sys/class/net/*/; do
        [ -d "$d" ] || continue
        local n; n=$(basename "$d")
        [ "$n" = "lo" ] && continue
        found="$n"
        local state; state=$(cat "$d/operstate" 2>/dev/null || echo unknown)
        local speed; speed=$(cat "$d/speed" 2>/dev/null || echo "")
        if [ -n "$speed" ] && [ "$speed" -gt 0 ] 2>/dev/null; then
            record nic "iface_$n" OK "$n state=$state speed=${speed}Mbps"
            emit OK "$n: $state, ${speed}Mbps"
        else
            record nic "iface_$n" DEGRADED "$n state=$state speed unknown"
            emit DEGRADED "$n: $state, speed unknown (override with --nic-speed-bps)"
        fi
    done
    if [ -z "$found" ]; then
        record nic any MISSING "no non-loopback interface in /sys/class/net"
        emit MISSING "no non-loopback NIC found"
    fi
}

# -----------------------------------------------------------------------------
# D. perf / IMC uncore (mbw fallback, llcmr)
# -----------------------------------------------------------------------------

check_perf_uncore() {
    section "perf + IMC uncore"

    if ls /sys/devices/uncore_imc_* >/dev/null 2>&1; then
        local n; n=$(ls -d /sys/devices/uncore_imc_* 2>/dev/null | wc -l)
        record perf imc_uncore OK "$n IMC PMU(s) present"
        emit OK "uncore_imc PMU x$n (mbw fallback path)"
    elif ls /sys/devices/amd_df_* >/dev/null 2>&1 || ls /sys/devices/uncore_df_* >/dev/null 2>&1; then
        record perf imc_uncore OK "AMD DF uncore present"
        emit OK "AMD DF uncore (mbw on EPYC)"
    elif [ -d /sys/devices/arm_cmn_0 ]; then
        record perf imc_uncore OK "arm_cmn PMU present"
        emit OK "arm_cmn PMU (mbw on ARM)"
    else
        record perf imc_uncore DEGRADED "no IMC/DF/CMN uncore PMU exposed"
        emit DEGRADED "no IMC uncore (mbw must use resctrl MBM only)"
    fi

    # perf_event_open syscall surface check (just probe the file existence).
    if [ -r /proc/sys/kernel/perf_event_max_sample_rate ]; then
        record perf perf_events OK "CONFIG_PERF_EVENTS active"
        emit OK "perf_event_open available"
    else
        record perf perf_events MISSING "/proc/sys/kernel/perf_event_max_sample_rate missing"
        emit MISSING "perf_event subsystem not available"
    fi
}

# -----------------------------------------------------------------------------
# D2. Container / VM / cgroup attribution (V2.1, V3.3)
#
# v2.1 (cgroup-native hybrid-C) and v3.3 (eBPF cgroup-native) attribute the
# canonical metrics per-cgroup so a container or VM can be measured as "a
# cgroup". That path needs: cgroup v2 unified hierarchy mounted at
# /sys/fs/cgroup, perf_event cgroup-mode (PERF_FLAG_PID_CGROUP; kernel >= 5.8),
# and -- for v3.3's cgroup_skb netp attach -- CAP_NET_ADMIN (plus CAP_BPF /
# CAP_PERFMON, normally satisfied by running as root). sched_ext is an
# informational probe for the future IADA/scheduler leg. This section is
# READ-ONLY: it never mounts cgroup2, never loads BPF, never changes anything.
# -----------------------------------------------------------------------------

check_cgroup_v2() {
    section "cgroup v2 unified hierarchy (V2.1, V3.3)"

    # cgroup v2 unified: /sys/fs/cgroup is itself a cgroup2 mount (no /unified
    # subdir on a pure-v2 host). Accept either a mountpoint with a cgroup2 entry
    # in /proc/mounts, or the cgroup.controllers file that only v2 exposes.
    local is_v2=0
    if grep -Eq '(^| )cgroup2 /sys/fs/cgroup ' /proc/mounts 2>/dev/null \
            || grep -Eq 'cgroup2 /sys/fs/cgroup ' /proc/self/mounts 2>/dev/null; then
        is_v2=1
    fi
    if [ "$is_v2" -eq 1 ] && [ -r /sys/fs/cgroup/cgroup.controllers ]; then
        local ctrl; ctrl=$(tr '\n' ' ' < /sys/fs/cgroup/cgroup.controllers 2>/dev/null)
        record cgroup_v2 unified OK "cgroup2 at /sys/fs/cgroup; controllers: ${ctrl% }"
        emit OK "cgroup v2 unified at /sys/fs/cgroup (controllers: ${ctrl% })"
    elif [ "$is_v2" -eq 1 ]; then
        record cgroup_v2 unified DEGRADED "cgroup2 mounted but cgroup.controllers unreadable"
        emit DEGRADED "cgroup v2 mounted but cgroup.controllers unreadable"
    elif [ -d /sys/fs/cgroup/unified ] || grep -q cgroup2 /proc/mounts 2>/dev/null; then
        record cgroup_v2 unified DEGRADED "hybrid cgroup layout (v2 present but not unified at /sys/fs/cgroup)"
        emit DEGRADED "hybrid cgroup layout -- v2.1/v3.3 need cgroup v2 UNIFIED (systemd.unified_cgroup_hierarchy=1)"
    else
        record cgroup_v2 unified MISSING "no cgroup2 mount (host is cgroup v1 only)"
        emit MISSING "no cgroup v2 unified hierarchy -- v2.1/v3.3 per-cgroup attribution unavailable"
    fi
}

check_perf_cgroup() {
    section "perf_event cgroup-mode (V2.1, V3.3)"

    # There is no direct sysfs probe for PERF_FLAG_PID_CGROUP; the kernel gate is
    # >= 5.8 (the cgroup v2 + perf cgroup-mode baseline both v2.1 and v3.3 use).
    # perf_event_open itself is checked in check_perf_uncore (perf:perf_events).
    if kernel_ge 5 8; then
        record perf_cgroup cgroup_mode OK "kernel $KREL >= 5.8 (PERF_FLAG_PID_CGROUP supported)"
        emit OK "perf cgroup-mode (kernel $KREL >= 5.8)"
    else
        record perf_cgroup cgroup_mode MISSING "kernel $KREL < 5.8 -- no per-cgroup perf attribution"
        emit MISSING "perf cgroup-mode needs kernel >= 5.8 (have $KREL)"
    fi
}

check_capabilities() {
    section "Capabilities (CAP_BPF / CAP_PERFMON / CAP_NET_ADMIN)"

    # Soft, informational: when running as root every capability is present, so
    # the verdicts gate on priv:root rather than these. The probe still surfaces
    # whether an unprivileged in-container/in-guest attach (v3.3 cgroup_skb)
    # could work. Prefer capsh --print; fall back to /proc/self/status CapEff.
    local have_capsh=0
    command -v capsh >/dev/null 2>&1 && have_capsh=1

    _cap_present() {
        # _cap_present <cap_name>  (e.g. cap_net_admin)
        local name="$1"
        if [ "$have_capsh" -eq 1 ]; then
            capsh --print 2>/dev/null | grep -qiw "$name" && return 0
            return 1
        fi
        # Without capsh: root has the full set; otherwise we cannot decode the
        # CapEff bitmask portably, so report unknown (treated as DEGRADED).
        [ "$(id -u 2>/dev/null)" = "0" ] && return 0
        return 2
    }

    local cap rec
    for cap in cap_perfmon cap_bpf cap_net_admin; do
        case "$cap" in
            cap_net_admin) rec=cap_net_admin ;;
            cap_perfmon)   rec=cap_perfmon ;;
            cap_bpf)       rec=cap_bpf ;;
        esac
        _cap_present "$cap"
        case $? in
            0) record capabilities "$rec" OK "$cap present"
               emit OK "$cap present" ;;
            1) record capabilities "$rec" DEGRADED "$cap not in current set (root or setcap needed for unprivileged attach)"
               emit DEGRADED "$cap absent (root/setcap needed for in-container/in-guest attach)" ;;
            *) record capabilities "$rec" DEGRADED "$cap unverifiable (no capsh, not root)"
               emit DEGRADED "$cap unverifiable (install libcap2-bin for capsh, or run as root)" ;;
        esac
    done
    unset -f _cap_present
}

check_sched_ext() {
    section "sched_ext (future IADA / scheduler leg)"

    # Informational only: not used in any verdict yet. The IADA leg attaches a
    # BPF scheduler via sched_ext/scx.
    if [ -d /sys/kernel/sched_ext ]; then
        record sched_ext available OK "/sys/kernel/sched_ext present"
        emit OK "/sys/kernel/sched_ext present (sched_ext/scx available)"
    else
        record sched_ext available MISSING "/sys/kernel/sched_ext absent (CONFIG_SCHED_CLASS_EXT=n or kernel < 6.12)"
        emit INFO "/sys/kernel/sched_ext absent -- IADA/scx leg not runnable (informational)"
    fi
}

# -----------------------------------------------------------------------------
# E. BTF (V3, V3.1)
# -----------------------------------------------------------------------------

check_btf() {
    section "BTF (eBPF CO-RE)"
    if [ -f /sys/kernel/btf/vmlinux ]; then
        record btf vmlinux OK "/sys/kernel/btf/vmlinux present"
        emit OK "/sys/kernel/btf/vmlinux"
    else
        record btf vmlinux MISSING "/sys/kernel/btf/vmlinux not found (kernel needs CONFIG_DEBUG_INFO_BTF=y)"
        emit MISSING "/sys/kernel/btf/vmlinux missing -- V3, V3.1 and V3.2 cannot load BPF"
    fi
}

# -----------------------------------------------------------------------------
# F. Kernel debuginfo (V0, V0.1, V1, V1.1)
# -----------------------------------------------------------------------------

check_debuginfo() {
    section "Kernel debuginfo (SystemTap)"
    local rel="$KREL"
    local d="/usr/lib/debug/boot/vmlinux-${rel}"
    local d2="/usr/lib/debug/lib/modules/${rel}/vmlinux"
    if [ -f "$d" ] || [ -f "$d2" ]; then
        record debuginfo vmlinux OK "vmlinux dbgsym present for $rel"
        emit OK "vmlinux-dbgsym for $rel"
    else
        record debuginfo vmlinux MISSING "no vmlinux dbgsym for $rel (apt install linux-image-${rel}-dbgsym)"
        emit MISSING "vmlinux-dbgsym not installed for $rel (run stap-prep / apt install linux-image-${rel}-dbgsym)"
    fi

    # Headers (needed to build stap modules)
    if [ -d "/lib/modules/${rel}/build" ]; then
        record debuginfo headers OK "kernel headers present"
        emit OK "linux-headers-$rel"
    else
        record debuginfo headers MISSING "linux-headers-${rel} missing"
        emit MISSING "linux-headers-${rel} (apt install linux-headers-${rel})"
    fi
}

# -----------------------------------------------------------------------------
# G. Toolchains
# -----------------------------------------------------------------------------

check_toolchains() {
    section "Toolchains and userspace tools"
    check_cmd tools gcc      gcc      "gcc"
    check_cmd tools make     make     "make"
    check_cmd tools git      git      "git"
    check_cmd tools jq       jq       "jq"
    check_cmd tools awk      awk      "awk"
    check_cmd tools sed      sed      "sed"
    check_cmd tools grep     grep     "grep"
    check_cmd tools stress   stress-ng "stress-ng (workload generator)"
    check_cmd tools perf     perf     "perf (groundtruth)"
    check_cmd tools iostat   iostat   "iostat (sysstat side-channel)"
    check_cmd tools numactl  numactl  "numactl"
    check_cmd tools iperf3   iperf3   "iperf3 (netp workload)"
    check_cmd tools python3  python3  "python3 (V3.1 orchestrator)"

    # SystemTap
    check_cmd tools stap     stap     "SystemTap (V0/V0.1/V1/V1.1)"
    if command -v stap >/dev/null 2>&1; then
        local sver
        sver=$(stap --version 2>/dev/null | sed -n 's/.*version \([0-9][0-9.]*\).*/\1/p' | head -1)
        if [ -n "$sver" ]; then
            local maj; maj=${sver%%.*}
            if [ "$maj" -ge 5 ] 2>/dev/null; then
                record tools stap_version OK "stap $sver (5.x required for V1)"
                emit OK "stap $sver"
            else
                record tools stap_version DEGRADED "stap $sver (V1 stap-native expects 5.x)"
                emit DEGRADED "stap $sver -- V1 expects >= 5.x"
            fi
        fi
    fi

    # bpftrace
    check_cmd tools bpftrace bpftrace "bpftrace (V3.1)"
    # libbpf / clang / bpftool
    check_cmd tools clang    clang    "clang (V3 BPF compiler)"
    check_cmd tools llvm     llvm-strip "llvm-strip (V3 build)"
    if pkg-config --exists libbpf 2>/dev/null \
            || [ -f /usr/include/bpf/libbpf.h ] \
            || [ -f /usr/local/include/bpf/libbpf.h ]; then
        record tools libbpf OK "libbpf headers present"
        emit OK "libbpf (-dev)"
    else
        record tools libbpf MISSING "libbpf-dev not installed (apt install libbpf-dev)"
        emit MISSING "libbpf-dev not installed"
    fi
    # bpftool: Ubuntu wraps it under /usr/lib/linux-tools/$krel/bpftool.
    if command -v bpftool >/dev/null 2>&1 && bpftool version >/dev/null 2>&1; then
        record tools bpftool OK "bpftool functional"
        emit OK "bpftool"
    elif ls /usr/lib/linux-tools/*/bpftool >/dev/null 2>&1; then
        record tools bpftool OK "bpftool present under /usr/lib/linux-tools/*"
        emit OK "bpftool (under /usr/lib/linux-tools/*)"
    else
        record tools bpftool MISSING "bpftool missing (apt install linux-tools-generic)"
        emit MISSING "bpftool"
    fi
    # libelf / zlib (V3 link deps)
    if [ -f /usr/include/libelf.h ] || [ -f /usr/include/elf.h ]; then
        record tools libelf OK "libelf-dev present"
        emit OK "libelf-dev"
    else
        record tools libelf MISSING "libelf-dev missing"
        emit MISSING "libelf-dev"
    fi
    if [ -f /usr/include/zlib.h ]; then
        record tools zlib OK "zlib1g-dev present"
        emit OK "zlib1g-dev"
    else
        record tools zlib MISSING "zlib1g-dev missing"
        emit MISSING "zlib1g-dev"
    fi

    # Optional environment tooling for bench --env=container/container-lxc/vm.
    # Either docker OR lxc satisfies a container environment; libvirt (virsh) +
    # virt-install complement qemu for managed-VM provisioning.
    check_cmd tools docker          docker             "docker (env=container)"
    check_cmd tools podman          podman             "podman (env=container-podman, daemonless OCI)"
    check_cmd tools lxc             lxc                "lxc (env=container-lxc, LXD/Incus)"
    check_cmd tools qemu            qemu-system-x86_64 "qemu-system-x86_64 (env=vm)"
    check_cmd tools cloud_localds   cloud-localds     "cloud-localds (env=vm)"
    check_cmd tools virsh           virsh              "virsh (env=vm, libvirt mgmt)"
    check_cmd tools virt_install    virt-install       "virt-install (env=vm guest setup)"

    # env=container-k8s (k3s pods). kubectl drives pod lifecycle; crictl resolves
    # the pod container's host-PID-namespace PID for the profiler to target the
    # deep kubepods cgroup. k3s itself is opt-in heavy (setup-host.sh --with-k8s)
    # and is not required to run other environments.
    check_cmd tools kubectl         kubectl            "kubectl (env=container-k8s, k3s pods)"
    check_cmd tools crictl          crictl             "crictl (env=container-k8s, pod container PID resolution)"

    # Probe k3s presence read-only: a k3s binary or unit file is enough to flag
    # the container-k8s env as runnable. Absence is informational, not a failure.
    local k3s_seen=0
    if command -v k3s >/dev/null 2>&1; then
        k3s_seen=1
    elif [ -f /etc/systemd/system/k3s.service ] || \
         [ -f /usr/local/lib/systemd/system/k3s.service ] || \
         [ -f /lib/systemd/system/k3s.service ]; then
        k3s_seen=1
    fi
    if [ "$k3s_seen" -eq 1 ]; then
        record tools k3s OK "k3s present (env=container-k8s)"
        emit OK "k3s present (env=container-k8s)"
    else
        record tools k3s INFO "k3s absent (env=container-k8s optional; install via setup-host.sh --with-k8s)"
        emit INFO "k3s absent -- env=container-k8s optional (install via setup-host.sh --with-k8s)"
    fi
}

# -----------------------------------------------------------------------------
# H. Privileges (informational; the script itself does not need root)
# -----------------------------------------------------------------------------

check_privs() {
    section "Privileges"
    if [ "$(id -u 2>/dev/null)" = "0" ]; then
        record priv root OK "running as root"
        emit OK "running as root (variants need this at runtime)"
    elif command -v sudo >/dev/null 2>&1; then
        record priv root DEGRADED "not root, sudo available"
        emit DEGRADED "not root -- variants need sudo at runtime"
    else
        record priv root MISSING "not root and sudo not available"
        emit MISSING "no root and no sudo -- profilers cannot be launched"
    fi
}

# -----------------------------------------------------------------------------
# Run all checks once
# -----------------------------------------------------------------------------

[ "$JSON" -eq 0 ] && [ "$QUIET" -eq 0 ] && {
    printf '%sIntP preflight%s -- host=%s kernel=%s\n' \
        "$C_BLD" "$C_RST" "$(hostname 2>/dev/null || echo ?)" "$KREL"
}

check_kernel_and_cpu
check_rdt
check_nic
check_perf_uncore
check_cgroup_v2
check_perf_cgroup
check_capabilities
check_sched_ext
check_btf
check_debuginfo
check_toolchains
check_privs

# -----------------------------------------------------------------------------
# Variant verdicts
# -----------------------------------------------------------------------------

# verdict <variant> <"BUILD"|"RUN"> <list of "category:key:level"> ...
# level = required | recommended. Required MISSING -> verdict MISSING. Required
# DEGRADED or recommended MISSING -> verdict DEGRADED. Otherwise OK.
verdict() {
    local variant="$1" phase="$2"; shift 2
    local worst=OK detail=""
    local item cat key level s d
    for item in "$@"; do
        IFS=: read -r cat key level <<< "$item"
        s=$(status_of "$cat" "$key")
        d=$(detail_of "$cat" "$key")
        [ -z "$s" ] && s=MISSING
        case "$s:$level" in
            MISSING:required)
                worst=MISSING; detail="$detail; $key: $d" ;;
            MISSING:recommended|DEGRADED:required)
                [ "$worst" = OK ] && worst=DEGRADED
                detail="$detail; $key: $d" ;;
            DEGRADED:recommended)
                [ "$worst" = OK ] && worst=DEGRADED
                detail="$detail; $key: $d" ;;
        esac
    done
    detail="${detail#; }"
    record verdict "$variant.$phase" "$worst" "$detail"
}

# v0 -- SystemTap, kernel <=6.6, full RDT, debuginfo
if want_variant v0; then
    if kernel_le 6 6; then
        record kernel_v0 era OK "kernel $KREL <= 6.6"
    else
        record kernel_v0 era MISSING "kernel $KREL > 6.6 -- V0 cannot run (cqm_rmid removed)"
    fi
    verdict v0 BUILD \
        tools:stap:required \
        tools:stap_version:required \
        tools:gcc:required \
        tools:make:required \
        debuginfo:vmlinux:required \
        debuginfo:headers:required
    verdict v0 RUN \
        kernel_v0:era:required \
        tools:stap:required \
        debuginfo:vmlinux:required \
        debuginfo:headers:required \
        rdt:cpu_flag_cqm:required \
        rdt:cpu_flag_cqm_occup:required \
        rdt:resctrl_mounted:recommended \
        kernel:tracefs:required \
        priv:root:required
fi

# v0.1 -- SystemTap, kernel 6.8+, LLC disabled
if want_variant v0.1; then
    if kernel_ge 6 8; then
        record kernel_v01 era OK "kernel $KREL >= 6.8"
    else
        record kernel_v01 era MISSING "kernel $KREL < 6.8 -- V0.1 targets 6.8+ specifically"
    fi
    verdict v0.1 BUILD \
        tools:stap:required \
        tools:gcc:required \
        tools:make:required \
        debuginfo:vmlinux:required \
        debuginfo:headers:required
    verdict v0.1 RUN \
        kernel_v01:era:required \
        tools:stap:required \
        debuginfo:vmlinux:required \
        debuginfo:headers:required \
        kernel:tracefs:required \
        priv:root:required
fi

# v0.2 -- stap + userspace helper, kernel 5.15 GA (U22), full 7 metrics
if want_variant v0.2; then
    # Window matches variant_kernel_ok in bench/run-intp-bench.sh: 5.10 ≤ k < 6.0.
    if kernel_ge 5 10 && ! kernel_ge 6 0; then
        record kernel_v02 era OK "kernel $KREL in [5.10, 6.0) -- v0.2 target window"
    elif ! kernel_ge 5 10; then
        record kernel_v02 era MISSING "kernel $KREL < 5.10 -- below v0.2 floor"
    else
        record kernel_v02 era MISSING "kernel $KREL >= 6.0 -- on 6.x use v1.1 (same helper pattern)"
    fi
    verdict v0.2 BUILD \
        tools:stap:required \
        tools:gcc:required \
        tools:make:required \
        debuginfo:vmlinux:required \
        debuginfo:headers:required
    verdict v0.2 RUN \
        kernel_v02:era:required \
        tools:stap:required \
        debuginfo:vmlinux:required \
        debuginfo:headers:required \
        kernel:tracefs:required \
        kernel:perf_paranoid:required \
        rdt:resctrl_mounted:required \
        priv:root:required
fi

# v1 -- SystemTap stap-native, 6.8+, mbw/llcocc disabled
if want_variant v1; then
    if kernel_ge 6 8; then
        record kernel_v1 era OK "kernel $KREL >= 6.8"
    else
        record kernel_v1 era MISSING "kernel $KREL < 6.8"
    fi
    verdict v1 BUILD \
        tools:stap:required \
        tools:stap_version:required \
        tools:gcc:required \
        debuginfo:vmlinux:required \
        debuginfo:headers:required
    verdict v1 RUN \
        kernel_v1:era:required \
        tools:stap:required \
        debuginfo:vmlinux:required \
        debuginfo:headers:required \
        kernel:tracefs:required \
        priv:root:required
fi

# v1.1 -- stap + helper, 6.8+, full 7 metrics (resctrl + uncore IMC required)
if want_variant v1.1; then
    if kernel_ge 6 8; then
        record kernel_v11 era OK "kernel $KREL >= 6.8"
    else
        record kernel_v11 era MISSING "kernel $KREL < 6.8"
    fi
    verdict v1.1 BUILD \
        tools:stap:required \
        tools:gcc:required \
        tools:make:required \
        debuginfo:vmlinux:required \
        debuginfo:headers:required
    verdict v1.1 RUN \
        kernel_v11:era:required \
        tools:stap:required \
        debuginfo:vmlinux:required \
        debuginfo:headers:required \
        kernel:tracefs:required \
        kernel:perf_paranoid:required \
        rdt:resctrl_mounted:required \
        rdt:cpu_flag_cqm_mbm:recommended \
        rdt:cpu_flag_cqm_occup:recommended \
        perf:imc_uncore:recommended \
        priv:root:required
fi

# v2 -- C / procfs / perf_event / resctrl
if want_variant v2; then
    if kernel_ge 4 10; then
        record kernel_v2 era OK "kernel $KREL >= 4.10"
    else
        record kernel_v2 era MISSING "kernel $KREL < 4.10 (resctrl baseline)"
    fi
    verdict v2 BUILD \
        tools:gcc:required \
        tools:make:required
    verdict v2 RUN \
        kernel_v2:era:required \
        kernel:tracefs:required \
        kernel:perf_paranoid:required \
        perf:perf_events:required \
        rdt:resctrl_mounted:recommended \
        rdt:cpu_flag_cqm:recommended \
        priv:root:required
fi

# v2.1 -- C / cgroup-native hybrid (intp-hybrid, same as v2) + cgroup v2 unified
# + perf cgroup-mode for per-cgroup attribution. Kernel >= 5.8 (cgroup v2 +
# PERF_FLAG_PID_CGROUP baseline). Same toolchain as v2 (gcc/make); 6/7 metrics
# per-cgroup, nets stays system-wide.
if want_variant v2.1; then
    if kernel_ge 5 8; then
        record kernel_v21 era OK "kernel $KREL >= 5.8 (cgroup v2 + perf cgroup-mode)"
    else
        record kernel_v21 era MISSING "kernel $KREL < 5.8 (cgroup v2 + perf cgroup-mode baseline)"
    fi
    verdict v2.1 BUILD \
        tools:gcc:required \
        tools:make:required
    verdict v2.1 RUN \
        kernel_v21:era:required \
        kernel:tracefs:required \
        kernel:perf_paranoid:required \
        perf:perf_events:required \
        cgroup_v2:unified:required \
        perf_cgroup:cgroup_mode:required \
        rdt:resctrl_mounted:recommended \
        rdt:cpu_flag_cqm:recommended \
        priv:root:required
fi

# v3.1 -- bpftrace + python orchestrator
if want_variant v3.1; then
    if kernel_ge 5 8; then
        record kernel_v31 era OK "kernel $KREL >= 5.8"
    else
        record kernel_v31 era MISSING "kernel $KREL < 5.8 (CO-RE baseline)"
    fi
    verdict v3.1 BUILD \
        tools:bpftrace:required \
        tools:python3:required
    verdict v3.1 RUN \
        kernel_v31:era:required \
        tools:bpftrace:required \
        tools:python3:required \
        btf:vmlinux:required \
        kernel:tracefs:required \
        kernel:perf_paranoid:required \
        rdt:resctrl_mounted:recommended \
        priv:root:required
fi

# v3 -- eBPF/CO-RE libbpf
if want_variant v3; then
    if kernel_ge 5 8; then
        record kernel_v3 era OK "kernel $KREL >= 5.8"
    else
        record kernel_v3 era MISSING "kernel $KREL < 5.8 (CO-RE baseline)"
    fi
    verdict v3 BUILD \
        tools:clang:required \
        tools:gcc:required \
        tools:make:required \
        tools:libbpf:required \
        tools:bpftool:required \
        tools:libelf:required \
        tools:zlib:required \
        btf:vmlinux:required
    verdict v3 RUN \
        kernel_v3:era:required \
        btf:vmlinux:required \
        kernel:tracefs:required \
        kernel:perf_paranoid:required \
        perf:perf_events:required \
        rdt:resctrl_mounted:recommended \
        priv:root:required
fi

# v3.2 -- eBPF/CO-RE libbpf, in-kernel aggregating (kernel >= 5.10)
if want_variant v3.2; then
    if kernel_ge 5 10; then
        record kernel_v32 era OK "kernel $KREL >= 5.10"
    else
        record kernel_v32 era MISSING "kernel $KREL < 5.10 (libbpf+CO-RE baseline)"
    fi
    verdict v3.2 BUILD \
        tools:clang:required \
        tools:gcc:required \
        tools:make:required \
        tools:libbpf:required \
        tools:bpftool:required \
        tools:libelf:required \
        tools:zlib:required \
        btf:vmlinux:required
    verdict v3.2 RUN \
        kernel_v32:era:required \
        btf:vmlinux:required \
        kernel:tracefs:required \
        kernel:perf_paranoid:required \
        perf:perf_events:required \
        rdt:resctrl_mounted:recommended \
        priv:root:required
fi

# v3.3 -- eBPF cgroup-native (intp-ebpf-cgroup, sibling of v3.2). Same toolchain
# as v3.2 (clang/libbpf/bpftool/BTF/libelf/zlib) PLUS cgroup v2 unified +
# cgroup_skb attach (CAP_NET_ADMIN) + perf cgroup-mode + bio-owner blk. Kernel
# >= 5.8 (cgroup-BPF + cgroup v2 floor). per-cgroup counter maps; nets is a
# per-cgroup byte-share proxy.
if want_variant v3.3; then
    if kernel_ge 5 8; then
        record kernel_v33 era OK "kernel $KREL >= 5.8 (cgroup-BPF + cgroup v2)"
    else
        record kernel_v33 era MISSING "kernel $KREL < 5.8 (cgroup-BPF + cgroup v2 baseline)"
    fi
    verdict v3.3 BUILD \
        tools:clang:required \
        tools:gcc:required \
        tools:make:required \
        tools:libbpf:required \
        tools:bpftool:required \
        tools:libelf:required \
        tools:zlib:required \
        btf:vmlinux:required
    verdict v3.3 RUN \
        kernel_v33:era:required \
        btf:vmlinux:required \
        kernel:tracefs:required \
        kernel:perf_paranoid:required \
        perf:perf_events:required \
        cgroup_v2:unified:required \
        perf_cgroup:cgroup_mode:required \
        capabilities:cap_net_admin:recommended \
        rdt:resctrl_mounted:recommended \
        priv:root:required
fi

# bench harness -- bench/run-intp-bench.sh and helpers
if want_variant bench; then
    verdict bench BUILD \
        tools:gcc:required \
        tools:make:required
    verdict bench RUN \
        tools:stress:required \
        tools:awk:required \
        tools:grep:required \
        tools:sed:required \
        tools:jq:required \
        tools:perf:recommended \
        tools:iostat:recommended \
        tools:iperf3:recommended \
        tools:numactl:recommended \
        tools:docker:recommended \
        tools:podman:recommended \
        tools:lxc:recommended \
        tools:qemu:recommended \
        tools:cloud_localds:recommended \
        tools:virsh:recommended \
        tools:virt_install:recommended \
        priv:root:required
fi

# -----------------------------------------------------------------------------
# Per-metric coverage (independent of variant choice)
# -----------------------------------------------------------------------------

metric_status() {
    # Echo OK / DEGRADED / MISSING for each of the 7 metrics.
    # Caller passes the metric name.
    local m="$1" v
    case "$m" in
        netp)
            v=$(awk -F'\t' '$1=="nic" && $3=="OK" {print "OK"; exit}' "$RESULTS")
            [ -n "$v" ] && echo OK || echo DEGRADED
            ;;
        nets|blk|cpu)
            status_of kernel tracefs
            ;;
        mbw)
            local r p
            r=$(status_of rdt cpu_flag_cqm_mbm)
            p=$(status_of perf imc_uncore)
            if [ "$r" = OK ] || [ "$p" = OK ]; then echo OK
            elif [ "$r" = OK ] || [ "$p" = DEGRADED ]; then echo DEGRADED
            else echo MISSING; fi
            ;;
        llcmr)
            status_of perf perf_events
            ;;
        llcocc)
            local f m
            f=$(status_of rdt cpu_flag_cqm_occup)
            m=$(status_of rdt resctrl_mounted)
            if [ "$f" = OK ] && [ "$m" = OK ]; then echo OK
            elif [ "$f" = OK ]; then echo DEGRADED
            else echo MISSING; fi
            ;;
    esac
}

# -----------------------------------------------------------------------------
# Final summary
# -----------------------------------------------------------------------------

if [ "$JSON" -eq 1 ]; then
    # Minimal JSON without jq dependency. Keys are stable; values are strings.
    printf '{\n'
    printf '  "host":"%s",\n' "$(hostname 2>/dev/null || echo ?)"
    printf '  "kernel":"%s",\n' "$KREL"
    printf '  "variants":{\n'
    first=1
    for v in "${SELECTED[@]}"; do
        b=$(status_of verdict "$v.BUILD"); r=$(status_of verdict "$v.RUN")
        bd=$(detail_of verdict "$v.BUILD"); rd=$(detail_of verdict "$v.RUN")
        [ -z "$b$r" ] && continue
        [ "$first" -eq 0 ] && printf ',\n'
        first=0
        printf '    "%s":{"build":"%s","run":"%s","build_detail":"%s","run_detail":"%s"}' \
            "$v" "${b:-N/A}" "${r:-N/A}" \
            "$(printf '%s' "$bd" | sed 's/"/\\"/g')" \
            "$(printf '%s' "$rd" | sed 's/"/\\"/g')"
    done
    printf '\n  },\n'
    printf '  "metrics":{\n'
    first=1
    for m in netp nets blk mbw llcmr llcocc cpu; do
        s=$(metric_status "$m")
        [ "$first" -eq 0 ] && printf ',\n'
        first=0
        printf '    "%s":"%s"' "$m" "${s:-MISSING}"
    done
    printf '\n  }\n}\n'
else
    printf '\n%s== Variant verdicts ==%s\n' "$C_BLD" "$C_RST"
    printf '%-8s %-10s %-10s  %s\n' "VARIANT" "BUILD" "RUN" "NOTES"
    for v in "${SELECTED[@]}"; do
        b=$(status_of verdict "$v.BUILD"); r=$(status_of verdict "$v.RUN")
        d=$(detail_of verdict "$v.RUN"); [ -z "$d" ] && d=$(detail_of verdict "$v.BUILD")
        [ -z "$b$r" ] && continue
        cb="$C_GRN"; cr="$C_GRN"
        case "$b" in DEGRADED) cb="$C_YEL";; MISSING) cb="$C_RED";; esac
        case "$r" in DEGRADED) cr="$C_YEL";; MISSING) cr="$C_RED";; esac
        printf '%-8s %s%-10s%s %s%-10s%s  %s\n' \
            "$v" "$cb" "${b:-N/A}" "$C_RST" "$cr" "${r:-N/A}" "$C_RST" "${d:0:80}"
    done
    printf '\n%s== Metric coverage ==%s\n' "$C_BLD" "$C_RST"
    for m in netp nets blk mbw llcmr llcocc cpu; do
        s=$(metric_status "$m"); col="$C_GRN"
        case "$s" in DEGRADED) col="$C_YEL";; MISSING) col="$C_RED";; esac
        printf '  %-7s %s%s%s\n' "$m" "$col" "${s:-MISSING}" "$C_RST"
    done
fi

# -----------------------------------------------------------------------------
# Exit code
# -----------------------------------------------------------------------------

worst=OK
for v in "${SELECTED[@]}"; do
    for phase in BUILD RUN; do
        s=$(status_of verdict "$v.$phase")
        case "$s" in
            MISSING)  [ "$worst" != MISSING  ] && worst=MISSING ;;
            DEGRADED) [ "$worst" = OK        ] && worst=DEGRADED ;;
        esac
    done
done

case "$worst" in
    OK)       exit 0 ;;
    DEGRADED) [ "$STRICT" -eq 1 ] && exit 2 || exit 0 ;;
    MISSING)  exit 2 ;;
esac

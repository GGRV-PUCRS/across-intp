#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# validate-rdt-host.sh -- Intel RDT host capability audit
#
# Validates that a host exposes every Intel Resource Director Technology (RDT)
# feature required for IntP interference profiling experiments:
#   - CAT (Cache Allocation Technology) -- L3 and optionally L2
#   - CBM (Capacity Bitmask) registers -- width, min-bits, CLOS count
#   - CMT (Cache Monitoring Technology) -- occupancy via CQM
#   - MBM (Memory Bandwidth Monitoring) -- total and local
#   - MBA (Memory Bandwidth Allocation) -- optional but flagged if absent
#   - resctrl filesystem -- mounted or mountable
#   - MSR device access and key RDT MSRs -- via /dev/cpu/*/msr + rdmsr
#   - Kernel config -- CONFIG_X86_CPU_RESCTRL
#
# Does NOT mount resctrl, load kernel modules, or change any system state.
#
# Usage:
#   ./validate-rdt-host.sh            # full audit, coloured output
#   ./validate-rdt-host.sh --json     # machine-readable JSON summary
#   ./validate-rdt-host.sh --quiet    # only the final verdict line
#   ./validate-rdt-host.sh --mount    # attempt a temporary resctrl mount to
#                                     # read capability info (requires root)
#
# Exit codes:
#   0  -- all required capabilities present
#   1  -- one or more required capabilities missing
#   2  -- host is not Intel or fundamentally incompatible
# -----------------------------------------------------------------------------

set -u

# ---- option parsing ---------------------------------------------------------

JSON=0
QUIET=0
DO_MOUNT=0

usage() { sed -n '2,/^# ---/p' "$0" | sed 's/^# \?//'; }

while [ $# -gt 0 ]; do
    case "$1" in
        --json)    JSON=1; shift ;;
        --quiet)   QUIET=1; shift ;;
        --mount)   DO_MOUNT=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) printf 'Unknown option: %s\n' "$1" >&2; usage >&2; exit 64 ;;
    esac
done

# ---- colour helpers ---------------------------------------------------------

if [ -t 1 ] && [ "$JSON" -eq 0 ]; then
    C_RED=$'\033[31m'; C_YEL=$'\033[33m'; C_GRN=$'\033[32m'
    C_CYN=$'\033[36m'; C_DIM=$'\033[2m';  C_BLD=$'\033[1m';  C_RST=$'\033[0m'
else
    C_RED=""; C_YEL=""; C_GRN=""; C_CYN=""; C_DIM=""; C_BLD=""; C_RST=""
fi

RESULTS=$(mktemp -t rdt-validate.XXXXXX)
trap 'rm -f "$RESULTS"' EXIT

# record <section> <key> <status:OK|WARN|FAIL|INFO> <detail>
record() {
    local sec="$1" key="$2" status="$3"; shift 3
    printf '%s\t%s\t%s\t%s\n' "$sec" "$key" "$status" "$*" >> "$RESULTS"
}

status_colour() {
    case "$1" in
        OK)   printf '%s' "${C_GRN}OK${C_RST}" ;;
        WARN) printf '%s' "${C_YEL}WARN${C_RST}" ;;
        FAIL) printf '%s' "${C_RED}FAIL${C_RST}" ;;
        INFO) printf '%s' "${C_CYN}INFO${C_RST}" ;;
    esac
}

log() { [ "$QUIET" -eq 0 ] && printf '%s\n' "$*"; }
logf() { [ "$QUIET" -eq 0 ] && printf "$@"; }

RESCTRL=/sys/fs/resctrl
RESCTRL_MOUNTED=0
RESCTRL_TEMP_MOUNT=0

# =============================================================================
# 1. CPU vendor and model
# =============================================================================

SEC="CPU"

vendor=$(grep -m1 'vendor_id' /proc/cpuinfo 2>/dev/null | awk -F: '{print $2}' | tr -d ' ')
model=$(grep -m1 'model name' /proc/cpuinfo 2>/dev/null | awk -F: '{print $2}' | sed 's/^ *//')
record "$SEC" vendor INFO "$vendor"
record "$SEC" model  INFO "$model"

if [ "$vendor" != "GenuineIntel" ]; then
    record "$SEC" vendor_check FAIL "Not Intel (got: ${vendor:-unknown}). RDT is Intel-only."
    # Emit partial output so user gets the full picture even on non-Intel
else
    record "$SEC" vendor_check OK "Intel CPU confirmed"
fi

cpu_family=$(grep -m1 'cpu family' /proc/cpuinfo 2>/dev/null | awk -F: '{print $2}' | tr -d ' ')
stepping=$(grep -m1 'stepping'    /proc/cpuinfo 2>/dev/null | awk -F: '{print $2}' | tr -d ' ')
record "$SEC" family_stepping INFO "family=${cpu_family} stepping=${stepping}"

sockets=$(grep -c 'physical id' /proc/cpuinfo 2>/dev/null | head -1 || echo "?")
sockets=$(sort -u <(grep 'physical id' /proc/cpuinfo 2>/dev/null | awk -F: '{print $2}') 2>/dev/null | wc -l)
cores=$(grep -m1 'cpu cores' /proc/cpuinfo 2>/dev/null | awk -F: '{print $2}' | tr -d ' ')
record "$SEC" topology INFO "sockets=${sockets} cores/socket=${cores:-?}"

# =============================================================================
# 2. CPU flags -- /proc/cpuinfo
# =============================================================================

SEC="CPU flags"

# Grab flags from first physical CPU entry only
cpu_flags=$(grep -m1 '^flags' /proc/cpuinfo 2>/dev/null | cut -d: -f2)

check_flag() {
    local flag="$1" desc="$2" required="${3:-yes}"
    if echo "$cpu_flags" | grep -qw "$flag"; then
        record "$SEC" "$flag" OK "$desc"
        return 0
    else
        [ "$required" = "yes" ] && record "$SEC" "$flag" FAIL "Missing -- $desc" \
                                || record "$SEC" "$flag" WARN "Absent (optional) -- $desc"
        return 1
    fi
}

# Core RDT monitoring flags (required for llcocc / llcmr via resctrl)
check_flag cqm          "Cache QoS Monitoring (CQM) base" yes
check_flag cqm_llc      "CQM LLC occupancy monitoring"    yes
check_flag cqm_occup_llc "CQM LLC occupancy (alias)"     no   # some kernels expose as cqm_llc only
check_flag cqm_mbm_total "MBM total memory bandwidth"     yes
check_flag cqm_mbm_local "MBM local memory bandwidth"     yes

# CAT / CBM flags (required for cache-way isolation & CBM registers)
check_flag rdt_a        "RDT Allocation feature leaf"     yes
check_flag cat_l3       "L3 Cache Allocation Technology"  yes
check_flag cat_l2       "L2 Cache Allocation Technology"  no
check_flag cdp_l3       "L3 Code/Data Prioritization"     no
check_flag cdp_l2       "L2 Code/Data Prioritization"     no
check_flag mba          "Memory Bandwidth Allocation"     no

# =============================================================================
# 3. CPUID leaf 0x0F / 0x10 via cpuid tool (optional deep check)
# =============================================================================

SEC="CPUID"

if command -v cpuid &>/dev/null; then
    # Leaf 0x10: RDT Allocation enumeration
    leaf10=$(cpuid -r -l 0x10 2>/dev/null | head -20)
    if [ -n "$leaf10" ]; then
        record "$SEC" leaf_0x10 OK "CPUID leaf 0x10 (RDT-A) readable"
        # Sub-leaf 1: L3 CAT
        leaf10_sl1=$(cpuid -r -l 0x10 -s 1 2>/dev/null | grep -i 'eax\|ecx\|edx' | head -5)
        if [ -n "$leaf10_sl1" ]; then
            # ECX contains CBM length - 1 (bits 4:0 of EAX in sub-leaf 1)
            cbm_len=$(cpuid -r -l 0x10 -s 1 2>/dev/null | awk '/eax/{print $NF}' | \
                      awk '{printf "%d\n", (strtonum($1) & 0x1F) + 1}' 2>/dev/null | head -1)
            [ -n "$cbm_len" ] && record "$SEC" l3_cbm_len INFO "L3 CBM length: ${cbm_len} bits"
        fi
    else
        record "$SEC" leaf_0x10 WARN "cpuid tool present but leaf 0x10 returned nothing"
    fi

    # Leaf 0x0F: RDT Monitoring enumeration
    leaf0f=$(cpuid -r -l 0x0F 2>/dev/null | head -10)
    if [ -n "$leaf0f" ]; then
        record "$SEC" leaf_0x0F OK "CPUID leaf 0x0F (RDT-M) readable"
    else
        record "$SEC" leaf_0x0F WARN "cpuid tool present but leaf 0x0F returned nothing"
    fi
else
    record "$SEC" cpuid_tool INFO "cpuid tool not installed; skipping CPUID leaf deep-check (apt install cpuid)"
fi

# =============================================================================
# 4. Kernel configuration
# =============================================================================

SEC="Kernel config"

kver=$(uname -r)
record "$SEC" kernel_version INFO "$kver"

# Look for CONFIG_X86_CPU_RESCTRL in several places
KCONFIG_FOUND=0
for cfg in "/boot/config-${kver}" "/proc/config.gz" "/boot/config" "/proc/config"; do
    if [ -f "$cfg" ]; then
        if [[ "$cfg" == *.gz ]]; then
            val=$(zcat "$cfg" 2>/dev/null | grep '^CONFIG_X86_CPU_RESCTRL' | head -1)
        else
            val=$(grep '^CONFIG_X86_CPU_RESCTRL' "$cfg" 2>/dev/null | head -1)
        fi
        if [ -n "$val" ]; then
            KCONFIG_FOUND=1
            if echo "$val" | grep -q '=y'; then
                record "$SEC" CONFIG_X86_CPU_RESCTRL OK "Built-in (=y) via $cfg"
            elif echo "$val" | grep -q '=m'; then
                record "$SEC" CONFIG_X86_CPU_RESCTRL WARN "Module (=m) via $cfg -- module must be loaded"
            else
                record "$SEC" CONFIG_X86_CPU_RESCTRL FAIL "Disabled ($val) via $cfg"
            fi
            break
        fi
    fi
done
[ "$KCONFIG_FOUND" -eq 0 ] && \
    record "$SEC" CONFIG_X86_CPU_RESCTRL WARN "Kernel config not readable; cannot verify (expected in /boot/config-${kver})"

# resctrl in /proc/filesystems
if grep -q resctrl /proc/filesystems 2>/dev/null; then
    record "$SEC" resctrl_fs_type OK "resctrl listed in /proc/filesystems"
else
    record "$SEC" resctrl_fs_type FAIL "resctrl NOT in /proc/filesystems -- kernel lacks resctrl support"
fi

# msr module
if [ -d /dev/cpu ] && ls /dev/cpu/0/msr &>/dev/null; then
    record "$SEC" msr_device OK "/dev/cpu/0/msr present (msr module loaded)"
elif modinfo msr &>/dev/null; then
    record "$SEC" msr_device WARN "msr module available but not loaded (run: modprobe msr)"
else
    record "$SEC" msr_device FAIL "msr module not available -- MSR reads impossible"
fi

# =============================================================================
# 5. resctrl filesystem capabilities
# =============================================================================

SEC="resctrl"

# Is it already mounted?
if mountpoint -q "$RESCTRL" 2>/dev/null; then
    RESCTRL_MOUNTED=1
    record "$SEC" mount OK "resctrl already mounted at $RESCTRL"
elif [ "$DO_MOUNT" -eq 1 ]; then
    if [ "$(id -u)" -eq 0 ]; then
        mkdir -p "$RESCTRL" 2>/dev/null || true
        if mount -t resctrl resctrl "$RESCTRL" 2>/dev/null; then
            RESCTRL_MOUNTED=1
            RESCTRL_TEMP_MOUNT=1
            record "$SEC" mount OK "Temporarily mounted resctrl at $RESCTRL (will unmount)"
        else
            record "$SEC" mount FAIL "mount -t resctrl failed -- kernel or hardware missing support"
        fi
    else
        record "$SEC" mount WARN "Not root; cannot attempt temporary mount (re-run with sudo --mount)"
    fi
else
    record "$SEC" mount WARN "resctrl not mounted; run 'sudo mount -t resctrl resctrl /sys/fs/resctrl' or pass --mount"
fi

# Read capability info from resctrl/info if mounted
if [ "$RESCTRL_MOUNTED" -eq 1 ] && [ -d "$RESCTRL/info" ]; then

    # --- L3 CAT ---
    if [ -d "$RESCTRL/info/L3" ]; then
        cbm_mask=$(cat "$RESCTRL/info/L3/cbm_mask"    2>/dev/null || echo "?")
        min_bits=$(cat "$RESCTRL/info/L3/min_cbm_bits" 2>/dev/null || echo "?")
        num_clos=$(cat "$RESCTRL/info/L3/num_closids"  2>/dev/null || echo "?")
        # derive CBM width from mask
        if [ "$cbm_mask" != "?" ]; then
            cbm_bits=$(printf '%d\n' "0x${cbm_mask}" 2>/dev/null | \
                       awk '{n=0; v=$1; while(v){n+=v%2; v=int(v/2)} print n}')
        else
            cbm_bits="?"
        fi
        record "$SEC" L3_CAT        OK   "L3 CAT supported"
        record "$SEC" L3_cbm_mask   INFO "cbm_mask=0x${cbm_mask} (${cbm_bits} ways)"
        record "$SEC" L3_min_bits   INFO "min_cbm_bits=${min_bits}"
        record "$SEC" L3_num_closids INFO "num_closids=${num_clos}"
        if [ "$cbm_bits" != "?" ] && [ "$cbm_bits" -ge 8 ] 2>/dev/null; then
            record "$SEC" L3_cbm_width OK "CBM width ${cbm_bits} bits (>= 8 ways: good)"
        elif [ "$cbm_bits" != "?" ]; then
            record "$SEC" L3_cbm_width WARN "CBM width ${cbm_bits} bits (narrow; interference partitioning limited)"
        fi
    else
        record "$SEC" L3_CAT FAIL "No $RESCTRL/info/L3 -- L3 CAT not exposed"
    fi

    # --- L2 CAT (optional) ---
    if [ -d "$RESCTRL/info/L2" ]; then
        l2_mask=$(cat "$RESCTRL/info/L2/cbm_mask"    2>/dev/null || echo "?")
        l2_clos=$(cat "$RESCTRL/info/L2/num_closids"  2>/dev/null || echo "?")
        record "$SEC" L2_CAT INFO "L2 CAT supported (cbm_mask=0x${l2_mask} num_closids=${l2_clos})"
    else
        record "$SEC" L2_CAT INFO "L2 CAT not present (optional)"
    fi

    # --- MBA (optional) ---
    if [ -d "$RESCTRL/info/MB" ]; then
        mb_gran=$(cat "$RESCTRL/info/MB/bandwidth_gran" 2>/dev/null || echo "?")
        mb_min=$(cat  "$RESCTRL/info/MB/min_bandwidth"  2>/dev/null || echo "?")
        mb_clos=$(cat "$RESCTRL/info/MB/num_closids"    2>/dev/null || echo "?")
        record "$SEC" MBA INFO "MBA supported: gran=${mb_gran}% min=${mb_min}% closids=${mb_clos}"
    else
        record "$SEC" MBA WARN "MBA (Memory Bandwidth Allocation) not present (optional)"
    fi

    # --- L3 Monitoring (CMT + MBM) ---
    if [ -d "$RESCTRL/info/L3_MON" ]; then
        max_rmid=$(cat  "$RESCTRL/info/L3_MON/max_rmid"      2>/dev/null || echo "?")
        mon_feat=$(cat  "$RESCTRL/info/L3_MON/mon_features"   2>/dev/null || echo "?")
        record "$SEC" L3_MON     OK "L3 monitoring (CMT/MBM) supported"
        record "$SEC" L3_max_rmid INFO "max_rmid=${max_rmid}"
        record "$SEC" L3_mon_features INFO "features: ${mon_feat}"

        # Verify each expected feature
        for feat in llc_occupancy mbm_total_bytes mbm_local_bytes; do
            if echo "$mon_feat" | grep -qw "$feat"; then
                record "$SEC" "mon_${feat}" OK "$feat available"
            else
                record "$SEC" "mon_${feat}" WARN "$feat NOT in mon_features (needed by IntP llcocc/llcmr)"
            fi
        done
    else
        record "$SEC" L3_MON FAIL "No $RESCTRL/info/L3_MON -- CMT/MBM not exposed"
    fi

    # Check that tasks file and mon_groups are writable (root test)
    if [ -w "$RESCTRL/tasks" ]; then
        record "$SEC" tasks_writable OK "resctrl/tasks writable (root confirmed)"
    else
        record "$SEC" tasks_writable WARN "resctrl/tasks not writable (not root or permission issue)"
    fi

else
    record "$SEC" capabilities WARN "resctrl not mounted -- skipping capability detail read"
fi

# Unmount if we mounted it temporarily
if [ "$RESCTRL_TEMP_MOUNT" -eq 1 ]; then
    umount "$RESCTRL" 2>/dev/null && \
        record "$SEC" temp_unmount INFO "Temporary resctrl mount removed" || \
        record "$SEC" temp_unmount WARN "Could not unmount temporary resctrl -- please run: umount $RESCTRL"
fi

# =============================================================================
# 6. MSR access and key RDT MSRs
# =============================================================================

SEC="MSRs"

MSR_OK=0
MSR_MODULE_AVAIL=0
if [ -c /dev/cpu/0/msr ]; then
    MSR_OK=1
    record "$SEC" msr_dev OK "/dev/cpu/0/msr accessible"
elif modinfo msr &>/dev/null; then
    MSR_MODULE_AVAIL=1
    record "$SEC" msr_dev WARN "/dev/cpu/0/msr absent -- msr module not loaded (fix: modprobe msr)"
else
    record "$SEC" msr_dev FAIL "/dev/cpu/0/msr not accessible and msr module unavailable (kernel built without MSR support)"
fi

# Key RDT MSR addresses
declare -A RDT_MSRS=(
    ["0xC8F"]="IA32_PQR_ASSOC (CLOS/RMID per-CPU assignment)"
    ["0xC8D"]="IA32_QM_EVTSEL  (QM event selector)"
    ["0xC8E"]="IA32_QM_CTR     (QM counter)"
    ["0xC81"]="MSR_IA32_L3_QOS_CFG (L3 CAT/CDP enable)"
    ["0xC90"]="IA32_L3_CBM_0   (L3 CBM for CLOS 0)"
)

if command -v rdmsr &>/dev/null && [ "$MSR_OK" -eq 1 ]; then
    record "$SEC" rdmsr_tool OK "rdmsr tool available"
    for addr in "0xC8F" "0xC8D" "0xC8E" "0xC81" "0xC90"; do
        desc="${RDT_MSRS[$addr]}"
        val=$(rdmsr -p 0 "$addr" 2>/dev/null || echo "ERR")
        if [ "$val" != "ERR" ]; then
            record "$SEC" "msr_${addr}" OK "  $addr = 0x${val}  -- $desc"
        else
            # Distinguish: permission error vs hardware-missing MSR
            if [ "$(id -u)" -ne 0 ]; then
                record "$SEC" "msr_${addr}" WARN "  $addr unreadable -- $desc (re-run as root)"
            else
                record "$SEC" "msr_${addr}" WARN "  $addr unreadable -- $desc (MSR not present on this CPU generation)"
            fi
        fi
    done
elif [ "$MSR_OK" -eq 1 ]; then
    record "$SEC" rdmsr_tool WARN "rdmsr not installed; cannot read individual MSRs (apt install msr-tools)"
    # Fallback: try a raw dd read of IA32_PQR_ASSOC (0xC8F = 3215 decimal)
    raw=$(dd if=/dev/cpu/0/msr bs=8 count=1 skip=3215 2>/dev/null | od -A n -t x8 | tr -d ' \n' || echo "")
    if [ -n "$raw" ]; then
        record "$SEC" msr_raw_read OK "Raw MSR read succeeded (IA32_PQR_ASSOC=0x${raw})"
    else
        record "$SEC" msr_raw_read WARN "Raw MSR read via dd failed (re-run as root)"
    fi
elif [ "$MSR_MODULE_AVAIL" -eq 1 ]; then
    record "$SEC" msr_reads INFO "MSR reads skipped -- load msr module first: modprobe msr"
else
    for addr in "${!RDT_MSRS[@]}"; do
        record "$SEC" "msr_${addr}" WARN "  $addr -- ${RDT_MSRS[$addr]} (skipped: msr module unavailable)"
    done
fi

# Check if IA32_PQR_ASSOC CLOS field is non-zero (would mean a CLOS was already set)
# -- informational only

# =============================================================================
# 7. Tooling availability
# =============================================================================

SEC="Tools"

for tool in rdmsr wrmsr pqos intel-cmt-cat; do
    if command -v "$tool" &>/dev/null; then
        record "$SEC" "$tool" OK "$(command -v "$tool")"
    else
        record "$SEC" "$tool" INFO "Not installed (optional)"
    fi
done

# pqos from intel-cmt-cat is the authoritative RDT tool
if command -v pqos &>/dev/null; then
    pqos_out=$(pqos -s 2>/dev/null | head -10 || echo "error")
    if echo "$pqos_out" | grep -qi "error\|not supported"; then
        record "$SEC" pqos_check WARN "pqos installed but reports error -- may need root or RDT not present"
    else
        record "$SEC" pqos_check OK "pqos -s succeeded"
    fi
fi

for tool in stress-ng perf; do
    if command -v "$tool" &>/dev/null; then
        record "$SEC" "$tool" OK "$(command -v "$tool")"
    else
        record "$SEC" "$tool" WARN "Not installed (needed for IntP benchmarks)"
    fi
done

# =============================================================================
# Output
# =============================================================================

if [ "$JSON" -eq 1 ]; then
    # ---- JSON output --------------------------------------------------------
    printf '{\n'
    printf '  "host": "%s",\n' "$(hostname)"
    printf '  "kernel": "%s",\n' "$(uname -r)"
    printf '  "cpu_model": "%s",\n' "$model"
    printf '  "checks": [\n'
    first=1
    while IFS=$'\t' read -r sec key status detail; do
        [ "$first" -eq 0 ] && printf ',\n'
        first=0
        printf '    {"section":"%s","key":"%s","status":"%s","detail":"%s"}' \
            "$sec" "$key" "$status" "${detail//\"/\\\"}"
    done < "$RESULTS"
    printf '\n  ],\n'
    # Compute summary counts
    fails=$(grep -c $'\tFAIL\t' "$RESULTS" || true)
    warns=$(grep -c $'\tWARN\t' "$RESULTS" || true)
    oks=$(grep -c   $'\tOK\t'   "$RESULTS" || true)
    if [ "$vendor" != "GenuineIntel" ]; then
        verdict="INCOMPATIBLE"
    elif [ "$fails" -gt 0 ]; then
        verdict="MISSING_REQUIRED"
    elif [ "$warns" -gt 0 ]; then
        verdict="DEGRADED"
    else
        verdict="READY"
    fi
    printf '  "summary": {"ok":%d,"warn":%d,"fail":%d,"verdict":"%s"}\n' \
        "$oks" "$warns" "$fails" "$verdict"
    printf '}\n'
    exit 0
fi

# ---- human-readable output --------------------------------------------------

[ "$QUIET" -eq 0 ] && printf '\n%s%-20s %-36s %s%s\n' \
    "${C_BLD}" "SECTION" "CHECK" "STATUS  DETAIL" "${C_RST}"
[ "$QUIET" -eq 0 ] && printf '%s%s%s\n' "$C_DIM" "$(printf '%-90s' '' | tr ' ' '-')" "$C_RST"

prev_sec=""
while IFS=$'\t' read -r sec key status detail; do
    if [ "$QUIET" -eq 1 ]; then
        [ "$status" = "FAIL" ] || [ "$status" = "WARN" ] || continue
    fi

    if [ "$sec" != "$prev_sec" ] && [ "$QUIET" -eq 0 ]; then
        printf '\n%s%s%s\n' "${C_BLD}${C_CYN}" "[$sec]" "${C_RST}"
        prev_sec="$sec"
    fi

    badge=$(status_colour "$status")
    printf '  %-34s [%s]  %s%s%s\n' \
        "$key" "$badge" "$C_DIM" "$detail" "$C_RST"
done < "$RESULTS"

[ "$QUIET" -eq 0 ] && printf '\n%s%s%s\n' "$C_DIM" "$(printf '%-90s' '' | tr ' ' '-')" "$C_RST"

# Compute and print summary
fails=$(grep -c $'\tFAIL\t' "$RESULTS" 2>/dev/null || true)
warns=$(grep -c $'\tWARN\t' "$RESULTS" 2>/dev/null || true)
oks=$(grep -c   $'\tOK\t'   "$RESULTS" 2>/dev/null || true)

fails=${fails:-0}
warns=${warns:-0}
oks=${oks:-0}

if [ "$vendor" != "GenuineIntel" ]; then
    verdict="${C_RED}INCOMPATIBLE${C_RST}"
    verdict_plain="INCOMPATIBLE"
    rc=2
elif [ "$fails" -gt 0 ]; then
    verdict="${C_RED}MISSING REQUIRED CAPABILITIES${C_RST}"
    verdict_plain="MISSING_REQUIRED"
    rc=1
elif [ "$warns" -gt 0 ]; then
    verdict="${C_YEL}DEGRADED (optional capabilities missing)${C_RST}"
    verdict_plain="DEGRADED"
    rc=0
else
    verdict="${C_GRN}READY${C_RST}"
    verdict_plain="READY"
    rc=0
fi

# RDT generation note based on which flags are present
rdt_gen=""
if echo "$cpu_flags" | grep -qw mba; then
    rdt_gen="Gen4 (Skylake-SP+): CAT+MBM+MBA"
elif echo "$cpu_flags" | grep -qw cqm_mbm_total && echo "$cpu_flags" | grep -qw cat_l3; then
    rdt_gen="Gen3 (Broadwell-EP, E5 v4): CAT+CMT+MBM (no MBA)"
elif echo "$cpu_flags" | grep -qw cat_l3; then
    rdt_gen="Gen2: CAT+CMT (no MBM)"
elif echo "$cpu_flags" | grep -qw cqm_llc; then
    rdt_gen="Gen1 (Haswell-EP, E5 v3): CMT only (no CAT, no MBM)"
elif [ "$vendor" = "GenuineIntel" ]; then
    rdt_gen="No RDT (pre-Haswell-EP or consumer CPU)"
fi

printf '\n%sVerdict: %s%s   %s(OK=%d  WARN=%d  FAIL=%d)%s\n' \
    "$C_BLD" "$verdict" "$C_RST" "$C_DIM" "$oks" "$warns" "$fails" "$C_RST"
[ -n "$rdt_gen" ] && printf '%sRDT gen:  %s%s\n' "$C_DIM" "$rdt_gen" "$C_RST"
printf '\n'

exit "$rc"

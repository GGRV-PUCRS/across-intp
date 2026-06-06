#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# setup-host.sh -- Bootstrap an IntP testbed host.
#
# Auto-detects Ubuntu version and installs everything the bench script needs:
#
#   Ubuntu 22.04 (legacy / V0 baseline):
#       * pins HWE 6.5 kernel (latest pre-6.8, still has cqm_rmid for V0,
#         has full Sapphire Rapids uncore IMC support unlike kernel 5.10)
#       * SystemTap 5.2 + matching debuginfo via the ddebs archive
#       * intel-cmt-cat (RDT user-space)
#       * stress-ng / iperf3 / sysstat / perf / numactl / jq for the bench
#         script and its ground-truth side-channels
#       * docker + qemu + cloud-utils for the optional container/VM envs
#
#   Ubuntu 24.04 (modern / V0.1..V3.3):
#       * SystemTap + ddebs (V0.1 / V1 still need it)
#       * bpftrace (V3.1)
#       * clang / llvm / libbpf-dev / libelf-dev / zlib1g-dev / pahole (V3, V3.2,
#         V3.3 eBPF build deps)
#       * BTF availability check + kernel >= 5.8 check (cgroup v2 + cgroup_skb
#         for the cgroup-native endpoints V2.1 / V3.3)
#       * everything from the common set above
#
# In both profiles:
#       * mounts resctrl and persists it in /etc/fstab
#       * sets perf_event_paranoid=-1 and kptr_restrict=0 via sysctl.d
#       * builds v2 + v2.1 (cgroup-native) and, on 24.04, v3 + v3.2 + v3.3
#       * runs a smoke test for each installed profiler
#       * installs the analysis stack (numpy / scipy / pandas / matplotlib /
#         scikit-learn) for the post-campaign W4 stats and bench/plot/*
#
#   Optional (container / VM / cgroup benchmarking, both profiles, --optional):
#       * docker.io + lxc/lxd/incus (env=container / env=container-lxc)
#       * qemu-kvm + libvirt + virtinst + bridge-utils + iproute2 (env=vm,
#         host tap/bridge for VM netp) + libguestfs-tools (virt-customize)
#       * cgroup-tools (per-cgroup attribution helpers)
#
# This script is idempotent. The first pass on a fresh 22.04 install will
# pin HWE 6.5 and request a reboot; running it again after the reboot
# completes the build and self-tests.
#
# Usage:
#   sudo ./setup-host.sh                   # auto-detect profile
#   sudo ./setup-host.sh --profile legacy  # force 22.04 / V0 path
#   sudo ./setup-host.sh --profile modern  # force 24.04 / V0.1..V3 path
#   sudo ./setup-host.sh --no-optional     # skip docker / lxc / qemu / libvirt
#   sudo ./setup-host.sh --no-build        # skip make of v2/v2.1/v3/v3.2/v3.3
#   sudo ./setup-host.sh --no-debuginfo    # skip ddebs (faster, no SystemTap full-signal)
#   sudo ./setup-host.sh --with-scx        # also install rustup/scx for the
#                                          # future IADA/sched_ext leg (opt-in)
#   sudo ./setup-host.sh --with-k8s        # also install k3s (lightweight
#                                          # single-binary k8s: bundles kubectl,
#                                          # crictl, containerd) for the
#                                          # env=container-k8s leg (opt-in, heavy)
# -----------------------------------------------------------------------------

set -euo pipefail

PROFILE_OVERRIDE=""
INSTALL_OPTIONAL=1
DO_BUILD=1
DO_DEBUGINFO=1
INSTALL_SCX=0
INSTALL_K8S=0
NEEDS_REBOOT=0

# -----------------------------------------------------------------------------
# 1. CLI / preflight
# -----------------------------------------------------------------------------

log()  { printf '[%s] %s\n' "$(date +%H:%M:%S)" "$*"; }
warn() { log "WARN: $*" >&2; }
die()  { log "FATAL: $*" >&2; exit 1; }

while [ $# -gt 0 ]; do
    case "$1" in
        --profile)        PROFILE_OVERRIDE="$2"; shift 2 ;;
        --no-optional)    INSTALL_OPTIONAL=0; shift ;;
        --no-build)       DO_BUILD=0; shift ;;
        --no-debuginfo)   DO_DEBUGINFO=0; shift ;;
        --with-scx)       INSTALL_SCX=1; shift ;;
        --with-k8s)       INSTALL_K8S=1; shift ;;
        -h|--help)
            sed -n '2,/^# ---/p' "$0" | sed 's/^# \?//; /^---$/q'
            exit 0
            ;;
        *) die "unknown option: $1" ;;
    esac
done

[ "$(id -u)" = "0" ] || die "must run as root"

. /etc/os-release
case "${ID:-}" in
    ubuntu) ;;
    debian) warn "running on Debian -- this script is tuned for Ubuntu, but will try" ;;
    *) die "unsupported distro: ${ID:-unknown}" ;;
esac

CODENAME="${UBUNTU_CODENAME:-${VERSION_CODENAME:-}}"
case "${VERSION_ID:-}" in
    22.04) DETECTED_PROFILE="legacy" ;;
    24.04) DETECTED_PROFILE="modern" ;;
    *)     DETECTED_PROFILE="" ;;
esac

PROFILE="${PROFILE_OVERRIDE:-$DETECTED_PROFILE}"
[ -n "$PROFILE" ] || die "could not infer profile from VERSION_ID=$VERSION_ID; use --profile"

case "$PROFILE" in
    legacy|modern) ;;
    *) die "invalid --profile: $PROFILE (legacy | modern)" ;;
esac

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

log "host=$(hostname) os=$PRETTY_NAME kernel=$(uname -r) profile=$PROFILE"
log "repo=$REPO_ROOT"

# -----------------------------------------------------------------------------
# 2. Apt setup -- ddebs (matched debuginfo, SystemTap requires it)
# -----------------------------------------------------------------------------

setup_ddebs() {
    [ "$DO_DEBUGINFO" -eq 1 ] || { log "skipping debuginfo per --no-debuginfo"; return 0; }
    [ -n "$CODENAME" ] || { warn "no codename; skipping ddebs"; return 0; }

    local list=/etc/apt/sources.list.d/ddebs.list
    if [ ! -f "$list" ]; then
        log "configuring ddebs.ubuntu.com for $CODENAME"
        cat > "$list" <<EOF
deb http://ddebs.ubuntu.com/ ${CODENAME} main restricted universe multiverse
deb http://ddebs.ubuntu.com/ ${CODENAME}-updates main restricted universe multiverse
deb http://ddebs.ubuntu.com/ ${CODENAME}-proposed main restricted universe multiverse
EOF
    fi
    apt-get install -y ubuntu-dbgsym-keyring >/dev/null 2>&1 || \
        apt-key adv --keyserver keyserver.ubuntu.com --recv-keys C8CAB6595FDFF622 >/dev/null 2>&1 || \
        warn "could not install ddebs key -- ddeb installs will fail signature checks"
}

# -----------------------------------------------------------------------------
# 3. Kernel pinning -- only on 22.04, install latest 6.5 and hold
# -----------------------------------------------------------------------------

pin_hwe_65() {
    local cur kver_major kver_minor
    cur=$(uname -r)
    kver_major=$(echo "$cur" | cut -d. -f1)
    kver_minor=$(echo "$cur" | cut -d. -f2)

    if [ "$kver_major" -eq 6 ] && [ "$kver_minor" -eq 5 ]; then
        log "already running on a 6.5 kernel ($cur), no pin needed"
        return 0
    fi

    log "looking for the newest linux-image-6.5.* in apt"
    apt-get update -qq

    # Latest 6.5.x-NN-generic available in this archive snapshot.
    local latest
    latest=$(apt-cache search '^linux-image-6\.5\.[0-9]+-[0-9]+-generic$' \
                | awk '{print $1}' | sort -V | tail -1)
    if [ -z "$latest" ]; then
        warn "no 6.5 kernel in apt -- jammy archive may have moved past 6.5"
        warn "Check manually: 'apt list --all-versions linux-image-6.5*'"
        warn "If empty, fall back to manually downloading 6.5 .debs from"
        warn "https://launchpad.net/ubuntu/+source/linux-hwe-6.5/+publishinghistory"
        die "cannot proceed without 6.5 kernel for V0 baseline"
    fi
    local headers="linux-headers-${latest#linux-image-}"
    log "installing $latest + $headers"
    DEBIAN_FRONTEND=noninteractive apt-get install -y "$latest" "$headers"

    # Hold to prevent jammy-updates from rolling forward to 6.8+ (which would
    # break V0).
    apt-mark hold "$latest" "$headers" >/dev/null
    apt-mark hold linux-image-generic-hwe-22.04 linux-headers-generic-hwe-22.04 >/dev/null 2>&1 || true

    # Force GRUB to default to the 6.5 entry on next boot.
    local menuentry
    menuentry=$(grep -oP "menuentry '[^']*${latest#linux-image-}[^']*'" /boot/grub/grub.cfg \
                | head -1 | sed "s/menuentry '\(.*\)'/\1/")
    if [ -n "$menuentry" ]; then
        sed -i "s|^GRUB_DEFAULT=.*|GRUB_DEFAULT=\"Advanced options for Ubuntu>${menuentry}\"|" /etc/default/grub
        update-grub
    else
        warn "could not locate GRUB menuentry for $latest -- you may need to pick it manually on first boot"
    fi
    NEEDS_REBOOT=1
}

# -----------------------------------------------------------------------------
# 4. Common packages (both profiles)
# -----------------------------------------------------------------------------

install_common() {
    log "installing common packages"
    DEBIAN_FRONTEND=noninteractive apt-get install -y \
        build-essential make gcc git curl wget jq pkg-config \
        stress-ng iperf3 sysstat numactl bc \
        linux-tools-common "linux-tools-$(uname -r)" \
        ca-certificates lsb-release
}

# Analysis / statistics stack (post-campaign, both profiles). numpy + scipy
# power the W4 faithfulness stats (KS / Mann-Whitney / effect size); pandas,
# matplotlib and scikit-learn drive bench/plot/* (mirrors bench/plot/
# requirements.txt). Installed via apt_install_some so a host missing one distro
# package (e.g. python3-sklearn naming drift) does not abort the whole setup.
install_analysis() {
    log "installing analysis/statistics stack (numpy, scipy, pandas, matplotlib, scikit-learn)"
    apt_install_some "analysis" \
        python3-numpy python3-scipy python3-pandas python3-matplotlib python3-sklearn
}

install_matching_kernel_compiler() {
    local compiler_pkg
    compiler_pkg=$(grep -oE 'gcc-[0-9]+' /proc/version | head -1 || true)

    if [ -z "$compiler_pkg" ]; then
        log "could not infer kernel compiler from /proc/version; relying on default gcc"
        return 0
    fi

    if command -v "$compiler_pkg" >/dev/null 2>&1; then
        log "kernel-matching compiler already present ($compiler_pkg)"
        return 0
    fi

    log "installing kernel-matching compiler ($compiler_pkg) for SystemTap module builds"
    DEBIAN_FRONTEND=noninteractive apt-get install -y "$compiler_pkg" \
        || warn "failed to install $compiler_pkg -- SystemTap builds may fail"
}

# Warn (do not fail) if the running kernel is older than the cgroup-native floor
# the v2.1 / v3.3 endpoints need: 5.8 for cgroup v2 unified, perf cgroup-mode
# (PERF_FLAG_PID_CGROUP) and cgroup_skb / cgroup-BPF attach.
check_kernel_version() {
    local req_major="$1" req_minor="$2" why="$3"
    local cur kmaj kmin
    cur=$(uname -r)
    kmaj=$(echo "$cur" | cut -d. -f1)
    kmin=$(echo "$cur" | cut -d. -f2)
    if [ "$kmaj" -gt "$req_major" ] \
            || { [ "$kmaj" -eq "$req_major" ] && [ "$kmin" -ge "$req_minor" ]; }; then
        log "kernel $cur >= ${req_major}.${req_minor} ($why)"
        return 0
    fi
    warn "kernel $cur < ${req_major}.${req_minor} -- $why"
    return 1
}

# Install each named package independently so one unavailable package does NOT
# abort the rest: 'apt-get install a b c' fails wholesale if any single package
# has no installation candidate (e.g. lxd, which is snap-only on 24.04). That
# wholesale failure previously skipped docker.io and broke env=container.
apt_install_some() {
    local label="$1"; shift
    local pkg ok=0 miss=0
    for pkg in "$@"; do
        if DEBIAN_FRONTEND=noninteractive apt-get install -y "$pkg"; then
            ok=$((ok + 1))
        else
            warn "$label: '$pkg' unavailable or failed -- skipped"
            miss=$((miss + 1))
        fi
    done
    log "$label: installed $ok, skipped $miss"
}

install_optional() {
    [ "$INSTALL_OPTIONAL" -eq 1 ] || { log "skipping optional packages per --no-optional"; return 0; }

    # Container runtimes: docker.io for env=container; lxc/incus for
    # env=container-lxc (the cgroup-native v2.1/v3.3 path); podman (+ crun, its
    # OCI runtime) for env=container-podman -- daemonless and OCI-compatible, so
    # rootful 'podman run' places containers in host-visible cgroup v2 cgroups
    # the host-side profiler attributes exactly like docker. incus is the modern
    # successor to lxd; lxd is snap-only on 24.04 (no apt candidate). Installed
    # per-package so a missing one never blocks docker.io/lxc/incus/podman.
    log "installing container runtimes (docker / lxc / incus / lxd / podman)"
    apt_install_some "container runtime" docker.io lxc incus lxd podman crun

    # Initialize incus (storage pool + incusbr0 + default-profile root/eth0) so
    # the container-lxc env can actually launch instances. The harness prefers
    # incus over the LXD snap shim. Idempotent: a fresh incus has no storage pool
    # (which fails launches with "No root device could be found"); skip if one
    # already exists.
    if command -v incus >/dev/null 2>&1; then
        # Guard on the ACTUAL launch precondition -- the default profile having a
        # root disk device -- not merely a storage pool existing. A manually
        # created pool (or an interrupted init) can leave a pool with no root
        # device, which still fails 'incus launch' with "No root device".
        if incus profile device get default root pool >/dev/null 2>&1; then
            log "incus already initialized (default profile has a root device)"
        else
            log "initializing incus (incus admin init --auto)"
            incus admin init --auto \
                || warn "incus admin init failed -- container-lxc launches may fail ('No root device')"
        fi
    fi

    # VM stack: qemu/KVM + libvirt management + virt-install (virtinst) +
    # libguestfs-tools (virt-customize, used by bench/deploy/build-full-vm.sh) +
    # bridge-utils/iproute2 for the host tap/bridge that carries per-VM netp.
    log "installing VM stack (qemu-kvm / libvirt / virtinst / bridge tooling)"
    apt_install_some "VM stack" \
        qemu-system-x86 qemu-utils qemu-kvm cloud-image-utils \
        libvirt-daemon-system libvirt-clients virtinst libguestfs-tools \
        bridge-utils iproute2

    # cgroup v2 manipulation helpers used by the per-cgroup attribution and
    # validation scripts (bench/validate-attribution.sh, run-intp-bench.sh) and
    # libcap2-bin for capsh (preflight CAP_NET_ADMIN / CAP_BPF audit).
    log "installing cgroup / capability tooling (cgroup-tools / libcap2-bin)"
    apt_install_some "cgroup/capability tooling" cgroup-tools libcap2-bin

    install_scx_optional
}

install_scx_optional() {
    # Opt-in only (--with-scx). The future IADA/scheduler leg attaches a BPF
    # scheduler via sched_ext/scx; the measurement host may already have it.
    # Guarded behind a flag so the default bootstrap never pulls rustup/cargo.
    [ "$INSTALL_SCX" -eq 1 ] || { log "skipping sched_ext/scx (enable with --with-scx)"; return 0; }
    if [ ! -d /sys/kernel/sched_ext ]; then
        warn "/sys/kernel/sched_ext absent -- kernel lacks CONFIG_SCHED_CLASS_EXT; installing scx tooling anyway per --with-scx"
    fi
    log "installing sched_ext/scx scheduler tooling (--with-scx)"
    # scx_loader / scx schedulers ship as a distro package on 24.04+; fall back
    # to a warning if the archive does not carry it (build-from-source is the
    # operator's call for the IADA leg).
    DEBIAN_FRONTEND=noninteractive apt-get install -y \
        scx rustc cargo \
        || warn "scx package unavailable in this archive -- build scx from source for the IADA leg"
}

install_k8s_optional() {
    # Opt-in only (--with-k8s). The env=container-k8s leg runs the bench tenant
    # as a Kubernetes pod -- the DEEPEST cgroup nesting the v3.3 ancestor-cgid
    # gate + target_level is exercised against:
    #   kubepods.slice/kubepods-<qos>.slice/
    #     kubepods-<qos>-pod<uid>.slice/cri-containerd-<id>.scope
    # We back it with k3s: a lightweight single-binary Kubernetes that bundles
    # kubectl, crictl and an embedded containerd, so a one-line install gives the
    # whole control plane + node runtime without a separate kubeadm/containerd
    # dance. k3s is DAEMON-FUL (k3s.service runs the kubelet, containerd and the
    # control plane), hence heavy idle interference: it is opt-in, never pulled
    # by the default bootstrap, and host-services.sh quiesces it for non-k8s
    # campaigns. Guarded behind the flag like scx so the default leg stays clean.
    [ "$INSTALL_K8S" -eq 1 ] || { log "skipping k3s/kubernetes (enable with --with-k8s)"; return 0; }

    if command -v k3s >/dev/null 2>&1; then
        log "k3s already installed ($(k3s --version 2>/dev/null | head -1))"
    else
        log "installing k3s via the official installer (--with-k8s)"
        # The official get.k3s.io script installs the k3s binary + k3s.service
        # and brings up a single-node cluster. INSTALL_K3S_EXEC can pin/limit the
        # server role; left at the default 'server' here. Warn-on-failure, never
        # fatal: a missing k3s only disables the env=container-k8s leg, exactly
        # like a missing scx only disables the IADA leg.
        if curl -sfL https://get.k3s.io | INSTALL_K3S_EXEC="server" sh -; then
            log "k3s installed; it bundles kubectl (also via 'k3s kubectl'), crictl and containerd"
        else
            warn "k3s install failed -- env=container-k8s will be unavailable (re-run with network access)"
            return 0
        fi
    fi

    # The bench tenant pod runs an image carrying stress-ng. The default leg
    # mirrors the docker env: it uses a stock ubuntu image and apt-installs
    # stress-ng inside the pod command at run time, so no pre-baked image is
    # required. To avoid the per-run install, import the bench image into k3s's
    # embedded containerd:
    #   k3s ctr images import <bench-image>.tar      # from bench/setup/Dockerfile.bench
    # or pull the published image from ghcr.io (see bench/setup/publish-images.sh).
    log "  k3s tenant image: default uses stock ubuntu + on-the-fly stress-ng install"
    log "  (avoid per-run install: 'k3s ctr images import' the bench image, or pull from ghcr.io)"
}

# -----------------------------------------------------------------------------
# 5. Profile-specific package sets
# -----------------------------------------------------------------------------

install_legacy_stack() {
    log "installing V0 stack (SystemTap 5.2 on 22.04 + HWE 6.5)"
    DEBIAN_FRONTEND=noninteractive apt-get install -y \
        intel-cmt-cat python3 python3-pip

    install_systemtap_52

    if [ "$DO_DEBUGINFO" -eq 1 ]; then
        # Matching debuginfo for the kernel that's actually running. After
        # pin_hwe_65 + reboot, this picks up 6.5.
        local krel=$(uname -r)
        local pkg="linux-image-${krel}-dbgsym"
        log "trying to install $pkg"
        DEBIAN_FRONTEND=noninteractive apt-get install -y "$pkg" \
            || warn "$pkg not yet available -- re-run setup after the kernel pin reboot"
        # SystemTap ships a helper that resolves and pulls everything else.
        stap-prep || warn "stap-prep returned non-zero (often benign)"
    fi
}

install_systemtap_52() {
    local stap_version srcdir

    if command -v stap >/dev/null 2>&1; then
        stap_version=$(stap --version 2>/dev/null | sed -n 's/.*version \([0-9][0-9.]*\)\/.*/\1/p' | head -1)
        if [ -n "$stap_version" ] && dpkg --compare-versions "$stap_version" ge 5.2; then
            log "SystemTap $stap_version already installed"
            return 0
        fi
    fi

    log "building SystemTap 5.2 from source for kernel compatibility"
    DEBIAN_FRONTEND=noninteractive apt-get install -y \
        autoconf automake bison flex gettext pkg-config \
        libavahi-client-dev libdw-dev libelf-dev libnspr4-dev libnss3-dev \
        libreadline-dev libsqlite3-dev libssl-dev libxml2-dev \
        python3-dev python3-setuptools zlib1g-dev

    srcdir=/usr/local/src/systemtap
    if [ -d "$srcdir/.git" ]; then
        git -C "$srcdir" fetch --tags origin
    else
        rm -rf "$srcdir"
        git clone https://sourceware.org/git/systemtap.git "$srcdir"
    fi

    git -C "$srcdir" checkout release-5.2
    (
        cd "$srcdir"
        ./configure --prefix=/usr/local --disable-docs --disable-publican --enable-sqlite --enable-virt >/dev/null
        make -j"$(nproc)"
        make install
    )
    hash -r

    if ! command -v stap >/dev/null 2>&1; then
        die "SystemTap 5.2 install completed but stap is not on PATH"
    fi
    log "using $(command -v stap) ($(stap --version 2>&1 | head -1))"
}

install_modern_stack() {
    log "installing V0.1..V3.3 stack (SystemTap + bpftrace + libbpf/CO-RE)"
    # clang/llvm/libbpf-dev/libelf-dev/zlib1g-dev/pkg-config are the eBPF build
    # deps shared by V3, V3.2 and the cgroup-native V3.3; pahole feeds BTF.
    DEBIAN_FRONTEND=noninteractive apt-get install -y \
        systemtap systemtap-runtime libdw-dev gettext intel-cmt-cat \
        bpftrace python3 python3-pip python3-venv \
        clang llvm libbpf-dev libelf-dev zlib1g-dev pkg-config pahole \
        "linux-headers-$(uname -r)"

    if [ "$DO_DEBUGINFO" -eq 1 ]; then
        local krel=$(uname -r)
        DEBIAN_FRONTEND=noninteractive apt-get install -y "linux-image-${krel}-dbgsym" \
            || warn "kernel debuginfo unavailable -- V1 (SystemTap+resctrl) will fail probe compilation"
        stap-prep || warn "stap-prep returned non-zero"
    fi

    if [ ! -f /sys/kernel/btf/vmlinux ]; then
        warn "/sys/kernel/btf/vmlinux missing -- V3.1, V3, V3.2 and V3.3 will not load BPF programs"
    else
        log "BTF present at /sys/kernel/btf/vmlinux"
    fi

    # cgroup-native endpoints (V2.1 / V3.3) need kernel >= 5.8 for cgroup v2
    # unified + perf cgroup-mode + cgroup_skb attach.
    check_kernel_version 5 8 \
        "V2.1/V3.3 cgroup-native attribution needs cgroup v2 unified + perf cgroup-mode + cgroup_skb" \
        || true
    if grep -q '^cgroup2 /sys/fs/cgroup ' /proc/mounts 2>/dev/null \
            || [ -r /sys/fs/cgroup/cgroup.controllers ]; then
        log "cgroup v2 unified hierarchy mounted at /sys/fs/cgroup"
    else
        warn "cgroup v2 unified hierarchy NOT mounted at /sys/fs/cgroup -- V2.1/V3.3 per-cgroup attribution will be unavailable (boot with systemd.unified_cgroup_hierarchy=1)"
    fi
}

# -----------------------------------------------------------------------------
# 6. Kernel runtime config -- resctrl mount + sysctls
# -----------------------------------------------------------------------------

configure_kernel_runtime() {
    log "configuring kernel runtime (resctrl, sysctls)"

    if grep -q resctrl /proc/filesystems 2>/dev/null; then
        if ! mountpoint -q /sys/fs/resctrl; then
            mount -t resctrl resctrl /sys/fs/resctrl \
                && log "mounted resctrl at /sys/fs/resctrl" \
                || warn "failed to mount resctrl -- mbw / llcocc will be unavailable"
        fi
    else
        warn "resctrl filesystem not in /proc/filesystems -- check CONFIG_X86_CPU_RESCTRL"
    fi

    if ! grep -q '/sys/fs/resctrl' /etc/fstab; then
        echo 'resctrl /sys/fs/resctrl resctrl defaults 0 0' >> /etc/fstab
        log "persisted resctrl mount in /etc/fstab"
    fi

    cat > /etc/sysctl.d/99-intp-bench.conf <<'EOF'
# IntP bench: allow uncore IMC counters and kernel pointer reads needed by
# SystemTap and eBPF profilers. Only activates after `sysctl --system`.
kernel.perf_event_paranoid = -1
kernel.kptr_restrict = 0
EOF
    sysctl --system >/dev/null
    log "applied perf_event_paranoid=-1 and kptr_restrict=0"
}

# -----------------------------------------------------------------------------
# 7. Build variants
# -----------------------------------------------------------------------------

build_variants() {
    [ "$DO_BUILD" -eq 1 ] || { log "skipping build per --no-build"; return 0; }

    # v2 + v2.1 are C/procfs builds (gcc/make) available in both profiles. v2.1
    # is the cgroup-native sibling of v2 (same intp-hybrid CLI, kernel >= 5.8).
    if [ -d "$REPO_ROOT/variants/v2-c-abi" ]; then
        log "building v2 (hybrid procfs)"
        make -C "$REPO_ROOT/variants/v2-c-abi" || warn "v2 build failed"
    fi

    if [ -d "$REPO_ROOT/variants/v2.1-cgroup-native" ]; then
        log "building v2.1 (cgroup-native hybrid-C)"
        make -C "$REPO_ROOT/variants/v2.1-cgroup-native" || warn "v2.1 build failed"
    fi

    # eBPF/CO-RE builds (clang/libbpf) -- modern profile only.
    if [ "$PROFILE" = "modern" ] && [ -d "$REPO_ROOT/variants/v3-ebpf-ring" ]; then
        log "building v3 (eBPF/CO-RE ring-buffer)"
        make -C "$REPO_ROOT/variants/v3-ebpf-ring" || warn "v3 build failed"
    fi

    if [ "$PROFILE" = "modern" ] && [ -d "$REPO_ROOT/variants/v3.2-ebpf-core" ]; then
        log "building v3.2 (eBPF/CO-RE in-kernel aggregation)"
        make -C "$REPO_ROOT/variants/v3.2-ebpf-core" || warn "v3.2 build failed"
    fi

    if [ "$PROFILE" = "modern" ] && [ -d "$REPO_ROOT/variants/v3.3-ebpf-cgroup" ]; then
        log "building v3.3 (eBPF cgroup-native)"
        make -C "$REPO_ROOT/variants/v3.3-ebpf-cgroup" || warn "v3.3 build failed"
    fi
}

# -----------------------------------------------------------------------------
# 8. Self-tests -- one per profiler we expect to work in this profile
# -----------------------------------------------------------------------------

selftest() {
    log "self-tests"

    if command -v stap >/dev/null 2>&1; then
        if timeout 30 stap -e 'probe begin { log("stap_ok"); exit() }' 2>/dev/null \
                | grep -q stap_ok; then
            log "  stap        OK"
        else
            warn "  stap        FAIL (missing gcc-X, headers, or module build mismatch?)"
        fi
    fi

    if [ -x "$REPO_ROOT/variants/v2-c-abi/intp-hybrid" ]; then
        if "$REPO_ROOT/variants/v2-c-abi/intp-hybrid" --list-backends >/dev/null 2>&1; then
            log "  v2          OK ($(${REPO_ROOT}/variants/v2-c-abi/intp-hybrid --list-backends 2>&1 | head -1))"
        else
            warn "  v2          FAIL (--list-backends returned non-zero)"
        fi
    fi

    # v2.1 (cgroup-native, intp-hybrid CLI like v2) -- both profiles.
    if [ -x "$REPO_ROOT/variants/v2.1-cgroup-native/intp-hybrid" ]; then
        if "$REPO_ROOT/variants/v2.1-cgroup-native/intp-hybrid" --list-backends >/dev/null 2>&1; then
            log "  v2.1        OK ($("${REPO_ROOT}"/variants/v2.1-cgroup-native/intp-hybrid --list-backends 2>&1 | head -1))"
        else
            warn "  v2.1        FAIL (--list-backends returned non-zero)"
        fi
    fi

    if [ "$PROFILE" = "modern" ]; then
        if command -v bpftrace >/dev/null 2>&1; then
            log "  bpftrace    OK ($(bpftrace --version 2>&1 | head -1))"
        else
            warn "  bpftrace    missing"
        fi
        if [ -x "$REPO_ROOT/variants/v3-ebpf-ring/intp-ebpf" ]; then
            if "$REPO_ROOT/variants/v3-ebpf-ring/intp-ebpf" --list-capabilities >/dev/null 2>&1; then
                log "  v3          OK"
            else
                warn "  v3          FAIL"
            fi
        fi
        if [ -x "$REPO_ROOT/variants/v3.2-ebpf-core/intp-eBPF-CORE" ]; then
            if "$REPO_ROOT/variants/v3.2-ebpf-core/intp-eBPF-CORE" --list-capabilities >/dev/null 2>&1; then
                log "  v3.2        OK"
            else
                warn "  v3.2        FAIL"
            fi
        fi
        if [ -x "$REPO_ROOT/variants/v3.3-ebpf-cgroup/intp-ebpf-cgroup" ]; then
            if "$REPO_ROOT/variants/v3.3-ebpf-cgroup/intp-ebpf-cgroup" --list-capabilities >/dev/null 2>&1; then
                log "  v3.3        OK"
            else
                warn "  v3.3        FAIL"
            fi
        fi
    fi

    log "  resctrl     $([ -d /sys/fs/resctrl/info/L3_MON ] && echo OK || echo missing)"
    log "  BTF         $([ -f /sys/kernel/btf/vmlinux ] && echo OK || echo missing)"
    log "  paranoid    $(cat /proc/sys/kernel/perf_event_paranoid)"
    # cgroup v2 unified + per-cgroup controller stat files (V2.1 / V3.3 floor).
    log "  cgroup_v2   $({ grep -q '^cgroup2 /sys/fs/cgroup ' /proc/mounts 2>/dev/null || [ -r /sys/fs/cgroup/cgroup.controllers ]; } && echo OK || echo missing)"
    log "  cgv2_cpu    $([ -f /sys/fs/cgroup/cpu.stat ] && echo OK || echo missing)"
    log "  cgv2_io     $([ -f /sys/fs/cgroup/io.stat ] && echo OK || echo missing)"
    log "  capsh       $(command -v capsh >/dev/null 2>&1 && echo OK || echo missing)"
    # Container runtimes (env=container / -lxc / -podman). podman is daemonless;
    # rootful 'podman run' uses host-visible cgroup v2 like docker.
    log "  docker      $(command -v docker >/dev/null 2>&1 && echo OK || echo missing)"
    log "  podman      $(command -v podman >/dev/null 2>&1 && echo OK || echo missing)"
    # k3s (env=container-k8s) -- opt-in (--with-k8s); 'missing' is expected on a
    # default bootstrap. kubectl is also reachable as 'k3s kubectl'.
    log "  k3s         $(command -v k3s >/dev/null 2>&1 && echo OK || echo missing)"
}

# -----------------------------------------------------------------------------
# 9. Driver
# -----------------------------------------------------------------------------

main() {
    apt-get update -qq

    setup_ddebs

    if [ "$PROFILE" = "legacy" ]; then
        pin_hwe_65
        if [ "$NEEDS_REBOOT" -eq 1 ]; then
            log ""
            log "==============================================================="
            log "HWE 6.5 kernel installed and held. Reboot, then re-run this"
            log "script to install SystemTap, build the variants, and self-test."
            log ""
            log "    reboot"
            log "    sudo $0 --profile legacy"
            log "==============================================================="
            exit 0
        fi
    fi

    install_common
    install_analysis
    install_matching_kernel_compiler
    install_optional
    # k3s is its own opt-in leg (--with-k8s), invoked independently of
    # install_optional so --no-optional never swallows the flag -- same wiring
    # rationale as scx (which lives inside install_optional but is itself a
    # standalone --with-scx guard).
    install_k8s_optional

    if [ "$PROFILE" = "legacy" ]; then
        install_legacy_stack
    else
        install_modern_stack
    fi

    configure_kernel_runtime
    build_variants
    selftest

    log ""
    log "Setup complete. Next:"
    log "    sudo $REPO_ROOT/bench/run-intp-bench.sh --variants $([ "$PROFILE" = "legacy" ] && echo "v0" || echo "v0.1,v1,v2,v2.1,v3.1,v3,v3.2,v3.3")"
    if [ "$PROFILE" = "modern" ]; then
        log "    # container (cgroup-native v2.1/v3.3):  sudo bash $REPO_ROOT/containerun24.sh --variants v2.1,v3.3"
        log "    # VM tenant (env=vm):  see bench/run-intp-bench.sh --env vm / run-big-batch.sh BENCH_ENVS=vm"
    fi
}

main

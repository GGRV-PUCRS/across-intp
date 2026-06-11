#!/usr/bin/env bash
# build-bench-vm.sh — build a LEAN bench-tenant qcow2 for the `vm` env by booting
# the Ubuntu 24.04 cloud image under qemu and letting cloud-init install the bench
# deps on first boot, then powering the guest off.
#
# Why qemu-boot instead of libguestfs virt-customize (DECISIONS-container C23):
# on Ubuntu 24.04 the libguestfs 1.52 appliance has no working OUTBOUND network on
# some hosts (passt egress + the systemd-resolved 127.0.0.53 stub the appliance
# inherits), so `virt-customize --install` cannot fetch packages. A normal qemu
# boot uses the guest's own user-mode (SLIRP) network — DNS via 10.0.2.3, full
# NAT — which works, and cloud-init installs the deps. cloud-init then powers the
# guest off (power_state) so the build is unattended; we verify the result
# read-only with virt-cat (which only needs the appliance to boot, now that passt
# is fixed — it does not need outbound network).
#
# Usage:
#   sudo bash bench/setup/build-bench-vm.sh
#   OUT=/path/to.qcow2 sudo bash bench/setup/build-bench-vm.sh
#   WITH_SUITES=1 sudo bash bench/setup/build-bench-vm.sh   # Tier-B/C suites image
#
# Env knobs:
#   OUT            destination qcow2 (default /var/lib/intp/intp-bench-vm.qcow2,
#                  or intp-bench-vm-suites.qcow2 under WITH_SUITES=1)
#   BASE_QCOW2     reuse this base instead of downloading (default /var/lib/intp/ubuntu24.qcow2)
#   BASE_URL       cloud image URL (default: Noble current)
#   IMG_SIZE       expand image to this size (default 12G; 64G under WITH_SUITES=1 --
#                  qcow2 stays sparse, content is ~10-15 GB)
#   VM_MEM         build VM memory in MiB (default 4096; 8192 under WITH_SUITES=1)
#   VM_CPUS        build VM vCPUs (default 4)
#   BUILD_TIMEOUT  seconds to wait for cloud-init install + poweroff
#                  (default 1800; 5400 under WITH_SUITES=1 -- multi-GB pulls)
#   WITH_SUITES    1 = ALSO bake docker + compose + the Tier-B/C suite stack
#                  (C32/C33): the bench/workloads/compose/ driver dirs at
#                  /opt/intp-suites, the DeathStarBench clone + wrk2 + images,
#                  the CloudSuite images + movielens volume. The 14 GB
#                  web-search index is SKIPPED (guest profile) -- app20 in
#                  vm-guest needs an image built with the cloudsuite installer
#                  run --with-websearch-index in-guest.
#   GUEST_SOLR_HEAP / GUEST_SPARK_MEM
#                  sizing baked into the in-guest driver .env files
#                  (default 4g/3g smoke-grade; use 12g/6g for the testbed
#                  full-size guest)
#
# Requires: qemu-system-x86_64 + KVM, qemu-img, cloud-localds (apt:
# qemu-system-x86 qemu-utils cloud-image-utils). virt-cat (libguestfs-tools) is
# optional, used only for post-build verification.

set -u -o pipefail

WITH_SUITES="${WITH_SUITES:-0}"
if [ "$WITH_SUITES" = "1" ]; then
    OUT="${OUT:-/var/lib/intp/intp-bench-vm-suites.qcow2}"
    IMG_SIZE="${IMG_SIZE:-64G}"
    VM_MEM="${VM_MEM:-8192}"
    BUILD_TIMEOUT="${BUILD_TIMEOUT:-5400}"
else
    OUT="${OUT:-/var/lib/intp/intp-bench-vm.qcow2}"
    IMG_SIZE="${IMG_SIZE:-12G}"
    VM_MEM="${VM_MEM:-4096}"
    BUILD_TIMEOUT="${BUILD_TIMEOUT:-1800}"
fi
BASE_QCOW2="${BASE_QCOW2:-/var/lib/intp/ubuntu24.qcow2}"
BASE_URL="${BASE_URL:-https://cloud-images.ubuntu.com/noble/current/noble-server-cloudimg-amd64.img}"
VM_CPUS="${VM_CPUS:-4}"
GUEST_SOLR_HEAP="${GUEST_SOLR_HEAP:-4g}"
GUEST_SPARK_MEM="${GUEST_SPARK_MEM:-3g}"

log() { printf '[build-bench-vm] %s\n' "$*"; }
die() { log "FATAL: $*"; exit 1; }

[ "$(id -u)" = "0" ] || die "run as root (qemu/kvm + virt-cat need it)"
for cmd in qemu-system-x86_64 qemu-img cloud-localds; do
    command -v "$cmd" >/dev/null 2>&1 \
        || die "missing: $cmd (apt: qemu-system-x86 qemu-utils cloud-image-utils)"
done
[ -e /dev/kvm ] || log "WARNING: /dev/kvm absent — build will run without KVM (slow)"

HERE="$(cd "$(dirname "$0")" && pwd)"
# The package list below mirrors bench/setup/vm-bench.cloud-init.yaml and
# bench/setup/Dockerfile.bench — keep the three in sync.
CLOUD_INIT="$HERE/vm-bench.cloud-init.yaml"
[ -f "$CLOUD_INIT" ] || log "note: $CLOUD_INIT not found (informational; packages are inlined below)"

mkdir -p "$(dirname "$OUT")"
WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT

# --- base image -----------------------------------------------------------
if [ -f "$BASE_QCOW2" ]; then
    log "reusing base $BASE_QCOW2 (skip download)"
else
    command -v curl >/dev/null 2>&1 || die "missing curl (needed to download base)"
    log "downloading $BASE_URL -> $BASE_QCOW2"
    curl -fsSL -o "$BASE_QCOW2" "$BASE_URL" || die "download failed"
fi
[ -f "$OUT" ] && { log "backing up existing $OUT -> $OUT.bak"; mv -f "$OUT" "$OUT.bak"; }
log "copy + resize base -> $OUT ($IMG_SIZE)"
cp --reflink=auto "$BASE_QCOW2" "$OUT"
qemu-img resize "$OUT" "$IMG_SIZE" >/dev/null

# --- cloud-init seed (install pkgs on first boot, mark, power off) --------
# Quoted heredoc: nothing is expanded by THIS shell; the $(...) in the marker
# script are evaluated by the guest at runcmd time.
cat > "$WORK/user-data" <<'CIEOF'
#cloud-config
package_update: true
package_upgrade: false
packages:
  - linux-generic-hwe-24.04
  - stress-ng
  - iperf3
  - sysstat
  - numactl
  - bc
  - procps
  - iproute2
  - git
  - curl
write_files:
  - path: /usr/local/bin/intp-bench-mark.sh
    permissions: '0755'
    content: |
      #!/bin/sh
      # cloud-init does NOT abort the boot on a failed apt, so verify EVERY bench
      # dep here and emit PKGS_OK=1 only if all are present; the host-side verify
      # gates on PKGS_OK. Also echo the marker to /dev/console so a host without
      # virt-cat can read it from the serial log.
      mkdir -p /var/lib /etc/intp
      ok=1
      {
        echo "built=$(date -u +%FT%TZ)"
        echo "kernel_pkg=$(dpkg -l linux-generic-hwe-24.04 2>/dev/null | awk '/^ii/{print $3}')"
        dpkg -s linux-generic-hwe-24.04 >/dev/null 2>&1 || { echo "kernel=MISSING"; ok=0; }
        for b in stress-ng iperf3 iostat numactl bc ip git curl; do
          if command -v "$b" >/dev/null 2>&1; then echo "bin_$b=ok"; else echo "bin_$b=MISSING"; ok=0; fi
        done
        echo "PKGS_OK=$ok"
      } > /var/lib/intp-bench-ready
      { echo INTP_BENCH_MARK_BEGIN; cat /var/lib/intp-bench-ready; echo INTP_BENCH_MARK_END; } > /dev/console 2>/dev/null || true
  - path: /etc/intp/build-method
    content: |
      qemu-boot + cloud-init (bench/setup/build-bench-vm.sh)
runcmd:
  - /usr/local/bin/intp-bench-mark.sh
power_state:
  mode: poweroff
  timeout: 120
  condition: true
CIEOF

# --- WITH_SUITES: a separate, fuller user-data (C32/C33) -------------------
# Bakes docker + compose + the Tier-B/C suite stack so the vm-guest leg can run
# COMPOSE/REDIS workloads without boot-time network installs. The driver dirs
# and the two suite installers travel as a base64 tar in the seed (they are a
# few tens of KB); the heavy content (DSB clone, images) is pulled in-guest by
# the installers over SLIRP NAT. Keep the base package list in sync with the
# lean heredoc above.
if [ "$WITH_SUITES" = "1" ]; then
    REPO_ROOT="$(cd "$HERE/../.." && pwd)"
    [ -d "$REPO_ROOT/bench/workloads/compose" ] || die "WITH_SUITES: $REPO_ROOT/bench/workloads/compose missing"
    PAYLOAD_B64="$(tar czf - -C "$REPO_ROOT" \
        bench/workloads/compose \
        bench/setup/setup-dsb-workload.sh \
        bench/setup/setup-cloudsuite-workload.sh | base64 -w0)" \
        || die "WITH_SUITES: payload tar failed"

    cat > "$WORK/user-data" <<CIEOF
#cloud-config
package_update: true
package_upgrade: false
packages:
  - linux-generic-hwe-24.04
  - stress-ng
  - iperf3
  - sysstat
  - numactl
  - bc
  - procps
  - iproute2
  - git
  - curl
  - docker.io
  - docker-compose-v2
  - redis-server
  - redis-tools
  - python3-aiohttp
  - lua-socket
  - build-essential
  - libssl-dev
  - zlib1g-dev
write_files:
  - path: /opt/intp-payload.tgz
    encoding: b64
    content: $PAYLOAD_B64
  - path: /usr/local/bin/intp-suites-provision.sh
    permissions: '0755'
    content: |
      #!/bin/bash
      # Provision the Tier-B/C suites in-guest: unpack the driver payload, run
      # both installers (they pull images / clone DSB / build wrk2 / size the
      # .env files), then place the runtime driver tree at /opt/intp-suites.
      set -u
      ok=1
      mkdir -p /opt/intp-stage /opt/intp-suites
      tar xzf /opt/intp-payload.tgz -C /opt/intp-stage || ok=0
      systemctl enable --now docker >/dev/null 2>&1 || ok=0
      systemctl disable --now redis-server >/dev/null 2>&1 || true
      bash /opt/intp-stage/bench/setup/setup-dsb-workload.sh --guest \\
          > /var/log/intp-suites-dsb.log 2>&1 || ok=0
      bash /opt/intp-stage/bench/setup/setup-cloudsuite-workload.sh --guest \\
          --solr-heap "$GUEST_SOLR_HEAP" --spark-mem "$GUEST_SPARK_MEM" \\
          > /var/log/intp-suites-cloudsuite.log 2>&1 || ok=0
      cp -a /opt/intp-stage/bench/workloads/compose/. /opt/intp-suites/ || ok=0
      docker compose version >/dev/null 2>&1 || ok=0
      echo "SUITES_OK=\$ok" >> /var/lib/intp-bench-ready
      { echo INTP_SUITES_MARK; tail -1 /var/lib/intp-bench-ready; } > /dev/console 2>/dev/null || true
  - path: /usr/local/bin/intp-bench-mark.sh
    permissions: '0755'
    content: |
      #!/bin/sh
      # cloud-init does NOT abort the boot on a failed apt, so verify EVERY bench
      # dep here and emit PKGS_OK=1 only if all are present; the host-side verify
      # gates on PKGS_OK. Also echo the marker to /dev/console so a host without
      # virt-cat can read it from the serial log.
      mkdir -p /var/lib /etc/intp
      ok=1
      {
        echo "built=\$(date -u +%FT%TZ)"
        echo "kernel_pkg=\$(dpkg -l linux-generic-hwe-24.04 2>/dev/null | awk '/^ii/{print \$3}')"
        dpkg -s linux-generic-hwe-24.04 >/dev/null 2>&1 || { echo "kernel=MISSING"; ok=0; }
        for b in stress-ng iperf3 iostat numactl bc ip git curl docker redis-server; do
          if command -v "\$b" >/dev/null 2>&1; then echo "bin_\$b=ok"; else echo "bin_\$b=MISSING"; ok=0; fi
        done
        echo "PKGS_OK=\$ok"
      } > /var/lib/intp-bench-ready
      { echo INTP_BENCH_MARK_BEGIN; cat /var/lib/intp-bench-ready; echo INTP_BENCH_MARK_END; } > /dev/console 2>/dev/null || true
  - path: /etc/intp/build-method
    content: |
      qemu-boot + cloud-init WITH_SUITES (bench/setup/build-bench-vm.sh)
runcmd:
  - /usr/local/bin/intp-bench-mark.sh
  - /usr/local/bin/intp-suites-provision.sh
power_state:
  mode: poweroff
  timeout: 120
  condition: true
CIEOF
fi

cat > "$WORK/meta-data" <<'MDEOF'
instance-id: intp-bench-build
local-hostname: intp-bench
MDEOF

SEED="${OUT%.qcow2}.seed.iso"
cloud-localds "$SEED" "$WORK/user-data" "$WORK/meta-data" || die "cloud-localds failed"
log "cloud-init seed: $SEED"

# --- boot the build VM (cloud-init installs deps, then powers off) --------
CONSOLE="${OUT%.qcow2}.build-console.log"
KVM_ARGS=(); [ -e /dev/kvm ] && KVM_ARGS=(-enable-kvm -cpu host)
log "booting build VM (mem=${VM_MEM}M cpus=${VM_CPUS}, timeout=${BUILD_TIMEOUT}s); console -> $CONSOLE"
qemu-system-x86_64 \
    "${KVM_ARGS[@]+"${KVM_ARGS[@]}"}" -m "$VM_MEM" -smp "$VM_CPUS" \
    -drive file="$OUT",if=virtio,format=qcow2 \
    -netdev user,id=n0 -device virtio-net-pci,netdev=n0 \
    -cdrom "$SEED" \
    -display none -serial "file:$CONSOLE" \
    -no-reboot &
QPID=$!

elapsed=0
while kill -0 "$QPID" 2>/dev/null; do
    if [ "$elapsed" -ge "$BUILD_TIMEOUT" ]; then
        kill "$QPID" 2>/dev/null; sleep 2; kill -9 "$QPID" 2>/dev/null
        die "build timed out after ${BUILD_TIMEOUT}s (cloud-init never powered off) — see $CONSOLE"
    fi
    sleep 10; elapsed=$((elapsed + 10))
done
log "build VM powered off after ~${elapsed}s"

# A real build boots, installs, marks, then powers off (~60s+). An exit far
# faster means qemu failed to boot (bad KVM/args), not a clean cloud-init
# poweroff -- do not treat it as success.
if [ "$elapsed" -lt 25 ]; then
    log "console tail:"; tail -20 "$CONSOLE" 2>/dev/null | sed 's/^/    /'
    die "build VM exited after only ${elapsed}s -- likely failed to boot (KVM/args), not a clean poweroff; see $CONSOLE"
fi

# --- verify: gate on the in-guest PKGS_OK=1 marker (ALL bench deps + HWE kernel).
# cloud-init does NOT fail the boot on a bad apt, so this marker is the only
# signal of a half-built image. Prefer virt-cat (reads the image); fall back to
# the serial console (the marker script echoed itself there) when virt-cat is
# absent -- never declare success with zero verification.
MARK=""
if command -v virt-cat >/dev/null 2>&1; then
    MARK="$(virt-cat -a "$OUT" /var/lib/intp-bench-ready 2>/dev/null || true)"
    [ -n "$MARK" ] || die "verify failed: marker absent in $OUT (cloud-init never completed?); see $CONSOLE"
else
    log "virt-cat unavailable -- verifying via the serial-console marker instead"
    MARK="$(sed -n '/INTP_BENCH_MARK_BEGIN/,/INTP_BENCH_MARK_END/p' "$CONSOLE" 2>/dev/null | grep -v 'INTP_BENCH_MARK_')"
    [ -n "$MARK" ] || die "verify failed: no build marker on the console ($CONSOLE) -- cloud-init did not complete"
fi
log "in-image marker:"; printf '%s\n' "$MARK" | sed 's/^/    /'
printf '%s\n' "$MARK" | grep -qx "PKGS_OK=1" \
    || die "verify failed: not all bench deps/kernel installed (PKGS_OK!=1) in $OUT -- see marker above and $CONSOLE"
log "verified: all bench deps + HWE kernel present (PKGS_OK=1)"
if [ "$WITH_SUITES" = "1" ]; then
    # The suites provisioner appends its own gate; a PKGS_OK image without
    # SUITES_OK=1 would silently fail every COMPOSE vm-guest rep later.
    printf '%s\n' "$MARK" | grep -qx "SUITES_OK=1" || {
        # virt-cat path re-reads the marker; console fallback sees the echo
        MARK2="$(virt-cat -a "$OUT" /var/lib/intp-bench-ready 2>/dev/null || true)"
        printf '%s\n' "$MARK2" | grep -qx "SUITES_OK=1" \
            || die "verify failed: SUITES_OK!=1 in $OUT (see /var/log/intp-suites-*.log in the image and $CONSOLE)"
    }
    log "verified: Tier-B/C suite stack baked (SUITES_OK=1)"
fi

log "build complete: $OUT ($(du -h "$OUT" | cut -f1))"
[ -f "$SEED" ] && log "seed: $SEED"
log ""
log "Next steps:"
log "  1. point INTP_BENCH_VM_IMAGE to $OUT"
log "  2. smoke: INTP_BENCH_VM_IMAGE=$OUT \\"
log "       sudo bash bench/run-intp-bench.sh --env vm --variants v2.1,v3.3 \\"
log "         --workloads app10_search --reps 1 --duration 10"
log "  3. publish as a repo package: bash bench/setup/publish-images.sh --vm --publish"

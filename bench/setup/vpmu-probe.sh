#!/bin/bash
# vpmu-probe.sh — diagnose which (perf event x scope) combinations count inside
# the vm-guest. Boots the bench qcow2, runs a cache-heavy stress-ng inside a
# cgroup, then perf-stats the LLC events in system-wide, per-task, and
# cgroup-mode (-G) scopes for both the architectural (cache-references/misses)
# and model-specific (LLC-loads/LLC-load-misses) encodings. One-off probe.
#
# Usage: bash vpmu-probe.sh '[-cpu flag]'   (default: host,pmu=on)
set -u
IMG="${INTP_BENCH_VM_IMAGE:-/var/lib/intp/intp-bench-vm.qcow2}"
CPUFLAG="${1:-host,pmu=on}"
[ -f "$IMG" ] || { echo "no image: $IMG"; exit 2; }
td=$(mktemp -d -t vpmu-XXXXXX)
trap 'kill ${qpid:-0} 2>/dev/null; wait ${qpid:-0} 2>/dev/null; rm -rf "$td"' EXIT
ssh-keygen -t ed25519 -N '' -q -f "$td/key"
pub=$(cat "$td/key.pub")
cat > "$td/user-data" <<UD
#cloud-config
users:
  - name: intp
    ssh_authorized_keys: ["$pub"]
    sudo: ALL=(ALL) NOPASSWD:ALL
    shell: /bin/bash
    groups: [sudo]
runcmd:
  - [ systemctl, enable, --now, ssh ]
UD
# Unique instance-id so cloud-init re-applies our ephemeral key on every run
# (a fixed id makes cloud-init skip user-data on the 2nd+ boot).
iid="vpmu-$(basename "$td")"
printf 'instance-id: %s\nlocal-hostname: vpmu\n' "$iid" > "$td/meta-data"
cloud-localds "$td/seed.iso" "$td/user-data" "$td/meta-data" || { echo "cloud-localds failed"; exit 3; }
# Throwaway overlay so the probe never mutates the shared backing image.
qemu-img create -q -f qcow2 -b "$IMG" -F qcow2 "$td/overlay.qcow2" 2>/dev/null || { echo "qemu-img overlay failed"; exit 3; }
port=12290
echo "[probe] booting -cpu $CPUFLAG (overlay on $IMG, iid=$iid) ..."
qemu-system-x86_64 -enable-kvm -nographic -name vpmu \
  -cpu "$CPUFLAG" -smp 4 -m 4G \
  -drive "file=$td/overlay.qcow2,if=virtio,format=qcow2" \
  -drive "file=$td/seed.iso,if=virtio,format=raw" \
  -netdev user,id=n0,hostfwd=tcp::${port}-:22 -device virtio-net-pci,netdev=n0 \
  > "$td/qemu.log" 2>&1 &
qpid=$!
SSH="ssh -o BatchMode=yes -o ConnectTimeout=3 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i $td/key -p $port intp@127.0.0.1"
ok=0; for i in $(seq 1 100); do $SSH true >/dev/null 2>&1 && { ok=1; break; }; sleep 2; done
[ "$ok" = 1 ] || { echo "[probe] guest SSH never came up"; tail -5 "$td/qemu.log"; exit 4; }
echo "=== guest PMU (dmesg) ==="; $SSH 'sudo dmesg 2>/dev/null | grep -iE "Intel PMU|generic registers|fixed-purpose|perfmon"'
# Launch a cache-heavy workload inside a dedicated cgroup (mirrors the orchestrator).
$SSH 'sudo mkdir -p /sys/fs/cgroup/pcg 2>/dev/null
      sudo sh -c "echo \$\$ > /sys/fs/cgroup/pcg/cgroup.procs; exec stress-ng --cache 3 --cache-level 3 --aggressive --cpu 1 --timeout 40s" >/tmp/wl.log 2>&1 &
      sleep 2; echo started'
WLPID=$($SSH 'pgrep -n stress-ng' 2>/dev/null)
echo "=== guest WLPID=$WLPID; its cgroup ==="; $SSH "cat /proc/$WLPID/cgroup 2>/dev/null"
echo "=== [A] system-wide architectural ==="; $SSH 'sudo perf stat -a -e cache-references,cache-misses -- sleep 3' 2>&1 | grep -iE "cache-"
echo "=== [B] per-task architectural (pid=$WLPID) ==="; $SSH "sudo perf stat -e cache-references,cache-misses -p $WLPID -- sleep 3" 2>&1 | grep -iE "cache-"
echo "=== [C] cgroup-mode architectural (-G pcg) ==="; $SSH 'sudo perf stat -a -e cache-references,cache-misses -G pcg -- sleep 3' 2>&1 | grep -iE "cache-"
echo "=== [D] per-task LL (pid=$WLPID) ==="; $SSH "sudo perf stat -e LLC-loads,LLC-load-misses -p $WLPID -- sleep 3" 2>&1 | grep -iE "LLC"
echo "=== [E] cgroup-mode LL (-G pcg) ==="; $SSH 'sudo perf stat -a -e LLC-loads,LLC-load-misses -G pcg -- sleep 3' 2>&1 | grep -iE "LLC"
echo "[probe] done."

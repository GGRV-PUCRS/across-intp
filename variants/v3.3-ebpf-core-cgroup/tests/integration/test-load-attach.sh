#!/bin/bash
# test-load-attach.sh -- smoke test: launch intp-ebpf-core-cgroup, verify programs
# load and attach, let it run briefly, check no programs leak, confirm
# TSV output is well-formed.

set -eu

BIN=${BIN:-./intp-ebpf-core-cgroup}
DURATION=${DURATION:-3}

if [ ! -x "$BIN" ]; then
    echo "ERROR: $BIN not built -- run 'make' first"
    exit 1
fi
if [ "$(id -u)" -ne 0 ]; then
    echo "ERROR: must run as root (BPF + perf_event need privileges)"
    exit 1
fi

# Leak check counts intp's OWN programs, never the global total (D12):
# on a busy multi-tenant host the system-wide BPF program count churns
# continuously (containers, systemd, qemu), so a global pre/post delta is
# not attributable to this profiler -- it false-failed on the RDT testbed
# (pre=111 post=115) while teardown was provably clean (own programs went
# 0 -> N -> 0). Names from intp_agg.bpf.c, truncated to the kernel's
# 15-char BPF_OBJ_NAME_LEN where longer.
INTP_PROG_RE='cg_skb_egress|cg_skb_ingress|tp_net_dev_xmit|tp_netif_receiv|tp_block_rq|tp_block_bio|tp_sched_switch|tp_sched_wakeup|tp_schedlat|tp_softirq_|perf_llc_'

count_intp_progs() {
    bpftool prog show 2>/dev/null | grep -cE "name ($INTP_PROG_RE)" |
        tr -d '[:space:]'
}

pre_count="$(count_intp_progs)"
pre_count="${pre_count:-0}"
echo "pre-run intp BPF programs: $pre_count"

out=$(mktemp)
trap 'rm -f "$out"' EXIT

echo "running $BIN --duration $DURATION --interval 1 --no-resctrl --no-perf-events"
timeout $((DURATION + 5)) "$BIN" --duration "$DURATION" --interval 1 \
    --no-resctrl --no-perf-events > "$out" 2>&1 || true

# BPF teardown is ASYNCHRONOUS to process exit: the skeleton destroy drops
# every link and refcount, but the kernel reaps tp_btf programs (observed:
# tp_schedlat) after an RCU grace period, so an immediate post-count can
# catch one for < 0.5s. Poll until the programs drain to the baseline;
# only a count that never settles within the timeout is a real leak.
settle_deadline=$(($(date +%s) + 5))
while :; do
    post_count="$(count_intp_progs)"
    post_count="${post_count:-0}"
    [ "$post_count" -le "$pre_count" ] && break
    [ "$(date +%s)" -ge "$settle_deadline" ] && break
    sleep 0.25
done
echo "post-run intp BPF programs: $post_count"

if [ "$post_count" -gt "$pre_count" ]; then
    echo "FAIL: leaked BPF programs (pre=$pre_count post=$post_count, did not drain in 5s)"
    bpftool prog show 2>&1 | grep -E "name ($INTP_PROG_RE)" | head -20
    exit 1
fi

lines="$(awk -F '\t' '/^[0-9]+\t/{c++} END{print c+0}' "$out")"
if [ "$lines" -lt 1 ]; then
    echo "FAIL: no TSV lines produced (output follows)"
    cat "$out"
    exit 1
fi

echo "OK: produced $lines TSV samples, no leaked programs"

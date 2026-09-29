/*
 * intp_agg.bpf.h -- types shared between the BPF-side programs
 * (intp_agg.bpf.c) and the userspace loader (intp_agg.c) for V3.3.
 *
 * V3.3 is the per-CGROUP sibling of V3.2. It keeps V3.2's in-kernel
 * counter-map aggregation (no ring buffer) but attributes every event to a
 * CGROUP IDENTITY (cgroup v2 inode id) rather than to a PID set. There are
 * still no per-event records; everything the BPF side wants to report lands
 * as an atomic increment into one of two counter maps:
 *
 *   agg_global       : BPF_MAP_TYPE_PERCPU_ARRAY, max_entries=1
 *                      a single struct intp_counters per CPU; userspace sums
 *                      across CPUs at poll time. Carries the host-wide totals
 *                      the cost model and diagnostics need: nets_*_lat_*
 *                      (system-wide softirq = the nets_sys numerator), the
 *                      device-level netp_dev_{tx,rx}_bytes (diagnostic, C1),
 *                      and bytes_total for the nets byte-share split (C2).
 *   agg_per_cgroup   : BPF_MAP_TYPE_HASH, max_entries=INTP_AGG_HASH_MAX
 *                      keyed by cgroup id (u64 inode). For a single --cgroup
 *                      target run the loader reads the slot at target_cgid.
 *
 * On the BPF side, __u32/__u64 come from vmlinux.h which the translation
 * unit has already included before this header. Userspace TUs get them
 * from <linux/types.h> instead; we pull that in here under the guard
 * below so callers don't have to remember.
 */

#ifndef INTP_AGG_BPF_H
#define INTP_AGG_BPF_H

#ifndef __VMLINUX_H__
#include <linux/types.h>
#endif

/* Retained for the userspace --pids buffer (intp_args_t) and the resctrl
 * PID-assignment path; the in-kernel PID filter loop is gone in V3.3. */
#define INTP_MAX_PIDS        64

/* Upper bound on tracked cgroup ids in the per-cgroup hash. A single
 * --cgroup run uses exactly one slot (target_cgid); the headroom is for the
 * DESIGN §6 "attribute every cgroup at once" generalization (the IADA
 * whole-node view) without a probe rewrite. */
#define INTP_AGG_HASH_MAX    1024

/*
 * Config map: userspace pushes one record into the single-entry array
 * before attaching programs. V3.3 replaces V3.2's PID-list machinery with
 * cgroup-identity gating (DESIGN §3):
 *
 *   target_cgid  : stat(cgroup_path).st_ino -- the cgroup v2 inode id that
 *                  bpf_get_current_cgroup_id() / the kernfs id equal.
 *   target_level : path-component depth under /sys/fs/cgroup, used by the
 *                  ancestor (child-inclusive) gate.
 *   exact_flag   : 1 => leaf-only gate (bpf_get_current_cgroup_id ==
 *                  target_cgid); 0 => ancestor gate
 *                  (bpf_get_current_ancestor_cgroup_id(target_level) ==
 *                  target_cgid), the V3.3 default (whole-container).
 *
 * system_wide is kept: when no --cgroup/--target-container is given the
 * loader sets it and the per-cgroup gate degrades to "attribute everything
 * to the host-wide totals only" (agg_global), matching V3.2's behaviour.
 */
struct intp_config {
    __u64 target_cgid;   /* stat(cgroup path).st_ino                     */
    __u32 target_level;  /* depth under /sys/fs/cgroup (ancestor gate)    */
    __u8  exact_flag;    /* 1 = leaf-only gate, 0 = ancestor-inclusive    */
    __u8  system_wide;   /* 1 = no cgroup target (agg_global only)        */
    __u16 _pad0;
};

/*
 * Per-CPU / per-cgroup counter struct.
 *
 * Fields are __u64 because every increment is via __sync_fetch_and_add()
 * and the kernel-side BPF verifier wants atomic-on-64-bit guarantees.
 * Trailing _pad pushes the struct out to a cache-line multiple so two
 * adjacent per-CPU slots never share a line under false-sharing pressure.
 *
 * Field semantics:
 *   netp_tx_bytes / netp_rx_bytes : CANONICAL per-cgroup network bytes
 *      transmitted / received summed over the interval, from the
 *      cgroup_skb egress/ingress programs (C1). netp = (tx+rx)/interval /
 *      nic_max * 100. In agg_per_cgroup these are the cgroup's bytes; in
 *      agg_global they are the host-wide bytes_total (the cost-model
 *      denominator). For a VM target (args.tap_iface set) the loader
 *      sources canonical netp from the host tap iface instead.
 *   netp_dev_tx_bytes / netp_dev_rx_bytes : DIAGNOSTIC device-level
 *      (host-wide, 'lo' excluded) bytes from net_dev_xmit /
 *      netif_receive_skb, used only in agg_global. Surfaced as the trailing
 *      netp_dev column for v3.2 cross-check (C1); never per-cgroup.
 *   nets_tx_lat_ns_sum / nets_tx_lat_n : softirq vec=2 NET_TX time and
 *      its count. nets_rx_lat_ns_sum / nets_rx_lat_n : same for vec=3.
 *      System-wide ONLY (softirq is not cgroup-keyable, C2): accumulated
 *      into agg_global. nets_sys = sum / interval_ns; the per-cgroup nets
 *      is the loader's byte-share split nets_sys * bytes(cg) / bytes_total.
 *   blk_svctm_ns_sum / blk_ops / blk_bytes : block I/O service time
 *      (svctm = complete - issue) and request count + bytes, attributed to
 *      the owning cgroup via the bio's blkcg (bio->bi_blkg). blk = svctm /
 *      interval_ns * 100 -- canonical unit unchanged (C7).
 *   cpu_on_ns_sum : aggregate on-CPU ns of the cgroup's tasks at
 *      sched_switch; userspace normalizes against (interval_ns *
 *      num_cores).
 *   llc_refs / llc_misses : already scaled by perf_event sample_period
 *      so the ratio stays correct regardless of the period chosen.
 */
struct intp_counters {
    __u64 netp_tx_bytes;
    __u64 netp_rx_bytes;
    __u64 netp_dev_tx_bytes;   /* diagnostic, agg_global only (C1) */
    __u64 netp_dev_rx_bytes;   /* diagnostic, agg_global only (C1) */
    __u64 nets_tx_lat_ns_sum;
    __u64 nets_tx_lat_n;
    __u64 nets_rx_lat_ns_sum;
    __u64 nets_rx_lat_n;
    __u64 blk_svctm_ns_sum;
    __u64 blk_ops;
    __u64 blk_bytes;
    __u64 cpu_on_ns_sum;
    __u64 llc_refs;
    __u64 llc_misses;
    __u64 schedlat_wait_ns_sum;  /* run-queue wait ns charged to the incoming
                                  * task's cgroup (schedlat: run-queue wait, as
                                  * Volpert's PSL; normalized by interval x CPUs
                                  * instead of per process, C26). */
    __u64 psp_count;             /* involuntary preemptions of target tasks
                                  * (prev still RUNNABLE at sched_switch) --
                                  * scheduling-regime sub-family. NOT Volpert's
                                  * PSP (switches to PID 0 as a throttling
                                  * indicator; throttling is schedthr).
                                  * Always counted; emitted only --portable-metrics
                                  * (canonical 7 untouched, like schedlat). */
    __u64 idle_preempt_count;    /* idle-CPU takeover rate (prev = swapper,
                                  * next = target task), scheduling-regime;
                                  * emitted --portable-metrics. */
    /* Cache-line pad. 17 fields * 8 = 136 bytes; +7*8 = 192 bytes (a 64-byte
     * cache-line multiple on x86_64). Keep the struct a 64-byte multiple so two
     * adjacent per-CPU slots never share a line; recheck false-sharing if the
     * field count changes. */
    __u64 _pad[7];
};

#endif /* INTP_AGG_BPF_H */

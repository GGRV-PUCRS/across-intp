/*
 * intp_agg.bpf.c -- kernel-side programs for IntP V3.3 (eBPF/cgroup).
 *
 * V3.3 is the per-CGROUP sibling of V3.2. Like V3.2 it accumulates the
 * per-event signal directly into per-CPU / per-cgroup counter maps and is
 * polled once per --interval by userspace -- no ring buffer, no
 * ring_buffer__poll, no consumer-wakeup feedback loop (the 188-390x
 * context-switch amplification V3 incurs, SBAC-PAD 2026 section V-D).
 *
 * The change from V3.2 is the ATTRIBUTION KEY: instead of a static
 * target_pids[] + a fork/exit-maintained descendant_tgids hash (membership
 * by PID-lineage, which misses tasks migrated into the cgroup after attach),
 * V3.3 gates on CGROUP IDENTITY:
 *
 *   exact   : bpf_get_current_cgroup_id()              == target_cgid
 *   ancestor: bpf_get_current_ancestor_cgroup_id(level) == target_cgid   (default)
 *
 * Migration-safe, no /proc seed, no fork tracking (DESIGN §3). Per-event
 * attribution lands in agg_per_cgroup keyed by cgroup id; a single --cgroup
 * run uses one slot at target_cgid and the loader reads it.
 *
 * Backend map (DECISIONS-container.md):
 *   C1 netp : canonical per-cgroup via cgroup_skb ingress/egress; trailing
 *             diagnostic netp_dev from net_dev_xmit / netif_receive_skb.
 *   C2 nets : softirq is NOT cgroup-keyable in softirq context, so the BPF
 *             side accumulates NET_TX/NET_RX time SYSTEM-WIDE into agg_global
 *             only; the per-cgroup byte-share split happens in the loader.
 *   C7 blk  : svctm (complete - issue), canonical unit stays %-of-interval.
 *
 * Kernel target: 6.17 with BTF + cgroup v2 unified + resctrl.
 */

#include "vmlinux.h"
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_core_read.h>
#include <bpf/bpf_tracing.h>

#include "intp_agg.bpf.h"

char LICENSE[] SEC("license") = "Dual MIT/GPL";

/* ------------------------------------------------------------------ Maps */

/* Config map. Userspace populates this once at attach time with
 * {target_cgid, target_level, exact_flag, system_wide}; probes read it on
 * every invocation via intp_cfg(). */
struct {
    __uint(type, BPF_MAP_TYPE_ARRAY);
    __uint(max_entries, 1);
    __type(key, __u32);
    __type(value, struct intp_config);
} intp_cfg_map SEC(".maps");

/* Global counter map: one struct intp_counters per CPU at key=0. Carries the
 * host-wide totals the loader needs -- system-wide softirq nets (C2), the
 * diagnostic device-level netp_dev (C1), and bytes_total (the netp_tx/rx
 * fields, the cost-model denominator). Userspace sums slots across all CPUs
 * at sampling time. iprof pattern (Goege thesis ch. 3.3, Becker et al. UCC
 * Companion 2024); this is what eliminates the ring-buffer consumer. */
struct {
    __uint(type, BPF_MAP_TYPE_PERCPU_ARRAY);
    __uint(max_entries, 1);
    __type(key, __u32);
    __type(value, struct intp_counters);
} agg_global SEC(".maps");

/* Per-cgroup counter map, keyed by cgroup id (u64 inode). Updated when the
 * cgroup-identity gate matches (not in system-wide mode). A single --cgroup
 * run populates exactly one slot at target_cgid; the headroom generalizes to
 * the DESIGN §6 whole-node view without a probe rewrite. */
struct {
    __uint(type, BPF_MAP_TYPE_HASH);
    __uint(max_entries, INTP_AGG_HASH_MAX);
    __type(key, __u64);
    __type(value, struct intp_counters);
} agg_per_cgroup SEC(".maps");

/* Single-slot per-CPU template of zeros, used to seed new entries in
 * agg_per_cgroup without putting a struct intp_counters on the BPF stack
 * (the struct is 128 bytes). Userspace doesn't touch this; the BPF side
 * reads from it under BPF_NOEXIST insertion. */
struct {
    __uint(type, BPF_MAP_TYPE_PERCPU_ARRAY);
    __uint(max_entries, 1);
    __type(key, __u32);
    __type(value, struct intp_counters);
} agg_zero SEC(".maps");

/* Per-request issue timestamp, keyed by (dev<<32)|sector for block svctm. */
struct {
    __uint(type, BPF_MAP_TYPE_HASH);
    __uint(max_entries, 16384);
    __type(key, __u64);
    __type(value, __u64);
} rq_start SEC(".maps");

/* Per-task on-CPU start timestamp, keyed by tid. */
struct {
    __uint(type, BPF_MAP_TYPE_HASH);
    __uint(max_entries, 32768);
    __type(key, __u32);
    __type(value, __u64);
} task_oncpu_start SEC(".maps");

/* Per-task wakeup timestamp, keyed by tid, for run-queue (scheduling) latency
 * (schedlat). Stamped at sched_wakeup/sched_wakeup_new when the task becomes
 * runnable; consumed + deleted at sched_switch when it is dispatched. */
struct {
    __uint(type, BPF_MAP_TYPE_HASH);
    __uint(max_entries, 32768);
    __type(key, __u32);
    __type(value, __u64);
} task_wakeup_ts SEC(".maps");

/* -------------------------------------------------------------- Helpers */

static __always_inline struct intp_config *intp_cfg(void)
{
    __u32 key = 0;
    return bpf_map_lookup_elem(&intp_cfg_map, &key);
}

/* Cgroup-identity gate for TASK-CONTEXT probes (sched_switch close, perf
 * overflow, block_rq_complete submission). Returns 1 when the *current*
 * task's cgroup is the target (exact) or a descendant of it (ancestor
 * gate, the V3.3 default). DESIGN §3. */
static __always_inline int cg_in_filter(struct intp_config *cfg)
{
    if (!cfg)             return 1;   /* misconfigured -> observe all */
    if (cfg->system_wide) return 1;

    if (cfg->exact_flag)
        return bpf_get_current_cgroup_id() == cfg->target_cgid;
    return bpf_get_current_ancestor_cgroup_id(cfg->target_level)
               == cfg->target_cgid;
}

/* Return the per-CPU agg_global slot for the calling probe. NULL on lookup
 * failure (unreachable for PERCPU_ARRAY[key=0] in practice, but the verifier
 * insists). */
static __always_inline struct intp_counters *agg_global_slot(void)
{
    __u32 key = 0;
    return bpf_map_lookup_elem(&agg_global, &key);
}

/* Return (and lazily create) the per-cgroup slot for cgid. The lazy-create
 * path seeds from agg_zero rather than putting a 128-byte struct on the probe
 * stack. The BPF_NOEXIST insert can race across CPUs; the subsequent lookup
 * is authoritative. */
static __always_inline struct intp_counters *
agg_per_cgroup_slot(__u64 cgid)
{
    struct intp_counters *p = bpf_map_lookup_elem(&agg_per_cgroup, &cgid);
    if (p) return p;

    __u32 zk = 0;
    struct intp_counters *z = bpf_map_lookup_elem(&agg_zero, &zk);
    if (!z) return NULL;

    bpf_map_update_elem(&agg_per_cgroup, &cgid, z, BPF_NOEXIST);
    return bpf_map_lookup_elem(&agg_per_cgroup, &cgid);
}

/* Convenience: the per-cgroup slot to charge a current-task event to.
 * Always keyed by target_cgid so a single --cgroup run uses one slot the
 * loader can read directly; cg_in_filter() has already confirmed the current
 * task belongs to the target. */
static __always_inline struct intp_counters *
target_cgroup_slot(struct intp_config *cfg)
{
    if (!cfg) return NULL;
    return agg_per_cgroup_slot(cfg->target_cgid);
}

/* Bounded ancestor walk for DEFERRED-CONTEXT cgroup ids (the bio's blkcg),
 * where current is the flusher kworker, not the owner -- so the per-task
 * ancestor helper cannot be used. Given an owning cgroup pointer, decide
 * whether it is (exact) or descends from (ancestor gate) target_cgid.
 *
 * cgroup v2 exposes cgroup->level (depth) and cgroup->ancestors[level]; we
 * read the leaf id and, for the ancestor gate, climb the ->self.parent chain
 * a bounded number of steps comparing the kernfs id. Bounded loop keeps the
 * verifier happy. CO-RE reads throughout. */
static __always_inline int cg_ptr_matches_target(struct intp_config *cfg,
                                                  struct cgroup *cg)
{
    if (!cfg) return 1;
    if (!cg)  return 0;

    __u64 id = BPF_CORE_READ(cg, kn, id);
    if (cfg->exact_flag)
        return id == cfg->target_cgid;

    /* ancestor gate: this cgroup OR any ancestor equals target_cgid. Climb
     * up via cgroup_subsys_state.parent->cgroup. 16 levels covers any sane
     * container nesting (LXD/systemd scopes are <= ~6 deep). */
    struct cgroup_subsys_state *css = BPF_CORE_READ(cg, self.parent);
#pragma unroll
    for (int i = 0; i < 16; i++) {
        if (id == cfg->target_cgid) return 1;
        if (!css) break;
        struct cgroup *pc = BPF_CORE_READ(css, cgroup);
        if (!pc) break;
        id  = BPF_CORE_READ(pc, kn, id);
        css = BPF_CORE_READ(css, parent);
    }
    return id == cfg->target_cgid;
}

/* =====================================================================
 * netp -- canonical PER-CGROUP via cgroup_skb + diagnostic device-level
 *
 * C1: the canonical netp column is per-cgroup. We attach
 * BPF_PROG_TYPE_CGROUP_SKB ingress + egress to the target cgroup fd; those
 * programs only fire for the target cgroup's sockets (and descendants),
 * so the attach point IS the gate -- every byte is charged to target_cgid.
 * That also yields the bytes(cg) numerator for the nets cost model (C2).
 *
 * The device-level signal (host-wide NIC bytes, what V3.2 reported and V2
 * reads from /sys/class/net non-lo) is retained for cross-check as the
 * trailing diagnostic netp_dev column -- it comes from the net_dev_xmit /
 * netif_receive_skb tracepoints into agg_global only.
 * ===================================================================== */

/* __sk_buff has the packet length in ->len directly (stable UAPI field). */
SEC("cgroup_skb/egress")
int cg_skb_egress(struct __sk_buff *skb)
{
    struct intp_config *cfg = intp_cfg();
    if (!cfg) return 1;

    __u32 len = skb->len;

    /* bytes_total numerator host-wide (the cost-model denominator lives in
     * agg_global). For a single-target attach this equals the cgroup bytes,
     * but the loader uses agg_global.netp_* as bytes_total regardless. */
    struct intp_counters *g = agg_global_slot();
    if (g) __sync_fetch_and_add(&g->netp_tx_bytes, len);

    if (!cfg->system_wide) {
        struct intp_counters *p = target_cgroup_slot(cfg);
        if (p) __sync_fetch_and_add(&p->netp_tx_bytes, len);
    }
    return 1;   /* cgroup_skb: 1 = allow the packet */
}

SEC("cgroup_skb/ingress")
int cg_skb_ingress(struct __sk_buff *skb)
{
    struct intp_config *cfg = intp_cfg();
    if (!cfg) return 1;

    __u32 len = skb->len;

    struct intp_counters *g = agg_global_slot();
    if (g) __sync_fetch_and_add(&g->netp_rx_bytes, len);

    if (!cfg->system_wide) {
        struct intp_counters *p = target_cgroup_slot(cfg);
        if (p) __sync_fetch_and_add(&p->netp_rx_bytes, len);
    }
    return 1;
}

/* Device-level diagnostic (netp_dev). lo excluded to avoid the single-host
 * xmit+recv 2x double-count, exactly as V3.2's device-level netp. */
static __always_inline int tp_dev_is_lo(void *ctx, unsigned int data_loc)
{
    unsigned int offset = data_loc & 0xFFFFu;
    char buf[4] = {};
    bpf_probe_read_kernel_str(buf, sizeof(buf), (char *)ctx + offset);
    return buf[0] == 'l' && buf[1] == 'o' && buf[2] == '\0';
}

SEC("tracepoint/net/net_dev_xmit")
int tp_net_dev_xmit(struct trace_event_raw_net_dev_xmit *ctx)
{
    if (tp_dev_is_lo(ctx, ctx->__data_loc_name)) return 0;

    struct intp_counters *g = agg_global_slot();
    if (!g) return 0;

    __u32 len = BPF_CORE_READ(ctx, len);
    __sync_fetch_and_add(&g->netp_dev_tx_bytes, len);
    return 0;
}

SEC("tracepoint/net/netif_receive_skb")
int tp_netif_receive_skb(struct trace_event_raw_net_dev_template *ctx)
{
    if (tp_dev_is_lo(ctx, ctx->__data_loc_name)) return 0;

    struct intp_counters *g = agg_global_slot();
    if (!g) return 0;

    __u32 len = BPF_CORE_READ(ctx, len);
    __sync_fetch_and_add(&g->netp_dev_rx_bytes, len);
    return 0;
}

/* =====================================================================
 * blk -- block I/O utilization, attributed by the bio's blkcg
 *
 * issue stashes the start ts keyed by (dev<<32)|sector; complete looks it
 * up and increments svctm_sum / blk_ops / blk_bytes. C7: canonical blk stays
 * %-of-interval svctm. The cgroup is the bio OWNER (bio->bi_blkg->blkcg),
 * so writeback is charged to the owning cgroup rather than the flusher
 * kworker -- using the deferred-context ancestor walk, not the current task.
 * ===================================================================== */

SEC("tracepoint/block/block_rq_issue")
int tp_block_rq_issue(struct trace_event_raw_block_rq *ctx)
{
    __u64 dev_sec = ((__u64)BPF_CORE_READ(ctx, dev) << 32)
                   | BPF_CORE_READ(ctx, sector);
    __u64 ts = bpf_ktime_get_ns();
    bpf_map_update_elem(&rq_start, &dev_sec, &ts, BPF_ANY);
    return 0;
}

/* block_rq_complete has no bio pointer in its trace context, so the bio's
 * blkcg cannot be read here. We attach a fentry-style raw tracepoint on the
 * bio path for the cgroup id instead -- but to keep this object portable on
 * 6.17 without BTF-funcs assumptions, we charge svctm host-wide in
 * agg_global and, for the per-cgroup slot, use the CURRENT task's cgroup
 * (process-context submission, e.g. direct/sync I/O, is the common case for
 * the validation workloads). Writeback-correct blkcg attribution via
 * bio->bi_blkg is wired through block_bio_complete below where the bio IS
 * available. */
SEC("tracepoint/block/block_rq_complete")
int tp_block_rq_complete(struct trace_event_raw_block_rq_completion *ctx)
{
    struct intp_config *cfg = intp_cfg();

    __u64 dev_sec = ((__u64)BPF_CORE_READ(ctx, dev) << 32)
                   | BPF_CORE_READ(ctx, sector);
    __u64 now = bpf_ktime_get_ns();
    __u64 svctm = 0;
    __u64 *start_ts = bpf_map_lookup_elem(&rq_start, &dev_sec);
    if (start_ts) {
        svctm = now - *start_ts;
        bpf_map_delete_elem(&rq_start, &dev_sec);
    }

    __u32 bytes = BPF_CORE_READ(ctx, nr_sector) * 512;

    struct intp_counters *g = agg_global_slot();
    if (!g) return 0;
    __sync_fetch_and_add(&g->blk_svctm_ns_sum, svctm);
    __sync_fetch_and_add(&g->blk_ops, 1);
    __sync_fetch_and_add(&g->blk_bytes, bytes);

    if (cfg && !cfg->system_wide && cg_in_filter(cfg)) {
        struct intp_counters *p = target_cgroup_slot(cfg);
        if (p) {
            __sync_fetch_and_add(&p->blk_svctm_ns_sum, svctm);
            __sync_fetch_and_add(&p->blk_ops, 1);
            __sync_fetch_and_add(&p->blk_bytes, bytes);
        }
    }
    return 0;
}

/* The block_rq_complete TRACEPOINT (above) does not expose the bio pointer
 * in its trace context (its CO-RE struct is dev/sector/nr_sector/error/rwbs
 * only), so bio->bi_blkg cannot be read there. The writeback-correct OWNER
 * cgroup (bio->bi_blkg->blkcg->css.cgroup) is reachable via the BTF raw
 * tracepoint block_bio_complete, whose typed signature on 6.17 is
 *   (struct request_queue *q, struct bio *bio)
 * (btf_trace_block_bio_complete in vmlinux.h). A tp_btf program receives the
 * real bio pointer, so this is the documented-safe CO-RE idiom for the
 * writeback case.
 *
 * This site does NOT touch the canonical svctm/ops counters (block_rq_complete
 * already owns svctm via its matched issue/complete pair -- C7 unit unchanged,
 * no double-count). It only attributes byte VOLUME to the correct owning
 * cgroup when the submitter ran in deferred context (flusher kworker), which
 * the current-task gate in block_rq_complete would otherwise misattribute. */
SEC("tp_btf/block_bio_complete")
int BPF_PROG(tp_block_bio_complete, struct request_queue *q, struct bio *bio)
{
    struct intp_config *cfg = intp_cfg();
    if (!cfg || cfg->system_wide) return 0;

    /* If the current task already matched, block_rq_complete handled it;
     * only take over here for deferred-context (writeback) bios whose owner
     * differs from the interrupted/flusher task. */
    if (cg_in_filter(cfg)) return 0;

    if (!bio) return 0;
    struct blkcg_gq *blkg = BPF_CORE_READ(bio, bi_blkg);
    if (!blkg) return 0;
    struct cgroup *cg = BPF_CORE_READ(blkg, blkcg, css.cgroup);
    if (!cg) return 0;
    if (!cg_ptr_matches_target(cfg, cg)) return 0;

    __u32 bytes = (__u32)BPF_CORE_READ(bio, bi_iter.bi_size);
    struct intp_counters *p = target_cgroup_slot(cfg);
    if (p) __sync_fetch_and_add(&p->blk_bytes, bytes);
    return 0;
}

/* =====================================================================
 * cpu -- CPU utilization via sched_switch
 *
 * On every sched_switch we close the outgoing task's on-CPU interval
 * (delta = now - task_oncpu_start[prev_pid]) and start the incoming task's
 * interval. At this tracepoint `current` is still the prev task, so
 * cg_in_filter() (which reads the current task's cgroup) decides whether the
 * outgoing slice belongs to the target cgroup. DESIGN §4: keyed by the
 * ancestor-cgroup-id of the switching task.
 * ===================================================================== */

SEC("tracepoint/sched/sched_switch")
int tp_sched_switch(struct trace_event_raw_sched_switch *ctx)
{
    struct intp_config *cfg = intp_cfg();

    __u32 prev_pid = BPF_CORE_READ(ctx, prev_pid);
    __u32 next_pid = BPF_CORE_READ(ctx, next_pid);
    __u64 now      = bpf_ktime_get_ns();

    __u64 *start_ts = bpf_map_lookup_elem(&task_oncpu_start, &prev_pid);
    if (start_ts) {
        __u64 delta = now - *start_ts;

        /* current == prev at sched_switch; gate on its cgroup. */
        int match = cg_in_filter(cfg);

        struct intp_counters *g = agg_global_slot();
        if (g && match) __sync_fetch_and_add(&g->cpu_on_ns_sum, delta);

        if (cfg && !cfg->system_wide && match) {
            struct intp_counters *p = target_cgroup_slot(cfg);
            if (p) __sync_fetch_and_add(&p->cpu_on_ns_sum, delta);
        }
        bpf_map_delete_elem(&task_oncpu_start, &prev_pid);
    }

    if (next_pid != 0)
        bpf_map_update_elem(&task_oncpu_start, &next_pid, &now, BPF_ANY);
    return 0;
}

/* =====================================================================
 * schedlat -- run-queue (scheduling) latency  [C26, VM-portable]
 *
 * sched_wakeup makes a task runnable; we stamp its wakeup time per tid. When
 * the task is later dispatched (sched_switch -> next), we charge the waited
 * interval (now - wakeup_ts) to the INCOMING task's cgroup. RDT/PMU-free and
 * VM-portable: this is Volpert ICPE'25 PSL / runqlat, the metric Paper 1's
 * future work names. We use tp_btf/sched_switch so the typed `next`
 * task_struct* is available -- bpf_get_current_cgroup_id() at switch returns
 * PREV, so we read next->cgroups directly via the deferred-context idiom
 * (cg_ptr_matches_target), exactly like the bio-owner case (block_bio_complete).
 */
static __always_inline void schedlat_enqueue(__u32 pid)
{
    if (pid == 0) return;
    __u64 now = bpf_ktime_get_ns();
    bpf_map_update_elem(&task_wakeup_ts, &pid, &now, BPF_ANY);
}

SEC("tracepoint/sched/sched_wakeup")
int tp_sched_wakeup(struct trace_event_raw_sched_wakeup_template *ctx)
{
    schedlat_enqueue((__u32)BPF_CORE_READ(ctx, pid));
    return 0;
}

SEC("tracepoint/sched/sched_wakeup_new")
int tp_sched_wakeup_new(struct trace_event_raw_sched_wakeup_template *ctx)
{
    schedlat_enqueue((__u32)BPF_CORE_READ(ctx, pid));
    return 0;
}

SEC("tp_btf/sched_switch")
int BPF_PROG(tp_schedlat, bool preempt, struct task_struct *prev,
             struct task_struct *next, unsigned int prev_state)
{
    __u64 now = bpf_ktime_get_ns();
    /* prev was preempted but still RUNNABLE -> it re-enters the run-queue now;
     * stamp its requeue time. CPU-bound tasks rarely sleep, so they almost
     * never hit sched_wakeup -- without this their run-queue wait is invisible
     * (runqlat handles this preempt-requeue case explicitly). Read prev->__state
     * DIRECTLY (TASK_RUNNING==0): the tracepoint `prev_state` ARG is the masked
     * TASK_REPORT value (preempted => TASK_REPORT_MAX, not 0), so it can't be
     * used for this test. */
    (void)prev_state;
    if (BPF_CORE_READ(prev, __state) == 0) {
        __u32 prev_pid = (__u32)BPF_CORE_READ(prev, pid);
        if (prev_pid != 0)
            bpf_map_update_elem(&task_wakeup_ts, &prev_pid, &now, BPF_ANY);
    }
    __u32 next_pid = (__u32)BPF_CORE_READ(next, pid);
    if (next_pid == 0) return 0;
    __u64 *wts = bpf_map_lookup_elem(&task_wakeup_ts, &next_pid);
    if (!wts) return 0;
    __u64 wait = now - *wts;
    bpf_map_delete_elem(&task_wakeup_ts, &next_pid);

    struct intp_config *cfg = intp_cfg();
    if (cfg && cfg->system_wide) {
        struct intp_counters *g = agg_global_slot();
        if (g) __sync_fetch_and_add(&g->schedlat_wait_ns_sum, wait);
        return 0;
    }
    /* per-cgroup: charge the INCOMING task's cgroup (next->cgroups->dfl_cgrp). */
    struct cgroup *ncg = BPF_CORE_READ(next, cgroups, dfl_cgrp);
    if (cg_ptr_matches_target(cfg, ncg)) {
        struct intp_counters *p = target_cgroup_slot(cfg);
        if (p) __sync_fetch_and_add(&p->schedlat_wait_ns_sum, wait);
    }
    return 0;
}

/* =====================================================================
 * nets -- network stack service time via softirq tracepoints
 *
 * C2: softirqs run in interrupted context, so bpf_get_current_cgroup_id()
 * returns whoever was preempted -- NOT the packet's owner. nets is therefore
 * structurally NOT cgroup-keyable at this site. The BPF side only accumulates
 * NET_TX (vec=2) / NET_RX (vec=3) softirq CPU time SYSTEM-WIDE into
 * agg_global (the nets_sys numerator); the per-cgroup byte-share split
 * (nets_sys * bytes(cg) / bytes_total) happens entirely in the loader.
 *
 * Per-CPU keyed because softirqs are non-preemptible on a CPU, so the
 * entry/exit pair always lives on the same CPU.
 * ===================================================================== */

struct {
    __uint(type, BPF_MAP_TYPE_HASH);
    __uint(max_entries, 256);
    __type(key, __u32);
    __type(value, __u64);
} softirq_tx_start SEC(".maps");

struct {
    __uint(type, BPF_MAP_TYPE_HASH);
    __uint(max_entries, 256);
    __type(key, __u32);
    __type(value, __u64);
} softirq_rx_start SEC(".maps");

SEC("tracepoint/irq/softirq_entry")
int tp_softirq_entry(struct trace_event_raw_softirq *ctx)
{
    __u32 vec = BPF_CORE_READ(ctx, vec);
    if (vec != 2 && vec != 3) return 0;
    __u32 cpu = bpf_get_smp_processor_id();
    __u64 ts  = bpf_ktime_get_ns();
    if (vec == 2)
        bpf_map_update_elem(&softirq_tx_start, &cpu, &ts, BPF_ANY);
    else
        bpf_map_update_elem(&softirq_rx_start, &cpu, &ts, BPF_ANY);
    return 0;
}

SEC("tracepoint/irq/softirq_exit")
int tp_softirq_exit(struct trace_event_raw_softirq *ctx)
{
    __u32 vec = BPF_CORE_READ(ctx, vec);
    if (vec != 2 && vec != 3) return 0;
    __u32 cpu = bpf_get_smp_processor_id();
    __u64 now = bpf_ktime_get_ns();

    __u64 *start_ts;
    if (vec == 2)
        start_ts = bpf_map_lookup_elem(&softirq_tx_start, &cpu);
    else
        start_ts = bpf_map_lookup_elem(&softirq_rx_start, &cpu);
    if (!start_ts) return 0;
    __u64 delta = now - *start_ts;

    if (vec == 2)
        bpf_map_delete_elem(&softirq_tx_start, &cpu);
    else
        bpf_map_delete_elem(&softirq_rx_start, &cpu);

    /* System-wide ONLY (C2). agg_global, never per-cgroup. */
    struct intp_counters *g = agg_global_slot();
    if (!g) return 0;
    if (vec == 2) {
        __sync_fetch_and_add(&g->nets_tx_lat_ns_sum, delta);
        __sync_fetch_and_add(&g->nets_tx_lat_n, 1);
    } else {
        __sync_fetch_and_add(&g->nets_rx_lat_ns_sum, delta);
        __sync_fetch_and_add(&g->nets_rx_lat_n, 1);
    }
    return 0;
}

/* =====================================================================
 * llcmr -- LLC miss ratio via perf_event BPF programs
 *
 * Userspace opens two perf_event counters (HW_CACHE_L3 references and
 * misses) in cgroup mode (PERF_FLAG_PID_CGROUP) bound to the target cgroup
 * and attaches these programs to each. cgroup-mode counters only accrue
 * while a task of the target cgroup is on-CPU, so per-cgroup attribution is
 * finished by the open flag -- these probes just fold the period-scaled
 * overflow into both agg_global and the target's per-cgroup slot.
 *
 * NOTE on reading sample_period from ctx: BPF_CORE_READ() on
 * bpf_perf_event_data hits the wrong offset and returns 0 (verified on V3 /
 * Sapphire Rapids / kernel 6.8). Direct field access is the verifier-blessed
 * path.
 * ===================================================================== */

SEC("perf_event")
int perf_llc_refs(struct bpf_perf_event_data *ctx)
{
    struct intp_config *cfg = intp_cfg();

    struct intp_counters *g = agg_global_slot();
    if (!g) return 0;
    __sync_fetch_and_add(&g->llc_refs, ctx->sample_period);

    if (cfg && !cfg->system_wide) {
        struct intp_counters *p = target_cgroup_slot(cfg);
        if (p) __sync_fetch_and_add(&p->llc_refs, ctx->sample_period);
    }
    return 0;
}

SEC("perf_event")
int perf_llc_misses(struct bpf_perf_event_data *ctx)
{
    struct intp_config *cfg = intp_cfg();

    struct intp_counters *g = agg_global_slot();
    if (!g) return 0;
    __sync_fetch_and_add(&g->llc_misses, ctx->sample_period);

    if (cfg && !cfg->system_wide) {
        struct intp_counters *p = target_cgroup_slot(cfg);
        if (p) __sync_fetch_and_add(&p->llc_misses, ctx->sample_period);
    }
    return 0;
}

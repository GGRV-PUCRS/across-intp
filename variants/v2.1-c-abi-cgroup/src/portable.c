/*
 * portable.c -- VM-portable interference metrics (--portable-metrics, C26).
 *
 * A SEPARATE, flag-gated benchmark (DESIGN §10 / docs/DECISIONS-container.md
 * C26). The canonical 7-metric IntP fingerprint (netp nets blk mbw llcmr llcocc
 * cpu), its on-disk schema, and the IADA input vector stay UNTOUCHED -- these
 * eight columns are emitted only when --portable-metrics is given, into their
 * own trailing columns, and analyzed by a dedicated faithfulness pass.
 *
 * Why these: inside a stock KVM guest the RDT metrics (mbw/llcocc) are
 * structurally absent (resctrl is host-only) and the LL-read PMU events that
 * back llcmr are <not supported> by the vPMU. The six portable metrics here are
 * computed by the GUEST'S OWN kernel and therefore survive in-guest; psp and
 * idle_preempt (bottom of this file) are the scheduling-regime pair:
 *
 *   schedlat   run-queue / scheduling latency  -- per-thread
 *              /proc/<tid>/schedstat run-delay (preferred backend), with PSI
 *              cpu.pressure 'some' as the fallback, %-of-interval. The direct
 *              VM-portable scheduling-contention signal (run-queue wait, as
 *              Volpert's PSL; normalized by interval x CPUs instead of per
 *              process). See Documentation/scheduler/sched-stats.rst and
 *              Documentation/accounting/psi.rst.
 *   psi_mem    PSI memory.pressure 'some'       -- %-of-interval. Memory-CAPACITY
 *              contention proxy (capacity, NOT bandwidth -- see membw_est).
 *   membw_est  DRAM-bandwidth estimate          -- LLC misses * 64B cacheline /
 *              interval (MB/s). The bandwidth complement psi_mem is blind to;
 *              uses the architectural cache-misses event (virtualized in-guest)
 *              via perfev_open_llc_cache*'s built-in fallback.
 *   psi_io     PSI io.pressure 'some'           -- %-of-interval. blk's
 *              contention companion.
 *   schedthr   CFS throttling                   -- cpu.stat throttled_usec,
 *              %-of-interval. Confound GUARD (separates an external noisy
 *              neighbour from a tenant hitting its own quota), not a contention
 *              signal; it plays the throttling-indicator role of Volpert's PSP.
 *              cgroup-only (no system analogue). throttled_usec exists whenever
 *              the cpu controller is enabled and reads 0 without a cpu.max
 *              limit; it is NOT hierarchical -- it counts only throttling by
 *              this cgroup's own limit, not an ancestor's
 *              (Documentation/admin-guide/cgroup-v2.rst, cpu.stat).
 *   steal      hypervisor-stolen vCPU time      -- /proc/stat field 8,
 *              %-of-total. VM-global (NOT cgroup-scoped); reflects host CPU
 *              contention only (not memory or IO); 0 on bare/container
 *              (Documentation/virt/kvm/x86/msr.rst, MSR_KVM_STEAL_TIME).
 *   psp        involuntary preemptions/s of the target's threads (NOT
 *              Volpert's PSP; see the psp block).
 *   idle_preempt  idle-CPU takeover rate -- eBPF-only, always "--" here.
 *
 * Claim classes: schedlat=directional; psi_mem/psi_io/membw_est=descriptive;
 * schedthr=descriptive (guard); steal=descriptive, VM-only.
 *
 * Each metric uses the same probe/init/read/cleanup backend chain as the
 * canonical metrics (cpu.c is the file-read template, llcmr.c the perf one).
 * A read returns METRIC_STATUS_UNAVAILABLE (-> "--") where the source is absent
 * (CONFIG_PSI=n, cpu controller not enabled for the cgroup, no cgroup target)
 * rather than a fake 0. schedthr without a cpu.max limit reads 0, not "--".
 */

#include "backend.h"
#include "detect.h"
#include "perfev.h"
#include "procutil.h"

#include <errno.h>
#include <fcntl.h>
#include <linux/perf_event.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

/* ------------------------------------------------------------------ shared file readers */

/* PSI 'some' cumulative stall time (microseconds) from the total= field. */
static int psi_some_total_us(const char *path, unsigned long long *out)
{
    FILE *f = fopen(path, "r");
    if (!f) return -1;
    char line[256];
    int rc = -1;
    while (fgets(line, sizeof(line), f)) {
        if (strncmp(line, "some", 4) != 0) continue;
        char *p = strstr(line, "total=");
        if (p && sscanf(p + 6, "%llu", out) == 1) rc = 0;
        break;
    }
    fclose(f);
    return rc;
}

/* CFS-bandwidth throttled time (microseconds) from a cgroup cpu.stat. */
static int cpu_stat_throttled_us(const char *path, unsigned long long *out)
{
    FILE *f = fopen(path, "r");
    if (!f) return -1;
    char line[128];
    int rc = -1;
    while (fgets(line, sizeof(line), f)) {
        if (sscanf(line, "throttled_usec %llu", out) == 1) { rc = 0; break; }
    }
    fclose(f);
    return rc;
}

/* /proc/stat aggregate cpu line: *steal = field 8 (jiffies), *total = sum. */
static int proc_stat_steal(unsigned long long *steal, unsigned long long *total)
{
    FILE *f = fopen("/proc/stat", "r");
    if (!f) return -1;
    char line[512];
    int rc = -1;
    if (fgets(line, sizeof(line), f) && strncmp(line, "cpu ", 4) == 0) {
        unsigned long long v[10] = {0};
        int n = sscanf(line + 4,
                       "%llu %llu %llu %llu %llu %llu %llu %llu %llu %llu",
                       &v[0],&v[1],&v[2],&v[3],&v[4],&v[5],&v[6],&v[7],&v[8],&v[9]);
        if (n >= 8) {
            unsigned long long t = 0;
            for (int i = 0; i < n; i++) t += v[i];
            *steal = v[7];   /* user nice system idle iowait irq softirq STEAL */
            *total = t;
            rc = 0;
        }
    }
    fclose(f);
    return rc;
}

/* ------------------------------------------------------------------ per-TID accounting */

/* /proc/<pid>/schedstat and the *_ctxt_switches lines of /proc/<pid>/status
 * describe ONE task_struct, not the thread group (fs/proc/base.c
 * proc_pid_schedstat prints task->sched_info.run_delay; fs/proc/array.c
 * task_context_switch_counts prints p->nvcsw/p->nivcsw). Reading them per TGID
 * counts only each process's leader thread, so a multi-threaded workload whose
 * leader sleeps (JVM, memcached, nginx workers) read ~0 (C38). schedlat and psp
 * therefore enumerate every TID of the target and keep a per-TID baseline:
 *
 *   - known TID:  delta = cur - prev, clamped at 0 per TID (TID reuse);
 *   - new TID:    delta = cur. The thread was born inside the interval, so its
 *                 whole counter belongs to it. The map is seeded at init(), so
 *                 this only applies to threads born mid-run; a thread that
 *                 existed before attach but was missed at seed time would
 *                 over-attribute its pre-attach history once, at its first
 *                 sample;
 *   - exited TID: drops out of the map; its last partial interval is lost.
 *
 * Per-TID baselines replace the old delta over a SUM of counters, where one
 * exiting task made the sum drop and the whole interval read 0. */

#define TIDMAP_SLOTS 32768u   /* power of two, >= 2 x INTP_MAX_TIDS */

typedef struct {
    pid_t              tid;   /* 0 = empty slot */
    unsigned long long val;
} tid_ent_t;

typedef int (*tid_reader_fn)(pid_t tid, unsigned long long *out);

typedef struct {
    tid_ent_t *prev;          /* last interval's baselines */
    tid_ent_t *cur;           /* scratch, swapped with prev after each sample */
    int        valid;
    int        capped;        /* last collection hit INTP_MAX_TIDS */
} tidacc_t;

static pid_t tid_buf[INTP_MAX_TIDS];

/* Collect the target's current TIDs: re-scan cgroup.threads over the cgroup
 * subtree each call when a cgroup is targeted (recursive -- catches workers
 * forked after start AND payloads that live in CHILD cgroups, as incus/lxc and
 * nested k8s pods place them under the cgroup v2 "no internal processes" rule),
 * else /proc/<pid>/task of each static --pids PID.
 * *capped is set when the INTP_MAX_TIDS cap was reached. */
static int collect_target_tids(pid_t *out, int max, int *capped)
{
    const intp_target_t *t = intp_target_get();
    *capped = 0;
    if (!t) return 0;
    int n = 0;
    if (t->cgroup_path) {
        n = procutil_read_cgroup_threads_rec(t->cgroup_path, out, (size_t)max);
    } else {
        for (int i = 0; i < t->n_pids && n < max; i++)
            n += procutil_read_proc_tasks(t->pids[i], out + n, (size_t)(max - n));
    }
    if (n >= max) *capped = 1;
    return n;
}

static unsigned tid_hash(pid_t tid)
{
    return ((unsigned)tid * 2654435761u) & (TIDMAP_SLOTS - 1u);
}

static tid_ent_t *tidmap_find(tid_ent_t *map, pid_t tid)
{
    for (unsigned h = tid_hash(tid), i = 0; i < TIDMAP_SLOTS;
         i++, h = (h + 1u) & (TIDMAP_SLOTS - 1u)) {
        if (map[h].tid == tid) return &map[h];
        if (map[h].tid == 0)   return NULL;
    }
    return NULL;
}

static void tidmap_put(tid_ent_t *map, pid_t tid, unsigned long long val)
{
    for (unsigned h = tid_hash(tid), i = 0; i < TIDMAP_SLOTS;
         i++, h = (h + 1u) & (TIDMAP_SLOTS - 1u)) {
        if (map[h].tid == 0 || map[h].tid == tid) {
            map[h].tid = tid;
            map[h].val = val;
            return;
        }
    }
}

/* Read every target TID into a->cur and, when `delta` is non-NULL, sum the
 * per-TID deltas against a->prev. Returns -1 when no TID was readable. */
static int tidacc_scan(tidacc_t *a, tid_reader_fn rd, unsigned long long *delta)
{
    int n = collect_target_tids(tid_buf, INTP_MAX_TIDS, &a->capped);
    if (n <= 0) return -1;
    memset(a->cur, 0, TIDMAP_SLOTS * sizeof(tid_ent_t));
    unsigned long long sum = 0;
    int any = 0;
    for (int i = 0; i < n; i++) {
        unsigned long long v;
        if (rd(tid_buf[i], &v) != 0) continue;   /* exited mid-scan */
        any = 1;
        tidmap_put(a->cur, tid_buf[i], v);
        if (!delta) continue;
        const tid_ent_t *p = tidmap_find(a->prev, tid_buf[i]);
        if (!p)              sum += v;           /* born this interval */
        else if (v >= p->val) sum += v - p->val;
    }
    if (!any) return -1;
    tid_ent_t *tmp = a->prev;
    a->prev = a->cur;
    a->cur  = tmp;
    if (delta) *delta = sum;
    return 0;
}

static void tidacc_free(tidacc_t *a)
{
    free(a->prev);
    free(a->cur);
    memset(a, 0, sizeof(*a));
}

/* Allocate the maps and seed the baselines with the TIDs present at init. */
static int tidacc_init(tidacc_t *a, tid_reader_fn rd)
{
    tidacc_free(a);
    a->prev = calloc(TIDMAP_SLOTS, sizeof(tid_ent_t));
    a->cur  = calloc(TIDMAP_SLOTS, sizeof(tid_ent_t));
    if (!a->prev || !a->cur || tidacc_scan(a, rd, NULL) != 0) {
        tidacc_free(a);
        return -1;
    }
    a->valid = 1;
    return 0;
}

/* Field 2 of /proc/<tid>/task/<tid>/schedstat: this thread's cumulative
 * run-queue wait (ns). The /proc/<tid>/task/<tid> form resolves for any TID,
 * leader or not, without knowing its TGID. */
static int read_tid_runqdelay(pid_t tid, unsigned long long *out)
{
    char path[80];
    snprintf(path, sizeof(path), "/proc/%d/task/%d/schedstat", (int)tid, (int)tid);
    FILE *f = fopen(path, "r");
    if (!f) return -1;
    unsigned long long run = 0, wait = 0;
    int rc = (fscanf(f, "%llu %llu", &run, &wait) == 2) ? 0 : -1;
    fclose(f);
    if (rc == 0) *out = wait;
    return rc;
}

/* nonvoluntary_ctxt_switches of /proc/<tid>/task/<tid>/status. */
static int read_tid_nonvol(pid_t tid, unsigned long long *out)
{
    char path[80];
    snprintf(path, sizeof(path), "/proc/%d/task/%d/status", (int)tid, (int)tid);
    FILE *f = fopen(path, "r");
    if (!f) return -1;
    char line[256];
    int rc = -1;
    while (fgets(line, sizeof(line), f)) {
        if (sscanf(line, "nonvoluntary_ctxt_switches: %llu", out) == 1) {
            rc = 0;
            break;
        }
    }
    fclose(f);
    return rc;
}

static double clamp_pct(double v)
{
    if (v < 0.0)   v = 0.0;
    if (v > 100.0) v = 100.0;
    return v;
}

static long online_cpus(void)
{
    long n = sysconf(_SC_NPROCESSORS_ONLN);
    return n < 1 ? 1 : n;
}

/* ==================================================================
 * Generic PSI metric (schedlat / psi_mem / psi_io share this core)
 * ================================================================== */

typedef struct {
    int                valid;
    unsigned long long prev_us;
    char               path[300];
} psi_state_t;

static int psi_seed(psi_state_t *s, const char *path)
{
    snprintf(s->path, sizeof(s->path), "%s", path);
    if (psi_some_total_us(s->path, &s->prev_us) != 0) return -1;
    s->valid = 1;
    return 0;
}

static int psi_sample(psi_state_t *s, metric_sample_t *out,
                      double interval_sec, const char *bid)
{
    if (!s->valid) return -1;
    unsigned long long cur = 0;
    if (psi_some_total_us(s->path, &cur) != 0) return -1;
    double d = (cur >= s->prev_us) ? (double)(cur - s->prev_us) : 0.0;
    s->prev_us = cur;
    double iv_us = interval_sec * 1.0e6;
    out->value      = (iv_us > 0.0) ? clamp_pct(d / iv_us * 100.0) : 0.0;
    out->status     = METRIC_STATUS_OK;
    out->backend_id = bid;
    out->note       = NULL;
    return 0;
}

/* Build a cgroup-relative PSI path, or "" if no cgroup target. */
static int cg_psi_path(const char *basename, char *out, size_t n)
{
    const intp_target_t *t = intp_target_get();
    if (!t || !t->cgroup_path) return -1;
    snprintf(out, n, "%s/%s", t->cgroup_path, basename);
    return access(out, R_OK) == 0 ? 0 : -1;
}

/* ---------------- schedlat (cpu.pressure / schedstat / /proc/pressure/cpu) ---- */

static psi_state_t schedlat_st;

static int schedlat_cg_probe(void)
{
    char p[300];
    return cg_psi_path("cpu.pressure", p, sizeof(p));
}
static int schedlat_cg_init(void)
{
    char p[300];
    if (cg_psi_path("cpu.pressure", p, sizeof(p)) != 0) return -1;
    return psi_seed(&schedlat_st, p);
}
static int schedlat_cg_read(metric_sample_t *out, double iv)
{
    return psi_sample(&schedlat_st, out, iv, "psi_cpu_cgroup");
}
static void schedlat_cg_cleanup(void) { schedlat_st.valid = 0; }

/* schedstat run-delay over the target's threads (no PSI dependency). This is
 * the PREFERRED schedlat backend because its scale matches the v3.3 eBPF
 * schedlat: Σ per-thread run-queue wait ÷ (interval × ncpus). The PSI
 * cpu.pressure backend below is a fallback only -- PSI 'some' is a
 * core-count-independent wall-clock stall FRACTION, a different (non-cored)
 * quantity that must not be mixed with this series in a cross-variant/cross-env
 * comparison. Per-TID, not per-TGID (C38; see the per-TID accounting block). */
static tidacc_t schedstat_acc;
static long     schedstat_ncpus;

static int schedlat_pid_probe(void)
{
    int capped;
    int n = collect_target_tids(tid_buf, INTP_MAX_TIDS, &capped);
    if (n <= 0) return -1;
    unsigned long long v;
    return read_tid_runqdelay(tid_buf[0], &v);   /* CONFIG_SCHEDSTATS present? */
}
static int schedlat_pid_init(void)
{
    if (tidacc_init(&schedstat_acc, read_tid_runqdelay) != 0) return -1;
    schedstat_ncpus = online_cpus();
    return 0;
}
static int schedlat_pid_read(metric_sample_t *out, double iv)
{
    if (!schedstat_acc.valid) return -1;
    unsigned long long d = 0;
    if (tidacc_scan(&schedstat_acc, read_tid_runqdelay, &d) != 0) return -1;
    double avail_ns = iv * 1.0e9 * (double)schedstat_ncpus;
    out->value      = (avail_ns > 0.0) ? clamp_pct((double)d / avail_ns * 100.0) : 0.0;
    out->status     = schedstat_acc.capped ? METRIC_STATUS_DEGRADED : METRIC_STATUS_OK;
    out->backend_id = "schedstat_pid";
    out->note       = schedstat_acc.capped ? "tid_cap" : NULL;
    return 0;
}
static void schedlat_pid_cleanup(void) { tidacc_free(&schedstat_acc); }

static int schedlat_sys_probe(void)
{
    return access("/proc/pressure/cpu", R_OK) == 0 ? 0 : -1;
}
static int schedlat_sys_init(void)
{
    return psi_seed(&schedlat_st, "/proc/pressure/cpu");
}
static int schedlat_sys_read(metric_sample_t *out, double iv)
{
    return psi_sample(&schedlat_st, out, iv, "psi_cpu_system");
}

static backend_t schedlat_cg = {
    .backend_id = "psi_cpu_cgroup",
    .description = "PSI cpu.pressure 'some' over the target cgroup",
    .probe = schedlat_cg_probe, .init = schedlat_cg_init,
    .read = schedlat_cg_read, .cleanup = schedlat_cg_cleanup,
};
static backend_t schedlat_pid = {
    .backend_id = "schedstat_pid",
    .description = "per-thread /proc/<tid>/schedstat run-queue wait",
    .probe = schedlat_pid_probe, .init = schedlat_pid_init,
    .read = schedlat_pid_read, .cleanup = schedlat_pid_cleanup,
};
static backend_t schedlat_sys = {
    .backend_id = "psi_cpu_system",
    .description = "system PSI /proc/pressure/cpu 'some'",
    .probe = schedlat_sys_probe, .init = schedlat_sys_init,
    .read = schedlat_sys_read, .cleanup = schedlat_cg_cleanup,
};
/* Order matters: schedstat (cored, eBPF-scale-consistent) is PREFERRED; the PSI
 * cpu.pressure backends are fallbacks whose 'some' stall fraction is on a
 * different (non-cored) scale and carry a distinct backend_id so the divergence
 * is visible in the output provenance (DESIGN §5.2; review fix). */
static metric_t schedlat_m = {
    .metric_name = "schedlat",
    .backends = { &schedlat_pid, &schedlat_cg, &schedlat_sys },
    .n_backends = 3,
};
metric_t *metric_schedlat(void) { return &schedlat_m; }

/* ---------------- psi_mem (memory.pressure / /proc/pressure/memory) ---------- */

static psi_state_t psi_mem_st;

static int psi_mem_cg_probe(void)  { char p[300]; return cg_psi_path("memory.pressure", p, sizeof(p)); }
static int psi_mem_cg_init(void)
{
    char p[300];
    if (cg_psi_path("memory.pressure", p, sizeof(p)) != 0) return -1;
    return psi_seed(&psi_mem_st, p);
}
static int psi_mem_cg_read(metric_sample_t *out, double iv) { return psi_sample(&psi_mem_st, out, iv, "psi_mem_cgroup"); }
static void psi_mem_cleanup(void) { psi_mem_st.valid = 0; }

static int psi_mem_sys_probe(void) { return access("/proc/pressure/memory", R_OK) == 0 ? 0 : -1; }
static int psi_mem_sys_init(void)  { return psi_seed(&psi_mem_st, "/proc/pressure/memory"); }
static int psi_mem_sys_read(metric_sample_t *out, double iv) { return psi_sample(&psi_mem_st, out, iv, "psi_mem_system"); }

static backend_t psi_mem_cg = {
    .backend_id = "psi_mem_cgroup", .description = "PSI memory.pressure 'some' over the target cgroup",
    .probe = psi_mem_cg_probe, .init = psi_mem_cg_init,
    .read = psi_mem_cg_read, .cleanup = psi_mem_cleanup,
};
static backend_t psi_mem_sys = {
    .backend_id = "psi_mem_system", .description = "system PSI /proc/pressure/memory 'some'",
    .probe = psi_mem_sys_probe, .init = psi_mem_sys_init,
    .read = psi_mem_sys_read, .cleanup = psi_mem_cleanup,
};
static metric_t psi_mem_m = {
    .metric_name = "psi_mem",
    .backends = { &psi_mem_cg, &psi_mem_sys },
    .n_backends = 2,
};
metric_t *metric_psi_mem(void) { return &psi_mem_m; }

/* ---------------- psi_io (io.pressure / /proc/pressure/io) ------------------- */

static psi_state_t psi_io_st;

static int psi_io_cg_probe(void)  { char p[300]; return cg_psi_path("io.pressure", p, sizeof(p)); }
static int psi_io_cg_init(void)
{
    char p[300];
    if (cg_psi_path("io.pressure", p, sizeof(p)) != 0) return -1;
    return psi_seed(&psi_io_st, p);
}
static int psi_io_cg_read(metric_sample_t *out, double iv) { return psi_sample(&psi_io_st, out, iv, "psi_io_cgroup"); }
static void psi_io_cleanup(void) { psi_io_st.valid = 0; }

static int psi_io_sys_probe(void) { return access("/proc/pressure/io", R_OK) == 0 ? 0 : -1; }
static int psi_io_sys_init(void)  { return psi_seed(&psi_io_st, "/proc/pressure/io"); }
static int psi_io_sys_read(metric_sample_t *out, double iv) { return psi_sample(&psi_io_st, out, iv, "psi_io_system"); }

static backend_t psi_io_cg = {
    .backend_id = "psi_io_cgroup", .description = "PSI io.pressure 'some' over the target cgroup",
    .probe = psi_io_cg_probe, .init = psi_io_cg_init,
    .read = psi_io_cg_read, .cleanup = psi_io_cleanup,
};
static backend_t psi_io_sys = {
    .backend_id = "psi_io_system", .description = "system PSI /proc/pressure/io 'some'",
    .probe = psi_io_sys_probe, .init = psi_io_sys_init,
    .read = psi_io_sys_read, .cleanup = psi_io_cleanup,
};
static metric_t psi_io_m = {
    .metric_name = "psi_io",
    .backends = { &psi_io_cg, &psi_io_sys },
    .n_backends = 2,
};
metric_t *metric_psi_io(void) { return &psi_io_m; }

/* ---------------- schedthr (cpu.stat throttled_usec, cgroup-only) ------------ */

static struct {
    int                valid;
    unsigned long long prev_us;
    char               path[300];
} schedthr_st;

static int schedthr_probe(void)
{
    const intp_target_t *t = intp_target_get();
    if (!t || !t->cgroup_path) return -1;   /* no system analogue */
    char p[300];
    snprintf(p, sizeof(p), "%s/cpu.stat", t->cgroup_path);
    unsigned long long v;
    return cpu_stat_throttled_us(p, &v) == 0 ? 0 : -1;
}
static int schedthr_init(void)
{
    const intp_target_t *t = intp_target_get();
    snprintf(schedthr_st.path, sizeof(schedthr_st.path), "%s/cpu.stat",
             t->cgroup_path);
    if (cpu_stat_throttled_us(schedthr_st.path, &schedthr_st.prev_us) != 0)
        return -1;
    schedthr_st.valid = 1;
    return 0;
}
static int schedthr_read(metric_sample_t *out, double iv)
{
    if (!schedthr_st.valid) return -1;
    unsigned long long cur = 0;
    if (cpu_stat_throttled_us(schedthr_st.path, &cur) != 0) return -1;
    double d = (cur >= schedthr_st.prev_us) ? (double)(cur - schedthr_st.prev_us) : 0.0;
    schedthr_st.prev_us = cur;
    double iv_us = iv * 1.0e6;
    out->value      = (iv_us > 0.0) ? clamp_pct(d / iv_us * 100.0) : 0.0;
    out->status     = METRIC_STATUS_OK;
    out->backend_id = "cpu.stat";
    out->note       = NULL;
    return 0;
}
static void schedthr_cleanup(void) { schedthr_st.valid = 0; }

static backend_t schedthr_b = {
    .backend_id = "cpu.stat", .description = "CFS throttled_usec over the target cgroup",
    .probe = schedthr_probe, .init = schedthr_init,
    .read = schedthr_read, .cleanup = schedthr_cleanup,
};
static metric_t schedthr_m = {
    .metric_name = "schedthr",
    .backends = { &schedthr_b },
    .n_backends = 1,
};
metric_t *metric_schedthr(void) { return &schedthr_m; }

/* ---------------- steal (/proc/stat field 8, VM-global) ---------------------- */

static struct {
    int                valid;
    unsigned long long prev_steal;
    unsigned long long prev_total;
} steal_st;

static int steal_probe(void)
{
    unsigned long long s, t;
    return proc_stat_steal(&s, &t) == 0 ? 0 : -1;
}
static int steal_init(void)
{
    if (proc_stat_steal(&steal_st.prev_steal, &steal_st.prev_total) != 0)
        return -1;
    steal_st.valid = 1;
    return 0;
}
static int steal_read(metric_sample_t *out, double iv)
{
    (void)iv;
    if (!steal_st.valid) return -1;
    unsigned long long cs = 0, ct = 0;
    if (proc_stat_steal(&cs, &ct) != 0) return -1;
    unsigned long long ds = (cs >= steal_st.prev_steal) ? cs - steal_st.prev_steal : 0;
    unsigned long long dt = (ct >= steal_st.prev_total) ? ct - steal_st.prev_total : 0;
    steal_st.prev_steal = cs;
    steal_st.prev_total = ct;
    out->value      = (dt > 0) ? clamp_pct((double)ds / (double)dt * 100.0) : 0.0;
    out->status     = METRIC_STATUS_OK;
    out->backend_id = "proc_stat";
    out->note       = NULL;
    return 0;
}
static void steal_cleanup(void) { steal_st.valid = 0; }

static backend_t steal_b = {
    .backend_id = "proc_stat", .description = "/proc/stat field 8 (hypervisor-stolen) %",
    .probe = steal_probe, .init = steal_init,
    .read = steal_read, .cleanup = steal_cleanup,
};
static metric_t steal_m = {
    .metric_name = "steal",
    .backends = { &steal_b },
    .n_backends = 1,
};
metric_t *metric_steal(void) { return &steal_m; }

/* ---------------- membw_est (LLC misses * 64B / interval -> MB/s) ------------ */

#define CACHELINE_BYTES 64.0

typedef struct {
    int      *fd_miss;
    uint64_t *prev_miss;
    int       n;
    int       valid;
    const char *bid;
} mbest_state_t;

static mbest_state_t mb;

static int mb_alloc(int n)
{
    mb.fd_miss   = calloc((size_t)n, sizeof(int));
    mb.prev_miss = calloc((size_t)n, sizeof(uint64_t));
    if (!mb.fd_miss || !mb.prev_miss) {
        free(mb.fd_miss);
        free(mb.prev_miss);
        mb.fd_miss = NULL;
        mb.prev_miss = NULL;
        return -1;
    }
    for (int i = 0; i < n; i++) mb.fd_miss[i] = -1;
    mb.n = n;
    return 0;
}
static void mb_free(void)
{
    if (mb.fd_miss) for (int i = 0; i < mb.n; i++) perfev_close(mb.fd_miss[i]);
    free(mb.fd_miss);
    free(mb.prev_miss);
    memset(&mb, 0, sizeof(mb));
}

/* membw_est does NOT reject ENV_VM: perfev_open_llc_cache* fall back to the
 * ARCHITECTURAL cache-misses event, which IS virtualized in a KVM guest (C26) --
 * so this is exactly the metric that recovers the memory-bandwidth dimension
 * in-guest where the LL-read llcmr cannot. */
static int mb_perf_ok(int need_sys)
{
    const system_capabilities_t *c = detect_cached();
    if (!c->perf_usable) return -1;
    if (need_sys && c->perf_paranoid > 0 && geteuid() != 0) return -1;
    if (!need_sys && c->perf_paranoid > 1 && geteuid() != 0) return -1;
    return 0;
}

/* cgroup-mode: one architectural/LL miss counter per online CPU. */
static int mb_cg_probe(void)
{
    const intp_target_t *t = intp_target_get();
    if (!t || !t->cgroup_path) return -1;
    if (mb_perf_ok(1) != 0) return -1;
    int fd = open(t->cgroup_path, O_RDONLY | O_DIRECTORY | O_CLOEXEC);
    if (fd < 0) return -1;
    close(fd);
    return 0;
}
static int mb_cg_init(void)
{
    const intp_target_t *t = intp_target_get();
    int cgfd = open(t->cgroup_path, O_RDONLY | O_DIRECTORY | O_CLOEXEC);
    if (cgfd < 0) return -1;
    long ncpu = online_cpus();
    if (mb_alloc((int)ncpu) != 0) { close(cgfd); return -1; }
    mb.bid = "membw_cgroup";
    int opened = 0;
    for (int cpu = 0; cpu < (int)ncpu; cpu++) {
        int loads = -1, miss = -1;
        if (perfev_open_llc_cache_cgroup(cgfd, cpu, &loads, &miss) != 0) {
            mb.fd_miss[cpu] = -1;
            continue;
        }
        perfev_close(loads);            /* membw_est needs misses only */
        mb.fd_miss[cpu] = miss;
        perfev_read(miss, &mb.prev_miss[cpu]);
        opened++;
    }
    close(cgfd);
    if (opened == 0) { mb_free(); return -1; }
    mb.valid = 1;
    return 0;
}

/* hwcache: per-PID (or system-wide on cpu 0) single miss counter. */
static int mb_hw_probe(void)
{
    const intp_target_t *t = intp_target_get();
    int need_sys = (t->n_pids == 0);
    return mb_perf_ok(need_sys);
}
static int mb_hw_init(void)
{
    const intp_target_t *t = intp_target_get();
    int n = t->n_pids > 0 ? t->n_pids : 1;
    if (mb_alloc(n) != 0) return -1;
    mb.bid = "perf_hwcache";
    for (int i = 0; i < n; i++) {
        pid_t pid = t->n_pids > 0 ? t->pids[i] : -1;
        int loads = -1, miss = -1;
        if (perfev_open_llc_cache(pid, &loads, &miss) != 0) { mb_free(); return -1; }
        perfev_close(loads);
        mb.fd_miss[i] = miss;
        perfev_read(miss, &mb.prev_miss[i]);
    }
    mb.valid = 1;
    return 0;
}

static int mb_read(metric_sample_t *out, double iv)
{
    if (!mb.valid) return -1;
    uint64_t miss_d = 0;
    for (int i = 0; i < mb.n; i++) {
        if (mb.fd_miss[i] < 0) continue;
        uint64_t m = 0;
        /* Only accumulate on a successful read, and clamp cur<prev (a failed
         * read or counter reset on an offlined CPU would otherwise underflow the
         * uint64 subtraction into a spurious ~2^64 spike). Mirrors v3.3's
         * counters_diff cur>=prev clamp. */
        if (perfev_read(mb.fd_miss[i], &m) == 0) {
            if (m >= mb.prev_miss[i]) miss_d += m - mb.prev_miss[i];
            mb.prev_miss[i] = m;
        }
    }
    double mbps = (iv > 0.0)
        ? (((double)miss_d * CACHELINE_BYTES) / iv) / 1.0e6 : 0.0;
    if (mbps < 0.0) mbps = 0.0;
    out->value      = mbps;       /* MB/s, NOT a percentage */
    out->status     = METRIC_STATUS_OK;
    out->backend_id = mb.bid;
    out->note       = NULL;
    return 0;
}
static void mb_cleanup(void) { mb_free(); }

static backend_t membw_est_cg = {
    .backend_id = "membw_cgroup",
    .description = "per-cgroup LLC misses * 64B / interval (cgroup-mode perf)",
    .probe = mb_cg_probe, .init = mb_cg_init,
    .read = mb_read, .cleanup = mb_cleanup,
};
static backend_t membw_est_hw = {
    .backend_id = "perf_hwcache",
    .description = "LLC misses * 64B / interval (per-PID / system perf)",
    .probe = mb_hw_probe, .init = mb_hw_init,
    .read = mb_read, .cleanup = mb_cleanup,
};
static metric_t membw_est_m = {
    .metric_name = "membw_est",
    .backends = { &membw_est_cg, &membw_est_hw },
    .n_backends = 2,
};
metric_t *metric_membw_est(void) { return &membw_est_m; }

/* ---------------- psp (involuntary preemption rate of the target's threads) - */
/* Not Volpert's PSP, which counts switches from an observed task to PID 0 as a
 * throttling indicator; the throttling guard here is schedthr. psp sums
 * nonvoluntary_ctxt_switches (/proc/<tid>/task/<tid>/status) over every thread
 * of the target; the per-interval per-TID delta / interval = involuntary
 * preemptions/s. Per-thread C-ABI analogue of v3.3's sched_switch
 * (prev-still-RUNNABLE) BPF counter. Scheduling-regime. */
static tidacc_t psp_acc;
static int psp_probe(void)
{
    int capped;
    int n = collect_target_tids(tid_buf, INTP_MAX_TIDS, &capped);
    if (n <= 0) return -1;
    unsigned long long v;
    return read_tid_nonvol(tid_buf[0], &v);
}
static int psp_init(void)
{
    return tidacc_init(&psp_acc, read_tid_nonvol);
}
static int psp_read(metric_sample_t *out, double iv)
{
    if (!psp_acc.valid) return -1;
    unsigned long long d = 0;
    if (tidacc_scan(&psp_acc, read_tid_nonvol, &d) != 0) return -1;
    out->value      = (iv > 0.0) ? (double)d / iv : 0.0;   /* preemptions / s */
    out->status     = psp_acc.capped ? METRIC_STATUS_DEGRADED : METRIC_STATUS_OK;
    out->backend_id = "nonvol_ctxt_pid";
    out->note       = psp_acc.capped ? "tid_cap" : NULL;
    return 0;
}
static void psp_cleanup(void) { tidacc_free(&psp_acc); }
static backend_t psp_pid = {
    .backend_id = "nonvol_ctxt_pid",
    .description = "per-thread /proc/<tid>/status nonvoluntary_ctxt_switches over target, ev/s",
    .probe = psp_probe, .init = psp_init, .read = psp_read, .cleanup = psp_cleanup,
};
static metric_t psp_m = {
    .metric_name = "psp",
    .backends = { &psp_pid },
    .n_backends = 1,
};
metric_t *metric_psp(void) { return &psp_m; }

/* ---------------- idle_preempt (idle-CPU takeover rate) --------------------- */
/* Not derivable per-process from /proc (idle is a global CPU concept); v3.3
 * measures it via the sched_switch BPF program. The probe always fails so the
 * metric reads "--" rather than a fake 0 -- honest unavailability on the C ABI. */
static int idle_preempt_probe(void) { return -1; }
static backend_t idle_preempt_none = {
    .backend_id = "unavailable",
    .description = "idle-CPU takeover rate -- eBPF-only (not derivable from /proc)",
    .probe = idle_preempt_probe,
    .init = NULL, .read = NULL, .cleanup = NULL,
};
static metric_t idle_preempt_m = {
    .metric_name = "idle_preempt",
    .backends = { &idle_preempt_none },
    .n_backends = 1,
};
metric_t *metric_idle_preempt(void) { return &idle_preempt_m; }

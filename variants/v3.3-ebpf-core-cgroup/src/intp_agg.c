/*
 * intp_agg.c -- userspace main for IntP V3.3 (eBPF/cgroup).
 *
 * V3.3 is the per-CGROUP sibling of V3.2. Like V3.2 there are no per-event
 * records: the kernel side accumulates everything into per-CPU (agg_global)
 * and per-cgroup (agg_per_cgroup) counter maps, and the main loop is just
 * "sleep --interval, read maps, compute deltas, emit one row." No
 * ring_buffer__poll, no event handler dispatch, no consumer-wakeup loop --
 * the structural change that eliminates V3's 188-390x context-switch
 * amplification (SBAC-PAD 2026 section V-D).
 *
 * The change from V3.2 is the ATTRIBUTION KEY (DESIGN §3, DECISIONS C1/C2):
 *   - --cgroup/--target-container PATH resolves to a cgroup-identity config
 *     {target_cgid = stat(PATH).st_ino, target_level = depth under
 *     /sys/fs/cgroup, exact_flag}, pushed into intp_cfg_map. No PID seed,
 *     no /proc descendant walk, migration-safe.
 *   - cgroup_skb ingress+egress are attached to the target cgroup fd for the
 *     canonical PER-CGROUP netp (C1) and the bytes(cg) numerator of the nets
 *     cost model (C2).
 *   - llcmr perf counters are opened in cgroup mode (PERF_FLAG_PID_CGROUP)
 *     bound to the target cgroup.
 *   - resctrl mon_group as in V3.2/v2.1 for mbw/llcocc.
 *
 * Canonical TSV column order (C5): netp nets blk mbw llcmr llcocc cpu, then
 * the trailing DIAGNOSTIC columns netp_dev, nets_sys, mbw_raw_mbps, blk_MBps
 * -- ALL suppressed by --no-diag-cols.
 *
 * VM mode (DESIGN §8.1, C1): --target-vm/--tap-iface sources canonical netp
 * from the host tap iface /sys/class/net/<tap>/statistics (mirrors v2.1's
 * stable-ABI b_tap path) instead of cgroup_skb, which cannot see guest
 * traffic. The full tc/XDP-on-tap path is the remote-validated enhancement.
 */

#include <bpf/bpf.h>
#include <bpf/libbpf.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <linux/perf_event.h>
#include <dirent.h>
#include <math.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <time.h>
#include <unistd.h>

#include "intp_agg.bpf.h"
#include "intp_agg.skel.h"
#include "intp_agg_args.h"

#include "../detect/detect.h"
#include "../resctrl/resctrl.h"

#define GROUP_NAME       "intp-v3.3"
#define CGROUP_ROOT      "/sys/fs/cgroup"

static volatile sig_atomic_t g_running = 1;
static void on_signal(int sig) { (void)sig; g_running = 0; }

/* ------------------------------------------------------------------ cgroup identity */

/* Resolve a cgroup directory path to its cgroup v2 id (== directory inode)
 * and its depth under /sys/fs/cgroup (for the ancestor gate). Returns 0 on
 * success. The kernfs id bpf_get_current_cgroup_id() returns equals st_ino
 * for cgroup v2 (DESIGN §3). */
static int resolve_cgroup_identity(const char *path, __u64 *out_cgid,
                                   __u32 *out_level)
{
    struct stat st;
    if (stat(path, &st) != 0) return -1;
    /* target_cgid comes from stat() on the (possibly non-canonical) input
     * path: stat() already follows symlinks, so st_ino is the real cgroup v2
     * inode regardless of how the path was spelled. Exact-mode gating relies
     * only on this and is therefore robust even if canonicalization below
     * fails or the resolved path is outside the cgroup root. */
    *out_cgid = (__u64)st.st_ino;

    /* Canonicalize before counting components: realpath() resolves symlinks,
     * trailing slashes, and . / .. so the ancestor LEVEL is counted against
     * the true path, not a non-canonical spelling that would miscount the
     * depth and make bpf_get_current_ancestor_cgroup_id(level) walk to the
     * wrong ancestor (FIX 4). */
    char resolved[PATH_MAX];
    const char *count_path;
    if (realpath(path, resolved) != NULL) {
        count_path = resolved;
        /* Verify the resolved path lives under the cgroup v2 root. On a
         * mismatch we cannot trust the ancestor depth, so fall back to
         * exact-mode semantics (target_cgid still resolves via st_ino). */
        const char *root = CGROUP_ROOT;
        size_t rlen = strlen(root);
        if (strncmp(resolved, root, rlen) != 0 ||
            (resolved[rlen] != '\0' && resolved[rlen] != '/')) {
            fprintf(stderr,
                "warning: cgroup path '%s' resolves to '%s' which is not under "
                "%s -- using exact-match (leaf) semantics\n",
                path, resolved, root);
            *out_level = 0;
            return 0;
        }
    } else {
        /* realpath failed (e.g. EACCES on an intermediate component);
         * count against the raw input, which still works for canonical
         * paths and degrades gracefully otherwise. */
        count_path = path;
    }

    /* depth = number of path components strictly under /sys/fs/cgroup.
     * e.g. /sys/fs/cgroup            -> level 0 (root)
     *      /sys/fs/cgroup/foo        -> level 1
     *      /sys/fs/cgroup/foo/bar    -> level 2
     * bpf_get_current_ancestor_cgroup_id(level) walks to that depth. */
    const char *root = CGROUP_ROOT;
    size_t rlen = strlen(root);
    const char *p = count_path;
    /* skip a leading prefix equal to the cgroup root if present */
    if (strncmp(count_path, root, rlen) == 0) p = count_path + rlen;
    __u32 level = 0;
    while (*p) {
        while (*p == '/') p++;
        if (!*p) break;
        level++;
        while (*p && *p != '/') p++;
    }
    *out_level = level;
    return 0;
}

/* ------------------------------------------------------------------ VM tap netp (stable-ABI) */

/* VM mode netp source -- mirror of v2.1's b_tap working path: read the host
 * tap/vnet iface byte counters from /sys/class/net/<tap>/statistics. The
 * cgroup_skb programs cannot see guest traffic (it crosses a tap, not a
 * cgroup socket), so for --target-vm/--tap-iface we substitute this for the
 * canonical netp. Returns 0 and sets *out_total on success. */
static int tap_total_bytes(const char *tap, unsigned long long *out_total)
{
    char p[160];
    unsigned long long tx = 0, rx = 0;
    FILE *f;

    snprintf(p, sizeof(p), "/sys/class/net/%.63s/statistics/tx_bytes", tap);
    f = fopen(p, "r");
    if (!f) return -1;
    if (fscanf(f, "%llu", &tx) != 1) { fclose(f); return -1; }
    fclose(f);

    snprintf(p, sizeof(p), "/sys/class/net/%.63s/statistics/rx_bytes", tap);
    f = fopen(p, "r");
    if (!f) return -1;
    if (fscanf(f, "%llu", &rx) != 1) { fclose(f); return -1; }
    fclose(f);

    *out_total = tx + rx;
    return 0;
}

/* ------------------------------------------------------------------ VM-portable metric file reads (C26) */

/* All four below are pure file reads computed by the GUEST'S OWN kernel, so
 * they survive inside a stock KVM guest where resctrl/RDT (mbw/llcocc) and the
 * LL-read PMU events (llcmr) do not (DESIGN §10). They feed the --portable-metrics
 * block only; the canonical 7 never touch them. membw_est is computed from the
 * existing llc_misses BPF counter in the main loop, not here. */

/* PSI 'some' cumulative stall time (microseconds) from the total= field of the
 * 'some' line. Path is a cgroup pressure file (<cg>/memory.pressure,
 * <cg>/io.pressure) or the system /proc/pressure fallback. 0 on success. */
static int read_psi_some_total_us(const char *path, unsigned long long *out)
{
    FILE *f = fopen(path, "r");
    if (!f) return -1;
    char line[256];
    int rc = -1;
    while (fgets(line, sizeof(line), f)) {
        if (strncmp(line, "some", 4) != 0) continue;
        char *p = strstr(line, "total=");
        if (p && sscanf(p + 6, "%llu", out) == 1) rc = 0;
        break;   /* 'some' is the first line; 'full' is not used here */
    }
    fclose(f);
    return rc;
}

/* CFS-bandwidth throttled time (microseconds) from a cgroup cpu.stat. Absent
 * when no cpu.max quota is set (no throttled_usec line) -> returns -1. */
static int read_cpu_stat_throttled_us(const char *path, unsigned long long *out)
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

/* /proc/stat aggregate cpu line: *steal = field 8 (hypervisor-stolen jiffies,
 * the 8th value after the 'cpu' label: user nice system idle iowait irq softirq
 * STEAL ...), *total = sum of all fields. VM-global, not cgroup-scoped, so 0 on
 * bare/container. 0 on success. */
static int read_proc_stat_steal(unsigned long long *steal,
                                unsigned long long *total)
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
            *steal = v[7];
            *total = t;
            rc = 0;
        }
    }
    fclose(f);
    return rc;
}

/* ------------------------------------------------------------------ perf_event for llcmr */

typedef struct {
    int *fds;
    int  n_fds;
    struct bpf_link **links;
} perf_attach_t;

static long sys_perf_event_open(struct perf_event_attr *a,
                                pid_t pid, int cpu, int group_fd,
                                unsigned long flags)
{
    return syscall(__NR_perf_event_open, a, pid, cpu, group_fd, flags);
}

/* Open one HW_CACHE_LL counter per CPU and attach prog to each. When
 * cgroup_fd >= 0 the counter is opened in cgroup mode (PERF_FLAG_PID_CGROUP,
 * pid==cgroup_fd) so it only accrues while a task of that cgroup is on-CPU
 * -- the per-cgroup llcmr attribution (DESIGN §4). Otherwise it is opened
 * system-wide (pid=-1), matching V3.2. */
static int open_cache_counters(struct bpf_program *prog,
                               unsigned long cache_result,
                               perf_attach_t *out,
                               int n_cpus, int cgroup_fd, int verbose)
{
    out->fds   = calloc((size_t)n_cpus, sizeof(int));
    out->links = calloc((size_t)n_cpus, sizeof(struct bpf_link *));
    out->n_fds = 0;
    if (!out->fds || !out->links) return -1;

    struct perf_event_attr attr;
    memset(&attr, 0, sizeof(attr));
    attr.type   = PERF_TYPE_HW_CACHE;
    attr.size   = sizeof(attr);
    attr.config = (PERF_COUNT_HW_CACHE_LL)
                | (PERF_COUNT_HW_CACHE_OP_READ << 8)
                | (cache_result << 16);
    /* Match V3: sample_period 1000 so even ~1k LLC events/sec trigger at
     * least one BPF invocation per interval. The kernel-side increment
     * scales by sample_period so the absolute count stays correct. */
    attr.sample_period = 1000;
    attr.wakeup_events = 1;
    attr.disabled      = 0;

    pid_t pid_arg        = cgroup_fd >= 0 ? (pid_t)cgroup_fd : -1;
    unsigned long flags  = cgroup_fd >= 0 ? PERF_FLAG_PID_CGROUP : 0UL;

    /* vm-guest fallback (C25/P5): the model-specific LL-read events are <not
     * supported> under a KVM vPMU even with pmu=on, while the ARCHITECTURAL
     * PERF_COUNT_HW_CACHE_REFERENCES/_MISSES are virtualized (and match the W4
     * ground-truth). Probe the LL event on cpu 0; if it cannot open, switch all
     * CPUs to the architectural event (raise sample_period: it is much higher
     * rate, and the BPF side scales by the period so counts stay correct).
     * bare/host keeps the LL events -- the probe succeeds there. */
    {
        int probe = (int)sys_perf_event_open(&attr, pid_arg, 0, -1, flags);
        if (probe < 0) {
            attr.type   = PERF_TYPE_HARDWARE;
            attr.config = (cache_result == PERF_COUNT_HW_CACHE_RESULT_MISS)
                        ? PERF_COUNT_HW_CACHE_MISSES
                        : PERF_COUNT_HW_CACHE_REFERENCES;
            attr.sample_period = 100000;
            if (verbose)
                fprintf(stderr, "warn: HW_CACHE LL perf unsupported (vPMU?); "
                        "using architectural cache %s\n",
                        cache_result == PERF_COUNT_HW_CACHE_RESULT_MISS
                        ? "misses" : "references");
        } else {
            close(probe);
        }
    }

    int opened = 0;
    for (int cpu = 0; cpu < n_cpus; cpu++) {
        int fd = (int)sys_perf_event_open(&attr, pid_arg, cpu, -1, flags);
        if (fd < 0) {
            if (verbose)
                fprintf(stderr,
                        "warn: perf_event_open on cpu %d failed: %s\n",
                        cpu, strerror(errno));
            continue;
        }
        struct bpf_link *link = bpf_program__attach_perf_event(prog, fd);
        if (!link) {
            if (verbose)
                fprintf(stderr,
                        "warn: attach perf_event on cpu %d failed: %s\n",
                        cpu, strerror(errno));
            close(fd);
            continue;
        }
        out->fds[opened]   = fd;
        out->links[opened] = link;
        opened++;
    }
    out->n_fds = opened;
    return opened > 0 ? 0 : -1;
}

static void close_cache_counters(perf_attach_t *p)
{
    if (!p) return;
    for (int i = 0; i < p->n_fds; i++) {
        if (p->links[i]) bpf_link__destroy(p->links[i]);
        if (p->fds[i] >= 0) close(p->fds[i]);
    }
    free(p->fds);
    free(p->links);
    p->fds = NULL;
    p->links = NULL;
    p->n_fds = 0;
}

/* ------------------------------------------------------------------ cgroup -> PID list */

/* Used only for the resctrl mon_group PID assignment (mbw/llcocc), which is
 * RDT, not eBPF (DESIGN §4). The eBPF gate no longer needs a PID list. */
/* Read cgroup.procs of `dir` AND, recursively, of every descendant cgroup.
 * cgroup v2's "no internal processes" rule means a PARENT cgroup whose children
 * hold the tasks has an EMPTY cgroup.procs. An incus/LXD system container puts
 * its PIDs in lxc.payload.<n>/init.scope (+ exec scopes), not in the top
 * lxc.payload.<n> the harness targets -> a non-recursive read of that parent
 * seeds NOTHING, so the resctrl mon_group gets no tasks and llcocc/mbw read 0
 * (docker/k8s targets are leaf scopes, so they were unaffected). Recursing fixes
 * the seed; resctrl_assign_pid_threads' /proc descendant walk still expands the
 * process tree. */
static int read_cgroup_pids_rec(const char *dir, pid_t *out, int max, int n)
{
    char path[512];
    snprintf(path, sizeof(path), "%s/cgroup.procs", dir);
    FILE *f = fopen(path, "r");
    if (f) {
        int pid;
        while (n < max && fscanf(f, "%d", &pid) == 1) out[n++] = (pid_t)pid;
        fclose(f);
    }
    DIR *d = opendir(dir);
    if (d) {
        struct dirent *e;
        while (n < max && (e = readdir(d)) != NULL) {
            /* Skip only '.'/'..' -- NOT all dot-prefixed names: incus runs the
             * container payload in a child cgroup literally named '.lxc', which
             * holds the workload's processes. Skipping it (the previous
             * d_name[0]=='.' test) missed every stress-ng worker -> llcocc 0. */
            if (!strcmp(e->d_name, ".") || !strcmp(e->d_name, "..")) continue;
            /* cgroupfs (kernfs) can report d_type as DT_UNKNOWN, so stat() to
             * detect child cgroups instead of trusting d_type. */
            char sub[512];
            struct stat stb;
            if ((size_t)snprintf(sub, sizeof(sub), "%s/%s", dir, e->d_name) >= sizeof(sub))
                continue;
            if (stat(sub, &stb) == 0 && S_ISDIR(stb.st_mode))
                n = read_cgroup_pids_rec(sub, out, max, n);
        }
        closedir(d);
    }
    return n;
}

static int read_cgroup_pids(const char *cgroup, pid_t *out, int max)
{
    return read_cgroup_pids_rec(cgroup, out, max, 0);
}

/* ------------------------------------------------------------------ aggregate snapshot */

/* Sum a per-cgroup HASH value (one struct per CPU) into out. */
static void accumulate_percpu(struct intp_counters *out,
                              const struct intp_counters *per_cpu, int n_cpus)
{
    for (int i = 0; i < n_cpus; i++) {
        out->netp_tx_bytes      += per_cpu[i].netp_tx_bytes;
        out->netp_rx_bytes      += per_cpu[i].netp_rx_bytes;
        out->netp_dev_tx_bytes  += per_cpu[i].netp_dev_tx_bytes;
        out->netp_dev_rx_bytes  += per_cpu[i].netp_dev_rx_bytes;
        out->nets_tx_lat_ns_sum += per_cpu[i].nets_tx_lat_ns_sum;
        out->nets_tx_lat_n      += per_cpu[i].nets_tx_lat_n;
        out->nets_rx_lat_ns_sum += per_cpu[i].nets_rx_lat_ns_sum;
        out->nets_rx_lat_n      += per_cpu[i].nets_rx_lat_n;
        out->blk_svctm_ns_sum   += per_cpu[i].blk_svctm_ns_sum;
        out->blk_ops            += per_cpu[i].blk_ops;
        out->blk_bytes          += per_cpu[i].blk_bytes;
        out->cpu_on_ns_sum      += per_cpu[i].cpu_on_ns_sum;
        out->llc_refs           += per_cpu[i].llc_refs;
        out->llc_misses         += per_cpu[i].llc_misses;
        out->schedlat_wait_ns_sum += per_cpu[i].schedlat_wait_ns_sum;
    }
}

/* Read agg_global (PERCPU_ARRAY[key=0]) across all CPUs and sum into out.
 * agg_global carries host-wide totals: system-wide softirq nets (nets_sys),
 * device-level netp_dev, and bytes_total (netp_tx/rx). */
static int read_global_aggregate(struct intp_agg_bpf *skel,
                                 struct intp_counters *out)
{
    int n_cpus = libbpf_num_possible_cpus();
    if (n_cpus <= 0) return -1;

    struct intp_counters *per_cpu = calloc((size_t)n_cpus, sizeof(*per_cpu));
    if (!per_cpu) return -1;

    __u32 key = 0;
    int fd = bpf_map__fd(skel->maps.agg_global);
    if (bpf_map_lookup_elem(fd, &key, per_cpu) != 0) {
        free(per_cpu);
        return -1;
    }

    memset(out, 0, sizeof(*out));
    accumulate_percpu(out, per_cpu, n_cpus);
    free(per_cpu);
    return 0;
}

/* Read agg_per_cgroup[cgid] (a plain HASH, single struct per key) into out.
 * Returns 0 on success, -1 if the slot does not yet exist (no events charged
 * to the target cgroup this run -> caller treats as all-zero). */
static int read_per_cgroup_aggregate(struct intp_agg_bpf *skel, __u64 cgid,
                                     struct intp_counters *out)
{
    memset(out, 0, sizeof(*out));
    int fd = bpf_map__fd(skel->maps.agg_per_cgroup);
    if (bpf_map_lookup_elem(fd, &cgid, out) != 0)
        return -1;   /* not created yet; out already zeroed */
    return 0;
}

/* delta = cur - prev, field-by-field, saturating on underflow (can happen if
 * cur was read while a probe was mid-add on another CPU -- extremely rare in
 * practice; saturate to 0 instead of wrapping). Covers every intp_counters
 * field, including the V3.3 netp_dev diagnostics. */
static void counters_diff(const struct intp_counters *cur,
                          const struct intp_counters *prev,
                          struct intp_counters *delta)
{
#define SUB(field) \
    delta->field = (cur->field >= prev->field) ? (cur->field - prev->field) : 0
    SUB(netp_tx_bytes);
    SUB(netp_rx_bytes);
    SUB(netp_dev_tx_bytes);
    SUB(netp_dev_rx_bytes);
    SUB(nets_tx_lat_ns_sum);
    SUB(nets_tx_lat_n);
    SUB(nets_rx_lat_ns_sum);
    SUB(nets_rx_lat_n);
    SUB(blk_svctm_ns_sum);
    SUB(blk_ops);
    SUB(blk_bytes);
    SUB(cpu_on_ns_sum);
    SUB(llc_refs);
    SUB(llc_misses);
    SUB(schedlat_wait_ns_sum);
#undef SUB
}

/* ------------------------------------------------------------------ metric math */

typedef struct {
    /* 7 canonical (C5 order). */
    double netp;
    double nets;
    double blk;
    double mbw;          /* % normalized */
    double llcmr;
    double llcocc;
    double cpu;
    /* trailing diagnostics (C1/C2/C5). */
    double netp_dev;     /* device-level host-wide netp % (v3.2 cross-check) */
    double nets_sys;     /* system-wide softirq nets % (v2.1/v3.2 parity)    */
    double mbw_raw_mbps; /* raw MB/s (v3.2 diagnostic)                       */
    double blk_MBps;     /* per-cgroup block I/O throughput MB/s, bio-owner  */
                         /* (writeback-correct) from blk_bytes (FIX 1)       */
    /* ---- VM-portable block (--portable-metrics, C26 / DESIGN §10). ----
     * A SEPARATE flag-gated benchmark; the canonical 7 above and the diag
     * columns stay untouched. NaN = the source is unavailable on this host
     * (e.g. CONFIG_PSI=n, or no cgroup target for schedthr) -> emitted "--",
     * never a fake 0. schedlat moved here from the diag block. */
    double schedlat;     /* run-queue (scheduling) latency %, eBPF           */
                         /* sched_wakeup->sched_switch (Volpert PSL)         */
    double psi_mem;      /* PSI memory.pressure 'some', %-of-interval        */
    double membw_est;    /* DRAM-bandwidth estimate, MB/s: llc_misses*64B    */
                         /* /interval (mbw complement; in-guest portable)    */
    double psi_io;       /* PSI io.pressure 'some', %-of-interval            */
    double schedthr;     /* CFS throttling: cpu.stat throttled_usec %        */
                         /* (confound guard, not a contention signal)        */
    double steal;        /* hypervisor-stolen vCPU %, /proc/stat field 8     */
                         /* (VM-global; 0 on bare/container)                 */
} intp_sample_t;

static double safe_pct(double num, double den)
{
    if (den <= 0.0) return 0.0;
    double p = num / den * 100.0;
    if (p < 0.0)   p = 0.0;
    if (p > 100.0) p = 100.0;
    return p;
}

/* Portable %-of-interval delta: (cur-prev) cumulative microseconds over the
 * interval microseconds, 0-100 (safe_pct caps). Used by psi_mem/psi_io/schedthr. */
static double port_pct(unsigned long long cur, unsigned long long prev,
                       double interval_us)
{
    double d = (cur >= prev) ? (double)(cur - prev) : 0.0;
    return safe_pct(d, interval_us);
}

/* compute_sample -- d_cg is the per-cgroup delta (canonical netp/blk/llcmr/cpu),
 * d_glob is the host-wide delta (nets_sys numerator, bytes_total denominator,
 * netp_dev diagnostic). vm_netp_pct >= 0 overrides the canonical netp with the
 * VM tap-iface reading (DESIGN §8.1 / C1). */
static void compute_sample(const struct intp_counters *d_cg,
                           const struct intp_counters *d_glob,
                           const system_capabilities_t *caps,
                           double interval_sec,
                           int num_cores,
                           double vm_netp_pct,
                           intp_sample_t *out)
{
    memset(out, 0, sizeof(*out));

    long max_nic = caps->nic_speed_bps > 0 ? caps->nic_speed_bps : 125000000L;
    double interval_ns = interval_sec * 1e9;

    /* --- canonical netp: per-cgroup cgroup_skb bytes (C1), or VM tap. ---
     * Read from agg_global (d_glob): cgroup_skb is attached ONLY to the target
     * cgroup, so agg_global.netp_* == the target's bytes, and the BPF side no
     * longer keeps a per-packet per-cgroup HASH netp counter (membw_est fidelity
     * fix -- see intp_agg.bpf.c cg_skb_egress; d_cg->netp_* is no longer set). */
    if (vm_netp_pct >= 0.0) {
        out->netp = vm_netp_pct;
    } else {
        double cg_bps =
            (double)(d_glob->netp_tx_bytes + d_glob->netp_rx_bytes) / interval_sec;
        out->netp = safe_pct(cg_bps, (double)max_nic);
    }

    /* --- canonical nets: PROXY = nets_sys * bytes(cg) / bytes_total (C2). ---
     * nets_sys is the system-wide softirq fraction; we scale it by the
     * cgroup's share of host-wide bytes. This is an explicit PROXY that MIXES
     * byte LEVELS: the numerator is per-cgroup SOCKET bytes (cgroup_skb tx+rx,
     * d_cg->netp_*), while the denominator is host-wide DEVICE bytes
     * (netp_dev tx+rx from net_dev_xmit/netif_receive_skb, d_glob->netp_dev_*).
     * The cgroup_skb programs are attached ONLY to the target cgroup, so
     * d_glob->netp_* equals the target's socket bytes (share would be ~1.0 and
     * misattribute all system softirq to one cgroup); the host-wide device
     * counters are the correct denominator. Validated on the remote against a
     * two-cgroup iperf3 ground truth (W3). Falls back to 0 when no device
     * bytes were observed host-wide this interval. */
    double net_lat_total =
        (double)(d_glob->nets_tx_lat_ns_sum + d_glob->nets_rx_lat_ns_sum);
    double nets_sys_pct = safe_pct(net_lat_total, interval_ns);
    out->nets_sys = nets_sys_pct;

    double bytes_cg    = (double)(d_glob->netp_tx_bytes + d_glob->netp_rx_bytes);
    double bytes_total =
        (double)(d_glob->netp_dev_tx_bytes + d_glob->netp_dev_rx_bytes);
    double share = (bytes_total > 0.0) ? (bytes_cg / bytes_total) : 0.0;
    if (share < 0.0) share = 0.0;
    if (share > 1.0) share = 1.0;
    out->nets = nets_sys_pct * share;

    /* --- canonical blk: %-of-interval svctm (C7), per-cgroup. --- */
    out->blk = safe_pct((double)d_cg->blk_svctm_ns_sum, interval_ns);

    /* --- diagnostic blk_MBps: per-cgroup block I/O THROUGHPUT (FIX 1). ---
     * Surfaces the bio-owner (writeback-correct) blk_bytes the kernel side
     * accumulates from block_rq_complete (current-task gate) plus the
     * tp_btf/block_bio_complete bio-owner top-up. Distinct from the canonical
     * blk (svctm %, C7, unchanged): this is volume, MB/s. */
    out->blk_MBps =
        (interval_sec > 0.0)
            ? ((double)d_cg->blk_bytes / interval_sec) / 1e6
            : 0.0;

    /* --- canonical cpu: per-cgroup on-CPU ns / (interval * cores). --- */
    double cpu_ns_available = interval_ns * (num_cores > 0 ? num_cores : 1);
    out->cpu = safe_pct((double)d_cg->cpu_on_ns_sum, cpu_ns_available);

    /* --- schedlat: per-cgroup run-queue wait, %-of-capacity (C26). The BPF
     * tp_schedlat program sums the incoming task's wakeup->dispatch wait into
     * d_cg->schedlat_wait_ns_sum; normalize against the same core-seconds
     * budget as cpu so the two share IntP's 0-100 scale. VM-portable. --- */
    out->schedlat = safe_pct((double)d_cg->schedlat_wait_ns_sum, cpu_ns_available);

    /* --- canonical llcmr: per-cgroup LLC miss ratio % (C7). --- */
    out->llcmr = safe_pct((double)d_cg->llc_misses, (double)d_cg->llc_refs);

    /* --- diagnostic netp_dev: device-level host-wide rate (C1). --- */
    double dev_bps =
        (double)(d_glob->netp_dev_tx_bytes + d_glob->netp_dev_rx_bytes)
        / interval_sec;
    out->netp_dev = safe_pct(dev_bps, (double)max_nic);

    /* mbw / llcocc / mbw_raw_mbps filled by caller (resctrl handle). */
}

/* ------------------------------------------------------------------ output */

static void emit_tsv_header(FILE *out,
                            const system_capabilities_t *caps,
                            int no_perf, int no_resctrl,
                            int no_diag_cols, int clip_mbw,
                            int vm_mode, int portable)
{
    /* Per-metric backend map + nets PROXY provenance (C2). */
    fprintf(out,
        "# v3.3 ebpf-core-cgroup -- netp:%s nets:cost-model[skb-share]PROXY"
        " blk:tracepoint[bio-blkcg] cpu:sched_switch[cgroup]"
        " llcmr:%s mbw:%s llcocc:%s\n",
        vm_mode ? "tap-iface[sysfs]" : "cgroup_skb",
        no_perf     ? "off" : "perf_event[cgroup-mode]",
        no_resctrl  ? "off" : "resctrl[mon_group]",
        no_resctrl  ? "off" : "resctrl[mon_group]");
    fprintf(out, "# kernel %d.%d env=%s\n",
            caps->kernel_major, caps->kernel_minor,
            caps->env == ENV_CONTAINER ? "container" :
            caps->env == ENV_VM        ? "vm" : "bare-metal");
    fprintf(out, "# nets = nets_sys * bytes(cgroup)/bytes_total "
                 "(PROXY: byte-share cost model, DESIGN §5; see nets_sys "
                 "diagnostic column for the system-wide softirq value)\n");
    fprintf(out, "# mbw_pct = (mbm_total_bytes_delta / interval) / "
                 "mem_bw_max_bps * 100  (clip_mbw=%s)\n",
            clip_mbw ? "on (legacy V3 cap-at-99)" : "off (raw, may exceed 100)");
    if (!no_diag_cols)
        fprintf(out, "# diagnostic trailing columns: netp_dev (device-level "
                     "host-wide netp %%, v3.2 cross-check), nets_sys "
                     "(system-wide softirq %%, v2.1/v3.2 parity), mbw_raw_mbps "
                     "(raw MB/s), blk_MBps (per-cgroup block I/O throughput "
                     "MB/s, bio-owner / writeback-correct from blk_bytes)\n");
    if (portable)
        fprintf(out, "# portable trailing columns (--portable-metrics, C26 / "
                     "DESIGN §10; SEPARATE benchmark, canonical 7 untouched): "
                     "schedlat (run-queue wait %%, eBPF sched_wakeup->sched_switch), "
                     "psi_mem (memory.pressure some %%), membw_est (DRAM-bandwidth "
                     "estimate MB/s = llc_misses*64B/interval), psi_io (io.pressure "
                     "some %%), schedthr (cpu.stat throttled %%), steal (/proc/stat "
                     "field 8 %%, VM-global) -- '--' where the source is unavailable\n");

    /* Column header: 7 canonical [+ 4 diag] [+ 6 portable]. */
    fprintf(out, "netp\tnets\tblk\tmbw\tllcmr\tllcocc\tcpu");
    if (!no_diag_cols)
        fprintf(out, "\tnetp_dev\tnets_sys\tmbw_raw_mbps\tblk_MBps");
    if (portable)
        fprintf(out, "\tschedlat\tpsi_mem\tmembw_est\tpsi_io\tschedthr\tsteal");
    fprintf(out, "\n");
    fflush(out);
}

/* Format one canonical metric cell: "--" when the metric is unavailable
 * (NaN sentinel, e.g. resctrl mbw/llcocc inside a stock KVM guest where RDT is
 * host-only) instead of a fake "00". The (int) cast runs only for finite
 * values, so NaN never reaches the conversion. "--" matches the missing-value
 * token stage_report and the cross-env layer already expect. */
static const char *metric_cell(char *buf, size_t n, double v)
{
    if (isnan(v)) snprintf(buf, n, "--");
    else          snprintf(buf, n, "%02d", (int)(v + 0.5));
    return buf;
}

/* Portable %-of-interval cell (schedlat/psi_mem/psi_io/schedthr/steal): "--"
 * for NaN (source unavailable, e.g. CONFIG_PSI=n), rounded 0-100 otherwise. */
static void pcell_pct(char *buf, size_t n, double v)
{
    if (isnan(v)) snprintf(buf, n, "--");
    else          snprintf(buf, n, "%d", (int)(v + 0.5));
}

/* Portable rate cell (membw_est, MB/s): "--" for NaN, rounded MB/s otherwise.
 * Not a percent -- the bandwidth dimension psi_mem is blind to (DESIGN §10). */
static void pcell_rate(char *buf, size_t n, double v)
{
    if (isnan(v)) snprintf(buf, n, "--");
    else          snprintf(buf, n, "%.0f", v);
}

/* Emit the 6 VM-portable cells in canonical order (DESIGN §10):
 * schedlat psi_mem membw_est psi_io schedthr steal. */
static void emit_portable_tsv_cells(FILE *out, const intp_sample_t *s)
{
    char a[16], b[16], c[16], d[16], e[16], f[16];
    pcell_pct (a, sizeof a, s->schedlat);
    pcell_pct (b, sizeof b, s->psi_mem);
    pcell_rate(c, sizeof c, s->membw_est);
    pcell_pct (d, sizeof d, s->psi_io);
    pcell_pct (e, sizeof e, s->schedthr);
    pcell_pct (f, sizeof f, s->steal);
    fprintf(out, "\t%s\t%s\t%s\t%s\t%s\t%s", a, b, c, d, e, f);
}

static void emit_tsv(FILE *out, const intp_sample_t *s, int no_diag_cols,
                     int portable)
{
    char c0[8], c1[8], c2[8], c3[8], c4[8], c5[8], c6[8];
    fprintf(out, "%s\t%s\t%s\t%s\t%s\t%s\t%s",
            metric_cell(c0, sizeof c0, s->netp),
            metric_cell(c1, sizeof c1, s->nets),
            metric_cell(c2, sizeof c2, s->blk),
            metric_cell(c3, sizeof c3, s->mbw),
            metric_cell(c4, sizeof c4, s->llcmr),
            metric_cell(c5, sizeof c5, s->llcocc),
            metric_cell(c6, sizeof c6, s->cpu));
    if (!no_diag_cols)
        fprintf(out, "\t%02d\t%02d\t%.0f\t%.2f",
                (int)(s->netp_dev + 0.5),
                (int)(s->nets_sys + 0.5),
                s->mbw_raw_mbps,
                s->blk_MBps);
    if (portable)
        emit_portable_tsv_cells(out, s);
    fputc('\n', out);
    fflush(out);
}

/* JSON number that renders NaN as null (portable sources may be unavailable). */
static void json_num(FILE *out, double v)
{
    if (isnan(v)) fprintf(out, "null");
    else          fprintf(out, "%.2f", v);
}

static void emit_json(FILE *out, const intp_sample_t *s, double t_sec,
                      int no_diag_cols, int portable)
{
    fprintf(out,
        "{\"t\":%.3f,\"netp\":%.2f,\"nets\":%.2f,\"blk\":%.2f,"
        "\"mbw\":%.2f,\"llcmr\":%.2f,\"llcocc\":%.2f,\"cpu\":%.2f",
        t_sec, s->netp, s->nets, s->blk, s->mbw, s->llcmr, s->llcocc, s->cpu);
    if (!no_diag_cols)
        fprintf(out,
            ",\"netp_dev\":%.2f,\"nets_sys\":%.2f,\"mbw_raw_mbps\":%.2f"
            ",\"blk_MBps\":%.2f,\"nets_note\":\"PROXY:skb-share\"",
            s->netp_dev, s->nets_sys, s->mbw_raw_mbps, s->blk_MBps);
    if (portable) {
        fprintf(out, ",\"schedlat\":");  json_num(out, s->schedlat);
        fprintf(out, ",\"psi_mem\":");   json_num(out, s->psi_mem);
        fprintf(out, ",\"membw_est\":"); json_num(out, s->membw_est);
        fprintf(out, ",\"psi_io\":");    json_num(out, s->psi_io);
        fprintf(out, ",\"schedthr\":");  json_num(out, s->schedthr);
        fprintf(out, ",\"steal\":");     json_num(out, s->steal);
    }
    fprintf(out, "}\n");
    fflush(out);
}

static void emit_prometheus(FILE *out, const intp_sample_t *s, int no_diag_cols,
                            int portable)
{
    fprintf(out,
        "intp_v3_3{metric=\"netp\"} %.2f\n"
        "intp_v3_3{metric=\"nets\"} %.2f\n"
        "intp_v3_3{metric=\"blk\"} %.2f\n"
        "intp_v3_3{metric=\"mbw\"} %.2f\n"
        "intp_v3_3{metric=\"llcmr\"} %.2f\n"
        "intp_v3_3{metric=\"llcocc\"} %.2f\n"
        "intp_v3_3{metric=\"cpu\"} %.2f\n",
        s->netp, s->nets, s->blk, s->mbw, s->llcmr, s->llcocc, s->cpu);
    if (!no_diag_cols)
        fprintf(out,
            "intp_v3_3{metric=\"netp_dev\"} %.2f\n"
            "intp_v3_3{metric=\"nets_sys\"} %.2f\n"
            "intp_v3_3{metric=\"mbw_raw_mbps\"} %.2f\n"
            "intp_v3_3{metric=\"blk_MBps\"} %.2f\n",
            s->netp_dev, s->nets_sys, s->mbw_raw_mbps, s->blk_MBps);
    if (portable) {
        /* NaN-valued portable sources are omitted (Prometheus has no null). */
        if (!isnan(s->schedlat))  fprintf(out, "intp_v3_3{metric=\"schedlat\"} %.2f\n",  s->schedlat);
        if (!isnan(s->psi_mem))   fprintf(out, "intp_v3_3{metric=\"psi_mem\"} %.2f\n",   s->psi_mem);
        if (!isnan(s->membw_est)) fprintf(out, "intp_v3_3{metric=\"membw_est\"} %.2f\n", s->membw_est);
        if (!isnan(s->psi_io))    fprintf(out, "intp_v3_3{metric=\"psi_io\"} %.2f\n",    s->psi_io);
        if (!isnan(s->schedthr))  fprintf(out, "intp_v3_3{metric=\"schedthr\"} %.2f\n",  s->schedthr);
        if (!isnan(s->steal))     fprintf(out, "intp_v3_3{metric=\"steal\"} %.2f\n",     s->steal);
    }
    fflush(out);
}

/* ------------------------------------------------------------------ main */

static int libbpf_quiet(enum libbpf_print_level lvl, const char *fmt, va_list ap)
{
    if (lvl == LIBBPF_WARN) return vfprintf(stderr, fmt, ap);
    return 0;
}

int main(int argc, char **argv)
{
    intp_args_t args;
    int r = intp_args_parse(argc, argv, &args);
    if (r == 1) return 0;
    if (r < 0)  return 1;

    system_capabilities_t caps;
    detect_all(&caps);

    if (args.nic_speed_bps_override > 0)
        caps.nic_speed_bps = args.nic_speed_bps_override;
    if (args.mem_bw_max_bps_override > 0)
        caps.mem_bw_max_bps = args.mem_bw_max_bps_override;
    if (args.llc_size_bytes_override > 0)
        caps.llc_size_bytes = args.llc_size_bytes_override;

    if (args.list_capabilities) {
        print_capabilities(&caps, stdout);
        return 0;
    }

    if (!args.verbose) libbpf_set_print(libbpf_quiet);

    int vm_mode = args.tap_iface && args.tap_iface[0];

    /* ------- resolve cgroup identity (DESIGN §3) ------- */
    struct intp_config cfg;
    memset(&cfg, 0, sizeof(cfg));
    int have_cgroup = 0;
    if (args.cgroup) {
        if (resolve_cgroup_identity(args.cgroup, &cfg.target_cgid,
                                    &cfg.target_level) != 0) {
            fprintf(stderr,
                "warning: cannot stat cgroup '%s' (%s) -- falling back to "
                "system-wide\n", args.cgroup, strerror(errno));
        } else {
            have_cgroup = 1;
            cfg.exact_flag = args.exact_match ? 1 : 0;
        }
    }
    cfg.system_wide = have_cgroup ? 0 : 1;

    /* ------- open + load BPF skeleton ------- */
    struct intp_agg_bpf *skel = intp_agg_bpf__open();
    if (!skel) {
        fprintf(stderr, "failed to open BPF skeleton: %s\n", strerror(errno));
        return 1;
    }

    if (args.no_perf_events) {
        bpf_program__set_autoload(skel->progs.perf_llc_refs,   false);
        bpf_program__set_autoload(skel->progs.perf_llc_misses, false);
    }
    /* cgroup_skb programs are attached manually to the cgroup fd; in VM mode
     * (netp from the tap iface) or system-wide mode they are not used. The
     * skeleton's auto-attach does not attach BPF_PROG_TYPE_CGROUP_SKB, so we
     * simply skip the manual attach below when not in container mode. */

    if (intp_agg_bpf__load(skel)) {
        fprintf(stderr, "failed to load BPF: %s\n", strerror(errno));
        intp_agg_bpf__destroy(skel);
        return 1;
    }

    /* ------- push cgroup-identity config into intp_cfg_map ------- */
    unsigned int cfg_key = 0;
    if (bpf_map__update_elem(skel->maps.intp_cfg_map, &cfg_key, sizeof(cfg_key),
                             &cfg, sizeof(cfg), BPF_ANY) != 0) {
        fprintf(stderr, "failed to write intp_config: %s\n", strerror(errno));
        intp_agg_bpf__destroy(skel);
        return 1;
    }

    /* ------- attach tracepoints (auto) -------
     * cgroup_skb ingress/egress (attached manually to the cgroup fd below)
     * and the perf_event LLC programs (attached manually per-CPU via
     * perf_event_open below) must NOT be auto-attached by the skeleton.
     * libbpf does not synthesize a default link for these program types, but
     * make the intent explicit rather than relying on that silent skip. */
    bpf_program__set_autoattach(skel->progs.cg_skb_egress,  false);
    bpf_program__set_autoattach(skel->progs.cg_skb_ingress, false);
    bpf_program__set_autoattach(skel->progs.perf_llc_refs,   false);
    bpf_program__set_autoattach(skel->progs.perf_llc_misses, false);

    if (intp_agg_bpf__attach(skel)) {
        fprintf(stderr, "failed to attach BPF programs: %s\n", strerror(errno));
        intp_agg_bpf__destroy(skel);
        return 1;
    }

    /* ------- attach cgroup_skb ingress+egress to the target cgroup fd -------
     * Canonical per-cgroup netp (C1). Only in container mode (have a cgroup
     * target and not VM mode). cgroup_skb cannot see guest traffic, so VM
     * mode sources netp from the tap iface instead. */
    int cgroup_fd = -1;
    struct bpf_link *skb_egress_link = NULL, *skb_ingress_link = NULL;
    if (have_cgroup) {
        cgroup_fd = open(args.cgroup, O_RDONLY | O_DIRECTORY);
        if (cgroup_fd < 0 && args.verbose)
            fprintf(stderr, "warn: open cgroup dir '%s' failed: %s "
                            "(per-cgroup netp / perf cgroup-mode disabled)\n",
                    args.cgroup, strerror(errno));
        if (cgroup_fd >= 0 && !vm_mode) {
            skb_egress_link =
                bpf_program__attach_cgroup(skel->progs.cg_skb_egress, cgroup_fd);
            skb_ingress_link =
                bpf_program__attach_cgroup(skel->progs.cg_skb_ingress, cgroup_fd);
            if ((!skb_egress_link || !skb_ingress_link) && args.verbose)
                fprintf(stderr, "warn: cgroup_skb attach failed: %s "
                                "(canonical netp will read 0)\n",
                        strerror(errno));
        }
    }

    /* ------- perf_event programs for llcmr (cgroup mode when targeted) ------- */
    perf_attach_t perf_refs = {0}, perf_miss = {0};
    if (!args.no_perf_events) {
        int n_cpus = detect_num_cores();
        int perf_cgroup_fd = (have_cgroup && cgroup_fd >= 0) ? cgroup_fd : -1;
        if (open_cache_counters(skel->progs.perf_llc_refs,
                                PERF_COUNT_HW_CACHE_RESULT_ACCESS,
                                &perf_refs, n_cpus, perf_cgroup_fd,
                                args.verbose) != 0
            && args.verbose) {
            fprintf(stderr, "warn: no LLC-refs counters opened\n");
        }
        if (open_cache_counters(skel->progs.perf_llc_misses,
                                PERF_COUNT_HW_CACHE_RESULT_MISS,
                                &perf_miss, n_cpus, perf_cgroup_fd,
                                args.verbose) != 0
            && args.verbose) {
            fprintf(stderr, "warn: no LLC-miss counters opened\n");
        }
    }

    /* ------- resctrl for mbw / llcocc -------
     * RDT, not eBPF (DESIGN §4): a targeted run gets its own mon_group seeded
     * from cgroup.procs; system-wide uses the root group. */
    resctrl_group_t *rg = NULL;
    if (!args.no_resctrl && caps.resctrl_usable) {
        if (have_cgroup) {
            pid_t pids[INTP_MAX_PIDS];
            int npids = read_cgroup_pids(args.cgroup, pids, INTP_MAX_PIDS);
            rg = resctrl_create_group(GROUP_NAME);
            if (rg && npids > 0
                && resctrl_assign_pid_threads(rg, pids, npids) != 0
                && args.verbose)
                fprintf(stderr, "warn: failed to assign PIDs to resctrl group\n");
        } else {
            rg = resctrl_use_root_group();
            if (!rg && args.verbose)
                fprintf(stderr, "warn: resctrl root group not readable; "
                                "mbw/llcocc will be 0\n");
        }
    }

    /* ------- output header ------- */
    int is_tsv  = strcmp(args.output_fmt, "tsv") == 0;
    int is_json = strcmp(args.output_fmt, "json") == 0;
    int is_prom = strcmp(args.output_fmt, "prometheus") == 0;
    if (is_tsv && args.want_header)
        emit_tsv_header(stdout, &caps, args.no_perf_events, args.no_resctrl,
                        args.no_diag_cols, args.clip_mbw, vm_mode,
                        args.portable_metrics);

    signal(SIGINT,  on_signal);
    signal(SIGTERM, on_signal);
    setvbuf(stdout, NULL, _IOLBF, 0);

    /* ------- main polling loop ------- */
    int mbw_warned = 0;
    struct intp_counters prev_g = {0}, cur_g = {0};
    struct intp_counters prev_c = {0}, cur_c = {0};
    if (read_global_aggregate(skel, &prev_g) != 0) {
        fprintf(stderr, "failed to read agg_global: %s\n", strerror(errno));
        resctrl_destroy_group(rg);
        intp_agg_bpf__destroy(skel);
        return 1;
    }
    if (have_cgroup)
        read_per_cgroup_aggregate(skel, cfg.target_cgid, &prev_c);

    unsigned long long tap_prev = 0;
    int tap_ok = 0;
    if (vm_mode)
        tap_ok = (tap_total_bytes(args.tap_iface, &tap_prev) == 0);
    if (vm_mode && !tap_ok)
        fprintf(stderr, "warn: cannot read tap iface '%s' statistics "
                        "(%s) -- VM netp will read 0\n",
                args.tap_iface, strerror(errno));

    /* ------- portable-metrics file paths + prev state (C26) ------- *
     * The PSI/cpu.stat sources are per-cgroup when a target is given, else the
     * system-wide /proc/pressure fallback (throttling has no system analogue).
     * Seed prev now so the first sample yields a real delta. */
    char psi_mem_path[PATH_MAX], psi_io_path[PATH_MAX], cpustat_path[PATH_MAX];
    unsigned long long p_psi_mem = 0, p_psi_io = 0, p_thr = 0,
                       p_steal = 0, p_cputot = 0;
    int psi_mem_ok = 0, psi_io_ok = 0, thr_ok = 0, steal_ok = 0;
    cpustat_path[0] = '\0';
    if (args.portable_metrics) {
        if (have_cgroup) {
            snprintf(psi_mem_path, sizeof(psi_mem_path), "%s/memory.pressure",
                     args.cgroup);
            snprintf(psi_io_path,  sizeof(psi_io_path),  "%s/io.pressure",
                     args.cgroup);
            snprintf(cpustat_path, sizeof(cpustat_path), "%s/cpu.stat",
                     args.cgroup);
        } else {
            snprintf(psi_mem_path, sizeof(psi_mem_path), "/proc/pressure/memory");
            snprintf(psi_io_path,  sizeof(psi_io_path),  "/proc/pressure/io");
        }
        psi_mem_ok = (read_psi_some_total_us(psi_mem_path, &p_psi_mem) == 0);
        psi_io_ok  = (read_psi_some_total_us(psi_io_path,  &p_psi_io)  == 0);
        if (cpustat_path[0])
            thr_ok = (read_cpu_stat_throttled_us(cpustat_path, &p_thr) == 0);
        steal_ok = (read_proc_stat_steal(&p_steal, &p_cputot) == 0);
        if (args.verbose && !psi_mem_ok)
            fprintf(stderr, "warn: PSI '%s' unreadable (CONFIG_PSI=n?) -- "
                            "psi_mem will read '--'\n", psi_mem_path);
    }

    struct timespec start, prev_t, now_t;
    clock_gettime(CLOCK_MONOTONIC, &start);
    prev_t = start;

    while (g_running) {
        struct timespec wait = {
            .tv_sec  = (time_t)args.interval_sec,
            .tv_nsec = (long)((args.interval_sec
                              - (double)(time_t)args.interval_sec) * 1e9)
        };
        if (wait.tv_sec == 0 && wait.tv_nsec == 0) wait.tv_nsec = 1000000;
        while (nanosleep(&wait, &wait) < 0 && errno == EINTR && g_running)
            continue;
        if (!g_running) break;

        if (read_global_aggregate(skel, &cur_g) != 0) break;
        if (have_cgroup)
            read_per_cgroup_aggregate(skel, cfg.target_cgid, &cur_c);
        clock_gettime(CLOCK_MONOTONIC, &now_t);

        double interval_real = (double)(now_t.tv_sec  - prev_t.tv_sec)
                             + (double)(now_t.tv_nsec - prev_t.tv_nsec) * 1e-9;
        if (interval_real <= 0.0) interval_real = args.interval_sec;

        struct intp_counters delta_g, delta_c;
        counters_diff(&cur_g, &prev_g, &delta_g);
        counters_diff(&cur_c, &prev_c, &delta_c);

        /* VM netp from the tap iface (stable-ABI, host-NIC normalized). */
        double vm_netp_pct = -1.0;
        if (vm_mode) {
            unsigned long long tap_cur = tap_prev;
            if (tap_ok && tap_total_bytes(args.tap_iface, &tap_cur) == 0) {
                unsigned long long d = (tap_cur >= tap_prev)
                                     ? (tap_cur - tap_prev) : 0;
                long max_nic = caps.nic_speed_bps > 0
                                 ? caps.nic_speed_bps : 125000000L;
                vm_netp_pct = safe_pct((double)d / interval_real,
                                       (double)max_nic);
                tap_prev = tap_cur;
            } else {
                vm_netp_pct = 0.0;
            }
        }

        intp_sample_t sample;
        compute_sample(&delta_c, &delta_g, &caps, interval_real,
                       caps.num_cores, vm_netp_pct, &sample);

        /* ------- VM-portable block (C26 / DESIGN §10). schedlat is already
         * filled by compute_sample from the BPF counter; here we add the five
         * file/counter-derived metrics. NaN where the source is unavailable
         * (emitted "--", never faked). ------- */
        if (args.portable_metrics) {
            double interval_us = interval_real * 1e6;

            /* schedlat in system-wide mode: the BPF charges run-queue wait to
             * agg_global (tp_schedlat, intp_agg.bpf.c), but compute_sample read
             * the per-cgroup delta -- zero when there is no cgroup target. Re-
             * derive from the global delta so the real signal surfaces instead of
             * a fake 0. (With a cgroup target the per-cgroup value already set by
             * compute_sample stands.) Same core-seconds budget as cpu. */
            if (!have_cgroup) {
                double cpu_ns_avail = interval_real * 1e9
                    * (caps.num_cores > 0 ? caps.num_cores : 1);
                sample.schedlat = safe_pct((double)delta_g.schedlat_wait_ns_sum,
                                           cpu_ns_avail);
            }

            /* membw_est: per-cgroup (or host-wide) LLC misses * 64B cacheline
             * / interval -> DRAM bandwidth estimate (MB/s). Reuses the existing
             * llc_misses counter, which falls back to the architectural
             * cache-misses event in a vPMU guest (so this survives in-guest
             * where the LL-read llcmr does not). Emits "--" (NaN), never a fake
             * 0, when the miss counter never opened (--no-perf-events, or
             * perf_event_open failed) so llc_misses would be a permanent 0. */
            unsigned long long miss =
                have_cgroup ? delta_c.llc_misses : delta_g.llc_misses;
            int membw_ok = !args.no_perf_events && perf_miss.n_fds > 0;
            sample.membw_est = (membw_ok && interval_real > 0.0)
                ? ((double)miss * 64.0 / interval_real) / 1e6 : NAN;

            sample.psi_mem = sample.psi_io = NAN;
            sample.schedthr = sample.steal = NAN;

            unsigned long long cur;
            if (psi_mem_ok && read_psi_some_total_us(psi_mem_path, &cur) == 0) {
                sample.psi_mem = port_pct(cur, p_psi_mem, interval_us);
                p_psi_mem = cur;
            }
            if (psi_io_ok && read_psi_some_total_us(psi_io_path, &cur) == 0) {
                sample.psi_io = port_pct(cur, p_psi_io, interval_us);
                p_psi_io = cur;
            }
            if (thr_ok && read_cpu_stat_throttled_us(cpustat_path, &cur) == 0) {
                sample.schedthr = port_pct(cur, p_thr, interval_us);
                p_thr = cur;
            }
            if (steal_ok) {
                unsigned long long cs = 0, ct = 0;
                if (read_proc_stat_steal(&cs, &ct) == 0) {
                    unsigned long long dt = (ct >= p_cputot) ? ct - p_cputot : 0;
                    unsigned long long ds = (cs >= p_steal)  ? cs - p_steal  : 0;
                    sample.steal = (dt > 0)
                        ? safe_pct((double)ds, (double)dt) : 0.0;
                    p_steal = cs; p_cputot = ct;
                }
            }
        }

        if (rg) {
            /* Re-scan cgroup.procs into the mon_group so RDT tracks PIDs that
             * fork or get (re)placed after startup. A one-shot startup snapshot
             * misses the workload's forked workers and, for an incus-managed
             * system container, PIDs whose RMID points at incus's own resctrl
             * group -> llcocc/mbw read 0 (the original snapshot's occupancy).
             * Eager for the first samples then periodic; mirrors v2.1's
             * resctrl_rescan_cgroup, which the v3.3 DESIGN already assumes.
             * Re-assigning already-tracked PIDs is a harmless no-op; the root
             * (system-wide) group needs no rescan. */
            if (have_cgroup) {
                static int rescan_n = 0;
                if (rescan_n < 5 || (rescan_n % 5) == 0) {
                    pid_t rpids[INTP_MAX_PIDS];
                    int rn = read_cgroup_pids(args.cgroup, rpids, INTP_MAX_PIDS);
                    if (rn > 0) resctrl_assign_pid_threads(rg, rpids, rn);
                }
                rescan_n++;
            }
            double pct = 0.0, raw = 0.0;
            resctrl_read_mbm_pct_and_raw(rg, &caps, interval_real,
                                         args.clip_mbw, &pct, &raw);
            sample.mbw          = pct;
            sample.mbw_raw_mbps = raw;
            sample.llcocc       = resctrl_read_llcocc(rg, &caps);

            if (!args.clip_mbw && pct > 100.0 && !mbw_warned) {
                fprintf(stderr,
                    "warn: mbw exceeded ceiling at t=%.2fs "
                    "(raw=%.0f MB/s, ceiling=%ld MB/s) "
                    "-- recheck --mem-bw-max-bps\n",
                    (double)(now_t.tv_sec - start.tv_sec) +
                    (double)(now_t.tv_nsec - start.tv_nsec) / 1e9,
                    raw,
                    caps.mem_bw_max_bps / 1000000L);
                mbw_warned = 1;
            }
        } else {
            /* resctrl/RDT unavailable (--no-resctrl, or no usable resctrl
             * mount -- e.g. a stock KVM vm-guest, where resctrl is host-only).
             * Emit '--' (NaN) for the RDT-derived metrics rather than a fake 0,
             * so availability.tsv records them as structurally unsupported and
             * the cross-env layer never reads them as measured-zero ("do not
             * fake it", C25/P5). mbw/llcocc are the only RDT-gated metrics; the
             * perf-gated llcmr has its own counters (available with guest PMU
             * pass-through). */
            sample.mbw          = NAN;
            sample.mbw_raw_mbps = NAN;
            sample.llcocc       = NAN;
        }

        if (is_tsv)  emit_tsv(stdout, &sample, args.no_diag_cols,
                              args.portable_metrics);
        if (is_json) {
            double t = (double)(now_t.tv_sec  - start.tv_sec)
                     + (double)(now_t.tv_nsec - start.tv_nsec) / 1e9;
            emit_json(stdout, &sample, t, args.no_diag_cols,
                      args.portable_metrics);
        }
        if (is_prom) emit_prometheus(stdout, &sample, args.no_diag_cols,
                                     args.portable_metrics);

        prev_g = cur_g;
        prev_c = cur_c;
        prev_t = now_t;

        if (args.duration_sec > 0.0) {
            double run = (double)(now_t.tv_sec  - start.tv_sec)
                       + (double)(now_t.tv_nsec - start.tv_nsec) / 1e9;
            if (run >= args.duration_sec) break;
        }
    }

    /* ------- cleanup ------- */
    close_cache_counters(&perf_refs);
    close_cache_counters(&perf_miss);
    if (skb_egress_link)  bpf_link__destroy(skb_egress_link);
    if (skb_ingress_link) bpf_link__destroy(skb_ingress_link);
    if (cgroup_fd >= 0)   close(cgroup_fd);
    resctrl_destroy_group(rg);
    intp_agg_bpf__destroy(skel);
    return 0;
}

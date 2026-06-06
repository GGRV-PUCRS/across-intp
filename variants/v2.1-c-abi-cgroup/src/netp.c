/*
 * netp.c -- network physical utilization.
 *
 *   netp_tap     /sys/class/net/<tap>/statistics  (VM netp via --target-vm)
 *   netp_cgroup  per-container netns /proc/<pid>/net/dev (host NIC normalized)
 *   netp_sysfs   /sys/class/net/<iface>/statistics/{rx,tx}_bytes (preferred)
 *   netp_procfs  /proc/net/dev (same data, less efficient parsing)
 *
 * Default is multi-interface aggregation: sum tx_bytes+rx_bytes across all
 * non-loopback interfaces. Matches v3's eBPF semantics (which excludes `lo`
 * to avoid double-counting xmit+recv on the same packet) and unblocks the
 * veth-routed workload setup, where traffic flows through `intp-veth-h`
 * rather than the physical NIC. `--iface NAME` pins a single interface
 * (legacy behavior); useful when you want to isolate a specific device.
 *
 * Normalization: (rx+tx)/interval / nic_speed_bps * 100. NIC speed unknown
 * (link down or virtual iface) -> assume 1Gbps and mark DEGRADED.
 */

#include "backend.h"
#include "detect.h"
#include "procutil.h"

#include <dirent.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

#define DEFAULT_BPS (1000000000L / 8)
#define MAX_IFACES  32

static int iface_skip(const char *name)
{
    return name[0] == '.' || strcmp(name, "lo") == 0;
}

static unsigned long long read_ull(const char *path)
{
    FILE *f = fopen(path, "r");
    if (!f) return 0;
    unsigned long long v = 0;
    if (fscanf(f, "%llu", &v) != 1) v = 0;
    fclose(f);
    return v;
}

long netp_resolve_speed(const char *iface, int *assumed_out)
{
    int  dummy = 0;
    int *assumed = assumed_out ? assumed_out : &dummy;
    const intp_target_t *t = intp_target_get();
    if (t && t->nic_speed_bps_override > 0) {
        *assumed = 0;
        return t->nic_speed_bps_override;
    }
    long bps = detect_nic_speed_bps(iface);
    if (bps <= 0) {
        *assumed = 1;
        return DEFAULT_BPS;
    }
    *assumed = 0;
    return bps;
}

/* ---- sysfs backend (multi-iface aware) ---------------------------------- */

static struct {
    int                valid;
    char               iface_override[64];   /* empty = aggregate non-lo */
    long               nic_speed_bps;
    int                assumed_speed;
    unsigned long long prev_total;
} sf;

/* Sum tx_bytes+rx_bytes via sysfs. If iface_override is set, returns that
 * one interface's bytes; otherwise sums across all non-lo entries under
 * /sys/class/net/. Returns -1 if no interface produced a reading. */
static int sysfs_total_bytes(const char *iface_override,
                             unsigned long long *out_total)
{
    if (iface_override && iface_override[0]) {
        char p[256];
        snprintf(p, sizeof(p),
                 "/sys/class/net/%.63s/statistics/tx_bytes", iface_override);
        unsigned long long tx = read_ull(p);
        snprintf(p, sizeof(p),
                 "/sys/class/net/%.63s/statistics/rx_bytes", iface_override);
        unsigned long long rx = read_ull(p);
        *out_total = tx + rx;
        return 0;
    }
    DIR *d = opendir("/sys/class/net/");
    if (!d) return -1;
    unsigned long long total = 0;
    int counted = 0;
    struct dirent *e;
    while ((e = readdir(d)) != NULL) {
        if (iface_skip(e->d_name)) continue;
        char p[320];
        snprintf(p, sizeof(p),
                 "/sys/class/net/%.63s/statistics/tx_bytes", e->d_name);
        total += read_ull(p);
        snprintf(p, sizeof(p),
                 "/sys/class/net/%.63s/statistics/rx_bytes", e->d_name);
        total += read_ull(p);
        counted++;
    }
    closedir(d);
    if (counted == 0) return -1;
    *out_total = total;
    return 0;
}

static int sysfs_probe(void)
{
    DIR *d = opendir("/sys/class/net/");
    if (!d) return -1;
    closedir(d);
    return 0;
}

static int sysfs_init(void)
{
    const intp_target_t *t = intp_target_get();
    const char *override = (t && t->iface && t->iface[0]) ? t->iface : "";
    snprintf(sf.iface_override, sizeof(sf.iface_override), "%s", override);

    /* Speed denominator: use the explicit interface if pinned, otherwise
     * the host's default-iface speed (matches v3's caps->nic_speed_bps). */
    const char *speed_iface = override[0] ? override : detect_default_iface();
    sf.nic_speed_bps = netp_resolve_speed(speed_iface, &sf.assumed_speed);

    if (sysfs_total_bytes(sf.iface_override, &sf.prev_total) != 0) return -1;
    sf.valid = 1;
    return 0;
}

static int sysfs_read(metric_sample_t *out, double interval_sec)
{
    if (!sf.valid || interval_sec <= 0) return -1;
    unsigned long long total = 0;
    if (sysfs_total_bytes(sf.iface_override, &total) != 0) return -1;
    unsigned long long d = total - sf.prev_total;
    sf.prev_total = total;

    double bps = (double)d / interval_sec;
    double v   = bps / (double)sf.nic_speed_bps * 100.0;
    if (v < 0.0)  v = 0.0;
    if (v > 99.0) v = 99.0;

    out->value      = v;
    out->backend_id = "sysfs";
    if (sf.assumed_speed) {
        out->status = METRIC_STATUS_DEGRADED;
        out->note   = "assumed_1gbps";
    } else {
        out->status = METRIC_STATUS_OK;
        out->note   = sf.iface_override[0] ? NULL : "aggregate_non_lo";
    }
    return 0;
}

static void sysfs_cleanup(void) { sf.valid = 0; }

/* ---- procfs fallback (multi-iface aware) -------------------------------- */

static struct {
    int                valid;
    char               iface_override[64];
    long               nic_speed_bps;
    int                assumed_speed;
    unsigned long long prev_total;
} pf;

static int procfs_total_bytes(const char *iface_override,
                              unsigned long long *out_total)
{
    netdev_entry_t entries[MAX_IFACES];
    int n = procutil_read_netdev(entries, MAX_IFACES);
    if (n <= 0) return -1;
    unsigned long long total = 0;
    int counted = 0;
    for (int i = 0; i < n; i++) {
        if (iface_override && iface_override[0]) {
            if (strcmp(entries[i].iface, iface_override) != 0) continue;
        } else if (iface_skip(entries[i].iface)) {
            continue;
        }
        total += entries[i].rx_bytes + entries[i].tx_bytes;
        counted++;
    }
    if (counted == 0) return -1;
    *out_total = total;
    return 0;
}

static int procfs_probe(void)
{
    FILE *f = fopen("/proc/net/dev", "r");
    if (!f) return -1;
    fclose(f);
    return 0;
}

static int procfs_init(void)
{
    const intp_target_t *t = intp_target_get();
    const char *override = (t && t->iface && t->iface[0]) ? t->iface : "";
    snprintf(pf.iface_override, sizeof(pf.iface_override), "%s", override);

    const char *speed_iface = override[0] ? override : detect_default_iface();
    pf.nic_speed_bps = netp_resolve_speed(speed_iface, &pf.assumed_speed);

    if (procfs_total_bytes(pf.iface_override, &pf.prev_total) != 0) return -1;
    pf.valid = 1;
    return 0;
}

static int procfs_read(metric_sample_t *out, double interval_sec)
{
    if (!pf.valid || interval_sec <= 0) return -1;
    unsigned long long total = 0;
    if (procfs_total_bytes(pf.iface_override, &total) != 0) return -1;
    unsigned long long d = total - pf.prev_total;
    pf.prev_total = total;

    double bps = (double)d / interval_sec;
    double v   = bps / (double)pf.nic_speed_bps * 100.0;
    if (v < 0.0)  v = 0.0;
    if (v > 99.0) v = 99.0;

    out->value      = v;
    out->backend_id = "procfs";
    if (pf.assumed_speed) {
        out->status = METRIC_STATUS_DEGRADED;
        out->note   = "assumed_1gbps";
    } else {
        out->status = METRIC_STATUS_OK;
        out->note   = pf.iface_override[0] ? NULL : "aggregate_non_lo";
    }
    return 0;
}

static void procfs_cleanup(void) { pf.valid = 0; }

/* ---- cgroup/netns backend (per-container netp) --------------------------- *
 *
 * A container has its own network namespace, so the host-side profiler can
 * read the container's interface counters through /proc/<pid>/net/dev (the
 * netns of <pid>) for any pid in the target cgroup -- the netns path the
 * design intends. Bytes are normalized by the HOST physical NIC speed, i.e.
 * "this container's share of the physical link", which is the
 * interference-relevant quantity under consolidation. Falls back to the
 * system-wide backends when the target shares the profiler's netns
 * (--net=host containers, bare colocated processes): per-process netp inside a
 * shared netns needs eBPF socket-cgroup attribution (v3.3). */
static struct {
    int                valid;
    char               path[64];          /* /proc/<pid>/net/dev */
    long               nic_speed_bps;
    int                assumed_speed;
    unsigned long long prev_total;
} cg;

/* 1 if <pid> is in a different network namespace than the profiler itself. */
static int netns_isolated(pid_t pid)
{
    char ap[64], la[128], lb[128];
    snprintf(ap, sizeof(ap), "/proc/%d/ns/net", (int)pid);
    ssize_t na = readlink(ap, la, sizeof(la) - 1);
    ssize_t nb = readlink("/proc/self/ns/net", lb, sizeof(lb) - 1);
    if (na <= 0 || nb <= 0) return 0;
    la[na] = '\0';
    lb[nb] = '\0';
    return strcmp(la, lb) != 0;
}

static int cg_total_bytes(unsigned long long *out_total)
{
    netdev_entry_t entries[MAX_IFACES];
    int n = procutil_read_netdev_at(cg.path, entries, MAX_IFACES);
    if (n <= 0) return -1;
    unsigned long long total = 0;
    int counted = 0;
    for (int i = 0; i < n; i++) {
        if (iface_skip(entries[i].iface)) continue;
        total += entries[i].rx_bytes + entries[i].tx_bytes;
        counted++;
    }
    if (counted == 0) return -1;
    *out_total = total;
    return 0;
}

static int cgroup_probe(void)
{
    const intp_target_t *t = intp_target_get();
    if (!t || t->n_pids <= 0) return -1;        /* needs a pid (seeded from --cgroup) */
    if (!netns_isolated(t->pids[0])) return -1; /* shared netns -> system-wide backends */
    char p[64];
    snprintf(p, sizeof(p), "/proc/%d/net/dev", (int)t->pids[0]);
    FILE *f = fopen(p, "r");
    if (!f) return -1;
    fclose(f);
    return 0;
}

static int cgroup_init(void)
{
    const intp_target_t *t = intp_target_get();
    if (!t || t->n_pids <= 0) return -1;
    snprintf(cg.path, sizeof(cg.path), "/proc/%d/net/dev", (int)t->pids[0]);
    /* Normalize by the HOST physical NIC (the shared resource), not the
     * container's veth -- a veth has no meaningful line rate. */
    cg.nic_speed_bps = netp_resolve_speed(detect_default_iface(), &cg.assumed_speed);
    if (cg_total_bytes(&cg.prev_total) != 0) return -1;
    cg.valid = 1;
    return 0;
}

static int cgroup_read(metric_sample_t *out, double interval_sec)
{
    if (!cg.valid || interval_sec <= 0) return -1;
    unsigned long long total = 0;
    if (cg_total_bytes(&total) != 0) return -1;
    unsigned long long d = total - cg.prev_total;
    cg.prev_total = total;

    double bps = (double)d / interval_sec;
    double v   = bps / (double)cg.nic_speed_bps * 100.0;
    if (v < 0.0)  v = 0.0;
    if (v > 99.0) v = 99.0;

    out->value      = v;
    out->backend_id = "cgroup";
    out->status     = cg.assumed_speed ? METRIC_STATUS_DEGRADED : METRIC_STATUS_OK;
    out->note       = cg.assumed_speed ? "assumed_1gbps" : "netns_per_cgroup";
    return 0;
}

static void cgroup_cleanup(void) { cg.valid = 0; }

/* ---- tap backend (VM netp via host-side tap/vnet iface) ----------------- *
 *
 * A VM's traffic crosses a host tap/vnet iface rather than a cgroup or netns
 * the host can introspect, so per-VM netp is read from
 * /sys/class/net/<tap>/statistics for the tap named by --target-vm/--tap-iface.
 * Bytes are normalized by the HOST physical NIC speed -- "this VM's share of
 * the physical link", the interference-relevant quantity, matching the cgroup
 * backend's semantics. The tap must be passed explicitly (the bench harness
 * sets it); there is no autodetect, so this backend only binds in VM mode.
 * (The full tc/XDP-on-tap path is the v3.3 deliverable; this is the v2.1
 * stable-ABI stand-in -- see docs/DECISIONS-container.md C1.) */
static struct {
    int                valid;
    char               tap[64];
    long               nic_speed_bps;
    int                assumed_speed;
    unsigned long long prev_total;
} tp;

static int tap_probe(void)
{
    const intp_target_t *t = intp_target_get();
    if (!t || !t->tap_iface || !t->tap_iface[0]) return -1;  /* VM mode only */
    char p[256];
    snprintf(p, sizeof(p),
             "/sys/class/net/%.63s/statistics/tx_bytes", t->tap_iface);
    FILE *f = fopen(p, "r");
    if (!f) return -1;
    fclose(f);
    return 0;
}

static int tap_init(void)
{
    const intp_target_t *t = intp_target_get();
    if (!t || !t->tap_iface || !t->tap_iface[0]) return -1;
    snprintf(tp.tap, sizeof(tp.tap), "%s", t->tap_iface);
    /* Normalize by the host physical NIC (the shared resource), not the tap. */
    tp.nic_speed_bps = netp_resolve_speed(detect_default_iface(), &tp.assumed_speed);
    if (sysfs_total_bytes(tp.tap, &tp.prev_total) != 0) return -1;
    tp.valid = 1;
    return 0;
}

static int tap_read(metric_sample_t *out, double interval_sec)
{
    if (!tp.valid || interval_sec <= 0) return -1;
    unsigned long long total = 0;
    if (sysfs_total_bytes(tp.tap, &total) != 0) return -1;
    unsigned long long d = total - tp.prev_total;
    tp.prev_total = total;

    double bps = (double)d / interval_sec;
    double v   = bps / (double)tp.nic_speed_bps * 100.0;
    if (v < 0.0)  v = 0.0;
    if (v > 99.0) v = 99.0;

    out->value      = v;
    out->backend_id = "tap";
    out->status     = tp.assumed_speed ? METRIC_STATUS_DEGRADED : METRIC_STATUS_OK;
    out->note       = tp.assumed_speed ? "assumed_1gbps" : "vm_tap";
    return 0;
}

static void tap_cleanup(void) { tp.valid = 0; }

static backend_t b_tap = {
    .backend_id  = "tap",
    .description = "VM netp via host tap/vnet /sys/class/net/<tap>/statistics (host NIC-speed normalized)",
    .probe = tap_probe, .init = tap_init,
    .read  = tap_read,  .cleanup = tap_cleanup,
};

static backend_t b_cgroup = {
    .backend_id  = "cgroup",
    .description = "per-container netns /proc/<pid>/net/dev (host NIC-speed normalized)",
    .probe = cgroup_probe, .init = cgroup_init,
    .read  = cgroup_read,  .cleanup = cgroup_cleanup,
};

static backend_t b_sysfs = {
    .backend_id = "sysfs",
    .description = "/sys/class/net/<iface>/statistics/{rx,tx}_bytes",
    .probe = sysfs_probe, .init = sysfs_init,
    .read  = sysfs_read,  .cleanup = sysfs_cleanup,
};

static backend_t b_procfs = {
    .backend_id = "procfs",
    .description = "/proc/net/dev",
    .probe = procfs_probe, .init = procfs_init,
    .read  = procfs_read,  .cleanup = procfs_cleanup,
};

static metric_t m = {
    .metric_name = "netp",
    .backends    = { &b_tap, &b_cgroup, &b_sysfs, &b_procfs },
    .n_backends  = 4,
};

metric_t *metric_netp(void) { return &m; }

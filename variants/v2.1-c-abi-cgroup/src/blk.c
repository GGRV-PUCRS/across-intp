/*
 * blk.c -- block I/O utilization.
 *
 *   blk_diskstats   /proc/diskstats io_ticks (sum across non-virtual whole
 *                   devices, or single device when --disk specified). This
 *                   is iostat's %util.
 *   blk_sysfs       /sys/block/<dev>/stat (same fields, per-device).
 */

#include "backend.h"
#include "detect.h"
#include "procutil.h"

#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

/* ---- cgroup backend: native per-cgroup block I/O via cgroup v2 io.stat ----
 *
 * v2.1's distinguishing feature for blk: attribute by cgroup, not device-wide.
 * io.stat reports cumulative rbytes/wbytes per backing device for every task
 * in the cgroup (and its descendants), so children spawned after startup are
 * counted automatically -- no cgroup.procs re-scan, no churn. Selected ahead
 * of the device-wide io_ticks backends when --cgroup names a cgroup v2 path.
 *
 * Semantic note: this measures the cgroup's I/O *throughput* normalized to a
 * device max-bandwidth reference -- NOT the device-busy %util the diskstats
 * backend reports. cgroup v2 exposes per-cgroup bytes, not per-cgroup busy
 * time (the kernel does not track the latter), so the two backends report
 * different physical quantities. backend_id and status make that explicit.
 * Denominator precedence: --disk-bw-max-bps override (status ok, no note) ->
 * detect_disk_max_bps() host class estimate (status ok, note detected_disk_bw)
 * -> flat 500 MB/s fallback when even the class can't be read (degraded).
 */
#define BLK_DEFAULT_BW_BPS  (500L * 1000 * 1000)   /* SATA-SSD-ish fallback */

static struct {
    int                valid;
    int                bw_ok;          /* 1 => status ok; 0 => degraded (flat default) */
    long               bw_bps;
    const char        *bw_note;        /* NULL for an explicit override */
    unsigned long long prev_bytes;     /* cumulative rbytes+wbytes summed */
} cg;

/* Sum rbytes+wbytes across every device line in <cgroup>/io.stat.
 * Line format: "<maj>:<min> rbytes=N wbytes=N rios=N wios=N dbytes=N dios=N" */
static int blk_cgroup_bytes(const char *cgpath, unsigned long long *out)
{
    char path[512];
    snprintf(path, sizeof(path), "%s/io.stat", cgpath);
    FILE *f = fopen(path, "r");
    if (!f) return -1;
    unsigned long long total = 0;
    char line[512];
    while (fgets(line, sizeof(line), f)) {
        char *p;
        unsigned long long v;
        if ((p = strstr(line, "rbytes=")) && sscanf(p, "rbytes=%llu", &v) == 1)
            total += v;
        if ((p = strstr(line, "wbytes=")) && sscanf(p, "wbytes=%llu", &v) == 1)
            total += v;
    }
    fclose(f);
    *out = total;
    return 0;
}

static long blk_resolve_bw(const char *disk, int *ok, const char **note)
{
    const intp_target_t *t = intp_target_get();
    if (t && t->disk_bw_max_bps_override > 0) {
        *ok = 1; *note = NULL;
        return t->disk_bw_max_bps_override;
    }
    long d = detect_disk_max_bps(disk);   /* host class estimate (nvme/ssd/hdd) */
    if (d > 0) {
        *ok = 1; *note = "detected_disk_bw";
        return d;
    }
    *ok = 0; *note = "assumed_500mbps";
    return BLK_DEFAULT_BW_BPS;
}

static int blk_cgroup_probe(void)
{
    const intp_target_t *t = intp_target_get();
    if (!t || !t->cgroup_path) return -1;
    char path[512];
    snprintf(path, sizeof(path), "%s/io.stat", t->cgroup_path);
    return (access(path, R_OK) == 0) ? 0 : -1;
}

static int blk_cgroup_init(void)
{
    const intp_target_t *t = intp_target_get();
    if (blk_cgroup_bytes(t->cgroup_path, &cg.prev_bytes) != 0) return -1;
    const char *disk = (t->disk && t->disk[0]) ? t->disk : NULL;
    cg.bw_bps = blk_resolve_bw(disk, &cg.bw_ok, &cg.bw_note);
    cg.valid  = 1;
    return 0;
}

static int blk_cgroup_read(metric_sample_t *out, double interval_sec)
{
    if (!cg.valid || interval_sec <= 0) return -1;
    const intp_target_t *t = intp_target_get();
    unsigned long long now = 0;
    if (blk_cgroup_bytes(t->cgroup_path, &now) != 0) return -1;

    /* Guard against counter reset (cgroup recreated) -> unsigned wrap. */
    double d_bytes = (now >= cg.prev_bytes) ? (double)(now - cg.prev_bytes) : 0.0;
    cg.prev_bytes = now;

    double bps = d_bytes / interval_sec;
    double v   = (cg.bw_bps > 0) ? (bps / (double)cg.bw_bps) * 100.0 : 0.0;
    if (v < 0.0)  v = 0.0;
    if (v > 99.0) v = 99.0;
    out->value      = v;
    out->backend_id = "cgroup";
    out->status     = cg.bw_ok ? METRIC_STATUS_OK : METRIC_STATUS_DEGRADED;
    out->note       = cg.bw_note;
    return 0;
}

static void blk_cgroup_cleanup(void) { cg.valid = 0; }

static backend_t b_cgroup = {
    .backend_id  = "cgroup",
    .description = "native per-cgroup I/O throughput via cgroup v2 io.stat",
    .probe = blk_cgroup_probe, .init = blk_cgroup_init,
    .read  = blk_cgroup_read,  .cleanup = blk_cgroup_cleanup,
};

static int is_virtual(const char *name)
{
    return strncmp(name, "loop", 4) == 0 ||
           strncmp(name, "ram",  3) == 0 ||
           strncmp(name, "zram", 4) == 0 ||
           strncmp(name, "dm-",  3) == 0;
}

static int is_partition(const char *name)
{
    size_t len = strlen(name);
    if (len == 0) return 0;
    if (name[len-1] < '0' || name[len-1] > '9') return 0;
    if (strncmp(name, "nvme", 4) == 0 || strncmp(name, "mmcblk", 6) == 0) {
        char *p = strrchr(name, 'p');
        return p && p > name && p[-1] >= '0' && p[-1] <= '9';
    }
    return 1;
}

static struct {
    int           valid;
    char          target[32];      /* "" = aggregate all whole devices       */
    unsigned long prev_io_ticks;
} ds;

static unsigned long sum_io_ticks(const char *target)
{
    diskstats_entry_t entries[64];
    int n = procutil_read_diskstats(entries, 64);
    if (n <= 0) return 0;
    unsigned long sum = 0;
    for (int i = 0; i < n; i++) {
        if (target[0]) {
            if (strcmp(entries[i].name, target) == 0)
                return entries[i].io_ticks;
            continue;
        }
        if (is_virtual(entries[i].name) || is_partition(entries[i].name))
            continue;
        sum += entries[i].io_ticks;
    }
    return sum;
}

static int diskstats_probe(void)
{
    diskstats_entry_t e[1];
    return procutil_read_diskstats(e, 1) >= 1 ? 0 : -1;
}

static int diskstats_init(void)
{
    const intp_target_t *t = intp_target_get();
    if (t && t->disk && t->disk[0]) {
        snprintf(ds.target, sizeof(ds.target), "%s", t->disk);
    } else {
        ds.target[0] = '\0';   /* aggregate */
    }
    ds.prev_io_ticks = sum_io_ticks(ds.target);
    ds.valid = 1;
    return 0;
}

static int diskstats_read(metric_sample_t *out, double interval_sec)
{
    if (!ds.valid || interval_sec <= 0) return -1;
    unsigned long ticks = sum_io_ticks(ds.target);
    long delta = (long)(ticks - ds.prev_io_ticks);
    ds.prev_io_ticks = ticks;
    double interval_ms = interval_sec * 1000.0;
    double v = (interval_ms > 0)
                 ? ((double)delta / interval_ms) * 100.0 : 0.0;
    if (v < 0.0)  v = 0.0;
    if (v > 99.0) v = 99.0;
    out->value      = v;
    out->status     = METRIC_STATUS_OK;
    out->backend_id = "diskstats";
    out->note       = ds.target[0] ? ds.target : "all-whole-devices";
    return 0;
}

static void diskstats_cleanup(void) { ds.valid = 0; }

/* sysfs fallback: reads /sys/block/<dev>/stat for a single device. */

static struct {
    int           valid;
    char          path[128];
    unsigned long prev_io_ticks;
} sb;

static int sysfs_probe(void)
{
    const intp_target_t *t = intp_target_get();
    char dev[64] = {0};
    if (t && t->disk && t->disk[0]) {
        snprintf(dev, sizeof(dev), "%s", t->disk);
    } else if (detect_default_disk(dev, sizeof(dev)) != 0) {
        return -1;
    }
    char p[128];
    snprintf(p, sizeof(p), "/sys/block/%s/stat", dev);
    FILE *f = fopen(p, "r");
    if (!f) return -1;
    fclose(f);
    return 0;
}

static unsigned long read_sysfs_io_ticks(const char *path)
{
    FILE *f = fopen(path, "r");
    if (!f) return 0;
    unsigned long a, b, c, d, e, g, h, i, j, k;
    int n = fscanf(f, "%lu %lu %lu %lu %lu %lu %lu %lu %lu %lu",
                   &a, &b, &c, &d, &e, &g, &h, &i, &j, &k);
    fclose(f);
    return n >= 10 ? j : 0;     /* j = io_ticks */
}

static int sysfs_init(void)
{
    const intp_target_t *t = intp_target_get();
    char dev[64];
    if (t && t->disk && t->disk[0]) {
        snprintf(dev, sizeof(dev), "%s", t->disk);
    } else if (detect_default_disk(dev, sizeof(dev)) != 0) {
        return -1;
    }
    snprintf(sb.path, sizeof(sb.path), "/sys/block/%s/stat", dev);
    sb.prev_io_ticks = read_sysfs_io_ticks(sb.path);
    sb.valid = 1;
    return 0;
}

static int sysfs_read(metric_sample_t *out, double interval_sec)
{
    if (!sb.valid || interval_sec <= 0) return -1;
    unsigned long ticks = read_sysfs_io_ticks(sb.path);
    long delta = (long)(ticks - sb.prev_io_ticks);
    sb.prev_io_ticks = ticks;
    double interval_ms = interval_sec * 1000.0;
    double v = (interval_ms > 0)
                 ? ((double)delta / interval_ms) * 100.0 : 0.0;
    if (v < 0.0)  v = 0.0;
    if (v > 99.0) v = 99.0;
    out->value      = v;
    out->status     = METRIC_STATUS_OK;
    out->backend_id = "sysfs";
    out->note       = NULL;
    return 0;
}

static void sysfs_cleanup(void) { sb.valid = 0; }

static backend_t b_diskstats = {
    .backend_id  = "diskstats",
    .description = "/proc/diskstats io_ticks aggregated",
    .probe = diskstats_probe, .init = diskstats_init,
    .read  = diskstats_read,  .cleanup = diskstats_cleanup,
};

static backend_t b_sysfs = {
    .backend_id  = "sysfs",
    .description = "/sys/block/<dev>/stat io_ticks",
    .probe = sysfs_probe, .init = sysfs_init,
    .read  = sysfs_read,  .cleanup = sysfs_cleanup,
};

static metric_t m = {
    .metric_name = "blk",
    .backends    = { &b_cgroup, &b_diskstats, &b_sysfs },
    .n_backends  = 3,
};

metric_t *metric_blk(void) { return &m; }

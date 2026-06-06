/*
 * intp-hybrid.c -- IntP V2 main: argument parsing, backend selection,
 * polling loop, output formatters.
 *
 * Output formats:
 *   tsv         (default)  IntP-compatible 7-column TSV: netp nets blk mbw
 *                          llcmr llcocc cpu. A leading "#" header line
 *                          documents which backend was used per metric so
 *                          consumers can distinguish OK/DEGRADED/PROXY.
 *   json        line-delimited JSON, one record per sample.
 *   prometheus  exposition format suitable for /metrics scraping.
 *
 * Lifecycle:
 *   parse args -> detect_all -> per-metric probe+init -> main loop
 *   On SIGINT/SIGTERM the loop exits and metric_cleanup() removes any
 *   created resctrl mon_groups and closes perf fds.
 */

#include "backend.h"
#include "detect.h"
#include "intp.h"
#include "procutil.h"

#include <ctype.h>
#include <dirent.h>
#include <errno.h>
#include <getopt.h>
#include <math.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

static volatile sig_atomic_t g_running = 1;

static void on_signal(int sig) { (void)sig; g_running = 0; }

static const char *status_str(metric_status_t s)
{
    switch (s) {
    case METRIC_STATUS_OK:           return "ok";
    case METRIC_STATUS_DEGRADED:     return "degraded";
    case METRIC_STATUS_PROXY:        return "proxy";
    case METRIC_STATUS_UNAVAILABLE:  /* fall through */
    default:                         return "unavailable";
    }
}

static void usage(const char *p)
{
    fprintf(stderr,
        "Usage: %s [options]\n"
        "\n"
        "Target selection:\n"
        "  --pids PID[,PID...]     monitor specific PIDs (default: system-wide)\n"
        "  --comm NAME             monitor processes by command name\n"
        "  --cgroup PATH           monitor a cgroup v0.1 path\n"
        "  --target-container PATH cgroup path of a container tenant (alias of --cgroup)\n"
        "  --target-vm IFACE       VM target: host tap/vnet iface for netp; scope the\n"
        "                          other 6 metrics via --cgroup <qemu scope>\n"
        "  --tap-iface NAME        explicit host tap/vnet iface for VM netp\n"
        "\n"
        "Sampling:\n"
        "  --interval SECONDS      sampling interval (default 1.0)\n"
        "  --duration SECONDS      total run time (default infinite)\n"
        "  --output FORMAT         tsv (default), json, prometheus\n"
        "  --header                emit column header (tsv default on)\n"
        "  --no-header             suppress header\n"
        "\n"
        "Backend control:\n"
        "  --force-backend M:ID    force a backend, e.g. mbw:perf_uncore_imc\n"
        "  --disable-metric M      skip metric M entirely\n"
        "  --list-backends         print capabilities and exit\n"
        "  --portable-metrics      append the 6 VM-portable columns (schedlat\n"
        "                          psi_mem membw_est psi_io schedthr steal) --\n"
        "                          a SEPARATE benchmark; canonical 7 untouched (C26)\n"
        "\n"
        "Hardware overrides:\n"
        "  --nic-speed-bps N\n"
        "  --mem-bw-max-bps N\n"
        "  --llc-size-bytes N\n"
        "  --disk-bw-max-bps N     device max bandwidth for cgroup blk (else assumed)\n"
        "  --iface NAME            network interface (default: autodetect)\n"
        "  --disk NAME             block device (default: autodetect)\n"
        "\n"
        "  -h, --help              show this help\n",
        p);
}

static int read_cgroup_pids(const char *cgpath, pid_t *out, int max)
{
    return procutil_read_cgroup_procs(cgpath, out, (size_t)max);
}

typedef struct {
    char metric[16];
    char backend[64];
} force_spec_t;

static int parse_force(const char *spec, force_spec_t *out)
{
    const char *colon = strchr(spec, ':');
    if (!colon) return -1;
    size_t mlen = (size_t)(colon - spec);
    if (mlen == 0 || mlen >= sizeof(out->metric)) return -1;
    memcpy(out->metric, spec, mlen);
    out->metric[mlen] = '\0';
    snprintf(out->backend, sizeof(out->backend), "%s", colon + 1);
    return 0;
}

static const char *metric_order_names[] = {
    "netp", "nets", "blk", "mbw", "llcmr", "llcocc", "cpu"
};

/* VM-portable trailing columns (--portable-metrics, C26 / DESIGN §10), in the
 * canonical order shared with intp_portable_metrics() and v3.3. A SEPARATE
 * benchmark: the 7 canonical columns above are byte-identical with or without
 * --portable-metrics. */
static const char *portable_order_names[] = {
    "schedlat", "psi_mem", "membw_est", "psi_io", "schedthr", "steal"
};

static void format_value(char *buf, size_t bufsz, const metric_sample_t *s)
{
    if (s->status == METRIC_STATUS_UNAVAILABLE || isnan(s->value)) {
        snprintf(buf, bufsz, "--");
    } else {
        snprintf(buf, bufsz, "%.0f", s->value);
    }
}

static void emit_header_tsv(FILE *out, int want_portable)
{
    int n;
    metric_t **all = intp_all_metrics(&n);
    fprintf(out, "# v2 backends:");
    for (size_t i = 0; i < sizeof(metric_order_names)/sizeof(metric_order_names[0]); i++) {
        metric_t *m = NULL;
        for (int j = 0; j < n; j++)
            if (strcmp(all[j]->metric_name, metric_order_names[i]) == 0)
                m = all[j];
        const char *bid = (m && m->active) ? m->active->backend_id : "none";
        fprintf(out, " %s=%s", metric_order_names[i], bid);
    }
    if (want_portable) {
        int np;
        metric_t **port = intp_portable_metrics(&np);
        fprintf(out, " | portable:");
        for (int i = 0; i < np; i++) {
            const char *bid = port[i]->active ? port[i]->active->backend_id : "none";
            fprintf(out, " %s=%s", portable_order_names[i], bid);
        }
    }
    fprintf(out, "\n");
    if (want_portable)
        fprintf(out, "# portable metrics (C26 / DESIGN §10; SEPARATE benchmark): "
                     "schedlat psi_mem psi_io schedthr steal are %% of interval; "
                     "membw_est is a DRAM-bandwidth estimate in MB/s; '--' = source "
                     "unavailable on this host\n");
    fprintf(out, "netp\tnets\tblk\tmbw\tllcmr\tllcocc\tcpu");
    if (want_portable)
        for (size_t i = 0; i < sizeof(portable_order_names)/sizeof(portable_order_names[0]); i++)
            fprintf(out, "\t%s", portable_order_names[i]);
    fprintf(out, "\n");
}

static void emit_tsv(FILE *out, metric_sample_t samples[7],
                     metric_sample_t *port, int n_port)
{
    char b[16];
    for (int i = 0; i < 7; i++) {
        format_value(b, sizeof(b), &samples[i]);
        fprintf(out, i ? "\t%s" : "%s", b);
    }
    for (int i = 0; i < n_port; i++) {
        format_value(b, sizeof(b), &port[i]);
        fprintf(out, "\t%s", b);
    }
    fprintf(out, "\n");
}

static void emit_json_obj(FILE *out, const char *name, const metric_sample_t *s)
{
    fprintf(out, ",\"%s\":{\"v\":", name);
    if (isnan(s->value)) fprintf(out, "null");
    else                 fprintf(out, "%.3f", s->value);
    fprintf(out, ",\"status\":\"%s\",\"backend\":\"%s\"",
            status_str(s->status), s->backend_id ? s->backend_id : "none");
    if (s->note) fprintf(out, ",\"note\":\"%s\"", s->note);
    fprintf(out, "}");
}

static void emit_json(FILE *out, metric_sample_t samples[7], double t_sec,
                      metric_sample_t *port, int n_port)
{
    fprintf(out, "{\"t\":%.3f", t_sec);
    for (int i = 0; i < 7; i++) emit_json_obj(out, metric_order_names[i], &samples[i]);
    for (int i = 0; i < n_port; i++) emit_json_obj(out, portable_order_names[i], &port[i]);
    fprintf(out, "}\n");
}

static void emit_prometheus(FILE *out, metric_sample_t samples[7],
                            metric_sample_t *port, int n_port)
{
    for (int i = 0; i < 7; i++) {
        if (isnan(samples[i].value)) continue;
        fprintf(out,
            "intp_v2{metric=\"%s\",backend=\"%s\",status=\"%s\"} %.3f\n",
            metric_order_names[i],
            samples[i].backend_id ? samples[i].backend_id : "none",
            status_str(samples[i].status),
            samples[i].value);
    }
    for (int i = 0; i < n_port; i++) {
        if (isnan(port[i].value)) continue;
        fprintf(out,
            "intp_v2{metric=\"%s\",backend=\"%s\",status=\"%s\"} %.3f\n",
            portable_order_names[i],
            port[i].backend_id ? port[i].backend_id : "none",
            status_str(port[i].status),
            port[i].value);
    }
}

static void timespec_add_sec(struct timespec *ts, double secs)
{
    long whole = (long)secs;
    long nsec  = (long)((secs - (double)whole) * 1.0e9);
    ts->tv_sec  += whole;
    ts->tv_nsec += nsec;
    if (ts->tv_nsec >= 1000000000L) {
        ts->tv_sec  += ts->tv_nsec / 1000000000L;
        ts->tv_nsec %= 1000000000L;
    }
}

int main(int argc, char *argv[])
{
    intp_target_t target;
    memset(&target, 0, sizeof(target));

    double interval_sec    = 1.0;
    double duration_sec    = -1.0;        /* infinite */
    const char *out_fmt    = "tsv";
    int   want_header      = 1;
    int   list_backends    = 0;
    int   want_portable    = 0;           /* --portable-metrics (C26) */

    force_spec_t forces[16];
    int n_forces = 0;

    char disabled[16][16];
    int n_disabled = 0;

    enum { OPT_PIDS = 1000, OPT_COMM, OPT_CGROUP, OPT_INTERVAL, OPT_DURATION,
           OPT_OUTPUT, OPT_HEADER, OPT_NO_HEADER, OPT_FORCE, OPT_DISABLE,
           OPT_LIST, OPT_NIC_SPEED, OPT_MEM_BW, OPT_LLC, OPT_IFACE, OPT_DISK,
           OPT_DISK_BW, OPT_TARGET_CONTAINER, OPT_TARGET_VM, OPT_TAP_IFACE,
           OPT_PORTABLE };

    static struct option long_opts[] = {
        { "pids",            required_argument, NULL, OPT_PIDS },
        { "comm",            required_argument, NULL, OPT_COMM },
        { "cgroup",          required_argument, NULL, OPT_CGROUP },
        { "target-container",required_argument, NULL, OPT_TARGET_CONTAINER },
        { "target-vm",       required_argument, NULL, OPT_TARGET_VM },
        { "tap-iface",       required_argument, NULL, OPT_TAP_IFACE },
        { "interval",        required_argument, NULL, OPT_INTERVAL },
        { "duration",        required_argument, NULL, OPT_DURATION },
        { "output",          required_argument, NULL, OPT_OUTPUT },
        { "header",          no_argument,       NULL, OPT_HEADER },
        { "no-header",       no_argument,       NULL, OPT_NO_HEADER },
        { "force-backend",   required_argument, NULL, OPT_FORCE },
        { "disable-metric",  required_argument, NULL, OPT_DISABLE },
        { "list-backends",   no_argument,       NULL, OPT_LIST },
        { "nic-speed-bps",   required_argument, NULL, OPT_NIC_SPEED },
        { "mem-bw-max-bps",  required_argument, NULL, OPT_MEM_BW },
        { "llc-size-bytes",  required_argument, NULL, OPT_LLC },
        { "iface",           required_argument, NULL, OPT_IFACE },
        { "disk",            required_argument, NULL, OPT_DISK },
        { "disk-bw-max-bps", required_argument, NULL, OPT_DISK_BW },
        { "portable-metrics",no_argument,       NULL, OPT_PORTABLE },
        { "help",            no_argument,       NULL, 'h' },
        { 0, 0, 0, 0 }
    };

    int c;
    while ((c = getopt_long(argc, argv, "h", long_opts, NULL)) != -1) {
        switch (c) {
        case OPT_PIDS:
            target.n_pids = intp_parse_pid_list(optarg, target.pids, INTP_MAX_PIDS);
            break;
        case OPT_COMM:
            target.n_pids = intp_find_pids_by_comm(optarg, target.pids, INTP_MAX_PIDS);
            if (target.n_pids == 0)
                fprintf(stderr, "warning: no PIDs found for comm '%s'\n", optarg);
            break;
        case OPT_CGROUP:
            target.cgroup_path = optarg;
            target.n_pids = read_cgroup_pids(optarg, target.pids, INTP_MAX_PIDS);
            break;
        case OPT_TARGET_CONTAINER:
            /* Alias of --cgroup with an explicit container targeting hint. */
            target.cgroup_path = optarg;
            target.n_pids = read_cgroup_pids(optarg, target.pids, INTP_MAX_PIDS);
            target.kind = INTP_TARGET_CONTAINER;
            break;
        case OPT_TARGET_VM:
            /* VM netp comes from the host-side tap iface; the other 6 metrics
             * are scoped by a separate --cgroup <qemu scope> passed alongside. */
            target.tap_iface = optarg;
            target.kind = INTP_TARGET_VM;
            break;
        case OPT_TAP_IFACE:
            target.tap_iface = optarg;
            break;
        case OPT_INTERVAL: interval_sec = atof(optarg); break;
        case OPT_DURATION: duration_sec = atof(optarg); break;
        case OPT_OUTPUT:   out_fmt      = optarg;       break;
        case OPT_HEADER:    want_header = 1; break;
        case OPT_NO_HEADER: want_header = 0; break;
        case OPT_FORCE:
            if (n_forces < (int)(sizeof(forces)/sizeof(forces[0])) &&
                parse_force(optarg, &forces[n_forces]) == 0) {
                n_forces++;
            } else {
                fprintf(stderr, "bad --force-backend spec: %s\n", optarg);
                return 1;
            }
            break;
        case OPT_DISABLE:
            if (n_disabled < (int)(sizeof(disabled)/sizeof(disabled[0]))) {
                snprintf(disabled[n_disabled], sizeof(disabled[n_disabled]),
                         "%s", optarg);
                n_disabled++;
            }
            break;
        case OPT_LIST:        list_backends = 1; break;
        case OPT_PORTABLE:    want_portable = 1; break;
        case OPT_NIC_SPEED:   target.nic_speed_bps_override  = atol(optarg); break;
        case OPT_MEM_BW:      target.mem_bw_max_bps_override = atol(optarg); break;
        case OPT_LLC:         target.llc_size_bytes_override = atol(optarg); break;
        case OPT_IFACE:       target.iface = optarg; break;
        case OPT_DISK:        target.disk  = optarg; break;
        case OPT_DISK_BW:     target.disk_bw_max_bps_override = atol(optarg); break;
        case 'h':
        default:
            usage(argv[0]);
            return c == 'h' ? 0 : 1;
        }
    }

    if (interval_sec <= 0.0) {
        fprintf(stderr, "interval must be > 0\n");
        return 1;
    }

    intp_target_set(&target);
    setvbuf(stdout, NULL, _IOLBF, 0);

    system_capabilities_t caps;
    detect_all(&caps);

    /* Probe and select backends per metric, applying --disable and --force. */
    int n_metrics;
    metric_t **all = intp_all_metrics(&n_metrics);

    for (int i = 0; i < n_metrics; i++) {
        metric_t *m = all[i];

        int is_disabled = 0;
        for (int j = 0; j < n_disabled; j++) {
            if (strcmp(disabled[j], m->metric_name) == 0) { is_disabled = 1; break; }
        }
        if (is_disabled) { m->active = NULL; continue; }

        const char *forced = NULL;
        for (int j = 0; j < n_forces; j++) {
            if (strcmp(forces[j].metric, m->metric_name) == 0) {
                forced = forces[j].backend;
                break;
            }
        }
        if (forced) {
            if (metric_force_backend(m, forced) != 0) {
                fprintf(stderr,
                        "warning: --force-backend %s:%s failed (probe rejected)\n",
                        m->metric_name, forced);
                metric_select_backend(m);
            }
        } else {
            metric_select_backend(m);
        }
    }

    if (list_backends) {
        print_capabilities(&caps, stdout);
        printf("\n# selected backends:\n");
        for (int i = 0; i < n_metrics; i++) {
            metric_t *m = all[i];
            const char *bid = m->active ? m->active->backend_id : "none";
            const char *desc = m->active ? m->active->description : "no backend probed successfully";
            printf("  %-7s %-22s %s\n", m->metric_name, bid, desc);
        }
        printf("\n# backend candidates (ordered by priority):\n");
        for (int i = 0; i < n_metrics; i++) {
            metric_t *m = all[i];
            printf("%s:\n", m->metric_name);
            for (int j = 0; j < m->n_backends; j++) {
                backend_t *b = m->backends[j];
                if (!b) continue;
                const char *mark = (m->active == b) ? "*" : " ";
                printf("  %s %-22s %s\n",
                       mark, b->backend_id,
                       b->description ? b->description : "");
            }
        }
        return 0;
    }

    /* Init each selected backend. */
    int any_ok = 0;
    for (int i = 0; i < n_metrics; i++) {
        metric_t *m = all[i];
        if (!m->active) continue;
        if (metric_init(m) == 0) any_ok = 1;
    }
    if (!any_ok) {
        fprintf(stderr, "no metric backend could be initialized\n");
        return 1;
    }

    /* Probe + init the 6 VM-portable metrics (--portable-metrics, C26). A
     * SEPARATE list from the canonical 7 so the fingerprint path is unchanged
     * when the flag is off. A metric that probes/inits to nothing reads "--". */
    int n_port = 0;
    metric_t **port = NULL;
    if (want_portable) {
        port = intp_portable_metrics(&n_port);
        for (int i = 0; i < n_port; i++) {
            metric_select_backend(port[i]);
            if (port[i]->active) metric_init(port[i]);
        }
    }

    signal(SIGINT,  on_signal);
    signal(SIGTERM, on_signal);

    int is_tsv  = strcmp(out_fmt, "tsv") == 0;
    int is_json = strcmp(out_fmt, "json") == 0;
    int is_prom = strcmp(out_fmt, "prometheus") == 0;
    if (!is_tsv && !is_json && !is_prom) {
        fprintf(stderr, "unknown --output format: %s\n", out_fmt);
        return 1;
    }
    if (is_tsv && want_header) emit_header_tsv(stdout, want_portable);

    struct timespec start, wake;
    clock_gettime(CLOCK_MONOTONIC, &start);
    wake = start;
    timespec_add_sec(&wake, interval_sec);

    while (g_running) {
        if (clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, &wake, NULL) != 0) {
            if (!g_running) break;
        }
        timespec_add_sec(&wake, interval_sec);

        struct timespec now;
        clock_gettime(CLOCK_MONOTONIC, &now);
        double t = (double)(now.tv_sec - start.tv_sec)
                 + (double)(now.tv_nsec - start.tv_nsec) / 1.0e9;

        metric_sample_t samples[7];
        for (int i = 0; i < 7; i++) {
            metric_t *m = NULL;
            for (int j = 0; j < n_metrics; j++)
                if (strcmp(all[j]->metric_name, metric_order_names[i]) == 0)
                    m = all[j];
            metric_read(m, &samples[i], interval_sec);
        }

        /* Portable metrics read in canonical (intp_portable_metrics) order;
         * metric_read fills UNAVAILABLE ("--") for any with no active backend. */
        metric_sample_t port_samples[INTP_N_PORTABLE];
        for (int i = 0; i < n_port; i++)
            metric_read(port[i], &port_samples[i], interval_sec);

        if (is_tsv)  emit_tsv(stdout, samples, port_samples, n_port);
        if (is_json) emit_json(stdout, samples, t, port_samples, n_port);
        if (is_prom) emit_prometheus(stdout, samples, port_samples, n_port);

        if (duration_sec > 0 && t >= duration_sec) break;
    }

    for (int i = 0; i < n_metrics; i++) metric_cleanup(all[i]);
    for (int i = 0; i < n_port; i++)    metric_cleanup(port[i]);
    return 0;
}

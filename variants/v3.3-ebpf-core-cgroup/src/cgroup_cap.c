/*
 * cgroup_cap.c: see cgroup_cap.h. Same algorithm as the v2.1 variant's
 * procutil_cgroup_cpu_capacity() so both variants agree on the divisor.
 */

#include "cgroup_cap.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#define CGCAP_ROOT "/sys/fs/cgroup"

static int read_small_file(const char *path, char *buf, size_t n)
{
    FILE *f = fopen(path, "r");
    if (!f) return -1;
    size_t got = fread(buf, 1, n - 1, f);
    fclose(f);
    buf[got] = '\0';
    return (int)got;
}

int intp_count_cpulist(const char *list)
{
    if (!list) return -1;
    int count = 0;
    const char *p = list;
    while (*p) {
        while (*p == ',' || *p == ' ' || *p == '\n' || *p == '\t') p++;
        if (!*p) break;
        char *end = NULL;
        long a = strtol(p, &end, 10);
        if (end == p || a < 0) return -1;
        long b = a;
        if (*end == '-') {
            const char *q = end + 1;
            b = strtol(q, &end, 10);
            if (end == q || b < a) return -1;
        }
        count += (int)(b - a + 1);
        p = end;
        if (*p && *p != ',' && *p != '\n' && *p != ' ' && *p != '\t') return -1;
    }
    return count;
}

double intp_cgroup_cpu_capacity(const char *cgroup_path)
{
    if (!cgroup_path || !*cgroup_path) return -1.0;

    char path[1100], buf[4096];
    double cap = -1.0;

    snprintf(path, sizeof(path), "%s/cpuset.cpus.effective", cgroup_path);
    if (read_small_file(path, buf, sizeof(buf)) > 0) {
        int n = intp_count_cpulist(buf);
        if (n > 0) cap = (double)n;
    }
    if (cap <= 0.0) {
        long n = sysconf(_SC_NPROCESSORS_ONLN);
        cap = (n > 0) ? (double)n : 1.0;
    }

    /* cpu.max on the cgroup or any ancestor bounds the CPU time it can get:
     * "<quota> <period>" or "max <period>". The root cgroup has no cpu.max. */
    char dir[1024];
    if (strlen(cgroup_path) >= sizeof(dir)) return cap;
    snprintf(dir, sizeof(dir), "%s", cgroup_path);
    for (int depth = 0; depth < 64; depth++) {
        snprintf(path, sizeof(path), "%s/cpu.max", dir);
        if (read_small_file(path, buf, sizeof(buf)) > 0) {
            char quota[32];
            long period = 0;
            if (sscanf(buf, "%31s %ld", quota, &period) == 2 &&
                strcmp(quota, "max") != 0 && period > 0) {
                double lim = strtod(quota, NULL) / (double)period;
                if (lim > 0.0 && lim < cap) cap = lim;
            }
        }
        char *slash = strrchr(dir, '/');
        if (!slash || slash == dir) break;
        *slash = '\0';
        if (strcmp(dir, CGCAP_ROOT) == 0) break;
    }
    return cap;
}

/*
 * test-cgroup-cap.c: host-side unit test for the --cpu-norm cgroup divisor.
 *
 * Builds a fake cgroup tree under /tmp and checks that the capacity is the
 * cpuset.cpus.effective CPU count, capped by the tightest cpu.max quota on the
 * path or an ancestor. No BPF, no root.
 */

#define _GNU_SOURCE
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/stat.h>
#include <unistd.h>

#include "cgroup_cap.h"

#define ASSERT(c) do { if (!(c)) { \
    fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); return 1; } } while (0)

static int near(double a, double b) { return fabs(a - b) < 1e-9; }

static void write_cg_file(const char *dir, const char *name, const char *text)
{
    char p[256];
    snprintf(p, sizeof(p), "%s/%s", dir, name);
    FILE *f = fopen(p, "w");
    if (f) { fputs(text, f); fclose(f); }
}

int main(void)
{
    ASSERT(intp_count_cpulist("0-15\n") == 16);
    ASSERT(intp_count_cpulist("0-3,8,10-11") == 7);
    ASSERT(intp_count_cpulist("5") == 1);
    ASSERT(intp_count_cpulist("3-1") == -1);
    ASSERT(intp_count_cpulist("a-b") == -1);

    char top[] = "/tmp/intp-v33-cputest-XXXXXX";
    ASSERT(mkdtemp(top) != NULL);
    char child[96], leaf[128];
    snprintf(child, sizeof(child), "%s/child", top);
    snprintf(leaf, sizeof(leaf), "%s/leaf", child);
    ASSERT(mkdir(child, 0755) == 0);
    ASSERT(mkdir(leaf, 0755) == 0);

    write_cg_file(top, "cpuset.cpus.effective", "0-15\n");
    write_cg_file(top, "cpu.max", "max 100000\n");
    ASSERT(near(intp_cgroup_cpu_capacity(top), 16.0));

    write_cg_file(child, "cpuset.cpus.effective", "0-3,8,10-11\n");
    ASSERT(near(intp_cgroup_cpu_capacity(child), 7.0));

    write_cg_file(leaf, "cpuset.cpus.effective", "0-3,8,10-11\n");
    write_cg_file(leaf, "cpu.max", "150000 100000\n");
    ASSERT(near(intp_cgroup_cpu_capacity(leaf), 1.5));

    write_cg_file(child, "cpu.max", "100000 100000\n");      /* tighter ancestor */
    ASSERT(near(intp_cgroup_cpu_capacity(leaf), 1.0));

    ASSERT(intp_cgroup_cpu_capacity(NULL) <= 0.0);

    printf("test-cgroup-cap: OK (cpulist, cpuset, cpu.max, ancestor cap)\n");
    return 0;
}

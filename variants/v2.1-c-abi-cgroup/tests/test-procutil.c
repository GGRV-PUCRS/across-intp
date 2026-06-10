/*
 * test-procutil.c -- exercise procutil parsers against the live /proc.
 */

#include "procutil.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

#define ASSERT(cond)                                                    \
    do {                                                                \
        if (!(cond)) {                                                  \
            fprintf(stderr,                                             \
                    "FAIL %s:%d: %s\n", __FILE__, __LINE__, #cond);     \
            return 1;                                                   \
        }                                                               \
    } while (0)

static void write_procs(const char *dir, const char *body)
{
    char p[512];
    snprintf(p, sizeof(p), "%s/cgroup.procs", dir);
    FILE *f = fopen(p, "w");
    if (f) { fputs(body, f); fclose(f); }
}

/* Build a fake nested cgroup tree (top has NO direct procs, the payload lives in
 * child + grandchild cgroups -- the incus/lxc layout) and check that the
 * recursive reader captures the descendants the non-recursive one misses. */
static int test_cgroup_procs_recursion(void)
{
    char top[] = "/tmp/intp-cgtest-XXXXXX";
    if (!mkdtemp(top)) return 1;
    char leaf[64], sub[96];
    snprintf(leaf, sizeof(leaf), "%s/leaf", top);
    snprintf(sub, sizeof(sub), "%s/sub", leaf);
    ASSERT(mkdir(leaf, 0755) == 0);
    ASSERT(mkdir(sub, 0755) == 0);

    write_procs(top, "");                /* top: no internal processes */
    write_procs(leaf, "1001\n1002\n");   /* payload in the child cgroup */
    write_procs(sub, "1003\n");          /* and a grandchild */

    pid_t pids[16];
    int flat = procutil_read_cgroup_procs(top, pids, 16);
    ASSERT(flat == 0);                   /* non-recursive misses the nested payload */

    int rec = procutil_read_cgroup_procs_rec(top, pids, 16);
    ASSERT(rec == 3);                    /* recursive captures the whole subtree */
    int got1001 = 0, got1003 = 0;
    for (int i = 0; i < rec; i++) {
        if (pids[i] == 1001) got1001 = 1;
        if (pids[i] == 1003) got1003 = 1;
    }
    ASSERT(got1001 && got1003);

    /* cleanup */
    char rmpath[128];
    snprintf(rmpath, sizeof(rmpath), "%s/cgroup.procs", sub);  unlink(rmpath);
    snprintf(rmpath, sizeof(rmpath), "%s/cgroup.procs", leaf); unlink(rmpath);
    snprintf(rmpath, sizeof(rmpath), "%s/cgroup.procs", top);  unlink(rmpath);
    rmdir(sub); rmdir(leaf); rmdir(top);
    return 0;
}

int main(void)
{
    char buf[128];
    int n = procutil_read_file("/proc/uptime", buf, sizeof(buf));
    ASSERT(n > 0);

    long v = procutil_read_long("/proc/sys/kernel/pid_max");
    ASSERT(v > 0);

    diskstats_entry_t ds[32];
    int nd = procutil_read_diskstats(ds, 32);
    ASSERT(nd >= 0);  /* zero entries is valid on diskless test runners */

    netdev_entry_t nets[16];
    int nn = procutil_read_netdev(nets, 16);
    ASSERT(nn >= 1);  /* loopback at minimum */

    unsigned long net_tx = 0, net_rx = 0;
    int sr = procutil_read_net_softirqs(&net_tx, &net_rx);
    ASSERT(sr == 0);

    unsigned long total = 0, idle = 0;
    ASSERT(procutil_read_stat_total(&total, &idle) == 0);
    ASSERT(total > idle);

    unsigned long ut = 0, st = 0;
    ASSERT(procutil_read_proc_stat(getpid(), &ut, &st) == 0);
    /* utime+stime can legitimately be 0 for very fresh processes. */

    ASSERT(test_cgroup_procs_recursion() == 0);

    printf("test-procutil: OK (disks=%d ifaces=%d total_jiffies=%lu, cgroup-recursion)\n",
           nd, nn, total);
    return 0;
}

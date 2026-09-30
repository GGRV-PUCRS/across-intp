/*
 * test-procutil.c -- exercise procutil parsers against the live /proc.
 */

#include "procutil.h"

#include <pthread.h>
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
    char leaf[64], sub[96], dotlxc[96];
    snprintf(leaf, sizeof(leaf), "%s/leaf", top);
    snprintf(sub, sizeof(sub), "%s/sub", leaf);
    snprintf(dotlxc, sizeof(dotlxc), "%s/.lxc", top);   /* incus payload cgroup */
    ASSERT(mkdir(leaf, 0755) == 0);
    ASSERT(mkdir(sub, 0755) == 0);
    ASSERT(mkdir(dotlxc, 0755) == 0);

    write_procs(top, "");                /* top: no internal processes */
    write_procs(leaf, "1001\n1002\n");   /* payload in the child cgroup */
    write_procs(sub, "1003\n");          /* and a grandchild */
    write_procs(dotlxc, "1004\n");       /* payload in a ".lxc" dot-dir (incus/lxc) */

    pid_t pids[16];
    int flat = procutil_read_cgroup_procs(top, pids, 16);
    ASSERT(flat == 0);                   /* non-recursive misses the nested payload */

    int rec = procutil_read_cgroup_procs_rec(top, pids, 16);
    ASSERT(rec == 4);                    /* recursive captures the subtree incl. .lxc */
    int got1001 = 0, got1003 = 0, got1004 = 0;
    for (int i = 0; i < rec; i++) {
        if (pids[i] == 1001) got1001 = 1;
        if (pids[i] == 1003) got1003 = 1;
        if (pids[i] == 1004) got1004 = 1;   /* the ".lxc" payload must be found */
    }
    ASSERT(got1001 && got1003 && got1004);

    /* cleanup */
    char rmpath[128];
    snprintf(rmpath, sizeof(rmpath), "%s/cgroup.procs", sub);    unlink(rmpath);
    snprintf(rmpath, sizeof(rmpath), "%s/cgroup.procs", leaf);   unlink(rmpath);
    snprintf(rmpath, sizeof(rmpath), "%s/cgroup.procs", dotlxc); unlink(rmpath);
    snprintf(rmpath, sizeof(rmpath), "%s/cgroup.procs", top);    unlink(rmpath);
    rmdir(sub); rmdir(leaf); rmdir(dotlxc); rmdir(top);
    return 0;
}

static void write_file(const char *dir, const char *name, const char *body)
{
    char p[512];
    snprintf(p, sizeof(p), "%s/%s", dir, name);
    FILE *f = fopen(p, "w");
    if (f) { fputs(body, f); fclose(f); }
}

/* cgroup.threads recursion (C38): the parent slice lists no threads, the TIDs
 * live in two child cgroups; cgroup.procs is deliberately different (leaders
 * only) to prove the threads reader reads the right file. */
static int test_cgroup_threads_recursion(void)
{
    char top[] = "/tmp/intp-cgthr-XXXXXX";
    if (!mkdtemp(top)) return 1;
    char a[64], b[64];
    snprintf(a, sizeof(a), "%s/a", top);
    snprintf(b, sizeof(b), "%s/b", top);
    ASSERT(mkdir(a, 0755) == 0);
    ASSERT(mkdir(b, 0755) == 0);
    write_file(top, "cgroup.threads", "");
    write_file(a, "cgroup.procs",   "2001\n");
    write_file(a, "cgroup.threads", "2001\n2002\n2003\n");
    write_file(b, "cgroup.procs",   "3001\n");
    write_file(b, "cgroup.threads", "3001\n3002\n");

    pid_t tids[16];
    int n = procutil_read_cgroup_threads_rec(top, tids, 16);
    ASSERT(n == 5);
    int got2003 = 0, got3002 = 0;
    for (int i = 0; i < n; i++) {
        if (tids[i] == 2003) got2003 = 1;
        if (tids[i] == 3002) got3002 = 1;
    }
    ASSERT(got2003 && got3002);
    ASSERT(procutil_read_cgroup_threads_rec(top, tids, 3) == 3);   /* capped */

    char rm[128];
    const char *files[] = { "cgroup.procs", "cgroup.threads" };
    for (int i = 0; i < 2; i++) {
        snprintf(rm, sizeof(rm), "%s/%s", a, files[i]); unlink(rm);
        snprintf(rm, sizeof(rm), "%s/%s", b, files[i]); unlink(rm);
    }
    snprintf(rm, sizeof(rm), "%s/cgroup.threads", top); unlink(rm);
    rmdir(a); rmdir(b); rmdir(top);
    return 0;
}

static volatile int thr_stop;
static void *idle_thread(void *arg)
{
    (void)arg;
    while (!thr_stop) usleep(1000);
    return NULL;
}

/* /proc/<pid>/task expansion lists the leader AND its worker threads. */
static int test_proc_tasks(void)
{
    pthread_t th[3];
    for (int i = 0; i < 3; i++)
        ASSERT(pthread_create(&th[i], NULL, idle_thread, NULL) == 0);
    pid_t tids[16];
    int n = procutil_read_proc_tasks(getpid(), tids, 16);
    int leader = 0;
    for (int i = 0; i < n; i++) if (tids[i] == getpid()) leader = 1;
    int capped = procutil_read_proc_tasks(getpid(), tids, 2);
    thr_stop = 1;
    for (int i = 0; i < 3; i++) pthread_join(th[i], NULL);
    ASSERT(n == 4);
    ASSERT(leader);
    ASSERT(capped == 2);
    ASSERT(procutil_read_proc_tasks(0x7ffffff0, tids, 16) == 0);   /* no such pid */
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
    ASSERT(test_cgroup_threads_recursion() == 0);
    ASSERT(test_proc_tasks() == 0);

    printf("test-procutil: OK (disks=%d ifaces=%d total_jiffies=%lu, cgroup-recursion, threads, tasks)\n",
           nd, nn, total);
    return 0;
}

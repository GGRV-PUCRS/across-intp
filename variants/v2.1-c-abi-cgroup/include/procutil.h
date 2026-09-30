/*
 * procutil.h -- procfs/sysfs parsing helpers.
 *
 * Each function is side-effect-free and reads the entire target file.
 * Intended for use by the metric backends and the unit tests.
 */

#ifndef INTP_PROCUTIL_H
#define INTP_PROCUTIL_H

#include <stddef.h>
#include <sys/types.h>

int  procutil_read_file(const char *path, char *buf, size_t bufsize);
long procutil_read_long(const char *path);   /* -1 on failure */

typedef struct {
    char           name[32];
    unsigned long  reads_completed;
    unsigned long  writes_completed;
    unsigned long  read_ms;
    unsigned long  write_ms;
    unsigned long  io_ticks;          /* field 13: weighted busy time (ms) */
    unsigned long  time_in_queue;
} diskstats_entry_t;

/* Returns count of entries, or -1 on error. */
int procutil_read_diskstats(diskstats_entry_t *entries, size_t max);

typedef struct {
    char           iface[32];
    unsigned long  rx_bytes, tx_bytes;
    unsigned long  rx_packets, tx_packets;
} netdev_entry_t;

int procutil_read_netdev(netdev_entry_t *entries, size_t max);

/* Same parser as procutil_read_netdev but against an explicit path, so the
 * caller can read another task's network namespace via /proc/<pid>/net/dev
 * (per-container netp attribution). */
int procutil_read_netdev_at(const char *path, netdev_entry_t *entries, size_t max);

/* Sum NET_TX and NET_RX softirq columns across all CPUs. */
int procutil_read_net_softirqs(unsigned long *net_tx,
                               unsigned long *net_rx);

/* Read /proc/<pid>/stat utime + stime in jiffies. */
int procutil_read_proc_stat(pid_t pid,
                            unsigned long *utime,
                            unsigned long *stime);

/* Read aggregate /proc/stat first line. total includes user+nice+sys+
 * idle+iowait+irq+softirq+steal+guest+guest_nice. */
int procutil_read_stat_total(unsigned long *total_jiffies,
                             unsigned long *idle_jiffies);

/* /proc/<pid>/io for read_bytes / write_bytes. */
int procutil_read_proc_io(pid_t pid,
                          unsigned long long *read_bytes,
                          unsigned long long *write_bytes);

/* Read PIDs from <cgroup_path>/cgroup.procs into out[] (up to max). Returns the
 * count. Used to (re-)populate a resctrl mon_group from a cgroup's live member
 * set. */
int procutil_read_cgroup_procs(const char *cgroup_path, pid_t *out, size_t max);

/* Like procutil_read_cgroup_procs, but recurses into descendant cgroups too.
 * cgroup v2's "no internal processes" rule places a container's payload in LEAF
 * cgroups (incus/lxc, nested k8s pods), so a non-recursive read of the targeted
 * cgroup misses them. A task lives in exactly one cgroup, so the subtree union is
 * disjoint (no dedup needed). Used for the per-task portable metrics (psp,
 * per-PID schedlat) so they scope the whole container subtree, not just its root.
 * Also used by the resctrl rescan (C38): a compose suite's parent slice holds no
 * processes of its own, so a non-recursive rescan enrolled nothing. */
int procutil_read_cgroup_procs_rec(const char *cgroup_path, pid_t *out, size_t max);

/* Like procutil_read_cgroup_procs_rec, but reads cgroup.threads: every TID in the
 * subtree, not only thread-group leaders. /proc/<pid>/schedstat and the
 * *_ctxt_switches lines of /proc/<pid>/status describe ONE task_struct
 * (fs/proc/base.c proc_pid_schedstat, fs/proc/array.c
 * task_context_switch_counts), so per-task scheduler metrics must be read per
 * TID or a multi-threaded workload's worker threads are never counted (C38). */
int procutil_read_cgroup_threads_rec(const char *cgroup_path, pid_t *out, size_t max);

/* List the TIDs of process `pid` from /proc/<pid>/task into out[] (up to max).
 * Returns the count; 0 if the process is gone. */
int procutil_read_proc_tasks(pid_t pid, pid_t *out, size_t max);

#endif /* INTP_PROCUTIL_H */

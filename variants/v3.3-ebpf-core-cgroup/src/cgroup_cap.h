/*
 * cgroup_cap.h: CPU capacity of a cgroup v2 path (opt-in cpu normalization).
 *
 * The canonical IntP cpu metric divides on-CPU time by interval * online CPUs.
 * With --cpu-norm cgroup the divisor is the CPU capacity granted to the target
 * cgroup instead: the CPU count of its cpuset.cpus.effective, capped by the
 * tightest cpu.max quota/period on the path or any ancestor.
 */

#ifndef INTP_V33_CGROUP_CAP_H
#define INTP_V33_CGROUP_CAP_H

/* Number of CPUs in a cpuset list such as "0-3,8,10-11"; -1 on a parse error. */
int intp_count_cpulist(const char *list);

/* CPUs available to a cgroup v2 path: the CPU count of its
 * cpuset.cpus.effective (online CPUs when the file is absent), capped by the
 * tightest cpu.max quota/period found on the path or any ancestor. Fractional
 * when a quota applies (e.g. 1.5). Returns <= 0 when it cannot be determined. */
double intp_cgroup_cpu_capacity(const char *cgroup_path);

#endif /* INTP_V33_CGROUP_CAP_H */

/*
 * mt_spin.c -- multi-threaded load helper for the per-TID portable-metric
 * tests (C38, T1/T2).
 *
 *   mt_spin NTHREADS SECONDS [CHURN_MS]
 *
 * The leader thread only sleeps; NTHREADS worker threads spin. Pin the process
 * to fewer CPUs than NTHREADS (taskset) so the workers wait on the run queue
 * and are preempted involuntarily: per-thread schedstat run-delay and
 * nonvoluntary_ctxt_switches grow on the WORKERS, while the leader's stay ~0.
 * A TGID-only reader therefore sees ~0 and a per-TID reader does not.
 *
 * With CHURN_MS > 0 every worker exits after CHURN_MS and is replaced by a new
 * thread, so TIDs are born and die continuously (T2: no interval may collapse
 * to 0 while churn continues).
 */

#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#include <unistd.h>

static long churn_ms;
static volatile int stop_all;

static double now_s(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec + (double)ts.tv_nsec / 1e9;
}

static void *spin(void *arg)
{
    (void)arg;
    double until = churn_ms > 0 ? now_s() + (double)churn_ms / 1000.0 : 1e300;
    volatile unsigned long x = 0;
    while (!stop_all && now_s() < until)
        for (int i = 0; i < 10000; i++) x += (unsigned long)i;
    return NULL;
}

/* Keeps one worker slot alive: re-spawns its worker whenever it exits. */
static void *slot(void *arg)
{
    (void)arg;
    while (!stop_all) {
        pthread_t w;
        if (pthread_create(&w, NULL, spin, NULL) != 0) { usleep(1000); continue; }
        pthread_join(w, NULL);
    }
    return NULL;
}

int main(int argc, char **argv)
{
    if (argc < 3) {
        fprintf(stderr, "usage: %s NTHREADS SECONDS [CHURN_MS]\n", argv[0]);
        return 2;
    }
    int n = atoi(argv[1]);
    int secs = atoi(argv[2]);
    churn_ms = argc > 3 ? atol(argv[3]) : 0;
    if (n < 1 || secs < 1) return 2;

    pthread_t *th = calloc((size_t)n, sizeof(pthread_t));
    if (!th) return 1;
    for (int i = 0; i < n; i++)
        if (pthread_create(&th[i], NULL, churn_ms > 0 ? slot : spin, NULL) != 0)
            return 1;
    sleep((unsigned)secs);              /* the leader only sleeps */
    stop_all = 1;
    for (int i = 0; i < n; i++) pthread_join(th[i], NULL);
    free(th);
    return 0;
}

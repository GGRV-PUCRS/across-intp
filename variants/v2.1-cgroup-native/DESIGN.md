# V2.1 Design -- Cgroup-native hybrid (procfs / perf_event / resctrl)

V2.1 is V2 plus **continuous per-cgroup attribution**. Where V2 attributes by
a PID set (a snapshot that misses short-lived children), V2.1 adds a `cgroup`
backend at the head of the chain for every metric that has a stable
per-cgroup kernel interface, so attribution follows the cgroup's current *and*
future tasks with no PID re-scan:

| metric | cgroup-native source              | continuous?  |
|--------|-----------------------------------|:------------:|
| cpu    | cgroup v2 `cpu.stat usage_usec`   | yes          |
| blk    | cgroup v2 `io.stat` rbytes+wbytes | yes          |
| llcmr  | `perf_event_open` cgroup mode (`PERF_FLAG_PID_CGROUP`) | yes |
| mbw    | resctrl mon_group (PID set today) | partial      |
| llcocc | resctrl mon_group (PID set today) | partial      |
| netp   | per-netns `/proc/<pid>/net/dev`   | netns-scoped |
| nets   | **system-wide only** (softirq is host-global) | n/a |

`nets` is the one metric with no per-cgroup source: softirq CPU time
(`/proc/stat`, `/proc/softirqs`) is host-global and not namespaced, and the
kernel does not charge the net bottom-half to the originating task's cgroup.
So V2.1 attributes **6/7 metrics per-cgroup**; per-cgroup `nets` requires eBPF
(`cgroup/skb` or softirq tracepoints + cgroup id) and is left to the eBPF
variant. The selected backend is declared per metric in the output banner, so
a `cgroup` vs `procfs_system` choice is visible to consumers.

A container *is* a cgroup, so the same `cgroup` backends serve bare
co-located workloads, containers (point `--cgroup` at the container's cgroup),
and vm-guest profiling with one code path.

## 1. Architectural rationale

The dissertation's contribution rests on a portability survey of the seven
IntP interference dimensions. That survey concluded that, for the
seconds-resolution interference characterisation IntP targets, every
dimension can be observed through stable kernel ABIs already shipped by
mainstream distributions. V2 is the empirical proof of that finding: a
binary that collects all seven metrics, on all major server architectures,
without SystemTap, without eBPF, and without compiling against debuginfo.

V2 is **not** "one implementation with one code path". It is a
runtime-adaptive hierarchy of backends. Each metric carries an ordered
list; at startup the runtime probes them in order and binds the first one
that succeeds. The output declares the chosen backend per metric so
consumers can treat the data appropriately.

This separation -- backend hierarchy at the data-plane, capability
detection at the control-plane, target binding shared via a single
`intp_target_t` -- makes the variant credible across heterogeneous hardware
without giving up the simplicity of a single C99 binary.

## 2. Backend hierarchy per metric

The decision tree below is encoded in each `src/<metric>.c`. "ID" is the
string written into `metric_sample_t.backend_id` and the `# v2 backends:`
TSV banner.

### netp -- network physical utilisation

| order | id      | interface                                                           | min kernel | requires       |
|-------|---------|---------------------------------------------------------------------|------------|----------------|
| 1     | sysfs   | `/sys/class/net/<iface>/statistics/{rx,tx}_bytes`                   | 2.6        | none           |
| 2     | procfs  | `/proc/net/dev`                                                     | 2.0        | none           |

Both backends compute `(rx+tx)/interval / nic_speed_bps * 100`. NIC speed
unknown -> assume 1Gbps and report status=DEGRADED.

What we lose vs SystemTap: nothing meaningful for utilisation; per-packet
latency is out of scope for V2.

### nets -- network stack utilisation

| order | id                  | interface                                              | requires |
|-------|---------------------|--------------------------------------------------------|----------|
| 1     | procfs_softirq      | `/proc/softirqs` NET_TX+NET_RX + `/proc/stat` softirq  | none     |
| 2     | procfs_throughput   | `/proc/net/dev` packets * fixed 1us per-packet cost    | none     |

V0 measures real per-packet kernel service time via kprobes on
`__dev_queue_xmit` and `napi_complete_done`. V2 cannot replicate that
without kprobes; both backends report `status=DEGRADED` and a `note`
identifying the approximation. This is the metric where V2 honestly loses
the most fidelity, and the `note` makes that explicit at consumption time.

### blk -- block I/O utilisation

| order | id          | interface                                                   |
|-------|-------------|-------------------------------------------------------------|
| 1     | cgroup      | cgroup v2 `io.stat` rbytes+wbytes / device max bandwidth    |
| 2     | diskstats   | `/proc/diskstats` field 13 (`io_ticks`), aggregated         |
| 3     | sysfs       | `/sys/block/<dev>/stat`                                     |

The `cgroup` backend (selected when `--cgroup` is given) measures the cgroup's
I/O **throughput** as a fraction of device max bandwidth -- a *different*
physical quantity from the device-busy `%util` the diskstats / sysfs backends
report (cgroup v2 exposes per-cgroup bytes, not per-cgroup busy time).
Denominator precedence: `--disk-bw-max-bps` override (status ok) ->
`detect_disk_max_bps()` zero-I/O class estimate from device name +
`queue/rotational` (NVMe / SSD / HDD; status ok, note `detected_disk_bw`) ->
flat 500 MB/s fallback (status degraded).

`(io_ticks_delta / interval_ms) * 100` matches iostat's `%util`. Aggregated
backend skips loop / ram / zram / dm-* virtual devices and partitions.

### mbw -- memory bandwidth utilisation

| order | id              | interface                                  | vendor | min kernel | requires       |
|-------|-----------------|--------------------------------------------|--------|------------|----------------|
| 1     | resctrl_mbm     | `mbm_total_bytes` summed across L3 domains | any    | 4.10/5.1/6.19 | resctrl mounted, root |
| 2     | perf_uncore_imc | `uncore_imc_*` CAS_COUNT.RD+WR             | Intel  | any        | paranoid<=-1 / root   |
| 3     | perf_amd_df     | `amd_df` event 0x07 umask 0x38             | AMD Zen2+ | 5.0     | paranoid<=-1 / root   |
| 4     | perf_arm_cmn    | `arm_cmn` HN-F memory traffic              | ARM    | 5.13       | paranoid<=-1 / root   |

Normalised by `--mem-bw-max-bps` or `detect_memory_bandwidth_max_bps()`
(dmidecode if root, else DDR4-3200 dual-channel default).

What we lose vs V0 SystemTap: nothing if MBM/uncore PMU is available;
fewer Intel SKUs are accurate (per Sohal et al. RTNS 2022 and Intel errata
SKX99/BDF102, MBM may report up to 2x theoretical bandwidth on affected
hardware -- the kernel applies correction factors but the warning stands).

### llcmr -- LLC miss ratio

| order | id            | interface                                       | requires       |
|-------|---------------|-------------------------------------------------|----------------|
| 1     | perf_hwcache  | `PERF_TYPE_HW_CACHE` LL access/miss             | CAP_PERFMON    |
| 2     | perf_raw      | vendor-specific raw event codes (Intel/AMD/ARM) | CAP_PERFMON    |

Per-PID when target has PIDs; system-wide on cpu 0 otherwise. Per-PID uses
`inherit=1` so child threads count.

### llcocc -- LLC occupancy

| order | id                    | interface                                                   |
|-------|-----------------------|-------------------------------------------------------------|
| 1     | resctrl               | `llc_occupancy` summed across mon_L3_* (bytes / LLC size)   |
| 2     | proxy_from_miss_ratio | reuse llcmr value as a directional indicator (status PROXY) |

The proxy only signals direction (high miss rate -> contending for cache);
its magnitude is not directly comparable to bytes-of-cache-occupied. The
`status=PROXY` flag tells consumers to interpret accordingly.

### cpu -- CPU utilisation

| order | id              | interface                                                       |
|-------|-----------------|-----------------------------------------------------------------|
| 1     | cgroup          | cgroup v2 `cpu.stat usage_usec` / (ncpus * interval); continuous |
| 2     | procfs_pid      | `/proc/<pid>/stat` utime+stime delta over `/proc/stat` total    |
| 3     | procfs_system   | `/proc/stat` `(1 - idle/total) * 100`                           |

cgroup backend is selected when `--cgroup` names a cgroup v2 path (counts
current+future tasks, no PID snapshot); PID backend when `--pids` is non-empty;
system backend otherwise.

## 3. Tradeoffs vs V0 / V1

V2 cannot do sub-second event-driven detection. The polling loop wakes
once per `--interval`; transient spikes shorter than that are smoothed
into the surrounding window. V0's SystemTap probes are event-driven and
will catch them.

V2 cannot causally attribute interference between processes. resctrl
gives per-`mon_group` byte counters but does not say *whose* requests
hit *whose* cache lines. V0's kprobes can tag stack frames with the
calling task. For the dissertation's coarse-grained characterisation
this distinction is acceptable; for fine-grained debugging it is not.

V2's nets metric is an approximation. The softirq-fraction backend is
the best we can do without per-packet timestamps. Cross-validating
against V0 in Phase 3 will quantify the gap.

V2's resctrl-based backends consume one RMID per IntP run. RMIDs are a
hard resource (32-256 per system on Intel). See section 5.

## 4. Per-cgroup attribution strategy (V2.1)

V2.1 prefers a continuous cgroup-native source over the V2 PID-set approach
wherever one exists:

| metric  | cgroup-native (preferred)                             | fallback                                  |
|---------|-------------------------------------------------------|-------------------------------------------|
| cpu     | cgroup v2 `cpu.stat usage_usec` (continuous)          | `/proc/<pid>/stat` -> `/proc/stat`        |
| blk     | cgroup v2 `io.stat` rbytes+wbytes (continuous)        | `/proc/diskstats` io_ticks (device %util) |
| llcmr   | `perf_event_open` cgroup mode (`PERF_FLAG_PID_CGROUP`)| `perf_event_open(pid)`+`inherit=1` -> `(-1,cpu=0)` |
| mbw     | resctrl mon_group, PIDs re-scanned from `cgroup.procs`| system-wide via mon_group                 |
| llcocc  | resctrl mon_group, PIDs re-scanned from `cgroup.procs`| proxy from llcmr                          |
| netp    | own netns `/proc/<pid>/net/dev`                       | `/sys/class/net/...` system-wide          |
| nets    | none -- softirq is host-global                        | always system-wide                        |

The "continuous" backends (cpu, blk, llcmr cgroup mode) track the cgroup's
current and future tasks with no re-scan. mbw/llcocc re-scan `cgroup.procs` on
a cadence (every sample for the first few, then periodic --
`resctrl_rescan_cgroup`) and re-assign the live member set to their mon_group,
so tasks spawned after init (late-launched workers, cgroup migrations) are
picked up; RMID fork-inheritance covers descendants between re-scans. `nets`
has no per-cgroup source at all.

`--cgroup PATH` selects the cgroup for the continuous backends and seeds the
resctrl mon_group / per-PID fallbacks from `cgroup.procs`.

## 5. RMID budget management

resctrl exposes `/sys/fs/resctrl/info/L3_MON/num_rmids` -- typically 32-256
per L3 instance on Intel, similar on AMD. Each `mon_group` consumes one
RMID for the duration of its existence. V2 follows three rules:

1. **One run, one RMID.** mbw and llcocc share a single mon_group named
   `intp_v4_<pid>` rather than allocating two distinct groups.
2. **Cleanup on signal.** SIGINT/SIGTERM trigger `metric_cleanup()` on
   every backend, which calls `resctrl_remove_mongroup()`.
3. **Co-existence.** `resctrl_rmids_in_use()` is exposed for higher-level
   tooling to count existing groups. Recommended ceiling: keep total
   mon_groups + CTRL_MON groups under 75% of `num_rmids` so background
   tools (perf, intel-cmt-cat, kernel selftests) still have headroom.

## 6. Accuracy validation strategy

Each V2 backend is cross-validatable against an external reference:

- **mbw resctrl_mbm** vs **mbw perf_uncore_imc** on the same Intel host
  (use `--force-backend`). Per kernel selftests on Skylake-SP the gap is
  ~5%; larger gaps indicate firmware/microcode skew.
- **mbw** vs Intel PCM `pcm-memory.x` output (independent code path).
- **llcocc resctrl** vs Intel CMT-CAT `pqos -m` output.
- **cpu procfs_pid** vs `top -p <pid>`.
- **blk** vs `iostat -x 1` `%util` column (reads the same `io_ticks`).
- **netp** vs `nload` / `bmon` (sysfs counters, byte-comparable).
- **nets** has no clean reference; cross-validate against V0 directly.

Phase 3 of the dissertation runs the same workload under V0, V1, and V2
side-by-side and reports per-metric correlation.

## 7. Cross-environment behaviour

**Bare-metal**: all backends usable subject to privileges. Reference
configuration.

**Docker container**: `--privileged` plus a host bind-mount of
`/sys/fs/resctrl` is sufficient. Without privileges the container loses
mbw, llcmr, llcocc; netp/nets/blk/cpu still work. See
`scripts/test-environments.sh` for an end-to-end harness.

**KVM/QEMU VM**: resctrl and uncore PMU availability depend on host
configuration. With `<feature policy='require' name='pmu'/>` (libvirt) or
the equivalent, llcmr works; resctrl typically requires explicit host
support not enabled in default cloud images.

`detect_execution_environment()` reports the environment and the
`--list-backends` output makes the resulting selection visible.

## 8. Comparison points for Phase 3 evaluation

| metric  | V0 (SystemTap)               | V1 (refactored SystemTap+resctrl) | V2 (this variant)                      |
|---------|------------------------------|-----------------------------------|----------------------------------------|
| netp    | counter delta                | same                              | sysfs (byte-equivalent)                |
| nets    | per-packet service time      | same                              | softirq fraction (approximation)       |
| blk     | bio probe latency            | bio probe latency                 | io_ticks (iostat-equivalent)           |
| mbw     | RMID via kprobe              | resctrl                           | resctrl > IMC > AMD DF > ARM CMN       |
| llcmr   | perf events via SystemTap    | perf events via SystemTap         | perf_event_open direct                 |
| llcocc  | RMID via kprobe              | resctrl                           | resctrl > proxy                        |
| cpu     | task stats                   | task stats                        | /proc/<pid>/stat                       |

V2's overhead profile is fundamentally different: no kprobe insertion,
no debuginfo loading, deterministic sleep-poll loop. Phase 3 measures
RSS, CPU%, and decision-quality preservation versus V0.

## 9. Known limitations and honest framing

V2 is **not** a claim that eBPF or SystemTap are obsolete. They remain
the right tool for: per-event sub-millisecond detection, causal
attribution between processes, kernel-internal counters not exposed via
ABI, and any analysis where the loss of half-a-microsecond probe overhead
matters less than missing the event entirely.

V2 is the claim that, for **aggregate interference characterisation at
seconds-resolution as defined by IntP**, stable kernel ABIs are
sufficient. The dissertation's novelty is in the comparative analysis
that demonstrates this -- not in any one of these backends individually.

The honest framing for the document is: V2 trades a small amount of
fidelity (chiefly in nets) and per-process attribution depth for a large
reduction in deployment complexity (no kernel build, no debuginfo, single
C99 binary, works on locked-down kernels and inside containers/VMs). For
some operational contexts that trade is unambiguously worth it; for
others it is not. The dissertation's job is to make the boundary
quantitative.

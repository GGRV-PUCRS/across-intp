# V3.3 Design -- eBPF-native per-cgroup

> **Status: IMPLEMENTED (active variant).** The binary `intp-ebpf-cgroup` builds
> and runs: cgroup-identity gating, the `agg_per_cgroup` map, per-cgroup `netp`
> (`cgroup_skb`), `blk` (bio blkcg), `cpu`/`llcmr` (cgroup-mode perf), the
> system-wide `nets` numerator with loader-side byte-share split, and the
> `schedlat` VM-portable metric under `--portable-metrics`. It is the
> eBPF-native sibling of v2.1 and the per-cgroup sibling of v3.2; the bench
> harness accepts `v3.3` (`containerun24.sh`, the `container-lxc` env). Sections
> below give the full specification; where this document still reads as forward
> ("proposed", "open decision") that reflects validation work, not missing code.

## 1. Research positioning

v3.3 is the **eBPF-native per-cgroup endpoint**. It keeps v3.2's in-kernel
aggregation architecture (per-CPU + hash counter maps polled once per interval,
no ring buffer) but attributes events to a **cgroup**, not to a PID set.

The dissertation's comparison structure is two parallel axes, granularity held
fixed:

| Granularity   | stable-ABI (no eBPF) | eBPF            | Paper |
|---------------|----------------------|-----------------|-------|
| system-wide   | v2                   | v3.2            | #1 (SBAC-PAD, released) |
| per-cgroup    | **v2.1**             | **v3.3**        | #2 (container + IADA)   |

So **v2.1-vs-v3.3 is the paper-#2 counterpart of v2-vs-v3.2**. The question
v3.3 answers: *with eBPF, which per-cgroup attributions become possible that
the stable-ABI v2.1 cannot reach?* The honest answer (developed in §7) is
**the network metrics** -- and `nets` (softirq CPU time) in particular -- which
no cgroup-v2 file or resctrl group exposes per-cgroup.

## 2. Relationship to v3.2 and v2.1

**Reused from v3.2 verbatim** (`variants/v3.2-ebpf-core/`):
- CO-RE + libbpf skeleton build (`clang -target bpf -g` + `bpftool gen
  skeleton`), the `Makefile`, and the `test-amplification` acceptance gate.
- The counter-map aggregation pattern (`agg_global` PERCPU_ARRAY, `agg_zero`
  template) and the once-per-interval userspace poll loop.
- The probe sites: `net:net_dev_xmit` / `net:netif_receive_skb` (netp),
  `block:block_rq_issue` / `block_rq_complete` (blk), `sched:sched_switch`
  (cpu), `irq:softirq_entry` / `softirq_exit` vec 2,3 (nets), two
  `perf_event` LLC counters (llcmr). mbw/llcocc stay the userspace resctrl
  hybrid.

**Changed from v3.2:**
- The filter. v3.2 gates on PID identity --
  `pid_in_filter()` (`intp_agg.bpf.c:131`) tests a static `target_pids[]`
  seeded from `cgroup.procs` at attach plus a `descendant_tgids` hash kept by
  `sched_process_fork/exit`. That is membership-by-PID-lineage: a task
  **migrated into** the cgroup after attach (not forked from a tracked PID) is
  missed. v3.3 replaces it with **cgroup-identity** gating (§3) -- exact and
  migration-safe, no `/proc` seed, no fork-tracking.
- The aggregation key. v3.2's per-target map `agg_per_pid` is keyed by TGID;
  v3.3's `agg_per_cgroup` is keyed by cgroup id (§6).

**Relationship to v2.1** (`variants/v2.1-cgroup-native/`): same granularity
(per-cgroup), opposite mechanism (eBPF in-kernel vs stable-ABI polling). §7 is
the metric-by-metric comparison and is deliberately honest about where v3.3 is
parity, not advantage.

## 3. cgroup identity and gating

cgroup v2 gives every cgroup a stable 64-bit id equal to the inode number of
its directory in the unified hierarchy. Two halves:

**Userspace -> config map.** Resolve the `--cgroup PATH` to its id with
`stat(PATH, &st); target_cgid = st.st_ino;` (the kernfs id
`bpf_get_current_cgroup_id()` returns equals that inode). Also record the
target's **depth** in the hierarchy (count path components under
`/sys/fs/cgroup`) for ancestor matching. Push `{target_cgid, target_level}`
into the `intp_cfg_map`.

**BPF -> gate.** In task context:

```c
/* exact: this task's leaf cgroup IS the target */
if (bpf_get_current_cgroup_id() == cfg->target_cgid) ...

/* hierarchical: the target OR any descendant (whole-container, incl. sub-scopes
 * LXD/systemd create). Compare the ancestor at the target's level. */
if (bpf_get_current_ancestor_cgroup_id(cfg->target_level) == cfg->target_cgid) ...
```

v3.3 uses the **ancestor form** by default so a container's payload cgroup and
any sub-cgroups it spawns are all attributed -- the continuous, child-inclusive
property v2.1 gets from `cpu.stat` being hierarchical. The exact form is
available behind a flag for leaf-only studies.

This works directly for the **task-context** probes (cpu via `sched_switch`,
process-context blk submission). The **deferred-context** probes (softirq nets,
writeback blk) need a different handle -- see §4 and §5, because in softirq
`bpf_get_current_cgroup_id()` returns the *interrupted* task's cgroup, not the
work's owner. That asymmetry is the whole story of v3.3.

## 4. Per-metric attribution

| metric | mechanism in v3.3 | context | continuous? |
|--------|-------------------|---------|-------------|
| cpu    | on-cpu ns at `sched_switch`, keyed by ancestor-cgroup-id of the switching task | task | yes |
| blk    | svctm from `block_rq_issue`->`complete`; cgroup from the **bio's blkcg** (`bio->bi_blkg`) so writeback is attributed to the owning cgroup, not the flusher kworker | mixed | yes |
| llcmr  | LL$ loads/misses; per-cgroup via `perf_event_open` **cgroup mode** fds (one pair per CPU, as v2.1) OR BPF perf-overflow tagged by current-cgroup-id | task/PMU | yes |
| netp   | physical NIC bytes; **DECISION (§8.1)** -- keep device-level (as v3.2) or attribute per-cgroup via `cgroup/skb` | softirq | n/a |
| nets   | softirq CPU time in NET_TX/NET_RX; **per-cgroup via skb cgroup id + a cost model (§5)** -- the headline capability | softirq | yes |
| mbw    | resctrl MBM mon_group (RDT hardware; *not* eBPF) -- same as v2.1 | userspace | re-scanned* |
| llcocc | resctrl LLC-occupancy mon_group (RDT hardware; *not* eBPF) -- same as v2.1 | userspace | re-scanned* |

\* mbw/llcocc re-scan `cgroup.procs` on a cadence to re-populate the mon_group
(v2.1's `resctrl_rescan_cgroup`: tight at startup, then periodic); v3.3 inherits
it. True hardware continuity would need RDT features unrelated to eBPF.

**Reading:** cpu/blk/llcmr reach **parity** with v2.1's continuity (eBPF adds
sub-interval resolution and, for blk, a real svctm/queue-depth signal that
v2.1's byte-only `io.stat` lacks). mbw/llcocc are **RDT, not eBPF** -- identical
to v2.1, no advantage. The genuine eBPF-only per-cgroup capability is the
**network pair**, and `nets` specifically.

## 5. The `nets` attribution mechanism (the crux)

Softirq NET_RX/NET_TX service time is host-global: the softirq drains packets
for *all* cgroups, and `bpf_get_current_cgroup_id()` in `softirq_entry` returns
whoever was preempted. This is exactly why v2 (`/proc/softirqs`), v2.1, and even
v3.2 all keep `nets` system-wide. Making it per-cgroup is what v3.3 exists to
demonstrate.

Two ingredients:

1. **Per-cgroup network bytes** (the attributable signal). Attach a
   `BPF_PROG_TYPE_CGROUP_SKB` ingress+egress program to the target cgroup fd
   (or tag sockets with their cgroup via a `cgroup/sock_create` /`sockops` hook
   + `bpf_sk_storage`, then read it at `net_dev_xmit`). Either way yields
   `bytes(cgroup)` independent of softirq context.

2. **A cost model mapping bytes -> softirq time.** Measure total NET softirq
   CPU time host-wide exactly as v3.2 does (`softirq_entry/exit` deltas), then
   split it by each cgroup's byte share over the interval:

   ```
   nets(cgroup) = nets_systemwide * bytes(cgroup) / bytes_total
   ```

   This is an explicit, validatable approximation (per-packet cost is roughly
   uniform within an interval at steady state). The alternative -- bracketing
   each skb's processing and charging time by `bpf_skb_cgroup_id` -- is exact
   but high-overhead and fragile across kernels; we propose the cost model as
   the default and the per-skb method as a validation cross-check.

**Open question (§8.2):** validate the cost model against a controlled
two-cgroup network workload (one heavy, one idle) where ground-truth softirq
share is known by construction.

## 6. Aggregation maps

```c
struct intp_counters { /* unchanged from v3.2: netp/nets/blk/llcmr/cpu fields */ };

struct { __uint(type, BPF_MAP_TYPE_PERCPU_ARRAY);  __uint(max_entries, 1);
         __type(key, __u32);  __type(value, struct intp_counters); } agg_global;   /* host-wide totals (nets_systemwide, bytes_total) */

struct { __uint(type, BPF_MAP_TYPE_HASH);  __uint(max_entries, 1024);
         __type(key, __u64);  __type(value, struct intp_counters); } agg_per_cgroup; /* key = cgroup id */
```

Single-target runs (`--cgroup` once) only need `target_cgid` + `agg_global`;
`agg_per_cgroup` generalizes to "attribute every cgroup at once" (the IADA
whole-node view) without a probe rewrite -- the gate becomes "look up / create
the slot for `bpf_get_current_ancestor_cgroup_id(level)`" instead of comparing
to one id. Lazy slot creation seeds from `agg_zero`, exactly as v3.2's
`agg_per_pid_slot()`.

## 7. v2.1 vs v3.3 -- honest comparison

| metric | v2.1 (as implemented)                    | v3.3                              | eBPF advantage |
|--------|-------------------------------------------|-----------------------------------|----------------|
| cpu    | per-cgroup continuous (`cpu.stat`)        | per-cgroup continuous             | parity (+ sub-interval) |
| blk    | per-cgroup continuous (`io.stat` bytes)   | per-cgroup (bio blkcg -> svctm)   | + queue-depth/svctm signal |
| llcmr  | per-cgroup (`perf` cgroup mode)           | per-cgroup (same / BPF sampled)   | parity |
| mbw    | per-cgroup, re-scanned (resctrl mon_group)| per-cgroup, re-scanned (resctrl)  | parity (RDT, not eBPF) |
| llcocc | per-cgroup, re-scanned (resctrl mon_group)| per-cgroup, re-scanned (resctrl)  | parity (RDT) |
| netp   | per-container via **netns** (`/proc/<pid>/net/dev`); host-net/shared-netns -> system-wide | per-cgroup via `cgroup/skb` (socket-exact; shared-netns/host-net too) | generalizes v2.1's netns path |
| nets   | **system-wide** (softirq host-global)     | **per-cgroup** (skb + cost model) | **eBPF-only -- the headline** |

So v2.1 as built is **6/7 per-cgroup** for netns-isolated containers (cpu, blk,
llcmr continuous; mbw, llcocc resctrl re-scanned; netp via the container netns),
with only **`nets` system-wide**. v3.3's irreducible contribution is therefore
`nets` -- per-cgroup softirq attribution, impossible over stable ABIs -- plus a
more robust `netp` (socket-exact `cgroup/skb` that also covers the
`--net=host` / shared-netns cases where v2.1's netns trick degrades to
system-wide). Everything else is parity or RDT. This is the paper-#2 result:
*per-cgroup softirq attribution is the one thing eBPF uniquely buys at container
granularity*, mirroring how v3.2's softirq tracepoints beat v2's
`/proc/softirqs` system-wide in paper #1.

> Note: this DESIGN's investigation found `netp.c` read system-wide
> `/proc/net/dev` (so v2.1 was 5/7, not the 6/7 the docs claimed). That was
> fixed in the same cycle -- `netp.c` now has a netns backend
> (`/proc/<pid>/net/dev`, host-NIC-normalized), so v2.1 genuinely reaches 6/7
> for netns-isolated containers. METRICS-ALIGNMENT and the variant tables are
> reconciled to match.

## 8. Open decisions

### 8.1 netp scope
v3.2 counts netp **device-level/host-wide** (`intp_agg.bpf.c:204`: physical NIC
utilization, matches V2's non-lo sysfs counters). v2.1, however, now emits
**per-container netp** in the canonical column when `--cgroup` is set (netns
backend), so for the v2.1-vs-v3.3 axis (granularity held fixed) v3.3 should
**match: per-cgroup netp in the canonical column for container runs**, via
`cgroup/skb` socket attribution -- which additionally covers the shared-netns /
`--net=host` cases v2.1 cannot. **Recommendation:** canonical netp = per-cgroup
in container runs (mirrors v2.1); additionally emit a diagnostic device-level
`netp_dev` column (like v3.2's trailing `mbw_raw_mbps`) to retain cross-paper
comparability with v3.2's host-wide netp.

Caveat for the §8.2 validation: multiple apps in **one** container share that
container's netns, so v2.1's netns `netp` cannot separate app-A from app-B
inside it -- it sees only the container total. Per-app-within-a-container `netp`
is exactly where v3.3's `cgroup/skb` (one program per sub-cgroup) earns its
place. When the validation uses **one app per container** (container = the app
unit), app-netp == container-netp and v2.1 already suffices.

### 8.2 nets cost model + netp validation
**Implemented (v2.1 slice):** `bench/validate-attribution.sh` is the runnable-now
realization of this section and the §11 gate. It does *not* test the scheduler
(that is the CloudSim + real-cluster eval); it validates the **signal** the IADA
loop consumes -- each unit's per-cgroup reading tracks its own load, an idle
unit reads ~0, and the units sum to the whole (conservation) -- under a
heavy/idle split known by construction (stress-ng for the five separable
metrics, iperf3 at a fixed rate for `netp`).

Two complementary experiments ("Both (hybrid)"):

- **intra** -- apps as sub-cgroups in **one** container ("container = machine").
  Validates `cpu/blk/llcmr/mbw/llcocc` per app. `netp`/`nets` cannot split here
  (the apps share the container netns / host softirq), so the harness asserts
  exactly that limit (heavy ≈ idle ≈ container-total) and labels it
  `LIMIT[v3.3]` -- the gap v3.3 closes, not a defect.
- **inter** -- two sibling containers interfering on the host ("node =
  machine"). Each container is its own netns, so `netp` **is** per-unit here:
  validates `netp(A)` tracks A, `netp(B) ≈ 0`, `netp(A)+netp(B) ≈ system-wide`
  (backend `cgroup`), plus the five separable metrics per container. `nets`
  stays system-wide -> reported; per-container split is `SKIP[v3.3]`.

**Validated now vs deferred to v3.3.** The v2.1 harness covers the per-app five
metrics (intra), per-container `netp` (inter), and container-total `netp`/`nets`
conservation. The two items it marks `LIMIT[v3.3]`/`SKIP[v3.3]` -- per-app
`netp` inside one netns, and per-cgroup `nets` via the byte-share cost model
(§5) -- are precisely v3.3's deliverables; the **same** harness switches those
assertions on once the v3.3 binary exists (one heavy/idle network cgroup pair
gives the ground-truth `nets` share by construction). Real multi-container
nodes are the same machinery with the node as the "machine".

### 8.3 continuous mbw/llcocc
v2.1 now re-scans `cgroup.procs` on a cadence to re-populate the resctrl
mon_group (`resctrl_rescan_cgroup`), so v3.3 inherits continuous-enough RDT
attribution -- no separate work needed. The only residual gap is a worker that
spawns and exits entirely between re-scans; tighten `RESCAN_EVERY` if a
campaign shows it matters.

## 9. Harness wiring (thin -- already stubbed)

- `bench/run-intp-bench.sh`: add `run_profiler_v3_3` (clone of
  `run_profiler_v3_2`; `--cgroup`/`--pids`/system-wide dispatch identical, drop
  `--no-raw-mbw` unless v3.3 keeps a diagnostic column), a `variant_kernel_ok`
  case (>=5.8, cgroup v2, BTF), and a `stage_build` block. `container-lxc`
  already routes `--cgroup` to the launcher; `variant_env_ok` already allows it.
- `run-big-batch.sh`: `_variant_requested v3.3 && ... make -C
  variants/v3.3-ebpf-cgroup`.
- `containerun24.sh`: already accepts `BENCH_VARIANTS=v2.1,v3.3`.
- Root `Makefile` + `VERSIONS.md` + `METRICS-ALIGNMENT.md` + the variant tables:
  add v3.3 the way v2.1 was added this cycle.

## 10. Kernel and privilege requirements

- **Kernel >= 5.8**: `bpf_get_current_cgroup_id` (4.18) and
  `bpf_get_current_ancestor_cgroup_id` (5.6) predate it, but cgroup-mode perf
  and stable cgroup-v2 unified semantics align v3.3 with v2.1's floor.
  `cgroup/skb` is old (4.10); `bpf_sk_storage` is 5.2.
- **BTF** (`/sys/kernel/btf/vmlinux`) for CO-RE, as v3 / v3.2.
- **Privilege**: `CAP_BPF` + `CAP_PERFMON` (or root); attaching `cgroup/skb`
  needs `CAP_NET_ADMIN` and a writable handle to the target cgroup fd. resctrl
  for mbw/llcocc as in v2.1/v2.

## 10a. VM-guest behaviour (the structural RDT/PMU gap)

Under a stock KVM guest the RDT/PMU dimensions are gapped by construction, not
by a code path:

- **resctrl is host-only.** `mbw` and `llcocc` have no usable resctrl mount in
  the guest, so v3.3 emits `--` (NaN) for them and records them in
  `availability.tsv` as structurally unsupported -- never a faked 0 the cross-env
  layer could read as measured-zero ("do not fake it").
- **`llcmr` architectural fallback.** The model-specific LL-read perf events are
  not virtualized under the guest vPMU even with `pmu=on`. v3.3 probes the LL
  event on cpu 0 and, if it cannot open, switches all CPUs to the **architectural**
  `PERF_COUNT_HW_CACHE_REFERENCES`/`_MISSES` events (virtualized, and matched
  against the W4 ground-truth); the BPF side scales by the raised `sample_period`
  so counts stay correct. bare/host keeps the LL events, where the probe succeeds.

The canonical 7-metric contract is held intact across every environment. The
dimensions RDT cannot fill in the guest are instead covered by a separate,
flag-gated VM-portable benchmark (`--portable-metrics`): `schedlat` (run-queue
latency, §4), `psi_mem`, `membw_est`, `psi_io`, `schedthr`, and `steal` -- all
RDT/PMU-free. This is a distinct measurement block, not a substitution into the
canonical columns, so the ABI the IADA classifier consumes is unchanged.

## 11. Acceptance gate and validation

- Reuse v3.2's `test-amplification` (ctxsw ratio <= 1.10 on a 90 s window) --
  v3.3 is also in-kernel-aggregating, so it must pass.
- Cgroup correctness: run a pinned stress-ng in cgroup A and an idle cgroup B;
  assert v3.3(A) tracks the workload and v3.3(B) stays ~0 across all per-cgroup
  metrics.
- Per-cgroup attribution + nets cost-model validation:
  `bench/validate-attribution.sh` (§8.2). The v2.1 slice (per-app five metrics,
  per-container `netp`, conservation) runs today; v3.3 switches on the per-app
  `netp` and per-cgroup `nets` assertions the harness currently marks
  `SKIP[v3.3]`/`LIMIT[v3.3]`.
- Cross-check cpu/blk/llcmr against v2.1 on the same cgroup (should agree within
  the documented per-metric tolerance) -- this is the core paper-#2 measurement.

## 12. Known limitations / honest framing

- mbw/llcocc are **not** an eBPF story (RDT hardware); v3.3 = v2.1 there.
- nets per-cgroup is an **approximation** (cost model), not a hardware counter;
  its credibility rests on §8.2 validation.
- cpu/blk/llcmr per-cgroup is **parity** with v2.1, not novelty -- the eBPF
  framing should not oversell them. The paper's claim is narrow and correct:
  per-cgroup **network/softirq** attribution is the eBPF-only capability.
- Single shared NET softirq cost split by bytes assumes roughly uniform
  per-byte cost; pathological small-packet vs large-packet mixes across cgroups
  would skew it (documented, validated, not hidden).

## References

- v3.2 in-kernel aggregation: `variants/v3.2-ebpf-core/DESIGN.md`
- v2.1 cgroup-native (stable-ABI sibling): `variants/v2.1-cgroup-native/DESIGN.md`
- Paper-#1 v2-vs-v3.2 system-wide comparison: `METRICS-ALIGNMENT.md`,
  `docs/V3-OVERHEAD-FINDINGS.md`
- cgroup-skb / `bpf_skb_cgroup_id` / `bpf_get_current_ancestor_cgroup_id`:
  kernel `Documentation/bpf/` and `bpf-helpers(7)`

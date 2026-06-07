# A VM/hypervisor-portable 8th IntP metric — design proposal (`schedlat`)

**Status:** design proposal; the resolved build target is recorded in §10.
**Motivated by** the evaluation finding (C26) that the RDT/PMU metrics are
structurally gapped inside a KVM `vm-guest`, and by the IntP modernization
paper's future work: *"scheduling-latency metrics [39]"* (Volpert et al., ICPE
2025).

## 1. The hardware-proven gap

On a Sapphire Rapids testbed (kernel 6.17) the vm-guest smoke
established, on real hardware:

- `mbw` / `llcocc` are **structurally absent** in a stock KVM guest — `resctrl`
  is host-only (no vRDT pass-through). v3.3 now correctly emits `--` (C26).
- The profiler's LLC perf events (`LLC-loads` / `LLC-load-misses`,
  `PERF_TYPE_HW_CACHE LL|OP_READ`) are **`<not supported>`** by the KVM vPMU
  even with `-cpu host,pmu=on` (probe `bench/setup/vpmu-probe.sh`, cases D/E).
  Only the *architectural* `cache-references`/`cache-misses` count — a different,
  all-reference miss ratio that rounds to ~0 for low-miss workloads and is not
  magnitude-comparable to the LL-read `llcmr` reported in the other five envs.
- `cpu` (scheduler/`/proc`-based) is the **only** one of the seven that survives
  cleanly in-guest.

So the VM row has a cpu signal but no faithful cache/memory-contention signal.
The literature is unanimous on the consequence: a VM-portable signal exists for
the **scheduling-contention** slice of interference, and a *defensible-but-
indirect* proxy exists for the **memory-subsystem** slice — but **none** measures
LLC miss-rate / occupancy / DRAM bandwidth physically. Any new metric is
**equivalent-intent** (the victim is slowed by a noisy neighbour), **not
equivalent-mechanism**.

## 2. Design space (ranked by independence from RDT/PMU)

| Rank | Candidate | Measures | How (VM-portable) | Proxies | cgroup-scoped? |
|---|---|---|---|---|---|
| 1 | **`schedlat`** | run-queue / scheduling latency (`sched_wakeup`→`sched_switch` wait) | eBPF sched tracepoints; or `/proc/<pid>/schedstat` run-delay; or `cpu.pressure` | sched/CPU contention (direct); cache/mem (indirect, via slowdown) | **yes** |
| 2 | **`psi_mem`** | PSI memory pressure (reclaim/refault/swap stalls) | `/sys/fs/cgroup/<cg>/memory.pressure` (pure file read) | memory-**capacity** contention (mbw/llcocc *intent*, not bandwidth) | **yes** |
| 3 | `schedthr` | CFS throttling (own-quota) | `cpu.stat` `nr_throttled`/`throttled_usec` | **confound guard** for `schedlat` (not a contention signal) | yes |
| 4 | `steal` | hypervisor-stolen vCPU time | `/proc/stat` field 8 | host-level cross-VM CPU contention | **no** (whole-vCPU) |

**Why `schedlat` is primary.** It is the exact metric Paper 1's future work names;
Volpert ICPE'25 formalises it as *Average Process Scheduling Latency* (PSL);
PRISM exposes it as `rq_time`; the Netflix production eBPF detector and `bcc
runqlat` use the same `sched_wakeup`/`sched_switch` site that IntP's `cpu` metric
already attaches. It is **RDT-free and PMU-free**, **cgroup-scopable** (matching
IntP's per-tenant model), and the cheapest probe class. When a noisy neighbour
thrashes the LLC or saturates DRAM, the victim retires fewer instructions/cycle,
runs slower on-CPU, and its run-queue backs up — so `schedlat` rises *alongside*
the contention even when the victim under-uses its own CPU (Volpert's
Steal/Starving signature — the false-positive that CPU-utilization detectors
miss). **Faithfulness limit:** it is effect-based — it cannot decompose *which*
shared resource is contended the way RDT can.

**Why `psi_mem` is secondary.** It is the only `/proc`-readable, VM-portable
signal that fires on the **memory subsystem** (reclaim/refault/swap), so it is
the closest portable stand-in for the mbw/llcocc *intent*. **Critical limit:** it
is **capacity-driven, not bandwidth-driven** — a pure DRAM-bandwidth stressor
with ample free RAM can slow the victim without moving `memory.pressure`. So it
proxies `mbw` only under memory-pressure regimes and must be validated before any
equivalence claim (§6, Step 3).

`schedthr` is a **guard column** (separates an external noisy neighbour from a
tenant hitting its own CPU quota — Volpert's PSL×PSP matrix; Netflix's documented
failure mode), not an interference metric. `steal` is the only true cross-VM
signal but is **whole-vCPU (not cgroup-attributable)** and 0 on bare/container, so
it violates IntP's per-tenant contract — at most a VM-global side-channel.

## 3. Recommendation

Adopt **`schedlat`** as the primary new VM-portable metric (per-cgroup run-queue
wait %, on IntP's 0–100 scale), with **`psi_mem`** as a validated secondary
memory-dimension proxy and **`schedthr`** as a confound guard. This recovers the
scheduling-contention slice directly and the memory-subsystem slice indirectly,
with no RDT and no LL-perf counters, matching IntP's cgroup-scoped model and
Paper 1's stated future work.

## 4. `schedlat` definition

Per-cgroup run-queue latency on IntP's percent-of-capacity convention:

```
per task:  wait = t(sched_switch onto CPU) − t(sched_wakeup)
schedlat   = Σ(per-task runqueue-wait ns over interval) / (interval_ns × num_cores) × 100,  capped at 99 (like blk)
```

This is Volpert's PSL / PRISM's `rq_time` / `runqlat`, normalised so it shares the
`cpu`/`blk` scale.

## 5. Implementation sketches

### 5.1 v3.3 (eBPF, `intp_agg.bpf.c`)
- New per-tid HASH map `task_wakeup_ts {tid → ns}`.
- `tracepoint/sched/sched_wakeup` + `sched_wakeup_new`: stamp `bpf_ktime_get_ns()`.
- Charge the wait to the **incoming** task's cgroup at switch. The existing
  `tp_sched_switch` gates on `current` (= *prev*); the incoming task's cgroup
  needs `next`, so use a **`tp_btf/sched_switch`** program (typed `prev,next
  task_struct*`) and `cg_ptr_matches_target(cfg, BPF_CORE_READ(next, cgroups,
  dfl_cgrp))` — mirroring the existing deferred-context idiom. Aggregate
  `schedlat_wait_ns_sum` into `struct intp_counters` (reclaim a `_pad` slot to
  keep the 128-byte layout); the loader normalises per §4. No ring buffer.

### 5.2 v2.1 (C, `src/portable.c`, three backends like `cpu.c`)
- **(a) schedstat per-PID (preferred):** sum `/proc/<pid>/schedstat` field 2
  (run-delay ns) across the cgroup's PIDs (re-scan `cgroup.procs` each interval,
  like the resctrl path); Δ/(interval_ns×ncpus)×100. This is the preferred backend
  because its normalization MATCHES §4 and the v3.3 eBPF schedlat (cored
  sum-of-waits), so v2.1 and v3.3 series are cross-comparable.
- **(b) PSI cgroup (fallback):** parse `cpu.pressure` `some total=<us>`;
  Δ/interval_us×100. NOTE: PSI 'some' is a core-count-INDEPENDENT wall-clock stall
  *fraction* — a different quantity on a different scale from (a), NOT
  `× num_cores`-rescalable. It carries a distinct `backend_id` (`psi_cpu_*`) so the
  divergence is visible; do not mix PSI-sourced schedlat with cored (schedstat/eBPF)
  schedlat in one cross-env comparison.
- **(c) `/proc/pressure/cpu` system PSI fallback** (same scale caveat as (b)).
- Register `metric_schedlat()` in `backend.h` / `backend_registry.c`; the
  `cpu.stat` parse in `cpu.c` is the file-read template.

`psi_mem` and `schedthr` need **no eBPF** in either variant — both the v3.3 loader
and v2.1 read the per-cgroup `memory.pressure` / `cpu.stat` files directly each
interval (the loader already reads resctrl `mon_data` files).

### 5.3 Portability
`sched_wakeup`/`sched_switch`, `/proc/<pid>/schedstat`, `cpu.pressure`,
`memory.pressure`, `cpu.stat` are all computed by the **guest's own kernel** —
independent of host resctrl and the KVM vPMU. eBPF path needs CAP_BPF + BTF +
cgroup-v2 (already the v3.3 floor); PSI needs `CONFIG_PSI=y` (≥4.20, sometimes
`psi=1` boot param); schedstat needs `CONFIG_SCHEDSTATS`.
**Caveat:** eBPF scheduler instrumentation can subtly perturb the scheduler, and
CFS (<6.6) vs EEVDF (≥6.6) differ — treat `schedlat` as a within-host *relative*
signal, not a cross-kernel absolute (Volpert §8).

## 6. Validation plan (reuse the §1b llcmr-vs-GT machinery)

1. **Emit as trailing diagnostic columns** (diagnostic-first stage, non-breaking
   — see §7) and run the existing solo campaign on **bare + container** (the 5 W4
   workloads).
2. **Correlate** per (env,variant,workload): Spearman rank of `schedlat` vs the
   perf-GT `llcmr` and resctrl-GT `mbw`/`llcocc` already in `groundtruth.tsv` —
   the exact directional-faithfulness pattern `analyze-faithfulness.py` §1b runs.
   Admissible if ρ is consistently positive/significant on the cache (app01) and
   memory (app07) stressors.
3. **Falsification test** (the literature gap): run a *pure DRAM-bandwidth*
   stressor with ample free RAM (`stress-ng --stream`/`--memrate`, **not**
   `--vm`). If `psi_mem` stays ~0 while GT `mbw` is high → `psi_mem` is
   bandwidth-blind → label it capacity-only (`descriptive`). Confirm `schedlat`
   *does* rise under that stressor on an oversubscribed host.
4. **Colocation discrimination** (pairwise stage): victim `schedlat` rises while
   its own `cpu` does not (Volpert Steal/Starving); `schedthr` stays low for true
   external interference, high for a self-throttled tenant.
5. **vm-guest confirmation:** same workloads in-guest — verify the per-cgroup
   counter aggregates non-zero and the rank-ordering matches bare/container while
   mbw/llcocc/llcmr are `--`.
6. **Overhead:** confirm the sched programs stay in the cheap class (in-kernel
   agg, no ring buffer); watch the scheduler-perturbation threat.

## 7. Design decisions (rationale; resolved target in §10)

1. **Scope:** `schedlat` alone (single canonical 8th), or `schedlat` + `psi_mem`
   (8th + 9th)? One metric is the cleanest schema change; the pair is more
   faithful (sched + memory dimensions). *Recommended:* `schedlat` canonical;
   `psi_mem` as a validated diagnostic that promotes to 9th only if it adds
   non-redundant signal (Step 3).
2. **Integration shape:** the **diagnostic-first stage** (trailing diagnostic
   columns, validate first, byte-compatible with the 7-metric `off=n-7` contract)
   → the **canonical-promotion stage** (promote to canonical 8th: bump
   `metric_order_names[]`/`samples[]`, `off=n-7`→`off=n-8`, every TSV header,
   `CLAIM_CLASS`, `METRICS`). *Recommended:* diagnostic-first stage first.
3. **eBPF attribution:** confirm switching/adding a `tp_btf/sched_switch` program
   to read `next->cgroups` (verifier/portability decision on 6.17).
4. **`steal`:** include as a VM-global descriptive side-channel, or omit (violates
   cgroup-attribution)? The GT collector already reads it.
5. **`psi_mem` disposition** if bandwidth-blind (Step 3): ship as capacity-only
   `descriptive`, or lean entirely on `schedlat` for the memory dimension?
6. **Output:** raw continuous 0–100 (consistent with the other six), or also a
   derived noisy-neighbour boolean via the `schedlat`×`schedthr` matrix?
   *Recommended:* raw number (IntP's "emit the number" philosophy).

## 8. Claim class & cross-env wiring (when promoted)

`schedlat` → `directional` (faithful for the sched/cpu dimension, directional for
mem); `psi_mem` → `descriptive` (capacity-only proxy); `schedthr` → `descriptive`
(guard); `steal` → `descriptive`, VM-only (add to `UNSUPPORTED` for
bare/container). `schedlat` is the **first** metric fully available in vm-guest —
it is added to *nothing* in the `UNSUPPORTED` map. The cross-env BH-FDR / KW /
Cliff's-δ machinery iterates `METRICS`, so widening it auto-includes the column.
Later, inject the system-wide backends into v2/v3.2 (the per-PID bare-metal
versions) for completeness.

## 9. Sources

- **Volpert, Winkelhofer, Domaschka, Wesner**, *"Detecting Noisy Neighbors in
  CPU-Isolated Cgroups Environments"*, ICPE '25, pp. 224–231 (PSL; PSL×PSP
  decision matrix; Steal/Starving scenarios). — Paper 1 ref [39].
- **Landau, Barbosa, Saurabh**, *PRISM* (`rq_time`; runtime/run-queue as a
  memory-contention proxy). — ref [38].
- **Becker / Gögge**, *iprof* (Gögge MSc thesis, run-queue occupancy via
  `finish_task_switch`). — refs [36],[37].
- **Fernandez et al.** (Netflix), eBPF noisy-neighbour detector
  (`sched_wakeup`/`sched_switch`, cgroup-id keying). — ref [29].
- **Xavier** PhD thesis §3.3.1 (CPU steal as the virtualization CPU-contention
  metric). — ref [7].
- **Weiner et al.**, PSI (LWN 2018); kernel PSI docs; CFS bandwidth-control docs.
- **Verdu et al.**, *Platform-Agnostic Steal-Time Measurement* (steal excludes
  cache/bandwidth contention).
- Web literature search (response-time vs scheduling-latency correlation; Netflix
  per-hook cost); figures to be re-verified before any paper claim.

*Synthesized from the local literature corpus (Volpert ICPE'25, PRISM, iprof,
the Xavier thesis) and external sources (PSI, CPU steal time, run-queue latency),
reconciled with the IntP modernization paper's future-work and related-work.*

## 10. Resolved build target (decisions locked)

After review, the build target is:

- **Metric set (6, VM-portable):** `schedlat` (run-queue latency, eBPF
  `sched_wakeup`→`sched_switch`), `psi_mem` (PSI `memory.pressure`), **`membw_est`**
  (architectural LLC-miss × cacheline → DRAM-**bandwidth** estimate — the `mbw`
  complement `psi_mem` is blind to, since the vPMU virtualizes architectural
  `cache-misses`), `psi_io` (PSI `io.pressure` — `blk`'s contention companion),
  `schedthr` (CFS-throttle guard), `steal` (VM-global host-stolen CPU; not
  cgroup-scoped).
- **Architecture — a SEPARATE benchmark, NOT a canonical-schema expansion.** The
  canonical 7-metric fingerprint, the `off=n-7` contract, stap-variant
  byte-compat, and the IADA classifier's 7-metric input vector stay UNTOUCHED
  (Paper 1's ABI-invariance thesis). The 6 portable metrics are emitted as a
  flag-gated block (`--portable-metrics`) into a separate `portable-means.tsv`,
  with their own cross-env + faithfulness analysis, run as a dedicated campaign
  and validated against the canonical RDT/`llcmr`/`mbw` GT where both exist.
  This supersedes the §3/§7 single-primary, canonical-leaning recommendation.
- **Claim classes:** `schedlat` = directional; `psi_mem`/`psi_io`/`membw_est` =
  descriptive; `schedthr` = descriptive (guard); `steal` = descriptive, VM-only.
- **Variants:** v3.3 (eBPF) + v2.1 (C) first; inject the system-wide backends
  into v2/v3.2 after validation. (Recorded in DECISIONS-container.md C26.)

## 11. Implementation status

The local build of the separate `--portable-metrics` benchmark is **complete and
compiles clean** (steps 1–4 below); remote validation (step 5) and the v2/v3.2
back-port (step 6) remain. See DECISIONS-container.md **C27**.

**`membw_est` net-path caveat (C31):** on net-heavy workloads the eBPF variant
(v3.3) over-reports `membw_est` (~6–7× v2.1 on app11) because per-packet eBPF net
hooks add cache misses to the counter it integrates (independent host GT confirms
~3.6× the system LLC misses v2.1 generates). The **canonical 7 are unaffected**
(`mbw`/`llcmr` are %-normalized → the footprint rounds to 0). Mitigation is
**document + the `analyze-portable.py` §4 corroboration gate** (flag cells where
`membw_est`>0 but `mbw`≈0 and `llcmr`≈0), NOT sampling (which would cost `netp`/`nets`
accuracy). See **C31**.

1. **v3.3 loader (`variants/v3.3-ebpf-core-cgroup/src/intp_agg.c`) — DONE.** schedlat
   (eBPF, already in the BPF object + counter) was moved out of the diagnostic
   block into the portable block. Added file-read helpers (`read_psi_some_total_us`,
   `read_cpu_stat_throttled_us`, `read_proc_stat_steal`), per-interval `psi_mem`,
   `psi_io`, `schedthr`, `steal`, and `membw_est` (reuses the existing `llc_misses`
   counter × 64 B / interval → MB/s, so it survives the vPMU gap in-guest). The 6
   are emitted as a trailing block (TSV/JSON/Prometheus) only under
   `--portable-metrics`; the canonical 7 + 4 diagnostic columns are unchanged.
2. **v2.1 backends (`variants/v2.1-c-abi-cgroup/src/portable.c`) — DONE.** Six
   `metric_t` chains in the existing backend-registry pattern: schedlat
   (`cpu.pressure` → per-PID `schedstat` → `/proc/pressure/cpu`), psi_mem/psi_io
   (cgroup pressure → `/proc/pressure/*`), schedthr (`cpu.stat`, cgroup-only),
   steal (`/proc/stat`), membw_est (cgroup-mode/per-PID perf cache-misses, with the
   architectural fallback). Exposed via a SEPARATE `intp_portable_metrics()` list
   (the canonical `intp_all_metrics()` returns exactly 7, unchanged) and appended
   by `intp-hybrid.c` only under `--portable-metrics`.
3. **Orchestrator (`bench/run-intp-bench.sh`) — DONE.** `--portable-metrics`
   captures into `portable.tsv` (canonical `profiler.tsv` / `off=n-7` report
   untouched) and aggregates header-aware into `aggregate-portable-means.tsv`
   (`stage_report_portable`). The flag threads into the container and in-guest
   (vm-guest) profiler invocations. Only v2.1/v3.3 implement it — pair with
   `--variants v2.1,v3.3`.
4. **Analyzer (`bench/analyze-portable.py`) — DONE.** The portable sibling of
   `analyze-faithfulness.py`: availability matrix (the vm-guest headline —
   portable `ok` while RDT `--`), Spearman of membw_est/schedlat/psi_mem vs the
   perf GT, the PSI bandwidth-blindness falsification (§6 step 3), and the vm-guest
   confirmation table.
5. **Validation campaign + report — PENDING (remote/testbed, single-flight).**
   Run `--portable-metrics --variants v2.1,v3.3 --env bare,container,vm-guest`
   incl. `app05_streaming` (the saturating mem-bandwidth driver the falsification
   needs), then `analyze-portable.py`.
6. **v2/v3.2 system-wide back-port — PENDING (after validation).**

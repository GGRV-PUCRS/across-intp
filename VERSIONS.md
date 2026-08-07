# IntP variant naming

This document maps the variant naming after the 2026-05-05 reorganization.
Use it to translate references between the legacy naming (used in commits
before the rename, in the original IntP paper, and in the `pre-rename-2026-05-05`
git tag) and the current naming (used everywhere else).

The active profiler variants for the container + cross-deployment work are
**v2.1 (c-abi-cgroup)** (C, per-cgroup via stable kernel ABIs) and
**v3.3 (ebpf-core-cgroup)** (eBPF/CO-RE, in-kernel aggregation); v0.x–v3.2 remain as
comparison and structural evidence. All variants emit the same canonical
7-metric contract — `netp nets blk mbw llcmr llcocc cpu` — as the leading
columns; this ordering is ABI-invariant (the IADA classifier consumes it) and
is what each row below means by "the canonical IntP fingerprint".

## Naming scheme

Major version groups variants by *paradigm*; minor version distinguishes
implementations within the same paradigm.

- **v0.x** -- legacy SystemTap. v0 / v0.1 are kept read-only for paper
  reproducibility; v0.2 (new) ports the V0 semantics to a userspace-helper
  pattern so the U22 / kernel 5.15 GA leg is runnable without the V0
  fragility cliff.
- **v1.x** -- modern SystemTap. Active.
- **v2.x** -- userspace C using stable kernel ABIs (procfs, perf_event_open,
  resctrl). Active. v2 attributes system-wide / per-PID; **v2.1** (new) adds
  continuous per-cgroup attribution (cgroup v2 `cpu.stat`/`io.stat`, perf
  cgroup mode) for the container / VM + IADA work -- the c-abi-cgroup, no-eBPF
  analogue of v3.2's per-cgroup path. `nets` stays system-wide (softirq is
  host-global without eBPF).
- **v3.x** -- eBPF-based implementations. Active. v3 streams events
  through a ring buffer (predecessor); v3.1 is the bpftrace companion;
  **v3.2** is the in-kernel-aggregation endpoint (paper §III-A)
  that supersedes v3 as the measured eBPF endpoint; **v3.3** (new)
  scopes the v3.2 design to a single cgroup (`cgroup_skb` + cgroup-id
  counter maps) -- the eBPF-native sibling of v3.2 and companion to
  v2.1 for the container / IADA work. Its `nets` is a per-cgroup proxy
  (byte-share cost model) that diverges by design from v2.1's
  system-wide `nets`.

## Mapping

The **Name** column is the descriptive, paper-facing name used verbatim in the
plot legends/titles (see `VARIANT_LABELS` in `bench/plot/*.py`). The four
**measured** versions are **v0.2 (legacy-intp-baseline)**, **v1.1 (stap-modern)**,
**v2 (C-ABI)** and **v3.2 (eBPF-CORE)**. In paper prose v0 is also referred
to as the "2022 baseline".

| Current | Name | Legacy | Directory | Approach | Status |
|---------|------|--------|-----------|----------|--------|
| v0      | stap-2022    | v1     | `variants/v0-stap-2022/`        | Original IntP paper, SystemTap + embedded C, MSR-direct RDT, kernel 4.x baseline | Reference only |
| v0.1    | stap-nollc   | v2     | `variants/v0.1-stap-nollc/`          | v0 patched for kernel 6.8: removes `cqm_rmid` access and conflicting MSR redefinitions; LLC occupancy disabled | Reference only |
| v0.2    | legacy-intp-baseline  | (new)  | `variants/v0.2-legacy-intp-baseline/`       | V0 probe set (paper-faithful for netp/nets/blk/llcmr/cpu) + userspace helper for the two RCU-unsafe operations (uncore IMC via `perf_event_open` syscall, LLC occupancy via resctrl mon\_groups). Target kernel **5.15 GA / Ubuntu 22.04**; same helper pattern v1.1 uses on 6.8+ | Active (legacy-V0 campaign) |
| v1      | stap-nohelper| v3*    | `variants/v1-stap-nohelper/`         | Stap-only, native probes (`probe perf.type(3).config(...).process(@1)`); no embedded C creating perf events; mbw and llcocc reported as 0 | Active |
| v1.1    | stap-modern  | (new)  | `variants/v1.1-stap-modern/`       | New build: stap for software metrics + userspace helper for hardware metrics (uncore IMC via `perf_event_open` syscall, LLC occupancy via resctrl mon\_groups). Helper architecture isolates RCU-unsafe operations from probe context | Active |
| v2      | C-ABI     | v4     | `variants/v2-c-abi/`        | Pure C (no framework): procfs polling, `perf_event_open` syscall, resctrl filesystem. Runtime-adaptive backend hierarchy | Active |
| v2.1    | c-abi-cgroup | (new)  | `variants/v2.1-c-abi-cgroup/`    | v2's hybrid-C backends with **per-cgroup attribution**: cgroup v2 `cpu.stat`/`io.stat`, `perf_event_open` cgroup mode (LLC), resctrl mon\_groups; disk bandwidth self-detected. `nets` stays system-wide. One code path for bare co-located + container + VM-guest. Target kernel **5.8+** (cgroup v2). See `variants/v2.1-c-abi-cgroup/DESIGN.md` | Active (container / IADA, paper #2) |
| v3      | ebpf-ring    | v6     | `variants/v3-ebpf-ring/`         | C + libbpf + CO-RE; software metrics through 16 MiB ring buffer (streaming pattern); hardware metrics through resctrl. **Predecessor of v3.2**; retained for overhead-evidence documentation. | Active (predecessor) |
| v3.1    | bpftrace     | v5     | `variants/v3.1-bpftrace/`          | bpftrace DSL scripts + Python orchestrator + resctrl. SystemTap-script-style ergonomics on top of eBPF | Active (companion) |
| v3.2    | eBPF-CORE     | (new)  | `variants/v3.2-ebpf-core/`    | C + libbpf + CO-RE with **in-kernel aggregation**: `BPF_MAP_TYPE_PERCPU_ARRAY` + `BPF_MAP_TYPE_HASH` counters polled once per interval (no ring buffer). Eliminates the 194-416x context-switch amplification documented for v3; emits both `mbw_pct` and `mbw_raw_mbps`. See `variants/v3.2-ebpf-core/DESIGN.md` and `docs/V3-OVERHEAD-FINDINGS.md`. | Active (measured eBPF endpoint) |
| v3.3    | ebpf-core-cgroup   | (new)  | `variants/v3.3-ebpf-core-cgroup/`    | C + libbpf + CO-RE with **per-cgroup attribution**: the in-kernel-aggregation design of v3.2 (counter maps polled once per interval, no ring buffer) scoped to one cgroup via `cgroup_skb` (netp) and cgroup-id-keyed counter maps. The **eBPF-native sibling of v3.2** and the **companion to v2.1**: same per-cgroup question, eBPF mechanism instead of c-abi-cgroup stable ABIs. `nets` is a per-cgroup **proxy** (byte-share cost model) that diverges by design from v2.1's system-wide `nets` (the v2.1-vs-v3.3 comparison axis). Binary `intp-ebpf-core-cgroup`. CLI adds `--cgroup`, `--target-container`, `--target-vm`, `--tap-iface`, `--exact`, `--no-diag-cols`. See `variants/v3.3-ebpf-core-cgroup/DESIGN.md`. | Active (container / IADA, paper #2) |

\* The v3 lineage was discontinued at the `pre-rename-2026-05-05` tag because
its embedded-C `perf_event_create_kernel_counter()` calls triggered RCU
stalls on kernel 6.8. The current v1 restores the v0-faithful stap-native
approach; v1.1 revisits the resctrl integration with a userspace helper
to avoid the RCU-unsafe pattern, recovering the full 7-metric coverage.

## Why the rename

1. **Major versions reflect paradigm.** The legacy naming grew incrementally
   (v1 -> v2 -> ... -> v6) and number proximity did not imply architectural
   proximity. v1 (legacy) and v3 (legacy) are both SystemTap and architecturally
   close; v4 (legacy) is a different paradigm. The new scheme groups paradigms
   under the same major version.
2. **Minor versions distinguish implementations.** v3 / v3.1 share eBPF as a
   paradigm but differ in DSL choice (libbpf C vs bpftrace).
3. **Paper references.** Citing "v3.1" tells readers it is a variant of the
   v3 approach with a specific implementation choice, more useful than "v5".

## Reproducing experiments

- For experiments published with **legacy naming**, check out
  `git checkout pre-rename-2026-05-05` to get the source tree as it existed
  on the day of the rename.
- For **current and future experiments**, use the current naming.
- Result snapshots in `results/` generated before the rename retain the legacy
  variant strings (e.g., `bare/v3/solo/...`) by design -- snapshots are
  immutable. Use this table to translate when reading them.

## Status after rename (2026-05-05)

- v1.1 (the helper-userspace SystemTap variant) is implemented and integrated
  into `bench/run-intp-bench.sh`; see `variants/v1.1-stap-modern/` and
  `METRICS-ALIGNMENT.md` for the full coverage matrix and the documented
  HiBench distributed-mode limitation.
- v1 was validated on the production host (no RCU stalls under repeated
  runs); see `bench/findings/v1-modernization-reliability-findings.md`.
- The v3-legacy result gap from the 2026-05-04 campaign (7 of 60 solo runs
  before the kernel hung) was retired in favour of the post-rename
  campaign on Hetzner Sapphire Rapids (`results/bench-full/`, dated
  2026-05-07), which covers v1.1, v2, v3, and v3.1.

## Status after legacy-V0 + cross-env campaigns (2026-05-11)

- v0 was re-enabled as the default measured baseline in
  `bench/run-intp-bench.sh`; v3.1 was swapped out of the default measured
  set but remains routable via `BENCH_VARIANTS=...,v3.1`. See
  `docs/EXPERIMENT-STRATEGY.md` for the rationale.
- v0.2 (new) was scaffolded as the U22 / kernel 5.15 leg of the
  legacy-V0 campaign. It uses the same userspace-helper pattern v1.1
  uses, but targets kernel 5.15 GA so the U22 leg of the experiment
  doesn't trip V0's stability cliff. Gated by `variant_kernel_ok` to
  `5.10 ≤ k < 6.0`; on 6.x v1.1 is the right variant. Not yet
  validated on a real U22 host -- pending the operator-side smoke
  test.
- Cross-environment campaign infrastructure (BENCH_CPUS/BENCH_MEM
  parity knobs, orphan-qemu PID reaping, Kruskal-Wallis + Mann-Whitney
  + Cliff's delta analysis over `aggregate-means.tsv`) is integrated
  in `bench/run-intp-bench.sh` and `bench/plot/plot-cross-environment.py`;
  see `docs/CROSS-ENV-CAMPAIGN.md`.

## Status after V3 auxiliary reruns for the SBAC-PAD paper (2026-05-12)

- v3 noise-floor characterization (12 reps × 90 s, system-wide eBPF
  with HiBench stack UP and IDLE) completed on Hetzner Sapphire Rapids
  (intp-master, kernel 6.8.0-111-generic). Raw data in
  `results/intp-aux-rerun-20260512-212112/noise_floor/`; figures in
  `results/intp-aux-rerun-20260512-212112/plots/` (generated by
  `bench/plot/plot-aux-rerun.py`).
- Methodological observation: `mbw` collapses to a bimodal 0/100
  distribution on this host despite resctrl reporting ~5.6 GB/s of
  steady-state DRAM traffic. `mbw` is therefore reported but **not
  used as a noise-floor signal in the paper**; `cpu` and `llcmr`
  remain the discriminative axes (`cpu` noise floor: 1 % ± 0;
  `llcmr` p95 ≈ 6).
- v3 composite-mechanism reruns (#5: pidstat + `perf stat -p` on the
  intp-ebpf-ring consumer) had two issues in the first run, both fixed in
  `shared/intp-ebpf-checkout.sh`:
  1. `pgrep -nf intp-ebpf-ring` was matching the `sudo` wrapper PID, so
     all 9 with-profiler reps lost consumer-side ctx-sw and CPU%
     ("Problems finding threads of monitor"). Replaced with
     `pgrep -nx` (exact comm match) + a 5-second poll loop.
  2. System-wide `perf stat -a -e sched:sched_switch` reported a
     98-99 % drop under V3, which is ambiguous — the V3 BPF program
     attaches to the same tracepoint, so the kernel perf counter may
     be suppressed by the BPF consumer rather than reflecting real
     scheduler activity. Added `vmstat 1` capture in both arms as an
     independent ground-truth for context-switches.

  The composite-mechanism rerun is queued and not yet executed;
  results land in a new `results/intp-aux-rerun-<ts>/` once the
  operator runs the patched script on the remote.

## Status after V3.2 introduction (2026-05-13)

- v3.2 (`variants/v3.2-ebpf-core/`) was added as the measured eBPF
  endpoint for the SBAC-PAD 2026 paper §III-A. Architecture:
  same eBPF probe set as v3 (`tracepoint:net/net_dev_xmit`,
  `tracepoint:block/block_rq_complete`, `tracepoint:sched/sched_switch`,
  `tracepoint:irq/softirq_entry+exit`, perf_event LLC counters),
  but every event is written into a `BPF_MAP_TYPE_PERCPU_ARRAY` +
  `BPF_MAP_TYPE_HASH` slot via `__sync_fetch_and_add`; userspace
  reads the maps once per `--interval` instead of draining a ring
  buffer. The structural goal is to eliminate the 194-416x ctxsw
  amplification v3 exhibits.
- v3 is retained as the **predecessor of v3.2**, not deleted. Its
  overhead measurements are the empirical evidence that motivates
  v3.2; see `docs/V3-OVERHEAD-FINDINGS.md` for the digest and
  `variants/v3-ebpf-ring/DESIGN.md` § 13 for the architectural narrative.
- The four "measured result" variants for the paper are now
  **v0.2, v1.1, v2, v3.2**. v3.1 stays runnable but is held out of
  the default matrix; v3 stays for overhead evidence only.
- Acceptance gate: `make -C variants/v3.2-ebpf-core test-amplification`
  must pass (ratio <= 1.10 on a 90 s stress-ng window) before v3.2
  joins a campaign. v3 fails this test at 194-416x by construction.

## Status after v2.1 introduction (2026-05-24)

- v2.1 (`variants/v2.1-c-abi-cgroup/`) was added as the c-abi-cgroup
  sibling of v2 for the paper-#2 container + IADA work: the same `intp-c-abi`
  CLI and backend-hierarchy design, but its cpu/blk/llcmr backends attribute
  **per-cgroup** (continuous, child-inclusive) when given `--cgroup`, via
  cgroup v2 `cpu.stat` (usage_usec), `io.stat` (rbytes+wbytes, normalized by a
  self-detected disk-bandwidth ceiling), and `perf_event_open` cgroup mode
  (`PERF_FLAG_PID_CGROUP`) for LLC. It is the stable-ABI, C99 analogue of
  v3.2's per-cgroup eBPF path (the future eBPF-native sibling is v3.3).
- `nets` is kept **system-wide**: softirq CPU time (`/proc/stat`,
  `/proc/softirqs`) is host-global with no per-cgroup counter absent eBPF, so
  6/7 metrics attribute per-cgroup and `nets` is the one irreducible eBPF
  advantage -- the v2.1-vs-v3.3 comparison axis for paper #2.
- "A container is a cgroup": the same per-cgroup code path serves bare
  co-located processes, containers, and VM guests. Wired into the bench harness
  as the `container-lxc` env (LXC/LXD, host-side profiler on the container
  cgroup) and the `containerun24.sh` campaign launcher. v2.1 is built on
  request via `BENCH_VARIANTS=...,v2.1`; the released paper-#1 matrices
  (ub24run.sh, ub22run.sh) are unchanged.

## Status after v3.3 introduction (2026-06-02)

- v3.3 (`variants/v3.3-ebpf-core-cgroup/`) was added as the **eBPF-native
  sibling of v3.2** and the **companion to v2.1** for the paper-#2
  container + IADA work. It scopes v3.2's in-kernel-aggregation design
  (counter maps polled once per `--interval`, no ring buffer) to a
  single cgroup: netp via a `cgroup_skb` program attached to the
  target cgroup, and the remaining software metrics via cgroup-id-keyed
  counter maps. Binary `intp-ebpf-core-cgroup`; target picked via `--cgroup`,
  `--target-container`, or `--target-vm` / `--tap-iface`.
- The v2.1 vs v3.3 axis answers the same per-cgroup question with two
  mechanisms: v2.1 uses c-abi-cgroup stable ABIs (cgroup v2
  `cpu.stat`/`io.stat`, perf cgroup mode, resctrl) with no eBPF; v3.3
  uses eBPF. Six of the seven metrics (netp, blk, mbw, llcmr, llcocc,
  cpu) are expected to agree within tolerance.
- **`nets` is the one expected-divergent metric.** v3.3's `nets` is a
  per-cgroup **proxy** computed from a byte-share cost model, whereas
  v2.1's `nets` is host-global softirq CPU time (system-wide). The
  divergence is by design, not a defect: any v2.1<->v3.3 equivalence
  check must EXEMPT `nets`. Whether the eBPF per-cgroup proxy is more
  faithful to true per-cgroup softirq cost than the system-wide
  attribution is a **hypothesis** to be settled by measurement, not an
  asserted advantage.
- Diagnostic columns: with `--no-diag-cols` (the harness/validate
  capture mode, mirroring v3.2's `--no-raw-mbw`) v3.3 emits leading-ts +
  exactly the 7 canonical columns. Without the flag it appends four
  trailing diagnostics -- `netp_dev`, `nets_sys`, `mbw_raw_mbps`,
  `blk_MBps` -- which are diagnostic, not metric. The first 7 columns
  remain the canonical IntP fingerprint.
- v3.3 inherits the existing `run.json` per-stage schemas (11-field
  stress-ng, 6-field HiBench) through the existing harness writers; no
  schema change. Built on request via `BENCH_VARIANTS=...,v3.3`; the
  released paper-#1 matrices (ub24run.sh, ub22run.sh) are unchanged.

## Status after the VM-portable metrics build (2026-06-04)

- v2.1 and v3.3 gained an OPT-IN `--portable-metrics` benchmark: six
  metrics computed by the **guest's own kernel** so a stock KVM guest
  (where `mbw`/`llcocc`/`llcmr` are structurally gapped) still has a
  scheduling + memory interference signal. Set:
  `schedlat psi_mem membw_est psi_io schedthr steal`
  (DECISIONS-container.md C26/C27; design in
  `docs/reports/8th-metric-vm-portable-design.md`).
- **It is a SEPARATE benchmark, not a schema change.** The canonical
  7-metric fingerprint, its on-disk TSV, the `off=n-7` report path, the
  stap byte-compat, and the IADA 7-vector are byte-identical when the
  flag is off (the v2.1 backend-registry test still reports exactly
  "7 metrics, 21 backends"). The 6 columns are appended only on demand,
  with their own `portable.tsv` capture, `aggregate-portable-means.tsv`
  report, and `bench/analyze-portable.py` adjudicator.
- v3.3's `schedlat` (formerly a trailing diagnostic) moved into the
  portable block; the four diagnostic columns are unchanged. `membw_est`
  reuses v3.3's `llc_misses` counter (× 64 B / interval → MB/s), which
  falls back to the architectural cache-misses event in-guest, so it
  carries the memory-bandwidth dimension where `llcmr` cannot.
- Released paper-#1 matrices and the canonical paper-#2 container campaign
  are unaffected; the portable campaign is run separately
  (`run-intp-bench.sh --portable-metrics --variants v2.1,v3.3`).
- PENDING: testbed validation campaign + report, then back-porting the
  system-wide backends into v2/v3.2.

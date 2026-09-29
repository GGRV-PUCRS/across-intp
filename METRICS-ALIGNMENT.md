# IntP Metrics Alignment Matrix

Reference variant: **V0 (stap-2022)** (`variants/v0-stap-2022/intp.stp`) — the original IntP design from Xavier & De Rose (SBAC-PAD 2022).

This document tracks how each metric is computed across the 11 variants and which divergences have been corrected.

> **Scope:** this matrix covers the **canonical 7 metrics** (`netp nets blk mbw llcmr llcocc cpu`). The eight portable and regime columns (`schedlat psi_mem membw_est psi_io schedthr steal psp idle_preempt`; `idle_preempt` is eBPF-only) are a SEPARATE, opt-in `--portable-metrics` benchmark on v2.1-c-abi-cgroup/v3.3-ebpf-core-cgroup — they do not alter this alignment and are documented in [docs/reports/8th-metric-vm-portable-design.md](docs/reports/8th-metric-vm-portable-design.md) (C26/C27).

## Variant index

| ID | Path | Mechanism | Kernel target |
|---|---|---|---|
| V0 (stap-2022)   | `variants/v0-stap-2022/intp.stp`        | SystemTap, classic kprobes        | ≤4.18 |
| V0.1 (stap-nollc) | `variants/v0.1-stap-nollc/intp-6.8.stp`      | SystemTap (stap-2022 ported to 6.8)      | 6.8 (experimental) |
| V0.2 (legacy-intp-baseline) | `variants/v0.2-legacy-intp-baseline/intp.stp.template` + `generate-stp.sh` | SystemTap + userspace helper, stap-2022-faithful probe set | 5.15 GA (U22) |
| V1 (stap-nohelper)   | `variants/v1-stap-nohelper/intp-resctrl.stp` | SystemTap + resctrl               | ≤6.7 |
| V1.1 (stap-modern) | `variants/v1.1-stap-modern/intp-v1.1.stp`  | SystemTap + userspace helper      | ≥4.19 (incl. 6.8) |
| V2 (C-ABI)   | `variants/v2-c-abi/src/*.c`         | C, /proc + perf + resctrl         | any |
| V2.1 (c-abi-cgroup) | `variants/v2.1-c-abi-cgroup/src/*.c`  | C, per-cgroup (cgroup v2 cpu.stat/io.stat + perf cgroup mode) + resctrl | ≥5.8 (cgroup v2) |
| V3 (ebpf-ring)   | `variants/v3-ebpf-ring/src/intp.{c,bpf.c}` | libbpf + tracepoints + kprobes  | ≥5.5 |
| V3.1 (bpftrace) | `variants/v3.1-bpftrace/scripts/*.bt`      | bpftrace + Python aggregator      | ≥4.19 |
| V3.2 (eBPF-CORE) | `variants/v3.2-ebpf-core/src/intp_agg.{c,bpf.c}` | libbpf + in-kernel counter map aggregation (no ring buffer) | ≥5.5 |
| V3.3 (ebpf-core-cgroup) | `variants/v3.3-ebpf-core-cgroup/src/intp_agg.{c,bpf.c}` | libbpf + **per-cgroup** in-kernel aggregation (`cgroup_skb` + cgroup-id counter maps, no ring buffer) | ≥5.8 (cgroup v2) |

## Metric formulas

| Metric | V0 (stap-2022, reference) | V0.1 (stap-nollc) | V0.2 (legacy-intp-baseline) | V1 (stap-nohelper) | V1.1 (stap-modern) | V2 (C-ABI) | V3 (ebpf-ring) | V3.1 (bpftrace) |
|---|---|---|---|---|---|---|---|---|
| **netp** | `(tput_bps / 125e6) × 100` | ≡ stap-2022 | ≡ stap-2022 | ≡ stap-2022 | ≡ stap-2022 | `bps / NIC_speed × 100` (autodetect) | ≡ C-ABI | ≡ C-ABI |
| **nets** | `(avg_lat_ns × count) / 1e9 × 100`, summed TX+RX. Probes: `__dev_queue_xmit`+`net:net_dev_xmit` (TX) and `__napi_schedule_irqoff`+`napi_complete_done` (RX) | ≡ stap-2022 | ≡ stap-2022 (paper-faithful per-packet kprobes preserved) | ≡ stap-2022 | **stap `softirq.entry/exit` tapset filtered by vec=2,3** [softirq tracepoints; same approach as bpftrace] | softirq fraction × softirq pct × num_cores [matches stap-2022 wall-clock semantics in aggregate] | **kprobe `__dev_queue_xmit`+`net:net_dev_start_xmit` (TX) + `napi_poll` entry/exit (RX) PLUS `irq:softirq_entry/exit`** [softirq tracepoints added — primary path on kernels where napi_poll is inlined / veth where per-packet model degenerates] | **`irq:softirq_entry/exit` filtered by vec=2,3** [softirq tracepoints; verified non-zero on kernel 6.8 + veth] |
| **blk** | `(avg_svctm_us × ops_per_sec) / 100` from `block:block_rq_complete` (over-amplified by ~100×) | ≡ stap-2022 | ≡ stap-2022 (stap-2022 amplification quirk preserved for paper fidelity) | ≡ stap-2022 | **`svctm_sum_ns / interval_ns × 100`** [aligned with ebpf-ring, drops stap-2022's amplification quirk] | `io_ticks_delta / interval_ms × 100` (DIFFERENT MODEL — measures % time disk had ≥1 outstanding I/O, no queue-depth signal) | `svctm_ns_sum / interval_ns × 100` (physical disk-busy fraction; preserves queue-depth pressure for parallel NVMe) | **`svctm_sum_ns / interval_ns × 100`** [aligned with ebpf-ring] |
| **mbw** | `bw_bps / 34e9 × 100` (hardcoded 34 GB/s) | ≡ stap-2022 | ≡ stap-2022 (helper-fed via uncore IMC `perf_event_open(2)`) | ≡ stap-2022 (returns 0; helper-fed) | ≡ stap-2022 (helper-fed) | `bw / mem_bw_max × 100` (autodetect) | ≡ C-ABI | ≡ C-ABI |
| **llcmr** | `(misses / loads) × 100` | ≡ stap-2022 | ≡ stap-2022 | ≡ stap-2022 | ≡ stap-2022 | ≡ stap-2022 | ≡ stap-2022 (refs ≈ loads) | ≡ stap-2022 |
| **llcocc** | `(occ_count × 49152) / 34e6 × 100` (hardcoded 34 MB) | ≡ stap-2022 | ≡ stap-2022 (helper-fed via resctrl mon_groups) | ≡ stap-2022 (helper-fed) | ≡ stap-2022 (helper-fed) | `occ_bytes / llc_size × 100` (autodetect via resctrl) | ≡ C-ABI | ≡ C-ABI |
| **cpu** | `(uticks + kticks) / allticks × 100` from `perf.sw.cpu_clock` | ≡ stap-2022 | ≡ stap-2022 | ≡ stap-2022 | ≡ stap-2022 | `(1 - idle/total) × 100` from /proc/stat | `on_cpu_ns / (interval × num_cores) × 100` (mathematically equivalent to stap-2022 — `allticks` in stap-2022 is per-CPU-summed, ebpf-ring divides explicitly) | ≡ ebpf-ring |

Legend:
- `≡ V0` = mathematically identical to stap-2022 (possibly with autodetected constants instead of hardcoded values)
- **bold** = previously divergent, now patched to match stap-2022
- *italics* = remaining divergence not yet patched

### V3.2 (eBPF-CORE) (in-kernel aggregation) — variant-specific notes

eBPF-CORE uses the same probe sites and same per-metric formulas as ebpf-ring
EXCEPT for the destination of the per-event update (`__sync_fetch_and_add`
into a `BPF_MAP_TYPE_PERCPU_ARRAY` counter slot instead of
`bpf_ringbuf_reserve`+submit). The values userspace divides through
are computed against the same `interval_real` × normalization
constants ebpf-ring uses.

| Metric  | V3.2 (eBPF-CORE) vs V3 (ebpf-ring)                                           |
|---------|-----------------------------------------------------------------------------|
| netp    | ≡ ebpf-ring (same probes, same denominator)                                 |
| nets    | ≡ ebpf-ring softirq path. eBPF-CORE has only the softirq path (kprobe+kretprobe and fentry/fexit napi_poll fallbacks of ebpf-ring are dropped — on 6.x they're unreachable anyway because napi_poll is inlined) |
| blk     | ≡ ebpf-ring                                                                 |
| cpu     | ≡ ebpf-ring                                                                 |
| llcmr   | ≡ ebpf-ring (sample_period scaling preserved)                               |
| **mbw** | **eBPF-CORE emits BOTH `mbw_pct` (no silent clip, opt-in via `--clip-mbw`) AND `mbw_raw_mbps` (raw MB/s); the bimodal discrete 96/80/64/48/32/16/0 artifact ebpf-ring produces from the silent clip is gone. See `docs/V3-OVERHEAD-FINDINGS.md` §3.** |
| llcocc  | ≡ ebpf-ring                                                                 |

The trailing `mbw_raw_mbps` column is diagnostic, not metric. The
first 7 TSV columns remain the canonical IntP fingerprint and are
byte-compatible with ebpf-ring.

### V2.1 (c-abi-cgroup) — variant-specific notes

c-abi-cgroup reuses C-ABI's per-metric formulas and backend hierarchy; the only change is
the *attribution scope*. When run with `--cgroup <path>` it attributes a single
cgroup: cpu/blk/llcmr continuously (child-inclusive), mbw/llcocc via a resctrl
mon_group re-scanned from `cgroup.procs` on a cadence, and netp via the
container's network namespace. Without `--cgroup` it is byte-for-byte C-ABI.

| Metric  | V2.1 (c-abi-cgroup) vs V2 (C-ABI)                                         |
|---------|----------------------------------------------------------------------------|
| netp    | per-cgroup via the container's netns (`/proc/<pid>/net/dev` for a cgroup PID), normalized by the **host** NIC speed = the cgroup's share of the physical link. Falls back to system-wide sysfs/procfs when the target shares the profiler's netns (`--net=host`, bare colocation) — that case needs eBPF (ebpf-core-cgroup). |
| **nets**| ≡ C-ABI, **always system-wide** — softirq CPU time (`/proc/stat`, `/proc/softirqs`) is host-global; no per-cgroup softirq counter exists without eBPF. The one metric the ebpf-core-cgroup variant (eBPF, per-cgroup) attributes that c-abi-cgroup cannot. |
| **blk** | per-cgroup via cgroup v2 `io.stat` (rbytes+wbytes) ÷ self-detected disk-bandwidth ceiling, vs C-ABI's system-wide `io_ticks`. Falls back to C-ABI's diskstats/sysfs when no `--cgroup`. |
| mbw     | per-cgroup via a resctrl **MBM mon_group** re-scanned from `cgroup.procs` on a cadence (tight at startup, then periodic — so late-spawned workers are picked up), vs C-ABI's socket-wide uncore IMC. System-wide when no `--cgroup`. |
| llcmr   | per-cgroup via `perf_event_open` cgroup mode (`PERF_FLAG_PID_CGROUP`, one LL$ loads/misses pair per online CPU), vs C-ABI's per-PID/system-wide perf. Falls back to C-ABI's HW_CACHE/raw counters when no `--cgroup`. |
| llcocc  | per-cgroup via a resctrl **occupancy mon_group** re-scanned from `cgroup.procs` on a cadence, vs C-ABI's system-wide group. System-wide when no `--cgroup`. |
| **cpu** | per-cgroup via cgroup v2 `cpu.stat` (usage_usec, hierarchical), vs C-ABI's `/proc/stat`. Falls back to per-PID/system procfs when no `--cgroup`. |

So 6/7 metrics gain per-cgroup attribution (cpu/blk/llcmr continuous,
mbw/llcocc resctrl-mon_group re-scanned on a cadence, netp via netns); `nets` stays
system-wide by construction (host-global softirq, no per-cgroup counter without
eBPF). The first 7 TSV columns remain the canonical IntP fingerprint.

### V3.3 (per-cgroup eBPF) — variant-specific notes

ebpf-core-cgroup is the **eBPF-native sibling of eBPF-CORE** and the **companion to c-abi-cgroup**: it
re-asks c-abi-cgroup's per-cgroup question (`--cgroup <path>`, or `--target-container` /
`--target-vm`+`--tap-iface`) using eBPF instead of c-abi-cgroup stable ABIs. It
reuses eBPF-CORE's in-kernel-aggregation pattern (counter maps polled once per
`--interval`, no ring buffer) but scopes attribution to one cgroup: a
`cgroup_skb` program attached to the target cgroup for `netp`, and cgroup-id-keyed
counter slots for the software metrics. Provenance per metric:

| Metric  | V3.3 (ebpf-core-cgroup) provenance                                             |
|---------|----------------------------------------------------------------------------|
| **netp**| per-cgroup via a `cgroup_skb` program attached to the target cgroup, normalized by the host NIC speed = the cgroup's share of the physical link. Diagnostic `netp_dev` (per-device byte counter) is appended only without `--no-diag-cols`. (C1) |
| **nets**| per-cgroup **PROXY** — a byte-share cost model that attributes a fraction of net-softirq cost to the cgroup. **DIVERGENT BY DESIGN from c-abi-cgroup's system-wide `nets`** (host-global softirq CPU time): the two answer different questions, so any c-abi-cgroup<->ebpf-core-cgroup equivalence check must **EXEMPT `nets`**. Whether the proxy is more faithful to true per-cgroup softirq cost is a *hypothesis* pending measurement, not an asserted advantage. Diagnostic `nets_sys` (the system-wide softirq figure, for cross-check) is appended only without `--no-diag-cols`. (C2) |
| **blk** | `svctm` busy-fraction % canonical (per-cgroup), matching the physical disk-busy-fraction model used by stap-modern / ebpf-ring / eBPF-CORE. Diagnostic `blk_MBps` (bio-owner per-cgroup throughput) is appended only without `--no-diag-cols`. (C15) |
| mbw     | per-cgroup, same scope as c-abi-cgroup (resctrl MBM for the cgroup); diagnostic `mbw_raw_mbps` (raw MB/s) appended only without `--no-diag-cols`. |
| llcmr   | per-cgroup, same scope as c-abi-cgroup (`perf_event_open` cgroup mode / cgroup-scoped LLC counters). |
| llcocc  | per-cgroup, same scope as c-abi-cgroup (resctrl occupancy mon_group for the cgroup). |
| cpu     | per-cgroup, same scope as c-abi-cgroup (cgroup v2 `cpu.stat` usage / cgroup-scoped on-CPU time). |

**VM `nets` = N/A** (C8): when the target is a VM (`--target-vm` / `--tap-iface`),
the guest's net-softirq cost is not observable as a per-cgroup signal on the host,
so `nets` is reported as N/A for the VM case (the byte-share proxy applies to the
container-cgroup case only).

**Column shape (C13).** With `--no-diag-cols` — the mode the bench harness and
`validate-cross-variant.sh` use at every ebpf-core-cgroup capture site, exactly mirroring how
eBPF-CORE is captured with `--no-raw-mbw` — ebpf-core-cgroup emits leading-ts + EXACTLY the 7
canonical columns (`netp nets blk mbw llcmr llcocc cpu`), byte-compatible with the
other variants. Without the flag it appends four **diagnostic** (not metric)
columns trailing the 7, in order: `netp_dev`, `nets_sys`, `mbw_raw_mbps`,
`blk_MBps`. `stage_report` reads the last 7 columns (`off = n-7`), so a leaked
diagnostic column would be mis-read as a metric — hence `--no-diag-cols` is
load-bearing at capture time. The first 7 TSV columns remain the canonical IntP
fingerprint.

## Patches applied (this campaign)

All rows below are merged on `main`. Commit shorthashes are given for
audit; use `git show <hash>` to inspect.

| Variant | Metric | Change | Commit |
|---|---|---|---|
| V3.1 (bpftrace) | nets | `nets.bt` measures CPU time in NET_TX (vec=2) + NET_RX (vec=3) softirqs via `irq:softirq_entry/exit` tracepoints. **Diverges from stap-2022's per-packet kprobe model** — empirically validated that on Hetzner kernel 6.8 + veth, stap-2022's `__dev_queue_xmit` kprobe captures only driver xmit time (microseconds for veth), and `napi_complete_done` rarely fires under sustained load (backlog never empties). Softirq tracepoints capture actual CPU time in net bottom half — same signal as C-ABI's procfs softirq backend, but in-kernel and finer granularity. | 364a225, 5a516a3 |
| V3.1 (bpftrace) | nets | Removed `× cpus` from `compute_nets` in aggregator.py — output is total CPU-seconds-in-stack across all CPUs (matches stap-2022's "summed event-time" semantic in aggregate, not per-CPU normalized). | cf378cb |
| V2 (C-ABI) | nets | Multiplied `softirq_pct` by `num_cores` in `softirq_read` (`/proc/stat` aggregates jiffies across CPUs already, so the resulting fraction was system-wide-normalized; multiplying recovers stap-2022's "total CPU-seconds-in-stack" semantics). | cf378cb |
| V2 (C-ABI) | nets | Removed `/num_cores` from `throughput_read` (was previously expressing as system-wide; now matches stap-2022's cumulative-across-CPUs semantics). | cf378cb |
| V1.1 (stap-modern) | blk  | Switched from `(svctm_ns / 1e8) × ops_per_sec` (10× under-amplified, blind port of stap-2022) to `sum(svctm_ns) / (runtime × 1e9) × 100` — physical disk-busy fraction matching ebpf-ring / bpftrace. stap-modern is the modern stap variant; alignment with ebpf-ring/bpftrace prioritised over fidelity to stap-2022's amplification quirk. | e8f0d4c |
| V3.1 (bpftrace) | blk  | Replaced `svctm_ms × ops_per_sec / 100` (algebraically same as stap-modern's old formula, 10× under-amplified) with `svctm_sum_ns / interval_ns × 100` — physical scale matching ebpf-ring directly. | cf378cb |
| V1.1 (stap-modern) | nets | Replaced stap-2022-faithful per-packet kprobes (`__dev_queue_xmit`+`net_dev_xmit` for TX, `__napi_schedule_irqoff`+`napi_complete_done` for RX) with the stap softirq tapset filtered by `$vec == 2,3` (`probe softirq.entry/exit` — switched to the tapset in commit 6596148 for reliable vector access; previously `kernel.trace("irq:softirq_entry/exit")` had brittle `$vec` resolution). Same rationale as bpftrace: stap-2022's per-packet model degenerates on kernel 6.8 + veth (driver xmit is microseconds; backlog NAPI under sustained traffic rarely completes). Net stack accumulators (`net_sent_lat`, `net_rcv_lat`, etc.) and `print_netstack_report` formula are unchanged — they now interpret softirq service-time samples instead of per-packet samples, semantically aligned with C-ABI / ebpf-ring / bpftrace. | 54a024d, 6596148 |
| V3 (ebpf-ring) | nets | Added `tracepoint/irq/softirq_entry` and `softirq_exit` BPF programs (filtered by vec=2,3) emitting `INTP_EVENT_NAPI_TX_LAT` / `NAPI_RX_LAT` events into the existing ring buffer. Userspace aggregation (`tx_lat_ns_sum` / `rx_lat_ns_sum`) accumulates softirq time alongside the existing kprobe-based per-packet samples. On kernels where `napi_poll` / `__napi_poll` are inlined (incl. 6.8) the kprobe RX path is auto-disabled by existing `kernel_has_symbol()` detection — softirq becomes the only RX source. The kprobe TX path on `__dev_queue_xmit` continues to fire but contributes microseconds for veth (negligible double-count). | 54a024d |

## Remaining divergences (NOT patched — discussed below)

### V2 (C-ABI) blk — io_ticks vs svctm × ops

**Current**: C-ABI reads `io_ticks` from `/proc/diskstats`, which is "% time disk had ≥1 outstanding I/O" (capped at 100% per device).

**stap-modern / ebpf-ring / bpftrace** (post-patch): physical disk-busy fraction `svctm_sum_ns / interval_ns × 100`. Captures parallel queue-depth pressure (can exceed 100% on multi-queue NVMe; capped to 99 in IntP schema).

**Why C-ABI not patched**: C-ABI is degraded-mode by design (`/proc` only, no kprobes/tracepoints). To get per-I/O service time, C-ABI would need access to `block:block_rq_complete` deltas, which is essentially what stap-modern/ebpf-ring/bpftrace do. `/proc/diskstats` `read_ticks + write_ticks` fields approximate this but include queueing time too. **C-ABI's role is the "no eBPF / no stap" fallback**, so io_ticks-based blk is its identity, not a bug.

**Workaround**: prefer stap-modern / ebpf-ring / bpftrace for blk-sensitive interference analysis. Document C-ABI's blk as "approximation" in the paper, with explicit note that C-ABI cannot capture queue-depth pressure on parallel NVMe.

### V0 (stap-2022) / V0.1 (stap-nollc) / V1 (stap-nohelper) blk scaling quirk (preserved by design)

stap-2022 / stap-nollc / stap-nohelper effectively compute `svctm_us × ops_per_sec / 100` which is **~100× higher** than the physical disk-busy fraction. For a workload with 100 IOPS × 1 ms each (= 10% disk utilization), stap-2022 outputs 1000 → capped to 99%.

**Decision**: stap-2022 / stap-nollc / stap-nohelper keep their original (over-amplified) formula for backward fidelity with the original IntP paper. **stap-modern, ebpf-ring, bpftrace explicitly drop this quirk** because they are the modern variants whose role is comparability with each other and with physical disk-busy fraction, not byte-for-byte numerical reproduction of stap-2022.

This is a documented design split in the paper:

- stap-2022 / stap-nollc / stap-nohelper: faithful reproduction of original IntP design (saturates easily on modern hardware)
- stap-modern / ebpf-ring / bpftrace: physically meaningful disk-busy fraction (allows fine-grained interference comparison on NVMe)
- C-ABI: io_ticks-based approximation (no kprobes, design-bounded)

### Constants (NIC speed, mbw max, llc size)

stap-2022 hardcodes:
- NIC: 125 MB/s = 1 Gbps
- Memory bandwidth: 34 GB/s
- LLC size: 34 MB
- LLC line scaling: 49152

C-ABI/ebpf-ring/bpftrace autodetect via `intp-detect.sh` and CLI overrides (`--nic-speed-bps`, `--mem-bw-max-bps`, `--llc-size-bytes`).

**Decision**: keep autodetection. The IntP paper's hardcoded constants reflect the testbed used in the 2022 paper, which itself is a Haswell-era platform (Xeon E5-2620v3, 8C/16T, DDR3-1600 — CPU released 2014). For Hetzner Sapphire Rapids (24C/48T, DDR5-4800, 46 MB LLC, 1 Gbps), autodetected values are physically meaningful. Hetzner's 1 Gbps NIC happens to match stap-2022's hardcoded 125 MB/s exactly, so `netp` is numerically aligned by coincidence.

If full numerical reproduction of stap-2022 is required (for cross-paper comparison), use:
```bash
NIC_SPEED_BPS=125000000 \
MEM_BW_MAX_BPS=34000000000 \
LLC_SIZE_BYTES=34000000 \
  ...
```

## Validation

After applying the patches above, the 7 metrics should be:
- **netp, nets, blk, mbw, llcmr, llcocc, cpu** numerically comparable across stap-2022 / stap-nollc / stap-nohelper / stap-modern / ebpf-ring / bpftrace
- **C-ABI** numerically comparable for netp, nets (post-patch), mbw, llcmr, llcocc, cpu
- **C-ABI blk** uses different model (io_ticks); document as design choice

For the SBAC-PAD campaign on Hetzner kernel 6.8:
- stap-2022, stap-nollc, stap-nohelper do not run (kernel ≥6.8 incompatibility)
- **stap-modern runs in two modes**: per-process for stress-ng (the workload IS its
  own parent, so `process("stress-ng")` attach resolves naturally), and
  **system-wide** for HiBench (Spark Driver launches after stap attach,
  inside netns intp-app — the per-process attach can't reach it). Switched
  via the `@1 = "@system"` sentinel in `intp-v1.1.stp`. See section below.
- C-ABI, ebpf-ring, bpftrace are the IntP successor variants — system-wide by construction.

### V1.1 (stap-modern) dual-mode design (per-process + system-wide)

stap-modern's stap-based per-process probes (`process(@1).begin`,
`perf.type(3).config(...).process(@1)`, plus `[pid()] in mpids` filters on
netfilter and scheduler probes) require `process(@1)` to attach to the
workload binary. This works for stress-ng — the workload IS the binary
named by the target — but fails for HiBench because the Spark Driver:

- launches **after** stap attaches (via `spark-submit` invoked by the
  HiBench runner), so the begin-probe uprobe has no instance to fire on
  at attach time and depends on detecting the new exec;
- runs **inside netns intp-app** (spawned by `ip netns exec`), where uprobe
  attachment to `process("java")` does not propagate cleanly.

Result before the fix: the Driver's PID never enters `mpids`, all
mpids-gated probes silently produce zero, only system-wide probes
(`block_rq_complete`, `softirq.entry/exit`, helper-fed `mbw` / `llcocc`)
captured Driver work.

The fix is to give stap-modern a **system-wide mode** matching C-ABI / ebpf-ring / bpftrace
semantics for HiBench. In `intp-v1.1.stp`, when `@1 == "@system"` the
preprocessor selects:

- no `process(@1).begin / .end` probes (mpids stays empty; nprocs is
  seeded to 1 in `probe begin` so all `nprocs > 0` gates open immediately);
- `perf.type(3).config(0x000002)` and `0x010002` attach **without** a
  `.process(...)` clause (system-wide LLC monitoring across every CPU);
- `netfilter.ip.local_out / local_in` count all IP traffic (no
  `[pid()] in mpids` gate, no flow whitelisting);
- `scheduler.ctxswitch` records every task's CPU time, normalised
  against `CPU_TOTAL_CORES * window_ns` (same denominator as per-process
  mode, so the percentage scale is preserved).

The userspace helper (`intp-helper`) is unchanged in either mode — its
resctrl `mon_group` enrollment scans `/proc/*/comm` on the host PID
namespace (which is shared with `intp-app`), so passing the actual comm
pattern (e.g. `"java"`) keeps `mbw` and `llcocc` accurate for the
Spark Driver. Only the stap side switches to `@system`.

`bench/hibench/run-hibench-subset.sh` invokes stap with `"@system"` for
stap-modern and the helper with the real comm pattern; `bench/run-intp-bench.sh`
keeps the per-process path for stress-ng.

# V3.3 — eBPF/cgroup per-tenant IntP

Per-cgroup interference profiler: the eBPF/CO-RE companion to
**v2.1-c-abi-cgroup**, extending the in-kernel-aggregating design of
[v3.2-ebpf-core](../v3.2-ebpf-core/) from per-PID to **per-cgroup** attribution so
interference can be charged to a single container or VM tenant.

See [DESIGN.md](DESIGN.md) for the full specification and
[docs/DECISIONS-container.md](../../docs/DECISIONS-container.md) for the ratified
artifact-contract decisions.

## Status

Active profiler variant. Binary `intp-ebpf-core-cgroup` (resctrl group `intp-v3.3`,
Prometheus label `intp_v3_3`) builds and runs. The eBPF object implements:

- **Cgroup-identity gating** — `bpf_get_current_cgroup_id()` (exact) or
  `bpf_get_current_ancestor_cgroup_id(level)` (ancestor, default), plus a
  bounded deferred-context ancestor walk for the bio owner; attribution lands
  in the `agg_per_cgroup` map keyed by cgroup id.
- **Per-cgroup `netp`** via `cgroup_skb` ingress/egress (canonical), with a
  device-level `netp_dev` diagnostic column.
- **Per-cgroup `blk`** from `bio->bi_blkg` (writeback attributed to the owning
  cgroup, not the flusher kworker).
- **Per-cgroup `cpu` and `llcmr`** (cgroup-mode `perf_event` counters).
- **`nets`** as a per-cgroup byte-share estimate over the system-wide softirq
  numerator (`nets_sys` diagnostic retained).
- **6 VM-portable metrics** (`schedlat psi_mem membw_est psi_io schedthr steal`)
  emitted as a SEPARATE block under `--portable-metrics` (C26/C27). `schedlat` is
  the eBPF `sched_wakeup`→`sched_switch` run-queue wait; `membw_est` reuses the
  `llc_misses` counter (× 64 B / interval → MB/s) so it survives the in-guest vPMU
  gap; the rest are guest-kernel file reads (PSI, `cpu.stat`, `/proc/stat`).

mbw/llcocc remain the userspace resctrl hybrid (RDT hardware, not eBPF).

## Canonical output

The 7 canonical IntP metrics in fixed order — `netp nets blk mbw llcmr llcocc cpu`
— with optional trailing **diagnostic** columns (`netp_dev`, `nets_sys`,
`mbw_raw_mbps`, `blk_MBps`) suppressed by `--no-diag-cols`. See C1/C2/C4/C5 in
`docs/DECISIONS-container.md`.

`--portable-metrics` appends the 6 VM-portable columns
(`schedlat psi_mem membw_est psi_io schedthr steal`) AFTER the canonical/diagnostic
columns — a SEPARATE benchmark that never alters the canonical 7 (C27). Run it via
`run-intp-bench.sh --portable-metrics --variants v2.1,v3.3` and adjudicate with
`bench/analyze-portable.py`.

## Metric provenance vs v2.1 (headline divergence)

- `netp` — **canonical = per-cgroup** (`cgroup_skb`); device-level retained as the
  diagnostic `netp_dev` column. VM uses tc/XDP on the tap iface (host-side).
- `nets` — **canonical = per-cgroup estimate** via an skb byte-share cost model
  (an explicit approximation, marked `PROXY`); system-wide softirq retained as the
  diagnostic `nets_sys` column. v2.1 keeps `nets` system-wide (no per-cgroup ABI).

## VM-guest path

Under a stock KVM guest, the RDT/PMU metrics are structurally gapped: resctrl is
host-only (mbw/llcocc emit `--`/NaN, recorded as structurally unsupported rather
than faked to 0), and the model-specific LL-read perf events are not virtualized.
For `llcmr`, v3.3 probes the LL event and, when it cannot open under the guest
vPMU, falls back to the **architectural** `PERF_COUNT_HW_CACHE_REFERENCES`/`_MISSES`
events, which are virtualized and match the W4 ground-truth (bare/host keeps the
LL events, where the probe succeeds). The RDT-gapped dimensions are instead
covered by the flag-gated **`--portable-metrics`** block (`schedlat`, `psi_mem`,
`membw_est`, `psi_io`, `schedthr`, `steal`), keeping the canonical 7-metric
contract intact on every environment.

## Build

```sh
make            # build intp-ebpf-core-cgroup (needs clang, libbpf-dev, bpftool, BTF)
make test-unit  # host-side counter-snapshot test (no kernel)
```

Load/attach, RDT, and per-cgroup smoke validation require a kernel ≥5.8 host with
BTF, cgroup v2, and resctrl (W3 remote validation).

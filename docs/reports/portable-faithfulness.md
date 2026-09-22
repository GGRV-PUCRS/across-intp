# Portable-metrics faithfulness adjudication — results/intp-bench-20260605_130235

Cells with data: 72 | reps/cell: min 12 max 12 | scipy: yes

## §1 Availability matrix (portable metrics render numeric vs '--')

`ok` = the metric produced a numeric reading in ≥1 rep of that env; `--` = never (source absent — e.g. CONFIG_PSI=n, no cpu.max quota, no perf). The VM-portable claim: schedlat/psi_*/membw_est/steal stay `ok` in vm-guest where the canonical RDT metrics (mbw/llcocc/llcmr) go `--`.

### v2.1

| env | schedlat | psi_mem | membw_est | psi_io | schedthr | steal | | | mbw | llcocc | llcmr |
|---|---|---|---|---|---|---|---|---|---|---|
| bare | ok | ok | ok | ok | ok | ok | | | ok | ok | ok |
| container | ok | ok | ok | ok | ok | ok | | | ok | ok | ok |
| container-podman | ok | ok | ok | ok | ok | ok | | | ok | ok | ok |
| container-lxc | ok | ok | ok | ok | ok | ok | | | ok | ok | ok |
| container-k8s | ok | ok | ok | ok | ok | ok | | | ok | ok | ok |
| vm-guest | ok | ok | ok | ok | ok | ok | | | -- | ok | ok |

### v3.3

| env | schedlat | psi_mem | membw_est | psi_io | schedthr | steal | | | mbw | llcocc | llcmr |
|---|---|---|---|---|---|---|---|---|---|---|
| bare | ok | ok | ok | ok | ok | ok | | | ok | ok | ok |
| container | ok | ok | ok | ok | ok | ok | | | ok | ok | ok |
| container-podman | ok | ok | ok | ok | ok | ok | | | ok | ok | ok |
| container-lxc | ok | ok | ok | ok | ok | ok | | | ok | ok | ok |
| container-k8s | ok | ok | ok | ok | ok | ok | | | ok | ok | ok |
| vm-guest | ok | ok | ok | ok | ok | ok | | | -- | -- | ok |

## §2 Spearman: portable metric vs ground truth (solo, traffic-gated)

| variant | portable | vs GT | n | ρ | p | verdict |
|---|---|---|---|---|---|---|
| v2.1 | membw_est | gt_mbw_bps | 0 | - | - | n<3 / no spread |
| v2.1 | membw_est | gt_llc_miss | 36 | 0.940 | 0.000 | faithful |
| v2.1 | schedlat | gt_llcmr | 36 | -0.223 | 0.192 | weak |
| v2.1 | psi_mem | gt_llc_miss | 36 | - | - | n<3 / no spread |
| v3.3 | membw_est | gt_mbw_bps | 0 | - | - | n<3 / no spread |
| v3.3 | membw_est | gt_llc_miss | 36 | 0.938 | 0.000 | faithful |
| v3.3 | schedlat | gt_llcmr | 36 | -0.541 | 0.001 | weak |
| v3.3 | psi_mem | gt_llc_miss | 36 | - | - | n<3 / no spread |

- **membw_est vs gt_mbw_bps** — INDEPENDENT validation vs resctrl MBM bandwidth — expect STRONG + (often n<3: resctrl mbw GT is '--' by CMT design, C24)
- **membw_est vs gt_llc_miss** — consistency check only — membw_est IS derived from cache-misses, so this shares its source, NOT an independent validation
- **schedlat vs gt_llcmr** — directional: contention slows the victim, its run-queue backs up — expect +
- **psi_mem vs gt_llc_miss** — FALSIFICATION: psi_mem is capacity-driven — expect WEAK vs bandwidth
- **Scope caveat (in-guest envs):** `groundtruth.tsv` is always captured HOST-side, while in vm-guest / container-guest the portable metrics are captured INSIDE the guest — so those cells correlate guest-side metrics against the host's counters. Treat vm-guest §2 rows as indicative only; the §1 availability + §4 in-guest tables are the load-bearing VM evidence.

## §3 PSI bandwidth-blindness falsification

Per (env,variant) the cell with the highest `membw_est`. If `membw_est` is high (≥1000 MB/s) while `psi_mem` stays flat (≤5%), `psi_mem` is confirmed **capacity-only** (bandwidth-blind) and `membw_est` is the metric carrying the bandwidth dimension. `schedlat` should rise too.

| env | variant | workload | membw_est (MB/s) | psi_mem (%) | schedlat (%) | finding |
|---|---|---|---|---|---|---|
| bare | v2.1 | app05_streaming | 6470 | 0.000 | 0.000 | blind CONFIRMED |
| container | v2.1 | app05_streaming | 5762 | 0.000 | 0.000 | blind CONFIRMED |
| container-podman | v2.1 | app05_streaming | 6040 | 0.000 | 0.000 | blind CONFIRMED |
| container-lxc | v2.1 | app05_streaming | 6236 | 0.000 | 0.000 | blind CONFIRMED |
| container-k8s | v2.1 | app05_streaming | 7096 | 0.000 | 0.000 | blind CONFIRMED |
| vm-guest | v2.1 | app05_streaming | 79826 | 0.000 | 0.000 | blind CONFIRMED |
| bare | v3.3 | app05_streaming | 6400 | 0.000 | 0.000 | blind CONFIRMED |
| container | v3.3 | app05_streaming | 5699 | 0.000 | 0.000 | blind CONFIRMED |
| container-podman | v3.3 | app05_streaming | 6146 | 0.000 | 0.000 | blind CONFIRMED |
| container-lxc | v3.3 | app05_streaming | 6109 | 0.000 | 0.000 | blind CONFIRMED |
| container-k8s | v3.3 | app05_streaming | 6554 | 0.000 | 0.000 | blind CONFIRMED |
| vm-guest | v3.3 | app05_streaming | 75089 | 0.000 | 0.000 | blind CONFIRMED |

**psi_mem capacity-only:** CONFIRMED on ≥1 cell (needs a saturating-bandwidth workload with ample free RAM, e.g. app05_streaming).

## §4 membw_est corroboration gate (net-path instrumentation caveat)

`membw_est` is cache-miss-derived and reported as an UNCLAMPED absolute (MB/s), so on net-heavy workloads where the hardware cache/bandwidth canonicals (`mbw`, `llcmr`) read ~0, a non-zero `membw_est` is NOT corroborated as workload DRAM bandwidth — it integrates net-softirq + per-packet eBPF-hook misses. The eBPF variant (v3.3) inflates this over the C variant (v2.1): on app11 v3.3 `membw_est` is ~6–7× v2.1, and an INDEPENDENT host-side GT shows v3.3 generating ~3.6× the system LLC misses v2.1 does on that workload (the bandwidth analogue of the eBPF overhead in `docs/V3-OVERHEAD-FINDINGS.md`). The **canonical 7 are UNAFFECTED** — `mbw`/`llcmr` are %-normalized + clamped, so the ~0.02%-of-ceiling footprint rounds to 0 (verified: app11 `mbw`=0/`llcmr`=0 for BOTH variants). Cells with `membw_est`>0 but `mbw`≈0 and `llcmr`≈0 are flagged **uncorroborated** (C31): read them as instrumentation-influenced, not true bandwidth; do not use them for cross-variant absolute-bandwidth claims.

| env | variant | workload | membw_est | mbw | llcmr | corroborated? |
|---|---|---|---|---|---|---|
| bare | v2.1 | app11_sort_net | 9.0 | 0.000 | 0.000 | **uncorroborated (net-path)** |
| bare | v3.3 | app11_sort_net | 65.0 | 0.000 | 0.000 | **uncorroborated (net-path)** |
| container | v2.1 | app11_sort_net | 11.0 | 0.000 | 0.000 | **uncorroborated (net-path)** |
| container | v3.3 | app11_sort_net | 65.5 | 0.000 | 0.000 | **uncorroborated (net-path)** |
| container-podman | v2.1 | app11_sort_net | 14.0 | 0.000 | 0.000 | **uncorroborated (net-path)** |
| container-podman | v3.3 | app11_sort_net | 74.5 | 0.000 | 0.000 | **uncorroborated (net-path)** |
| container-lxc | v2.1 | app11_sort_net | 11.0 | 0.000 | 0.000 | **uncorroborated (net-path)** |
| container-lxc | v3.3 | app11_sort_net | 27.5 | 0.000 | 0.000 | **uncorroborated (net-path)** |
| container-k8s | v2.1 | app11_sort_net | 4.0 | 0.000 | 0.000 | **uncorroborated (net-path)** |
| container-k8s | v3.3 | app11_sort_net | 40.5 | 0.000 | 0.000 | **uncorroborated (net-path)** |

_10 cell(s) flagged: RDT present but mbw≈0 and llcmr≈0 while membw_est>0. The v2.1↔v3.3 gap on these is the eBPF net-path footprint, not workload bandwidth (C31). vm-guest is excluded here (mbw is structurally `--`; see the §2 scope caveat)._

## §5 vm-guest confirmation

Portable medians in-guest (across workloads), and the canonical RDT metrics that are structurally `--` there.

| variant | schedlat | psi_mem | membw_est | psi_io | schedthr | steal | mbw | llcocc | llcmr |
|---|---|---|---|---|---|---|---|---|---|
| v2.1 | 0.000 | 0.000 | 597 | 0.000 | 0.000 | 0.000 | -- | 5.0 | 28.0 |
| v3.3 | 0.500 | 0.000 | 694 | 0.000 | 0.000 | 0.000 | -- | -- | 26.5 |

If the portable columns are numeric while mbw/llcocc/llcmr are `--`, the portable benchmark recovers scheduling + memory dimensions in a stock KVM guest where the RDT/LL-PMU fingerprint cannot (C26).

## §6 Per-cell medians (claim class in header)

| env | variant | workload | schedlat[directional] | psi_mem[descriptive] | membw_est[descriptive] | psi_io[descriptive] | schedthr[descriptive(guard)] | steal[descriptive(vm-only)] |
|---|---|---|---|---|---|---|---|---|
| bare | v2.1 | app01_ml_llc | 21.0 | 0.000 | 78.5 | 0.000 | 0.000 | 0.000 |
| bare | v2.1 | app05_streaming | 0.000 | 0.000 | 6470 | 0.000 | 0.000 | 0.000 |
| bare | v2.1 | app07_ordering | 1.0 | 0.000 | 944 | 0.000 | 0.000 | 0.000 |
| bare | v2.1 | app10_search | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| bare | v2.1 | app11_sort_net | 0.000 | 0.000 | 9.0 | 0.000 | 0.000 | 0.000 |
| bare | v2.1 | app13_query_scan | 0.000 | 0.000 | 69.0 | 80.0 | 0.000 | 0.000 |
| bare | v3.3 | app01_ml_llc | 20.5 | 0.000 | 79.0 | 0.000 | 0.000 | 0.000 |
| bare | v3.3 | app05_streaming | 0.000 | 0.000 | 6400 | 0.000 | 0.000 | 0.000 |
| bare | v3.3 | app07_ordering | 1.0 | 0.000 | 932 | 0.000 | 0.000 | 0.000 |
| bare | v3.3 | app10_search | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| bare | v3.3 | app11_sort_net | 1.0 | 0.000 | 65.0 | 0.000 | 0.000 | 0.000 |
| bare | v3.3 | app13_query_scan | 0.000 | 0.000 | 68.0 | 79.0 | 0.000 | 0.000 |
| container | v2.1 | app01_ml_llc | 22.0 | 0.000 | 76.0 | 0.000 | 0.000 | 0.000 |
| container | v2.1 | app05_streaming | 0.000 | 0.000 | 5762 | 0.000 | 0.000 | 0.000 |
| container | v2.1 | app07_ordering | 1.0 | 0.000 | 935 | 0.000 | 0.000 | 0.000 |
| container | v2.1 | app10_search | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| container | v2.1 | app11_sort_net | 0.000 | 0.000 | 11.0 | 0.000 | 0.000 | 0.000 |
| container | v2.1 | app13_query_scan | 0.000 | 0.000 | 69.0 | 80.0 | 0.000 | 0.000 |
| container | v3.3 | app01_ml_llc | 21.5 | 0.000 | 81.0 | 0.000 | 0.000 | 0.000 |
| container | v3.3 | app05_streaming | 0.000 | 0.000 | 5699 | 0.000 | 0.000 | 0.000 |
| container | v3.3 | app07_ordering | 1.0 | 0.000 | 924 | 0.000 | 0.000 | 0.000 |
| container | v3.3 | app10_search | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| container | v3.3 | app11_sort_net | 1.0 | 0.000 | 65.5 | 0.000 | 0.000 | 0.000 |
| container | v3.3 | app13_query_scan | 0.000 | 0.000 | 68.5 | 79.5 | 0.000 | 0.000 |
| container-podman | v2.1 | app01_ml_llc | 21.0 | 0.000 | 77.0 | 0.000 | 0.000 | 0.000 |
| container-podman | v2.1 | app05_streaming | 0.000 | 0.000 | 6040 | 0.000 | 0.000 | 0.000 |
| container-podman | v2.1 | app07_ordering | 1.0 | 0.000 | 938 | 0.000 | 0.000 | 0.000 |
| container-podman | v2.1 | app10_search | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| container-podman | v2.1 | app11_sort_net | 0.000 | 0.000 | 14.0 | 0.000 | 0.000 | 0.000 |
| container-podman | v2.1 | app13_query_scan | 0.000 | 0.000 | 68.5 | 79.0 | 0.000 | 0.000 |
| container-podman | v3.3 | app01_ml_llc | 21.5 | 0.000 | 82.5 | 0.000 | 0.000 | 0.000 |
| container-podman | v3.3 | app05_streaming | 0.000 | 0.000 | 6146 | 0.000 | 0.000 | 0.000 |
| container-podman | v3.3 | app07_ordering | 1.0 | 0.000 | 925 | 0.000 | 0.000 | 0.000 |
| container-podman | v3.3 | app10_search | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| container-podman | v3.3 | app11_sort_net | 1.0 | 0.000 | 74.5 | 0.000 | 0.000 | 0.000 |
| container-podman | v3.3 | app13_query_scan | 0.000 | 0.000 | 67.0 | 81.0 | 0.000 | 0.000 |
| container-lxc | v2.1 | app01_ml_llc | 28.0 | 0.000 | 86.0 | 0.000 | 0.000 | 0.000 |
| container-lxc | v2.1 | app05_streaming | 0.000 | 0.000 | 6236 | 0.000 | 0.000 | 0.000 |
| container-lxc | v2.1 | app07_ordering | 3.0 | 0.000 | 928 | 0.000 | 0.000 | 0.000 |
| container-lxc | v2.1 | app10_search | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| container-lxc | v2.1 | app11_sort_net | 2.0 | 0.000 | 11.0 | 0.000 | 0.000 | 0.000 |
| container-lxc | v2.1 | app13_query_scan | 0.000 | 0.000 | 68.5 | 80.0 | 0.000 | 0.000 |
| container-lxc | v3.3 | app01_ml_llc | 23.0 | 0.000 | 98.0 | 0.000 | 0.000 | 0.000 |
| container-lxc | v3.3 | app05_streaming | 0.000 | 0.000 | 6109 | 0.000 | 0.000 | 0.000 |
| container-lxc | v3.3 | app07_ordering | 1.0 | 0.000 | 917 | 0.000 | 0.000 | 0.000 |
| container-lxc | v3.3 | app10_search | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| container-lxc | v3.3 | app11_sort_net | 1.0 | 0.000 | 27.5 | 0.000 | 0.000 | 0.000 |
| container-lxc | v3.3 | app13_query_scan | 0.000 | 0.000 | 69.0 | 80.0 | 0.000 | 0.000 |
| container-k8s | v2.1 | app01_ml_llc | 21.0 | 0.000 | 78.5 | 0.000 | 0.000 | 0.000 |
| container-k8s | v2.1 | app05_streaming | 0.000 | 0.000 | 7096 | 0.000 | 0.000 | 0.000 |
| container-k8s | v2.1 | app07_ordering | 0.000 | 0.000 | 949 | 0.000 | 0.000 | 0.000 |
| container-k8s | v2.1 | app10_search | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| container-k8s | v2.1 | app11_sort_net | 0.000 | 0.000 | 4.0 | 0.000 | 0.000 | 0.000 |
| container-k8s | v2.1 | app13_query_scan | 0.000 | 0.000 | 65.0 | 81.0 | 0.000 | 0.000 |
| container-k8s | v3.3 | app01_ml_llc | 21.0 | 0.000 | 81.0 | 0.000 | 0.000 | 0.000 |
| container-k8s | v3.3 | app05_streaming | 0.000 | 0.000 | 6554 | 0.000 | 0.000 | 0.000 |
| container-k8s | v3.3 | app07_ordering | 0.000 | 0.000 | 938 | 0.000 | 0.000 | 0.000 |
| container-k8s | v3.3 | app10_search | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| container-k8s | v3.3 | app11_sort_net | 1.0 | 0.000 | 40.5 | 0.000 | 0.000 | 0.000 |
| container-k8s | v3.3 | app13_query_scan | 0.000 | 0.000 | 66.5 | 81.0 | 0.000 | 0.000 |
| vm-guest | v2.1 | app01_ml_llc | 33.0 | 0.000 | 8.0 | 0.000 | 0.000 | 0.000 |
| vm-guest | v2.1 | app05_streaming | 0.000 | 0.000 | 79826 | 0.000 | 0.000 | 0.000 |
| vm-guest | v2.1 | app07_ordering | 1.0 | 0.000 | 25537 | 0.000 | 0.000 | 0.000 |
| vm-guest | v2.1 | app10_search | 0.000 | 0.000 | 1.0 | 0.000 | 0.000 | 0.000 |
| vm-guest | v2.1 | app11_sort_net | 0.000 | 0.000 | 108 | 0.000 | 0.000 | 0.000 |
| vm-guest | v2.1 | app13_query_scan | 0.000 | 0.000 | 1506 | 17.0 | 0.000 | 0.000 |
| vm-guest | v3.3 | app01_ml_llc | 33.0 | 0.000 | 6.0 | 0.000 | 0.000 | 0.000 |
| vm-guest | v3.3 | app05_streaming | 0.000 | 0.000 | 75089 | 0.000 | 0.000 | 0.000 |
| vm-guest | v3.3 | app07_ordering | 1.0 | 0.000 | 24574 | 0.000 | 0.000 | 0.000 |
| vm-guest | v3.3 | app10_search | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| vm-guest | v3.3 | app11_sort_net | 1.0 | 0.000 | 77.0 | 0.000 | 0.000 | 0.000 |
| vm-guest | v3.3 | app13_query_scan | 0.000 | 0.000 | 1545 | 16.0 | 0.000 | 0.000 |


# Portable-metrics faithfulness adjudication — results/p2-15metric-xdeploy

Cells with data: 60 | reps/cell: min 12 max 12 | scipy: yes

## §1 Availability matrix (portable metrics render numeric vs '--')

`ok` = the metric produced a numeric reading in ≥1 rep of that env; `--` = never (source absent — e.g. CONFIG_PSI=n, no cpu.max quota, no perf). The VM-portable claim: schedlat/psi_*/membw_est/steal stay `ok` in vm-guest where the canonical RDT metrics (mbw/llcocc/llcmr) go `--`.

### v2.1

| env | schedlat | psi_mem | membw_est | psi_io | schedthr | steal | psp | idle_preempt | | | mbw | llcocc | llcmr |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| bare | ok | ok | ok | ok | ok | ok | ok | -- | | | ok | ok | ok |
| container | ok | ok | ok | ok | ok | ok | ok | -- | | | ok | ok | ok |
| container-podman | ok | ok | ok | ok | ok | ok | ok | -- | | | ok | ok | ok |
| container-lxc | ok | ok | ok | ok | ok | ok | ok | -- | | | ok | ok | ok |
| container-k8s | ok | ok | ok | ok | ok | ok | ok | -- | | | ok | ok | ok |
| vm-guest | ok | ok | ok | ok | ok | ok | ok | -- | | | -- | ok | ok |

### v3.3

| env | schedlat | psi_mem | membw_est | psi_io | schedthr | steal | psp | idle_preempt | | | mbw | llcocc | llcmr |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| bare | ok | ok | ok | ok | ok | ok | ok | ok | | | ok | ok | ok |
| container | ok | ok | ok | ok | ok | ok | ok | ok | | | ok | ok | ok |
| container-podman | ok | ok | ok | ok | ok | ok | ok | ok | | | ok | ok | ok |
| container-lxc | ok | ok | ok | ok | ok | ok | ok | ok | | | ok | ok | ok |
| container-k8s | ok | ok | ok | ok | ok | ok | ok | ok | | | ok | ok | ok |
| vm-guest | ok | ok | ok | ok | ok | ok | ok | ok | | | -- | -- | ok |

## §2 Spearman: portable metric vs ground truth (solo, traffic-gated)

| variant | portable | vs GT | n | ρ | p | verdict |
|---|---|---|---|---|---|---|
| v2.1 | membw_est | gt_mbw_bps | 0 | - | - | n<3 / no spread |
| v2.1 | membw_est | gt_llc_miss | 30 | 0.948 | 0.000 | faithful |
| v2.1 | schedlat | gt_llcmr | 30 | -0.471 | 0.009 | weak |
| v2.1 | psi_mem | gt_llc_miss | 30 | - | - | n<3 / no spread |
| v3.3 | membw_est | gt_mbw_bps | 0 | - | - | n<3 / no spread |
| v3.3 | membw_est | gt_llc_miss | 30 | 0.896 | 0.000 | faithful |
| v3.3 | schedlat | gt_llcmr | 30 | -0.792 | 0.000 | weak |
| v3.3 | psi_mem | gt_llc_miss | 30 | - | - | n<3 / no spread |

- **membw_est vs gt_mbw_bps** — INDEPENDENT validation vs resctrl MBM bandwidth — expect STRONG + (often n<3: resctrl mbw GT is '--' by CMT design, C24)
- **membw_est vs gt_llc_miss** — consistency check only — membw_est IS derived from cache-misses, so this shares its source, NOT an independent validation
- **schedlat vs gt_llcmr** — directional: contention slows the victim, its run-queue backs up — expect +
- **psi_mem vs gt_llc_miss** — FALSIFICATION: psi_mem is capacity-driven — expect WEAK vs bandwidth
- **Scope caveat (in-guest envs):** `groundtruth.tsv` is always captured HOST-side, while in vm-guest / container-guest the portable metrics are captured INSIDE the guest — so those cells correlate guest-side metrics against the host's counters. Treat vm-guest §2 rows as indicative only; the §1 availability + §4 in-guest tables are the load-bearing VM evidence.

## §3 PSI bandwidth-blindness falsification

Per (env,variant) the cell with the highest `membw_est`. If `membw_est` is high (≥1000 MB/s) while `psi_mem` stays flat (≤5%), `psi_mem` is confirmed **capacity-only** (bandwidth-blind) and `membw_est` is the metric carrying the bandwidth dimension. `schedlat` should rise too.

| env | variant | workload | membw_est (MB/s) | psi_mem (%) | schedlat (%) | finding |
|---|---|---|---|---|---|---|
| bare | v2.1 | app05_streaming | 6174 | 0.000 | 0.000 | blind CONFIRMED |
| container | v2.1 | app05_streaming | 6610 | 0.000 | 0.000 | blind CONFIRMED |
| container-podman | v2.1 | app05_streaming | 5902 | 0.000 | 0.000 | blind CONFIRMED |
| container-lxc | v2.1 | app05_streaming | 6380 | 0.000 | 0.000 | blind CONFIRMED |
| container-k8s | v2.1 | app05_streaming | 7136 | 0.000 | 0.000 | blind CONFIRMED |
| vm-guest | v2.1 | app05_streaming | 79818 | 0.000 | 0.000 | blind CONFIRMED |
| bare | v3.3 | app05_streaming | 6218 | 0.000 | 0.000 | blind CONFIRMED |
| container | v3.3 | app05_streaming | 5657 | 0.000 | 0.000 | blind CONFIRMED |
| container-podman | v3.3 | app05_streaming | 5847 | 0.000 | 0.000 | blind CONFIRMED |
| container-lxc | v3.3 | app05_streaming | 5852 | 0.000 | 0.000 | blind CONFIRMED |
| container-k8s | v3.3 | app05_streaming | 6394 | 0.000 | 0.000 | blind CONFIRMED |
| vm-guest | v3.3 | app05_streaming | 75318 | 0.000 | 0.000 | blind CONFIRMED |

**psi_mem capacity-only:** CONFIRMED on ≥1 cell (needs a saturating-bandwidth workload with ample free RAM, e.g. app05_streaming).

## §4 membw_est corroboration gate (net-path instrumentation caveat)

`membw_est` is cache-miss-derived and reported as an UNCLAMPED absolute (MB/s), so on net-heavy workloads where the hardware cache/bandwidth canonicals (`mbw`, `llcmr`) read ~0, a non-zero `membw_est` is NOT corroborated as workload DRAM bandwidth — it integrates net-softirq + per-packet eBPF-hook misses. The eBPF variant (v3.3) inflates this over the C variant (v2.1): on app11 v3.3 `membw_est` is ~6–7× v2.1, and an INDEPENDENT host-side GT shows v3.3 generating ~3.6× the system LLC misses v2.1 does on that workload (the bandwidth analogue of the eBPF overhead in `docs/V3-OVERHEAD-FINDINGS.md`). The **canonical 7 are UNAFFECTED** — `mbw`/`llcmr` are %-normalized + clamped, so the ~0.02%-of-ceiling footprint rounds to 0 (verified: app11 `mbw`=0/`llcmr`=0 for BOTH variants). Cells with `membw_est`>0 but `mbw`≈0 and `llcmr`≈0 are flagged **uncorroborated** (C31): read them as instrumentation-influenced, not true bandwidth; do not use them for cross-variant absolute-bandwidth claims.

| env | variant | workload | membw_est | mbw | llcmr | corroborated? |
|---|---|---|---|---|---|---|
| bare | v2.1 | app11_sort_net | 10.0 | 0.000 | 0.000 | **uncorroborated (net-path)** |
| bare | v3.3 | app11_sort_net | 55.0 | 0.000 | 0.000 | **uncorroborated (net-path)** |
| container | v2.1 | app11_sort_net | 12.5 | 0.000 | 0.000 | **uncorroborated (net-path)** |
| container | v3.3 | app11_sort_net | 57.5 | 0.000 | 0.000 | **uncorroborated (net-path)** |
| container-podman | v2.1 | app11_sort_net | 17.0 | 0.000 | 0.000 | **uncorroborated (net-path)** |
| container-podman | v3.3 | app11_sort_net | 50.5 | 0.000 | 0.000 | **uncorroborated (net-path)** |
| container-lxc | v2.1 | app11_sort_net | 13.5 | 0.000 | 0.000 | **uncorroborated (net-path)** |
| container-lxc | v3.3 | app11_sort_net | 36.0 | 0.000 | 0.000 | **uncorroborated (net-path)** |
| container-k8s | v2.1 | app11_sort_net | 5.0 | 0.000 | 0.000 | **uncorroborated (net-path)** |
| container-k8s | v3.3 | app11_sort_net | 40.5 | 0.000 | 0.000 | **uncorroborated (net-path)** |

_10 cell(s) flagged: RDT present but mbw≈0 and llcmr≈0 while membw_est>0. The v2.1↔v3.3 gap on these is the eBPF net-path footprint, not workload bandwidth (C31). vm-guest is excluded here (mbw is structurally `--`; see the §2 scope caveat)._

## §5 vm-guest confirmation

Portable medians in-guest (across workloads), and the canonical RDT metrics that are structurally `--` there.

| variant | schedlat | psi_mem | membw_est | psi_io | schedthr | steal | psp | idle_preempt | mbw | llcocc | llcmr |
|---|---|---|---|---|---|---|---|---|---|---|---|
| v2.1 | 0.000 | 0.000 | 119 | 0.000 | 0.000 | 0.000 | 10.0 | -- | -- | 0.000 | 1.0 |
| v3.3 | 0.000 | 0.000 | 102 | 0.000 | 0.000 | 0.000 | 11.0 | 101 | -- | -- | 0.000 |

If the portable columns are numeric while mbw/llcocc/llcmr are `--`, the portable benchmark recovers scheduling + memory dimensions in a stock KVM guest where the RDT/LL-PMU fingerprint cannot (C26).

## §6 Per-cell medians (claim class in header)

| env | variant | workload | schedlat[directional] | psi_mem[descriptive] | membw_est[descriptive] | psi_io[descriptive] | schedthr[descriptive(guard)] | steal[descriptive(vm-only)] | psp[directional] | idle_preempt[directional] |
|---|---|---|---|---|---|---|---|---|---|---|
| bare | v2.1 | app01_ml_llc | 21.0 | 0.000 | 76.0 | 0.000 | 0.000 | 0.000 | 1952 | - |
| bare | v2.1 | app05_streaming | 0.000 | 0.000 | 6174 | 0.000 | 0.000 | 0.000 | 28.0 | - |
| bare | v2.1 | app10_search | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 39.0 | - |
| bare | v2.1 | app11_sort_net | 0.000 | 0.000 | 10.0 | 0.000 | 0.000 | 0.000 | 79.0 | - |
| bare | v2.1 | app13_query_scan | 0.000 | 0.000 | 70.0 | 79.0 | 0.000 | 0.000 | 9.0 | - |
| bare | v3.3 | app01_ml_llc | 21.0 | 0.000 | 84.0 | 0.000 | 0.000 | 0.000 | 2004 | 52.0 |
| bare | v3.3 | app05_streaming | 0.000 | 0.000 | 6218 | 0.000 | 0.000 | 0.000 | 29.0 | 1.0 |
| bare | v3.3 | app10_search | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 39.0 | 1.0 |
| bare | v3.3 | app11_sort_net | 1.0 | 0.000 | 55.0 | 0.000 | 0.000 | 0.000 | 82.5 | 229950 |
| bare | v3.3 | app13_query_scan | 0.000 | 0.000 | 69.0 | 78.5 | 0.000 | 0.000 | 9.0 | 1366 |
| container | v2.1 | app01_ml_llc | 21.0 | 0.000 | 76.5 | 0.000 | 0.000 | 0.000 | 1914 | - |
| container | v2.1 | app05_streaming | 0.000 | 0.000 | 6610 | 0.000 | 0.000 | 0.000 | 31.0 | - |
| container | v2.1 | app10_search | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 37.5 | - |
| container | v2.1 | app11_sort_net | 0.000 | 0.000 | 12.5 | 0.000 | 0.000 | 0.000 | 80.5 | - |
| container | v2.1 | app13_query_scan | 0.000 | 0.000 | 69.0 | 78.0 | 0.000 | 0.000 | 8.0 | - |
| container | v3.3 | app01_ml_llc | 21.0 | 0.000 | 81.5 | 0.000 | 0.000 | 0.000 | 1985 | 52.0 |
| container | v3.3 | app05_streaming | 0.000 | 0.000 | 5657 | 0.000 | 0.000 | 0.000 | 29.0 | 0.000 |
| container | v3.3 | app10_search | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 40.0 | 1.0 |
| container | v3.3 | app11_sort_net | 1.0 | 0.000 | 57.5 | 0.000 | 0.000 | 0.000 | 86.0 | 217948 |
| container | v3.3 | app13_query_scan | 0.000 | 0.000 | 69.0 | 79.0 | 0.000 | 0.000 | 8.0 | 1367 |
| container-podman | v2.1 | app01_ml_llc | 21.5 | 0.000 | 78.5 | 0.000 | 0.000 | 0.000 | 1910 | - |
| container-podman | v2.1 | app05_streaming | 0.000 | 0.000 | 5902 | 0.000 | 0.000 | 0.000 | 29.0 | - |
| container-podman | v2.1 | app10_search | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 38.0 | - |
| container-podman | v2.1 | app11_sort_net | 0.000 | 0.000 | 17.0 | 0.000 | 0.000 | 0.000 | 80.5 | - |
| container-podman | v2.1 | app13_query_scan | 0.000 | 0.000 | 68.0 | 79.0 | 0.000 | 0.000 | 8.0 | - |
| container-podman | v3.3 | app01_ml_llc | 21.0 | 0.000 | 84.0 | 0.000 | 0.000 | 0.000 | 1934 | 52.0 |
| container-podman | v3.3 | app05_streaming | 0.000 | 0.000 | 5847 | 0.000 | 0.000 | 0.000 | 30.0 | 1.0 |
| container-podman | v3.3 | app10_search | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 42.0 | 2.0 |
| container-podman | v3.3 | app11_sort_net | 1.0 | 0.000 | 50.5 | 0.000 | 0.000 | 0.000 | 84.0 | 219378 |
| container-podman | v3.3 | app13_query_scan | 0.000 | 0.000 | 61.5 | 81.5 | 0.000 | 0.000 | 7.5 | 1366 |
| container-lxc | v2.1 | app01_ml_llc | 28.0 | 0.000 | 87.5 | 0.000 | 0.000 | 0.000 | 0.000 | - |
| container-lxc | v2.1 | app05_streaming | 0.000 | 0.000 | 6380 | 0.000 | 0.000 | 0.000 | 0.000 | - |
| container-lxc | v2.1 | app10_search | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | - | - |
| container-lxc | v2.1 | app11_sort_net | 2.0 | 0.000 | 13.5 | 0.000 | 0.000 | 0.000 | - | - |
| container-lxc | v2.1 | app13_query_scan | 0.000 | 0.000 | 69.0 | 79.0 | 0.000 | 0.000 | - | - |
| container-lxc | v3.3 | app01_ml_llc | 24.0 | 0.000 | 94.0 | 0.000 | 0.000 | 0.000 | 2702 | 820 |
| container-lxc | v3.3 | app05_streaming | 0.000 | 0.000 | 5852 | 0.000 | 0.000 | 0.000 | 736 | 703 |
| container-lxc | v3.3 | app10_search | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 856 | 816 |
| container-lxc | v3.3 | app11_sort_net | 1.0 | 0.000 | 36.0 | 0.000 | 0.000 | 0.000 | 2441 | 288077 |
| container-lxc | v3.3 | app13_query_scan | 0.000 | 0.000 | 68.5 | 79.0 | 0.000 | 0.000 | 112 | 1476 |
| container-k8s | v2.1 | app01_ml_llc | 21.0 | 0.000 | 78.5 | 0.000 | 0.000 | 0.000 | 1998 | - |
| container-k8s | v2.1 | app05_streaming | 0.000 | 0.000 | 7136 | 0.000 | 0.000 | 0.000 | 31.5 | - |
| container-k8s | v2.1 | app10_search | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 40.0 | - |
| container-k8s | v2.1 | app11_sort_net | 0.000 | 0.000 | 5.0 | 0.000 | 0.000 | 0.000 | 73.5 | - |
| container-k8s | v2.1 | app13_query_scan | 0.000 | 0.000 | 55.5 | 84.0 | 0.000 | 0.000 | 7.0 | - |
| container-k8s | v3.3 | app01_ml_llc | 21.0 | 0.000 | 83.5 | 0.000 | 0.000 | 0.000 | 1944 | 52.0 |
| container-k8s | v3.3 | app05_streaming | 0.000 | 0.000 | 6394 | 0.000 | 0.000 | 0.000 | 31.5 | 0.000 |
| container-k8s | v3.3 | app10_search | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 41.0 | 1.0 |
| container-k8s | v3.3 | app11_sort_net | 1.0 | 0.000 | 40.5 | 0.000 | 0.000 | 0.000 | 77.0 | 254770 |
| container-k8s | v3.3 | app13_query_scan | 0.000 | 0.000 | 54.0 | 82.5 | 0.000 | 0.000 | 6.0 | 1310 |
| vm-guest | v2.1 | app01_ml_llc | 33.0 | 0.000 | 10.0 | 0.000 | 0.000 | 0.000 | 2178 | - |
| vm-guest | v2.1 | app05_streaming | 0.000 | 0.000 | 79818 | 0.000 | 0.000 | 0.000 | 10.0 | - |
| vm-guest | v2.1 | app10_search | 0.000 | 0.000 | 1.0 | 0.000 | 0.000 | 0.000 | 8.5 | - |
| vm-guest | v2.1 | app11_sort_net | 0.000 | 0.000 | 122 | 0.000 | 0.000 | 0.000 | 792 | - |
| vm-guest | v2.1 | app13_query_scan | 0.000 | 0.000 | 874 | 12.0 | 0.000 | 0.000 | 1.0 | - |
| vm-guest | v3.3 | app01_ml_llc | 33.0 | 0.000 | 13.0 | 0.000 | 0.000 | 0.000 | 2208 | 102 |
| vm-guest | v3.3 | app05_streaming | 0.000 | 0.000 | 75318 | 0.000 | 0.000 | 0.000 | 10.5 | 0.000 |
| vm-guest | v3.3 | app10_search | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 8.0 | 0.000 |
| vm-guest | v3.3 | app11_sort_net | 1.0 | 0.000 | 102 | 0.000 | 0.000 | 0.000 | 84.5 | 171516 |
| vm-guest | v3.3 | app13_query_scan | 0.000 | 0.000 | 818 | 14.0 | 0.000 | 0.000 | 1.0 | 102 |


# Portable-metrics faithfulness adjudication — results/p2-15metric-xdeploy-1of3 (1/3 footprint + hard CPU pinning; supersedes the 2/3 run)

> **NOTE (mbw ceiling, C34):** v2.1 `mbw` is correctly scoped (per-cgroup
> resctrl, D12) against the audited machine ceiling (281600 MB/s, 2026-06-13
> re-run). Banked v3.3 `mbw` was computed against the pre-audit ceiling
> (42656 MB/s) and reads ~6.6x high in absolute terms (multiply by 0.151 for
> the corrected ceiling); within-variant ratios-vs-bare and rank correlations
> are ceiling-invariant and unaffected.

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
| v2.1 | membw_est | gt_llc_miss | 30 | 0.880 | 0.000 | faithful |
| v2.1 | schedlat | gt_llcmr | 30 | -0.886 | 0.000 | weak |
| v2.1 | psi_mem | gt_llc_miss | 30 | - | - | n<3 / no spread |
| v3.3 | membw_est | gt_mbw_bps | 0 | - | - | n<3 / no spread |
| v3.3 | membw_est | gt_llc_miss | 30 | 0.916 | 0.000 | faithful |
| v3.3 | schedlat | gt_llcmr | 30 | -0.887 | 0.000 | weak |
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
| bare | v2.1 | app05_streaming | 7150 | 0.000 | 0.000 | blind CONFIRMED |
| container | v2.1 | app05_streaming | 6662 | 0.000 | 0.000 | blind CONFIRMED |
| container-podman | v2.1 | app05_streaming | 6373 | 0.000 | 0.000 | blind CONFIRMED |
| container-lxc | v2.1 | app05_streaming | 6840 | 0.000 | 0.000 | blind CONFIRMED |
| container-k8s | v2.1 | app05_streaming | 6212 | 0.000 | 0.000 | blind CONFIRMED |
| vm-guest | v2.1 | app05_streaming | 79994 | 0.000 | 0.000 | blind CONFIRMED |
| bare | v3.3 | app05_streaming | 6694 | 0.000 | 0.000 | blind CONFIRMED |
| container | v3.3 | app05_streaming | 6448 | 0.000 | 0.000 | blind CONFIRMED |
| container-podman | v3.3 | app05_streaming | 6284 | 0.000 | 0.000 | blind CONFIRMED |
| container-lxc | v3.3 | app05_streaming | 6448 | 0.000 | 0.000 | blind CONFIRMED |
| container-k8s | v3.3 | app05_streaming | 6008 | 0.000 | 0.000 | blind CONFIRMED |
| vm-guest | v3.3 | app05_streaming | 75342 | 0.000 | 0.000 | blind CONFIRMED |

**psi_mem capacity-only:** CONFIRMED on ≥1 cell (needs a saturating-bandwidth workload with ample free RAM, e.g. app05_streaming).

## §4 membw_est corroboration gate (net-path instrumentation caveat)

`membw_est` is cache-miss-derived and reported as an UNCLAMPED absolute (MB/s), so on net-heavy workloads where the hardware cache/bandwidth canonicals (`mbw`, `llcmr`) read ~0, a non-zero `membw_est` is NOT corroborated as workload DRAM bandwidth — it integrates net-softirq + per-packet eBPF-hook misses. The eBPF variant (v3.3) inflates this over the C variant (v2.1): on app11 v3.3 `membw_est` is ~6–7× v2.1, and an INDEPENDENT host-side GT shows v3.3 generating ~3.6× the system LLC misses v2.1 does on that workload (the bandwidth analogue of the eBPF overhead in `docs/V3-OVERHEAD-FINDINGS.md`). The **canonical 7 are UNAFFECTED** — `mbw`/`llcmr` are %-normalized + clamped, so the ~0.02%-of-ceiling footprint rounds to 0 (verified: app11 `mbw`=0/`llcmr`=0 for BOTH variants). Cells with `membw_est`>0 but `mbw`≈0 and `llcmr`≈0 are flagged **uncorroborated** (C31): read them as instrumentation-influenced, not true bandwidth; do not use them for cross-variant absolute-bandwidth claims.

| env | variant | workload | membw_est | mbw | llcmr | corroborated? |
|---|---|---|---|---|---|---|
| — | — | — | — | — | — | all membw_est readings corroborated by mbw/llcmr |

_0 cell(s) flagged: RDT present but mbw≈0 and llcmr≈0 while membw_est>0. The v2.1↔v3.3 gap on these is the eBPF net-path footprint, not workload bandwidth (C31). vm-guest is excluded here (mbw is structurally `--`; see the §2 scope caveat)._

## §5 vm-guest confirmation

Portable medians in-guest (across workloads), and the canonical RDT metrics that are structurally `--` there.

| variant | schedlat | psi_mem | membw_est | psi_io | schedthr | steal | psp | idle_preempt | mbw | llcocc | llcmr |
|---|---|---|---|---|---|---|---|---|---|---|---|
| v2.1 | 50.0 | 0.000 | 524 | 0.000 | 0.000 | 0.000 | 2262 | -- | -- | 1.0 | 2.0 |
| v3.3 | 50.0 | 0.000 | 586 | 0.000 | 0.000 | 0.000 | 2238 | 0.000 | -- | -- | 1.0 |

If the portable columns are numeric while mbw/llcocc/llcmr are `--`, the portable benchmark recovers scheduling + memory dimensions in a stock KVM guest where the RDT/LL-PMU fingerprint cannot (C26).

## §6 Per-cell medians (claim class in header)

| env | variant | workload | schedlat[directional] | psi_mem[descriptive] | membw_est[descriptive] | psi_io[descriptive] | schedthr[descriptive(guard)] | steal[descriptive(vm-only)] | psp[directional] | idle_preempt[directional] |
|---|---|---|---|---|---|---|---|---|---|---|
| bare | v2.1 | app01_ml_llc | 31.5 | 0.000 | 134 | 0.000 | 0.000 | 0.000 | 1892 | - |
| bare | v2.1 | app05_streaming | 0.000 | 0.000 | 7150 | 0.000 | 0.000 | 0.000 | 30.0 | - |
| bare | v2.1 | app10_search | 17.0 | 0.000 | 2.0 | 0.000 | 1.0 | 0.000 | 2686 | - |
| bare | v2.1 | app11_sort_net | 20.0 | 0.000 | 4050 | 0.000 | 0.000 | 0.000 | 33008 | - |
| bare | v2.1 | app13_query_scan | 0.000 | 0.000 | 94.0 | 79.0 | 0.000 | 0.000 | 6.5 | - |
| bare | v3.3 | app01_ml_llc | 31.0 | 0.000 | 107 | 0.000 | 0.000 | 0.000 | 1866 | 33.5 |
| bare | v3.3 | app05_streaming | 0.000 | 0.000 | 6694 | 0.000 | 0.000 | 0.000 | 29.5 | 0.000 |
| bare | v3.3 | app10_search | 17.0 | 0.000 | 2.0 | 0.000 | 1.0 | 0.000 | 2690 | 12.5 |
| bare | v3.3 | app11_sort_net | 20.0 | 0.000 | 4224 | 0.000 | 0.000 | 0.000 | 17386 | 22104 |
| bare | v3.3 | app13_query_scan | 0.000 | 0.000 | 55.0 | 82.5 | 0.000 | 0.000 | 6.5 | 1381 |
| container | v2.1 | app01_ml_llc | 32.0 | 0.000 | 108 | 0.000 | 0.000 | 0.000 | 1824 | - |
| container | v2.1 | app05_streaming | 0.000 | 0.000 | 6662 | 0.000 | 0.000 | 0.000 | 28.5 | - |
| container | v2.1 | app10_search | 17.0 | 0.000 | 2.0 | 0.000 | 1.0 | 0.000 | 2690 | - |
| container | v2.1 | app11_sort_net | 21.0 | 0.000 | 2908 | 0.000 | 0.000 | 0.000 | 36015 | - |
| container | v2.1 | app13_query_scan | 0.000 | 0.000 | 52.5 | 83.5 | 0.000 | 0.000 | 5.0 | - |
| container | v3.3 | app01_ml_llc | 32.0 | 0.000 | 108 | 0.000 | 0.000 | 0.000 | 1776 | 33.0 |
| container | v3.3 | app05_streaming | 0.000 | 0.000 | 6448 | 0.000 | 0.000 | 0.000 | 30.0 | 0.000 |
| container | v3.3 | app10_search | 17.0 | 0.000 | 2.0 | 0.000 | 1.0 | 0.000 | 2690 | 12.5 |
| container | v3.3 | app11_sort_net | 19.0 | 0.000 | 4700 | 0.000 | 0.000 | 0.000 | 19984 | 19188 |
| container | v3.3 | app13_query_scan | 0.000 | 0.000 | 47.5 | 84.5 | 0.000 | 0.000 | 6.0 | 1318 |
| container-podman | v2.1 | app01_ml_llc | 31.5 | 0.000 | 107 | 0.000 | 0.000 | 0.000 | 1824 | - |
| container-podman | v2.1 | app05_streaming | 0.000 | 0.000 | 6373 | 0.000 | 0.000 | 0.000 | 30.0 | - |
| container-podman | v2.1 | app10_search | 17.0 | 0.000 | 2.0 | 0.000 | 1.0 | 0.000 | 2696 | - |
| container-podman | v2.1 | app11_sort_net | 21.0 | 0.000 | 2920 | 0.000 | 0.000 | 0.000 | 35332 | - |
| container-podman | v2.1 | app13_query_scan | 0.000 | 0.000 | 97.0 | 79.0 | 0.000 | 0.000 | 6.5 | - |
| container-podman | v3.3 | app01_ml_llc | 31.0 | 0.000 | 110 | 0.000 | 0.000 | 0.000 | 1852 | 32.0 |
| container-podman | v3.3 | app05_streaming | 0.000 | 0.000 | 6284 | 0.000 | 0.000 | 0.000 | 31.0 | 0.000 |
| container-podman | v3.3 | app10_search | 17.0 | 0.000 | 2.0 | 0.000 | 0.000 | 0.000 | 2680 | 20.5 |
| container-podman | v3.3 | app11_sort_net | 19.0 | 0.000 | 4403 | 0.000 | 0.000 | 0.000 | 21289 | 19076 |
| container-podman | v3.3 | app13_query_scan | 0.000 | 0.000 | 64.0 | 80.5 | 0.000 | 0.000 | 7.0 | 1429 |
| container-lxc | v2.1 | app01_ml_llc | 33.0 | 0.000 | 104 | 0.000 | 0.000 | 0.000 | 2428 | - |
| container-lxc | v2.1 | app05_streaming | 0.000 | 0.000 | 6840 | 0.000 | 0.000 | 0.000 | 1161 | - |
| container-lxc | v2.1 | app10_search | 17.0 | 0.000 | 2.0 | 0.000 | 0.000 | 0.000 | 3774 | - |
| container-lxc | v2.1 | app11_sort_net | 24.0 | 0.000 | 1357 | 0.000 | 0.000 | 0.000 | 71652 | - |
| container-lxc | v2.1 | app13_query_scan | 0.000 | 0.000 | 85.0 | 80.0 | 0.000 | 0.000 | 69.0 | - |
| container-lxc | v3.3 | app01_ml_llc | 32.0 | 0.000 | 110 | 0.000 | 0.000 | 0.000 | 2564 | 814 |
| container-lxc | v3.3 | app05_streaming | 0.000 | 0.000 | 6448 | 0.000 | 0.000 | 0.000 | 1024 | 994 |
| container-lxc | v3.3 | app10_search | 17.0 | 0.000 | 2.0 | 0.000 | 0.000 | 0.000 | 3977 | 1394 |
| container-lxc | v3.3 | app11_sort_net | 24.0 | 0.000 | 1438 | 0.000 | 0.000 | 0.000 | 37838 | 30867 |
| container-lxc | v3.3 | app13_query_scan | 0.000 | 0.000 | 66.0 | 81.0 | 0.000 | 0.000 | 74.5 | 1478 |
| container-k8s | v2.1 | app01_ml_llc | 31.0 | 0.000 | 108 | 0.000 | 0.000 | 0.000 | 1858 | - |
| container-k8s | v2.1 | app05_streaming | 0.000 | 0.000 | 6212 | 0.000 | 0.000 | 0.000 | 31.0 | - |
| container-k8s | v2.1 | app10_search | 17.0 | 0.000 | 2.0 | 0.000 | 1.0 | 0.000 | 2686 | - |
| container-k8s | v2.1 | app11_sort_net | 23.5 | 0.000 | 1274 | 0.000 | 0.000 | 0.000 | 70108 | - |
| container-k8s | v2.1 | app13_query_scan | 0.000 | 0.000 | 59.0 | 83.0 | 0.000 | 0.000 | 6.0 | - |
| container-k8s | v3.3 | app01_ml_llc | 31.0 | 0.000 | 110 | 0.000 | 0.000 | 0.000 | 1896 | 33.0 |
| container-k8s | v3.3 | app05_streaming | 0.000 | 0.000 | 6008 | 0.000 | 0.000 | 0.000 | 30.0 | 0.000 |
| container-k8s | v3.3 | app10_search | 17.0 | 0.000 | 2.0 | 0.000 | 1.0 | 0.000 | 2692 | 20.5 |
| container-k8s | v3.3 | app11_sort_net | 24.0 | 0.000 | 1402 | 0.000 | 0.000 | 0.000 | 42395 | 29858 |
| container-k8s | v3.3 | app13_query_scan | 0.000 | 0.000 | 64.0 | 81.5 | 0.000 | 0.000 | 7.0 | 1392 |
| vm-guest | v2.1 | app01_ml_llc | 87.5 | 0.000 | 12.0 | 0.000 | 0.000 | 0.000 | 2262 | - |
| vm-guest | v2.1 | app05_streaming | 0.000 | 0.000 | 79994 | 0.000 | 0.000 | 0.000 | 11.0 | - |
| vm-guest | v2.1 | app10_search | 50.0 | 0.000 | 4.0 | 0.000 | 0.000 | 0.000 | 2693 | - |
| vm-guest | v2.1 | app11_sort_net | 81.0 | 0.000 | 524 | 0.000 | 0.000 | 0.000 | 420921 | - |
| vm-guest | v2.1 | app13_query_scan | 0.000 | 0.000 | 1280 | 15.5 | 0.000 | 1.0 | 1.0 | - |
| vm-guest | v3.3 | app01_ml_llc | 88.5 | 0.000 | 13.0 | 0.000 | 0.000 | 0.000 | 2238 | 80.0 |
| vm-guest | v3.3 | app05_streaming | 0.000 | 0.000 | 75342 | 0.000 | 0.000 | 0.000 | 11.5 | 0.000 |
| vm-guest | v3.3 | app10_search | 50.0 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 2693 | 0.000 |
| vm-guest | v3.3 | app11_sort_net | 82.0 | 0.000 | 589 | 0.000 | 0.000 | 0.000 | 200201 | 0.000 |
| vm-guest | v3.3 | app13_query_scan | 0.000 | 0.000 | 1203 | 13.5 | 0.000 | 0.500 | 1.0 | 93.0 |


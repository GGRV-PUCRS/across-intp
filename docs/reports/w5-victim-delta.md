# W5 colocation victim-delta (pairwise − solo) — results/p2-15metric-xdeploy-1of3-w5 (1/3 footprint + hard CPU pinning; bare/container/vm-guest unified at the same baseline + correct 281600 MB/s ceiling; supersedes w5-vmguest.md)

Envs: bare, container, vm-guest. Variants: v2.1, v3.3. Pairs: 5. scipy: yes.

**Victim-delta = median(pairwise victim) − median(solo victim)** per metric. PRIMARY contention signals (should RISE under a noisy neighbour): `schedlat, psi_mem, psi_io, membw_est`. GUARDS (own-quota/steal, not contention): `schedthr, steal`. Significance = Mann-Whitney U (pairwise vs solo) + Cliff's δ, BH-FDR across the metric family per (env,variant,pair). Under colocation `cpu` is DIRECTIONAL not absolute (cgroup profiler vs system-wide GT — C29).

### v2.1 — bare  *(primary contention signals; Δ = pairwise − solo)*

| victim — vs aggressor | schedlat Δ (q,δ) | psi_mem Δ (q,δ) | psi_io Δ (q,δ) | membw_est Δ (q,δ) | cpu Δ (q,δ) | contention |
|---|---|---|---|---|---|---|
| app01_ml_llc — vs app05_membw | 7.5 (***,1.0) | 0.000 (n/a,0.000) | 0.000 (n/a,0.000) | 94.0 (***,0.965) | -7.5 (***,-1.0) | **schedlat+membw_est** ↑ / ⚠STARVING |
| app07_ordering — vs app05_membw | 0.000 (n.s.,0.083) | -4.5 (***,-1.0) | 0.000 (n.s.,-0.083) | -4.0 (n.s.,-0.229) | 0.000 (n/a,0.000) | psi_mem ↓ |
| app10_search — vs app05_membw | 0.000 (n/a,0.000) | 0.000 (n/a,0.000) | 0.000 (n/a,0.000) | 11.0 (***,1.0) | 0.000 (n/a,0.000) | **membw_est** ↑ |
| app11_sort_net — vs app05_membw | 4.0 (***,1.0) | 0.000 (n/a,0.000) | 0.000 (n/a,0.000) | 2231 (***,1.0) | 0.000 (n/a,0.000) | **schedlat+membw_est** ↑ |
| app13_query_scan — vs app05_membw | 0.000 (n/a,0.000) | 0.000 (n/a,0.000) | -9.0 (***,-1.0) | -11.5 (***,-0.965) | 0.000 (n.s.,0.250) | psi_io+membw_est ↓ |

### v2.1 — container  *(primary contention signals; Δ = pairwise − solo)*

| victim — vs aggressor | schedlat Δ (q,δ) | psi_mem Δ (q,δ) | psi_io Δ (q,δ) | membw_est Δ (q,δ) | cpu Δ (q,δ) | contention |
|---|---|---|---|---|---|---|
| app01_ml_llc — vs app05_membw | 7.0 (***,1.0) | 0.000 (n/a,0.000) | 0.000 (n/a,0.000) | 108 (***,1.0) | -7.0 (***,-1.0) | **schedlat+membw_est** ↑ / ⚠STARVING |
| app07_ordering — vs app05_membw | 0.000 (n.s.,0.083) | -4.0 (***,-0.847) | 0.000 (n.s.,-0.083) | 27.0 (**,0.778) | 0.000 (n/a,0.000) | **membw_est** ↑ / psi_mem ↓ |
| app10_search — vs app05_membw | 0.000 (n/a,0.000) | 0.000 (n/a,0.000) | 0.000 (n/a,0.000) | 11.0 (***,1.0) | 0.000 (n/a,0.000) | **membw_est** ↑ |
| app11_sort_net — vs app05_membw | 3.0 (***,1.0) | 0.000 (n/a,0.000) | 0.000 (n/a,0.000) | 3204 (***,1.0) | 0.000 (n/a,0.000) | **schedlat+membw_est** ↑ |
| app13_query_scan — vs app05_membw | 0.000 (n/a,0.000) | 0.000 (n/a,0.000) | -13.0 (***,-1.0) | 22.0 (**,0.799) | 2.0 (***,0.917) | **membw_est** ↑ / psi_io ↓ |

### v2.1 — vm-guest  *(primary contention signals; Δ = pairwise − solo)*

| victim — vs aggressor | schedlat Δ (q,δ) | psi_mem Δ (q,δ) | psi_io Δ (q,δ) | membw_est Δ (q,δ) | cpu Δ (q,δ) | contention |
|---|---|---|---|---|---|---|
| app01_ml_llc — vs app05_membw | 5.5 (***,1.0) | 0.000 (n/a,0.000) | 0.000 (n/a,0.000) | 2787 (***,1.0) | -5.0 (***,-1.0) | **schedlat+membw_est** ↑ / ⚠STARVING |
| app07_ordering — vs app05_membw | 1.0 (***,1.0) | 0.000 (n/a,0.000) | 0.000 (n/a,0.000) | -6460 (***,-1.0) | -1.0 (**,-0.583) | **schedlat** ↑ / membw_est ↓ / ⚠STARVING |
| app10_search — vs app05_membw | 0.000 (n/a,0.000) | 0.000 (n/a,0.000) | 0.000 (n/a,0.000) | 566 (***,1.0) | 0.000 (n/a,0.000) | **membw_est** ↑ |
| app11_sort_net — vs app05_membw | 0.000 (*,0.333) | 0.000 (n/a,0.000) | 0.000 (n/a,0.000) | 4899 (***,1.0) | 0.000 (n/a,0.000) | **membw_est** ↑ |
| app13_query_scan — vs app05_membw | 0.000 (n/a,0.000) | 0.000 (n/a,0.000) | 5.5 (**,0.833) | 39.5 (n.s.,0.181) | 1.0 (**,0.618) | **psi_io** ↑ |

### v3.3 — bare  *(primary contention signals; Δ = pairwise − solo)*

| victim — vs aggressor | schedlat Δ (q,δ) | psi_mem Δ (q,δ) | psi_io Δ (q,δ) | membw_est Δ (q,δ) | cpu Δ (q,δ) | contention |
|---|---|---|---|---|---|---|
| app01_ml_llc — vs app05_membw | 7.0 (***,1.0) | 0.000 (n/a,0.000) | 0.000 (n/a,0.000) | 99.5 (***,1.0) | -7.0 (***,-1.0) | **schedlat+membw_est** ↑ / ⚠STARVING |
| app07_ordering — vs app05_membw | 0.000 (n.s.,0.083) | -3.0 (**,-0.694) | 0.000 (n.s.,-0.083) | -3.0 (n.s.,-0.042) | 0.000 (n/a,0.000) | psi_mem ↓ |
| app10_search — vs app05_membw | 0.000 (n/a,0.000) | 0.000 (n/a,0.000) | 0.000 (n/a,0.000) | 11.0 (***,1.0) | 0.000 (n/a,0.000) | **membw_est** ↑ |
| app11_sort_net — vs app05_membw | 3.0 (***,1.0) | 0.000 (n/a,0.000) | 0.000 (n/a,0.000) | 1433 (***,1.0) | -1.0 (***,-1.0) | **schedlat+membw_est** ↑ / ⚠STARVING |
| app13_query_scan — vs app05_membw | 0.000 (n/a,0.000) | 0.000 (n/a,0.000) | -12.5 (***,-1.0) | 26.5 (***,1.0) | 1.0 (***,1.0) | **membw_est** ↑ / psi_io ↓ |

### v3.3 — container  *(primary contention signals; Δ = pairwise − solo)*

| victim — vs aggressor | schedlat Δ (q,δ) | psi_mem Δ (q,δ) | psi_io Δ (q,δ) | membw_est Δ (q,δ) | cpu Δ (q,δ) | contention |
|---|---|---|---|---|---|---|
| app01_ml_llc — vs app05_membw | 7.0 (***,1.0) | 0.000 (n/a,0.000) | 0.000 (n/a,0.000) | 110 (***,1.0) | -7.0 (***,-1.0) | **schedlat+membw_est** ↑ / ⚠STARVING |
| app07_ordering — vs app05_membw | 0.000 (n.s.,0.083) | -3.5 (***,-0.958) | 0.000 (n.s.,-0.083) | 17.0 (***,1.0) | 0.000 (n/a,0.000) | **membw_est** ↑ / psi_mem ↓ |
| app10_search — vs app05_membw | 0.000 (n/a,0.000) | 0.000 (n/a,0.000) | 0.000 (n/a,0.000) | 12.0 (***,1.0) | 0.000 (n/a,0.000) | **membw_est** ↑ |
| app11_sort_net — vs app05_membw | 4.0 (***,1.0) | 0.000 (n/a,0.000) | 0.000 (n/a,0.000) | 908 (***,1.0) | -1.0 (***,-0.667) | **schedlat+membw_est** ↑ / ⚠STARVING |
| app13_query_scan — vs app05_membw | 0.000 (n/a,0.000) | 0.000 (n/a,0.000) | -13.5 (***,-1.0) | 27.0 (***,1.0) | 1.0 (***,1.0) | **membw_est** ↑ / psi_io ↓ |

### v3.3 — vm-guest  *(primary contention signals; Δ = pairwise − solo)*

| victim — vs aggressor | schedlat Δ (q,δ) | psi_mem Δ (q,δ) | psi_io Δ (q,δ) | membw_est Δ (q,δ) | cpu Δ (q,δ) | contention |
|---|---|---|---|---|---|---|
| app01_ml_llc — vs app05_membw | 4.5 (***,1.0) | 0.000 (n/a,0.000) | 0.000 (n/a,0.000) | 3266 (***,1.0) | -5.0 (***,-1.0) | **schedlat+membw_est** ↑ / ⚠STARVING |
| app07_ordering — vs app05_membw | 1.0 (**,0.667) | 0.000 (n/a,0.000) | 0.000 (n/a,0.000) | -6188 (***,-1.0) | 0.000 (n/a,0.000) | **schedlat** ↑ / membw_est ↓ |
| app10_search — vs app05_membw | 0.000 (n/a,0.000) | 0.000 (n/a,0.000) | 0.000 (n/a,0.000) | 521 (***,1.0) | 0.000 (n.s.,-0.174) | **membw_est** ↑ |
| app11_sort_net — vs app05_membw | 0.000 (n.s.,0.083) | 0.000 (n/a,0.000) | 0.000 (n/a,0.000) | 5664 (***,1.0) | 0.000 (n/a,0.000) | **membw_est** ↑ |
| app13_query_scan — vs app05_membw | 0.000 (n/a,0.000) | 0.000 (n/a,0.000) | 8.5 (**,0.785) | 70.0 (n.s.,0.097) | 1.0 (n.s.,0.458) | **psi_io** ↑ |


_Machine-readable rows: results/p2-15metric-xdeploy-1of3-w5/w5-victim-delta.tsv (420 victim-delta cells)._

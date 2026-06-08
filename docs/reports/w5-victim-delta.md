# W5 colocation victim-delta (pairwise − solo) — results/intp-bench-20260605_130235

Envs: bare, container. Variants: v2.1, v3.3. Pairs: 5. scipy: yes.

> vm-guest colocation is reported separately in [w5-vmguest.md](w5-vmguest.md): two
> co-located KVM guests need a size-matched baseline (96 GiB each so both fit in host
> RAM), so its solo baseline differs from this bare/container run and the two are not
> merged into one table. The portable signals behave consistently across all three envs.

**Victim-delta = median(pairwise victim) − median(solo victim)** per metric. PRIMARY contention signals (should RISE under a noisy neighbour): `schedlat, psi_mem, psi_io, membw_est`. GUARDS (own-quota/steal, not contention): `schedthr, steal`. Significance = Mann-Whitney U (pairwise vs solo) + Cliff's δ, BH-FDR across the metric family per (env,variant,pair). Under colocation `cpu` is DIRECTIONAL not absolute (cgroup profiler vs system-wide GT — C29).

### v2.1 — bare  *(primary contention signals; Δ = pairwise − solo)*

| victim — vs aggressor | schedlat Δ (q,δ) | psi_mem Δ (q,δ) | psi_io Δ (q,δ) | membw_est Δ (q,δ) | cpu Δ (q,δ) | contention |
|---|---|---|---|---|---|---|
| app01_ml_llc — vs app05_membw | 7.5 (***,1.0) | 0.000 (n/a,0.000) | 0.000 (n/a,0.000) | 153 (***,1.0) | -7.5 (***,-1.0) | **schedlat+membw_est** ↑ / ⚠STARVING |
| app07_ordering — vs app05_membw | 0.000 (n/a,0.000) | 0.000 (n/a,0.000) | 0.000 (n/a,0.000) | 103 (***,1.0) | 0.000 (n/a,0.000) | **membw_est** ↑ |
| app10_search — vs app05_membw | 0.000 (n/a,0.000) | 0.000 (n/a,0.000) | 0.000 (n/a,0.000) | 6.5 (***,1.0) | 0.000 (n/a,0.000) | **membw_est** ↑ |
| app11_sort_net — vs app05_membw | 0.000 (n/a,0.000) | 0.000 (n/a,0.000) | 0.000 (n/a,0.000) | 146 (***,1.0) | -0.500 (*,-0.500) | **membw_est** ↑ |
| app13_query_scan — vs app05_membw | 0.000 (n/a,0.000) | 0.000 (n/a,0.000) | -5.5 (***,-0.948) | -9.0 (**,-0.729) | -1.0 (**,-0.625) | psi_io+membw_est ↓ |

### v2.1 — container  *(primary contention signals; Δ = pairwise − solo)*

| victim — vs aggressor | schedlat Δ (q,δ) | psi_mem Δ (q,δ) | psi_io Δ (q,δ) | membw_est Δ (q,δ) | cpu Δ (q,δ) | contention |
|---|---|---|---|---|---|---|
| app01_ml_llc — vs app05_membw | 7.0 (***,1.0) | 0.000 (n/a,0.000) | 0.000 (n/a,0.000) | 165 (***,1.0) | -7.5 (***,-1.0) | **schedlat+membw_est** ↑ / ⚠STARVING |
| app07_ordering — vs app05_membw | 0.000 (n/a,0.000) | 0.000 (n/a,0.000) | 0.000 (n/a,0.000) | 108 (***,1.0) | 0.000 (n/a,0.000) | **membw_est** ↑ |
| app10_search — vs app05_membw | 0.000 (n/a,0.000) | 0.000 (n/a,0.000) | 0.000 (n/a,0.000) | 5.0 (***,1.0) | 0.000 (n/a,0.000) | **membw_est** ↑ |
| app11_sort_net — vs app05_membw | 0.000 (n/a,0.000) | 0.000 (n/a,0.000) | 0.000 (n/a,0.000) | 160 (***,1.0) | -1.0 (***,-1.0) | **membw_est** ↑ |
| app13_query_scan — vs app05_membw | 0.000 (n/a,0.000) | 0.000 (n/a,0.000) | -7.5 (*,-0.542) | -8.5 (*,-0.646) | -1.0 (**,-0.625) | psi_io+membw_est ↓ |

### v3.3 — bare  *(primary contention signals; Δ = pairwise − solo)*

| victim — vs aggressor | schedlat Δ (q,δ) | psi_mem Δ (q,δ) | psi_io Δ (q,δ) | membw_est Δ (q,δ) | cpu Δ (q,δ) | contention |
|---|---|---|---|---|---|---|
| app01_ml_llc — vs app05_membw | 8.5 (***,1.0) | 0.000 (n/a,0.000) | 0.000 (n/a,0.000) | 169 (***,1.0) | -8.0 (***,-1.0) | **schedlat+membw_est** ↑ / ⚠STARVING |
| app07_ordering — vs app05_membw | 0.000 (n/a,0.000) | 0.000 (n/a,0.000) | 0.000 (n/a,0.000) | 107 (***,1.0) | 0.000 (n/a,0.000) | **membw_est** ↑ |
| app10_search — vs app05_membw | 0.000 (n/a,0.000) | 0.000 (n/a,0.000) | 0.000 (n/a,0.000) | 4.5 (***,1.0) | 0.000 (n/a,0.000) | **membw_est** ↑ |
| app11_sort_net — vs app05_membw | 0.000 (n/a,0.000) | 0.000 (n/a,0.000) | 0.000 (n/a,0.000) | 583 (***,1.0) | -1.0 (***,-0.917) | **membw_est** ↑ |
| app13_query_scan — vs app05_membw | 0.000 (n/a,0.000) | 0.000 (n/a,0.000) | -1.0 (n.s.,-0.479) | -22.0 (**,-0.760) | -1.0 (***,-0.875) | membw_est ↓ |

### v3.3 — container  *(primary contention signals; Δ = pairwise − solo)*

| victim — vs aggressor | schedlat Δ (q,δ) | psi_mem Δ (q,δ) | psi_io Δ (q,δ) | membw_est Δ (q,δ) | cpu Δ (q,δ) | contention |
|---|---|---|---|---|---|---|
| app01_ml_llc — vs app05_membw | 7.5 (***,1.0) | 0.000 (n/a,0.000) | 0.000 (n/a,0.000) | 160 (***,1.0) | -7.5 (***,-1.0) | **schedlat+membw_est** ↑ / ⚠STARVING |
| app07_ordering — vs app05_membw | 0.000 (n/a,0.000) | 0.000 (n/a,0.000) | 0.000 (n/a,0.000) | 112 (***,1.0) | 0.000 (n/a,0.000) | **membw_est** ↑ |
| app10_search — vs app05_membw | 0.000 (n/a,0.000) | 0.000 (n/a,0.000) | 0.000 (n/a,0.000) | 6.0 (***,1.0) | 0.000 (n/a,0.000) | **membw_est** ↑ |
| app11_sort_net — vs app05_membw | 0.000 (n/a,0.000) | 0.000 (n/a,0.000) | 0.000 (n/a,0.000) | 616 (***,1.0) | -1.0 (***,-1.0) | **membw_est** ↑ |
| app13_query_scan — vs app05_membw | 0.000 (n/a,0.000) | 0.000 (n/a,0.000) | -2.5 (**,-0.750) | -14.0 (***,-0.979) | -1.0 (**,-0.625) | psi_io+membw_est ↓ |


_Machine-readable rows: results/intp-bench-20260605_130235/w5-victim-delta.tsv (260 victim-delta cells)._

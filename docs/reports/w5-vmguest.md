# W5 colocation victim-delta (pairwise − solo) — results/vmg-w5-96g

Envs: vm-guest. Variants: v2.1, v3.3. Pairs: 5. scipy: yes.

**Victim-delta = median(pairwise victim) − median(solo victim)** per metric. PRIMARY contention signals (should RISE under a noisy neighbour): `schedlat, psi_mem, psi_io, membw_est`. GUARDS (own-quota/steal, not contention): `schedthr, steal`. Significance = Mann-Whitney U (pairwise vs solo) + Cliff's δ, BH-FDR across the metric family per (env,variant,pair). Under colocation `cpu` is DIRECTIONAL not absolute (cgroup profiler vs system-wide GT — C29).

### v2.1 — vm-guest  *(primary contention signals; Δ = pairwise − solo)*

| victim — vs aggressor | schedlat Δ (q,δ) | psi_mem Δ (q,δ) | psi_io Δ (q,δ) | membw_est Δ (q,δ) | cpu Δ (q,δ) | contention |
|---|---|---|---|---|---|---|
| app01_ml_llc — vs app05_membw | 4.5 (**,1.0) | 0.000 (n/a,0.000) | 0.000 (n/a,0.000) | 3115 (**,1.0) | -4.5 (**,-1.0) | **schedlat+membw_est** ↑ / ⚠STARVING |
| app07_ordering — vs app05_membw | 0.000 (n.s.,0.333) | 0.000 (n/a,0.000) | 0.000 (n/a,0.000) | -5128 (**,-1.0) | 0.000 (n.s.,-0.333) | membw_est ↓ |
| app10_search — vs app05_membw | 0.000 (n/a,0.000) | 0.000 (n/a,0.000) | 0.000 (n/a,0.000) | 363 (**,1.0) | 0.000 (n/a,0.000) | **membw_est** ↑ |
| app11_sort_net — vs app05_membw | 1.0 (*,0.667) | 0.000 (n/a,0.000) | 0.000 (n/a,0.000) | 4383 (**,1.0) | 0.000 (n/a,0.000) | **schedlat+membw_est** ↑ |
| app13_query_scan — vs app05_membw | 0.000 (n/a,0.000) | 0.000 (n/a,0.000) | 7.5 (*,1.0) | 276 (n.s.,0.500) | 1.0 (n.s.,0.583) | **psi_io** ↑ |

### v3.3 — vm-guest  *(primary contention signals; Δ = pairwise − solo)*

| victim — vs aggressor | schedlat Δ (q,δ) | psi_mem Δ (q,δ) | psi_io Δ (q,δ) | membw_est Δ (q,δ) | cpu Δ (q,δ) | contention |
|---|---|---|---|---|---|---|
| app01_ml_llc — vs app05_membw | 6.0 (**,1.0) | 0.000 (n/a,0.000) | 0.000 (n/a,0.000) | 3439 (**,1.0) | -5.5 (**,-1.0) | **schedlat+membw_est** ↑ / ⚠STARVING |
| app07_ordering — vs app05_membw | 0.000 (n.s.,0.000) | 0.000 (n.s.,0.167) | 0.000 (n.s.,0.167) | -5032 (*,-1.0) | 0.000 (n.s.,-0.306) | membw_est ↓ |
| app10_search — vs app05_membw | 0.000 (n/a,0.000) | 0.000 (n/a,0.000) | 0.000 (n/a,0.000) | 330 (**,1.0) | 0.000 (n.s.,-0.194) | **membw_est** ↑ |
| app11_sort_net — vs app05_membw | 1.0 (*,0.667) | 0.000 (n/a,0.000) | 0.000 (n/a,0.000) | 5518 (**,1.0) | 0.000 (n/a,0.000) | **schedlat+membw_est** ↑ |
| app13_query_scan — vs app05_membw | 0.000 (n/a,0.000) | 0.000 (n/a,0.000) | 7.0 (**,1.0) | 313 (**,1.0) | 2.2 (**,0.972) | **psi_io+membw_est** ↑ |


_Machine-readable rows: results/vmg-w5-96g/w5-victim-delta.tsv (115 victim-delta cells)._

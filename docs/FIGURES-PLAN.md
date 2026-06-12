# Figure plan — P2 (cross-deployment + portable) and P3 (IADA/regime) campaigns

Specification of the paper figure set, each figure tied to its **claim**, its
**data source** (campaign + file), and the **plot script** that renders it
(existing under `bench/plot/`, or the named gap). The Ready column tracks
whether the figure can be rendered from data banked today
(`results/p2-15metric-xdeploy-1of3`, snapshot 20260612T112030Z) or is blocked
by a queued campaign / the C34 v2.1 re-run.

Conventions: variant labels use the descriptive names (stap-legacy / hybrid-c
/ ebpf-agg …) per the canonical map, not bare vN tags; every figure that
aggregates reps carries the rep count and BH-FDR-corrected significance from
the analyzer TSVs (never recomputed in the plot layer).

## P2 §results — cross-deployment portability (banked Tier-A 1/3)

| id | Claim the figure carries | Data | Script | Ready |
|---|---|---|---|---|
| F1 | Containers preserve the canonical 7 (ratio≈1 in the W4 band); the VM boundary does not | `cross-deployment.tsv` (absolute rows: ratio + CI vs bare) | `plot-cross-environment.py` (omnibus/boxplots) — feed the analyzer TSV, facet env x metric | ready, EXCEPT v2.1 mbw cells (C34 re-run) |
| F2 | Claim-class taxonomy at a glance: absolute / directional / descriptive per metric x env | `cross-deployment.tsv` (claim_class + signif columns) | gap: small matrix/heatmap renderer (`plot-claim-class-matrix.py`) | ready (class structure unaffected by C34) |
| F3 | Availability matrix: what the VM destroys (mbw/llcocc -> `--`) vs what the portable set keeps | portable report §1 (re-derive from portable.tsv availability) | gap: availability-grid renderer (boolean heatmap, v2.1/v3.3 panels) | ready |
| F4 | membw_est is faithful (rho≈0.92 vs GT LLC misses), so the bandwidth dimension survives where RDT is absent | portable.tsv + groundtruth.tsv pairs (solo, traffic-gated) | gap: scatter+rho panel (`plot-portable-faithfulness.py`) | ready |
| F5 | PSI is bandwidth-blind (falsification): membw_est high while psi_mem flat, every env | portable report §3 cells (app05) | same script as F4 (second panel) | ready |
| F6 | Scheduling-regime pair: psp fires in solo under oversubscription (app16) and separates envs directionally; idle_preempt is eBPF-only | `cross-deployment.tsv` directional rows (psp, idle_preempt) | `plot-cross-environment.py` directional facet; verify psp y-scale (events/s, log) | ready |
| F7 | 15-metric fingerprint geometry: the added dimensions are non-redundant (PCA + correlation circle per variant) | per-rep portable.tsv vectors | `plot-pca-correlation-circle.py` + `plot_pca_dendro.py` (verify 15-col input) | ready, mbw axis caveat until C34 re-run |

## P2 §overhead — cadence sweep (queued campaign)

| id | Claim | Data | Script | Ready |
|---|---|---|---|---|
| F8 | Fidelity vs sampling cadence (frequency-response curve per metric class) + the cadence knee | cadence sweep dirs + `sweep-manifest.tsv` | `analyze-cadence.py` output -> gap: curve renderer (`plot-cadence-curves.py`) | blocked: campaign not run |
| F9 | Profiler overhead vs cadence (Volpert D) per variant | same sweep, overhead stage | same renderer, second panel | blocked: campaign not run |

## P2/P3 §colocation — W5 victim-delta (deferred campaign)

| id | Claim | Data | Script | Ready |
|---|---|---|---|---|
| F10 | Victim-delta forest plot: schedlat/psi_*/membw_est RISE under a noisy neighbour; schedthr/steal guards stay flat | W5 pairwise vs solo (same dir), analyzer `--w5` output | gap: forest/dot plot per (env, victim) (`plot-w5-victim-delta.py`) | blocked: W5 deferred; ALSO gated on D12 sync (C34) |
| F11 | The 7-metric fingerprint misses the contention the portable set sees in vm-guest (the P2 punchline) | W5 vm-guest leg | same script, vm-guest facet | blocked: same |

## P3 §realism — Tier-B/C real workloads (queued)

| id | Claim | Data | Script | Ready |
|---|---|---|---|---|
| F12 | Real-app 15-metric fingerprints (Redis/CloudSuite/DSB) are MIXED — single-resource-class labels do not apply | Tier-B/C campaign portable.tsv | `plot-intp-bench.py` radar/heatmap path (verify 15-col) | blocked: campaign not run |
| F13 | IADA tiered ablation 7 -> 13 -> 15 (IDI / classifier quality per tier) | IADA M1 runs (off-box) + ml-ablation | `bench/iada/plot-iada.py` + `ml-ablation.py` output | blocked: M1 campaign queued (env ready) |

## Cross-cutting blockers and order-of-operations

1. **C34 v2.1 re-run gates F1/F7 final renders** (mbw axis). Render
   everything else from the banked data now; re-render those two after the
   re-run replaces the v2.1 cells.
2. **mbw ceiling audit gates the re-run itself** (C34 open question): v3.3
   medians >100 mean the detected ceiling under-reads the machine ~6x; fix
   `intp-detect.sh`'s derivation (or re-derive empirically via a STREAM peak)
   first, otherwise F1's mbw panel saturates at the clamp.
3. The **figure-set dry run on banked data** (F1–F7) is the cheapest way to
   surface plot-layer gaps (axis scales, 15-column parsing, label maps)
   BEFORE the queued campaigns multiply the data volume — render first,
   queue second.
4. Gap scripts to add under `bench/plot/`: claim-class matrix (F2),
   availability grid (F3), portable-faithfulness panels (F4/F5), cadence
   curves (F8/F9), W5 forest (F10/F11). All consume analyzer outputs (TSV /
   report tables), never raw captures, so they stay cheap to re-render.

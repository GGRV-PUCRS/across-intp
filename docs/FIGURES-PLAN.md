# Figure plan — P2 (cross-deployment + portable) and P3 (IADA/regime) campaigns

Specification of the paper figure set, each figure tied to its **claim**, its
**data source** (campaign + file), and the **plot script** that renders it
(existing under `bench/plot/`, or the named gap). The Ready column tracks
whether the figure can be rendered from data banked today
(`results/p2-15metric-xdeploy-1of3`, the canonical campaign with the C34 v2.1
re-run merged in on 2026-06-13) or is blocked by a queued campaign.

Conventions: variant labels use the descriptive names (stap-legacy / hybrid-c
/ ebpf-agg …) per the canonical map, not bare vN tags; every figure that
aggregates reps carries the rep count and BH-FDR-corrected significance from
the analyzer TSVs (never recomputed in the plot layer).

## P2 §results — cross-deployment portability (banked Tier-A 1/3)

| id | Claim the figure carries | Data | Script | Ready |
|---|---|---|---|---|
| F1 | Containers preserve the canonical 7 (ratio≈1 in the W4 band); the VM boundary does not | `cross-deployment.tsv` (absolute rows: ratio + CI vs bare) | `plot-cross-environment.py` (omnibus/boxplots) — feed the analyzer TSV, facet env x metric | ready (C34 v2.1 re-run merged 2026-06-13) |
| F2 | Claim-class taxonomy at a glance: absolute / directional / descriptive per metric x env | `cross-deployment.tsv` (claim_class + signif columns) | gap: small matrix/heatmap renderer (`plot-claim-class-matrix.py`) | ready (class structure unaffected by C34) |
| F3 | Availability matrix: what the VM destroys (mbw/llcocc -> `--`) vs what the portable set keeps | portable report §1 (re-derive from portable.tsv availability) | gap: availability-grid renderer (boolean heatmap, v2.1/v3.3 panels) | ready |
| F4 | membw_est is faithful (rho≈0.92 vs GT LLC misses), so the bandwidth dimension survives where RDT is absent | portable.tsv + groundtruth.tsv pairs (solo, traffic-gated) | gap: scatter+rho panel (`plot-portable-faithfulness.py`) | ready |
| F5 | PSI is bandwidth-blind (falsification): membw_est high while psi_mem flat, every env | portable report §3 cells (app05) | same script as F4 (second panel) | ready |
| F6 | Scheduling-regime pair: psp fires in solo under oversubscription (app16) and separates envs directionally; idle_preempt is eBPF-only | `cross-deployment.tsv` directional rows (psp, idle_preempt) | `plot-cross-environment.py` directional facet; verify psp y-scale (events/s, log) | ready |
| F7 | 15-metric fingerprint geometry: the added dimensions are non-redundant (PCA + correlation circle per variant) | per-rep portable.tsv vectors | `plot-pca-correlation-circle.py` + `plot_pca_dendro.py` (verify 15-col input) | ready (C34 re-run merged; v3.3 mbw axis on pre-audit ceiling — x0.151, see report note) |

## P2 §overhead — cadence sweep (queued campaign)

| id | Claim | Data | Script | Ready |
|---|---|---|---|---|
| F8 | Fidelity vs sampling cadence (frequency-response curve per metric class) + the cadence knee | `cadence-fidelity.tsv` (analyzer `--tsv`) + `sweep-manifest.tsv` | `analyze-cadence.py` + `plot-cadence-curves.py` -> `F8-cadence-fidelity` (knee curves + density) and `F8-cadence-sensitivity` (per-metric max\|Δref\| heatmap), png+pdf | DONE (sweep 2026-06-15; knee: app05 psp -87% at 5s, app16 cache/membw ~-25%; steady metrics robust; density ~1/interval; v2.1≈v3.3) |
| F9 | Profiler overhead vs cadence (Volpert D) per variant | `overhead-vs-cadence.tsv` (analyzer) from the `--stages overhead --overhead-volpert` cadence sweep (`results/p2-cadence-overhead`, bare, arms baseline/v2.1/v3.3, refs cpu/stream/disk, 3 reps) | `analyze-cadence-overhead.py` → `F9-overhead-vs-cadence` (overhead% vs interval per variant), png+pdf | DONE (2026-06-17). Overhead ≤2.5%: cpu ref rises to ~1.8% at 0.1s, decays to ~0 at 5s (both variants); v3.3/eBPF carries a ~2% constant stream overhead; v2.1 lower. ref_disk excluded from the curve (I/O-variance-dominated ±7-9%), kept in the report table |

## P2/P3 §colocation — W5 victim-delta (run 2026-06-14, 1/3 footprint, all 3 envs)

| id | Claim | Data | Script | Ready |
|---|---|---|---|---|
| F10 | Victim-delta forest plot: schedlat/psi_*/membw_est RISE under a noisy neighbour; schedthr/steal guards stay flat | W5 pairwise vs solo (same dir), analyzer `--w5` output → `w5-victim-delta.tsv` (420 cells) | `plot-w5-victim-delta.py` → `F10-victim-delta-forest` (Cliff's δ per metric × env; v2.1●/v3.3■, filled=majority BH-FDR signif), png+pdf | DONE (2026-06-16). membw_est δ=+1 (signif) in all 3 envs; guards (schedthr/steal) ≈0 not-signif; canonical mbw/llcocc/psp move on host |
| F11 | The 7-metric fingerprint misses the contention the portable set sees in vm-guest (the P2 punchline) | W5 vm-guest leg (`w5-victim-delta.tsv`) | `plot-w5-victim-delta.py` → `F11-vmguest-portable-vs-canonical`, png+pdf | DONE (2026-06-16). vm-guest: mbw absent (RDT n/a) yet membw_est δ≈+1 signif — the portable proxy captures the memory-bandwidth contention the canonical RDT metric cannot see in the VM |

## P3 §realism — Tier-B/C real workloads (queued)

| id | Claim | Data | Script | Ready |
|---|---|---|---|---|
| F12 | Real-app 15-metric fingerprints (Redis/CloudSuite/DSB) are MIXED — single-resource-class labels do not apply | Tier-B/C `fingerprints.tsv` (analyzer `bench/analyze-tierb.py`); combined TSV `results/p2-realapps-combined/` (cat the two campaign TSVs) | `plot-tierb-fingerprint.py` → `F12-fingerprint` (class-grouped heatmap) + `F12-class-activation` (IADA 5-class ✓ matrix), 2×2 env×variant, png+pdf → `results/figures/p2-realapps-15metric/` | DONE (2026-06-16, all loads properly sized). **Every real app spans ≥2 IADA classes** — container·v3.3: redis=2 (net+cache), data-caching=4, in-memory-analytics=3, web-search=3 (cpu+mem+cache), DSB=4 (cpu+net+cache+mem); vm-guest DSB reaches 5 (adds disk via mongo). web-search + DSB were re-run at corrected loads (web-search Faban 128w/20-50ms; DSB wrk2 -R4000) after the defaults under-drove the 16-core third. **web-search vm-guest now runs in-guest** (the 14 GB Solr index was baked into the suites base qcow2; vm-guest scope fallback fixed by the slice pre-create, commit 16a1913 — verified fallback=0). No under-drive/N-A caveats remain |
| F13 | IADA classifier tiers T1/A/B (7-canonical / 7-proxy-swap / 15+regime): CV+transfer tables, per-tier scheduling IDI | tier campaign 2026-06-17 (`results/iada-trainsets`, `results/iada-sim`) + sim-experiment campaign 2026-08 (E1–E5, S8: `IADA-second-born/`) | `plot-iada-tier-table.py` (both tables) + `plot-iada-sim.py`; sim-experiment panels via `plot-sim-experiments.py` | DONE (3 figures in `p2-iada-tiers`); caveats: E2 shows B's IDI gap is ~39% the 6th multiplier; S8 rebank pending (B 5753→≈4402); see `bench/iada/DECISIONS-sim-experiments.md` |
| F14 | K-Means level-threshold map (Meyer 2021 Fig. 9 form): shipped vs 50k-retrained centroids on the level-defining metric, over the published utilization bands (C14/V5: bands unimplemented; retrained levels are tie-break artifacts) | `IADA-second-born/meyer-validation/kmeans-centers.tsv` | `bench/plot/plot-meyer-validation.py` → `results/figures/p2-meyer-validation/` | rendered 2026-08-12 |
| F15 | Degradation tables in IADA 2022 Fig. 6 form: fork (JSS empirical) vs paper (CCPE/JSA) multipliers by class × level (N1/E5/W2.3) | `Degradation.java` tables | `bench/plot/plot-meyer-validation.py` → `results/figures/p2-meyer-validation/` | rendered 2026-08-12 |

## Cross-cutting blockers and order-of-operations

1. **C34 v2.1 re-run — DONE (2026-06-13).** The re-run completed and was
   merged into the canonical campaign (`bench/merge-and-render-p2.sh`); F1/F7
   are re-rendered with corrected v2.1 mbw cells. No longer a blocker.
2. **mbw ceiling audit — CLOSED.** The 42 656 MB/s was intp-detect.sh's
   DDR4 fallback; the audited machine ceiling is 281 600 MB/s. The v2.1 re-run
   inherited the correct ceiling; banked v3.3 mbw absolute values carry the
   pre-audit ceiling (multiply by 0.151), flagged in the report ceiling note —
   within-variant ratios are ceiling-invariant.
3. The **figure-set dry run on banked data** (F1–F7) is the cheapest way to
   surface plot-layer gaps (axis scales, 15-column parsing, label maps)
   BEFORE the queued campaigns multiply the data volume — render first,
   queue second.
4. Gap scripts to add under `bench/plot/`: claim-class matrix (F2),
   availability grid (F3), portable-faithfulness panels (F4/F5), cadence
   curves (F8/F9), W5 forest (F10/F11). All consume analyzer outputs (TSV /
   report tables), never raw captures, so they stay cheap to re-render.

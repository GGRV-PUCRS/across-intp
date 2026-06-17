# IADA classifier tiers — cross-deployment comparison (F13, classifier axis)

The three IADA-classifier tiers, trained from our 15-metric campaign
micro-benchmarks (each stresses one resource → labelled per-class samples),
within-env 5-fold CV. Host = bare + container pooled; VM = vm-guest (where the
RDT metrics mbw/llcocc arrive as `--`/0).

| tier | schema | classes | mem level-metric | regime |
|---|---|---|---|---|
| **T1 canonical-7** | netp,nets,blk,mbw,llcmr,llcocc,cpu | 5 | `mbw` (RDT) | — |
| **A proxy-swap** | same 7, `membw_est` in the `mbw` slot | 5 | `membw_est` | — |
| **B full-15+regime** | all 15 metrics | 6 | membw_est + psi_mem | psp/idle_preempt |

## Result 1 — resource-CLASS identification is NOT the portability bottleneck

Within-env CV classification accuracy / macro-F1:

| tier | host acc | host F1 | VM acc | VM F1 |
|---|---|---|---|---|
| T1 | 1.000 | 1.000 | 0.998 | 0.999 |
| A  | 0.999 | 0.999 | 0.999 | 0.999 |
| B  | 1.000 | 1.000 | 1.000 | 1.000 |

All tiers identify the resource **class** near-perfectly in **both** envs —
including canonical-7 in the VM. Even with mbw/llcocc absent, the surviving
metrics (llcmr + cpu + netp/nets + blk) separate the single-resource
micro-benchmarks. So *which* resource a workload stresses is recoverable in the
VM regardless of tier; classification is not where the canonical set fails.

## Result 2 — the real gap is degradation-LEVEL / IDI estimation

IADA does not only name the class: per class it estimates a **level**
(low/mod/hig) from a fixed *level-column* metric (mem←`mbw`, cache←`llcocc`),
which indexes the empirical IDI degradation table that drives scheduling. In the
VM those RDT level-metrics are `--`/0, so **T1 can name the class but not its
severity** → the IDI lookup collapses to "absent/low" → wrong migration
decisions. **A** restores the mem level via `membw_est`; **B** restores mem via
`membw_est`+`psi_mem` and adds a scheduling-regime class. This is the axis where
the portable proxies matter — and it is invisible to the (saturated)
classification accuracy above. Quantifying it requires the CloudSim IDI/
scheduling simulation (next step).

## Result 3 — absolute proxy values are not cross-env comparable → retrain per domain

A host-trained classifier does **not** transfer to the VM: e.g. `membw_est` for
the same streaming stressor is ~7,200 on the host but ~77,000 in the guest
(~10×, different PMU/scope behaviour). A host→VM transfer test mislabels VM
samples (the proxy lands far outside the trained range). IADA's own M2 guard
already mandates per-domain retraining; the within-env CV above is the correct
usage, and the proxies work **within** each domain once retrained.

## Data-structure note

bare/container `portable.tsv` rows carry a leading wall-clock timestamp column
(16 fields vs the 15-name header); vm-guest rows do not (15 fields). The
converter (`campaign-to-trainsets.py`) drops the extra leading column per-row.

## Conclusion

The canonical-7's cross-deployment weakness is in **degradation-level / IDI**
estimation in the VM (mbw/llcocc gone), not class identification. The portable
proxies close that gap — minimally for mem (A), fully + regime (B). Next:
the CloudSim IDI simulation to score scheduling quality per tier.

## CloudSim IDI / scheduling simulation — the closed-loop result

The classifier axis above shows class ID is recoverable in the VM; this axis
asks the consequential question — **does the metric set change the scheduler's
decisions and the resulting interference?** We run the full IADA closed loop
(classifier → IDI degradation level → SA placement → migration) over our
campaign workloads turned into CloudSim cloudlet traces, in the VM condition
(host-trained `.rda` applied to vm-guest traces, where the RDT metrics read 0).
The SA scheduler is stochastic, so 5 reps/tier.

**Headline metric `idi_avg`** = interference + migration cost (IADA's own
metric); **lower = better placement**. Mean ± SD over 5 reps, VM condition:

| classifier tier | idi_avg (VM) | migrations | vs canonical |
|---|---|---|---|
| Canonical 7-metric (RDT, baseline) | 5958 ± 74 | 14 ± 4 | — |
| Proxy-swap (membw_est → mem slot) | **3410 ± 34** | 19 ± 9 | **−43% IDI** |

**The portable proxy yields 43% lower interference-degradation in the VM.**
Canonical-7's `mbw` reads 0 in the guest, so the scheduler under-estimates the
memory contention and co-locates memory-heavy containers; the proxy (`membw_est`)
restores that signal, so the scheduler separates them — it migrates a little more
(acting on contention it can now *see*) but ends at far lower interference. This
is the scheduling-level payoff of the portable metrics, and it is exactly the gap
the saturated classification accuracy could not show.
Figure: `results/figures/p2-iada-tiers/F13-tier-scheduling-idi.{png,pdf}`.

CloudSim was retargeted from the paper's 7200-sample / 96-host config to our
120-sample traces + a 12-host cluster (`bench/iada/patches/cloudsim-small-cluster-sim.patch`):
`NUMBER_HOSTS/VMS`→12, container list sized to the loaded cloudlets,
deterministic cross-tier cloudlet ordering, and `InterferenceClassifier`'s
placement horizon retargeted to 120 samples.

**Approach B (full-15 + regime) in the sim** additionally needs the CloudSim Java
widened end-to-end (`Interference.java`/`MLClassifier.java` 7→15 features, a 6th
`regime` class in `MLCResult`/`Degradation.java` with a W5-calibrated IDI table,
and 15-column traces through `convert-profiler-to-meyer.py`/`generate-iada-tree.py`).
B's *classification* is already covered above; its sim is an incremental
"does the full set beat the single mem proxy for scheduling" question.

_Artifacts: `bench/iada/scripts/campaign-to-trainsets.py`,
`bench/iada/scripts/eval-tiers.R`, `bench/plot/plot-iada-tier-table.py`,
`results/iada-trainsets/tier-eval{,-transfer}.tsv`,
`results/iada-tier-rda/{T1,A}/`._

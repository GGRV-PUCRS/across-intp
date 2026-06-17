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
proxies close that gap — minimally for mem (A), fully + regime (B). The CloudSim
IDI simulation below scores this scheduling-quality gap per tier.

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

| Interference-classifier tier | idi_avg (VM, 5 reps) | vs canonical | regime class |
|---|---|---|---|
| Canonical 7-metric (RDT baseline) | 6400 ± 179 | — | — (mislabels oversub as *mem*) |
| Proxy-swap (membw_est → mem slot) | **3622 ± 154** | **−43%** | — |
| Full 15-metric (+ regime class) | 5753 ± 534 | −10% | **yes — oversub → *regime*** |

**(1) The like-for-like comparison is T1 vs A** — the same 5-class interference
model, differing only in the memory metric the classifier can see. In the VM,
canonical-7's `mbw` reads 0, so the scheduler under-estimates memory contention and
co-locates memory-heavy containers; the portable proxy (`membw_est`) restores that
signal and cuts the interference-degradation index **43%** (A migrates a little
more — acting on contention it can now *see* — but ends far lower). This is the
scheduling-level payoff the saturated classification accuracy could not show.

**(2) Full-15 (B) adds a dimension the canonical fingerprint cannot represent.**
B carries a 6th *oversubscription-regime* class. Verified end-to-end, B classifies
the oversubscription workload (app16) as `regime` at 100%, whereas T1 mislabels it
as `mem` (76%) and A likewise has no regime class. B's IDI is **not magnitude-
comparable** to T1/A — it includes an extra `regime` degradation factor (a 6-term
cost vs 5) — so the meaningful reading is that B stays **10% below canonical
*while additionally* accounting for interference the others are structurally blind
to. The regime IDI table is calibrated from the W5 victim-delta study
(`Degradation.getRegime` abs/low/mod/hig = 1.00/1.20/1.55/1.95 — regime contention
saturates, Cliff's |δ|→1 for the schedlat/membw_est primaries).
Figure: `results/figures/p2-iada-tiers/F13-tier-scheduling-idi.{png,pdf}`.

**CloudSim changes (saved as patches under `bench/iada/patches/`).** Retargeted
from the paper's 7200-sample / 96-host config to our 120-sample traces + a 12-host
cluster (`cloudsim-small-cluster-sim.patch`): `NUMBER_HOSTS/VMS`→12, container list
sized to the loaded cloudlets, deterministic cross-tier cloudlet order, and
`InterferenceClassifier`'s horizon retargeted to 120 samples. For B, the classifier
was made **generic over feature width** — `MLClassifier` builds its frame from the
training frame's column names (7 for T1/A, 15 for B), which also removed a latent
netp/nets inference swap — and B's own tier-dir R was widened (`svm.R`/`kmeans.R`:
6 classes, `[,1:15]`, VM-robust level columns mem→`membw_est`, cache→`llcmr`,
regime→`schedlat`), with `retrain.R` gaining a `--tier B` mode and a
`predict.kmeans` NA-safety fix (saturated level columns no longer crash the
classifier — this also recovered the host condition). Traces are emitted unclamped
(`--no-clamp`) so the absolute proxy magnitudes survive into the sim.

_Artifacts: `bench/iada/scripts/{campaign-to-trainsets.py,eval-tiers.R,
run-tier-sims.sh,run-tier-sim-reps.sh}`, `bench/plot/{plot-iada-tier-table.py,
plot-iada-sim.py}`, `bench/iada/patches/{cloudsim-small-cluster-sim,cloudsim-tier-b-15metric-regime}.patch`
(the retrain.R quantile-breaks robustness fix is folded into the tier-b patch),
`bench/iada/tier-b-R/` (B's widened inference R), `results/iada-trainsets/
tier-eval{,-transfer}.tsv`, `results/iada-sim/tier-sim-reps.tsv`,
`results/iada-tier-rda/{T1,A,B}/`._

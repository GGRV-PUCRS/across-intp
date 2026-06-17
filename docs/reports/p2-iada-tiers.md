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

## CloudSim IDI / scheduling simulation — status

The classifier axis above (within-env CV + host→VM transfer) is the F13 headline.
The closed-loop **IDI/scheduling** axis (does better classification → better
placement?) is staged but is a larger integration:

- **Done:** CloudSim compiled + the bundled baseline sim runs end-to-end (JRI
  bridge, no segfault). The drop-in tiers' classifiers are retrained from our
  campaign data — `results/iada-tier-rda/{T1,A}/` (6 `.rda` each: svm_model +
  cpuk/memk/diskk/netk/cachek), 5-class/7-feature, vendorable via `INTP_R_FOLDER`.
  A robustness patch (`bench/iada/patches/retrain-robust-quantile-breaks.patch`)
  lets `retrain.R` handle zero-skewed level columns in real captures.
- **Remaining (the heavy part):**
  1. Convert our campaign workloads into CloudSim cloudlet traces (an iada-tree
     `source/` of per-cloudlet CSVs) in the VM condition (RDT→0) — so the sim
     classifies VM-style inputs where the tiers actually diverge. T1/A are 7-col
     (drop-in); the bundled host traces don't discriminate the tiers (no VM
     condition), so our VM traces are required.
  2. **Approach B** needs the CloudSim Java widened (`MLClassifier`/`Interference.java`
     7→15 features, `int`→`double`, the regime class) + a fresh IDI calibration
     in `Degradation.java` — grounded in our **W5 victim-delta** measurements.
  3. Run the SA scheduler per tier → parse idi_avg/sum/max, migrations,
     interference (`parse-cloudsim-output.py`) → the per-tier scheduling table.

_Artifacts: `bench/iada/scripts/campaign-to-trainsets.py`,
`bench/iada/scripts/eval-tiers.R`, `bench/plot/plot-iada-tier-table.py`,
`results/iada-trainsets/tier-eval{,-transfer}.tsv`,
`results/iada-tier-rda/{T1,A}/`._

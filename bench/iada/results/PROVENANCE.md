# PROVENANCE — 2026-08 simulation campaign (frozen 2026-08-12)

Everything under `results/` is gitignored by design; this manifest freezes what
the campaign actually consisted of so the numbers in the reports and in
`DECISIONS-sim-experiments.md` can be traced to immutable artifacts.

- **Simulator source**: `CloudSimInterference` tag **`campaign-2026-08`**
  (= commit `e49fb46`, branch `feat/approach-b-15metric`, pushed to ggrv-intp).
- **Build**: `javac --release 8` (class file major 52), tree
  `CloudSimInterference-rel8`; bit-compatible with the banked Eclipse `bin/`.
  A JDK-17 (major 61) build was shown equivalent (S2, 20-rep confirmation).
- **JVM**: OpenJDK 17 (`java-17-openjdk-amd64`), flags per `~/.iada-env` +
  per-arm `IADA_JAVA_EXTRA`.
- **R stack**: R version 4.3.3 (2024-02-29) -- "Angel Food Cake"; e1071 1.7.17 ; rJava 1.0.18 ; fossil 0.4.0 ;
- **Traces**: `/tmp/tree-{T1,A,B}-vm-guest` regenerated from
  `results/p2-15metric-xdeploy-1of3` (28 CSVs × 120 rows each; B = 15 cols).
- **Classifiers**: `results/iada-tier-rda/{T1,A,B}` (June 17 retrain) and
  `B-psp` (S8 re-key; patch in `bench/iada/patches/s8-regime-psp-rekey.patch`).
- **Raw outputs**: `~/Desktop/intpismo/IADA-second-born/` (owner-versioned).

## TSV inventory (sha256 first 16 hex; rows exclude header)

| file | rows | sha256 |
|---|---|---|
| `ab-run-20260811/confirm-T1-java8.tsv` | 20 | `546951f5aa654e00…` |
| `ab-run-20260811/confirm-T1-jdk17.tsv` | 20 | `c59d19169296a95b…` |
| `ab-run-20260811/reps-java8.tsv` | 30 | `ab37c0ca5b0447b2…` |
| `ab-run-20260811/reps-jdk17.tsv` | 30 | `d2df22665f688759…` |
| `sim-experiments-20260811/e1-startup-0.tsv` | 30 | `14663a2e88dbc0d5…` |
| `sim-experiments-20260811/e1-startup-10.tsv` | 30 | `8e7b7bb79a87302c…` |
| `sim-experiments-20260811/e1-startup-50.tsv` | 30 | `9552e2b746d97868…` |
| `sim-experiments-20260811/e2-regime-off.tsv` | 10 | `b003a508a46543c7…` |
| `sim-experiments-20260811/e3-hosts-14.tsv` | 30 | `5d96a2c1e90afb55…` |
| `sim-experiments-20260811/e3-hosts-19.tsv` | 30 | `56f32f388b055468…` |
| `sim-experiments-20260811/e3-hosts-23.tsv` | 30 | `654f04893ca6cffa…` |
| `sim-experiments-20260811/e3-hosts-28.tsv` | 30 | `a91f22f704779739…` |
| `sim-experiments-20260811/e3-hosts-9.tsv` | 30 | `5b6462a93554d77a…` |
| `sim-experiments-20260811/e4-ramp-convex.tsv` | 10 | `c6409145b21f2c7a…` |
| `sim-experiments-20260811/e4-ramp-measured.tsv` | 10 | `2551506f83292b70…` |
| `sim-experiments-20260811/e4-ramp-step.tsv` | 10 | `a3f7e9ebb94da41a…` |
| `sim-experiments-20260811/e5-degtable-paper.tsv` | 30 | `782ce758ca50e6a5…` |
| `sim-experiments-20260811/gate-default.tsv` | 30 | `752a85b612caa16c…` |
| `sim-experiments-20260811/s8-bpsp-default-b.tsv` | 10 | `080385ecc0326424…` |
| `sim-experiments-20260811/s8-bpsp-default.tsv` | 20 | `44d38030874cb98c…` |
| `sim-experiments-20260811/s8-bpsp-degtable-paper.tsv` | 10 | `d4795c7f2276938f…` |
| `sim-experiments-20260811/s8-bpsp-ramp-measured.tsv` | 10 | `d05985e547fc3189…` |
| `sim-experiments-20260811/s8-bpsp-ramp-step.tsv` | 10 | `f3a511567ea9e95c…` |

## Classifier directory digests (order-stable over *.rda + *.R contents)

| dir | models | digest |
|---|---|---|
| `iada-tier-rda/T1` | 6 .rda | `c5a79fd50fc7129b…` |
| `iada-tier-rda/A` | 6 .rda | `f270f6fd300ce2c1…` |
| `iada-tier-rda/B` | 7 .rda | `50807c1048c3756a…` |
| `iada-tier-rda/B-psp` | 7 .rda | `4bb1dc085b1b6102…` |

Regenerate the digests with the inline python in `git log` for this file's
commit, or ad hoc: sha256 over name+bytes of sorted `*.rda`+`*.R` per dir.

## Meyer-validation leg (W2, frozen 2026-08-12 — CONFORMANCE.md §5)

- **Simulator source**: `campaign-2026-08` + `16ba42b` (`iada.simLimit` flag,
  default unchanged), rebuilt `--release 8` (major 52) in the main checkout.
- **Traces**: Meyer's published 12 (`interference-classifier/source/`,
  3 apps × 4 patterns, 281–1080 rows), laid out by
  `bench/iada/scripts/meyer-traces-to-tree.py`; horizon/simLimit 280.
- **Classifier arms**: fork `R/` as shipped; `meyer-validation/rda-50k/`
  (retrain.R --seed 42 on `interference-classifier/training_dataset/`).
- **Runner scripts + shims**: `meyer-validation/run-{svm-accuracy,kmeans-rindex,retrain-cv}.R`
  (deviations documented in each header), `bench/iada/scripts/run-meyer-validation.sh`.

| file | rows | sha256 |
|---|---|---|
| `meyer-validation/meyer-sim-reps.tsv` | 70 | `93c33119db026c30…` |
| `meyer-validation/meyer-scripts-output.txt` | 40 | `1ca2922fc9fbd676…` |
| `meyer-validation/retrain-cv-output.txt` | 58 | `efb201c495d1e4e7…` |
| `meyer-validation/retrain-artifacts-output.txt` | 31 | `afb12a489eb7c46e…` |
| `meyer-validation/rda-50k/cachek.rda` | — | `cd254bba214cd9ad…` |
| `meyer-validation/rda-50k/cpuk.rda` | — | `ee722a1c1ad95921…` |
| `meyer-validation/rda-50k/diskk.rda` | — | `cdc91044f981b807…` |
| `meyer-validation/rda-50k/memk.rda` | — | `90a069b2f6fab3ef…` |
| `meyer-validation/rda-50k/netk.rda` | — | `990bae6da842bfb5…` |
| `meyer-validation/rda-50k/svm_model.rda` | — | `a9b8c91ca2bbac1b…` |

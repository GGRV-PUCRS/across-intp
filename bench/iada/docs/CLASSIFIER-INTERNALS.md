# IADA Classifier — internals reference

> For **conformance claims** (what the papers say vs what the code does),
> [`../CONFORMANCE.md`](../CONFORMANCE.md) is authoritative and supersedes
> this file; this file remains the internals snapshot.

Snapshot of how the **CloudSimInterference** fork (ggrv-intp branch
`master` at the time of writing) loads and uses the shipped
classifier, captured to anchor the sanity-check + retrain pipelines
in `bench/iada/`.

This document is descriptive. The authoritative behaviour is in the
fork's own source. If a future inspection diverges from what's
written here, treat the fork as the source of truth and update this
file.

---

## 1. Files in the fork's `R/` directory

The classifier ships as **six binary R artifacts** plus a small set of
source files. All paths below are relative to `<CLOUDSIM_REPO>/R/`.

| File              | Type     | Role                                                                       |
| ----------------- | -------- | -------------------------------------------------------------------------- |
| `svm_model.rda`   | binary   | Pre-trained `e1071::svm` C-classification model (polynomial kernel, ν=0.10). |
| `cpuk.rda`        | binary   | K-Means model (3 centers) for the **cpu** class.                           |
| `memk.rda`        | binary   | K-Means model (3 centers) for the **mem** class.                           |
| `diskk.rda`       | binary   | K-Means model (3 centers) for the **disk** class.                          |
| `netk.rda`        | binary   | K-Means model (3 centers) for the **net** class.                           |
| `cachek.rda`      | binary   | K-Means model (3 centers) for the **cache** class.                         |
| `input_dataset.R` | source   | Loads `forced/*.csv` into the 7-feature + category data frame.             |
| `svm.R`           | source   | Trains (`firstTime==0`) or loads (`firstTime==1`) `svm_model.rda`.         |
| `kmeans.R`        | source   | Trains or loads the per-class K-Means models; defines `predict.kmeans`.    |
| `forced/`         | dir      | Per-class training CSVs (~500 rows/class; **not** the Meyer 2021 paper's 50k Node-Tiers set — zero row overlap; finding F4 in [`../CONFORMANCE.md`](../CONFORMANCE.md)). |

The five class names used end-to-end are **`cpu`, `mem`, `disk`,
`net`, `cache`**. Note the abbreviations: this is the exact label set
emitted by `input_dataset.R` and consumed by `svm.R`/`kmeans.R`. Any
new pipeline must preserve these names.

---

## 2. Feature schema (7 columns)

The training CSVs under `R/forced/` and the runtime input to
`MLClassifier.java` use the same 7-column schema. There are no
headers; the separator is `;`.

| Column index | Name      | Units (paper)               |
| -----------: | --------- | --------------------------- |
| 1            | `netp`    | network packets             |
| 2            | `nets`    | network bytes               |
| 3            | `blk`     | block I/O bytes/ops         |
| 4            | `mbw`     | memory bandwidth            |
| 5            | `llcmr`   | last-level cache misses     |
| 6            | `llcocc`  | last-level cache occupancy  |
| 7            | `cpu`     | CPU utilisation             |

> **Quirk (fixed in the classification path, 2026-08)**: upstream
> `MLClassifier.java` constructed the at-classification-time data frame
> using the column ordering `(nets, netp, blk, mbw, llcmr, llcocc,
> cpu)`, i.e. `nets`/`netp` swapped relative to the training order in
> `input_dataset.R` (`netp, nets, blk, …`) — a long-standing upstream
> bug. Since `a24fe55` the classification path derives column names
> from the loaded training frame (`feat_cols <- setdiff(names(total),
> "category")`), which removes the swap for classification. The swapped
> header survives only in the (never-executed) OCPD path
> `getIntervalsOCPM` (see F1 in [`../CONFORMANCE.md`](../CONFORMANCE.md)).

---

## 3. Training dataset (`R/forced/`)

Files (each ~500 rows × 7 cols, `;`-separated, no header):

```
cache100.csv     → category = "cache"
cache_miss.csv   → category = "miss" (loaded but excluded from rbind)
memory100.csv    → category = "mem"
cpu100.csv       → category = "cpu"
disk100.csv      → category = "disk"
net100.csv       → category = "net"
```

`input_dataset.R` builds the training frame as:
`total <- rbind(cpu, mem, disk, net, cache)` — `cache_miss` is loaded
but **excluded** from the rbind. Note this is a **fork divergence, not
upstream intent**: the published classifier's `input_dataset.R`
(`interference-classifier` repo) rbinds `cache_miss` as a sixth class
labelled `miss` (finding F4, [`../CONFORMANCE.md`](../CONFORMANCE.md)).
The retrain pipeline mirrors the fork's 5-class behaviour by default.

---

## 4. Hyperparameters baked into the shipped models

These are read out of `R/svm.R` and `R/kmeans.R` and must be
reproduced by any retrain pipeline that aims for drop-in
compatibility:

- **SVM** (`e1071::svm`):
  - `type = 'C-classification'`
  - `kernel = "polynomial"`
  - `nu = 0.10`  *(passed even though `nu` is meaningful only for
    nu-classification; preserved verbatim to avoid behavioural drift)*
  - `scale = TRUE`
  - formula: `category ~ .`

- **K-Means** (`stats::kmeans`), one per class:
  - `centers = 3`
  - `nstart = 20`
  - input: the 7 feature columns for samples of that class only

- **Level mapping** (`predict.kmeans` in `R/kmeans.R`):
  per-class "which centroid is hig/mod/low" is decided by the
  centroid's value on a fixed feature column:
  - cpu → column 7 (cpu)
  - mem → column 4 (mbw)
  - disk → column 3 (blk)
  - net → column 1 (netp)
  - cache → column 6 (llcocc)

Output of `predict_<class>.kmeans` is one of `"low"`, `"mod"`, `"hig"`.

---

## 5. How `MLClassifier.java` loads the artifacts

The Java side **already supports** `INTP_R_FOLDER` /
`INTP_R_LIBPATHS` env-var overrides (verified in the ggrv-intp fork's
`master` at the time of writing).

```
String envFolder    = System.getenv("INTP_R_FOLDER");
String envLibPaths  = System.getenv("INTP_R_LIBPATHS");
if (envFolder != null && !envFolder.isEmpty()) {
    project_folder = envFolder.endsWith("/") ? envFolder : envFolder + "/";
    if (envLibPaths != null && !envLibPaths.isEmpty()) {
        re.eval(".libPaths('" + envLibPaths + "')");
    }
}
```

The path is then used as the prefix for every `.rda` `load()` and
every `source()` of the support `.R` files. **No code change is
required in the fork to swap in domain-retrained models — just
overwrite the six `.rda` files in `R/` and restart CloudSim.**

The runtime flag `firstTime` (and its sibling `firstTimeK`) defaults
to `1` in the constructor, which means CloudSim **uses the saved
`.rda` files** rather than retraining on every simulation. Retraining
is intentionally a separate operation; the new `R/retrain.R` in the
fork's `retrain-pipeline` branch is the supported way to regenerate
the six `.rda` files for a new domain.

---

## 6. Sanity check (overview)

The `bench/iada/scripts/sanity-check-classifier.sh` script picks N
profiles from a `<iada-tree>/<variant>/<env>/source/` directory,
classifies each one through the shipped SVM + K-Means models, and
compares the predicted class against a class **expected from the
workload name** (e.g. `cpu_solo_*` → `cpu`).

A `mismatch` rate above `--fail-threshold-pct` (default 30%) hard-
fails the wrapper, with an explicit suggestion to either retrain
(`R/retrain.R`) or rerun under `MODALITY=M1` if the failure came from
an unsupported env (bare/vm).

The script reads the six `.rda` files via the same conventions
described above — same path, same names. The TSV it writes lives in
`<campaign-dir>/sanity/<variant>__<env>.tsv` with columns:

```
workload  expected_class  predicted_class  predicted_level  plausibility
```

where `plausibility ∈ {match, mismatch, unknown}`.

---

## 7. Retraining for a new domain

See `R/RETRAIN.md` in the **CloudSimInterference** fork, branch
`retrain-pipeline`, for the full operating manual. In summary:

```bash
cd <CLOUDSIM_REPO>
Rscript R/retrain.R \
    --dataset-root <path-to-domain-dataset> \
    --output-dir   R/
```

The dataset root must contain per-class subdirectories — `cpu/`,
`memory/`, `disk/`, `network/`, `cache/` — each with one or more
Meyer-format CSVs (the legacy `forced/cpu100.csv` layout is also
accepted automatically). The script overwrites the six `.rda` files
in `--output-dir`; the existing files are backed up with a timestamp
suffix beforehand.

Retraining is the **recommended path** before running an M2 campaign
(`MODALITY=M2`, env != container). Without retraining, M2 results are
methodologically interpretable only as a domain-transfer ablation —
see `iada-campaign.md §"Methodological framing"`.

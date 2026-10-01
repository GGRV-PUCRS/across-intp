# bench/plot -- Plotting and post-processing scripts

Standalone Python scripts that consume the artefacts produced by the
bench and campaign runners: `bench/run-intp-bench.sh`,
`run-big-batch.sh` (repo root), and `bench/hibench/run-hibench-subset.sh`
for the Paper-1 set; the cross-deployment, cadence-sweep, colocation,
and IADA simulation drivers for the P2 set. Use them when you want to
re-plot an existing campaign without re-running the workload — for
example when iterating on figure styling, regenerating a single panel,
or analysing an archived `results/` snapshot from another host.

Two drivers invoke parts of this set automatically:
`run-big-batch.sh` (repo root) renders the Paper-1 stress-ng/HiBench
segment (`plot-intp-bench.py`, `extract-fragility.py`,
`quality-flags.py`, `plot-pca-correlation-circle.py`,
`plot-hibench.py`, `cross-variant-correlation.py`, chaining
`plot-cross-environment.py` when a campaign spans >= 2 envs), and
`bench/merge-and-render-p2.sh` pulls and re-renders the canonical P2
cross-deployment campaign (the analyzers plus `plot-p2-15metric.py`).
A third driver, **`bench/render-jsa-paper-figures.sh`** (repo `bench/`, one
level up), is the canonical way to reproduce the 17 JSA paper figure PDFs
from the consolidated archive:

```
bench/render-jsa-paper-figures.sh [DATA_ROOT] [OUT_DIR]
# defaults: $HOME/IntP-JSA-consolidated-data  $HOME/paper/figs
```

It treats the archive as read-only (derived TSVs — `cross-deployment
-tagged.tsv`, `w5-victim-delta-tagged.tsv`, `aggregate-means.tsv`,
`fingerprints-tagged.tsv` — are regenerated inside `cp -rs` symlink farms
under `/tmp`), invokes the JSA renderers below (`plot-fig2-3-4-6-8-jsa.py`,
`plot-fig-arch.py`, `plot-cadence-curves.py --jsa-merged`,
`analyze-cadence-overhead.py --jsa-style`, `plot-fig-pipeline.py`,
`plot-fig6-v2-jsa.py`, `plot-fig9-a3-jsa.py`, `plot-fig11-fig12-jsa.py`,
`plot-tierb-fingerprint.py`), renames the `Figure_N.pdf` outputs to the
paper's `fig_*.pdf` names, and renders the per-variant fingerprints
`fig_fingerprint_v33.pdf` (main text) and `fig_fingerprint_v21_prefix.pdf`
(appendix, C38 pre-fix cells hatched) with `plot-tierb-fingerprint.py
--variants ... --pdf ...` (the paper's `fig_fingerprint.pdf` is still the
combined F12 render). **`crop-fig14-fingerprint.py` is obsolete since v0.2.1**
(DECISIONS.md D17): it cut the combined render into halves, and the v3.3 half
carried no workload labels. It is kept for the v0.2.0 figures only. It validates each regenerated TSV against the old-name
reference tree under `~/results/` (reference is never pipeline input) and
prints a per-figure checklist. Every other script — the P2 cadence / W5 /
IADA figures, the seminar figure, and the utilities — is run standalone.
This guide covers the **standalone** invocation flow.

## How the figures are named

Every renderer writes its output through
[`fig_names.py`](fig_names.py), which turns the figure's internal stem into a
filename a person can read outside this repository:

```
F1-absolute-metric-ratio-versus-bare-metal--tier-a-cross-deployment.png
^^                    ^^                              ^^
figure number,        what the figure shows           which measurement
as the reports cite it                                campaign produced it
```

The **figure number** is the anchor `docs/FIGURES-PLAN.md`, the reports under
`docs/reports/` and the paper drafts cite (`F0`–`F15` for the cross-deployment
and IADA work, `fig00`–`fig14` for the SBAC-PAD set); a figure the pipeline
never numbered starts with its description instead. The **campaign tag** comes
from the tree the renderer was pointed at — every script takes `--dataset TAG`
to override it, which is how `render-sa-figures.py` names the whole Seminario
cut after the document rather than after the seven trees it draws from.

The stem stays the internal key: it selects the printed geometry in
`paper_style` / `sa_style` and the description in `fig_names.FIGURES`. Adding a
figure means adding its stem there — an unregistered stem raises rather than
falling back to itself, so a new figure cannot quietly ship under a name only
its author can read.

## Contents

| Script | Input | Output | Use when |
|---|---|---|---|
| `plot-intp-bench.py`        | a `bench-full/` directory (one campaign) | `<input>/plots/{png,pdf}/fig00-…fig14-*` + `aggregate-means.csv` | re-rendering the cross-variant figure set (fig00 - fig14, plus fig01b / fig04b / fig04c) from solo / pairwise / overhead / timeseries data |
| `plot-hibench.py`           | a `hibench/` directory (one or more workload sweeps) | `<input>/plots/{png,pdf}/fig00-…fig12-*` | rendering the HiBench-specific resource-family figures |
| `plot-pca-correlation-circle.py` | an `aggregate-means.{tsv,csv}` from a single campaign | `fig_pca_correlation_circle.png` | publication-grade single-figure biplot for the SBAC-PAD short paper |
| `plot_pca_dendro.py`      | an `aggregate-means.{csv,tsv}` (filtered to solo/bare rows) | `<out>/{png,pdf}/fig02-pca-and-ward-dendrogram-*` | the PCA + K-means + Ward-dendrogram two-panel (paper Fig. 2); manual argv parse, not argparse. `--stem=F7-pca-dendro` names the cross-deployment cut |
| `extract-fragility.py`      | a `bench-full/` directory (SystemTap stap.log per run) | `<input>/fragility-summary.tsv` and `fragility-aggregated.tsv` | quantifying probe skips, overload, sample loss for the stap-2022 / stap-nollc / stap-nohelper / stap-modern stap variants |
| `plot-cross-environment.py` | a `bench-full/` directory containing `aggregate-means.tsv` (>= 2 envs) | `<input>/cross-env/{summary,availability,stats}.tsv` + `plots/<variant>/<workload>.png` | comparing bare vs container vs vm under the same workload using Kruskal-Wallis + Mann-Whitney (Bonferroni) + Cliff's delta |
| `cross-variant-correlation.py` | a campaign tree (publication or fused layout) | `--out` dir: `correlation-{4way,per-metric}-<env>.tsv`, `correlation-{family-summary,per-metric-family}.tsv`, `overhead-bounds.tsv` | reproducing the paper's §V cross-variant fingerprint correlations (per-metric + per-family, raw and z-scored) and per-variant throughput-overhead bounds from the merged `aggregate-means.tsv` + overhead `throughput.tsv` |
| `render-paper-figures.py`   | a published campaign tree | `--out` dir: `figures/` (paper filenames), `published/<subset>/`, per-subset `{pdf,png}/` | regenerating the eleven SBAC-PAD camera-ready figures at their exact printed size |
| `qa_fig_fonts.py`           | a directory of paper-named PDFs | `QA-FIGS.md` + `qa/` contact sheet | gating the camera-ready set on page width and minimum font size, and diffing content against the previously published render |
| `paper_style.py`            | (imported, not run) | — | the shared camera-ready typography, page geometry and per-figure size table |

### P2 figure set (cross-environment, cadence, colocation, IADA)

These renderers consume the analyzer TSVs produced under `results/` (or,
for the W4 figure, the committed markdown adjudication under
`docs/reports/`); they never recompute statistics. The registry tying
each figure to its claim, data source, and script is
[../../docs/FIGURES-PLAN.md](../../docs/FIGURES-PLAN.md).

| Script | Input | Output | Use when |
|---|---|---|---|
| `plot-p2-15metric.py`       | a P2 campaign dir with `cross-deployment.tsv` + per-rep `portable.tsv`/`groundtruth.tsv` | `results/figures/<campaign>/{png,pdf}/F0-…F6-*` | rendering the 15-metric cross-deployment set (fingerprint heatmap, ratio-vs-bare, claim-class matrix, availability grid, membw_est validation, PSI falsification, psp panel) |
| `plot-cadence-curves.py`    | `cadence-fidelity.tsv` from `bench/analyze-cadence.py` | `results/figures/p2-cadence-sweep/{png,pdf}/F8-cadence-{fidelity,sensitivity}.*` | re-rendering the cadence knee curves and the per-metric sensitivity heatmap |
| `plot-w5-victim-delta.py`   | `w5-victim-delta.tsv` from `bench/analyze-cross-deployment.py --w5` | `results/figures/p2-w5-victim-delta/{png,pdf}/F10-*, F11-*` | the W5 colocation forest plot and the vm-guest portable-vs-canonical panel |
| `plot-iada-sim.py`          | `tier-sim-reps.tsv` from `run-tier-sim-reps.sh` | `results/figures/p2-iada-tiers/{png,pdf}/F13-tier-scheduling-idi.*` | the per-tier closed-loop scheduling outcome (degradation index + migrations, rep-level CIs) |
| `plot-iada-tier-table.py`   | `tier-eval.tsv` from `bench/iada/scripts/eval-tiers.R` | same dir, `F13-tier-{portability,transfer}-table.*` | the screenshot-ready tier portability / host→VM transfer tables (`--transfer` for the latter) |
| `plot-tierb-fingerprint.py` | `fingerprints.tsv` (or `fingerprints-tagged.tsv`, for the proxy markers) from `bench/analyze-tierb.py` | `results/figures/p2-tierb-realapps/{png,pdf}/F12-{fingerprint,class-activation}.*`; with `--pdf PATH` only that one fingerprint PDF | the real-app mixed-class fingerprint figures (`--envs` picks the row bands, `--variants` the columns; `--mask c38-prefix` hatches the v2.1 cells of `C38_PREFIX_MASK` as "pre-fix, not interpreted"; `--pdf` writes the self-contained paper cut with a legend instead of the suptitle) |
| `crop-fig14-fingerprint.py` | the combined F12 fingerprint PDF | `fig_fingerprint_v{21,33}.pdf` halves | **obsolete since v0.2.1** (D17); superseded by `plot-tierb-fingerprint.py --variants --pdf`. Kept only to reproduce the v0.2.0 figures |
| `plot-meyer-validation.py`  | `kmeans-centers.tsv` from the IADA validation tree + in-script degradation tables | `results/figures/p2-meyer-validation/{png,pdf}/F14-*, F15-*` | re-rendering the Meyer-2021 / IADA-2022 validation figures |
| `plot-sim-experiments.py`   | `--exp-dir` with `gate-default.tsv` + per-arm TSVs from `run-sim-experiments.sh` | `results/figures/p2-sim-experiments/` + `summary.tsv` | the E1–E5 / S8 simulator-sensitivity panels (missing arms are skipped, not fatal) |
| `plot-jdk-ab.py`            | `--ab-dir` with `reps-java8.tsv` + `reps-jdk17.tsv` | `results/figures/p2-jdk-ab/` + `{summary,delta}.tsv` | the JDK 8-vs-17 CloudSim rebuild equivalence check |
| `plot-w4-summary.py`        | `docs/reports/W4-faithfulness-r2.md` (markdown adjudication from `bench/analyze-faithfulness.py`; no verdict TSV exists) | `results/figures/w4-faithfulness/{png,pdf}/w4-summary.*` | re-rendering the two-panel W4 faithfulness headline (Seminario de Andamento figure) |

### Shared modules and data utilities

| Script | Input | Output | Use when |
|---|---|---|---|
| `fig_names.py`              | (imported, not run) | — | the single owner of what a figure is called: stem → description, campaign directory → campaign tag |
| `p2_figio.py`               | (imported, not run) | — | the single owner of the `<set>/{png,pdf}/` figure layout, and of the flat printed-size layout the LaTeX drop-ins use |
| `p2_ci.py`                  | (imported, not run) | — | the rep-level bootstrap 95% CI convention (bars at the sample mean; CI supplies only the whiskers) |
| `make-aggregate-means.py`   | a P2 campaign dir (per-rep `portable.tsv` captures) | `<campaign>/aggregate-means.tsv` | rebuilding a 15-metric `aggregate-means.tsv` as input to the PCA figures |
| `hibench-sample-loss.py`    | a results root with HiBench `profiler.tsv` runs | `fragility-hibench-{samples,aggregated}.tsv` | timestamp-gap sample loss on old trees that lack `duration_target_s` (where `extract-fragility.py` reports 0) |
| `quality-flags.py`          | a `bench-full/` dir (`aggregate-means.tsv`, optionally `fragility-summary.tsv`) | `<results>/plots/quality-flags.tsv` | advisory per-workload data-quality flags; never rewrites aggregates |
| `plot-aux-rerun.py`         | a `shared/intp-ebpf-checkout.sh` run dir | `<run>/plots/*.{png,pdf}` (flat layout, not p2_figio) | noise-floor and exp5 sched_switch figures from aux runs (`--compare-with` for cross-run panels) |

## Dependencies

```bash
pip install -r bench/plot/requirements.txt   # numpy, pandas, matplotlib, scikit-learn, scipy
```

`scikit-learn` is needed by `plot-intp-bench.py` (PCA / KMeans figure
fig02), by `plot-pca-correlation-circle.py`, and by `plot_pca_dendro.py`.
`plot-hibench.py` warns and skips the PCA panel if it is missing.

`scipy` is required by `plot_pca_dendro.py` and optional for
`plot-p2-15metric.py` (without it the F4 validation panel prints
rho=nan). `qa_fig_fonts.py` additionally needs `pymupdf`.

`extract-fragility.py` has no external dependencies (stdlib only).

## Expected input layout

The plot scripts read the directory tree produced by the bench
runners:

```
results/<campaign>/bench-full/
├── aggregate-means.tsv              # produced by run-big-batch.sh
├── metadata.txt
├── variants.manifest
├── bare/                            # one subtree per env (bare | container | vm)
│   └── <variant>/                   # v0 | v0.1 | v1 | v1.1 | v2 | v3 | v3.1
│       ├── solo/<workload>/rep<R>/profiler.tsv
│       ├── pairwise/<a>__vs__<b>/rep<R>/profiler.tsv
│       └── timeseries/<workload>/rep<R>/profiler.tsv
└── overhead/
    └── bare/<variant>/<workload>/rep<R>/{profiler.tsv,run.json,stress-ng.log}

results/<campaign>/hibench/
└── <profile>-<scale>/aggregate-means.tsv     # one per profile sweep
    └── <variant>/<workload>/rep<R>/profiler.tsv
```

The P2 campaigns keep a per-rep-capture layout; the figure scripts
consume the analyzer TSV at the campaign root plus the raw captures
underneath it:

```
results/<p2-campaign>/
├── cross-deployment.tsv           # bench/analyze-cross-deployment.py
│   (or w5-victim-delta.tsv with --w5, or fingerprints.tsv from analyze-tierb.py)
├── capabilities.env, metadata.txt, variants.manifest
└── <env>/                         # bare | container | container-podman | container-lxc | container-k8s | vm-guest
    └── <variant>/                 # v2.1 | v3.3
        └── solo/<workload>/rep<R>/{portable,groundtruth}.tsv, run.json
```

Cadence sweeps nest one such tree per interval under
`results/<sweep>/cadence-<N>ms/` plus a `sweep-manifest.tsv`; the
analyzers (`bench/analyze-cadence.py`, `bench/analyze-cadence-overhead.py`)
turn them into the TSVs the F8/F9 renderers read.

Variant directories use the **current** naming
(`v0`, `v0.1`, `v1`, `v1.1`, `v2`, `v3`, `v3.1`); see
[../../VERSIONS.md](../../VERSIONS.md) for the legacy↔current map if
you are replaying a pre-2026-05-05 snapshot.

## Running each script

### plot-intp-bench.py — full bench figure set

```bash
# 14-figure render against an existing campaign
python3 bench/plot/plot-intp-bench.py results/<campaign>/bench-full

# Custom output directory
python3 bench/plot/plot-intp-bench.py results/<campaign>/bench-full \
    --out /tmp/fig-iteration
```

Produces `fig00-*` … `fig14-*` plus the b-suffixed siblings
(`fig01b-per-variant-workload-fingerprint`,
`fig04b-profiler-extra-system-cpu-time`,
`fig04c-profiler-extra-context-switches`), each emitted as both PNG (under
`plots/png/`) and PDF (under `plots/pdf/`), and also `aggregate-means.csv`.
Every figure is auto-skipped when its required input subtree is empty
(e.g. no `timeseries/` data → no fig03), so it is safe to point at a
partial run.

### plot-hibench.py — HiBench resource-family figures

```bash
python3 bench/plot/plot-hibench.py results/<campaign>/hibench
python3 bench/plot/plot-hibench.py results/<campaign>/hibench --out /tmp/hb
```

Iterates over each `<profile>-<scale>/` subdirectory containing a
`aggregate-means.tsv` and emits the canonical IntP Fig. 4 panel
(`fig00-hibench-interference-ratios-per-workload-*`), the IntP Fig. 8
resource-family trace (`fig09-hibench-resource-family-timeseries-*`), and a
variants × resources heatmap.

### plot-pca-correlation-circle.py — single biplot

```bash
python3 bench/plot/plot-pca-correlation-circle.py \
    results/<campaign>/bench-full/aggregate-means.tsv

# Filter to a subset of variants, drop sparse rows
python3 bench/plot/plot-pca-correlation-circle.py \
    results/<campaign>/bench-full/aggregate-means.tsv \
    --variants v1.1,v2,v3,v3.1 --min-samples 30

# Override the feature set
python3 bench/plot/plot-pca-correlation-circle.py \
    results/<campaign>/bench-full/aggregate-means.tsv \
    --features cpu,mbw,llcocc,llcmr
```

Available knobs: `--env`, `--variants`, `--min-samples`,
`--features`, `--no-polygons`, `--output`. Run with `--help` for the
full list. By default the figure lands under `<input-dir>/plots/{png,pdf}/`. `--output`
gives the directory plus the figure *stem*: the stem picks the registered
description (`fig_pca_correlation_circle` over the paper-1 campaigns,
`F7-pca-correlation-circle` over the cross-deployment one), and the filename is
composed from it. Both project the canonical seven metrics; F7's extended-set
variant is still the open item in `docs/FIGURES-PLAN.md`.

### extract-fragility.py — SystemTap reliability metrics

```bash
python3 bench/plot/extract-fragility.py results/<campaign>/bench-full
```

Walks every `rep<R>/` under the campaign, parses
`profiler.stap.log` (only emitted by stap-2022/stap-nollc/stap-nohelper/stap-modern) and the
sibling `run.json`, and writes:

- `fragility-summary.tsv` — one row per
  `(env, variant, stage, workload, rep)` with skip counts, error
  counts, sample-loss percent.
- `fragility-aggregated.tsv` — `(env, variant)` rollup with means
  and standard deviations.

Console output prints a per-variant ranking of mean sample loss for
the bare-metal env, useful for the dissertation's reliability tables.

If your campaign was run with a non-default sampling interval, set
`INTP_INTERVAL` so `expected_samples` is computed correctly:

```bash
INTP_INTERVAL=0.5 python3 bench/plot/extract-fragility.py \
    results/<campaign>/bench-full
```

### cross-variant-correlation.py — §V correlation + overhead tables

```bash
python3 bench/plot/cross-variant-correlation.py \
    --campaign results/<campaign> --out paper-tables/ [--verify] [--plot]
```

Reproduces the numbers the paper cites in §V: how strongly the four
profiler endpoints agree on their per-application interference
fingerprints, and the per-variant throughput-overhead bounds. No other
plotter computes these. It reads the merged wide-format
`aggregate-means.tsv` (locating it under the campaign root or
`bench-full/` + per-profile `hibench/`) and the overhead
`throughput.tsv` files — no re-capture.

Two analysis envs: `bare` = the stress-ng layer (`stage == solo`),
`hibench` = the HiBench layer (`stage` like `hibench-<profile>`). The
"application" a fingerprint is built over is a stress-ng solo workload
(17) or a `(profile, workload)` pair (42). Correlation is Pearson on
the flattened `[application × metric]` fingerprint (raw and
per-metric-z-scored) and per single metric across applications. The
family roll-up splits the endpoints into the SystemTap pair
`{legacy-intp-baseline, stap-modern}` and the production-grade pair `{C-ABI, eBPF-CORE}`; the
**cross-family** rows are where the `llcocc` capability gap and the
legacy-intp-baseline overhead surface. Outputs (to `--out`, default `paper-tables/`):

- `correlation-4way-<env>.tsv` — the 6 pairwise r (raw + z-scored).
- `correlation-per-metric-<env>.tsv` — 7 metrics × 6 pairs.
- `correlation-family-summary.tsv` — the headline roll-up.
- `correlation-per-metric-family.tsv` — per-metric family roll-up.
- `overhead-bounds.tsv` — throughput overhead % per `(variant, ref_load)`,
  per-variant baseline (`_baseline.<variant>` overrides `_baseline`).
- `correlation-heatmap-<env>.pdf` — only with `--plot` (a debug sanity
  check, not a paper figure).

`--verify` checks the produced tables against `EXPECTED_VALUES` (the
exact numbers the paper cites, with provenance noted in the script) and
**exits non-zero on any mismatch**, so the artifact and the text cannot
silently drift. Run it against the canonical fused tree:

```bash
python3 bench/plot/cross-variant-correlation.py \
    --campaign results/ub22-and-24-full --out paper-tables/ --verify
```

`run-big-batch.sh` invokes the script (without `--verify`) in its plot
segment, writing `<campaign>/paper-tables/`.

### render-paper-figures.py — SBAC-PAD camera-ready figure set

```bash
python3 bench/plot/render-paper-figures.py sbac-results --out /tmp/camera-ready
python3 bench/plot/qa_fig_fonts.py /tmp/camera-ready/figures \
    --out /tmp/camera-ready --compare-to <payload>/published
```

Regenerates the eleven figures the paper includes, each rendered at its
**exact printed size** (`paper_style.py` holds the width/height table and the
IEEEtran page geometry), so `\includegraphics` embeds them at scale 1.0 and a
7 pt label is a printed 7 pt. Writes them twice — under the paper's filenames
in `figures/` and in the artifact's `published/<subset>/` layout — plus
`qa/pearson_ground_truth.tsv`, the nine profiler-vs-ground-truth Pearson r
values as data rather than as a picture.

The three plotters take `--camera-ready --paper-subset {baseline,new,merged}`
individually; the driver just sequences them. **Without those flags nothing
changes**, so the exploratory figure sets are unaffected.

Why printed size: the pre-camera-ready pipeline rendered every figure large
(7–15 in wide) and let `\includegraphics` scale it down to the column or text
width, which multiplied every font size by the same factor — an 8 pt tick
inside a 12 in figure placed at 3.45 in prints at ~2.3 pt. Reviewer 3 asked
for legible labels at printed size; rendering at scale 1.0 makes the 7 pt
body / 6.5 pt annotation sizes true printed floors. That left the paper over
the SBAC-PAD page limit with fonts and margins already spent, so the second
pass reduced the *count* of panels and floats instead: panels were merged
(legacy + modern fingerprints into one figure), transposed (the seven-panel
HiBench grid into one column-width heatmap) or relocated (the Pearson matrix
into a TSV set as a table). Only size, layout and typography changed — the
QA gate's content diff is the audit that no number moved.

Nine of the eleven PDFs are placed in the paper; two —
`fig01b-…-legacy-intp-baseline-only` and `fig05-…-all-published-variants`
— are rendered as *alternatives* to floats that were consolidated away, so
the author can put either back. `paper_style.FLOATS` records which PDFs make
up which float and what each costs.

`qa_fig_fonts.py` is the gate: it re-opens each PDF, asserts the page width
against the target, the 6.5 pt floor against the embedded text spans, and
that no text runs off the page box; diffs every visible string against the
previous render; reports each float's cost in points of column-space against
the consolidation budget; writes `QA-FIGS.md` plus a 300-dpi contact sheet
under `qa/`; and exits nonzero on any violation. It needs `pymupdf` in
addition to the dependencies above.

The off-the-page-box check exists because a figure can be shrunk until
matplotlib centres a y-axis label — which is as tall as it is long — on an
axes too short to hold it, and the ends fall outside the page. The page is
still the right width and the fonts are still the right size, so nothing else
in the gate notices that the label lost its last three characters. The fix is
a shorter label or a taller figure, never a smaller font.

### The P2 figure set — analyzer TSV to plotter

The P2 renderers never recompute statistics: they draw from the TSV the
corresponding `bench/analyze-*.py` already produced (BH-FDR significance,
rep-level bootstrap CIs per `p2_ci.py`). The chain is always campaign →
analyzer → plotter, and every figure lands in the shared `p2_figio`
layout (`results/figures/<set>/{png,pdf}/`, named per **How the figures are
named** above).

```bash
# F0-F6, cross-deployment 15-metric set (automated by bench/merge-and-render-p2.sh)
python3 bench/analyze-cross-deployment.py results/<p2-campaign>            # cross-deployment.tsv
python3 bench/analyze-portable.py        results/<p2-campaign> --out R.md  # docs report
python3 bench/plot/plot-p2-15metric.py   results/<p2-campaign> [--out DIR]

# F8/F9, cadence sweep (F9 is rendered by the analyzer itself, not a plot-* script)
python3 bench/analyze-cadence.py          results/p2-cadence-sweep         # cadence-fidelity.tsv
python3 bench/plot/plot-cadence-curves.py results/p2-cadence-sweep/cadence-fidelity.tsv [--out DIR]
python3 bench/analyze-cadence-overhead.py results/p2-cadence-overhead      # overhead TSV + report + F9

# F10/F11, W5 colocation victim-delta
python3 bench/analyze-cross-deployment.py results/<w5-campaign> --w5       # w5-victim-delta.tsv
python3 bench/plot/plot-w5-victim-delta.py results/<w5-campaign>/w5-victim-delta.tsv [--out DIR]

# F12, tier-B/C real-application fingerprints
python3 bench/analyze-tierb.py            results/<tierb-campaign>         # fingerprints.tsv
python3 bench/plot/plot-tierb-fingerprint.py results/<tierb-campaign>/fingerprints.tsv [--envs container,vm-guest]

# F13, IADA classifier tiers (sim + tables)
python3 bench/plot/plot-iada-sim.py        results/iada-sim/tier-sim-reps.tsv [--out DIR]
python3 bench/plot/plot-iada-tier-table.py results/iada-trainsets/tier-eval.tsv [--transfer]

# w4-summary, the Seminario de Andamento W4 headline (parses the committed
# markdown adjudication; analyze-faithfulness.py emits no verdict TSV)
python3 bench/plot/plot-w4-summary.py docs/reports/W4-faithfulness-r2.md [--out DIR]

# Simulator-sensitivity panels (E1-E5 / S8) and the JDK rebuild equivalence check
python3 bench/plot/plot-sim-experiments.py --exp-dir results/<sim-exp-dir>
python3 bench/plot/plot-jdk-ab.py          --ab-dir  results/<jdk-ab-dir>

# F14/F15, Meyer-2021 / IADA-2022 validation
python3 bench/plot/plot-meyer-validation.py \
    <IADA-second-born>/meyer-validation/kmeans-centers.tsv [--out DIR]
```

### Utilities

```bash
# Rebuild a 15-metric aggregate-means.tsv from per-rep portable.tsv captures
python3 bench/plot/make-aggregate-means.py results/<p2-campaign>

# Timestamp-gap sample loss for HiBench trees predating duration_target_s
python3 bench/plot/hibench-sample-loss.py results/<campaign>

# Advisory per-workload data-quality flags (LOW_SAMPLE, BIMODAL, ...)
python3 bench/plot/quality-flags.py results/<campaign>/bench-full

# Noise-floor / exp5 figures from a shared/intp-ebpf-checkout.sh run dir
python3 bench/plot/plot-aux-rerun.py results/<aux-run> [--compare-with RUN_DIR]

# PCA + K-means + Ward dendrogram (paper Fig. 2); manual argv, not argparse
python3 bench/plot/plot_pca_dendro.py [aggregate-means.csv] [outdir] \
    [--variants=v0.2,v2,v3.2] [--camera-ready --paper-subset=merged]
```

## Output sizing

The Paper-1 `plot-*.py` scripts cap PNG output at ~2600 px per side and
render at 160 DPI. Re-style those figures by editing the constants at
the top of each script (`MAX_PIXELS`, `SAVE_DPI`, `setup_style()`).
The companion PDF (vector) export bypasses the pixel cap.

The P2 renderers share the `p2_figio` layout instead and pick a per-set
DPI (140-160); `plot-aux-rerun.py` (200) and `plot_pca_dendro.py` (220)
carry their own.

## Replaying an archived campaign

Untar the result snapshot somewhere outside the repo and point the
scripts at the extracted root:

```bash
tar -xzf results/big-batch-stress-rep4-failhibench.tar.gz -C /tmp
python3 bench/plot/plot-intp-bench.py /tmp/bench-full
```

The plots write into the snapshot, not into the working tree, so
parallel re-renders against different snapshots do not collide.

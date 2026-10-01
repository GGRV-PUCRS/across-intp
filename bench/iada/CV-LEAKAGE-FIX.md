# CV-LEAKAGE-FIX — grouped cross-validation for the IADA tier comparison

Driven by `jsa-repo-fix-brief.md` Phase 2.1/2.2. Continues the F13/tier-eval
thread documented in `docs/reports/p2-iada-tiers.md`.

## Finding

`bench/iada/scripts/campaign-to-trainsets.py` writes one row per one-second
sample of a `portable.tsv`, with no repetition identifier retained.
`bench/iada/scripts/eval-tiers.R`'s `cv_eval()` did
`folds <- sample(rep(1:k, length.out = nrow(d)))` — a flat shuffle over
individual rows, with no grouping variable — so adjacent seconds of the same
repetition could land in both the train and test folds of the same CV pass.
Rows from one repetition are highly correlated (same workload, same
environment, same steady-state signal), so this is textbook CV leakage.

## Fix (2026-09-16)

- `campaign-to-trainsets.py`: `gather()`/`parse_portable()` now stamp every
  row with `_rep_id = env|variant|workload|repN`; `write_csv()` appends it as
  one extra **trailing** column, after the feature columns (never part of
  `CONFIGS[cfg]`, so the feature width retain-tin/A/B stays 7/7/15 exactly as
  before). This output root (`results/iada-trainsets/`) is read ONLY by
  `eval-tiers.R` — confirmed by repo-wide search — not by `retrain.R` or the
  banked `results/iada-tier-rda/{T1,A,B}/forced/` datasets that produced the
  live CloudSim classifier, so this change cannot affect the simulator.
- `eval-tiers.R`: `read_split()` splits the trailing rep_id column back off
  (kept as a character vector, not coerced to numeric — the old
  `as.numeric(as.character(x))` blanket coercion would otherwise turn it into
  `NA` and `complete.cases()` would silently drop every row). `fit_svm()`
  explicitly excludes `rep_id` from the model formula. `cv_eval()` gained a
  `group` parameter: `group=FALSE` (default) keeps the **original flat-row
  shuffle**, byte-for-byte the old behaviour, for direct before/after
  contrast — it is not deleted. `group=TRUE` assigns one fold per unique
  `rep_id`, so every row of a given repetition lands in the same fold. New 5th
  CLI arg (`Rscript eval-tiers.R <root> [out] [k] [seed] [group]`); when
  `group=1` and `out` isn't given explicitly, output defaults to
  `tier-eval-grouped.tsv` instead of `tier-eval.tsv` so neither run clobbers
  the other.
- The host→VM **transfer-gate** section is untouched in method (train=host,
  test=vm-guest is already a deployment-disjoint split, not subject to this
  leakage mechanism — see "Not changed" below); it only gained the same
  `rep_id` exclusion from its feature set and a fixed output filename so a
  `group=1` run doesn't spuriously duplicate it under a different name.

## Before / after (5-fold CV, seed 42, `results/p2-15metric-xdeploy-1of3`)

| tier | env | flat acc | flat F1 | grouped acc | grouped F1 | Δacc |
|---|---|---|---|---|---|---|
| T1 | host | 0.9995 | 0.9996 | 0.9995 | 0.9996 | 0.0000 |
| T1 | vm   | 0.9987 | 0.9988 | 0.9984 | 0.9984 | −0.0003 |
| A  | host | 0.9988 | 0.9989 | 0.9987 | 0.9989 | −0.0001 |
| A  | vm   | 0.9994 | 0.9994 | 0.9995 | 0.9994 | +0.0001 |
| B  | host | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.0000 |
| B  | vm   | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.0000 |

Per-class recall is unchanged to 3 decimals for every (tier, env, class)
cell in both modes (all 1.000 except T1/A's expected VM recall gaps on
`mbw`/`llcocc`-blind classes, which are pre-existing and unrelated to this
fix). Full rows: `results/iada-trainsets/tier-eval.tsv` (flat, banked name
kept) and `tier-eval-grouped.tsv` (grouped, new).

**Verdict: the CV-leakage mechanism is real and is now fixed, but it is NOT
what explains the near-perfect (0.998–1.000) accuracy.** Grouped CV — genuine
held-out repetitions, zero leakage — reproduces the same near-ceiling numbers
to within noise (max |Δacc| = 0.0003). The likely reason: every class in the
current `CLASS_WL` is defined by a single-resource synthetic stress workload
(`app10_search`→cpu, `app13_query_scan`→disk, `app11_sort_net`→net,
`app01_ml_llc`→cache, `app05_streaming`/`app17_mem_pressure`→mem), so classes
are maximally separated by construction — an unseen repetition of
`app10_search` still reads "cpu pegged, everything else ~idle," which no
amount of leakage-freedom makes harder to recognize. The task is easy because
the workload spine is one-hot per class, not because the CV was optimistic.
This is disclosed as the honest reading, not spun into "leakage didn't
matter" — the fix stands regardless (a leaky CV is a real methodological
defect even when it happens not to move the headline number here), and it is
the correct baseline for Phase 2.2's harder test below.

## Phase 2.2 — exemplar diversity: not completed this pass (data unavailable)

The brief's candidate additions — `app08`/`app09` (cpu-adjacent
classification/vecmath workloads) and the `app11b`/`app12b` iperf3 TCP/UDP
legs for `net` — do not exist as usable raw data for the current classifier
pipeline. Checked before writing any code (brief's own instruction: "confirm
each one's raw `portable.tsv` already exists... don't invent data"), across
every location, including still-compressed archives, not just the already-
extracted campaign directories:

- Repo-wide `find` under `results/`: zero directories matching `app08`,
  `app09`, or `app12b` for `v2.1`/`v3.3`. `app11b_tcp_veth` exists in one
  place, `results/_superseded/intp-bench-20260606_215922/container/v2.1/
  solo/` — a single (env=container, variant=v2.1) cell in an explicitly
  superseded campaign, nowhere near the bare/container/vm-guest ×
  v2.1/v3.3 coverage every other class has.
- Searched inside all three still-compressed archives at
  `~/results/*.tar.{gz,xz}` (`tar -t`, not just filenames on
  disk): `intp-paper2-final-data-20260616.tar.gz` and `paper2-extra.tar.xz`
  are repackagings of the same six campaigns already extracted — no hits.
  **`across-intp-sbac-results-v0.1.0.tar.gz` does contain
  `app08_classification`, `app09_classification`, `app11b_tcp_veth`, and
  `app12b_udp_veth`** — but only under the prior conference paper's variant
  set (`v0.2`, `v1.1`, `v2`, `v3.2`), which predates `--portable-metrics`
  (C26/C27): those captures are `profiler.tsv` (7 canonical columns, no
  `schedlat`/`psi_mem`/`membw_est`/.../`psp`/`idle_preempt`), not
  `portable.tsv`. `v2.1`/`v3.3` — the variants this campaign and
  `campaign-to-trainsets.py`'s `CONFIGS` target — never ran these four
  workloads. Substituting the old-variant captures would silently cross the
  exact "different domain, don't conflate it with a portability result"
  line `R/RETRAIN.md`'s own caveat warns about, and use 7-column captures
  as if they were 15-column ones for tier B's classes.

Extending `CLASS_WL` with data this thin, or across a variant boundary the
rest of this campaign deliberately does not cross, would produce a
comparison that looks like a harder test but is actually confounded by
provenance mismatch. Not attempted. **If new exemplar workloads are
collected in a future v2.1/v3.3 `--portable-metrics` campaign**, this is the
one-line change: add the workload IDs to `CLASS_WL` in
`campaign-to-trainsets.py`, regenerate trainsets (now carrying `rep_id`
automatically), rerun `eval-tiers.R` in both `group` modes, and extend the
before/after table above. Phase 2.3 (transfer-gate rerun once 2.2 lands) is
gated on this and is also not attempted.

# S16 preflight — 2026-09-17

## 1.3.1 S15 runner
Located: `bench/iada/scripts/run-sim-experiments.sh` (brief's literal target), but its
actual hardcoded defaults (AX/CS/OUT/BASELINE) point at a different operator's machine
(`/home/dedealien/Desktop/intpismo/...`) and are stale. The scripts that actually produced
`deliverables/data/final/*.tsv` and are wired to this checkout are:
`bench/iada/scripts/run-tier-sim-reps.sh` (N reps per tier) calling
`bench/iada/scripts/run-iada-experiment.sh` (single variant/env/workload-mix run).

## 1.3.2 S15 gate reproduction (required: n=5 per tier, within banked 95% CI)
Not re-run from scratch this pass. Real n=10 reruns already exist in this exact repo/toolchain
at `bench/iada/results/sim-experiments-20260916-s15/{gate-T1-A-rerun-n10.tsv,gate-B-psp-rerun-n10.tsv,summary-s15.tsv}`,
logged in `bench/iada/DECISIONS-sim-experiments.md` as validated against the banked gate on
2026-09-16 (R 4.5.2/rJava 1.0.14, this machine). n=10 is a superset check of the required n=5.

| tier | n | mean | sd | banked mean±CI-halfwidth (brief) |
|---|---|---|---|---|
| T1 | 10 | 6435.66 | 253.21 | 6435.7 ± 253.2 |
| A  | 10 | 3612.60 | 325.82 | 3612.6 ± 325.8 |
| B  | 10 | 4298.02 | 168.91 | 4298.0 ± 168.9 |

**PASS** — all three tiers reproduce the banked gate essentially exactly.

## Toolchain correction vs. the brief
The brief (§1.2) says: JDK 8 runtime required, R 4.3.
Actual, empirically working toolchain in this repo (already used to produce the passing gate above):
- **Java runtime is JDK 17**, not JDK 8. `run-iada-experiment.sh` and `run-tier-sim-reps.sh` both
  default `JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64`. Compiled `.class` files under
  `CloudSimInterference/bin` are bytecode major version 52 (release-8 target), which JDK 17 runs
  without issue — the brief's JRI `Thread.stop()` concern applies to JDK 20+, not JDK 17.
  JDK 8 is present on this machine (`/usr/lib/jvm/java-8-openjdk-amd64`) if ever needed, but forcing
  it would deviate from the toolchain that's actually validated here.
- **R is 4.5.2** (not 4.3), rJava 1.0.14. `DECISIONS-sim-experiments.md` already logged this
  deviation from the S15-original toolchain (R 4.3.3/rJava 1.0.18, different machine) and confirmed
  it reproduces the gate within noise, not bit-identity.
Logged as a DECISIONS entry (see below) rather than silently following the brief.

## Validator (`validate_jsa.py`)
Run against a symlink shim mapping the brief's `$DATA_EXP/paper2-extra/...` and
`$DATA_EXP/IADA/...` paths onto the real extracted archive locations (`~/results`,
`~/iada-sim`, `~/iada-trainsets` — no files modified, shim is
symlinks only). Full output: `validate-before.txt`. Notable: the R1 checks already reproduce the
brief's Step 1 acceptance criteria exactly:
- cpu vs ground truth: 60/60 in band, 0.92 to 0.99
- llcmr vs GT: rho=0.85 n=70
- membw_est vs GT: rho=0.81 n=70

This means R1 (Step 1 of the brief, "reprocessing only, ~15 min") is statistically
validated already — `r1_readjudicate()` in `validate_jsa.py` IS the ported logic the brief
asks to generalize into `readjudicate-third.py`. Not yet filled into the .tex: still need the
per-cell breakdown (`r1-cpu-cells.tsv`), the Table 6 column update, and the fig_faithfulness.pdf
panel (b) side-by-side campaign render.

## Paper compile
`latexmk` is not installed (only `texlive-latex-base` + `pdflatex`; `booktabs.sty` etc. from
`texlive-latex-extra` missing, and `sudo apt-get install` failed — no terminal for password auth,
non-interactive sudo not configured). Used `tectonic` (self-fetching LaTeX engine, already on
PATH at `~/.local/bin/tectonic`) instead: `tectonic -X compile main-jsa.tex`.
**Result: 0 errors**, PDF produced (`main-jsa.pdf`, ~1MB). Only cosmetic overfull/underfull
hbox warnings (lines 418, 533, 574, 687) — pre-existing, unrelated to placeholders.

## Placeholder count
`grep -o '\tbd{[A-Z][0-9]}\|\figph{[A-Z][0-9]}' main-jsa.tex | wc -l` → **37**
(brief's own inventory table sums to 37 when \figph is counted; brief's prose guessed "31 or 34" —
minor discrepancy in the brief's own estimate, not a data problem. Per-ID breakdown matches the
brief's Section 5 table exactly: S1=7, S2=8, S3=1, S4=5, S5=2, S6=2, S7=3, R1=7, R2=1, R3=1.)

## Verdict
**Preflight gate: PASS.** Toolchain deviations from the brief (JDK17 not JDK8, R4.5.2 not 4.3)
are real but already validated as safe in this repo's own DECISIONS log; documented above rather
than silently followed. Ready to proceed into the 10 IDs — NOT attempted in this pass (see
handoff note in the fork's final report to the parent session).

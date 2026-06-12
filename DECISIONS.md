# DECISIONS.md — HiBench sample-loss reproducibility

Implementation notes / deviations for the 4-phase HiBench timestamp-gap
sample-loss fix. One commit per phase on `main`.

## Conventions applied

- Branch `main`; one commit per phase, using the brief's stated commit messages.
- Commits **omit** the `Co-Authored-By` trailer (per user instruction, 2026-06-01).
- No unrelated reformatting.

## D1 — `extract-fragility.patched.py` is not a separate file

The brief names a provided `extract-fragility.patched.py` as the Phase-2 "source
of truth" to diff against. No such file exists in the working tree or the
provided artifact. Per the user (2026-06-01), that patched reference was folded
directly into the working-tree `bench/plot/extract-fragility.py` modifications.
Verified the edit against the brief's explicit 3-edit description instead
(`expected_from_timestamps()` added after `count_tsv_samples()`; per-run
`interval` + timestamp-gap fallback in `row_for()`; path-based `env` fallback) —
it matches.

## D2 — prior uncommitted pass left a stripped EOF newline

The working tree already held the Phase-1 file (untracked) and the Phase-2 edit
(unstaged). Both files had the trailing newline at EOF removed — a spurious diff
that violates "do not reformat untouched code". Fixed:

- `bench/plot/hibench-sample-loss.py`: restored to byte-verbatim by copying the
  pristine provided copy, then `chmod +x` (Phase 1).
- `bench/plot/extract-fragility.py`: trailing newline restored so the diff vs
  HEAD is only the intended insertions (Phase 2).

## D3 — acceptance tree location; no stall dumps present

Acceptance was run against the provided release tree, which the user relocated
into the repo at `results/across-intp-sbac-results-v0.1.0/sbac_results-publish/`
(`/results/` is gitignored, so it is never committed). This is the **redacted
public payload**: it contains no `stall-monitor/` dumps (`stall-dump-*` count =
0). The shipped `fragility-aggregated.tsv` still carries
`bare legacy-intp-baseline sum_stalls_detected=148` from the full tree, so the extractor must
NOT overwrite the shipped file here (that would reset stalls to 0). See D5
(Phase-2 validation method) and the README do-not-regenerate caveat.

## D4 — Phase 1 validated

`python3 bench/plot/hibench-sample-loss.py <tree> --out-dir <tmp>` reproduces the
shipped `fragility-hibench-aggregated.tsv` exactly over 2016 HiBench reps
(4×504): legacy-intp-baseline 3.03% / max 55.0% (68 reps>5%), stap-modern 4.39% / max 73.08%
(100 reps>5%), C-ABI 0.0% (max 2.38), eBPF-CORE 0.01% (max 1.85).

## D5 — Phase 2 validated without clobbering the shipped artifact

Method: backed up `fragility-aggregated.tsv` + `fragility-summary.tsv`, ran
`python3 bench/plot/extract-fragility.py <tree>`, inspected the regenerated
output, then restored the backups (confirmed byte-identical; bare legacy-intp-baseline
`sum_stalls_detected=148`, `runs_with_stall_dump=28` intact). Results:

- **env=bare UNCHANGED**: legacy-intp-baseline 277 mean 6.38 / max 75.56; stap-modern 277 mean 15.96 /
  max 98.89; C-ABI/eBPF-CORE zero. (Regenerating against this redacted tree reads stall
  counts as 0 — see D3 — which is exactly why the shipped file is preserved,
  not overwritten.)
- **env=hibench NEW (real loss)**: stap-modern mean 4.05 / max 73.08 / 100 runs>5%;
  legacy-intp-baseline mean 2.8 / max 55.0 / 68>5%; C-ABI/eBPF-CORE ~0 (max <2.4). n_runs = 546 = 504
  per-rep + 42 workload-aggregate `run.json` rows (no profiler.tsv → 0 loss),
  which is why the per-variant mean is ~4.05 here vs the Phase-1 tool's 4.39
  (expected, per the brief).

## D6 — paper text reconciled to the reproducible HiBench numbers

The paper (`main.tex`) has been updated to the reproducible timestamp-gap
figures — **stap-modern: 100 of 504 reps >5%, mean 4.39%, max 73.08%** — i.e. exactly
the `fragility-hibench-aggregated.tsv` values produced by `hibench-sample-loss.py`
(an earlier draft predated this definition). The repo task does not modify the
paper; `main.tex` is maintained separately and already compiles clean.
Reviewers regenerating via the unified `extract-fragility.py` see a marginally
lower per-variant mean (~4.05%) for `env=hibench`, because those rows also
include the 0-loss workload-aggregate `run.json` files; the canonical per-rep
figure is 4.39% (see D4/D5).

## D7 — `samples > elapsed_s` in old run.json is expected

The profiler window spans more than the Spark job's own wall-clock `elapsed_s`,
so `samples` can exceed `elapsed_s`. The timestamp-gap method intentionally
ignores `elapsed_s` and derives the window from the profiler `ts` column.

## D8 — Phase 3: env + sample_interval_s in both HiBench run.json writers

- Added `"sample_interval_s":$INTERVAL` (the required field) to **both** the
  per-rep writer (heredoc ~L1251) and the workload-aggregate writer (~L1301).
  Adding it to the aggregate was trivial, so it was not skipped.
- Also stamped `"env":"hibench"` into both writers (the brief's optional
  self-describing-env step), keeping the Phase-2 path-based fallback. Old trees
  (no field) and new trees (field present) therefore classify identically as
  `env=hibench` — extractor output is unchanged either way. Extended the stamp
  to the aggregate writer too (the brief mentioned per-rep) for symmetry.
- Safe: no consumer depends on `env` being absent from HiBench run.json — plot
  scripts/tests read the `env` column of derived TSVs (not run.json);
  `hibench-sample-loss.py` reads only status/elapsed/samples; the script's own
  `rep_is_complete()` resume check greps for `"status":"ok"` only.
- Left the rare `profiler_start_failed` per-rep writer (printf, ~L1143)
  untouched: no profiler.tsv → loss is N/A and the path fallback still
  classifies it (minimal-change).
- Validated: `bash -n` clean; both writers emit valid JSON; a synthetic tree
  proves `extract-fragility.py` honors a recorded `sample_interval_s`
  (interval=2 → loss 0 vs interval absent/=1 → loss 40 on the same 3-sample,
  4 s-span profiler.tsv).

## D9 — Phase 4: reader/reviewer-facing data-quality section

Added a "Data-quality / sample loss" section to the repo's tracked
`sbac-results/README.md` (the scaffold README had none; the detailed copy lives
only in the gitignored published payload). It gives the stress-ng and HiBench
loss formulas, states that `extract-fragility.py` now emits real `env=hibench`
rows, that `hibench-sample-loss.py` is the standalone backfill for old trees,
and that future runs record `sample_interval_s`. Written for readers/reviewers
with **no author-only notes** (per user guidance, 2026-06-01): it cites the
canonical `fragility-hibench-aggregated.tsv` figures (stap-modern 4.39% / max 73.08% /
100-of-504 reps>5%) and explains the unified extractor's ~4.05% nuance for
reviewers. The existing do-not-regenerate / legacy-intp-baseline-stalls-as-counts caveat (under
Anonymization) is left intact and cross-referenced rather than duplicated, plus
a note that `hibench-sample-loss.py` is safe to re-run on the published tree
(writes only `fragility-hibench-*.tsv`) whereas `extract-fragility.py` would
rewrite the stall-bearing tables.

## D10 — v2.1 + v3.3 ported-and-frozen into ggrv-intp/intp (2026-06-10)

The production repository (`ggrv-intp/intp`, local `../intp`) ported
the measured engines at freeze commit `2e87b30fc762` of
`feat/container-based-interference`:

- v2.1 (c-abi-cgroup) → the baseline backend set (per-metric files
  under `src/backends/`, selection semantics from
  `backend_registry.c`, detection/resctrl/perfev/procutil infra).
- v3.3 (ebpf-core-cgroup) → the higher-priority eBPF backends
  (`intp_agg.bpf.c` byte-frozen; `intp_agg.c` split into a refcounted
  loader + per-metric shims).

Contract (recorded in `../intp/SYNC.md`): the migration is one-way and
frozen; the repositories evolve independently. Fixes to the production
profiler belong in intp; this repository remains the experiment
harness and the papers' record. Any future re-sync requires a new ADR
on the intp side and a D-entry here. Cross-variant equivalence checks
against the intp binary must EXEMPT per-cgroup `nets` (the byte-share
proxy divergence, C2) and compare `blk` only within semantic model
families (io_ticks vs svctm vs cgroup-throughput; see intp ADR-0010).

The port was verified file-by-file against the originals (formulas,
constants, vendor event codes, chain order, status assignments):
zero behavioral drift; intentional additions are limited to RMID
hygiene (stale mon_group reaping + a 75% num_rmids budget preflight)
documented in the intp tree.

## D11 — latent per-overflow perf wakeup load in v3.2/v3.3 llcmr (observation from the intp port, 2026-06-11)

While gating the production port (ggrv-intp/intp, see D10), the
v3.3-inherited ctxsw-amplification acceptance test FAILED on a hybrid
client CPU (Intel Core 7 240H, kernel 6.17) at **ratio 6.84** under a
cpu-bound stress-ng load — despite the identical attr passing <= 1.10
on the Sapphire Rapids testbed. A four-arm bisect (no-profiler floor
0.95; pure-C 1.0-equivalent; eBPF minus llcmr 0.95; full default 6.84)
isolated the amplifier to the **llcmr perf-overflow sampling path**:
~6.7k extra context switches/s.

Cause: `attr.wakeup_events = 1` on the sampled LLC events —

- `variants/v3.3-ebpf-core-cgroup/src/intp_agg.c:275`
- `variants/v3.2-ebpf-core/src/intp_agg.c:143`

requests a perf-fd wakeup on every overflow, but in the v3.2/v3.3
design **nothing ever consumes that fd**: the attached BPF program
handles each overflow and the counts live in the counter maps, scaled
by sample_period. The wakeups are pure waste. On the server testbed
the load was invisible (absorbed by the much larger ctxsw baseline and
a different PMU/overflow profile); on a quiet hybrid client CPU it
dominates the ratio.

Fix applied on the production side (intp commit 6127c78): delete the
`attr.wakeup_events = 1;` line. Metric values are unchanged by
construction (the BPF handler runs per overflow regardless); the
amplification gate on the same laptop went 6.84 -> **1.06**.

Resolution (author-approved 2026-06-11): the deletion is APPLIED to
both variants in this commit (with a D11-referencing comment at each
attr site); both rebuild clean. PENDING before the next campaign:
re-run `make -C variants/v3.2-ebpf-core test-amplification` (and the
v3.3 equivalent) as root to re-gate.
- **Measurement-consistency caveat:** any paper-2 overhead legs already
  executed measured v3.3 WITH the wakeup load. Fixing mid-campaign
  changes the overhead characteristics between legs — either re-run
  the affected overhead stages after the fix, or keep v3.3 as-is for
  the remaining legs and annotate.
- v3-ebpf-ring also sets the field (src/intp.c:296) but is retained
  precisely as the documented-overhead predecessor; not a fix target.
- Paper-2 angle: the finding itself is a portability observation for
  the eBPF overhead claim — "<= 1.10x on the reference server" does
  not transfer to client/hybrid CPUs while the wakeup load is present,
  which sharpens the scope qualifier the overhead claims must carry.

## D12 — v2.1 per-cgroup/PID mbw was silently system-wide; shared RMID group; test robustness back-ports (2026-06-12)

Found while closing the intp v0.9.0 release gate on the RDT testbed
(kernel ground truth via a manual resctrl mon_group) and back-ported
here after evaluation, per the alignment review.

**1. v2.1 mbw scope bug (FIXED).** The mbw chain preferred the uncore
memory-controller PMUs (Intel IMC / AMD DF / ARM CMN) unconditionally,
but those count TOTAL socket DRAM traffic and physically cannot
attribute to a cgroup or PID set — so for `--cgroup`/`--pids` targets
v2.1 reported the SYSTEM-WIDE figure as the target's mbw (an idle
cgroup read ~58% while the kernel's own per-RMID mon_group read 0%).
This contradicted v2.1's own scoped-mon_group intent in
`mbw.c:resctrl_init_` and `bench/validate-attribution.sh`'s
`SEPARABLE_METRICS` claim that mbw is "per-cgroup attributable in
v2.1". Fix: the uncore probes now reject non-system targets so the
resctrl mbm backend (per-RMID, isolatable) is selected for
cgroup/PID targets; system-wide keeps IMC (its most accurate source).

**2. v2.1 single-RMID clash (FIXED, required by 1).** With resctrl
selected for a target, mbw and llcocc each created their own mon_group
(`intp_v2_mbw_*` / `intp_v2_occ_*`) and assigned the SAME tasks — but a
task can be in only one RMID, so the loser's group read 0. Both
counters live in one mon_group's mon_data; they now share a refcounted
`intp_v2_rdt_<pid>` group (`resctrl_target_group_acquire/rescan/
release`). Verified on the testbed: one group, heavy cgroup reads mbw
72–99 AND llcocc 74–96 concurrently, idle cgroup mbw isolates to 0.

**Measurement caveats:**
- Any prior per-cgroup or per-PID v2.1 row recorded mbw as the
  system-wide value. `--pids` mbw semantics change from
  IMC-system-wide to task-scoped resctrl (the correct reading of "this
  workload's mbw", and now the same scope v3.3 reports). Re-run or
  annotate affected legs; system-wide rows are unaffected.
- v3.3 needed NO product change (single shared `intp-v3.3` group +
  resctrl for cgroup mbw already — it was right all along; D11's
  "v3.3 mbw over-read" observations vs v2.1/intp were in fact v3.3
  being correctly cgroup-scoped while the others read system-wide).

**3. v3.2/v3.3 test-load-attach robustness (FIXED).** The leak check
compared global `bpftool prog show | wc -l` before/after — on a busy
multi-tenant host the system-wide count churns (the testbed now runs
k3s with ~111 BPF programs; the test false-fails there today), and BPF
teardown is asynchronous (tp_btf programs linger <0.5s post-exit).
Now counts only the variant's OWN program names and polls up to 5 s
for the async drain. Per-variant name lists (v3.2 has
tp_sched_process_* and no cg_skb/tp_schedlat). Verified 3/3 PASS on
the k3s-busy testbed.

**Evaluated and deliberately NOT changed:**
- `shared/validate-cross-variant.sh` — already sequential and
  PID-targeted; the system-wide/concurrent parity bugs existed only in
  intp's port of it, fixed there (intp 7c19e21).
- `bench/validate-attribution.sh` — FLAG: its intra leg profiles
  heavy/idle/slice-TOTAL with three CONCURRENT v2.1 instances whose
  cgroups OVERLAP (total ⊇ heavy+idle). With per-target mon_groups,
  the instances steal each other's tasks via the same single-RMID
  physics as (2) — per-(metric, instance) values can read ~0 or flap
  with the rescan cadence. Needs sequential windows or disjoint legs
  before its resctrl rows are trusted; left to the paper-2 analysis
  pass rather than a mechanical rewrite here.

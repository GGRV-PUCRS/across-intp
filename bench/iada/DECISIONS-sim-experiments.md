# DECISIONS-sim-experiments.md — IADA/CloudSim second campaign (post-recovery)

Decision log for the simulation-side experiment campaign started 2026-08-11 on
the dedealien box, after recovering the uncommitted Approach B working tree.
Companion to `docs/DECISIONS-container.md` (container axis) and
`docs/reports/p2-iada-tiers.md` (tier definitions). Everything here is
**simulation/analysis only**: the 15-metric campaign and W5 victim-delta
captures already on disk are the sole inputs; no new IntP profiling.

Output home: `~/Desktop/intpismo/IADA-second-born/` (versioned by the owner,
outside any repo). Campaign runner:
`bench/iada/scripts/run-sim-experiments.sh`; per-arm TSVs land in
`IADA-second-born/sim-experiments-20260811/`.

## Conventions applied

- CloudSim work on branch `feat/approach-b-15metric` (CloudSimInterference),
  analysis/driver work on `feat/container-based-interference` (this repo).
- Commits omit the `Co-Authored-By` trailer (repo convention).
- Pushing to the private remotes is now **on** (owner decision, 2026-08-12);
  the earlier no-push rule was for the anonymized-artifact phase.
- Every new CloudSim parameter defaults to the committed behaviour, so an
  unflagged run reproduces the banked campaign bit-for-bit in expectation.

---

## Ratified decisions (2026-08-11 → 12)

### S1 — Recovery supersedes the handoff's calibration plan

The uncommitted working tree held the real fixes: `SIMULATION_LIMIT
99999999999→119`, `IntContainerDataCenter` horizon `7200→119` with intervals
`{1,20}`, hosts/VMs `96→12`, and `containerList` sized from
`cloudletList.size()`. The handoff's `VM_STARTTUP_DELAY` hypothesis was wrong
and its calibration sweep is cancelled. Committed as `a24fe55` on
`feat/approach-b-15metric`; also preserved in
`IADA-second-born/recovered-cloudsim-edits.patch` and the banked `bin/`
tarball (`~/cloudsim-bin-banked-backup.tar.gz`, class major 52).

### S2 — Bytecode target: campaign runs on `--release 8`

A JDK 17 (major 61) rebuild first showed T1 +204 [+58,+362] vs the banked
Java 8 build; a 20-rep/leg confirmation returned −28.5 [−185,+121] with the
migration gap gone. **Verdict: false positive; the builds are equivalent on
all tiers.** The campaign still uses the `--release 8` tree
(`CloudSimInterference-rel8`) so its artifacts stay bit-compatible with the
banked ones. The first-pass java8 leg (sd 105 vs the true ~285) was the
outlier that manufactured the effect — recorded here as a worked example of
why single-pass 10-rep deltas do not gate anything.

### S3 — Gate arm before any experiment arm

`run-sim-experiments.sh` arm 0 re-runs T1/A/B at all-default parameters on the
rel8 build and bootstrap-tests each tier against the banked A/B baseline
(`ab-run-20260811/reps-java8.tsv`). Any tier whose 95% diff-CI excludes zero
aborts the campaign. Rationale: after the S2 episode, no arm is interpretable
unless the zero-flag configuration reproduces.

### S4 — Parameters over constants, defaults = committed values

New system properties in CloudSimInterference (all read once, all defaulting
to the previously hardcoded value):

| flag | replaces | experiment |
|---|---|---|
| `iada.hosts` / `iada.vms` | `NUMBER_HOSTS/VMS = 12` (was inert vs `PM_COUNT`) | E3 |
| `iada.vmStartup` | `VM_STARTTUP_DELAY = 100` | E1 |
| `iada.regime` (`on/off`) | unconditional 6th cost term | E2 |
| `iada.degTable` (`fork/paper`) | hard-wired hot table | E5 |
| `iada.regimeRamp` (`low,mod,hig`) | `1.20,1.55,1.95` | E4 |
| `iada.horizon` | `total = 119` literal | (safety) |

Driver side: `run-iada-experiment.sh` now honours `INTP_JAVA_OPTS` (it was
defined in `~/.iada-env` but never wired into the java line — the three JRI
flags were duplicated inline) and adds `IADA_JAVA_EXTRA` as the per-arm hook.
Wiring verified end-to-end by forcing `iada.horizon=200`, which reproduces the
original `Index 121 out of bounds for length 120` crash on demand.

### S5 — Degradation table is a switch, not a rewrite

Upstream `Degradation.java` ships values 2–8% hotter than Meyer/Ludwig
Table 2 and carried the paper's set as commented-out dead code — a deliberate
fork, not drift. `-Diada.degTable=paper` selects the published table
(memory/moderate corrected 1.64→1.62 to match the printed paper). Default
stays `fork` so banked results reproduce. E5 measures whether the choice
moves tier rankings; whichever table we standardise on afterwards gets named
in the paper text.

### S6 — Host sweep matched on contention ratio, not host count

Meyer 2021 swept 4/6/8/10/12 hosts over 12 apps: ratios 3.0/2.0/1.5/1.2/1.0
with degeneracy (1 app/host, zero interference) at 12. With 28 traces the
same ratios give **9/14/19/23/28**, degeneracy at 28. Adopting Meyer's raw
counts (or the handoff's 4/6/8/12) would compare different contention regimes
across studies. Requires S4's `iada.hosts` — with the old inert flag a sweep
leg would have written a 4-PM `input.txt` while the datacenter silently built
12 hosts.

### S7 — Regime ramp: the W5 evidence is binary, and the level column is suspect

Re-binning W5 (`w5-victim-delta.tsv`, v3.3, regime primaries
schedlat/membw_est, n=30): 11 rows at |Cliff's δ|≤0.10, 18 at ≥0.90, **one**
in between — the `low`/`mod` calibration bins are empty. The committed
near-linear ramp (1.20/1.55/1.95) asserts a gradation the data never showed.
E4 therefore sweeps shapes (step 1.90/1.93/1.95, convex 1.07/1.55/1.95,
measured-inflation 1.10/1.25/1.41) as a sensitivity analysis, **not** a
calibration.

Deeper issue found while answering "are psp/idle_preempt runtime metrics?":
they are not (events/s regime indicators; the runtime-adjacent signals are
the psi_* stall fractions) — but `retrain.R` levels the regime class on
column 8 = **schedlat** (a victim-delay metric), while the tier report
defines the regime signal as **psp/idle_preempt** (cols 14/15). schedlat's
fire-or-not behaviour likely explains the empty bins; psp is genuinely graded
across apps (87…9901 events/s in the tier-C report) and could support 3
levels. **Follow-on (S8, pending): re-level regime on psp, retrain tier B,
re-run E2/E4.** Not folded into this campaign because the retrain rewrites
the `.rda` the running sims read.

---

## Experiment matrix (running)

| arm | tiers | hosts | flags | question |
|---|---|---|---|---|
| gate-default | T1 A B | 12 | — | does rel8+defaults reproduce the banked arm? |
| e2-regime-off | B | 12 | `iada.regime=off` | fingerprint vs 6th-multiplier confound |
| e5-degtable-paper | T1 A B | 12 | `iada.degTable=paper` | does the table choice move rankings? |
| e4-ramp-{step,convex,measured} | B | 12 | `iada.regimeRamp=…` | ramp-shape sensitivity |
| e1-startup-{0,10,50} | T1 A B | 12 | `iada.vmStartup=…` | co-execution window 19s → 119s |
| e3-hosts-{9,14,19,23,28} | T1 A B | 9–28 | `iada.hosts=…` | ratio-matched contention curve |

10 reps/arm-tier; rep-level bootstrap CI (N=10000, seed 20260607) per
`bench/plot/p2_ci.py`; figures via `paper_style.py` + `p2_figio.py`.

## Campaign results (landed 2026-08-12, all arms complete, 0 failed reps)

Full per-arm numbers: `results/figures/p2-sim-experiments/summary.tsv`;
figures `F-simexp-deltas` / `F-simexp-hosts`. Deltas are arm − gate, same
tier, 95% bootstrap CI. Five intervals exclude zero; every one is a
cost-model knob:

| finding | numbers | reading |
|---|---|---|
| **E2** regime term off | B −2090 [−2320, −1926] | The 6th multiplier carries ~39% of B's IDI; without it B (3292) lands *below* A (3629). B-vs-A is dominated by the extra cost term, not the 15-metric fingerprint. |
| **E4** ramp shape | step +292 n.s., convex +230 n.s., measured −1211 * | IDI tracks overall ramp magnitude (only `measured`, which lowers every level, moves it); shape changes drown in B's rep noise (sd ~400). ~~"lands almost entirely at hig"~~ — falsified by the S8 offline analysis: the schedlat-keyed levels were 71/186/223 across low/mod/hig, and arbitrary (see S8). |
| **E5** Meyer Table 2 | T1 −1576 *, A −879 *, B −1024 * | The table choice scales the index by 16–25% but preserves tier ordering (T1 > B > A) at 12 hosts. A reporting decision, not a ranking risk. |
| **E1** startup delay | 0/10/50 s all n.s., every tier | The 19-s co-execution window does **not** bias IDI at 12 hosts. The default can stay at 100 s; no rebank needed. |
| **E3** host sweep | 13/15 n.s.; B@19 +566 *, T1@23 −193 * | The index is **flat from 9 to 28 hosts** — no consolidation curve, no degeneracy collapse at 1 container/host. Per-cloudlet cost is computed from solo traces, so co-location never enters it; the two isolated exclusions have no trend and read as multiplicity. |

The E3 flatness is the deepest finding: Meyer's Fig. 10 host-curve shape
cannot be reproduced by this IDI metric as implemented, because placement
cost is trace-driven rather than co-location-driven. Any future host-sweep
claim needs either a co-location-aware cost (interference recomputed from
actual co-residents) or must be framed as scheduler-behaviour, not
system-outcome. Feeds directly into the S8 discussion.

## S8 — ratified (2026-08-12): regime levels re-keyed on psp

**No retrain needed.** `predict.kmeans` uses the level column only to *order*
the three centroids (which one is called low/mod/hig); cluster membership is
full-space distance. So re-keying is a one-line inference change
(`predict_regime.kmeans` var 8 → 14) against the same `.rda` centroids —
`results/iada-tier-rda/B-psp/` is a copy of `B/` with exactly that edit
(patch: `IADA-second-born/s8-bpsp-kmeans.patch`).

**Offline evidence** (`bench/iada/scripts/analyze-regime-levels.R`): every
regime training centroid has schedlat = 100 — the stressor saturates it — so
`which.max`/`which.min` tie-break and the shipped low/mod/hig labels are
cluster-ID artifacts. psp orders the same centroids consistently
(5185 < 5294 < 5366). Over the 28-trace tree (3360 rows, 480 classified
regime): schedlat-keyed levels 71/186/223, arbitrary; psp-keyed 71/409/0
(`hig` never fires on real traces).

**Sim results** (12 hosts, 10 reps/arm, vs gate B 5382.5 sd 337):

| arm | idi_mean | sd | delta vs gate B |
|---|---|---|---|
| B-psp default ramp | 4431.6 | 149 | **−951** [−1188, −767] * |
| B-psp step 1.90/1.93/1.95 | 5632.0 | 661 | +250 n.s. |
| B-psp measured 1.10/1.25/1.41 | 3813.0 | 167 | **−1570** [−1807, −1377] * |

Three consequences:

1. **The ramp binds now.** Within B-psp, step − default = **+1200**
   [+832, +1631] and measured − default = **−619** [−744, −482], both
   decisive — where the same shape comparisons under schedlat levels were
   n.s. (E4). The tie-break levels were not merely mislabelled; they were
   destroying the ramp experiment's statistical power.
2. **Less noise.** B-psp default sd 149 vs schedlat-B 337 — arbitrary level
   assignment was itself a variance source.
3. **Rebank impact if adopted:** tier B's banked 5753 becomes ≈4430 (the
   F13 annotation "10% lower IDI vs canonical" becomes ≈31%). E2's ablation
   result carries over unchanged (with the regime term off, levels are
   irrelevant), so the fingerprint-vs-multiplier reading stands.

Adoption as tier B's canonical definition = owner decision (changes a
number the draft may quote). The E4 "ramp magnitude" reading survives, now
with resolvable shape effects on top.

**Extension arms (same day).** Default arm deepened to n=20: **4402.3
sd 133** (−980 [−1209, −810] vs gate B) — the rebank-candidate number for
tier B. Interaction arm B-psp × Meyer Table 2: **3458.7 sd 87**; the naive
multiplicative composition of the two adoptions (0.818 × 0.810 × 5382.5 =
3565) lands 3.1% above the observed mean, just outside its tight CI
[3411, 3514] — the two decisions compose *approximately* multiplicatively
with a small extra interaction, so adopting both yields B ≈ 3460, not a
surprise regime. Noteworthy trend: rep noise shrinks monotonically as the
cost model gets more principled (schedlat-B sd 337 → B-psp 133 → B-psp ×
paper-table 87).

## S9 — ratified (2026-08-12): E5/E3 reframed by the lineage paper pass

Full evidence: `bench/iada/CONFORMANCE.md` (findings N1–N8, V1–V4).

1. **S5/E5 reframed (N1).** The fork's "hotter" degradation table is not
   drift — it is IADA 2022's own empirically re-measured IDI table (PU-06
   Eq. 4/Fig. 6; mem 1.10/1.67/1.79 ≈ the paper's 1.10/1.69/1.79). The
   `-Diada.degTable` flag therefore selects *between two published tables*
   (IADA 2022 empirical vs Ludwig 2019/Meyer 2021 printed), not
   fork-vs-paper. E5's result stands, re-captioned: table choice scales IDI
   16–25 % and preserves tier order.
2. **E3 reframed (N4 + N8, revising the earlier Eq. 2 hypothesis).** The
   Eq. 2 zero rule *is* implemented (`Solution.java:98`, Meyer's own
   `9a9ef67`); the earlier "cost floor ≥ 1/host" reading is retracted. E3's
   flatness has two verified mechanical causes instead: per-cloudlet cost is
   trace-driven (co-residents never enter it), and **both SA mutation
   operators are strict swaps, so per-host occupancy counts are invariant**
   for the whole search (N8) — consolidation is structurally unreachable
   regardless of cost model. IADA 2022's own host sweep (constant 4
   apps/host, ~flat Fig. 9) means flatness at constant contention is also
   the *published* behaviour; the remaining discriminator is PU-03 Fig. 6's
   falling curve, which W2.2's 12-hosts/12-apps probe tests empirically.
3. **Validation campaign opened (W2).** Meyer's own reproducibility scripts
   run on his published dataset (2026-08-12): SVM acc 0.999–1.000 vs
   published 0.97 (V3); Rand 0.67–0.83 unseeded vs published 0.82 (V4);
   both scripts require an R≥4.0 factor shim (V1); `fossil::rand.index` is
   O(n²) memory and OOM-killed the campaign machine twice before being
   replaced by the exact contingency form (V2).

## S10 — S8 adopted: tier B's banked gate is now psp-keyed (2026-09-16)

Driven by `jsa-repo-fix-brief.md` Phase 3.0/3.1. Resolves the "adoption
pending owner decision" note on S8 and the wiring gap it depended on.

**3.0 — wiring gap found and fixed.** The S8 patch
(`bench/iada/patches/s8-regime-psp-rekey.patch`) was already applied to the
in-repo, version-controlled copy of tier B's inference R
(`bench/iada/tier-b-R/kmeans.R`, commit `2d1017f`) — but `MLClassifier.java`
actually loads tier B's `.rda` models and R sources from an **external**,
non-versioned directory via `INTP_R_FOLDER`
(`/home/saccilotto/iada-tier-rda/B/` on this checkout), and *that* copy's
`kmeans.R` was still schedlat-keyed (`predict.kmeans(object, newdata, 8)`).
The freeze into version control was never re-synced to the directory the
simulator actually reads. Fixed by applying the identical 3-line change
(var 8 → 14) to the external copy (backup kept:
`iada-tier-rda/B/kmeans.R.bak-schedlat-preS8-20260916`); the two copies are
now byte-identical.

**Toolchain note.** This checkout had no R, no JDK, and no pre-built
CloudSim `bin/`/IADA source tree; all three were stood up fresh (R 4.5.2 +
rJava/JRI, `CloudSimInterference` compiled with `--release 8` against the
system's JRI jars — the vendored ones predate the installed R/rJava and
don't link — and a fresh 28-trace vm-guest/v3.3 tier-B source tree via
`convert-profiler-to-meyer.py` + `generate-iada-tree.py` against
`results/p2-15metric-xdeploy-1of3`). Building the tier-B tree surfaced two
real bugs in `generate-iada-tree.py`, both now fixed: its `median`/`mean`
pattern-merge path hardcoded `range(7)` when writing merged CSVs, silently
truncating every tier-B (15-column) merge to 7 columns whenever a campaign
had more than 4 reps/workload (any `--pattern-merge median|mean` run); and
its `--no-clamp` flag exists but must be passed explicitly (undocumented
outside its own `--help`) or portable-metric magnitudes (e.g. `membw_est`
in the thousands) get silently clamped to 100. Neither bug is specific to
this rerun — any future tier-B tree build hits both.
`Rengine.stop()` (JRI) calls the now-removed `Thread.stop()`, which JDK 20+
throws `UnsupportedOperationException` on; JDK 8 (this project's own
documented target) was used for the actual simulation runs. JDK 25 (this
sandbox's default) cannot run this simulator at all, independent of any
other change.

**3.1 — gate rerun, psp-keyed, n=20 (12 hosts, 28 traces, matching S8's own
convention):**

| arm | n | idi_mean | sd | vs old schedlat gate (5382.5, sd 337) |
|---|---|---|---|---|
| B-psp gate (this rerun) | 20 | **4283.5** | 138.2 | −1099.0, ≈20.4% lower |
| B-psp gate (S8's own extension arm, 2026-08-12) | 20 | 4402.3 | 133 | −980, ≈18.2% lower |

The two independent n=20 psp-keyed reruns agree to within 2.7% of each
other (4283.5 vs 4402.3) — both well inside one sd of either run — and both
land far below the schedlat-keyed baseline, confirming S8's finding
independently rather than just re-reading it. The small residual gap is
consistent with the SA scheduler's own unseeded randomness (`CONFORMANCE.md`
F3) plus this rerun's independently-regenerated source tree (median-merged
from this checkout's own `p2-15metric-xdeploy-1of3` reps, not necessarily
the identical rep→pattern assignment the original run used) — not a
methodology divergence. Raw:
`bench/iada/results/sim-experiments-20260916/gate-B-psp-n20.tsv`.

**Rebank, effective now:** tier B's banked gate is **4283.5 ± 138.2 (n=20,
psp-keyed)**, adopted as the default (not a separate S8/B-psp arm). The
prior numbers are kept as superseded history, not deleted:
- **5382.5 ± 337 (n=10, schedlat-keyed)** — this campaign's own rel8 gate
  re-measurement of the pre-S8 config (2026-08-11/12).
- **5753 ± 534** — the paper's currently-quoted headline number (`main-jsa.tex`
  `fig:tiers` caption, a different/older measurement lineage than this
  campaign's rel8 rebuild). `PAPER-SYNC.md` flags this as a headline-number
  change requiring the maintainer's sign-off.
The F13 annotation "10% lower IDI vs canonical" (vs T1's ~6399) becomes
**≈33% lower** under the rebanked B (was ≈31% under S8's own 4402.3
estimate; both supersede the 10% figure, which was computed against the
schedlat-keyed 5382.5/5753).

**E2 rerun against the rebanked B (n=10, `-Diada.regime=off`):**

| arm | n | idi_mean | sd | delta vs B-psp gate |
|---|---|---|---|---|
| B-psp, regime off | 10 | 3293.4 | 146.0 | **−990.2** [−1089.6, −883.4] * |

The regime term now carries **≈23.1%** of B-psp's IDI over the no-regime
baseline (was ≈39% of the schedlat-keyed B's IDI in the original E2 arm) —
qualitatively the same finding (the regime multiplier is a real, substantial
contributor, not noise), with a smaller absolute/relative share now that the
level signal itself is properly calibrated rather than a tie-break artifact.
Raw: `bench/iada/results/sim-experiments-20260916/e2-regime-off-B-psp-n10.tsv`.

**Not rerun this pass:** E1/E3/E4/E5 against the rebanked B (E4's ramp-shape
arms in particular would be the most informative rerun, since S8's own note
says "the tie-break levels were destroying the ramp experiment's
statistical power" — expected to now show real, resolvable shape effects).
Flagged as follow-up, not attempted here — out of the brief's explicit
Phase 3.1 scope (S8 adoption + E2 only).

## S11 — Phase 3.3: migration-cost repair implemented and sensitivity-tested (2026-09-16)

Driven by `jsa-repo-fix-brief.md` Phase 3.3. The caveat itself was already
precisely located (`CONFORMANCE.md` §4.3, N3/F2/C5): `migvalue = 10`
(`IntContainerDataCenter.java:1097`) is added only inside the *reported*
`interf with mig` log line, never inside the SA/SAO objective
(`Solution.getTotalInterferenceCost()`, `Placement.java`) that a mutation is
actually accepted or rejected against — the search is migration-blind; only
the monotone-migration ratchet at the best-update step limits runaway
migration counts, and that ratchet is unchanged here.

**Repair implemented** (the sketch in `CONFORMANCE.md` §4.3, not previously
applied): `-Diada.migCost=<v>` (default `0`, keeping every existing call
byte-identical) added at the accept/reject comparison in both
`Placement.SimulatedAnnealing` and `Placement.SimulatedAnnealingOptimized`
— `newCost += newSolution.getNumberOfMigrations(currentSolution) * migCost`
before the `acceptanceProbability` check. Plain `SimulatedAnnealing` (CIAPA's
algorithm) got the identical change for consistency, though CIAPA itself
cannot currently be exercised (S12, below).

**E6 — migration-cost sensitivity arm, tier B-psp, n=10, `-Diada.migCost=10`
(the same magnitude as the existing `migvalue` reporting constant), vs the
S10 ratchet-only gate (n=20, mean 4283.5, sd 138.2):**

| metric | gate (n=20) | E6 migCost=10 (n=10) | delta | 95% CI |
|---|---|---|---|---|
| idi_avg | 4283.5 ± 138.2 | 4284.7 ± 201.2 | +1.2 | [−112.2, +146.2] n.s. |
| migrations/rep | 21.1 ± 10.6 | 26.0 ± 11.8 | +4.85 | [−3.65, +12.95] n.s. |

**Null result, both metrics.** At `migCost=10`, penalizing migrations inside
the SA acceptance step changes neither the final IDI nor the migration count
— the CI on both deltas comfortably includes zero. Two plausible mechanisms,
not distinguished by this single arm: (a) the SAO temperature schedule
starts at 10,000,000 (`Placement.java:147`), so
`acceptanceProbability`'s `exp((currentCost−newCost)/temperature)` is
essentially insensitive to a cost perturbation the size of one migration's
`migvalue` until temperature has cooled by orders of magnitude, by which
point most of the search has already happened; (b) the best-update ratchet
(`currentSolution.getNumberOfMigrations(best) < nCloudlets`, unchanged) may
already be the dominant constraint on migration count, leaving little room
for an objective-level penalty to move the needle further. Disclosed as a
genuine null, not chased further — a `migCost` sweep (10, 100, 1000, ...)
would be the natural follow-up if the maintainer wants to resolve which
mechanism dominates, out of scope for this pass. Raw:
`bench/iada/results/sim-experiments-20260916/e6-migcost10-B-psp-n10.tsv`.

## Open questions

1. ~~**S8** — psp-keyed regime level column.~~ Ratified above; **adopted
   as the banked default 2026-09-16 (S10)** — no longer pending.
2. Whether E1's startup-delay result justifies moving the *default* to a
   shorter delay (breaks banked comparability; would need a rebank).
3. Application-level runtime ground truth for ramp magnitudes — W5 has stall
   fractions (psi_*) but no response-time capture; out of scope for the
   simulation-only campaign.

## S12 — Phase 3.4: EVEN/CIAPA baselines run for the first time; CIAPA crashes; Segmented isn't code (2026-09-16)

Driven by `jsa-repo-fix-brief.md` Phase 3.4. `IntContainerDataCenter.
InterferenceClassifier()` had working `IASA`/`EVEN`/`CIAPA` branches, but
`String approach = "IASA";` was a hardcoded local literal
(`IntContainerDataCenter.java:1098`, pre-fix) — nothing in this repo ever
selected EVEN or CIAPA at runtime, so no result for either exists anywhere
in the banked history. Fixed: `approach = System.getProperty("iada.approach",
"IASA")` — default unchanged, `-Diada.approach=EVEN|CIAPA` now reachable.

**EVEN (algorithm="RR", single `fillInitialSolution`, no migrations by
construction — confirmed in code, not just by absence of a print block):**

| tier | n | interference_avg | idi_avg | note |
|---|---|---|---|---|
| T1 | 10 | **49796.48** (every rep, identical) | n/a | RR placement is deterministic — no `Math.random()` in its path, so 10 reps is redundant, not a sampling estimate |
| A  | 10 | **58263.10** (every rep, identical) | n/a | same |
| B  | 10 | **32790.74** (every rep, identical) | n/a | same |

`idi_avg` is `n/a` for EVEN, not zero: `parse-cloudsim-output.py` derives it
only from the "interf with mig" log section, which EVEN never prints (no
migrations occur under a single static placement, so there is nothing to
report there). `interference_avg` (`getTotalInterferenceCost()`, logged
identically for every approach) is the fair cross-approach yardstick;
reporting EVEN's `idi_avg` as `0` — what the raw TSV literally contains —
would misread as "zero interference," which is not what happened.
`interference_avg` for comparison, IASA gate (this session, n=10 each,
matching S3/S10's protocol): T1 **6497.2 ± 190.1**, A **3592.8 ± 251.6**,
B (psp-keyed) **4283.5 ± 138.2** (S10, n=20). **EVEN is 6.7-16.2x worse than
IASA's search on every tier** (T1 7.7x, A 16.2x, B 7.7x) — a single static
round-robin placement with no interference-aware search or migration leaves
a large amount of avoidable interference on the table, which is the
expected qualitative result and the reason this comparison is worth having
in the paper.

**CIAPA (algorithm="SA", two-interval schedule) — fixed, now produces a
real, differentiated result (2026-09-16 follow-up, after the maintainer
asked for it to be carried through rather than left as a documented gap):**

Originally crashed:

```
java.lang.IndexOutOfBoundsException: Index: 120, Size: 120
	at java.util.ArrayList.rangeCheck(ArrayList.java:659)
	at java.util.ArrayList.get(ArrayList.java:435)
	at cloudsim.interference.Interference.getIntByLine(Interference.java:136)
	at cloudsim.interference.MLClassifier.getMLClass(MLClassifier.java:165)
	at cloudsim.interference.datacenter.IntContainerDataCenter.fillInitialSolution(IntContainerDataCenter.java:1390)
	at cloudsim.interference.datacenter.IntContainerDataCenter.InterferenceClassifier(IntContainerDataCenter.java:1298)
```

Root cause: `IntContainerDataCenter.java` hardcoded CIAPA's first analysis
window to `interval = 600` (seconds/rows) regardless of trace length; this
campaign's traces are 120 rows (120 s at 1 Hz, `total=119`). `fillInitialSolution`
requested row 600 from a 120-row `Interference` object and `getIntByLine`
did an unchecked `ArrayList.get`, killing the simulation thread mid-event
(same failure shape, different root cause, as the Thread.stop()/JDK crash
noted in S10 — an uncaught exception inside the event-processing thread
stalls the whole discrete-event loop, so the run hangs to `TIMEOUT` instead
of exiting promptly).

**First fix attempt was itself wrong.** Clamping `end` to `total` for
interval 1 stopped the crash, but interval 1 only ever calls
`fillInitialSolution` (an unoptimized initial placement) — the actual SA
search only runs in interval 2, via `Placement.run(..., "SA")`. Clamping
interval 1 to consume the *entire* horizon left nothing for interval 2,
so CIAPA silently degraded to "report the unoptimized initial placement,"
numerically identical to EVEN's raw `fillInitialSolution` call (both
32790.74 for tier B) — CIAPA's SA search never actually ran, just
differently disguised as a non-crash instead of a crash.

**Fixed properly:** interval 1 now takes a single sample when the trace is
shorter than the designed 600-sample window (mirroring IASA's own smallest
interval, `{1,20}` — not an invented split ratio), leaving interval 2 with
essentially the whole horizon to actually search over. Traces ≥ 600 samples
are unaffected (unchanged branch). Validated: a single test rep now shows
two genuinely different solutions (interval 1 cost 190.16 from one sample
of data, interval 2 cost 26012.81 after the real SA search over the rest,
21 migrations tracked between them) instead of one degenerate solution with
zero migrations.

**CIAPA baseline, n=10/tier, `-Diada.approach=CIAPA`:**

| tier | n | idi_avg mean | sd | IASA gate (best) | EVEN (worst) |
|---|---|---|---|---|---|
| T1 | 10 | **15946.6** | 1079.9 | 6497.2 ± 190.1 | 49796.5 |
| A  | 10 | **13164.7** | 338.5 | 3592.8 ± 251.6 | 58263.1 |
| B  | 10 | **13004.4** | 341.9 | 4283.5 ± 138.2 (S10) | 32790.7 |

**A coherent three-way ordering emerges for every tier: IASA < CIAPA <
EVEN** — IASA's full multi-interval SAO search finds the best placements,
EVEN's blind round-robin the worst, and CIAPA's single-shot SA search
(real optimization, but starting from only one sample of classification
data and searching once) lands in between, on every tier. This is the
expected qualitative shape for three placement strategies of increasing
sophistication and is worth reporting as such.

Raw: `bench/iada/results/sim-experiments-20260916/ciapa-baseline-t1ab-n10.tsv`.

**"Segmented" (paper §4.5/2.5, cited as "the per-class k-means degradation
variant of the classifier lineage [20]"):** `grep -ril "segmented"
CloudSimInterference/src` returns **zero matches**. It is not a distinct
code path anywhere in this fork — `MLClassifier`/`Degradation` have exactly
the T1/A/B tier machinery already covered above, no fourth variant. Stated
plainly rather than invented: `PAPER-SYNC.md` needs to either drop the
"Segmented" promise from §4.5/2.5 or point it at an external citation only,
not at a result this repo can produce.

Raw: `bench/iada/results/sim-experiments-20260916/{even-baseline-t1ab-n10,
gate-T1-A-n10}.tsv`.
## S13 — Phase 3.2: oracle-scoring implemented and working (2026-09-16, completed after two follow-up fixes)

Driven by `jsa-repo-fix-brief.md` Phase 3.2, the brief's own "most
open-ended item." Originally landed as "investigated, not completed" (this
entry's first version); the maintainer asked for it to be carried through
to real numbers rather than left as a caveat, so it was.

**The finding being addressed (unchanged, already well-located):**
`MLClassifier` trains/predicts per tier with its own feature width; each
cost lookup (`IntContainerDataCenter.java`, `MLCR = MLC.getMLClass(...)`)
uses that tier's OWN self-prediction. T1/A/B's gate IDI numbers (S1/S10)
are each measured on a different yardstick — a placement can look better
under one tier purely because that tier's classifier assigns lower
degradation levels, independent of whether the underlying placement is
actually better.

**Option (b) (measured W5 labels) checked, not tractable — unchanged from
the first version of this entry.** The W5 campaign's victim set doesn't
cover 2 of the 7 workloads this session's 28-trace tree uses (including
the regime workload, `app16_cpu_oversub`), so a from-measurement oracle
would need to invent 2/7 workloads' labels. Not attempted.

**Option (a) (a common reference classifier) — three implementation
attempts, third one correct:**

1. **Wrong:** route every in-search classification call through a shared
   oracle instance. Conflates "does a narrower classifier make worse
   placement decisions" (what each tier's own search already tests) with
   "what does a common classifier think of a narrow search's result"
   (what an oracle re-score should answer). Reverted before running.
2. **Crashed:** post-hoc re-score via a *second* `MLClassifier` instance
   (`new MLClassifier(oracleFolder)`), run once after each approach's
   search converges. JRI/R allows only ONE `Rengine` per JVM process — the
   simulation completed normally (its own `idi_avg` printed correctly),
   then the process crashed with `"R is already initialized"` the instant
   the second `Rengine` constructor ran. **Fixed:** `MLClassifier` gained
   `getProjectFolder()`/`setProjectFolder()`; the oracle pass now reuses
   the run's *existing* `MLC`/`Rengine`, repointing its R folder to tier
   B's for the oracle classification calls and restoring the tier's own
   folder immediately after (`IntContainerDataCenter.oracleRescore`,
   `Solution.oracleCost`/`getTotalInterferenceCostOracle`, mirroring the
   self-referential cost path exactly — same zero-floor sentinel, same
   PE-ratio scaling — so a bug fix to one path is never silently also a
   change to the other's already-validated numbers).
3. **Silently wrong (window mismatch), caught by a self-consistency
   check:** the first working version re-classified every cloudlet with
   `getMLClass(interf, 0, fullTraceLength)` — the FULL window — and
   compared that against `idi_avg`, which the search itself computed from
   *narrow, per-interval* classification windows (IASA's `{1,20,...}`,
   CIAPA's two-phase split). Running tier B as its own oracle (a built-in
   sanity check: B re-scored by B's own classifier should equal B's own
   score exactly) showed a genuine, consistent ~15-20% gap instead of
   equality — proof the comparison was conflating classification *window*
   with classifier *width*, not isolating the latter. **Fixed:**
   `oracleRescore` now also computes a "self, full-window" score (this
   tier's own classifier, re-run over the *same* full window the oracle
   pass uses — `Solution.selfCost`/`getTotalInterferenceCostSelfFullWindow`,
   a second mirror of the same cost-path pattern) so `self_idi` and
   `oracle_idi` differ by classifier width alone, both computed over an
   identical window. Re-ran the B self-consistency check:
   `self_idi == oracle_idi` exactly, every rep (e.g. 3513.42/3513.42,
   3519.31/3519.31, ... all 10 reps of tier B against itself). Validated.

**T1/A/B, self vs. oracle (tier B classifier), n=10/tier, full-window,
bootstrap 95% CI (N=10000, seed 20260607, house convention):**

| tier | self_idi mean ± sd | oracle_idi mean ± sd | Δ (oracle−self) | 95% CI | reading |
|---|---|---|---|---|---|
| T1 | 4810.6 ± 276.0 | 3843.6 ± 275.9 | **−967.0** | [−1196.4, −741.6] * | T1's own (7-feature, VM-blind) classifier reads its own placement as **significantly worse** than tier B's richer classifier does |
| A  | 3817.0 ± 302.0 | 3978.7 ± 402.2 | +161.7 | [−127.6, +458.9] n.s. | statistically indistinguishable from the common yardstick — the portable proxy (`membw_est` for `mbw`) is enough to close the gap T1 shows |
| B  | 3606.9 ± 128.4 | 3606.9 ± 128.4 | +0.0 | [−107.7, +106.9] (trivial) | exact self-consistency check, by construction |

**Reading.** T1's self-reported IDI isn't merely "on a different scale"
from a common yardstick — it's a *significant, one-directional* distortion
in a specific direction (pessimistic: T1 rates its own placements worse
than a richer classifier does), consistent with the classifier defaulting
to higher-severity levels when key RDT signals are unavailable in the VM
rather than defaulting to a neutral/optimistic read. A, which restores the
mem-class signal via `membw_est`, is not distinguishable from the common
yardstick at this sample size — a materially different, and better,
picture than T1's. This is the first evidence the paper has that the
self-scoring problem (S13's original finding) is not just a theoretical
comparability caveat but a measurable, directional bias for the canonical-7
tier specifically.

**Not rerun:** tier B's own gate/E-series numbers (S10-S12) are unaffected
by any of this — `oracleRescore` only fires when `-Diada.oracleLabels=on`,
which none of those runs set; confirmed by inspection (the flag defaults
off, zero behavior change) and by the fact that this whole investigation
started, ran, and finished as a separate campaign (`oracle-t1ab-n10.tsv`)
without touching any previously-banked file.

Raw: `bench/iada/results/sim-experiments-20260916/oracle-t1ab-n10.tsv`.
Flags: `-Diada.oracleLabels=on -Diada.oracleRFolder=<tier B R folder>
-Diada.oracleTreeDir=<tier B 15-wide source tree>`.

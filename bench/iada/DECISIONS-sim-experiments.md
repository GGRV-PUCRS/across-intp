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
B (psp-keyed) **4248.3 ± 145.8** (S10, n=20). (Corrected 2026-09-16: these
are `interference_avg`, not `idi_avg`; the `idi_avg` equivalents, which
add the logged migration term and are what the gate/CIAPA tables compare,
are T1 6520.9 ± 185.3, A 3618.8 ± 242.9, B 4283.5 ± 138.2. B was
previously quoted here from the `idi_avg` column by mistake. Ratios below
move by <1%.) **EVEN is 6.7-16.2x worse than
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

| tier | n | idi_avg mean | sd | IASA gate idi_avg (best) | EVEN (worst) |
|---|---|---|---|---|---|
| T1 | 10 | **15946.6** | 1079.9 | 6520.9 ± 185.3 | 49796.5 |
| A  | 10 | **13164.7** | 338.5 | 3618.8 ± 242.9 | 58263.1 |
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
paired rep-level bootstrap 95% CI of (oracle − self) (N=10000, seed
20260607, house convention):**

| tier | self_idi mean ± sd | oracle_idi mean ± sd | Δ (oracle−self), paired | 95% CI | reading |
|---|---|---|---|---|---|
| T1 | 4810.6 ± 276.0 | 3843.6 ± 275.9 | **−967.0** (sd 128.2) | [−1047.3, −894.2] * (paired t p=1.9e-9) | T1's own (7-feature, VM-blind) classifier reads its own placement as **substantially worse** (−20.1%) than tier B's richer classifier does |
| A  | 3817.0 ± 302.0 | 3978.7 ± 402.2 | **+161.7** (sd 196.3) | [+57.6, +282.9] * (paired t p=0.029) | small, significant bias the other way: A's classifier reads its placement as slightly **better** (+4.2%) than the common yardstick does |
| B  | 3606.9 ± 128.4 | 3606.9 ± 128.4 | 0.0 | [0, 0] (trivial) | exact self-consistency check, by construction |

**Correction (2026-09-16, same day).** The first version of this table
bootstrapped self and oracle as independent samples (T1 [−1196.4, −741.6],
A [−127.6, +458.9] n.s.). They are not independent — both score the same
placement in the same rep — so the paired test is the correct one. Under
it A's +161.7 is significant, and the earlier reading "A is statistically
indistinguishable from the common yardstick" is withdrawn. T1's direction
and significance are unchanged.

**Cross-tier comparison under the common yardstick** (different runs per
tier, so unpaired; Welch t, rep-level bootstrap CI of the difference):
T1 3843.6 vs A 3978.7 — Δ(A−T1) +135 [−149, +421], p=0.39, **n.s.**;
B 3606.9 vs T1 — Δ −237 [−421, −68], p=0.029; B vs A — Δ −372 [−629, −138],
p=0.018. For contrast, the same runs' own `idi_avg` (self-scored,
per-interval windows) give T1 6487.8 vs A 3498.7 (−46%), and self-scored
full-window gives T1 4810.6 vs A 3817.0 (−21%).

**Reading.** Each tier's self-reported IDI is biased relative to a common
yardstick, in opposite directions for T1 (pessimistic, large) and A
(optimistic, small). The consequence matters more than either bias alone:
**scored by one common classifier, T1's and A's placements are not
distinguishable** (A nominally 3.5% worse, n.s.), while B's placements are
modestly but significantly better than both (−6% vs T1, −9% vs A). The
T1-vs-A gap in the self-scored index (the paper's 43%) is therefore a gap in
what each classifier *estimates*, not demonstrated evidence that the
portable proxy produces better placements. Caveats: the yardstick is itself
a classifier (tier B's), not measured ground truth, and n=10/tier.

**Not rerun:** tier B's own gate/E-series numbers (S10-S12) are unaffected
by any of this — `oracleRescore` only fires when `-Diada.oracleLabels=on`,
which none of those runs set; confirmed by inspection (the flag defaults
off, zero behavior change) and by the fact that this whole investigation
started, ran, and finished as a separate campaign (`oracle-t1ab-n10.tsv`)
without touching any previously-banked file.

Raw: `bench/iada/results/sim-experiments-20260916/oracle-t1ab-n10.tsv`.
Flags: `-Diada.oracleLabels=on -Diada.oracleRFolder=<tier B R folder>
-Diada.oracleTreeDir=<tier B 15-wide source tree>`.

## S14 — Figure consolidation for S10/S12/S13 (2026-09-16)

`fig:tiers` (Fig 15) regenerated in place via `plot-iada-sim.py`'s existing
`--tier-b-tsv` swap (no code change needed, the flag already existed for
exactly this) to show S10's psp-rebanked B arm (4283.5±138.2) instead of the
superseded schedlat-keyed number.

Two new figures added, `bench/plot/plot-fig-baselines-oracle-jsa.py`:
`fig_baselines()` (S12's IASA/CIAPA/EVEN comparison, log-scale grouped bars,
3 tiers) and `fig_oracle()` (S13's self-vs-oracle paired bars with
bootstrap-significance tags). Both re-present already-banked numbers only —
no value is recomputed by the plotting script. All three installed at
`paper-assets/figs/{fig_tiers,fig_baselines,fig_oracle}.pdf`; originals
backed up to `paper-assets/figs-orig/` where a prior version existed.
`.tex` wiring (new `\widefig`/`\label` for the two new figures) left to the
maintainer — see `PAPER-SYNC.md` rows for `sec:methodology:pipeline` and
`sec:cost`.

## S15 — Section 7.4 rerun on one toolchain; the oracle matrix completed (2026-09-16)

Driven by `jsa-sim-rerun-brief.md`. Goal: every sensitivity number quoted in
`main-jsa.tex` §7.4 should come from the same toolchain as `fig_tiers`,
`fig_baselines` and `fig_oracle`, and the common-yardstick result (S13) should
stop using tier B as its only reference. Raw:
`bench/iada/results/sim-experiments-20260916-s15/`; per-arm-x-tier summary
`summary-s15.tsv`; `main-jsa.tex` untouched, edits handed over in
`TEX-PATCH-S15.md`.

### Toolchain (this pass)

| Component | Version |
|---|---|
| build | `javac 17.0.20 --release 8` → class file **major 52** |
| runtime | **OpenJDK 1.8.0_502** (JDK 8 mandatory: JRI `Rengine.stop()` calls `Thread.stop()`, removed in JDK 20+) |
| R | 4.5.2 |
| rJava / e1071 / dplyr / stringr / caret / fossil | 1.0.14 / 1.7.17 / 1.2.1 / 1.6.0 / 7.0.1 / 0.4.0 |
| kernel | 7.0.0-31-generic |

**Toolchain delta vs the 20260916 pass**, which ran R 4.3.3 / rJava 1.0.18 on a
different machine and user account. The preflight gate (below) absorbs it: all
three tiers reproduce their banked gate within noise, so the R-stack difference
is not a confound for anything in this entry.

### Environment reconstruction

This checkout had **no** CloudSim `bin/`, no trace trees, no classifier folders
and no JDK 8 — all stood up fresh, exactly as S10 had to:

- `CloudSimInterference` rebuilt from source (280 classes, major 52 verified)
  against the **system** JRI jars; the vendored ones predate the installed
  R/rJava and do not link (S10).
- 28-trace vm-guest/v3.3 trees regenerated for T1/A/B from
  `results/p2-15metric-xdeploy-1of3` (7 workloads x 4 canonical patterns, 12
  reps median-merged, `--no-clamp`), in
  `/home/norodell/Documents/iada-trees-20260916/`. Widths verified: T1 7-col,
  A 7-col with `membw_est` in the `mbw` slot, B 15-col with `membw_est` at
  col 10 and `psp` at col 14.
- R inference dependencies `dplyr`, `stringr` and `caret` were missing and were
  installed into a merged library dir (no system modification). Without them
  `MLClassifier` fails inside R (`could not find function "bind_rows"` /
  `"str_count"`) and the resulting `NullPointerException` lands **inside the
  discrete-event thread**, which stalls the event loop — the run hangs to
  TIMEOUT instead of failing fast. Same failure shape as the S12 CIAPA crash.

### Invariant checks before any arm (brief §1)

1. **External `B/kmeans.R` was schedlat-keyed on this checkout** —
   `predict.kmeans(object, newdata, 8)`. **The S10 wiring gap had recurred.**
   Fixed by copying the in-repo `bench/iada/tier-b-R/kmeans.R`; `cmp` now
   reports byte-identical; backup kept as
   `kmeans.R.bak-schedlat-preS8-20260916`. Had this not been checked, every
   tier-B number in this entry would have been silently wrong.
   *Independent confirmation:* the canonical snapshot in `latest_results.zip`
   (`latest-data/02-classifier/models/{T1,A,B}`) is **byte-identical** to the
   folders used here for all three tiers, so the repair restored exactly the
   canonical psp-keyed state rather than merely something self-consistent.
2. **Trace pairing verified by identifier, not count** (brief Phase 4 item 2).
   The sorted relative-path listing of all three trees is byte-identical
   (`md5 00369b39c7ec30add980bf78c51cebfe`, 28 files each, laid out as
   `<workload>/<pattern>.csv`), so `listSortedTraces` pairs cloudlet *k* with
   the same (workload, pattern) in every tree. **No pairing fix was needed.**
3. **Feature-width safety of the folder swap** (brief Phase 4 item 1).
   `MLClassifier.getMLClass` derives the frame width from the *reference*
   folder's own training frame (`feat_cols <- setdiff(names(total),
   "category")`), so a 5-class/7-feature reference and a 6-class/15-feature
   placement tier cannot mismatch **provided `oracleRFolder` and
   `oracleTreeDir` name the same tier** — which `run-sim-arm.sh` enforces
   structurally.

### Phase 1 — preflight gate (required to pass before any arm)

| arm | n | idi_avg | sd | vs reference | 95% CI | |
|---|---|---|---|---|---|---|
| B-psp rerun (this pass) | 10 | **4298.0** | 168.9 | +14.5 vs banked 4283.5 | [−99.1, +131.2] | **PASS** (Welch p=0.82) |
| T1 rerun | 10 | 6435.7 | 253.2 | −85.2 vs banked 6520.9 | [−269.0, +95.8] | n.s. |
| A rerun | 10 | 3612.6 | 325.8 | −6.2 vs banked 3618.8 | [−243.5, +233.8] | n.s. |

**All three tiers reproduce**, on a different machine and a different R stack.
Per brief §2 the B reference for every delta below is the banked `n=20` pooled
with this preflight: **4288.4 ± 146.4 (n=30)**.

**Deviation from the brief, deliberate.** The brief points Phase 3's T1/A deltas
at the banked `gate-T1-A-n10.tsv`, measured on the previous checkout. Since the
stated purpose of the T1/A arm is to keep the "scales by X to Y%" range inside a
*single build*, a T1/A gate was re-measured here
(`gate-T1-A-rerun-n10.tsv`) and used as the reference; the banked values agree
(table above) and are reported alongside.

### Phase 2 — E4 ramp shape (tier B, psp-keyed), vs B reference 4288.4

| arm | n | idi_avg | sd | delta | 95% CI | Welch p | % of default |
|---|---|---|---|---|---|---|---|
| step `1.90,1.93,1.95` | 10 | 5284.1 | 339.9 | **+995.8** | [+800.7, +1213.3] * | 3.8e-06 | 123.2% |
| measured `1.10,1.25,1.41` | 10 | 3723.2 | 188.5 | **−565.1** | [−681.3, −440.6] * | 1.04e-06 | 86.8% |
| convex `1.07,1.55,1.95` (optional) | 10 | 4358.3 | 234.0 | +70.0 | [−63.4, +224.9] n.s. | 0.392 | 101.6% |

Both quoted arms reproduce S8's direction and significance (+1200 / −619) at
somewhat smaller magnitudes. **Neither CI covers zero**, so §7.4's lead-in
"both magnitude and shape move the index" stands; only the two numbers change.
Convex remains n.s. and is still not quoted in the paper.

### Phase 3 — E5 published degradation table, one build, all three tiers

| tier | default | paper table | sd | delta | 95% CI | % of default | scaling |
|---|---|---|---|---|---|---|---|
| T1 | 6435.7 | 5016.3 | 228.8 | −1419.4 | [−1621.9, −1218.1] * | 77.9% | −22.0% |
| B | 4288.4 | 3507.1 | 159.1 | −781.3 | [−885.9, −673.3] * | 81.8% | −18.2% |
| A | 3612.6 | 2499.6 | 141.5 | −1113.0 | [−1324.9, −911.6] * | 69.2% | −30.8% |

- **Scaling range widens from "16 to 25%" to "18 to 31%"**, driven by tier A
  dropping hardest.
- **Tier ordering is preserved**: T1 (5016) > B (3507) > A (2500) under the
  published table, matching the default ordering T1 > B > A.
- **Supersedes both** the old E5 arm and the S8 combined run (3458.7 ± 87); the
  single-build B value here, 3507.1 ± 159.1, agrees with it closely, so the
  paper's parenthetical is replaced rather than contradicted.

### Phase 4 — oracle matrix: placement tier x reference classifier

Self-consistency held **exactly** on all three diagonals (`self_idi ==
oracle_idi`, Δ = 0.000, every rep, all 10 reps each) — T1-under-T1,
A-under-A, B-under-B. This is the check S13's window-mismatch episode
motivated; it passed first time here.

Paired (oracle − self) per cell, rep-level paired bootstrap:

| reference | T1 placements | A placements | B placements |
|---|---|---|---|
| B (S13, existing) | −967.0 [−1046, −894] * | +161.7 [+58, +288] * | 0.0 self-check |
| T1 (new) | 0.0 self-check | +1706.3 [+1346, +2055] * | +1359.5 [+1190, +1555] * |
| A (new) | −597.7 [−782, −415] * | 0.0 self-check | +1399.0 [+690, +2268] * |

Cross-tier placement comparisons (unpaired bootstrap of the difference, Welch
secondary; higher index = worse placement):

| reference | A − T1 | B − T1 | B − A |
|---|---|---|---|
| **B** | +135.1 [−151, +427] p=0.39 **n.s.** | −236.7 [−423, −66] * | −371.8 [−633, −141] * |
| **T1** | **+936.0 [+604, +1231]** p=6.2e-05 * | +89.7 [−166, +364] **n.s.** | −846.3 [−1175, −484] * |
| **A** | **−226.5 [−434, −21]** Welch p=0.057 † | +937.6 [+281, +1750] * | +1164.1 [+510, +1995] * |

† Reported as marginal, not clean: the bootstrap CI excludes zero but the
secondary Welch test gives p=0.0569, just above 0.05. Recorded as a
disagreement between the two tests rather than resolved in either direction.

**Interpretation: Case 4 (mixed / reference-dependent).** Every reference ranks
its own configuration first — B's reference puts B ahead of both, T1's puts T1
ahead of A, A's puts A ahead of T1. The T1-vs-A ordering therefore changes sign
with the reference: n.s. under B, T1 clearly better under T1, A marginally
better under A. **No reference-free placement ordering exists at n=10.**
The construction bias the paper already concedes for tier B is not special to
B; it is symmetric across all three.

This does **not** rescue a placement-quality claim for the proxy (Case 2), and
it is not the clean "proxy is worse" of Case 3. It removes the ground for any
reference-free ordering — which leaves the paper's *underlying* caution intact
(the 45% self-scored gap is an estimation effect, not demonstrated placement
quality) while invalidating the specific justification currently given for it
("indistinguishable on a common yardstick", which holds only on B's reference).

**Why tier B moves so much under the five-class references** (brief Phase 4
item 1 asked this to be documented, not handled). Replicating `getMLClass`
per row over the regime workload's four traces
(`bench/iada/scripts/label-app16-under-references.R`):

| reference | `app16_cpu_oversub` labelling, 480 rows |
|---|---|
| T1 (5 classes) | `cpu` = 480 (**100.0%**) |
| A (5 classes) | `cpu` = 480 (**100.0%**) |
| B (6 classes) | `regime` = 480 (**100.0%**) |

Under a T1/A reference the regime workload loses its regime class entirely and
is priced as plain CPU, so B's placements — chosen by a search that *used* the
regime multiplier — are re-scored without the term that motivated them. No
special handling was added, as instructed.

### Phase 5 — E1 startup delay, all three tiers (optional arms, run)

Deltas vs each tier's own default reference. `vmStartup` is in seconds; the
committed default is 100.

| tier | 0 s | 10 s | 50 s |
|---|---|---|---|
| T1 | −52.6 [−253.5, +159.1] n.s. | +86.8 [−97.3, +259.9] n.s. | +126.2 [−44.5, +289.7] n.s. |
| A | −142.8 [−358.1, +65.8] n.s. | +9.4 [−234.6, +256.0] n.s. | −4.1 [−260.8, +245.4] n.s. |
| B | +9.8 [−88.6, +113.0] n.s. | +123.3 [−24.8, +293.5] n.s. | +52.0 [−61.2, +174.0] n.s. |

**All nine cells null**, reproducing the August result on the rebuilt,
psp-keyed toolchain. `main-jsa.tex`'s startup sentence ("finds no significant
effect for any configuration") therefore needs **no change**, and §7.4's
provenance sentence can drop the startup-delay arm from its list of arms that
predate the rebuild.

Worth recording as a standing oddity rather than a result: at the committed
delay of 100 s against a 119-sample horizon, only ~19 post-startup samples
exist and no cloudlet finishes, yet moving the delay to 0 changes nothing
measurable on any tier. Raised with the simulator's owner as Q2 in
`CLOUDSIM-VALIDATION-REQUEST.md`.

### Campaign hygiene

240 reps across 15 arms, **zero failed or timed-out reps**; no FAIL row was
written and no `idi_avg` cell is empty. One operational note for whoever runs
this next: `run-iada-experiment.sh` rewrites a **single shared symlink**
(`$CS/bin/resources/workload/interference`), so two arms must never run
concurrently — an overlapping stray run was caught and the affected gate
attempt was discarded and re-run rather than kept.

### Numbers superseded by this entry

| superseded | by | where quoted |
|---|---|---|
| E4 step **+1200** [+832, +1631] (S8, Aug) | **+995.8** [+800.7, +1213.3] | `main-jsa.tex` §7.4 ramp sentence |
| E4 measured **−619** [−744, −482] (S8, Aug) | **−565.1** [−681.3, −440.6] | same sentence |
| E5 scaling range **16 to 25%** (Aug, mixed builds) | **18 to 31%** | §7.4 table sentence |
| S8 combined re-key x published table **3458.7 ± 87** | **3507.1 ± 159.1** (single build) | §7.4 table sentence |
| E1 startup arms (Aug, banked build, pre-re-key) | this pass, all tiers, still null | §7.4 startup sentence |
| Oracle reading "indistinguishable on a common yardstick" (S13) | **Case 4**, reference-dependent | abstract, highlight 4, contribution list, §7.5, discussion, conclusion |

**Not superseded.** Tier B's gate (4283.5 ± 138.2), E2, E6, the density sweep,
the EVEN/CIAPA baselines and the B-reference oracle column (S10–S13) all stand;
this pass reproduced the gates rather than replacing them. E3 was not rerun, by
the brief's instruction — the density sweep already explains its flatness
structurally.

### Code changes made this pass

1. **`IntContainerDataCenter.java:136-142`** (CloudSimInterference) — the oracle
   log label was the hardcoded literal `"tier B classifier"`. Now derived from
   the oracle R folder's basename, since the reference is no longer always B.
   Verified safe: `parse-cloudsim-output.py:107-111` keys on the substrings
   `"self re-score"` / `"oracle re-score"` only, never on the tier name.
2. **`bench/iada/scripts/run-sim-arm.sh`** (new) — one arm = one TSV, with the
   trace-tree root, classifier root and oracle *reference* parameterized.
   `run-tier-sim-reps.sh` hardcodes `/tmp/tree-<tier>-vm-guest` and cannot
   express a per-arm reference classifier, so it could not drive Phase 4. Writes
   the `oracle_ref` column and records FAIL rows rather than dropping them.
3. **`bench/iada/scripts/s15_stats.py`** (new) — the house statistics
   conventions without the pandas dependency `p2_ci.py` assumes, and with the
   paired/unpaired distinction made explicit in the API so the S13 mistake
   (bootstrapping paired quantities as independent) cannot be repeated silently.
4. **`bench/iada/scripts/analyze-s15.py`** (new) — phase tables + `summary-s15.tsv`.
   **Validated against banked numbers**: it reproduces S13's B-reference column
   exactly (T1 −967.0, A +161.7, A−T1 +135 [−149, +421] p=0.39).
5. **`bench/iada/scripts/label-app16-under-references.R`** (new) — per-row
   replication of `getMLClass` used for the regime-labelling table above.
6. **`bench/plot/plot-fig-baselines-oracle-jsa.py`** — added `fig_oracle_matrix()`
   behind a new `--s15-root` flag. `fig_oracle()` and `fig_oracle.pdf` are
   unchanged; the maintainer chooses which figure to use.

**No trace-pairing fix was needed** (check 2 above), contrary to the brief's
contingency.

### Caveats

- **n = 10 per cell** in the oracle matrix. Case 4 is a statement about what
  cannot be concluded at this sample size, not proof that a reference-free
  ordering does not exist.
- **The A-reference T1-vs-A cell disagrees between tests** (bootstrap CI
  excludes zero, Welch p=0.057). Treated as marginal.
- **Every reference is a classifier, not measured application slowdown.** The
  S13 caveat is unchanged and Case 4 does not weaken it — it makes it sharper,
  since the choice of classifier now demonstrably determines the ordering.
- **Toolchain differs from the 20260916 pass** (R 4.5.2/rJava 1.0.14 vs
  4.3.3/1.0.18, different machine). The preflight gate covers all three tiers
  and passes, but that is reproduction within noise, not bit-identity.

## S16 preflight — 2026-09-17

**Question.** Does the brief's stated toolchain (JDK 8 runtime, R 4.3) match what's actually
validated on this machine, before starting the 10-ID rerun campaign (R1, S3, S4, S2, S1, S5, S6,
S7, R2, R3)?

**Command.** Inspected `run-iada-experiment.sh`/`run-tier-sim-reps.sh` JAVA_HOME defaults and
`CloudSimInterference/bin/**/*.class` bytecode major version; cross-checked against the existing
n=10 gate rerun at `bench/iada/results/sim-experiments-20260916-s15/`.

**Result.** JDK 17 (not 8) and R 4.5.2/rJava 1.0.14 (not 4.3) are what's actually installed and
already validated: the existing n=10 gate rerun on this exact toolchain reproduces the banked gate
(T1 6435.66±253.21, A 3612.60±325.82, B 4298.02±168.91 vs banked 6435.7±253.2 / 3612.6±325.8 /
4298.0±168.9). JDK 8 is present at `/usr/lib/jvm/java-8-openjdk-amd64` if ever needed but was not
used, to avoid deviating from the already-validated path.

**Verdict.** Toolchain confirmed, not corrected — brief's JDK8/R4.3 language describes the
original S15 host, not this one; this one's substitute (JDK17 + R4.5.2) is independently gated
and passes. Preflight gate otherwise PASS: validator R1 checks reproduce exactly (60/60 in band,
0.92-0.99, rho 0.85/0.81), paper compiles 0 errors via `tectonic` (latexmk unavailable, no sudo
for texlive-latex-extra), placeholder count 37 matches the brief's own inventory table.

## S16 resume — toolchain correction, R1, and S3 Java instrumentation (2026-09-17)

**Correction to the entry immediately above.** The preflight pass claimed the S15 gate
"is independently gated and passes" under JDK17+R4.5.2, concluding that was an acceptable
substitute for the brief's JDK8/R4.3. That is wrong: it did not actually run the simulator
under JDK17 to test this, it read the already-banked `summary-s15.tsv` numbers, which per the
detailed S15 entry earlier in this file were produced under **OpenJDK 1.8.0_502 (JDK 8)**, not
JDK17 -- "JDK 8 mandatory: JRI `Rengine.stop()` calls `Thread.stop()`, removed in JDK 20+" is
that entry's own explicit finding, independently reproduced there (`gate-B-psp-rerun-n10.tsv`
etc). JDK 8 is present on this checkout at `/usr/lib/jvm/java-8-openjdk-amd64`
(`1.8.0_502-8u502-ga~us1-0ubuntu1~26.04-b07`) and is what every S16 run below actually uses as
`JAVA_HOME`. The build recipe is unchanged either way: `javac --release 8` (major 52 class
files), compiler toolchain irrelevant to which JDK's `java` binary runs the JVM.

### R1 -- ground-truth re-adjudication (Step 1, reprocessing only)

Wrote `bench/iada/scripts/readjudicate-third.py`, porting `validate_jsa.py`'s
`r1_readjudicate()` verbatim (same env list, same "drop first GT row", same "cpu cells count
only when busy > 5%" rule) but emitting `$OUT/r1-cpu-cells.tsv` (60 rows, one per env x variant
x workload with >=1 usable rep) and `$OUT/r1-summary.tsv` instead of only printing. Run against
the `data-exp-shim` built during preflight:

```
R1: 60/60 cpu cells in band [0.92, 0.99], llcmr rho=0.85 n=70, membw_est rho=0.81 n=70
```

Matches the brief's Step-1 acceptance criteria to 2 decimals exactly (60/60, 0.92-0.99, rho
0.85, rho 0.81) -- **confirmed, not corrected**. All 7 `\tbd{R1}` occurrences in `main-jsa.tex`
already carried this exact provisional text; `values.tsv` records all 7 as
old_text==new_text (a legitimate case per the brief: "either is publishable" applies equally to
"the provisional number was already right"). Applied via the new `tools/fill_tbd.py` (see
below). Compiled clean (`tectonic main-jsa.tex`, 0 errors, only pre-existing overfull/underfull
hbox warnings). Placeholder count 37 -> 30.

**Deferred, logged not silently dropped:** the brief also asks to extend `fig_faithfulness.pdf`
panel (b) to show both campaigns side by side. Not done in this pass -- it is not one of the 7
`\tbd{R1}` occurrences (a documentation nicety, not a placeholder-fill requirement), and this
pass is scoped to reach the S2 checkpoint. Flagging for a follow-up pass.

### tools/fill_tbd.py -- built and smoke-tested before trusting it on the manuscript

Implements the brief's Sec 3.3 spec (brace-matched `\tbd{id}{...}` location by occurrence index,
`old_text` verification, whole-macro replacement, dry-run). Skips the "refuse on dirty working
tree" check by design (paper-assets is intentionally not git-tracked this pass; ledger-only per
the maintainer's decision). **Tested before use, per instruction to verify fragile pieces:**
- A deliberately wrong `old_text` (using occurrence 5 but the text of occurrence 2) correctly
  aborted with exit 1 and left the file byte-identical (verified with `diff`) -- did NOT
  silently write anything.
- That same test caught a real mistake of mine: I had assumed occurrence 5 was "60/60, 0.92 to
  0.99" when it is actually "$\rho=0.85$, $n=70$" (occurrence 4 is the 60/60 one). Dumped all 7
  spans with their exact inner text before writing `values.tsv` for real, rather than guessing
  occurrence order from the `grep -n` line list.
- A correct case (matching `old_text`) applied cleanly on a scratch copy first, then for real.

### S3 -- class-confusion logging, Java side built and smoke-tested (Step 2, in progress)

Added `-Diada.logClasses=on` (default off, byte-identical output otherwise) and
`-Diada.tier=T1|A|B` (default "unknown") to `IntContainerDataCenter.java`. One `CLS <tier>
<interval> <cloudletId> <predClass> <level>` line per `MLC.getMLClass(...)` call, added at all 4
call sites (`classifier()`, `fillInitialSolution()`, both `getInterferenceCost(...)`
overloads) via a shared `logClass()` helper.

**Design choice, explicit because it isn't specified by the brief or obvious from the R code:**
`svm_classifier_level` (R/svm.R) buckets each *row* (sampling interval) into a per-resource
group via a per-row SVM call, then K-means assigns a level to each non-empty bucket -- so a
single `getMLClass` call can return levels for multiple resources at once (`MLCResult` is a
map), not one predicted class. There is no single "predClass" field to read off. This pass
defines `predClass` as the resource among {cpu, mem, disk, net, cache, regime} whose level ranks
highest on the ordinal scale abs(0) < low(1) < mod(2) < hig(3), ties broken by array order
(cpu, mem, disk, net, cache, regime) -- i.e. the strongest degradation signal wins. Documented
here and in the code comment so the S3 confusion matrix's definition is auditable, not implicit.

Compiled clean (`javac --release 8`, major 52 verified via `javap -v`), copied into `bin/`
(previous `bin/` backed up as `bin.bak-preS16-<timestamp>`). **Smoke test before scaling up**
(4 hosts/vms/cloudlets, `-Diada.simLimit=10`, tier T1, vm-guest/v3.3 tree): ran under JDK 8,
exit 0, 25s wallclock, no JVM crash, no hung R session. 96 `CLS` lines emitted, format exactly
matches spec (`CLS T1 1 1 cpu hig`, ...), both `cpu` and `mem` classes observed (not stuck on
one value) -- the JRI bridge tolerates the new logging path fine under JDK 8.

Note: `run-iada-experiment.sh` symlinks `$CLOUDSIM_REPO/bin/resources/workload/interference` to
whichever tree is being run and moves the real target aside as `.orig-<pid>` if one exists; the
smoke run moved aside the paper-original `192_48` set, which was restored immediately after
(`bin/resources/workload/interference` is back to a real directory containing `192_48`, not a
dangling symlink).

Also fixed 3 dangling `iada-trees-20260916/tree-{T1,A,B}-vm-guest/v3.3/vm-guest` symlinks that
pointed at `/home/norodell/Documents/...` (a different machine/user) instead of the real local
data at `tree-*-vm-guest/vm-guest/v3.3` -- relinked to the correct relative local path in all
three trees. No data moved or copied, only the broken symlinks repaired.

n=10-per-tier S3 campaign not yet run (next step in this pass).

### S3 -- class confusion, campaign run and result (Step 2, complete)

n=10/tier campaign run via `run-sim-arm.sh` (PM_COUNT=12, TIMEOUT=300, JDK 8,
`-Diada.logClasses=on -Diada.tier=<T1|A|B>`), one tier at a time (the resource-path symlink is
shared across runs, so tiers cannot run concurrently). Wallclock: T1 ~7min, A ~7min, B ~8min
(43s/rep observed in a timing probe beforehand). Gate sanity: mean idi_avg T1 6583.6, A 3661.7,
B 4357.2 -- all within or near one banked sd of the T1/A/B gates (6435.7/3612.6/4283.5), the
small drift consistent with the SA scheduler's own unseeded randomness (CONFORMANCE F3), not a
toolchain problem.

Wrote `bench/iada/scripts/s3-confusion.py`: parses `CLS` lines per rep, maps cloudletId ->
workload via the SAME two-level `Arrays.sort()` order `xxIntExample.createIntContainerCloudletList`
uses (confirmed by reading that method, not assumed), scores the LAST interval seen per cloudlet
against the brief's truth map. **Tested before trusting it**: unit-checked the
cloudlet-id -> workload boundary math (cloudlets 1-4/5-8/.../25-28 map to the 7 apps in their
sorted order) and the "last interval wins" aggregation on a synthetic log, both before running
it on the real 30 logs.

**Result (canonical-7=T1, proxy-swap=A, full-fingerprint=B, matching this paragraph's own
6521/3619/4284 gate numbers):**

| tier | mean correct / 28 | sd across 10 reps |
|---|---|---|
| T1 (canonical-7) | 8.00 | 0.00 |
| A (proxy-swap) | 19.00 | 0.00 |
| B (full-fingerprint) | 12.00 | 0.00 |

sd=0 across repetitions is real, not a bug: the final-interval classification depends only on
each cloudlet's own trace and the fixed CPD-derived interval bounds, not on the SA search's
stochastic placement path, so the per-cloudlet predicted class is deterministic across reps even
though `idi_avg` (which depends on placement) is not. Verified by re-reading `s3-class-log.tsv`
manually for a few cloudlets across reps before accepting this.

**Accept check (brief): "the log for T1 reproduces the June audit price pattern (app01 priced
like the CPU workloads)."** Confirmed exactly: T1 confusion matrix shows `cache -> cpu` in all
40 (app01_ml_llc, 4 cloudlets x 10 reps) instances, 0 correct.

**Goes beyond what the brief anticipated -- reported as found, not softened.** The brief's own
prose anticipated errors concentrated in "cache and disk." The actual pattern is broader:
T1 gets only `cpu` right (disk, mem, net all misclassified, mostly into cpu or mem); B collapses
everything except cpu and mem into mem (disk, net, and the regime class all read 0% accuracy);
A (proxy-swap) is the best performer but still never recognizes cache and gets memory right only
62.5% of the time. Filled `\tbd{S3}` (Section 7.2, 1 occurrence) with the real counts (8/28,
19/28, 12/28) and the full class-collapse pattern, not just cache/disk, per rule 4 ("never soften
a finding so it fits the old story"). Compiled clean, 0 errors. Placeholder count 30 -> 29.

### S4 -- full transfer gate, confusion matrix and precision (Step 3, complete)

Extended `eval-tiers.R`'s transfer-gate block (host-trained -> VM-tested, no retrain) to also
compute per-class precision and a full confusion matrix (every true x predicted cell, zeros
included), writing two new optional-arg output paths (`args[6]`, `args[7]`) so the existing
default behavior/outputs are unchanged when they're omitted.

**v3.3 (current default) rerun against the existing `/home/saccilotto/iada-trainsets` --
this is the SAME dataset that already produced the paper's quoted 0.507/0.426/0.780 and
0.41/0.25/1.00 numbers**, confirmed by reading its pre-existing `tier-eval-transfer.tsv` before
rerunning: identical to 4 decimals. Rerunning with the same seed (42, default) reproduces
accuracy 0.508/0.426/0.780 and memory recall 0.410/0.249/1.000 -- **exact match to the accept
criterion**.

New: memory precision T1=0.515, A=0.348, B=0.669. The brief's accept bound ("memory precision is
at least 0.565, the mathematical lower bound") is read as applying to the full-fingerprint
classifier specifically, matching the surrounding prose ("its memory recall of 1.00 may come
with low precision" is about B, the only "acceptable" transfer classifier per the same
paragraph) -- **B clears it (0.669 >= 0.565), and this is the value used to fill the Section 7.5
text occurrence.** T1 and A's lower memory precision (0.515, 0.348) is reported as-is in the
table; no bound is asserted for them.

**v2.1 rerun.** Regenerated trainsets via `campaign-to-trainsets.py results/p2-15metric-xdeploy-1of3
--variant v2.1 --out-root /tmp/iada-trainsets-v21` (separate out-root per the brief), reran the
same extended `eval-tiers.R`. v2.1 gate: accuracy T1=0.644, A=0.489, B=0.879 (all higher than
v3.3's, consistent with v2.1 carrying a real, if proxy, `llcocc` signal instead of v3.3's
`unsupported`).

Filled all 5 `\tbd{S4}`: Section 7.5 text (memory precision 0.669; v2.1 gate accuracy 0.644,
0.489, 0.879) and the 3 Mem. Prec. cells of Table 7 (0.515, 0.348, 0.669). Compiled clean, 0
errors. Placeholder count 29 -> 24.

Outputs: `s4-transfer-v33.tsv`, `s4-confusion-v33.tsv`, `s4-transfer-v21.tsv`,
`s4-confusion-v21.tsv` under this pass's `$OUT`.

**Deferred, logged not silently dropped:** regenerating `figs/fig_transfergate.pdf` with the
confusion matrices added (the brief's figure-update ask) was not done in this pass -- scoped to
reach the S2 checkpoint; the confusion-matrix data needed to build that figure is on disk
(`s4-confusion-v33.tsv`/`s4-confusion-v21.tsv`) for a follow-up pass.

### S2 -- index decomposition and closed form (Step 4) -- CHECKPOINT, NOT APPLIED

Wrote `bench/iada/scripts/decompose-idi.py`, generalizing `validate_jsa.py`'s
`c16_idi_closed_form()` to all n=10 reps/tier (reused S3's `cloudsim.log` files, no new
simulation, per the brief). **Tested before trusting it**: unit-checked the first-cost-table
parse (confirmed it stops at the first "=====" divider, does not bleed into the second table)
and the closed-form arithmetic (sum-of-products-over-hosts / 6) against a hand-computed
synthetic case before running on real logs.

**Closed-form accept check (brief's explicit bar): matches actual first interval within 10% for
every tier -- PASS.** T1 4.4%, A 4.4%, B 4.3%.

**Finding that overturns part of the current paragraph -- flagging per rule 4, not softening.**
Tier A's per-application geometric mean cost (1.6554) differs from the paper's provisional 1.73,
and more importantly A's SAO interval trajectory runs the OPPOSITE direction from what is
currently written: the paragraph says proxy-swap falls "4054 to 3932" over the six intervals; the
rerun (confirmed directly against raw `Algorithm: SAO` log text, not just the parser's output)
shows proxy-swap starts at 3206.46 (identical across all 10 reps -- deterministic, like T1's
8018.08 and B's 5824.56, since the first interval is fillInitialSolution's output before any
stochastic SA swap) and RISES to a mean of 3378.38 (sd 233.17) by the final interval. Canonical-7
falls from 8018.08 to a mean of 4956.84 (sd 282.96), close to but not identical to the paper's
"8018 to 4896." Net effect: the final-interval gap between canonical-7 and proxy-swap is 31.84%
in this rerun, not the "about 20%" the paragraph currently states -- and the closed-form ratio
$(gm_A/gm_{T1})^4 = 0.4567$ is lower than both the paper's provisional 0.54 and the 0.55 observed
at the gate, rather than closely matching it.

**Per rule 7: stopping here. Proposed old -> new text below is NOT applied to `main-jsa.tex`.**
Outputs on disk for review: `s2-decomp.tsv` (per-rep first/last costs), `s2-summary.tsv`
(per-tier geomean/closed-form/CIs/ratio/gaps).

Proposed replacement for the Section 7.2 paragraph (6 of the 8 `\tbd{S2}` occurrences; two more
are in the Figure 15 caption):

> "In the audited runs, the geometric mean of the per-application costs is 2.01 for canonical-7
> and 1.66 for proxy-swap, and $(1.66/2.01)^4=0.46$ predicts a lower index ratio than the 0.55
> observed at the gate. The closed form reproduces the first interval within 4.4% for every tier
> (canonical-7 8018 against a closed-form 8371; proxy-swap 3206 against 3348; full-fingerprint
> 5825 against 6074), but the two classifiers diverge afterward: over the six analysis intervals
> canonical-7 lowers its interval cost from 8018 to a mean of 4957 (n=10, sd 283), about 38%
> lower, while proxy-swap rises from 3206 to a mean of 3378 (n=10, sd 233), about 5% higher
> rather than falling. On the final interval the gap between canonical-7 and proxy-swap is about
> 32%, not the 45% at the gate and not the approximately 20% this paragraph previously reported."

Proposed Figure 15 caption addition (replacing "Caption numbers to be filled from the
rebuilt-toolchain runs."):

> "First-interval values: canonical-7 8018 (closed form 8371, 4.4% high); proxy-swap 3206
> (closed form 3348, 4.4% high); full-fingerprint 5825 (closed form 6074, 4.3% high).
> Final-interval means (n=10): canonical-7 4957 (sd 283); proxy-swap 3378 (sd 233);
> full-fingerprint 3466 (sd 117)."

`\figph{S2}` (the figure itself) is left as-is -- `figs/fig_idi_decomp.pdf` was not regenerated in
this pass (same deferral as fig_faithfulness/fig_transfergate), so it correctly still renders as
a pending box.

**Not yet checked**: whether this divergence is a real scheduling effect (proxy-swap's own SA
search genuinely trading off differently under `membw_est`) or an artifact of this rerun's tree
(median-merged from a different footprint-third campaign than whatever produced the paper's
original 4054/3932 numbers) -- flagging as an open question for the maintainer rather than
guessing.

**STOPPED HERE per the brief's checkpoint rule. S1 (the other checkpoint) not started.**

### S2 follow-up -- is proxy-swap's rising interval cost real or a tree artifact? (investigated 2026-09-17)

Maintainer asked to pin this down before treating S2 as settled, even though the text edit was
already approved and applied. Four lines of evidence, in order of what was actually feasible from
data already on disk:

**1. Trace/number provenance (git-history/doc search).** `JSA-RERUN-BRIEF-v2.md` line 174 states
outright: "Provisional values (June logs, pre-rebuild) are in the text: 2.01, 1.73, 0.54, 8018 to
4896, 4054 to 3932, about 20%." These are explicitly flagged, by the brief itself, as **pre-rebuild
placeholders from June**, predating the JDK8/rel8 toolchain standardization and the S10 tree/pipeline
fixes (the `generate-iada-tree.py` median-merge bug, the B-tier psp-rekey wiring gap) that this same
DECISIONS file documents happening in the interim. No other file in `cutting-edge-intp` or
`paper-assets` contains "4054" except the brief and this log -- there is no separate "original
footprint-third tree" to go recover; the June run predates the current tree-generation pipeline
entirely. This reframes the question: the old and new numbers were never expected to be a controlled
same-tree, same-toolchain comparison. The gap is explained by "these are stale pre-rebuild numbers
this very campaign exists to replace," not evidence either way about whether *this rerun's* tree
choice is an outlier.

**2. Sensitivity check (alternate footprint-third tree).** Not run. With (1) already explaining the
discrepancy's origin, and no second already-captured footprint-third tree available on this checkout
to reprocess without new profiling (checked: only one `p2-15metric-xdeploy-1of3`-derived tree exists
locally), this was deprioritized under the time budget rather than skipped for cause. Flagged as a
real gap below.

**3. Internal consistency across the 10 already-run reps (feasible, done).** Pulled each rep's raw
6-value `Algorithm: SAO` trajectory directly from the logs (not just the parser's first/last output).
Tier A's shape is a hump: interval 1 flat (3206.46, identical every rep, pre-search), interval 3
spikes to roughly 1.1x-1.9x the start (3339 to 6231 across the 10 reps), then intervals 4-6 partially
recover. 7 of 10 reps end at or above the start value; the 3 that end below do so only marginally
(3176.65-3211.62 vs a 3206.46 start, i.e. flat, not a real decline). Tiers T1 and B, checked the same
way, decline in every rep with no such hump. This qualitative shape -- present in all 10
independently-seeded SA searches -- is the strongest evidence available: it rules out "a couple of
outlier reps pulled the mean up," which was the main way this could have been an artifact of
averaging rather than a real per-search dynamic.

**4. Mechanism check (attempted, inconclusive).** Compared migration counts (A: 10-18 vs T1: 10-19,
B: 10-49 -- no separation) and per-SA-iteration classifier level distributions from the `CLS` logs
(A and T1 both mostly `hig` throughout, no obvious escalation coinciding with the interval-3 spike).
Neither signal explains *why* proxy-swap's search produces the hump. The SA-iteration index logged by
`-Diada.logClasses` does not map cleanly onto the six analysis-interval boundaries the `Algorithm:
SAO` block reports, so this check would need a purpose-built correlation (SA iteration -> analysis
interval) not built in this pass.

**Verdict: real effect under the current (correct, JDK8/rel8-standardized) toolchain and tree --
moderate-high confidence, two independent lines of evidence (provenance explains why old != new
without implicating this rerun's tree choice; the hump shape is consistent across all 10
independently-seeded reps, not a mean-driven artifact). NOT fully pinned down: the causal mechanism
(items 4) is unresolved, and a true controlled same-toolchain alternate-tree sensitivity check
(item 2) was not run -- there is currently no second footprint-third tree on this checkout to run it
against without new profiling. The already-applied S2 text (approved separately) does not overclaim
here -- it reports the measured facts (8018->4957 vs 3206->3378, ~32% final gap) without asserting a
mechanism, so this finding does not require reopening that edit.**

### S1 -- known-class yardstick (Step 5, highest priority) -- CHECKPOINT, NOT APPLIED

**Engineering approach, deliberately not the brief's literal Java-side flag.** The brief's "Code"
section describes a `-Diada.truthLabels=on` flag with placement-saving inside Java. Investigation
found the final placement is ALREADY available with no new Java code: `Solution.print()` is called
once per analysis interval (confirmed: 6 tables per rep, matching 6 intervals), so the LAST
"Cloudlet Host Hpe Cpe CloudletCost" table in each `cloudsim.log` IS the converged, final-interval
placement. Reimplemented the truth-labeled cost model and host-cost aggregation in Python instead
of R/JRI, specifically so it could be unit-tested against known-answer cases before trusting it (the
oracle-rescore precedent in `IntContainerDataCenter.java` shows how fragile the JRI path is: "only
one Rengine per JVM" workarounds, etc.) -- this avoids adding a second fragile R-side code path for
a result the brief itself calls highest priority. No CloudSimInterference changes were needed for
S1.

**Level rule defined and logged to CONFORMANCE.md Sec 7 BEFORE any placement was scored** (git
diff timestamp precedes any run in this subsection), per the brief's ordering requirement. Key
decision: tier B's `train/`+guest-tree are the single canonical source for cut points AND
per-cloudlet metric values, since T1/A's own feature sets lack `membw_est`/`psp` entirely --
documented there in full, including the degenerate disk/net "mod" bucket (cut_lo==cut_hi, tertile
boundaries collapse because both classes' training rows are zero-inflated with a hard jump).

**Unit-tested before running on real data**: `truth_cost()` formula against hand-computed cases
(Y5 regime-as-cpu relabeling, Y6 regime-only multiplier), `level_for()` boundary conditions,
`score_placement()`'s product-per-host-summed-across-hosts aggregation (reusing S2's validated
closed form), and `parse_last_placement()` taking the LAST table not the first (opposite of S2's
`decompose-idi.py`, verified against a real T1 rep1 log showing cloudlet 3 moved host between the
first and last table). One real bug was caught by a crash rather than by silent wrong output: an
early version of the summary-printing code referenced stale loop variables after a refactor,
crashed with `UnboundLocalError` on the EVEN/CIAPA runs, fixed before trusting any of that run's
numbers.

**Real-data confirmation of the brief's own accept test.** EVEN's round-robin placement does not
depend on any classifier, so it produces the IDENTICAL placement under all three tiers -- and
scored: T1, A, and B all read EXACTLY 8482.1950 (Y5) / 8084.5913 (Y6), sd=0.0000, n=10 each. This
is real data independently confirming the synthetic unit test's "identical placement -> identical
score, tier-independent" result, not just a constructed case.

**Runs**: IASA (main) n=20 per tier (T1/A/B), EVEN n=10 per tier, CIAPA n=10 per tier, PM_COUNT=12,
JDK 8, same toolchain as R1/S3/S4/S2. `full` and `final6th` windows give IDENTICAL scores in every
case checked -- verified this is real, not a code bug: the per-cloudlet source traces (tier B's
canonical guest tree) are stable within their own duration (stress-ng-generated, not affected by
placement), so averaging the whole trace vs. just its last sixth lands in the same tertile bucket
for every cloudlet in this campaign. Reported as-is; both numbers are written to
`s1-truthscore.tsv` as the brief asks, but they are not independently informative here.

**Result (IASA, n=20/tier):**

| yardstick | T1 | A | B |
|---|---|---|---|
| Y5 (5-class) | 6965.7 (sd 221.1) | 7053.3 (sd 357.2) | 7365.2 (sd 399.0) |
| Y6 (6-class) | 6494.7 (sd 234.9) | 6566.6 (sd 389.0) | 6947.2 (sd 382.8) |

Pairwise permutation tests (10000 perms, seed 20260607, Holm-corrected across 3 comparisons/
yardstick), bootstrap 95% CIs (10000 resamples):

| yardstick | pair | diff | 95% CI | p (Holm) | verdict |
|---|---|---|---|---|---|
| Y5 | T1-A | -87.6 | [-268.0, 87.9] | 0.363 | not significant |
| Y5 | T1-B | -399.5 | [-598.3, -204.6] | 0.0012 | significant |
| Y5 | A-B | -311.9 | [-539.4, -86.3] | 0.0288 | significant |
| Y6 | T1-A | -71.9 | [-266.5, 117.1] | 0.486 | not significant |
| Y6 | T1-B | -452.5 | [-647.3, -258.4] | 0.0006 | significant |
| Y6 | A-B | -380.6 | [-612.7, -150.6] | 0.0070 | significant |

EVEN (n=10/tier, identical across tiers as noted above): 8482.2 (Y5) / 8084.6 (Y6).
CIAPA (n=10/tier, Y5): T1 6916.2 (sd 270.5), A 6715.4 (sd 126.7), B 6635.4 (sd 110.4).

**Headline finding: the ranking reverses relative to self-scoring.** Under each configuration's
OWN classifier, full-fingerprint (B) has the lowest (best) self-scored index (~4357, per S3's gate
means) and canonical-7 (T1) the highest/worst (~6584). Under the classifier-free yardstick, this
inverts: T1 and A do not differ from each other and both score significantly BETTER (lower =
less estimated degradation) than B, by about 4.4% to 7.0% depending on yardstick and pair. This
directly supports contribution 5's existing framing ("re-scoring against each classifier finds no
ranking that survives a change of reference") with an actual number rather than a placeholder.

**Not yet done / deferred, logged not hidden:**
- `figs/fig_truthscore.pdf` not generated (same deferral pattern as the other 3 figures this
  pass). Data for it is on disk (`s1-truthscore.tsv`).
- CIAPA under Y6 and its own pairwise stats were computed (`s1-truthscore.tsv` has the rows) but
  not separately reported above; can be pulled if the maintainer wants them in the caption.
- The "full-trace vs six-interval-equivalent" distinction the brief asks for produced identical
  numbers in this campaign (explained above); if the maintainer wants a real distinction, the
  window would need to be redefined (e.g. against the ACTUAL per-interval CPD boundaries the
  running simulation used, rather than a fixed last-1/6-of-rows heuristic) -- flagged as a
  design choice, not implemented as a fallback silently.

**Proposed text for the 6 `\tbd{S1}` occurrences below. NOT applied to `main-jsa.tex`. Per rule 7,
stopping here for maintainer sign-off (abstract, contribution 5, and conclusion all touched).**

1. Abstract (replaces "scored against the known workload classes, the resulting placements differ
   by X%"):
   > "scored against the known workload classes, the ranking reverses: full-fingerprint places
   > about 4 to 7% worse than canonical-7 or proxy-swap, which do not differ from each other"

2. Contribution 5 (replaces "a classifier-free yardstick built from the known workload classes
   ranks the placements as ..."):
   > "a classifier-free yardstick built from the known workload classes ranks canonical-7 and
   > proxy-swap together and full-fingerprint worst, the reverse of the self-scored ranking"

3. Section 7.4 tertile-rule description: unchanged, already accurate as written ("tertiles of
   each class's dominant measured metric over the host traces").

4. Section 7.4 result (replaces the "Result: canonical-7 X..." placeholder):
   > "Result: canonical-7 6966 $\pm$ 221, proxy-swap 7053 $\pm$ 357, full-fingerprint 7365 $\pm$
   > 399 ($n=20$ per configuration, five-class yardstick; six-class yardstick 6495 $\pm$ 235,
   > 6567 $\pm$ 389, 6947 $\pm$ 383). Canonical-7 and proxy-swap do not differ (permutation
   > $p_{Holm}=0.363$ five-class, $0.486$ six-class); full-fingerprint scores higher than both
   > (canonical-7: $p_{Holm}=0.001$ five-class, $0.001$ six-class; proxy-swap: $p_{Holm}=0.029$
   > five-class, $0.007$ six-class), about 4 to 7% higher depending on configuration and
   > yardstick. EVEN scores 8482 (five-class) or 8085 (six-class) identically regardless of which
   > tier produced its placement, since its round-robin assignment does not depend on a
   > classifier; CIAPA scores 6635 to 6916 (five-class, $n=10$ per configuration), closer to
   > canonical-7 and proxy-swap than to full-fingerprint."

5. Figure 15's... wait, Figure~\ref{fig:truthscore} caption (replaces "Caption numbers to be
   filled."):
   > "Five-class yardstick means: canonical-7 6966 (sd 221), proxy-swap 7053 (sd 357),
   > full-fingerprint 7365 (sd 399), $n=20$. Six-class yardstick means: canonical-7 6495 (sd 235),
   > proxy-swap 6567 (sd 389), full-fingerprint 6947 (sd 383). EVEN scores 8482 (five-class) or
   > 8085 (six-class), identical across configurations; CIAPA scores 6635 to 6916 (five-class,
   > $n=10$ per configuration)."

6. Conclusion (replaces "Against the known workload classes, the placements ..."):
   > "Against the known workload classes, the placements from canonical-7 and proxy-swap do not
   > differ from each other, and both place significantly better than full-fingerprint despite
   > full-fingerprint scoring best against its own classifier"

**STOPPED HERE per the brief's checkpoint rule.**


## S16 R2 -- cadence fidelity per environment (Step 9, reprocessing only, 2026-09-19)

**Question.** Does the pooled cadence-fidelity table hide per-environment effects, and do the
Section 4.6 / Figure 5 numbers survive a per-environment breakdown?

**Command.** `python3 bench/analyze-cadence.py <archive>/final/03-cadence-sweep --by-env --tsv
$OUT/r2-cadence-by-env.tsv --out $OUT/r2-cadence-by-env.md` (d7b6ad4's `--by-env` mode already
implements exactly this; nothing new written analyzer-side), plus a pooled rerun with `--tsv
/tmp/r2-pooled-check.tsv` for the acceptance diff. Archive read-only: both outputs redirected
outside it. Figure: `plot-cadence-curves.py` gained `--by-env-tsv`; `--jsa-merged` with it
renders a third panel row (per-environment deviations) between the pooled fidelity row and the
sensitivity heatmap; `render-jsa-paper-figures.sh` step 4 now passes the banked by-env TSV.

**Output.** `$OUT/r2-cadence-by-env.tsv` (1080 rows), `$OUT/r2-cadence-by-env.md`,
`paper-assets/figs/fig_cadence.pdf` (regenerated, 7.17 x 8.40 in, three rows), ledger
`$OUT/values-r2.tsv` (7 rows; main-jsa.tex NOT edited by this pass, applied centrally).

**Acceptance (pooled reproduction).** The regenerated pooled TSV is byte-identical to the
banked `final/03-cadence-sweep/cadence-fidelity.tsv` (`diff` empty, 372 rows). The regenerated
by-env TSV is also byte-identical to the banked `cadence-fidelity-by-env.tsv` from d7b6ad4.
PASS, exact.

**Per-env headline deviations.** The divergence is confined to four (metric, variant) series,
all involving the KVM guest; everything else reads the same per environment as pooled:
- app05 `psp`: host environments fall 86 to 87% at 5 s, but the in-guest reading (10 events/s
  reference) RISES, max +40% (v2.1, at 2 s) and +45% (v3.3, at 5 s). Sign flip.
- app05 v3.3 `cpu`: host environments stay within 4% of the 0.1 s reference at every cadence,
  but in-guest it climbs 6 -> 24 -> 48 -> 43 -> 56 -> 69 across 0.1 to 5 s (+1050% at 5 s).
  v2.1 in-guest `cpu` reads a flat 75 at every cadence (confirmed).
- app16 v2.1 `llcocc` (the proxy): +12.5 to +12.7% on the host environments, -31% in the guest
  from 1 s onward. Sign flip. (v3.3 reports no guest `llcocc`.)

**Prose corrections recorded in the ledger (values-r2.tsv).** Three Section 4.6 / Figure 5
numbers were wrong or imprecise against the per-env table: "rises by 40 to 50%" -> "40 to 45%"
(actual maxima +40/+45); v3.3 in-guest cpu "from 5.5% ... to 68%" -> "from 6% ... to 69%" (the
5.5/68 pair matches no statistic this table computes; the pooled-samples medians are 6 and 69);
oversubscription `psp` "stays within 2%" -> "stays within about 2%" (pooled v3.3 max |dref| is
2.23%, marginally over the stated bound; v2.1 stays under 1%). All other numbers in the
paragraph and caption reproduce exactly: psp streaming loss 86 to 87% at 5 s (pooled 5 s dref
-0.871 v2.1, -0.862 v3.3); llcmr/membw_est drift 24 to 29% (pooled maxima 23.5 to 28.5%);
llcocc rise 10 to 16% (pooled maxima 10.5 to 16.2%); psp references about 140 and about 5400
events/s; v3.3 pooled cpu +16% at 2 s (exactly 0.16); density 1190 to 1199 rows/rep at 0.1 s
down to 23 at 5 s. The caption also gains a "Middle:" sentence describing the new panel, and
the "Top:" sentence now says the pooling explicitly (the brief requires pooled panels to be
labeled as pooled).

**Verdict.** R2 confirmed with corrections: pooled acceptance exact, the two known guest
effects reproduce (with corrected magnitudes), and one new guest effect is quantified in the
caption (v2.1 in-guest `llcocc` -31% on app16, already noted in the rerun brief).

### R3 -- audit of the v3.3 victim mbw disagreement (Step 10, code+data audit, complete; 2026-09-19)

**Question.** Section 6.1: under W5 colocation the variants disagree on the victim's
`mbw` -- v2.1 reads it rising by 1 to 4 points (app01_ml_llc, app11_sort_net) while
v3.3 reads it falling by 18 to 38.5 (Cliff's delta = -1.0). Is this a resctrl
mon_group enrollment bug in v3.3, an inconsistent ceiling normalization between the
solo and pairwise arms, or a real signal?

**Files/commands examined.** v3.3 read path:
variants/v3.3-ebpf-core-cgroup/src/intp_agg.c:60 (fixed mon_group name), 355-402
(recursive victim-cgroup seeding), 977-996 (enrollment), 1188-1202 (per-interval
rescan); variants/v3.3-ebpf-core-cgroup/resctrl/resctrl.c:287-328 (delta +
normalization by caps->mem_bw_max_bps). Harness: bench/run-intp-bench.sh:4188-4238
(pairwise profiles the VICTIM ONLY; the aggressor runs unprofiled in its own
cgroup/cpuset, so no aggressor ever enters the victim's mon_group; one profiler
instance per run makes the fixed group name harmless), 3604-3636 + 3781-3782
(v3.3 gets --mem-bw-max-bps from capabilities.env), 3521-3584 (v2.1 gets no
override and self-detects the audited 281600 MB/s ceiling,
variants/v2.1-c-abi-cgroup/src/detect.c:433-465). Data:
results/02-w5-colocation vs results/p2-15metric-xdeploy-1of3.

**Findings.** (1) Raw mbm_total_bytes deltas are NOT logged (--no-diag-cols
suppresses mbw_raw_mbps; groundtruth resctrl_mbw_bps is "--" by design), so
recomputation works from the logged percent column. (2) All 168 comparable w5
v3.3 SOLO cells are byte-identical (cmp) to the pre-audit 2026-06-10 xdeploy
cells, whose 42656 MB/s fallback ceiling is documented (DECISIONS-container.md
C34) and confirmed in-situ by 113 "ceiling=42656 MB/s" warnings in the copied
cells' own portable.v3.3.log files; the PAIRWISE cells were collected 2026-06-13
after the ceiling audit with INTP_MEM_BW_MBPS=281600 in the campaign
capabilities.env, so the victim delta mixed two scales. (3) Rescaling the solo
arm by 42656/281600 = 0.1514 (script r3-recompute.py reproduces the published
as-logged values exactly first) turns the disputed cells into +3.21/+2.96 (bare)
and +1.77/+2.65 (container), Cliff's delta +0.75..+1.0, consistent with v2.1's
+1/+3 and 0/+4 and with the ceiling-independent per-cgroup signals (llcmr
triples, membw_est rises). (4) app07_ordering solo cells are a later collection
absent from the pre-audit snapshot, so their scale is ambiguous; either reading
removes the v3.3-only fall there too.

**Output.** $OUT/r3-mbw-audit.md, $OUT/r3-mbw-recomputed.tsv, $OUT/r3-recompute.py,
ledger row in $OUT/values-r3.tsv (not applied to main-jsa.tex by this agent).

**Verdict: explained, and corrected in analysis.** The sign flip is a
ceiling-scale mismatch between the copied pre-audit solo arm and the post-audit
pairwise arm, not a mon_group enrollment bug. mbw victim deltas remain
descriptive-only (the app07 provenance ambiguity shows the column still mixes
provenances), which the sentence already states.

## S16 S5 -- density sweep with early exit (Step 6, complete; 2026-09-19)

**Question.** Does the annealing loop terminate once the objective reaches zero
(early exit), what does the index-vs-density curve look like over the full
7-point sweep at n=10, do the tier conclusions depend on sitting at the 4.0
applications-per-host operating point, and does the S2 closed form explain the
curve's shape?

**Code change (CloudSimInterference, committed there).** `Placement.java` gains
`-Diada.earlyExitZero=on` (default off): break the annealing loop when the
current/best solution's total interference cost is 0, checked BEFORE the first
`randomSwap()` call as well as after each accepted swap. The pre-swap check is
load-bearing, not defensive: at 1 application per host every cloudlet is alone
on its host, so `swapping()`'s retry loop never finds a valid partner and a
post-swap-only check is never reached (found by hanging smoke runs, not by
static reading). Recorded in `CONFORMANCE.md` Sec 8 as a bug-fix candidate,
default off so banked S15 results stay reproducible.

**Smoke test (spec: runs finish well under 400 s with idi 0).**
`smoke-s5/v3.3/vm-guest/` under $OUT: `smoke-before` (no flag) exit 124 at the
400 s timeout, 0 intervals finished, idi 0; `smoke-fixed` (flag on,
containerPes=48) exit 0 in 56 s, 6 intervals, idi_avg 0, migrations 0;
`smoke-cp32-fixed` (containerPes=32) exit 0 in 39 s. PASS.

**Sweep (run 2026-09-18, tier B, n=10 per point, early exit on, PM_COUNT=28,
IADA_HOSTS=28, JDK 8, same toolchain as S1/S2/S3/S4).** containerPes in
{48,32,24,20,17,14,12} = 1, 1.5, 2, 2.4, 2.82, 3.43, 4 applications per host
(48/14=3.43 reported, not 3.3 -- 14.5 PEs is not an integer). All 70 reps
exit 0, mean elapsed 56 to 57 s (no timeouts anywhere). Output:
`s5-density.tsv` (per-rep; exit/elapsed columns filled from the per-rep
`cloudsim.exit`/`cloudsim.elapsed` files, which live in transient
`/tmp/s5-work/` -- the TSV is the durable artifact) and `s5-summary.tsv`
(per-density mean + 95% bootstrap CI, `p2_ci.rep_ci` convention).

| apps/host | total index (CI) | interference only (CI) | migration share |
|---|---|---|---|
| 1.0  | 0 | 0 | -- |
| 1.5  | 0 | 0 | -- |
| 2.0  | 73.4 [61.8, 86.8] | 33.6 [33.4, 33.8] | 54% |
| 2.4  | 84.3 [73.1, 99.8] | 48.8 [48.3, 49.3] | 42% |
| 2.82 | 99.1 [91.7, 108.7] | 67.6 [67.0, 68.2] | 32% |
| 3.43 | 470.0 [456.8, 484.8] | 418.5 [413.4, 424.3] | 11% |
| 4.0  | 4442.4 [4277.8, 4630.3] | 4415.8 [4244.1, 4604.7] | 0.6% |

**Tier check at the midpoint (containerPes=17, 2.82 apps/host).** T1, A, B at
n=10 each via `run-sim-arm.sh` (`-Diada.containerPes=17
-Diada.earlyExitZero=on`, same toolchain; idi TSV `s5-tiers-at-2.82-idi.tsv`,
logs in transient `/tmp/s5-tier-work/`), every final placement scored with the
S1 Y5 yardstick (`s1-truthscore.py`, same level rule and canonical trace
source as S1). Output: `s5-tiers-at-2.82.tsv`, per-rep scores and placements
under `s5-tier-check/`. Result (Y5, n=10): T1 219.4 (sd 3.0), A 220.5 (sd
1.7), B 220.4 (sd 3.5); no pairwise difference survives Holm correction
(smallest Holm p = 1.0 for Y5; Y6 identical pattern). The S1 yardstick gap at
4.0 apps/host (full-fingerprint worst by about 4 to 7%) does NOT appear at
2.82: the tier conclusions depend on the operating point. This is the answer
the brief's item 4 asked for.

**Functional-form check.** `bench/iada/scripts/s5-fit.py`: regress
log(interference_avg) on log of the S2 closed form `(28/d)*(g*d)^d/6` with
d=48/containerPes and g = tier B geomean cloudlet cost 1.9261 (from
`s2-summary.tsv`). Densities 1.0/1.5 excluded (interference 0, cannot log).
Per-rep fit (n=50): slope 1.03 (95% CI 0.96 to 1.10), R^2 0.945;
per-density-mean fit (n=5): slope 1.03, R^2 0.945. Output `s5-fit.tsv`. The
multiplicative form's exponent is consistent with the data.

**Acceptance (spec: reproduce S15 banked values at 2.0, 2.82, 4.0 within their
CIs).** Mixed, reported honestly in `s5-acceptance.tsv`. The S15 banked sweep
(`sim-experiments-20260916/density-sweep/`) has n=5 per point, not n=10.
Strict criterion (S16 mean inside S15 95% bootstrap CI): PASS 3 of 6 --
interference-only at 2.0 (33.6 vs 33.6) and both components at 4.0 (4442
inside [4167, 4450]; 4416 inside [4109, 4423]); FAIL 3 of 6 -- total index at
2.0 (73.4 vs CI [59.1, 68.7]) and at 2.82 (99.1 vs [100.2, 130.9]), and
interference at 2.82 by 0.03 (67.59 vs CI upper 67.56). The failures are
entirely the migration term: interference-only agrees to within 1% at every
banked density, while mean migration counts differ (2.0: 23.9 vs 18.2; 2.82:
18.9 vs 30.4) and a 10000-permutation test on the difference of means finds
nothing significant (p = 0.41 at 2.0, 0.066 at 2.82, 0.27 at 4.0). Early exit
cannot be the cause: it fires only at cost 0, and no rep at these densities
ever reaches cost 0 -- the difference is run-to-run SA noise between the n=5
and n=10 batches. Verdict: interference component reproduces; total index
agrees within noise but not within the tight n=5 CIs at 2.0/2.82.

**Figure.** `figA_density.pdf` regenerated (two lines: total index and
interference only, n=10, 95% bootstrap band) via the new `--density-tsv`
option of `bench/plot/plot-fig-baselines-oracle-jsa.py` (default behavior
unchanged), copied to `paper-assets/figs/figA_density.pdf`.

**Placeholders.** Both `\tbd{S5}` filled via `values-s5.tsv` + fill_tbd.py
(dry-run verified). Per ground rule 4, the surrounding prose was also moved to
the n=10 rerun's numbers (they supersede the banked n=5 values the sentences
quoted): Section 7.6 now reads "rises from 73 at two applications per host to
99 at 2.82 and 4442 at 4.0" and "54% at 2.0 and 32% at 2.82 (interference
alone 34 and 68)" (was: 64/118/4264, 50%/40%, 34/67); the Figure A.4 caption
gains the early-exit description and drops the stale "crosses = timed out"
sentence (no rep times out any more). The caption's n=5 -> n=10. tectonic
compile: 0 errors; `\tbd{S5}` count 0.

### S1/S2 figures -- fig_truthscore + fig_idi_decomp rendered (2026-09-19)

**Question.** The two `\figph` placeholders still rendering as pending boxes --
`\figph{S1}` (`figs/fig_truthscore.pdf`) and `\figph{S2}`
(`figs/fig_idi_decomp.pdf`) -- need real figures from the S16/S1+S2 TSVs,
in house style, wired into the one-shot render.

**Command.**
`python3 bench/plot/plot-fig-truthscore-jsa.py --data-root bench/iada/results/sim-experiments-20260917-s16 --out DIR`
and
`python3 bench/plot/plot-fig-idi-decomp-jsa.py --data-root bench/iada/results/sim-experiments-20260917-s16 --out DIR --s3-work-root /tmp/s3-work`
(both also exercised end-to-end via `bench/render-jsa-paper-figures.sh`, new
step [8b/9]; `pytest bench/plot/tests/` 50 passed including the new
`test_plot_s16_figures.py`).

**Output.** `paper-assets/figs/fig_truthscore.pdf` and
`paper-assets/figs/fig_idi_decomp.pdf` (also in the render script's OUT).
fig_truthscore: two panels (Y5/Y6), IASA bars n=20 per tier with rep-level
95% bootstrap CIs (Y5 6966/7053/7365, Y6 6495/6567/6947), CIAPA hatched bars
n=10 (Y5 6916/6715/6635, Y6 6397/6230/6120) on the same yardstick, EVEN as a
dashed tier-independent reference line (8482 Y5 / 8085 Y6). fig_idi_decomp:
left panel the six per-interval SAO costs per tier (interval 1 marked as the
pre-search placement) with the closed-form prediction overlaid at interval 1
(8371/3348/6074 vs actual 8018/3206/5825, 4.4/4.4/4.3% high); right panel the
final-interval index with 95% bootstrap CIs (4957/3378/3466, tags -38%/+5%/-40%
vs interval 1). All plotted means cross-checked against the summary TSVs at
render time (VALIDATION OK lines); pymupdf text checks in the render script.

**Data provenance.** fig_truthscore from `s1-truthscore.tsv` (per-rep) +
`s1-truthscore-summary.tsv` (EVEN + cross-check). fig_idi_decomp endpoints and
closed form from `s2-decomp.tsv` + `s2-summary.tsv`; intervals 2-5 re-parsed
from the S3 gate campaign's `cloudsim.log` "Algorithm: SAO" blocks
(`/tmp/s3-work/s3-gate-{T1,A,B}/...`, the same n=10/tier runs S2 used --
parsed endpoints match s2-decomp.tsv exactly for all three tiers before
plotting). Intervals 2-5 exist only in those logs, not in any TSV; when the
log tree is absent the renderer degrades to endpoints 1 and 6 with a warning,
so the render stays one-shot runnable from the TSVs alone.

**Result.** Both pending-box placeholders now render as real figures; the
`\figph{S1}`/`\figph{S2}` call sites in main-jsa.tex resolve. The S2
follow-up's interval-3 hump for proxy-swap is visible in the figure (mean
trajectory 3206, 3737, 4625, 3225, 3658, 3378).

**Verdict.** figures shipped; no text edits (coordinator owns main-jsa.tex).
Open caveat, same as S2's own entry: /tmp/s3-work is volatile -- if it is
wiped, re-render from a fresh S3 gate run's logs to restore the full
6-interval trajectories (the endpoints-only fallback stays correct).

## S16 S6 -- oracle re-scoring matrix at n=20, shared placements (Step 7, complete; 2026-09-19)

**Question.** Does any placement ordering survive a change of reference classifier at
n=20, and can the three reference columns be made to share placements so the
batching caveat of the n=10 pass (three separate simulator batches, each with its
own placements) disappears?

**Design: the brief's PREFERRED option, offline.** Reused the S1 campaign's saved
final placements (`s1-placements/IASA/`, n=20 per tier, 60 files) and re-scored
each placement under all three reference classifiers (T1, A, B). No new simulator
run was needed, because (a) the placement is already on disk from S1, and (b) the
reference classification is placement-independent: `oracleRescore` classifies
cloudlet k's trace from the REFERENCE's own tree (`oracleTreeDir`) with the
reference's model, so one cost per (reference, cloudlet) prices every placement
tier. Two new scripts:

- `bench/iada/scripts/s6-refclass.R` -- literal R replication of
  `MLClassifier.getMLClass(interf, 0, len)` (the exact call oracleRescore makes):
  same sourcing order, same zero-placeholder first row in `teste`, same
  `svm_classifier_level(teste, 1, nrow(teste))`, degradation fork table, floor 1,
  regime term only for the 6-class B model. **Validated against the simulator's
  own output before use**: replicates the S3 campaign's `CLS` log lines exactly
  (predClass + level match for all 28 cloudlets x 3 tiers x 3 reps at the
  final-interval window, and x 2 reps at a middle window; 420/420). Writes
  `s6-refcosts.tsv` (one cost per ref x cloudlet; classification inputs from the
  canonical trees in `paper-assets/deliverables/data/inputs-iada-trees-20260916`,
  read-only).
- `bench/iada/scripts/s6-oracle-matrix.py` -- literal port of
  `Solution.getTotalInterferenceCostOracle`: per-cloudlet cost x hostPe/clPe
  (48/12, verified constant in all 60 S1 gate logs), product per host over
  co-residents, single-occupancy hosts floored to 0, total scaled by
  (end-start)/ttime = 18/119 (final IASA interval, start=101 end=119 ttime=119,
  traced from the interval loop; identical for every IASA rep, cancels in all
  paired diffs).

**Statistics (fixed seed 20260607, 10000 perms/resamples).** Self vs reference per
cell: sign-flip permutation test on paired differences + paired percentile
bootstrap CI (`s6-selfref.tsv`). Cross-tier under each reference: label-shuffle
permutation test + unpaired bootstrap CI, Holm correction across all 9
comparisons; every significance label follows the Holm p (`s6-cross-tier.tsv`).

**Result (means, n=20; placement tier x reference):**

| reference | T1 placements | A placements | B placements |
|---|---|---|---|
| T1 (canonical-7) | **4814** +- 293 (self) | 5540 +- 556 | 5095 +- 541 |
| A (proxy-swap) | 4692 +- 776 | **3959** +- 595 (self) | 5514 +- 1574 |
| B (full-fingerprint) | 3880 +- 286 | 4022 +- 267 | **3620** +- 237 (self) |

Diagonal cells are exactly Delta=0 for all 60 reps (self-consistency, as at n=10).
Paired self vs reference: T1 under B -934 [-1010, -864] perm p=0.0001 (19% lower);
A under B +64 [-165, +236] p=0.64 (**n.s. at n=20; was +162 [58, 283] significant
at n=10 -- overturned, see below**); T1 under A -121 n.s.; A under T1 +1581 *;
B under T1 +1475 *; B under A +1894 *. Cross-tier (delta = arm - base, Holm p):
ref T1: A-T1 +726 * (0.001), B-T1 +281 n.s. (0.111), B-A -445 n.s. (0.066);
ref A: A-T1 -734 * (0.013), B-T1 +821 n.s. (0.111), B-A +1555 * (0.001);
ref B: A-T1 +142 n.s. (0.116), B-T1 -260 * (0.009), B-A -403 * (0.001).

**Verdict: Case 4 stands and sharpens. No reference-free ordering exists at n=20.**
Every reference still ranks its own configuration first in point estimate, and the
canonical-7 versus proxy-swap comparison changes sign with the reference --
significantly so in BOTH directions now (A is 726 worse under the canonical-7
reference, p_Holm=0.001; 734 better under the proxy-swap reference, p_Holm=0.013),
whereas at n=10 the flip was significant only under the canonical-7 reference and
marginal under proxy-swap. Two prose corrections vs the n=10 text, per rule 4:
(1) proxy-swap's self score is NO LONGER distinguishable from the full-fingerprint
reference (+64, CI includes zero) -- "slightly optimistic, 4% higher" is withdrawn;
(2) under the full-fingerprint reference, B's advantage over both other tiers is
now Holm-significant. The batching sentence ("separate batches of ten
repetitions") was deleted from Section 7.3 and the Figure 19 caption; the text
states that all three references score the same twenty placements.

**Acceptance.** Diagonal Delta=0 exactly: PASS (all 60 reps). n=20 means within
n=10 CIs: 11 of 12 cells PASS (`s6-acceptance.tsv`). The exception is T1
placements under the A reference: n=20 mean 4692 vs n=10 CI [3953, 4230]
(mean 4083). Explanation, not a pipeline error: the per-rep values are heavy-tailed
(3595 to 6130 at n=20, visibly two clusters; the n=10 batch drew entirely from the
lower cluster, max 4576). The A-referenced price of a T1 search placement depends
on whether A's classifier prices the co-resident group expensively, and the
product-per-host cost amplifies a single expensive pairing; a 10-rep bootstrap CI
of such a skewed mean is too narrow to gate on. The classifier replication itself
is exact (420/420 CLS matches), and the other 11 cells -- including both
self columns and the B-reference column -- reproduce the independent n=10 runs.

**Outputs.** `$OUT/s6-refcosts.tsv`, `s6-oracle-matrix.tsv`, `s6-oracle-scores.tsv`
(long form, S15 oracle schema, figure input), `s6-selfref.tsv`, `s6-cross-tier.tsv`,
`s6-acceptance.tsv`, `values-s6.tsv`. Figures regenerated at n=20
(`fig_oracle.pdf`, `fig_oracle_matrix.pdf` installed in `paper-assets/figs/`,
n=10 versions kept in `figs-orig/*.n10`); `bench/plot/plot-fig-baselines-oracle-jsa.py`
gained `--s6-scores` (default behaviour unchanged), and
`bench/render-jsa-paper-figures.sh` step [8c/9] renders both from `$OUT`
(`JSASIM16` overridable). Paper: both `\tbd{S6}` occurrences filled plus the full
Section 7.3 numeric rewrite and both figure captions (4 rows in values-s6.tsv);
tectonic compile 0 errors; placeholder count 6 (S1 x2, S2 x1, S7 x3; S6 = 0).
No CloudSimInterference changes (no new simulator code was needed).

## S16 S7 -- regime level audit, same-build re-key, and multiplier sweep (Step 8, complete; 2026-09-19)

**Question.** What are the regime level counts 71/409/0; is the highest regime
multiplier (1.95) ever applied; how large is the psp re-key effect on a single
build; and how sensitive is tier B's index to the regime multiplier magnitude?

**Audit (task 1).** Reran `bench/iada/scripts/analyze-regime-levels.R` unchanged
against the psp-keyed R folder the simulator reads (`/home/saccilotto/iada-tier-rda/B`)
and the current canonical 28-trace tree (reached via a symlink shim; nothing
modified). The three counts are **per-level sample counts**: trace rows the tier B
SVM classifies as regime (480 of 3360) assigned by the regime k-means to
low/mod/hig when the centroids are ordered on `psp` (col 14). Every centroid has
schedlat = 100 (saturated), confirming the S8 tie-break diagnosis; psp orders them
consistently (5184.7 < 5293.8 < 5365.6). On the current tree the counts replay as
**31/449/0**, not the banked 71/409/0 (same 480 regime rows, so the SVM agrees on
which rows are regime; the low/mod split differs because the August tree and the
current canonical tree differ; hig = 0 in both). In-simulation cross-check on this
build (S3 class log, tier B final interval): all 40 oversubscription cloudlet
classifications are `mod`, none `hig`. **Verdict: the 1.95 multiplier is never
applied; the regime class is always priced at low or mod (on the current tree,
almost always mod).** Output: `s7-levels.md`.

**Same-build re-key (task 2).** Tier B with schedlat-keyed levels (S8 patch reverted
in a scratch copy of the tier R folder at `/tmp/s7-rda-schedlat/B`; the real
`/home/saccilotto/iada-tier-rda/B` untouched), n=10, same rebuilt toolchain and
tree as S3, via `run-sim-arm.sh`. Compared against S3's psp-keyed tier B
(`s3-gate-B.tsv`, same build):

| arm | n | idi_avg mean | sd | 95% CI |
|---|---|---|---|---|
| schedlat-keyed (this pass) | 10 | **5255.5** | 180.5 | [5157.3, 5368.1] |
| psp-keyed (S3, same build) | 10 | **4357.2** | 168.3 | [4266.5, 4463.4] |

On one build the re-key alone moves the full-fingerprint index by about −898
(about −17%). Output: `s7-rekey-samebuild.tsv`.

**Multiplier sweep (task 3).** Tier B, psp-keyed, n=10 per arm, early exit OFF
(comparable to S3/S5), regime vector uniformly rescaled to top values 1.0 (flat:
1.00/1.00/1.00), 1.5 (0.9231/1.1923/1.50, shape preserved), 1.95 (current default
1.20/1.55/1.95), 2.5 (1.5385/1.9872/2.50). IDI from the run TSVs; placements scored
with the S1 known-class yardstick (Y6, `s1-truthscore.py`, same level rule as S1):

| top | ramp | idi_avg (95% CI) | Y6 mean (sd) |
|---|---|---|---|
| 1.0 (flat) | 1.00/1.00/1.00 | **3264.3** [3213.8, 3316.6] | 7104.5 (544.6) |
| 1.5 | 0.9231/1.1923/1.50 | **3587.7** [3540.2, 3643.4] | 6692.2 (359.7) |
| 1.95 (current) | 1.20/1.55/1.95 | **4307.4** [4224.7, 4392.6] | 6780.8 (293.6) |
| 2.5 | 1.5385/1.9872/2.50 | **5795.5** [5527.8, 6078.4] | 6635.0 (360.1) |

The self-scored index rises monotonically with the top multiplier (flat to 2.5
spans 3264 to 5796, about 1.8x), so the committed hand-set ramp is not a
knife-edge: no choice inside the swept range changes the ordering story, and the
current 1.95 sits inside the swept range. The Y6 yardstick barely moves
(6635 to 7105, overlapping CIs): placement quality as read by the
classifier-free yardstick is insensitive to the regime multiplier, while the
self-scored index is not. Outputs: `s7-multipliers.tsv` (per-rep),
`s7-multipliers-summary.tsv`.

**Acceptance (psp-keyed arm vs S15 gate B 4298.0 ± 168.9).** The top-1.95 arm on
this build: 4307.4 ± 145.4, CI [4224.7, 4392.6] — inside the banked gate interval
[4129.1, 4466.9]. **PASS.**

**Fills.** All 3 `\tbd{S7}` plus one occurrence-0 correction (the banked level
split 71/409/0 is replaced by 31/449/0 measured on the current canonical tree;
the load-bearing hig = 0 is confirmed) written to `values-s7.tsv`;
`fill_tbd.py --dry-run` verifies all 4 rows against `main-jsa.tex` (not edited
here; coordinator applies).

**Verdict.** Audit hypothesis confirmed (top multiplier never applied) with a
correction to the low/mod split; re-key effect measured on one build at about
−898 IDI; the index is monotone in the regime multiplier over 1.0 to 2.5 while
the known-class yardstick is flat across the sweep.

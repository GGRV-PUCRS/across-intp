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
| **E4** ramp shape | step +292 n.s., convex +230 n.s., measured −1211 * | Shapes sharing `hig`≈1.95 are indistinguishable → in-sim regime classifications land almost entirely at `hig`, confirming W5's bimodality from inside the simulation. IDI tracks the `hig` value, i.e. ramp *magnitude*, not shape. |
| **E5** Meyer Table 2 | T1 −1576 *, A −879 *, B −1024 * | The table choice scales the index by 16–25% but preserves tier ordering (T1 > B > A) at 12 hosts. A reporting decision, not a ranking risk. |
| **E1** startup delay | 0/10/50 s all n.s., every tier | The 19-s co-execution window does **not** bias IDI at 12 hosts. The default can stay at 100 s; no rebank needed. |
| **E3** host sweep | 13/15 n.s.; B@19 +566 *, T1@23 −193 * | The index is **flat from 9 to 28 hosts** — no consolidation curve, no degeneracy collapse at 1 container/host. Per-cloudlet cost is computed from solo traces, so co-location never enters it; the two isolated exclusions have no trend and read as multiplicity. |

The E3 flatness is the deepest finding: Meyer's Fig. 10 host-curve shape
cannot be reproduced by this IDI metric as implemented, because placement
cost is trace-driven rather than co-location-driven. Any future host-sweep
claim needs either a co-location-aware cost (interference recomputed from
actual co-residents) or must be framed as scheduler-behaviour, not
system-outcome. Feeds directly into the S8 discussion.

## Open questions

1. **S8** — psp-keyed regime level column (retrain + re-run, after campaign).
2. Whether E1's startup-delay result justifies moving the *default* to a
   shorter delay (breaks banked comparability; would need a rebank).
3. Application-level runtime ground truth for ramp magnitudes — W5 has stall
   fractions (psi_*) but no response-time capture; out of scope for the
   simulation-only campaign.

# S16-SUMMARY — Mid-revision reruns (2026-09-17 to 2026-09-19)

Maintainer summary for the placeholder-filling campaign specified in
the local rerun brief (rerun IDs R1..R3, S1..S7) against
`paper-assets/main-jsa.tex`. All 37 placeholder occurrences are filled; the
paper compiles with 0 errors (tectonic) with `\draftmarksfalse` and
`\supersededfalse`; the validator FAIL set shrank from 11 to 3, and the 3
remaining fails (C10 v3.3, C11, C12) are pre-existing hardware-data checks
that already failed at the `validate-before.txt` baseline and are outside
this campaign's scope.

Per-ID old/new text: the exact strings are the `old_text`/`new_text` columns
of `values.tsv`, `values-r1.tsv` … `values-s7.tsv` in this directory
(applied via `paper-assets/tools/fill_tbd.py`; occurrence 0 = plain sentence
rewrite). Full question/command/output/verdict narratives: per-ID entries in
`../DECISIONS-sim-experiments.md`. Verdicts below: **confirmed** (provisional
text matched rerun), **corrected** (number/wording changed), **overturned**
(direction or claim changed).

## R1 — ground truth re-adjudication (reprocessing)
**Confirmed.** 60/60 CPU cells in band (0.92 to 0.99), llcmr rho 0.85 (n=70),
membw_est rho 0.81 (n=70). Sources: `r1-cpu-cells.tsv`, `r1-summary.tsv`.
Commit 65a924b.

## S3 — class confusion inside the simulation
**Confirmed/extended.** Per-cloudlet class logging (`-Diada.logClasses`)
reproduced the June audit price pattern; confusion counts written into the
Section 7.2 parenthetical. Sources: `s3-class-log.tsv`, `s3-confusion.tsv`,
`s3-summary.tsv`. Commit 65a924b.

## S4 — full transfer gate
**Confirmed.** v3.3 accuracy/recall reproduced Table 7 exactly; memory
precision added (>= the 0.565 mathematical bound); v2.1 gate sentence added.
`fig_transfergate.pdf` regenerated with confusion matrices.
Sources: `s4-transfer-{v33,v21}.tsv`, `s4-confusion-{v33,v21}.tsv`. Commit 65a924b.

## S2 — index decomposition and closed form
**Overturned in part.** Interval cost does not fall proxy-swap vs T1 as the
old text claimed: it rises 3206 to 3378 (+5%); the hump is consistent across
all 10 reps (June numbers were provisional, pre-rebuild). Closed form
matches the logged first interval within 4.4% for every tier (acceptance
<10%: pass). `fig_idi_decomp.pdf` rendered from `s2-decomp.tsv` +
`s2-summary.tsv` + `s2-intervals.tsv` (the interval trajectories, persisted
from the volatile /tmp/s3-work log tree). Commits 65a924b, 310326e, d9d915a.

## S1 — known-class yardstick (headline)
**Overturned.** Under the classifier-free yardstick the self-scored ranking
reverses: canonical-7 and proxy-swap tie (6966±221 vs 7053±357, five-class;
6495±235 vs 6567±389 six-class; Holm p 0.363/0.486) and both beat
full-fingerprint by about 4 to 7% (Holm p 0.001 to 0.029). EVEN sanity
checks at exactly 8482 (Y5) / 8085 (Y6) independent of tier, as the accept
test requires. `fig_truthscore.pdf` rendered from `s1-truthscore*.tsv`.
Commits f4cc5dd, 83d1d29, 310326e.

## S5 — density sweep with early exit
**Corrected.** New `-Diada.earlyExitZero` flag (CONFORMANCE.md bug-fix
candidate; default off) — 1 and 1.5 applications per host now finish in
about 56 s with idi 0 instead of hitting the 400 s limit. n=10 sweep:
interference-only 0, 0, 34, 49, 68, 418, 4416 vs totals 0, 0, 73, 84, 99,
470, 4442 over 1, 1.5, 2, 2.4, 2.82, 3.43 (48/14, not 3.3), 4.
log-log regression on the S2 closed form: slope 1.03 (CI 0.96 to 1.10),
R² 0.94. Tier check at 2.82: T1/A/B indistinguishable on the Y5 yardstick
(~219 to 220, Holm p = 1.0) — the S1 gap is density-dependent, stated in
Section 7.6. Acceptance vs S15 banked values: mixed by the strict
n=5-vs-n=10 criterion, all gaps in the migration term and none significant
(permutation p 0.066 to 0.41); documented honestly in DECISIONS.
Sources: `s5-density.tsv`, `s5-tiers-at-2.82.tsv`, `s5-fit.tsv`,
`s5-acceptance.tsv`. Commits bba668a (CloudSimInterference), 13fa987.

## S6 — oracle matrix at n=20
**Corrected (sharpened).** Preferred design worked: the S1-saved n=20
placements were re-scored offline under all three reference classifiers
(`s6-refclass.R` replicates the classifier exactly, 420/420 log matches;
no new simulator runs; batching sentence deleted from Section 7.3 and the
Figure 19 caption). Diagonals exactly Δ=0 (60/60 reps). No reference-free
ordering survives, but the T1-vs-A comparison now flips sign with the
reference and is Holm-significant in both directions (+726, p_Holm=0.001
under the T1 reference; −734, p_Holm=0.013 under the A reference); under the
B reference B's placements beat both others (−260, p=0.009; −403, p=0.001).
One withdrawal per rule 4: proxy-swap's "slightly optimistic" self-vs-B gap
is n.s. at n=20 (+64, CI −165 to +236), kept as an \oldval note.
Acceptance: 11/12 n=20 means inside n=10 CIs; the one miss (T1 placements
under the A reference) is heavy-tail placement sampling, explained in
DECISIONS. `fig_oracle.pdf` / `fig_oracle_matrix.pdf` regenerated at n=20
(n=10 versions preserved in `paper-assets/figs-orig/*.n10`).
Sources: `s6-oracle-scores.tsv`, `s6-oracle-matrix.tsv`, `s6-cross-tier.tsv`,
`s6-selfref.tsv`, `s6-acceptance.tsv`. Commit ea40ad6.

## S7 — regime level audit and multiplier sweep
**Corrected.** "71/409/0" replays as 31/449/0 on the current 28-trace tree
(unchanged script; August tree had a different low/mod split). The three
counts are per-level sample counts of regime-classified trace rows; the high
count is 0 in both, so the 1.95 multiplier is never applied. Same-build
re-key (schedlat scratch copy): 5256 vs 4357, about −898 (−17%).
Multiplier sweep (top 1.0/1.5/1.95/2.5): index 3264/3588/4307/5796
monotone; Y6 yardstick flat (7105/6692/6781/6635). Acceptance: PASS
(psp-keyed 4307 inside the S15 gate B CI). Sources: `s7-levels.md`,
`s7-rekey-samebuild.tsv`, `s7-multipliers*.tsv`. Commit 7f9f8d8.

## R2 — cadence per environment (reprocessing)
**Confirmed + corrected.** Pooled columns reproduce the banked
cadence-fidelity table byte-identically (372 rows). `fig_cadence.pdf` gains
a per-environment deviation panel. Corrections: guest psp rise 40 to 45%
(was 40 to 50); v3.3 in-guest cpu 6% to 69% (was 5.5 to 68, matching no
statistic); "within 2%" hedged to "about 2%" (max 2.23%); caption relabeled
so pooled panels say pooled. Sources: `r2-cadence-by-env.{tsv,md}`.
Commits c2a23cc, df7dfdb.

## R3 — audit of v3.3 victim mbw
**Explained, corrected in analysis.** No mon_group bug: pairwise profiles the
victim only and the enrollment/read math is sound. The disagreement is a
scale mismatch — the v3.3 solo baselines are byte-identical copies of
pre-audit cells normalized at the 42656 MB/s fallback ceiling while the
pairwise cells were collected post-audit at 281600 MB/s; rescaling the solo
arm by 0.1514 turns the disputed deltas into rises of 2 to 3 points
(n=12 per arm), consistent with v2.1. Raw mbm_total_bytes not logged, so
recomputation used the logged percent column. app07_ordering provenance
remains ambiguous; mbw victim deltas stay descriptive-only (already stated).
Sources: `r3-mbw-audit.md`, `r3-mbw-recomputed.tsv`, `r3-recompute.py`.
Commit 01c5b49.

## Changes to headline material (abstract / contributions / conclusion)
- **Abstract:** the S1 sentence now states the reversal — full-fingerprint
  places about 4 to 7% worse than canonical-7 or proxy-swap under the
  known-class yardstick, which do not differ (was a placeholder).
- **Contribution 5:** now says the classifier-free yardstick ranks
  canonical-7 and proxy-swap together and full-fingerprint worst, the
  reverse of the self-scored ranking (was a placeholder).
- **Conclusion:** the S1 sentence (two places) states canonical-7 and
  proxy-swap do not differ and both beat full-fingerprint despite
  full-fingerprint scoring best against its own classifier.
- No other abstract/contribution/conclusion text changed in S16.

## Deferred / out of scope (logged, not hidden)
- Validator fails C10 (v3.3), C11, C12 pre-date S16 (hardware data and
  text-claim mismatches; see validate-before.txt).
- `fig_truthscore.pdf` CIAPA under Y6 and pairwise stats computed but not
  separately reported (pull from s1-truthscore.tsv if wanted in the caption).
- S2 mechanism (why the proxy-swap SA search humps) unexplained; needs new
  profiling. S5 acceptance mixed on the strict criterion (see S5 above).
- Simulator re-scoring caveat from S1: full-trace vs six-interval
  distinction produced identical numbers in this campaign (real property,
  documented in the S1 DECISIONS entry).
- Sweep/tier-check cloudsim.log originals for S5/S7 are transient (/tmp);
  the TSVs in this directory are the durable artifacts.
- CloudSimInterference `Placement.java` early exit (bba668a) is recorded in
  CONFORMANCE.md as a bug-fix candidate; default remains off so S15 and
  earlier runs reproduce exactly.

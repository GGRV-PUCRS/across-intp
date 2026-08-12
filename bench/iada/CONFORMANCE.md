# CONFORMANCE.md — IADA lineage conformance & provenance ledger

**Status:** authoritative for conformance claims as of 2026-08-12. Where
`docs/CLASSIFIER-INTERNALS.md` or `docs/iada-campaign.md` disagree with this
file on a *conformance* claim (what the papers say vs what the code does),
this file wins; those documents remain authoritative for internals snapshots
and campaign operation respectively.

**Scope.** Claim-by-claim audit of our three working trees —
`CloudSimInterference` (fork of ViniciusMeyer/CloudSimInterference, campaign
tag `campaign-2026-08` = `e49fb46`), `interference-classifier` (Meyer's
published classifier artifact), and this repo's `bench/iada/` pipeline —
against the published lineage (PU-01…PU-07 below). Compiled from a full
re-read of the lineage papers, a code audit with git archaeology, and the
first runs of Meyer's own reproducibility scripts (§5). Per owner decision
(2026-08-12): **audit only — no simulator repairs before the Meyer call.**

**Verdict vocabulary** (used in §3):
`conforms` · `diverges-deliberately` (+why) · `diverges-undocumented` ·
`never-executed` · `false-in-our-docs` (+correction applied).

**Terminology guard — "IDI" collision.** Paper 1 (ours, SBAC-PAD 2026) uses
IDI = *interference discrimination index* (profiler-side, signed
pairwise−solo delta). The IADA lineage uses IDI = *interference degradation
index* (response-time ratio; PU-06 Eq. 4). This ledger and the whole sim
campaign use the **IADA sense**; any Paper-2 text or figure caption must
disambiguate on first use.

---

## 1. Lineage corpus

| key | work | role |
|---|---|---|
| PU-01 | Ludwig et al. 2017, WSCAD (`ludwig2017policies`) | Problem formulation: interference vs affinity, R1–R4 placement policies. **No degradation table yet** (verified: no multiplier values, no SA/CIAPA). |
| PU-02 | Ludwig et al. 2019, CCPE (`ludwig2019optimizing`) | CIAPA. Origin of the level bands (Table 2: 0 / 1–20 / 21–50 / 51–100 %) and the degradation multipliers (Table 3, **with an Affinity column, no Network**). Cost Eqs 1–8: floor-1 product per PM, **average** across PMs. SA vs HC < 3 % apart. 5-exec/std-dev protocol. |
| PU-03 | Meyer et al. 2020, JSSPP (`meyer2020towards`) | The **affinity→"Network" relabel** happens here (its Table 3). The four workload patterns and the 3-app trace set originate here. 4/6/8/10/12-host sweep with the explicit 12/12 "producing no interference" degeneracy statement (its Fig. 6). ARIMA/MLP/GRU proactive leg. |
| PU-04 | Meyer et al. 2021, JSA (`meyer2021ml`) | The classifier paper: SVM + per-class K-Means, Unique/Segmented (+22 %), Table 3 targets **acc 0.97 / F1 0.98 / Rand 0.82**, 50k Node-Tiers training set. Reprints PU-02's multipliers as its Table 2 (1.07/1.62/1.74 for mem). |
| PU-05 | Xavier et al. 2022, SBAC-PAD (`xavier2022intp`) | IntP, the profiler; the 7 canonical metrics. |
| PU-06 | Meyer et al. 2022, JSS (`meyer2022iada`) | IADA, the simulator's paper. Eq. 2 (host score zero rule), Eq. 3 (sum across hosts), Eq. 4 / Fig. 6 (empirically re-measured IDI table), §4.3 (migration overhead in TotalIntScore), Algorithm 1 (monotone-migration acceptance), Table 3 (host sweep at constant 4 apps/host), Table 4 (24 OCPD intervals at 24/96). |
| PU-07 | Xavier 2019, PhD thesis (`xavier2019thesis`) | IntP + the 15-stress-ng stand-in catalog; prototype scheduler claims 35 % scheduling / 42 % resource efficiency. |

Full BibTeX in Appendix A. Our own anchors: **Paper 1 §VIII explicitly
commissions this program** ("close the loop … feeding the modernized
fingerprints to the IADA classifier and scheduler to quantify what the
measured fidelity differences cost in placement quality"); the Proposta's
dissertation scope (Obj. 1–3) is the measurement layer only — everything in
this ledger is Paper-2/defense material and does not alter dissertation
commitments.

**Degradation-table lineage (settled).** The multipliers debut in PU-02
Table 3 (CPU/Mem/Disk/Cache/**Affinity**) → PU-03 relabels Affinity as
"Network" (so the published "network interference" degradations were measured
as *communication affinity* degradations) → PU-04 reprints them as its
Table 2 → PU-06 re-measures them empirically (Eq. 4 / Fig. 6). **The fork
encodes the PU-06 empirical values** (mem 1.10/1.67/1.79 ≈ the paper's
1.10/1.69/1.79), not drift from the PU-02/PU-04 table (1.07/1.62/1.74).
`-Diada.degTable={fork,paper}` therefore selects *which published table*,
not fork-vs-paper (finding N1; settles decision S5's framing).

---

## 2. Findings registry

### 2.1 Paper-pass findings (N)

- **N1 — fork's degradation table = PU-06's own empirical IDI table.** See
  lineage note above. Reframes S5/E5: the E5 arm compares two *published*
  tables (PU-06 empirical vs PU-02/PU-04 printed) on our tiers; it found the
  choice scales IDI 16–25 % but preserves tier ordering.
- **N2 (revised 2026-08-12) — the Eq. 2 zero rule IS implemented; the real
  cost-function divergences are elsewhere.** An earlier audit pass recorded
  "solo-app host contributes 1, hosts summed → ≥1 cost floor per host"; that
  was **wrong** and is retracted here. Verified against
  `Solution.java` (`getCostFromHost`, lines 81–99): a host whose product
  stays 1 (zero or one non-solo cloudlet) returns **0** — Meyer's own code
  since 2020-06-16 (`9a9ef67`). The *actual* divergences vs the published
  equations, each verified at file:line, are in dossier §4.2: (a) per-factor
  PE normalization `clCost / (clPe/hostPe)` that appears in no published
  equation; (b) the host loop iterates IDs `1..countHosts()` (a *count* of
  occupied hosts) instead of the actual occupied-ID set; (c) a time-scaling
  factor `(end−start)/ttime`; (d) vs PU-02 only: sum across PMs where CIAPA
  averages (the fork follows PU-06's sum).
- **N3 — migration overhead enters the *reported* metric, not the SA
  objective.** PU-06 §4.3 describes migration overhead inside TotalIntScore
  (~18 s/migration measured, Fig. 11). In code, `migvalue = 10` is added
  when *printing* `interf with mig` (`IntContainerDataCenter.java:1256`),
  i.e. it is in the IDI we parse — but `Placement.java`'s annealers optimize
  `getTotalInterferenceCost()` alone, so the search never pays for
  migrations. The monotone-migration acceptance ("ratchet",
  `Placement.java:173-180`) **is** the published mechanism (PU-06
  Algorithm 1 + §4.4.1) — conformant, not our bug.
- **N4 — PU-06's own host sweep holds contention constant** (Table 3:
  6/12/24/48 hosts ↔ 24/48/96/192 apps = 4 apps/host throughout) and its
  Fig. 9 is ~flat per scheduler — flatness at constant contention is
  *expected*. Our E3 ratio sweep (9–28 hosts, fixed 28 apps) matched
  Meyer-2021-style designs instead; E3's reading is reframed by this plus
  N8 below.
- **N5 — the upstream frozen 24-interval list is real OCPD output.**
  Upstream `IntContainerDataCenter` hardcoded
  `{1, 311, 622, 940, …, 7164}` — 24 values, matching PU-06 Table 4's 24
  intervals for the 24-host/96-app arrangement; 7200 = the 2-hour trace
  segments. The OCPD genuinely ran in the *real* (LXD/CRIU) leg; the sim
  consumed one captured output, frozen. Our campaign replaced the list with
  `{1, 20}` retargeted to 120-sample traces (`a24fe55`, documented inline).
- **N6 — 20 s is the published minimum action spacing** (container
  migration meantime, PU-06). Our `{1,20}` interval accidentally equals it.
  Real-leg classification cadence was OCPD-driven, not fixed-180 s (180 s
  was Meyer 2021).
- **N7 — the real IADA controller (Python/LXD/CRIU) has no public repo**;
  the only cited artifact is ViniciusMeyer/CloudSimInterference. Node-Tiers
  traces derive from Wikimedia pageviews / Alibaba cluster-trace-v2018 /
  NASA WC98.
- **N8 (new, 2026-08-12) — the SA neighbourhood preserves per-host occupancy
  counts, so consolidation is structurally unreachable.** Both mutation
  operators are strict two-way swaps: `swapping()` exchanges two cloudlets'
  hosts, and `moving()` — despite its "move a cloudlet" comment — also calls
  `swapCloudletHost` (`Placement.java:250-308`), which is a strict exchange
  (`Solution.java:172-189`). Consequently the multiset of per-host cloudlet
  counts fixed by the initial placement is invariant across the entire
  search, for SA, SAO, HC, and GA alike. The falling-cost-with-hosts curve
  of PU-03 Fig. 6 (minimum at 12/12 "producing no interference") can never
  be produced by the search itself — only by the initial allocation.
  Together with the fact that per-cloudlet cost is a trace-driven constant
  (co-residents never enter it), this — not the previously-suspected missing
  zero rule — is the mechanical explanation for E3's flat host curve.

### 2.2 Code-audit findings (F)

- **F1 — OCPD never executed in the sim.** The live call
  (`MLC.getIntervalsOCPM`) is commented out at
  `IntContainerDataCenter.java:1142` — by Meyer's own commit (`c4e27df`
  "find OCP intervals" era) — in favour of the frozen list (N5).
  `nextInterval` is initialized to 1 and never advanced, so the frozen list
  is effectively read as a single constant period. Supporting R:
  `PCAtraces.R` has a min-gap 300 that is fatal at 120-sample traces;
  `getIntervalsOCPM` is still 7-metric with the swapped `nets`/`netp`
  header (`MLClassifier.java:214,228`).
- **F2 — migrations are free in the SA objective** (`nMig` unused in cost) —
  the objective side of N3.
- **F3 — SA is unseedable and non-reproducible run-to-run:**
  `Math.random()` (acceptance, `Placement.java:169`; operator choice, `:252`)
  and `ThreadLocalRandom` (`:311`). No seed flag exists. The `nCloudlets`
  ratchet is conformant per N3 but remains a variance driver worth
  documenting against PU-02's 5-exec/std-dev protocol.
- **F4 — the shipped classifier was NOT trained on the published 50k set.**
  The fork's `R/forced/` CSVs are ~500 low-cardinality rows/class with zero
  row overlap with `interference-classifier/training_dataset/` (~10k
  rows/class). Our docs' "trained by Meyer on LXC + Node-Tiers" claim was
  false (corrected, §6) and had underpinned the M1 in-domain argument.
  Class-count divergence on top: the published `input_dataset.R` rbinds
  `cache_miss` (6 classes, labelled `miss`); the fork's copy excludes it
  (5 classes).
- **F5 — our inc/dec/osc/con "patterns" are repetition-index aliases.**
  `generate-iada-tree.py` assigns rep1→inc, rep2→dec, … with no shape
  logic; docs claimed "the same classifier rules from the IADA paper" — no
  such rules exist in any lineage paper or artifact. (The genuine patterned
  traces are PU-03's 3-app × 4-pattern set, which Meyer shipped — used by
  W2.2.)
- **F6 — PU-02/PU-04 level bands are not implemented.** The fork's
  `predict.kmeans` maps centroid→level by argmax on a fixed feature column
  per class, not by the published 0/1–20/21–50/51–100 % bands; Rand Index
  was never measured anywhere in the fork; CV in our `retrain.R` was
  non-stratified with a 2× mem imbalance; cadence/horizon divergences
  (N6).

### 2.3 Validation findings from Meyer's own scripts (V, run 2026-08-12)

Runs in `IADA-second-born/meyer-validation/` (runner scripts + full output
there; shims documented in each script header).

- **V1 — both published accuracy scripts are broken on R ≥ 4.0** (scripts
  dated 01-2021). `SVM_accuracy.R`: the string `category` column no longer
  auto-converts to factor, so `e1071::svm` falls into regression mode and
  halts ("Need numeric dependent variable for regression").
  `kmeans_rindex.R`: `as.numeric(category)` coerces character→NA, so the
  Rand index would be computed against all-NA labels. One-line factor shim
  restores the 2021 semantics (deviation D2 in the runners).
- **V2 — `kmeans_rindex.R` cannot run on the full published dataset in
  31 GB RAM.** `fossil::rand.index` materializes n×n matrices; at
  n = 59,994 that is ~28.8 GB apiece. Observed: kernel OOM kill of R at
  anon-rss 28.2 GB / total-vm 56.5 GB (2026-08-12 12:31:29), and the
  earlier same-day machine crash was the same call. Either the published
  0.82 was computed on a subset or on a much larger machine. Our runner
  substitutes the exact contingency-table Rand index (O(n)) and asserts
  equality against `fossil::rand.index` on a 6,000-row subsample every run.
- **V3 — SVM accuracy overshoots the published target.** His script (1000
  rows/class of the published set, unseeded 70/30 split, poly-3 SVM):
  accuracy **0.9994 / 1.000 / 0.9994** over 3 runs, F1 ≈ 1.0, 56–61 support
  vectors, 0.016 s training. Published PU-04 Table 3: 0.97 / 0.98. The
  published numbers cannot come from this data + script as-is — the
  published set is near-perfectly separable. (Plan rule applied: report the
  delta, don't tune.)
- **V4 — the published Rand 0.82 is the upper tail of an unseeded,
  high-variance procedure.** Full-set Rand across 3 runs: **0.829 / 0.670 /
  0.777** (k=3 vs 6 true labels, per his script). Run 1 reproduces the
  published 0.82 almost exactly; runs 2–3 do not. Contributing script bug:
  `cl_total <- kmeans(…, nstart=20)` is computed and never used — the
  scored clustering is a second `kmeans()` with default `nstart=1`.

---

## 3. Conformance table

| # | published claim (source) | our state | verdict |
|---|---|---|---|
| C1 | Degradation multipliers per class×level (PU-02 T3 → PU-04 T2; PU-06 Eq. 4/Fig. 6 re-measured) | Fork hardcodes the PU-06 empirical table; `-Diada.degTable=paper` selects the PU-02/PU-04 printed table (mem/moderate 1.64→1.62 corrected to match print). E5: choice scales IDI 16–25 %, preserves tier order | `conforms` (to PU-06); table *choice* is a reporting decision (N1) |
| C2 | "Network" interference class (PU-03 onward) | Implemented; ledger note: the underlying multipliers were measured as *affinity/communication* degradations in PU-02 and relabelled in PU-03 | `conforms`, provenance caveat |
| C3 | Host score = Π app scores if j≥2 else 0 (PU-06 Eq. 2) | Zero-and-floor guard present (`Solution.java:98`, Meyer's `9a9ef67`); but each factor is PE-normalized `clCost/(clPe/hostPe)` — in no published equation | `diverges-undocumented` (normalization only; zero rule conforms — earlier audit claim retracted, N2) |
| C4 | TotalIntScore = Σ hosts (PU-06 Eq. 3); CIAPA averages across PMs (PU-02 Eq. 8) | Fork sums (`Solution.java:66-77`) | `conforms` to PU-06; `diverges-deliberately` from PU-02 (fork implements the later paper) |
| C5 | Migration overhead inside TotalIntScore (PU-06 §4.3, Fig. 11) | In the *reported* `interf with mig` metric (`IntContainerDataCenter.java:1256`, `migvalue=10`), absent from the SA objective (`Placement.java:166-171`) | `diverges-undocumented` (N3/F2) — top call-question |
| C6 | Monotone-migration acceptance (PU-06 Alg. 1, §4.4.1) | `nCloudlets` ratchet in SAO (`Placement.java:173-180`) | `conforms` |
| C7 | OCPD decides *when* to reschedule (PU-06 §4.2; real leg) | Sim: call site commented out, frozen 24-interval list (upstream) = captured OCPD output for 24/96 (Table 4); our campaign: `{1,20}` | `never-executed` (in the simulator — upstream's own freeze; N5/F1) |
| C8 | Decision cadence ≥ 20 s migration meantime (PU-06) | Our `{1,20}` interval equals it (accidentally) | `conforms` (numerically) |
| C9 | Host sweep at constant 4 apps/host, ~flat (PU-06 T3/Fig. 9) | E3 swept ratio 9–28 hosts/28 apps — different design; flat for a different reason (N8: occupancy invariant + trace-driven costs) | `diverges-deliberately` (design); E3 reframed per N4/N8 |
| C10 | Consolidation curve: cost falls with hosts, min at 12/12 (PU-03 Fig. 6) | Structurally unreachable by the search: both SA operators preserve per-host occupancy (N8); only the initial placement sets spread. **Probe result (W2.2): confirmed** — at 12 hosts/12 apps the score is ≈291/≈906 (shipped/rda50k), not →0, and flat across 3/6/12 hosts | `diverges-undocumented` (N8, measured) |
| C11 | Classifier: SVM+K-Means trained on 50k Node-Tiers (PU-04) | Shipped `.rda` trained on `R/forced/` ~500 rows/class, zero overlap with the published set; 5-class (drops `cache_miss`) vs published 6-class | `diverges-undocumented` upstream + `false-in-our-docs` (corrected, §6) (F4) |
| C12 | Acc 0.97 / F1 0.98 (PU-04 T3) | His script on his published set: 0.999–1.000 / ≈1.0 (V3) | measured; published numbers not reproducible *as stated* from the published artifact |
| C13 | Rand Index 0.82 (PU-04 T3) | 0.829 / 0.670 / 0.777 unseeded (V4); scored clustering is nstart=1, the nstart=20 model is dead code; O(n²) memory bug makes the full-set computation impossible as published (V2) | measured; `conforms` only as the procedure's upper tail |
| C14 | Level bands 0/1–20/21–50/51–100 % (PU-02 T2, PU-04 T1) | Not implemented: argmax over a fixed per-class feature column (F6); S8 showed the shipped levels were tie-break artifacts on saturated schedlat, re-keyed on psp | `diverges-undocumented` upstream; S8 documented ours |
| C15 | 7 canonical IntP metrics (PU-05) | Conforms in training; at-inference `nets`/`netp` swap existed upstream, fixed for classification in `a24fe55` (names now derived from the training frame), still present in the unused OCPD path | `conforms` (post-`a24fe55`), residue noted |
| C16 | inc/dec/osc/con behavioural patterns (PU-03/PU-06) | Our tree generator aliases patterns by repetition index — no shape logic (F5); docs corrected; Meyer's genuine 12 patterned traces adopted for W2.2 | `false-in-our-docs` (corrected, §6) |
| C17 | 5-exec/std-dev reporting protocol (PU-02) | Our campaign: 10–20 reps + bootstrap CIs — stronger; but the simulator itself is unseedable (F3) | `conforms` (exceeds), seeding caveat |
| C18 | Real-leg architecture: LXD/CRIU + Python controller + per-second IntP polling (Vinícius's email; PU-06) | No public artifact exists (N7); the simulator is the only published executable leg | provenance gap — call question |

---

## 4. Mechanism dossier (audit only — no repairs; each row = call agenda)

### 4.1 OCPD / decision cadence (F1, N5, N6)

**Paper:** OCPD watches per-second IntP extracts and triggers rescheduling
at change points (PU-06 §4.2); Table 4 reports 24 intervals for 24/96.
**Code:** `IntContainerDataCenter.InterferenceClassifier()` — the live call
`intervals = MLC.getIntervalsOCPM(…)` is commented out
(`IntContainerDataCenter.java:1142`); upstream hardcoded the 24 captured
values `{1,311,…,7164}`; `nextInterval` never advances, so `get(1)` is the
only period ever read. Our campaign retargeted the list to `{1,20}` for
120-sample traces (`a24fe55`, annotated inline). The R side of OCPD
(`PCAtraces.R`) hard-fails on 120-sample traces (min-gap 300) and its
feeder still uses the swapped 7-col header (`MLClassifier.java:213-228`).
**Classification:** upstream's own freeze — the sim never executed the
architecture's "when" mechanism; every published sim number inherits it.
**Repair sketch (not applied):** re-enable `getIntervalsOCPM` behind
`-Diada.ocpd=live|frozen|fixed:<n>`, port PCAtraces min-gap to a
trace-length fraction, advance `nextInterval`; validate frozen-vs-live on
Meyer's own 7200-sample traces.
**Ask Vinícius:** was the freeze a scaffold? Does a live-OCPD sim variant
exist anywhere?

### 4.2 Cost function vs the published equations (N2 revised, C3/C4)

**Paper:** PU-06 Eq. 2–3: host score = product of app IntScores if j≥2 else
0; total = Σ hosts. PU-02: floor-1 product per PM, *average* across PMs.
**Code** (`Solution.java:66-99`): total = Σ_{i=1..countHosts()}
`getCostFromHost(i)`, then scaled by `(end−start)/ttime`. Per host:
`hostCost = Π clCost/(clPe/hostPe)` over its non-solo cloudlets;
`return hostCost == 1 ? 0 : hostCost`.
**Verified divergences:** (a) the PE normalization multiplies every factor
by `hostPe/clPe` (≫1 when containers are small relative to the host) — in
no published equation; (b) `countHosts()` counts *distinct occupied* hosts
but the loop then queries host IDs `1..count` — correct only while the
occupied set is exactly `{1..k}` (true under the campaign's full-occupancy
configs; wrong under partial occupancy); (c) the time scaling is not in
Eq. 3; (d) the earlier "no zero rule" claim is retracted (N2) — the guard
is Meyer's own 2020 code.
**Ask Vinícius:** which exact cost variant produced the published Fig. 9 —
and was the PE normalization deliberate?

### 4.3 Migration cost (N3, F2, C5)

**Paper:** §4.3 — migration overhead (measured ~18 s) is part of the score
the optimizer minimizes.
**Code:** `migvalue = 10` ("oversized value",
`IntContainerDataCenter.java:1097`) is added only in the reporting line
`interf with mig` (`:1256`); the annealers' objective is
`getTotalInterferenceCost()` alone. So the search is migration-blind; only
the *acceptance* ratchet (4.4) limits migrations.
**Repair sketch (not applied):** `-Diada.migCost=<v>` added inside the SA
objective as `cost + nMig·v`; E-arm against the ratchet-only baseline.
**Ask:** which code produced the published numbers, and his view on
CRIU/NVMe-era migration-cost modelling (his email hypothesis).

### 4.4 SA acceptance, seeding, and the occupancy invariant (F3, N8, C6/C10)

**Conformant:** the SAO best-update ratchet (`Placement.java:173-180`)
matches Algorithm 1's monotone-migration acceptance.
**Divergent/undocumented:** (i) unseedable randomness (`Math.random`,
`ThreadLocalRandom`) — no reproducible run exists, relevant against PU-02's
protocol; (ii) **N8**: both mutation operators are strict swaps
(`swapping()`, and `moving()` whose comment says "move" but whose body
swaps — `Placement.java:291-308`, `Solution.java:172-189`), so per-host
occupancy counts are invariant for the whole search across SA/SAO/HC/GA.
Consolidation (PU-03 Fig. 6's minimum at 12/12) is unreachable; the
initial placement fully determines spread.
**Repair sketch (not applied):** `-Diada.seed`; add a true move operator
(host-capacity-respecting) behind `-Diada.moveOp=swap|move` and re-run the
host sweep.
**Ask:** was pure-swap deliberate (capacity safety?) or an implementation
shortcut?

### 4.5 Level mapping vs published bands (F6, C14, S8)

**Paper:** PU-02 Table 2 / PU-04 Table 1: utilization bands
0/1–20/21–50/51–100 % → absent/low/moderate/high.
**Code:** `predict.kmeans` orders the 3 centroids by one fixed feature
column per class and labels low/mod/hig by rank — no bands. S8 (decisions
log) showed the shipped regime levels were `which.max` tie-break artifacts
on a saturated column (schedlat = 100 in every centroid) and re-keyed them
on psp (col 14), halving variance and making the E4 ramp bind.
**Ask:** were the bands ever implemented anywhere, and did the real leg use
banded levels or centroid ranks?

### 4.6 Classifier training data (F4, C11–C13)

**Paper:** PU-04 — trained on 50k Node-Tiers samples.
**Artifacts:** fork ships `.rda` trained on `R/forced/` (~500 rows/class,
5 classes); the separately-published `interference-classifier` repo carries
`training_dataset/` (~10k rows/class, 6 classes incl. `cache_miss`-as-`miss`)
plus the reproducibility scripts audited in §2.3. Zero row overlap between
the two datasets.
**Ask:** what generated `R/forced/`, and was the shipped `.rda` ever meant
to represent the paper classifier?

---

## 5. Validation on Meyer's artifacts — status

| leg | design | status |
|---|---|---|
| W2.1a — his scripts, his data | `SVM_accuracy.R` + `kmeans_rindex.R`, 3 unseeded runs each, shims documented | **done 2026-08-12** — V1–V4 above; raw output `IADA-second-born/meyer-validation/meyer-scripts-output.txt` |
| W2.1b — our `retrain.R` on his 50k | 5-class and 6-class variants; stratified CV; Rand our way vs his way; `read.csv2` header quirk replicated for his numbers, fixed for ours | **done 2026-08-12** — seeded retrain.R-faithful CV on the full set: 5-class acc **1.0000** (sd 0.0001), 6-class **0.9998**, stratified delta ≈ 0 (F6's stratification concern is moot on his data); per-class cohesion Rand (our method, first recorded): cpu 0.53 / mem 0.53 / disk 0.76 / cache 0.76 / net NA (his `netp` level column is zero-skewed). Provenance wrinkle: read with `header=FALSE` the 5-class set is **exactly 50,000 rows** (the paper's "50k") while the published 6-class `input_dataset.R` yields 60,000 — the JSA 2021 classifier may have been 5-class after all (call question, softens F4's class-count leg). `cache_miss.csv` carries a trailing `;` (8th empty column). Artifacts: `rda-50k/` (drop-in, seeded, for W2.2 arm b); output `retrain-cv-output.txt` |
| W2.2 — his 12 patterned traces through our sim | `source/{bench4q,linkbench,tpch}/{inc,dec,osc,con}.csv` (281–1080 rows × 7 cols); arms: shipped-classifier vs 50k-retrained; hosts 3/6/12 at 4 apps/host + the 12/12 degeneracy probe (Eq. 2/N8 empirical test: paper predicts score→0) | **done 2026-08-12** — 70 sims, 0 failed (build `16ba42b` = `campaign-2026-08` + the `iada.simLimit` flag, major 52; horizon 280, vmStartup 0, 10 reps/leg). **(i) E3's flatness reproduces on his data** — shipped: idi_avg 289.0/292.6/291.3 at 3/6/12 hosts (sd 3–6); rda50k: 883.0/885.6/906.1 (sd 34–55) — a simulator property, not an our-data artifact. **(ii) The 12/12 degeneracy probe refutes the published prediction in the artifact**: score ≈291 (shipped) / ≈906 (rda50k), not →0, with `interference_avg` byte-flat across host counts (256.4/256.6/256.1) — direct empirical confirmation of N8 (occupancy invariance: initial packing is permanent; the zero rule can never fire). **(iii) F4 quantified**: swapping the shipped forced/-trained classifier for the published-50k-retrained one **triples** IDI on Meyer's own traces (~290 → ~885) — the two classifiers are not interchangeable. Raw: `meyer-sim-reps.tsv`, per-run logs `sim/` |
| W2.3 — both-tables leg | W2.2 main arm under `-Diada.degTable=paper` — PU-06-vs-PU-04 table on Meyer's own traces | **done 2026-08-12** — rda50k @3 hosts: fork table 883.0 → paper table **646.1** (−27 %); same direction/magnitude class as E5 on our tiers (16–25 %), now shown on Meyer's own traces |

---

## 6. Corrections applied to our own docs (2026-08-12)

- `docs/EXPERIMENT-STRATEGY.md` (M1 rationale): retracted "shipped
  classifier was trained on container-collected profiles (Meyer 2021,
  LXC + Node-Tiers)" → replaced with the F4 finding; M1's in-domain argument
  now rests on environment-closeness, explicitly not on training-set
  provenance.
- `bench/iada/docs/iada-campaign.md` §Methodological framing: same
  retraction; §IADA tree layout: retracted "same classifier rules from the
  IADA paper" → "per-repetition aliases" (F5) with a pointer here.
- `bench/iada/docs/CLASSIFIER-INTERNALS.md`: `R/forced/` is **not** the
  "Meyer 2021 paper dataset" (F4); `cache_miss` exclusion is a fork
  divergence from the published 6-class `input_dataset.R`, not upstream
  intent; the nets/netp swap note updated (classification path fixed in
  `a24fe55`; residue only in the unused OCPD path).
- `bench/iada/DECISIONS-sim-experiments.md`: S9 appended — S5/E5 reframed
  per N1 (both tables published; the flag picks a paper) and E3 reframed
  per N4/N8 (revised N2).

---

## Appendix A — BibTeX (owner-supplied)

```bibtex
@inproceedings{ludwig2017policies,
  author    = {Ludwig, ULisses L. L. and Kirchoff, Dionatr{\~a} F. and Cezar, Ian B. and De Rose, Cesar A. F.},
  title     = {Policies for Interference- and Affinity-Aware Placement of Multi-Tier Applications in Private Cloud Infrastructures},
  booktitle = {Proc. XVIII Simp{\'o}sio em Sistemas Computacionais de Alto Desempenho (WSCAD)},
  publisher = {SBC},
  year      = {2017}
}

@article{ludwig2019optimizing,
  author  = {Ludwig, ULisses L. L. and Xavier, Miguel G. and Kirchoff, Dionatr{\~a} F. and Cezar, Ian B. and De Rose, Cesar A. F.},
  title   = {Optimizing Multi-Tier Application Performance with Interference and Affinity-Aware Placement Algorithms},
  journal = {Concurrency and Computation: Practice and Experience},
  volume  = {31},
  number  = {18},
  pages   = {e5098},
  year    = {2019},
  doi     = {10.1002/cpe.5098}
}

@inproceedings{meyer2020towards,
  author    = {Meyer, Vin{\'i}cius and Ludwig, ULisses L. L. and Xavier, Miguel G. and Kirchoff, Dionatr{\~a} F. and De Rose, Cesar A. F.},
  title     = {Towards Interference-Aware Dynamic Scheduling in Virtualized Environments},
  booktitle = {Job Scheduling Strategies for Parallel Processing (JSSPP 2020), Lecture Notes in Computer Science},
  volume    = {12326},
  pages     = {1--24},
  publisher = {Springer},
  year      = {2020}
}

@article{meyer2021ml,
  author  = {Meyer, Vin{\'i}cius and Kirchoff, Dionatr{\~a} F. and da Silva, Matheus L. and De Rose, Cesar A. F.},
  title   = {{ML}-Driven Classification Scheme for Dynamic Interference-Aware Resource Scheduling in Cloud Infrastructures},
  journal = {Journal of Systems Architecture},
  volume  = {116},
  pages   = {102064},
  year    = {2021},
  doi     = {10.1016/j.sysarc.2021.102064}
}

@inproceedings{xavier2022intp,
  author    = {Xavier, Miguel G. and Cano, Carlos H. C. and Meyer, Vin{\'i}cius and De Rose, Cesar A. F.},
  title     = {{IntP}: Quantifying Cross-Application Interference via System-Level Instrumentation},
  booktitle = {Proc. IEEE 34th Int. Symp. on Computer Architecture and High Performance Computing (SBAC-PAD)},
  pages     = {231--240},
  year      = {2022},
  doi       = {10.1109/SBAC-PAD55451.2022.00034}
}

@article{meyer2022iada,
  author  = {Meyer, Vin{\'i}cius and da Silva, Matheus L. and Kirchoff, Dionatr{\~a} F. and De Rose, Cesar A. F.},
  title   = {{IADA}: A Dynamic Interference-Aware Cloud Scheduling Architecture for Latency-Sensitive Workloads},
  journal = {Journal of Systems and Software},
  volume  = {194},
  pages   = {111491},
  year    = {2022},
  doi     = {10.1016/j.jss.2022.111491}
}

@phdthesis{xavier2019thesis,
  author = {Xavier, Miguel G.},
  title  = {Data Processing with Cross-Application Interference Control via System-Level Instrumentation},
  school = {Pontif{\'i}cia Universidade Cat{\'o}lica do Rio Grande do Sul (PUCRS)},
  year   = {2019}
}
```

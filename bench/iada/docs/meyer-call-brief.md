# Call brief — Vinícius Meyer (IADA), prepared 2026-08-12

Working agenda for the call. Evidence for everything below:
[`../CONFORMANCE.md`](../CONFORMANCE.md) (findings N1–N8, F1–F6, V1–V4,
verdict table C1–C18, mechanism dossier §4);
[`../DECISIONS-sim-experiments.md`](../DECISIONS-sim-experiments.md)
(S1–S9, campaign numbers). Context: his email described the production
IADA loop — LXC/LXD live migration via CRIU, a Python controller polling
per-second IntP extracts, the classifier, OCPD deciding *when*, SA deciding
*where*, with hard failures on disk-intensive apps under CRIU.

---

## 1. What we present (contributions)

1. **Recovery + parameterized simulator.** His CloudSimInterference fork
   runs end-to-end again (JRI/R 4.3, Java 17 launcher, `--release 8`
   bytecode); every sizing/behaviour constant is now a flag defaulting to
   the committed value (`iada.hosts/vms/cloudlets/horizon/simLimit/
   vmStartup/regime/degTable/regimeRamp`) — an unflagged run reproduces the
   banked campaign bit-for-bit in expectation. Campaign provenance frozen
   (tag `campaign-2026-08`, `results/PROVENANCE.md` manifest).
2. **The S1–S8 simulation campaign** (gate + E1–E5, 10–20 reps/arm,
   bootstrap CIs). Headlines: the 6th "regime" cost term carries ~39 % of
   tier B's IDI (E2); the degradation-table choice scales IDI 16–25 % but
   preserves tier order (E5); startup delay is inert at 12 hosts (E1); the
   host curve is flat 9–28 hosts (E3 — now explained, see §2.4). **S8:** the
   shipped regime levels were k-means tie-break artifacts on a saturated
   schedlat column; re-keying levels on psp halves rep variance and makes
   the ramp experiment statistically resolvable — the candidate tier-B
   rebank is ≈4400 (vs 5750), pending the validation below.
3. **Approach B / 15-metric portable fingerprint** (adds scheduler-pressure
   and VM-available metrics to the canonical 7) and the fingerprint-vs-
   cost-term decomposition (E2).
4. **Validation on his own artifacts (first external reproduction attempt
   of the classifier stack):**
   - His `SVM_accuracy.R` + `kmeans_rindex.R`, run his way on his published
     `training_dataset/`: SVM accuracy 0.999–1.000 (published: 0.97/0.98);
     Rand 0.67–0.83 unseeded across runs (published: 0.82).
   - Our seeded retrain pipeline on the same data: CV accuracy 1.0000
     (5-class, full 50k), 0.9998 (6-class with `cache_miss`).
   - His 12 patterned traces (bench4q/linkbench/tpch × inc/dec/osc/con)
     through the simulator: shipped-classifier vs 50k-retrained arms,
     3/6/12-host arrangements incl. the 12/12 degeneracy probe, and a
     both-degradation-tables leg. *(Results land in CONFORMANCE.md §5 —
     flag any leg still running at call time.)*
   - Reproduction notes he may want for his own archive: both scripts need
     a one-line factor shim on R ≥ 4.0; `fossil::rand.index` allocates
     O(n²) (~29 GB at n≈60 k — it OOM-killed our 31 GB box twice; exact
     contingency-table form substituted); `kmeans_rindex.R` computes an
     `nstart=20` model it never scores (the scored one is `nstart=1` —
     the main source of the 0.67–0.83 spread); `cache_miss.csv` has a
     trailing `;` (8th empty column).

## 2. What we ask (only he can answer)

1. **`R/forced/` provenance (F4).** The shipped `.rda` classifier was
   trained on `forced/` (~500 low-cardinality rows/class, 5 classes), not
   the published 50k set (zero row overlap). What generated `forced/`, and
   was the shipped `.rda` ever meant to represent the paper classifier?
   Related: the published `input_dataset.R` rbinds `cache_miss` (6 classes,
   60 k rows), but the 5-class set is exactly 50,000 rows — was the JSA 2021
   classifier 5-class or 6-class?
2. **The OCPD freeze (F1/N5).** The sim's `getIntervalsOCPM` call is
   commented out in favour of a hardcoded 24-interval list that matches
   Table 4's 24/96 arrangement, and `nextInterval` never advances. Was the
   frozen list a temporary scaffold? Does a version with live OCPD in the
   simulator exist? (The 24-interval list looks like real captured OCPD
   output — from which run?)
3. **Migration cost in the objective (N3/F2).** JSS §4.3 describes migration
   overhead inside TotalIntScore (~18 s measured), but in the artifact
   `migvalue=10` only enters the printed `interf with mig` metric — the SA
   objective never pays for migrations. Which code produced the published
   Fig. 9/Table numbers? And his current view on CRIU/NVMe-era migration
   cost (his email hypothesis) — we'd turn it into an E-arm.
4. **Cost-function details (N2/N8).** The Eq. 2 zero rule is implemented,
   but each factor is normalized by `clPe/hostPe` (in no published
   equation), and both SA operators are strict swaps — per-host occupancy
   counts are invariant for the whole search, so consolidation behaviour
   (JSSPP 2020 Fig. 6's minimum at 12/12) cannot emerge from the search.
   Deliberate (capacity safety) or shortcut? Which cost variant is the
   published one?
5. **Level bands (F6).** The 0/1–20/21–50/51–100 % bands (CCPE Table 2 /
   JSA Table 1) are not in the artifact — levels come from centroid ranks
   on one feature column per class. Were the bands ever implemented, and
   did the real leg use bands or ranks?
6. **The real controller (N7).** Is the Python/LXD/CRIU controller code
   available privately? The Wikimedia/Alibaba/NASA 2-h profiled segments
   that drove Node-Tiers? Even a partial drop would let us validate the
   sim against the real loop's decisions.
7. **Standardization asks for our Paper 2.** Which degradation table he'd
   standardize on for a rebank (JSS empirical vs CCPE/JSA printed — N1);
   whether he sees the psp re-key (S8) as faithful to the architecture's
   intent; and whether he wants co-authorship/acknowledgement on the
   validation write-up.

## 3. Proposals to float (time permitting)

- **Repair menu, gated on his answers** (each becomes a flagged E-arm with
  the existing gate pattern): live OCPD; migration term in the SA
  objective; a true move operator; `-Diada.seed` for reproducibility.
- **Forecasting leg:** JSSPP 2020's ARIMA/MLP/GRU and JSS's "proactive"
  future work partially claim the direction — align before we invest.
- **Fingerprint upgrade path:** Paper 1's per-family calibration guidance +
  the 15-metric tier as the classifier input he never had; the tier
  campaign quantifies what fidelity differences cost in placement quality
  (Paper 1 §VIII's commissioned loop-closure).

# R3 -- audit of the v3.3 victim `mbw` disagreement under W5 colocation

Date: 2026-09-19. Spec: the local rerun brief, step 10; rationale:
paper-assets/JSA-RERUN-BRIEF-v2.md R3. Disputed sentence: main-jsa.tex §6.1
(line 545), `\tbd{R3}` occurrence 1.

## Question

Under W5 colocation (victim vs the app05_membw aggressor, host envs), v2.1
reads the victim's `mbw` rising by 1 to 4 points (app01_ml_llc, app11_sort_net)
while v3.3 reads it falling by 18 to 38.5 (Cliff's delta = -1.0). Is this a
resctrl mon_group enrollment bug in v3.3 (aggressor inside the victim's group),
an inconsistent ceiling normalization (42656 MB/s fallback vs the audited
281600 MB/s; the C34 "0.151 correction"), or a real signal?

## Code paths examined

Orchestration (bench/run-intp-bench.sh):

- Pairwise stage profiles the VICTIM ONLY; the profiler attaches to the victim
  cgroup and the aggressor runs unprofiled in its own cgroup and cpuset B
  (comments lines 4188-4194; stage_pairwise body 4197-4238; cpuset split
  680-684, 704-705). One profiler instance per run, so v3.3's fixed mon_group
  name cannot collide across concurrent instances.
- v3.3 invocation: run_profiler_v3_3 (3720-3789). Captures with
  `--no-diag-cols` (3753-3754), so the `mbw_raw_mbps` diagnostic column is NOT
  in the archived portable.tsv. The harness passes `--mem-bw-max-bps` resolved
  from $OUTPUT_DIR/capabilities.env INTP_MEM_BW_MBPS x 1e6
  (resolve_mem_bw_max_bps 3604-3636; applied 3781-3782).
- v2.1 invocation: run_profiler_v2_1 (3521-3584). NO `--mem-bw-max-bps` is
  passed; v2.1 self-detects the ceiling (below).

v3.3 profiler (variants/v3.3-ebpf-core-cgroup):

- mon_group lifecycle: one group, fixed name "intp-v3.3"
  (src/intp_agg.c:60, 977-996), seeded recursively from the VICTIM cgroup's
  cgroup.procs (read_cgroup_pids_rec, src/intp_agg.c:355-402) with a
  /proc descendant walk (resctrl/resctrl.c:101-195), re-scanned each interval
  (src/intp_agg.c:1188-1202). The aggressor is never enrolled: the seed reads
  only the victim cgroup, and the victim-delta rows confirm it (the aggressor
  cgroup is a sibling, not a descendant).
- Read path: resctrl_read_mbm_pct_and_raw (resctrl/resctrl.c:287-328) sums
  mbm_total_bytes across mon_L3_* domains (197-244), takes the per-interval
  delta against the previous sample, and normalizes:
  pct = delta/interval / caps->mem_bw_max_bps * 100, unclipped by default
  (clip_mbw=off per the archived headers). The ceiling comes from the harness
  override when given (src/intp_agg.c:853-854), else from
  detect_memory_bandwidth_max_bps (detect/detect.c:375-398).
- First sample returns 0 (baseline set), so counter offsets and RMID reuse
  cannot bias the deltas.

v2.1 profiler (variants/v2.1-c-abi-cgroup):

- Same hardware source for cgroup targets: the uncore backends are rejected
  for sub-system targets (src/mbw.c:168-179) so mbw falls through to
  resctrl_mbm (src/mbw.c:43-92), a shared per-target mon_group
  (src/resctrl.c:312-368, name intp_v2_rdt_<pid>).
- Ceiling: self-detected as n_imc x MT/s x 1e6 x 8 (src/detect.c:433-465),
  which on this host (8 uncore_imc PMUs, DDR 4400 MT/s) yields 281.6e9 B/s =
  the audited 281600 MB/s. The w5 v2.1 solo cells are byte copies of the
  post-C34 re-run cells, so both v2.1 arms sit on the audited ceiling.

## Data findings

1. Raw mbm_total_bytes deltas are NOT logged anywhere in the w5 cells:
   portable.tsv was captured with --no-diag-cols (mbw_raw_mbps suppressed),
   and groundtruth.tsv's resctrl_mbw_bps column is "--" by design
   (bench/intp_metrics.py:361 comment; verified in the cells). Direct
   recomputation from raw counters is impossible; the recompute below uses the
   logged mbw percent and the documented ceiling ratio.

2. The two arms of the v3.3 victim delta are on DIFFERENT ceilings:
   - The w5 v3.3 SOLO cells are byte-identical copies of the pre-audit
     cross-deployment campaign (p2-15metric-xdeploy-1of3, collected
     2026-06-10): verified by cmp for every cell present in both trees, 168 of
     168 identical across bare+container (app07_ordering excepted, see item 4).
     That campaign's v3.3 mbw was normalized against the 42656 MB/s fallback
     ceiling (intp-detect.sh's DDR4 fallback, captured when dmidecode failed;
     docs/DECISIONS-container.md C34). The copied cells carry their own proof:
     113 "mbw exceeded ceiling ... ceiling=42656 MB/s" warnings in
     */v3.3/solo/*/rep*/portable.v3.3.log (e.g.
     container-lxc/v3.3/solo/app05_streaming/rep1), zero in pairwise logs.
   - The w5 v3.3 PAIRWISE cells were freshly collected 2026-06-13 (run.json
     start_iso 19:03+, after the C34 ceiling audit closed 2026-06-13) into a
     campaign dir whose capabilities.env carries the audited
     INTP_MEM_BW_MBPS=281600 (written 2026-06-13T16:31 by the detect stage,
     before the first pairwise rep), and the harness passes it as
     --mem-bw-max-bps 281600e6. Cross-check: the v3.3 and v2.1 pairwise
     readings are within 1.7x of each other (app11 bare 10 vs 6) although both
     read the same hardware counter for equivalent runs; on the 42656 scale
     the v3.3 pairwise arm would imply a raw rate about 4x below v2.1's.
   - Ratio: 42656/281600 = 0.1514, the documented 0.151 correction.

3. Recompute (r3-recompute.py, parsing identical to the pipeline: warmup row
   dropped, per-rep medians, median and Cliff's delta over 12 reps). The
   as-logged columns reproduce results/02-w5-colocation/w5-victim-delta.tsv
   exactly (e.g. bare app11 46.5 -> 10.0, delta -36.5). Rescaling the v3.3
   solo arm by 0.1514 (r3-mbw-recomputed.tsv):

   | env | victim | delta as logged | delta rescaled | v2.1 delta |
   |---|---|---|---|---|
   | bare | app01_ml_llc | -18.00 | +3.21 | +1.00 |
   | bare | app11_sort_net | -36.50 | +2.96 | +3.00 |
   | container | app01_ml_llc | -27.50 | +1.77 | +0.00 |
   | container | app11_sort_net | -38.50 | +2.65 | +4.00 |

   Cliff's delta flips from -1.0 to +0.75..+1.0 in these four cells. The
   physical cross-checks agree with the corrected direction: the victim's
   per-cgroup LLC miss rate (llcmr) roughly triples and membw_est
   (llc_misses x 64B/s, perf-based, ceiling-independent) RISES under
   contention (app11 bare 4224 -> 5656), so the victim's DRAM traffic rises;
   the logged v3.3 fall was the scale artifact, not a misread of the counter.

4. Provenance exception: the w5 v3.3 solo app07_ordering cells are NOT in the
   local pre-audit snapshot (index.tsv dates them 2026-06-12/13, a later
   collection into the same campaign dir), so their ceiling is ambiguous and
   the rescaled row for app07 (+6.3) should not be trusted; if its solo arm is
   already on the audited ceiling, its logged delta (-3) matches v2.1 (-2).
   Either way app07 does not support a v3.3-only falling-mbw claim, and the
   paper already rests no victim-delta claim on mbw.

## Verdict

EXPLAINED, and CORRECTED IN ANALYSIS. The sign flip is a units mismatch
between the two arms of the delta: v3.3 solo baselines are byte-identical
copies of pre-audit cells on the 42656 MB/s fallback ceiling, while the
pairwise cells were collected after the ceiling audit at 281600 MB/s. No
mon_group enrollment bug: the aggressor is never in the victim's group, and
the delta accounting is sound. Rescaled to a common ceiling, v3.3 reads the
victim's mbw rising by 2 to 3 points in the disputed cells, consistent with
v2.1's 1 to 4. `mbw` victim deltas should remain descriptive-only: the
residual app07 ambiguity shows the column still mixes provenances.

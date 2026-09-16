# DENSITY-SWEEP — the W2.2 zero-floor anomaly, resolved, and a genuine density sweep

Driven by `jsa-repo-fix-brief.md` Phase 4. This is a **new, exploratory**
result — kept separate from the banked E1-E5/S8-S13 numbers and from the
existing Appendix A host-count-flatness discussion (`fig:a1`, E3), which
stays as-is (it is accurate for the sweep it actually ran).

## Step 1 (mandatory prerequisite) — why W2.2's score wasn't zero at hosts==apps

**Background.** `CONFORMANCE.md` W2.2 found that at the theoretically
degenerate 12-hosts/12-apps point (1 cloudlet/host, where `Solution.
getCostFromHost`'s zero-floor rule should fire for every host), the
measured score was nonzero (≈291 shipped classifier / ≈906 retrained) and
flat across 3/6/12 hosts. The brief treats resolving this as a hard
prerequisite for building any density sweep on top of it — a sweep over an
unexplained nonzero floor produces numbers nobody can trust.

**Investigated (2026-09-16), by instrumentation, not just static reading.**
Added `-Diada.debugHostCost=on` to `IntContainerDataCenter.
fillInitialSolution` (prints CloudSim's own per-host container count and
`host.getId()` right after the initial container→host binding, before any
SA mutation runs). Ran three configurations against a real 12-cloudlet tree
(3 workloads × 4 patterns, this session's tier-B vm-guest data) at 12 hosts:

| run | flags | result |
|---|---|---|
| 1 | `PM_COUNT=12` (default container sizing) | **12 hosts declared, but only 3 got any containers — 4 each. 9 hosts sat completely empty.** `idi_avg=1716.5` |
| 2 | `PM_COUNT=12 PM_CPU=1` | Identical packing (still 4/host on 3 hosts) — `PM_CPU` (the `input.txt` "pm" line) has **no effect** on packing |
| 3 | `PM_COUNT=12 -Diada.containerPes=48` | **All 12 hosts got exactly 1 container each.** `idi_avg=0` |

**Root cause, fully identified:** `host.getId()` is a clean, contiguous
1..N sequence (run 1 above already rules out the N2/host-ID-indexing
hypothesis — `getTotalInterferenceCost()`'s `for(i=1;i<=nHosts;i++)`
assumption is fine). The actual mechanism is in `xxIntExample.java`:
`VM_PES = HOST_PES = { 48 }` (lines 86-87, 102-103) and, before this fix,
`CONTAINER_PES = { 12 }` (line 95) were **hardcoded constants**, entirely
independent of `-Diada.hosts`/`PM_COUNT`/the `input.txt` "pm" line's CPU
field. `48 / 12 = 4` — the VM/container allocation policy always packs
exactly 4 containers onto every host it uses (first-fit, by PE capacity),
and only opens as many hosts as that packing needs; every additional host
`-Diada.hosts` declares beyond that sits structurally idle for the initial
placement. Combined with the already-documented N8 finding (SA's swap
operators preserve per-host occupancy counts), this idle capacity can never
be used by the search either — **so `-Diada.hosts`/`PM_COUNT` was never
controlling density at all**, for W2.2's probe or for the original E3 host
sweep. `Solution.getCostFromHost`'s zero-floor rule itself is *correct* —
run 3 proves it fires exactly as designed once density is genuinely 1:1.

**Fix:** `xxIntExample.CONTAINER_PES` is now `-Diada.containerPes=<v>`
(default `12`, unchanged) — the first flag that actually controls
containers-per-host. `-Diada.debugHostCost=on` is left in place
(default off, no output) as permanent, cheap diagnostic tooling for
anyone debugging placement density again.

**This changes how N4/N8/C9/C10 and the W2.2 write-up should be read**: the
existing "SA occupancy invariance means consolidation pressure never enters
the objective" explanation is still correct as far as it goes, but it was
answering a question sitting on top of a more basic one — the *initial*
placement's density was never what `-Diada.hosts` implied either. Both
mechanisms are real and stack: even with `-Diada.containerPes` fixed correctly,
N8's occupancy-count invariance still means a bad initial packing can't be
undone mid-search.

## Step 2 — genuine density sweep, tier B (psp-keyed), n=5/point

Fixed 28-cloudlet trace set (`/tmp/tree-B-vm-guest`, this session's tier-B
vm-guest tree — regenerate per S10's recipe if picking this up, it lives
only in `/tmp`), `-Diada.hosts=28 -Diada.vms=28` (**not** `PM_COUNT` — that
env var only ever wrote a cosmetic "pm N cpu" line into `input.txt` that
`xxIntExample`'s actual host/VM creation never reads; the real host-count
control is `-Diada.hosts`/`IADA_HOSTS`, confirmed by a first failed attempt
at this sweep that used `PM_COUNT=28` alone, silently ran with the
`IADA_HOSTS` default of 12, and deadlocked at `containerPes=48` — 28
cloudlets each needing a full host, only 12 hosts' worth of capacity
available. A second, correct run is what this table reports), enough hosts
for the sparsest point. `-Diada.containerPes` swept instead of host count
(the brief's original plan swept hosts 28→7; per Step 1, that lever doesn't
work — this is the corrected lever for the same intent, apps/host actually
varying). `n=5`/point, not the brief's suggested 10-20 — see the timeout
note below for why the two sparsest points are capped here.

| containerPes | apps/host (48/pes) | n | idi_avg mean | sd | status |
|---|---|---|---|---|---|
| 48 | 1.0 | 5 | **0.00** | 0.00 | interval-1-only (see below) |
| 32 | 1.5 | 5 | **0.00** | 0.00 | interval-1-only (see below) |
| 24 | 2.0 | 5 | **63.93** | 6.30 | fully converged, 55-62s/rep |
| 17 | 2.82 | 5 | **117.50** | 20.22 | fully converged, 55-59s/rep |
| 12 | 4.0 (the original hardcoded default) | 5 | **4263.70** | 207.55 | fully converged, 57-59s/rep; matches S10's independent n=20 gate rerun (4283.5±138.2) to within 0.5% — good cross-check |

Raw: `bench/iada/results/sim-experiments-20260916/density-sweep/density-pes{48,32,24,17,12}-ratio*.tsv`
(+ `density-sweep-combined.tsv`).

**A genuine consolidation curve appears** once density is real: 0 → 0 →
64 → 118 → 4264 as apps/host rises 1.0 → 1.5 → 2.0 → 2.82 → 4.0. The last
jump (117.5 → 4264, apps/host 2.82 → 4.0) is roughly 36x, far larger than
the earlier steps — worth flagging as a steep, not smooth, curve; this
sweep has five points, not enough to characterize the shape between 2.82
and 4.0, and the brief's original request (10-20 reps/point, more density
points) would sharpen this if the maintainer wants to invest more compute.

**Step 3 (scoring).** Run under current (self-referential) scoring only —
oracle scoring (S13/Phase 3.2) was not completed this pass, so there is
nothing to run the sweep under a second time yet. If 3.2 lands later, rerun
this sweep under `-Diada.oracleLabels=on` once that flag actually does
something, and add the second curve to `F-simexp-density`.

**Why 48/32 report exactly 0.00, sd 0.00, not a converged low number.** Both
points hit their 400s per-rep timeout on every one of 5 reps, every time —
this is a **new, distinct finding from the W2.2 zero-floor mechanism
above**, not the same thing: `Solution.getTotalInterferenceCost()` iterates
`for (i=1; i<=countHosts(); i++) getCostFromHost(i)`, and `getCostFromHost`
itself does an O(cloudlets) scan (calling `runninginOnlyOneHost`, itself
another O(cloudlets) scan) per host — so one call is roughly
O(hosts × cloudlets²). At `containerPes=48` (28 active hosts) and `=32`
(~19 active hosts), this is called at least 4x per SA iteration, up to the
`maxNoChange=10000` iteration cap — the search never finishes interval 2
within a practical timeout. The number reported (0.00) is not wrong or
fabricated: it is interval 1's placement, which genuinely is 1-per-host (or
close to it) and genuinely does cost 0 by `Solution`'s own zero-floor rule
— it is simply not a multi-interval SA-optimized average like every other
point in this table, and should not be read as "the search found zero
interference is achievable," only as "the search never got far enough to
find anything else." **This is a real performance limitation of the SA
implementation at low host-density, independent of and additional to the
W2.2 finding** — worth its own line in `PAPER-SYNC.md` if this sweep is
cited, and a good target for anyone wanting to extend this sweep to sparser
points (the O(hosts×cloudlets²) cost function itself is the thing to
optimize, e.g. memoizing `runninginOnlyOneHost` per solution instead of
recomputing it inside every `getCostFromHost` call).

## Step 4 — figure

`F-simexp-density` (new stem, registered in `fig_names.py`), rendered by
`bench/plot/plot-sim-experiments.py`'s new `fig_density()` (extended, not
forked, per the brief's instruction) via its `--density-tsv` flag pointing
at `density-sweep-combined.tsv`. Installed:
`results/figures/p2-sim-experiments/degradation-index-rises-with-genuine-
placement-density--density-sweep-20260916.{png,pdf}`. The two
interval-1-only points are marked with a red X and an in-plot caption note,
not silently plotted as if they were converged means.

## Step 5 — relation to Appendix A / existing E3

This is **new** material — Appendix A's existing host-count-flatness
discussion (`fig:a1`) is accurate for the sweep it actually ran (varying
`-Diada.hosts` while `-Diada.containerPes` stayed at the hardcoded default)
and stays as-is. `PAPER-SYNC.md` should add a pointer from Appendix A to
this new result, not replace the existing text — and should note that E3's
"host count 9→28" axis, in light of Step 1, was never actually varying
placement density in the way its own framing implied.

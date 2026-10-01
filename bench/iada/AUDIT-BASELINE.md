# AUDIT-BASELINE — regression baseline before this pass's fixes (2026-09-16)

Per `jsa-repo-fix-brief.md` Phase 0 step 4: reproduce the banked numbers
under the current, as-checked-out configuration, before applying any fix,
as the regression baseline every later phase is compared against.

## What was actually reproduced, and one honest gap

**T1/A gate arm and the CV/transfer numbers were reproduced independently,
before this session's Phase 2 (CV-leakage) or Phase 3 (S8 rebank) changes
altered anything they'd be compared against:**

| target | banked (prior campaigns) | this session's reproduction | agreement |
|---|---|---|---|
| T1 gate idi_avg | ≈6399 | 6520.9 ± 185.3 (n=10) | within ~1.9% |
| A gate idi_avg | ≈3629 | 3618.8 ± 242.9 (n=10) | within ~0.3% |
| within-env CV accuracy (all tiers/envs) | 0.998–1.000 | 0.998–1.000 (flat, unmodified `cv_eval`, before the grouped-CV fix) | exact |
| host→VM transfer accuracy (T1/A/B) | 0.507/0.426/0.780 | 0.508/0.426/0.780 | exact to 3 decimals |

**Gap, stated plainly:** tier B's gate arm was **not** independently
reproduced in its pre-fix (schedlat-keyed) form this session. Step 0's
toolchain build and Step 3.0's wiring-gap investigation (S10) happened
before the first B gate run of this session, and by the time a B gate arm
was run, the psp re-key patch had already been applied to the canonical R
config (`~/iada-tier-rda/B/kmeans.R`) — deliberately, since
reverting a ratified, already-validated fix just to re-measure a baseline
that's already recorded in `DECISIONS-sim-experiments.md`'s own S8 section
would have been pure overhead. The pre-fix B number used throughout this
pass's write-ups (**5382.5, sd 337, n=10**) is therefore the *existing
repo's own recorded value* (`DECISIONS-sim-experiments.md` line ~175, "gate
B 5382.5 sd 337"), not an independent re-verification. It is used as
historical context (documented as superseded, per S10), never as a number
this session claims to have re-derived from scratch.

**Toolchain note:** this checkout had no R, no JDK, and no pre-built
CloudSim/IADA artifacts at the start of this pass — all reproduction above
required standing up R 4.5.2 + rJava/JRI, compiling `CloudSimInterference`
against the system's JRI jars (the vendored ones predate the installed
R/rJava and don't link), and building a 28-trace vm-guest/v3.3 source tree
from raw campaign captures. Full recipe: `DECISIONS-sim-experiments.md` S10.
JDK 8 was required for the simulator to run at all (JDK 20+ disables
`Thread.stop()`, which JRI's `Rengine.stop()` calls).

## Disposition

Good enough to trust as "this environment reproduces the banked numbers"
for T1/A and the classifier-quality numbers, which is what every
downstream Phase 1-4 comparison in this pass is actually measured against.
The one gap (B's pre-fix baseline) is inherited from the repo's own prior
record rather than re-verified, and is flagged everywhere it's used.

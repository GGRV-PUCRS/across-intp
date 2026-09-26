#!/usr/bin/env bash
# run-sim-experiments.sh — the simulation-side experiment campaign.
#
# Every arm here varies a CloudSim parameter that used to be a compile-time
# constant. Nothing re-profiles: the 15-metric and W5 captures already on disk
# are the only inputs, so this is reproducible without touching a testbed.
#
# The build is the --release 8 tree, which targets the same bytecode level as
# the banked Eclipse artifacts. That matters because the JDK 17 (major 61)
# rebuild moved tier T1's index by ~200 while A and B held, so major 52 is the
# conservative choice until that is settled.
#
# Arm 0 is a gate: if the rel8 build with every parameter left at its default
# does not reproduce the banked arm, nothing after it is interpretable, so the
# script stops rather than burning two hours on results nobody can use.
set -uo pipefail

AX="${AX:-/home/dedealien/Desktop/intpismo/across-intp}"
CS="${CS:-/home/dedealien/Desktop/intpismo/CloudSimInterference-rel8}"
OUT="${OUT:-/home/dedealien/Desktop/intpismo/sim-experiments-20260811}"
REPS="${REPS:-10}"
BASELINE="${BASELINE:-/home/dedealien/Desktop/intpismo/ab-run-20260811/reps-java8.tsv}"
cd "$AX"
mkdir -p "$OUT"

# One arm = one TSV. JAVA_EXTRA carries the -D flags under test; PMS overrides
# the host count for the sweep (both knobs must move together, since PM_COUNT
# shapes input.txt while iada.hosts sizes the datacenter).
arm() {
  local name=$1 tiers=$2 pms=$3; shift 3
  local extra="$*"
  if [ -s "$OUT/$name.tsv" ] && [ "$(wc -l < "$OUT/$name.tsv")" -gt 1 ]; then
    echo "[skip] $name (already has rows)"; return 0
  fi
  echo "[arm ] $name  tiers=$tiers pm=$pms  $extra"
  CS="$CS" TIERS="$tiers" REPS="$REPS" PM_COUNT="$pms" IADA_HOSTS="$pms" IADA_VMS="$pms" \
    IADA_JAVA_EXTRA="$extra" \
    TSV_OVERRIDE="$OUT/$name.tsv" \
    bash bench/iada/scripts/run-tier-sim-reps.sh >/dev/null 2>&1
  local n; n=$(($(wc -l < "$OUT/$name.tsv" 2>/dev/null || echo 1) - 1))
  echo "[done] $name -> $n rows"
}

echo "=== ARM 0 — gate: rel8 build, all parameters default ==="
arm gate-default "T1 A B" 12

python3 - "$OUT/gate-default.tsv" "$BASELINE" <<'PY'
# Gate on overlap of rep-level bootstrap CIs rather than on equality: both
# sides are stochastic SA samples, so demanding equal means would fail on
# noise. Any tier whose interval misses the baseline's is a real discrepancy.
#
# The baseline pools every same-config java8 rep available: the first-pass
# 10-rep batch PLUS the 20-rep confirmation legs. The first campaign run
# gated against the 10-rep batch alone and failed on T1 (+147.7
# [+17.6, +282.1]) -- but that batch is the same outlier (mean 6251, sd 105
# vs the confirmed ~6425/286) that manufactured the S2 false positive, and
# the rel8 gate mean 6398.8 sits dead-centre of the confirmation. Gating a
# 10-rep sample against a known-anomalous 10-rep sample re-runs the S2
# mistake with the roles reversed.
import sys, glob, os
import numpy as np, pandas as pd
new, base = (pd.read_csv(p, sep="\t") for p in sys.argv[1:3])
for extra in glob.glob(os.path.join(os.path.dirname(sys.argv[2]), "confirm-*-java8.tsv")):
    base = pd.concat([base, pd.read_csv(extra, sep="\t")], ignore_index=True)
bad = []
for t in ("T1", "A", "B"):
    a = pd.to_numeric(base[base.tier == t].idi_avg, errors="coerce").dropna().to_numpy()
    b = pd.to_numeric(new[new.tier == t].idi_avg, errors="coerce").dropna().to_numpy()
    if len(a) < 2 or len(b) < 2:
        bad.append(f"{t}: missing reps"); continue
    rng = np.random.default_rng(20260607)
    d = (rng.choice(b, (10000, len(b))).mean(1) - rng.choice(a, (10000, len(a))).mean(1))
    lo, hi = np.percentile(d, [2.5, 97.5])
    ok = lo <= 0 <= hi
    print(f"  {t}: baseline {a.mean():8.1f} | rel8 {b.mean():8.1f} | "
          f"diff {b.mean()-a.mean():+7.1f} [{lo:+.1f}, {hi:+.1f}] {'ok' if ok else 'MISMATCH'}")
    if not ok:
        bad.append(t)
sys.exit(1 if bad else 0)
PY
if [ $? -ne 0 ]; then
  echo "!! gate failed — rel8 defaults do not reproduce the banked arm. Stopping."
  echo "   Inspect $OUT/gate-default.tsv before running the remaining arms."
  exit 1
fi
echo "=== gate passed ==="

# E2 — regime ablation. B only: the regime term is null for T1/A anyway, so
# those tiers would just re-run the gate. `on` is the gate's own B column.
echo "=== E2 — regime ablation ==="
arm e2-regime-off "B" 12 -Diada.regime=off

# E5 — Meyer/Ludwig Table 2 against the hotter values this fork shipped.
echo "=== E5 — degradation table ==="
arm e5-degtable-paper "T1 A B" 12 -Diada.degTable=paper

# E4 — regime ramp shape. The W5 calibration data puts 29 of 30 observations
# at |Cliff's d| <= 0.10 or >= 0.90, leaving the low and mod bins empty, so the
# near-linear default is asserting gradation the evidence never showed. `step`
# is the shape that bimodality actually implies; `convex` matches the canonical
# classes; `measured` uses the median inflation ratio seen in the hig bin.
echo "=== E4 — regime ramp shape ==="
arm e4-ramp-step     "B" 12 -Diada.regimeRamp=1.90,1.93,1.95
arm e4-ramp-convex   "B" 12 -Diada.regimeRamp=1.07,1.55,1.95
arm e4-ramp-measured "B" 12 -Diada.regimeRamp=1.10,1.25,1.41

# E1 — startup delay. At the committed 100 only 19 of 120 samples are
# post-startup, so placement is scored on a tail in which no cloudlet finishes.
echo "=== E1 — startup delay sweep ==="
for d in 0 10 50; do
  arm "e1-startup-$d" "T1 A B" 12 -Diada.vmStartup=$d
done

# E3 — host sweep matched on CONTENTION RATIO, not on Meyer's host counts.
# Meyer had 12 apps over 4/6/8/10/12 hosts = 3.0/2.0/1.5/1.2/1.0 apps per host,
# with 12 the degenerate 1:1 point. We have 28 traces, so the same ratios land
# on 9/14/19/23/28 and the degeneracy is at 28, not 12.
echo "=== E3 — ratio-matched host sweep ==="
for h in 9 14 19 23 28; do
  arm "e3-hosts-$h" "T1 A B" "$h"
done

echo "=== campaign complete ==="
wc -l "$OUT"/*.tsv

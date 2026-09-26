#!/usr/bin/env bash
# run-sim-arm.sh — one experiment arm = one TSV (S15 campaign).
#
# Generalizes run-tier-sim-reps.sh, which hardcodes the trace trees to
# /tmp/tree-<tier>-vm-guest and cannot express a per-arm oracle *reference*
# classifier. Both are needed for the S15 3x3 placement-tier x reference-
# classifier matrix, so this script parameterizes:
#
#   TREES_ROOT    holds tree-<tier>-vm-guest/<VARIANT>/<ENV>/source
#   RDA_ROOT      holds <tier>/{*.rda,*.R}   (INTP_R_FOLDER per tier)
#   ORACLE_REF    T1|A|B — when set, adds the three -Diada.oracle* flags and
#                 an `oracle_ref` column; when unset, the 7-column schema of
#                 the banked non-oracle TSVs is written unchanged.
#
# Schema (invariant 5 of jsa-sim-rerun-brief.md):
#   tier env rep idi_avg idi_sum migrations interference_avg
#   [+ self_idi oracle_idi oracle_ref]  when ORACLE_REF is set
#
# A failed/timed-out rep is written as a FAIL row, never silently dropped
# (invariant 7).
#
#   OUT_TSV=... TIERS="T1 A B" REPS=10 bash run-sim-arm.sh -Diada.degTable=paper
set -uo pipefail

AX="${AX:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}"
CS="${CS:?CS not set (CloudSimInterference checkout)}"
TREES_ROOT="${TREES_ROOT:?TREES_ROOT not set}"
RDA_ROOT="${RDA_ROOT:?RDA_ROOT not set}"
OUT_TSV="${OUT_TSV:?OUT_TSV not set}"
TIERS="${TIERS:-T1 A B}"
REPS="${REPS:-10}"
PM_COUNT="${PM_COUNT:-12}"
VARIANT="${VARIANT:-v3.3}"
ENVNAME="${ENVNAME:-vm-guest}"
TIMEOUT="${TIMEOUT:-900}"
ORACLE_REF="${ORACLE_REF:-}"
# JDK 8 is mandatory: JRI's Rengine.stop() calls Thread.stop(), which JDK 20+
# throws UnsupportedOperationException on (S10).
JAVA_HOME="${JAVA_HOME:-/usr/lib/jvm/java-8-openjdk-amd64}"
R_LIBS_USER="${R_LIBS_USER:-$(Rscript -e 'cat(dirname(find.package("rJava")))' 2>/dev/null)}"
WORK="${WORK:-${TMPDIR:-/tmp}/sim-arm-work}"

EXTRA="$*"

restore() {
  local RL=$CS/bin/resources/workload/interference
  [ -L "$RL" ] && rm "$RL"
  local o; o=$(ls -d "${RL}".orig-* 2>/dev/null | head -1)
  [ -n "$o" ] && mv "$o" "$RL"
  return 0
}

if [ -n "$ORACLE_REF" ]; then
  echo -e "tier\tenv\trep\tidi_avg\tidi_sum\tmigrations\tinterference_avg\tself_idi\toracle_idi\toracle_ref" > "$OUT_TSV"
else
  echo -e "tier\tenv\trep\tidi_avg\tidi_sum\tmigrations\tinterference_avg" > "$OUT_TSV"
fi

for tier in $TIERS; do
  tree="$TREES_ROOT/tree-$tier-vm-guest"
  [ -d "$tree/$VARIANT/$ENVNAME/source" ] || { echo "[skip] $tier: no tree at $tree"; continue; }

  arm_extra="$EXTRA"
  if [ -n "$ORACLE_REF" ]; then
    refR="$RDA_ROOT/$ORACLE_REF/"
    refTree="$TREES_ROOT/tree-$ORACLE_REF-vm-guest/$VARIANT/$ENVNAME/source"
    [ -d "$refTree" ] || { echo "FATAL: oracle ref tree missing: $refTree" >&2; exit 2; }
    arm_extra="$arm_extra -Diada.oracleLabels=on -Diada.oracleRFolder=$refR -Diada.oracleTreeDir=$refTree"
  fi

  for rep in $(seq 1 "$REPS"); do
    VARIANT="$VARIANT" ENV="$ENVNAME" WORKLOAD_MIX="rep$rep" TIMEOUT="$TIMEOUT" \
      PM_COUNT="$PM_COUNT" IADA_HOSTS="$PM_COUNT" IADA_VMS="$PM_COUNT" \
      IADA_TREE_ROOT="$tree" CLOUDSIM_REPO="$CS" \
      OUT_DIR="$WORK/$(basename "$OUT_TSV" .tsv)/$tier" \
      JAVA_HOME="$JAVA_HOME" R_LIBS_USER="$R_LIBS_USER" \
      INTP_R_FOLDER="$RDA_ROOT/$tier/" \
      IADA_JAVA_EXTRA="$arm_extra" \
      bash "$AX/bench/iada/scripts/run-iada-experiment.sh" >/dev/null 2>&1
    restore
    m="$WORK/$(basename "$OUT_TSV" .tsv)/$tier/$VARIANT/$ENVNAME/rep$rep/metrics.tsv"
    if [ -s "$m" ]; then
      if [ -n "$ORACLE_REF" ]; then
        tail -1 "$m" | awk -v t="$tier" -v r="$rep" -v o="$ORACLE_REF" \
          'BEGIN{FS=OFS="\t"}{print t,"vm",r,$13,$14,$11,$8,$16,$17,o}' >> "$OUT_TSV"
      else
        tail -1 "$m" | awk -v t="$tier" -v r="$rep" \
          'BEGIN{FS=OFS="\t"}{print t,"vm",r,$13,$14,$11,$8}' >> "$OUT_TSV"
      fi
    else
      echo -e "$tier\tvm\t$rep\tFAIL" >> "$OUT_TSV"
    fi
    echo "  $tier rep$rep -> idi_avg=$(tail -1 "$m" 2>/dev/null | cut -f13)"
  done
done
echo "[wrote $OUT_TSV]"

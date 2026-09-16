#!/usr/bin/env bash
# run-tier-sim-reps.sh — N reps of the CloudSim IADA scheduler per classifier
# tier in the VM condition (the SA scheduler is stochastic, so average over reps).
# Reuses the pre-built source trees /tmp/tree-<tier>-vm-guest and the per-tier
# .rda+R dir results/iada-tier-rda/<tier>. Appends rows to tier-sim-reps.tsv.
#
#   TIERS="T1 A" REPS=5 bash bench/iada/scripts/run-tier-sim-reps.sh
set -uo pipefail
# Repo and CloudSim locations are per-operator; override via env.
AX="${AX:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}"
CS="${CS:-$HOME/Desktop/intpinto/CloudSimInterference}"
OUT=$AX/results/iada-sim; TSV=$OUT/tier-sim-reps.tsv
TIERS="${TIERS:-T1 A B}"; REPS="${REPS:-10}"
# Host-count arrangement for this sweep leg (IADA Table 3: 6/12/24/48).
PM_COUNT="${PM_COUNT:-48}"
# Root holding <tier>/{.rda,kmeans.R,...} -- was hardcoded to $AX/results/
# iada-tier-rda (a path that only resolves through a machine-specific Windows
# mount on some checkouts); overridable so a sandbox can point it at wherever
# its tier .rda/R sources actually live.
IADA_TIER_RDA_ROOT="${IADA_TIER_RDA_ROOT:-$AX/results/iada-tier-rda}"
JAVA_HOME="${JAVA_HOME:-/usr/lib/jvm/java-17-openjdk-amd64}"
# Keep legs from different host counts in separate output files.
TSV="${TSV_OVERRIDE:-$TSV}"
source ~/.iada-env 2>/dev/null
mkdir -p "$OUT"
restore(){ local RL=$CS/bin/resources/workload/interference; [ -L "$RL" ]&&rm "$RL"; local o; o=$(ls -d ${RL}.orig-* 2>/dev/null|head -1); [ -n "$o" ]&&mv "$o" "$RL"; }
echo -e "tier\tenv\trep\tidi_avg\tidi_sum\tmigrations\tinterference_avg\tself_idi\toracle_idi" > "$TSV"
for tier in $TIERS; do
  tree=/tmp/tree-$tier-vm-guest
  [ -e "$tree/v3.3/vm-guest/source" ] || { echo "[skip] $tier: no tree at $tree"; continue; }
  for rep in $(seq 1 "$REPS"); do
    VARIANT=v3.3 ENV=vm-guest WORKLOAD_MIX="rep$rep" TIMEOUT=200 PM_COUNT="$PM_COUNT" \
      IADA_TREE_ROOT="$tree" CLOUDSIM_REPO="$CS" OUT_DIR="$OUT/reps/$tier" \
      JAVA_HOME="$JAVA_HOME" \
      R_HOME="$(R RHOME)" R_LIBS_USER="${R_LIBS_USER:-$(Rscript -e 'cat(dirname(find.package("rJava")))' 2>/dev/null)}" \
      INTP_R_FOLDER="$IADA_TIER_RDA_ROOT/$tier/" \
      bash "$AX/bench/iada/scripts/run-iada-experiment.sh" >/dev/null 2>&1
    restore
    m="$OUT/reps/$tier/v3.3/vm-guest/rep$rep/metrics.tsv"
    if [ -s "$m" ]; then
      tail -1 "$m" | awk -v t=$tier -v r=$rep 'BEGIN{FS=OFS="\t"}{print t,"vm",r,$13,$14,$11,$8,$16,$17}' >> "$TSV"
    else echo -e "$tier\tvm\t$rep\tFAIL" >> "$TSV"; fi
    echo "  $tier rep$rep -> idi_avg=$(tail -1 "$m" 2>/dev/null | cut -f13)"
  done
done
echo "[wrote $TSV]"

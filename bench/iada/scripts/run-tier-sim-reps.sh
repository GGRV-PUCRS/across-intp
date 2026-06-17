#!/usr/bin/env bash
# run-tier-sim-reps.sh — N reps of the CloudSim IADA scheduler per classifier
# tier in the VM condition (the SA scheduler is stochastic, so average over reps).
# Reuses the pre-built source trees /tmp/tree-<tier>-vm-guest and the per-tier
# .rda+R dir results/iada-tier-rda/<tier>. Appends rows to tier-sim-reps.tsv.
#
#   TIERS="T1 A" REPS=5 bash bench/iada/scripts/run-tier-sim-reps.sh
set -uo pipefail
AX=/home/dedealien/Desktop/across-intp
CS=/home/dedealien/Desktop/CloudSimInterference
OUT=$AX/results/iada-sim; TSV=$OUT/tier-sim-reps.tsv
TIERS="${TIERS:-T1 A}"; REPS="${REPS:-5}"
source ~/.iada-env 2>/dev/null
mkdir -p "$OUT"
restore(){ local RL=$CS/bin/resources/workload/interference; [ -L "$RL" ]&&rm "$RL"; local o; o=$(ls -d ${RL}.orig-* 2>/dev/null|head -1); [ -n "$o" ]&&mv "$o" "$RL"; }
echo -e "tier\tenv\trep\tidi_avg\tidi_sum\tmigrations\tinterference_avg" > "$TSV"
for tier in $TIERS; do
  tree=/tmp/tree-$tier-vm-guest
  [ -e "$tree/v3.3/vm-guest/source" ] || { echo "[skip] $tier: no tree at $tree"; continue; }
  for rep in $(seq 1 "$REPS"); do
    VARIANT=v3.3 ENV=vm-guest WORKLOAD_MIX="rep$rep" TIMEOUT=200 \
      IADA_TREE_ROOT="$tree" CLOUDSIM_REPO="$CS" OUT_DIR="$OUT/reps/$tier" \
      R_HOME="$(R RHOME)" R_LIBS_USER="$HOME/R/library" \
      INTP_R_FOLDER="$AX/results/iada-tier-rda/$tier/" \
      bash "$AX/bench/iada/scripts/run-iada-experiment.sh" >/dev/null 2>&1
    restore
    m="$OUT/reps/$tier/v3.3/vm-guest/rep$rep/metrics.tsv"
    if [ -s "$m" ]; then
      tail -1 "$m" | awk -v t=$tier -v r=$rep 'BEGIN{FS=OFS="\t"}{print t,"vm",r,$13,$14,$11,$8}' >> "$TSV"
    else echo -e "$tier\tvm\t$rep\tFAIL" >> "$TSV"; fi
    echo "  $tier rep$rep -> idi_avg=$(tail -1 "$m" 2>/dev/null | cut -f13)"
  done
done
echo "[wrote $TSV]"

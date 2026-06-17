#!/usr/bin/env bash
# run-tier-sims.sh — F13 closed-loop: run the CloudSim IADA scheduler per
# classifier tier × deployment condition on our 15-metric campaign, collect the
# scheduling/IDI metrics into one comparison TSV.
#
# A "tier run" = (tier .rda+R sources via INTP_R_FOLDER) × (a cloudlet source
# tree built from our portable.tsv). Classifiers are HOST-trained (results/
# iada-tier-rda/<tier>); we test them on a HOST condition (container) and a VM
# condition (vm-guest) — the latter is where the canonical RDT metrics vanish.
#
# Tiers: T1 canonical-7, A proxy-swap (membw_est in mbw slot). B (full-15+regime)
# is run separately after its Java widening. Sims are SEQUENTIAL (they share the
# CloudSim bin/resources symlink). Run from the across-intp repo root.
set -uo pipefail

AX=/home/dedealien/Desktop/across-intp
CS=/home/dedealien/Desktop/CloudSimInterference
CAMPAIGN=$AX/results/p2-15metric-xdeploy-1of3
OUT=$AX/results/iada-sim
REPMAP="rep1=inc,rep2=dec,rep3=osc,rep4=con"
TIERS="${TIERS:-T1 A}"
CONDS="${CONDS:-container vm-guest}"   # host condition, VM condition
source ~/.iada-env 2>/dev/null
mkdir -p "$OUT"
COMPARE="$OUT/tier-sim-compare.tsv"; : > "$COMPARE"

# tier -> convert column set + clamp policy
metrics_for() { [ "$1" = A ] && echo "netp,nets,blk,membw_est,llcmr,llcocc,cpu" || echo "netp,nets,blk,mbw,llcmr,llcocc,cpu"; }

restore_bundled() { local RL=$CS/bin/resources/workload/interference; [ -L "$RL" ] && rm "$RL"; local o; o=$(ls -d ${RL}.orig-* 2>/dev/null|head -1); [ -n "$o" ] && mv "$o" "$RL"; }

for tier in $TIERS; do
  RDA=$AX/results/iada-tier-rda/$tier
  [ -d "$RDA" ] || { echo "[skip] $tier: no .rda dir"; continue; }
  meyer=/tmp/meyer-$tier; man=/tmp/manifest-$tier.tsv; rm -rf "$meyer" "$man"
  echo "== convert ($tier, metrics=$(metrics_for $tier)) =="
  python3 "$AX/bench/convert-profiler-to-meyer.py" "$CAMPAIGN" \
    --capture-name portable.tsv --stage solo --no-clamp --metrics "$(metrics_for $tier)" \
    --manifest "$man" --output-root "$meyer" >/dev/null 2>&1
  for cond in $CONDS; do
    tree=/tmp/tree-$tier-$cond; rm -rf "$tree"
    python3 "$AX/bench/generate-iada-tree.py" --manifest "$man" --out-root "$tree" \
      --env "$cond" --variant v3.3 --stage solo \
      --rep-pattern-map "$REPMAP" --pattern-merge median --min-rows 30 --mode copy >/dev/null 2>&1
    # bridge path order: runner wants <variant>/<env>/source; tree has <env>/<variant>/source
    mkdir -p "$tree/v3.3"; ln -sfn "../$cond/v3.3" "$tree/v3.3/$cond"
    if [ ! -e "$tree/v3.3/$cond/source" ]; then echo "[skip] $tier/$cond: no source tree"; continue; fi
    echo "== sim $tier × $cond =="
    VARIANT=v3.3 ENV="$cond" WORKLOAD_MIX="$tier" TIMEOUT=400 \
      IADA_TREE_ROOT="$tree" CLOUDSIM_REPO="$CS" OUT_DIR="$OUT/$tier" \
      R_HOME="$(R RHOME)" R_LIBS_USER="$HOME/R/library" \
      INTP_R_FOLDER="$RDA/" \
      bash "$AX/bench/iada/scripts/run-iada-experiment.sh" >/dev/null 2>&1
    restore_bundled
    m="$OUT/$tier/v3.3/$cond/$tier/metrics.tsv"
    if [ -s "$m" ]; then
      [ -s "$COMPARE" ] || head -1 "$m" | sed 's/^variant/tier/' > "$COMPARE"
      # label condition as host/vm for readability
      tail -n +2 "$m" | awk -v c="$cond" 'BEGIN{FS=OFS="\t"} {$2=(c=="vm-guest"?"vm":"host"); print}' >> "$COMPARE"
      echo "   $tier/$cond: $(tail -1 "$COMPARE" | cut -f4,13,16,17)"
    else
      echo "   $tier/$cond: NO metrics (sim failed; see $OUT/$tier/v3.3/$cond/$tier/cloudsim.log)"
    fi
  done
done
echo; echo "=== $COMPARE ==="; column -t -s$'\t' "$COMPARE" 2>/dev/null || cat "$COMPARE"

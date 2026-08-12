#!/usr/bin/env bash
# run-meyer-validation.sh — W2.2/W2.3: Meyer's 12 published patterned traces
# through the fork's simulator (bench/iada/CONFORMANCE.md §5).
#
# Arms (REPS reps each):
#   shipped      x hosts {3,6,12}  — fork's own R/ .rda (forced/-trained)
#   rda50k       x hosts {3,6,12}  — retrained on the published 50k set
#   rda50k-paper x hosts {3}       — W2.3: -Diada.degTable=paper on the main
#                                    contention point (4 apps/host, IADA-style)
#
# 12 apps throughout; 12 hosts = the degeneracy probe (Eq. 2 zero rule /
# occupancy invariance N8: paper lineage predicts score->0 at 1 app/host).
# Horizon/simLimit 280 = shortest trace (bench4q/dec, 281 rows) - 1.
# vmStartup=0 per plan (horizon varies vs the banked campaign).
#
#   REPS=10 bash bench/iada/scripts/run-meyer-validation.sh
set -uo pipefail
AX="${AX:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}"
CS="${CS:-$HOME/Desktop/intpismo/CloudSimInterference}"
MV="${MV:-$HOME/Desktop/intpismo/IADA-second-born/meyer-validation}"
TREE="${TREE:-/tmp/tree-meyer}"
REPS="${REPS:-10}"
HORIZON=280
TSV=$MV/meyer-sim-reps.tsv
source ~/.iada-env 2>/dev/null
mkdir -p "$MV/sim"

[ -e "$TREE/meyer/paper/source" ] || python3 "$AX/bench/iada/scripts/meyer-traces-to-tree.py" \
    --classifier-repo "$HOME/Desktop/intpismo/interference-classifier" --out "$TREE"

restore(){ local RL=$CS/bin/resources/workload/interference; [ -L "$RL" ]&&rm "$RL"; local o; o=$(ls -d ${RL}.orig-* 2>/dev/null|head -1); [ -n "$o" ]&&mv "$o" "$RL"; }

echo -e "arm\thosts\trep\tidi_avg\tidi_sum\tmigrations\tinterference_avg" > "$TSV"

run_leg() {  # arm rfolder hosts extra
  local arm=$1 rfolder=$2 hosts=$3 extra=$4
  for rep in $(seq 1 "$REPS"); do
    VARIANT=meyer ENV=paper WORKLOAD_MIX="h${hosts}-rep$rep" TIMEOUT=600 \
      PM_COUNT="$hosts" IADA_HOSTS="$hosts" IADA_VMS="$hosts" \
      IADA_JAVA_EXTRA="-Diada.vmStartup=0 -Diada.horizon=$HORIZON -Diada.simLimit=$HORIZON $extra" \
      IADA_TREE_ROOT="$TREE" CLOUDSIM_REPO="$CS" OUT_DIR="$MV/sim/$arm" \
      R_HOME="$(R RHOME)" R_LIBS_USER="${R_LIBS_USER:-$(Rscript -e 'cat(dirname(find.package("rJava")))' 2>/dev/null)}" \
      INTP_R_FOLDER="$rfolder" \
      bash "$AX/bench/iada/scripts/run-iada-experiment.sh" >/dev/null 2>&1
    restore
    local m="$MV/sim/$arm/meyer/paper/h${hosts}-rep$rep/metrics.tsv"
    if [ -s "$m" ] && [ "$(wc -l < "$m")" -gt 1 ]; then
      tail -1 "$m" | awk -v a=$arm -v h=$hosts -v r=$rep 'BEGIN{FS=OFS="\t"}{print a,h,r,$13,$14,$11,$8}' >> "$TSV"
    else echo -e "$arm\t$hosts\t$rep\tFAIL" >> "$TSV"; fi
    echo "  $arm h$hosts rep$rep -> idi_avg=$(tail -1 "$m" 2>/dev/null | cut -f13)"
  done
}

for h in 3 6 12; do run_leg shipped "$CS/R/"       "$h" ""; done
for h in 3 6 12; do run_leg rda50k  "$MV/rda-50k/" "$h" ""; done
run_leg rda50k-paper "$MV/rda-50k/" 3 "-Diada.degTable=paper"

echo "[wrote $TSV]"

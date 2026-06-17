#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# run-iada-experiment.sh
#
# Runs the IADA/CloudSim scheduler simulation for a single (variant, env)
# combination, using Meyer-format profiles as input.
#
# Inputs (env vars):
#   VARIANT          v0|v0.1|v0.2|v1|v1.1|v2|v3|v3.1|v3.2   (which IntP variant produced the profiles)
#   ENV              bare|container|container-guest|vm|vm-guest|...
#                    (environment where profiles were collected)
#   IADA_TREE_ROOT   path to iada-tree dir produced by generate-iada-tree.py
#   CLOUDSIM_REPO    path to CloudSimInterference checkout
#   OUT_DIR          where to put logs + parsed metrics
#   WORKLOAD_MIX     name of the workload mix (e.g. "all", "cpu_only")
#                    -- selects which subset of cloudlets to use
#
# Optional:
#   JAVA_HOME        defaults to OpenJDK 17
#   R_LIBS_USER      defaults to ~/R/library
#   TIMEOUT          simulation wallclock cap in seconds (default 7200)
#
# Output:
#   $OUT_DIR/<variant>/<env>/<workload_mix>/
#     ├── cloudsim.log         full stdout/stderr
#     ├── cloudsim.exit        exit code
#     ├── cloudsim.elapsed     wallclock seconds
#     ├── input.txt            the input.txt fed to CloudSim (for reproducibility)
#     └── metrics.tsv          parsed scheduling metrics (created by parse step)
# -----------------------------------------------------------------------------

set -euo pipefail

: "${VARIANT:?VARIANT not set (v0|v0.1|v0.2|v1|v1.1|v2|v3|v3.1|v3.2)}"
: "${ENV:?ENV not set (bare|container|container-guest|vm|vm-guest|...)}"
: "${IADA_TREE_ROOT:?IADA_TREE_ROOT not set}"
: "${CLOUDSIM_REPO:?CLOUDSIM_REPO not set}"
: "${OUT_DIR:?OUT_DIR not set}"
: "${WORKLOAD_MIX:=all}"
: "${JAVA_HOME:=/usr/lib/jvm/java-17-openjdk-amd64}"
: "${R_LIBS_USER:=$HOME/R/library}"
: "${TIMEOUT:=7200}"

JRI_DIR="$R_LIBS_USER/rJava/jri"
[ -f "$JRI_DIR/libjri.so" ] || { echo "FATAL: libjri.so not at $JRI_DIR" >&2; exit 2; }

VARIANT_TREE="$IADA_TREE_ROOT/$VARIANT/$ENV/source"
[ -d "$VARIANT_TREE" ] || { echo "FATAL: missing $VARIANT_TREE" >&2; exit 2; }

RUN_DIR="$OUT_DIR/$VARIANT/$ENV/$WORKLOAD_MIX"
mkdir -p "$RUN_DIR"

# 1) Build input.txt (declarative app list pointing at our Meyer CSVs)
#    For now: include all *.csv from source/ and use 48 PMs (paper config).
#    Future: extend with WORKLOAD_MIX filtering.
python3 "$(dirname "$0")/generate-iada-input.py" \
    --tree "$VARIANT_TREE" \
    --pm-count 48 --pm-cpu 100 \
    --output "$RUN_DIR/input.txt"

# 2) Symlink CloudSim's expected resource path to our variant's tree
#    (CloudSim hardcodes resources/workload/interference/<wkl>/ in classpath)
RESOURCE_LINK="$CLOUDSIM_REPO/bin/resources/workload/interference"
mkdir -p "$(dirname "$RESOURCE_LINK")"
if [ -L "$RESOURCE_LINK" ]; then
    rm "$RESOURCE_LINK"
elif [ -e "$RESOURCE_LINK" ]; then
    # Refuse to rm -rf a real directory -- would destroy original workload data.
    # Move it aside so the symlink can be created; it can be restored after the run.
    mv "$RESOURCE_LINK" "${RESOURCE_LINK}.orig-$$"
    echo "WARN: moved real directory $RESOURCE_LINK to ${RESOURCE_LINK}.orig-$$" >&2
fi
ln -sfn "$VARIANT_TREE" "$RESOURCE_LINK"

# 3) Run CloudSim with R signal handlers disabled (critical fix: avoids JRI segfault)
export R_HOME="${R_HOME:-$(R RHOME)}"
export LD_LIBRARY_PATH="$JRI_DIR:$R_HOME/lib:${LD_LIBRARY_PATH:-}"
export R_LIBS_USER
# honor a pre-set INTP_R_FOLDER (per-tier .rda + R sources); default to the fork
export INTP_R_FOLDER="${INTP_R_FOLDER:-$CLOUDSIM_REPO/R/}"
export INTP_R_LIBPATHS="$R_LIBS_USER"

CP="$CLOUDSIM_REPO/bin"
CP="$CP:$JRI_DIR/JRI.jar:$JRI_DIR/JRIEngine.jar:$JRI_DIR/REngine.jar"
CP="$CP:$CLOUDSIM_REPO/lib/commons-math3-3.3.jar:$CLOUDSIM_REPO/lib/opencsv-3.7.jar"

START=$(date +%s)
set +e
timeout "$TIMEOUT" "$JAVA_HOME/bin/java" \
    -Xmx6g -Xss8m -XX:+UseSerialGC \
    -DR_SignalHandlers=0 \
    -Djava.library.path="$JRI_DIR" \
    -cp "$CP" \
    cloudsim.interference.aaa.xxIntExample \
    > "$RUN_DIR/cloudsim.log" 2>&1
EXIT=$?
set -e
END=$(date +%s)
ELAPSED=$((END - START))

echo "$EXIT" > "$RUN_DIR/cloudsim.exit"
echo "$ELAPSED" > "$RUN_DIR/cloudsim.elapsed"

echo "[$VARIANT/$ENV/$WORKLOAD_MIX] exit=$EXIT, elapsed=${ELAPSED}s"

# 4) Parse output -> metrics.tsv
python3 "$(dirname "$0")/parse-cloudsim-output.py" \
    --log "$RUN_DIR/cloudsim.log" \
    --variant "$VARIANT" --env "$ENV" --workload-mix "$WORKLOAD_MIX" \
    --output "$RUN_DIR/metrics.tsv"

[ "$EXIT" -ne 0 ] && [ "$EXIT" -ne 124 ] && exit "$EXIT"
exit 0

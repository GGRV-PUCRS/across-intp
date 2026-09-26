#!/usr/bin/env bash
#
# run-cadence-sweep.sh -- sampling-cadence sweep for the IntP bench campaign.
#
# Runs run-intp-bench.sh once per sampling interval, each into its own
# cadence-tagged output subdir, so downstream analysis can plot metric
# FIDELITY and profiler OVERHEAD against sampling frequency. This is the
# Paper-2 headline experiment and the direct answer to the examining
# chair's "verify sampling frequency and overhead, not only whether the
# metrics are equal" review point.
#
# Design: a thin, non-invasive wrapper. It does NOT modify run-intp-bench.sh's
# stage/variant/output machinery -- it just sets --interval and --output-dir
# per cadence and forwards every other flag through unchanged. Each cadence
# subdir is therefore a normal, self-contained campaign dir that the existing
# analyzers (analyze-cross-deployment.py / analyze-portable.py) run on as-is;
# a per-sweep manifest ties the cadences together for the cadence-vs-* curves.
#
# Usage:
#   bench/run-cadence-sweep.sh [--intervals "0.1,0.25,0.5,1,2,5"] \
#                              [--sweep-dir DIR] \
#                              -- <args forwarded to run-intp-bench.sh>
#
# Everything after the sweep-specific flags is forwarded verbatim, e.g.:
#   bench/run-cadence-sweep.sh --intervals "0.1,0.5,1,2" -- \
#       --env bare --variants v2.1,v3.3 --stages solo \
#       --portable-metrics --workloads app01_ml_llc,app05_streaming \
#       --reps 12 --duration 120
#
# Notes:
#   * --interval and --output-dir are OWNED by this driver; passing them in the
#     forwarded args is rejected (they would collide with the per-cadence values).
#   * The build stage (if selected) re-runs per cadence; for a pure cadence
#     sweep prefer --stages solo (and build once beforehand) to avoid rebuilds.
#   * Honors --dry-run (forwarded) for a no-op validation of the full plan.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BENCH="$SCRIPT_DIR/run-intp-bench.sh"

INTERVALS="0.1,0.25,0.5,1,2,5"
SWEEP_DIR=""
PASSTHROUGH=()

usage() { sed -n '2,40p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }

while [ $# -gt 0 ]; do
    case "$1" in
        --intervals)  INTERVALS="$2"; shift 2 ;;
        --sweep-dir)  SWEEP_DIR="$2"; shift 2 ;;
        -h|--help)    usage; exit 0 ;;
        --)           shift; while [ $# -gt 0 ]; do PASSTHROUGH+=("$1"); shift; done ;;
        --interval|--output-dir)
            echo "error: $1 is owned by the cadence-sweep driver; use --intervals / --sweep-dir" >&2
            exit 2 ;;
        *)            PASSTHROUGH+=("$1"); shift ;;
    esac
done

[ -x "$BENCH" ] || { echo "error: $BENCH not found/executable" >&2; exit 1; }

# Reject a forwarded --interval/--output-dir that slipped past the '--' split.
for a in ${PASSTHROUGH[@]+"${PASSTHROUGH[@]}"}; do
    case "$a" in
        --interval|--output-dir)
            echo "error: $a must not appear in forwarded args (driver owns it)" >&2
            exit 2 ;;
    esac
done

if [ -z "$SWEEP_DIR" ]; then
    SWEEP_DIR="$REPO_ROOT/results/cadence-sweep-$(date +%Y%m%d_%H%M%S)"
fi
mkdir -p "$SWEEP_DIR"

# Zero-padded ms tag so cadence subdirs sort numerically (0100ms < 0250ms < 1000ms).
tag_for() { awk -v s="$1" 'BEGIN{ printf "%04dms", (s*1000)+0.5 }'; }

manifest="$SWEEP_DIR/sweep-manifest.tsv"
printf 'interval_s\tcadence_tag\toutput_dir\n' > "$manifest"

IFS=',' read -r -a IVS <<< "$INTERVALS"
echo "[cadence-sweep] sweep_dir=$SWEEP_DIR  intervals=${INTERVALS}  cadences=${#IVS[@]}"
echo "[cadence-sweep] forwarding to run-intp-bench.sh: ${PASSTHROUGH[*]:-<none>}"

n=0
FAILED=()
for iv in "${IVS[@]}"; do
    iv="$(echo "$iv" | tr -d ' ')"
    [ -n "$iv" ] || continue
    tag="$(tag_for "$iv")"
    outdir="$SWEEP_DIR/cadence-$tag"
    n=$((n+1))
    echo "[cadence-sweep] ($n/${#IVS[@]}) interval=${iv}s -> $outdir"
    printf '%s\t%s\t%s\n' "$iv" "$tag" "$outdir" >> "$manifest"
    # if-guarded so one failed cadence does not abort the whole sweep (set -e safe).
    if "$BENCH" --interval "$iv" --output-dir "$outdir" \
            ${PASSTHROUGH[@]+"${PASSTHROUGH[@]}"}; then
        :
    else
        echo "[cadence-sweep] WARN: cadence ${iv}s failed (rc=$?); continuing" >&2
        FAILED+=("${iv}s")
    fi
done

echo "[cadence-sweep] DONE ($n cadences) -> $SWEEP_DIR"
echo "[cadence-sweep] manifest: $manifest"
if [ ${#FAILED[@]} -gt 0 ]; then
    echo "[cadence-sweep] FAILED cadences: ${FAILED[*]}" >&2
fi
echo "[cadence-sweep] next: analyze each cadence-*/ dir, then build the cadence-vs-fidelity / cadence-vs-overhead curves from the manifest."

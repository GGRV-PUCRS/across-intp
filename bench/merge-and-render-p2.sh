#!/usr/bin/env bash
#
# merge-and-render-p2.sh -- fold a targeted v2.1 re-run into the P2 cross-deployment
# campaign and re-render the report + figure set from the merged result (C34).
#
# The targeted re-run (docs/DECISIONS-container.md C34) replaced ONLY the v2.1
# host-env solo cells (the D12 mbw scope fix); v3.3 (all envs) and vm-guest/v2.1
# were never touched. Rather than trust the live box's in-place dir wholesale, we
# rebuild a MERGED tree from the validated PREVIOUS run as the base and overlay
# only the re-run cells -- so everything outside the re-run scope is byte-identical
# to the banked, validated data, and an integrity diff flags any drift.
#
# Three folders (per the merge contract):
#   <CAMP>-prerun-banked  the PREVIOUS run, archived untouched (base of truth)
#   <CAMP>-rerun          the FRESH pull from the testbed (the newly made cells)
#   <CAMP>                the MERGED canonical tree (base + overlaid re-run cells);
#                         reports + figures render from here.
#
# Idempotent: safe to re-run (archive made once via copy; merged tree rebuilt each
# time and swapped in atomically). The testbed host is NEVER hard-coded -- pass it
# via INTP_TESTBED=root@<host> (consumed by pull-results.sh). Pull ONLY when the
# box is idle (between campaigns); this script refuses if a campaign is in flight.
set -euo pipefail

CAMP="${1:-p2-15metric-xdeploy-1of3}"
HOST_ENVS=(bare container container-podman container-lxc container-k8s)
TITLE_SUFFIX=" (1/3 footprint + hard CPU pinning; supersedes the 2/3 run)"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT"   # so analyzers/figures receive a relative campaign dir (clean report titles)
CAMP_REL="results/$CAMP"
RES="$ROOT/results"
PREV="$RES/$CAMP"                       # current local = previous run, becomes MERGED
ARCHIVE="$RES/${CAMP}-prerun-banked"    # preserved previous run (base of truth)
RERUN="$RES/${CAMP}-rerun"              # fresh testbed pull (newly made cells)
XDEP_REPORT="$ROOT/docs/reports/p2-cross-deployment-15metric.md"
PORT_REPORT="$ROOT/docs/reports/p2-portable-15metric.md"

say()  { echo "[merge-p2] $*"; }
fail() { echo "[merge-p2] ERROR: $*" >&2; exit 1; }

[ -n "${INTP_TESTBED:-}" ] || fail "set INTP_TESTBED=root@<host> (host is not stored in the repo)"
KEY="${INTP_TESTBED_KEY:-$HOME/.ssh/id_ed25519}"

# --- 0. idle guard: never pull a live campaign --------------------------------
say "checking the testbed is idle before pulling..."
# bracket trick so the guard command does not self-match over ssh (-f matches
# full cmdlines, and the pgrep invocation itself carries the pattern string).
busy="$(ssh -i "$KEY" -o ConnectTimeout=20 -o BatchMode=yes "$INTP_TESTBED" \
        'pgrep -fc "run-intp-[b]ench|[s]tress-ng|[q]emu-system" || true' 2>/dev/null || echo "?")"
case "$busy" in
    0) say "host idle (0 campaign procs)";;
    "?") fail "could not reach testbed to confirm idle (refusing to pull blind)";;
    *) fail "testbed BUSY ($busy campaign procs) -- refusing to pull mid-run";;
esac

# --- 1. archive the previous run (once) ---------------------------------------
[ -d "$PREV" ] || fail "no local previous campaign at $PREV"
if [ ! -d "$ARCHIVE" ]; then
    say "archiving previous run -> $(basename "$ARCHIVE") (base of truth)"
    cp -a "$PREV" "$ARCHIVE"
else
    say "archive already present ($(basename "$ARCHIVE")); using it as base"
fi
prev_tsv=$(find "$ARCHIVE" -name '*.tsv' | wc -l)
say "base TSVs: $prev_tsv"

# --- 2. pull the fresh re-run snapshot ----------------------------------------
say "pulling fresh snapshot of $CAMP from \$INTP_TESTBED ..."
bash "$ROOT/bench/pull-results.sh" "$CAMP"
SNAP="$RES/_snapshots/latest.tar.gz"
[ -f "$SNAP" ] || fail "expected snapshot symlink $SNAP after pull"
rm -rf "$RERUN"; mkdir -p "$RERUN"
tar xzf "$SNAP" -C "$RERUN" --strip-components=1
rerun_v21_tsv=$(find "$RERUN" -path '*/v2.1/*' -name '*.tsv' | wc -l)
say "fresh pull extracted -> $(basename "$RERUN") (v2.1 TSVs: $rerun_v21_tsv)"

# --- 3. build the merged canonical tree (base + overlaid re-run cells) ---------
say "building merged tree: base + ${#HOST_ENVS[@]} host-env v2.1 subtrees from re-run"
TMP="$RES/.${CAMP}.merge.tmp"
rm -rf "$TMP"; cp -a "$ARCHIVE" "$TMP"
for env in "${HOST_ENVS[@]}"; do
    [ -d "$RERUN/$env/v2.1" ] || fail "re-run is missing $env/v2.1 (incomplete pull?)"
    rm -rf "$TMP/$env/v2.1"
    cp -a "$RERUN/$env/v2.1" "$TMP/$env/v2.1"
done
# refresh top-level provenance from the fresh pull (correct mbw ceiling etc.);
# the per-cell analyzer outputs are regenerated below.
for f in capabilities.env variants.manifest metadata.txt; do
    [ -f "$RERUN/$f" ] && cp -a "$RERUN/$f" "$TMP/$f"
done
rm -f "$TMP/cross-deployment.tsv" "$TMP/index.tsv"
# swap in atomically
rm -rf "$PREV"; mv "$TMP" "$PREV"
merged_tsv=$(find "$PREV" -name '*.tsv' | wc -l)
say "merged canonical tree rebuilt at $(basename "$PREV") (TSVs: $merged_tsv)"

# --- 4. integrity guardrail: outside the re-run scope, merged == fresh pull ----
# Only the 5 host-env v2.1 subtrees and regenerated top-level files may differ;
# anything else (v3.3 everywhere, vm-guest/v2.1) drifting means the box mutated
# data it should not have, or the pull is incomplete -> surface it loudly.
say "integrity diff (merged vs fresh pull, outside re-run scope)..."
diff -rq "$PREV" "$RERUN" > "$RES/.merge-diff.txt" 2>&1 || true
unexpected="$(grep -E 'differ|Only in' "$RES/.merge-diff.txt" \
    | grep -vE "/(bare|container|container-podman|container-lxc|container-k8s)/v2.1(/|$)" \
    | grep -vE '(cross-deployment\.tsv|index\.tsv|w5-victim-delta\.tsv|portable.*\.md)' || true)"
if [ -n "$unexpected" ]; then
    say "WARNING: unexpected differences outside the re-run scope:"
    echo "$unexpected" | sed 's/^/[merge-p2]   /'
    say "(merged tree keeps the VALIDATED banked data for these; review before trusting absolute claims)"
else
    say "integrity OK: outside the re-run scope, merged == fresh pull (no drift)"
fi

# --- 5. regenerate reports from the merged tree -------------------------------
# Analyzer emits a clean report (no C34 invalidity caveat -- v2.1 mbw is valid
# now). We re-apply the manual title suffix and a concise mbw-ceiling note.
say "regenerating reports from merged tree..."
NOTE_BLOCK='> **NOTE (mbw ceiling, C34):** v2.1 `mbw` is correctly scoped (per-cgroup
> resctrl, D12) against the audited machine ceiling (281600 MB/s, 2026-06-13
> re-run). Banked v3.3 `mbw` was computed against the pre-audit ceiling
> (42656 MB/s) and reads ~6.6x high in absolute terms (multiply by 0.151 for
> the corrected ceiling); within-variant ratios-vs-bare and rank correlations
> are ceiling-invariant and unaffected.'

regen_report() {  # $1 analyzer  $2 out-report
    local raw="$RES/.report.raw.md"
    python3 "$ROOT/bench/$1" "$CAMP_REL" --out "$raw"
    { head -1 "$raw" | sed "s|\$|$TITLE_SUFFIX|"
      printf '\n%s\n' "$NOTE_BLOCK"
      tail -n +2 "$raw"
    } > "$2"
    rm -f "$raw"
    say "  wrote $(basename "$2")"
}
regen_report analyze-cross-deployment.py "$XDEP_REPORT"
regen_report analyze-portable.py "$PORT_REPORT"

# --- 6. render the figure set from the merged tree ----------------------------
say "rendering figures from merged tree..."
python3 "$ROOT/bench/plot/plot-p2-15metric.py" "$CAMP_REL" --out "$RES/figures/$CAMP"
say "figures -> results/figures/$CAMP/"

say "DONE: merged=$(basename "$PREV") ($merged_tsv TSVs)  base=$(basename "$ARCHIVE") ($prev_tsv)  pull=$(basename "$RERUN")"

#!/usr/bin/env bash
#
# pull-results.sh -- snapshot the remote testbed's consolidated results/ into the
# local ./results/ as a timestamped tarball, for safety against loss of the
# (ephemeral cloud) testbed. Run ONLY BETWEEN campaigns, when the remote host is
# IDLE -- never mid-run: the tar's CPU/IO and reading a results/ tree that is being
# written would perturb the in-flight benchmark. Run it after a campaign finishes
# (host quiesced) and before the next one starts, so a reclaimed/dead host never
# costs us a completed campaign's data.
#
# Pull-only: streams `tar` over the ssh channel (no scp/sftp push to the remote
# required, and nothing is written on the remote). Idempotent -- each run drops a
# new timestamped archive under ./results/_snapshots/ and refreshes `latest`.
#
# The testbed host is NEVER hard-coded (it is treated as sensitive); pass it via
# the environment:
#     INTP_TESTBED=root@<host> bash bench/pull-results.sh [CAMPAIGN_SUBDIR] [--extract]
#
# Env knobs:
#   INTP_TESTBED         ssh target, e.g. root@host           (REQUIRED)
#   INTP_TESTBED_KEY     ssh identity file   (default: ~/.ssh/id_ed25519)
#   INTP_REMOTE_RESULTS  remote results dir  (default: /root/across-intp/results)
#
# Args:
#   CAMPAIGN_SUBDIR  optional: snapshot just one campaign dir (default: all of results/)
#   --extract        also unpack the tarball into ./results/ for local use (plots etc.)
set -euo pipefail

REMOTE="${INTP_TESTBED:-}"
KEY="${INTP_TESTBED_KEY:-$HOME/.ssh/id_ed25519}"
REMOTE_RESULTS="${INTP_REMOTE_RESULTS:-/root/across-intp/results}"

SUBDIR=""
EXTRACT=0
for a in "$@"; do
    case "$a" in
        --extract) EXTRACT=1 ;;
        --*)       echo "unknown flag: $a" >&2; exit 2 ;;
        *)         SUBDIR="$a" ;;
    esac
done

[ -n "$REMOTE" ] || { echo "ERROR: set INTP_TESTBED=root@<host> (host is not stored in the repo)" >&2; exit 2; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCAL_RESULTS="$(cd "$SCRIPT_DIR/.." && pwd)/results"
SNAP_DIR="$LOCAL_RESULTS/_snapshots"
mkdir -p "$SNAP_DIR"

TAG="$(date -u +%Y%m%dT%H%M%SZ)"
label="${SUBDIR:-all}"
label="${label//\//_}"
OUT="$SNAP_DIR/snap-${TAG}-${label}.tar.gz"

SSH=(ssh -i "$KEY" -o ConnectTimeout=30 -o BatchMode=yes "$REMOTE")

# Sanity: the remote results dir exists and has the requested subdir.
"${SSH[@]}" "test -d '$REMOTE_RESULTS/${SUBDIR}'" \
    || { echo "ERROR: remote '$REMOTE_RESULTS/${SUBDIR}' not found" >&2; exit 1; }

echo "[pull-results] $REMOTE:$REMOTE_RESULTS/${SUBDIR:-} -> $OUT"
# Stream a gzip'd tar of the (sub)tree over ssh stdout into the local file.
"${SSH[@]}" "tar czf - -C '$REMOTE_RESULTS' '${SUBDIR:-.}'" > "$OUT"

# Verify the archive is intact before trusting it as a backup.
if ! gzip -t "$OUT" 2>/dev/null; then
    echo "[pull-results] ERROR: archive failed gzip integrity check; removing" >&2
    rm -f "$OUT"; exit 1
fi
nfiles="$(tar tzf "$OUT" | wc -l)"
bytes="$(stat -c%s "$OUT")"
ln -sf "$(basename "$OUT")" "$SNAP_DIR/latest.tar.gz"
echo "[pull-results] OK: $((bytes/1024/1024)) MB, $nfiles entries  (latest -> $(basename "$OUT"))"

if [ "$EXTRACT" = 1 ]; then
    echo "[pull-results] extracting into $LOCAL_RESULTS/"
    tar xzf "$OUT" -C "$LOCAL_RESULTS"
    echo "[pull-results] extracted."
fi

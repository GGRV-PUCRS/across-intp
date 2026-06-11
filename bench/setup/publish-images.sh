#!/usr/bin/env bash
# publish-images.sh — build the LEAN bench-tenant images and (optionally)
# publish them as packages: the container image to GHCR, and the VM qcow2 as a
# GitHub release asset.
#
# NOTE (2026-06): the repo moved to github.com/Saccilotto/across-intp and the OLD
# ghcr.io/ggrv-intp/intp-bench package + bench-vm release asset were DELETED. The
# refs below target the new org; nothing in the harness depends on these packages
# (container/k8s use public ubuntu:24.04 + on-the-fly install; vm-guest uses the
# LOCAL qcow2), so the deletion does not affect any campaign — only re-publishing.
#
# ┌───────────────────────────────────────────────────────────────────────────┐
# │  THIS SCRIPT IS OPERATOR-INVOKED. It is NOT run by the harness or CI.        │
# │  The --publish path performs OUTWARD, AUTHENTICATED, BANDWIDTH-HEAVY actions:│
# │    * docker push  ghcr.io/saccilotto/intp-bench:24.04   (needs GHCR login)    │
# │    * gh release upload <tag> intp-bench-vm.qcow2       (needs gh auth + a    │
# │                                                          multi-GB upload)    │
# │    * oras push    ghcr.io/saccilotto/intp-bench-vm-suites:24.04 (GHCR login;  │
# │                                                          ~7 GiB upload)      │
# │  Without --publish it ONLY builds locally and PRINTS the push/upload         │
# │  commands so you can run them yourself with your own credentials.            │
# └───────────────────────────────────────────────────────────────────────────┘
#
# Usage:
#   bash bench/setup/publish-images.sh                 # build + print push recipe (default, safe)
#   bash bench/setup/publish-images.sh --publish       # build + actually push/upload (operator only)
#   bash bench/setup/publish-images.sh --vm            # also build the bench VM qcow2 (needs sudo/root)
#   bash bench/setup/publish-images.sh --vm --publish  # build both + push image + upload qcow2
#   bash bench/setup/publish-images.sh --suites --publish
#                                                      # also push the WITH_SUITES qcow2.zst as a
#                                                      # GHCR OCI artifact (oras) — NOT a release
#                                                      # asset: GitHub caps those at 2 GiB and the
#                                                      # compressed suites image is ~7 GiB
#
# Env knobs:
#   IMAGE_REF=ghcr.io/saccilotto/intp-bench:24.04   container image ref to build/push
#   VM_OUT=/var/lib/intp/intp-bench-vm.qcow2       qcow2 produced by build-bench-vm.sh
#   RELEASE_TAG=bench-images-v1                     GitHub release tag for the qcow2 asset
#   RELEASE_REPO=Saccilotto/across-intp              repo for `gh release`
#   SUITES_ZST=/var/lib/intp/staging/intp-bench-vm-suites.qcow2.zst
#                                                   compressed WITH_SUITES qcow2 (zstd of the
#                                                   build-bench-vm.sh WITH_SUITES=1 output)
#   SUITES_REF=ghcr.io/saccilotto/intp-bench-vm-suites:24.04
#                                                   GHCR artifact ref for the suites image
#
# Requires: docker (build); for --publish also docker login to GHCR and `gh`
# authenticated (`gh auth status`); for --suites --publish also `oras`
# (https://oras.land). For --vm: sudo + virt-customize toolchain
# (see build-bench-vm.sh).

set -u -o pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
IMAGE_REF="${IMAGE_REF:-ghcr.io/saccilotto/intp-bench:24.04}"
VM_OUT="${VM_OUT:-/var/lib/intp/intp-bench-vm.qcow2}"
RELEASE_TAG="${RELEASE_TAG:-bench-images-v1}"
RELEASE_REPO="${RELEASE_REPO:-Saccilotto/across-intp}"
SUITES_ZST="${SUITES_ZST:-/var/lib/intp/staging/intp-bench-vm-suites.qcow2.zst}"
SUITES_REF="${SUITES_REF:-ghcr.io/saccilotto/intp-bench-vm-suites:24.04}"

DO_PUBLISH=0
DO_VM=0
DO_SUITES=0
for arg in "$@"; do
    case "$arg" in
        --publish) DO_PUBLISH=1 ;;
        --vm)      DO_VM=1 ;;
        --suites)  DO_SUITES=1 ;;
        -h|--help) sed -n '2,40p' "$0"; exit 0 ;;
        *)         printf 'unknown arg: %s\n' "$arg" >&2; exit 2 ;;
    esac
done

log()  { printf '[publish-images] %s\n' "$*"; }
die()  { log "FATAL: $*"; exit 1; }

banner() {
    printf '\n'
    printf '================================================================\n'
    printf '  %s\n' "$*"
    printf '================================================================\n\n'
}

command -v docker >/dev/null 2>&1 || die "docker not in PATH"
docker info >/dev/null 2>&1 || die "docker daemon not running (try 'sudo systemctl start docker')"

# ── 1. build the lean container image ──────────────────────────────────────────
log "building container image: $IMAGE_REF (from Dockerfile.bench)"
docker build -f "$HERE/Dockerfile.bench" -t "$IMAGE_REF" "$HERE" \
    || die "docker build failed"
log "built: $IMAGE_REF"
log "image size: $(docker image inspect "$IMAGE_REF" --format '{{.Size}}' | numfmt --to=iec)"

# Smoke test: stress-ng + the bench deps must be present (no per-run apt needed).
log "smoke test: verifying bench deps are pre-baked"
docker run --rm "$IMAGE_REF" \
    bash -lc 'for t in stress-ng iperf3 numactl bc ip; do command -v "$t" >/dev/null || { echo "missing: $t"; exit 1; }; done; echo "bench deps OK"' \
    || die "smoke test failed — bench deps missing from $IMAGE_REF"
log "smoke OK"

# ── 2. optionally build the lean VM qcow2 ───────────────────────────────────────
if [ "$DO_VM" = "1" ]; then
    log "building bench VM qcow2 via build-bench-vm.sh (OUT=$VM_OUT)"
    OUT="$VM_OUT" bash "$HERE/build-bench-vm.sh" || die "build-bench-vm.sh failed"
fi

# ── 2b. suites artifact (WITH_SUITES qcow2.zst -> GHCR OCI artifact) ────────────
# This script does NOT build/compress the suites image (build-bench-vm.sh
# WITH_SUITES=1, then zstd) — it only publishes an existing artifact. The
# .sha256 travels in the same artifact so a testbed `oras pull` into
# /var/lib/intp/staging satisfies stage-next-campaigns.sh's integrity gate.
if [ "$DO_SUITES" = "1" ]; then
    [ -f "$SUITES_ZST" ] || die "suites artifact missing: $SUITES_ZST (WITH_SUITES=1 build-bench-vm.sh, then zstd -T0 -8 the qcow2 into place)"
    [ -f "$SUITES_ZST.sha256" ] || die "missing $SUITES_ZST.sha256 (cd $(dirname "$SUITES_ZST") && sha256sum $(basename "$SUITES_ZST") > $(basename "$SUITES_ZST").sha256)"
fi

# ── 3. publish (guarded) ────────────────────────────────────────────────────────
PUSH_CMD="docker push $IMAGE_REF"
REL_CMD="gh release upload $RELEASE_TAG $VM_OUT --repo $RELEASE_REPO --clobber"
REL_CREATE="gh release create $RELEASE_TAG --repo $RELEASE_REPO --title 'IntP bench images' --notes 'Lean bench-tenant images'"
# oras records file paths as artifact titles, so push from inside the staging
# dir (bare basenames) — a testbed pull then lands flat files, not a dir tree.
SUITES_CMD="oras push $SUITES_REF \
    --artifact-type application/vnd.intp.bench-vm-image \
    --annotation org.opencontainers.image.source=https://github.com/$RELEASE_REPO \
    $(basename "$SUITES_ZST"):application/zstd \
    $(basename "$SUITES_ZST").sha256:text/plain"

if [ "$DO_PUBLISH" != "1" ]; then
    banner "BUILD ONLY — nothing pushed. Re-run with --publish to publish."
    log "To publish the container image to GHCR (needs: docker login ghcr.io):"
    log "    $PUSH_CMD"
    if [ "$DO_VM" = "1" ]; then
        log ""
        log "To attach the VM qcow2 to a GitHub release (needs: gh auth login):"
        log "    # create the release once if it does not exist:"
        log "    $REL_CREATE"
        log "    $REL_CMD"
    fi
    if [ "$DO_SUITES" = "1" ]; then
        log ""
        log "To push the WITH_SUITES VM artifact to GHCR (needs: oras login ghcr.io):"
        log "    cd $(dirname "$SUITES_ZST") && $SUITES_CMD"
    fi
    exit 0
fi

banner "PUBLISH MODE — outward, authenticated, bandwidth-heavy actions follow."
log "This requires YOUR GitHub/GHCR credentials and uploads multi-GB assets."

# Container image -> GHCR
command -v docker >/dev/null 2>&1 || die "docker not in PATH"
log "pushing $IMAGE_REF to GHCR (expects prior 'docker login ghcr.io')"
$PUSH_CMD || die "docker push failed — did you 'docker login ghcr.io'?"
log "pushed: $IMAGE_REF"

# VM qcow2 -> GitHub release asset
if [ "$DO_VM" = "1" ]; then
    command -v gh >/dev/null 2>&1 || die "gh CLI not in PATH (needed for release upload)"
    gh auth status >/dev/null 2>&1 || die "gh not authenticated (run 'gh auth login')"
    [ -f "$VM_OUT" ] || die "qcow2 not found at $VM_OUT (build it with --vm)"
    log "ensuring release $RELEASE_TAG exists on $RELEASE_REPO"
    gh release view "$RELEASE_TAG" --repo "$RELEASE_REPO" >/dev/null 2>&1 \
        || gh release create "$RELEASE_TAG" --repo "$RELEASE_REPO" \
             --title "IntP bench images" --notes "Lean bench-tenant images" \
        || die "could not create release $RELEASE_TAG"
    log "uploading $VM_OUT to release $RELEASE_TAG (multi-GB; this is slow)"
    $REL_CMD || die "gh release upload failed"
    log "uploaded: $VM_OUT"
fi

# WITH_SUITES qcow2.zst -> GHCR OCI artifact
if [ "$DO_SUITES" = "1" ]; then
    command -v oras >/dev/null 2>&1 || die "oras not in PATH (https://oras.land; needed for the GHCR artifact push)"
    log "pushing $(basename "$SUITES_ZST") (+.sha256) to $SUITES_REF (~7 GiB; this is slow)"
    ( cd "$(dirname "$SUITES_ZST")" && $SUITES_CMD ) \
        || die "oras push failed — did you 'oras login ghcr.io'?"
    log "pushed: $SUITES_REF"
fi

banner "PUBLISH COMPLETE."
log "Point the harness at the published artifacts (opt-in; defaults unchanged):"
log "    INTP_BENCH_CONTAINER=$IMAGE_REF"
[ "$DO_VM" = "1" ] && log "    INTP_BENCH_VM_IMAGE=<path to downloaded $(basename "$VM_OUT")>"
[ "$DO_SUITES" = "1" ] && log "    testbed: oras pull $SUITES_REF -o /var/lib/intp/staging/ && bash bench/setup/stage-next-campaigns.sh"

#!/usr/bin/env bash
# render-jsa-paper-figures.sh -- one-shot reproduction of all 19 JSA paper
# figure PDFs from the consolidated data archive.
#
# Usage:
#   bench/render-jsa-paper-figures.sh [DATA_ROOT] [OUT_DIR]
#
# Defaults:
#   DATA_ROOT = /home/saccilotto/IntP-JSA-consolidated-data
#   OUT_DIR   = /home/saccilotto/paper/figs
#
# The archive is treated as read-only: renderers whose inputs must sit inside
# the campaign directory (tagged TSVs, aggregate-means.tsv) run against
# symlink farms under /tmp (cp -rs makes real dirs over symlinked files, so
# derived files land in the farm, not the archive). All other scratch output
# goes to a staging dir and only the 19 final PDFs are copied into OUT_DIR.
#
# Reference-only validation: regenerated derived TSVs are diffed against the
# old-name reference tree under ~/results (never used as pipeline input).

set -euo pipefail

DATA="${1:-/home/saccilotto/IntP-JSA-consolidated-data}"
OUT="${2:-/home/saccilotto/paper/figs}"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REF="${JSAREF:-$HOME/results}"           # validation reference only
WORK=/tmp/jsa-fig-render                 # staging
FARM1=/tmp/jsa-camp-01                   # 01-tier-a-cross-deployment
FARM2=/tmp/jsa-camp-02                   # 02-w5-colocation

cd "$REPO"
rm -rf "$WORK" "$FARM1" "$FARM2"
mkdir -p "$WORK" "$OUT"
cp -rs "$DATA/final/01-tier-a-cross-deployment" "$FARM1"
cp -rs "$DATA/final/02-w5-colocation" "$FARM2"

WARN=()
warn() { WARN+=("$1"); echo "WARN: $1" >&2; }

diff_check() { # diff_check <fresh> <reference> <label>
    if diff -q "$2" "$1" >/dev/null 2>&1; then
        echo "VALIDATION OK: $3 matches $2"
    elif [[ -z "$(diff "$1" "$2" | grep '^>')" ]]; then
        local n
        n=$(diff "$1" "$2" | grep -c '^<' || true)
        echo "VALIDATION OK: $3 covers $2 exactly (reference is a strict subset; fresh adds $n lines -- consolidated archive includes the app16/app17 workloads the old tree's TSV predates)"
    else
        warn "$3 DIFFERS from $2 (see: diff $1 $2)"
    fi
}

echo "== [1/9] derived TSVs: cross-deployment tagged (camp 01)"
python3 bench/analyze-cross-deployment.py "$FARM1" --tag-status \
    --out "$WORK/cross-deployment-report.md" >/dev/null
diff_check "$FARM1/cross-deployment-tagged.tsv" \
    "$REF/p2-15metric-xdeploy-1of3/cross-deployment-tagged.tsv" \
    "cross-deployment-tagged.tsv"

echo "== [2/9] Figures 2/3/4/8/14 (availability, psi, membwproxy, claimclass, preempt)"
mkdir -p "$WORK/figset1"
python3 bench/plot/plot-fig2-3-4-6-8-jsa.py "$FARM1" --out "$WORK/figset1" --tag-status
cp "$WORK/figset1/Figure_2.pdf"  "$WORK/fig_availability.pdf"
cp "$WORK/figset1/Figure_8.pdf"  "$WORK/fig_claimclass.pdf"
cp "$WORK/figset1/Figure_3.pdf"  "$WORK/fig_psi.pdf"
cp "$WORK/figset1/Figure_4.pdf"  "$WORK/fig_membwproxy.pdf"
cp "$WORK/figset1/Figure_14.pdf" "$WORK/fig_preempt.pdf"

echo "== [3/9] fig_arch (no data)"
python3 bench/plot/plot-fig-arch.py --out "$WORK/fig_arch.pdf"

echo "== [4/9] fig_cadence (merged three-row: pooled + per-env + sensitivity)"
# --out must be passed explicitly: its default mkdir trips over the repo's
# dangling 'results' symlink. --by-env-tsv adds the R2 per-environment
# deviation row (banked by-env TSV reproduced exactly by
# analyze-cadence.py --by-env; see s16 R2 in DECISIONS-sim-experiments.md).
python3 bench/plot/plot-cadence-curves.py \
    "$DATA/final/03-cadence-sweep/cadence-fidelity.tsv" \
    --out "$WORK/cadence-scratch" --jsa-merged "$WORK/fig_cadence.pdf" \
    --by-env-tsv "$DATA/final/03-cadence-sweep/cadence-fidelity-by-env.tsv"

echo "== [5/9] fig_overhead (F9 JSA style; all side outputs redirected)"
python3 bench/analyze-cadence-overhead.py "$DATA/final/06-cadence-overhead-F9" \
    --tsv "$WORK/overhead-vs-cadence.tsv" --out "$WORK/overhead-report.md" \
    --fig "$WORK/overhead-scratch" --jsa-style "$WORK/fig_overhead.pdf"

echo "== [6/9] fig_pipeline (no data)"
python3 bench/plot/plot-fig-pipeline.py --out "$WORK/fig_pipeline.pdf"

echo "== [7/9] fig_faithfulness (Figure_6_v2)"
mkdir -p "$WORK/fig6v2"
python3 bench/plot/plot-fig6-v2-jsa.py "$FARM1" \
    --report "$REPO/docs/reports/W4-faithfulness-r2.md" --out "$WORK/fig6v2" \
    | tee "$WORK/fig6v2.log"
cp "$WORK/fig6v2/Figure_6_v2.pdf" "$WORK/fig_faithfulness.pdf"
if [[ $(grep -o "(20, 20)" "$WORK/fig6v2.log" | wc -l) -eq 2 ]]; then
    echo "VALIDATION OK: faithfulness 20/20 cells for both variants"
else
    warn "fig_faithfulness: expected (20, 20) faith cells for both variants, see $WORK/fig6v2.log"
fi

echo "== [8/9] fig_anomaly + figA_anomaly_v33 (Figures 9/A3)"
python3 bench/plot/make-aggregate-means.py "$FARM1" --out "$FARM1/aggregate-means.tsv"
mkdir -p "$WORK/fig9"
python3 bench/plot/plot-fig9-a3-jsa.py "$FARM1" --out "$WORK/fig9"
cp "$WORK/fig9/Figure_9.pdf"  "$WORK/fig_anomaly.pdf"
cp "$WORK/fig9/Figure_A3.pdf" "$WORK/figA_anomaly_v33.pdf"

echo "== [8b/9] fig_truthscore + fig_idi_decomp (S16 sim TSVs, \\figph{S1}/\\figph{S2})"
# Sim-side figures: sources of record are the S16 rerun TSVs (see
# bench/iada/DECISIONS-sim-experiments.md S1/S2 entries). Intervals 2-5 of
# fig_idi_decomp re-parse the S3 gate campaign's cloudsim.log "Algorithm: SAO"
# blocks from JSAS3WORK (default /tmp/s3-work); when that tree is gone the
# renderer degrades to the s2-decomp.tsv endpoints and warns, so this step
# stays runnable on a fresh checkout of the TSVs alone.
SIM16="${JSASIM16:-$REPO/bench/iada/results/sim-experiments-20260917-s16}"
S3WORK="${JSAS3WORK:-/tmp/s3-work}"
python3 bench/plot/plot-fig-truthscore-jsa.py --data-root "$SIM16" --out "$WORK"
if [[ -d "$S3WORK" ]]; then
    python3 bench/plot/plot-fig-idi-decomp-jsa.py --data-root "$SIM16" \
        --out "$WORK" --s3-work-root "$S3WORK"
else
    warn "fig_idi_decomp: $S3WORK not found; rendering intervals 1 and 6 only"
    python3 bench/plot/plot-fig-idi-decomp-jsa.py --data-root "$SIM16" \
        --out "$WORK" --s3-work-root "$S3WORK"
fi

echo "== [8c/9] fig_oracle + fig_oracle_matrix (S16/S6 n=20 oracle matrix)"
# Sim-side oracle figures. S6 re-scored the S1-saved final placements (n=20 per
# configuration) under all three reference classifiers, so the three columns
# share placements (bench/iada/DECISIONS-sim-experiments.md S6 entry). The
# renderer consumes the long-schema s6-oracle-scores.tsv; without it the n=10
# batch TSVs are used instead (flag omitted -> old behaviour).
if [[ -s "$SIM16/s6-oracle-scores.tsv" ]]; then
    mkdir -p "$WORK/figoracle"
    python3 bench/plot/plot-fig-baselines-oracle-jsa.py \
        --data-root "$REPO/bench/iada/results/sim-experiments-20260916" \
        --s15-root "$REPO/bench/iada/results/sim-experiments-20260916-s15" \
        --s6-scores "$SIM16/s6-oracle-scores.tsv" \
        --out "$WORK/figoracle"
    cp "$WORK/figoracle/fig_oracle.pdf" "$WORK/fig_oracle.pdf"
    cp "$WORK/figoracle/fig_oracle_matrix.pdf" "$WORK/fig_oracle_matrix.pdf"
else
    warn "fig_oracle/fig_oracle_matrix: $SIM16/s6-oracle-scores.tsv missing; keeping previous renders"
fi

echo "== [9/9] fig_victim + fig_vmproxy (W5) and Fig-14 fingerprints"
python3 bench/analyze-cross-deployment.py "$FARM2" --w5 --tag-status \
    --out "$WORK/w5-report.md" >/dev/null
diff_check "$FARM2/w5-victim-delta-tagged.tsv" \
    "$REF/p2-15metric-xdeploy-1of3-w5/w5-victim-delta-tagged.tsv" \
    "w5-victim-delta-tagged.tsv"
mkdir -p "$WORK/fig11"
python3 bench/plot/plot-fig11-fig12-jsa.py \
    "$FARM2/w5-victim-delta-tagged.tsv" --out "$WORK/fig11"
cp "$WORK/fig11/Figure_11.pdf" "$WORK/fig_victim.pdf"
cp "$WORK/fig11/Figure_12.pdf" "$WORK/fig_vmproxy.pdf"

# Fig 14 (paper) per-variant fingerprint split -- scripted here for the first
# time: regenerate both real-app fingerprint TSVs, concatenate in the
# p2-realapps-combined order (tier-b rows then tier-c rows), render the
# combined F12 PDF, then crop per variant with the banked cropboxes.
python3 bench/analyze-tierb.py "$DATA/final/04-tier-b-realapps" --tag-status \
    --tsv "$WORK/fingerprints-tierb-tagged.tsv" --out "$WORK/tierb-report.md" >/dev/null
python3 bench/analyze-tierb.py "$DATA/final/05-tier-c-dsb" --tag-status \
    --tsv "$WORK/fingerprints-tierc-tagged.tsv" --out "$WORK/tierc-report.md" >/dev/null
cat "$WORK/fingerprints-tierb-tagged.tsv" \
    <(tail -n +2 "$WORK/fingerprints-tierc-tagged.tsv") \
    > "$WORK/fingerprints-tagged.tsv"
diff_check "$WORK/fingerprints-tagged.tsv" \
    "$REF/p2-realapps-combined/fingerprints-tagged.tsv" \
    "fingerprints-tagged.tsv"
python3 bench/plot/plot-tierb-fingerprint.py "$WORK/fingerprints-tagged.tsv" \
    --out "$WORK/f12" --dataset p2-realapps-combined
F12_PDF="$(echo "$WORK"/f12/pdf/F12-real-applications-stress-several-resource-classes--*.pdf)"
cp "$F12_PDF" "$WORK/fig_fingerprint.pdf"   # banked fig_fingerprint.pdf is
                                            # exactly this uncropped render
python3 bench/plot/crop-fig14-fingerprint.py "$F12_PDF" "$WORK"

echo "== install into $OUT"
FIGS=(
    fig_availability fig_claimclass fig_psi fig_membwproxy fig_preempt
    fig_arch fig_cadence fig_overhead fig_pipeline fig_faithfulness
    fig_anomaly figA_anomaly_v33 fig_victim fig_vmproxy
    fig_fingerprint fig_fingerprint_v21 fig_fingerprint_v33
    fig_truthscore fig_idi_decomp
    fig_oracle fig_oracle_matrix
)
fail=0
for f in "${FIGS[@]}"; do
    if [[ -s "$WORK/$f.pdf" ]]; then
        cp "$WORK/$f.pdf" "$OUT/$f.pdf"
    else
        echo "MISSING RENDER: $f.pdf" >&2; fail=1
    fi
done
[[ $fail -eq 0 ]]

echo
echo "== per-figure checklist ($OUT)"
for f in "${FIGS[@]}"; do
    if [[ -s "$OUT/$f.pdf" ]]; then
        sz=$(stat -c%s "$OUT/$f.pdf")
        if [[ $sz -gt 1000 ]]; then st="OK"; else st="SUSPICIOUSLY SMALL"; fail=1; fi
        printf "  [%-18s] %-24s %8d bytes\n" "$st" "$f.pdf" "$sz"
    else
        printf "  [%-18s] %-24s\n" "MISSING" "$f.pdf"; fail=1
    fi
done

echo
echo "== in-figure value checks"
python3 - "$OUT" <<'EOF'
import sys, pymupdf
out = sys.argv[1]
t = pymupdf.open(f"{out}/fig_membwproxy.pdf")[0].get_text()
ok = all(s in t for s in ("0.81", "413", "412"))
print(f"  fig_membwproxy rho=0.81 n=413/412: {'OK' if ok else 'MISSING -- CHECK'}")
t = pymupdf.open(f"{out}/fig_truthscore.pdf")[0].get_text()
ok = all(s in t for s in ("6966", "7365", "6495", "6947", "EVEN 8482", "EVEN 8085"))
print(f"  fig_truthscore Y5/Y6 IASA means + EVEN lines: {'OK' if ok else 'MISSING -- CHECK'}")
t = pymupdf.open(f"{out}/fig_idi_decomp.pdf")[0].get_text()
ok = all(s in t for s in ("8371", "3348", "6074", "4957", "3378", "3466"))
print(f"  fig_idi_decomp closed-form + final-interval values: {'OK' if ok else 'MISSING -- CHECK'}")
for name, want in (("fig_fingerprint_v21", "v2.1"), ("fig_fingerprint_v33", "v3.3")):
    d = pymupdf.open(f"{out}/{name}.pdf")
    p = d[0]
    # pymupdf text extraction is relative to the cropbox already; passing
    # clip=p.cropbox would double-apply the offset and match nothing.
    t = p.get_text()
    print(f"  {name} cropbox={tuple(round(v,1) for v in p.cropbox)} "
          f"contains '{want}': {'OK' if want in t else 'MISSING -- CHECK'}")
EOF

echo
if [[ ${#WARN[@]} -gt 0 ]]; then
    echo "== validation warnings"
    printf '  - %s\n' "${WARN[@]}"
else
    echo "== all derived-TSV validations passed"
fi
[[ $fail -eq 0 ]] && echo "ALL 19 FIGURES RENDERED" || { echo "FAILURES PRESENT" >&2; exit 1; }

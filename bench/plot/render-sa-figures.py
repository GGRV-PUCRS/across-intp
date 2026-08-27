#!/usr/bin/env python3
"""
render-sa-figures.py -- Regenerate the Seminario de Andamento figure set.

Mirrors ``render-paper-figures.py`` for the SA document: drives each P2
renderer in its ``--sa-style`` mode and collects the PDFs under the stems the
SA .tex already writes in its ``\\includegraphics``, so ``<out>/`` is a drop-in
replacement for the Overleaf project's ``fig/``.

    plot-w4-summary.py           w4-summary
    plot-p2-15metric.py          F3-availability-grid
    plot-w5-victim-delta.py      F10-victim-delta-forest, F11-vmguest-...
    plot-cadence-curves.py       F8-cadence-sensitivity
    analyze-cadence-overhead.py  F9-overhead-vs-cadence
    plot-iada-sim.py             F13-tier-scheduling-idi (+ the -psp arm)
    plot-hibench.py              fig10_variant_resource_heatmap
    (copied)                     schedule-plan-vs-actual

Each figure is emitted at its exact printed width (see sa_style.py), so LaTeX
includes it at scale 1.0 and the point sizes in the file are the point sizes on
paper. Every PDF gets a 300 dpi PNG sibling: the presentation refactor embeds
those instead of the stale ALL-FIG exports the current deck points at.

Usage:
    python3 bench/plot/render-sa-figures.py <results-dir> --out <dir> \\
        --hibench <hibench-campaign-dir> [--tier-b-tsv <s8-bpsp-default.tsv>] \\
        [--gantt-pdf <schedule-plan-vs-actual.pdf>]

<results-dir> is the campaign tree holding p2-15metric-xdeploy-1of3{,-w5}/,
p2-cadence-sweep/, p2-cadence-overhead/ and iada-sim/. Nothing is written
inside it: the one renderer that would (analyze-cadence-overhead.py rewrites
its analyzer TSV and report) is redirected into <out>/scratch/, so a campaign
snapshot stays immutable.

Like the paper pipeline, the run is deterministic in what it draws but not
byte-identical across environments -- constrained_layout solves the packing
from measured text extents. Diff content, not bytes: run
``qa_fig_fonts.py --style sa --compare-to`` against the current SA figures.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sa_style  # noqa: E402

HERE = Path(__file__).resolve().parent
BENCH = HERE.parent
REPO = BENCH.parent

# 300 dpi so a figure fills a projected slide without resampling artefacts.
DECK_DPI = 300


def run(cmd: list[str]) -> None:
    print("  $ " + " ".join(str(c) for c in cmd))
    proc = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
    if proc.returncode != 0:
        sys.stdout.write(proc.stdout)
        sys.stderr.write(proc.stderr)
        sys.exit(f"FAILED ({proc.returncode}): "
                 f"{' '.join(str(c) for c in cmd)}")
    for line in proc.stdout.splitlines():
        if line.startswith(("wrote ", "[", "tier B ")):
            print("    " + line)


def rasterize(pdf: Path, png: Path, dpi: int = DECK_DPI) -> bool:
    """Render ``pdf`` to ``png`` for the deck. False if PyMuPDF is missing.

    Only used for figures this pipeline copies rather than draws (the Gantt);
    every renderer writes its own PNG straight from the figure, which keeps
    the text vector-sharp instead of resampled.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return False
    doc = fitz.open(pdf)
    doc[0].get_pixmap(dpi=dpi).save(png)
    doc.close()
    return True


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("results", type=Path,
                    help="Campaign tree (p2-15metric-xdeploy-1of3{,-w5}/, "
                         "p2-cadence-sweep/, p2-cadence-overhead/, iada-sim/)")
    ap.add_argument("--out", type=Path, required=True,
                    help="Output directory for the regenerated figures")
    ap.add_argument("--hibench", type=Path, default=None,
                    help="HiBench campaign dir for fig10. Without it fig10 is "
                         "skipped and the QA gate reports it missing.")
    ap.add_argument("--w4-report", type=Path, default=None,
                    help="W4 adjudication markdown "
                         "(default: docs/reports/W4-faithfulness-r2.md)")
    ap.add_argument("--tier-b-tsv", type=Path, default=None,
                    help="S8 psp rebank reps; renders the second F13 arm "
                         "(F13-tier-scheduling-idi-psp) alongside the banked "
                         "one so the arm can be chosen before the SA freeze.")
    ap.add_argument("--gantt-pdf", type=Path, default=None,
                    help="Existing schedule-plan-vs-actual.pdf to carry into "
                         "the set. It is copied, not re-rendered: make_gantt.py "
                         "is not in this repository, and the delivered PDF "
                         "already clears the floor at 7.00 in / 6.60 pt.")
    args = ap.parse_args()

    res: Path = args.results
    if not res.is_dir():
        sys.exit(f"results tree does not exist: {res}")

    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)
    scratch = out / "scratch"
    scratch.mkdir(parents=True, exist_ok=True)

    xdeploy = res / "p2-15metric-xdeploy-1of3"
    w5 = res / "p2-15metric-xdeploy-1of3-w5" / "w5-victim-delta.tsv"
    cadence = res / "p2-cadence-sweep" / "cadence-fidelity.tsv"
    overhead = res / "p2-cadence-overhead"
    tiers = res / "iada-sim" / "tier-sim-reps.tsv"
    w4 = args.w4_report or (REPO / "docs" / "reports" / "W4-faithfulness-r2.md")

    missing = [str(p) for p in (xdeploy, w5, cadence, overhead, tiers, w4)
               if not p.exists()]
    if missing:
        sys.exit("required inputs are missing: " + ", ".join(missing))

    py = sys.executable

    print("\n=== w4-summary ===")
    run([py, HERE / "plot-w4-summary.py", w4, "--sa-style", "--out", out])

    print("\n=== F3-availability-grid ===")
    run([py, HERE / "plot-p2-15metric.py", xdeploy, "--sa-style",
         "--out", out])

    print("\n=== F10 / F11 (colocation victim delta) ===")
    run([py, HERE / "plot-w5-victim-delta.py", w5, "--sa-style", "--out", out])

    print("\n=== F8-cadence-sensitivity ===")
    run([py, HERE / "plot-cadence-curves.py", cadence, "--sa-style",
         "--out", out])

    # This one recomputes from raw captures because the banked analyzer TSV
    # predates the bootstrap CI columns, and dropping the whiskers would be a
    # content change. Its TSV and report go to scratch/ so the campaign
    # snapshot is never written to.
    print("\n=== F9-overhead-vs-cadence ===")
    run([py, BENCH / "analyze-cadence-overhead.py", overhead, "--sa-style",
         "--tsv", scratch / "overhead-vs-cadence.tsv",
         "--out", scratch / "p2-cadence-overhead.md", "--fig", out])

    print("\n=== F13-tier-scheduling-idi (banked tier B) ===")
    run([py, HERE / "plot-iada-sim.py", tiers, "--sa-style", "--out", out])

    if args.tier_b_tsv:
        print("\n=== F13-tier-scheduling-idi-psp (S8 rebank arm) ===")
        run([py, HERE / "plot-iada-sim.py", tiers, "--sa-style",
             "--stem", "F13-tier-scheduling-idi-psp",
             "--tier-b-tsv", args.tier_b_tsv, "--out", out])

    if args.hibench:
        print("\n=== fig10_variant_resource_heatmap ===")
        hb = out / "hibench"
        run([py, HERE / "plot-hibench.py", args.hibench,
             "--variants", "v0.2,v2,v3.2", "--camera-ready", "--style", "sa",
             "--formats", "pdf,png", "--out", hb])
        for fmt in ("pdf", "png"):
            src = hb / fmt / f"fig10_variant_resource_heatmap.{fmt}"
            if not src.exists():
                sys.exit(f"expected render is missing: {src}")
            shutil.copyfile(src, out / src.name)
        print(f"    collected fig10_variant_resource_heatmap.{{pdf,png}}")
    else:
        print("\n=== fig10_variant_resource_heatmap: SKIPPED "
              "(no --hibench campaign given) ===")

    if args.gantt_pdf:
        print("\n=== schedule-plan-vs-actual (copied) ===")
        dst = out / "schedule-plan-vs-actual.pdf"
        shutil.copyfile(args.gantt_pdf, dst)
        png = out / "schedule-plan-vs-actual.png"
        note = "" if rasterize(dst, png) else "  (PNG skipped: no PyMuPDF)"
        print(f"    {args.gantt_pdf} -> {dst.name}{note}")

    produced = sorted(p.name for p in out.glob("*.pdf"))
    expected = {s.out_name for s in sa_style.SA_FIGURES.values()}
    print(f"\n{len(produced)} SA figures written to {out}")
    for name in produced:
        print(f"  {name}")
    absent = sorted(expected - set(produced))
    if absent:
        print("\nnot produced this run: " + ", ".join(absent))
    print("\nNext: python3 bench/plot/qa_fig_fonts.py "
          f"{out} --style sa --compare-to <current-sa-fig-dir> --out {out}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
qa_fig_fonts.py -- Camera-ready QA gate for the SBAC-PAD 2026 paper figures.

Reviewer 3's complaint was that labels were illegible at printed size. The fix
(render each figure at its exact printed width, see paper_style.py) is only
worth anything if it is *checked*, so this script re-opens the produced PDFs
and measures what a reader will actually see:

1. every text span and its size, extracted with PyMuPDF;
2. page width against the target (+/- WIDTH_TOL in), so LaTeX includes the
   figure at scale 1.0 rather than rescaling -- and re-shrinking -- the fonts;
3. minimum span size against style.ANNOT_FLOOR;
4. height against each figure's budget (a warning, not a failure: legibility
   wins over compactness, so a figure may exceed its budget to hold the 7 pt
   floor);
5. a 300-dpi PNG contact sheet per figure under <out>/qa/ for human review.

Writes QA-FIGS.md and exits nonzero on any violation, so the pipeline fails
loudly rather than shipping a figure that regressed.

Usage:
    python3 bench/plot/qa_fig_fonts.py <figures-dir> --out <dir>

<figures-dir> is the directory of paper-named PDFs produced by
render-paper-figures.py.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fig_names  # noqa: E402  (figure naming registry)
import paper_style  # noqa: E402
import sa_style  # noqa: E402

try:
    import fitz  # PyMuPDF
except ImportError:
    sys.exit("PyMuPDF is required for the QA gate: pip install pymupdf")

# Page width must match the target this closely, in inches.
WIDTH_TOL = 0.05
# How far a text span may reach past the page box before it counts as clipped,
# in points. Measured across the camera-ready set, a healthy render's closest
# span sits +0.18 pt *inside* the page and a cropped one lands outside it
# (-0.23 pt for a y-label missing its last three characters, -2.2 pt for one
# missing a word), so the sign is the signal and this only absorbs rounding.
CLIP_TOL = 0.05
# Contact-sheet render resolution.
CONTACT_DPI = 300
PT_PER_IN = 72.0


def spans(page) -> list[tuple[float, str]]:
    """(size, text) for every non-blank text span on the page."""
    return [(size, text) for size, text, _bbox in _spans_with_bbox(page)]


def _spans_with_bbox(page) -> list[tuple[float, str, tuple]]:
    """(size, text, bbox) for every non-blank text span on the page."""
    out = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text = span["text"].strip()
                if text:
                    out.append((round(span["size"], 2), text, span["bbox"]))
    return out


def clipped(page) -> list[str]:
    """Text that runs off the page box, i.e. the figure is cropped.

    ``paper_style.save`` sizes the page from the figure's tight bounding box,
    so in a correct render every glyph sits inside the page on all four sides.
    A span that extends past it means the tight bbox did not own it and the
    PDF is missing ink -- which is what happens when a figure is made short
    enough that an axis label, being as tall as it is long, no longer fits:
    matplotlib centres the label on the axes and the ends fall outside.

    This is not hypothetical. The Addendum B height cuts produced exactly that
    on the overhead panels, and nothing else in this gate saw it: the fonts
    were the right size and the page was the right width, it was just missing
    the second half of "Δ busy jiffies (arm − baseline)". Font size and page
    width are worth nothing if the text is not on the page, so it fails here.
    """
    rect = page.rect
    bad = []
    for _size, text, bbox in _spans_with_bbox(page):
        x0, y0, x1, y1 = bbox
        outside = max(rect.x0 - x0, rect.y0 - y0, x1 - rect.x1, y1 - rect.y1)
        if outside > CLIP_TOL:
            bad.append(text)
    return bad


def _find(directory: Path, *stems: str) -> Path | None:
    """The PDF in ``directory`` for one figure, whichever campaign it names.

    Figures are written as ``<stem>--<campaign>.pdf`` (bench/plot/
    fig_names.py). The gate is handed a directory, not a campaign, so it
    matches the campaign-independent stem and accepts whatever tail follows.
    Extra ``stems`` are fallbacks, which is how ``--compare-to`` still finds a
    previous render made before this naming.
    """
    for stem in stems:
        exact = directory / f"{stem}.pdf"
        if exact.exists():
            return exact
        hits = sorted(directory.glob(f"{stem}--*.pdf"))
        if hits:
            return hits[0]
    return None


def text_counter(pdf: Path) -> Counter:
    """Multiset of the visible strings in a PDF's first page."""
    doc = fitz.open(pdf)
    c = Counter(t for _, t in spans(doc[0]))
    doc.close()
    return c


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("figures", type=Path,
                    help="Directory of paper-named PDFs")
    ap.add_argument("--out", type=Path, default=None,
                    help="Where to write QA-FIGS.md and qa/ "
                         "(default: alongside <figures>)")
    ap.add_argument("--style", choices=["paper", "sa"], default="paper",
                    help="Which figure set to gate: the SBAC-PAD camera-ready "
                         "(paper_style.PAPER_FIGURES, the default) or the "
                         "Seminario de Andamento (sa_style.SA_FIGURES). The "
                         "checks are identical -- only the spec table, the "
                         "page geometry and the budget section differ.")
    ap.add_argument("--no-contact-sheet", action="store_true",
                    help="Skip the PNG renders (faster; text checks still run)")
    ap.add_argument("--compare-to", type=Path, default=None,
                    help="Directory of the previously published figures, laid "
                         "out as <subset>/<stem>.pdf. Every visible string is "
                         "diffed against the new render so the report records "
                         "exactly what changed — the regeneration is supposed "
                         "to alter only typography and layout, so anything "
                         "beyond dropped titles, shared-axis de-duplication "
                         "and tick-locator thinning is a red flag.")
    args = ap.parse_args()

    # The gate is style-agnostic from here down: `style` supplies the spec
    # table and the floors, and both modules expose the same names. Only the
    # two report sections that are genuinely per-document -- the paper's
    # float-cost budget and the SA's column-inch accounting -- branch on it.
    sa = args.style == "sa"
    style = sa_style if sa else paper_style
    figures = sa_style.SA_FIGURES if sa else paper_style.PAPER_FIGURES

    # Figures are named <id>-<what-it-shows>--<campaign> (bench/plot/
    # fig_names.py). The gate does not know which campaign the directory was
    # rendered from, and does not need to: it matches on the campaign-
    # independent stem and reads the tail off whatever it finds.
    name_of = {k: (sa_style.out_stem(k[1]) if sa else paper_style.out_stem(k))
               for k in figures}

    global PAPER_FIGURES_NAME
    PAPER_FIGURES_NAME = dict(name_of)

    out = args.out or args.figures.parent
    qa_dir = out / "qa"
    qa_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    failures = []
    warnings = []
    deltas: list[tuple[str, list[str], list[str]]] = []

    for key, spec in sorted(figures.items(),
                            key=lambda kv: (kv[1].paper_fig, name_of[kv[0]])):
        subset, stem = key
        name = name_of[key]
        # Artifact-only figures never reach figures/, so they are measured
        # where they do land: the published/ tree the driver writes alongside.
        # The paper pipeline parks its artifact-only cuts under published/;
        # the SA writes every stem, alternative arms included, straight into
        # the drop-in directory. Under published/ the file carries no subset
        # qualifier -- the directory is the qualifier -- so it is matched on
        # the stem's own name instead.
        where = (args.figures if sa or not spec.artifact_only
                 else out / "published" / subset)
        wanted = name if sa or not spec.artifact_only else fig_names.head(stem)
        pdf = _find(where, wanted)
        if pdf is None:
            failures.append(f"{name}: missing")
            rows.append((spec, subset, stem, name, None, None, None, "MISSING",
                         "file not produced"))
            continue

        doc = fitz.open(pdf)
        page = doc[0]
        width = page.rect.width / PT_PER_IN
        height = page.rect.height / PT_PER_IN
        found = spans(page)
        notes = []

        if not found:
            failures.append(
                f"{name}: no extractable text — the PDF is not "
                f"embedding text as text (check pdf.fonttype = 42)")
            min_pt = None
            notes.append("no text spans found")
        else:
            min_pt = min(s for s, _ in found)
            if min_pt < style.ANNOT_FLOOR - 1e-6:
                worst = sorted({t for s, t in found if s == min_pt})[:3]
                failures.append(
                    f"{name}: min font {min_pt:.2f} pt < "
                    f"{style.ANNOT_FLOOR} pt floor "
                    f"(e.g. {', '.join(repr(w) for w in worst)})")
                notes.append(f"below {style.ANNOT_FLOOR} pt floor")

        cut = clipped(page)
        if cut:
            shown = sorted(set(cut))[:3]
            failures.append(
                f"{name}: text runs off the page box — the figure is "
                f"cropped (e.g. {', '.join(repr(c) for c in shown)}). The "
                f"figure is too short for its labels; shorten the label or "
                f"raise the height, never the font.")
            notes.append("clipped text")

        if abs(width - spec.width) > WIDTH_TOL:
            failures.append(
                f"{name}: width {width:.3f} in != target "
                f"{spec.width:.2f} in (tolerance {WIDTH_TOL} in)")
            notes.append("width off target")

        # Height budget is advisory: exceeding it to hold the font floor is the
        # documented trade-off, so it warns rather than fails.
        if height > spec.height_budget + 1e-6:
            over = height - spec.height_budget
            verdict = f"OVER by {over:.2f} in"
            warnings.append(
                f"{name}: height {height:.2f} in exceeds budget "
                f"{spec.height_budget:.2f} in by {over:.2f} in "
                f"(kept to preserve the {style.AXIS_FLOOR} pt floor)")
        else:
            verdict = f"OK ({height:.2f} <= {spec.height_budget:.2f} in)"

        if not args.no_contact_sheet:
            pix = page.get_pixmap(dpi=CONTACT_DPI)
            pix.save(qa_dir / f"{name}.png")

        if args.compare_to is not None:
            # The previous render may predate this naming, so match on the
            # stem's own name as well as the current one.
            prev = _find(args.compare_to if sa else args.compare_to / subset,
                         fig_names.head(stem), stem)
            if prev is not None:
                before = text_counter(prev)
                after = Counter(t for _, t in found)
                deltas.append((name,
                               sorted((before - after).elements()),
                               sorted((after - before).elements())))
            else:
                deltas.append((name, ["(no previous render found)"], []))

        rows.append((spec, subset, stem, name, width, height, min_pt, verdict,
                     "; ".join(notes) if notes else "—"))
        doc.close()

    # ---- report -----------------------------------------------------------
    lines = [
        "# QA-FIGS-SA — Seminario de Andamento figure gate" if sa
        else "# QA-FIGS — camera-ready figure gate",
        "",
        "Generated by `bench/plot/qa_fig_fonts.py`. Every row is measured from",
        "the produced PDF, not from the plotting code: page geometry comes from",
        "the page box and font sizes from the embedded text spans.",
        "",
        f"- Font floor: **{style.ANNOT_FLOOR} pt** any glyph "
        f"(heatmap cell annotations), **{style.AXIS_FLOOR} pt** for "
        f"axis/tick/legend/label text.",
        f"- Width tolerance: **±{WIDTH_TOL} in** against the printed target.",
        "- Height budget is advisory — legibility wins, so a figure may exceed",
        "  it rather than drop below the font floor.",
        "",
        "## Figure map",
        "",
        ("| Placement | File | Generator | Span |" if sa
         else "| Paper fig | File | Generator | Subset |"),
        "|---|---|---|---|",
    ]
    gen_of = ({
        "w4-summary": "`plot-w4-summary.py`",
        "F3-availability-grid": "`plot-p2-15metric.py`",
        "F10-victim-delta-forest": "`plot-w5-victim-delta.py`",
        "F11-vmguest-portable-vs-canonical": "`plot-w5-victim-delta.py`",
        "F8-cadence-sensitivity": "`plot-cadence-curves.py`",
        "F9-overhead-vs-cadence": "`analyze-cadence-overhead.py`",
        "F13-tier-scheduling-idi": "`plot-iada-sim.py`",
        "F13-tier-scheduling-idi-psp": "`plot-iada-sim.py`",
        "fig10_variant_resource_heatmap": "`plot-hibench.py`",
        "schedule-plan-vs-actual": "*(copied; `make_gantt.py` is not in "
                                   "this repository)*",
    } if sa else {
        "fig02_pca_dendro": "`plot_pca_dendro.py`",
        "fig10_variant_resource_heatmap": "`plot-hibench.py`",
    })
    for spec, subset, stem, name, *_ in rows:
        if sa:
            gen = gen_of.get(stem, "—")
            span = sa_style.SPAN.get(stem, 1)
            where = "figure*" if span == 2 else "figure"
            lines.append(f"| {spec.paper_fig} | `{name}` | {gen} "
                         f"| {where} |")
        else:
            gen = gen_of.get(stem, "`plot-intp-bench.py`")
            lines.append(f"| {spec.paper_fig} | `{name}` | {gen} "
                         f"| {subset} |")

    lines += [
        "",
        "## Measurements",
        "",
        "| File | Width (in) | Target (in) | Height (in) | Min font (pt) | "
        "Height budget | Notes |",
        "|---|---|---|---|---|---|---|",
    ]
    for spec, _subset, _stem, name, width, height, min_pt, verdict, notes in rows:
        w = f"{width:.2f}" if width is not None else "—"
        h = f"{height:.2f}" if height is not None else "—"
        m = f"{min_pt:.2f}" if min_pt is not None else "—"
        lines.append(
            f"| `{name}` | {w} | {spec.width:.2f} | {h} | {m} | "
            f"{verdict} | {notes} |")

    if deltas:
        lines += [
            "",
            "## Content delta vs the previously published figures",
            "",
            "Every visible string in each PDF, before and after. The",
            "regeneration is only allowed to change size, layout and",
            "typography, so this table is the audit for that: the expected",
            "entries are in-figure titles that were dropped because the LaTeX",
            "caption already carries them, axis tick labels thinned by",
            "matplotlib's locator at the smaller width, and y-labels that",
            "appear once per row instead of once per panel now that panels",
            "share an axis. **Nothing should appear under _added_, and no",
            "data value should appear under _removed_.**",
            "",
            "| File | Removed | Added |",
            "|---|---|---|",
        ]
        for name, removed, added in deltas:
            def fmt(items):
                if not items:
                    return "—"
                uniq = sorted(set(items))
                shown = "; ".join(f"`{u}`" + (f" ×{items.count(u)}"
                                              if items.count(u) > 1 else "")
                                  for u in uniq)
                return shown.replace("|", "\\|")
            lines.append(f"| `{name}` | {fmt(removed)} | {fmt(added)} |")

    # ---- Addendum B: float-cost budget ------------------------------------
    # Measured, not asserted: the drawing height of every float comes from the
    # page boxes above, so this table cannot claim a saving the PDFs do not
    # actually deliver.
    height_of = {(subset, stem): height
                 for spec, subset, stem, _w, height, *_ in rows}
    minpt_of = {(subset, stem): min_pt
                for spec, subset, stem, _w, _h, min_pt, *_ in rows}
    if sa:
        # ---- SA: column-inch accounting -----------------------------------
        # The SA is two-column acmart, so a `figure*` costs its drawing height
        # twice. Everything here is measured: the new heights are the page
        # boxes above, and the current ones are the compare-to PDFs scaled by
        # the `width=` factor the .tex includes them at today. Nothing is
        # asserted that the files do not actually show.
        lines += [
            "",
            "## Column-inch budget",
            "",
            "What costs page space is the float, and a `figure*` pays for its",
            "drawing twice because it spans both columns — so the unit is",
            f"column-inches, `span x drawing height`, and one page holds",
            f"**{sa_style.PAGE_COLUMN_INCHES:.1f}** of them (2 columns x",
            f"{sa_style.TEXT_HEIGHT:.2f} in).",
            "",
            "*Now* is this render. *Before* is the current SA figure, priced",
            "the way the document actually prints it: its own page height",
            "scaled by the `width=` factor in the .tex. Alternative arms are",
            "gated but placed by no float, so they cost nothing.",
            "",
            "| Figure | Span | Before (col-in) | Now (col-in) | Δ | Budget |",
            "|---|---|---|---|---|---|",
        ]
        before_total = after_total = 0.0
        unpriced = []
        for spec, subset, stem, name, _w, height, *_ in rows:
            span = sa_style.SPAN.get(stem, 1)
            after = sa_style.column_inches(stem, height) if height else 0.0
            after_total += after
            before = None
            prev = (_find(args.compare_to, fig_names.head(stem), stem)
                    if args.compare_to else None)
            if prev is not None:
                d = fitz.open(prev)
                pw = d[0].rect.width / PT_PER_IN
                ph = d[0].rect.height / PT_PER_IN
                d.close()
                scale = sa_style.printed_width(stem) / pw
                before = 0.0 if spec.artifact_only else span * ph * scale
                before_total += before
            elif not spec.artifact_only:
                unpriced.append(name)
            budget = ("—" if spec.artifact_only
                      else f"{span * spec.height_budget:.2f}")
            lines.append(
                f"| `{name}` | {span} | "
                f"{'—' if before is None else format(before, '.2f')} | "
                f"{after:.2f} | "
                f"{'—' if before is None else format(after - before, '+.2f')} "
                f"| {budget} |")
        delta = after_total - before_total
        lines += [
            f"| **total (placed)** | | **{before_total:.2f}** | "
            f"**{after_total:.2f}** | **{delta:+.2f}** | |",
            "",
            f"The placed set now costs **{after_total:.2f} column-inches**, "
            f"{delta:+.2f} against the {before_total:.2f} it costs today —",
            f"about **{abs(delta) / sa_style.PAGE_COLUMN_INCHES:.2f} of a "
            f"page**. That is the figure-side half of the page budget; the",
            "other half is caption length and float separation, which this",
            "pipeline does not change.",
            "",
            f"**The page count is not asserted here.** The gate that closes "
            f"the loop is compiling the SA and counting pages with PyMuPDF "
            f"(limit: {sa_style.PAGE_LIMIT}). If it lands at "
            f"{sa_style.PAGE_LIMIT + 1}, trim heights in this order — "
            "F10 3.4→3.1, F13 3.0→2.8, the Gantt 3.95→3.7 — never fonts.",
        ]
        if unpriced:
            lines += [
                "",
                "Not priced against a current figure (no `--compare-to` match): "
                + ", ".join(f"`{u}`" for u in unpriced) + ".",
            ]

        # ---- SA: what the .tex has to change ------------------------------
        lines += [
            "",
            "## LaTeX-side changes",
            "",
            "This pipeline does not edit `seminario-andamento.tex`. Every PDF",
            "above is emitted at its exact printed width, so a `width=` factor",
            "left at 0.92 or 0.96 would silently rescale it and re-shrink every",
            "label — which is the defect this whole pass exists to remove.",
            "",
            "| Figure | `width=` now | `width=` required |",
            "|---|---|---|",
        ]
        for _spec, _subset, stem, *_ in rows:
            ch = sa_style.LATEX_CHANGES.get(stem)
            if not ch:
                continue
            now, want, _notes = ch
            flag = "" if now == want else " **(must change)**"
            lines.append(f"| `{stem}` | `{now}` | `{want}`{flag} |")
        lines.append("")
        for _spec, _subset, stem, *_ in rows:
            ch = sa_style.LATEX_CHANGES.get(stem)
            if not ch:
                continue
            _now, _want, notes = ch
            lines.append(f"**`{stem}`**")
            lines.append("")
            lines += [f"- {n}" for n in notes]
            lines.append("")
    else:

        lines += [
            "",
            "## Float-cost budget (Addendum B)",
            "",
            "What costs page space is a float, not a PDF: its drawing, its",
            "caption and the separation around it — and a `figure*` pays all of",
            "that twice because it consumes both columns. So the unit is points",
            "of column-space, `span × (drawing + caption + separation)`, and one",
            f"page holds {paper_style.PAGE_COLUMN_SPACE:.0f} pt of it (2 columns ×",
            "684 pt). Drawing heights are the measured page heights above;",
            "caption and separation are per float, carried over from the",
            "measurements on the pre-consolidation PDF.",
            "",
            "| Float | Members | Span | Drawing (pt) | Cost before (pt) | "
            "Cost after (pt) | Saving (pt) | ≥7 pt floor |",
            "|---|---|---|---|---|---|---|---|",
        ]
        total_before = total_after = 0.0
        for fl in paper_style.FLOATS:
            heights = [height_of.get(m) for m in fl.members]
            heights = [h for h in heights if h is not None]
            draw_pt = max(heights) * PT_PER_IN if heights else 0.0
            gone = not fl.now
            cost_after = 0.0 if gone else fl.span * (draw_pt + fl.overhead_pt)
            saving = fl.cost_before_pt - cost_after
            total_before += fl.cost_before_pt
            total_after += cost_after
            mins = [minpt_of.get(m) for m in fl.members]
            mins = [m for m in mins if m is not None]
            floor = ("—" if not mins
                     else "yes" if min(mins) >= style.ANNOT_FLOOR - 1e-6
                     else f"**NO ({min(mins):.2f} pt)**")
            names = "<br>".join(f"`{PAPER_FIGURES_NAME[m]}`" for m in fl.members
                                if m in PAPER_FIGURES_NAME)
            who = f"{fl.was} → {fl.now}" if fl.now else f"{fl.was} → *removed*"
            lines.append(
                f"| {who} | {names} | {'—' if gone else fl.span} | "
                f"{'—' if gone else format(draw_pt, '.0f')} | "
                f"{fl.cost_before_pt:.0f} | {cost_after:.0f} | "
                f"{saving:+.0f} | {floor} |")
        saved = total_before - total_after
        target = paper_style.SAVING_TARGET_PT
        lines += [
            f"| **total** | | | | **{total_before:.0f}** | **{total_after:.0f}** "
            f"| **{saved:+.0f}** | |",
            "",
            f"**{saved:.0f} pt recovered against the {target:.0f} pt target** "
            f"({saved / target * 100:.0f} %), which is "
            f"{saved / paper_style.PAGE_COLUMN_SPACE:.2f} of a page. The figure",
            f"set now costs {total_after:.0f} pt of column-space, down from "
            f"{total_before:.0f} pt.",
            "",
            "Fig. 1 (the TikZ architecture diagram, 248 pt) is out of scope and is",
            "excluded from both sides. Fig. 4 → Fig. 3 (PCA + dendrogram) is",
            "deliberately untouched: its height is what made the dendrogram leaf",
            "labels legible.",
            "",
            "Still rendered, no longer placed — the fallbacks, at zero cost unless",
            "the author puts one back:",
            "",
        ]
        for m, why in paper_style.unplaced():
            spec = paper_style.PAPER_FIGURES[m]
            h = height_of.get(m)
            lines.append(
                f"- `{paper_style.out_stem(m)}` — {why}"
                + (f", {h * PT_PER_IN:.0f} pt tall" if h is not None else "")
                + (f"; reinstating it as its own single-column float would cost "
                   f"about {h * PT_PER_IN + 38:.0f} pt." if h is not None else ""))

        # The budget above iterates FLOATS, which only knows about floats the paper
        # places. Artifact-only figures would otherwise vanish from the narrative
        # and the report would read as though it had covered everything it gated.
        artifact_only = [(k, s) for k, s in sorted(paper_style.PAPER_FIGURES.items())
                         if s.artifact_only]
        if artifact_only:
            lines += [
                "",
                "## Artifact-only figures",
                "",
                "Gated and measured above, shipped in `published/`, but included by",
                "no float — so they cost no column-space and do not appear in the",
                "budget. These are the other variant subset's cut of a panel the",
                "camera-ready places for one subset only.",
                "",
            ]
            for (subset, stem), spec in artifact_only:
                h = height_of.get((subset, stem))
                mn = minpt_of.get((subset, stem))
                lines.append(
                    f"- `published/{subset}/{stem}.pdf` — {spec.paper_fig}"
                    + (f", {h * PT_PER_IN:.0f} pt tall" if h is not None else "")
                    + (f", min {mn:.2f} pt" if mn is not None else ""))

        # ---- what main.tex has to change --------------------------------------
        lines += [
            "",
            "## LaTeX-side changes",
            "",
            "This pipeline does not edit `main.tex`, and half of each saving",
            "above is a LaTeX-side change: a float that stops spanning, an",
            "`\\includegraphics` that goes away, a `width=` factor that no longer",
            "matches the PDF it scales. A `width=` left at its old value is the",
            "dangerous one — it silently rescales the PDF and re-shrinks every",
            "label, which is exactly what Addendum A was for.",
            "",
            "**Worth checking while you are in there.** Addendum B.1 measured the",
            "old Fig. 2 drawing at 241 pt, but the PDF this pipeline produces for",
            "it, `baseline-fig01b_per_variant_bars.pdf`, is 299 pt tall — so",
            "`main.tex` was including it at about 0.81 scale, and its 7 pt labels",
            "were printing at roughly 5.7 pt. Every other float's measurement",
            "reconciles with its PDF to within a point, so this looks like one",
            "stale `width=` factor rather than a systematic problem. That figure",
            "is being deleted either way, but the same check is worth running over",
            "whatever `width=` values survive: each should make the PDF come out",
            "at its natural size.",
            "",
        ]
        for fl in paper_style.FLOATS:
            changes = paper_style.LATEX_CHANGES.get(fl.was)
            if not changes:
                continue
            who = f"{fl.was} → {fl.now}" if fl.now else f"{fl.was} (removed)"
            lines.append(f"**{who}**")
            lines.append("")
            lines += [f"- {c}" for c in changes]
            lines.append("")

    lines += ["", "## Result", ""]
    if failures:
        lines.append(f"**FAIL** — {len(failures)} violation(s):")
        lines.append("")
        lines += [f"- {f}" for f in failures]
    else:
        lines.append(f"**PASS** — {len(rows)} figures, all at target width "
                     f"and above the {style.ANNOT_FLOOR} pt floor.")
    if warnings:
        lines += ["", f"{len(warnings)} height-budget warning(s):", ""]
        lines += [f"- {w}" for w in warnings]
    lines += ["", f"Contact sheet: `{qa_dir.name}/` "
                  f"({CONTACT_DPI} dpi PNG per figure).", ""]

    report = out / ("QA-FIGS-SA.md" if sa else "QA-FIGS.md")
    report.write_text("\n".join(lines))
    print("\n".join(lines[-(len(failures) + len(warnings) + 8):]))
    print(f"\nreport: {report}")
    print(f"contact sheet: {qa_dir}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

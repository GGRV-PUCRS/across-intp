#!/usr/bin/env python3
"""
sa_style.py -- Printed geometry for the Seminario de Andamento (SA) figure set.

Same problem, same fix, different page. The SA document embedded figures
rendered 7.2 to 13.5 in wide and let ``\\includegraphics`` scale them down,
which multiplies every font by the scale factor: eight of the nine figures
printed below the 6.5 pt floor, the worst at 2.90 pt. This module is the SA's
half of the camera-ready pass that fixed the same defect for the SBAC-PAD
paper (``paper_style.py``, and ``bench/plot/README.md`` "Why printed size").

It is deliberately thin. Everything that decides how a figure *looks* --
rcParams, the font floors, the exact-width ``save`` -- is imported from
``paper_style`` and re-exported here, so the two styles cannot drift apart.
What this module owns is the two things that are genuinely different:

1. the page geometry, measured from the compiled SA (acmart sigconf, not
   IEEEtran -- the column is 3.36 in, *not* the paper's 3.45); and
2. the per-figure ``FigSpec`` table, keyed the way the SA .tex names them.

Like ``paper_style``, this exposes no data-shaping knobs: only size, layout
and typography may change, and the QA gate's ``--compare-to`` content diff is
what proves that they did.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import paper_style  # noqa: E402

# Imported wholesale so a figure rendered in SA geometry is typographically
# identical to a paper figure: same floors, same rcParams, same exact-width
# save. Re-exported rather than re-declared -- a second copy of these numbers
# is exactly how the two styles would drift.
from paper_style import (  # noqa: E402,F401
    ANNOT,
    ANNOT_FLOOR,
    AXIS_FLOOR,
    BODY,
    PAD_INCHES,
    TITLE,
    FigSpec,
    compact_legend,
    save,
)

import matplotlib.pyplot as plt  # noqa: E402

# The one typographic difference from the paper set. ``paper_style`` puts
# legend text at ANNOT_FLOOR, with the in-cell annotations; the SA pass counts
# a legend as structural text and holds it at AXIS_FLOOR. F3 in particular
# moves its entire per-cell encoding into two legend entries, so the legend
# stops being decoration and becomes the only thing that says what a colour
# means -- it has to be as legible as an axis label.
LEGEND = AXIS_FLOOR


def apply() -> None:
    """Install ``paper_style``'s rcParams, then raise legends to AXIS_FLOOR.

    Everything else -- fonttype 42, the DejaVu Sans family, the thinned
    furniture, the constrained-layout padding -- is inherited unchanged, so an
    SA figure and a paper figure are the same drawing at two page widths.
    """
    paper_style.apply()
    plt.rcParams["legend.fontsize"] = LEGEND

# --------------------------------------------------------------------------
# Page geometry (acmart, sigconf)
#
# Measured with PyMuPDF on the compiled SA, not taken from the class file:
# 241.8 pt column, 506.3 pt text block, 626 pt text height. Reusing IEEEtran's
# 3.45 in column here would be a 2.7 % overshoot -- LaTeX would scale every
# single-column figure to 0.974 and the 7.0 pt floor would print at 6.8 pt,
# which is the whole failure this pass exists to remove.
# --------------------------------------------------------------------------

COLUMN_WIDTH = 3.36   # inches, \columnwidth  (241.8 pt)
TEXT_WIDTH = 7.03     # inches, \textwidth    (506.3 pt)
TEXT_HEIGHT = 8.69    # inches, text block    (626 pt)

# One page of the SA holds this many column-inches of float drawing:
# two columns times the text height. The height budgets below are set so the
# regenerated set costs about what the current one does; the gate reports the
# delta in these units.
PAGE_COLUMN_INCHES = 2 * TEXT_HEIGHT

# The SA's page limit (Instrucao Normativa). The final gate compiles the
# document and counts pages; this is the number it asserts against.
PAGE_LIMIT = 14


# --------------------------------------------------------------------------
# Per-figure targets
#
# Keyed ("sa", stem) rather than by stem alone so the same QA gate can iterate
# this table and paper_style.PAPER_FIGURES without caring which it got. The
# stems are the ones the SA .tex already writes in its \includegraphics, so
# the rendered directory is a drop-in for the Overleaf project's fig/.
#
# ``span`` is not a FigSpec field (the paper's floats carry it in FLOATS
# instead), so it lives in SPAN below, next to the .tex change that sets it.
# --------------------------------------------------------------------------

SA_FIGURES: dict[tuple[str, str], FigSpec] = {
    # Two panels side by side at column width. The panel titles are the first
    # thing to go if the height fights back -- the .tex caption already says
    # what both panels are -- but the annotation bars must hold ANNOT_FLOOR.
    ("sa", "w4-summary"): FigSpec(
        COLUMN_WIDTH, 1.9, 1.88, "Sec. 3.3 (figure, \\linewidth)",
        "w4-summary.pdf"),

    # The biggest single win in the set: the per-cell "ok"/"--" strings were
    # 7.5 pt text scaled to 3.73 pt. Two colours plus one legend entry each
    # carry the same information with no glyph at all, which is what buys the
    # room for 7 pt row and column labels at half the width.
    ("sa", "F3-availability-grid"): FigSpec(
        TEXT_WIDTH, 2.4, 2.38, "Sec. 3.4 (figure*, \\linewidth)",
        "F3-availability-grid.pdf"),

    # 15 metric rows at 7 pt need about 0.14 in of pitch each, so the rows
    # alone are 2.1 in and the budget is mostly them. The shared legend stays
    # one row below the panels; the two-line suptitle moves to the caption.
    ("sa", "F10-victim-delta-forest"): FigSpec(
        TEXT_WIDTH, 3.4, 3.38, "Sec. 3.3 (figure*, \\linewidth)",
        "F10-victim-delta-forest.pdf"),

    # Seven horizontal bars plus a two-entry legend at column width.
    ("sa", "F11-vmguest-portable-vs-canonical"): FigSpec(
        COLUMN_WIDTH, 2.4, 2.38, "Sec. 3.4 (figure, \\linewidth)",
        "F11-vmguest-portable-vs-canonical.pdf"),

    # The three-line italic explainer inside the figure duplicated the LaTeX
    # caption almost sentence for sentence; removing it is most of the height.
    ("sa", "F13-tier-scheduling-idi"): FigSpec(
        TEXT_WIDTH, 3.0, 2.98, "Sec. 3.4 (figure*, \\linewidth)",
        "F13-tier-scheduling-idi.pdf"),

    # The S8 psp rebank arm of the same float. Rendered alongside the banked
    # arm so the author can compare the two before the SA freeze and swap one
    # \includegraphics line; only one of the two is ever placed, so this one
    # is gated but costs no column-inches (see artifact_only).
    ("sa", "F13-tier-scheduling-idi-psp"): FigSpec(
        TEXT_WIDTH, 3.0, 2.98, "Sec. 3.4 alternative (S8 psp rebank)",
        "F13-tier-scheduling-idi-psp.pdf", artifact_only=True),

    # 7 rows x 4 cols of cell numbers: these are the ANNOT_FLOOR consumers,
    # and at column width the cell pitch is 0.34 in, which holds 6.5 pt.
    ("sa", "F8-cadence-sensitivity"): FigSpec(
        COLUMN_WIDTH, 2.4, 2.38, "Sec. 3.5 (figure, \\linewidth)",
        "F8-cadence-sensitivity.pdf"),

    # Legend consolidated to one row: two refs x two variants read as 2+2
    # entries rather than the 4-entry two-column block, which is what lets the
    # curve keep its height at column width.
    ("sa", "F9-overhead-vs-cadence"): FigSpec(
        COLUMN_WIDTH, 2.5, 2.48, "Sec. 3.5 (figure, \\linewidth)",
        "F9-overhead-vs-cadence.pdf"),

    # Already gate-compliant, for IEEEtran's 3.45 in column. Re-emitted at the
    # acmart column and otherwise untouched: same renderer, same layout, same
    # data, 0.09 in narrower.
    ("sa", "fig10_variant_resource_heatmap"): FigSpec(
        COLUMN_WIDTH, 3.0, 3.00, "Sec. 3.1 (figure, \\linewidth)",
        "fig10_variant_resource_heatmap.pdf"),

    # Already at 7.00 in and 6.60 pt, i.e. already passing. Re-emitted only to
    # remove the residual 0.4 % downscale that 7.00 into a 7.03 in text block
    # would leave; if make_gantt.py is not available the current PDF ships
    # unchanged and this row is skipped (see render-sa-figures.py).
    ("sa", "schedule-plan-vs-actual"): FigSpec(
        TEXT_WIDTH, 4.0, 3.95, "Sec. 4 (figure*, \\textwidth)",
        "schedule-plan-vs-actual.pdf"),
}

# Columns of page each float spans: 2 = figure*, 1 = figure. What costs page
# space is the float, and a figure* pays for its drawing twice because it
# consumes both columns -- so this is the multiplier in the column-inch
# accounting, and it is also exactly what the .tex environment declares.
SPAN: dict[str, int] = {
    "w4-summary": 1,
    "F3-availability-grid": 2,
    "F10-victim-delta-forest": 2,
    "F11-vmguest-portable-vs-canonical": 1,
    "F13-tier-scheduling-idi": 2,
    "F13-tier-scheduling-idi-psp": 2,
    "F8-cadence-sensitivity": 1,
    "F9-overhead-vs-cadence": 1,
    "fig10_variant_resource_heatmap": 1,
    "schedule-plan-vs-actual": 2,
}


# --------------------------------------------------------------------------
# What seminario-andamento.tex has to change
#
# This pipeline does not edit the SA .tex. Every figure below is emitted at
# its exact printed width, so every surviving ``width=`` factor must be the
# full one -- a factor left at 0.92 or 0.96 silently rescales the PDF and
# re-shrinks every label, which is the defect this pass exists to remove.
# The gate prints this table into the report the author actually reads.
# --------------------------------------------------------------------------

LATEX_CHANGES: dict[str, tuple[str, str, tuple[str, ...]]] = {
    # stem: (current width= factor, required factor, notes)
    "fig10_variant_resource_heatmap": (
        "0.92\\linewidth", "\\linewidth",
        ("The PDF is now 3.36 in, exactly \\columnwidth; at 0.92 it would "
         "print its 6.5 pt cell numbers at 6.0 pt.",)),
    "w4-summary": (
        "\\linewidth", "\\linewidth",
        ("No change to the factor. The two in-figure panel titles moved into "
         "the caption, which must now name both panels (cpu absolute "
         "faithfulness; llcmr directional faithfulness) and carry the "
         "faithful/adjudicable cell count and the p value.",)),
    "F11-vmguest-portable-vs-canonical": (
        "\\linewidth", "\\linewidth",
        ("No change to the factor. The two-line in-figure title moved to the "
         "caption.",)),
    "F8-cadence-sensitivity": (
        "\\linewidth", "\\linewidth",
        ("No change to the factor. The three-line in-figure title moved to "
         "the caption, including the 'blank = metric near zero' reading "
         "note, which is no longer drawn.",)),
    "F9-overhead-vs-cadence": (
        "\\linewidth", "\\linewidth",
        ("No change to the factor. The three-line in-figure title moved to "
         "the caption, including the error-bar definition.",)),
    "F10-victim-delta-forest": (
        "0.96\\linewidth", "\\linewidth",
        ("The PDF is now 7.03 in, exactly \\textwidth.",
         "The two-line in-figure suptitle moved to the caption, which must "
         "carry the grey-band reading (negligible effect) and the "
         "filled/open significance convention.")),
    "F3-availability-grid": (
        "0.96\\linewidth", "\\linewidth",
        ("The PDF is now 7.03 in, exactly \\textwidth.",
         "The per-cell 'ok'/'--' text is gone: availability is now a "
         "two-colour encoding, with the same two strings as the legend keys. "
         "The caption already carries the message and needs no new sentence.",
         "The panel titles are the variant names alone now. The reading note "
         "they used to carry -- 'left: portable + regime | right: RDT "
         "canonicals' -- does not fit at 7 pt across half the text block, so "
         "the caption must state which side of the rule is which.")),
    "F13-tier-scheduling-idi": (
        "0.96\\linewidth", "\\linewidth",
        ("The PDF is now 7.03 in, exactly \\textwidth.",
         "The three-line italic explainer under the panels is gone; it "
         "duplicated the caption. Check that the caption still states that "
         "T1 and A share a 5-class model while B adds a 6th regime class.",
         "If the S8 psp rebank is adopted before the freeze, point this "
         "line at F13-tier-scheduling-idi-psp.pdf and update the Section "
         "3.4/4 numbers from 5753 to 4402 in the same patch.")),
    "schedule-plan-vs-actual": (
        "\\textwidth", "\\textwidth",
        ("No change to the factor, and no change to the figure unless it is "
         "re-emitted at 7.03 in; the current 7.00 in PDF prints at 0.996 "
         "scale, i.e. 6.60 pt becomes 6.57 pt, which still clears the "
         "floor.",)),
}


# The ``width=`` factor each figure is included at *today*, before the patch
# in LATEX_CHANGES lands. Multiplied by the column or text width (per SPAN)
# this gives the width the current PDF is actually printed at, which is what
# the QA gate needs to price the current figure set in column-inches and to
# report what the regeneration costs or saves against it.
CURRENT_WIDTH_FACTOR: dict[str, float] = {
    "fig10_variant_resource_heatmap": 0.92,
    "w4-summary": 1.00,
    "F11-vmguest-portable-vs-canonical": 1.00,
    "F8-cadence-sensitivity": 1.00,
    "F9-overhead-vs-cadence": 1.00,
    "F10-victim-delta-forest": 0.96,
    "F3-availability-grid": 0.96,
    "F13-tier-scheduling-idi": 0.96,
    "F13-tier-scheduling-idi-psp": 0.96,
    "schedule-plan-vs-actual": 1.00,
}


def printed_width(stem: str, factor: float | None = None) -> float:
    """Inches the SA prints ``stem`` at, for a given ``width=`` factor.

    ``figure*`` floats scale against the text block, ``figure`` against the
    column, which is the whole reason the two width targets exist.
    """
    if factor is None:
        factor = CURRENT_WIDTH_FACTOR.get(stem, 1.0)
    base = TEXT_WIDTH if SPAN.get(stem, 1) == 2 else COLUMN_WIDTH
    return factor * base


def spec_for(stem: str) -> FigSpec | None:
    """SA printed spec for ``stem``, or None if it is not an SA figure."""
    return SA_FIGURES.get(("sa", stem))


def column_inches(stem: str, height_in: float) -> float:
    """Column-inches of page a float of this drawing height costs.

    A ``figure*`` consumes both columns, so its drawing is paid for twice.
    Artifact-only specs cost nothing: they are rendered as alternatives and
    no float includes them unless the author swaps one in.
    """
    spec = spec_for(stem)
    if spec is not None and spec.artifact_only:
        return 0.0
    return SPAN.get(stem, 1) * height_in

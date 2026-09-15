#!/usr/bin/env python3
"""jsa_style.py -- shared camera-ready typography and sizing for the JSA
("Environment-Aware Cross-Application Interference Profiling...") figure
rework.

Same contract as paper_style.py (SBAC-PAD): each figure is rendered at its
*exact printed size* so a font size set here is a true printed point size.
The difference is geometry -- this manuscript is a single-column elsarticle
preprint that displays every figure via \\widefig{...} at \\figscale=1.3 x
\\textwidth, so a figure authored at COLUMN_WIDTH/TEXT_WIDTH below reads,
in print, 1.3x larger than the inches recorded here. Author at these sizes;
the manuscript's own upscale is what buys the extra headroom over the 7 pt
floor -- do not compensate for it here or the floor is paid twice.

Per the brief's ground rules: colorblind-safe Okabe-Ito palette, marker
shape as a second channel for any categorical distinction (never color
alone), grey reserved for unavailable/unsupported cells, no in-figure
titles/subtitles beyond what is needed to decode the marks (the 2026-09-15
caption-policy update moved restatement of the result into the caption).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import matplotlib.pyplot as plt
from matplotlib.transforms import Bbox

# --------------------------------------------------------------------------
# Page geometry (brief's ground rules: single column ~252 pt, full width
# ~516 pt -- these are the manuscript's pre-\figscale dimensions)
# --------------------------------------------------------------------------

COLUMN_WIDTH = 252.0 / 72.0   # inches, 3.5 in
TEXT_WIDTH = 516.0 / 72.0     # inches, 7.16 in

# --------------------------------------------------------------------------
# Typography floors (identical contract to paper_style.py)
# --------------------------------------------------------------------------

ANNOT_FLOOR = 6.5     # heatmap cell annotations, segment tags
AXIS_FLOOR = 7.0      # axis labels, ticks, legends

BODY = 7.0
LEGEND = 6.5
TITLE = 7.5            # reserved for multi-panel short statistical tags only
ANNOT = 6.5

PAD_INCHES = 0.02

# --------------------------------------------------------------------------
# Okabe-Ito colorblind-safe palette
# https://jfly.uni-koeln.de/color/ -- the eight-color set, black first so it
# is never assigned to data by an unthinking next(cycle).
# --------------------------------------------------------------------------

BLACK = "#000000"
ORANGE = "#E69F00"
SKY_BLUE = "#56B4E9"
BLUISH_GREEN = "#009E73"
YELLOW = "#F0E442"
BLUE = "#0072B2"
VERMILLION = "#D55E00"
REDDISH_PURPLE = "#CC79A7"
GREY = "#999999"          # reserved: unavailable / unsupported cells only

OKABE_ITO = (BLUE, VERMILLION, BLUISH_GREEN, ORANGE, REDDISH_PURPLE,
             SKY_BLUE, YELLOW, BLACK)

# Two profiler variants recur across nearly every figure in this set;
# fixing their color+marker pair once keeps the encoding identical figure
# to figure, which is itself part of "every figure must stand alone".
VARIANT_COLOR = {"v2.1": BLUE, "v3.3": VERMILLION}
VARIANT_MARKER = {"v2.1": "o", "v3.3": "^"}
VARIANT_LABEL = {"v2.1": "v2.1", "v3.3": "v3.3"}


def apply() -> None:
    """Install the camera-ready rcParams. Call after any script setup_style()."""
    plt.rcParams.update({
        "pdf.fonttype":      42,
        "ps.fonttype":       42,
        "font.family":       "DejaVu Sans",
        "font.size":         BODY,
        "axes.titlesize":    TITLE,
        "axes.labelsize":    BODY,
        "xtick.labelsize":   BODY,
        "ytick.labelsize":   BODY,
        "legend.fontsize":   LEGEND,
        "legend.frameon":    False,
        "axes.spines.top":   False,
        "axes.spines.right": False,
        "axes.grid":         True,
        "grid.linestyle":    ":",
        "grid.alpha":        0.4,
        "axes.linewidth":    0.6,
        "grid.linewidth":    0.5,
        "xtick.major.width": 0.6,
        "ytick.major.width": 0.6,
        "xtick.major.size":  2.5,
        "ytick.major.size":  2.5,
        "xtick.major.pad":   1.5,
        "ytick.major.pad":   1.5,
        "axes.labelpad":     2.0,
        "axes.titlepad":     3.0,
        "lines.linewidth":   1.0,
        "axes.prop_cycle":   plt.cycler(color=list(OKABE_ITO)),
        "legend.handlelength": 1.4,
        "legend.handletextpad": 0.5,
        "legend.columnspacing": 1.0,
        "legend.borderaxespad": 0.3,
        "figure.constrained_layout.w_pad":  0.02,
        "figure.constrained_layout.h_pad":  0.02,
        "figure.constrained_layout.wspace": 0.02,
        "figure.constrained_layout.hspace": 0.02,
    })


@dataclass(frozen=True)
class FigSpec:
    """Printed geometry for one JSA figure.

    width   exact printed width in inches (COLUMN_WIDTH or TEXT_WIDTH,
            occasionally a fraction for a panel).
    height  the height actually used for the render.
    label   the manuscript \\label{...} this spec belongs to, for the QA
            report -- not used for filenames (jsa figures keep their
            existing Figure_N.pdf names, tracked in fig_names.py).
    """
    width: float
    height: float
    label: str


def save(fig, path, spec: FigSpec) -> tuple[float, float]:
    """Write ``fig`` to ``path`` at exactly ``spec.width`` inches wide.

    Same tight-bbox-then-pad-to-target approach as paper_style.save(): trims
    dead margins, then widens symmetrically to the exact printed width so
    the manuscript's \\figscale upscale multiplies a known quantity.
    """
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    bb = fig.get_tightbbox(renderer).padded(PAD_INCHES)
    dw = spec.width - bb.width
    if dw < -0.01:
        import warnings
        warnings.warn(
            f"{path.name}: content is {bb.width:.2f} in wide but the target "
            f"is {spec.width:.2f} in -- the saved page will clip. Adjust the "
            f"layout for this figure.", stacklevel=2)
    bb = Bbox.from_extents(bb.x0 - dw / 2.0, bb.y0, bb.x1 + dw / 2.0, bb.y1)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, bbox_inches=bb)
    return spec.width, bb.height


def compact_legend(ax_or_fig, handles, labels, **kwargs):
    """One-row legend tuned for camera-ready panels."""
    opts = dict(
        loc="lower center", bbox_to_anchor=(0.5, 1.0),
        ncol=max(1, len(handles)), frameon=False, fontsize=LEGEND,
        handlelength=1.2, handletextpad=0.4, columnspacing=0.8,
        borderaxespad=0.15, borderpad=0.0,
    )
    opts.update(kwargs)
    return ax_or_fig.legend(handles, labels, **opts)

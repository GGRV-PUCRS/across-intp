#!/usr/bin/env python3
"""p2_figio.py -- one place that decides where a P2 figure lands on disk.

Every renderer in the set writes the same figure twice, once per format. Doing
that inline in each script meant the layout was restated in nine places and
drifted. This module owns it instead::

    results/figures/<set>/png/<name>.png
    results/figures/<set>/pdf/<name>.pdf

Format subdirectories rather than a flat directory: the PNGs are the ones that
get dragged into slides and the PDFs are the ones LaTeX includes, so the two
audiences never have to filter one out of a listing of the other.

The filename comes from ``fig_names`` -- ``<figure-id>-<what-it-shows>--<which
-campaign>`` -- so a figure dragged out of this tree still says what it is and
what produced it. The F-number survives at the front because
``docs/FIGURES-PLAN.md``, the reports and the paper drafts cite figures by it.
The renderer's own stem stays the internal key: it is what selects the printed
geometry in ``paper_style`` / ``sa_style`` and the description here.

Each renderer sets the campaign tag once, from the tree it was pointed at::

    p2_figio.set_dataset(fig_names.dataset_tag(args.campaign_dir))

Leaving it unset is an error, not a default: a figure named after no campaign
is exactly the thing this layout exists to prevent.
"""
from __future__ import annotations

from pathlib import Path

import fig_names

FORMATS = ("png", "pdf")
DEFAULT_DPI = 150
#: The Seminario de Andamento cut ships PNGs for the deck as well as the PDFs
#: LaTeX includes; 300 dpi so a figure fills a projected slide without
#: resampling artefacts.
SA_PNG_DPI = 300

_DATASET: str | None = None


def set_dataset(tag: str) -> None:
    """Name the campaign every subsequent ``save`` call is rendering."""
    global _DATASET
    _DATASET = tag


def dataset() -> str:
    if not _DATASET:
        raise RuntimeError(
            "p2_figio.set_dataset() was never called: the renderer does not "
            "know which campaign it is drawing, and the figure would be "
            "written under a name that cannot be traced back to its data.")
    return _DATASET


def save(fig, outdir, stem: str, dpi: int = DEFAULT_DPI,
         *, qualifier: str = "", **savefig_kw) -> list[Path]:
    """Write ``fig`` as ``<outdir>/<fmt>/<name>.<fmt>`` for each format.

    ``stem`` is the renderer's internal figure key; the name on disk is
    ``fig_names.name(stem, ...)``. ``bbox_inches="tight"`` is the default the
    whole set already used; pass it explicitly in ``savefig_kw`` to override.
    Returns the written paths.
    """
    outdir = Path(outdir)
    savefig_kw.setdefault("bbox_inches", "tight")
    base = fig_names.name(stem, dataset(), qualifier=qualifier)

    written = []
    for fmt in FORMATS:
        d = outdir / fmt
        d.mkdir(parents=True, exist_ok=True)
        path = d / f"{base}.{fmt}"
        # dpi is a raster concern; passing it for PDF is harmless but noisy.
        fig.savefig(path, dpi=dpi, **savefig_kw) if fmt == "png" else \
            fig.savefig(path, **savefig_kw)
        written.append(path)
    return written


def save_flat(fig, outdir, stem: str, spec, *, dpi: int = SA_PNG_DPI,
              qualifier: str = "") -> tuple[float, float]:
    """Write one figure at its exact printed size, flat under ``outdir``.

    The Seminario de Andamento and camera-ready cuts are collected into a
    single directory that a LaTeX project includes from, so they skip the
    per-format subdirectories the exploratory sets use. The PDF is sized by
    ``spec`` (a ``paper_style.FigSpec``); the PNG sibling is for the deck.
    """
    import matplotlib.pyplot as plt
    import sa_style

    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    base = fig_names.name(stem, dataset(), qualifier=qualifier)
    w, h = sa_style.save(fig, outdir / f"{base}.pdf", spec)
    fig.savefig(outdir / f"{base}.png", dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {outdir}/{base}.{{pdf,png}} ({w:.2f} x {h:.2f} in)")
    return w, h


def describe(outdir, stem: str, *, qualifier: str = "") -> str:
    """One-line 'wrote ...' message naming both outputs."""
    base = fig_names.name(stem, dataset(), qualifier=qualifier)
    return f"wrote {Path(outdir)}/{{{','.join(FORMATS)}}}/{base}.{{{','.join(FORMATS)}}}"

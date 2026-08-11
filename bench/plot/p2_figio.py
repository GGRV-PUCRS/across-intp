#!/usr/bin/env python3
"""p2_figio.py -- one place that decides where a P2 figure lands on disk.

Every renderer in the set writes the same figure twice, once per format. Doing
that inline in each script meant the layout was restated in nine places and
drifted. This module owns it instead::

    results/figures/<set>/png/<stem>.png
    results/figures/<set>/pdf/<stem>.pdf

Format subdirectories rather than a flat directory: the PNGs are the ones that
get dragged into slides and the PDFs are the ones LaTeX includes, so the two
audiences never have to filter one out of a listing of the other.

Filenames keep their F-number stem (``F0-fingerprint-heatmap``). The number is
the anchor that docs/FIGURES-PLAN.md and the reports cross-reference, and the
seminar deck swaps images by filename. Only the in-plot TITLES dropped the
F-numbers, since a paper reader never sees the repository's numbering.
"""
from __future__ import annotations

from pathlib import Path

FORMATS = ("png", "pdf")
DEFAULT_DPI = 150


def save(fig, outdir, stem: str, dpi: int = DEFAULT_DPI, **savefig_kw) -> list[Path]:
    """Write ``fig`` as ``<outdir>/<fmt>/<stem>.<fmt>`` for each format.

    ``bbox_inches="tight"`` is the default the whole set already used; pass it
    explicitly in ``savefig_kw`` to override. Returns the written paths.
    """
    outdir = Path(outdir)
    savefig_kw.setdefault("bbox_inches", "tight")

    written = []
    for fmt in FORMATS:
        d = outdir / fmt
        d.mkdir(parents=True, exist_ok=True)
        path = d / f"{stem}.{fmt}"
        # dpi is a raster concern; passing it for PDF is harmless but noisy.
        fig.savefig(path, dpi=dpi, **savefig_kw) if fmt == "png" else \
            fig.savefig(path, **savefig_kw)
        written.append(path)
    return written


def describe(outdir, stem: str) -> str:
    """One-line 'wrote ...' message naming both outputs."""
    return f"wrote {Path(outdir)}/{{{','.join(FORMATS)}}}/{stem}.{{{','.join(FORMATS)}}}"

#!/usr/bin/env python3
"""crop-fig14-fingerprint.py -- split the F12 fingerprint render into the two
per-variant halves the JSA paper includes as fig:fingerprint (v2.1 left,
v3.3 right).

The combined F12-fingerprint PDF (plot-tierb-fingerprint.py, ~1278 x 386 pt)
places the v2.1 panel at x in [0, 655.5] and the v3.3 panel at x in
[657.6, 1275.7]; the banked paper PDFs carry exactly these cropboxes (and a
346.4 pt tall window that drops the figure's bottom margin). pypdf is not
available in this environment, so the split uses PyMuPDF: cropbox and
mediabox are both set to the banked rectangles, which read back identical.

    python3 bench/plot/crop-fig14-fingerprint.py <f12.pdf> <out_dir>

writes <out_dir>/fig_fingerprint_v21.pdf and <out_dir>/fig_fingerprint_v33.pdf
"""
from __future__ import annotations

import sys
from pathlib import Path

import pymupdf

#: Banked cropboxes (PDF points) of paper/figs/fig_fingerprint_v{21,33}.pdf.
CROPS = {
    "fig_fingerprint_v21.pdf": (0.0, 0.0, 655.455, 346.414),
    "fig_fingerprint_v33.pdf": (657.611, 0.0, 1275.694, 346.414),
}


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    src, out_dir = Path(sys.argv[1]), Path(sys.argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, (x0, y0, x1, y1) in CROPS.items():
        doc = pymupdf.open(src)
        page = doc[0]
        rect = pymupdf.Rect(x0, y0, x1, y1)
        page.set_cropbox(rect)
        page.set_mediabox(rect)
        dest = out_dir / name
        doc.save(dest)
        doc.close()
        # read back and report the effective box + visible text span
        chk = pymupdf.open(dest)
        p = chk[0]
        n_words = len(p.get_text("words"))
        print(f"wrote {dest} cropbox={tuple(round(v, 1) for v in p.cropbox)} "
              f"({n_words} words visible)")
        chk.close()


if __name__ == "__main__":
    main()

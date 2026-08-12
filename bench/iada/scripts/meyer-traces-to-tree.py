#!/usr/bin/env python3
"""meyer-traces-to-tree.py — lay Meyer's 12 published patterned traces out as
an IADA tree consumable by run-iada-experiment.sh (W2.2 validation leg).

Source: interference-classifier/source/{bench4q,linkbench,tpch}/{inc,dec,osc,con}.csv
        — the genuinely patterned 3-app x 4-pattern trace set from
        Meyer 2020 (JSSPP) / Meyer 2022 (JSS), 7-col ';'-separated,
        281-1080 rows. Unlike generate-iada-tree.py's per-repetition
        aliases (finding F5, bench/iada/CONFORMANCE.md), these patterns
        are real shapes.

Output layout (matches generate-iada-tree.py conventions):
    <out>/<variant>/<env>/source/<app>/<pattern>.csv

Usage:
  meyer-traces-to-tree.py --classifier-repo ~/Desktop/intpismo/interference-classifier \
                          --out /tmp/tree-meyer [--variant meyer] [--env paper]
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

APPS = ("bench4q", "linkbench", "tpch")
PATTERNS = ("inc", "dec", "osc", "con")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--classifier-repo", required=True, type=Path)
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--variant", default="meyer")
    p.add_argument("--env", default="paper")
    args = p.parse_args()

    src_root = args.classifier_repo / "source"
    dst_root = args.out / args.variant / args.env / "source"

    n = 0
    min_rows = None
    for app in APPS:
        (dst_root / app).mkdir(parents=True, exist_ok=True)
        for pat in PATTERNS:
            src = src_root / app / f"{pat}.csv"
            if not src.is_file():
                print(f"FATAL: missing {src}", file=sys.stderr)
                return 2
            rows = sum(1 for _ in src.open())
            min_rows = rows if min_rows is None else min(min_rows, rows)
            shutil.copy(src, dst_root / app / f"{pat}.csv")
            n += 1

    print(f"wrote {n} traces to {dst_root}")
    print(f"shortest trace: {min_rows} rows -> use iada.horizon={min_rows - 1} "
          f"and iada.simLimit={min_rows - 1}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

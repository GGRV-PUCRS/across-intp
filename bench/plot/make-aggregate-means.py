#!/usr/bin/env python3
"""make-aggregate-means.py -- the F7 input adapter.

The two F7 renderers (plot-pca-correlation-circle.py, plot_pca_dendro.py)
consume ``aggregate-means.tsv``: one row per (env, variant, stage, workload,
rep) with per-metric means over the rep window. That file was produced by the
old bench-full pipeline and survives only under ``results/_superseded/`` --
predating the regime metrics, so it stops at 13 columns. The canonical
campaign tree instead holds 1008 per-rep ``portable.tsv`` captures. This
adapter closes that gap: walk the tree, average each rep, emit the schema the
renderers already parse, now with the full 15-metric set.

Per-rep format quirks handled here: three ``#`` comment lines; a header of 15
metric names over 16-field data rows (the leading field is an unlabelled epoch
timestamp, which pandas maps to the index when told there is one extra
column); ``--`` for source-unavailable (kept as NaN, so a metric absent in an
environment stays absent rather than becoming zero).

    python3 bench/plot/make-aggregate-means.py results/p2-15metric-xdeploy-1of3
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("campaign_dir", type=Path)
    ap.add_argument("--capture-name", default="portable.tsv")
    ap.add_argument("--out", type=Path, default=None,
                    help="default: <campaign_dir>/aggregate-means.tsv")
    args = ap.parse_args()

    rows = []
    caps = sorted(args.campaign_dir.glob(f"*/*/*/*/*/{args.capture_name}"))
    for cap in caps:
        # <campaign>/<env>/<variant>/<stage>/<workload>/<rep>/portable.tsv
        rep_dir, workload, stage, variant, env = (p.name for p in cap.parents[:5])
        try:
            df = pd.read_csv(cap, sep="\t", comment="#", index_col=0,
                             na_values=["--"])
        except Exception as e:                      # unreadable capture: report, keep going
            print(f"[skip] {cap}: {e}", file=sys.stderr)
            continue
        rows.append({"env": env, "variant": variant, "stage": stage,
                     "workload": workload, "rep": rep_dir.replace("rep", ""),
                     **df.mean(numeric_only=True).round(3).to_dict()})
    if not rows:
        print(f"no {args.capture_name} under {args.campaign_dir}", file=sys.stderr)
        return 1

    out = args.out or (args.campaign_dir / "aggregate-means.tsv")
    pd.DataFrame(rows).to_csv(out, sep="\t", index=False)
    print(f"wrote {out}: {len(rows)} rows "
          f"({len({r['env'] for r in rows})} envs x "
          f"{len({r['variant'] for r in rows})} variants)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

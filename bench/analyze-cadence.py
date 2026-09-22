#!/usr/bin/env python3
"""analyze-cadence.py -- metric fidelity & sample density vs sampling cadence.

Consumes a cadence-sweep directory produced by bench/run-cadence-sweep.sh
(a `sweep-manifest.tsv` plus one campaign subdir per cadence) and reports,
per (variant, workload, metric):

  * the metric's central value (median over all samples x reps) at each cadence;
  * its deviation from the FINEST-cadence reference -- i.e. does coarser
    sampling miss the signal? (the "1 s cadence misses sub-second LLC-eviction
    transients" question Paper 1 raised qualitatively and Paper 2 quantifies);
  * the realized sample density (rows/rep) at each cadence -- a sampling-rate
    and (proxy) overhead signal.

This is the analysis half of the Paper-2 sampling-frequency axis. Overhead
proper (profiler self-cost vs a reference load) comes from sweeping the
`overhead` stage; this script reads whatever stages are present and focuses on
the solo fingerprint fidelity + density.

Usage:
    python3 bench/analyze-cadence.py <sweep_dir> [--out report.md]
"""
import argparse
import glob
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from intp_metrics import (parse_capture, METRICS_CANON, METRICS_PORTABLE,
                          METRICS_ALL, CLAIM_CLASS, _median, _fmt)


def read_manifest(sweep_dir):
    """Return [(interval_s, cadence_tag, output_dir), ...] sorted finest-first."""
    man = os.path.join(sweep_dir, "sweep-manifest.tsv")
    if not os.path.isfile(man):
        sys.exit(f"no sweep-manifest.tsv under {sweep_dir}")
    rows = []
    with open(man) as fh:
        header = fh.readline()
        for line in fh:
            p = line.rstrip("\n").split("\t")
            if len(p) >= 3:
                rows.append((float(p[0]), p[1], p[2]))
    rows.sort(key=lambda r: r[0])
    return rows


def find_captures(cadence_dir):
    """<env>/<variant>/<stage>/<workload>/rep*/portable.tsv (fallback profiler.tsv)."""
    pat = os.path.join(cadence_dir, "*", "*", "*", "*", "rep*", "portable.tsv")
    caps = glob.glob(pat)
    if not caps:
        caps = glob.glob(pat.replace("portable.tsv", "profiler.tsv"))
    return caps


def cap_meta(path, cadence_dir):
    rel = os.path.relpath(path, cadence_dir).split(os.sep)
    return tuple(rel[:5]) if len(rel) >= 6 else (None,) * 5  # env,variant,stage,wl,rep


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sweep_dir")
    ap.add_argument("--out", default=None)
    ap.add_argument("--by-env", action="store_true",
                    help="break fidelity/density tables down per environment "
                         "(the default pools every env, which hides sign-flipping "
                         "per-env effects -- e.g. the in-guest psp RISE on the "
                         "streaming workload that the pooled table shows falling)")
    ap.add_argument("--tsv", default=None,
                    help="machine-readable rows for the plot layer "
                         "(default <sweep_dir>/cadence-fidelity.tsv)")
    args = ap.parse_args()

    man = read_manifest(args.sweep_dir)
    tags = [t for _, t, _ in man]
    iv_by_tag = {t: iv for iv, t, _ in man}
    ref_tag = tags[0]  # finest interval = reference

    # samples[key+(metric,)][tag] -> flat list of sample values
    samples = defaultdict(lambda: defaultdict(list))
    # density[key][tag] -> per-rep row counts
    # key = (variant, wl); under --by-env, (env, variant, wl)
    density = defaultdict(lambda: defaultdict(list))
    present_metrics = set()

    for iv, tag, _box_cdir in man:
        # Reconstruct the cadence dir from the LOCAL sweep_dir + tag. The
        # manifest's output_dir column records the generation-time (remote)
        # absolute path, which is wrong once the sweep is pulled to another host.
        cdir = os.path.join(args.sweep_dir, f"cadence-{tag}")
        for cap in find_captures(cdir):
            env, variant, _, wl, _ = cap_meta(cap, cdir)
            if variant is None:
                continue
            key = (env, variant, wl) if args.by_env else (variant, wl)
            rows = parse_capture(cap)
            density[key][tag].append(len(rows))
            for m in METRICS_ALL:
                vals = [r[m] for r in rows if r.get(m) is not None]
                if vals:
                    present_metrics.add(m)
                    samples[key + (m,)][tag].extend(vals)

    metrics = [m for m in METRICS_ALL if m in present_metrics]
    keys = sorted({k[:-1] for k in samples})
    label = lambda k: " — ".join(k)  # noqa: E731

    # machine-readable rows for the plot layer (plot-cadence-curves.py).
    # Under --by-env the TSV gains a leading env column and a distinct default
    # name so the plot layer's pooled input is never silently swapped.
    if args.by_env:
        tsv_rows = ["env\tvariant\tworkload\tmetric\tclass\tinterval_s\tcadence_tag\tmedian\tdref"]
    else:
        tsv_rows = ["variant\tworkload\tmetric\tclass\tinterval_s\tcadence_tag\tmedian\tdref"]

    def tsv_key(k):
        return "\t".join(k)

    lines = []
    scope_note = " (per environment)" if args.by_env else " (all environments pooled)"
    lines.append(f"# Cadence sweep: fidelity & sample density vs sampling interval{scope_note} — {args.sweep_dir}\n")
    lines.append(f"Cadences (interval s): {', '.join(f'{iv_by_tag[t]:g}' for t in tags)}. "
                 f"Reference (finest) = {iv_by_tag[ref_tag]:g}s. "
                 f"Variants×workloads: {len(keys)}. Metrics present: {len(metrics)}.\n")
    lines.append("**Fidelity** = median over all samples×reps per cadence; **Δref** = relative "
                 "deviation from the finest-cadence median (large |Δref| at coarse cadence ⇒ the "
                 "signal needs fine sampling). Claim class in parentheses (abs/dir/desc).\n")

    # --- sample density table ---
    lines.append("## Sample density (median rows/rep)\n")
    hdr = "| " + label(("variant", "workload") if not args.by_env else ("env", "variant", "workload")) + " | " + " | ".join(f"{iv_by_tag[t]:g}s" for t in tags) + " |"
    sep = "|---" * (len(tags) + 1) + "|"
    lines.append(hdr)
    lines.append(sep)
    for k in keys:
        cells = []
        for t in tags:
            rc = density[k].get(t, [])
            cells.append(str(int(_median(rc))) if rc else "—")
            if rc:
                tsv_rows.append(f"{tsv_key(k)}\t_density_rows_\tmeta\t{iv_by_tag[t]:g}\t{t}\t{_median(rc):.6g}\t")
        lines.append(f"| {label(k)} | " + " | ".join(cells) + " |")
    lines.append("")

    # --- per key fidelity table ---
    for k in keys:
        lines.append(f"## {label(k)}  *(median per cadence; Δref vs {iv_by_tag[ref_tag]:g}s)*\n")
        hdr = "| metric (class) | " + " | ".join(f"{iv_by_tag[t]:g}s" for t in tags) + " | max|Δref| |"
        sep = "|---" * (len(tags) + 2) + "|"
        lines.append(hdr)
        lines.append(sep)
        for m in metrics:
            per_tag = samples.get(k + (m,), {})
            meds = {t: (_median(per_tag[t]) if per_tag.get(t) else None) for t in tags}
            ref = meds.get(ref_tag)
            cls = {"absolute": "abs", "directional": "dir"}.get(CLAIM_CLASS.get(m, "descriptive"), "desc")
            cells = []
            max_dev = 0.0
            for t in tags:
                mv = meds[t]
                if mv is None:
                    cells.append("—")
                    continue
                cell = _fmt(mv)
                dev = None
                if ref not in (None, 0) and t != ref_tag:
                    dev = (mv - ref) / abs(ref)
                    max_dev = max(max_dev, abs(dev))
                    cell += f" ({dev:+.0%})"
                cells.append(cell)
                tsv_rows.append(f"{tsv_key(k)}\t{m}\t{cls}\t{iv_by_tag[t]:g}\t{t}\t{mv:.6g}\t"
                                + ("" if dev is None else f"{dev:.6g}"))
            mxd = f"{max_dev:.0%}" if ref not in (None, 0) else "—"
            lines.append(f"| {m} ({cls}) | " + " | ".join(cells) + f" | {mxd} |")
        lines.append("")

    if args.tsv:
        tsv_path = args.tsv
    elif args.by_env:
        tsv_path = os.path.join(args.sweep_dir, "cadence-fidelity-by-env.tsv")
    else:
        tsv_path = os.path.join(args.sweep_dir, "cadence-fidelity.tsv")
    with open(tsv_path, "w") as fh:
        fh.write("\n".join(tsv_rows) + "\n")
    print(f"[wrote {tsv_path} ({len(tsv_rows) - 1} rows)]")

    report = "\n".join(lines)
    if args.out:
        with open(args.out, "w") as fh:
            fh.write(report)
        print(f"[wrote {args.out}]")
    else:
        print(report)


if __name__ == "__main__":
    main()

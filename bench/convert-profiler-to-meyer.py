#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


METRICS = ("netp", "nets", "blk", "mbw", "llcmr", "llcocc", "cpu")
CLAMP = True   # clamp values to [0,100]; disabled (--no-clamp) for proxy columns
               # like membw_est (MB/s) whose magnitude must survive into the trace

# Execution-environment directory names emitted by bench/run-intp-bench.sh.
# Result layout is <env>/<variant>/<stage>/<workload>/rep<R>/profiler.tsv.
# Kept in sync with run-intp-bench.sh's DEFAULT_ENVS comment and
# bench/iada/scripts/plot-iada.py's ENV_ORDER. Bare-metal is the only env
# exercised so far; the container/vm names are wired ahead of those runs so
# the IADA path picks them up without a second pass here.
ENV_NAMES = (
    "bare",
    "container", "container-guest", "container-full",
    "vm", "vm-guest", "vm-full",
)


def _env_index(parts: tuple[str, ...] | list[str]) -> int | None:
    """Index of the first path component that is a known execution env."""
    for i, part in enumerate(parts):
        if part in ENV_NAMES:
            return i
    return None


@dataclass
class ConversionResult:
    source: Path
    output: Path
    rows: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Convert IntP profiler.tsv files into Meyer/IADA CSV format "
            "(semicolon-separated, 7 columns, no header)."
        )
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        help="One or more profiler.tsv files or result directories to scan recursively.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        help=(
            "Mirror converted files under this directory instead of writing "
            "<profiler>.meyer.csv alongside each profiler.tsv."
        ),
    )
    parser.add_argument(
        "--stage",
        action="append",
        default=[],
        help=(
            "Keep only profiler.tsv paths whose stage component matches this value. "
            "May be passed multiple times, e.g. --stage solo --stage timeseries."
        ),
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        help="Write a TSV manifest with source/output path and run metadata.",
    )
    parser.add_argument(
        "--capture-name",
        default="profiler.tsv",
        help=(
            "Capture filename to scan for (default: profiler.tsv). The 15-metric "
            "--portable-metrics campaigns write portable.tsv instead (C26); the "
            "canonical 7 columns are located via the header, so the extra "
            "portable/scheduling-regime columns are ignored."
        ),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing output files.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned conversions without writing files.",
    )
    parser.add_argument(
        "--metrics",
        default=None,
        help=(
            "Comma-separated 7 metric names to emit (header-mapped), overriding the "
            "canonical set. For Approach A: netp,nets,blk,membw_est,llcmr,llcocc,cpu "
            "(membw_est replaces mbw)."
        ),
    )
    parser.add_argument(
        "--no-clamp",
        action="store_true",
        help="Do not clamp values to [0,100] (needed when a column is an absolute "
             "rate like membw_est MB/s).",
    )
    return parser.parse_args()


def iter_profiler_paths(inputs: Iterable[str], capture_name: str = "profiler.tsv") -> list[Path]:
    results: list[Path] = []
    for raw in inputs:
        path = Path(raw)
        if path.is_file():
            if path.name != capture_name:
                raise SystemExit(f"Expected a {capture_name} file, got: {path}")
            results.append(path)
            continue
        if path.is_dir():
            results.extend(sorted(path.rglob(capture_name)))
            continue
        raise SystemExit(f"Input path does not exist: {path}")
    if not results:
        raise SystemExit(f"No {capture_name} files found.")
    return dedupe_preserve_order(results)


def dedupe_preserve_order(paths: Iterable[Path]) -> list[Path]:
    seen: set[Path] = set()
    out: list[Path] = []
    for path in paths:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        out.append(path)
    return out


def stage_from_path(path: Path) -> str | None:
    parts = path.parts
    idx = _env_index(parts)
    if idx is None or idx + 2 >= len(parts):
        return None
    return parts[idx + 2]


def filter_by_stage(paths: list[Path], stages: list[str]) -> list[Path]:
    if not stages:
        return paths
    allowed = {stage.strip() for stage in stages if stage.strip()}
    return [path for path in paths if stage_from_path(path) in allowed]


def split_fields(line: str) -> list[str]:
    if "\t" in line:
        return [field.strip() for field in line.split("\t") if field.strip()]
    return line.split()


def parse_metric_row(
    line: str,
    line_no: int,
    source: Path,
    header_cols: list[str] | None = None,
) -> list[int] | None:
    stripped = line.strip()
    if not stripped:
        return None
    if stripped.startswith("#") or stripped.startswith("ts") or stripped.startswith("netp"):
        return None

    fields = split_fields(stripped)
    if len(fields) < 7:
        return None

    if header_cols and all(metric in header_cols for metric in METRICS):
        # Header-mapped extraction: portable.tsv carries the canonical 7 FIRST
        # plus portable/scheduling-regime columns after them, and the harness
        # prepends a timestamp to data rows but not the header -- the offset
        # accounts for it. For a plain 7-column profiler.tsv this reduces to
        # the same last-7 slice as the fallback below.
        offset = len(fields) - len(header_cols)
        if offset < 0:
            return None
        tail = [fields[offset + header_cols.index(metric)] for metric in METRICS]
    else:
        tail = fields[-7:]
    try:
        # '--'/empty = source unavailable in this env (e.g. RDT mbw/llcocc/llcmr
        # in a KVM guest) -> 0, matching campaign-to-trainsets.py. Without this
        # the canonical 7 of a vm-guest capture abort the whole conversion.
        values = [0 if field in ("--", "") else round(float(field)) for field in tail]
    except ValueError as exc:
        raise ValueError(f"{source}:{line_no}: could not parse metrics from {tail}") from exc

    return [clamp_percent(value) if CLAMP else value for value in values]


def clamp_percent(value: int) -> int:
    if value < 0:
        return 0
    if value > 100:
        return 100
    return value


def output_path_for(source: Path, output_root: Path | None) -> Path:
    if output_root is None:
        return source.with_suffix(".meyer.csv")

    resolved_root = output_root.resolve()
    resolved_source = source.resolve()
    anchor = resolved_source.anchor
    relative = Path(str(resolved_source)[len(anchor) :].lstrip("/")) if anchor else resolved_source
    mirrored = resolved_root / relative
    return mirrored.with_suffix(".meyer.csv")


def extract_metadata(source: Path) -> dict[str, str]:
    parts = source.parts
    idx = _env_index(parts)
    if idx is None:
        return {"env": "", "variant": "", "stage": "", "workload": "", "rep": ""}
    return {
        "env": parts[idx],
        "variant": parts[idx + 1] if idx + 1 < len(parts) else "",
        "stage": parts[idx + 2] if idx + 2 < len(parts) else "",
        "workload": parts[idx + 3] if idx + 3 < len(parts) else "",
        "rep": parts[idx + 4] if idx + 4 < len(parts) else "",
    }


def convert_one(source: Path, output_root: Path | None, force: bool, dry_run: bool) -> ConversionResult:
    output = output_path_for(source, output_root)
    if output.exists() and not force:
        raise FileExistsError(f"Output already exists (use --force): {output}")

    rows: list[list[int]] = []
    header_cols: list[str] | None = None
    with source.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            stripped = line.strip()
            if stripped.startswith("netp") or stripped.startswith("ts\t"):
                # Column header (portable.tsv: canonical 7 + portable cols)
                cols = split_fields(stripped)
                header_cols = cols[1:] if cols and cols[0] == "ts" else cols
                continue
            record = parse_metric_row(line, line_no, source, header_cols)
            if record is not None:
                rows.append(record)

    if not rows:
        raise ValueError(f"No metric rows found in {source}")

    if not dry_run:
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, delimiter=";", lineterminator="\n")
            writer.writerows(rows)

    return ConversionResult(source=source, output=output, rows=len(rows))


def write_manifest(path: Path, results: list[ConversionResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["env", "variant", "stage", "workload", "rep", "rows", "source", "output"])
        for result in results:
            meta = extract_metadata(result.source)
            writer.writerow(
                [
                    meta["env"],
                    meta["variant"],
                    meta["stage"],
                    meta["workload"],
                    meta["rep"],
                    result.rows,
                    str(result.source),
                    str(result.output),
                ]
            )


def main() -> int:
    args = parse_args()
    global METRICS, CLAMP
    if args.metrics:
        METRICS = tuple(m.strip() for m in args.metrics.split(","))
        if len(METRICS) != 7:
            raise SystemExit(f"--metrics needs exactly 7 names, got {len(METRICS)}")
    if args.no_clamp:
        CLAMP = False
    profiler_paths = filter_by_stage(iter_profiler_paths(args.inputs, args.capture_name), args.stage)
    if not profiler_paths:
        raise SystemExit(f"No {args.capture_name} files matched the requested filters.")

    results: list[ConversionResult] = []
    for source in profiler_paths:
        result = convert_one(source, args.output_root, args.force, args.dry_run)
        results.append(result)
        print(f"{source} -> {result.output} ({result.rows} rows)")

    if args.manifest and not args.dry_run:
        write_manifest(args.manifest, results)
        print(f"manifest written to {args.manifest}")

    print(f"converted {len(results)} profiler.tsv file(s)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
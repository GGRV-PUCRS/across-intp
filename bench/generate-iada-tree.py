#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from statistics import median


@dataclass(frozen=True)
class ManifestRow:
    env: str
    variant: str
    stage: str
    workload: str
    rep: str
    rows: int
    source: Path
    output: Path


@dataclass
class LinkedFile:
    rows: list[ManifestRow]
    pattern: str
    destination: Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate classifier/CloudSim input tree from a convert-profiler-to-meyer manifest."
        )
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        required=True,
        help="TSV manifest produced by bench/convert-profiler-to-meyer.py --manifest.",
    )
    parser.add_argument(
        "--out-root",
        type=Path,
        required=True,
        help="Root where source/<workload>/<pattern>.csv and cloudsim input files will be created.",
    )
    parser.add_argument(
        "--env",
        action="append",
        default=[],
        help="Filter by env (default: all in manifest). Can be passed multiple times.",
    )
    parser.add_argument(
        "--variant",
        action="append",
        default=[],
        help="Filter by variant (default: all in manifest). Can be passed multiple times.",
    )
    parser.add_argument(
        "--stage",
        action="append",
        default=["solo"],
        help="Filter by stage (default: solo). Can be passed multiple times.",
    )
    parser.add_argument(
        "--workload-regex",
        default=".*",
        help="Regex to keep workload names (default: keep all).",
    )
    parser.add_argument(
        "--rep-pattern-map",
        default="rep1=inc,rep2=dec,rep3=osc,rep4=con",
        help=(
            "Map repetitions to canonical patterns. Example: "
            "rep1=inc,rep2=dec,rep3=osc,rep4=con"
        ),
    )
    parser.add_argument(
        "--mode",
        choices=("symlink", "copy"),
        default="symlink",
        help="How to materialize source/<workload>/<pattern>.csv files.",
    )
    parser.add_argument(
        "--pattern-merge",
        choices=("error", "first", "mean", "median"),
        default="error",
        help=(
            "How to handle multiple reps mapped to the same canonical pattern for the same "
            "(env, variant, stage, workload). "
            "error=fail on collision (default), first=keep first rep only, "
            "mean/median=aggregate rows and write one canonical CSV."
        ),
    )
    parser.add_argument(
        "--pm-count",
        type=int,
        default=12,
        help="PM count for generated CloudSim input files.",
    )
    parser.add_argument(
        "--pm-size",
        type=int,
        default=100,
        help="PM size for generated CloudSim input files.",
    )
    parser.add_argument(
        "--min-rows",
        type=int,
        default=30,
        help=(
            "Minimum number of rows a converted CSV must have to be included. "
            "Series shorter than this are silently skipped (default: 30)."
        ),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite destination files and regenerate input files.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned actions without writing files.",
    )
    parser.add_argument(
        "--no-clamp",
        action="store_true",
        help="Do not clamp aggregated values to [0,100] (needed for absolute-rate "
             "columns like membw_est/psp in the 15-metric Approach B traces).",
    )
    return parser.parse_args()


def parse_rep_pattern_map(raw: str) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        if "=" not in token:
            raise SystemExit(f"Invalid --rep-pattern-map token: {token}")
        rep, pattern = token.split("=", 1)
        rep = rep.strip()
        pattern = pattern.strip()
        if not rep or not pattern:
            raise SystemExit(f"Invalid --rep-pattern-map token: {token}")
        mapping[rep] = pattern
    if not mapping:
        raise SystemExit("--rep-pattern-map resolved to an empty mapping.")
    return mapping


def read_manifest(path: Path) -> list[ManifestRow]:
    if not path.exists():
        raise SystemExit(f"Manifest not found: {path}")

    rows: list[ManifestRow] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        required = {"env", "variant", "stage", "workload", "rep", "rows", "source", "output"}
        if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
            raise SystemExit(
                f"Manifest missing required columns. Expected: {sorted(required)}; got: {reader.fieldnames}"
            )

        for row in reader:
            rows.append(
                ManifestRow(
                    env=row["env"].strip(),
                    variant=row["variant"].strip(),
                    stage=row["stage"].strip(),
                    workload=row["workload"].strip(),
                    rep=row["rep"].strip(),
                    rows=int(row["rows"]),
                    source=Path(row["source"].strip()),
                    output=Path(row["output"].strip()),
                )
            )
    return rows


def select_rows(
    rows: list[ManifestRow],
    env_filter: list[str],
    variant_filter: list[str],
    stage_filter: list[str],
    workload_regex: str,
    rep_to_pattern: dict[str, str],
    min_rows: int = 30,
) -> list[tuple[ManifestRow, str]]:
    env_set = {item.strip() for item in env_filter if item.strip()}
    variant_set = {item.strip() for item in variant_filter if item.strip()}
    stage_set = {item.strip() for item in stage_filter if item.strip()}
    workload_re = re.compile(workload_regex)

    selected: list[tuple[ManifestRow, str]] = []
    skipped_short: list[str] = []
    for row in rows:
        if env_set and row.env not in env_set:
            continue
        if variant_set and row.variant not in variant_set:
            continue
        if stage_set and row.stage not in stage_set:
            continue
        if not workload_re.search(row.workload):
            continue

        pattern = rep_to_pattern.get(row.rep)
        if pattern is None:
            continue
        if row.rows < min_rows:
            skipped_short.append(
                f"{row.env}/{row.variant}/{row.stage}/{row.workload}/{row.rep} "
                f"({row.rows} rows < min {min_rows})"
            )
            continue
        selected.append((row, pattern))

    if skipped_short:
        import sys
        print(
            f"WARNING: skipped {len(skipped_short)} series below --min-rows={min_rows}:",
            file=sys.stderr,
        )
        for msg in skipped_short:
            print(f"  {msg}", file=sys.stderr)

    return selected


def sanitize_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", value)


def build_destinations(
    rows_with_patterns: list[tuple[ManifestRow, str]],
    out_root: Path,
) -> dict[tuple[str, str], list[LinkedFile]]:
    grouped: dict[tuple[str, str], dict[Path, LinkedFile]] = {}

    for row, pattern in rows_with_patterns:
        key = (row.env, row.variant)
        dest_dir = out_root / sanitize_name(row.env) / sanitize_name(row.variant) / "source" / sanitize_name(row.workload)
        dest = dest_dir / f"{sanitize_name(pattern)}.csv"

        env_group = grouped.setdefault(key, {})
        entry = env_group.get(dest)
        if entry is None:
            env_group[dest] = LinkedFile(rows=[row], pattern=pattern, destination=dest)
            continue

        entry.rows.append(row)

    out: dict[tuple[str, str], list[LinkedFile]] = {}
    for key, by_dest in grouped.items():
        out[key] = list(by_dest.values())
    return out


def rep_sort_key(value: str) -> tuple[int, str]:
    match = re.search(r"(\d+)$", value)
    if match is None:
        return (10**9, value)
    return (int(match.group(1)), value)


def validate_no_collisions(grouped: dict[tuple[str, str], list[LinkedFile]]) -> None:
    for links in grouped.values():
        for link in links:
            if len(link.rows) <= 1:
                continue
            reps = ",".join(row.rep for row in sorted(link.rows, key=lambda item: rep_sort_key(item.rep)))
            raise SystemExit(
                "Destination collision detected. Check filters and rep-pattern map. "
                f"Conflicting destination: {link.destination} (reps={reps})"
            )


def read_meyer_csv(path: Path) -> list[list[int]]:
    rows: list[list[int]] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle, delimiter=";")
        for line_no, fields in enumerate(reader, start=1):
            if not fields:
                continue
            if len(fields) not in (7, 15):
                raise SystemExit(f"Expected 7 (T1/A) or 15 (B) columns in {path}:{line_no}, got {len(fields)}")
            try:
                values = [int(float(field)) for field in fields]
            except ValueError as exc:
                raise SystemExit(f"Invalid numeric value in {path}:{line_no}") from exc
            rows.append(values)

    if not rows:
        raise SystemExit(f"Converted CSV has no rows: {path}")
    return rows


CLAMP = True  # clamp aggregated values to [0,100]; disabled (--no-clamp) for B


def clamp_percent(value: int) -> int:
    if not CLAMP:
        return value
    if value < 0:
        return 0
    if value > 100:
        return 100
    return value


def aggregate_metric(values: list[int], method: str) -> int:
    if method == "mean":
        return clamp_percent(round(sum(values) / len(values)))
    if method == "median":
        return clamp_percent(round(median(values)))
    raise SystemExit(f"Unsupported aggregate method: {method}")


def write_meyer_csv(path: Path, rows: list[list[int]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter=";", lineterminator="\n")
        writer.writerows(rows)


def materialize_aggregated(link: LinkedFile, method: str, force: bool, dry_run: bool) -> None:
    src_paths = [row.output.resolve() for row in sorted(link.rows, key=lambda item: rep_sort_key(item.rep))]
    for src in src_paths:
        if not src.exists():
            raise SystemExit(f"Converted CSV listed in manifest not found: {src}")

    dst = link.destination
    if dst.exists() or dst.is_symlink():
        if not force:
            raise SystemExit(f"Destination already exists (use --force): {dst}")
        if not dry_run:
            dst.unlink()

    if dry_run:
        return

    series = [read_meyer_csv(src) for src in src_paths]
    min_rows = min(len(rows) for rows in series)
    max_rows = max(len(rows) for rows in series)
    if min_rows != max_rows:
        reps = ",".join(row.rep for row in sorted(link.rows, key=lambda item: rep_sort_key(item.rep)))
        print(
            f"warning: row-count mismatch for {dst} reps={reps}; "
            f"truncating to {min_rows} rows"
        )

    merged: list[list[int]] = []
    for idx in range(min_rows):
        merged.append(
            [
                aggregate_metric([trace[idx][metric_idx] for trace in series], method)
                for metric_idx in range(7)
            ]
        )
    write_meyer_csv(dst, merged)

def materialize_link(link: LinkedFile, mode: str, force: bool, dry_run: bool, pattern_merge: str) -> None:
    ordered_rows = sorted(link.rows, key=lambda item: rep_sort_key(item.rep))
    src = ordered_rows[0].output.resolve()
    if not src.exists():
        raise SystemExit(f"Converted CSV listed in manifest not found: {src}")

    if len(ordered_rows) > 1 and pattern_merge in ("mean", "median"):
        materialize_aggregated(link, method=pattern_merge, force=force, dry_run=dry_run)
        return

    dst = link.destination
    if dst.exists() or dst.is_symlink():
        if not force:
            raise SystemExit(f"Destination already exists (use --force): {dst}")
        if not dry_run:
            dst.unlink()

    if dry_run:
        return

    dst.parent.mkdir(parents=True, exist_ok=True)
    if mode == "copy":
        shutil.copy2(src, dst)
    else:
        dst.symlink_to(src)


def write_cloudsim_input(
    key: tuple[str, str],
    links: list[LinkedFile],
    out_root: Path,
    pm_count: int,
    pm_size: int,
    force: bool,
    dry_run: bool,
) -> Path:
    env, variant = key
    input_path = out_root / sanitize_name(env) / sanitize_name(variant) / "cloudsim-input.txt"

    if (input_path.exists() or input_path.is_symlink()) and not force:
        raise SystemExit(f"CloudSim input already exists (use --force): {input_path}")

    lines = ["Datacenter file configuration"]
    for link in sorted(links, key=lambda item: (item.rows[0].workload, item.pattern)):
        lines.append(f"app 1 {link.destination.resolve()}")
    lines.append(f"pm {pm_count} {pm_size}")

    if not dry_run:
        input_path.parent.mkdir(parents=True, exist_ok=True)
        with input_path.open("w", encoding="utf-8", newline="") as handle:
            handle.write("\n".join(lines) + "\n")

    return input_path


def write_tree_manifest(
    key: tuple[str, str], links: list[LinkedFile], out_root: Path, dry_run: bool
) -> Path:
    env, variant = key
    manifest_path = out_root / sanitize_name(env) / sanitize_name(variant) / "tree-manifest.tsv"

    if dry_run:
        return manifest_path

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["env", "variant", "stage", "workload", "rep", "pattern", "source", "destination"])
        for link in sorted(links, key=lambda item: (item.rows[0].workload, item.pattern)):
            ordered_rows = sorted(link.rows, key=lambda item: rep_sort_key(item.rep))
            writer.writerow(
                [
                    ordered_rows[0].env,
                    ordered_rows[0].variant,
                    ordered_rows[0].stage,
                    ordered_rows[0].workload,
                    ",".join(row.rep for row in ordered_rows),
                    link.pattern,
                    ",".join(str(row.output.resolve()) for row in ordered_rows),
                    str(link.destination.resolve()),
                ]
            )
    return manifest_path


def main() -> int:
    args = parse_args()
    global CLAMP
    if args.no_clamp:
        CLAMP = False
    rep_to_pattern = parse_rep_pattern_map(args.rep_pattern_map)
    manifest_rows = read_manifest(args.manifest)

    selected = select_rows(
        rows=manifest_rows,
        env_filter=args.env,
        variant_filter=args.variant,
        stage_filter=args.stage,
        workload_regex=args.workload_regex,
        rep_to_pattern=rep_to_pattern,
        min_rows=args.min_rows,
    )
    if not selected:
        raise SystemExit("No manifest rows matched the filters and repetition-pattern mapping.")

    grouped = build_destinations(selected, args.out_root)
    if args.pattern_merge == "error":
        validate_no_collisions(grouped)

    total_files = 0
    merged_outputs = 0
    for key, links in sorted(grouped.items(), key=lambda item: item[0]):
        for link in links:
            materialize_link(link, args.mode, args.force, args.dry_run, args.pattern_merge)
            total_files += 1
            if len(link.rows) > 1:
                merged_outputs += 1

        cloudsim_input = write_cloudsim_input(
            key=key,
            links=links,
            out_root=args.out_root,
            pm_count=args.pm_count,
            pm_size=args.pm_size,
            force=args.force,
            dry_run=args.dry_run,
        )
        tree_manifest = write_tree_manifest(key=key, links=links, out_root=args.out_root, dry_run=args.dry_run)

        env, variant = key
        print(
            f"[{env}/{variant}] files={len(links)} merged={sum(1 for link in links if len(link.rows) > 1)} "
            f"cloudsim_input={cloudsim_input} tree_manifest={tree_manifest}"
        )

    print(
        f"prepared {total_files} canonical CSV file(s) across {len(grouped)} env+variant group(s) "
        f"(merged destinations={merged_outputs}, pattern_merge={args.pattern_merge})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
#!/usr/bin/env python3
"""plot-jdk-ab.py -- does rebuilding CloudSim under JDK 17 move the IDI results?

The banked IADA numbers were produced by the Eclipse JDT build that shipped in
``bin/`` (class major 52, i.e. a Java 8 target). Reproducing the campaign from
source uses ``javac`` from JDK 17 and therefore emits major 61. Both builds
compile the *same* recovered sources and run on the *same* JVM, so any
difference in the results would have to come from the bytecode target alone --
which is exactly the kind of thing that is cheap to assume and expensive to be
wrong about, since every downstream figure inherits it.

This renderer answers it as an EQUIVALENCE question rather than a difference
one. The scheduler is a stochastic SA search, so two legs never produce
identical numbers and "the means differ" is uninformative on its own. What
matters is whether the difference is small relative to rep-to-rep noise, so the
delta panel plots the difference with a bootstrap CI against a zero line: an
interval that straddles zero says the rebuild is indistinguishable from the
banked build at this rep count.

Colour follows the TIER, matching the rest of the P2 set (plot-iada-sim.py), and
the build is carried by texture rather than a second hue, so the reader's
existing T1/A/B colour mapping keeps working. Bars carry direct value labels:
the tier-B green sits at 2.8:1 against the figure surface, below the 3:1 mark,
so the numbers are not allowed to be colour-only.

    python3 bench/plot/plot-jdk-ab.py --ab-dir <dir> [--out-set p2-jdk-ab]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parent))
import p2_ci                      # noqa: E402  rep-level bootstrap CI
import fig_names  # noqa: E402  (figure naming registry)
import p2_figio                   # noqa: E402  {png,pdf} output layout
import paper_style                # noqa: E402  camera-ready typography
import jsa_style                  # noqa: E402  JSA manuscript typography

TIER_LABEL = {"T1": "canonical-7", "A": "proxy-swap", "B": "full-fingerprint"}

# Tier colours are the P2 set's existing mapping (bench/plot/plot-iada-sim.py:37).
COLOR = {"T1": "#c0392b", "A": "#2980b9", "B": "#27ae60"}
TIERS = ["T1", "A", "B"]

# The build is a secondary encoding on top of the tier hue: solid fill for the
# banked artefacts, hatched for the rebuild.
BUILD_LABEL = {"java8": "banked build (Java 8 target)",
               "jdk17": "rebuilt from source (JDK 17)"}
BUILD_HATCH = {"java8": "", "jdk17": "///"}

# Depths the campaign was asked for. 10 reps is the campaign; the first 5 are
# the control leg, kept as a subset so both depths come from one run. None
# means "every rep available" -- with --confirm-dir the T1 legs gain the
# 20-rep confirmation batch, and that pooled sample is what settled the
# question, so it gets its own row rather than being truncated to 10.
DEPTHS = [5, 10, None]


def load_leg(path: Path, leg: str) -> pd.DataFrame:
    df = pd.read_csv(path, sep="\t")
    # Failed reps are written as a short row with the literal FAIL in idi_avg.
    df = df[pd.to_numeric(df["idi_avg"], errors="coerce").notna()].copy()
    df["idi_avg"] = df["idi_avg"].astype(float)
    df["build"] = leg
    return df


def diff_ci(a, b, seed_offset: int = 0, n: int = p2_ci.BOOTSTRAP_N):
    """Bootstrap CI for mean(b) - mean(a) with the two legs resampled apart.

    The legs are independent runs -- rep 3 of one build has no correspondence
    with rep 3 of the other -- so this resamples each group separately rather
    than pairing them. Percentile bounds and the seed convention follow p2_ci.
    """
    a = np.asarray(a, dtype=float); b = np.asarray(b, dtype=float)
    a = a[~np.isnan(a)]; b = b[~np.isnan(b)]
    point = float(b.mean() - a.mean())
    if a.size < 2 or b.size < 2:
        return point, point, point
    rng = np.random.default_rng(p2_ci.BOOTSTRAP_SEED + seed_offset)
    ra = rng.choice(a, size=(n, a.size), replace=True).mean(axis=1)
    rb = rng.choice(b, size=(n, b.size), replace=True).mean(axis=1)
    lo, hi = np.nanpercentile(rb - ra, list(p2_ci.CI_PCTILES))
    return point, float(lo), float(hi)


def fig_levels(rows, banked, outdir, equivalent: bool):
    """Per-tier IDI for both builds, with the banked campaign as a reference."""
    fig, ax = plt.subplots(figsize=(paper_style.COLUMN_WIDTH, 1.95))
    width, gap = 0.34, 0.03

    for ti, tier in enumerate(TIERS):
        for bi, leg in enumerate(("java8", "jdk17")):
            # Deepest sample available for this tier = the verdict numbers.
            r = rows.get((tier, leg, None), rows[(tier, leg, 10)])
            # 2 px of surface between the paired bars, per the set's mark specs.
            x = ti + (bi - 0.5) * (width + gap)
            ax.bar(x, r["mean"], width, color=COLOR[tier],
                   hatch=BUILD_HATCH[leg], edgecolor="white", linewidth=0.6,
                   alpha=1.0 if leg == "java8" else 0.85, zorder=2)
            ax.errorbar(x, r["mean"], yerr=[[r["mean"] - r["lo"]], [r["hi"] - r["mean"]]],
                        fmt="none", ecolor="#333333", elinewidth=0.7, capsize=1.8, zorder=4)
            # Per-rep points: the reader sees the sample the CI is built from.
            ax.scatter(np.full(len(r["vals"]), x), r["vals"], s=2.0,
                       color="#333333", alpha=0.45, linewidths=0, zorder=5)
            ax.text(x, r["hi"] + 260, f"{r['mean']:.0f}", ha="center", va="bottom",
                    fontsize=paper_style.ANNOT, color="#222222")

        if tier in banked:
            # Dashed rule = the 5-rep result already in the repository.
            ax.plot([ti - 0.5, ti + 0.5], [banked[tier]] * 2, ls=(0, (2.5, 1.5)),
                    lw=0.8, color="#444444", zorder=6)

    ax.set_xticks(range(len(TIERS)))
    ax.set_xticklabels([f"tier {t}" for t in TIERS])
    ax.set_ylabel("interference degradation index")
    # The title states the outcome, so it has to be derived from it rather than
    # written in advance -- a hardcoded "unchanged" would keep claiming that on
    # the run where it stops being true.
    ax.set_title("Rebuilding under JDK 17 leaves the degradation index unchanged"
                 if equivalent else
                 "Rebuilding under JDK 17 shifts the degradation index", pad=3)
    ax.set_ylim(0, max(r["hi"] for r in rows.values()) * 1.16)
    ax.margins(x=0.06)

    handles = [plt.Rectangle((0, 0), 1, 1, facecolor="#9a9a9a", edgecolor="white",
                             linewidth=0.6, hatch=BUILD_HATCH[l], label=BUILD_LABEL[l])
               for l in ("java8", "jdk17")]
    handles.append(plt.Line2D([0], [0], ls=(0, (2.5, 1.5)), lw=0.8, color="#444444",
                              label="banked 5-rep campaign"))
    ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, -0.22),
              ncol=2, handlelength=1.6, columnspacing=1.0, borderpad=0.2)

    paper_style.apply()
    p2_figio.save(fig, outdir, "F-jdk-ab-idi")
    print(p2_figio.describe(outdir, "F-jdk-ab-idi"))
    plt.close(fig)


def fig_delta(deltas, outdir):
    """Rebuild minus banked build, with the interval that decides equivalence."""
    fig, ax = plt.subplots(figsize=(paper_style.COLUMN_WIDTH, 1.75))
    # Zero first, so the marks read against it rather than over it.
    ax.axvline(0, color="#444444", lw=0.8, zorder=1)

    ypos, ylabels = [], []
    # Top-to-bottom T1, A, B so the rows track the bar panel's left-to-right order.
    for ti, tier in enumerate(reversed(TIERS)):
        tier_rows = [(dep, deltas[(tier, dep)]) for dep in DEPTHS
                     if (tier, dep) in deltas]
        for di, (depth, d) in enumerate(tier_rows):
            final = di == len(tier_rows) - 1  # deepest sample = the verdict row
            y = ti * 2.3 + (len(tier_rows) - 1 - di) * 0.72
            ypos.append(y)
            ylabels.append(f"all ({d['n']})" if depth is None else f"{depth} reps")
            ax.plot([d["lo"], d["hi"]], [y, y], lw=1.3, color=COLOR[tier],
                    solid_capstyle="round", alpha=1.0 if final else 0.55, zorder=3)
            ax.scatter([d["point"]], [y], s=13 if final else 9,
                       color=COLOR[tier], edgecolor="white", linewidth=0.6,
                       zorder=4, alpha=1.0 if final else 0.75)
            ax.text(d["hi"], y + 0.30, f"{d['point']:+.0f}", ha="right", va="bottom",
                    fontsize=paper_style.ANNOT, color="#222222")

    ax.set_yticks(ypos); ax.set_yticklabels(ylabels)
    # Tier tag sits outboard of the "N reps" ticks, which are the widest labels
    # on this axis -- at -0.145 it landed on top of them.
    for ti, tier in enumerate(reversed(TIERS)):
        ax.text(-0.30, ti * 2.3 + 0.36, f"tier {tier}", transform=
                ax.get_yaxis_transform(), ha="left", va="center",
                fontsize=paper_style.BODY, color=COLOR[tier])
    ax.set_xlabel("difference in degradation index  (rebuild − banked build)")
    # The verdict row per tier is the DEEPEST sample: shallower rows stay
    # visible so the reader can see an excursion that did not survive pooling
    # (T1's 10-rep +204 is exactly that), but they do not set the title.
    finals = {}
    for (tier, dep), d in deltas.items():
        cur = finals.get(tier)
        key = float("inf") if dep is None else dep
        if cur is None or key > cur[0]:
            finals[tier] = (key, d)
    n_excl = sum(1 for _, d in finals.values() if not d["covers_zero"])
    ax.set_title("The deepest interval per tier covers zero: the builds agree"
                 if n_excl == 0 else
                 f"{n_excl} of {len(finals)} tiers differ at full depth",
                 pad=3)
    ax.set_ylim(-0.7, (len(TIERS) - 1) * 2.3 + 2.1)
    ax.grid(axis="y", visible=False)

    paper_style.apply()
    p2_figio.save(fig, outdir, "F-jdk-ab-delta")
    print(p2_figio.describe(outdir, "F-jdk-ab-delta"))
    plt.close(fig)


def jsa_delta(deltas, out_path: Path) -> None:
    """Figure_A2 for the JSA manuscript (fig:a2): fig_delta's own interval
    computation, JSA geometry, no in-figure title (the caption already
    states the equivalence verdict), tier codenames spelled out."""
    jsa_style.apply()
    width, height = jsa_style.COLUMN_WIDTH * 1.55, 2.75
    fig, ax = plt.subplots(figsize=(width, height), layout="constrained")
    ax.axvline(0, color="#444444", lw=0.8, zorder=1)

    ypos, ylabels = [], []
    for ti, tier in enumerate(reversed(TIERS)):
        tier_rows = [(dep, deltas[(tier, dep)]) for dep in DEPTHS
                     if (tier, dep) in deltas]
        for di, (depth, d) in enumerate(tier_rows):
            final = di == len(tier_rows) - 1
            y = ti * 2.3 + (len(tier_rows) - 1 - di) * 0.72
            ypos.append(y)
            ylabels.append(f"all ({d['n']})" if depth is None else f"{depth} reps")
            ax.plot([d["lo"], d["hi"]], [y, y], lw=1.3, color=COLOR[tier],
                    solid_capstyle="round", alpha=1.0 if final else 0.55,
                    zorder=3)
            ax.scatter([d["point"]], [y], s=13 if final else 9,
                       color=COLOR[tier], edgecolor="white", linewidth=0.6,
                       zorder=4, alpha=1.0 if final else 0.75)
            ax.text(d["hi"], y + 0.30, f"{d['point']:+.0f}", ha="right",
                    va="bottom", fontsize=jsa_style.ANNOT, color="#222222")

    ax.set_yticks(ypos)
    ax.set_yticklabels(ylabels, fontsize=jsa_style.BODY)
    for ti, tier in enumerate(reversed(TIERS)):
        ax.text(-0.32, ti * 2.3 + 0.36, TIER_LABEL[tier], transform=
                ax.get_yaxis_transform(), ha="left", va="center",
                fontsize=jsa_style.BODY, color=COLOR[tier])
    ax.set_xlabel("difference in degradation index (rebuild − banked build)")
    ax.set_ylim(-0.7, (len(TIERS) - 1) * 2.3 + 2.1)
    ax.grid(axis="y", visible=False)

    spec = jsa_style.FigSpec(width, height, "fig:a2")
    w, h = jsa_style.save(fig, out_path, spec)
    plt.close(fig)
    print(f"wrote {out_path} ({w:.2f} x {h:.2f} in)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ab-dir", required=True, type=Path,
                    help="directory holding reps-java8.tsv and reps-jdk17.tsv")
    ap.add_argument("--confirm-dir", type=Path, default=None,
                    help="directory holding confirm-<tier>-<leg>.tsv batches "
                         "to pool into the matching leg (defaults to --ab-dir)")
    ap.add_argument("--banked", type=Path,
                    default=Path("results/iada-sim/tier-sim-reps.tsv"))
    ap.add_argument("--out-set", default="p2-jdk-ab")
    ap.add_argument("--figures-root", type=Path, default=Path("results/figures"))
    ap.add_argument("--jsa", default=None,
                    help="also render fig:a2 for the JSA manuscript to this "
                         "exact PDF path (Figure_A2.pdf)")
    fig_names.add_dataset_arg(ap)
    args = ap.parse_args()
    p2_figio.set_dataset(args.dataset or fig_names.dataset_tag(args.ab_dir))

    confirm_dir = args.confirm_dir or args.ab_dir
    legs = {}
    for leg in ("java8", "jdk17"):
        p = args.ab_dir / f"reps-{leg}.tsv"
        if not p.exists():
            print(f"missing {p}", file=sys.stderr); return 1
        frames = [load_leg(p, leg)]
        # Confirmation batches are independent same-config reps, so pooling is
        # legitimate; renumber them past the first-pass reps so head(depth)
        # keeps selecting the original batch for the fixed-depth rows.
        for cf in sorted(confirm_dir.glob(f"confirm-*-{leg}.tsv")):
            extra = load_leg(cf, leg)
            base = frames[0]["rep"].max()
            extra["rep"] = extra["rep"] + base
            frames.append(extra)
        legs[leg] = pd.concat(frames, ignore_index=True)

    # Keep the banked REPS, not just their mean: the banked figure is itself 5
    # noisy samples, so "is the rerun consistent with it" is a two-sample
    # question. Testing the banked mean for membership in the rerun's interval
    # would treat 5 reps as ground truth and call ordinary noise a regression.
    banked, banked_reps = {}, {}
    if args.banked.exists():
        b = pd.read_csv(args.banked, sep="\t")
        b = b[pd.to_numeric(b["idi_avg"], errors="coerce").notna()]
        b = b.astype({"idi_avg": float})
        banked = b.groupby("tier")["idi_avg"].mean().to_dict()
        banked_reps = {t: g["idi_avg"].to_numpy() for t, g in b.groupby("tier")}

    # ---- aggregate -------------------------------------------------------
    rows, deltas, table = {}, {}, []
    for ti, tier in enumerate(TIERS):
        # Drop the "all reps" row for tiers with no confirmation batch -- it
        # would duplicate the 10-rep row exactly.
        n_all = min(len(legs[l][legs[l]["tier"] == tier]) for l in ("java8", "jdk17"))
        tier_depths = [d for d in DEPTHS if d is not None or n_all > max(
            d2 for d2 in DEPTHS if d2 is not None)]
        for depth in tier_depths:
            per_leg = {}
            for bi, leg in enumerate(("java8", "jdk17")):
                q = legs[leg].query("tier == @tier").sort_values("rep")
                v = (q["idi_avg"] if depth is None else
                     q["idi_avg"].head(depth)).to_numpy()
                mean, lo, hi = p2_ci.rep_ci(v, seed_offset=ti * 10 + bi)
                per_leg[leg] = v
                rows[(tier, leg, depth)] = {"mean": mean, "lo": lo, "hi": hi,
                                            "vals": v, "n": len(v)}
                # Migrations is the scheduler's own behaviour rather than the
                # cost it optimises, so a build difference could show up here
                # even with the index unmoved. Text-only: it does not need a
                # panel, but it should not go unlooked-at either.
                mig = (q["migrations"] if depth is None else
                       q["migrations"].head(depth)).astype(float).to_numpy()
                table.append({"tier": tier, "build": leg,
                              "depth": "all" if depth is None else depth,
                              "reps": len(v),
                              "idi_mean": round(mean, 2), "ci_lo": round(lo, 2),
                              "ci_hi": round(hi, 2),
                              "sd": round(float(np.std(v, ddof=1)), 2) if len(v) > 1 else float("nan"),
                              "migrations_mean": round(float(mig.mean()), 2) if mig.size else float("nan")})
            point, lo, hi = diff_ci(per_leg["java8"], per_leg["jdk17"],
                                    seed_offset=100 + ti * 10 +
                                    (99 if depth is None else depth))
            # Equivalent = the interval cannot exclude zero.
            deltas[(tier, depth)] = {"point": point, "lo": lo, "hi": hi,
                                     "n": min(len(per_leg["java8"]),
                                              len(per_leg["jdk17"])),
                                     "covers_zero": lo <= 0 <= hi}

    outdir = args.figures_root / args.out_set
    outdir.mkdir(parents=True, exist_ok=True)

    # The green tier sits under 3:1 on the figure surface, so the numbers must
    # also exist as text somewhere -- this is that table view, not a nicety.
    tdf = pd.DataFrame(table)
    tdf.to_csv(outdir / "summary.tsv", sep="\t", index=False)
    ddf = pd.DataFrame([{"tier": t, "depth": "all" if d is None else d,
                         **{k: (round(v, 2) if isinstance(v, float) else v)
                            for k, v in deltas[(t, d)].items()}}
                        for t in TIERS for d in DEPTHS if (t, d) in deltas])
    ddf.to_csv(outdir / "delta.tsv", sep="\t", index=False)

    paper_style.apply()
    # Verdict from the deepest sample per tier (see fig_delta).
    deepest = {}
    for (t, dep), d in deltas.items():
        key = float("inf") if dep is None else dep
        if t not in deepest or key > deepest[t][0]:
            deepest[t] = (key, d)
    equivalent = all(d["covers_zero"] for _, d in deepest.values())
    fig_levels(rows, banked, outdir, equivalent)
    fig_delta(deltas, outdir)
    if args.jsa:
        jsa_delta(deltas, Path(args.jsa))

    print("\n== per-build IDI ==");  print(tdf.to_string(index=False))
    print("\n== rebuild - banked build =="); print(ddf.to_string(index=False))
    if banked_reps:
        print("\n== rerun (banked build) - banked campaign ==")
        for ti, tier in enumerate(TIERS):
            if tier not in banked_reps:
                continue
            r = rows.get((tier, "java8", None), rows[(tier, "java8", 10)])
            point, lo, hi = diff_ci(banked_reps[tier], r["vals"], seed_offset=200 + ti)
            print(f"  {tier}: banked {banked[tier]:8.1f} (n={len(banked_reps[tier])}) | "
                  f"rerun {r['mean']:8.1f} (n={r['n']}) | diff {point:+8.1f} "
                  f"[{lo:+.1f}, {hi:+.1f}] "
                  f"{'consistent' if lo <= 0 <= hi else 'DIFFERS'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

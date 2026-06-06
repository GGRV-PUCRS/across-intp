#!/usr/bin/env python3
"""analyze-cross-deployment.py -- Paper-2 cross-deployment paired-delta report.

The fused Track-A+B headline (DECISIONS C25/C26/C27): operationalizes the advisor
frame "measure the same application on bare metal, then on container/VM" as paired
per-(workload, metric, variant) deltas against the BARE baseline, across the full
deployment axis (bare -> docker -> podman -> incus -> k3s -> vm-guest), over the
13-metric superset (7 canonical + 6 VM-portable) captured by one --portable-metrics
campaign. This is the cross-deployment analogue of Volpert et al.'s relative
degradation D = C_i / C_bare.

The statistic is CLAIM-CLASS-GATED (bench/intp_metrics.py CLAIM_CLASS):
  absolute    (cpu)            -> log-ratio overhead vs bare + bootstrap CI; the
                                  W4 ratio band 0.8-1.25 flags faithful/over/under.
  directional (llcmr, schedlat)-> delta + effect size reported, but stamped
                                  RANK-ONLY: never an absolute-overhead claim.
  descriptive (the other 10)   -> median+IQR delta vs bare + effect size, stamped
                                  descriptive (no faithfulness claim).
Every env-vs-bare pair gets a Mann-Whitney U p-value (BH-FDR-adjusted across the
env family per workload/metric) + Cliff's delta effect size. Env-validity guard
(GT cpu on the cpu workload) excludes envs that never loaded the host.

Sibling tools: analyze-faithfulness.py (solo metric-vs-GT faithfulness),
analyze-portable.py (portable-vs-GT + the PSI bandwidth-blindness falsification),
plot/plot-cross-environment.py (symmetric all-pairs omnibus + boxplots). This tool
adds the missing BARE-BASELINE paired delta -- the Paper-2 table generator.

Usage:  python3 bench/analyze-cross-deployment.py results/<campaign> [--out report.md]
                 [--stage solo] [--variants v2.1,v3.3] [--tsv cross-deployment.tsv]
"""
import argparse
import glob
import os
import statistics
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import intp_metrics as M  # noqa: E402

try:
    from scipy.stats import mannwhitneyu
    HAVE_SCIPY = True
except Exception:
    HAVE_SCIPY = False

BARE = "bare"


def _mw_p(a, b):
    a = [x for x in a if x is not None]
    b = [x for x in b if x is not None]
    if not (HAVE_SCIPY and len(a) >= 2 and len(b) >= 2 and len(set(a) | set(b)) > 1):
        return None
    try:
        return float(mannwhitneyu(a, b, alternative="two-sided").pvalue)
    except Exception:
        return None


def _bootstrap_ratio_ci(env, bare, n=2000, seed=0):
    """Percentile bootstrap CI for median(env)/median(bare) -- the SAME statistic
    as the displayed point ratio, so the CI brackets it and agrees with the band
    tag. Seeded for reproducibility. Returns (lo, hi) or (None, None)."""
    import random
    env = [x for x in env if x is not None]
    bare = [x for x in bare if x is not None]
    if not env or not bare:
        return (None, None)
    rng = random.Random(seed)
    ratios = []
    for _ in range(n):
        e = statistics.median(rng.choices(env, k=len(env)))
        b = statistics.median(rng.choices(bare, k=len(bare)))
        if b > 0:
            ratios.append(e / b)
    if not ratios:
        return (None, None)
    ratios.sort()
    return (ratios[int(0.025 * len(ratios))], ratios[min(len(ratios) - 1, int(0.975 * len(ratios)))])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("campaign_dir")
    ap.add_argument("--out", default=None)
    ap.add_argument("--tsv", default=None, help="machine-readable rows (default <campaign>/cross-deployment.tsv)")
    ap.add_argument("--stage", default="solo")
    ap.add_argument("--variants", default=None, help="CSV; default v2.1,v3.3")
    args = ap.parse_args()
    base = args.campaign_dir.rstrip("/")
    variants = args.variants.split(",") if args.variants else list(M.VARIANTS)
    tsv_path = args.tsv or os.path.join(base, "cross-deployment.tsv")

    # cell[(env,var,wl)] -> [rep_summary, ...]
    cell = defaultdict(list)
    for env in M.ENVS:
        for var in variants:
            for wl in M.WORKLOAD:
                for rep in sorted(glob.glob(f"{base}/{env}/{var}/{args.stage}/{wl}/rep*")):
                    cell[(env, var, wl)].append(M.rep_summary(rep))

    def vals(env, var, wl, key):
        return [s.get(key) for s in cell[(env, var, wl)] if s.get(key) is not None]

    if not any(cell.values()):
        msg = (f"no data under {base} (expected "
               f"{base}/<env>/<variant>/{args.stage}/<workload>/rep*/[portable|profiler].tsv)")
        print(f"# Cross-deployment paired-delta — {base}\n\n**{msg}**")
        if args.out:
            open(args.out, "w").write(f"# Cross-deployment — {msg}\n")
        return

    envs_present = M.order_envs({e for (e, v, w) in cell if cell[(e, v, w)]})
    wls_present = [w for w in M.WORKLOAD if any(cell[(e, v, w)] for e in envs_present for v in variants)]
    invalid = M.env_validity(envs_present, variants, M.CPU_WL, vals)
    good = [e for e in envs_present if e not in invalid]
    # which of the 13 metrics actually have any data (so a canonical-only campaign
    # doesn't print 6 empty portable columns, and vice-versa)
    metrics_present = [m for m in M.METRICS_ALL
                       if any(vals(e, v, w, m) for e in envs_present for v in variants for w in wls_present)]

    L = []
    def em(s=""):
        L.append(s)

    em(f"# Cross-deployment paired-delta (vs bare) — {base}")
    em("")
    em(f"Deployment axis: {' -> '.join(envs_present)}. Variants: {', '.join(variants)}. "
       f"Stage: {args.stage}. Metrics with data: {len(metrics_present)}/13. "
       f"scipy: {'yes' if HAVE_SCIPY else 'NO (MW p skipped; bootstrap CI still computed)'}.")
    em("")
    em("Statistic is claim-class-gated (intp_metrics.CLAIM_CLASS): **absolute** = ratio vs bare "
       f"+ bootstrap CI, W4 band {M.RATIO_LO}-{M.RATIO_HI}; **directional** = delta + effect size, "
       "RANK-ONLY (no absolute-overhead claim); **descriptive** = median+IQR delta vs bare. Every "
       "env-vs-bare pair carries Mann-Whitney U p (BH-FDR across the env family) + Cliff's delta.")
    if invalid:
        em("")
        parts = [f"{e} (no app10 GT)" if g is None else f"{e} (GT cpu={M._fmt(g)}% < {M.INVALID_CPU_PCT})"
                 for e, g in invalid.items()]
        em("**INVALID envs (host never loaded; excluded):** " + ", ".join(parts))
    if BARE not in good:
        em("")
        em(f"**WARNING: `{BARE}` baseline absent/invalid — paired deltas vs bare cannot be computed.**")
    em("")

    tsv_rows = [("variant", "workload", "metric", "claim_class", "env",
                 "bare_median", "env_median", "delta", "ratio", "ci_lo", "ci_hi",
                 "cliffs_delta", "cliffs_mag", "mw_p", "mw_q_bh", "signif")]

    nonbare = [e for e in good if e != BARE]

    # ---- §1 Overhead (absolute metrics) ----------------------------------------
    abs_metrics = [m for m in metrics_present if M.CLAIM_CLASS.get(m) == "absolute"]
    em("## §1 Overhead vs bare — ABSOLUTE metrics (ratio + bootstrap CI)")
    em("")
    if not abs_metrics:
        em("_no absolute-class metric with data._")
    for var in variants:
        for m in abs_metrics:
            em(f"### {var} — {m}")
            em("")
            em("| workload | bare | " + " | ".join(f"{e}" for e in nonbare) + " |")
            em("|" + "---|" * (len(nonbare) + 2))
            for wl in wls_present:
                bare_reps = vals(BARE, var, wl, m)
                bm = M._median(bare_reps)
                # BH-adjust the env-family MW p-values (mirrors §2/§3 so the
                # absolute metric carries the FDR discipline the header promises).
                raw_p = {e: _mw_p(vals(e, var, wl, m), bare_reps) for e in nonbare}
                keys = [e for e in nonbare if raw_p[e] is not None]
                q = M.bh_adjust([raw_p[e] for e in keys])
                qmap = dict(zip(keys, q))
                cells = [wl, M._fmt(bm)]
                for e in nonbare:
                    er = vals(e, var, wl, m)
                    emd = M._median(er)
                    if bm is None or emd is None or bm == 0:
                        cells.append("-")
                        continue
                    ratio = emd / bm
                    lo, hi = _bootstrap_ratio_ci(er, bare_reps)
                    tag = "ok" if M.RATIO_LO <= ratio <= M.RATIO_HI else ("UNDER" if ratio < M.RATIO_LO else "OVER")
                    ci = f" [{M._fmt(lo)},{M._fmt(hi)}]" if lo is not None else ""
                    qv = qmap.get(e)
                    mark = M.signif_marker(qv) if qv is not None else "n/a"
                    cells.append(f"{ratio:.2f}x{ci} {tag} {mark}")
                    cd = M.cliffs_delta(er, bare_reps)
                    tsv_rows.append((var, wl, m, "absolute", e, M._fmt(bm), M._fmt(emd),
                                     M._fmt(emd - bm), f"{ratio:.3f}", M._fmt(lo), M._fmt(hi),
                                     M._fmt(cd), M.cliffs_mag(cd), M._fmt_p(raw_p[e]), M._fmt_p(qv), mark))
                em("| " + " | ".join(cells) + " |")
            em("")

    # ---- §2 + §3 delta-vs-bare (directional + descriptive) ---------------------
    def delta_section(title, metrics, rank_only):
        em(f"## {title}")
        em("")
        if not metrics:
            em("_no metric of this class with data._")
            em("")
            return
        if rank_only:
            em("RANK-ONLY: the delta shows direction/magnitude of change vs bare, but only the "
               "ORDERING is claimable for these metrics (event-definition/scope or proxy confounds).")
            em("")
        for var in variants:
            for m in metrics:
                cls = M.CLAIM_CLASS.get(m, "descriptive")
                em(f"### {var} — {m}  *({cls})*")
                em("")
                em("| workload | bare | " + " | ".join(f"{e} Δ±IQR (q,δ)" for e in nonbare) + " |")
                em("|" + "---|" * (len(nonbare) + 2))
                for wl in wls_present:
                    bare_reps = vals(BARE, var, wl, m)
                    bm = M._median(bare_reps)
                    # BH-adjust the env family's MW p-values for this (var,wl,metric)
                    raw_p = {e: _mw_p(vals(e, var, wl, m), bare_reps) for e in nonbare}
                    keys = [e for e in nonbare if raw_p[e] is not None]
                    q = M.bh_adjust([raw_p[e] for e in keys])
                    qmap = dict(zip(keys, q))
                    cells = [wl, M._fmt(bm)]
                    for e in nonbare:
                        er = vals(e, var, wl, m)
                        emd = M._median(er)
                        if bm is None or emd is None:
                            cells.append("-")
                            continue
                        d = emd - bm
                        iqr = M._iqr(er)            # dispersion of the env distribution
                        cd = M.cliffs_delta(er, bare_reps)
                        p = raw_p[e]
                        qv = qmap.get(e)
                        mark = M.signif_marker(qv) if qv is not None else "n/a"
                        cells.append(f"{M._fmt(d)}±{M._fmt(iqr)} ({mark},{M._fmt(cd)})")
                        tsv_rows.append((var, wl, m, cls, e, M._fmt(bm), M._fmt(emd), M._fmt(d),
                                         "", "", "", M._fmt(cd), M.cliffs_mag(cd),
                                         M._fmt_p(p), M._fmt_p(qv), mark))
                    em("| " + " | ".join(cells) + " |")
                em("")

    dir_metrics = [m for m in metrics_present if M.CLAIM_CLASS.get(m) == "directional"]
    desc_metrics = [m for m in metrics_present if M.CLAIM_CLASS.get(m, "").startswith("descriptive")]
    delta_section("§2 Δ vs bare — DIRECTIONAL metrics (llcmr, schedlat)", dir_metrics, rank_only=True)
    delta_section("§3 Δ vs bare — DESCRIPTIVE metrics", desc_metrics, rank_only=False)

    # ---- write outputs ---------------------------------------------------------
    with open(tsv_path, "w") as fh:
        for r in tsv_rows:
            fh.write("\t".join(str(x) for x in r) + "\n")
    em(f"_Machine-readable rows: {tsv_path} ({len(tsv_rows) - 1} env-vs-bare comparisons)._")

    report = "\n".join(L) + "\n"
    if args.out:
        open(args.out, "w").write(report)
        sys.stderr.write(f"[wrote {args.out} + {tsv_path}]\n")
    else:
        print(report)
        sys.stderr.write(f"[wrote {tsv_path}]\n")


if __name__ == "__main__":
    main()

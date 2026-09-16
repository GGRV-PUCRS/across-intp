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


def _cell_backend_status(base, env, var, stage, wl):
    """Union of parse_backend_status() over every rep in a cell. The three
    campaign trees behind this analyzer are one status per (variant, env,
    metric) with zero exceptions (verified across the full portable.tsv set,
    2026-09-16), so a disagreement across reps of the SAME cell is treated as
    a data anomaly worth surfacing rather than silently averaged away."""
    merged = {}
    disagreements = []
    for rep in sorted(glob.glob(f"{base}/{env}/{var}/{stage}/{wl}/rep*")):
        for fn in ("portable.tsv", "profiler.tsv"):
            p = os.path.join(rep, fn)
            if os.path.exists(p):
                for m, st in M.parse_backend_status(p).items():
                    if m in merged and merged[m] != st:
                        disagreements.append((rep, m, merged[m], st))
                    merged[m] = st
                break
    if disagreements:
        for rep, m, old, new in disagreements:
            print(f"[WARN] backend-status disagreement in {rep}: {m} was "
                  f"{old}, saw {new}", file=sys.stderr)
    return merged


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


# Primary colocation contention signals (C29): these are the VM-portable metrics
# expected to RISE when a noisy neighbour is co-located. schedthr/steal are confound
# guards (own-quota throttling / hypervisor steal), not contention signals.
W5_PRIMARY = ["schedlat", "psi_mem", "psi_io", "membw_est"]
W5_GUARD = ["schedthr", "steal"]


def w5_report(base, variants, stage_pair="pairwise", stage_solo="solo", tag_status=False):
    """W5 colocation victim-delta (C29): per (env, variant, victim) report the
    pairwise-minus-solo delta on all 13 metrics, with the VM-portable signals
    (schedlat/psi_*/membw_est) as the PRIMARY contention evidence. Pairs are named
    `<victim_wl>__vs__<aggressor>`; the solo baseline is the victim's own solo cell
    in the SAME campaign (so run W5 into the solo campaign dir). Under colocation
    `cpu` drops absolute->directional (cgroup profiler vs system-wide GT; C29)."""
    pair_cell = defaultdict(list)   # (env,var,pair) -> [rep_summary]
    solo_cell = defaultdict(list)   # (env,var,victim_wl) -> [rep_summary]
    pairs, envs_seen = set(), set()
    for env in M.ENVS:
        for var in variants:
            for pp in sorted(glob.glob(f"{base}/{env}/{var}/{stage_pair}/*__vs__*")):
                name = os.path.basename(pp)
                reps = sorted(glob.glob(f"{pp}/rep*"))
                if not reps:
                    continue
                pairs.add(name); envs_seen.add(env)
                for rep in reps:
                    pair_cell[(env, var, name)].append(M.rep_summary(rep))
    victims = sorted({p.split("__vs__")[0] for p in pairs})
    for env in M.ENVS:
        for var in variants:
            for wl in victims:
                for rep in sorted(glob.glob(f"{base}/{env}/{var}/{stage_solo}/{wl}/rep*")):
                    solo_cell[(env, var, wl)].append(M.rep_summary(rep))

    L = []
    def em(s=""):
        L.append(s)
    em(f"# W5 colocation victim-delta (pairwise − solo) — {base}")
    em("")
    empty_hdr = ("variant", "env", "pair", "metric", "class", "solo_median", "pair_median",
                 "delta", "cliffs_delta", "mw_p", "mw_q_bh", "signif", "role")
    if tag_status:
        empty_hdr = empty_hdr + ("status",)
    if not pairs:
        em(f"**no W5 pairwise data under {base}/<env>/<variant>/{stage_pair}/<victim>__vs__<aggressor>/rep***")
        return "\n".join(L) + "\n", [empty_hdr]
    envs_present = M.order_envs(envs_seen)
    em(f"Envs: {', '.join(envs_present)}. Variants: {', '.join(variants)}. "
       f"Pairs: {len(pairs)}. scipy: {'yes' if HAVE_SCIPY else 'NO'}.")
    em("")
    em(f"**Victim-delta = median(pairwise victim) − median(solo victim)** per metric. PRIMARY "
       f"contention signals (should RISE under a noisy neighbour): `{', '.join(W5_PRIMARY)}`. "
       f"GUARDS (own-quota/steal, not contention): `{', '.join(W5_GUARD)}`. Significance = "
       "Mann-Whitney U (pairwise vs solo) + Cliff's δ, BH-FDR across the metric family per "
       "(env,variant,pair). Under colocation `cpu` is DIRECTIONAL not absolute (cgroup profiler "
       "vs system-wide GT — C29).")
    em("")

    def cls_of(m):
        return "directional" if m == "cpu" else M.CLAIM_CLASS.get(m, "descriptive")

    tsv = [empty_hdr]
    cols = W5_PRIMARY + ["cpu"]   # the headline columns
    for var in variants:
        for env in envs_present:
            env_pairs = [p for p in sorted(pairs) if pair_cell[(env, var, p)]]
            if not env_pairs:
                continue
            em(f"### {var} — {env}  *(primary contention signals; Δ = pairwise − solo)*")
            em("")
            em("| victim — vs aggressor | " + " | ".join(f"{c} Δ (q,δ)" for c in cols) + " | contention |")
            em("|" + "---|" * (len(cols) + 2))
            for p in env_pairs:
                vwl = p.split("__vs__")[0]
                prs = pair_cell[(env, var, p)]
                status = _cell_backend_status(base, env, var, stage_pair, p) if tag_status else {}
                # BH across the full 13-metric family for this cell
                raw = {}
                for m in M.METRICS_ALL:
                    pv = [s.get(m) for s in prs if s.get(m) is not None]
                    sv = [s.get(m) for s in solo_cell[(env, var, vwl)] if s.get(m) is not None]
                    raw[m] = (_mw_p(pv, sv), pv, sv)
                keys = [m for m in M.METRICS_ALL if raw[m][0] is not None]
                q = M.bh_adjust([raw[m][0] for m in keys])
                qmap = dict(zip(keys, q))
                dvals = {}
                row = [p.replace("__vs__", " — vs ")]
                for m in cols:
                    pmd = M._median(raw[m][1]); smd = M._median(raw[m][2])
                    if pmd is None or smd is None:
                        row.append("-"); dvals[m] = (None, None); continue
                    d = pmd - smd
                    cd = M.cliffs_delta(raw[m][1], raw[m][2])
                    qv = qmap.get(m)
                    mark = M.signif_marker(qv) if qv is not None else "n/a"
                    row.append(f"{M._fmt(d)} ({mark},{M._fmt(cd)})")
                    dvals[m] = (d, mark)
                # full 13 -> TSV
                for m in M.METRICS_ALL:
                    pmd = M._median(raw[m][1]); smd = M._median(raw[m][2])
                    if pmd is None or smd is None:
                        continue
                    cd = M.cliffs_delta(raw[m][1], raw[m][2])
                    qv = qmap.get(m)
                    role = "primary" if m in W5_PRIMARY else ("guard" if m in W5_GUARD else cls_of(m))
                    row_t = (var, env, p, m, cls_of(m), M._fmt(smd), M._fmt(pmd),
                             M._fmt(pmd - smd), M._fmt(cd), M._fmt_p(raw[m][0]),
                             M._fmt_p(qv), M.signif_marker(qv) if qv is not None else "n/a", role)
                    if tag_status:
                        row_t = row_t + (status.get(m, "OK"),)
                    tsv.append(row_t)
                def _sig(mm):
                    dd, mk = dvals.get(mm, (None, None))
                    return dd is not None and mk not in ("n.s.", "n/a")
                up = [mm for mm in W5_PRIMARY if _sig(mm) and dvals[mm][0] > 0]
                down = [mm for mm in W5_PRIMARY if _sig(mm) and dvals[mm][0] < 0]
                parts = []
                if up:
                    parts.append("**" + "+".join(up) + "** ↑")
                if down:
                    parts.append("+".join(down) + " ↓")
                # Steal/Starving (Volpert): victim runs LESS on-CPU (cpu↓) while its
                # run-queue wait RISES (schedlat↑) — the false-negative a cpu-util
                # detector misses but schedlat catches.
                if _sig("cpu") and dvals["cpu"][0] < 0 and _sig("schedlat") and dvals["schedlat"][0] > 0:
                    parts.append("⚠STARVING")
                row.append(" / ".join(parts) if parts else "—")
                em("| " + " | ".join(row) + " |")
            em("")
    return "\n".join(L) + "\n", tsv


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("campaign_dir")
    ap.add_argument("--out", default=None)
    ap.add_argument("--tsv", default=None, help="machine-readable rows (default <campaign>/cross-deployment.tsv)")
    ap.add_argument("--stage", default="solo")
    ap.add_argument("--w5", action="store_true",
                    help="W5 colocation victim-delta mode: pairwise−solo per metric (C29), "
                         "reads <campaign>/<env>/<var>/pairwise/<victim>__vs__<aggressor>/rep*")
    ap.add_argument("--variants", default=None, help="CSV; default v2.1,v3.3")
    ap.add_argument("--tag-status", action="store_true",
                    help="append a status column (OK/PROXY/UNAVAILABLE) per row, read from "
                         "each portable.tsv's backend-provenance header (intp_metrics."
                         "parse_backend_status) -- e.g. v2.1 vm-guest llcocc is a real reading "
                         "via the miss-ratio proxy fallback, not the same 'unavailable' as v3.3's. "
                         "Default output filename gains a '-tagged' suffix unless --tsv is given.")
    args = ap.parse_args()
    base = args.campaign_dir.rstrip("/")
    variants = args.variants.split(",") if args.variants else list(M.VARIANTS)
    default_name = "cross-deployment-tagged.tsv" if args.tag_status else "cross-deployment.tsv"
    tsv_path = args.tsv or os.path.join(base, default_name)

    if args.w5:
        default_w5_name = "w5-victim-delta-tagged.tsv" if args.tag_status else "w5-victim-delta.tsv"
        tsv_path = args.tsv or os.path.join(base, default_w5_name)
        report, tsv_rows = w5_report(base, variants, tag_status=args.tag_status)
        with open(tsv_path, "w") as fh:
            for r in tsv_rows:
                fh.write("\t".join(str(x) for x in r) + "\n")
        report += f"\n_Machine-readable rows: {tsv_path} ({len(tsv_rows) - 1} victim-delta cells)._\n"
        if args.out:
            open(args.out, "w").write(report)
            sys.stderr.write(f"[wrote {args.out} + {tsv_path}]\n")
        else:
            print(report)
            sys.stderr.write(f"[wrote {tsv_path}]\n")
        return

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

    hdr = ("variant", "workload", "metric", "claim_class", "env",
           "bare_median", "env_median", "delta", "ratio", "ci_lo", "ci_hi",
           "cliffs_delta", "cliffs_mag", "mw_p", "mw_q_bh", "signif")
    if args.tag_status:
        hdr = hdr + ("status",)
    tsv_rows = [hdr]

    nonbare = [e for e in good if e != BARE]

    status_cache = {}
    def get_status(env, var, wl, m):
        key = (env, var, wl)
        if key not in status_cache:
            status_cache[key] = _cell_backend_status(base, env, var, args.stage, wl)
        return status_cache[key].get(m, "OK")

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
                    row_t = (var, wl, m, "absolute", e, M._fmt(bm), M._fmt(emd),
                             M._fmt(emd - bm), f"{ratio:.3f}", M._fmt(lo), M._fmt(hi),
                             M._fmt(cd), M.cliffs_mag(cd), M._fmt_p(raw_p[e]), M._fmt_p(qv), mark)
                    if args.tag_status:
                        row_t = row_t + (get_status(e, var, wl, m),)
                    tsv_rows.append(row_t)
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
                        row_t = (var, wl, m, cls, e, M._fmt(bm), M._fmt(emd), M._fmt(d),
                                 "", "", "", M._fmt(cd), M.cliffs_mag(cd),
                                 M._fmt_p(p), M._fmt_p(qv), mark)
                        if args.tag_status:
                            row_t = row_t + (get_status(e, var, wl, m),)
                        tsv_rows.append(row_t)
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

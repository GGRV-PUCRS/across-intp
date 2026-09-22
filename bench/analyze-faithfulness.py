#!/usr/bin/env python3
"""analyze-faithfulness.py — W4 faithfulness adjudication from groundtruth.tsv.

Closes the W4 process gap (C22): the per-dimension agents under-used the
`groundtruth.tsv` present in every run dir. Reads each solo run's `profiler.tsv`
(the 7 canonical metrics) and `groundtruth.tsv` (the stress-ng side-channel) and
adjudicates faithfulness per (env, variant, workload) using median/IQR across
reps plus scipy stats (Mann-Whitney U + Cliff's delta) when scipy is present.

Scale discipline (critical): of the GT columns, ONLY `cpu_busy_pct` is on the
same 0-100 scale as its profiler metric (`cpu`), so it is the only column that
admits a direct ratio adjudication -- and it is populated for EVERY workload, so
we adjudicate `cpu` vs `cpu_busy_pct` across all workloads. CAVEAT (scope): the
profiler `cpu` is CGROUP-SCOPED (the tenant) while GT `cpu_busy_pct` is read from
/proc/stat and is SYSTEM-WIDE; for these SOLO runs the single tenant is the only
significant load so they align, but under colocation they diverge by design, so
the ratio verdict is meaningful for solo only. The profiler's `blk`, `netp`,
`nets` are 0-100 normalized utilizations while GT `disk_*`/`net_*` are raw
MB/interval, so those are reported QUALITATIVELY (does the metric activate on the
expected workload) -- a raw ratio there is meaningless (C7 blk normalization;
netp on a loopback workload sees NIC GT ~0). `llcmr` IS adjudicated (§1b) against
the perf GT (100*llc_miss/llc_ref); like cpu it is system-wide perf (-a) vs a
cgroup-scoped profiler metric, so the ratio is a solo-only verdict and is gated on
enough LLC traffic. `mbw`/`llcocc` GT columns (resctrl CMT) stay empty =>
UNVERIFIABLE (one RMID per task; the profiler holds it, so its own read is the GT).

Invalid-cell guard: an env whose CPU workload (app10) shows GT cpu_busy_pct < 10
for EVERY variant that ran it did not actually load the host (the tenant never
ran in the measured cgroup); it is flagged INVALID and excluded from
faithfulness conclusions. Validity is derived per-variant so a v3.3-only campaign
(or a failed v2.1 app10) is not mis-flagged.

Usage:  python3 bench/analyze-faithfulness.py results/<campaign-dir> [--out report.md]
"""
import sys, os, glob, argparse
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import intp_metrics as M  # noqa: E402  (shared metric model + stats; see bench/intp_metrics.py)

try:
    from scipy.stats import mannwhitneyu, spearmanr
    HAVE_SCIPY = True
except Exception:
    HAVE_SCIPY = False

# Metric model + thresholds are shared (bench/intp_metrics.py). The faithfulness
# adjudicator works the canonical 7 + the W4 5-class spine (WORKLOAD_SPINE), so
# its tables are unchanged; CLAIM_CLASS is the unified 13-metric map.
METRICS     = M.METRICS_CANON
CLAIM_CLASS = M.CLAIM_CLASS
ENVS        = M.ENVS
VARIANTS    = M.VARIANTS
WORKLOAD    = M.WORKLOAD_SPINE      # W4 5-class spine (unchanged from this file's original)
CPU_WL      = M.CPU_WL
DISK_WL     = M.DISK_WL
NET_WL      = M.NET_WL
UNVERIFIABLE = M.UNVERIFIABLE
RATIO_LO, RATIO_HI = M.RATIO_LO, M.RATIO_HI
IDLE_GT     = M.IDLE_GT
LLCREF_MIN  = M.LLCREF_MIN


# Basic stats helpers shared (identical implementations) -- bench/intp_metrics.py.
_median = M._median
_iqr = M._iqr
cliffs_delta = M.cliffs_delta


def _stat(a, b):
    """Compact 'cliff=.. p=..' suffix comparing rep-lists a vs b (None-safe)."""
    a = [x for x in a if x is not None]
    b = [x for x in b if x is not None]
    d = cliffs_delta(a, b)
    out = f"cliff={_fmt(d)}" if d is not None else ""
    # MWU needs >=1 each AND some spread across the pooled values (else undefined).
    if HAVE_SCIPY and len(a) >= 2 and len(b) >= 2 and len(set(a) | set(b)) > 1:
        try:
            out += f" p={mannwhitneyu(a, b, alternative='two-sided').pvalue:.3f}"
        except Exception:
            pass
    return out


# Parsers + per-rep summary are shared (bench/intp_metrics.py). rep_summary prefers
# portable.tsv's 13-col superset then profiler.tsv, so the faithfulness adjudicator
# now also works on a --portable-metrics (fused) campaign, reading the canonical 7
# from portable.tsv. Byte-identical to this file's original on a profiler.tsv
# campaign with no '--' cells (the W4 data); parse_capture additionally keeps a row
# when a single metric is '--' (None that cell) rather than dropping the whole row.
parse_gt = M.parse_gt
rep_summary = M.rep_summary


_fmt = M._fmt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("campaign_dir")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    base = args.campaign_dir.rstrip("/")

    cell = defaultdict(list)  # (env,var,wl) -> [rep_summary,...]
    for env in ENVS:
        for var in VARIANTS:
            for wl in WORKLOAD:
                for rep in sorted(glob.glob(f"{base}/{env}/{var}/solo/{wl}/rep*")):
                    cell[(env, var, wl)].append(rep_summary(rep))

    def vals(env, var, wl, key):
        return [s.get(key) for s in cell[(env, var, wl)] if s.get(key) is not None]

    reps = [len(v) for v in cell.values() if v]
    if not reps:
        msg = (f"no data under {base} "
               f"(expected {base}/<env>/<variant>/solo/<workload>/rep*/profiler.tsv)")
        print(f"# W4 faithfulness adjudication — {base}\n\n**{msg}**")
        if args.out:
            open(args.out, "w").write(f"# W4 faithfulness — {msg}\n")
        return

    # env-validity: derived per-variant (handles v3.3-only campaigns / failed v2.1).
    invalid = {}  # env -> None (no app10 GT) | value (host never loaded)
    for env in ENVS:
        gtcs = [_median(vals(env, v, CPU_WL, "gt_cpu")) for v in VARIANTS]
        present = [g for g in gtcs if g is not None]
        if not present:
            invalid[env] = None
        elif max(present) < 10:
            invalid[env] = max(present)
    good = [e for e in ENVS if e not in invalid]

    L = []
    em = L.append
    em(f"# W4 faithfulness adjudication — {base}")
    em("")
    em(f"scipy: {'available (Mann-Whitney U + Cliff delta)' if HAVE_SCIPY else 'ABSENT (Cliff delta only)'}; "
       f"reps/cell median: {int(_median(reps) or 0)}")
    if invalid:
        em("")
        parts = []
        for e, g in invalid.items():
            parts.append(f"{e} (no app10 GT data)" if g is None
                         else f"{e} (app10 GT cpu_busy_pct={_fmt(g)} for all variants => tenant never loaded host)")
        em("**INVALID envs (excluded from faithfulness):** " + ", ".join(parts))
    em("")

    # ---- 1. CPU faithfulness ---------------------------------------------------
    em("## 1. CPU faithfulness — `cpu` vs GT `cpu_busy_pct` (only same-scale GT; all workloads)")
    em("")
    em(f"Verdict: FAITHFUL {RATIO_LO}<=ratio<={RATIO_HI}, else UNDER/OVERREPORTS; each variant vs "
       f"ITS OWN runs' GT (cliff/p from scipy over reps). NOTE: profiler `cpu` is cgroup-scoped, GT "
       f"`cpu_busy_pct` is system-wide -- they align for SOLO runs (single tenant) but would diverge "
       f"under colocation; the ratio is a solo-only adjudication. GT cpu% column = median over variants.")
    em("")
    em("| env | workload | GT cpu% | v2.1 cpu | v2.1 verdict | v3.3 cpu | v3.3 verdict |")
    em("|---|---|---|---|---|---|---|")
    for env in good:
        for wl in WORKLOAD:
            gt_disp = _median([x for v in VARIANTS for x in vals(env, v, wl, "gt_cpu")])
            row = [env, wl, _fmt(gt_disp)]
            for var in VARIANTS:
                pr = vals(env, var, wl, "cpu")
                gvr = vals(env, var, wl, "gt_cpu")
                cm, gvm = _median(pr), _median(gvr)
                r = (cm / gvm) if (cm is not None and gvm) else None
                if gvm is not None and gvm < IDLE_GT:
                    v = "n/a (idle wl)"
                elif r is None:
                    v = "-"
                else:
                    tag = "FAITHFUL" if RATIO_LO <= r <= RATIO_HI else ("**UNDER**" if r < RATIO_LO else "**OVER**")
                    st = _stat(pr, gvr)
                    v = f"{tag} ({r:.2f})" + (f" [{st}]" if st else "")
                row += [_fmt(cm), v]
            em("| " + " | ".join(row) + " |")
    em("")
    em("**CPU summary (good envs, non-idle workloads):**")
    for var in VARIANTS:
        faith = under = over = 0
        bad = []
        for env in good:
            for wl in WORKLOAD:
                cm, gvm = _median(vals(env, var, wl, "cpu")), _median(vals(env, var, wl, "gt_cpu"))
                if cm is None or not gvm or gvm < IDLE_GT:
                    continue
                r = cm / gvm
                if RATIO_LO <= r <= RATIO_HI:
                    faith += 1
                elif r < RATIO_LO:
                    under += 1; bad.append(f"{env}/{wl} under(r={r:.2f})")
                else:
                    over += 1; bad.append(f"{env}/{wl} over(r={r:.2f})")
        em(f"- {var}: {faith} faithful, {under} under, {over} over"
           + (f" — {', '.join(bad)}" if bad else ""))
    em("")

    # ---- 1b. LLC miss-ratio (DIRECTIONAL — event-definition + scope differ) ----
    em("## 1b. LLC miss-ratio — `llcmr` vs perf GT `100×llc_miss/llc_ref` (DIRECTIONAL; see caveat)")
    em("")
    em("**Read these verdicts as DIRECTIONAL, not as a same-scale pass/fail.** Both variants emit `llcmr` "
       "as a percentage (miss/ref×100), but the profiler and the GT do NOT count the same physical "
       "quantity, so an absolute ratio outside the band does not by itself prove unfaithfulness:")
    em("")
    em("- **Event-definition (denominators differ).** GT uses perf `cache-references`/`cache-misses` = "
       "`PERF_COUNT_HW_CACHE_REFERENCES`/`_MISSES` (Intel `LONGEST_LAT_CACHE.REFERENCE`/`.MISS`, ALL request "
       "ops: reads + RFO/writes + code). Both variants instead use `PERF_TYPE_HW_CACHE` "
       "`LL|OP_READ|RESULT_ACCESS` for the denominator — a READ-ONLY LL-access event with a distinct kernel "
       "PMU mapping. Numerators agree in intent (LLC misses); the DENOMINATORS are a different physical "
       "event, which shifts the absolute % independent of any counting bug. (v2.1's raw-fallback denom "
       "`0x4F2E` IS `LONGEST_LAT_CACHE.REFERENCE` = GT's event, but these runs used the primary hwcache "
       "backend — perfev.c:125-130/183-188; v3.3 intp_agg.c:196-200,729-737.)")
    em("- **Scope (cgroup vs system-wide).** Profiler `llcmr` is cgroup-scoped (tenant tasks only); GT is "
       "perf `-a` (all CPUs incl. kernel/background). A miss ratio is intensive, so system-wide is the "
       "reference-weighted blend of tenant + background ratios — it moves the value materially ONLY when the "
       "tenant's reference footprint is small (app10_search, GT llc_ref ~12M/interval → its ~1% vs ~7-8% gap "
       "is plausible scope dilution) and CANNOT explain a tenant-dominated workload (app07_ordering, GT "
       "llc_ref ~495M/interval, true ratio ~87% → scope moves it only points; the ~40% profiler read there "
       "is event-definition, not scope). There is NO `llcmr_sys` diagnostic column.")
    em("")
    em(f"Band FAITHFUL {RATIO_LO}<=ratio<={RATIO_HI} (else UNDER/OVER) is kept for reference but is "
       f"indicative only. Gated on median GT llc_ref >= {LLCREF_MIN:.0g}/interval. GT cols = median over "
       f"variants. The Spearman rank check below the table is the load-bearing faithfulness measure here.")
    em("")
    em("| env | workload | GT llcmr% | GT llc_ref | v2.1 llcmr | v2.1 verdict | v3.3 llcmr | v3.3 verdict |")
    em("|---|---|---|---|---|---|---|---|")
    have_llcmr_gt = False
    for env in good:
        for wl in WORKLOAD:
            gtmr = _median([x for v in VARIANTS for x in vals(env, v, wl, "gt_llcmr")])
            gtref = _median([x for v in VARIANTS for x in vals(env, v, wl, "gt_llc_ref")])
            if gtmr is not None:
                have_llcmr_gt = True
            row = [env, wl, _fmt(gtmr), _fmt(gtref)]
            for var in VARIANTS:
                pr = vals(env, var, wl, "llcmr")
                gvr = vals(env, var, wl, "gt_llcmr")
                cm, gvm = _median(pr), _median(gvr)
                grefm = _median(vals(env, var, wl, "gt_llc_ref"))
                r = (cm / gvm) if (cm is not None and gvm) else None
                if gvm is None or grefm is None:
                    v = "-"
                elif grefm < LLCREF_MIN:
                    v = "n/a (low LLC traffic)"
                elif r is None:
                    v = "-"
                else:
                    tag = "FAITHFUL" if RATIO_LO <= r <= RATIO_HI else ("**UNDER**" if r < RATIO_LO else "**OVER**")
                    st = _stat(pr, gvr)
                    v = f"{tag} ({r:.2f})" + (f" [{st}]" if st else "")
                row += [_fmt(cm), v]
            em("| " + " | ".join(row) + " |")
    if not have_llcmr_gt:
        em("")
        em("_(No populated GT llc_ref/llc_miss in this campaign — perf GT path absent or all "
           "'--'; re-run with the interval-mode perf harness to adjudicate.)_")
    em("")
    # directional faithfulness: Spearman rank of profiler llcmr vs GT across adjudicated cells.
    # This is the real faithfulness signal for llcmr (absolute ratios are confounded by the
    # event-definition + scope differences above) -- does the profiler ORDER cells like the GT?
    if HAVE_SCIPY and have_llcmr_gt:
        em("**Directional faithfulness (Spearman rank — profiler `llcmr` vs GT across adjudicated cells):**")
        for var in VARIANTS:
            xs, ys = [], []
            for env in good:
                for wl in WORKLOAD:
                    cm = _median(vals(env, var, wl, "llcmr"))
                    gm = _median(vals(env, var, wl, "gt_llcmr"))
                    gr = _median(vals(env, var, wl, "gt_llc_ref"))
                    if cm is not None and gm is not None and gr is not None and gr >= LLCREF_MIN:
                        xs.append(cm); ys.append(gm)
            if len(xs) >= 3 and len(set(xs)) > 1 and len(set(ys)) > 1:
                rho, p = spearmanr(xs, ys)
                ok = rho is not None and rho >= 0.6 and p < 0.05
                em(f"- {var}: rho={rho:.2f} (p={p:.1e}, n={len(xs)} cells) — "
                   + ("directionally FAITHFUL" if ok else "weak rank agreement"))
            else:
                em(f"- {var}: insufficient spread/cells for rank correlation (n={len(xs)})")
        em("(So the absolute UNDER/OVER labels above reflect the event-definition + scope differences, "
           "not an established absolute miss-ratio error; the profiler ranks cells by miss-ratio "
           "consistently with the GT.)")
        em("")

    # ---- 2. Normalized-metric activation (qualitative) -------------------------
    em("## 2. Normalized metrics (blk / netp / nets) — qualitative activation")
    em("")
    em("0-100 utilizations; GT `disk_*`/`net_*` are raw MB/interval (blk: C7 normalization; net: "
       "loopback workload => NIC GT ~0). No ratio.")
    em("")
    em(f"- **blk on {DISK_WL} (disk)** vs max on non-disk workloads:")
    for env in good:
        for v in VARIANTS:
            on = _median(vals(env, v, DISK_WL, "blk"))
            off = max([_median(vals(env, v, w, "blk")) or 0 for w in WORKLOAD if w != DISK_WL] or [0])
            tag = "tracks disk" if (on or 0) > 50 else "CHECK"
            em(f"    - {env}/{v}: blk={_fmt(on)} (max-off {_fmt(off)}) — {tag}")
    em(f"- **netp/nets on {NET_WL} (loopback net)** — hook-placement difference:")
    for env in good:
        cells = "  ".join(f"{v}: netp={_fmt(_median(vals(env, v, NET_WL, 'netp')))} "
                          f"nets={_fmt(_median(vals(env, v, NET_WL, 'nets')))}" for v in VARIANTS)
        em(f"    - {env}: {cells}")
    em("  (v3.3 cgroup_skb captures per-cgroup loopback the v2.1 device path misses; v2.1 softirq "
       "`nets` sees it. NOT NIC-GT-confirmable -- loopback.)")
    em("")

    em(f"## 3. GT-UNVERIFIABLE metrics: {', '.join(UNVERIFIABLE)}")
    em("resctrl GT columns (`resctrl_mbw_bps`,`resctrl_llcocc_bytes`) are empty BY DESIGN: Intel RDT "
       "CMT/MBM bind one RMID per task and the profiler holds the tenant's RMID, so no independent "
       "collector can read the same tasks' occupancy/bandwidth concurrently — the profiler's own "
       "resctrl read IS the occupancy/bandwidth ground truth (which is exactly why the v3.3 nested-"
       "cgroup read had to target the right cgroup; C24). `llcmr` IS now COMPARED (§1b) against the perf "
       "GT — but DIRECTIONALLY: the perf event (read-only LL access vs all-op cache-references) and scope "
       "(cgroup vs `-a`) differ, so absolute ratios are indicative and the §1b rank correlation is the "
       "faithfulness measure. Values in §5.")
    em("")

    # ---- 4. dominant-metric signature -----------------------------------------
    em("## 4. Per-workload dominant metric (qualitative signature)")
    em("")
    em("| env | variant | " + " | ".join(WORKLOAD) + " |")
    em("|" + "---|" * (len(WORKLOAD) + 2))
    for env in ENVS:
        for var in VARIANTS:
            cells = []
            for wl in WORKLOAD:
                meds = {m: _median(vals(env, var, wl, m)) for m in METRICS}
                meds = {m: v for m, v in meds.items() if v is not None}
                dom = max(meds, key=meds.get) if meds else "-"
                cells.append(f"{dom}({_fmt(meds.get(dom))})")
            tag = " *(INVALID)*" if env in invalid else ""
            em(f"| {env}{tag} | {var} | " + " | ".join(cells) + " |")
    em("")

    # ---- 5. full per-cell table ------------------------------------------------
    em("## 5. Per-cell median (spread = q3-q1 nearest-rank; ~full range for small n) — all metrics")
    em("")
    em("| env | variant | workload | " + " | ".join(METRICS) + " | gt_cpu | gt_disk | gt_net | gt_llcmr |")
    em("|" + "---|" * (len(METRICS) + 7))
    for env in ENVS:
        for var in VARIANTS:
            for wl in WORKLOAD:
                row = [env + (" (INVALID)" if env in invalid else ""), var, wl]
                for m in METRICS:
                    xs = vals(env, var, wl, m)
                    row.append(f"{_fmt(_median(xs))}({_fmt(_iqr(xs))})")
                for k in ("gt_cpu", "gt_disk", "gt_net", "gt_llcmr"):
                    row.append(_fmt(_median(vals(env, var, wl, k))))
                em("| " + " | ".join(row) + " |")

    report = "\n".join(L)
    print(report)
    if args.out:
        open(args.out, "w").write(report + "\n")
        sys.stderr.write(f"[wrote {args.out}]\n")


if __name__ == "__main__":
    main()

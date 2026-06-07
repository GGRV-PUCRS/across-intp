#!/usr/bin/env python3
"""analyze-portable.py — faithfulness adjudication for the VM-portable metrics.

The portable benchmark (C26 / docs/reports/8th-metric-vm-portable-design.md §10)
is a SEPARATE campaign: `run-intp-bench.sh --portable-metrics` captures the six
VM-portable metrics into per-rep `portable.tsv` files (alongside `groundtruth.tsv`).
This is the dedicated adjudicator -- the portable-metrics sibling of
`analyze-faithfulness.py`, reusing its conventions (solo glob, median-across-reps,
'--' = unavailable, scipy-optional, env-validity guard).

The six portable metrics (canonical order):

    schedlat   run-queue / scheduling latency  -- DIRECTIONAL
    psi_mem    PSI memory.pressure 'some'       -- DESCRIPTIVE (capacity, not bw)
    membw_est  DRAM-bandwidth estimate (MB/s)   -- DESCRIPTIVE (the bw complement)
    psi_io     PSI io.pressure 'some'           -- DESCRIPTIVE
    schedthr   CFS throttling                   -- DESCRIPTIVE (confound guard)
    steal      hypervisor-stolen vCPU %         -- DESCRIPTIVE, VM-only

What it adjudicates (DESIGN §6):

  §1 Availability matrix -- which portable metrics render numeric per env. The
     headline VM result: schedlat/psi_*/membw_est/steal are available in vm-guest
     while the canonical mbw/llcocc/llcmr are '--' (the gap that motivated them).
  §2 Spearman portable-vs-GT -- membw_est vs the perf memory-traffic GT
     (llc_miss), schedlat vs GT llcmr (the contention it should track), and the
     KEY falsification psi_mem vs llc_miss (expected WEAK: capacity-blind to
     bandwidth). Solo-scope, traffic-gated, like analyze-faithfulness §1b.
  §3 PSI bandwidth-blindness falsification -- on the highest-membw_est cell per
     env, is psi_mem ~0 while membw_est is high? If so psi_mem is confirmed
     capacity-only (descriptive); membw_est is the metric that carries the
     bandwidth dimension. schedlat is expected to rise under the same stressor.
  §4 vm-guest confirmation -- portable medians + availability in-guest.
  §5 Per-cell median table for every portable metric.

Overhead is measured by the orchestrator's `overhead` stage, not here.

Usage:  python3 bench/analyze-portable.py results/<campaign-dir> [--out report.md]
"""
import sys, os, glob, argparse
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import intp_metrics as M  # noqa: E402

try:
    from scipy.stats import spearmanr
    HAVE_SCIPY = True
except Exception:
    HAVE_SCIPY = False

# Metric model + parsers + stats are shared (bench/intp_metrics.py) so the
# portable adjudicator, the faithfulness adjudicator, the cross-env omnibus, and
# the cross-deployment paired-delta generator agree on order / claim-class /
# parsing. Aliased here so the report logic below reads unchanged.
PORTABLE        = M.METRICS_PORTABLE   # schedlat psi_mem membw_est psi_io schedthr steal
CLAIM_CLASS     = M.CLAIM_CLASS        # 13-metric map; the 6 portable values are unchanged
CANON_RDT       = M.CANON_RDT          # mbw llcocc llcmr (go '--' in a KVM guest)
CANON           = M.METRICS_CANON
ENVS            = M.ENVS
VARIANTS        = M.VARIANTS
WORKLOAD        = M.WORKLOAD
CPU_WL          = M.CPU_WL
INVALID_CPU_PCT = M.INVALID_CPU_PCT
LLCREF_MIN      = M.LLCREF_MIN
RHO_OK          = M.RHO_OK
MEMBW_HI        = M.MEMBW_HI
PSI_LO          = M.PSI_LO


# Parsers + helpers are shared (header-aware/ts-agnostic capture reader, the
# unified groundtruth parser, and per-rep summary that prefers portable.tsv's
# 13-metric superset). See bench/intp_metrics.py.
parse_portable = M.parse_capture
parse_gt       = M.parse_gt
rep_summary    = M.rep_summary
_median        = M._median
_fmt           = M._fmt


# --------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("campaign_dir")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    base = args.campaign_dir.rstrip("/")

    cell = defaultdict(list)   # (env,var,wl) -> [rep_summary,...]
    for env in ENVS:
        for var in VARIANTS:
            for wl in WORKLOAD:
                for rep in sorted(glob.glob(f"{base}/{env}/{var}/solo/{wl}/rep*")):
                    cell[(env, var, wl)].append(rep_summary(rep))

    def vals(env, var, wl, key):
        return [s.get(key) for s in cell[(env, var, wl)] if s.get(key) is not None]

    L = []   # report lines
    def w(line=""):
        L.append(line)

    reps = [len(v) for v in cell.values() if v]
    w(f"# Portable-metrics faithfulness adjudication — {base}")
    w()
    if not reps:
        w(f"**no data** (expected {base}/<env>/<variant>/solo/<workload>/rep*/portable.tsv)")
        _emit(L, args.out)
        return
    envs_present = sorted({e for (e, v, wl) in cell if cell[(e, v, wl)]},
                          key=lambda e: ENVS.index(e) if e in ENVS else 99)
    w(f"Cells with data: {sum(1 for v in cell.values() if v)} | "
      f"reps/cell: min {min(reps)} max {max(reps)} | "
      f"scipy: {'yes' if HAVE_SCIPY else 'NO (Spearman skipped)'}")
    w()

    # env-validity (per-variant, like analyze-faithfulness): host actually loaded?
    invalid = {}
    for env in ENVS:
        gtcs = [_median(vals(env, v, CPU_WL, "gt_cpu")) for v in VARIANTS]
        present = [g for g in gtcs if g is not None]
        if present and max(present) < INVALID_CPU_PCT:
            invalid[env] = max(present)
    good = [e for e in envs_present if e not in invalid]

    # ---- §1 availability matrix ----
    w("## §1 Availability matrix (portable metrics render numeric vs '--')")
    w()
    w("`ok` = the metric produced a numeric reading in ≥1 rep of that env; `--` = "
      "never (source absent — e.g. CONFIG_PSI=n, no cpu.max quota, no perf). The "
      "VM-portable claim: schedlat/psi_*/membw_est/steal stay `ok` in vm-guest "
      "where the canonical RDT metrics (mbw/llcocc/llcmr) go `--`.")
    w()
    for var in VARIANTS:
        rows = [e for e in envs_present if any(cell[(e, var, wl)] for wl in WORKLOAD)]
        if not rows:
            continue
        w(f"### {var}")
        w()
        hdr = ["env"] + PORTABLE + ["|", "mbw", "llcocc", "llcmr"]
        w("| " + " | ".join(hdr) + " |")
        w("|" + "---|" * len(hdr))
        for env in rows:
            tag = " (INVALID)" if env in invalid else ""
            cells = [env + tag]
            for m in PORTABLE:
                av = any(s.get("avail_" + m) for wl in WORKLOAD for s in cell[(env, var, wl)])
                cells.append("ok" if av else "--")
            cells.append("|")
            for m in CANON_RDT:
                got = any(vals(env, var, wl, m) for wl in WORKLOAD)
                cells.append("ok" if got else "--")
            w("| " + " | ".join(cells) + " |")
        w()

    # ---- §2 Spearman portable-vs-GT ----
    w("## §2 Spearman: portable metric vs ground truth (solo, traffic-gated)")
    w()
    if not HAVE_SCIPY:
        w("_scipy unavailable — install numpy/scipy to compute Spearman ρ._")
        w()
    else:
        # (portable metric, GT key, expectation/caveat)
        pairs = [
            ("membw_est", "gt_mbw_bps",  "INDEPENDENT validation vs resctrl MBM bandwidth — expect STRONG + (often n<3: resctrl mbw GT is '--' by CMT design, C24)"),
            ("membw_est", "gt_llc_miss", "consistency check only — membw_est IS derived from cache-misses, so this shares its source, NOT an independent validation"),
            ("schedlat",  "gt_llcmr",    "directional: contention slows the victim, its run-queue backs up — expect +"),
            ("psi_mem",   "gt_llc_miss", "FALSIFICATION: psi_mem is capacity-driven — expect WEAK vs bandwidth"),
        ]
        w("| variant | portable | vs GT | n | ρ | p | verdict |")
        w("|---|---|---|---|---|---|---|")
        for var in VARIANTS:
            for pm, gk, _note in pairs:
                xs, ys = [], []
                for env in good:
                    for wl in WORKLOAD:
                        pmm = _median(vals(env, var, wl, pm))
                        gkm = _median(vals(env, var, wl, gk))
                        ref = _median(vals(env, var, wl, "gt_llc_ref"))
                        if pmm is None or gkm is None:
                            continue
                        if ref is None or ref < LLCREF_MIN:
                            continue
                        xs.append(pmm); ys.append(gkm)
                if len(xs) >= 3 and len(set(xs)) > 1 and len(set(ys)) > 1:
                    rho, p = spearmanr(xs, ys)
                    if pm == "psi_mem":
                        verdict = "blind (capacity-only)" if (rho is None or rho < RHO_OK or p >= 0.05) \
                                  else "tracks bandwidth (unexpected)"
                    else:
                        verdict = "faithful" if (rho is not None and rho >= RHO_OK and p < 0.05) else "weak"
                    w(f"| {var} | {pm} | {gk} | {len(xs)} | {_fmt(rho)} | {p:.3f} | {verdict} |")
                else:
                    w(f"| {var} | {pm} | {gk} | {len(xs)} | - | - | n<3 / no spread |")
        w()
        for pm, gk, note in pairs:
            w(f"- **{pm} vs {gk}** — {note}")
        w("- **Scope caveat (in-guest envs):** `groundtruth.tsv` is always captured "
          "HOST-side, while in vm-guest / container-guest the portable metrics are "
          "captured INSIDE the guest — so those cells correlate guest-side metrics "
          "against the host's counters. Treat vm-guest §2 rows as indicative only; "
          "the §1 availability + §4 in-guest tables are the load-bearing VM evidence.")
        w()

    # ---- §3 PSI bandwidth-blindness falsification ----
    w("## §3 PSI bandwidth-blindness falsification")
    w()
    w(f"Per (env,variant) the cell with the highest `membw_est`. If `membw_est` is "
      f"high (≥{MEMBW_HI:.0f} MB/s) while `psi_mem` stays flat (≤{PSI_LO:.0f}%), "
      f"`psi_mem` is confirmed **capacity-only** (bandwidth-blind) and `membw_est` "
      f"is the metric carrying the bandwidth dimension. `schedlat` should rise too.")
    w()
    w("| env | variant | workload | membw_est (MB/s) | psi_mem (%) | schedlat (%) | finding |")
    w("|---|---|---|---|---|---|---|")
    any_conf = False
    for var in VARIANTS:
        for env in good:
            best_wl, best_mb = None, None
            for wl in WORKLOAD:
                mbv = _median(vals(env, var, wl, "membw_est"))
                if mbv is not None and (best_mb is None or mbv > best_mb):
                    best_mb, best_wl = mbv, wl
            if best_wl is None:
                continue
            pmem = _median(vals(env, var, best_wl, "psi_mem"))
            sl   = _median(vals(env, var, best_wl, "schedlat"))
            if best_mb >= MEMBW_HI and pmem is not None and pmem <= PSI_LO:
                finding = "blind CONFIRMED"; any_conf = True
            elif best_mb < MEMBW_HI:
                finding = "membw too low to test"
            elif pmem is None:
                finding = "psi_mem unavailable"   # never measured -- not "moved"
            else:
                finding = "psi_mem moved"
            w(f"| {env} | {var} | {best_wl} | {_fmt(best_mb)} | {_fmt(pmem)} | {_fmt(sl)} | {finding} |")
    w()
    w(f"**psi_mem capacity-only:** {'CONFIRMED on ≥1 cell' if any_conf else 'not confirmed in this campaign'} "
      f"(needs a saturating-bandwidth workload with ample free RAM, e.g. app05_streaming).")
    w()

    # ---- §4 membw_est corroboration gate (net-path instrumentation caveat) ----
    w("## §4 membw_est corroboration gate (net-path instrumentation caveat)")
    w()
    w("`membw_est` is cache-miss-derived and reported as an UNCLAMPED absolute (MB/s), so "
      "on net-heavy workloads where the hardware cache/bandwidth canonicals (`mbw`, "
      "`llcmr`) read ~0, a non-zero `membw_est` is NOT corroborated as workload DRAM "
      "bandwidth — it integrates net-softirq + per-packet eBPF-hook misses. The eBPF "
      "variant (v3.3) inflates this over the C variant (v2.1): on app11 v3.3 `membw_est` "
      "is ~6–7× v2.1, and an INDEPENDENT host-side GT shows v3.3 generating ~3.6× the "
      "system LLC misses v2.1 does on that workload (the bandwidth analogue of the eBPF "
      "overhead in `docs/V3-OVERHEAD-FINDINGS.md`). The **canonical 7 are UNAFFECTED** — "
      "`mbw`/`llcmr` are %-normalized + clamped, so the ~0.02%-of-ceiling footprint rounds "
      "to 0 (verified: app11 `mbw`=0/`llcmr`=0 for BOTH variants). Cells with `membw_est`>0 "
      "but `mbw`≈0 and `llcmr`≈0 are flagged **uncorroborated** (C31): read them as "
      "instrumentation-influenced, not true bandwidth; do not use them for cross-variant "
      "absolute-bandwidth claims.")
    w()
    w("| env | variant | workload | membw_est | mbw | llcmr | corroborated? |")
    w("|---|---|---|---|---|---|---|")
    n_uncorr = 0
    for env in envs_present:
        for var in VARIANTS:
            for wl in WORKLOAD:
                mb = _median(vals(env, var, wl, "membw_est"))
                if mb is None or mb <= 0:
                    continue
                mbwv = _median(vals(env, var, wl, "mbw"))
                lmrv = _median(vals(env, var, wl, "llcmr"))
                if (mbwv is not None and mbwv > 1) or (lmrv is not None and lmrv > 1):
                    continue   # corroborated by a hardware cache/bw signal — list only suspects
                n_uncorr += 1
                w(f"| {env} | {var} | {wl} | {_fmt(mb)} | {_fmt(mbwv)} | {_fmt(lmrv)} | "
                  f"**uncorroborated (net-path)** |")
    if n_uncorr == 0:
        w("| — | — | — | — | — | — | all membw_est readings corroborated by mbw/llcmr |")
    w()
    w(f"_{n_uncorr} cell(s) flagged (membw_est>0 with mbw≈0 and llcmr≈0). The v2.1↔v3.3 "
      "gap on these is the eBPF net-path footprint, not workload bandwidth (C31)._")
    w()

    # ---- §5 vm-guest confirmation ----
    w("## §5 vm-guest confirmation")
    w()
    if "vm-guest" not in envs_present:
        w("_no vm-guest data in this campaign._")
    else:
        w("Portable medians in-guest (across workloads), and the canonical RDT "
          "metrics that are structurally `--` there.")
        w()
        w("| variant | " + " | ".join(PORTABLE) + " | mbw | llcocc | llcmr |")
        w("|---|" + "---|" * (len(PORTABLE) + 3))
        for var in VARIANTS:
            if not any(cell[("vm-guest", var, wl)] for wl in WORKLOAD):
                continue
            cells = [var]
            for m in PORTABLE:
                allv = [x for wl in WORKLOAD for x in vals("vm-guest", var, wl, m)]
                cells.append(_fmt(_median(allv)) if allv else "--")
            for m in CANON_RDT:
                allv = [x for wl in WORKLOAD for x in vals("vm-guest", var, wl, m)]
                cells.append(_fmt(_median(allv)) if allv else "--")
            w("| " + " | ".join(cells) + " |")
        w()
        w("If the portable columns are numeric while mbw/llcocc/llcmr are `--`, the "
          "portable benchmark recovers scheduling + memory dimensions in a stock KVM "
          "guest where the RDT/LL-PMU fingerprint cannot (C26).")
    w()

    # ---- §6 per-cell medians ----
    w("## §6 Per-cell medians (claim class in header)")
    w()
    head = ["env", "variant", "workload"] + [f"{m}[{CLAIM_CLASS[m]}]" for m in PORTABLE]
    w("| " + " | ".join(head) + " |")
    w("|" + "---|" * len(head))
    for env in envs_present:
        for var in VARIANTS:
            for wl in WORKLOAD:
                if not cell[(env, var, wl)]:
                    continue
                row = [env, var, wl] + [_fmt(_median(vals(env, var, wl, m))) for m in PORTABLE]
                w("| " + " | ".join(row) + " |")
    w()
    if invalid:
        w("_Invalid envs (host not loaded; GT cpu<10% on the cpu workload): "
          + ", ".join(f"{e} ({_fmt(v)}%)" for e, v in invalid.items()) + "._")

    _emit(L, args.out)


def _emit(lines, out):
    text = "\n".join(lines) + "\n"
    if out:
        open(out, "w").write(text)
        print(f"wrote {out}")
    else:
        print(text)


if __name__ == "__main__":
    main()

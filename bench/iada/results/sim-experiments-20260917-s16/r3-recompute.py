#!/usr/bin/env python3
# r3-recompute.py -- R3: recompute W5 victim mbw deltas with the v3.3 solo arm
# rescaled from the pre-audit 42656 MB/s ceiling to the audited 281600 MB/s
# ceiling (factor 0.1514, the C34 "0.151 correction").
#
# Parsing mirrors the analysis pipeline exactly: intp_metrics.parse_capture
# (warmup row dropped, '--' -> skipped) + rep_summary (per-rep median), then
# analyze-cross-deployment.py w5_report (median and Cliff's delta over the 12
# per-rep medians). Validation: the *_logged columns must reproduce
# results/02-w5-colocation/w5-victim-delta.tsv exactly; they do.
import glob, os, statistics, sys

W5 = os.path.expanduser("~/results/02-w5-colocation")
XDEP = os.path.expanduser("~/results/p2-15metric-xdeploy-1of3")
SCALE = 42656.0 / 281600.0  # pre-audit fallback ceiling / audited ceiling


def rep_medians(env, variant, stage, wl):
    meds = []
    reps = sorted(glob.glob(f"{W5}/{env}/{variant}/{stage}/{wl}/rep*"),
                  key=lambda p: int(os.path.basename(p)[3:]))
    for rep in reps:
        f = os.path.join(rep, "portable.tsv")
        if not os.path.exists(f):
            continue
        names, vals, first = None, [], True
        for line in open(f):
            s = line.rstrip("\n")
            if not s or s[0] == "#":
                continue
            if s.startswith("netp"):
                names = s.split("\t")
                continue
            if names is None or not (s[0].isdigit() or s[0] == "-"):
                continue
            c = s.split("\t")
            off = len(c) - len(names)
            if off not in (0, 1):
                continue
            if first:  # warmup row dropped (parse_capture semantics)
                first = False
                continue
            v = c[names.index("mbw") + off]
            if v not in ("--", ""):
                vals.append(float(v))
        if vals:
            meds.append(statistics.median(vals))
    return meds


def cliffs(a, b):
    gt = sum(1 for x in a for y in b if x > y)
    lt = sum(1 for x in a for y in b if x < y)
    return (gt - lt) / (len(a) * len(b)) if a and b else None


def solo_is_bytecopy(env, variant, wl):
    """True if every w5 solo cell that also exists in the pre-audit
    cross-deployment tree is byte-identical to it (cmp semantics)."""
    any_pair = False
    for rep in range(1, 13):
        a = f"{W5}/{env}/{variant}/solo/{wl}/rep{rep}/portable.tsv"
        b = f"{XDEP}/{env}/{variant}/solo/{wl}/rep{rep}/portable.tsv"
        if os.path.exists(a) and os.path.exists(b):
            any_pair = True
            if open(a, "rb").read() != open(b, "rb").read():
                return False
    return any_pair


hdr = ("env", "variant", "victim", "n_solo_reps", "n_pair_reps",
       "solo_median_logged", "pair_median", "delta_logged", "cliffs_logged",
       "solo_median_rescaled", "delta_rescaled", "cliffs_rescaled",
       "v21_delta", "v21_cliffs", "solo_provenance")
print("\t".join(hdr))
for env in ["bare", "container"]:
    for wl in ["app01_ml_llc", "app07_ordering", "app10_search",
               "app11_sort_net", "app13_query_scan"]:
        pair = f"{wl}__vs__app05_membw"
        sv = rep_medians(env, "v3.3", "solo", wl)
        pv = rep_medians(env, "v3.3", "pairwise", pair)
        sv21 = rep_medians(env, "v2.1", "solo", wl)
        pv21 = rep_medians(env, "v2.1", "pairwise", pair)
        if not sv or not pv:
            continue
        svr = [x * SCALE for x in sv]
        prov = ("bytecopy-of-preaudit-xdeploy" if solo_is_bytecopy(env, "v3.3", wl)
                else "later-collection-not-in-preaudit-snapshot")
        row = (env, "v3.3", wl, len(sv), len(pv),
               f"{statistics.median(sv):.2f}", f"{statistics.median(pv):.2f}",
               f"{statistics.median(pv) - statistics.median(sv):+.2f}",
               f"{cliffs(pv, sv):+.3f}",
               f"{statistics.median(svr):.2f}",
               f"{statistics.median(pv) - statistics.median(svr):+.2f}",
               f"{cliffs(pv, svr):+.3f}",
               f"{statistics.median(pv21) - statistics.median(sv21):+.2f}" if sv21 and pv21 else "n/a",
               f"{cliffs(pv21, sv21):+.3f}" if sv21 and pv21 else "n/a",
               prov)
        print("\t".join(map(str, row)))

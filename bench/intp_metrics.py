#!/usr/bin/env python3
"""intp_metrics.py -- shared metric model + parsers + stats for the IntP
cross-deployment analysis suite.

Single source of truth fusing the canonical 7-metric fingerprint and the 6
VM-portable metrics (--portable-metrics, C26/C27) into ONE 13-metric model, so
the faithfulness adjudicator (analyze-faithfulness.py), the portable adjudicator
(analyze-portable.py), the cross-env omnibus (plot/plot-cross-environment.py),
and the unified cross-deployment paired-delta generator
(analyze-cross-deployment.py) all agree on metric order, claim classes, parsing,
and the basic statistics.

Dependency discipline: STDLIB ONLY (statistics/os). numpy/scipy live in the
callers that need them (plot-cross-environment.py, the Spearman/MW paths), so any
analyzer can import this module without acquiring a hard numpy dependency.
"""
import os
import statistics
from collections import OrderedDict

# --------------------------------------------------------------- metric model

# Canonical 7-metric IntP fingerprint (ABI-invariant; Paper 1).
METRICS_CANON = ["netp", "nets", "blk", "mbw", "llcmr", "llcocc", "cpu"]
# 6 VM-portable metrics (--portable-metrics; canonical order shared with
# portable.c / intp_portable_metrics() / the v3.3 emitter).
METRICS_PORTABLE = ["schedlat", "psi_mem", "membw_est", "psi_io", "schedthr", "steal"]
# The 13-metric superset captured per-rep by a --portable-metrics campaign.
METRICS_ALL = METRICS_CANON + METRICS_PORTABLE

# RDT metrics that are structurally gapped in a stock KVM guest.
CANON_RDT = ["mbw", "llcocc", "llcmr"]
# resctrl metrics with no independent ground truth (CMT one-RMID-per-task).
UNVERIFIABLE = ["mbw", "llcocc"]

# Per-metric Paper-2 claim tier, wired to the W4 verdicts (DECISIONS C24a) and
# the portable design (C26/C27 §8). The tier gates what a claim may assert:
#   absolute    -- same-scale ground truth exists (ratio claims allowed)
#   directional -- faithful in rank/ordering only (Spearman; never an abs ratio)
#   descriptive -- no independent GT; report value/delta, no faithfulness claim
CLAIM_CLASS = {
    # canonical 7
    "cpu": "absolute",
    "llcmr": "directional",
    "netp": "descriptive",
    "nets": "descriptive",
    "blk": "descriptive",
    "mbw": "descriptive",
    "llcocc": "descriptive",
    # portable 6
    "schedlat": "directional",
    "psi_mem": "descriptive",
    "membw_est": "descriptive",
    "psi_io": "descriptive",
    "schedthr": "descriptive(guard)",
    "steal": "descriptive(vm-only)",
}

# Canonical deployment axis (left->right). Envs not listed sort after, alpha.
DEPLOY_ORDER = [
    "bare", "container", "container-podman", "container-lxc",
    "container-k8s", "vm-guest", "vm",
]
ENVS = list(DEPLOY_ORDER)
VARIANTS = ["v2.1", "v3.3"]

# Metrics STRUCTURALLY unavailable in an env (distinct from a collection miss).
# vm-guest: resctrl is host-only, so RDT occupancy/bandwidth cannot be read in a
# stock KVM guest (llcmr IS available there via the architectural PMU fallback).
UNSUPPORTED = {
    "vm-guest": {"mbw", "llcocc"},
}

# Workload spine (W4 5-class; one representative per interference class). Kept as
# a distinct constant so the faithfulness adjudicator's tables are unchanged.
WORKLOAD_SPINE = OrderedDict([
    ("app01_ml_llc", "LLC/cache"),
    ("app07_ordering", "memory"),
    ("app10_search", "cpu"),
    ("app11_sort_net", "network"),
    ("app13_query_scan", "disk"),
])
# Fused cross-deployment workload set: the spine + the saturating
# memory-bandwidth driver app05_streaming (the §3 bandwidth-blindness driver).
WORKLOAD = OrderedDict([
    ("app01_ml_llc", "LLC/cache"),
    ("app05_streaming", "mem-bandwidth"),
    ("app07_ordering", "memory"),
    ("app10_search", "cpu"),
    ("app11_sort_net", "network"),
    ("app11b_tcp_veth", "network(veth)"),
    ("app13_query_scan", "disk"),
])
CPU_WL = "app10_search"        # env-validity guard workload
DISK_WL = "app13_query_scan"
NET_WL = "app11_sort_net"

MISSING_TOKEN = "--"

# Thresholds (shared across the adjudicators).
RATIO_LO, RATIO_HI = 0.8, 1.25   # FAITHFUL band (cpu vs cpu_busy_pct; llcmr ref)
IDLE_GT = 5.0                     # GT cpu% below which a workload is too idle to ratio
INVALID_CPU_PCT = 10.0           # GT cpu% on the cpu workload below which the env is INVALID
LLCREF_MIN = 1e6                 # median GT llc_ref/interval below which LLC traffic is too low
RHO_OK = 0.6                     # Spearman directional-faithfulness threshold
MEMBW_HI = 1000.0                # MB/s: "high" bandwidth for the psi_mem falsification gate
PSI_LO = 5.0                     # %: psi_mem at/below this is "flat"

# --------------------------------------------------------------- stats helpers

def _median(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def _iqr(xs):
    xs = sorted(x for x in xs if x is not None)
    if len(xs) < 2:
        return 0.0
    return xs[(3 * len(xs)) // 4] - xs[len(xs) // 4]


def _fmt(x):
    if x is None:
        return "-"
    if abs(x) >= 100:
        return f"{x:.0f}"
    if abs(x) >= 1:
        return f"{x:.1f}"
    return f"{x:.3f}"


def _fmt_p(p):
    """p/q-value formatter that preserves small magnitudes for the machine-
    readable TSV (a strongly-significant p must not round to '0.000' like _fmt)."""
    if p is None or p != p:
        return "-"
    if 0 < p < 1e-3:
        return f"{p:.2e}"
    return f"{p:.4f}"


def cliffs_delta(a, b):
    """Cliff's delta (float in [-1,1]), None if either side is empty. Pure
    stdlib; matches analyze-faithfulness.py's semantics."""
    a = [x for x in a if x is not None]
    b = [x for x in b if x is not None]
    if not a or not b:
        return None
    gt = sum(1 for x in a for y in b if x > y)
    lt = sum(1 for x in a for y in b if x < y)
    return (gt - lt) / (len(a) * len(b))


def cliffs_mag(d):
    """Vargha-Delaney magnitude label for a Cliff's delta."""
    if d is None:
        return "n/a"
    ad = abs(d)
    if ad < 0.147:
        return "negligible"
    if ad < 0.33:
        return "small"
    if ad < 0.474:
        return "medium"
    return "large"


def bh_adjust(pvals):
    """Benjamini-Hochberg FDR (pure stdlib). Returns q-values in input order;
    None inputs (and NaN) stay None and are excluded from the rank count."""
    idx = [i for i, p in enumerate(pvals) if p is not None and p == p]
    m = len(idx)
    q = [None] * len(pvals)
    if m == 0:
        return q
    order = sorted(idx, key=lambda i: pvals[i])
    prev = 1.0
    for rank in range(m, 0, -1):          # largest p first -> monotone accumulate
        i = order[rank - 1]
        prev = min(prev, pvals[i] * m / rank)
        q[i] = max(0.0, min(1.0, prev))
    return q


def signif_marker(p, threshold=0.05):
    if p is None or p != p:
        return "n/a"
    if p < threshold / 50:
        return "***"
    if p < threshold / 5:
        return "**"
    if p < threshold:
        return "*"
    return "n.s."


def order_envs(envs):
    """Sort envs along DEPLOY_ORDER; unknown envs sort after, alphabetically."""
    rank = {e: i for i, e in enumerate(DEPLOY_ORDER)}
    return sorted(envs, key=lambda e: (rank.get(e, len(DEPLOY_ORDER)), e))


# --------------------------------------------------------------- parsing

def parse_capture(path):
    """Header-aware, ts-agnostic read of a profiler.tsv OR portable.tsv.

    The column-header line (starts with 'netp') names the columns; data rows MAY
    carry a leading host timestamp (host-observer captures prepend one, off=1;
    in-guest captures via docker exec / ssh do NOT, off=0). The offset is derived
    per row from the field-count delta, so 7-col and 13-col, ts and no-ts, all
    parse. Returns per-row dicts keyed by the column names present (whichever of
    the 13 metrics the capture carries), warmup row dropped. '--' -> None.
    """
    names = None
    rows = []
    with open(path) as fh:
        for line in fh:
            s = line.rstrip("\n")
            if not s or s[0] == "#":
                continue
            if s.startswith("netp"):
                names = s.split("\t")
                continue
            if names is None or not (s[0].isdigit() or s[0] == "-"):
                continue
            c = s.split("\t")
            off = len(c) - len(names)        # 1 = leading ts, 0 = none
            if off not in (0, 1):
                continue
            row = {}
            for i, nm in enumerate(names):
                v = c[i + off]
                try:
                    row[nm] = float(v)
                except ValueError:
                    row[nm] = None            # '--'
            rows.append(row)
    return rows[1:]   # drop the warmup/priming first sample


def parse_gt(path):
    """groundtruth.tsv -> per-interval dicts. Columns: ts cpu_busy_pct
    disk_read_mb disk_write_mb net_rx_mb net_tx_mb instr cycles llc_ref llc_miss
    resctrl_mbw_bps resctrl_llcocc_bytes. First (cumulative) row dropped."""
    rows = []
    with open(path) as fh:
        for line in fh:
            s = line.rstrip("\n")
            if not s or s.startswith("ts\t"):
                continue
            c = s.split("\t")
            if len(c) < 6:
                continue

            def f(i):
                try:
                    return float(c[i])
                except (ValueError, IndexError):
                    return None
            dr, dw, nr, nt = f(2), f(3), f(4), f(5)
            rows.append({
                "gt_cpu": f(1),
                "gt_disk": (dr + dw) if (dr is not None and dw is not None) else None,
                "gt_net": (nr + nt) if (nr is not None and nt is not None) else None,
                "gt_llc_ref": f(8),     # perf cache-references / interval
                "gt_llc_miss": f(9),    # perf cache-misses / interval (memory-traffic GT)
                "gt_mbw_bps": f(10),    # resctrl MBM bytes/s (often '--' by CMT design)
            })
    return rows[1:]


def rep_summary(rundir):
    """Per-run medians for whichever metrics the capture carries (prefers
    portable.tsv's 13-metric superset, else profiler.tsv's 7), plus the GT keys
    and gt_llcmr, plus avail_<metric> flags. Reused by every adjudicator."""
    out = {}
    cap = None
    for fn in ("portable.tsv", "profiler.tsv"):
        p = os.path.join(rundir, fn)
        if os.path.exists(p):
            cap = parse_capture(p)
            break
    if cap is not None:
        present = set()
        for r in cap:
            present.update(r.keys())
        for m in present:
            xs = [r.get(m) for r in cap if r.get(m) is not None]
            out[m] = statistics.median(xs) if xs else None
            out["avail_" + m] = 1 if xs else 0
    gp = os.path.join(rundir, "groundtruth.tsv")
    if os.path.exists(gp):
        gr = parse_gt(gp)
        mref = _median([r["gt_llc_ref"] for r in gr])
        mmiss = _median([r["gt_llc_miss"] for r in gr])
        out["gt_cpu"] = _median([r["gt_cpu"] for r in gr])
        out["gt_disk"] = _median([r["gt_disk"] for r in gr])
        out["gt_net"] = _median([r["gt_net"] for r in gr])
        out["gt_llc_ref"] = mref
        out["gt_llc_miss"] = mmiss
        out["gt_mbw_bps"] = _median([r["gt_mbw_bps"] for r in gr])
        out["gt_llcmr"] = (100.0 * mmiss / mref) if (mref and mmiss is not None and mref > 0) else None
    return out


def env_validity(envs, variants, cpu_wl, vals):
    """Per-variant env-validity guard: an env whose CPU-workload GT cpu_busy_pct
    is < INVALID_CPU_PCT for ALL variants never loaded the host. `vals(env, var,
    wl, key)` is the caller's accessor. Returns {env: None|value} for INVALID
    envs (None = no GT at all)."""
    invalid = {}
    for env in envs:
        gtcs = [_median(vals(env, v, cpu_wl, "gt_cpu")) for v in variants]
        present = [g for g in gtcs if g is not None]
        # Mark INVALID only when GT is PRESENT but below the load floor (genuinely
        # idle host). NO GT at all is insufficient evidence, NOT "idle" -- keep the
        # env (e.g. a missing app10 GT must not silently drop the bare baseline and
        # disable every paired delta-vs-bare).
        if present and max(present) < INVALID_CPU_PCT:
            invalid[env] = max(present)
    return invalid

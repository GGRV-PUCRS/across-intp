#!/usr/bin/env python3
"""analyze-tierb.py -- real-application 15-metric fingerprints (Tier-B/C).

Adjudicates figure F12: the fingerprints of REAL applications (Redis,
CloudSuite, DeathStarBench) are *mixed* across resource classes -- a single
resource-class label (IADA's cpu/mem/cache/disk/net) does not describe them.
Unlike the synthetic micro-benchmarks (each built to stress one resource),
every real app activates two or more classes at once.

This is the realism half of Paper 2 / the bridge to IADA: it is exactly the
single-class assumption baked into the IADA classifier that this campaign
stresses. The analyzer is workload-agnostic -- it auto-discovers whatever apps,
envs and variants are present under the campaign tree, so the same script serves
Tier-B (app18-21) and Tier-C (app22 DSB).

Inputs: <campaign>/<env>/<variant>/solo/<app>/rep*/portable.tsv  (no
ground-truth needed -- real apps have no synthetic GT; this is a fingerprint
report, not a faithfulness adjudication).

Usage:
    python3 bench/analyze-tierb.py <campaign_dir> [--out report.md]
                                   [--tsv fingerprints.tsv]
"""
import argparse
import glob
import os
import sys
from collections import defaultdict, OrderedDict

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
import intp_metrics as M

METRICS_ALL = M.METRICS_ALL
CANON_RDT   = set(M.CANON_RDT)          # mbw llcocc llcmr -> '--' in a KVM guest
rep_summary = M.rep_summary
_median     = M._median
_fmt        = M._fmt

# IADA resource-class taxonomy (the 5 classes the classifier assigns). F12 shows
# real apps span >=2 of these, so a single-class label is wrong for them. Only
# resource-CONSUMPTION metrics define class membership; the scheduling-regime
# metrics (psp/idle_preempt) and guards (schedthr/steal) are cross-cutting
# contention indicators present in most apps, so they are reported separately
# (REGIME) rather than inflating the cpu class.
RESOURCE_CLASS = OrderedDict([
    ("cpu",   ["cpu", "schedlat"]),
    ("mem",   ["mbw", "membw_est", "psi_mem"]),
    ("cache", ["llcmr", "llcocc"]),
    ("disk",  ["blk", "psi_io"]),
    ("net",   ["netp", "nets"]),
])
REGIME = ["psp", "idle_preempt", "schedthr", "steal"]
CLASS_OF = {m: c for c, ms in RESOURCE_CLASS.items() for m in ms}
CLASS_OF.update({m: "regime" for m in REGIME})

# Per-metric noise floor: the median must clear this to count as "the app uses
# this resource". Set conservatively at "clearly above idle" in each metric's
# native unit (pkts/s, KB/s, %, MB/s, misses, occupancy, us, preempt/s); the
# raw §2 fingerprint lets a reader re-adjudicate. Absolute (per-app), so a
# genuine mid-level user is not masked by a heavier app on the same axis.
FLOOR = {"netp": 10, "nets": 10, "blk": 1, "mbw": 1, "llcmr": 5, "llcocc": 5,
         "cpu": 5, "schedlat": 5, "psi_mem": 1, "membw_est": 50, "psi_io": 1,
         "schedthr": 1, "steal": 1, "psp": 5, "idle_preempt": 50}
ENV_ORDER = ["bare", "container", "container-podman", "container-lxc",
             "container-k8s", "vm-guest", "vm"]


def discover(base):
    """Return (envs, variants, apps) present under base, in a stable order."""
    envs, variants, apps = set(), set(), set()
    for p in glob.glob(f"{base}/*/*/solo/*/rep*/portable.tsv"):
        rel = os.path.relpath(p, base).split(os.sep)
        envs.add(rel[0]); variants.add(rel[1]); apps.add(rel[3])
    envs = [e for e in ENV_ORDER if e in envs] + sorted(envs - set(ENV_ORDER))
    return envs, sorted(variants), sorted(apps)


def scope_fallbacks(base, envs, variants, apps):
    """Find (env,var,app) cells where the profiler could not stat its scoping
    cgroup and fell back to system-wide measurement (recorded in the capture
    header). In a dedicated single-app VM, system-wide ≈ app + guest-OS, so the
    cell is usable but slightly inflated — worth flagging."""
    hit = defaultdict(int)
    tot = defaultdict(int)
    for env in envs:
        for var in variants:
            for app in apps:
                for cap in glob.glob(f"{base}/{env}/{var}/solo/{app}/rep*/portable.tsv"):
                    tot[(env, var, app)] += 1
                    try:
                        with open(cap, errors="ignore") as fh:
                            head = "".join(fh.readline() for _ in range(6))
                        if "falling back to system-wide" in head:
                            hit[(env, var, app)] += 1
                    except OSError:
                        pass
    return {k: (hit[k], tot[k]) for k in tot if hit[k]}


def collect(base, envs, variants, apps):
    """med[(env,var,app)][metric] = median-across-reps; avail = fraction of reps
    with the metric present; nreps[(env,var,app)] = rep count."""
    med = defaultdict(dict)
    avail = defaultdict(dict)
    nreps = {}
    for env in envs:
        for var in variants:
            for app in apps:
                reps = sorted(glob.glob(f"{base}/{env}/{var}/solo/{app}/rep*"))
                nreps[(env, var, app)] = len(reps)
                if not reps:
                    continue
                summ = [rep_summary(r) for r in reps]
                for m in METRICS_ALL:
                    xs = [s[m] for s in summ if s.get(m) is not None]
                    av = sum(1 for s in summ if s.get("avail_" + m)) / len(summ)
                    med[(env, var, app)][m] = _median(xs) if xs else None
                    avail[(env, var, app)][m] = av
    return med, avail, nreps


def activation(med, env, var, apps):
    """An app 'activates' a metric when its median clears the metric's absolute
    noise floor, and a class when >=1 of the class's consumption metrics is
    active. Absolute (per-app), so a genuine mid-level user is not masked by a
    heavier app on the same axis. Returns {app: set(classes)}."""
    classes = {}
    for a in apps:
        cs = set()
        for c, ms in RESOURCE_CLASS.items():
            for m in ms:
                v = med[(env, var, a)].get(m)
                if v is not None and abs(v) >= FLOOR[m]:
                    cs.add(c); break
        classes[a] = cs
    return classes


def low_drive(med, env, var, a):
    """Heuristic flag: the app barely registered (likely under-driven load gen,
    not a genuinely idle resource profile)."""
    g = med[(env, var, a)].get
    cpu = g("cpu") or 0
    net = max(g("netp") or 0, g("nets") or 0)
    mbe = g("membw_est") or 0
    return cpu < FLOOR["cpu"] and net < FLOOR["netp"] and mbe < FLOOR["membw_est"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("campaign_dir")
    ap.add_argument("--out", default=None)
    ap.add_argument("--tsv", default=None)
    args = ap.parse_args()
    base = args.campaign_dir.rstrip("/")

    envs, variants, apps = discover(base)
    if not apps:
        sys.exit(f"no data (expected {base}/<env>/<variant>/solo/<app>/rep*/portable.tsv)")
    med, avail, nreps = collect(base, envs, variants, apps)

    L = []
    def w(s=""):
        L.append(s)

    w(f"# Real-application 15-metric fingerprints (F12) — {base}\n")
    w(f"Envs: {', '.join(envs)}. Variants: {', '.join(variants)}. "
      f"Apps: {', '.join(apps)}.\n")
    w("**Claim (F12):** real applications are *mixed* across the IADA resource "
      "classes (cpu / mem / cache / disk / net) — a single-class label, the "
      "assumption the IADA classifier is built on, does not describe them. "
      "Activation rule: a class is active in an app when ≥1 of its "
      "*consumption* metrics clears an absolute noise floor (`netp/nets`≥10, "
      "`cpu/schedlat`≥5, `membw_est`≥50, `mbw/llcmr/llcocc`≥5/1, `blk/psi_*`≥1; "
      "native units). Floors are per-app and absolute, so a mid-level user is "
      "not masked by a heavier app on the same axis (the §2 raw fingerprint "
      "lets a reader re-adjudicate). The scheduling-regime metrics "
      "(psp, idle_preempt) and guards (schedthr, steal) are cross-cutting "
      "contention indicators, reported separately — they do not define a class. "
      "1/3 footprint + hard CPU pinning; solo stage.\n")

    # ---- coverage + caveats ----
    w("## §0 Coverage & scope caveats\n")
    w("| env — variant | " + " | ".join(a.replace("_", " ") for a in apps) + " |")
    w("|---" * (len(apps) + 1) + "|")
    for env in envs:
        for var in variants:
            cells = [str(nreps.get((env, var, a), 0)) for a in apps]
            w(f"| {env} — {var} | " + " | ".join(cells) + " |")
    w("")
    # RDT availability in vm-guest + any system-wide scope fallbacks
    rdt_note = []
    for env in envs:
        for var in variants:
            for a in apps:
                for m in CANON_RDT:
                    if avail[(env, var, a)].get(m, 0) == 0 and nreps.get((env, var, a)):
                        rdt_note.append((env, var))
                        break
    if rdt_note:
        seen = sorted(set(rdt_note))
        w("- **RDT metrics (mbw/llcocc/llcmr) → `--`** (no samples) in: "
          + ", ".join(f"{e}·{v}" for e, v in seen)
          + " — expected where resctrl is unavailable (KVM guest). The portable "
            "mem/cache proxies (membw_est, psi_mem) carry the dimension there; "
            "see §3.\n")
    fb = scope_fallbacks(base, envs, variants, apps)
    if fb:
        w("- **System-wide scope fallback** (profiler could not stat the in-guest "
          "scoping cgroup → measured system-wide): "
          + "; ".join(f"{e}·{v}·{a.replace('_',' ')} ({h}/{t} reps)"
                      for (e, v, a), (h, t) in sorted(fb.items()))
          + ". In a dedicated single-app VM this is ≈ app + guest-OS background, "
            "so the fingerprint is usable but slightly inflated, not lost.\n")

    # ---- F12 punchline: class activation ----
    w("## §1 Resource-class activation — the F12 punchline\n")
    w("Number of IADA classes each real app activates (✓ = active). >1 ⇒ the "
      "single-class label fails. Computed on each host env where all metrics are "
      "available; vm-guest omitted from the count (RDT blind).\n")
    host_envs = [e for e in envs if e not in ("vm-guest", "vm")]
    low = set()
    for var in variants:
        for env in host_envs:
            if not any(nreps.get((env, var, a)) for a in apps):
                continue
            classes = activation(med, env, var, apps)
            w(f"**{env} — {var}**\n")
            w("| app | " + " | ".join(RESOURCE_CLASS.keys()) + " | # classes | regime |")
            w("|---" * (len(RESOURCE_CLASS) + 3) + "|")
            for a in apps:
                marks = ["✓" if c in classes[a] else "·" for c in RESOURCE_CLASS]
                reg = [r for r in REGIME
                       if (med[(env, var, a)].get(r) or 0) >= FLOOR[r]]
                flag = " ⚠" if low_drive(med, env, var, a) else ""
                if low_drive(med, env, var, a):
                    low.add(a)
                w(f"| {a.replace('_',' ')}{flag} | " + " | ".join(marks)
                  + f" | **{len(classes[a])}** | {', '.join(reg) or '—'} |")
            w("")
    # verdict on the cleanest host env (container if present, else first)
    venv = "container" if "container" in host_envs else (host_envs[0] if host_envs else None)
    verdict_lines = []
    for var in variants:
        if venv is None or not any(nreps.get((venv, var, a)) for a in apps):
            continue
        classes = activation(med, venv, var, apps)
        mixed = [a for a in apps if len(classes[a]) >= 2]
        verdict_lines.append(
            f"- **{venv}·{var}:** {len(mixed)}/{len([a for a in apps if nreps.get((venv,var,a))])} "
            f"apps activate ≥2 classes ("
            + "; ".join(f"{a.replace('_',' ')}={len(classes[a])}" for a in apps if nreps.get((venv, var, a)))
            + ").")
    # data-driven verdict (computed, never hardcoded): judge only the apps that
    # were actually driven on the verdict env; under-driven apps are a load-gen
    # artifact, not evidence for or against F12.
    nm = lambda xs: ", ".join(sorted(x.replace("_", " ") for x in xs))
    if venv is not None:
        venv_apps = [a for a in apps if any(nreps.get((venv, v, a)) for v in variants)]
        best = {a: max((len(activation(med, venv, v, apps)[a])
                        for v in variants if nreps.get((venv, v, a))), default=0)
                for a in venv_apps}
        driven = [a for a in venv_apps if a not in low]
        multi = [a for a in driven if best[a] >= 2]
        single_real = [a for a in driven if best[a] < 2]
        if driven and not single_real:
            verdict = (f"every adequately-driven app on {venv} spans ≥2 IADA resource "
                       f"classes ({nm(multi)}) — the single-class label fails for real apps")
        elif multi and single_real:
            verdict = (f"{len(multi)}/{len(driven)} adequately-driven apps span ≥2 classes "
                       f"({nm(multi)}); {nm(single_real)} stayed single-class even when driven")
        elif not driven:
            verdict = ("every app in this campaign was under-driven at the default load on the "
                       "1/3 footprint — no multi-resource conclusion from this campaign alone; "
                       "see the per-app fingerprint and the scheduling-regime signal in §2")
        else:
            verdict = f"{nm(single_real)} stayed single-class; {nm(multi) or 'none'} spanned ≥2"
        w(f"> **Verdict (F12):** {verdict}.\n")
    for vl in verdict_lines:
        w(vl)
    if low:
        w(f"\n⚠ **Low-drive cells:** {nm(low)} "
          "barely registered (cpu<5%, no net, membw_est<50) — at the 1/3 footprint "
          "the default load generator under-drove the service, so its low class-count "
          "is a load-gen artifact, not a single-resource signature. The scheduling-regime "
          "signal (idle_preempt/psp) and cache activity in §2 still show the app is live; "
          "an adequately-driven re-run is needed to read its full resource mix.")
    w("")

    # ---- full fingerprint tables ----
    w("## §2 Full 15-metric fingerprint (median across reps)\n")
    for a in apps:
        w(f"### {a.replace('_', ' ')}\n")
        cols = [(e, v) for e in envs for v in variants if nreps.get((e, v, a))]
        w("| metric (class) | " + " | ".join(f"{e}·{v}" for e, v in cols) + " |")
        w("|---" * (len(cols) + 1) + "|")
        for m in METRICS_ALL:
            cells = []
            for e, v in cols:
                mv = med[(e, v, a)].get(m)
                cells.append(_fmt(mv) if mv is not None else "—")
            w(f"| {m} ({CLASS_OF.get(m,'?')}) | " + " | ".join(cells) + " |")
        w("")

    # ---- vm-guest portability ----
    if any(e in envs for e in ("vm-guest", "vm")):
        w("## §3 vm-guest portability: portable proxies where RDT is `--`\n")
        w("Where mbw/llcocc/llcmr are unavailable in the guest, do the portable "
          "mem/cache/sched proxies still carry signal? (median, vm-guest)\n")
        ge = "vm-guest" if "vm-guest" in envs else "vm"
        proxy = ["membw_est", "psi_mem", "schedlat", "psi_io", "steal"]
        for var in variants:
            cols = [a for a in apps if nreps.get((ge, var, a))]
            if not cols:
                continue
            w(f"**{ge} — {var}**\n")
            w("| metric | " + " | ".join(a.replace("_", " ") for a in cols) + " |")
            w("|---" * (len(cols) + 1) + "|")
            for m in (CANON_RDT_ORDER := ["mbw", "llcocc", "llcmr"] + proxy):
                cells = []
                for a in cols:
                    mv = med[(ge, var, a)].get(m)
                    cells.append(_fmt(mv) if mv is not None else "—")
                tag = " (RDT)" if m in CANON_RDT else " (proxy)"
                w(f"| {m}{tag} | " + " | ".join(cells) + " |")
            w("")

    report = "\n".join(L)
    if args.out:
        with open(args.out, "w") as fh:
            fh.write(report + "\n")
        print(f"[wrote {args.out}]")
    else:
        print(report)

    # ---- machine-readable TSV for the plot layer (F12 radar/heatmap) ----
    tsv_path = args.tsv or os.path.join(base, "fingerprints.tsv")
    rows = ["env\tvariant\tapp\tmetric\tclass\tmedian\tavail_frac\tnreps"]
    for env in envs:
        for var in variants:
            for a in apps:
                n = nreps.get((env, var, a), 0)
                if not n:
                    continue
                for m in METRICS_ALL:
                    mv = med[(env, var, a)].get(m)
                    av = avail[(env, var, a)].get(m, 0)
                    rows.append(f"{env}\t{var}\t{a}\t{m}\t{CLASS_OF.get(m,'?')}\t"
                                + ("" if mv is None else f"{mv:.6g}")
                                + f"\t{av:.3g}\t{n}")
    with open(tsv_path, "w") as fh:
        fh.write("\n".join(rows) + "\n")
    print(f"[wrote {tsv_path} ({len(rows) - 1} rows)]")


if __name__ == "__main__":
    main()

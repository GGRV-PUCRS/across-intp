#!/usr/bin/env python3
"""s15_stats.py -- statistics helpers for the S15 simulation rerun.

Conventions are those of `bench/plot/p2_ci.py` (invariant 6 of
jsa-sim-rerun-brief.md), restated here rather than imported because that module
assumes pandas and only exposes a single-sample / percent-displacement API:

    N       = 10000 resamples
    seed    = 20260607
    method  = percentile, np.percentile(..., [2.5, 97.5])  -> ASYMMETRIC
    SD      = sample SD, ddof=1
    Welch t = the SECONDARY test, reported alongside every bootstrap CI

Two difference estimators, deliberately distinguished:

  * `unpaired_diff_ci` -- two separate runs (different tiers, or an arm vs the
    gate). The two rep vectors are independent samples, so each bootstrap
    iteration resamples them INDEPENDENTLY. Same formulation as the gate check
    already inlined in `run-sim-experiments.sh`.

  * `paired_diff_ci` -- self vs oracle within one run. Both numbers score the
    SAME placement in the SAME rep, so the rep index is the cluster: each
    iteration resamples rep indices once and applies them to both vectors.
    Bootstrapping these as independent samples is what the S13 correction
    withdrew, so it is not offered here.
"""
from __future__ import annotations

import csv
import math

import numpy as np
from scipy import stats

BOOTSTRAP_N = 10000
BOOTSTRAP_SEED = 20260607
CI_PCTILES = (2.5, 97.5)


def read_tsv(path):
    """Rows of a results TSV as dicts. FAIL rows are kept, not dropped."""
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def col(rows, field, tier=None, oracle_ref=None):
    """Numeric column as a float array; non-numeric (FAIL/empty) cells dropped.

    Returns ``(values, n_rows_considered, n_failed)`` so a caller can report n
    per arm and never silently lose a failed rep (invariant 7).
    """
    sel = [r for r in rows
           if (tier is None or r.get("tier") == tier)
           and (oracle_ref is None or r.get("oracle_ref") == oracle_ref)]
    vals, failed = [], 0
    for r in sel:
        raw = (r.get(field) or "").strip()
        try:
            vals.append(float(raw))
        except ValueError:
            failed += 1
    return np.asarray(vals, dtype=float), len(sel), failed


def mean_sd(values):
    arr = np.asarray(values, dtype=float)
    if arr.size == 0:
        return float("nan"), float("nan")
    sd = float(arr.std(ddof=1)) if arr.size > 1 else float("nan")
    return float(arr.mean()), sd


def unpaired_diff_ci(base, arm, seed_offset: int = 0, n: int = BOOTSTRAP_N):
    """95% rep-level bootstrap CI of mean(arm) - mean(base), independent resampling.

    Returns ``(delta, lo, hi, welch_p)``.
    """
    b = np.asarray(base, dtype=float)
    a = np.asarray(arm, dtype=float)
    if b.size == 0 or a.size == 0:
        return (float("nan"),) * 4
    delta = float(a.mean() - b.mean())
    if b.size < 2 or a.size < 2:
        return (delta, delta, delta, float("nan"))
    rng = np.random.default_rng(BOOTSTRAP_SEED + seed_offset)
    d = (rng.choice(a, (n, a.size), replace=True).mean(1)
         - rng.choice(b, (n, b.size), replace=True).mean(1))
    lo, hi = np.percentile(d, list(CI_PCTILES))
    p = float(stats.ttest_ind(a, b, equal_var=False).pvalue)
    return (delta, float(lo), float(hi), p)


def paired_diff_ci(first, second, seed_offset: int = 0, n: int = BOOTSTRAP_N):
    """95% paired rep-level bootstrap CI of mean(second - first).

    ``first`` and ``second`` must be aligned rep-by-rep (e.g. self_idi and
    oracle_idi of the same run). Returns ``(delta, lo, hi, paired_t_p, sd_of_diff)``.
    """
    f = np.asarray(first, dtype=float)
    s = np.asarray(second, dtype=float)
    if f.size == 0 or f.size != s.size:
        return (float("nan"),) * 5
    diff = s - f
    delta = float(diff.mean())
    sd = float(diff.std(ddof=1)) if diff.size > 1 else float("nan")
    if diff.size < 2:
        return (delta, delta, delta, float("nan"), sd)
    if np.allclose(diff, 0.0):
        # Exact self-consistency check (tier scored by its own classifier):
        # the interval is degenerate and a t-test is undefined, not p=nan-by-error.
        return (0.0, 0.0, 0.0, float("nan"), 0.0)
    rng = np.random.default_rng(BOOTSTRAP_SEED + seed_offset)
    k = diff.size
    idx = rng.integers(0, k, size=(n, k))
    means = diff[idx].mean(1)
    lo, hi = np.percentile(means, list(CI_PCTILES))
    p = float(stats.ttest_rel(s, f).pvalue)
    return (delta, float(lo), float(hi), p, sd)


def sig(lo, hi):
    """'*' when the 95% CI excludes zero, 'n.s.' otherwise."""
    if any(math.isnan(v) for v in (lo, hi)):
        return "?"
    return "*" if (lo > 0 or hi < 0) else "n.s."


def fmt(x, nd=1):
    return "nan" if (x is None or (isinstance(x, float) and math.isnan(x))) else f"{x:.{nd}f}"

#!/usr/bin/env python3
"""p2_ci.py -- rep-level bootstrap confidence intervals for the P2 figure set.

The Paper 1 camera-ready pass replaced the ad-hoc spread on fig11's IDI bars
with a 95 % cluster-bootstrap CI (5704125), then reworded the in-plot tag to say
which level the CI is computed at (9795c5b). The P2 figures inherit that
convention here so every aggregate bar in the set means the same thing.

What the CI answers: "given the rep-to-rep measurement noise, is this bar
distinguishable from another (or from zero)?" The cluster is the REPETITION, so
each bootstrap iteration draws len(values) reps with replacement and recomputes
the aggregate. Structural variation that is identical in every rep does not
enter the interval, exactly as in the Paper 1 rep-level method.

Convention shared with plot-intp-bench.py (fig11):

    N       = 10000 resamples
    seed    = 20260607, offset per series so each series has its own stream
    method  = percentile, np.nanpercentile(..., [2.5, 97.5]) -> ASYMMETRIC

The interval is asymmetric on purpose: it is the 2.5/97.5 percentile of the
resampled aggregate, not mean +/- k*SD, so it is not forced to be symmetric
about the bar and it never implies a Gaussian the 5-rep samples do not support.

Callers plot the bar at the POINT ESTIMATE computed from the full sample (the
same number as before this module existed) and use the CI only for the error
bar, so adopting it never moves a bar.
"""
from __future__ import annotations

import numpy as np

BOOTSTRAP_N = 10000
BOOTSTRAP_SEED = 20260607
CI_PCTILES = (2.5, 97.5)

#: Reader-facing tag naming the level the CI is computed at. Mirrors the
#: IDI_CI_TITLE wording settled in 9795c5b ("rep-level 95%").
CI_TAG = "rep-level 95% CI"


def rep_ci(values, seed_offset: int = 0, n: int = BOOTSTRAP_N):
    """95 % rep-level bootstrap CI of the mean of ``values``.

    Returns ``(mean, lo, hi)`` where ``mean`` is the plain sample mean over all
    reps (the plotted bar) and ``lo``/``hi`` are the percentile bounds. With
    fewer than two usable reps there is nothing to resample, so the interval
    collapses onto the point estimate and the bar draws no whisker.
    """
    arr = np.asarray([v for v in values if v is not None], dtype=float)
    arr = arr[~np.isnan(arr)]
    if arr.size == 0:
        return (float("nan"), float("nan"), float("nan"))
    mean = float(arr.mean())
    if arr.size < 2:
        return (mean, mean, mean)

    k = arr.size
    rng = np.random.default_rng(BOOTSTRAP_SEED + seed_offset)
    # Multinomial weights == drawing k reps with replacement, vectorised over
    # all N resamples at once. Same formulation as fig11's cluster bootstrap.
    weights = rng.multinomial(k, np.full(k, 1.0 / k), size=n).astype(float)
    means = (weights @ arr) / k
    lo, hi = np.nanpercentile(means, list(CI_PCTILES))
    return (mean, float(lo), float(hi))


def ratio_ci(base_values, arm_values, seed_offset: int = 0, n: int = BOOTSTRAP_N):
    """95 % rep-level bootstrap CI of a percent displacement between two arms.

    The statistic is the one F9 already reports::

        pct = (median(base) - median(arm)) / median(base) * 100

    Each iteration resamples the baseline reps and the arm reps INDEPENDENTLY
    with replacement (the two arms are separate runs, so their rep noise is
    independent) and recomputes ``pct`` through the same median path, so the
    interval inherits the estimator rather than approximating it. This mirrors
    fig11's two-sided cluster bootstrap, with baseline/arm standing in for
    solo/pairwise.

    Returns ``(pct, lo, hi)``; the point estimate is computed from the full
    sample and is bit-for-bit the value F9 reported before the CI existed.
    """
    b = np.asarray([v for v in base_values if v is not None], dtype=float)
    a = np.asarray([v for v in arm_values if v is not None], dtype=float)
    b, a = b[~np.isnan(b)], a[~np.isnan(a)]
    if b.size == 0 or a.size == 0 or np.median(b) == 0:
        return (float("nan"), float("nan"), float("nan"))

    pct = float((np.median(b) - np.median(a)) / np.median(b) * 100.0)
    if b.size < 2 or a.size < 2:
        return (pct, pct, pct)

    rng = np.random.default_rng(BOOTSTRAP_SEED + seed_offset)
    bs = rng.choice(b, size=(n, b.size), replace=True)
    as_ = rng.choice(a, size=(n, a.size), replace=True)
    bmed = np.median(bs, axis=1)
    amed = np.median(as_, axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        pcts = (bmed - amed) / bmed * 100.0
    lo, hi = np.nanpercentile(pcts, list(CI_PCTILES))
    return (pct, float(lo), float(hi))


def yerr(mean: float, lo: float, hi: float):
    """CI as a matplotlib asymmetric ``yerr`` column ``[[down], [up]]``.

    Clamped at zero so floating-point noise cannot hand matplotlib a negative
    error length when the interval collapses onto the point estimate.
    """
    return [[max(0.0, mean - lo)], [max(0.0, hi - mean)]]


def yerr_many(triples):
    """``yerr`` for a sequence of ``(mean, lo, hi)``, as ``[[down...], [up...]]``."""
    down = [max(0.0, m - lo) for m, lo, _ in triples]
    up = [max(0.0, hi - m) for m, _, hi in triples]
    return [down, up]

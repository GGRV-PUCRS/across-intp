#!/usr/bin/env python3
"""ml-ablation.py -- does a richer interference fingerprint classify better?

The scientific spine of Paper 3: a tiered feature ablation that asks whether the
portable metrics and the scheduling-regime pair carry *non-redundant predictive
signal* over the legacy 7-metric fingerprint (Meyer-2021's SVM feature set).

Three feature tiers (from the shared intp_metrics model):
    7   canonical            netp nets blk mbw llcmr llcocc cpu
    13  + portable           + schedlat psi_mem membw_est psi_io schedthr steal
    15  + scheduling-regime  + psp idle_preempt

For each tier it trains the Meyer baseline (RBF-SVM) and a non-linear model
(gradient boosting) under stratified cross-validation, reports balanced-accuracy
/ macro-F1 / AUC, runs McNemar's paired test between adjacent tiers (does adding
the metrics change the *same-fold* predictions significantly?), and ranks the
permutation importance of the metrics in the richest tier (which ones carry the
gain). The decisive Paper-3 result is whether 13 > 7 and 15 > 13.

Labels come from the W5 victim-delta ground truth (contended vs not, or the
4-level interference class). Run on real data:
    python3 bench/ml-ablation.py --data fingerprints.tsv --label-col label --out ablation.md
or validate the pipeline end-to-end on synthetic data where the portable +
scheduling metrics are constructed to carry extra signal:
    python3 bench/ml-ablation.py --synthetic 800 --out /tmp/ablation.md
"""
import argparse
import os
import sys

import numpy as np
import pandas as pd
from scipy.stats import binomtest
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC
from sklearn.metrics import balanced_accuracy_score, f1_score, roc_auc_score
from sklearn.inspection import permutation_importance

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from intp_metrics import METRICS_CANON, METRICS_PORTABLE  # noqa: E402

TIERS = {
    "7 canonical":          list(METRICS_CANON),
    "13 +portable":         list(METRICS_CANON) + list(METRICS_PORTABLE[:6]),
    "15 +sched-regime":     list(METRICS_CANON) + list(METRICS_PORTABLE),
}


def make_synthetic(n, seed=12345):
    """Synthetic fingerprints where a latent contention level is weakly visible
    in the canonical 7 but strongly in membw_est / psi_mem / schedlat / psp /
    idle_preempt -- so a correct harness must show 13 > 7 and 15 > 13."""
    rng = np.random.default_rng(seed)
    c = rng.integers(0, 2, size=n)             # latent: 0 = uncontended, 1 = contended
    cols = {}
    def sig(weak):  # signal + noise; weak channels barely separate the classes
        return c * weak + rng.normal(0, 1.0, n)
    for m in METRICS_CANON:
        cols[m] = sig(0.5)                     # canonical: weak, noisy proxies
    for m in ["schedlat", "psi_mem", "membw_est", "psi_io", "schedthr", "steal"]:
        cols[m] = sig(1.1 if m in ("membw_est", "psi_mem") else 0.7)
    cols["psp"] = sig(1.6)                      # scheduling-regime: strongest channels
    cols["idle_preempt"] = sig(1.4)
    df = pd.DataFrame(cols)
    df["label"] = c
    return df


def load_data(path, label_col):
    # Flat TSV: metric columns (subset of the 15) + a label column. '--' -> NaN.
    df = pd.read_csv(path, sep="\t")
    if label_col not in df.columns:
        sys.exit(f"label column '{label_col}' not in {path} (have: {list(df.columns)})")
    for m in set(sum(TIERS.values(), [])):
        if m in df.columns:
            df[m] = pd.to_numeric(df[m].replace("--", np.nan), errors="coerce")
    return df


def eval_tier(df, feats, label, n_splits, seed):
    feats = [f for f in feats if f in df.columns]
    sub = df.dropna(subset=feats + [label])
    X = sub[feats].to_numpy(dtype=float)
    y = sub[label].to_numpy()
    skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=seed)
    out = {"n": len(y), "k": len(feats), "feats": feats}
    for name, model in (("svm", make_pipeline(StandardScaler(), SVC(kernel="rbf", probability=True, random_state=seed))),
                        ("gbm", GradientBoostingClassifier(random_state=seed))):
        pred = cross_val_predict(model, X, y, cv=skf)
        out[name] = {
            "pred": pred,
            "bal_acc": balanced_accuracy_score(y, pred),
            "f1": f1_score(y, pred, average="macro"),
        }
        try:
            proba = cross_val_predict(model, X, y, cv=skf, method="predict_proba")
            out[name]["auc"] = roc_auc_score(y, proba[:, 1]) if proba.shape[1] == 2 else \
                roc_auc_score(y, proba, multi_class="ovr")
        except Exception:
            out[name]["auc"] = float("nan")
    out["y"] = y
    return out


def mcnemar(y, pred_a, pred_b):
    """Paired test on same-sample predictions: b = a-wrong & b-right, c = a-right
    & b-wrong. Exact binomial on the discordant pairs (robust for small counts)."""
    a_ok, b_ok = (pred_a == y), (pred_b == y)
    b = int(np.sum(~a_ok & b_ok))   # b improves over a
    c = int(np.sum(a_ok & ~b_ok))   # b regresses vs a
    nd = b + c
    p = binomtest(min(b, c), nd, 0.5).pvalue if nd > 0 else 1.0
    return b, c, p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data")
    ap.add_argument("--synthetic", type=int, default=0)
    ap.add_argument("--label-col", default="label")
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--seed", type=int, default=12345)
    ap.add_argument("--out")
    args = ap.parse_args()

    if args.synthetic:
        df, label, src = make_synthetic(args.synthetic, args.seed), "label", f"synthetic(n={args.synthetic})"
    elif args.data:
        df, label, src = load_data(args.data, args.label_col), args.label_col, args.data
    else:
        sys.exit("provide --data <tsv> or --synthetic <N>")

    res = {t: eval_tier(df, feats, label, args.folds, args.seed) for t, feats in TIERS.items()}

    L = []
    L.append(f"# Interference-classification ablation (7 -> 13 -> 15 metrics) — {src}\n")
    L.append(f"Stratified {args.folds}-fold CV; classes={sorted(set(df[label]))}; "
             f"n={res[list(TIERS)[0]]['n']}. Models: SVM (Meyer-2021 baseline) + GBM.\n")
    L.append("| tier (k feats) | SVM bal-acc | SVM F1 | SVM AUC | GBM bal-acc | GBM F1 | GBM AUC |")
    L.append("|---|---|---|---|---|---|---|")
    for t in TIERS:
        r = res[t]
        L.append(f"| {t} ({r['k']}) | {r['svm']['bal_acc']:.3f} | {r['svm']['f1']:.3f} | "
                 f"{r['svm']['auc']:.3f} | {r['gbm']['bal_acc']:.3f} | {r['gbm']['f1']:.3f} | "
                 f"{r['gbm']['auc']:.3f} |")
    L.append("")

    # McNemar between adjacent tiers (GBM out-of-fold predictions on the shared rows).
    L.append("## McNemar (paired, GBM out-of-fold predictions): does the added tier change predictions?\n")
    L.append("| comparison | b (improved) | c (regressed) | p |")
    L.append("|---|---|---|---|")
    order = list(TIERS)
    for a, b in [(order[0], order[1]), (order[1], order[2]), (order[0], order[2])]:
        # align on the rows both tiers scored (they share df after dropna on each
        # tier's feats; for synthetic / fully-numeric data the row sets match).
        ya, yb = res[a]["y"], res[b]["y"]
        if len(ya) == len(yb):
            nb, nc, p = mcnemar(ya, res[a]["gbm"]["pred"], res[b]["gbm"]["pred"])
            L.append(f"| {a} -> {b} | {nb} | {nc} | {p:.4g} |")
        else:
            L.append(f"| {a} -> {b} | (row sets differ: {len(ya)} vs {len(yb)}; align before testing) | | |")
    L.append("")

    # Permutation importance on the richest tier (which metrics carry the gain).
    rich = order[-1]
    feats = res[rich]["feats"]
    sub = df.dropna(subset=feats + [label])
    Xr, yr = sub[feats].to_numpy(dtype=float), sub[label].to_numpy()
    gbm = GradientBoostingClassifier(random_state=args.seed).fit(Xr, yr)
    imp = permutation_importance(gbm, Xr, yr, n_repeats=10, random_state=args.seed)
    rank = sorted(zip(feats, imp.importances_mean), key=lambda x: -x[1])
    L.append(f"## Permutation importance — {rich} (top metrics carrying the signal)\n")
    L.append("| metric | importance |")
    L.append("|---|---|")
    for m, v in rank[:8]:
        L.append(f"| {m} | {v:+.4f} |")
    L.append("")

    report = "\n".join(L)
    if args.out:
        with open(args.out, "w") as fh:
            fh.write(report)
        print(f"[wrote {args.out}]")
    else:
        print(report)


if __name__ == "__main__":
    main()

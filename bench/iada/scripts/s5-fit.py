#!/usr/bin/env python3
"""s5-fit.py -- S16/S5 (jsa-repo-fix-brief), functional-form check.

Regresses log(interference_avg) from the density sweep (s5-density.tsv, tier
B, n=10 per density) on log of the S2 closed form evaluated at each density.

The S2 closed form (decompose-idi.py / validate_jsa.py c16_idi_closed_form,
validated within 4.4% of the actual first interval for every tier) is

    sum over hosts of product over the host's cloudlets of (cost * Hpe / Cpe) / 6

At density d = apps per host = HOST_PES / containerPes = 48 / containerPes,
each occupied host holds d cloudlets of cost ~ geomean_cost (tier B's
geomean from s2-summary.tsv, 1.9261) and Hpe / Cpe = 48 / containerPes = d,
so the per-host product is (g * d)^d, the occupied-host count is
n_cloudlets / d = 28 / d, and the per-interval closed form is

    cf(d) = (28 / d) * (g * d)^d / 6

Densities with interference_avg == 0 (1.0 and 1.5 apps per host) cannot be
logged and are excluded, which the TSV records as n and the excluded rows.
OLS slope/R^2 via the two-pass formulas, no numpy dependency.
"""
import argparse
import math
import statistics as st


def ols(xs, ys):
    n = len(xs)
    mx, my = st.mean(xs), st.mean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    slope = sxy / sxx
    intercept = my - slope * mx
    ss_res = sum((y - (intercept + slope * x)) ** 2 for x, y in zip(xs, ys))
    ss_tot = sum((y - my) ** 2 for y in ys)
    r2 = 1 - ss_res / ss_tot if ss_tot else float("nan")
    # slope SE and 95% CI (n-2 df, t_{0.975} approximated by table for small n)
    t975 = {3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306,
            48: 2.011, 49: 2.010, 50: 2.009}
    df = n - 2
    se = math.sqrt(ss_res / df / sxx) if df > 0 and sxx else float("nan")
    tcrit = t975.get(df, 1.96)
    return slope, intercept, r2, se, (slope - tcrit * se, slope + tcrit * se), n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--density", required=True, help="s5-density.tsv")
    ap.add_argument("--s2-summary", required=True, help="s2-summary.tsv (tier B geomean)")
    ap.add_argument("--out", required=True, help="s5-fit.tsv")
    ap.add_argument("--cloudlets", type=float, default=28.0)
    ap.add_argument("--intervals", type=float, default=6.0)
    args = ap.parse_args()

    gm = None
    for line in open(args.s2_summary):
        p = line.rstrip("\n").split("\t")
        if p[0] == "B":
            gm = float(p[1])
    if gm is None:
        raise SystemExit("no tier B row in s2-summary.tsv")

    rows = []
    with open(args.density) as f:
        hdr = f.readline().rstrip("\n").split("\t")
        for line in f:
            p = line.rstrip("\n").split("\t")
            rows.append(dict(zip(hdr, p)))

    pts, excluded = [], []
    for r in rows:
        cp = float(r["containerPes"])
        d = float(r["apps_per_host"])
        interf = float(r["interference_avg"])
        cf = (args.cloudlets / d) * (gm * d) ** d / args.intervals
        if interf > 0:
            pts.append((cp, d, int(r["rep"]), interf, cf))
        else:
            excluded.append((cp, d))

    xs = [math.log(p[4]) for p in pts]
    ys = [math.log(p[3]) for p in pts]
    slope, intercept, r2, se, ci, n = ols(xs, ys)

    # same regression on per-density means, for the caption-scale statement
    by_d = {}
    for cp, d, rep, interf, cf in pts:
        by_d.setdefault(d, {"i": [], "cf": cf})["i"].append(interf)
    mx = [math.log(v["cf"]) for v in by_d.values()]
    my = [math.log(st.mean(v["i"])) for v in by_d.values()]
    mslope, mintercept, mr2, mse, mci, mn = ols(mx, my)

    with open(args.out, "w") as f:
        f.write("geomean_cost_B\t%.4f\n" % gm)
        f.write("closed_form\t(28/d)*(g*d)^d/6 with d=48/containerPes, g=geomean_cost_B\n")
        f.write("excluded_zero_interference_densities\t%s\n"
                % ",".join(f"{d:g}(cp{int(cp)})" for cp, d in excluded))
        f.write("unit\tslope\tintercept\tr2\tslope_se\tslope_ci95_lo\tslope_ci95_hi\tn\n")
        f.write("per_rep\t%.4f\t%.4f\t%.4f\t%.4f\t%.4f\t%.4f\t%d\n"
                % (slope, intercept, r2, se, ci[0], ci[1], n))
        f.write("per_density_mean\t%.4f\t%.4f\t%.4f\t%.4f\t%.4f\t%.4f\t%d\n"
                % (mslope, mintercept, mr2, mse, mci[0], mci[1], mn))
        f.write("\ncontainerPes\td\tclosed_form\tinterference_avg_mean\tn\n")
        for d in sorted(by_d):
            v = by_d[d]
            f.write("%.0f\t%.4f\t%.4f\t%.4f\t%d\n"
                    % (48.0 / d, d, v["cf"], st.mean(v["i"]), len(v["i"])))

    print(f"per-rep: slope={slope:.3f} (95% CI {ci[0]:.3f} to {ci[1]:.3f}), R^2={r2:.4f}, n={n}")
    print(f"per-density-mean: slope={mslope:.3f} (95% CI {mci[0]:.3f} to {mci[1]:.3f}), R^2={mr2:.4f}, n={mn}")
    print(f"excluded (interference 0, cannot log): {excluded}")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()

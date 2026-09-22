#!/usr/bin/env python3
"""readjudicate-third.py -- S16/R1 (jsa-repo-fix-brief).

Ground-truth re-adjudication on the one-third-footprint host cells, ported
from validate_jsa.py's r1_readjudicate() (which already reproduces the
brief's acceptance numbers: 60/60 in band 0.92-0.99, llcmr rho=0.85 n=70,
membw_est rho=0.81 n=70). This script is the "official" R1 generator the
brief asks for: same logic, but it writes r1-cpu-cells.tsv (one row per
env x variant x workload) and r1-summary.tsv instead of just printing.

Usage: DATA_EXP=<data-exp root> python3 readjudicate-third.py --out $OUT
"""
import argparse
import glob
import os
import statistics as st

from scipy.stats import spearmanr

ENVS = ["bare", "container", "container-podman", "container-lxc", "container-k8s"]
VARIANTS = ["v2.1", "v3.3"]


def load_rows(path):
    hdr, rows = None, []
    for line in open(path, errors="ignore"):
        line = line.rstrip("\n")
        if not line or line.startswith("#"):
            continue
        p = line.split("\t")
        if hdr is None:
            hdr = p if p[0] in ("netp", "ts") else None
            continue
        rows.append(dict(zip(hdr, p[len(p) - len(hdr):])))
    return rows


def med(rows, k):
    v = [float(r[k]) for r in rows if r.get(k) not in (None, "--", "")]
    return st.median(v) if v else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="$OUT directory to write r1-*.tsv into")
    args = ap.parse_args()

    root = os.environ.get("DATA_EXP", "data-exp")
    xd = os.path.join(root, "paper2-extra", "p2-15metric-xdeploy-1of3")

    os.makedirs(args.out, exist_ok=True)
    cells_path = os.path.join(args.out, "r1-cpu-cells.tsv")
    summary_path = os.path.join(args.out, "r1-summary.tsv")

    cpu, llc, mb = [], [], []
    with open(cells_path, "w") as cf:
        cf.write("env\tvariant\tworkload\tn_reps\tcpu_ratio\tllcmr_pred\tllcmr_gt\tmembw_pred\tmembw_gt\n")
        for env in ENVS:
            base = os.path.join(xd, env)
            if not os.path.isdir(base):
                continue
            for var in VARIANTS:
                solo = os.path.join(base, var, "solo")
                if not os.path.isdir(solo):
                    continue
                for wl in sorted(os.listdir(solo)):
                    pc, gc, pl, gl, pm, gm = [], [], [], [], [], []
                    n_reps = 0
                    for rep in glob.glob(os.path.join(solo, wl, "rep*")):
                        P = load_rows(rep + "/portable.tsv")
                        G = load_rows(rep + "/groundtruth.tsv")[1:]  # drop first row (counter warm-up)
                        if not P or not G:
                            continue
                        n_reps += 1
                        pc.append(med(P, "cpu"))
                        gc.append(med(G, "cpu_busy_pct"))
                        lr = [float(g["llc_miss"]) / float(g["llc_ref"]) * 100
                              for g in G if g["llc_ref"] not in ("--", "0")]
                        if lr:
                            gl.append(st.median(lr))
                            pl.append(med(P, "llcmr"))
                        lm = [float(g["llc_miss"]) for g in G if g["llc_miss"] != "--"]
                        if lm:
                            gm.append(st.median(lm))
                            pm.append(med(P, "membw_est"))

                    row_cpu_ratio = ""
                    if pc and st.median(gc) > 5:
                        ratio = st.median(pc) / st.median(gc)
                        cpu.append(ratio)
                        row_cpu_ratio = f"{ratio:.4f}"
                    row_llcmr_pred = row_llcmr_gt = row_membw_pred = row_membw_gt = ""
                    if pl:
                        p_llc, g_llc = st.median(pl), st.median(gl)
                        p_mb, g_mb = st.median(pm), st.median(gm)
                        llc.append((p_llc, g_llc))
                        mb.append((p_mb, g_mb))
                        row_llcmr_pred, row_llcmr_gt = f"{p_llc:.4f}", f"{g_llc:.4f}"
                        row_membw_pred, row_membw_gt = f"{p_mb:.4f}", f"{g_mb:.4f}"
                    if n_reps:
                        cf.write(f"{env}\t{var}\t{wl}\t{n_reps}\t{row_cpu_ratio}\t"
                                 f"{row_llcmr_pred}\t{row_llcmr_gt}\t{row_membw_pred}\t{row_membw_gt}\n")

    inb = sum(0.8 <= r <= 1.25 for r in cpu)
    llcmr_rho = spearmanr(*zip(*llc)).statistic
    membw_rho = spearmanr(*zip(*mb)).statistic

    with open(summary_path, "w") as sf:
        sf.write("metric\tvalue\n")
        sf.write(f"cpu_in_band\t{inb}\n")
        sf.write(f"cpu_total\t{len(cpu)}\n")
        sf.write(f"cpu_ratio_min\t{min(cpu):.4f}\n")
        sf.write(f"cpu_ratio_max\t{max(cpu):.4f}\n")
        sf.write(f"llcmr_rho\t{llcmr_rho:.4f}\n")
        sf.write(f"llcmr_n\t{len(llc)}\n")
        sf.write(f"membw_est_rho\t{membw_rho:.4f}\n")
        sf.write(f"membw_est_n\t{len(mb)}\n")

    print(f"R1: {inb}/{len(cpu)} cpu cells in band [{min(cpu):.2f}, {max(cpu):.2f}], "
          f"llcmr rho={llcmr_rho:.2f} n={len(llc)}, membw_est rho={membw_rho:.2f} n={len(mb)}")
    print(f"wrote {cells_path}")
    print(f"wrote {summary_path}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""plot-graphical-abstract-jsa.py -- the JSA graphical abstract
(graphical-abstract-JSA.pdf / .png, 3984 x 1592 px, ratio 2.5).

A title, one subtitle and a compact availability panel: three deployment
columns (bare metal, containers, KVM guest) by three metric families
(hardware-backed canonical, software canonical, portable). It reads the same
input as Fig. 1 (fig:availability) through plot-fig2-3-4-6-8-jsa.py's own
loaders (scan_cells / scan_backend_status, imported via importlib: that
filename is not a valid module name), so the two cannot disagree. No metric
identifiers, variant names or internal environment ids are printed.

Each family cell holds one unlabeled square per metric. A column pools both
profiler variants and every environment it stands for (DECISIONS.md D21):

  unavailable           no variant reads the metric in any of the column's
                        environments;
  available             every variant reads it from its own backend in every
                        environment;
  through a proxy       otherwise, provided every reading that is not native
                        is a substitute-backend (PROXY) reading, e.g. the v2.1
                        llcocc miss-ratio fallback in the KVM guest. Any other
                        mix stops the script rather than picking a state.

    python3 bench/plot/plot-graphical-abstract-jsa.py \\
        results/p2-15metric-xdeploy-1of3 --out figs
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
import textwrap
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jsa_style as style  # noqa: E402

_PLOT_DIR = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location(
    "plot_fig23468_jsa", _PLOT_DIR / "plot-fig2-3-4-6-8-jsa.py")
avail = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(avail)

TITLE = "Interference profiling across deployment environments"
# One subtitle, wrapped into two balanced lines: on a single line it would
# print below 4 pt at the 13 cm width the journal displays the abstract at.
SUBTITLE = ("Containers preserve the profiler's measurements. Inside a KVM "
            "guest, cache and bandwidth monitoring is unavailable, and "
            "portable software metrics still detect a noisy neighbor.")

COLUMNS = [
    ("bare metal", "", ["bare"]),
    ("containers", "Docker, Podman, Incus, k3s",
     ["container", "container-podman", "container-lxc", "container-k8s"]),
    ("KVM guest", "", ["vm-guest"]),
]
FAMILIES = [
    ("hardware-backed\ncanonical metrics", ["mbw", "llcocc", "llcmr"]),
    ("software\ncanonical metrics", ["netp", "nets", "blk", "cpu"]),
    ("portable metrics", ["schedlat", "psi_mem", "membw_est", "psi_io",
                          "schedthr", "steal"]),
]

AVAILABLE, PROXY, UNAVAILABLE = "available", "proxy", "unavailable"
STATE_STYLE = {
    AVAILABLE: dict(facecolor=style.BLUISH_GREEN, hatch=None),
    PROXY: dict(facecolor=style.BLUISH_GREEN, hatch="...."),
    UNAVAILABLE: dict(facecolor=style.GREY, hatch="////"),
}
STATE_LABEL = {AVAILABLE: "available", PROXY: "available through a proxy",
               UNAVAILABLE: "unavailable"}

WIDTH_PX, HEIGHT_PX, DPI = 3984, 1592, 300


def metric_state(cells, status, envs, variants, metric) -> str:
    """Pooled state of one metric over a column's environments and variants."""
    reads = []
    for env in envs:
        for var in variants:
            reps = cells.get(env, {}).get(var, [])
            ok = any(metric in r for r in reps)
            st = status.get((env, var), {}).get(
                metric, "OK" if ok else "UNAVAILABLE")
            reads.append("PROXY" if ok and st == "PROXY"
                         else "OK" if ok else "UNAVAILABLE")
    if all(r == "UNAVAILABLE" for r in reads):
        return UNAVAILABLE
    if all(r == "OK" for r in reads):
        return AVAILABLE
    if "PROXY" in reads:
        return PROXY
    raise SystemExit(f"{metric} in {envs}: mixed native/absent readings "
                     f"{sorted(set(reads))}; no aggregation rule covers it")


def draw(fig, states) -> None:
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, WIDTH_PX)
    ax.set_ylim(0, HEIGHT_PX)
    ax.axis("off")

    ax.text(WIDTH_PX / 2, 1500, TITLE, ha="center", va="center",
            fontsize=25, fontweight="bold")
    lines = textwrap.wrap(SUBTITLE, width=len(SUBTITLE) // 2 + 2)
    ax.text(WIDTH_PX / 2, 1300, "\n".join(lines), ha="center", va="center",
            fontsize=16, color="#333333", linespacing=1.35)

    label_x = 330
    col_x0, col_w, col_gap = 1000, 860, 80
    row_y0, row_h, row_gap = 980, 230, 40
    sq, sq_gap = 96, 22

    for ci, (name, sub, _envs) in enumerate(COLUMNS):
        cx = col_x0 + ci * (col_w + col_gap) + col_w / 2
        ax.text(cx, row_y0 + 75, name, ha="center", va="bottom",
                fontsize=18, fontweight="bold")
        if sub:
            ax.text(cx, row_y0 + 22, sub, ha="center", va="bottom",
                    fontsize=14, color="#555555")

    for ri, (fam, metrics) in enumerate(FAMILIES):
        top = row_y0 - ri * (row_h + row_gap)
        cy = top - row_h / 2
        ax.text(label_x, cy, fam, ha="center", va="center", fontsize=16,
                linespacing=1.15)
        for ci in range(len(COLUMNS)):
            x0 = col_x0 + ci * (col_w + col_gap)
            ax.add_patch(plt.Rectangle((x0, top - row_h), col_w, row_h,
                                       facecolor="#f4f4f4", edgecolor="none"))
            n = len(metrics)
            span = n * sq + (n - 1) * sq_gap
            sx = x0 + (col_w - span) / 2
            for k, m in enumerate(metrics):
                ax.add_patch(plt.Rectangle(
                    (sx + k * (sq + sq_gap), cy - sq / 2), sq, sq,
                    edgecolor="white", linewidth=1.5,
                    **STATE_STYLE[states[(ci, m)]]))

    # legend: one row under the panel, laid out from measured text widths
    # and centered on the page
    renderer = fig.canvas.get_renderer()
    leg_y, key, pad, sep, fs = 95, 60, 25, 70, 15
    items = [(None, "one square per metric:")] + [
        (st, STATE_LABEL[st]) for st in (AVAILABLE, PROXY, UNAVAILABLE)]
    placed, x = [], 0.0
    for state, label in items:
        t = ax.text(0, leg_y, label, ha="left", va="center", fontsize=fs,
                    color="black" if state else "#555555")
        tw = t.get_window_extent(renderer).width  # 1 px = 1 data unit
        kx = None
        if state:
            kx, x = x, x + key + pad
        placed.append((t, state, kx, x))
        x += tw + sep
    shift = (WIDTH_PX - (x - sep)) / 2
    for t, state, kx, tx in placed:
        t.set_x(tx + shift)
        if state:
            ax.add_patch(plt.Rectangle(
                (kx + shift, leg_y - key / 2), key, key, edgecolor="white",
                linewidth=1.5, **STATE_STYLE[state]))

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("campaign_dir", type=Path,
                    help="01-tier-a-cross-deployment (the Fig. 1 input)")
    ap.add_argument("--out", type=Path, required=True,
                    help="directory for graphical-abstract-JSA.{pdf,png}")
    args = ap.parse_args()

    style.apply()
    plt.rcParams["hatch.linewidth"] = 1.6
    flat = avail.scan_cells(args.campaign_dir)
    status = avail.scan_backend_status(args.campaign_dir)
    cells: dict[str, dict[str, list]] = {}
    for (env, var, _wl), reps in flat.items():
        cells.setdefault(env, {}).setdefault(var, []).extend(reps)
    variants = sorted({var for (_e, var, _w) in flat})

    states = {}
    for ci, (_name, _sub, envs) in enumerate(COLUMNS):
        missing = [e for e in envs if e not in cells]
        if missing:
            sys.exit(f"no captures for {missing} under {args.campaign_dir}")
        for _fam, metrics in FAMILIES:
            for m in metrics:
                states[(ci, m)] = metric_state(cells, status, envs, variants, m)

    fig = plt.figure(figsize=(WIDTH_PX / DPI, HEIGHT_PX / DPI), dpi=DPI)
    draw(fig, states)
    args.out.mkdir(parents=True, exist_ok=True)
    for ext in ("pdf", "png"):
        path = args.out / f"graphical-abstract-JSA.{ext}"
        fig.savefig(path, dpi=DPI)
        print(f"wrote {path}")
    plt.close(fig)
    for ci, (name, _sub, _envs) in enumerate(COLUMNS):
        row = "; ".join(
            f"{fam.replace(chr(10), ' ')}: " + " ".join(
                {AVAILABLE: "A", PROXY: "P", UNAVAILABLE: "U"}[states[(ci, m)]]
                for m in metrics)
            for fam, metrics in FAMILIES)
        print(f"  {name}: {row}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""plot-fig-arch.py -- the JSA architecture figure (fig:arch).

Hand-drawn schematic, not data-driven: there is no campaign TSV behind this
figure, so unlike every other renderer in this directory it takes no
--dataset. It replaces the "FIGURE TO BE DRAWN" placeholder in main-jsa.tex
and shows, left to right:

  1. the attribution path: a workload is scoped to a cgroup, and the same
     per-cgroup profiler code path serves bare processes, every container
     engine, and (as a boundary) the KVM guest, which the host can only see
     as one opaque process;
  2. the 15-metric fingerprint, grouped as canonical-7 / portable-6 /
     regime-2, matching the grouping already in the manuscript's
     sec:design:fingerprint;
  3. the offline path from the profiler's per-second output into the
     interference classifier and its three CloudSimInterference
     configurations (canonical-7, proxy-swap, full-fingerprint). The
     classifier, simulator and scheduling stages sit in a dashed enclosure
     labelled "context, not evaluated": the JSA article validates the
     per-second stream only (D20).

Usage: python3 plot-fig-arch.py --out /path/to/Figure_1.pdf
"""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

import jsa_style as style


def box(ax, xy, w, h, text, *, fc="white", ec=style.BLACK, ls="-", lw=0.8,
        fontsize=None, fontweight="normal", zorder=2, text_color="black"):
    x, y = xy
    patch = FancyBboxPatch(
        (x, y), w, h,
        boxstyle="round,pad=0.006,rounding_size=0.010",
        facecolor=fc, edgecolor=ec, linewidth=lw, linestyle=ls, zorder=zorder)
    ax.add_patch(patch)
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center",
             fontsize=fontsize or style.BODY, fontweight=fontweight,
             color=text_color, zorder=zorder + 1, wrap=True)
    return patch


def arrow(ax, p0, p1, *, color=style.BLACK, lw=0.9, style_="-|>",
          connectionstyle="arc3,rad=0.0", zorder=1.5):
    ax.add_patch(FancyArrowPatch(
        p0, p1, arrowstyle=style_, mutation_scale=7, linewidth=lw,
        color=color, connectionstyle=connectionstyle, zorder=zorder,
        shrinkA=1, shrinkB=1))


def draw(ax) -> None:
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    # ---- column boundaries -------------------------------------------
    col1_x0, col1_x1 = 0.005, 0.305
    col2_x0, col2_x1 = 0.335, 0.615
    col3_x0, col3_x1 = 0.650, 0.995

    ax.text((col1_x0 + col1_x1) / 2, 0.975, "Attribution path", ha="center",
             va="top", fontsize=style.LEGEND, fontweight="bold")
    ax.text((col2_x0 + col2_x1) / 2, 0.975, "15-metric fingerprint",
             ha="center", va="top", fontsize=style.LEGEND, fontweight="bold")
    ax.text((col3_x0 + col3_x1) / 2, 0.975, "Offline scheduling loop",
             ha="center", va="top", fontsize=style.LEGEND, fontweight="bold")

    # ==================================================================
    # Column 1: attribution path
    # ==================================================================
    cx = (col1_x0 + col1_x1) / 2
    inset = col1_x0 + 0.05, col1_x1 - 0.05
    bw = inset[1] - inset[0]
    box(ax, (inset[0], 0.855), bw, 0.075, "workload", fc="white")
    box(ax, (inset[0], 0.740), bw, 0.075, "cgroup",
        fc=style.SKY_BLUE + "33", ec=style.SKY_BLUE)
    arrow(ax, (cx, 0.855), (cx, 0.815))

    box(ax, (inset[0], 0.600), bw, 0.10,
        "bare · Docker · Podman ·\nIncus/LXC · k3s",
        fc=style.BLUISH_GREEN + "22", ec=style.BLUISH_GREEN,
        fontsize=style.ANNOT - 1.0)
    arrow(ax, (cx, 0.740), (cx, 0.700))

    box(ax, (inset[0], 0.470), bw, 0.085, "profiler\n(per-cgroup)",
        fc=style.ORANGE + "33", ec=style.ORANGE, fontsize=style.ANNOT)
    arrow(ax, (cx, 0.600), (cx, 0.555))
    bridge_y = 0.470 + 0.085 / 2  # vertical center of the profiler box

    # KVM guest: the host's profiler only sees the guest as one process;
    # only in-guest instrumentation can see inside it. Generous vertical
    # room throughout so nothing collides with the dashed border.
    guest_y0, guest_h = 0.075, 0.355
    box(ax, (col1_x0 + 0.03, guest_y0), col1_x1 - col1_x0 - 0.06, guest_h,
        "", fc="#eeeeee", ec=style.BLACK, ls="--", lw=1.0)
    ax.text(col1_x0 + 0.05, guest_y0 + guest_h - 0.030, "KVM guest",
             ha="left", va="top", fontsize=style.ANNOT, fontweight="bold")
    ax.text(col1_x0 + 0.05, guest_y0 + guest_h - 0.078,
             "host profiler sees one\nprocess, not inside it",
             ha="left", va="top", fontsize=style.ANNOT - 0.7,
             style="italic", color="#444444")
    profiler_box_y0 = guest_y0 + guest_h - 0.235
    box(ax, (inset[0] + 0.01, profiler_box_y0), bw - 0.02, 0.075,
        "in-guest profiler", fc=style.ORANGE + "33", ec=style.ORANGE,
        fontsize=style.ANNOT - 0.5)
    arrow(ax, (cx, 0.470), (cx, guest_y0 + guest_h), lw=0.8)
    ax.text(cx, (guest_y0 + profiler_box_y0) / 2,
             "RDT unavailable in-guest",
             ha="center", va="center", fontsize=style.ANNOT - 1.0,
             color=style.VERMILLION, style="italic")

    # Bridge to column 2: the profiler's output is exactly the fingerprint
    # column 2 details, so the arrow lands on that stack's vertical center.
    # Geometry must match the group-box loop below exactly (row_h/gap/
    # head_pad and the 7/6/2-metric group sizes), so it is computed once
    # here and reused by both this arrow and the column-3 bridge arrow.
    row_h, gap, head_pad = 0.0385, 0.020, 0.052
    group_sizes = (7, 6, 2)
    fp_top = 0.90
    fp_bottom = fp_top - sum(row_h * n + head_pad for n in group_sizes) \
        - gap * (len(group_sizes) - 1)
    fp_center = (fp_top + fp_bottom) / 2
    arrow(ax, (col1_x1, bridge_y), (col2_x0, fp_center), lw=1.0,
          color=style.BLACK, connectionstyle="arc3,rad=0.15")

    # ==================================================================
    # Column 2: 15-metric fingerprint, grouped
    # ==================================================================
    groups = [
        ("canonical 7", style.ORANGE,
         ["netp", "nets", "blk", "mbw", "llcmr", "llcocc", "cpu"]),
        ("portable 6", style.SKY_BLUE,
         ["schedlat", "psi_mem", "membw_est", "psi_io", "schedthr", "steal"]),
        ("regime 2", style.BLUISH_GREEN,
         ["psp", "idle_preempt"]),
    ]
    y = fp_top
    for title, color, metrics in groups:
        gh = row_h * len(metrics) + head_pad
        box(ax, (col2_x0, y - gh), col2_x1 - col2_x0, gh, "",
            fc=color + "18", ec=color, lw=1.0)
        ax.text(col2_x0 + 0.016, y - 0.026, title, ha="left", va="top",
                 fontsize=style.ANNOT, fontweight="bold", color=color)
        for j, m in enumerate(metrics):
            my = y - head_pad - (j + 0.58) * row_h
            ax.text(col2_x0 + 0.035, my, m, ha="left", va="center",
                     fontsize=style.ANNOT - 0.5, family="monospace")
        y = y - gh - gap

    # Bridge to column 3: the fingerprint IS what profiler.tsv carries, so
    # curve up to that box specifically rather than pointing at empty space.
    tsv_cy = 0.85 + 0.075 / 2
    arrow(ax, (col2_x1, fp_center), (col3_x0, tsv_cy), lw=1.0)

    # ==================================================================
    # Column 3: offline path
    # ==================================================================
    tsv = box(ax, (col3_x0 + 0.02, 0.85), col3_x1 - col3_x0 - 0.04, 0.075,
                "profiler.tsv\n(per-second)", fc="white", fontsize=style.ANNOT)

    # Everything below profiler.tsv is downstream context: the article
    # validates the per-second stream, not the classifier or the simulator
    # (D20). Dashed enclosure + dashed box edges mark that region.
    ax.add_patch(FancyBboxPatch(
        (col3_x0 + 0.004, 0.035), 0.999 - col3_x0 - 0.008, 0.800,
        boxstyle="round,pad=0.004,rounding_size=0.012",
        facecolor="none", edgecolor="#777777", linewidth=0.8,
        linestyle=(0, (3, 2)), zorder=1))
    ax.text(0.988, 0.828, "context,\nnot evaluated",
             ha="right", va="top", fontsize=style.ANNOT - 0.5,
             style="italic", color="#555555", zorder=3)
    ctx_ls = (0, (3, 2))

    arrow(ax, ((col3_x0 + col3_x1) / 2, 0.85),
          ((col3_x0 + col3_x1) / 2, 0.735))
    clf = box(ax, (col3_x0 + 0.02, 0.66), col3_x1 - col3_x0 - 0.04, 0.075,
               "interference\nclassifier", fc=style.REDDISH_PURPLE + "33",
               ec=style.REDDISH_PURPLE, ls=ctx_ls, fontsize=style.ANNOT)

    tiers = [
        ("canonical-7", style.ORANGE),
        ("proxy-\nswap", style.SKY_BLUE),
        ("full-\nfingerprint", style.BLUISH_GREEN),
    ]
    tw = (col3_x1 - col3_x0 - 0.06) / 3
    ty = 0.44
    for i, (name, color) in enumerate(tiers):
        tx = col3_x0 + 0.02 + i * (tw + 0.02)
        box(ax, (tx, ty), tw, 0.09, name, fc=color + "22", ec=color,
            ls=ctx_ls, fontsize=style.ANNOT - 1.0)
        arrow(ax, ((col3_x0 + col3_x1) / 2, 0.66), (tx + tw / 2, ty + 0.09),
              lw=0.6)

    sim = box(ax, (col3_x0 + 0.02, 0.235), col3_x1 - col3_x0 - 0.04, 0.075,
               "CloudSimInterference\n(closed-loop placement)", fc="white",
               ls=ctx_ls, fontsize=style.ANNOT - 0.5)
    for i in range(3):
        tx = col3_x0 + 0.02 + i * (tw + 0.02)
        arrow(ax, (tx + tw / 2, ty), ((col3_x0 + col3_x1) / 2, 0.31), lw=0.6)

    arrow(ax, ((col3_x0 + col3_x1) / 2, 0.235),
          ((col3_x0 + col3_x1) / 2, 0.13))
    box(ax, (col3_x0 + 0.02, 0.055), col3_x1 - col3_x0 - 0.04, 0.075,
        "scheduling decision", fc="#eeeeee", ls=ctx_ls,
        fontsize=style.ANNOT - 0.5)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="output PDF path")
    ap.add_argument("--png", default=None,
                     help="optional sibling PNG path (deck use)")
    args = ap.parse_args()

    style.apply()
    fig, ax = plt.subplots(figsize=(style.TEXT_WIDTH, 3.4))
    ax.grid(False)
    draw(ax)

    out = Path(args.out)
    spec = style.FigSpec(style.TEXT_WIDTH, 3.4, "fig:arch")
    w, h = style.save(fig, out, spec)
    print(f"wrote {out} ({w:.2f} x {h:.2f} in)")
    if args.png:
        fig.savefig(args.png, dpi=300, bbox_inches="tight")
        print(f"wrote {args.png}")
    plt.close(fig)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

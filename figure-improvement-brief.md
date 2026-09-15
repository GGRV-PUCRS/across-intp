# Figure improvement brief for the JSA submission

Purpose: hand this brief to the code agent that will rework the figures of `main-jsa.tex` ("Environment-Aware Cross-Application Interference Profiling and Its Implications on Dynamic Scheduling", Journal of Systems Architecture). Goal: reviewer-grade readability at final print size, and a small set of new figure options where the current art undersells the result.

## Ground rules

- Keep every data value exactly as in the frozen campaign archive (manifest dated 2026-06-16). Redraw, never recompute silently; if a redraw changes any number, flag it.
- Output format: vector PDF, one file per figure, same filenames under `figs/` so the .tex needs no changes. If a figure is split or replaced by a new option, keep the old file and add the new one with a suffix (for example `Figure_6_v2.pdf`), and list the suggested `\label`/caption pairing.
- Target sizes: single column about 252 pt wide (3.5 in), full width about 516 pt (7.16 in). Figures must be legible at those widths: axis and tick labels at least 7 pt equivalent after scaling, line weights at least 0.6 pt, no rasterized text.
- Color: colorblind-safe palette (Okabe-Ito). Never encode information by red/green alone; add marker or hatch differences. Grey is reserved for unavailable/unsupported cells.
- Fonts: match the manuscript (Computer Modern or a neutral sans like Helvetica/Source Sans). No mixed font families inside one figure.
- Every figure must stand alone: units on axes, variant names spelled out (v2.1, v3.3) rather than internal codenames, and no internal repository labels anywhere (no W4/W5, F-numbers, Tier-A/B/C, C-numbers, E-numbers). Use the descriptive names from the paper: cross-deployment campaign, colocation campaign, cadence sweep, real applications, microservices, overhead.

## Current inventory and readability assessment

| file | role in the paper | assessment and required fixes |
|---|---|---|
| Figure_2.pdf | Metric availability matrix per environment and variant | Wide and flat (972x327 pt). Cells likely small at full width. Increase cell size, rotate environment labels 30-45 degrees, spell out metric names in a side legend. |
| Figure_8.pdf | Claim class per deployment and metric | Similar matrix problem. Add a caption-independent legend for shading intensity. |
| Figure_3.pdf | PSI bandwidth-blindness (psi_mem flat at 0 under saturation) | Two-panel or overlaid design suggested so the flat PSI line and the saturated bandwidth are on comparable scales; add an annotated callout "saturation point". |
| Figure_4.pdf | membw_est versus ground-truth traffic, log-log | Add the rho values inside the plot area, mark the identity line, distinguish v2.1/v3.3 with shape plus color. |
| Figure_5.pdf | Overhead versus cadence | Very small source (242x178 pt); will pixelate or look cramped. Regenerate at full size with error bars visible, add the 2.5 percent budget line. |
| Figure_6.pdf | Absolute ratio to bare metal with bootstrap CIs | Core faithfulness figure. Ensure the 0.8 to 1.25 equivalence corridor is shaded and labeled inside the plot, not only in the caption. |
| Figure_7.pdf | Faithfulness against ground truth (CPU 20/20, llcmr rank only) | Short and wide (511x162 pt). Consider merging with Figure_6 as a two-panel figure if space is tight. |
| F6-involuntary-preemptions...pdf | psp preemption deltas per deployment | Filename carries internal labels; content is fine. Consider log scale given the 33008 to 420922 range. |
| Figure_9.pdf | app10_search distributions under v2.1 after the fix | Multi-panel; check per-panel titles stay readable at full width. |
| Figure_12.pdf | In-guest portable proxy versus missing canonical mbw | Key W5 result. Emphasize the guest panel; consider a paired before/after axis. |
| Figure_11.pdf | Victim shift under noisy neighbour (Cliff's delta forest) | Ensure delta=1.0 cells are visually distinct (they saturate). |
| Figure_10.pdf | Victim-delta forest across workloads | Largest figure (1408x740 pt). Candidate for splitting into two stacked panels if reviewers print in grayscale. |
| Figure_13.pdf | 15-metric fingerprint per workload across the stack | Grey marks unavailable metrics; verify the grey is distinguishable from low-value cells in print. |
| fig:tiers figure (Figure for classifier configurations) | Closed-loop IDI per classifier configuration | Rename any on-figure tier labels to canonical-7, proxy-swap, full-fingerprint. |
| Figure_A1.pdf | Host-count sweep flatness (appendix) | Tiny source (254x164 pt). Regenerate. |
| Figure_A2.pdf | JDK equivalence check (appendix) | Tiny source (278x140 pt). Regenerate. |
| Figure_A3.pdf | app10_search distributions under v3.3 (appendix) | Keep paired layout with Figure_9 for side-by-side comparison. |
| F8-*.pdf (two files) | Cadence fidelity curve and per-metric loss | Merge into one two-panel figure if possible; the two currently separate pages waste space. |

## Missing figure: architecture (fig:arch placeholder)

The paper currently has a "FIGURE TO BE DRAWN" box for the architecture figure. Priority one. Content it must show: the per-cgroup attribution path (workload to cgroup to profiler), the five container-side environments plus the KVM guest as an opaque boundary, the 15-metric fingerprint grouped as canonical 7, portable 6, regime 2, and the offline path from profiler.tsv into the interference-classifier and CloudSimInterference forks. Draw as vector (TikZ, Inkscape, or matplotlib-free diagram tooling), one full-width figure, colorblind-safe.

## New figure options worth generating

1. Pipeline schematic of the experiment automation (ub22run/ub24run and containerun24 into run-big-batch, analyzers, figures), for the reproducibility subsection. Simple left-to-right flow, no screenshots of terminals.
2. Campaign overview table-as-figure is not needed; instead a compact timeline-style graphic of the six campaigns with cell counts would help reviewers grasp scale quickly.
3. A combined "transfer gate" visual: within-domain accuracy versus host-to-VM transfer accuracy per classifier configuration, bars with the memory-class recall annotated. Currently this is only a table.
4. Optional: small multiples of the fingerprint heatmap per deployment (bare, container, guest) if the single stacked version reads poorly in grayscale.

## Acceptance check

Recompile `main-jsa.tex` with tectonic after the rework; confirm no undefined references, no new overfull boxes from figure widths, and visually inspect each page at 100 percent zoom assuming a printed A4 page.

## Caption policy update (2026-09-15)

The manuscript captions have been rewritten to be self-contained: each caption now states what the figure shows, the axes and encodings, the campaign and cell counts behind it, and the headline reading. Therefore, when reworking the figures, strip verbose in-figure titles, subtitle lines, and footer notes. Keep only what the reader needs to decode the marks: axis labels with units, tick labels, legends (only when direct labeling is impossible), and in-plot annotations that carry data (for example the rho values in Figure_4 and the 2.5 percent budget line in Figure_5). Anything that merely restates the result belongs in the caption, not inside the figure. Panel titles inside multi-panel figures (Figure_9, Figure_A3) should keep only the statistical outcome per panel, in short form (for example "KW p<0.01"), not sentence-long headers.

#!/usr/bin/env python3
"""fig_names.py -- the one place that decides what a rendered figure is called.

Every renderer under ``bench/plot/`` used to name its output after the internal
stem it happened to use (``F1-ratio-vs-bare``, ``fig04b_overhead_cpu_jiffies``).
Those read fine next to the code that wrote them and not at all anywhere else:
dragged into a slide deck, mailed to the advisor, or opened six months later in
a folder of nine hundred figures, ``fig04b`` says nothing about what is in it or
which campaign produced it. This module turns the stem into a name that carries
both::

    <figure-id>-<what-the-figure-shows>--<which-campaign>.<ext>

    F1-absolute-metric-ratio-versus-bare-metal--tier-a-cross-deployment.png
    fig04b-profiler-extra-system-cpu-time--ubuntu22+24-all-variants.pdf

The **figure id** is the stem's own number, kept because ``docs/FIGURES-PLAN.md``,
the reports under ``docs/reports/`` and the paper drafts all cite figures by it;
a figure the pipeline never numbered simply starts with its description. The
**description** is the figure's own title, compressed to a slug. The **campaign
tag** is the measurement session the data came from, so a file that leaves the
tree still says what it is evidence of.

The stem stays the internal key -- ``paper_style.spec_for`` and
``sa_style.spec_for`` are still keyed by it, and so is this module's registry.
Only the bytes on disk change.

Adding a figure: add its stem to ``FIGURES``. A stem that is missing raises
rather than falling back to itself, so a new figure cannot quietly ship under an
un-reviewed name.
"""
from __future__ import annotations

import re
from pathlib import Path

__all__ = ["FIGURES", "DATASETS", "SA_DATASET", "figure_id", "describe",
           "dataset_tag", "head", "name", "phrase", "slug", "add_dataset_arg",
           "split_suffix"]


# ---------------------------------------------------------------------------
# What each figure shows. Keys are renderer stems; values are the figure's own
# title, slugged. Grouped by the renderer that owns them.
# ---------------------------------------------------------------------------

FIGURES: dict[str, str] = {
    # --- plot-intp-bench.py: cross-variant comparison over stress-ng --------
    "fig00_canonical_intp_fig4":      "per-application-interference-ratios",
    "fig01_per_workload_bars":        "per-workload-metric-fingerprint",
    "fig01b_per_variant_bars":        "per-variant-workload-fingerprint",
    "fig02_pca_kmeans":               "pca-kmeans-workload-clustering",
    "fig03_timeseries":               "long-trace-interference-profile",
    "fig04_overhead_throughput":      "profiler-induced-workload-slowdown",
    "fig04b_overhead_cpu_jiffies":    "profiler-extra-system-cpu-time",
    "fig04c_overhead_sched_switch":   "profiler-extra-context-switches",
    "fig05_fidelity_matrix":          "profiler-vs-ground-truth-pearson-r",
    "fig06_env_heatmap":              "metric-ratio-across-environments",
    "fig07_pairwise_heatmap":         "pairwise-colocation-interference-signal",
    "fig08_metric_availability":      "metric-availability-per-variant",
    "fig09_radar_fingerprint":        "per-workload-radar-fingerprint",
    "fig10_workload_clustermap":      "hierarchical-workload-clustermap",
    "fig11_idi_bars":                 "interference-discrimination-index-by-resource",
    "fig12_pairwise_timeseries":      "resource-family-trace-under-mixed-load",
    "fig13_iada_segmented":           "segmented-loess-interference-trace",
    "fig14_variant_resource_heatmap": "variant-by-resource-family-heatmap",

    # --- plot-hibench.py: the same comparison over the Spark profiles -------
    "fig00_hibench_canonical_intp_fig4":
        "hibench-interference-ratios-per-workload",
    "fig01_fingerprint":              "hibench-metric-fingerprint",
    "fig02_sensitivity":              "hibench-sensitivity-to-co-runner-pressure",
    "fig03_metric_compare":           "hibench-per-profile-variant-comparison",
    "fig04_per_workload_bars":        "hibench-per-workload-variant-fingerprint",
    "fig05_radar_fingerprint":        "hibench-per-workload-radar-fingerprint",
    "fig06_pca_workloads":            "hibench-workloads-in-pca-space",
    "fig07_timeseries":               "hibench-metric-timeseries",
    "fig08_hibench_coverage":         "hibench-metric-coverage-per-variant",
    "fig08_idi_bars":                 "hibench-resource-sensitivity-to-network-interference",
    "fig09_resource_timeseries":      "hibench-resource-family-timeseries",
    "fig10_variant_resource_heatmap": "hibench-variant-by-resource-family-heatmap",
    "fig11_metric_availability":      "hibench-metric-availability-per-variant",
    "fig12_workload_clustermap":      "hibench-hierarchical-workload-clustermap",

    # --- the PCA pair, over the canonical seven metrics ---------------------
    "fig_pca_correlation_circle":     "correlation-circle-of-variants-in-metric-space",
    "fig02_pca_dendro":               "pca-and-ward-dendrogram-of-workload-clusters",

    # --- cross-variant-correlation.py --------------------------------------
    "correlation-heatmap":            "cross-variant-fingerprint-correlation",

    # --- plot-aux-rerun.py: what the eBPF endpoints read when idle ----------
    "noise-floor-distribution":       "profiler-noise-floor-distribution-while-idle",
    "noise-floor-timeseries":         "profiler-noise-floor-time-series-while-idle",
    "noise-floor-compare":            "profiler-noise-floor-ebpf-ring-vs-ebpf-core",
    "exp5-sched-switch":              "context-switch-counter-vs-vmstat-ground-truth",

    # --- plot-p2-15metric.py: Tier-A cross-deployment portability -----------
    "F0-fingerprint-heatmap":         "15-metric-interference-fingerprint-across-deployments",
    "F1-ratio-vs-bare":               "absolute-metric-ratio-versus-bare-metal",
    "F2-claim-class-matrix":          "claim-class-per-deployment-and-metric",
    "F3-availability-grid":           "metric-availability-across-the-deployment-stack",
    "F4-membw-validation":            "estimated-memory-bandwidth-tracks-true-memory-traffic",
    "F5-psi-bandwidth-blindness":     "psi-memory-pressure-cannot-see-bandwidth-saturation",
    "F6-psp-directional":             "involuntary-preemptions-per-second-by-deployment",

    # --- the same PCA pair over the cross-deployment campaign ---------------
    # Both still project the canonical seven metrics: plot-pca-correlation-
    # circle.py's --features and plot_pca_dendro.py's METRICS default to them.
    # docs/FIGURES-PLAN.md F7 wants the extended set ("verify 15-col input");
    # until that is done the name must not claim it.
    "F7-pca-correlation-circle":      "cross-deployment-correlation-circle-in-metric-space",
    "F7-pca-dendro":                  "cross-deployment-pca-and-ward-dendrogram",

    # --- cadence sweep and its overhead leg ---------------------------------
    "F8-cadence-fidelity":            "profiler-fidelity-versus-sampling-cadence",
    "F8-cadence-sensitivity":         "which-metrics-need-fine-grained-sampling",
    "F9-overhead-vs-cadence":         "profiler-overhead-versus-sampling-cadence",

    # --- W5 colocation ------------------------------------------------------
    "F10-victim-delta-forest":        "victim-metric-shift-under-a-noisy-neighbour",
    "F11-vmguest-portable-vs-canonical":
        "in-a-vm-the-portable-proxy-sees-contention-rdt-cannot",

    # --- Tier-B / Tier-C real applications ----------------------------------
    "F12-fingerprint":                "real-applications-stress-several-resource-classes",
    "F12-class-activation":           "real-applications-activate-multiple-iada-classes",

    # --- IADA classifier tiers ---------------------------------------------
    "F13-tier-scheduling-idi":        "closed-loop-scheduling-outcome-per-classifier-tier",
    "F13-tier-scheduling-idi-psp":
        "closed-loop-scheduling-outcome-per-classifier-tier-psp-rebank-arm",
    "F13-tier-portability-table":     "iada-classifier-portability-across-deployments",
    "F13-tier-transfer-table":        "host-trained-classifier-applied-inside-the-vm",

    # --- Meyer-2021 / IADA-2022 validation ----------------------------------
    "F14-kmeans-threshold-map":       "kmeans-level-thresholds-shipped-versus-retrained",
    "F15-degradation-tables":         "response-time-degradation-multipliers-by-class-and-level",

    # --- simulator sensitivity and the JDK rebuild check --------------------
    "F-simexp-deltas":                "which-simulator-knobs-move-the-degradation-index",
    "F-simexp-hosts":                 "degradation-index-is-flat-across-the-host-count-sweep",
    "F-simexp-density":               "degradation-index-rises-with-genuine-placement-density",
    "F-jdk-ab-idi":                   "jdk17-rebuild-leaves-the-degradation-index-unchanged",
    "F-jdk-ab-delta":                 "jdk17-versus-java8-build-difference-covers-zero",

    # --- Seminario de Andamento --------------------------------------------
    "w4-summary":                     "faithfulness-cpu-absolute-and-llcmr-directional",
    "schedule-plan-vs-actual":        "dissertation-schedule-planned-versus-actual",

    # --- bench/iada/scripts/plot-iada.py: IADA campaign manifests -----------
    "fig_iada_variant_ranking":       "iada-degradation-index-per-profiler-variant",
    "fig_iada_migrations_vs_idi":     "iada-migrations-versus-degradation-index",
    "fig_iada_wallclock":             "iada-simulation-wall-clock-per-variant",
    "fig_iada_transfer_heatmap":      "iada-degradation-index-per-variant-and-environment",
    "fig_iada_transfer_degradation":  "iada-cross-environment-transfer-penalty",
    "fig_iada_fragility_vs_idi":      "iada-profiler-fragility-versus-degradation-index",

    # --- plot-cross-environment.py -----------------------------------------
    # One figure per (variant, workload); the pair rides in as the suffix.
    "cross-environment":              "metric-distribution-by-environment",
}


# ---------------------------------------------------------------------------
# Which campaign produced the data. Keyed by the directory name the renderer
# was pointed at, so the tag follows the data rather than the invocation.
# ---------------------------------------------------------------------------

DATASETS: dict[str, str] = {
    # Paper 1 -- the SBAC-PAD stress-ng / HiBench campaigns.
    "ub22-and-24-full":                "ubuntu22+24-all-variants",
    "ub24-concat":                     "ubuntu24-kernel6.8-modern-variants",
    "ub22-campaign-20260521_162957":   "ubuntu22-legacy-baseline-2026-05-21",
    "ub22-campaign-20260523_184651":   "ubuntu22-legacy-baseline-2026-05-23",
    "ub24-campaign-20260518_021737":   "ubuntu24-stap-modern-and-c-abi-2026-05-18",
    "ub24-campaign-20260522_183908":   "ubuntu24-ebpf-core-2026-05-22",
    "ub24-campaign-20260523_131301":   "ubuntu24-ebpf-core-2026-05-23",

    # Paper 2 -- cross-deployment, cadence, colocation, real applications.
    "p2-15metric-xdeploy-1of3":        "tier-a-cross-deployment",
    "p2-15metric-xdeploy-1of3-w5":     "w5-colocation",
    "p2-cadence-sweep":                "cadence-sweep",
    "p2-cadence-overhead":             "cadence-sweep",
    "p2-tierb":                        "tier-b-real-apps",
    "p2-tierc":                        "tier-c-deathstarbench",
    "p2-realapps-combined":            "tier-b+c-combined",

    # IADA -- classifier tiers, simulator campaign, Meyer validation.
    "iada-sim":                        "iada-tier-campaign",
    "iada-trainsets":                  "iada-tier-campaign",
    "sim-experiments-20260811":        "sim-experiments-2026-08-11",
    "ab-run-20260811":                 "jdk-ab-run-2026-08-11",
    "meyer-validation":                "meyer-published-artifacts",

    # The published noise-floor pair (release v0.1.0 extra/).
    "intp-aux-rerun-v3-20260524-164742":   "ebpf-ring-v3-noise-floor",
    "intp-aux-rerun-v3.2-20260524-173601": "ebpf-core-v3.2-noise-floor",

    # Documents rather than campaigns.
    "W4-faithfulness-r2":              "w4-faithfulness-adjudication",
}

#: The tag ``render-sa-figures.py`` gives every renderer, so the Seminario set
#: is named after the document it is cut for rather than after seven different
#: campaign trees.
SA_DATASET = "seminario-de-andamento"

# Compound terms that must survive the hyphens-to-spaces pass in `phrase`.
_KEEP_HYPHEN = (
    "stress-ng", "c-abi", "ebpf-core", "ebpf-ring", "15-metric", "rep-level",
    "closed-loop", "bare-metal", "cross-deployment", "long-trace", "co-runner",
    "fine-grained", "ground-truth", "level-defining", "response-time",
    "host-count", "host-trained", "in-a-vm", "per-workload", "per-variant",
    "per-second", "per-deployment", "per-resource", "vs-ground-truth",
)

_TIMESTAMPED = re.compile(r"^(?P<base>.+?)[-_](?P<date>20\d{6})(?:[-_]\d{6})?$")


def slug(text: str) -> str:
    """Lower-case, hyphen-joined, safe on every filesystem we target."""
    text = str(text).replace("_", "-").replace(" ", "-").lower()
    return re.sub(r"-{2,}", "-", re.sub(r"[^a-z0-9.+-]", "", text)).strip("-")


def phrase(description: str) -> str:
    """A slug description read back as a sentence, for reports and indexes."""
    out = description
    for term in _KEEP_HYPHEN:
        out = out.replace(term, term.replace("-", "\x00"))
    return out.replace("-", " ").replace("\x00", "-")


def figure_id(stem: str) -> str:
    """The number the reports cite: ``F0``, ``F13``, ``fig04b``, or ``""``.

    Case is preserved -- ``F1`` and ``fig01`` are different figures in
    different documents, and lower-casing the first would lose that.
    """
    if stem.startswith("F-"):            # F-simexp-*, F-jdk-ab-*: never numbered
        return ""
    if re.match(r"^F\d", stem):          # F0-fingerprint-heatmap
        return stem.split("-")[0]
    m = re.match(r"^fig\d+[a-z]?", stem)  # fig04b_overhead_cpu_jiffies
    return m.group(0) if m else ""


def split_suffix(stem: str) -> tuple[str, str]:
    """Split a composed stem into its registry key and its variable tail.

    HiBench appends a profile (``fig01_fingerprint_cache-extreme``) and
    plot-intp-bench appends an environment (``fig07_pairwise_heatmap_bare``);
    both are one registry entry with a per-render tail. Longest match wins, so
    ``fig00_canonical_intp_fig4`` resolves before its HiBench siblings.
    """
    if stem in FIGURES:
        return stem, ""
    for key in sorted(FIGURES, key=len, reverse=True):
        if stem.startswith(key + "_") or stem.startswith(key + "-"):
            return key, stem[len(key) + 1:]
    raise KeyError(
        f"no description registered for figure stem {stem!r}. Add it to "
        f"FIGURES in bench/plot/fig_names.py -- a figure without a reviewed "
        f"description would ship under a name nobody outside this repository "
        f"can read.")


def describe(stem: str) -> str:
    """The slugged description for a stem, tail included."""
    key, tail = split_suffix(stem)
    return FIGURES[key] + (f"-{slug(tail)}" if tail else "")


def dataset_tag(source) -> str:
    """The campaign tag for a path (or bare name) the renderer was given.

    Known campaigns get their reviewed tag; anything else falls back to the
    directory's own name with a trailing capture timestamp normalised, so an
    unregistered tree still produces a stable, legible name instead of an
    error. Pass a file and the lookup walks up to the campaign root.
    """
    if source is None:
        raise ValueError("dataset_tag() needs a campaign path or tag")
    p = Path(str(source))
    for part in (p.name, p.stem, *[q.name for q in p.parents]):
        if part in DATASETS:
            return DATASETS[part]
    # Unregistered: use the directory itself (its parent if it is a file).
    base = p.stem if p.suffix else p.name
    m = _TIMESTAMPED.match(base)
    if m:
        d = m.group("date")
        base = f"{m.group('base')}-{d[:4]}-{d[4:6]}-{d[6:]}"
    return slug(base) or "unknown-campaign"


def head(stem: str, qualifier: str = "") -> str:
    """The campaign-independent part of a figure name.

    ``<figure-id>-<description>[-<qualifier>]``. The qualifier distinguishes
    renders of the same figure that differ in something other than the data --
    the paper's variant subsets, for instance. This is what the LaTeX spec
    tables key on; ``name()`` adds the campaign.
    """
    out = describe(stem)
    fid = figure_id(stem)
    if fid:
        out = f"{fid}-{out}"
    return f"{out}-{slug(qualifier)}" if qualifier else out


def name(stem: str, dataset: str, *, qualifier: str = "",
         ext: str | None = None) -> str:
    """The on-disk name for one figure.

    ``<figure-id>-<description>[-<qualifier>]--<campaign>[.<ext>]``.
    """
    if not dataset:
        raise ValueError(
            f"figure {stem!r} has no campaign tag. Pass --dataset, or let the "
            f"renderer derive one from its input path with dataset_tag().")
    base = f"{head(stem, qualifier)}--{slug(dataset)}"
    return f"{base}.{ext}" if ext else base


def add_dataset_arg(parser) -> None:
    """Add the ``--dataset`` override every renderer accepts."""
    parser.add_argument(
        "--dataset", default=None, metavar="TAG",
        help="campaign tag for the output filenames (default: derived from "
             "the input path via fig_names.dataset_tag)")

#!/usr/bin/env python3
# Tests for bench/plot/fig_names.py, the figure-naming registry.
#
# The registry decides what every rendered figure is called, so the things
# worth pinning are the ones that would silently corrupt a folder of nine
# hundred files: two figures colliding on one name, a stem losing its
# description, a campaign losing its tag, or the LaTeX spec tables drifting
# away from what the renderers actually write.
#
# Run:  python3 -m unittest bench/plot/tests/test_fig_names.py

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import fig_names  # noqa: E402
import paper_style  # noqa: E402
import sa_style  # noqa: E402


class NameCompositionTest(unittest.TestCase):
    def test_numbered_figure_keeps_its_number(self) -> None:
        self.assertEqual(
            fig_names.name("F1-ratio-vs-bare", "tier-a-cross-deployment"),
            "F1-absolute-metric-ratio-versus-bare-metal--tier-a-cross-deployment")

    def test_unnumbered_figure_starts_with_the_description(self) -> None:
        # F-simexp-* never carried an F-number in docs/FIGURES-PLAN.md.
        self.assertEqual(
            fig_names.name("F-simexp-hosts", "sim-experiments-2026-08-11"),
            "degradation-index-is-flat-across-the-host-count-sweep"
            "--sim-experiments-2026-08-11")

    def test_variable_tail_rides_after_the_description(self) -> None:
        # HiBench appends a profile; plot-intp-bench appends an environment.
        self.assertEqual(
            fig_names.name("fig01_fingerprint_cache-extreme", "ub24"),
            "fig01-hibench-metric-fingerprint-cache-extreme--ub24")
        self.assertEqual(
            fig_names.name("fig07_pairwise_heatmap_bare", "ub24"),
            "fig07-pairwise-colocation-interference-signal-bare--ub24")

    def test_qualifier_separates_cuts_of_one_figure(self) -> None:
        stem = "fig01b_per_variant_bars"
        self.assertNotEqual(
            fig_names.name(stem, "ub22+24", qualifier="c-abi-and-ebpf-core"),
            fig_names.name(stem, "ub22+24", qualifier="all-published-variants"))

    def test_extension_is_optional(self) -> None:
        self.assertTrue(
            fig_names.name("F1-ratio-vs-bare", "x", ext="pdf").endswith(".pdf"))

    def test_a_figure_without_a_campaign_is_refused(self) -> None:
        # A name with no campaign tail is exactly what this module exists to
        # prevent, so it must fail loudly rather than default.
        with self.assertRaises(ValueError):
            fig_names.name("F1-ratio-vs-bare", "")

    def test_an_unregistered_stem_is_refused(self) -> None:
        with self.assertRaises(KeyError):
            fig_names.name("fig99_something_new", "x")


class RegistryTest(unittest.TestCase):
    def test_descriptions_are_slugs(self) -> None:
        for stem, desc in fig_names.FIGURES.items():
            with self.subTest(stem=stem):
                self.assertEqual(desc, fig_names.slug(desc))

    def test_descriptions_are_distinct(self) -> None:
        seen: dict[str, str] = {}
        for stem, desc in fig_names.FIGURES.items():
            head = fig_names.head(stem)
            self.assertNotIn(
                head, seen,
                f"{stem} and {seen.get(head)} would produce the same filename")
            seen[head] = stem

    def test_campaign_tags_are_slugs(self) -> None:
        for key, tag in fig_names.DATASETS.items():
            with self.subTest(campaign=key):
                self.assertEqual(tag, fig_names.slug(tag))

    def test_phrase_keeps_compound_terms(self) -> None:
        self.assertEqual(
            fig_names.phrase("cross-variant-fingerprint-correlation-stress-ng"),
            "cross variant fingerprint correlation stress-ng")


class DatasetTagTest(unittest.TestCase):
    def test_registered_campaign_anywhere_in_the_path(self) -> None:
        self.assertEqual(
            fig_names.dataset_tag(
                "/data/consolidation/fusion/ub22-and-24-full/bench-full"),
            "ubuntu22+24-all-variants")

    def test_registered_campaign_from_a_file_inside_it(self) -> None:
        self.assertEqual(
            fig_names.dataset_tag(
                "/data/results/p2-cadence-sweep/cadence-fidelity.tsv"),
            "cadence-sweep")

    def test_document_matches_on_its_stem(self) -> None:
        self.assertEqual(
            fig_names.dataset_tag("docs/reports/W4-faithfulness-r2.md"),
            "w4-faithfulness-adjudication")

    def test_unregistered_tree_normalises_its_capture_timestamp(self) -> None:
        self.assertEqual(
            fig_names.dataset_tag("/data/intp-bench-20260605_044515"),
            "intp-bench-2026-06-05")

    def test_unregistered_tree_without_a_timestamp(self) -> None:
        self.assertEqual(fig_names.dataset_tag("/data/some-run"), "some-run")


class SpecTableTest(unittest.TestCase):
    """The LaTeX drop-ins must not collide or drift from the registry."""

    def test_paper_names_are_distinct(self) -> None:
        names = [paper_style.out_name(k, "c") for k in paper_style.PAPER_FIGURES]
        self.assertEqual(len(names), len(set(names)))

    def test_sa_names_are_distinct(self) -> None:
        names = [sa_style.out_name(stem) for (_, stem) in sa_style.SA_FIGURES]
        self.assertEqual(len(names), len(set(names)))

    def test_every_spec_stem_is_registered(self) -> None:
        for _, stem in paper_style.PAPER_FIGURES:
            with self.subTest(stem=stem):
                self.assertTrue(fig_names.describe(stem))
        for _, stem in sa_style.SA_FIGURES:
            with self.subTest(stem=stem):
                self.assertTrue(fig_names.describe(stem))

    def test_collected_name_extends_the_rendered_one(self) -> None:
        # render-paper-figures.py collects <rendered> into <collected>; the
        # two are built from the same stem, so the qualifier is all that may
        # differ. If that stops holding, the driver silently copies nothing.
        for key in paper_style.PAPER_FIGURES:
            _subset, stem = key
            with self.subTest(stem=stem):
                rendered = fig_names.head(stem)
                self.assertTrue(paper_style.out_stem(key).startswith(rendered))

    def test_sa_names_are_campaign_independent(self) -> None:
        # The SA .tex includes them by name, so re-rendering from a different
        # snapshot must not move the file.
        self.assertTrue(
            sa_style.out_name("F3-availability-grid").endswith(
                f"--{fig_names.SA_DATASET}.pdf"))


if __name__ == "__main__":
    unittest.main()

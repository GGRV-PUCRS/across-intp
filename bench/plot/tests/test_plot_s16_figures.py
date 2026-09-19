#!/usr/bin/env python3
# Tests for bench/plot/plot-fig-truthscore-jsa.py and
# bench/plot/plot-fig-idi-decomp-jsa.py (the two S16/S1+S2 paper figures).
#
# Drives both scripts against bench/plot/tests/fixtures/s16/, a small synthetic
# stand-in for bench/iada/results/sim-experiments-20260917-s16/:
#   - s1-truthscore*.tsv: IASA n=3, CIAPA n=2 per tier/yardstick, EVEN rows in
#     the summary; 'final6th' duplicate-window rows exercise the window filter.
#   - s2-decomp.tsv / s2-summary.tsv / s2-intervals.tsv: 3 reps per tier with
#     endpoints consistent across all three files; s2-summary.tsv carries the
#     trailing ratio lines of the real file to exercise defensive parsing.
#
# Run:  python3 -m unittest bench/plot/tests/test_plot_s16_figures.py

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
FIXTURE = THIS_DIR / "fixtures" / "s16"
TRUTHSCORE = THIS_DIR.parent / "plot-fig-truthscore-jsa.py"
IDI_DECOMP = THIS_DIR.parent / "plot-fig-idi-decomp-jsa.py"


class TruthscorePlotTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="truthscore-test-"))
        proc = subprocess.run(
            [sys.executable, str(TRUTHSCORE),
             "--data-root", str(FIXTURE), "--out", str(cls.tmpdir)],
            capture_output=True, text=True, check=False,
        )
        cls.proc = proc
        if proc.returncode != 0:
            raise RuntimeError(
                f"plot-fig-truthscore-jsa.py failed (rc={proc.returncode})\n"
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
            )

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def test_output_exists(self) -> None:
        pdf = self.tmpdir / "fig_truthscore.pdf"
        self.assertTrue(pdf.exists() and pdf.stat().st_size > 1000,
                        f"missing fig_truthscore.pdf in {self.tmpdir}")

    def test_iasa_means_printed(self) -> None:
        self.assertIn(
            "truthscore Y5 IASA means: "
            "canonical-7=7000 proxy-swap=7050 full-fingerprint=7350",
            self.proc.stdout)
        self.assertIn(
            "truthscore Y6 IASA means: "
            "canonical-7=6500 proxy-swap=6550 full-fingerprint=6950",
            self.proc.stdout)

    def test_even_scores_printed(self) -> None:
        self.assertIn("truthscore EVEN: Y5=9000 Y6=8500", self.proc.stdout)

    def test_summary_crosscheck_passes(self) -> None:
        self.assertIn("VALIDATION OK: Y5 IASA means match "
                      "s1-truthscore-summary.tsv", self.proc.stdout)
        self.assertIn("VALIDATION OK: Y6 CIAPA means match "
                      "s1-truthscore-summary.tsv", self.proc.stdout)
        self.assertNotIn("VALIDATION WARN", self.proc.stdout)


class IdiDecompPlotTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="idi-decomp-test-"))
        proc = subprocess.run(
            [sys.executable, str(IDI_DECOMP),
             "--data-root", str(FIXTURE), "--out", str(cls.tmpdir),
             "--intervals-tsv", str(FIXTURE / "s2-intervals.tsv"),
             "--s3-work-root", "/nonexistent"],
            capture_output=True, text=True, check=False,
        )
        cls.proc = proc
        if proc.returncode != 0:
            raise RuntimeError(
                f"plot-fig-idi-decomp-jsa.py failed (rc={proc.returncode})\n"
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
            )

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def test_output_exists(self) -> None:
        pdf = self.tmpdir / "fig_idi_decomp.pdf"
        self.assertTrue(pdf.exists() and pdf.stat().st_size > 1000,
                        f"missing fig_idi_decomp.pdf in {self.tmpdir}")

    def test_interval_means_and_closed_form_printed(self) -> None:
        self.assertIn("idi_decomp canonical-7: interval means "
                      "8000 7000 7200 6500 5600 5000; closed form 8350",
                      self.proc.stdout)
        self.assertIn("idi_decomp full-fingerprint: interval means "
                      "5800 4700 4300 3900 3700 3450; closed form 6050",
                      self.proc.stdout)

    def test_final_means_printed(self) -> None:
        self.assertIn("idi_decomp canonical-7 final: mean 5000",
                      self.proc.stdout)
        self.assertIn("idi_decomp proxy-swap final: mean 3300",
                      self.proc.stdout)
        self.assertIn("idi_decomp full-fingerprint final: mean 3450",
                      self.proc.stdout)

    def test_crosschecks_pass(self) -> None:
        self.assertIn("VALIDATION OK: interval source endpoints match "
                      "s2-decomp.tsv for canonical-7 (n=3)", self.proc.stdout)
        self.assertIn("VALIDATION OK: canonical-7 final mean 5000.0 matches "
                      "s2-summary.tsv", self.proc.stdout)
        self.assertNotIn("VALIDATION WARN", self.proc.stdout)


if __name__ == "__main__":
    unittest.main()

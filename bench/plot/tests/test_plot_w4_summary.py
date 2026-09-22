#!/usr/bin/env python3
# Tests for bench/plot/plot-w4-summary.py.
#
# Drives the script against bench/plot/tests/fixtures/w4-report/, a trimmed
# synthetic W4 report exercising the three structures the renderer parses:
# FAITHFUL ratio cells (band = 0.90-1.02), the per-variant CPU summary lines
# (20/20 adjudicable cells), and the Spearman directional-faithfulness lines
# (rho 0.66 / 0.83, both p < 0.001).
#
# Run:  python3 -m unittest bench/plot/tests/test_plot_w4_summary.py

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
SCRIPT = THIS_DIR.parent / "plot-w4-summary.py"
FIXTURE = THIS_DIR / "fixtures" / "w4-report" / "W4-faithfulness-r2.md"


class W4SummaryPlotTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="w4-summary-test-"))
        # --dataset is pinned so the expected filename does not depend on
        # where the fixture happens to live.
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), str(FIXTURE),
             "--out", str(cls.tmpdir), "--dataset", "w4-fixture"],
            capture_output=True, text=True, check=False,
        )
        cls.proc = proc
        if proc.returncode != 0:
            raise RuntimeError(
                f"plot-w4-summary.py failed (rc={proc.returncode})\n"
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
            )

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def test_outputs_exist(self) -> None:
        # Spelled out rather than derived from fig_names, so a change to the
        # registered description has to be made deliberately here too.
        name = "faithfulness-cpu-absolute-and-llcmr-directional--w4-fixture"
        for fmt in ("png", "pdf"):
            with self.subTest(fmt=fmt):
                self.assertTrue(
                    (self.tmpdir / fmt / f"{name}.{fmt}").exists(),
                    f"missing {fmt} output; produced "
                    f"{sorted(p.name for p in (self.tmpdir / fmt).glob('*'))}")

    def test_parsed_ratio_band(self) -> None:
        self.assertIn("min=0.90 max=1.02", self.proc.stdout)

    def test_parsed_cell_count(self) -> None:
        self.assertIn("cells=20/20", self.proc.stdout)

    def test_parsed_spearman(self) -> None:
        self.assertIn("'v2.1': 0.66", self.proc.stdout)
        self.assertIn("'v3.3': 0.83", self.proc.stdout)
        self.assertIn("p < 0.001", self.proc.stdout)


if __name__ == "__main__":
    unittest.main()

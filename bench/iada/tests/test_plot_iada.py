#!/usr/bin/env python3
"""
test_plot_iada.py — minimal smoke tests for plot-iada.py.

Drives the script against the two checked-in fixture manifests and
asserts that the expected outputs appear under a temp directory. Does
not validate figure content, only file existence + the README/summary
side-outputs. Uses stdlib unittest so it runs without extra deps.

Run:
    python3 -m unittest bench/iada/tests/test_plot_iada.py
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT  = Path(__file__).resolve().parents[3]
SCRIPT     = REPO_ROOT / "bench" / "iada" / "scripts" / "plot-iada.py"
FIXTURES   = Path(__file__).resolve().parent / "fixtures"
M1_FIXTURE = FIXTURES / "manifest-m1.tsv"
M2_FIXTURE = FIXTURES / "manifest-m2.tsv"


#: Figures are named <what-they-show>--<campaign> (bench/plot/fig_names.py);
#: the tag is pinned so the expected filenames do not depend on where the
#: fixture manifest happens to live.
DATASET = "iada-fixture"

#: stem -> the name plot-iada.py writes. Spelled out rather than derived from
#: fig_names, so a change to a registered description has to be made here too.
NAME = {
    "fig_iada_variant_ranking":
        f"iada-degradation-index-per-profiler-variant--{DATASET}.png",
    "fig_iada_migrations_vs_idi":
        f"iada-migrations-versus-degradation-index--{DATASET}.png",
    "fig_iada_wallclock":
        f"iada-simulation-wall-clock-per-variant--{DATASET}.png",
    "fig_iada_transfer_heatmap":
        f"iada-degradation-index-per-variant-and-environment--{DATASET}.png",
    "fig_iada_transfer_degradation":
        f"iada-cross-environment-transfer-penalty--{DATASET}.png",
    "fig_iada_fragility_vs_idi":
        f"iada-profiler-fragility-versus-degradation-index--{DATASET}.png",
}


def run_plot(manifest: Path, out_dir: Path, modality: str | None = None,
             extra: list[str] | None = None) -> subprocess.CompletedProcess:
    cmd = [sys.executable, str(SCRIPT), str(manifest),
           "--out-dir", str(out_dir), "--dataset", DATASET]
    if modality:
        cmd += ["--modality", modality]
    if extra:
        cmd += extra
    return subprocess.run(cmd, capture_output=True, text=True)


class TestPlotIadaM1(unittest.TestCase):
    def test_m1_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out_dir = Path(td)
            res = run_plot(M1_FIXTURE, out_dir, modality="M1")
            self.assertEqual(res.returncode, 0,
                             f"plot-iada.py failed: stderr=\n{res.stderr}")

            # M1 PNGs.
            for name in (
                NAME["fig_iada_variant_ranking"],
                NAME["fig_iada_migrations_vs_idi"],
                NAME["fig_iada_wallclock"],
            ):
                self.assertTrue((out_dir / name).is_file(),
                                f"missing {name} in {out_dir}")

            # M2-only PNGs MUST NOT be present in M1.
            for name in (
                NAME["fig_iada_transfer_heatmap"],
                NAME["fig_iada_transfer_degradation"],
            ):
                self.assertFalse((out_dir / name).exists(),
                                 f"unexpected {name} in M1 output")

            self.assertTrue((out_dir / "summary.tsv").is_file())
            readme = (out_dir / "README.md").read_text()
            self.assertIn("M1", readme)
            self.assertIn("Baseline variant", readme)


class TestPlotIadaM2(unittest.TestCase):
    def test_m2_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out_dir = Path(td)
            res = run_plot(M2_FIXTURE, out_dir, modality="M2")
            self.assertEqual(res.returncode, 0,
                             f"plot-iada.py failed: stderr=\n{res.stderr}")

            for name in (
                NAME["fig_iada_variant_ranking"],
                NAME["fig_iada_migrations_vs_idi"],
                NAME["fig_iada_wallclock"],
                NAME["fig_iada_transfer_heatmap"],
                NAME["fig_iada_transfer_degradation"],
            ):
                self.assertTrue((out_dir / name).is_file(),
                                f"missing {name} in {out_dir}")

            self.assertTrue((out_dir / "summary.tsv").is_file())
            readme = (out_dir / "README.md").read_text()
            self.assertIn("M2", readme)
            self.assertIn("container", readme)


class TestPlotIadaAuto(unittest.TestCase):
    def test_auto_detects_m1(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out_dir = Path(td)
            res = run_plot(M1_FIXTURE, out_dir, modality="auto")
            self.assertEqual(res.returncode, 0, msg=res.stderr)
            self.assertFalse((out_dir / NAME["fig_iada_transfer_heatmap"]).exists())

    def test_auto_detects_m2(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out_dir = Path(td)
            res = run_plot(M2_FIXTURE, out_dir, modality="auto")
            self.assertEqual(res.returncode, 0, msg=res.stderr)
            self.assertTrue((out_dir / NAME["fig_iada_transfer_heatmap"]).is_file())


if __name__ == "__main__":
    unittest.main()

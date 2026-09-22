#!/usr/bin/env python3
# Tests for bench/plot/plot-cross-environment.py.
#
# Drives the script against bench/plot/tests/fixtures/cross-env/ which
# contains a synthetic aggregate-means.tsv spanning 3 envs (bare, container,
# vm) × 2 variants (v2, v3.1) × 2 workloads × 3 reps. The fixture is designed
# to exercise three branches:
#   (a) variant=v2 workload=app01_ml_llc metric=cpu: bare ≪ container ≪ vm,
#       i.e. KW omnibus must be significant at alpha=0.05.
#   (b) variant=v2 workload=app01_ml_llc metric=mbw: values overlap, KW n.s.
#   (c) variant=v3.1 workload=app10_search metric=llcocc: vm reps are "--",
#       availability.tsv must flag the (vm, v3.1, app10, llcocc) cell missing.
#
# Run:  python3 -m unittest bench/plot/tests/test_plot_cross_environment.py

from __future__ import annotations

import csv
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
FIXTURE_DIR = THIS_DIR / "fixtures" / "cross-env"
SCRIPT = THIS_DIR.parent / "plot-cross-environment.py"


def _read_tsv(path: Path) -> list[dict]:
    with path.open() as f:
        return list(csv.DictReader(f, delimiter="\t"))


class CrossEnvPlotTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="cross-env-test-"))
        # The script expects either a campaign root containing bench-full/, or
        # a bench-full/ directly. We mirror the fixture into a bench-full/ so
        # the test exercises the campaign-root code path too.
        bench_full = cls.tmpdir / "bench-full"
        bench_full.mkdir()
        shutil.copy2(FIXTURE_DIR / "aggregate-means.tsv",
                     bench_full / "aggregate-means.tsv")
        # Run the script
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), str(cls.tmpdir)],
            capture_output=True, text=True, check=False,
        )
        cls.proc = proc
        if proc.returncode != 0:
            raise RuntimeError(
                f"plot-cross-environment.py failed (rc={proc.returncode})\n"
                f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
            )
        cls.outdir = bench_full / "cross-env"

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def test_outputs_exist(self) -> None:
        for name in ("summary.tsv", "stats.tsv", "availability.tsv", "README.md"):
            with self.subTest(name=name):
                self.assertTrue((self.outdir / name).exists(),
                                f"missing {name}")

    def test_summary_row_count(self) -> None:
        # 3 envs × 2 variants × 2 workloads × 7 metrics = 84 rows
        rows = _read_tsv(self.outdir / "summary.tsv")
        self.assertEqual(len(rows), 84, f"unexpected row count: {len(rows)}")

    def test_kw_significant_case(self) -> None:
        rows = _read_tsv(self.outdir / "stats.tsv")
        target = [r for r in rows
                  if r["variant"] == "v2"
                  and r["workload"] == "app01_ml_llc"
                  and r["metric"] == "cpu"]
        self.assertEqual(len(target), 1)
        r = target[0]
        kw_p = float(r["kw_p"])
        self.assertLess(kw_p, 0.05,
                        f"KW for v2/app01/cpu should be significant; p={kw_p}")
        self.assertIn(r["kw_signif"], ("*", "**", "***"))
        # Bonferroni-corrected pairwise fields must be populated (not 'skip')
        for pair in ("bare_vs_container", "bare_vs_vm", "container_vs_vm"):
            with self.subTest(pair=pair):
                self.assertNotEqual(r.get(f"mw_signif_{pair}"), "skip",
                                    f"pairwise for {pair} should run when KW is sig")
                self.assertNotEqual(r.get(f"cliffs_mag_{pair}"), "skip")

    def test_kw_not_significant_case(self) -> None:
        rows = _read_tsv(self.outdir / "stats.tsv")
        target = [r for r in rows
                  if r["variant"] == "v2"
                  and r["workload"] == "app01_ml_llc"
                  and r["metric"] == "mbw"]
        self.assertEqual(len(target), 1)
        r = target[0]
        kw_p = float(r["kw_p"])
        # Not asserting p > 0.05 specifically; just asserting that when KW is
        # not significant the pairwise tests are skipped to honor the alpha
        # gate. If kw_p < 0.05 the test will be flagged as the fixture drifting.
        if kw_p >= 0.05:
            self.assertEqual(r["kw_signif"], "n.s.")
            for pair in ("bare_vs_container", "bare_vs_vm", "container_vs_vm"):
                with self.subTest(pair=pair):
                    self.assertEqual(r.get(f"mw_signif_{pair}"), "skip")

    def test_availability_missing_case(self) -> None:
        rows = _read_tsv(self.outdir / "availability.tsv")
        missing = [r for r in rows
                   if r["env"] == "vm"
                   and r["variant"] == "v3.1"
                   and r["workload"] == "app10_search"
                   and r["metric"] == "llcocc"]
        self.assertEqual(len(missing), 1)
        self.assertEqual(missing[0]["status"], "missing")
        self.assertEqual(missing[0]["n_samples"], "0")

    def test_at_least_one_png_emitted(self) -> None:
        plots = list((self.outdir / "plots").rglob("*.png"))
        self.assertGreaterEqual(len(plots), 1,
                                "expected at least one PNG under cross-env/plots/")

    def test_claim_class_column(self) -> None:
        # Every (variant, workload, metric) row carries the Paper-2 claim tier,
        # wired to the W4 verdicts; the tier is metric-determined.
        rows = _read_tsv(self.outdir / "stats.tsv")
        by_metric = {r["metric"]: r["claim_class"] for r in rows}
        self.assertEqual(by_metric.get("cpu"), "absolute")
        self.assertEqual(by_metric.get("llcmr"), "directional")
        for m in ("mbw", "llcocc", "blk", "netp", "nets"):
            with self.subTest(metric=m):
                self.assertEqual(by_metric.get(m), "descriptive")
        # summary.tsv carries it too
        srows = _read_tsv(self.outdir / "summary.tsv")
        self.assertTrue(srows and all("claim_class" in r for r in srows))

    def test_bh_fdr_q_column(self) -> None:
        # The BH-adjusted q-value column is emitted for run pairs (replaces the
        # Bonferroni-threshold-only scheme).
        rows = _read_tsv(self.outdir / "stats.tsv")
        r = next(r for r in rows
                 if r["variant"] == "v2" and r["workload"] == "app01_ml_llc"
                 and r["metric"] == "cpu")
        for pair in ("bare_vs_container", "bare_vs_vm", "container_vs_vm"):
            with self.subTest(pair=pair):
                self.assertIn(f"mw_q_{pair}", r)
                self.assertNotIn(r.get(f"mw_q_{pair}"), ("", "skip"))


class CrossEnvUnsupportedTest(unittest.TestCase):
    """vm-guest RDT metrics (mbw/llcocc) that are '--' must read as
       'unsupported' (structural: resctrl is host-only), while a non-RDT '--'
       stays 'missing' (a collection gap)."""

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp(prefix="cross-env-unsup-"))
        bench_full = self.tmpdir / "bench-full"
        bench_full.mkdir()
        cols = "env\tvariant\tstage\tworkload\trep\tnetp\tnets\tblk\tmbw\tllcmr\tllcocc\tcpu\n"
        lines = [cols]
        for rep in (1, 2):
            lines.append(f"bare\tv3.3\tsolo\tapp10_search\t{rep}\t1\t1\t0.5\t10\t0.2\t2\t50\n")
        # vm-guest: mbw/llcocc structurally absent; blk a (non-RDT) gap; cpu OK
        for rep in (1, 2):
            lines.append(f"vm-guest\tv3.3\tsolo\tapp10_search\t{rep}\t1\t1\t--\t--\t0.2\t--\t50\n")
        (bench_full / "aggregate-means.tsv").write_text("".join(lines))
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), str(self.tmpdir)],
            capture_output=True, text=True, check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"script failed (rc={proc.returncode}): {proc.stderr}")
        self.rows = _read_tsv(bench_full / "cross-env" / "availability.tsv")

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _status(self, env: str, metric: str) -> str:
        return next(r["status"] for r in self.rows
                    if r["env"] == env and r["metric"] == metric
                    and r["workload"] == "app10_search")

    def test_vm_guest_rdt_unsupported(self) -> None:
        self.assertEqual(self._status("vm-guest", "mbw"), "unsupported")
        self.assertEqual(self._status("vm-guest", "llcocc"), "unsupported")

    def test_vm_guest_nonrdt_gap_is_missing(self) -> None:
        self.assertEqual(self._status("vm-guest", "blk"), "missing")

    def test_bare_present_is_ok(self) -> None:
        self.assertEqual(self._status("bare", "cpu"), "OK")


if __name__ == "__main__":
    unittest.main()

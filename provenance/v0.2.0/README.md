# provenance/v0.2.0: pre-fix v2.1 readings (D16, C38)

The JSA campaigns ran with release `v0.2.0`. Release `v0.2.1` fixes two v2.1
defects (C38 in `docs/DECISIONS-container.md`) but re-measures nothing, so the
data attached to `v0.2.1` is byte-identical to the `v0.2.0` assets:

| Asset | SHA-256 |
| --- | --- |
| `across-intp-jsa-results-v0.2.0.tar.gz` | `9311351e43d59cf72ccce2e6061e95403ee1ec76c99ba51aa49c955ee1cdee23` |
| `IntP-JSA-complete-data-20260918.tar.xz` | `63e94d2e1d8f4dcb117213c0535085f8f9ece7b099bb0b999b118e0b148190c4` |

Both are also archived in the `v0.2.0` Zenodo record,
[10.5281/zenodo.22970881](https://doi.org/10.5281/zenodo.22970881).

## Where the v0.2.0 v2.1 Tier B/C trees live

| Archive | Tier B (app18 to app21) | Tier C (app22) |
| --- | --- | --- |
| `across-intp-jsa-results-v0.2.0.tar.gz` | `04-tier-b-realapps/` | `05-tier-c-dsb/` |
| `IntP-JSA-complete-data-20260918.tar.xz` | `IntP-JSA-consolidated-data/final/04-tier-b-realapps/` | `IntP-JSA-consolidated-data/final/05-tier-c-dsb/` |

The v2.1 cells are the `{bare,container,vm-guest}/v2.1/solo/<app>/rep<N>/`
subtrees (6 subtrees, about 1,300 files, 18 MB). The combined real-application
fingerprint table is `IntP-JSA-consolidated-data/derived/p2-realapps-combined/fingerprints.tsv`.

## Which readings are pre-fix

Only **v2.1** cells of the compose-based suites:

- `schedlat` and `psp` read the thread-group leader only (C38 F1), so they
  read about 0 on the multi-threaded apps (data-caching, web-search,
  in-memory-analytics, DeathStarBench), in every environment. Single-threaded
  Redis (app18) is unaffected.
- `mbw` and `llcocc` read 0 where the target is a parent slice with an empty
  `cgroup.procs` (C38 F2): app19 to app22 on bare metal and in containers. In
  vm-guest `mbw` is unavailable and `llcocc` is the miss-ratio proxy, neither
  affected.

This is the rule `C38_PREFIX_MASK` in `bench/plot/plot-tierb-fingerprint.py`
hatches in `fig_fingerprint_v21_prefix.pdf`.

Not affected: every v3.3 cell, the stress-ng spine (`01-tier-a-cross-deployment/`,
`03-cadence-sweep/`), the colocation campaign (`02-w5-colocation/`), and the
other v2.1 metrics.

Keep these trees as they are. If the v2.1 re-run of C38 is done later, it lands
in fresh `04-tier-b-realapps-v021/` and `05-tier-c-dsb-v021/` directories and
the trees above stay the provenance of the pre-fix numbers.

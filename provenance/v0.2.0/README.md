# provenance/v0.2.0 — pre-fix v2.1 readings (D16, C38)

The JSA campaigns ran with release `v0.2.0`. Release `v0.2.1` fixes two v2.1
defects (C38 in `docs/DECISIONS-container.md`) but re-measures nothing, so the
data attached to `v0.2.1` is byte-identical to the `v0.2.0` assets:

| Asset | SHA-256 |
| --- | --- |
| `across-intp-jsa-results-v0.2.0.tar.gz` | `9311351e43d59cf72ccce2e6061e95403ee1ec76c99ba51aa49c955ee1cdee23` |
| `IntP-JSA-complete-data-20260918.tar.xz` | `63e94d2e1d8f4dcb117213c0535085f8f9ece7b099bb0b999b118e0b148190c4` |

Both are also archived in the `v0.2.0` Zenodo record,
[10.5281/zenodo.22970881](https://doi.org/10.5281/zenodo.22970881).

## Which readings are pre-fix

Only **v2.1** cells of the compose-based suites, in
`04-tier-b-realapps/` (`app18`–`app21`) and `05-tier-c-dsb/` (`app22`) of
`across-intp-jsa-results-v0.2.0.tar.gz`, all three environments:

- `schedlat` and `psp` read the thread-group leader only (C38 F1), so they
  read ~0 on multi-threaded servers (web-search, in-memory-analytics,
  DeathStarBench). Single-threaded Redis is unaffected.
- `mbw` and `llcocc` read 0 wherever the target is a parent slice with an
  empty `cgroup.procs` (C38 F2): data-caching, web-search,
  in-memory-analytics and DeathStarBench, on bare metal and in containers.

Not affected: every v3.3 cell, the stress-ng spine (`01-tier-a-cross-deployment/`,
`02-w5-colocation/`, `03-cadence-sweep/`), and the other v2.1 metrics.

Keep these trees as they are. When the v2.1 re-run in C38 exists, it lands in
fresh `04-tier-b-realapps-v021/` and `05-tier-c-dsb-v021/` directories and the
trees above stay as the provenance of the pre-fix numbers.

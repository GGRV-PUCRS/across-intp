# Across-IntP: Multi-Variant Interference Profiler

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.21959350.svg)](https://doi.org/10.5281/zenodo.21959350)

## JSA artifact (release v0.2.1)

This repository is the artifact of the JSA article *Interference Profiling in
Containers and Virtual Machines with IntP*. Everything a reader needs to check
the article's figures is below; the rest of this README describes the
repository as a whole.

### What to cite

| You are citing | Identifier |
| --- | --- |
| The JSA article's code and data | **Version DOI [10.5281/zenodo.23071202](https://doi.org/10.5281/zenodo.23071202)** (release [`v0.2.1`](https://github.com/ggrv-intp/across-intp/releases/tag/v0.2.1)) |
| The latest release, whatever it is | Concept DOI [10.5281/zenodo.21959350](https://doi.org/10.5281/zenodo.21959350) (the badge above); it moves with every release, so do not use it to cite the JSA results |
| The SBAC-PAD 2026 artifact | Release [`v0.1.0`](https://github.com/ggrv-intp/across-intp/releases/tag/v0.1.0). It predates the Zenodo integration and has no version DOI; cite it by its tag, never by the concept DOI |

The campaigns ran with release v0.2.0. Release v0.2.1 adds a post-campaign fix
to the v2.1 profiler (thread and subtree enumeration, DECISIONS.md D16) and
does not re-measure anything: its data files are the v0.2.0 ones, unchanged.

### Where the data are

Zenodo record [23071202](https://zenodo.org/records/23071202) holds the source
snapshot of v0.2.1 and the three data files below. The same three files are
attached to the GitHub releases
[`v0.2.0`](https://github.com/ggrv-intp/across-intp/releases/tag/v0.2.0) and
[`v0.2.1`](https://github.com/ggrv-intp/across-intp/releases/tag/v0.2.1).

| File | Size | What it holds |
| --- | ---: | --- |
| `IntP-JSA-complete-data-20260918.tar.xz` | 121 MB | The frozen campaign archive `IntP-JSA-consolidated-data/`: `final/` holds the six campaigns behind every figure (2394 cells, `final/MANIFEST.md`); `superseded/`, `superseded-prerun-originals/` and `dev-runs/` keep the audit trail; `derived/` holds the IADA train sets. `00-README.md` explains the layout |
| `across-intp-jsa-results-v0.2.0.tar.gz` | 88 MB | The v0.2.0 results payload: campaigns 01 to 05 with their reports and rendered figures. The figure sequence below uses the complete archive, which also carries campaign 06 (overhead) |
| `SHA256SUMS` | | Checksums of both tarballs |

The data tarballs are released under CC BY 4.0; the code is under MIT (see
[LICENSE](LICENSE)).

### Figure and table map

Scripts live under `bench/`; inputs are paths inside
`IntP-JSA-complete-data-20260918.tar.xz`, relative to
`IntP-JSA-consolidated-data/final/`. "Output" names the file the script
writes when it differs from the manuscript's file name.

| Manuscript | File | Script | Input | Output |
| --- | --- | --- | --- | --- |
| Fig. 1, availability | `fig_availability.pdf` | `plot/plot-fig2-3-4-6-8-jsa.py --tag-status` | `01-tier-a-cross-deployment/` | `Figure_2.pdf` |
| Fig. 2, architecture | `fig_arch.pdf` | `plot/plot-fig-arch.py` | none (schematic) | |
| Fig. 3, claim class | `fig_claimclass.pdf` | `plot/plot-fig2-3-4-6-8-jsa.py --tag-status` | `01-tier-a-cross-deployment/` | `Figure_8.pdf` |
| Fig. 4, PSI | `fig_psi.pdf` | `plot/plot-fig2-3-4-6-8-jsa.py --tag-status` | `01-tier-a-cross-deployment/` | `Figure_3.pdf` |
| Fig. 5, cadence | `fig_cadence.pdf` | `plot/plot-cadence-curves.py --jsa-merged` | `03-cadence-sweep/cadence-fidelity.tsv` | |
| Fig. 6, overhead | `fig_overhead.pdf` | `analyze-cadence-overhead.py --jsa-style` | `06-cadence-overhead-F9/` | |
| Fig. 7, pipeline | `fig_pipeline.pdf` | `plot/plot-fig-pipeline.py` | none (schematic) | |
| Fig. 8, faithfulness | `fig_faithfulness.pdf` | `plot/plot-fig6-v2-jsa.py` | `01-tier-a-cross-deployment/cross-deployment.tsv` (regenerated, see below) and `docs/reports/W4-faithfulness-r2.md` (repository) | `Figure_6_v2.pdf` |
| Fig. 9, `membw_est` proxy | `fig_membwproxy.pdf` | `plot/plot-fig2-3-4-6-8-jsa.py --tag-status` | `01-tier-a-cross-deployment/` | `Figure_4.pdf` |
| Fig. 10, preemption | `fig_preempt.pdf` | `plot/plot-fig2-3-4-6-8-jsa.py --tag-status` | `01-tier-a-cross-deployment/` | `Figure_14.pdf` |
| Fig. 11, anomaly (v2.1) | `fig_anomaly.pdf` | `plot/plot-fig9-a3-jsa.py` | `01-tier-a-cross-deployment/aggregate-means.tsv` (from `plot/make-aggregate-means.py`) | `Figure_9.pdf` |
| Fig. 12, in-guest proxy | `fig_vmproxy.pdf` | `plot/plot-fig11-fig12-jsa.py` | `02-w5-colocation/w5-victim-delta-tagged.tsv` | `Figure_12.pdf` |
| Fig. 13, victim delta | `fig_victim.pdf` | `plot/plot-fig11-fig12-jsa.py` | `02-w5-colocation/w5-victim-delta-tagged.tsv` | `Figure_11.pdf` |
| Fig. 14, fingerprint (v3.3) | `fig_fingerprint_v33.pdf` | `plot/plot-tierb-fingerprint.py --variants v3.3` | `04-tier-b-realapps/` and `05-tier-c-dsb/` via `analyze-tierb.py --tag-status` | |
| Fig. 15, decision procedure | | none: TikZ in the manuscript | none | |
| Fig. A.1, anomaly (v3.3) | `figA_anomaly_v33.pdf` | `plot/plot-fig9-a3-jsa.py` | as Fig. 11 | `Figure_A3.pdf` |
| Fig. A.2, fingerprint (v2.1, masked) | `fig_fingerprint_v21_prefix.pdf` | `plot/plot-tierb-fingerprint.py --variants v2.1 --mask c38-prefix` | as Fig. 14 | |

| Manuscript | Source |
| --- | --- |
| Table 2, deployment environments | `final/*/metadata.txt`, `capabilities.env`, `variants.manifest` in the archive; host build in [bench/setup/REPRODUCTION.md](bench/setup/REPRODUCTION.md) |
| Table 3, workload set | `bench/run-intp-bench.sh` (synthetic layer), `bench/workloads/compose/` and `bench/setup/stage-next-campaigns.sh` (real applications and DeathStarBench) |
| Table 4, campaign inventory | `final/MANIFEST.md` in the archive (cell counts per campaign) |
| Table 5, faithfulness verdicts | [docs/reports/W4-faithfulness-r2.md](docs/reports/W4-faithfulness-r2.md), [docs/reports/portable-faithfulness.md](docs/reports/portable-faithfulness.md) |
| Table 6, findings summary | Summarizes Figs. 1, 4, 8, 9, 10, 12 and 14; each row's numbers come from the figure's input above and from [docs/reports/p2-cross-deployment-15metric.md](docs/reports/p2-cross-deployment-15metric.md), [docs/reports/w5-victim-delta.md](docs/reports/w5-victim-delta.md) and [docs/reports/p2-tierb-15metric.md](docs/reports/p2-tierb-15metric.md) |
| Table 7, corrections and open findings | [docs/DECISIONS-container.md](docs/DECISIONS-container.md) (mid-campaign corrections, C-entries) and [DECISIONS.md](DECISIONS.md) D16 to D18 (the v0.2.1 fix) |

Table 1 (comparison with prior systems) is drawn from the literature and has no
data source here. [PAPER-SYNC.md](PAPER-SYNC.md) records how each figure and
number reached the manuscript.

### Regenerate the figures without a testbed

Needs Python 3 with `pip install -r bench/plot/requirements.txt`; no root, no
RDT hardware. From an empty directory:

```bash
git clone --branch v0.2.1 https://github.com/ggrv-intp/across-intp.git
mkdir jsa-data && cd jsa-data
for f in IntP-JSA-complete-data-20260918.tar.xz SHA256SUMS; do
  curl -LO "https://zenodo.org/records/23071202/files/$f"
done
grep IntP-JSA-complete SHA256SUMS | sha256sum -c -
tar xJf IntP-JSA-complete-data-20260918.tar.xz
cd ../across-intp
D=../jsa-data/IntP-JSA-consolidated-data/final
OUT=../jsa-figs; mkdir -p "$OUT"

# Derived tables. The first call rewrites the archive's cross-deployment.tsv,
# which predates the app16/app17 rows (710 rows; regenerated: 994).
python3 bench/analyze-cross-deployment.py $D/01-tier-a-cross-deployment --out $OUT/xdeploy.md
python3 bench/analyze-cross-deployment.py $D/01-tier-a-cross-deployment --tag-status --out $OUT/xdeploy-tagged.md
python3 bench/analyze-cross-deployment.py $D/02-w5-colocation --w5 --tag-status --out $OUT/w5.md
python3 bench/plot/make-aggregate-means.py $D/01-tier-a-cross-deployment \
    --out $D/01-tier-a-cross-deployment/aggregate-means.tsv
python3 bench/analyze-tierb.py $D/04-tier-b-realapps --tag-status --tsv $OUT/fp-tierb.tsv --out $OUT/tierb.md
python3 bench/analyze-tierb.py $D/05-tier-c-dsb --tag-status --tsv $OUT/fp-tierc.tsv --out $OUT/tierc.md
{ cat $OUT/fp-tierb.tsv; tail -n +2 $OUT/fp-tierc.tsv; } > $OUT/fingerprints-tagged.tsv

# Figures (file names per the map above)
python3 bench/plot/plot-fig2-3-4-6-8-jsa.py $D/01-tier-a-cross-deployment --tag-status --out $OUT/set1
python3 bench/plot/plot-fig-arch.py --out $OUT/fig_arch.pdf
python3 bench/plot/plot-cadence-curves.py $D/03-cadence-sweep/cadence-fidelity.tsv \
    --out $OUT/cadence --jsa-merged $OUT/fig_cadence.pdf
python3 bench/analyze-cadence-overhead.py $D/06-cadence-overhead-F9 --tsv $OUT/overhead.tsv \
    --out $OUT/overhead.md --fig $OUT/overhead --jsa-style $OUT/fig_overhead.pdf
python3 bench/plot/plot-fig-pipeline.py --out $OUT/fig_pipeline.pdf
python3 bench/plot/plot-fig6-v2-jsa.py $D/01-tier-a-cross-deployment \
    --report docs/reports/W4-faithfulness-r2.md --out $OUT/faith
python3 bench/plot/plot-fig9-a3-jsa.py $D/01-tier-a-cross-deployment --out $OUT/anomaly
python3 bench/plot/plot-fig11-fig12-jsa.py $D/02-w5-colocation/w5-victim-delta-tagged.tsv --out $OUT/w5
python3 bench/plot/plot-tierb-fingerprint.py $OUT/fingerprints-tagged.tsv \
    --variants v3.3 --pdf $OUT/fig_fingerprint_v33.pdf
python3 bench/plot/plot-tierb-fingerprint.py $OUT/fingerprints-tagged.tsv \
    --variants v2.1 --mask c38-prefix --pdf $OUT/fig_fingerprint_v21_prefix.pdf
```

Checked on 2026-10-01 from a clean clone and the release tarball (Python 3.14,
Matplotlib 3.11.2) against the manuscript's figure files, rasterized at
150 dpi:

- **Identical pixels and text**: Figs. 1, 3 to 13 and A.1. Fig. 2 matched
  as well before the context marking described in DECISIONS.md D20.
- **Visually identical, same values**: Figs. 14 and A.2. The page is about
  0.4% wider because the manuscript files were rendered with Matplotlib
  3.10.7.
- **Byte-identical**: none. Matplotlib embeds a creation date in every PDF.

Two traps, both avoided by the sequence above:

- `bench/render-jsa-paper-figures.sh` reads `cross-deployment.tsv` as
  shipped, so Fig. 8 loses its app16/app17 rows.
- The same script passes `--by-env-tsv`, which adds a third row to Fig. 5 that
  the manuscript does not have.

### Requirements to re-run the campaigns

Re-measuring, as opposed to re-plotting, needs:

- an Intel CPU with RDT exposed through `resctrl` (the testbed is a Xeon Gold
  5412U, Sapphire Rapids);
- cgroup v2;
- root;
- the kernel the campaigns ran on, 6.17.0-35-generic (Ubuntu 24.04.4 LTS).

The VM leg also needs KVM with PMU pass-through. Host provisioning, calibration
and the step-by-step checklist are in
[bench/setup/REPRODUCTION.md](bench/setup/REPRODUCTION.md).

<img src="docs/images/across-intp.png" alt="Across-IntP: Linux interference profiler with multi-variant comparison of SystemTap, procfs, bpftrace, and eBPF/CO-RE instrumentation." width="720">

This repository contains eleven implementation variants of IntP, an interference
profiler that collects 7 metrics from the Linux kernel. The variants are
organized for systematic comparison as part of a Master's dissertation on
kernel instrumentation for interference profiling (PPGCC/PUCRS, advisor
Prof. Cesar De Rose). It is the companion artifact of the SBAC-PAD 2026 paper
that reports the comparison.

**Three of the eleven are the measured versions** the paper evaluates:
**V0.2 (intp-baseline)**, the legacy-faithful reference, which keeps the 2022
SystemTap probe set verbatim and isolates the two RCU-unsafe operations in a
userspace helper; **V2 (C-ABI)**, a portable C implementation on stable
userspace ABIs; and **V3.2 (eBPF-CORE)**, eBPF/CO-RE with in-kernel
aggregation. Six more (stap-2022, stap-nollc, stap-nohelper, stap-modern,
ebpf-ring, bpftrace) are structural evidence: they document the portability and
reliability cliffs, prove out an architecture, or corroborate the measured
results. The remaining two per-cgroup variants, **V2.1 (c-abi-cgroup)** (pure
C, per-cgroup attribution) and **V3.3 (ebpf-core-cgroup)** (eBPF/CO-RE,
per-cgroup, in-kernel aggregation), are the active profilers for the
cross-deployment work of the JSA article. The comparison axes are **portability,
overhead, and fidelity**.

## About

**Author:** André Sacilotto Santos (PPGCC/PUCRS)
**Advisor:** Prof. Cesar De Rose
**Program:** Post-Graduate Program in Computer Science -- PPGCC, PUCRS
**Research Area:** Cloud computing performance, kernel instrumentation, interference profiling

### Background

IntP (Interference Profiler) was originally developed by Xavier et al. (2022, PUCRS)
as a SystemTap-based tool for measuring resource interference between co-located workloads
in cloud environments. It collects seven low-level metrics (network physical, network
stack, block I/O, memory bandwidth, LLC miss ratio, LLC occupancy, CPU) to characterize
how one tenant's resource usage affects another's performance.

This work extends and refactors IntP to support modern Linux kernels (6.8+) and
modern instrumentation frameworks (bpftrace, eBPF/CO-RE), addressing the fragility of
the original SystemTap approach across kernel versions and hardware architectures.

### Research Goals

1. Reproduce the original IntP baseline (stap-2022) and document breakage on kernel 6.8+.
2. Develop minimal patches to restore functionality on current kernels (stap-nollc, stap-nohelper) and stap+helper hybrids that recover full metric coverage without RCU-unsafe operations: legacy-intp-baseline on kernel 5.15 GA (Ubuntu 22.04, paper-faithful stap-2022 semantics) and stap-modern on kernel 6.8+.
3. Implement kernel-module-free alternatives using procfs/perf_event (C-ABI), bpftrace, and eBPF/CO-RE (ebpf-ring).
4. Compare all eleven variants across the paper's three axes (portability, overhead, and fidelity) plus deployment complexity and safety.

### Status

Role names follow the paper's Table I. **Measured** marks the three versions the
paper's results are computed from; the rest are structural evidence, except the
two per-cgroup variants, which are the cross-deployment profilers of the JSA article.

| Variant | Role (paper Table I) | Status |
| --------- | -------- | -------- |
| V0 (stap-2022) -- Original (SystemTap, needs `intel_cqm` driver; mainline removed it in 4.14) | Cliff (portability) | Reference only; in practice runs only on a pre-4.14 mainline kernel, an enterprise kernel still carrying the `intel_cqm` backport, or a custom build with the driver restored |
| V0.1 (stap-nollc) -- Updated (SystemTap, LLC disabled) | Cliff (portability, partial) | Complete; recovers compilation at the cost of `llcocc` (6/7 metrics) |
| V0.2 (legacy-intp-baseline) -- Stap + userspace helper (SystemTap, 5.15 GA, stap-2022-faithful, RCU-safe) | **Measured** (`intp-baseline`) | Complete; the campaign's UB22 leg (kernel 5.15.0-177) |
| V1 (stap-nohelper) -- Stap-native (SystemTap, 6.8+, mbw/llcocc disabled) | Cliff (reliability) | Complete; emits `mbw`/`llcocc` as zeros and destabilizes `systemd-logind`; that is the result it exists to show |
| V1.1 (stap-modern) -- Stap + userspace helper (SystemTap, 6.8+, full metrics, RCU-safe) | Arch. proof (kernel 6.8) | Complete; carries the V0.2 helper design to 6.8 to prove SystemTap needs it there. Not a measured endpoint. HiBench distributed-mode limitation documented in METRICS-ALIGNMENT.md |
| V2 (C-ABI) -- C / procfs / perf_event / resctrl | **Measured** | Complete; the campaign's UB24 leg (kernel 6.8.0-111) |
| V2.1 (c-abi-cgroup) -- C, per-cgroup attribution (cgroup v2 + perf cgroup mode, no eBPF) | JSA profiler | Active; validated on Hetzner Sapphire Rapids |
| V3.1 (bpftrace) -- bpftrace + Python orchestrator | Companion (corroboration) | Complete; mirrors V3's attachment points |
| V3 (ebpf-ring) -- eBPF/CO-RE (libbpf, ring-buffer-streaming) | Predecessor (mechanism) | Complete; retained to contrast overhead profiles with V3.2; it is the variant that shows the ~194-416x context-switch amplification |
| V3.2 (eBPF-CORE) -- eBPF/CO-RE (libbpf, in-kernel-aggregating, paper §III-A) | **Measured** | Complete; the campaign's UB24 leg (kernel 6.8.0-111) |
| V3.3 (ebpf-core-cgroup) -- eBPF/CO-RE (libbpf, per-cgroup, in-kernel-aggregating) | JSA profiler | Active; validated on Hetzner Sapphire Rapids |

All measurements were collected on a single-socket Intel Xeon Gold 5412U
(Sapphire Rapids, 24 physical / 48 logical cores, 256 GB DDR5), dual-booted
across the two kernel series.

### Citation

If you use this software in your research, please cite it using the metadata in
[CITATION.cff](CITATION.cff). A full thesis citation will be added upon defense
(expected until March 2027).

### Where the measurement data lives

**The campaign data and the rendered figures are not files in this repository.**
Cloning the repository will not produce them; download them instead.

- **JSA article (v0.2.0 campaigns, cited as v0.2.1)**: Zenodo record
  [23071202](https://zenodo.org/records/23071202) (version DOI
  10.5281/zenodo.23071202) holds `across-intp-jsa-results-v0.2.0.tar.gz`,
  `IntP-JSA-complete-data-20260918.tar.xz` and `SHA256SUMS`. The same files are
  attached to the GitHub releases
  [`v0.2.0`](https://github.com/ggrv-intp/across-intp/releases/tag/v0.2.0) and
  [`v0.2.1`](https://github.com/ggrv-intp/across-intp/releases/tag/v0.2.1). See
  [JSA artifact](#jsa-artifact-release-v021) for what each file holds.
- **SBAC-PAD paper**: release assets of
  [`v0.1.0`](https://github.com/ggrv-intp/across-intp/releases/tag/v0.1.0) only
  (no Zenodo record), about 350 MB of measurement output that would swamp a
  source tree:

| v0.1.0 release asset | What it holds |
| --- | --- |
| `across-intp-sbac-results-v0.1.0.tar.gz` | The anonymized campaign payload: the fusion tree of `run.json` records and profiler traces, `aggregate-means.tsv`, the fragility tables, the §V backing tables under `paper-tables/`, and `published/` with the 33 figure PDFs (13 of them camera-ready renders) plus `QA-FIGS.md`, the typography gate report |
| `consolidation-raw.tar.gz` | The pre-anonymization raw sources: the five measurement sessions across two hosts, the auxiliary reruns behind the §V-B amplification result, and the fusion trees with their PROVENANCE records |
| `SHA256SUMS` | Integrity reference covering both tarballs |

What this repository *does* carry is everything that **produced** those assets:
the eleven variants under `variants/`, the campaign drivers and complete plotting
pipeline under `bench/`, and
[sbac-results/PROVENANCE.md](sbac-results/PROVENANCE.md), the chain from the
SBAC-PAD measurement sessions to the published tarballs (the JSA counterpart is
[provenance/v0.2.0/](provenance/v0.2.0/README.md)). Note that `sbac-results/` holds
that provenance record and its README **only**; the results themselves are in
the release assets, not in that directory.

In [docs/READER-MAP.md](docs/READER-MAP.md) every row is tagged **repo:** or
**artifact:** precisely so this stays unambiguous.

### Releases

| Release | What it is |
| --- | --- |
| [`v0.1.0`](https://github.com/ggrv-intp/across-intp/releases/tag/v0.1.0) | The SBAC-PAD 2026 artifact, with the data assets above. The `release/v0.1.0` branch holds the same tree for browsing without downloading. |
| [`v0.2.0`](https://github.com/ggrv-intp/across-intp/releases/tag/v0.2.0) | Superseded by v0.2.1 (code fix; same data). The JSA campaigns ran with this release: the container-based interference work (v2.1 and v3.3 per-cgroup profilers, the cross-deployment suite, the IADA simulator campaigns). Campaign results and the frozen campaign archive are attached as release assets. See `docs/DECISIONS-container.md` and DECISIONS.md D15. |
| [`v0.2.1`](https://github.com/ggrv-intp/across-intp/releases/tag/v0.2.1) | The JSA artifact as cited. Fixes v2.1 per-thread scheduler metrics (`schedlat`, `psp`) and recursive RDT enrollment (C38); the affected cells are not re-measured. The data assets are the v0.2.0 ones, unchanged; see [provenance/v0.2.0/](provenance/v0.2.0/README.md) and DECISIONS.md D16 to D18. |

The production profiler built from V2.1 and V3.3 is `intp`, packaged for
Ubuntu in [`ppa:norohim/intp`](https://launchpad.net/~norohim/+archive/ubuntu/intp);
its `SYNC.md` names the commit of this repository it is synced with.

## Variant Comparison

| Feature                  | V0 classic | V0.1 k68 | V0.2 helper | V1 native | V1.1 helper | V2 stable-abi | V2.1 cgroup | V3.1 bpftrace | V3 ebpf-core | V3.2 eBPF-CORE | V3.3 ebpf-core-cgroup |
|--------------------------|:----------:|:--------:|:-----------:|:---------:|:-----------:|:-------------:|:-----------:|:-------------:|:------------:|:--------------:|:----------------:|
| Kernel module required   |    Yes     |   Yes    |     Yes     |    Yes    |     Yes     |      No       |     No      |     No        |      No      |      No        |       No         |
| Userspace helper         |    No      |   No     |     Yes     |    No     |     Yes     |      n/a      |     n/a     |     Yes       |     Yes      |      Yes       |       Yes        |
| Debuginfo required       |    Yes     |   Yes    |     Yes     |    Yes    |     Yes     |      No       |     No      |   No (BTF)    |   No (BTF)   |   No (BTF)     |     No (BTF)      |
| Kernel crash risk        |    High    |   High   |     Low     |    Low    |     Low     |     None      |    None     |    None       |     None     |     None       |      None        |
| Min kernel version       |   <=6.6    |   6.8+   |  5.15 GA    |    6.8+   |     6.8+    |     4.10+     |    5.8+     |    5.8+       |     5.8+     |    5.8+        |      5.8+         |
| Per-cgroup attribution   |     No     |    No    |     No      |     No    |     No      |      No       |     Yes     |     No        |      No      |      No        |      Yes         |
| netp                     |     x      |    x     |      x      |     x     |      x      |       x       |      x      |       x       |       x      |       x        |       x          |
| nets (service-time)      |     x      |    x     |      x      |     x     |      x      |       ~       |      ~      |       x       |       x      |       x        |       x          |
| blk                      |     x      |    x     |      x      |     x     |      x      |       x       |      x      |       x       |       x      |       x        |       x          |
| mbw                      |     x      |    x     |      x      |     -     |      x      |       x       |      x      |       x       |       x      | x + raw MB/s   |   x + raw MB/s   |
| llcmr                    |     x      |    x     |      x      |     x     |      x      |       x       |      x      |       x       |       x      |       x        |       x          |
| llcocc                   |     x      |    -     |      x      |     -     |      x      |       x       |      x      |       x       |       x      |       x        |       x          |
| cpu                      |     x      |    x     |      x      |     x     |      x      |       x       |      x      |       x       |       x      |       x        |       x          |
| Framework                | SystemTap  | SystemTap| SystemTap+C | SystemTap | SystemTap+C |     None      |    None     |   bpftrace    |    libbpf    |    libbpf      |     libbpf       |
| Per-event introspection  |    Yes     |   Yes    |     Yes     |    Yes    |     Yes     |      No       |     No      |     Yes       |     Yes      |      No        |      No          |
| AMD EPYC compatible      |  Partial   |  Partial |   Partial   |  Partial  |   Partial   |      Yes      |     Yes     |     Yes       |      Yes     |      Yes       |      Yes         |
| ARM server compatible    |    No      |   No     |     No      |    No     |     No      |    Partial    |   Partial   |   Partial     |    Partial   |    Partial     |    Partial       |

x = supported, ~ = polling approximation, - = disabled in this build

## The 7 Metrics

- **netp** -- Network physical utilization (NIC TX+RX bandwidth)
- **nets** -- Network stack utilization (kernel networking service time)
- **blk** -- Block I/O utilization (disk busy percentage)
- **mbw** -- Memory bandwidth utilization (LLC-to-DRAM traffic)
- **llcmr** -- LLC miss ratio (cache misses / cache references)
- **llcocc** -- LLC occupancy (bytes of last-level cache occupied)
- **cpu** -- CPU utilization (user + system time percentage)

### VM-portable metrics (separate `--portable-metrics` benchmark)

A stock KVM guest cannot measure `mbw`/`llcocc` (resctrl is host-only) or a
comparable `llcmr` (the LL-read PMU events are not virtualized). `v2.1` and `v3.3`
therefore offer eight additional columns -- six portable metrics computed by the
**guest's own kernel** plus a scheduling-regime pair -- as a SEPARATE, flag-gated
benchmark (`--portable-metrics`); the canonical 7-metric
fingerprint above and its on-disk schema are left untouched. Design + status:
[docs/reports/8th-metric-vm-portable-design.md](docs/reports/8th-metric-vm-portable-design.md).

- **schedlat** -- run-queue wait of the target's threads, % of interval × CPUs
  (eBPF `sched_wakeup`→`sched_switch` in v3.3; per-thread `/proc/<tid>/schedstat`
  in v2.1, PSI `cpu.pressure` as fallback); *directional*
- **psi_mem** -- PSI `memory.pressure` (memory-capacity contention); *descriptive*
- **membw_est** -- DRAM-bandwidth estimate (LLC misses × 64 B / interval, MB/s; the
  bandwidth complement `psi_mem` is blind to, and the metric that survives in-guest); *descriptive*
- **psi_io** -- PSI `io.pressure` (`blk`'s contention companion); *descriptive*
- **schedthr** -- CFS throttling (`cpu.stat` `throttled_usec`, a confound guard;
  reads 0 without a `cpu.max` limit and counts only the cgroup's own limit); *descriptive*
- **steal** -- hypervisor-stolen vCPU time (`/proc/stat`; VM-global, reflects host
  CPU contention only); *descriptive*
- **psp** -- involuntary preemptions/s of the target's threads (scheduling regime;
  not Volpert's PSP, whose throttling role `schedthr` plays)
- **idle_preempt** -- idle-CPU takeovers/s: the target's tasks dispatched onto a
  previously idle CPU (scheduling regime; eBPF-only, `--` in v2.1)

## Directory Layout

```text
.
|-- README.md                  This file
|-- LICENSE                    MIT license
|-- CITATION.cff               Citation metadata (software + the SBAC-PAD 2026 paper)
|-- VERSIONS.md                Variant-naming map (current vs legacy pre-2026-05-05)
|-- DECISIONS.md               Decision log, including the two release refreshes (D10, D11)
|-- METRICS-ALIGNMENT.md       Per-metric equivalence across variants, and where it is only approximate
|-- Makefile                   Build entry points for the compiled variants
|-- capabilities-sbacpad.env   Capability snapshot of the campaign host
|-- run-big-batch.sh           Full campaign driver (stress-ng + HiBench, all envs)
|-- run-smoke-all.sh           Fast all-variant sanity sweep
|-- ub22run.sh / ub24run.sh    Per-OS campaign drivers (kernel 5.15 leg / kernel 6.8 leg)
|-- docs/                      Cross-variant documentation
|   |-- READER-MAP.md          Start here if you arrived from the paper
|   |-- METRICS-DEEP-DIVE.md   Probe points, formulas and constants behind the 7 metrics
|   |-- VARIANT-COMPARISON.md  Detailed rationale for each of the eleven variants
|   |-- KERNEL-6.8-CHANGES.md  What kernel 6.8 broke and why
|   |-- PORTABILITY-ROADMAP.md Cross-kernel, cross-arch analysis
|   |-- HARDWARE-COMPATIBILITY.md  RDT / PQoS / MPAM feature tables
|   |-- EXPERIMENT-STRATEGY.md Operational gotchas, run discipline, workload->metric stress map
|   |-- V3-OVERHEAD-FINDINGS.md  Context-switch amplification, its decomposition, the mbw silent clip
|   |-- CROSS-ENV-CAMPAIGN.md  bare / container / VM campaign design
|   |-- NETP-SYNTHETIC-TRAFFIC.md  veth + iperf3 workload rationale
|   |-- PAPER-CROSS-REFERENCES.md  Historical (writing phase); draft section numbering
|   |-- images/                Repository banner
|-- shared/                    Components used across variants
|   |-- intp-detect.sh         Hardware capability detection
|   |-- intp-preflight.sh      Pre-run environment gate
|   |-- intp-resctrl-helper.sh resctrl companion daemon
|   |-- intp-ebpf-checkout.sh  libbpf/vmlinux.h bootstrap for the eBPF variants
|   |-- validate-cross-variant.sh  Cross-variant output contract check
|-- variants/                  One directory per IntP implementation variant
|   |-- v0-stap-2022/          Unmodified 2022 IntP (SystemTap; needs pre-4.14 cqm_rmid)
|   |-- v0.1-stap-nollc/       Compilation recovered by dropping llcocc (6/7 metrics)
|   |-- v0.2-legacy-intp-baseline/  MEASURED `intp-baseline`: kernel 5.15, V0-faithful stap + userspace helper
|   |-- v1-stap-nohelper/      Kernel 6.8+, stap-native probes (mbw/llcocc disabled)
|   |-- v1.1-stap-modern/      Kernel 6.8+, stap + userspace helper (architectural proof)
|   |-- v2-c-abi/              MEASURED `C-ABI`: pure C over procfs / perf_event_open / resctrl
|   |-- v2.1-c-abi-cgroup/     Pure C, per-cgroup attribution (cgroup v2 + perf cgroup mode, no eBPF)
|   |-- v3-ebpf-ring/          eBPF/CO-RE with libbpf, ring-buffer-streaming
|   |-- v3.1-bpftrace/         bpftrace scripts + Python orchestrator + resctrl
|   |-- v3.2-ebpf-core/        MEASURED `eBPF-CORE`: eBPF/CO-RE, in-kernel aggregation (paper §III-A)
|   |-- v3.3-ebpf-core-cgroup/ eBPF/CO-RE, per-cgroup targeting + in-kernel aggregation (JSA cross-deployment path)
|-- bench/                     Campaign harness and analysis pipeline
|   |-- OVERVIEW.md            Workload table, campaign stages, run accounting
|   |-- run-intp-bench.sh      stress-ng campaign driver (per-variant kernel gates live here)
|   |-- run-os-campaign.sh     Per-OS leg orchestration
|   |-- publish-sbac-results.sh  Merge a campaign tree into sbac-results/ layout
|   |-- plot/                  Full plotting pipeline + camera-ready figure gate
|   |-- hibench/               HiBench Spark subset provisioning and sweep
|   |-- setup/                 Testbed provisioning, REPRODUCTION.md
|   |-- findings/              Per-campaign empirical notes
|   |-- deploy/                Remote deployment helpers
|   |-- iada/                  IADA downstream-classifier integration
|-- sbac-results/              Provenance record ONLY -- the data itself is a release asset
|   |-- PROVENANCE.md          Chain from the measurement sessions to the published tarballs
|   |-- README.md              Layout of the published tree inside the artifact
```

The campaign output tree (`results/`) is gitignored: it is reproduced by the
drivers above, and its published form ships as the release assets described in
[Where the measurement data lives](#where-the-measurement-data-lives).

## Quick Start

### V0 (stap-2022) -- Original IntP (kernel <= 6.6)

```bash
cd variants/v0-stap-2022
sudo stap -g intp.stp <PID> <interval_ms>
```

Requires: SystemTap, kernel debuginfo, kernel <= 6.6.

### V0.1 (stap-nollc) -- Updated for Kernel 6.8 (LLC disabled)

```bash
cd variants/v0.1-stap-nollc
sudo stap -g intp-6.8.stp <PID> <interval_ms>
```

Requires: SystemTap, kernel debuginfo, kernel 6.8+. Note: llcocc returns 0.

### V0.2 (legacy-intp-baseline) -- stap-2022-faithful + userspace helper (kernel 5.15 GA / Ubuntu 22.04)

```bash
cd variants/v0.2-legacy-intp-baseline
make
sudo INTP_HELPER_IMC_PMU_TYPE=14 \
     INTP_HELPER_DRAM_BW_MBPS=34000 \
     INTP_HELPER_L3_SIZE_KB=35840 \
     ./intp-helper <comm-pattern> &
sudo bash generate-stp.sh
sudo stap -g intp.recal.stp <comm-pattern>
# after run: kill the helper
```

Requires: SystemTap, kernel debuginfo, **kernel 5.15 GA (Ubuntu 22.04)**,
Intel RDT (resctrl) for `llcocc`, uncore IMC PMU for `mbw`. Same helper
pattern as stap-modern, but the SystemTap script keeps the paper-faithful stap-2022
probes (no softirq tapset switch). The helper isolates the two RCU-unsafe
operations (uncore IMC perf events, cqm_rmid LLC occupancy) from probe
context, eliminating stap-2022's fragility cliff on the Canonical RCU-backport
kernel.

### V1 (stap-nohelper) -- Stap-native (5/7 metrics; no helper, no embedded I/O)

```bash
cd variants/v1-stap-nohelper
sudo stap -g intp-resctrl.stp <comm-pattern>
```

Requires: SystemTap 5.x, kernel debuginfo, kernel 6.8+. mbw and llcocc are
reported as 0 (deferred to stap-modern).

### V1.1 (stap-modern) -- Stap + userspace helper (full 7/7 metrics, RCU-safe)

```bash
cd variants/v1.1-stap-modern
make
sudo ./intp-helper <comm-pattern> &
sudo stap -g intp-v1.1.stp <comm-pattern>
# after run: kill the helper
```

Requires: SystemTap 5.x, kernel debuginfo, kernel 6.8+, Intel RDT (resctrl)
for `llcocc`, uncore IMC PMU for `mbw`. mbw/llcocc gracefully degrade to 0
if hardware is unavailable.

### V2 (C-ABI) -- C: procfs / perf_event / resctrl

```bash
cd variants/v2-c-abi
make
sudo ./intp-c-abi -p <PID> -i <interval_ms>
```

No framework dependencies. Requires: resctrl for mbw/llcocc.

### V2.1 (c-abi-cgroup) -- C: c-abi-cgroup per-cgroup attribution

```bash
cd variants/v2.1-c-abi-cgroup
make
# system-wide / per-PID (like v2):
sudo ./intp-c-abi --pids <PID> --interval <seconds>
# per-cgroup (continuous, child-inclusive) -- e.g. a container's cgroup:
sudo ./intp-c-abi --cgroup /sys/fs/cgroup/<path> --interval <seconds>
```

C-ABI's hybrid-C sibling with continuous per-cgroup attribution: cpu/blk/llcmr read
cgroup v2 `cpu.stat`/`io.stat` and `perf_event_open` cgroup mode when `--cgroup`
is given; disk bandwidth self-detects. `nets` stays system-wide (softirq is
host-global without eBPF). One code path serves bare co-located processes,
containers, and VM guests -- the container / IADA path of the JSA article; see
`variants/v2.1-c-abi-cgroup/DESIGN.md`. Requires kernel 5.8+ (cgroup v2);
resctrl for mbw/llcocc.

```bash
# VM-portable benchmark: append the 6 portable columns (separate, canonical 7
# untouched). Same flag on v3.3. Analyze with bench/analyze-portable.py.
sudo ./intp-c-abi --cgroup /sys/fs/cgroup/<path> --portable-metrics --interval 1
```

### V3.1 (bpftrace) -- bpftrace

```bash
cd variants/v3.1-bpftrace
sudo ./run-intp-bpftrace.sh <PID> <interval_ms>
```

Requires: bpftrace, kernel BTF, resctrl for mbw/llcocc.

### V3 (ebpf-ring) -- eBPF/CO-RE

```bash
cd variants/v3-ebpf-ring
make
sudo ./intp-ebpf-ring -p <PID> -i <interval_ms>
```

Requires: libbpf, clang, kernel BTF, resctrl for mbw/llcocc.

### V3.2 (eBPF-CORE) -- eBPF/CO-RE in-kernel aggregating

```bash
cd variants/v3.2-ebpf-core
make
sudo ./intp-ebpf-core --pids <PID> --interval <seconds>

# Critical acceptance gate before campaign inclusion:
sudo make test-amplification
```

eBPF-CORE is the in-kernel-aggregating variant specified in paper §III-A:
same probe set as ebpf-ring, but the 16 MiB ring buffer is replaced
with per-CPU + per-PID counter maps polled once per `--interval`.
The userspace consumer is no longer draining a continuous event
stream, which eliminates the 194-416x context-switch amplification
documented in paper §V-B -- the auxiliary rerun measures eBPF-CORE at
1.0x the no-profiler baseline on all three reference loads.

Requires: libbpf, clang, kernel BTF, resctrl for mbw/llcocc (same as
ebpf-ring). Adds a trailing `mbw_raw_mbps` diagnostic column to the TSV
output (suppressible via `--no-raw-mbw`); the first 7 columns stay
byte-compatible with ebpf-ring.

### V3.3 (ebpf-core-cgroup) -- eBPF/CO-RE per-cgroup

```bash
cd variants/v3.3-ebpf-core-cgroup
make
# system-wide / per-PID (like v3.2):
sudo ./intp-ebpf-core-cgroup --pids <PID> --interval <seconds>
# per-cgroup (child-inclusive) -- e.g. a container's cgroup:
sudo ./intp-ebpf-core-cgroup --cgroup /sys/fs/cgroup/<path> --interval <seconds>
# container alias / VM guest:
sudo ./intp-ebpf-core-cgroup --target-container /sys/fs/cgroup/<path> --interval <seconds>
sudo ./intp-ebpf-core-cgroup --target-vm <nic> --cgroup /sys/fs/cgroup/<qemu-scope> --interval <seconds>
```

ebpf-core-cgroup is the eBPF/CO-RE counterpart of c-abi-cgroup: it keeps eBPF-CORE's
in-kernel aggregation but adds per-cgroup targeting, attributing the canonical 7
metrics to one container or VM-guest cgroup instead of system-wide.
`--cgroup` (or its alias `--target-container`) scopes a cgroup;
`--target-vm <nic>` / `--tap-iface <nic>` source VM `netp` from the
host tap/vnet interface while the other six metrics are scoped via
`--cgroup` over the QEMU scope. `--no-diag-cols` suppresses the
trailing diagnostic columns. This is the active eBPF profiler for the
JSA cross-deployment suite; see
`variants/v3.3-ebpf-core-cgroup/DESIGN.md`.

Requires: libbpf, clang, kernel BTF, kernel 5.8+ (cgroup v2), resctrl
for mbw/llcocc.

### Full per-OS campaign (one command)

`ub24run.sh` and `ub22run.sh` (repo root) run the entire SBAC-PAD
pipeline for one OS leg end to end: veth setup -> stress-ng (cluster
down) -> bring Hadoop/Spark/HiBench up -> HiBench (cluster up) -> tear
down -> publish into `sbac-results/`.

```bash
sudo bash ub24run.sh             # Ubuntu 24.04 leg -- v1.1, v2, v3.2 (bare metal)
sudo bash ub22run.sh             # Ubuntu 22.04 leg -- v0.2 (bare metal)
sudo bash containerun24.sh       # container leg -- v2.1 in LXC/LXD (JSA article)
sudo bash ub24run.sh --dry-run   # preview every step, run nothing
```

`ub24run.sh`/`ub22run.sh` wrap `bench/run-os-campaign.sh` (`--help` for all
knobs and the `SKIP_*` resume flags); `containerun24.sh` is the c-abi-cgroup
container counterpart -- it pins the `container-lxc` env and drives
`run-big-batch.sh` (stress-ng leg; HiBench off until a container HiBench
launcher exists). See
[bench/setup/REPRODUCTION.md](bench/setup/REPRODUCTION.md) section 9b.

## JSA article: cross-deployment suite

The JSA article runs the SAME application across six deployment legs --
bare → docker (container) → podman (container-podman) → incus
(container-lxc) → k3s (container-k8s) → vm-guest -- and profiles each
with the per-cgroup variants V2.1 (c-abi-cgroup) and V3.3 (ebpf-core-cgroup),
reporting paired deltas against the `bare` baseline. Each metric carries a
claim class wired to the W4 faithfulness verdicts: `cpu` is absolute, `llcmr`
is directional, and the remaining metrics are descriptive. The parity contract
treats network mode and storage backend as the only treatment variables, with a
per-run `caps_applied` audit so the legs stay comparable.

The `vm-guest` leg yields valid per-cgroup `cpu`, but the RDT/PMU metrics
(`mbw`, `llcocc`, `llcmr`) are structurally gapped under KVM -- resctrl is
host-only and last-level-cache perf events are not virtualized. The VM
path therefore uses a separate, flag-gated benchmark
(`--portable-metrics`: `schedlat`, `psi_mem`, `membw_est`, `psi_io`,
`schedthr`, `steal`, plus the scheduling-regime pair `psp` and
`idle_preempt`) so the canonical 7-metric contract (netp nets blk mbw
llcmr llcocc cpu) stays intact. See
[docs/CROSS-ENV-CAMPAIGN.md](docs/CROSS-ENV-CAMPAIGN.md),
[docs/DECISIONS-container.md](docs/DECISIONS-container.md), and
[docs/reports/8th-metric-vm-portable-design.md](docs/reports/8th-metric-vm-portable-design.md).

## Documentation

- [Hardware Compatibility](docs/HARDWARE-COMPATIBILITY.md) -- RDT, PQoS, MPAM tables
- [Kernel 6.8 Changes](docs/KERNEL-6.8-CHANGES.md) -- What broke and the fix paths
- [Metrics Deep Dive](docs/METRICS-DEEP-DIVE.md) -- Kernel probe points, formulas, constants
- [Portability Roadmap](docs/PORTABILITY-ROADMAP.md) -- Cross-kernel, cross-arch analysis
- [Variant Comparison](docs/VARIANT-COMPARISON.md) -- Detailed rationale for each variant
- [Experiment Strategy](docs/EXPERIMENT-STRATEGY.md) -- Operational gotchas, run discipline, workload→metric stress map
- [Paper Cross-References](docs/PAPER-CROSS-REFERENCES.md) -- Maps each `[TODO: ...]` in the paper draft to the repo doc carrying the material
- [Bench Findings Index](bench/findings/README.md) -- Centralized empirical findings (stap-2022 baseline diagnosis, stap-nohelper reliability notes)

## References

- **Original IntP source repository:** [projectintp/intp](https://github.com/projectintp/intp).
- **Original IntP paper:** Xavier, M. G., Cano, C. H. C., Meyer, V., and De Rose, C. A. F. (2022). *IntP: Quantifying Cross-Application Interference via System-Level Instrumentation*. SBAC-PAD 2022, Bordeaux, France, pp. 231-240. IEEE. PUCRS. PDF: <https://repositorio.pucrs.br/dspace/bitstream/10923/24018/2/IntP_Quantifying_crossapplication_interference_via_systemlevel_instrumentation.pdf>. IEEE: <https://ieeexplore.ieee.org/document/9980934/>.
- **IADA (interference-aware scheduler that consumes IntP):** Meyer, V., da Silva, M. L., Kirchoff, D. F., De Rose, C. A. F. (2022). *IADA: A dynamic interference-aware cloud scheduling architecture for latency-sensitive workloads*. Journal of Systems and Software, vol. 194, pp. 111491. PUCRS.
- **iprof -- eBPF interference profiler (related work, TU Berlin):**
  - Gögge, R. (2023). *Finding noisy neighbours: Measuring application interference with system-level instrumentation using eBPF*. Master's thesis, Technical University of Berlin. Supervised by Sören Becker and Prof. Dr. Odej Kao.
  - Becker, S., Goegge, R., Kao, O. (2024). *Measuring application interference with system-level instrumentation*. IEEE/ACM International Conference on Utility and Cloud Computing Companion (UCC Companion). Technical University of Berlin.
- **PRISM (related work, Utrecht):** Landau, D., Barbosa, J., Saurabh, N. (2025). *eBPF-based instrumentation for generalisable diagnosis of performance degradation*. arXiv:2505.13160. <https://arxiv.org/abs/2505.13160>. Code: <https://github.com/EC-labs/prism>.
- **eBPF vs SystemTap overhead methodology:** Volpert, S., Eichhammer, P., Held, F., Huffert, T., Wesner, H. P., Domaschka, S. (2025). *Towards eBPF overhead quantification: An exemplary comparison of eBPF and SystemTap*. ICPE '25 Companion. ACM.
- **CO-RE portability study:** Zhong, S., Liu, J., Arpaci-Dusseau, A. C., Arpaci-Dusseau, R. H. (2025). *Revealing the unstable foundations of eBPF-based kernel extensions*. EuroSys '25. ACM. (University of Wisconsin-Madison.)
- **Intel RDT measurement caveats:** Sohal, P., Tabish, R., Drepper, U., Mancuso, R. (2022). *A closer look at Intel resource director technology (RDT)*. RTNS '22. ACM.
- **CO-RE reference guide:** Nakryiko, A. *BPF CO-RE reference guide*. <https://nakryiko.com/posts/bpf-core-reference-guide/>.

## License

MIT -- see [LICENSE](LICENSE).

# bench/ -- IntP comprehensive evaluation suite

Runs the primary IntP benchmark methodology
across all seven IntP variants in this repository, and extends it with the
cross-environment dimensions (bare-metal / container / VM) called for by
the dissertation Phase-3 plan. Captures additional ground-truth signals
(perf, resctrl, /proc/diskstats, /proc/net/dev) so we can score each
variant on measurement fidelity, runtime overhead, and availability of
each metric across environments.

The active profiler variants for the container and cross-deployment work
are **v2.1 (c-abi-cgroup)** (C / cgroup) and **v3.3 (ebpf-core-cgroup)** (eBPF /
CO-RE with in-kernel aggregation); the earlier v0.x..v3.2 variants remain
as comparison and structural evidence. All variants emit the same
canonical 7-metric contract (`netp nets blk mbw llcmr llcocc cpu`), which
is ABI-invariant and consumed downstream by the IADA classifier. The
cross-deployment suite runs the same application across bare ->
docker (`container`) -> podman (`container-podman`) -> incus
(`container-lxc`) -> k3s (`container-k8s`) -> `vm-guest`, computing paired
deltas vs bare with a per-run `caps_applied` parity audit (net mode and
storage backend are the treatment variables). Under KVM the RDT/PMU
metrics (`mbw`/`llcocc`/`llcmr`) are structurally gapped, so a separate,
flag-gated VM-portable benchmark (`--portable-metrics`: schedlat,
psi_mem, membw_est, psi_io, schedthr, steal) is planned as the VM path,
keeping the canonical 7 intact.

## Files

- `run-intp-bench.sh` -- single bash orchestrator. Read this first.
- `convert-profiler-to-meyer.py` -- converts `profiler.tsv` into the semicolon CSV expected by `interference-classifier` and `CloudSimInterference`.
- `generate-iada-tree.py` -- reorganizes converted CSV files into `source/<workload>/<pattern>.csv` and writes CloudSim `input.txt` files.
- `plot/plot-intp-bench.py` -- reproduces the figures.
- `analyze-faithfulness.py` -- adjudicates the canonical 7 metrics vs `groundtruth.tsv` (W4).
- `analyze-portable.py` -- adjudicates the VM-portable metrics (the `--portable-metrics` benchmark) vs ground truth.
- `hibench/README.md` -- Track B (HiBench Spark subset) for fidelity checks.
- `findings/README.md` -- canonical index of benchmark findings and diagnoses.

## Findings

All benchmark diagnoses and reliability notes are centralized in
`bench/findings/`.

- v0 (stap-2022) baseline compilation diagnosis:
    `bench/findings/v0-baseline-failure-diagnosis.md`
- v1 (stap-nohelper) modernization reliability findings:
    `bench/findings/v1-modernization-reliability-findings.md`

## Quick start

```bash
sudo apt install -y stress-ng sysstat linux-tools-$(uname -r) jq
sudo apt install -y docker.io qemu-system-x86 cloud-image-utils  # for env=container,vm
pip install --user pandas numpy matplotlib scikit-learn          # for plotter

# default: detect+build+solo+pairwise+overhead+timeseries+report on bare-metal
sudo ./run-intp-bench.sh

# focus on the modern variants only
sudo ./run-intp-bench.sh --variants v1,v2,v3.1,v3

# focus on the c-abi-cgroup container/cross-deployment variants
sudo ./run-intp-bench.sh --variants v2.1,v3.3

# enable a container env (docker / podman / lxc / k8s share the same launcher)
sudo ./run-intp-bench.sh --env bare,container

# enable VM envs (vm = host-side profiler; vm-guest = profiler inside the guest)
sudo ./run-intp-bench.sh --env bare,vm --vm-image /var/lib/libvirt/images/ubuntu-24.04.qcow2

# VM-portable metrics benchmark (SEPARATE; canonical 7 untouched). Only v2.1/v3.3
# implement --portable-metrics. Captures portable.tsv + aggregate-portable-means.tsv.
sudo ./run-intp-bench.sh --portable-metrics --variants v2.1,v3.3 \
     --env bare,container,vm-guest --stage solo,report
python3 bench/analyze-portable.py results/intp-bench-<ts> --out portable-faithfulness.md

# render every figure
python3 bench/plot/plot-intp-bench.py results/intp-bench-<ts>

# convert profiler.tsv files to Meyer/IADA CSV format
python3 bench/convert-profiler-to-meyer.py \
    results/intp-bench-<ts> \
    --stage solo \
    --manifest results/intp-bench-<ts>/meyer-convert.tsv

# build source/<workload>/<pattern>.csv and cloudsim-input.txt per env+variant
python3 bench/generate-iada-tree.py \
    --manifest results/intp-bench-<ts>/meyer-convert.tsv \
    --out-root results/intp-bench-<ts>/iada-tree \
    --variant v2 --stage solo \
    --rep-pattern-map rep1=inc,rep2=dec,rep3=osc,rep4=con

# REPS > 4 without changing IADA/Classifier/CloudSim file names:
# map extra reps to canonical patterns and merge into one inc/dec/osc/con file
python3 bench/generate-iada-tree.py \
    --manifest results/intp-bench-<ts>/meyer-convert.tsv \
    --out-root results/intp-bench-<ts>/iada-tree \
    --variant v2 --stage solo \
    --rep-pattern-map rep1=inc,rep2=dec,rep3=osc,rep4=con,rep5=inc,rep6=dec,rep7=osc \
    --pattern-merge median
```

## Stages

| Stage        | What it does                                                  | Maps to                       |
| ------------ | ------------------------------------------------------------- | ----------------------------- |
| `detect`     | Hardware/kernel snapshot, capabilities.env, variants.manifest | preflight                     |
| `build`      | `make` for C-ABI / ebpf-ring                               | preflight                     |
| `solo`       | 15 workloads x reps, one variant at a time, no co-runner      | legacy IntP-style figures (per-app + PCA) |
| `pairwise`   | victim + antagonist co-located; profiler attached to victim   | cross-interference analysis   |
| `overhead`   | reference workload with vs without each profiler              | Volpert et al. 2025           |
| `timeseries` | 5-min mixed workload trace per variant                        | long-trace stability analysis |
| `report`     | aggregate every profiler.tsv into one TSV; print summary      | --                            |

Under `--portable-metrics`, each rep captures `portable.tsv` (instead of
`profiler.tsv`) and `report` aggregates those, header-aware, into
`aggregate-portable-means.tsv` (the canonical `off=n-7` path is left untouched).

## Output layout

```
results/intp-bench-<ts>/
    metadata.txt
    capabilities.env
    variants.manifest
    index.tsv               # one row per (env,variant,stage,workload,rep)
    aggregate-means.tsv     # one row per run with per-metric mean
    bare/v2/solo/app10_search/rep1/
        profiler.tsv        # ts + 7 metrics
        groundtruth.tsv     # cpu / disk / net / resctrl + perf-stat.txt
        workload.log
        run.json
    bare/v2/pairwise/cpu_v_cache/rep1/
        antagonist.log
        ...
    overhead/bare/v2/ref_cpu/rep1/
        elapsed_s
        workload.log
    plots/                  # populated by plot-intp-bench.py
```

`index.tsv` is the single source of truth; every figure is built from it.

## Workload matrix

15 workloads aligned with the categories in the original IntP paper
(machine-learning/LLC, streaming/LLC+memory, ordering/memory,
classification/CPU+memory, search/CPU, sort/network, query/disk).
IDs are `app01_*` ... `app15_*` so they line up with the paper.

5 pairwise pairs (victim + antagonist) cover LLC, memory bandwidth, disk,
network, and a mixed pressure case.

3 overhead reference workloads (CPU compute, memory streaming, sequential
disk write).

## Hardware preflight (Hetzner SB Xeon Gold 5412U target)

The script auto-detects everything via `shared/intp-detect.sh`, but the
expected baseline on the rented box is:

- CPU: Intel Xeon Gold 5412U (Sapphire Rapids, 24C/48T) -- full RDT (CMT, MBM, CAT, MBA)
- Memory: 8 x 32 GiB DDR5-4800 ECC -> ~307 GB/s peak, all 8 channels
- Storage: 2 x 1.92 TB NVMe (datacenter), ext4 striped or single-disk
- Network: 1 GbE (Intel X550-AT2)

If `intp-detect.sh` reports a memory bandwidth figure significantly lower
than ~300 GB/s, half the channels are likely unpopulated -- DDR5
single-channel can artificially inflate `mbw`.

v0 (stap-2022) requires kernel <= 6.7. The script refuses to run stap-2022 on newer kernels
unless `--allow-v0` is passed; the recommended flow is to dual-boot
Ubuntu 22.04 for the stap-2022 baseline and Ubuntu 24.04 for stap-nollc..ebpf-ring, then run
the script under each boot and keep the two output directories side by
side -- the plotter will merge them if you point it at a parent dir.

## Figures produced

Listed by their internal stem. On disk each one is named
`<figure-id>-<what-it-shows>--<which-campaign>` — see
[plot/fig_names.py](plot/fig_names.py) and the "How the figures are named"
section of [plot/README.md](plot/README.md).

| Figure                            | Source stage   | Maps to                                                          |
| --------------------------------- | -------------- | ---------------------------------------------------------------- |
| `fig00_canonical_intp_fig4`       | solo           | IntP Fig. 4 canonical reproduction (single panel per variant)    |
| `fig01_per_workload_bars`         | solo           | per-workload bars, variants compared                             |
| `fig01b_per_variant_bars`         | solo           | dual view — per-(env, variant) workload x metric heatmap         |
| `fig02_pca_kmeans`                | solo           | PCA + k-means clustering (joint fit, variants overlaid)          |
| `fig03_timeseries`                | timeseries     | long-trace metric profile (IntP Fig. 3)                          |
| `fig04_overhead_throughput`       | overhead       | Volpert et al. 2025 — stress-ng bogo-ops/s slowdown              |
| `fig04b_overhead_cpu_jiffies`     | overhead       | Volpert et al. 2025 — extra system-wide CPU jiffies              |
| `fig04c_overhead_sched_switch`    | overhead       | Volpert et al. 2025 — sched:sched_switch perturbation            |
| `fig05_fidelity_matrix`           | solo + GT      | Pearson r vs ground truth                                        |
| `fig06_env_heatmap`               | solo (envs)    | dissertation Phase 3 (cross-env ratios; >=2 envs required)       |
| `fig07_pairwise_heatmap_<env>`    | pairwise       | cross-variant interference map per env                           |
| `fig08_metric_availability`       | any            | which (variant, metric) pairs reported non-zero signal           |
| `fig09_radar_fingerprint`         | solo           | per-workload polar fingerprint, variants overlaid                |
| `fig10_workload_clustermap`       | solo           | hierarchical (Ward) workload clustermap per variant              |
| `fig11_idi_bars`                  | pairwise       | IADA Fig. 6 — interference degradation by resource family        |
| `fig12_pairwise_timeseries`       | timeseries     | IntP Fig. 8 — mixed-load resource-family trace                   |
| `fig13_iada_segmented`            | timeseries     | IADA Fig. 5 — segmented Loess-smoothed interference trace        |
| `fig14_variant_resource_heatmap`  | solo+pairwise  | variant x resource summary heatmap                               |

Companion CSVs (`overhead_summary.csv`, `fidelity_matrix.csv`,
`env_ratio.csv`, `pairwise_means.csv`, `metric_availability.csv`,
`aggregate-means.csv`, `idi_resource.csv`, `variant_resource_summary.csv`)
make every figure reproducible / regenerable without re-running the
experiment. Each figure is also emitted as a vector PDF under
`plots/pdf/`.

## Repetitions and confidence intervals

`--reps N` controls repetitions per (env, variant, workload). Default 3
balances runtime against variance; bump to 5 for the final run reported
in the dissertation. Standard deviation across reps is included as error
bars in the `fig04` overhead panels; the other figures plot the mean.

## Estimated runtime

With defaults (3 reps, 60 s solo, 60 s overhead, 300 s timeseries,
7 variants, 1 env, 15 solo + 5 pair + 3 overhead workloads):

- solo: 7 * 15 * 3 * (10 + 60 + 5) ~ 3.9 h
- pairwise: 7 * 5 * 3 * 75 ~ 1.3 h
- overhead: 1 * 3 * 3 * 60 (baseline) + 7 * 3 * 3 * 60 (with) ~ 1.6 h
- timeseries: 7 * 1 * 300 ~ 0.6 h
- Total bare-metal: ~7.5 h
- + container env: roughly +6.5 h
- + VM env: roughly +7 h (boot overhead)

Use `--workloads` to subset for iteration.

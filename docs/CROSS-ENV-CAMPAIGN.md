# Cross-environment campaign (bare / container / vm)

This document is the operational guide for comparing IntP variants under
the *same* workload across execution regimes — bare metal, the container
family (docker / podman / incus / k3s), and VM — and quantifying the
overhead each regime imposes on every metric the profiler reports. It
complements [EXPERIMENT-STRATEGY.md](EXPERIMENT-STRATEGY.md) (per-variant
operational rules) by adding the cross-env analysis layer. The
cross-deployment Paper 2 suite (its normative axis, variant set, and claim
classes) is defined in EXPERIMENT-STRATEGY.md § "Paper 2 — cross-deployment
benchmark suite"; this guide is the pipeline that runs it. The active
profiler variants for the container + cross-deployment work are
`v2.1-c-abi-cgroup` and `v3.3-ebpf-core-cgroup`; the older v0.x–v3.2 variants
remain as comparison/structural evidence.

## Goal

For every `(variant, workload, metric)` triple, answer:

1. Does the choice of execution regime change the measurement at a level
   that exceeds run-to-run noise?
2. If yes, which pair of regimes accounts for the difference, and how
   large is the effect?

The pipeline produces a `summary.tsv` of descriptive statistics, a
`stats.tsv` of significance + effect-size tests, an `availability.tsv`
that lists which `(env, variant, workload, metric)` cells the profiler
actually captured, and one PNG per `(variant, workload)`. All artefacts
land under `<campaign>/bench-full/cross-env/`.

## Why `vm-guest` is the default for VM rows

The bench script offers two VM modes:

- `vm` — host-observer: qemu boots a guest, but the profiler attaches to
  the *qemu host process*. Metrics like `cpu` and `mbw` reflect the
  host-side cost of running the guest (qemu's user/kernel CPU, host
  memory bandwidth on the qcow2 backing) and *not* the workload running
  inside the guest. `netp`/`nets` reflect SLIRP/TAP forwarding on the
  host NIC, `blk` reflects the qcow2 backing file I/O. Per-process
  metrics for the in-guest workload are unavailable.
- `vm-guest` — in-guest profiler: qemu boots a guest, cloud-init drops
  an ephemeral SSH key, the host launches the profiler binary *inside*
  the guest, and `profiler.tsv` is scp'd back to the campaign tree.
  Per-process attribution matches what bare metal and container would
  see, and the guest boots with PMU pass-through (`-cpu host,pmu=on`) so
  `llcmr` and `cpu` are measurable. The two RDT metrics (`mbw`,
  `llcocc`) are structurally unavailable in a stock KVM guest (resctrl is
  host-only; no vRDT pass-through) and are recorded `unsupported`, never
  0. Per rep there is also some VM boot latency.

The cross-env analysis treats each env's data as independent samples,
so missing columns in the `vm` mode would bias the KW omnibus away from
detecting real overhead. **Use `vm-guest` unless you have a specific
reason to study qemu-host-process overhead in isolation.** If you need
to distinguish host-observer from in-guest overhead, run both and
include `vm` and `vm-guest` as separate envs — the analysis treats them
as independent rows.

## Resource parity

`bench/run-intp-bench.sh` exposes two cross-env parity knobs:

| Flag | Env var | Default |
|---|---|---|
| `--bench-cpus N` | `INTP_BENCH_CPUS` | `floor(nproc * 2/3)` |
| `--bench-mem SIZE` | `INTP_BENCH_MEM` | `floor(MemTotal_GB * 2/3)G` |

The same values flow into all three envs:

| Env | Enforcement |
|---|---|
| `bare` | cgroup v2 `cpu.max` (`N * 100000 100000`) and `memory.max` written to the per-workload `intp-bench-<wlname>` cgroup. Best-effort: if the controllers are not delegated, a warning is logged and the rep proceeds without parity. |
| `container`, `container-guest`, `container-full` | `docker run --cpus=N --memory=SIZE`. If docker rejects the caps (legacy cgroup driver) the launcher warns and retries without the caps. |
| `vm`, `vm-guest`, `vm-full` | qemu `-smp N -m SIZE`. `VM_CPUS` / `VM_MEM` inherit `BENCH_CPUS` / `BENCH_MEM` unless explicitly overridden via `--vm-cpus` / `--vm-mem` or `INTP_BENCH_VM_*`. |

The default of 2/3 leaves headroom for the profiler, the kernel, the
qemu/docker daemons, and IO buffers. On a 96-thread Sapphire Rapids
host with 192 GB RAM, the default lands at 64 vCPUs and 128 GB —
representative of a workload that doesn't try to monopolize the host.

Override at campaign granularity:

```bash
sudo INTP_BENCH_CPUS=64 INTP_BENCH_MEM=192G \
     bash bench/run-intp-bench.sh ...
```

## Statistical method

For each `(variant, workload, metric)` the cross-env script gathers one
sample per (env, rep) — the per-rep mean from `aggregate-means.tsv` —
and applies:

1. **Kruskal-Wallis omnibus** across envs (n ≥ 2 per env). Non-parametric
   one-way analysis; no normality assumption.
2. **Pairwise Mann-Whitney U** (two-sided) for every env pair, *only* if
   the KW p-value is below `--alpha` (default 0.05).
3. **Bonferroni correction** on the pairwise tests: `alpha_pair = alpha
   / num_pairs`.
4. **Cliff's delta** for every env pair as a distribution-free effect
   size, classified by Vargha-Delaney magnitude (negligible < 0.147,
   small < 0.33, medium < 0.474, large ≥ 0.474).

Why non-parametric: the profiler reports skewed, saturable quantities
(LLC occupancy capped by the cache, memory bandwidth capped by channel
count, event counts bounded below at zero) and the per-rep sample size
is small. Normality is not defensible; ANOVA-derived p-values would be
optimistic. KW + MW preserves interpretability under those conditions.

Bonferroni is the conservative choice and matches the small env-set of a
classic bare/container/vm comparison (typically 3). The cross-deployment
Paper 2 suite spans 6 envs (15 pairs), where Bonferroni is overly
conservative; that suite corrects with BH-FDR over the 15-pair table
instead, and stamps the per-metric `claim_class` into `stats.tsv` (see
EXPERIMENT-STRATEGY.md § "Comparison statistic + claim classes").

## Running

Full campaign on the Hetzner Sapphire Rapids host:

```bash
sudo BENCH_ENVS=bare,container,vm-guest \
     BENCH_VARIANTS=v1.1,v2,v3,v3.1 \
     VM_IMAGE=/var/lib/intp/ubuntu24.qcow2 \
     INTP_BENCH_CPUS=64 INTP_BENCH_MEM=192G \
     REPS=10 DURATION=120 \
     bash run-big-batch.sh
```

Full cross-deployment campaign (Paper 2 axis) on the Sapphire Rapids host:

```bash
sudo BENCH_ENVS=bare,container,container-podman,container-lxc,container-k8s,vm-guest \
     BENCH_VARIANTS=v2.1,v3.3 \
     VM_IMAGE=/var/lib/intp/ubuntu24.qcow2 \
     INTP_BENCH_CPUS=64 INTP_BENCH_MEM=192G \
     REPS=12 DURATION=120 \
     bash run-big-batch.sh
```

After the run the cross-env analysis is chained automatically from
`plot-intp-bench.py`. To re-run only the analysis (no figures
regenerated):

```bash
python3 bench/plot/plot-cross-environment.py \
    results/<campaign>/bench-full
```

Standalone smoke (no full campaign needed):

```bash
SMOKE_CROSS_ENV=1 VM_IMAGE=/var/lib/intp/ubuntu24.qcow2 \
    bash run-smoke-all.sh
```

This runs `v2,v3.1 × bare,container,vm-guest × app01_ml_llc × reps=2 ×
duration=20s` and drives the cross-env consumer in one shot — useful
for catching regressions in the pipeline without a 6-hour bench-full.

## Known limitations

- **RDT metrics in guest are structurally gapped, not missing.** `mbw`
  and `llcocc` rely on Intel RDT counters via `/sys/fs/resctrl`, which is
  host-only under KVM (no vRDT pass-through), so they are structurally
  unavailable inside the guest. The Paper 2 suite records those cells
  with an `unsupported` availability status (distinct from `missing`) and
  never emits them as 0. For VM rows that need bandwidth/memory pressure
  signal, the flag-gated `--portable-metrics` VM benchmark (schedlat,
  psi_mem, membw_est, psi_io, schedthr, steal) is the VM path, keeping
  the canonical 7-metric contract intact. Plain `vm` (host-observer)
  still captures host-side RDT but attributed to qemu, not the workload.
- **Network forwarding model.** The canonical `vm-guest` row boots with a
  TAP NIC bridged to the host so `netp`/`nets` see a real device. The
  legacy qemu user-mode SLIRP path (port forwarding for SSH) throttles
  `netp`/`nets` and is unsuitable for representative network numbers;
  TAP requires `CAP_NET_ADMIN` and changes the guest IP plan.
- **VM boot latency.** Each rep pays ~30–60 s of cloud-init time. At
  `--reps 10 --duration 120` the VM boot tax is ~10% of the campaign
  budget for VM rows. Pre-baking IntP build deps into the qcow2 (so
  cloud-init skips `apt-get install`) brings this down to ~15 s.
- **scp round-trip.** `profiler.tsv` is fetched from the guest after
  the rep; on a 120-s rep this is negligible (~1 s), but for short
  smokes it can be a measurable fraction of duration. The cross-env
  smoke uses `--duration 20`, which means the scp tail is ~5% — fine
  for regression detection, not for absolute overhead claims.

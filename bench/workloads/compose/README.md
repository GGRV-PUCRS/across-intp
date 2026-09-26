# Compose suite drivers (Tier-B CloudSuite / Tier-C DeathStarBench)

Each directory here drives one multi-container real-world workload for the
benchmark harness (spec `COMPOSE:<suite-dir>:<load-profile>:<extra load args>`
in `bench/run-intp-bench.sh`, decision C33). The harness — not the driver —
owns project naming, cgroup scoping, resource caps, readiness gating, load
lifetime, and teardown; a driver only declares *what* to run.

## Contract

A driver directory contains:

| File | Required | Role |
|---|---|---|
| `meta.env` | yes | Sourced by the launcher. Must set `COMPOSE_FILES` (space-separated; relative paths resolve against the driver dir, absolute paths may point into an installer-provisioned clone such as `/opt/DeathStarBench`) and `ANCHOR_SERVICE` (the service whose host PID is the liveness signal / `--pids` fallback). Optional: `READY_TIMEOUT` (s, default 180), `SETUP_HINT` (installer to name in error messages). |
| `compose.yml` | usually | The suite's services with **pinned image tags**. Omitted only when `COMPOSE_FILES` points entirely at an external clone. |
| `ready.sh` | no | Host-side readiness probe, polled after `up` until `READY_TIMEOUT`. Gets `PROJECT` and `SUITE_DIR` in the environment; exit 0 = ready. |
| `load.sh` | no | Host-side load generator, started after readiness and killed with the run window. Gets `PROJECT`, `SUITE_DIR`, `DURATION`, `CPUSET_LOAD`, `LOAD_PROFILE`, `LOAD_EXTRA`, `NETWORK`. Must pin itself to `CPUSET_LOAD` (`taskset` / `--cpuset-cpus`) and clean up its children on TERM. |

## Scoping & caps (done by the harness)

- A generated override file parents **every service** under one cgroup (a
  systemd slice on the default Ubuntu 24.04 docker setup), so the cgroup-scoped
  profilers (v2.1 recursive `cgroup.procs`, v3.3 ancestor cgroup-id gate) see
  the whole app as **one workload**, across service restarts.
- Services named **`load*`** are the exception: in-project load generators
  (e.g. the CloudSuite client images) stay outside the profiled parent and are
  pinned to the host third (`CPUSET_C`) instead.
- The instance third (`BENCH_CPUS`/`BENCH_MEM`/cpuset A or B) is applied to the
  **parent** cgroup — the whole app shares one footprint, matching the
  stress-ng resource model.
- Dataset volumes that must survive `down -v` (rep-to-rep) are declared
  `external: true` and provisioned by the suite installer in `bench/setup/`.

## Deployment classes

Compose suites run on the 3 deployment classes only (C32): `bare`
(= compose-on-host, stamped `notes=compose_on_host`), `container`, and
`vm-guest` (in-guest docker, suites baked into the bench VM image by
`build-bench-vm.sh WITH_SUITES=1`). podman/lxc/k8s refuse the spec.

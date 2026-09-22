# Profiler overhead vs sampling cadence (F9) — results/p2-cadence-overhead

Overhead = throughput displacement of the reference workload under a profiler arm vs the _baseline arm (Volpert D), within each cadence. Reference = stress-ng bogo-ops/s. Positive % = the profiler slowed the workload. Env(s): bare; variants: v2.1, v3.3.

## bare — overhead % by sampling interval

| variant · ref | 0.1s | 0.25s | 0.5s | 1s | 2s | 5s | max |
|---|---|---|---|---|---|---|---|
| v2.1 · cpu | +1.82 | +0.57 | +0.07 | +0.43 | -0.03 | -0.25 | 1.82 |
| v2.1 · stream | +0.02 | -1.40 | +0.02 | -0.24 | +0.26 | +0.32 | 1.40 |
| v2.1 · disk | +0.44 | -1.18 | +0.22 | -9.42 | +2.47 | +0.61 | 9.42 |
| v3.3 · cpu | +1.68 | +0.62 | +0.30 | +0.30 | +0.05 | +0.01 | 1.68 |
| v3.3 · stream | +2.07 | +1.88 | +2.33 | +2.04 | +2.09 | +2.50 | 2.50 |
| v3.3 · disk | -0.09 | +6.14 | +5.57 | -7.54 | +7.69 | -0.07 | 7.69 |

## Headline

_Headline uses the throughput-stable cpu/stream refs; ref_disk is I/O-variance-dominated (±7-9% run-to-run) and is shown in the table but excluded from the F9 curve + this summary._

- **v2.1** (bare): mean overhead +0.92% at 0.1s (finest) → +0.04% at 5s (coarsest).
- **v3.3** (bare): mean overhead +1.88% at 0.1s (finest) → +1.25% at 5s (coarsest).

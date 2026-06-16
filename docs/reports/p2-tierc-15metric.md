# Real-application 15-metric fingerprints (F12) — results/p2-tierc

Envs: bare, container, vm-guest. Variants: v2.1, v3.3. Apps: app22_dsb_socialnet.

**Claim (F12):** real applications are *mixed* across the IADA resource classes (cpu / mem / cache / disk / net) — a single-class label, the assumption the IADA classifier is built on, does not describe them. Activation rule: a class is active in an app when ≥1 of its *consumption* metrics clears an absolute noise floor (`netp/nets`≥10, `cpu/schedlat`≥5, `membw_est`≥50, `mbw/llcmr/llcocc`≥5/1, `blk/psi_*`≥1; native units). Floors are per-app and absolute, so a mid-level user is not masked by a heavier app on the same axis (the §2 raw fingerprint lets a reader re-adjudicate). The scheduling-regime metrics (psp, idle_preempt) and guards (schedthr, steal) are cross-cutting contention indicators, reported separately — they do not define a class. 1/3 footprint + hard CPU pinning; solo stage.

## §0 Coverage & scope caveats

| env — variant | app22 dsb socialnet |
|---|---|
| bare — v2.1 | 12 |
| bare — v3.3 | 12 |
| container — v2.1 | 12 |
| container — v3.3 | 12 |
| vm-guest — v2.1 | 12 |
| vm-guest — v3.3 | 12 |

- **RDT metrics (mbw/llcocc/llcmr) → `--`** (no samples) in: vm-guest·v2.1, vm-guest·v3.3 — expected where resctrl is unavailable (KVM guest). The portable mem/cache proxies (membw_est, psi_mem) carry the dimension there; see §3.

## §1 Resource-class activation — the F12 punchline

Number of IADA classes each real app activates (✓ = active). >1 ⇒ the single-class label fails. Computed on each host env where all metrics are available; vm-guest omitted from the count (RDT blind).

**bare — v2.1**

| app | cpu | mem | cache | disk | net | # classes | regime |
|---|---|---|---|---|---|---|---|
| app22 dsb socialnet | ✓ | ✓ | ✓ | · | ✓ | **4** | psp |

**container — v2.1**

| app | cpu | mem | cache | disk | net | # classes | regime |
|---|---|---|---|---|---|---|---|
| app22 dsb socialnet | ✓ | ✓ | ✓ | · | ✓ | **4** | psp |

**bare — v3.3**

| app | cpu | mem | cache | disk | net | # classes | regime |
|---|---|---|---|---|---|---|---|
| app22 dsb socialnet | ✓ | ✓ | ✓ | · | ✓ | **4** | psp, idle_preempt |

**container — v3.3**

| app | cpu | mem | cache | disk | net | # classes | regime |
|---|---|---|---|---|---|---|---|
| app22 dsb socialnet | ✓ | ✓ | ✓ | · | ✓ | **4** | psp, idle_preempt |

> **Verdict (F12):** every adequately-driven app on container spans ≥2 IADA resource classes (app22 dsb socialnet) — the single-class label fails for real apps.

- **container·v2.1:** 1/1 apps activate ≥2 classes (app22 dsb socialnet=4).
- **container·v3.3:** 1/1 apps activate ≥2 classes (app22 dsb socialnet=4).

## §2 Full 15-metric fingerprint (median across reps)

### app22 dsb socialnet

| metric (class) | bare·v2.1 | bare·v3.3 | container·v2.1 | container·v3.3 | vm-guest·v2.1 | vm-guest·v3.3 |
|---|---|---|---|---|---|---|
| netp (net) | 8.5 | 24.0 | 6.0 | 5.0 | 5.0 | 4.0 |
| nets (net) | 52.0 | 46.0 | 45.0 | 29.0 | 31.5 | 18.0 |
| blk (disk) | 0.000 | 0.000 | 0.000 | 0.000 | 1.0 | 0.000 |
| mbw (mem) | 0.000 | 7.0 | 0.000 | 1.0 | — | — |
| llcmr (cache) | 21.0 | 27.0 | 18.0 | 18.0 | 9.0 | 9.0 |
| llcocc (cache) | 0.000 | 74.0 | 0.000 | 69.0 | 6.0 | — |
| cpu (cpu) | 12.0 | 27.0 | 9.0 | 10.0 | 34.0 | 32.0 |
| schedlat (cpu) | 0.000 | 6.0 | 0.000 | 0.000 | 1.0 | 3.0 |
| psi_mem (mem) | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| membw_est (mem) | 668 | 1551 | 478 | 478 | 1464 | 1491 |
| psi_io (disk) | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| schedthr (regime) | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| steal (regime) | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| psp (regime) | 166 | 9901 | 87.0 | 256 | 1063 | 3223 |
| idle_preempt (regime) | — | 48960 | — | 63628 | — | 54048 |

## §3 vm-guest portability: portable proxies where RDT is `--`

Where mbw/llcocc/llcmr are unavailable in the guest, do the portable mem/cache/sched proxies still carry signal? (median, vm-guest)

**vm-guest — v2.1**

| metric | app22 dsb socialnet |
|---|---|
| mbw (RDT) | — |
| llcocc (RDT) | 6.0 |
| llcmr (RDT) | 9.0 |
| membw_est (proxy) | 1464 |
| psi_mem (proxy) | 0.000 |
| schedlat (proxy) | 1.0 |
| psi_io (proxy) | 0.000 |
| steal (proxy) | 0.000 |

**vm-guest — v3.3**

| metric | app22 dsb socialnet |
|---|---|
| mbw (RDT) | — |
| llcocc (RDT) | — |
| llcmr (RDT) | 9.0 |
| membw_est (proxy) | 1491 |
| psi_mem (proxy) | 0.000 |
| schedlat (proxy) | 3.0 |
| psi_io (proxy) | 0.000 |
| steal (proxy) | 0.000 |


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
| app22 dsb socialnet ⚠ | · | · | ✓ | · | · | **1** | — |

**container — v2.1**

| app | cpu | mem | cache | disk | net | # classes | regime |
|---|---|---|---|---|---|---|---|
| app22 dsb socialnet ⚠ | · | · | ✓ | · | · | **1** | — |

**bare — v3.3**

| app | cpu | mem | cache | disk | net | # classes | regime |
|---|---|---|---|---|---|---|---|
| app22 dsb socialnet ⚠ | · | · | ✓ | · | · | **1** | psp, idle_preempt |

**container — v3.3**

| app | cpu | mem | cache | disk | net | # classes | regime |
|---|---|---|---|---|---|---|---|
| app22 dsb socialnet ⚠ | · | · | ✓ | · | · | **1** | psp, idle_preempt |

> **Verdict (F12):** every app in this campaign was under-driven at the default load on the 1/3 footprint — no multi-resource conclusion from this campaign alone; see the per-app fingerprint and the scheduling-regime signal in §2.

- **container·v2.1:** 0/1 apps activate ≥2 classes (app22 dsb socialnet=1).
- **container·v3.3:** 0/1 apps activate ≥2 classes (app22 dsb socialnet=1).

⚠ **Low-drive cells:** app22 dsb socialnet barely registered (cpu<5%, no net, membw_est<50) — at the 1/3 footprint the default load generator under-drove the service, so its low class-count is a load-gen artifact, not a single-resource signature. The scheduling-regime signal (idle_preempt/psp) and cache activity in §2 still show the app is live; an adequately-driven re-run is needed to read its full resource mix.

## §2 Full 15-metric fingerprint (median across reps)

### app22 dsb socialnet

| metric (class) | bare·v2.1 | bare·v3.3 | container·v2.1 | container·v3.3 | vm-guest·v2.1 | vm-guest·v3.3 |
|---|---|---|---|---|---|---|
| netp (net) | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| nets (net) | 3.0 | 3.0 | 3.0 | 3.0 | 7.0 | 2.0 |
| blk (disk) | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| mbw (mem) | 0.000 | 0.000 | 0.000 | 0.000 | — | — |
| llcmr (cache) | 16.0 | 15.0 | 16.0 | 16.0 | 7.0 | 7.0 |
| llcocc (cache) | 0.000 | 40.0 | 0.000 | 34.0 | 0.000 | — |
| cpu (cpu) | 1.0 | 1.0 | 1.0 | 1.0 | 4.0 | 4.0 |
| schedlat (cpu) | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| psi_mem (mem) | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| membw_est (mem) | 42.0 | 42.0 | 43.0 | 42.5 | 120 | 122 |
| psi_io (disk) | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| schedthr (regime) | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| steal (regime) | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| psp (regime) | 1.0 | 6.0 | 1.0 | 6.0 | 1.0 | 15.0 |
| idle_preempt (regime) | — | 8542 | — | 8554 | — | 8238 |

## §3 vm-guest portability: portable proxies where RDT is `--`

Where mbw/llcocc/llcmr are unavailable in the guest, do the portable mem/cache/sched proxies still carry signal? (median, vm-guest)

**vm-guest — v2.1**

| metric | app22 dsb socialnet |
|---|---|
| mbw (RDT) | — |
| llcocc (RDT) | 0.000 |
| llcmr (RDT) | 7.0 |
| membw_est (proxy) | 120 |
| psi_mem (proxy) | 0.000 |
| schedlat (proxy) | 0.000 |
| psi_io (proxy) | 0.000 |
| steal (proxy) | 0.000 |

**vm-guest — v3.3**

| metric | app22 dsb socialnet |
|---|---|
| mbw (RDT) | — |
| llcocc (RDT) | — |
| llcmr (RDT) | 7.0 |
| membw_est (proxy) | 122 |
| psi_mem (proxy) | 0.000 |
| schedlat (proxy) | 0.000 |
| psi_io (proxy) | 0.000 |
| steal (proxy) | 0.000 |


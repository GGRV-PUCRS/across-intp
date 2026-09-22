# Real-application 15-metric fingerprints (F12) — results/p2-tierb

Envs: bare, container, vm-guest. Variants: v2.1, v3.3. Apps: app18_redis_kv, app19_cs_datacaching, app20_cs_websearch, app21_cs_imanalytics.

**Claim (F12):** real applications are *mixed* across the IADA resource classes (cpu / mem / cache / disk / net) — a single-class label, the assumption the IADA classifier is built on, does not describe them. Activation rule: a class is active in an app when ≥1 of its *consumption* metrics clears an absolute noise floor (`netp/nets`≥10, `cpu/schedlat`≥5, `membw_est`≥50, `mbw/llcmr/llcocc`≥5/1, `blk/psi_*`≥1; native units). Floors are per-app and absolute, so a mid-level user is not masked by a heavier app on the same axis (the §2 raw fingerprint lets a reader re-adjudicate). The scheduling-regime metrics (psp, idle_preempt) and guards (schedthr, steal) are cross-cutting contention indicators, reported separately — they do not define a class. 1/3 footprint + hard CPU pinning; solo stage.

## §0 Coverage & scope caveats

| env — variant | app18 redis kv | app19 cs datacaching | app20 cs websearch | app21 cs imanalytics |
|---|---|---|---|---|
| bare — v2.1 | 12 | 12 | 12 | 12 |
| bare — v3.3 | 12 | 12 | 12 | 12 |
| container — v2.1 | 12 | 12 | 12 | 12 |
| container — v3.3 | 12 | 12 | 12 | 12 |
| vm-guest — v2.1 | 12 | 12 | 12 | 12 |
| vm-guest — v3.3 | 12 | 12 | 12 | 12 |

- **RDT metrics (mbw/llcocc/llcmr) → `--`** (no samples) in: vm-guest·v2.1, vm-guest·v3.3 — expected where resctrl is unavailable (KVM guest). The portable mem/cache proxies (membw_est, psi_mem) carry the dimension there; see §3.

## §1 Resource-class activation — the F12 punchline

Number of IADA classes each real app activates (✓ = active). >1 ⇒ the single-class label fails. Computed on each host env where all metrics are available; vm-guest omitted from the count (RDT blind).

**bare — v2.1**

| app | cpu | mem | cache | disk | net | # classes | regime |
|---|---|---|---|---|---|---|---|
| app18 redis kv | · | · | ✓ | · | ✓ | **2** | psp |
| app19 cs datacaching | ✓ | ✓ | ✓ | · | ✓ | **4** | — |
| app20 cs websearch | ✓ | ✓ | ✓ | · | · | **3** | — |
| app21 cs imanalytics | ✓ | ✓ | ✓ | · | · | **3** | — |

**container — v2.1**

| app | cpu | mem | cache | disk | net | # classes | regime |
|---|---|---|---|---|---|---|---|
| app18 redis kv | · | · | ✓ | · | ✓ | **2** | psp |
| app19 cs datacaching | ✓ | ✓ | ✓ | · | ✓ | **4** | — |
| app20 cs websearch | ✓ | ✓ | ✓ | · | · | **3** | — |
| app21 cs imanalytics | ✓ | ✓ | ✓ | · | · | **3** | — |

**bare — v3.3**

| app | cpu | mem | cache | disk | net | # classes | regime |
|---|---|---|---|---|---|---|---|
| app18 redis kv | · | · | ✓ | · | ✓ | **2** | psp, idle_preempt |
| app19 cs datacaching | ✓ | ✓ | ✓ | · | ✓ | **4** | psp, idle_preempt |
| app20 cs websearch | ✓ | ✓ | ✓ | · | · | **3** | psp, idle_preempt |
| app21 cs imanalytics | ✓ | ✓ | ✓ | · | · | **3** | psp, idle_preempt |

**container — v3.3**

| app | cpu | mem | cache | disk | net | # classes | regime |
|---|---|---|---|---|---|---|---|
| app18 redis kv | · | · | ✓ | · | ✓ | **2** | psp |
| app19 cs datacaching | ✓ | ✓ | ✓ | · | ✓ | **4** | psp, idle_preempt |
| app20 cs websearch | ✓ | ✓ | ✓ | · | · | **3** | psp, idle_preempt |
| app21 cs imanalytics | ✓ | ✓ | ✓ | · | · | **3** | psp, idle_preempt |

> **Verdict (F12):** every adequately-driven app on container spans ≥2 IADA resource classes (app18 redis kv, app19 cs datacaching, app20 cs websearch, app21 cs imanalytics) — the single-class label fails for real apps.

- **container·v2.1:** 4/4 apps activate ≥2 classes (app18 redis kv=2; app19 cs datacaching=4; app20 cs websearch=3; app21 cs imanalytics=3).
- **container·v3.3:** 4/4 apps activate ≥2 classes (app18 redis kv=2; app19 cs datacaching=4; app20 cs websearch=3; app21 cs imanalytics=3).

## §2 Full 15-metric fingerprint (median across reps)

### app18 redis kv

| metric (class) | bare·v2.1 | bare·v3.3 | container·v2.1 | container·v3.3 | vm-guest·v2.1 | vm-guest·v3.3 |
|---|---|---|---|---|---|---|
| netp (net) | 0.000 | 8.0 | 0.000 | 8.0 | 0.000 | 89.5 |
| nets (net) | 65.0 | 60.0 | 61.0 | 59.0 | 40.0 | 0.000 |
| blk (disk) | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| mbw (mem) | 0.000 | 0.000 | 0.000 | 0.000 | — | — |
| llcmr (cache) | 0.000 | 0.000 | 0.000 | 0.000 | 1.0 | 1.0 |
| llcocc (cache) | 6.0 | 6.0 | 7.5 | 8.0 | 3.0 | — |
| cpu (cpu) | 2.0 | 2.0 | 2.0 | 2.0 | 6.0 | 6.0 |
| schedlat (cpu) | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| psi_mem (mem) | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| membw_est (mem) | 0.000 | 0.000 | 0.000 | 0.000 | 12.0 | 13.0 |
| psi_io (disk) | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| schedthr (regime) | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| steal (regime) | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| psp (regime) | 7.0 | 7.0 | 8.0 | 8.0 | 5.0 | 5.0 |
| idle_preempt (regime) | — | 57.0 | — | 41.0 | — | 407 |

### app19 cs datacaching

| metric (class) | bare·v2.1 | bare·v3.3 | container·v2.1 | container·v3.3 | vm-guest·v2.1 | vm-guest·v3.3 |
|---|---|---|---|---|---|---|
| netp (net) | 94.0 | 43.0 | 94.0 | 43.0 | 99.0 | 50.5 |
| nets (net) | 99.0 | 25.0 | 99.0 | 25.0 | 99.0 | 25.0 |
| blk (disk) | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| mbw (mem) | 0.000 | 0.000 | 0.000 | 0.000 | — | — |
| llcmr (cache) | 16.0 | 16.0 | 16.0 | 16.0 | 15.5 | 14.0 |
| llcocc (cache) | 0.000 | 52.0 | 0.000 | 51.0 | 15.0 | — |
| cpu (cpu) | 7.0 | 7.0 | 7.0 | 7.0 | 22.5 | 23.0 |
| schedlat (cpu) | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| psi_mem (mem) | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| membw_est (mem) | 298 | 278 | 300 | 278 | 943 | 848 |
| psi_io (disk) | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| schedthr (regime) | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| steal (regime) | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| psp (regime) | 0.000 | 7.0 | 0.000 | 7.0 | 0.000 | 5.0 |
| idle_preempt (regime) | — | 71138 | — | 70946 | — | 30791 |

### app20 cs websearch

| metric (class) | bare·v2.1 | bare·v3.3 | container·v2.1 | container·v3.3 | vm-guest·v2.1 | vm-guest·v3.3 |
|---|---|---|---|---|---|---|
| netp (net) | 1.0 | 1.0 | 1.0 | 1.0 | 0.000 | 0.000 |
| nets (net) | 6.0 | 4.0 | 6.0 | 4.0 | 0.000 | 0.000 |
| blk (disk) | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| mbw (mem) | 0.000 | 6.0 | 0.000 | 7.0 | — | — |
| llcmr (cache) | 9.0 | 10.0 | 10.0 | 10.0 | 30.0 | 30.0 |
| llcocc (cache) | 0.000 | 69.0 | 0.000 | 70.0 | 0.000 | — |
| cpu (cpu) | 33.0 | 33.0 | 33.0 | 33.0 | 3.0 | 3.0 |
| schedlat (cpu) | 0.000 | 97.5 | 0.000 | 88.0 | 0.000 | 0.000 |
| psi_mem (mem) | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| membw_est (mem) | 193 | 204 | 196 | 200 | 374 | 378 |
| psi_io (disk) | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| schedthr (regime) | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| steal (regime) | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| psp (regime) | 0.000 | 7425 | 0.000 | 7238 | 0.000 | 4.0 |
| idle_preempt (regime) | — | 1038 | — | 1316 | — | 746 |

### app21 cs imanalytics

| metric (class) | bare·v2.1 | bare·v3.3 | container·v2.1 | container·v3.3 | vm-guest·v2.1 | vm-guest·v3.3 |
|---|---|---|---|---|---|---|
| netp (net) | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| nets (net) | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| blk (disk) | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| mbw (mem) | 0.000 | 4.0 | 0.000 | 4.0 | — | — |
| llcmr (cache) | 46.0 | 46.0 | 46.0 | 46.0 | 30.0 | 30.0 |
| llcocc (cache) | 0.000 | 92.0 | 0.000 | 92.0 | 17.0 | — |
| cpu (cpu) | 27.0 | 27.0 | 27.0 | 27.0 | 42.0 | 42.0 |
| schedlat (cpu) | 0.000 | 4.0 | 0.000 | 4.0 | 0.000 | 3.0 |
| psi_mem (mem) | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| membw_est (mem) | 1606 | 1604 | 1629 | 1602 | 5424 | 5304 |
| psi_io (disk) | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| schedthr (regime) | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| steal (regime) | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| psp (regime) | 0.000 | 849 | 0.000 | 871 | 0.000 | 948 |
| idle_preempt (regime) | — | 2696 | — | 2716 | — | 14252 |

## §3 vm-guest portability: portable proxies where RDT is `--`

Where mbw/llcocc/llcmr are unavailable in the guest, do the portable mem/cache/sched proxies still carry signal? (median, vm-guest)

**vm-guest — v2.1**

| metric | app18 redis kv | app19 cs datacaching | app20 cs websearch | app21 cs imanalytics |
|---|---|---|---|---|
| mbw (RDT) | — | — | — | — |
| llcocc (RDT) | 3.0 | 15.0 | 0.000 | 17.0 |
| llcmr (RDT) | 1.0 | 15.5 | 30.0 | 30.0 |
| membw_est (proxy) | 12.0 | 943 | 374 | 5424 |
| psi_mem (proxy) | 0.000 | 0.000 | 0.000 | 0.000 |
| schedlat (proxy) | 0.000 | 0.000 | 0.000 | 0.000 |
| psi_io (proxy) | 0.000 | 0.000 | 0.000 | 0.000 |
| steal (proxy) | 0.000 | 0.000 | 0.000 | 0.000 |

**vm-guest — v3.3**

| metric | app18 redis kv | app19 cs datacaching | app20 cs websearch | app21 cs imanalytics |
|---|---|---|---|---|
| mbw (RDT) | — | — | — | — |
| llcocc (RDT) | — | — | — | — |
| llcmr (RDT) | 1.0 | 14.0 | 30.0 | 30.0 |
| membw_est (proxy) | 13.0 | 848 | 378 | 5304 |
| psi_mem (proxy) | 0.000 | 0.000 | 0.000 | 0.000 |
| schedlat (proxy) | 0.000 | 0.000 | 0.000 | 3.0 |
| psi_io (proxy) | 0.000 | 0.000 | 0.000 | 0.000 |
| steal (proxy) | 0.000 | 0.000 | 0.000 | 0.000 |


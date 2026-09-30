# DECISIONS-container.md — v2.1 / v3.3 container-based interference

Implementation notes / deviations for the container-axis packet: finalizing
**v2.1-c-abi-cgroup** (C/cgroup) and building **v3.3-ebpf-core-cgroup** (eBPF/cgroup)
to measure per-tenant interference for container and VM targets. Scope is the
local `[FAN-OUT]` zone (codegen, build, schema, analysis) plus the gated remote
`[SINGLE-FLIGHT]` zone. Kept separate from the root
`DECISIONS.md`, which covers the unrelated HiBench sample-loss fix.

## Conventions applied

- Branch `feat/container-based-interference`; one commit per logical unit.
- Commits **omit** the `Co-Authored-By` trailer (repo convention).
- No pushing (anonymized academic artifact); no unrelated reformatting.
- Preserve the canonical seven IntP metrics: `netp nets blk mbw llcmr llcocc cpu`.

---

## Ratified decisions (2026-06-02)

### C1 — `netp` canonical scope for v3.3 = per-cgroup + `netp_dev` diagnostic

v3.3 DESIGN §8.1 left this OPEN. **Decision:** the canonical `netp` column is
**per-cgroup** (cgroup-skb egress/ingress keyed by cgroup id), and v3.3 appends a
**diagnostic trailing column `netp_dev`** carrying the device-level (host-wide)
rate for cross-check against v3.2. For VM targets, per-cgroup cgroup-skb is not
available for the guest, so `netp` is measured via **tc/XDP on the tap iface**
(host-side), per the §2 matrix. This gives per-tenant attribution (the point of
the container axis) while retaining v3.2 comparability via `netp_dev`.

### C2 — `nets` divergence = canonical per-cgroup (v3.3) + `nets_sys` diagnostic

`nets` (softirq) has no stable per-cgroup ABI, so **v2.1 keeps `nets`
system-wide** in the canonical column (matches `../METRICS-ALIGNMENT.md` at the
repo root). **v3.3**
emits a **per-cgroup estimate** (skb byte-share cost model — an explicit
approximation) in the canonical `nets` column, **plus a diagnostic trailing
column `nets_sys`** carrying the system-wide softirq value for parity with v2.1
and v3.2. Provenance is recorded so analysis never silently compares the
system-wide v2.1 `nets` against the estimated per-cgroup v3.3 `nets` as if equal:

- comment-header line: `# nets=system-wide[softirq]` (v2.1) vs
  `# nets=cost-model[skb-share]` (v3.3);
- the v3.3 cost-model `nets` carries a `PROXY`/note status marker per sample;
- a `LIMIT[v3.3]` marker is documented for the approximation.

### C3 — decisions home = this file

Container-axis decisions live in `docs/DECISIONS-container.md` (this file),
distinct from the root HiBench `DECISIONS.md`. (New file authorized by user.)

---

## Schema facts pinned by W0 preflight (verified against reference data)

### C4 — parity target is the 7-metric `profiler.tsv`, NOT `groundtruth.tsv`

The v2.1↔v3.3 column parity target is the **7 canonical metric columns**
(`netp nets blk mbw llcmr llcocc cpu`) of `profiler.tsv`. The 12-field
`groundtruth.tsv` (`ts cpu_busy_pct disk_read_mb … resctrl_llcocc_bytes`) is a
**stress-ng-only derived ground-truth artifact**, not the sampler record, and is
not a parity target.

### C5 — leading `ts` column is harness-owned (7-header / 8-data asymmetry)

Reference `profiler.tsv` has a **7-field header** but **8-field data rows**: a
leading Unix-epoch timestamp is injected by the bench harness
(`bench/run-intp-bench.sh`), not by the profiler binary (v2 `emit_tsv` writes
exactly 7 fields; v3.3 clones v3.2's emitter). Parity enforcement
(`shared/validate-cross-variant.sh`) **must tolerate the 7-vs-8 asymmetry** and
must not false-positive on it. v3.3's diagnostic trailing columns (`netp_dev`,
`nets_sys`, and v3.2's optional `mbw_raw_mbps`) are appended **after** the 7
canonical metrics and are excluded from the 7-metric parity check.

### C6 — two `run.json` schemas (per-stage), both required

- stress-ng (solo/pairwise/timeseries): 11-field schema
  `{env, variant, stage, workload, rep, start_iso, duration_target_s,
  duration_observed_s, samples, workload_pid, notes}`.
- HiBench: 6-field schema `{variant, workload, rep, elapsed_s, samples, status}`.

v2.1 and v3.3 must emit the correct schema **per stage**; parity is checked
per-stage, not as one universal schema.

---

## Defaulted (open to ratification)

### C7 — `blk` / `llcmr` unit normalization across v2.1 and v3.3

**Default:** the on-disk `blk` and `llcmr` columns carry **identical unit
definitions** across variants — `blk` = % of interval in block-I/O service time,
`llcmr` = LLC miss ratio (%). v3.3 sources a richer underlying signal (`blk` from
`bio->bi_blkg` with svctm/queue-depth; `llcmr` possibly from BPF perf-overflow vs
perf cgroup-mode fds), but normalizes to the **same on-disk unit**. The richer
signal, if surfaced, goes to a diagnostic column or the comment-header, never the
canonical column. Flagged for ratification if the intended contract differs.

---

## Open items — W2 remote gate ( kernel 6.17.0-35, 48 cores)

### C8 — VM metric asymmetry (documented limitation)

5 metrics (`cpu blk mbw llcocc llcmr`) scope identically for container and VM.
`netp` is measurable on the VM tap iface (host-side). Guest `nets` is **not
attributable host-side → N/A**, documented as a limitation, not a defect.

### C9 — remote platform verification (gated, before any mutation)

W0 confirmed only reachability + kernel 6.17.0-35 + 48 cores. **Unverified:**
resctrl/RDT mount + RMID count, BTF at `/sys/kernel/btf/vmlinux` (v3.3 CO-RE),
cgroup v2 unified + perf cgroup-mode, sched_ext (`/sys/kernel/sched_ext/`).
These are verified by running `shared/intp-preflight.sh` on the remote — a
**human-gated W2 step**, no remote mutation before that gate.

### C10 — code transport to remote = git clone (ratified, 2026-06-02)

**Decision (ratified):** sync the remote host by **git clone** of the pushed
`feat/container-based-interference` branch (not rsync of the working tree, not a
`build-deb.sh` `.deb`). The branch is pushed, so W2 clones it on the testbed
and builds there against kernel 6.17. Remote mutation still requires the human
gate per the brief's `[SINGLE-FLIGHT]` rule — the transport method is settled, the
go-ahead to execute W2 is separate.

---

## W1 implementation plan & codegen strategy (2026-06-02)

W1 scoping (read-only fan-out + feasibility audit) produced a 17-packet,
foundation-first plan. v2.1 = MEDIUM effort (already 6/7 per-cgroup, builds
clean); v3.3 = HIGH (from-stub clone of v3.2). Local preflight confirmed this
notebook can **compile** all of it (clang 18, libbpf-dev, bpftool, BTF, gcc 13);
load/attach/RDT/workload validation is run-side and defers to the remote (W3).

Packets: P0 scaffold (done), P1 shared types, P2 BPF object, P3 loader, P4 CLI,
P5 unit test, P6 integration tests; V1 v2.1 target abstraction, V2 v2.1 VM-netp
tap backend, V3 v2.1 RDT/perf-cgroup remote validation, V4 .deb (optional);
H1 harness `run_profiler_v3_3`, H2 VM tap-netdev qemu path, H3 `stage_report`
guard, H4 HiBench wiring; S1 `validate-cross-variant.sh`, S2 docs/registration.
Ordering: P0 → P1 → V1 → P4 → V4 → P2 → P3 → V2 → P5 → H1 → H3 → S1 → H2 → H4 →
P6 → V3 → S2.

### C11 — codegen strategy: single-writer for coherent units

The v3.3 BPF unit **P1→P2→P3** (shared header `intp_agg.bpf.h` → BPF object
`intp_agg.bpf.c` → loader `intp_agg.c`) shares the `struct intp_counters` layout,
the `agg_per_cgroup` map ABI, and the field-for-field `SUB()`/sum loops. They MUST
be authored **sequentially by one writer** — parallel codegen desyncs the
kernel/userspace contract and the BPF verifier rejects a mismatched skeleton at
load. Likewise the three harness packets **H1→H2→H3** all edit
`bench/run-intp-bench.sh` and must be one single-writer chain. Fan-out (parallel
worktrees) is allowed only across the **disjoint trees**: v3.3 / v2.1 (V1→V2) /
shared-docs. P4 (args) and P5 (unit test) touch disjoint files and may overlap the
BPF unit, but P5 depends on the final P1+P3 field set.

### C12 — do NOT rename the v3.3 BPF basenames

Keep `intp_agg.{bpf.c,bpf.h,c,_args.c,_args.h}` and the skeleton symbol prefix
`intp_agg_bpf__*`. Renaming would force matching churn in `gen-vmlinux.sh`,
`test-core-portability.sh`, the Makefile `BPF_*` vars, and every
`intp_agg_bpf__open/load/attach/destroy` call site for no benefit. P0 renamed only
the **binary** (`intp-ebpf-core-cgroup`), `GROUP_NAME`, and the Prometheus label.

### C13 — `--no-diag-cols` is load-bearing for the harness (H3)

`stage_report()` in `run-intp-bench.sh` reads `off=n-7` (the LAST 7 columns as the
metrics). If a v3.3 row carries trailing `netp_dev`/`nets_sys`/`mbw_raw_mbps`, that
mis-reads diagnostics as metrics. Fix (repo-consistent, mirrors v3.2's
`--no-raw-mbw`): every harness/validate call site that captures the canonical TSV
(`run_profiler_v3_3` in H1, HiBench in H4, `validate-cross-variant.sh` in S1)
passes **`--no-diag-cols`**, keeping captured rows at leading-ts + exactly 7
columns so `off=n-7` stays correct (C5). Diagnostic columns are emitted only when
explicitly requested for analysis.

### C14 — deferred items flagged by the W1 audit (track to closure)

- v3.3 `nets` × VM = **N/A** (guest softirq host-unattributable, C8) — record
  explicitly in S2 docs so the parity matrix is unambiguous (not only the generic
  C8 asymmetry note).
- Add a VM tap-coverage assertion (analogous to `diagnose-netp-veth-coverage.sh`)
  so `--target-vm` netp is proven to move and does **not** silently degrade to
  system-wide when H2's tap iface is absent (current `launch_workload_vm` uses
  SLIRP user-net with no host tap).
- H1 must add the v3.3 arm to BOTH the `stage_build` build step AND the
  per-variant binary-existence GUARD block (`variant_selected vX && [ ! -x $VX_BIN ]`),
  or `stage_build` won't warn on a missing `intp-ebpf-core-cgroup`.
- Test scripts (`BIN=./intp-ebpf-core` defaults, `PIN_ROOT=…intp-v3.2-core-test`)
  still carry v3.2 strings after P0; P6 owns those edits. (The args `--help`
  `V3.2-specific:` text was fixed in P4.)

---

## v3.3 BPF unit (P1-P3+P5) review resolution (2026-06-02)

The single-writer BPF unit passed adversarial static review (ABI coherent,
CO-RE reads correct vs real 6.17 BTF, builds warning-free, 17 unit assertions
pass, canonical order intact, C1/C2/C5/C7 honored). Verdict was "iterate" for the
findings below. Load/attach is unverifiable locally (no CAP_BPF, perf_paranoid=4,
resctrl absent) — compile-clean + unit-test is the W1 bar.

### C15 — review findings resolution

- **blk bio-owner output (HIGH) → surfaced, not dropped.** `blk_bytes` (from the
  current-task `block_rq_complete` gate + the bio-owner `tp_btf/block_bio_complete`
  writeback top-up) was written but unread. Resolution: surface per-cgroup block
  throughput as a new diagnostic trailing column **`blk_MBps`** (after
  `mbw_raw_mbps`, suppressed by `--no-diag-cols`). Canonical `blk` stays svctm %
  (C7). The bio-owner program is KEPT — it is the v3.3 bio-cgroup blk differentiator
  (§2 matrix) and is now observable/testable; its verifier validation is a W3 gate
  item (below). Diagnostic columns are now: `netp_dev, nets_sys, mbw_raw_mbps,
  blk_MBps`.
- **nets PROXY denominator (LOW) → corrected.** The byte-share cost model
  `nets(cg)=nets_sys*bytes(cg)/bytes_total` used `agg_global` cgroup_skb bytes as the
  denominator, but cgroup_skb is attached only to the target cgroup, so the
  denominator equalled the target's bytes and `share≈1.0` (it wrongly charged all
  system softirq to one tenant). Fixed: denominator = true host-wide device bytes
  (`netp_dev_tx+rx` from `net_dev_xmit`/`netif_receive_skb`); numerator stays the
  target's cgroup_skb bytes. An explicit PROXY mixing socket-level and device-level
  bytes, validated on the remote.
- **auto-attach (LOW) → explicit.** `set_autoattach(false)` on the cgroup_skb and
  perf programs before skeleton attach (they are attached manually), removing the
  implicit reliance on libbpf silently skipping their auto-attach.
- **cgroup path level (LOW) → `realpath()`.** `resolve_cgroup_identity()`
  canonicalizes the path before counting components for `target_level` and asserts
  the `/sys/fs/cgroup` prefix.

### C16 — W3 remote-verifier gate items (deferred, MEDIUM)

These need a real verifier/load on the remote kernel 6.17 (clone+build, then
`tests/integration/test-load-attach.sh`) and are NOT W1-blockers:

- `tp_btf/block_bio_complete` typed `bio*` load; the 16-level unrolled CO-RE
  ancestor walk (`cg_ptr_matches_target`) instruction-count/complexity; the
  `tp_dev_is_lo` ctx+dynamic-offset read.
- `cgroup_skb` ingress/egress attach (needs CAP_NET_ADMIN + writable cgroup-v2 dir
  fd) and non-zero byte accrual on a real container.
- perf cgroup-mode (`PERF_FLAG_PID_CGROUP`) open + on-CPU-gated accrual for llcmr.
- nets PROXY accuracy vs a controlled two-cgroup iperf3 ground truth.
- blk no-double-count across the `block_rq_complete` (svctm) and
  `block_bio_complete` (byte top-up) probes.
- cgroup-id == st_ino and `target_level` depth vs `bpf_get_current_ancestor_cgroup_id`
  semantics on LXD/systemd nested scopes.
- VM tap-coverage: `launch_workload_vm` currently uses SLIRP user-net (no host tap),
  so `--target-vm` netp needs the H2 tap path + a coverage assertion (also C14).

---

## W3 remote validation findings (2026-06-02)

W2 bootstrap + W3 smoke ran on the testbed (kernel 6.17, BTF + cgroup2 +
sched_ext + CAP_* all present). The v3.3 BPF unit **loads + attaches cleanly**
(verifier passes the `tp_btf/block_bio_complete` prog, the unrolled CO-RE walk,
`cgroup_skb`, perf-cgroup-mode — C16 resolved positively). Manual busy-vs-idle
smoke + the minimal stress-ng campaign confirmed **per-cgroup attribution works
on bare** (cpu/blk/netp/nets/llcmr/mbw/llcocc sane per class; v3.3 `cgroup_skb`
even captures loopback netp that v2.1's netns path misses).

### C17 — v3.3 container attribution: PID-launched envs need cgroup resolution

**Bug (W3):** in the **docker container** env, v3.3 reported `scope=system-wide`
and **all-zero** BPF metrics, while v2.1 was sane. Root cause: the docker
launcher (`launch_workload_container`) targets the profiler by container **PID**
(`--pids <cpid>`) and never resolves a cgroup — unlike the bare path
(pre-created cgroup) and the LXC path (resolves the cgroup). v2.1/v2/v3.2 accept
`--pids`; **v3.3 is cgroup-id only (it dropped the PID path), so `--pids` is a
no-op → it ran system-wide → ~0 for a 1–2-core workload on 48 cores.**

**Fix:** `run_profiler_v3_3` now self-resolves the target PID's cgroup v2 path
(`resolve_pid_cgroup` → `/proc/<pid>/cgroup` → `/sys/fs/cgroup<rel>`) and passes
`--cgroup` whenever handed a PID without a cgroup. Localized to the v3.3 wrapper;
v2.1/v3.2 unchanged. Also the **foundation for the PID-launched runtimes**
(podman, k8s pods). Pending remote re-test of the container env.

### C18 — container-runtime comparison axis (planned)

Extend the env set beyond `container` (docker) / `container-lxc` with
**`container-podman`** (daemonless → no quiesce needed; CRIU/live-migration that
docker lacks) and **`container-k8s`** (k3s-backed pods; the deepest cgroup
nesting `kubepods.slice/.../<scope>` — the hardest test of v3.3's ancestor-cgid
gate + `target_level`; heavy daemons → strongest quiesce case). The bench-tenant
image (`bench/setup/Dockerfile.bench`) is OCI, so it serves docker/podman
directly and imports into k3s containerd (or pulls from the `publish-images.sh`
ghcr.io path). k3s install is opt-in (heavy), like `--with-scx`. All four
runtimes share the C17 cgroup-from-PID resolution.

### C19 — runtime-axis validation status (2026-06-02)

Remote re-validation on the testbed after the C17 fix + podman:

- **C17 CONFIRMED.** v3.3 in the **docker** env flipped zero→sane: profiler
  header now `scope=cgroup=…/system.slice/docker-<id>.scope (resolved from
  pid=…)`, cpu≈28, and netp≈79 / nets≈59 on the net workload (was all-zero
  system-wide).
- **podman VALIDATED.** v3.3 in `container-podman` attributes correctly:
  `scope=cgroup=…/machine.slice/libpod-<id>.scope/container (resolved from
  pid=…)` — note the runtime's cgroup is a level deeper than docker's and
  `resolve_pid_cgroup` handled it transparently. cpu≈32, netp≈79.
- **v2.1 unchanged** in both envs (regression check passed: cpu≈37, nets≈74).
- **k8s SCAFFOLDED, not yet runtime-validated.** Pod launcher + crictl PID
  resolution (jq `.info.pid`, grep+sed fallback) builds clean; the deep
  `kubepods.slice` ancestor-cgid gate and crictl ordering need a live k3s host —
  gated behind the opt-in `--with-k8s` install.

Runtime axis: **docker ✓, podman ✓, lxc (existing), k8s (scaffolded)**.

### C20 — v2.1↔v3.3 method differences observed (for W4)

Both variants attribute sanely, but the per-cgroup methods legitimately differ —
W4 must characterize, not treat as error:

- `netp`: v3.3 `cgroup_skb` ≈79 vs v2.1 netns ≈4 on the container net workload —
  v3.3 captures the tenant's socket traffic v2.1's netns path misses (a real
  eBPF advantage, not a bug).
- `cpu`: v3.3 (`sched_switch` on-cpu ns) runs ~25% below v2.1 (`cpu.stat`
  usage_usec) — a normalization/method difference to reconcile in W4.
- `llcocc`: v3.3 per-cgroup ≈33–67 vs v2.1 ≈91 — different resctrl mon_group
  scoping; W4 to determine which better reflects the tenant's true occupancy.

### C21 — k8s (container-k8s) VALIDATED on the remote (2026-06-02)

The four-runtime axis is complete: **docker ✓ (C17), podman ✓, lxc (existing),
k8s ✓**. The k8s path needed three manifest-validity fixes (W3 caught each — the
launcher was untested locally), all "pod never launched → crictl PID 0 →
system-wide":

1. `resources:` block over-indented (8→6 spaces) → `kubectl apply` YAML parse error.
2. pod name carried `_`/`.` (`app10_search`, `v2.1`) → RFC 1123 reject; sanitized.
3. `${pod: -63}` cap emptied sub-63-char names on bash 5.2.21 → empty-name reject;
   guarded + switched to `tail -c 63`.

After the fixes, the pod schedules, `crictl inspect .info.pid` returns the host
PID, and **v3.3 resolves the deepest cgroup**
`/sys/fs/cgroup/kubepods.slice/kubepods-pod<uid>.slice/cri-containerd-<id>.scope` —
the ancestor-cgid gate + `target_level` resolve at depth (the C18 deep-nesting
stress test PASSES). Metrics are per-class sane (v3.3 cpu≈39 on the cpu workload,
netp≈95/nets≈90 on the net workload; v2.1 cpu≈47, nets≈94). The C20 method deltas
hold (v3.3 per-cgroup `llcocc`≈8–54 vs v2.1≈93–96). k3s is registered for quiesce
(kept only for container-k8s campaigns).

### C22 — W4 conformance analysis (2026-06-02): PARTIAL (conformance established)

Compared the W3 v2.1/v3.3 results against the v2/v3.2 reference (different host —
the legacy host on k6.8 vs the testbed on k6.17), with an adversarial refutation layer.

- **Schema conformance: ESTABLISHED.** Identical column-header md5 across all 52
  W3 + 554 reference profiler.tsv files; 7-col header / 8-field (leading-ts) data
  rows; identical 11-key run.json. Rep-independent.
- **Qualitative/behavioral conformance: ESTABLISHED.** v2.1 reproduces v2's
  per-class dominant-metric signature in all 5 workload classes; v3.3 reproduces
  v3.2's. Family ancestry holds. v3.2-reference netp=0 (all 90 samples) confirms
  v3.3's per-cgroup netp=100 (cgroup_skb loopback capture) is genuinely new, not a
  regression. Ranks survive the thin reps.
- **NO cross-host numeric equivalence** is claimed or supported (different host/
  kernel/backends) — only schema + qualitative conformance, per the W4 guard.
- **Runtime axis:** docker≈podman≈k8s attribution is consistent + sane vs bare,
  but QUALITATIVE/rank only (n=1 rep per container runtime; variance unestimable).

**Faithfulness (C20 deltas) — adjudicated by groundtruth.tsv where possible:**

- **cpu: v2.1 is faithful, v3.3 underreports.** GT `cpu_busy_pct` ≈50.2 (cpu wl)/
  33.5 (mem)/15 (cache); v2.1 `cpu.stat` matches, v3.3 `sched_switch` reads ~8–12.
  (This RETRACTS an earlier "needs ground truth / neither wrong" claim.)
- **netp: v3.3 advantage by hook placement** (cgroup_skb counts per-cgroup loopback
  socket bytes v2.1 netns / v3.2 device miss) — but NOT GT-confirmed (NIC GT ≈0 for
  this loopback workload).
- **llcocc: v3.3 advantage by attribution SCOPE** (v2.1 degrades to system-wide in
  containers; v3.3 resolves the cgroup) — UNVERIFIED by occupancy GT (the
  resctrl_llcocc_bytes / mbw / perf GT columns are empty).
- Net: faithfulness is **mixed by metric**, not a uniform "v3.3 wins."

**Process gap caught by refutation:** the per-dimension agents under-used the
`groundtruth.tsv` present in every W3 run dir (populated cpu/disk/net columns);
the refutation layer re-derived the cpu/disk/net adjudication from it.

**Data limitations / what a paper-grade campaign needs:** ≥5–10 reps per container
runtime (W3 had n=1); container-axis coverage of the cache/mem/disk classes
(currently bare-only off the container axis); a populated resctrl/perf ground-truth
path to actually adjudicate llcocc/mbw/llcmr faithfulness; same-host v2/v3.2
re-measurement to upgrade qualitative ancestry to numeric equivalence; and
scipy/numpy on the analysis host for KS/Mann-Whitney/effect-size rigor (absent now —
all W4 stats are stdlib median/IQR/rank).

### C23 — W5-prep campaign + W4 faithfulness redo (2026-06-03)

Scoped validation campaign on the testbed (k6.17.0-35, 48c) to upgrade W4 from
n=1 to n=5 and adjudicate faithfulness directly from `groundtruth.tsv`, closing
the C22 process gap with a dedicated tool, `bench/analyze-faithfulness.py`.
numpy/scipy now installed on the host (and added to `setup-host.sh`
`install_analysis`), so the stats are KS / Mann-Whitney / Cliff's-delta, not the
stdlib-only fallback C22 used.

- **Campaign:** solo stage, one workload/class {app01 LLC, app07 mem, app10 cpu,
  app11 net, app13 disk} x {bare, container (docker), container-podman,
  container-lxc, container-k8s} x {v2.1, v3.3} x 5 reps x 60s, quiesce active
  (keep docker/lxd/incus/k3s). **250/250 cells, 60 samples each, 0 failed
  attribution.** Results + report (gitignored): `results/container-solo-5cls/`,
  `.../W4-faithfulness.md`.
- **netp denominator verified:** `detect_default_iface()` resolves `cni0`@10G;
  the degraded/down NICs (docker0/eno2/virbr0/lxcbr0/enx…) are never selected
  (only chosen via fallback when nothing is up) and carry no workload bytes
  (loopback). Consistent across envs because the container-k8s campaign keeps k3s
  (hence cni0) up. No harness change needed.

**W4 faithfulness — GT-adjudicated:**

- **cpu is the only same-scale GT** (`cpu_busy_pct`, populated for ALL workloads;
  profiler cpu is cgroup-scoped vs GT system-wide -- they align for SOLO runs, so
  the ratio is a solo-only adjudication). Numbers below are AFTER the
  container-lxc re-run (all 5 envs now valid; analyzer emits Cliff's-delta +
  Mann-Whitney p, mwu_p<=0.012 / Cliff -1 on the under cells).
  - **v2.1 cpu: 20/20 FAITHFUL** (5 envs x 4 non-idle workloads, ratio 0.93–1.01).
  - **v3.3 cpu: 15/20 faithful, 5 UNDER** — the 5 under-reports are EXACTLY the
    pure-CPU app10 (matrixprod), one per env. **This REFINES C22:** v3.3
    `sched_switch` undercounts CPU specifically for compute-bound /
    low-context-switch workloads (threads rarely yield => switch-driven on-cpu
    accrual misses time), NOT uniformly -- it is faithful on cache/mem/net. The
    undercount magnitude is RUNTIME-DEPENDENT: ratio 0.22–0.34 on
    bare/docker/podman/k8s but milder (0.75) in the incus system container
    (container-lxc), whose heavier system-container scheduling yields more
    context switches for sched_switch to catch.
- **blk/netp/nets are 0–100 normalized** (GT disk/net are raw MB/interval; the
  net workload is loopback => NIC GT~0) => adjudicated QUALITATIVELY, no ratio.
  blk saturates on the disk wl (~80–100) and ~0 elsewhere (both variants track);
  v3.3 `netp`=100 captures per-cgroup loopback (cgroup_skb) the v2.1 device path
  misses (netp=0), and v2.1 softirq `nets`=99 sees it (C20/C22 hook-placement
  story holds, not GT-confirmed).
- **mbw/llcocc/llcmr: GT-UNVERIFIABLE** — resctrl/perf GT columns empty ('--').
  Same W4 data limit; populating that GT path + a re-run is the paper-campaign fix.

**container-lxc was INVALID in the first run — ROOT-CAUSED, FIXED, and RE-RUN
(now valid; 5-runtime axis complete).** GT `cpu_busy_pct`~=0.36 (host idle) +
profiler pinned `llcocc`=98 across ALL workloads => the lxc tenant never executed
in the measured cgroup. THREE layered causes, all fixed and validated:

1. **Unsanitized incus instance name** (harness). The per-run name carried the
   variant ('v2.1' -> '.') and workload ('app10_search' -> '_'); incus allows
   only [a-zA-Z0-9-], so `launch` failed and the profiler fell back to
   system-wide. Fixed: `_lxc_instance_name()` (commit `8488fe9`) — same class as
   the C21 k8s pod-name fix.
2. **incus uninitialized** (host). No storage pool / default-profile devices =>
   "Failed getting root disk: No root device could be found". Fixed:
   `incus admin init --auto` (storage pool + incusbr0 + root/eth0); now also run
   idempotently by `setup-host.sh`.
3. **Wrong engine** (harness default). `LXC_BIN` defaulted to `lxc` = the
   `/usr/sbin/lxc` LXD-snap shim (5.21.4 LTS, uninitialized), NOT the apt `incus`
   (6.0.0). Fixed: `run-intp-bench.sh` auto-prefers `incus` + the `images:` remote
   when present (override via INTP_BENCH_LXC_BIN / INTP_BENCH_LXC_IMAGE). Snap LXD
   is intentionally not used (bloated, user decision).

Validated (commit `325f975`): container-lxc attaches to
`cgroup=/sys/fs/cgroup/lxc.payload.<name>`, stress-ng running inside the incus
container. The 50 INVALID lxc cells were then **re-run** (incus, same params) and
the W4 report regenerated: lxc is now per-class sane and folds into the cpu
faithfulness above (v2.1 lxc app10 cpu=50 vs GT 50.5 FAITHFUL; v3.3 app10 UNDER
but milder, 0.75). Two lxc-specific observations: (a) the v3.3 app10 undercount
is runtime-dependent (above); (b) **v3.3 reads `llcocc`=0 for the incus
`lxc.payload` cgroup** (resctrl mon-group unresolved there) while v2.1 reads it
(~86–99) — a v3.3 per-cgroup resctrl coverage gap for system containers (llcocc
is GT-unverifiable regardless). Report: `results/container-solo-5cls/
W4-faithfulness.md` (gitignored, on the remote).

**VM image (vm env) — RESOLVED (libguestfs blocked here; switched to qemu-boot; built + published):**

1. **passt SIGSEGV (FIXED).** Ubuntu 24.04 GA passt (`0.0~git20240220`) crashes
   under libguestfs 1.52; both the direct and libvirt backends route appliance
   networking through passt, so `build-bench-vm.sh` died at virt-customize
   `[0.0] Examining the guest`. Fixed with the official upstream passt .deb
   (`2026_05_26`/`4b28237`, reversible via `apt install --reinstall passt`) — the
   appliance now boots without crashing.
2. **No appliance outbound connectivity (OPEN).** In-appliance apt then fails DNS
   ("Temporary failure resolving archive.ubuntu.com"). The appliance inherits the
   host resolv.conf (systemd-resolved 127.0.0.53 stub); priming a routable
   resolver inside the `--run-command` (commit on `build-bench-vm.sh`) did NOT
   help — the appliance cannot reach `1.1.1.1` either, i.e. it has no working
   outbound NAT/route, not just a DNS-config problem.

=> The `virt-customize --install` path cannot fetch packages on this host.
**RESOLVED** by rewriting `build-bench-vm.sh` (commit `9374f6e`) to customize via
a normal qemu boot + cloud-init instead of libguestfs: the guest's own SLIRP
user-net works, cloud-init installs the bench deps on first boot then powers off,
and the result is verified read-only with virt-cat (which only needs the
appliance to boot, not outbound net). Built a 3.5G qcow2 (Ubuntu 24.04 + HWE 6.17
kernel + stress-ng/iperf3/sysstat/numactl/bc/iproute2; verified PKGS_OK).

**Published as a single-artifact GitHub Package**, not a release (GitHub release
assets cap at 2 GiB; even a compact 2.6G qcow2 exceeds it -> would force a split):
a `FROM scratch` OCI image carrying the qcow2, pushed to
`ghcr.io/ggrv-intp/intp-bench-vm:24.04` (LABEL `org.opencontainers.image.source`
=> the repo; private by default; the 2.6G layer needed a push retry past a
transient ghcr 502). Extract: `id=$(docker create
ghcr.io/ggrv-intp/intp-bench-vm:24.04); docker cp $id:/intp-bench-vm.qcow2 .;
docker rm $id`. Cached on the remote: `/var/lib/intp/ubuntu24.qcow2` (base),
`/var/lib/intp/intp-bench-vm.qcow2` (built).

### C24 — v3.3 nested-cgroup resctrl fix + groundtruth perf path (2026-06-03)

Two paper-grade follow-ups to C23 (the W4 GT gaps and the v3.3 incus llcocc=0).

**(a) v3.3 per-cgroup llcocc/mbw = 0 for incus — ROOT-CAUSED + FIXED (`b9611db`),
live-validated.** v3.3 read llcocc/mbw = 0 for the container-lxc env while v2.1
read them. A live resctrl probe (run v3.3 directly on the container cgroup +
snapshot `/sys/fs/resctrl`) showed: incus runs the payload in a CHILD cgroup
literally named **`.lxc`** (siblings `init.scope`, `system.slice`); cgroup v2's
no-internal-processes rule leaves the targeted PARENT `lxc.payload.<n>` with an
empty `cgroup.procs`. v3.3's `read_cgroup_pids` read ONLY the parent's
`cgroup.procs` (non-recursive) => seeded NO PIDs => its resctrl mon_group got no
tasks => occupancy 0. docker/k8s targets are leaf scopes, so they were
unaffected. Fix: recurse the cgroup subtree (`stat`-based, since cgroupfs reports
`d_type=DT_UNKNOWN`), skipping ONLY `.`/`..` (NOT `.lxc` — a first attempt that
skipped all dot-names reproduced the bug), plus rescan each interval (mirrors
v2.1 `resctrl_rescan_cgroup` + the v3.3 DESIGN). Validated on incus: app01
llcocc 0->76, app07 llcocc 0->95 / mbw 0->17. (The earlier C23 W4 lxc rows were
captured pre-fix; v3.3 lxc llcocc/mbw should be re-measured to update them.)

**(b) groundtruth perf columns now populated (`a1315ea`).** `start_groundtruth()`
spawned `perf stat` but never parsed `perf-stat.txt`, so instr/cycles/llc_ref/
llc_miss were hardcoded `--`. Switched perf to interval mode (`-x; -I <ms> -a`,
one CSV line per (interval,event)) + added `merge_perf_into_groundtruth()` to fold
per-interval counts into the TSV. Validated on bare/app10 (instr~147G, cycles~69G,
llc_ref~12M, llc_miss~1M per interval). This makes **`llcmr` GT-adjudicable**
(miss ratio = llc_miss/llc_ref) plus instr/cycles cross-checks; the perf GT is
system-wide (`-a`), valid as the tenant's GT for SOLO runs (like cpu_busy_pct).

**resctrl mbw/llcocc GT remain `--` by design.** resctrl CMT/MBM is exclusive
per task (one RMID per task): while the profiler-under-test holds the tenant's
tasks in its mon_group, no independent collector can read those same tasks'
occupancy/bandwidth. So the profiler's OWN direct resctrl read IS the occupancy/
mbw ground truth; "adjudicating" them reduces to verifying it monitors the right
mon_group/tasks — which is exactly the (a) fix. (An independent membw GT could use
the uncore IMC PMU, which is what the profiler's mbw backend already reads.)

**Next to fully close W4:** a campaign re-run with the fixed harness (populated
perf cols) + the fixed v3.3 (incus llcocc/mbw) + an analyzer pass that adjudicates
`llcmr` against the new GT and refreshes the lxc resctrl rows.

### C24a — W4 closing re-run + faithfulness verdict (`container-solo-5cls-r2`, 2026-06-03)

The C24 "next to close W4" re-run is **done**: fixed harness + fixed v3.3, analyzer
adjudicates `llcmr`. **250/250 cells** (5 envs × {v2.1,v3.3} × 5 workloads × 5 reps,
60 samples/cell, 0 failed attribution). Report: `docs/reports/W4-faithfulness-r2.md`.
Findings were cross-checked by independent recomputation from the raw perf/profiler
files (multi-agent adversarial verification).

- **CPU (the only same-scale ABSOLUTE GT): 20/20 FAITHFUL both variants** (ratios
  0.90–1.02), recomputed independently from `groundtruth.tsv`. The C23 v3.3 app10
  CPU undercount did **not** recur in r2.
- **`llcmr` now GT-adjudicable, but the ratio is DIRECTIONAL only.** GT method
  verified correct (100×llc_miss/llc_ref reproduced from raw perf; matches perf's
  own native "of all cache refs" within ~10% on every bare cell). §1b shows every
  cell UNDER/OVER, but that is **not** an absolute-faithfulness failure:
  - *Event-definition:* GT denominator = `cache-references`
    (`PERF_COUNT_HW_CACHE_REFERENCES`, all-op `LONGEST_LAT_CACHE.REFERENCE`); both
    profiler variants use `PERF_TYPE_HW_CACHE LL|OP_READ|RESULT_ACCESS` (READ-only,
    distinct kernel PMU mapping). Numerators agree in intent (LLC misses);
    denominators are a **different physical event**. (v2.1's raw-fallback denom
    `0x4F2E` *is* GT's event, but these runs used the primary hwcache backend.)
  - *Scope:* profiler cgroup-scoped vs GT system-wide `-a`. A miss ratio is
    intensive, so scope can only move it for low-footprint tenants: app10_search
    (GT llc_ref ~12M/interval) gap ≈ scope dilution ✓; app07_ordering (GT llc_ref
    ~495M/interval, true ratio ~87%) gap is event-definition, NOT scope. No
    `llcmr_sys` diagnostic column exists.
  - *Directionally the profiler IS faithful:* Spearman (profiler vs GT across 25
    cells) **v2.1 ρ=0.66, v3.3 ρ=0.83 (both p<0.001)**, computed in the analyzer.
    v3.3 preserves GT's high>low>zero macro-tier in 5/5 envs; v2.1 weaker (its
    container-family app01 cgroup read over-counts misses, breaking the top-2 in
    3/5 envs). So §1b's UNDER/OVER labels are indicative, not an absolute error.
  - (Checked: the app07 `llcmr≈40` figure IS correct in the raw data — field-6
    median 40–41; an earlier "stale" suspicion was a column-misread of `mbw`.)
- **v3.3 incus/lxc llcocc/mbw fix confirmed in r2:** `llcocc` **0 → ~78 (app01) /
  ~93 (app07)**, consistent with the C24 0→76/95 validation.
- **resctrl `mbw`/`llcocc` GT stay `--` by design** (CMT one-RMID-per-task
  exclusivity; the profiler's own read is the GT). Unchanged from C24.
- **v2.1-only oddity (noted, out of scope):** v2.1 reads `llcocc≈97` for app10_search
  (pure CPU, touches ~no LLC) inside all four container envs but ~2 on bare; v3.3
  correctly reads ~2 everywhere. A v2.1 resctrl occupancy-attribution inflation
  in-container; v2.1 is not under repair, so logged not fixed.

**W4 status: CLOSED.** CPU faithful (absolute); llcmr directionally faithful
(absolute ratio confounded by event-definition + scope, documented); resctrl
mbw/llcocc unverifiable by design; v3.3 nested-cgroup occupancy bug fixed.

### C25 — Paper 2 cross-deployment suite: design decisions (2026-06-04)

Design decisions for the Paper 2 cross-deployment suite. The suite operationalizes the
advisor frame ("measure the same application on bare metal, then on container")
as paired per-`(workload, metric, variant)` deltas against the bare baseline,
across the full deployment axis `bare → docker(container) →
podman(container-podman) → incus(container-lxc) → k3s(container-k8s) →
vm-guest`, profiled by {v2.1-c-abi-cgroup, v3.3-ebpf-core-cgroup}, 7 metrics each.
No code this phase; the durable suite definition + parity contract land in
[EXPERIMENT-STRATEGY.md](EXPERIMENT-STRATEGY.md) ("Paper 2 — cross-deployment
benchmark suite").

**State at entry (verified).** The 5 container-family axis points are fully
wired and W4-closed (C24a, 250/250 solo). The cross-env layer
(`plot-cross-environment.py`) is a symmetric all-pairs KW/MW/Cliff omnibus with
NO baseline delta and NO claim-class label; the faithfulness adjudicator
(`analyze-faithfulness.py`) is solo-only and its `ENVS` list (`bare …
container-k8s`, :45) OMITS vm/vm-guest. The Paper 2 statistic (paired
delta-vs-bare + per-metric claim class) is the Phase 1/3 delta.

**P1 — workload set: EXPAND.** Keep the W4 5-class spine and add (a)
`app05_streaming` (`--stream 8 --vm 4 --vm-bytes 16G`, :292) as a saturating
memory-bandwidth driver (the W4 set only reaches mbw≈17 on app07), and (b) a
real-NIC network path: the veth/iperf3 workloads (`app11b_tcp_veth`,
`app12b_udp_veth`, :310-311) are bare-only today (only `launch_workload_bare`
parses the `VETH:` sentinel, :1220), so Phase 1 extends veth/iperf3 dispatch
into the container and VM launchers (TAP for vm-guest, per P5). The network
representative therefore upgrades from the loopback `app11_sort_net` (netp=0 on
v2.1 / =100 cgroup_skb artifact on v3.3) to `app11b_tcp_veth` across the axis.
Result: every one of the 7 metrics has ≥1 clean cross-env representative. Cost:
net-new launcher code in 4+ env paths (Phase 1). Caveat: app05's 16G working
set must fit under `--bench-mem` (ample at the 2/3-host default on the testbed;
flag if `--bench-mem` is set low).

**P2 — parity contract: network mode + storage backend are TREATMENT
variables.** Held constant: workload binary+args, the CPU/RAM budget (existing
floor(2/3-host) via `--bench-cpus`/`--bench-mem`), profiler interval/duration,
quiesce keep-set {docker lxd incus k3s}. Treatment axes: deployment env (6) ×
profiler variant (2) × network mode (host/veth/TAP/SLIRP) × storage backend
(native/overlayfs/qcow2). Net mode and storage backend are NOT forced identical
across envs (that would be unrepresentative); each env runs its canonical
net+storage, recorded per run (`net_mode`, `storage_backend`), and a delta vs
bare is attributed to the *env
bundle* (isolation boundary + net + storage), with explicit decomposition arms
where needed (e.g. docker `--net=host` vs bridge). Mandated addition: a per-run
`caps_applied` audit field — today the launchers warn-and-retry-without-caps
when an engine rejects cpu.max/memory.max (:1294-1314 et al.) and nothing
records it, so a "parity" run is currently un-auditable; a run with
caps_applied=false is excluded from parity comparisons.

**P3 — statistic: per-class, claim-class-gated** (additive extension, not a
rewrite). cpu (ABSOLUTE) → log-ratio overhead vs bare + bootstrap CI on the
per-rep means (ratio band 0.8–1.25 retained from W4). llcmr (DIRECTIONAL) →
Spearman ρ + rank-preservation flag; never an absolute ratio.
mbw/llcocc/blk/netp/nets (DESCRIPTIVE) → median+IQR delta vs bare, stamped
descriptive. A module-level `CLAIM_CLASS` map in both `analyze-faithfulness.py`
and `plot-cross-environment.py` stamps a `claim_class` column into `stats.tsv`
so a descriptive metric can never emit an absolute-overhead claim. Reps stay
UNPAIRED (KW/MW/Cliff — independent-sample by design,
[CROSS-ENV-CAMPAIGN.md](CROSS-ENV-CAMPAIGN.md):44-50); multiple-comparison
correction switches Bonferroni → BH-FDR for the 6-env (15-pair) axis (already
flagged upstream in the doc, :103-106); env order is passed in deployment-axis
order to the cross-env plotter (which currently defaults to alphabetical,
`plot-cross-environment.py`:478; `plot-intp-bench.py` already uses a fixed
deployment-axis `ENV_ORDER`, :162).

**P4 — scope: solo + full W5 colocation + IADA closed loop, in-paper.** Solo
deltas are the headline; the W5 colocation campaign and the IADA closed loop
(EXPERIMENT-STRATEGY.md) are in-paper, not deferred. Implications recorded for
Phase 4: (1) the cpu ABSOLUTE claim is solo-only by construction (profiler
cgroup-scoped vs GT system-wide align only single-tenant,
W4-faithfulness-r2.md:12) → under colocation cpu drops to directional UNLESS a
cgroup-scoped CPU ground truth (per-cgroup `cpu.stat` read by an independent
collector) is added; (2) `analyze-faithfulness.py` is hardcoded to the solo
glob (:187) → colocation needs new analyzer code; (3) the `pairwise` stage does
NOT compute a victim-throughput delta today (contrary to the orchestrator
docstring :18-21) — it writes raw victim/antagonist logs only (:3238-3262); the
only existing interference delta is (pairwise − solo) on the 7 PROFILER metrics
in the plotter (`plot-intp-bench.py`:1327-1358). The W5 design is the T2
deliverable (below).

**P5 — VM semantics: vm-guest, PMU + TAP pass-through.** vm-guest (in-guest
profiler, per-process attribution comparable to bare/container) is the
canonical VM row; host-observer `vm` is not used for paper rows. Boot the guest
with PMU pass-through (`-cpu host,pmu=on`) so llcmr is measurable in-guest
(DIRECTIONAL), and use the TAP NIC path (`INTP_BENCH_VM_TAP`) so netp/nets see a
real device (required by P1's cross-env net), not throttled SLIRP. mbw/llcocc
remain STRUCTURALLY unavailable in a stock KVM guest (resctrl is host-only; no
vRDT pass-through plumbed) → recorded with an availability status distinct from
`missing` (an `unsupported` status), NEVER faked. BLOCKER to fix before any
vm-guest data is trusted: v3.3 reportedly emits silent zeros for
mbw/llcocc/llcmr in an RDT-less guest instead of `--`, which `availability.tsv`
then mis-marks "OK=measured" — the exact "do not fake it" violation the brief
forbids (v2.1 correctly emits `--`). Fix is Phase 1, verified at the T1 smoke.

**P6 — rep shape: `--reps 12 --duration 120`.** Matches the orchestrator
default (`REPS=12`, :148) and is 3 IADA cycles (multiple of 4), so per-cell
results are ingestible as IADA scheduler input without resampling (P4). 12 reps
(vs W4's 5) tighten the cpu absolute-delta bootstrap CI; the statistical sample
unit is the per-rep mean (the within-run 1 Hz trace is collapsed before the
stats, CROSS-ENV-CAMPAIGN.md:84), so reps — not duration — drive n. A MEASURED
wall-clock estimate (incl. per-rep qemu boot) is produced from a timing dry-run
for sign-off before any Phase-2 launch. Order-of-magnitude: solo axis
(6 env × 2 var × 6 wl × 12 rep ≈ 864 runs) ≈ 1.5 days single-flight (assuming
≤60 s/rep guest boot); the colocation and IADA campaigns stack on top.

**P7 — T3 / v2.1 in-container llcocc: FIX the harness asymmetry + re-run
(option a).** Root cause confirmed two-part: (i) HARNESS targeting asymmetry —
v2.1 dispatch only adds `--pids` when `V_USE_PID_FILTER=1` (default 0), so
docker/podman (which hand a PID, not a cgroup) get neither `--cgroup` nor
`--pids` and v2.1 falls to its system-wide `<root>` mon_group reading
whole-machine L3 ≈97 (:2702, verified), whereas v3.3 gates only on pid-present
and resolves the cgroup → ≈2 (:2889, verified) — matches the C22 hypothesis;
(ii) a STRUCTURAL incus(lxc) scope artifact — even when scoped, v2.1 attributes
the whole `lxc.payload` container's L3 footprint and reads `cgroup.procs`
non-recursively. Decision: fix (i) for future runs (make v2.1 resolve the PID's
cgroup for docker/podman like v3.3, or set the PID filter) and re-run the
occupancy cells; (ii) remains a documented caveat (the harness fix cannot
remove it, and llcocc has no independent GT by RDT-CMT design, C24). The v2.1
llcocc claim class is provisional pending the re-run: expected to drop to ≈2
(faithful) on docker/podman, with lxc/k8s still caveated.

**Carry-over status.**

- **T1 (vm campaign): BLOCKED on Phase-1 fixes.** The 5 container-family envs
  are run-ready; vm-guest needs the P5 fixes (v3.3 silent-zero → `--`; PMU+TAP
  wiring; confirm the in-guest profiler targets the guest-local stress-ng PID —
  `launch_workload_vm_guest` returns the host qemu PID and exports
  `INTP_VMG_GUEST_PID` separately, :2030-2031) plus the one-line
  `analyze-faithfulness.py` ENVS addition (:45). Smoke (human-gated) must assert
  mbw/llcocc render `--`/`unsupported`, NOT 00, for both variants. Image
  publication tag to reconcile at smoke (C23 records
  `ghcr.io/ggrv-intp/intp-bench-vm:24.04`; the brief and `publish-images.sh`
  reference `bench-images-v1`).
- **T2 (W5 colocation design): DESIGN deliverable, not blocking the freeze.**
  Pairing matrix + aggressor set + env subset + victim-delta definition to be
  logged as its own C-entry; must pick the victim-delta definition
  (profiler-metric space vs stress-ng throughput — the latter is new
  orchestrator code) and state cpu's reclassification under colocation. No
  cross-deployment colocation primitive exists yet (`pairwise` co-locates two
  workloads in the SAME env).
- **T3 (v2.1 llcocc): root-caused; outcome = P7 (fix + re-run).** Resolved at
  evidence level above; this C25 entry is the logged structural evidence the
  brief required before accepting a non-default path.

**Phase 1 delta (what the suite requires — implement only this).**

1. `analyze-faithfulness.py` + `plot-cross-environment.py`: `CLAIM_CLASS` map +
   `claim_class` column; paired delta-vs-bare per the P3 per-class statistic;
   BH-FDR; pass deployment-axis env order to `plot-cross-environment.py`
   (replacing its alphabetical `sorted()` default, :478); add vm/vm-guest to
   `ENVS`.
2. `run-intp-bench.sh`: extend veth/iperf3 net dispatch into the container + VM
   launchers (P1); vm-guest PMU (`-cpu host,pmu=on`) + TAP (P5); per-run
   `caps_applied` audit field (P2); add `app05_streaming` to the suite list.
3. v3.3: emit `--` (not 0) for RDT-unavailable mbw/llcocc/llcmr in-guest;
   `availability.tsv`: add an `unsupported` status distinct from `missing`.
4. v2.1 occupancy harness fix (P7): resolve PID→cgroup for docker/podman.

### C26 — Testbed validation + vm-guest enablement + vPMU gap → portable-metrics direction (2026-06-04)

Container-suite code validated on the testbed (Sapphire Rapids, k6.17), and the
vm-guest path brought to first-ever working state. Commits: `3044001`, `34434c8`,
`e03d09a`, `07ac112`, `a2df146`, `b3f8afe`. Pushed to origin; testbed
`git pull && make all` clean.

**Validated on hardware (smoke `results/p2-*`, 1 rep × 20 s):**

- **T3/P7 ✓** — v2.1 in-container `llcocc` on app10 now reads **≈2** (was ≈97);
  the cgroup-resolve fix removed the system-wide `<root>` mon_group fallthrough.
- **caps_applied (P2) ✓** — docker cells record `caps_applied=yes` with
  `bench_cpus`/`bench_mem` in run.json; the undelegated/rejected paths flip to
  `no`.
- **v3.3 `--`-not-`0` (P5) ✓** — RDT-less vm-guest emits `--` for mbw/llcocc
  (not fake `00`); availability marks them `unsupported`. "Do not fake it" held.

**vm-guest enablement (was never working — T1 "never run"): four fixes, all
validated.**

1. `e03d09a` — propagate the in-guest SSH state (tmpdir/sshport/PID) across the
   `$(... | tail -1)` launch subshell via a `.vmg-state` sidecar (the exports
   were lost → the in-guest profiler was silently skipped).
2. `07ac112` — target the **guest-local** stress-ng PID, not the host qemu PID.
3. `a2df146` — scope the in-guest profiler to a **dedicated guest cgroup**
   (`/sys/fs/cgroup/intp-vmg-wl`, heredoc-staged launcher) so `--cgroup` captures
   the whole stress-ng tree; `--pids` on the idle supervisor read cpu/llcmr ≈0.
   **Result: vm-guest `cpu` now works** (v2.1 75 on app10 / 39–44 on app01; v3.3
   16–100 / 40–42) — the absolute-claim metric is usable in the VM row.
4. `b3f8afe` — `perfev.c`/`intp_agg.c` fall back to architectural
   `PERF_COUNT_HW_CACHE_REFERENCES/_MISSES` when the LL-read events fail; guest-
   only (bare/container keep the W4-validated LL events — confirmed: container
   v2.1 app01 llcmr unchanged at 9,8,5,7).

**vPMU finding (definitive, probe `bench/setup/vpmu-probe.sh`):** the KVM guest
has a healthy PMU (8 generic + 3 fixed counters) and architectural
`cache-references`/`cache-misses` count in **all** scopes incl. cgroup-mode — but
the profiler's **LL-read events (`LLC-loads`/`LLC-load-misses`) are `<not
supported>`** in every scope. The architectural substitute is a different,
all-reference miss ratio (~0.01–few %) that rounds to ~0 for low-miss workloads
and is **not magnitude-comparable** to the LL-read `llcmr` in the other five
envs. So a cross-env-comparable in-guest `llcmr` is **not achievable** — a KVM
vPMU virtualization limit, not a code bug. **vm-guest disposition:** `cpu` works;
mbw/llcocc/`llcmr` remain gapped (mbw/llcocc structural `--`; `llcmr` emits the
architectural value but is documented non-comparable). The b3f8afe fallback is
retained as harmless + GT-aligned.

**Direction: add VM-portable metrics** instead of forcing `llcmr` in-guest —
pursuing the IntP modernization paper's future work *"scheduling-latency
metrics [39]"* (Volpert ICPE'25). A research synthesis over the local
`articles/` corpus (Volpert, PRISM, iprof/Gögge, Xavier thesis) + external
sources (PSI, steal, runqlat) recommends **`schedlat`** (per-cgroup run-queue/scheduling
latency via `sched_wakeup`→`sched_switch`; eBPF in v3.3, `/proc/schedstat`+PSI in
v2.1) as the primary VM-portable interference signal, with **`psi_mem`** (PSI
`memory.pressure`) as a secondary memory-dimension proxy and **`schedthr`** (CFS
throttle) as a confound guard. Full design + citations + validation plan:
[docs/reports/8th-metric-vm-portable-design.md](reports/8th-metric-vm-portable-design.md).
Implementation gated on the §7 decisions (scope: schedlat alone vs +psi_mem;
diagnostic-column stage vs canonical-8th promotion stage; tp_btf/sched_switch
attribution; steal inclusion; output raw vs flagged). Once validated, inject the
system-wide backends into v2/v3.2 for completeness.

**Diagnostic tool added:** `bench/setup/vpmu-probe.sh` (boots the qcow2 via a
throwaway overlay + unique cloud-init instance-id, probes perf event × scope
support in-guest).

### C27 — portable-metrics benchmark IMPLEMENTED (local build complete; 2026-06-04)

The C26 direction is built as a SEPARATE, flag-gated (`--portable-metrics`)
benchmark — the canonical 7-metric fingerprint, its on-disk schema, the `off=n-7`
report path, stap byte-compat, and the IADA 7-vector are UNTOUCHED (verified: the
v2.1 backend-registry test still reports exactly "7 metrics, 21 backends"; the
canonical TSV is byte-identical when the flag is off). Metric set + order (locked):
`schedlat psi_mem membw_est psi_io schedthr steal`. Full design + status:
[reports/8th-metric-vm-portable-design.md](reports/8th-metric-vm-portable-design.md)
§10–§11.

**§7 decisions resolved.** Scope = all 6 (not schedlat-alone); integration =
separate benchmark (NOT a canonical-8th promotion — supersedes the §7.2
diagnostic-first/promotion staging); `tp_btf/sched_switch` attribution confirmed
loading on the testbed (C16/W3); `steal` included as a VM-global descriptive
side-channel; `psi_mem` shipped as capacity-only `descriptive` (the analyzer's §3
falsification test adjudicates its bandwidth-blindness); output = raw numbers
(percent for schedlat/psi_*/schedthr/steal, MB/s for membw_est).

**Landed (compiles clean, behavior smoke-tested locally; remote validation
pending):**

- v3.3 loader `intp_agg.c`: schedlat moved diag→portable; added psi_mem/psi_io/
  schedthr/steal file reads + membw_est (reuses the `llc_misses` counter, so it
  works in-guest where the LL-PMU `llcmr` does not); TSV/JSON/Prometheus portable
  block; header.
- v2.1 `src/portable.c` (+ `backend.h`/`backend_registry.c`/`intp-hybrid.c`/
  Makefile): 6 portable `metric_t` chains via a SEPARATE `intp_portable_metrics()`
  list; `--portable-metrics` appends them; `--` (never 0) when a source is absent.
- Orchestrator `run-intp-bench.sh`: `--portable-metrics` → `portable.tsv` +
  header-aware `aggregate-portable-means.tsv` (`stage_report_portable`, NOT
  `off=n-7`); threaded into container + vm-guest in-guest launches. Only v2.1/v3.3
  implement it → pair with `--variants v2.1,v3.3`.
- `bench/analyze-portable.py`: availability matrix, Spearman portable-vs-GT, PSI
  bandwidth-blindness falsification, vm-guest confirmation.

**PENDING:** (5) the validation campaign on the testbed (single-flight;
`--env bare,container,vm-guest`, add `app05_streaming`) + report; (6) back-port the
system-wide backends into v2/v3.2 after validation.

### C28 — Track-A+B fusion: one 13-metric cross-deployment suite (2026-06-05)

The portable benchmark (C26/C27) and the canonical Paper-2 cross-deployment suite
(C25) are fused into ONE suite over the **13-metric superset** (7 canonical + 6
portable), fed by ONE `--portable-metrics` campaign. Rationale: `--portable-metrics`
already emits all 13 columns per `portable.tsv`, so the portable metrics become
first-class citizens of the cross-deployment analysis rather than a parallel track.

- **Shared model `bench/intp_metrics.py`** — single source of truth: `METRICS_CANON`/
  `METRICS_PORTABLE`/`METRICS_ALL`, the 13-metric `CLAIM_CLASS` (cpu=absolute;
  llcmr,schedlat=directional; the other 10=descriptive), `DEPLOY_ORDER`,
  `UNSUPPORTED`, the header-aware/ts-agnostic `parse_capture`, `parse_gt`,
  `rep_summary`, and the stdlib stats (`cliffs_delta`/`bh_adjust`/`order_envs`/...).
- **`bench/analyze-cross-deployment.py`** — the missing Paper-2 headline: paired
  delta-vs-bare per (variant, workload, metric over 13), claim-class-gated (absolute
  → ratio + bootstrap CI, W4 band 0.8-1.25; directional → delta + effect size,
  RANK-ONLY; descriptive → median+IQR delta), every env-vs-bare pair carrying
  Mann-Whitney p (BH-FDR across the env family) + Cliff's delta. The
  cross-deployment analogue of Volpert's D = C_i / C_bare.
- **Refactor** of `analyze-faithfulness.py`, `analyze-portable.py`,
  `plot/plot-cross-environment.py` onto the shared model — verified
  OUTPUT-PRESERVING (byte-identical reports for the two frozen analyzers on
  fixtures; the regression gate of the plan).
- **One campaign feeds all:** `stage_report_portable` now emits the 13-col
  `aggregate-means.tsv` (plus the 6-col portable view), so the cross-env omnibus
  (`plot-cross-environment.py`, reads the 7 it knows) and the paired-delta
  generator run on the same `--portable-metrics` campaign.
- **Testbed-gated remainder:** veth/iperf3 dispatch into the container/VM launchers
  (P1, currently bare-only) is implemented + validated together on the testbed (it
  cannot be validated locally and the loopback `app11_sort_net` is what the current
  campaign uses); until then the network representative across non-bare envs is the
  loopback workload (a documented limitation, as in C20/C22).

### C29 — W5 colocation campaign design (T2 deliverable; 2026-06-05)

The solo deltas (C28) are the cross-deployment baseline; the interference story
needs CO-LOCATED runs, and the VM-portable metrics are exactly the colocation
signals. Design (the `pairwise` stage already co-locates two workloads in one env
and captures the profiler reading; under `--portable-metrics` it captures the
victim's 13 metrics):

- **Pairing matrix:** victim ∈ the 5-class spine {app01 cache, app07 memory, app10
  cpu, app11 net, app13 disk}; aggressor ∈ one saturating stressor per contended
  resource {app01/cache, **app05_streaming/mem-bandwidth**, app10/cpu, app13/disk,
  app11(b)/net}. Headline cells pair each victim with the aggressor that contends
  its own resource (e.g. app01-vs-app05 = cache victim under bandwidth pressure)
  plus a cross-resource control.
- **Env subset:** bare + ≥1 container (docker) + vm-guest (to show the portable
  metrics fire under colocation in a KVM guest where RDT cannot).
- **Victim-delta:** `(pairwise − solo)` per metric on all 13 profiler metrics, with
  `schedlat`/`psi_mem`/`psi_io`/`membw_est` as the PRIMARY contention signals
  (run-queue wait + memory/io pressure + bandwidth rise under a noisy neighbour) and
  `schedthr`/`steal` as confound guards; optional stress-ng victim-throughput delta
  (new orchestrator code) as an external corroboration.
- **Claim-class under colocation:** `cpu` DROPS from absolute to directional under
  colocation (the profiler is cgroup-scoped but GT `cpu_busy_pct` is system-wide, so
  they align only single-tenant — C25 P4/W4-faithfulness-r2 §12) UNLESS a
  cgroup-scoped CPU GT (independent per-cgroup `cpu.stat` reader) is added; the other
  tiers are unchanged. The victim-delta analyzer is a `--w5`/pairwise mode of
  `analyze-cross-deployment.py` (added with the F6 campaign so it is exercised on
  real pairwise data).
- **Shape:** reps/duration per the solo campaign; single-flight, run after the solo
  6-env campaign.

### C30 — v2.1/v3.3 descriptive rename to match the paper labels (2026-06-06)

Extends main's descriptive-variant rename (76bcf59: v2→C-ABI, v3.2→eBPF-CORE, …)
to the two per-cgroup container variants so the paper label, the directory slug,
and every in-repo name agree:

- **v2.1**: dir `variants/v2.1-cgroup-native` → `variants/v2.1-c-abi-cgroup`;
  label `cgroup-native` → **c-abi-cgroup** (the C-ABI approach, per-cgroup);
  binary `intp-hybrid` → **intp-c-abi-cgroup**.
- **v3.3**: dir `variants/v3.3-ebpf-cgroup` → `variants/v3.3-ebpf-core-cgroup`;
  label `ebpf-cgroup` → **ebpf-core-cgroup** (the eBPF-CORE approach, per-cgroup);
  binary `intp-ebpf-cgroup` → **intp-ebpf-core-cgroup**.

**Profiler binaries now match their variant** (every compiled profiler is
`intp-<dir-slug-suffix>`, so a packaged single-variant folder ships a clearly-named
binary): v2 `intp-hybrid` → **intp-c-abi**, v3 `intp-ebpf` → **intp-ebpf-ring**,
v3.2 `intp-eBPF-CORE` → **intp-ebpf-core**, plus the two above. KEPT: the C *source*
basenames (`intp-hybrid.c`, `intp_agg.*` — a package's internal module names), the
shared userspace helper binary `intp-helper` (v0.2/v1.1 RDT helper, same artifact in
both), the stap scripts, and the IDs/GROUP_NAME/Prometheus labels.

Applied across folders, all path references (Makefiles, orchestrator, hibench,
preflight, validate, tests), the `VARIANT_LABELS` maps in every `bench/plot/*.py`
(+ iada), `VERSIONS.md`, and the docs. **Supersedes C12** ("do not rename the v3.3
binary"): C12 avoided churn during the build; the paper-consistency rename is worth
it. KEPT (ID-based, not the stale approach name): variant IDs `v2.1`/`v3.3`, the
resctrl GROUP_NAME `intp-v3.3`, the Prometheus label `intp_v3_3`, and the BPF source
basenames `intp_agg.*`. Verified: 0 old slugs / 0 `intp-ebpf-cgroup` / 0 `ebpf-cgroup`
remaining; all variants build at the new paths; v2.1 unit tests pass (7 metrics/21
backends); analyzers/plotters compile; all scripts bash -n clean.

### C31 — membw_est net-path instrumentation: document + gate (not sample) (2026-06-07)

v3.3 (eBPF) over-reports `membw_est` on net-heavy workloads (~6–7× v2.1 on
app11_sort_net: solo membw_est v3.3≈65 vs v2.1≈9). Root cause: the per-packet eBPF
net instrumentation (`cgroup_skb` ingress/egress + the `net_dev_xmit`/
`netif_receive_skb` tracepoints + the nets-latency probes) executes on every packet
and its cache misses are charged to the cgroup-scoped cache-miss counter that
`membw_est` integrates. **Confirmed by an INDEPENDENT host-side counter**: the
campaign `groundtruth.tsv` shows the v3.3 app11 run generating ~9.0 M system LLC
misses vs ~2.5 M for the v2.1 run (~3.6×). This is the bandwidth analogue of the eBPF
event-amplification in `docs/V3-OVERHEAD-FINDINGS.md` (188–390× ctxsw).

- **The canonical 7 are UNAFFECTED.** `mbw`/`llcmr` are %-normalized (against the
  ~281 GB/s ceiling / as a miss ratio) and clamped 0–99, so the ~0.02%-of-ceiling
  footprint rounds to 0. Verified: app11 `mbw`=0 and `llcmr`=0 for BOTH v2.1 and v3.3.
  Only `membw_est` shows it, because it is the one metric reported as an unclamped
  absolute MB/s. The fingerprint contract holds.

- **Decision: DOCUMENT + GATE, not sample.** Sampling 1-in-N packets in the net hooks
  would cut the footprint ~N× but degrade `netp`/`nets` accuracy (trading one metric's
  contract to fix another's) — REJECTED. Instead `analyze-portable.py` §4 emits a
  **corroboration gate**: any cell with `membw_est`>0 while `mbw`≈0 and `llcmr`≈0 is
  flagged `uncorroborated (net-path)` and must NOT be used for cross-variant
  absolute-bandwidth claims. For non-net workloads membw_est is corroborated (v2.1≈v3.3).

- **Note on commit `7904566`** ("drop per-packet per-cgroup netp HASH update"): it is a
  valid micro-optimization (removes a redundant, cross-CPU-contended `__sync_fetch_and_add`
  that duplicates `agg_global` for a single-target attach; netp from `agg_global` ==
  per-cgroup for single-target) but it is NOT the membw_est fix — the footprint is the
  per-packet hook EXECUTION across all the net hooks, not that one write. The commit
  message overclaimed; this entry is the correction.

### C32 — 15-metric campaign workload set: augmented stress-ng spine + tiered real-world; drop HiBench (2026-06-08)

The extended 15-metric envelope (canonical 7 + portable 6 + scheduling-regime 2: `psp`/`idle_preempt`)
no longer maps to the 6 resource classes alone — `psi_mem`, `schedthr`, `steal`, and the
scheduling-regime trio (`schedlat`/`psp`/`idle_preempt`) need oversubscription, memory pressure,
CFS caps, and colocation, not single-subsystem stress. Workload set for the P2/P3 campaigns is a
three-tier **realism ladder**, each tier run at the breadth it needs (not the full Cartesian):

- **Tier A — controlled stress-ng spine (metric validation; FULL breadth).** Resource-class spine
  + two new profiles (this commit): `app16_cpu_oversub` (`--cpu 96`, oversubscribe the 48 logical
  cores → tasks forced off while runnable → `psp`/`schedlat`/`idle_preempt` fire in *solo*) and
  `app17_mem_pressure` (`--vm --vm-keep` large anon footprint → `psi_mem` reclaim WHEN under a
  cgroup memory cap; ~0 uncapped on a 256G host, expected). `schedthr` from the container-cap legs,
  `steal` from vm-guest. Tier A runs the FULL grid (6 envs + the cadence sweep): cheap, robust,
  isolates each metric.

- **Tier B — real-world ecological validity (3 deployment classes, fixed 1 s).** Redis + memtier
  (latency/scheduling → `schedlat`/`psp`/`idle_preempt` + net; the IADA latency-sensitive narrative)
  and a CloudSuite subset (web-search, in-memory-analytics, data-caching → the SOTA interference
  suite the proposal cites). Run on bare + one container + vm-guest (the 3 CLASSES), fixed 1 s,
  full reps → realistic MIXED 15-metric fingerprints. NOT the full 6-env/cadence grid (cadence is
  characterized by Tier A; the container engine does not change cadence behaviour).

- **Tier C — microservice scheduling story (P3 capstone).** DeathStarBench social-network for the
  strongest scheduling/tail-latency realism, feeding the P3 IADA/sched_ext colocation (W5-style
  victim/aggressor with a real microservice victim). Deployed via docker-compose UNIFORMLY across
  bare, container, AND vm-guest (the bench guest is provisioned with docker — see "Engineering"
  below), so the microservice colocation runs in all three deployment classes, not just bare/
  container. Its deployment lift is absorbed by full automation (a setup script: clone +
  build/pull images + `compose up` + wrk2 load), making it a scripted one-time cost rather than a
  reason to defer.

**DROP HiBench** from the 15-metric campaigns (all profiles = too extensive, one = arbitrary;
heavyweight Spark, overlapping profiles). Keep it only for Paper-1's existing sample-loss study.
nf-core pipelines are reserved for the Paper-4 iprof head-to-head (enrich B5).

**Factorization (avoids a blow-up):** cadence sweep = 3 deployment classes × 6 cadences (cadence
effect); cross-deployment = 6 envs × fixed 1 s (env effect).

**Engineering the heavy real apps into vm-guest (NOT a caveat).** The "docker-in-VM" obstacle is
solved by provisioning the bench VM image with docker (a `setup-bench-vm-docker` cloud-init/setup
step; the guest's SLIRP user-net provides outbound NAT, so in-guest `docker pull` works). The
vm-guest launcher then drives CloudSuite/DeathStarBench through the same SSH→docker-compose path it
already uses for stress-ng, giving uniform bare/container/vm-guest coverage. Each real app ships a
reproducible installer under `bench/setup/` (e.g. `setup-redis-workload.sh`, and equivalents for
CloudSuite + DeathStarBench) so provisioning a host, a container image, or the guest is one
scripted command. Redis needs none of this — it is apt-native and already runs in all three
classes (validated bare 2026-06-08).

### C33 — Compose-suite workload type: one parent cgroup per app, 3-label coverage, idle-window staging (2026-06-11)

C32's Tier-B/C real apps are now implemented as a first-class workload type in
`run-intp-bench.sh`: `COMPOSE:<suite>:<load-profile>:<extra>` (app19–app21 =
CloudSuite data-caching / web-search / in-memory-analytics, app22 = DSB
social-network), with driver dirs under `bench/workloads/compose/` (contract
documented there) and reproducible installers `setup-cloudsuite-workload.sh` +
`setup-dsb-workload.sh`.

**Scoping: the WHOLE multi-container app is ONE profiled workload.** A
generated override parents every service under a per-rep systemd slice
(`cgroup_parent:`; raw cgroup dir under the cgroupfs driver). v2.1's recursive
`cgroup.procs` reader and v3.3's ancestor-cgroup-id gate (its default;
`--exact` is the opt-in) both scope that subtree without profiler changes —
service restarts included, which is what makes the looped in-memory-analytics
batch (restart:always) profileable. Validated live (Docker 29 / Compose v5 /
systemd driver): all services land under the slice; a paused load + outside
stress-ng reads all-zero in-scope (no leakage), resumed load reads hot.

**Load is never profiled.** In-project client containers follow a `load*`
service-name convention → left outside the parent, pinned to the host third
(CPUSET_C); host-side load (DSB wrk2 + graph init) is pinned the same way.
Resource caps apply to the PARENT (slice properties / cgroup files), so the
whole app shares one 1/3-footprint instance — `caps_applied` is recorded from
the KERNEL files, not the systemctl rc.

**Deployment classes (amends C32's "uniformly across bare/container/vm-guest"
reading):** the suites run under all 3 LABELS, but `bare` executes
compose-on-host (container-native apps have no truer bare form) and every such
run records `notes=compose_on_host`; analyzers must treat bare-vs-container
for app19–app22 as an engine-identity check, not a deployment contrast. Only
Redis (app18) spans 3 true classes. podman/lxc/k8s refuse the spec (Tier-B/C
is 3-class by design, C32).

**vm-guest:** `_vmg_start_workload` now dispatches on the spec prefix
(stress-ng | REDIS — closing the vm-guest Tier-B Redis gap — | COMPOSE). The
COMPOSE leg requires the WITH_SUITES bench VM image
(`build-bench-vm.sh WITH_SUITES=1` → `intp-bench-vm-suites.qcow2`: docker +
compose + driver dirs at /opt/intp-suites + DSB clone/wrk2 + CloudSuite
images baked; the 14 GB web-search index is EXCLUDED from the image by
default — app20's vm-guest leg needs an in-guest
`setup-cloudsuite-workload.sh --with-websearch-index` first).

**Box-time discipline:** all provisioning is wrapped by
`bench/setup/stage-next-campaigns.sh`, which REFUSES to run while a benchmark
is in flight and is the single idle-window command (staged-tar loads,
installers, on-box WITH_SUITES image build, verification, READY manifest with
launch commands). Campaign chaining stays monitor-driven from the dev side
(no remote queue daemon) per the operator's decision.

### C34 — D12 impact on the banked P2 campaigns: v2.1 mbw column invalid; targeted v2.1 re-run required; ceiling question (2026-06-12)

Upstream D12 (DECISIONS.md, 2026-06-12) fixed v2.1's mbw chain: for
`--cgroup`/`--pids` targets it had silently preferred the uncore IMC PMUs
(system-total by physics) and, once routed to resctrl, the mbw/llcocc
single-RMID clash (both now share one refcounted `intp_v2_rdt_<pid>` group).
v3.3 needed no change — it was correctly cgroup-scoped all along.

**Impact on the banked Tier-A 1/3 campaign (results/p2-15metric-xdeploy-1of3,
reports at 0eaa86c):** every v2.1 cell ran cgroup-targeted, so every v2.1
`mbw` value is from the pre-fix chain. Quantified against v3.3 (the correct
scope) on the banked snapshot, per-cell medians:

| workload | v2.1 mbw (median) | v3.3 mbw (median) | ratio |
|---|---|---|---|
| app05_streaming | 17 | 318–340 | ~19x |
| app17_mem_pressure | 6–7 | 119–134 | ~18x |
| app11_sort_net | 1–2 | 25–49 | ~20x |
| app01_ml_llc | 2 | 24–35 | ~13x |
| app13_query_scan | 1 | 12–16 | ~13x |
| app10_search / app16 | 0 | 0–6 | — |

The discrepancy is structural (likely a partial uncore-box read on this
host), not a small background bias — the banked v2.1 mbw column supports NO
absolute, ratio, or cross-variant claim. llcocc is NOT affected in the banked
data (pre-fix mbw never claimed a resctrl group, so no RMID clash occurred);
all other columns are untouched. vm-guest v2.1 is unaffected (mbw is
structurally `--` in-guest). D11's "v3.3 mbw over-read vs v2.1" reading
inverts: v3.3 was right.

**Decision: targeted re-run, not annotation.** Re-collect v2.1 x 5 host-side
envs x 7 workloads x 12 reps (420 cells, ~14 h) into the SAME campaign dir,
replacing the v2.1 cells wholesale (replacing only the mbw column would mix
runs). v3.3 cells stay banked. Gate the re-run on a post-sync D12 smoke on
the testbed (idle-cgroup mbw=0; app05 cgroup mbw high WITH llcocc concurrent
— the D12 verification pair) after rebuilding the v2.1 binary there.

**Open question to settle BEFORE the re-run — the mbw ceiling.** v3.3
medians >100 (app05 ~320) mean the detected host ceiling (42 656 MB/s per
the campaign log) is ~6x below the machine's achievable bandwidth, so mbw%
saturates/clamps and loses dynamic range exactly where the metric matters;
in-guest detection on the same box derives 281 600 MB/s. Audit
intp-detect.sh's derivation (and the v2.1/v3.3 normalize+clamp paths) and
either fix the ceiling source or re-derive it empirically (STREAM peak)
before spending the 14 h — otherwise the re-run inherits a saturated scale.

W5 dodged this: the colocation campaign was aborted pre-data (its v2.1
victim-scoped mbw under a noisy neighbour would have been system-wide =
victim+aggressor — the worst case of this bug). W5 relaunch is gated on the
same D12 sync + smoke.

**C34 addendum — ceiling audit closed; re-run launched (2026-06-12).** The
42 656 MB/s ceiling in the banked campaign was intp-detect.sh's hard-coded
DDR4-fallback, captured into the campaign's capabilities.env when the
dmidecode path failed at campaign time. A fresh detect on the testbed now
derives the correct 281 600 MB/s (4400 MT/s x 64 bit x 8 channels from 16
DIMMs), and the campaign dir's capabilities.env already carries it (refreshed
by the aborted W5 attempt's detect stage), so new runs in that dir inherit
the right scale with no code change. Consequence for the BANKED v3.3 mbw
column: values were normalized against the low fallback -> multiply by
42 656/281 600 ~= 0.151 for absolute claims (app05 "320" ~= 48 %); env-vs-bare
ratios within v3.3 are unaffected (the ceiling cancels). The D12 smoke passed
both gates on the rebuilt v2.1 (idle cgroup mbw=0; heavy stream cgroup
mbw=30 with llcocc=86-96 concurrently), and the 420-cell targeted v2.1
re-run (5 host envs x 7 workloads x 12 reps, ~18 h) is running into the
campaign dir; vm-guest v2.1 and all v3.3 cells stay banked.

**C34 closure — re-run done + merged (2026-06-13).** The 420-cell re-run
finished clean (DONE 13:08, ~17 h). It was folded into the canonical campaign
by `bench/merge-and-render-p2.sh`, which keeps a three-folder contract: the
previous run is archived untouched as `...-prerun-banked` (base of truth), the
fresh pull lands in `...-rerun`, and the canonical `...-xdeploy-1of3` is
rebuilt as base + only the 5 host-env v2.1 subtrees overlaid from the re-run.
An integrity diff confirmed that outside the re-run scope the merged tree is
byte-identical to the fresh pull (v3.3 everywhere + vm-guest/v2.1 -> no drift).
The scope fix is visible end-to-end: v2.1 `app05_streaming` mbw moved 17 ->
33 (matching the D12 smoke's heavy-stream 30, and within ~1.5x of the banked
v3.3 ~320 once that is rescaled by 0.151 to ~48 on the audited ceiling) -- the
old ~19x v2.1/v3.3 gap is gone. Reports were regenerated (the v2.1-mbw-INVALID
caveat dropped; a smaller ceiling note retained for the v3.3 absolute
asymmetry), and the figure set re-rendered (`C34_INVALID` is now empty -> the
crimson hatch/borders are gone). Next: W5 relaunch -- now unblocked on the D12
sync and running the correctly-scoped v2.1 binary.

### C35 — Paper 1 CI + vocabulary directive ported to the P2 figure set (2026-08-11)

**Upstream sync.** `upstream/main` (ggrv-intp) carried one novelty over the
fork's `main`, `66a419a` (campaign stages + veth workloads in bench/OVERVIEW.md
and a READER-MAP entry); the camera-ready plot/style work was already on this
branch via `8825e81`. `main` fast-forwarded, then merged here. One conflict, in
`variants/v3.2-ebpf-core/src/intp_agg.c` and so outside the bench/plot + docs
envelope the merge policy anticipated: the feat side had rewritten
`emit_tsv_header()` to emit the 6 portable trailing columns (`a495e0a`), while
main still held the pre-portable form of the same block. Resolved to the feat
side wholesale. Nothing was lost: main's only real edit to that file was the
section retarget to `docs/V3-OVERHEAD-FINDINGS.md 3`, which this branch had
already applied independently in `3b02996`, so the resolved file is identical to
the feat side and no stale `paper IV-E` reference survives.

**Directive source.** `0611429` (fig11 in-plot title -> "interference
discrimination index (IDI)"), `5704125` (95 % bootstrap CI on fig11, rep-level
primary with the unit-level method retained as artifact, N=10000, seed
20260607, percentile method -> asymmetric), `9795c5b` (CI tag reworded to
"rep-level 95%").

**What was ported.** New `bench/plot/p2_ci.py` carries the convention once
(same N, seed and percentile method as fig11) so every P2 aggregate means the
same thing: `rep_ci()` for a mean over reps, `ratio_ci()` for F9's
median-based percent displacement, which resamples the baseline and arm reps
independently because they are separate runs. Applied to:

- **F13 scheduling** (`plot-iada-sim.py`): both panels moved from population SD
  whiskers to the 95 % rep-level bootstrap CI; bar heights are unchanged to
  full precision, since the point estimate is still the plain sample mean.
- **F9** (`analyze-cadence-overhead.py`): every point gained an asymmetric CI
  whisker. `ci_lo`/`ci_hi` are APPENDED to `overhead-vs-cadence.tsv`; columns
  1-8 re-render byte-identical to the banked TSV.
- **F4/F5** (`plot-p2-15metric.py`): the bare `membw_est` column name in axis
  labels and the F4 title now reads "estimated memory bandwidth", with the
  column token kept parenthetically so the figure stays traceable to the TSV.

**Judgment calls.**

1. *The two IDIs are not the same quantity.* `0611429` renamed fig11 precisely
   because the profiler-side interference DISCRIMINATION index collided with
   IADA's response-time interference DEGRADATION index. F13 plots the latter,
   so applying the fig11 wording literally would have asserted something false.
   The word is spelled out and the docstring states the distinction; only the
   internal `idi_avg` token was removed.
2. *F13 states its own n.* Its input is a CloudSim simulator run
   (`run-tier-sim-reps.sh`, default `REPS=5`), not a measurement campaign, so
   the CI rests on 5 reps where fig11's rested on 12. A percentile CI over 5
   points is coarse, so the title carries `n=5 sim reps`, read from the data
   rather than hardcoded. Chased a suspected 4-rep default and did not find one
   anywhere in the IADA path: `run-tier-sim-reps.sh` defaults `REPS=5` (and the
   banked TSV holds exactly 5 rows per tier); on the training side
   `bench/iada/scripts/eval-tiers.R` defaults `K <- 5L` for the within-env
   k-fold CV behind the F13 tables, which `docs/reports/p2-iada-tiers.md`
   independently records as "within-env 5-fold CV"; and the CloudSimInterference
   fork's SA driver (`Placement.java`) uses `epoch = 10`. The only literal 4 in
   that tree is `args[4]`, a CLI argument position. The number is 5 on both the
   simulation and the training axis.
3. *F6 `psp` and F11 `mbw` were left alone*: both are already glossed in place
   for a reader, so rewording would have added length without adding clarity.

**Not done, and why.** The typography half of the directive (`paper_style.apply`
plus the printed-width `save()` path) was NOT applied. `paper_style` sizes text
against an exact printed column width and `PAPER_FIGURES` is keyed by Paper 1
stems only, so `spec_for()` returns None for every F-numbered figure, and
`qa_fig_fonts.py` iterates that same registry rather than the directory it is
pointed at -- pointing it at the P2 figures reports Paper 1 stems MISSING and
checks nothing. Registering P2 specs means choosing each figure's printed width,
which is a Paper 2 LaTeX-geometry decision that does not exist yet. Applying the
7 pt floors to figures still sized for a slide would also have shrunk the text
relative to the canvas and broken the deck geometry the current renders feed.
Paper 1 itself gates this behind `--camera-ready`; the same opt-in should be
added for P2 once the target venue's column width is known.

**Verification.** Pre-edit and post-edit renders were compared in one
environment: 15 of 19 figures byte-identical, 4 changed and all 4 intended.
Aspect drift max 2.3 % (F9, from a third title line), the rest at or under
0.1 %, so the seminar deck geometry survives the swap. `pytest bench/plot/tests`
green (17 passed, 24 subtests); all six analyzers still import.

### C36 — P5's "v2.1 correctly emits `--`" falsified: v2.1 vm-guest `llcocc` is a live proxy, not a gap (2026-09-16)

**Continues the P5/C26 thread (line 664-676, C26 line 742).** P5's plan text
reads: *"mbw/llcocc remain STRUCTURALLY unavailable in a stock KVM guest...
recorded with an availability status distinct from `missing`... BLOCKER to fix
before any vm-guest data is trusted: v3.3 reportedly emits silent zeros for
mbw/llcocc/llcmr in an RDT-less guest instead of `--`... the exact 'do not
fake it' violation the brief forbids (v2.1 correctly emits `--`)."* C26 later
validated the v3.3 half of this ("v3.3 `--`-not-`0` (P5) ✓"). **The v2.1 half
was never independently re-checked against the final campaign data, and it is
false.**

**Finding.** `llcocc`'s backend registry in v2.1 (`variants/v2.1-c-abi-cgroup/
src/llcocc.c:130-142`) falls back `resctrl -> proxy_from_miss_ratio`. In a KVM
guest (no resctrl), v2.1 does not emit `--` for `llcocc` — it silently emits a
value derived from `llcmr` via the proxy backend. `v3.3` has no such fallback
and correctly emits `--`. This is detectable, not guesswork: every `v2.1`
`portable.tsv` header carries the backend registry verbatim (`# v2 backends:
... llcocc=proxy_from_miss_ratio ...` in `vm-guest`, vs `llcocc=resctrl`
everywhere else), and the actual data columns confirm it — a full scan of
every `portable.tsv` under `results/p2-15metric-xdeploy-1of3{,-w5}`,
`results/p2-tierb`, `results/p2-tierc` (all envs × both variants) finds
exactly one (variant, env, metric) triple with this property:
`v2.1 × vm-guest × llcocc = PROXY`, deterministic across every workload and
repetition sampled. `mbw` (`mbw=none` in the same header line) has no such
fallback and correctly stays `--` in v2.1 too — only `llcocc` is proxied.

Downstream, this silently inflated `avail_frac`/median columns in three
already-banked artifacts: `cross-deployment.tsv` (v2.1 vm-guest `llcocc` has
5/5 workload rows with real, often-significant deltas, e.g. app11_sort_net
78.0->1.0, `**bare_median=78, env_median=1.0, cliffs_delta=-1.0, ***`), the
w5-victim-delta counterpart (5/5 workload rows), and `p2-tierb`/
`p2-realapps-combined`'s `fingerprints.tsv` (all 5 real apps, `avail_frac=1`).
Where v3.3 correctly goes blind (0/5, 0/5 rows respectively), v2.1 reports —
a genuinely interesting asymmetry (v2.1 has a directional fallback where v3.3
has none) worth keeping visible, not a defect to silently patch away.

**Fix (analysis-layer only — no hardware re-run, no C-backend change).**
- `bench/intp_metrics.py`: new `parse_backend_status(path)`, reading the
  `#`-comment backend-registry line(s) of a `portable.tsv`/`profiler.tsv` and
  classifying each metric `OK`/`PROXY`/`UNAVAILABLE`. The **data column is
  authoritative** for OK-vs-UNAVAILABLE, not the declared backend string —
  v3.3's header declares `llcocc:resctrl[mon_group]` even inside a vm-guest
  where every row is `--` (the declaration names the *attempted* source, not
  a guarantee it produced data); the declared string is trusted only to
  detect an explicit `proxy` fallback.
- `bench/analyze-cross-deployment.py`: new `--tag-status` flag (both the
  cross-deployment and `--w5` modes) appends a `status` column, writing
  `cross-deployment-tagged.tsv` / `w5-victim-delta-tagged.tsv` alongside the
  originals (parallel outputs, per the brief — the banked files are
  untouched). Row counts are byte-identical (711 / 421 lines incl. header);
  only the new trailing column is added.
- `bench/analyze-tierb.py`: same `--tag-status` flag, same convention, for
  `results/p2-tierb` and `results/p2-tierc` (`p2-realapps-combined/
  fingerprints.tsv` is their straight concatenation — confirmed byte-for-byte
  — so the tagged combined file is assembled the same way).
- Five figures regenerated with a third, distinct visual mark for PROXY cells
  (never conflated with either "available" or "structurally unavailable"):
  **Fig 1** (`fig:availability`, `plot-fig2-3-4-6-8-jsa.py`) — third hatch
  (`"...."`, vs `"////"` for unavailable); **Fig 3** (`fig:claimclass`, same
  file) — hatch overlay on the claim-class cell; **Fig 12** (`fig:vmproxy`,
  `plot-fig11-fig12-jsa.py`) — third bar hatch, was previously showing v2.1's
  proxied `llcocc` bar identically to a genuine RDT reading; **Fig 13**
  (`fig:victim`, same file) — a colored ring around the marker, composable
  with the existing saturation ring; **Fig 14** (`fig:fingerprint`,
  `plot-tierb-fingerprint.py`) — a small triangle marker in the cell corner
  (imshow cells can't carry a `Rectangle`-style hatch). All five keep full
  backward compatibility (`--tag-status` off / no `status` column -> identical
  output to before this change; verified byte-reproducible for the no-flag
  path). `pytest bench/plot/tests`: 42 passed / 158 subtests, no regressions.
- **Checked, not changed:** Fig 8 (`fig:w4faith`) and Fig 10 (`fig:preempt`)
  plot `cpu`/`llcmr` and `psp` respectively — the full-campaign scan above
  confirms PROXY never occurs for any metric other than `llcocc`, so these
  two figures have nothing to mark. Fig 11 (`fig:anomaly`) does include
  `llcocc` among its per-env Kruskal-Wallis panels, but its design point is
  the unrelated, already-fixed T3/P7 container-attribution bug (root
  `mon_group` fallthrough), and its box/violin panel layout has no clean
  hatch-equivalent for a single proxied env among several — left as a
  follow-up if the maintainer wants it, not silently dropped.

**Incidental finding (out of scope, flagged not chased):** building the
per-rep status scan surfaced that `schedthr` in `container-lxc` (both
variants) flickers between a real `0` reading and `--` **within the same
cell**, sometimes within the same rep — 18 such disagreements logged across
the two 15-metric campaigns, all confined to `container-lxc`. This looks like
intermittent CFS-throttle read flakiness specific to that runtime, distinct
from the deterministic RDT/proxy story above (which never disagrees across
reps). Not investigated further here — out of scope for this pass, but worth
a dedicated look before `schedthr` claims are tightened for `container-lxc`.

**Not a repo fix:** the C backend's `resctrl -> proxy_from_miss_ratio`
fallback itself is untouched — changing it would require re-measuring, which
is out of scope for this pass (see `jsa-repo-fix-brief.md` Phase 1 framing).
This entry is about correctly *labeling* data already collected.

### C37 — vm-guest `cpu` ratio hypothesis: host/guest CPU-count denominator mismatch, checked (2026-09-16)

**Finding.** Guest `cpu` ratios of 1.45-3.35x (vs bare) line up almost exactly
with 48 host logical threads / 16 guest vCPUs = 3.0x (the banked one-third
footprint; `bench_cpus=16` confirmed in a live vm-guest `run.json`) and 48/32
= 1.5x (the superseded two-thirds-footprint run). Hypothesis: the host's
`cpu` reading normalizes to the full 48 physical threads while the guest's
normalizes to its own 16 vCPUs, so identical absolute work reads ~3x higher
inside the guest — a denominator mismatch, not a fidelity defect.

**Checked (no rerun).** New `results/p2-15metric-xdeploy-1of3/vm-cpu-
renormalized.tsv`, additive to the existing ratio column (raw ratio kept,
`ratio_renormalized = ratio_raw * 16/48` added alongside, both auditable):

| workload | variant | ratio_raw | in 0.8-1.25? | ratio_renorm | in 0.8-1.25? |
|---|---|---|---|---|---|
| app01_ml_llc | v2.1 | 3.351 | no | 1.117 | **yes** |
| app05_streaming | v2.1 | 3.000 | no | 1.000 | **yes** |
| app10_search | v2.1/v3.3 | 3.030 | no | 1.010 | **yes** |
| app11_sort_net | v2.1/v3.3 | 3.030 | no | 1.010 | **yes** |
| app01_ml_llc | v3.3 | 3.237 | no | 1.079 | **yes** |
| app13_query_scan | v2.1 | 1.000 | yes | 0.333 | no |
| app05_streaming | v3.3 | 1.700 | no | 0.567 | no |
| app13_query_scan | v3.3 | 1.500 | no | 0.500 | no |

Raw: 1/10 cells inside the 0.8-1.25 corridor. Renormalized: **7/10**. The
hypothesis collapses the ratio cleanly for every workload with meaningful CPU
load (>=18% bare-metal `cpu`); the two `app13_query_scan` rows (2-3% bare
`cpu` — the disk workload, essentially idle on this metric) and
`app05_streaming`/v3.3 (an existing outlier elsewhere in this campaign, not
reproduced by v2.1 on the same workload) don't fully collapse — most likely
noise dominating at low absolute utilization rather than a falsification,
but this is disclosed, not asserted.

**Disposition:** the hypothesis is checked and substantially confirmed, not
proven for every cell. Goes to `PAPER-SYNC.md` as a caveat sentence
regardless of the residual 3 cells — per the brief, the paper needs to
disclose the hypothesis and what was checked either way.

### C38 — v2.1 scheduler metrics read one thread per process; v2.1 RDT enrollment skipped nested cgroups (2026-09-28)

**Status: fixed, not re-measured** (release `v0.2.1`, D16). T1 and T2 pass on
the development host; T3, the v2.1/v3.3 agreement leg and the re-run below are
pending on the testbed.

Two v2.1 defects found while grading the v0.2.0 real-application tiers
(`docs/reports/p2-tierb-15metric.md`, `p2-tierc-15metric.md`). Both only affect
**v2.1 on the compose-based suites** (Tier B `app18`–`app21`, Tier C `app22`);
v3.3 and the stress-ng spine are unaffected.

**F1 — `schedlat` and `psp` counted only the thread-group leader.**
`portable.c` summed field 2 of `/proc/<pid>/schedstat` and
`nonvoluntary_ctxt_switches` of `/proc/<pid>/status` over the TGIDs in
`cgroup.procs`. Both files describe one `task_struct`, not the thread group
(`fs/proc/base.c` `proc_pid_schedstat()` prints `task->sched_info.run_delay`;
`fs/proc/array.c` `task_context_switch_counts()` prints `p->nvcsw`/`p->nivcsw`),
so the worker threads of a multi-threaded server were never counted. Bare-metal
medians in v0.2.0:

| Workload | Metric | v2.1 | v3.3 |
|---|---|---|---|
| web-search | `schedlat` | 0 | 97.5 |
| web-search | `psp` | 0 | 7425 |
| in-memory-analytics | `psp` | 0 | 849 |
| DeathStarBench | `psp` | 166 | 9901 |
| Redis (single-threaded) | `psp` | 7 | 7 |

The spine is unaffected: stress-ng workers are separate processes, and the
v2.1/v3.3 cadence rows agree. A second defect sat in the same functions: the
interval delta was `cur >= prev ? cur - prev : 0` over a SUM of per-task
counters, so one exiting task made the sum drop and zeroed the whole interval.

**F2 — v2.1 resctrl enrollment did not descend into child cgroups.**
`resctrl_rescan_cgroup()` read `cgroup.procs` non-recursively. The compose
suites target a parent systemd slice (`bench/run-intp-bench.sh`, C33) whose own
`cgroup.procs` is empty under the cgroup v2 no-internal-processes rule, so the
shared mon_group (D12) never received a task. v2.1 `mbw` and `llcocc` read 0 on
bare metal and in containers for data-caching, web-search, in-memory-analytics
and DeathStarBench, where v3.3 (recursive since C24) reads 4–7 (`mbw`) and
51–92 (`llcocc`). Redis, a single container, was non-zero under both. D15 item 3
stated that the harness targets leaf cgroups; that holds for the spine only.

**Fix.**
- `schedlat` (schedstat backend) and `psp` enumerate TIDs: `cgroup.threads`
  over the cgroup subtree (`procutil_read_cgroup_threads_rec()`, same traversal
  and dot-dir handling as `procutil_read_cgroup_procs_rec()`), or
  `/proc/<pid>/task` for a `--pids` target. Each thread is read at
  `/proc/<tid>/task/<tid>/{schedstat,status}`.
- A per-TID baseline map replaces the delta over a sum: a known TID contributes
  `cur - prev` (clamped at 0 per TID, for TID reuse); a TID new in this interval
  contributes `cur`, since it was born inside the interval. The map is seeded
  at `init()`, so this only applies to threads born mid-run. An exited TID drops
  out, and its last partial interval is lost. A thread born and exited between
  two samples is never seen, which a `/proc` sampler cannot avoid; v3.3 sees it
  through `sched_switch`.
- Normalization is unchanged: `schedlat` = Σ per-thread wait ÷ (interval ×
  online CPUs) × 100, the v3.3 scale; `psp` = Σ per-thread involuntary switches
  ÷ interval.
- The TID set is capped at `INTP_MAX_TIDS` (16384). When the cap is hit, both
  metrics report status `degraded` with note `tid_cap` instead of silently
  truncating.
- `resctrl_rescan_cgroup()` reads the subtree recursively, and
  `resctrl_target_group_acquire()` enrolls immediately when a cgroup target
  starts with no PIDs, so the first samples do not read an empty group. Every
  TID is still written (the existing `/proc/<pid>/task` walk).
- `v2-c-abi` gets the same per-TID `schedlat` for `--pids` targets (it has no
  cgroup target and no `psp`). No published data depends on v2.

**Tests** (`variants/v2.1-c-abi-cgroup/tests/`, `make integration-tests`):
- unit: `test-procutil` covers the `cgroup.threads` recursion and the
  `/proc/<pid>/task` expansion;
- T1 `t1-multithreaded-target.sh`: `tests/helpers/mt_spin` (sleeping leader,
  spinning workers pinned to fewer CPUs). On a 20-CPU development host
  (kernel 7.0, unprivileged, systemd user scope), 8 threads on 2 CPUs: fixed
  v2.1 `schedlat` 30.0 and `psp` ≈ 699/s on both the cgroup and the `--pids`
  target; the v0.2.0 binary reads 0 and 0. 30.0 is the expected value: 6
  threads always waiting out of 20 CPUs. The v2.1/v3.3 agreement leg (ratio 0.5 to 2)
  needs root and runs on the testbed.
- T2 `t2-thread-churn.sh`: every worker is replaced every 100 ms. No interval
  collapses to 0 (`psp` 15–43/s, `schedlat` 0.50–1.10 % on the development
  host) and none shows an underflow spike. The level is low because threads
  that live less than one interval are mostly unseen (see above).
- T3 `t3-nested-slice.sh`: parent cgroup with no processes, cache-heavy
  stress-ng in two children, `llcocc`/`mbw` must be non-zero and within the W4
  band (0.8–1.25) of v3.3. Needs root, resctrl and stress-ng, and is run on the
  testbed against the v0.2.0 binary first: if that binary is NOT 0 there, F2 is
  not the cause and the re-run below shrinks to F1.

**Cost.** Per-TID reads add syscalls on thread-heavy targets. On the
development host, profiling a 501-thread `mt_spin` for 10 s with
`--portable-metrics` cost 0.07 s CPU (0.01 user + 0.06 sys, ≈0.7 % of one
core), against ≈0 for the leader-only reader. The published ≤2.5 % budget was
measured on the spine and is not re-claimed for thread-heavy targets; the
testbed measurement on the CPU reference is still to be done.

**Re-run scope (pending on the testbed).** v2.1 only, Tier B (`app18`–`app21`)
and Tier C (`app22`), environments `bare`, `container`, `vm-guest`, 12 reps ×
120 s, same configuration as v0.2.0: 180 cells. v3.3 cells are reused. Fresh
result dirs `04-tier-b-realapps-v021`, `05-tier-c-dsb-v021`; the v0.2.0 trees
are kept as provenance. Gates:
- (a) v2.1 `schedlat`/`psp` on web-search, in-memory-analytics and DeathStarBench
  are of the same order as v3.3;
- (b) v2.1 `mbw`/`llcocc` on the compose suites are non-zero on the host
  environments;
- (c) canonical `cpu`, `llcmr`, `blk`, `netp`, `nets` medians move by less than
  the run-to-run IQR relative to v0.2.0;
- (d) the F12 class-activation table for v2.1, before and after.

Spine sanity check: 1 cell per environment for `app01` and `app16` with the
fixed v2.1; `schedlat`/`psp` must stay within the cadence-sweep tolerance of
v0.2.0. Before/after numbers: _to be filled after the re-run_.

Also corrected in the same change (comments and docs): `psp` is not Volpert's
PSP, which counts switches to PID 0 as a throttling indicator (that role is
`schedthr`'s); `schedthr` reads 0, not `--`, without a `cpu.max` limit and is
non-hierarchical; `idle_preempt` is an idle-CPU takeover rate; the docs now
list all 8 portable and regime columns.

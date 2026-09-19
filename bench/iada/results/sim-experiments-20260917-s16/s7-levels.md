# S7 task 1 — audit of the regime level counts "71/409/0"

Date: 2026-09-19. Tool: `bench/iada/scripts/analyze-regime-levels.R` (the S8 audit
script, rerun unchanged) against the psp-keyed tier B R folder
(`/home/saccilotto/iada-tier-rda/B`, the folder the simulator actually reads) and the
current canonical 28-trace tier B tree
(`paper-assets/deliverables/data/inputs-iada-trees-20260916/tree-B-vm-guest`,
reached through a symlink shim `/tmp/s7-tree-shim` so the script's tree glob matches;
no file modified).

## What the three counts are

They are **sample counts per severity level**: the number of trace rows (sampling
intervals) that (i) the tier B SVM classifies as `regime` and (ii) the regime k-means
model assigns to each of the three severity levels low/mod/hig, when the three
centroids are ordered on the `psp` column (col 14, the S8 re-key) instead of the
saturated `schedlat` column (col 8). The levels map to the regime multipliers
1.20 (low), 1.55 (mod), 1.95 (hig), so a zero in the third position means the highest
multiplier is never applied to any classified-regime row.

## Script output on the current canonical tree (2026-09-19 rerun)

```
regime centroids on the two candidate level columns:
  schedlat    psp
1      100 5184.7
2      100 5293.8
3      5365.6   <- (psp ordering: 5184.7 < 5293.8 < 5365.6)
cluster sizes: 175 299 2406

SVM class distribution over 3360 trace rows:
  cpu 784, mem 1439, disk 1, net 480, cache 176, regime 480

regime rows: 480
levels keyed on schedlat (col 8, shipped -- tie-break artifacts):
  low 32, mod 211, hig 237
levels keyed on psp (col 14, S8):
  low 31, mod 449, hig 0
```

(Full raw output: `/tmp/s7-levels-raw.txt`; the schedlat column of every centroid is
exactly 100, the stressor saturation that made the shipped schedlat-keyed levels
tie-break artifacts.)

## Reconciliation with the banked "71/409/0"

The banked counts (DECISIONS S8 entry, 2026-08-12) came from the August `/tmp`
campaign tree; the regime-row total is identical (480 of 3360 rows), so the SVM
agrees exactly on *which* rows are regime, but the low/mod split differs on the
current canonical tree (regenerated 2026-09-16 with the fixed
`generate-iada-tree.py` median-merge path): **31/449/0 on the current tree versus
71/409/0 banked**. The load-bearing fact is identical in both: **hig = 0**.

## Independent in-simulation cross-check (same build, same tree)

From the S3 class-confusion campaign on this exact toolchain and tree
(`s3-class-log.tsv`, tier B, final interval, 10 reps x 4 oversubscription cloudlets):
all 40 regime classifications are `mod`; none is `hig`. During actual placement
searches the regime class is therefore priced at 1.20 or 1.55 only.

## Conclusion

- The three numbers are per-level counts of regime-classified trace rows
  (low/mod/hig), not centroid values.
- On the current canonical tree the counts are 31/449/0 (banked: 71/409/0 on the
  August tree); in both, the top-level count is 0.
- **The highest regime multiplier (1.95) is never applied**, neither in the offline
  replay nor in any in-simulation classification of this campaign: the oversubscription
  workload is always priced at low or mod severity.

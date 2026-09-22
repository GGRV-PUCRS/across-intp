# W4 faithfulness adjudication — synthetic fixture for test_plot_w4_summary.py

Trims the real report (docs/reports/W4-faithfulness-r2.md) to the three
structures the renderer parses: FAITHFUL ratio cells, the CPU summary lines,
and the Spearman directional-faithfulness lines.

## 1. CPU faithfulness

| env | workload | GT cpu% | v2.1 cpu | v2.1 verdict | v3.3 cpu | v3.3 verdict |
|---|---|---|---|---|---|---|
| bare | app01_ml_llc | 29.0 | 29.0 | FAITHFUL (1.02) [cliff=-0.120 p=0.834] | 28.0 | FAITHFUL (0.96) [cliff=-0.360 p=0.402] |
| container | app07_ordering | 17.2 | 17.0 | FAITHFUL (0.90) [cliff=-1.0 p=0.007] | 16.0 | FAITHFUL (0.93) [cliff=-1.0 p=0.007] |

**CPU summary (good envs, non-idle workloads):**
- v2.1: 20 faithful, 0 under, 0 over
- v3.3: 20 faithful, 0 under, 0 over

**Directional faithfulness (Spearman rank — profiler `llcmr` vs GT across adjudicated cells):**
- v2.1: rho=0.66 (p=3.2e-04, n=25 cells) — directionally FAITHFUL
- v3.3: rho=0.83 (p=3.2e-07, n=25 cells) — directionally FAITHFUL

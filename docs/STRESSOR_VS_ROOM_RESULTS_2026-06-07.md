# Stressor vs Room — cohort analysis

*Same pipeline and cleaning as the plant/no-plant analysis
(`scripts/cohort_stressor_vs_room.py`, reusing `cohort_plant_analysis.py`).
Outputs in `outputs/cohort_stressor_room/`.*

## Period definitions (within-subject)
- **Stressor** = `event_marker` in {`stressor_test_1`, `stressor_test_2`}.
- **Room** = `condition` in {`physical_plants`, `physical_no_plants`} (the two
  room exposures pooled).
- Cleaning, HRV plausibility gating (most wrist-BI HRV is invalid), respiration
  measures, and within-subject normalization are identical to the prior analysis.
- 16 subjects; HRV usable in only 7.

## Results (paired, within-subject: Stressor − Room)

| Measure | n | Stressor | Room | mean diff | Cohen's dz | paired t p | Wilcoxon p | % higher in stressor |
|---|---|---|---|---|---|---|---|---|
| **Respiration rate (bpm)** | 16 | 15.10 | 13.33 | **+1.77** | **0.64** | **0.022** | **0.011** | 87.5% |
| EDA tonic (µS) | 16 | 1.22 | 0.97 | +0.25 | 0.43 | 0.32 | 0.46 | 43.8% |
| Resp. stress index (exp.) | 16 | 0.61 | 0.57 | +0.04 | 0.32 | 0.21 | 0.46 | 50.0% |
| Resp. stress weighted (exp.) | 16 | 0.67 | 0.65 | +0.02 | 0.10 | 0.68 | 0.71 | 43.8% |
| RMSSD (ms, valid HRV only) | 7 | 105.3 | 105.7 | −0.3 | −0.01 | 0.98 | 1.00 | — |

## Interpretation
Unlike plant vs no-plant (which was null), the stressor manipulation produced a
**clear, significant physiological effect**: respiration rate was faster during
the stressor than during the rooms (+1.8 bpm; significant by both paired t and
Wilcoxon; 14 of 16 subjects breathed faster under stress). EDA tonic arousal was
also higher during the stressor (+0.25 µS, medium dz = 0.43) but did not reach
significance in this sample. The experimental respiratory-pattern stress scale
did not separate the periods, and HRV is uninformative (wrist BI; n = 7).

This is also a useful **validity check**: the stressor task did what it was
designed to do (elevate breathing/arousal), which increases confidence that the
recording and cleaning pipeline captures real autonomic change — and, by
contrast, that the null plant vs no-plant result is a true null rather than an
insensitive measure.

## Figures (`outputs/cohort_stressor_room/`)
- `fig1_paired_measures.png` — per-subject paired change (red = higher in stressor).
- `fig2_effect_sizes.png` — within-subject effect sizes (positive = higher in stressor).
- `fig3_pattern_diff_heatmap.png` — respiratory pattern counts, stressor minus room.

## Tables
- `table_stressor_vs_room.csv` — the comparison above.
- `per_subject_period.csv` — per-subject, per-period measures (raw).

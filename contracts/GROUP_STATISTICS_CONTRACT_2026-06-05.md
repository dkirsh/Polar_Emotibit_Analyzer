# GROUP STATISTICS CONTRACT

**Date:** 2026-06-05
**Module:** `backend/app/services/processing/group_statistics.py`
**Status:** ACTIVE
**Merged from:** `Polar_Emotibit_Analyzer_normalized` v2.2.0

---

## Purpose

Repeated-measures and blocked-model statistics for Latin-square experimental
designs. Distinguishes condition effects from visit-order effects while
respecting within-subject dependence.

---

## Normalized Metrics

All statistics operate on these 5 baseline-relative normalized metrics
(produced by `normalization.py`):

| Key | Label | Digits |
|-----|-------|--------|
| `mean_hr_delta_bpm` | HR delta from baseline | 1 |
| `mean_hr_pct_change` | HR percent change from baseline | 2 |
| `mean_eda_delta_us` | EDA tonic delta from baseline | 3 |
| `eda_phasic_delta` | EDA phasic delta from baseline | 4 |
| `ln_rmssd_delta` | log RMSSD delta from baseline | 4 |

---

## Statistical Tests

### 1. Friedman Chi-Square Test
**What it tests:** Non-parametric repeated-measures ANOVA equivalent.
Within-subject omnibus test for differences across conditions or visits.

**Input requirements:**
- Complete-case only: subjects missing any level are dropped
- Minimum 3 subjects with complete data
- Minimum 2 factor levels

**Output:**
```json
{
  "levels": ["A", "B", "C", "D"],
  "n_subjects_complete": 8,
  "statistic": 12.3,
  "p": 0.006
}
```

**Returns `None`** when insufficient subjects or levels.

### 2. Pairwise Wilcoxon Signed-Rank Tests
**What it tests:** Post-hoc pairwise comparisons between all pairs of levels.

**Correction:** Holm-Bonferroni step-down procedure (`p_holm`).

**Input requirements:**
- Minimum 3 subjects with data for both levels in a pair
- Only run when Friedman is significant (called conditionally)

**Output per pair:**
```json
{
  "left": "A", "right": "B",
  "n": 8,
  "mean_diff": 2.3,
  "statistic": 3.0,
  "p_raw": 0.012,
  "p_holm": 0.036
}
```

### 3. Blocked Partial F-Test Model
**What it tests:** Linear model that separates condition effects from
visit-order effects, controlling for subject random effects.

**Model structure:**
- Reduced model (subject only): `y ~ subject`
- Add visit: `y ~ subject + visit`
- Add condition: `y ~ subject + condition`
- Full model: `y ~ subject + visit + condition`

**Four partial F-tests computed:**
1. `visit_given_subject`: visit effect after controlling for subject
2. `condition_given_subject`: condition effect after controlling for subject
3. `condition_given_subject_and_visit`: condition effect after controlling for subject AND visit order
4. `visit_given_subject_and_condition`: visit effect after controlling for subject AND condition

**Minimum 12 rows required** (too few observations otherwise cause rank-deficient matrices).

**Output:**
```json
{
  "n_rows": 32,
  "visit_given_subject": {"df_num": 3, "df_den": 20, "f_statistic": 5.2, "p": 0.008},
  "condition_given_subject": {"df_num": 3, "df_den": 20, "f_statistic": 1.1, "p": 0.37},
  "condition_given_subject_and_visit": {"df_num": 3, "df_den": 17, "f_statistic": 0.9, "p": 0.46},
  "visit_given_subject_and_condition": {"df_num": 3, "df_den": 17, "f_statistic": 4.8, "p": 0.013}
}
```

---

## `build_condition_aggregate_inference()` Entry Point

**Input:** List of normalized room rows (each must have `subject_id`, `room_type`, `visit_number`, and the 5 normalized metric fields).

**Output:**
```json
{
  "normalized_metrics": [
    {
      "key": "mean_hr_delta_bpm",
      "label": "HR delta from baseline",
      "digits": 1,
      "condition_friedman": { ... },
      "condition_pairwise_holm": [ ... ],
      "visit_friedman": { ... },
      "visit_pairwise_holm": [ ... ],
      "blocked_model": { ... }
    }
  ],
  "visit_summaries": {
    "mean_hr_delta_bpm": [
      {"visit_number": 1, "n": 8, "mean": 3.2, "sd": 1.1, "min": 1.0, "max": 5.5}
    ]
  }
}
```

---

## Invariants

1. **No data fabrication:** If a metric column is missing, it is skipped entirely
2. **Complete-case analysis:** Friedman and Wilcoxon use only subjects with data for ALL levels
3. **Holm correction is monotone:** Adjusted p-values never decrease as you move from smaller to larger raw p-values
4. **F-test denominator guard:** Returns `None` if denominator df ≤ 0 or MSE ≤ 0 (rank-deficient)
5. **Visit column semantics:** `visit_number` encodes chronological order (1 = first visit, regardless of room type). This is what the Latin-square design requires.

---

## Dependencies

- `scipy.stats`: `friedmanchisquare`, `wilcoxon`, `f.sf`
- `numpy.linalg.lstsq` for blocked model
- `normalization.py`: produces the input metrics

---

## NOT Covered
- Effect size computation (Cohen's d, Kendall's W)
- Mixed-effects / hierarchical models
- Bayesian alternatives (Bayes factor)
- Multiple comparison correction beyond Holm (no FDR/Benjamini-Hochberg)

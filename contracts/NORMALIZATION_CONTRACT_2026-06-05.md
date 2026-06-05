# NORMALIZATION CONTRACT

**Date:** 2026-06-05
**Module:** `backend/app/services/processing/normalization.py`
**Status:** ACTIVE
**Merged from:** `Polar_Emotibit_Analyzer_normalized` v2.2.0

---

## Purpose

Compute within-subject baseline-relative normalized derivatives for
cross-subject and cross-room comparison. Raw values are preserved; normalized
deltas are added alongside them.

---

## Baseline Reference Computation

### Input Requirements
- A cleaned DataFrame with `timestamp_ms` column and at least one of `hr_bpm`, `eda_us`
- Event markers list containing `baseline_onset` and `baseline_offset` codes with valid `utc_ms`

### Invariants
1. `BaselineReference` is computed ONLY when both `baseline_onset` and `baseline_offset` markers are present AND `offset > onset`
2. The baseline window is inclusive: `onset_ms <= timestamp_ms <= offset_ms`
3. Minimum 2 data points must fall within the baseline window; otherwise `None` is returned
4. `mean_hr_bpm`: arithmetic mean of `hr_bpm` values in baseline window
5. `tonic_eda_us`: arithmetic mean of `eda_us` values in baseline window
6. `phasic_eda_index`: mean of absolute first-differences of EDA values
7. `rmssd_ms`: computed via `compute_time_domain_features` on baseline window data

### Failure Modes
- Missing baseline markers → `BaselineReference` is `None` → all deltas are `None`
- Insufficient data in window → same as above
- `compute_time_domain_features` exception → `rmssd_ms` is `None`, other fields still computed

---

## Delta Functions

### `delta_from_baseline(value, baseline)`
- Returns `value - baseline`
- Returns `None` if either input is `None`

### `pct_change_from_baseline(value, baseline)`
- Returns `100 * (value - baseline) / baseline`
- Returns `None` if baseline is zero (within 1e-9)
- Returns `None` if either input is `None`

### `log_delta_from_baseline(value, baseline)`
- Returns `ln(value) - ln(baseline)`
- Returns `None` if either value is ≤ 0
- Returns `None` if either input is `None`

---

## Room Row Normalization

### Fields Added to Each Room Row
| Field | Computation | Type |
|-------|-------------|------|
| `baseline_hr_bpm` | Baseline mean HR | float or None |
| `baseline_eda_tonic_us` | Baseline mean EDA | float or None |
| `baseline_eda_phasic_index` | Baseline phasic index | float or None |
| `baseline_rmssd_ms` | Baseline RMSSD | float or None |
| `mean_hr_delta_bpm` | `room_mean_hr - baseline_hr` | float or None |
| `mean_hr_pct_change` | `100*(room_hr - base_hr)/base_hr` | float or None |
| `mean_eda_delta_us` | `room_eda - baseline_eda` | float or None |
| `eda_phasic_delta` | `room_phasic - baseline_phasic` | float or None |
| `ln_rmssd_delta` | `ln(room_rmssd) - ln(baseline_rmssd)` | float or None |

### Special Cases
- Baseline room row: all deltas set to `0.0` (self-reference)
- No baseline markers present: all delta fields are `None`

---

## Integration Points

1. **room_analysis.py**: `compute_room_stats()` calls `compute_baseline_reference()` once, then `normalize_room_rows()` before returning
2. **exporters.py**: Interval CSV and room comparison CSV include delta columns
3. **group_statistics.py**: Operates on normalized room rows for cross-subject inference

---

## NOT Covered
- Between-session normalization (each session normalized to its own baseline)
- Z-score normalization (we use raw deltas, not standardized scores)
- EDA decomposition beyond first-difference phasic index

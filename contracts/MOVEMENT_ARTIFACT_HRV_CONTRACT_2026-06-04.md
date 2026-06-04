# Movement-Artifact-Aware HRV Contract

**Date**: 2026-06-04
**Module**: `backend/app/services/processing/features.py`
**Function**: `compute_hrv_features_with_accel`

## Purpose

Extends the Lipponen-Tarvainen (2019) ectopic beat correction with
accelerometer-based movement artifact exclusion. RR intervals falling
within movement-flagged epochs are excluded from HRV computation
entirely, because gross body movement contaminates the chest-strap
signal in a way that ectopic correction cannot repair.

## Parameters

| Parameter            | Type    | Default | Description                                          |
|---------------------|---------|---------|------------------------------------------------------|
| `accel_threshold_g` | float   | 1.5     | Accel magnitude above which an epoch is flagged       |
| `epoch_duration_ms` | float   | 1000.0  | Duration of each epoch for magnitude averaging        |

## Threshold Rationale

The default 1.5 g is higher than the EDA motion threshold (0.3 g in
`clean.py`) because cardiac signals from a chest strap are more
motion-resilient than wrist-worn EDA. The threshold is user-configurable
via the `accel_threshold_g` keyword argument.

## Exclusion Rules

1. Accelerometer magnitude is computed as `sqrt(ax² + ay² + az²)`.
2. The recording is divided into epochs of `epoch_duration_ms`.
3. If **any** sample within an epoch has magnitude **strictly greater
   than** `accel_threshold_g`, the entire epoch is flagged.
4. RR intervals whose cumulative timestamp falls within a flagged epoch
   are excluded from HRV computation.
5. Values exactly at the threshold are **not** flagged (strict `>`).

## Output Fields

| Field                       | Type  | Guarantee                                       |
|----------------------------|-------|-------------------------------------------------|
| `rmssd_ms`                 | float | RMSSD of clean RR; 0.0 if < 3 clean RRs remain |
| `sdnn_ms`                  | float | SDNN of clean RR; 0.0 if < 3 clean RRs remain  |
| `mean_hr_bpm`              | float | Mean HR from `hr_bpm` column                    |
| `rr_source`                | str   | Provenance string from `_get_rr_intervals`      |
| `rr_total`                 | int   | Total RR intervals before exclusion              |
| `rr_excluded_movement`     | int   | Count of RR intervals excluded due to movement   |
| `movement_artifact_ratio`  | float | `rr_excluded_movement / rr_total`; 0.0 if none  |

## Backward Compatibility

When no accelerometer columns (`acc_x`, `acc_y`, `acc_z`) are present
in the input DataFrame:
- `rr_excluded_movement` = 0
- `movement_artifact_ratio` = 0.0
- HRV values are computed on all RR intervals (identical to
  `compute_hrv_features`)

This ensures existing callers that do not have accelerometer data
receive the same HRV values as before.

## Edge Cases

| Scenario                     | Behaviour                                              |
|-----------------------------|--------------------------------------------------------|
| All epochs flagged          | Returns `rmssd_ms=0.0`, `sdnn_ms=0.0`, ratio=1.0      |
| < 3 total RR intervals     | Returns zeros, ratio=0.0                                |
| < 2 accel timestamps       | Skips movement filtering, computes HRV on all RRs      |
| NaN in accel columns        | `pd.to_numeric(errors="coerce")` → NaN excluded safely |

## Test Coverage

7 tests in `backend/tests/test_features.py`:
- `test_hrv_accel_no_movement_passes_through_unchanged`
- `test_hrv_accel_movement_spikes_cause_exclusion`
- `test_hrv_accel_exclusion_ratio_is_correct`
- `test_hrv_accel_no_accel_columns_still_works`
- `test_hrv_accel_all_movement_returns_zero_hrv`
- `test_hrv_accel_borderline_threshold`
- `test_hrv_accel_mismatched_lengths`

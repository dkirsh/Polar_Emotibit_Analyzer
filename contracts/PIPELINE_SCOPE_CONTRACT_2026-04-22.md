# Pipeline Scope Contract

**Module**: `app/services/processing/pipeline.py::run_analysis`
**Date**: 2026-04-22
**Status**: In force.

## Scope

`run_analysis` is the end-to-end post-hoc analysis pipeline for the
Polar-EmotiBit Analyzer. It accepts a pre-synchronised pair of Polar
H10 and EmotiBit DataFrames, applies drift correction, merges them
onto a common time axis, extracts time- and frequency-domain HRV
features, EDA features, sync quality metrics, and two exploratory
stress composites, and returns a single Pydantic `AnalysisResponse`
object that carries every downstream field the HTTP surface and the
frontend need.

## Inputs

Two `pandas.DataFrame` objects, in order:

**`emotibit_df`**: at minimum columns `timestamp_ms` (int, milliseconds
since session start) and `eda_us` (float, skin conductance in
microsiemens). Optional columns: `acc_x`, `acc_y`, `acc_z` (float,
gravity-units), `resp_bpm` (float, respiration rate).

**`polar_df`**: at minimum columns `timestamp_ms` (int) and `hr_bpm`
(float). Optional column: `rr_ms` (float, native Polar inter-beat
intervals). When `rr_ms` is present the pipeline is in research-grade
mode; when it is absent the pipeline falls back to arithmetic
RR derivation from `hr_bpm` and flags the reduced accuracy in the
quality-flag stream.

**Minimum preconditions**: `len(polar_df) >= 50` (Kubios user-guide
convention for RMSSD stability); `len(emotibit_df) >= 30`
(≈ 30 s at 1 Hz). Below either threshold `run_analysis` raises
`InsufficientDataError`.

## Outputs

A Pydantic `AnalysisResponse` (schema in
`app/schemas/analysis.py::AnalysisResponse`) carrying:

- `synchronized_samples: int` — row count of the merged DataFrame.
- `drift_slope`, `drift_intercept_ms`, `drift_segments` — piecewise
  linear drift-correction parameters.
- `xcorr_offset_ms: float` — disabled in V2.1; reported as 0.0.
- `feature_summary: FeatureSummary` — all HRV / EDA / stress fields.
- `quality_flags: list[str]` — human-readable conditions raised during
  the run.
- `movement_artifact_ratio: float` — fraction of synced samples with
  accel magnitude above the clean-signal threshold.
- `report_markdown: str` — the legacy markdown summary.
- `non_diagnostic_notice: str` — see
  [`NON_DIAGNOSTIC_CONTRACT_2026-04-22.md`](NON_DIAGNOSTIC_CONTRACT_2026-04-22.md).
- `sync_qc_score`, `sync_qc_band`, `sync_qc_gate`,
  `sync_qc_failure_reasons` — see
  [`SYNC_QC_CONTRACT_2026-04-22.md`](SYNC_QC_CONTRACT_2026-04-22.md).

## Success conditions

1. **HRV reads from raw Polar RR, not the sync-decimated DataFrame.**
   The merge-asof step decimates beat-level RR at normal adult heart
   rates; HRV features therefore run on `corrected_polar`, not on
   `cleaned`. Enforced by
   `tests/test_real_data_audit.py::test_welltory_hrv_matches_ground_truth`.
2. **RMSSD within 1 ms of hand-computed reference on real data.**
   Pipeline RMSSD on Welltory subjects 01 and 05 matches the
   Lipponen-Tarvainen-corrected direct calculation within 1 ms.
   Enforced by the same test.
3. **Honest rr_source labelling.** When `polar_df` lacks an `rr_ms`
   column, `feature_summary.rr_source == "derived_from_bpm"` and the
   quality-flag stream includes the reduced-accuracy warning. Enforced
   by `test_synthetic_input_reports_derived_rr_source`.
4. **Minimum-sample guard.** Input with fewer than 50 beats or fewer
   than 30 EmotiBit samples raises `InsufficientDataError`. Enforced
   by `test_empty_csv_returns_422`,
   `test_below_minimum_beats_returns_422`,
   `test_below_minimum_emotibit_samples_returns_422`.

## Non-promises

- The pipeline does **not** perform movement-artifact-aware HRV
  filtering. Accel-flagged movement epochs are computed but are not
  used to remove RR beats from the HRV calculation.
- The pipeline does **not** normalise features between subjects. All
  outputs are raw units; between-subject comparisons require an
  external normalisation step.
- The pipeline does **not** produce a clinical interpretation of its
  outputs. See the Non-Diagnostic Contract.
- The pipeline does **not** support live streaming; inputs must be
  complete CSVs. GUI scope is file-only per
  `docs/GUI_SCOPE_FILE_ONLY_2026-04-20.md`.

## Test coverage

All pipeline success conditions are exercised by
`backend/tests/test_real_data_audit.py` and
`backend/tests/test_features.py`. Full suite: 25 passing as of
2026-04-22 (see commit `2fdfeba`).

## References

Task Force of the European Society of Cardiology and the North
American Society of Pacing and Electrophysiology. (1996). Heart rate
variability. *Circulation*, 93(5), 1043–1065.
https://doi.org/10.1161/01.CIR.93.5.1043

Chung, V., Chopin, L., Karadayi, J., & Grèzes, J. (2026). Validity of
the Polar H10 for continuous measures of heart rate and heart rate
synchrony analysis. *Sensors*, 26(3), 855.
https://doi.org/10.3390/s26030855

# Sync QC Contract

**Module**: `app/services/processing/sync_qc.py`
**Date**: 2026-04-22
**Status**: In force.

## Scope

The sync-QC module computes a quality gate for the cross-sensor
time-alignment between Polar H10 and EmotiBit signals. Output is a
score, a band, a gate decision, and a list of failure reasons that
the rest of the pipeline reports in the `AnalysisResponse` so a
consumer can decide whether to trust downstream inferences.

The gate exists because sync failures are the highest-leverage error
mode in a two-sensor pipeline: a bad drift-correction fit can
silently corrupt every timeseries and every windowed feature
derived from the merged signal, while leaving the summary statistics
of each individual stream unaffected. The gate flags this before
downstream analysis is read.

## Inputs

Four objects, in order:

- `emotibit_df: pd.DataFrame` — the pre-merge EmotiBit signals.
- `polar_df: pd.DataFrame` — the drift-corrected Polar signals.
- `synced_df: pd.DataFrame` — the post-merge merged DataFrame.
- `drift_model: PiecewiseDriftModel` — the fitted drift model,
  carrying per-segment slope and intercept.

## Outputs

A `SyncQcReport` dataclass with fields:

- `sync_confidence_score: float` — a 0–100 score combining merge
  loss, per-segment drift-slope deviation from 1.0, and motion
  artifact ratio.
- `sync_confidence_band: Literal["green", "yellow", "red"]` — the
  score bucketed into three bands with thresholds documented in the
  module source.
- `sync_confidence_gate: Literal["go", "conditional_go", "no_go"]` —
  the gate decision. Downstream consumers should refuse to render
  quantitative inferences on `no_go`; may render with an explicit
  caveat on `conditional_go`; may render normally on `go`.
- `failure_reasons: list[str]` — per-criterion failure explanations,
  empty on `go`.

## Success conditions

1. **Band consistency.** The band is a pure function of the score:
   green ≥ 85, yellow 60–85, red < 60.
2. **Gate consistency.** The gate is a pure function of the band
   plus the failure reasons: green → `go`, yellow → `conditional_go`
   when all reasons are soft, red → `no_go`.
3. **Deterministic failure reasons.** When the gate is
   `conditional_go` or `no_go`, `failure_reasons` is non-empty and
   names the specific failing criteria; when the gate is `go`,
   `failure_reasons` is empty.

## Non-promises

- The module does **not** re-compute the drift correction. It
  evaluates whatever drift model it is handed.
- The module does **not** auto-correct marginal sync failures; it
  only reports. Any auto-correction logic lives elsewhere.
- The module does **not** depend on either sensor's native sampling
  rate. The gate's thresholds are rate-agnostic.
- The module does **not** gate on respiratory or stress features;
  only on the sync-alignment quality proper.

## Test coverage

`backend/tests/test_features.py` (sync_qc integration path).
End-to-end gate behaviour exercised in the Welltory real-data tests
in `test_real_data_audit.py`.

## References

Internal to this repository. The gate thresholds were set empirically
during the 2026-04-20 integration pass; adjust with care and ship a
new dated contract if the thresholds change.

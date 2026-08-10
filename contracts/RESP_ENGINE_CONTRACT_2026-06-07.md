# Contract — Respiratory engine (RespInPeace) & extended classifier

Modules: `processing/respiratory/_engine/` (vendored RespInPeace),
`respinpeace_engine.py`, `pattern_classifier.py`. Wired in `respiratory/signal.py`
(`from_vernier_respinpeace`) and `respiratory/pipeline.py`.

## Engine (supersedes the legacy peak detector)
- The pipeline's Stage-0 signal now prefers **RespInPeace** (ALS baseline,
  prominence cycle detection, BreathMetrics-style hold detector). On any failure
  it falls back to the legacy `from_vernier` detector — supersession, not
  deletion. `manifest.engine` records which ran (`respinpeace` /
  `legacy_peakdetect` / `recompute`).
- RespInPeace supplies peaks/troughs; the existing `extract_breath_cycles`
  formats them, so the cycle schema is unchanged. A per-cycle `hold_dur_s` is
  added from the hold detector.
- **Run on full-resolution data.** Belt CSVs with second-quantized timestamps
  degrade detection; use the millisecond `.xlsx` (or the raw stream).

## Hold-detector tuning (part B)
Library defaults over-detected (~40% of breaths). Tuned constants in
`respinpeace_engine.py`: `HOLD_MIN_DUR_S = 1.0` (was 0.25), `HOLD_PROMINENCE =
0.12` (was 0.05), `HOLD_MIN_GAP_S = 0.15`. Apnea is a hold ≥ 1.0 s.
**Invariant:** tuned parameters must yield ≤ the hold count of looser parameters
on the same signal (regression-guarded).

## Extended classifier (recalibrated, 11 patterns)
- Thresholds are relative to each subject's **rest baseline** (rest markers, or
  the `phase` column), removing the saturation of fixed cutoffs.
- Patterns: tachypnea, bradypnea, ie_shift, inverted_ie, shallow, irregular,
  sigh, apnea, hyperventilation, breath_stacking, periodic. (Paradoxical
  excluded — needs a second belt.)
- Missing optional inputs (`onset_level`, `hold_dur_s`) disable only their
  dependent patterns; the classifier never raises on a valid cycle table.
- **Differential diagnosticity:** `PATTERN_WEIGHTS` encode that patterns are NOT
  equally stress-diagnostic — irregularity and sighing weighted highest;
  rate/I:E changes lower; voluntary breath-holds lowest. The weighted index uses
  these; the raw count does not. Both are reported.

## Pipeline integration (last mile)
`pipeline.run` attaches `result.extended_patterns` (counts, stress_rate_per100,
weighted_index, weights, n_breaths) additively, and the extended layer is
fail-soft (errors recorded in `extended_patterns_error`, never raised).

## Known liability reconciled
The Estelita `RespInPeace_Output/code/` copy is now SUPERSEDED by the vendored
backend copy (CLAUDE.md note #8). Treat the Estelita copy as archival.

# Changelog

All notable changes to the Polar-EmotiBit Analyzer are recorded here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
version numbers follow [Semantic Versioning](https://semver.org/).

## [2.4.0] — 2026-06-04

Vernier respiration-belt integration and Estelita script fixes.

### Added

- **Vernier respiration-belt parser**: new `vernier_parser.py` module in
  `backend/app/services/ingestion/` that reads Vernier respiration-belt
  `.xlsx` exports with columns: `timestamp_unix`, `force`, plus optional
  `timestamp`, `RR`, `event_marker`, `condition`. Resamples to uniform
  20 Hz grid and runs the RespInPeace ALS baseline removal + cycle
  detection pipeline. Outputs per-breath features (inhale/exhale
  duration, I:E ratio, duty cycle, amplitude, respiratory rate).
- **Validation endpoint**: `POST /api/v1/validate/csv/vernier` — schema
  validation for Vernier Excel files. Returns sample rate, duration,
  conditions, event markers, and vendor RR statistics.
- **Analysis endpoint update**: `POST /api/v1/analyze` now accepts an
  optional `vernier_file` upload. Parsed Vernier data (metadata, event
  markers, respiratory features) is stored alongside the session.
- **Frontend upload slot**: fifth drop-zone on the StartPage for
  Vernier `.xlsx` files. Shows recording duration, sample rate, and
  vendor RR statistics after validation.
- **Ingestion contract**: `contracts/VERNIER_INGESTION_CONTRACT_2026-06-04.md`
  defining accepted formats, output schema, validation rules, error
  codes, API surface, frontend slot specification, and backward
  compatibility guarantee.
- **Vernier test suite**: 23 new tests in `tests/test_vernier_parser.py`
  covering happy path, resampling, event markers, conditions, vendor
  RR, minimal columns, adversarial error handling (empty file, missing
  columns, NaN-heavy, zero-duration, corrupted, single row),
  respiratory feature extraction, mixed-frequency resampling, and HTTP
  endpoint round-trips.

### Fixed

- **Estelita `analyze.py` HERE bug**: `HERE` variable was used before
  definition (on `sys.path.insert`) causing a `NameError` at import
  time. Moved `HERE = os.path.dirname(...)` before its first usage.

## [2.3.0] — 2026-06-04

Movement-artifact-aware HRV and synthetic data fidelity.

### Added

- **Movement-artifact-aware HRV**: new `compute_hrv_features_with_accel`
  function in `features.py`. Extends the Lipponen-Tarvainen (2019) ectopic
  correction with accelerometer cross-checking. When `acc_x`, `acc_y`,
  `acc_z` columns are present, epochs where accelerometer magnitude
  exceeds a configurable threshold (default 1.5 g) are flagged as
  movement artifacts, and RR intervals falling within those epochs are
  excluded from HRV computation. Output includes `rr_total`,
  `rr_excluded_movement`, and `movement_artifact_ratio` fields.
  Backward-compatible: when no accelerometer columns are present,
  behaviour is identical to `compute_hrv_features`.
- **Movement artifact tests**: 7 new tests covering no-movement
  passthrough, movement spike exclusion, ratio computation, all-movement
  adversarial case, borderline threshold, no-accel-columns fallback,
  and mismatched timestamp lengths.
- **Synthetic 15 Hz tests**: 7 new tests verifying exact sample counts
  at 15 Hz for various durations, timestamp spacing, and downstream
  EDA feature validity.

### Fixed

- **Synthetic EDA sampling rate**: `generate_synthetic_session` now
  generates EmotiBit data at 15 Hz (was 1 Hz) to match the real
  EmotiBit hardware sampling rate. Polar HR remains at 1 Hz. Motion
  burst injection scaled to the 15 Hz sample count.

## [2.2.1] — 2026-06-04

Five targeted quick-fixes addressing build metadata, import-time side
effects, script bugs, provenance propagation, and frontend export
robustness. Each fix has a corresponding contract in `contracts/` and
adversarial tests in `backend/tests/test_quickfixes.py`.

### Fixed

- **T1 — pyproject.toml readme path.** The `readme = "README.md"`
  field referenced a file that doesn't exist in `backend/`. Changed
  to inline text form so `pip install -e '.[dev]'` succeeds without
  warnings.

- **T2 — Import-time session_store.json side effect.** Importing the
  analysis router called `_load_store_from_disk()` at module level,
  which could read and rewrite `session_store.json` just from an
  import. Moved to an explicit `init_session_store()` function called
  from a FastAPI `lifespan` startup hook.

- **T3 — Estelita analyze.py `HERE` bug.** `HERE` was used on line 24
  (`sys.path.insert(0, HERE)`) but defined on line 32. Moved the
  definition before the first use.

- **T4 — EDR proxy `rr_source` propagation.** `compute_edr_detailed()`
  discarded the RR source with `rr, _ = _get_rr_intervals(df)`. Now
  captures and propagates `rr_source`, `rr_source_note`, and
  `source_confidence` into the EDR output. When RR is derived from
  BPM, the quality is flagged as `degraded: True` and the verdict is
  capped at "weak".

- **T5 — SVG export `getBBox()` fallback.** The `catch` block after
  `getBBox()` was empty, so SVG exports could lack proper dimensions
  when the element wasn't fully rendered. Added a three-tier fallback:
  existing `viewBox` → `clientWidth`/`offsetHeight` → hardcoded
  920×430 defaults.

### Added

- **Contracts**: five new module-level contracts in `contracts/`:
  `BUILD_METADATA_CONTRACT_2026-06-04.md`,
  `SESSION_STORE_INIT_CONTRACT_2026-06-04.md`,
  `ESTELITA_ANALYZE_CONTRACT_2026-06-04.md`,
  `EDR_RR_PROVENANCE_CONTRACT_2026-06-04.md`,
  `SVG_EXPORT_CONTRACT_2026-06-04.md`.

- **Adversarial tests**: `backend/tests/test_quickfixes.py` with 14
  tests that actively try to break each fix.

## [2.2.0] — 2026-04-22

Kubios-parity pass. Pipeline now reproduces the Kubios HRV Premium
time-domain, Poincaré, and normalised-unit frequency-domain panels
within 1 % of textbook-formula references on real Polar H10 data,
applies the same ectopic correction algorithm (Lipponen-Tarvainen
2019) with cubic-spline interpolation, and exports in all four
formats Kubios ships (CSV, XLSX, MAT, PDF).

### Added

- **Time-domain HRV**: NN50 count and pNN50 percentage (Task Force 1996).
- **Poincaré nonlinear HRV**: SD1, SD2, SD1/SD2 ratio, ellipse area
  (Brennan, Palaniswami & Kamen 2001 closed-form).
- **Normalised-unit frequency-domain HRV**: total power, LF_nu, HF_nu,
  VLF%, LF%, HF% (Task Force 1996 definitions).
- **Ectopic correction**: full Lipponen-Tarvainen (2019) adaptive-
  threshold detector with cubic-spline interpolation, replacing the
  simplified local-median filter.
- **Export endpoint**: `GET /api/v1/sessions/{id}/export?format=…`
  for CSV, XLSX, MAT, PDF. Frontend adds download buttons on the
  results cover page.
- **Stress composite v2**: seven-channel composite using pNN50,
  SD1/SD2 ratio, and LF_nu alongside v1's channels. Emitted alongside
  v1 with per-channel contribution audit. Explicit
  experimental-not-validated caveat preserved.
- **Glossary**: 12 new entries covering NN50, pNN50, SD1, SD2,
  SD1/SD2 ratio, Poincaré ellipse area, total power, LF_nu, HF_nu,
  Lipponen-Tarvainen correction, cubic-spline interpolation, quartile
  deviation. Glossary now renders as hover tooltips in detail-page
  prose.
- **Analytics catalog**: two new entries — normalised-units
  sympathovagal balance; stress v1-vs-v2 comparison panel.
- **Response-model coverage**: all 8 HTTP endpoints now carry an
  OpenAPI response schema (was 1 of 8).
- **Minimum-sample guard**: `/api/v1/analyze` returns HTTP 422 with a
  structured `insufficient_data` reason on sessions with < 50 beats
  or < 30 EmotiBit samples.
- **Regression test suite**: 7 new tests in
  `backend/tests/test_real_data_audit.py` using real Welltory Polar
  H10 fixtures (CC0-1.0).
- **`contracts/` directory**: six module-level contracts — pipeline
  scope, HRV features, stress composite, export formats, sync QC,
  non-diagnostic notice.
- **`docs/README.md`** and **`docs/archive/2026-04-20/README.md`**:
  documentation indices for the live docs and the historical
  working logs.
- **Panel consultation record**: five-expert panel (Thayer, Shaffer,
  Tarvainen, Porges, Lakens) justification of the v2 composite's
  weighting scheme at
  `docs/STRESS_COMPOSITE_V2_PANEL_JUSTIFICATION_2026-04-21.md`.

### Changed

- **HRV feature computation**: now reads from raw drift-corrected
  Polar RR, not from the sync-decimated DataFrame. Fixes a 30 %
  RMSSD bias at normal adult heart rates (F12).
- **Chart palette**: 11 core colours moved from inline hex literals
  to `:root { --chart-* }` CSS custom properties, read at runtime by
  `frontend/src/analytics/chartPalette.ts`. Re-theming now requires
  only a CSS edit.
- **README validation claim**: scoped. Previous wording overstated
  Kubios validation. New wording names three validation states
  separately.
- **Analytics count**: README 21 → 24 (catalogue now has 24 entries).

### Deprecated

- `_filter_ectopic` (legacy local-median filter) kept only as a
  fallback for sessions with < 11 beats, below the Lipponen-
  Tarvainen running-median window minimum.

### Fixed

- **F12 P0 HRV-from-decimated-RR bug** — HRV now reads from raw
  Polar, eliminating a 30 % RMSSD bias on real Welltory data.
- **F1 P0 rr_source mislabel** — pipeline no longer reports
  `rr_source = "native_polar"` when RR was arithmetically derived
  from `hr_bpm`. Resolves as a side effect of F12.
- **F2/F6 P0 empty-CSV → 200** — empty or below-minimum inputs now
  return HTTP 422 with a structured reason instead of 200 with
  `stress_score = 0.5` and NumPy RuntimeWarnings.
- **F4 P1 orphan glossary** — 23-entry glossary now wired as hover
  tooltips on every AnalyticDetailPage prose block (now 35 entries
  with the Kubios-parity additions).
- **F5 P1 NaN guards** — `TimeseriesOverlay` now filters non-finite
  values before SVG path generation.
- **F9 P2 dead chart-kind case** — `phase_comparison` removed from
  the ChartRenderer switch.

## [2.1.0] — 2026-04-20

Path-A integration pass. Six missing backend modules lifted from the
sibling `emotibit_polar_data_system` repo; FastAPI HTTP surface wired
on 8 endpoints; frontend brought to a running dashboard with 21
science-writer-voice analytics; RSA / EDR respiratory channel added
to the stress composite. See `docs/archive/2026-04-20/` for the
full working-log set.

## [2.0.0] — earlier

Initial analyser scaffold. See git history for pre-2026-04-20
commits.

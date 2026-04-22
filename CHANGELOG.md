# Changelog

All notable changes to the Polar-EmotiBit Analyzer are recorded here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
version numbers follow [Semantic Versioning](https://semver.org/).

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

# Contract — Canonical regimented store

Producer: `scripts/regiment_data.py`. Output: a SQLite database plus exported
CSVs (`data/regimented_events.csv`, `data/regimented_sessions.csv`).

## Purpose
Normalise heterogeneous EmotiBit/Polar/marker recordings — which differ in
timestamp units and marker conventions between recorders — into one canonical,
queryable, provenance-bearing store, so every downstream analysis reads one shape
instead of guessing per file.

## Inferred per session (never assumed)
- **Timestamp unit** of each physiological file (ms / ns / µs), by column-name
  hint **and** magnitude check, normalised to UTC milliseconds (`t_ms`).
- **Marker convention**: `onset_offset` (explicit `X_onset`/`X_offset` pairs) or
  `active_until_next` (point markers, each running until the next). Both normalise
  to explicit `(label, onset_ms, offset_ms)` windows.

## Canonical schema
- `session(session_id PK, ingested_at, duration_s, polar_time_unit,
  marker_convention, n_eda, n_rr, n_events, warnings, provenance)`
- `eda_sample(session_id, t_ms, eda_us, acc_x, acc_y, acc_z)`
- `rr_sample(session_id, t_ms, rr_ms, hr_bpm)`
- `event(session_id, label, onset_ms, offset_ms, note)` — the regimented windows.

## Invariants & success conditions
- All `t_ms` and window bounds are UTC milliseconds in one epoch; a session's
  event windows must fall within (or be reported against) its physio time span.
- **No silent drops:** a marker-like column that cannot be interpreted, an
  offset without an onset, or a malformed marker file is recorded in
  `session.warnings`, never dropped quietly.
- **Idempotent:** re-running a session replaces its rows; never duplicates.
- **Provenance:** every session records source filenames, SHA-256, detected
  timestamp unit, and marker convention — the normalisation is auditable and
  reproducible.

## Known data-quality outputs (from the sample run, for the recorder to fix)
- p013, p021, p024: marker files contain only an empty `Unnamed: 0` column →
  flagged `marker_convention=unknown`, 0 windows. These are upstream export
  defects, surfaced rather than hidden.
- p021 also showed an implausible physio duration (~44 h), indicating a stray
  out-of-range timestamp row worth screening.

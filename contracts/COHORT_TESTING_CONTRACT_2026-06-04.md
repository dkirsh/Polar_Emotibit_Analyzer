# Cohort Testing Contract

**Module**: `backend/tests/test_cohort_e2e.py`, `backend/app/services/cohort/partition.py`
**Version**: 1.0
**Date**: 2026-06-04

---

## Purpose

Guarantees that the full analysis pipeline can process multi-subject cohort
data end-to-end, from ZIP archive extraction through per-subject analysis
to cross-subject comparison output.

## Invariants

1. **Failure isolation**: One subject failing must NOT crash the cohort run.
   Each subject is processed in its own try/except and failures are logged.

2. **Per-subject success criteria**: A valid pipeline run produces:
   - Non-null RMSSD and SDNN (time-domain HRV)
   - Non-null tonic EDA (when EmotiBit data is present)
   - No unhandled exceptions

3. **Cross-subject output**: The comparison CSV has one row per subject with
   standardized column schema (subject_id, rmssd_ms, sdnn_ms, mean_hr_bpm,
   tonic_eda_us, etc.).

4. **ZIP structure tolerance**: The system accepts varying naming conventions
   within the Alice ZIP archives.

5. **Room-level analysis**: When Order & Affect files are present, room-level
   windowed analysis runs without error.

## Preconditions

- ZIP archives exist in `data/Alice/`
- Backend venv has all dependencies installed
- Test marked `@pytest.mark.slow` (excluded from fast suite)

## Postconditions

- All non-corrupted subjects produce valid analysis output
- Corrupted/truncated subjects are reported in the failure log
- Cross-subject CSV has correct row count

## Failure Modes

| Condition | Response | Impact |
|-----------|----------|--------|
| Missing ZIP | Test skipped | No crash |
| Corrupted subject CSV | Graceful skip + error in report | Other subjects unaffected |
| Mismatched timestamps | Sync QC flag | Analysis runs with degraded quality |
| Empty Order & Affect | Room analysis skipped | Core HRV/EDA still computed |

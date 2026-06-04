# Vernier Respiration-Belt Ingestion Contract

**Version:** 1.0
**Date:** 2026-06-04
**Status:** Active
**Scope:** Backend parser, validation endpoint, analysis endpoint, frontend upload slot

---

## Accepted File Formats

| Property | Value |
|---|---|
| Format | `.xlsx` (Office Open XML Spreadsheet) |
| Engine | openpyxl (already a backend dependency) |
| Sheet | First sheet (index 0) |
| Header | Row 0 — column names are stripped of leading/trailing whitespace |

## Required Columns

| Column | Type | Description |
|---|---|---|
| `timestamp_unix` | `float` | Unix epoch seconds (e.g., `1700000000.123`) |
| `force` | `float` | Respiratory force sensor reading (arbitrary units) |

## Optional Columns

| Column | Type | Description |
|---|---|---|
| `timestamp` | `datetime` | Human-readable timestamp (used for metadata only) |
| `RR` | `float` | Vendor-computed respiratory rate in BPM (used for validation) |
| `event_marker` | `string` | Experimental phase marker labels |
| `condition` | `string` | Experimental condition labels |

## Output Schema

| Property | Value |
|---|---|
| Target frequency | **20 Hz** uniform grid via `np.interp` |
| Timestamp column | `timestamp_ms` (int, milliseconds from recording start) |
| Force column | `force` (float, resampled from raw) |
| Elapsed column | `elapsed_s` (float, seconds from recording start) |

## Respiratory Processing Pipeline

Mirrors the Estelita RespInPeace standalone scripts:

1. **ALS baseline removal** — `_baseline_als(lam=1e10, p=0.01, niter=10)` identical to `rip.py Resp.baseline_als`
2. **Moving z-score normalization** — 10-second window, matching `rip.py Resp._move_zscore`
3. **Peak/trough detection** — `_peakdetect_simple(lookahead=1, delta=1.0)` matching `peakdetect.py`
4. **Per-breath feature extraction** — inhale/exhale duration, I:E ratio, duty cycle, amplitude

## Validation Rules

| Rule | Threshold | Error |
|---|---|---|
| Min valid samples | ≥ 10 | `"Vernier file has only N rows; need at least 10"` |
| Required columns | `timestamp_unix`, `force` | `"missing required columns: [...]"` |
| Duration | > 0 seconds | `"zero or negative duration"` |
| Valid (non-NaN) samples | ≥ 10 after `isfinite` filter | `"too few valid (non-NaN) timestamp/force samples"` |
| File format | Valid XLSX | `"Could not read Vernier Excel file"` |

## Error Codes

| HTTP Status | Condition |
|---|---|
| `200` | Valid file parsed and validated successfully |
| `400` | Unparseable file (not valid XLSX, unexpected structure) |
| `422` | Schema validation failure (missing columns, insufficient data) |

## API Endpoint Surface

### Validation
```
POST /api/v1/validate/csv/vernier
Content-Type: multipart/form-data
Body: file (UploadFile)

Response: CsvValidationResponse {
  valid: true,
  filename, n_rows, columns_present,
  sample_rate_hz, duration_s, duration_min,
  conditions, n_event_markers, n_resampled,
  vendor_rr_median
}
```

### Analysis
```
POST /api/v1/analyze
Content-Type: multipart/form-data
Body: emotibit_file, polar_file, ...existing fields...,
      vernier_file (Optional[UploadFile])

Response: AnalysisResponse (unchanged schema)
Stored session includes: vernier_data: {
  metadata, event_markers, respiratory_features, n_samples
}
```

## Frontend Upload Slot

| Property | Value |
|---|---|
| Slot label | `"Vernier Respiration Belt XLSX (respiratory force)"` |
| Required | `false` |
| Accept filter | `.csv,.zip,.xlsx` |
| Slot code | `"vn"` (UploadSlot type) |
| File check | Warns if file extension is not `.xlsx`/`.xls` |
| Info display | `"N samples · X.Xmin · 20Hz resampled · vendor RR Y bpm"` |

## Backward Compatibility Guarantee

- The `vernier_file` parameter is **Optional** with default `None`
- All existing 4-file workflows (EmotiBit + Polar + Markers + Order & Affect) are **unchanged**
- The `AnalysisResponse` schema is **unchanged** — Vernier data is stored only in the session store
- The `CsvValidationResponse` adds 7 new optional fields (all `None` by default for other file types)
- No existing test regressions: all 71 pre-existing tests continue to pass

## Test Coverage

| Test Class | Count | Scope |
|---|---|---|
| `TestParseVernierXlsx` | 6 | Core parsing: happy path, 20 Hz resampling, event markers, conditions, vendor RR, minimal columns |
| `TestVernierAdversarial` | 7 | Error handling: empty file, missing columns, NaN-heavy, zero-duration, corrupted, single row |
| `TestRespiratoryFeatures` | 5 | Respiratory processing: sine wave rate accuracy, short signal, per-breath features, I:E ratio, duty cycle |
| `TestParseAndAnalyze` | 2 | End-to-end integration, mixed-frequency resampling |
| `TestVernierValidationEndpoint` | 3 | HTTP round-trip: valid file, invalid file, empty file |
| **Total** | **23** | |

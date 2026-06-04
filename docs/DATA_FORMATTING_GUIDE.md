# Data Formatting Guide

How to prepare your sensor data for the Polar-EmotiBit Analyzer. Each file type has a required schema. Example files are in the `docs/examples/` directory.

---

## 1. EmotiBit CSV (Required)

Electrodermal activity and accelerometer data from an EmotiBit wrist sensor.

### Required columns

| Column | Type | Unit | Description |
|--------|------|------|-------------|
| `timestamp_ms` | integer | milliseconds | Unix epoch timestamp in ms |
| `eda_us` | float | microsiemens (µS) | Tonic skin conductance |

### Optional columns (recommended)

| Column | Type | Unit | Description |
|--------|------|------|-------------|
| `acc_x` | float | g | Accelerometer X-axis |
| `acc_y` | float | g | Accelerometer Y-axis |
| `acc_z` | float | g | Accelerometer Z-axis (≈ 9.8 at rest) |

### Example

```csv
timestamp_ms,eda_us,acc_x,acc_y,acc_z
1715000000000,2.498,-0.012,-0.072,9.865
1715000000066,2.466,-0.073,0.011,9.776
1715000000133,2.604,0.027,-0.101,9.764
```

### Sampling rate

EmotiBit typically samples EDA at **15 Hz** (one row per ~66 ms). Accelerometer data is sampled at the same rate when present.

### Alternative format: Native EmotiBit channels

The analyzer also accepts native EmotiBit per-channel exports (separate files for EA, AX, AY, AZ) with `LocalTimestamp` (Unix seconds, float) instead of `timestamp_ms`. These are auto-detected and merged internally.

---

## 2. Polar H10 CSV (Required)

Heart rate and RR interval data from a Polar H10 chest strap.

### Accepted input modes (in order of preference)

#### Mode A: Raw ECG (best)

| Column | Type | Unit |
|--------|------|------|
| `timestamp_ms` or `timestamp_ns` | integer | ms or ns epoch |
| `ecg_uv` or `ecg_mv` or `ecg` | float | microvolts or millivolts |

HR and RR are derived in-app from the raw ECG trace. This produces the highest quality HRV.

#### Mode B: Native Polar RR (recommended)

| Column | Type | Unit |
|--------|------|------|
| `utc_epoch_ns` | integer | nanoseconds epoch |
| `rr_ms` | float | milliseconds |

Comment lines starting with `#` are automatically skipped.

#### Mode C: Beat-level metrics (fallback)

| Column | Type | Unit | Required? |
|--------|------|------|-----------|
| `timestamp_ms` | integer | ms epoch | **Yes** |
| `hr_bpm` | float | beats per minute | **Yes** |
| `rr_ms` | float | milliseconds | Recommended |

> **Warning**: If only `hr_bpm` is provided (no `rr_ms`), RR intervals are derived from BPM. This produces **degraded** HRV estimates. The quality flag `derived_from_bpm` will be set and HRV confidence is capped at "weak".

### Example (Mode C — beat-level)

```csv
timestamp_ms,hr_bpm,rr_ms
1715000000000,71.0,837.9
1715000001000,74.2,798.9
1715000002000,71.5,839.1
```

### Sampling rate

One row per heartbeat (≈ 1 Hz at rest). Raw ECG mode produces one row per ECG sample (130 Hz or 1000 Hz for Polar H10).

---

## 3. Event Markers CSV (Optional)

Experimental phase boundaries — when baseline, task, and recovery phases start and end.

### Required columns

| Column | Type | Description |
|--------|------|-------------|
| `event_code` | string | Phase identifier (e.g., `baseline_onset`, `room1_onset`) |
| `utc_ms` | integer | Unix epoch timestamp in milliseconds |

### Optional columns

| Column | Type | Description |
|--------|------|-------------|
| `session_id` | string | Session identifier |
| `note` | string | Free-text annotation |

### Naming convention for event codes

Use `{phase}_onset` / `{phase}_offset` pairs:

```
recording_start     → session begins
baseline_onset      → baseline phase starts
baseline_offset     → baseline phase ends
room1_onset         → room 1 visit starts
room1_offset        → room 1 visit ends
room2_onset         → room 2 visit starts
...
recovery_onset      → recovery phase starts
recovery_offset     → recovery phase ends
recording_end       → session ends
```

### Example

```csv
session_id,event_code,utc_ms,note
STUDY001_P041,recording_start,1715000000000,session begin
STUDY001_P041,baseline_onset,1715000030000,entering baseline
STUDY001_P041,baseline_offset,1715000150000,leaving baseline
STUDY001_P041,room1_onset,1715000180000,entering room 1 (Type A)
STUDY001_P041,room1_offset,1715000420000,leaving room 1
```

> **Important**: The `utc_ms` timestamps must be on the **same clock** as the EmotiBit `timestamp_ms`. If markers use a different time source, use the app's marker editor to manually align.

---

## 4. Order & Affect CSV (Optional)

Maps each subject's room visit sequence to room types and includes self-report valence/arousal ratings.

### Required columns

| Column | Type | Description |
|--------|------|-------------|
| `subject_id` | string | Subject identifier (e.g., `P041`) |
| `room_number` | integer | Visit order (1, 2, 3, ...) |
| `room_type` | string | Room condition label (e.g., `biophilic`, `minimalist`) |
| `valence` | float | Self-report valence (1–5 or 1–7 scale) |
| `arousal` | float | Self-report arousal (1–5 or 1–7 scale) |

### Example

```csv
subject_id,room_number,room_type,valence,arousal
P041,1,biophilic,4.2,1.8
P041,2,minimalist,3.1,2.5
P041,3,industrial,2.4,3.8
P041,4,cozy_warm,4.5,1.6
```

### Notes

- One row per room visit per subject
- `room_number` determines visit order (used for Latin-square counterbalancing analysis)
- `room_type` labels are user-defined — the analyzer groups by these labels for cross-subject comparison
- Valence and arousal scales should be consistent across subjects

---

## 5. Vernier Respiration Belt XLSX (Optional)

Direct respiratory force data from a Vernier respiration belt sensor.

### Required columns

| Column | Type | Unit | Description |
|--------|------|------|-------------|
| `timestamp_unix` | float | seconds | Unix epoch timestamp |
| `force` | float | arbitrary | Respiratory force sensor reading |

### Optional columns

| Column | Type | Description |
|--------|------|-------------|
| `timestamp` | datetime | Human-readable datetime |
| `RR` | float | Vendor-computed respiratory rate (validation only) |
| `event_marker` | string | Experimental phase markers |
| `condition` | string | Experimental condition labels |

### Notes

- Must be `.xlsx` format (Excel workbook), not CSV
- Data is resampled internally to a uniform **20 Hz** grid
- The respiratory processing pipeline uses ALS baseline removal and peak/trough detection (matching the Estelita RespInPeace protocol)
- Output includes per-breath features: inhale/exhale duration, I:E ratio, duty cycle, amplitude, respiratory rate

---

## Timestamp Synchronization

All timestamps across files must be on the **same clock**. The analyzer performs piecewise-linear drift correction between the Polar and EmotiBit clocks, but large offsets (> 5 minutes) will cause synchronization failure.

### Checklist

- [ ] EmotiBit `timestamp_ms` and Polar `timestamp_ms` are within 60 seconds of each other at the start of the recording
- [ ] Event marker `utc_ms` values fall within the EmotiBit recording time range
- [ ] Vernier `timestamp_unix` values (if present) fall within the same recording window

---

## File Upload Combinations

| Upload Combination | What You Get |
|-------------------|-------------|
| EmotiBit + Polar | Full paired analysis: HR, HRV, EDA, stress composite, synchronization QC |
| EmotiBit + Polar + Markers | Above + phase-comparison forest plots, room-level windowed analysis |
| EmotiBit + Polar + Markers + Order & Affect | Above + room-type aggregation, Latin-square condition comparison, factorial plots |
| EmotiBit + Polar + Vernier | Above + direct respiratory analysis, enhanced RSA, 6-channel stress composite |
| Polar only | HR and HRV only (no EDA, no stress composite, no synchronization) |
| EmotiBit only | EDA only (no HR, no HRV, no stress composite) |

---

## Export Formats

After analysis, results can be exported in four formats:

| Format | Extension | Contents |
|--------|-----------|----------|
| **CSV** | `.csv` | Flat table of all computed features |
| **Excel** | `.xlsx` | Multi-sheet workbook (summary, timeseries, room stats) |
| **MATLAB** | `.mat` | Struct with all analysis fields (MATLAB v5 compatible) |
| **PDF** | `.pdf` | Formatted report with charts and interpretation |

---

## Example Data Files

Ready-to-use example files are in [`docs/examples/`](docs/examples/):

- [`emotibit_example.csv`](docs/examples/emotibit_example.csv) — EmotiBit EDA + accelerometer
- [`polar_h10_example.csv`](docs/examples/polar_h10_example.csv) — Polar H10 beat-level metrics
- [`event_markers_example.csv`](docs/examples/event_markers_example.csv) — Experimental phase markers
- [`order_affect_example.csv`](docs/examples/order_affect_example.csv) — Room visit order + self-report ratings

For a complete working dataset (300-second recording with realistic physiological signals), run:

```bash
cd test_data && python generate_test_data.py
```

This generates `test_emotibit.csv`, `test_polar.csv`, and `test_markers.csv` with synthetic but physiologically plausible data.

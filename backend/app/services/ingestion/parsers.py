"""Parsers for EmotiBit and Polar exports."""

from __future__ import annotations

from io import StringIO

import numpy as np
import pandas as pd
from scipy.signal import butter, filtfilt, find_peaks


REQUIRED_EMOTIBIT_COLUMNS = {"timestamp_ms", "eda_us"}
OPTIONAL_EMOTIBIT_ACCEL_COLUMNS = ("acc_x", "acc_y", "acc_z")
OPTIONAL_EMOTIBIT_RESP_COLUMNS = ("resp_bpm",)
POLAR_TIMESTAMP_COLUMNS = ("timestamp_ms", "timestamp_ns")
POLAR_ECG_COLUMNS = ("ecg_uv", "ecg_mv", "ecg", "raw_ecg", "raw_ecg_uv", "voltage_uv")


def _validate_columns(df: pd.DataFrame, required: set[str], source: str) -> None:
    missing = required.difference(set(df.columns))
    if missing:
        raise ValueError(f"{source} missing required columns: {sorted(missing)}")


def _coerce_polar_timestamp_ms(df: pd.DataFrame) -> pd.Series:
    if "timestamp_ms" in df.columns:
        return pd.to_numeric(df["timestamp_ms"], errors="coerce")
    if "timestamp_ns" in df.columns:
        return pd.to_numeric(df["timestamp_ns"], errors="coerce") / 1_000_000.0
    raise ValueError(
        "Polar missing timestamp column. Expected one of: "
        f"{list(POLAR_TIMESTAMP_COLUMNS)}"
    )


def _first_present(columns: list[str], candidates: tuple[str, ...]) -> str | None:
    for candidate in candidates:
        if candidate in columns:
            return candidate
    return None


def _derive_beats_from_raw_ecg(timestamp_ms: pd.Series, ecg_series: pd.Series, *, ecg_col: str) -> pd.DataFrame:
    aligned = pd.DataFrame({"timestamp_ms": timestamp_ms, ecg_col: ecg_series}).dropna()
    if len(aligned) < 10:
        raise ValueError("Polar raw ECG has too few valid samples to derive beats")

    ts_ms = aligned["timestamp_ms"].to_numpy(dtype=float)
    ecg = aligned[ecg_col].to_numpy(dtype=float)
    if "uv" in ecg_col.lower():
        ecg = ecg / 1000.0  # convert microvolts to millivolts for numerical stability

    diffs_ms = np.diff(ts_ms)
    diffs_ms = diffs_ms[diffs_ms > 0]
    if len(diffs_ms) == 0:
        raise ValueError("Polar raw ECG timestamps are not strictly increasing")

    sample_hz = 1000.0 / float(np.median(diffs_ms))
    if sample_hz < 20.0:
        raise ValueError(
            f"Polar raw ECG sample rate looks too low ({sample_hz:.1f} Hz) for beat detection"
        )

    centered = ecg - float(np.median(ecg))
    if abs(float(np.min(centered))) > abs(float(np.max(centered))):
        centered = -centered

    nyquist = sample_hz / 2.0
    low_hz = 5.0 if sample_hz >= 50.0 else max(1.0, sample_hz * 0.04)
    high_hz = min(18.0, nyquist * 0.9)
    if low_hz >= high_hz:
        low_hz = max(0.5, high_hz * 0.5)

    b, a = butter(2, [low_hz / nyquist, high_hz / nyquist], btype="bandpass")
    filtered = filtfilt(b, a, centered)
    scale = float(np.std(filtered))
    if not np.isfinite(scale) or scale <= 0:
        raise ValueError("Polar raw ECG could not be normalized for beat detection")

    distance = max(1, int(sample_hz * 0.30))
    prominence = max(scale * 0.60, float(np.median(np.abs(filtered))) * 1.50)
    peaks, _props = find_peaks(filtered, distance=distance, prominence=prominence)
    if len(peaks) < 3:
        peaks, _props = find_peaks(filtered, distance=distance, prominence=max(scale * 0.30, 1e-6))
    if len(peaks) < 3:
        raise ValueError("Polar raw ECG did not yield enough R peaks to derive HR and RR")

    rr_ms = np.diff(ts_ms[peaks])
    beat_ts_ms = ts_ms[peaks[1:]]
    valid = (rr_ms >= 300.0) & (rr_ms <= 2000.0)
    if np.any(valid):
        median_rr = float(np.median(rr_ms[valid]))
        rhythm_valid = np.abs(rr_ms - median_rr) / max(median_rr, 1.0) <= 0.35
        valid &= rhythm_valid
    rr_ms = rr_ms[valid]
    beat_ts_ms = beat_ts_ms[valid]
    if len(rr_ms) < 3:
        raise ValueError("Polar raw ECG produced too few physiologically plausible RR intervals")

    hr_bpm = 60_000.0 / rr_ms
    beats = pd.DataFrame(
        {
            "timestamp_ms": np.round(beat_ts_ms).astype(int),
            "hr_bpm": hr_bpm.astype(float),
            "rr_ms": rr_ms.astype(float),
            "rr_source": "derived_from_ecg",
        }
    )
    return beats.sort_values("timestamp_ms").reset_index(drop=True)


def _parse_polar_beat_metrics(raw: pd.DataFrame, timestamp_ms: pd.Series) -> pd.DataFrame:
    parsed = pd.DataFrame({"timestamp_ms": timestamp_ms})
    has_hr = "hr_bpm" in raw.columns
    has_rr = "rr_ms" in raw.columns

    if has_hr:
        parsed["hr_bpm"] = pd.to_numeric(raw["hr_bpm"], errors="coerce")
    if has_rr:
        parsed["rr_ms"] = pd.to_numeric(raw["rr_ms"], errors="coerce")

    if not has_hr and not has_rr:
        raise ValueError(
            "Polar missing usable signal columns. Expected raw ECG "
            f"({list(POLAR_ECG_COLUMNS)}) or beat metrics ('hr_bpm' and/or 'rr_ms')."
        )

    if has_rr and "hr_bpm" not in parsed.columns:
        rr = parsed["rr_ms"].clip(lower=1.0)
        parsed["hr_bpm"] = 60_000.0 / rr

    if has_rr:
        parsed["rr_source"] = "native_polar"
        parsed = parsed.dropna(subset=["rr_ms", "hr_bpm"])
    else:
        parsed["rr_source"] = "derived_from_bpm"
        parsed = parsed.dropna(subset=["hr_bpm"])

    return parsed.sort_values("timestamp_ms").reset_index(drop=True)


def parse_emotibit_csv(csv_text: str) -> pd.DataFrame:
    """Parse EmotiBit CSV and enforce minimal schema."""
    df = pd.read_csv(StringIO(csv_text))
    _validate_columns(df, REQUIRED_EMOTIBIT_COLUMNS, "EmotiBit")
    parsed = df.copy()
    parsed["timestamp_ms"] = parsed["timestamp_ms"].astype(int)
    parsed["eda_us"] = pd.to_numeric(parsed["eda_us"], errors="coerce")
    for col in OPTIONAL_EMOTIBIT_ACCEL_COLUMNS:
        if col in parsed.columns:
            parsed[col] = pd.to_numeric(parsed[col], errors="coerce")
    for col in OPTIONAL_EMOTIBIT_RESP_COLUMNS:
        if col in parsed.columns:
            parsed[col] = pd.to_numeric(parsed[col], errors="coerce")
    parsed = parsed.dropna(subset=["eda_us"]).sort_values("timestamp_ms")
    return parsed


def parse_polar_csv(csv_text: str) -> pd.DataFrame:
    """Parse Polar CSV.

    Preferred input: raw ECG export (`timestamp_ms` or `timestamp_ns` plus a
    recognized ECG column such as `ecg_uv`). In that case HR and RR are derived
    in-app from the raw trace.

    Backward-compatible input: beat-level Polar export with `hr_bpm`, optional
    `rr_ms`, and `timestamp_ms`.
    """
    raw = pd.read_csv(StringIO(csv_text))
    input_columns = list(raw.columns)
    input_n_rows = int(len(raw))

    timestamp_ms = _coerce_polar_timestamp_ms(raw)
    ecg_col = _first_present(input_columns, POLAR_ECG_COLUMNS)

    if ecg_col is not None:
        parsed = _derive_beats_from_raw_ecg(
            timestamp_ms=timestamp_ms,
            ecg_series=pd.to_numeric(raw[ecg_col], errors="coerce"),
            ecg_col=ecg_col,
        )
        parsed.attrs.update(
            {
                "input_columns_present": input_columns,
                "input_n_rows": input_n_rows,
                "polar_input_mode": "raw_ecg",
                "has_raw_ecg": True,
                "has_native_rr": False,
                "rr_source": "derived_from_ecg",
                "rr_source_note": (
                    f"Raw Polar ECG column '{ecg_col}' present — HR and RR were computed in-app."
                ),
            }
        )
        return parsed

    parsed = _parse_polar_beat_metrics(raw, timestamp_ms)
    rr_source = str(parsed["rr_source"].iloc[0]) if len(parsed) else "derived_from_bpm"
    parsed.attrs.update(
        {
            "input_columns_present": input_columns,
            "input_n_rows": input_n_rows,
            "polar_input_mode": "beat_metrics",
            "has_raw_ecg": False,
            "has_native_rr": rr_source == "native_polar",
            "rr_source": rr_source,
            "rr_source_note": (
                "Native Polar RR intervals present — research-grade HRV."
                if rr_source == "native_polar"
                else "Only hr_bpm present — HRV will be derived from BPM (reduced accuracy)."
            ),
        }
    )
    parsed["timestamp_ms"] = np.round(parsed["timestamp_ms"]).astype(int)
    return parsed

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


# ---- Native EmotiBit format support ----------------------------------------
# Native EmotiBit exports produce separate CSV files per channel (EA, AX, AY,
# AZ) with a `LocalTimestamp` column (Unix seconds, float). These must be
# merged onto a common timeline before the pipeline can consume them.

NATIVE_EMOTIBIT_TIMESTAMP_COL = "LocalTimestamp"
NATIVE_EMOTIBIT_CHANNEL_MAP = {
    "EA": "eda_us",
    "AX": "acc_x",
    "AY": "acc_y",
    "AZ": "acc_z",
}
_MERGE_TOLERANCE_S = 0.05  # per PROMPT_INPUT spec


def _is_native_emotibit(df: pd.DataFrame) -> bool:
    """Check if a single CSV looks like a native EmotiBit channel file."""
    cols = set(c.strip() for c in df.columns)
    return NATIVE_EMOTIBIT_TIMESTAMP_COL in cols and "timestamp_ms" not in cols


def parse_native_emotibit(channel_texts: dict[str, str]) -> pd.DataFrame:
    """Parse native EmotiBit multi-channel CSVs and merge onto the EA timeline.

    Args:
        channel_texts: mapping of channel suffix to raw CSV text.
            Expected keys: "EA" (required), and optionally "AX", "AY", "AZ".

    Returns:
        DataFrame with columns: timestamp_ms, eda_us, acc_x, acc_y, acc_z.
    """
    if "EA" not in channel_texts:
        raise ValueError(
            "Native EmotiBit upload requires an EDA channel file (*_EA.csv)."
        )

    dfs: dict[str, pd.DataFrame] = {}
    for suffix, text in channel_texts.items():
        df = pd.read_csv(StringIO(text))
        if NATIVE_EMOTIBIT_TIMESTAMP_COL not in df.columns:
            raise ValueError(
                f"Native EmotiBit {suffix} file missing '{NATIVE_EMOTIBIT_TIMESTAMP_COL}' column."
            )
        df[NATIVE_EMOTIBIT_TIMESTAMP_COL] = pd.to_numeric(
            df[NATIVE_EMOTIBIT_TIMESTAMP_COL], errors="coerce"
        )
        # Identify the data column: the first column that is not LocalTimestamp
        data_cols = [c for c in df.columns if c != NATIVE_EMOTIBIT_TIMESTAMP_COL]
        if not data_cols:
            raise ValueError(f"Native EmotiBit {suffix} file has no data column.")
        # Use the first data column and rename to our schema name
        target_name = NATIVE_EMOTIBIT_CHANNEL_MAP.get(suffix, data_cols[0])
        df = df[[NATIVE_EMOTIBIT_TIMESTAMP_COL, data_cols[0]]].copy()
        df.columns = ["local_ts", target_name]
        df[target_name] = pd.to_numeric(df[target_name], errors="coerce")
        df = df.dropna().sort_values("local_ts").reset_index(drop=True)
        dfs[suffix] = df

    # Build timeline from EA channel
    ea = dfs["EA"]
    result = pd.DataFrame({
        "timestamp_ms": np.round(ea["local_ts"].to_numpy() * 1000).astype(int),
        "eda_us": ea["eda_us"].to_numpy(),
    })

    # Merge accelerometer channels by nearest timestamp
    for suffix in ("AX", "AY", "AZ"):
        if suffix not in dfs:
            continue
        chan = dfs[suffix]
        target_col = NATIVE_EMOTIBIT_CHANNEL_MAP[suffix]
        chan_ts = chan["local_ts"].to_numpy()
        ea_ts = ea["local_ts"].to_numpy()
        # For each EA timestamp, find the nearest channel timestamp
        idxs = np.searchsorted(chan_ts, ea_ts, side="left")
        idxs = np.clip(idxs, 0, len(chan_ts) - 1)
        # Check the neighbor to the left as well
        left = np.clip(idxs - 1, 0, len(chan_ts) - 1)
        use_left = np.abs(chan_ts[left] - ea_ts) < np.abs(chan_ts[idxs] - ea_ts)
        idxs[use_left] = left[use_left]
        # Apply tolerance: NaN if too far
        deltas = np.abs(chan_ts[idxs] - ea_ts)
        values = chan[target_col].to_numpy()[idxs].astype(float)
        values[deltas > _MERGE_TOLERANCE_S] = np.nan
        result[target_col] = values

    result = result.dropna(subset=["eda_us"]).sort_values("timestamp_ms").reset_index(drop=True)
    return result


# ---- Native Polar format support ------------------------------------------
# Native Polar H10 exports use `utc_epoch_ns` for timestamps and `rr_ms` or
# `rr` for inter-beat intervals, with metadata rows prefixed by `#`.

NATIVE_POLAR_TIMESTAMP_COL = "utc_epoch_ns"
NATIVE_POLAR_RR_CANDIDATES = ("rr_ms", "rr", "RR", "ibi_ms", "ibi")


def _is_native_polar(df: pd.DataFrame) -> bool:
    """Check if a CSV looks like a native Polar export (utc_epoch_ns)."""
    cols = set(c.strip() for c in df.columns)
    return NATIVE_POLAR_TIMESTAMP_COL in cols and "timestamp_ms" not in cols


def parse_native_polar(csv_text: str) -> pd.DataFrame:
    """Parse a native Polar H10 CSV with utc_epoch_ns timestamps.

    Skips comment rows starting with '#'. Converts nanosecond timestamps
    to milliseconds and derives hr_bpm from rr_ms.

    Returns:
        DataFrame with columns: timestamp_ms, hr_bpm, rr_ms, rr_source.
    """
    # Filter out comment lines
    lines = [line for line in csv_text.split("\n") if not line.strip().startswith("#")]
    filtered_text = "\n".join(lines)

    raw = pd.read_csv(StringIO(filtered_text))
    if NATIVE_POLAR_TIMESTAMP_COL not in raw.columns:
        raise ValueError(
            f"Native Polar file missing '{NATIVE_POLAR_TIMESTAMP_COL}' column."
        )

    # Convert nanosecond timestamps to milliseconds
    ts_ns = pd.to_numeric(raw[NATIVE_POLAR_TIMESTAMP_COL], errors="coerce")
    timestamp_ms = np.round(ts_ns / 1_000_000.0).astype(int)

    # Find the RR column
    rr_col = _first_present(list(raw.columns), NATIVE_POLAR_RR_CANDIDATES)
    if rr_col is None:
        raise ValueError(
            f"Native Polar file missing RR column. Expected one of: "
            f"{list(NATIVE_POLAR_RR_CANDIDATES)}. Got: {list(raw.columns)}"
        )

    rr_ms = pd.to_numeric(raw[rr_col], errors="coerce")

    parsed = pd.DataFrame({
        "timestamp_ms": timestamp_ms,
        "rr_ms": rr_ms,
    })
    parsed = parsed.dropna()
    parsed["rr_ms"] = parsed["rr_ms"].clip(lower=1.0)
    parsed["hr_bpm"] = 60_000.0 / parsed["rr_ms"]
    parsed["rr_source"] = "native_polar"

    input_columns = list(raw.columns)
    input_n_rows = int(len(raw))
    parsed = parsed.sort_values("timestamp_ms").reset_index(drop=True)
    parsed.attrs.update({
        "input_columns_present": input_columns,
        "input_n_rows": input_n_rows,
        "polar_input_mode": "native_rr",
        "has_raw_ecg": False,
        "has_native_rr": True,
        "rr_source": "native_polar",
        "rr_source_note": (
            "Native Polar RR intervals (utc_epoch_ns + rr_ms) — research-grade HRV."
        ),
    })
    return parsed


def parse_emotibit_csv(csv_text: str) -> pd.DataFrame:
    """Parse EmotiBit CSV and enforce minimal schema.

    Auto-detects native EmotiBit format (LocalTimestamp column) for single-
    channel files and converts them to the standard schema.
    """
    df = pd.read_csv(StringIO(csv_text))

    # Auto-detect native single-file EmotiBit format
    if _is_native_emotibit(df):
        return parse_native_emotibit({"EA": csv_text})

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

    Also accepts native Polar format with `utc_epoch_ns` + `rr_ms` columns.

    Backward-compatible input: beat-level Polar export with `hr_bpm`, optional
    `rr_ms`, and `timestamp_ms`.
    """
    # Filter comment lines before initial read
    lines = [line for line in csv_text.split("\n") if not line.strip().startswith("#")]
    filtered_text = "\n".join(lines)

    raw = pd.read_csv(StringIO(filtered_text))
    input_columns = list(raw.columns)
    input_n_rows = int(len(raw))

    # Auto-detect native Polar format (utc_epoch_ns)
    if _is_native_polar(raw):
        return parse_native_polar(csv_text)

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

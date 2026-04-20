"""Parsers for EmotiBit and Polar exports."""

from __future__ import annotations

from io import StringIO

import pandas as pd


REQUIRED_EMOTIBIT_COLUMNS = {"timestamp_ms", "eda_us"}
REQUIRED_POLAR_COLUMNS = {"timestamp_ms", "hr_bpm"}
OPTIONAL_EMOTIBIT_ACCEL_COLUMNS = ("acc_x", "acc_y", "acc_z")
OPTIONAL_EMOTIBIT_RESP_COLUMNS = ("resp_bpm",)


def _validate_columns(df: pd.DataFrame, required: set[str], source: str) -> None:
    missing = required.difference(set(df.columns))
    if missing:
        raise ValueError(f"{source} missing required columns: {sorted(missing)}")


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
    """Parse Polar CSV and enforce minimal schema."""
    df = pd.read_csv(StringIO(csv_text))
    _validate_columns(df, REQUIRED_POLAR_COLUMNS, "Polar")
    parsed = df.copy()
    parsed["timestamp_ms"] = parsed["timestamp_ms"].astype(int)
    parsed["hr_bpm"] = pd.to_numeric(parsed["hr_bpm"], errors="coerce")
    if "rr_ms" in parsed.columns:
        parsed["rr_ms"] = pd.to_numeric(parsed["rr_ms"], errors="coerce")
    parsed = parsed.dropna(subset=["hr_bpm"]).sort_values("timestamp_ms")
    return parsed

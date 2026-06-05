#!/usr/bin/env python3
"""Preprocess Estelita biometrics CSV for the Polar-EmotiBit Analyzer.

Estelita's biometrics CSV uses different column names and timestamp format
than the analyzer expects. This script converts:
  - timestamp_unix (seconds) → timestamp_ms (milliseconds)
  - EDA → eda_us
  - HR → hr_bpm
  - BI (beat interval ms) → rr_ms

The Vernier XLSX file can be used directly — the parser auto-derives
timestamp_unix from the datetime timestamp column.

Usage:
    python preprocess_estelita.py <biometrics.csv> [output.csv]

If output is omitted, writes to <input>_prepped.csv
"""
import sys
import pandas as pd
import numpy as np


def preprocess_biometrics(input_path: str, output_path: str | None = None) -> str:
    df = pd.read_csv(input_path)
    print(f"Read {len(df)} rows from {input_path}")
    print(f"Columns: {list(df.columns)}")

    out = pd.DataFrame()

    # Timestamps: unix seconds → milliseconds
    if "timestamp_unix" in df.columns:
        out["timestamp_ms"] = (df["timestamp_unix"] * 1000).round().astype("int64")
    elif "timestamp_ms" in df.columns:
        out["timestamp_ms"] = df["timestamp_ms"].astype("int64")
    else:
        raise ValueError("No timestamp_unix or timestamp_ms column found")

    # EDA (microsiemens)
    if "EDA" in df.columns:
        out["eda_us"] = pd.to_numeric(df["EDA"], errors="coerce")
    elif "eda_us" in df.columns:
        out["eda_us"] = pd.to_numeric(df["eda_us"], errors="coerce")

    # Heart rate
    if "HR" in df.columns:
        out["hr_bpm"] = pd.to_numeric(df["HR"], errors="coerce")
    elif "hr_bpm" in df.columns:
        out["hr_bpm"] = pd.to_numeric(df["hr_bpm"], errors="coerce")

    # Beat interval → RR interval
    if "BI" in df.columns:
        out["rr_ms"] = pd.to_numeric(df["BI"], errors="coerce")
    elif "rr_ms" in df.columns:
        out["rr_ms"] = pd.to_numeric(df["rr_ms"], errors="coerce")

    # Accelerometer (optional — EmotiBit ground_truth files have these)
    for em_col, out_col in [("AX", "accel_x"), ("AY", "accel_y"), ("AZ", "accel_z")]:
        if em_col in df.columns:
            out[out_col] = pd.to_numeric(df[em_col], errors="coerce")

    # Sort by time; keep all rows (EmotiBit interleaves EDA/HR on separate rows)
    out = out.sort_values("timestamp_ms")
    sensor_cols = [c for c in ["eda_us", "hr_bpm", "rr_ms"] if c in out.columns]
    before = len(out)
    out = out.dropna(subset=sensor_cols, how="all")
    after = len(out)
    if before != after:
        print(f"Dropped {before - after} rows with no sensor data")

    if output_path is None:
        output_path = input_path.replace(".csv", "_prepped.csv")

    out.to_csv(output_path, index=False)
    print(f"Wrote {len(out)} rows to {output_path}")
    print(f"Columns: {list(out.columns)}")
    print(f"EDA range: {out['eda_us'].min():.4f} – {out['eda_us'].max():.4f}")
    if "hr_bpm" in out.columns:
        hr = out["hr_bpm"].dropna()
        print(f"HR range: {hr.min():.1f} – {hr.max():.1f} ({len(hr)} values)")
    if "rr_ms" in out.columns:
        rr = out["rr_ms"].dropna()
        print(f"RR range: {rr.min():.1f} – {rr.max():.1f} ({len(rr)} values)")

    return output_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    in_path = sys.argv[1]
    out_path = sys.argv[2] if len(sys.argv) > 2 else None
    preprocess_biometrics(in_path, out_path)

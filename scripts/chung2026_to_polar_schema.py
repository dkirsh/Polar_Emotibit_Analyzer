#!/usr/bin/env python3
"""Map a Chung et al. (2026) OSF WYM3S participant folder into our Polar schema.

The Chung, Chopin, Karadayi & Grèzes (2026) OSF deposit
(doi:10.17605/OSF.IO/WYM3S) stores raw Polar H10 ECG at 133 Hz plus a
computed inter-beat-interval (IBI / RR) series. Our pipeline expects a
Polar CSV with columns `timestamp_ms`, `hr_bpm`, and (optionally) `rr_ms`.

This script consumes one participant's IBI file, computes hr_bpm per beat
from RR, and emits a single CSV in the schema our parser expects.

Usage:
    python3 scripts/chung2026_to_polar_schema.py \\
        --ibi-file data/samples/P01/ibi.csv \\
        --out data/samples/polar_sample_01.csv

The exact column names in the Chung et al. files may differ per
participant folder; the script's --rr-col flag lets you override the
default guess. Inspect the source file with `head` first if unsure.

This is a *smoke-test* helper, not a validated conversion pipeline. The
Chung et al. paper reports r > 0.99 between the H10 and a gold-standard
ECG on this same data, so a successful pipeline run should reproduce a
mean_hr_bpm close to the paper's published per-participant values
(checked independently by the caller).
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def convert(ibi_path: Path, out_path: Path, rr_col: str = "rr_ms", ts_col: str = "timestamp_ms") -> None:
    df = pd.read_csv(ibi_path)

    # Column auto-detection with common Chung-style fallbacks
    candidate_rr = [rr_col, "rr_ms", "rr", "RR", "ibi_ms", "ibi"]
    candidate_ts = [ts_col, "timestamp_ms", "t_ms", "timestamp", "time"]

    rr_found = next((c for c in candidate_rr if c in df.columns), None)
    ts_found = next((c for c in candidate_ts if c in df.columns), None)

    if rr_found is None:
        raise SystemExit(
            f"No RR column found. Tried {candidate_rr}. Columns: {df.columns.tolist()}"
        )
    if ts_found is None:
        # Build timestamps from cumulative RR sums when no explicit timestamp.
        rr_vals = pd.to_numeric(df[rr_found], errors="coerce").dropna()
        ts_ms = rr_vals.cumsum().astype(int)
    else:
        ts_ms = pd.to_numeric(df[ts_found], errors="coerce").dropna().astype(int)
        if ts_ms.min() > 1e12:  # looks like nanoseconds, convert
            ts_ms = (ts_ms // 1_000_000).astype(int)

    rr_ms = pd.to_numeric(df[rr_found], errors="coerce").dropna().astype(float)

    # Align lengths
    n = min(len(ts_ms), len(rr_ms))
    ts_ms = ts_ms.iloc[:n].reset_index(drop=True)
    rr_ms = rr_ms.iloc[:n].reset_index(drop=True)

    # Derive hr_bpm from RR
    hr_bpm = (60_000.0 / rr_ms.clip(lower=1.0)).astype(float)

    out = pd.DataFrame({
        "timestamp_ms": ts_ms,
        "hr_bpm": hr_bpm.round(2),
        "rr_ms": rr_ms.round(1),
    })
    out.to_csv(out_path, index=False)
    print(f"wrote {len(out)} rows to {out_path}")
    print(f"  hr range: {out['hr_bpm'].min():.1f} – {out['hr_bpm'].max():.1f} bpm")
    print(f"  session span: {(ts_ms.iloc[-1] - ts_ms.iloc[0]) / 1000:.1f} s")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ibi-file", type=Path, required=True, help="Chung et al. IBI CSV for one participant")
    p.add_argument("--out", type=Path, required=True, help="Output polar_sample.csv in our schema")
    p.add_argument("--rr-col", default="rr_ms", help="Override RR column name")
    p.add_argument("--ts-col", default="timestamp_ms", help="Override timestamp column name")
    args = p.parse_args()
    convert(args.ibi_file, args.out, rr_col=args.rr_col, ts_col=args.ts_col)


if __name__ == "__main__":
    main()

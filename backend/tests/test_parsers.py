from __future__ import annotations

from io import StringIO

import numpy as np
import pandas as pd

from app.services.ingestion.parsers import parse_polar_csv


def _make_raw_ecg_csv(
    *,
    n_beats: int = 80,
    rr_ms: int = 800,
    sample_hz: int = 130,
) -> str:
    rng = np.random.default_rng(42)
    total_ms = int((n_beats + 2) * rr_ms)
    dt_ns = int(round(1_000_000_000 / sample_hz))
    ts_ns = np.arange(0, int(total_ms * 1_000_000), dt_ns, dtype=np.int64)
    ecg_uv = rng.normal(0.0, 18.0, len(ts_ns))

    beat_times_ms = np.cumsum(np.full(n_beats, rr_ms, dtype=float))
    sample_ms = ts_ns / 1_000_000.0
    kernel = [90.0, 260.0, 950.0, 260.0, 90.0]
    for beat_ms in beat_times_ms:
        idx = int(np.argmin(np.abs(sample_ms - beat_ms)))
        for offset, amp in enumerate(kernel, start=-2):
            j = idx + offset
            if 0 <= j < len(ecg_uv):
                ecg_uv[j] += amp

    raw = pd.DataFrame({"timestamp_ns": ts_ns, "ecg_uv": ecg_uv})
    return raw.to_csv(index=False)


def test_parse_polar_csv_accepts_raw_ecg_and_derives_beats():
    parsed = parse_polar_csv(_make_raw_ecg_csv())

    assert {"timestamp_ms", "hr_bpm", "rr_ms", "rr_source"}.issubset(parsed.columns)
    assert parsed.attrs["polar_input_mode"] == "raw_ecg"
    assert parsed.attrs["has_raw_ecg"] is True
    assert parsed.attrs["rr_source"] == "derived_from_ecg"
    assert len(parsed) >= 50
    assert abs(float(parsed["hr_bpm"].mean()) - 75.0) < 5.0
    assert abs(float(parsed["rr_ms"].mean()) - 800.0) < 50.0
    assert set(parsed["rr_source"].unique()) == {"derived_from_ecg"}


def test_parse_polar_csv_still_accepts_rr_only_exports():
    raw = StringIO("timestamp_ms,rr_ms\n800,800\n1600,790\n2400,810\n3200,805\n")
    parsed = parse_polar_csv(raw.getvalue())

    assert {"timestamp_ms", "hr_bpm", "rr_ms", "rr_source"}.issubset(parsed.columns)
    assert parsed.attrs["rr_source"] == "native_polar"
    assert parsed.attrs["has_native_rr"] is True
    assert len(parsed) == 4

from __future__ import annotations

import pandas as pd

from app.services.processing.room_analysis import compute_room_stats


def test_room_stats_include_baseline_normalized_fields():
    rows = []
    for i in range(60):
        rows.append({"timestamp_ms": i * 1000, "hr_bpm": 60.0, "eda_us": 1.0})
    for i in range(60, 120):
        rows.append({"timestamp_ms": i * 1000, "hr_bpm": 72.0, "eda_us": 1.5})
    df = pd.DataFrame(rows)
    markers = [
        {"event_code": "baseline_onset", "utc_ms": 0},
        {"event_code": "baseline_offset", "utc_ms": 59_000},
        {"event_code": "room1_onset", "utc_ms": 60_000},
        {"event_code": "room1_offset", "utc_ms": 119_000},
    ]

    stats = compute_room_stats(df, markers)
    baseline = next(row for row in stats if row["room_key"] == "baseline")
    room1 = next(row for row in stats if row["room_key"] == "room1")

    assert baseline["mean_hr_delta_bpm"] == 0.0
    assert baseline["mean_eda_delta_us"] == 0.0
    assert baseline["mean_hr_pct_change"] == 0.0

    assert room1["mean_hr_delta_bpm"] == 12.0
    assert round(room1["mean_hr_pct_change"], 2) == 20.0
    assert room1["mean_eda_delta_us"] == 0.5
    assert room1["eda_phasic_delta"] == 0.0
    assert "ln_rmssd_delta" in room1

"""Room-level windowed analysis.

Computes per-room descriptive statistics using only data within each room's
onset/offset marker window. When Order & Affect data is present, attaches
room-type labels and self-report valence/arousal for cross-subject comparison.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from app.services.processing.features import (
    compute_time_domain_features,
    compute_poincare_features,
    compute_hrv_frequency_features,
    compute_edr,
)
from app.services.processing.stress import compute_stress_score_v2
from app.services.processing.extended_analytics import decompose_stress


def compute_room_stats(
    cleaned_df: pd.DataFrame,
    markers: list[dict[str, Any]],
    order_affect: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Compute per-room physiological statistics from onset/offset bounded windows.

    Only data points where onset_ms <= timestamp_ms <= offset_ms are included.
    Data outside these windows is ignored.

    Args:
        cleaned_df: Cleaned/synchronized timeseries with timestamp_ms, hr_bpm, eda_us, etc.
        markers: List of marker dicts with event_code and utc_ms.
        order_affect: Optional parsed OrderAffectData dict with room-type mappings.

    Returns:
        List of per-room stat dicts, each containing:
            room_number, room_type, onset_ms, offset_ms, duration_s,
            mean_hr, sd_hr, mean_eda, sd_eda, rmssd, stress_v2, stress_v1,
            valence, arousal, sample_count
    """
    if cleaned_df is None or len(cleaned_df) == 0:
        return []

    # Extract room onset/offset pairs from markers
    intervals = _extract_room_intervals(markers)
    if not intervals:
        return []

    # Build room-type map from order_affect
    room_type_map: dict[int, str] = {}
    affect_map: dict[int, dict[str, float | None]] = {}
    if order_affect and isinstance(order_affect.get("rooms"), list):
        for room in order_affect["rooms"]:
            rn = room.get("room_number")
            if rn is not None:
                room_type_map[rn] = room.get("room_type", str(rn))
                affect_map[rn] = {
                    "valence": room.get("valence"),
                    "arousal": room.get("arousal"),
                }

    results: list[dict[str, Any]] = []

    for interval in intervals:
        room_number = interval["room_number"]
        onset_ms = interval["onset_ms"]
        offset_ms = interval["offset_ms"]

        # Gate the timeseries to this room's window
        mask = (
            (cleaned_df["timestamp_ms"] >= onset_ms) &
            (cleaned_df["timestamp_ms"] <= offset_ms)
        )
        window = cleaned_df[mask].copy()

        room_type = room_type_map.get(room_number, interval.get("key", str(room_number)))
        affect = affect_map.get(room_number, {"valence": None, "arousal": None})

        stats: dict[str, Any] = {
            "room_number": room_number,
            "room_key": interval.get("key", f"room{room_number}"),
            "room_type": room_type,
            "onset_ms": onset_ms,
            "offset_ms": offset_ms,
            "duration_s": round((offset_ms - onset_ms) / 1000.0, 1),
            "sample_count": len(window),
            "valence": affect.get("valence"),
            "arousal": affect.get("arousal"),
        }

        if len(window) < 2:
            stats.update({
                "mean_hr": None, "sd_hr": None,
                "mean_eda": None, "sd_eda": None,
                "rmssd": None, "stress_v2": None, "stress_v1": None,
            })
            results.append(stats)
            continue

        # HR stats
        if "hr_bpm" in window.columns:
            hr = window["hr_bpm"].dropna()
            stats["mean_hr"] = round(float(hr.mean()), 1) if len(hr) > 0 else None
            stats["sd_hr"] = round(float(hr.std(ddof=1)), 1) if len(hr) > 1 else 0.0
        else:
            stats["mean_hr"] = None
            stats["sd_hr"] = None

        # EDA stats
        if "eda_us" in window.columns:
            eda = window["eda_us"].dropna()
            stats["mean_eda"] = round(float(eda.mean()), 2) if len(eda) > 0 else None
            stats["sd_eda"] = round(float(eda.std(ddof=1)), 2) if len(eda) > 1 else 0.0
        else:
            stats["mean_eda"] = None
            stats["sd_eda"] = None

        # HRV features (RMSSD)
        try:
            td = compute_time_domain_features(window)
            stats["rmssd"] = round(float(td.get("rmssd_ms", 0.0)), 1) if td.get("rmssd_ms") is not None else None
        except Exception:
            stats["rmssd"] = None

        # Stress scores
        try:
            phasic = 0.0
            if "eda_us" in window.columns and len(window) > 1:
                phasic = float(np.mean(np.abs(np.diff(window["eda_us"].dropna().to_numpy(dtype=float)))))

            mean_hr = stats["mean_hr"] or 0.0
            mean_eda = stats["mean_eda"] or 0.0
            rmssd_val = stats["rmssd"] or 0.0

            poincare = compute_poincare_features(window)
            freq = compute_hrv_frequency_features(window)
            edr = compute_edr(window)
            rsa_amp = float(edr.get("rsa_amplitude", 0.0)) if edr.get("rsa_amplitude") is not None else None

            stress_v2, _ = compute_stress_score_v2(
                rmssd_ms=rmssd_val,
                mean_hr_bpm=mean_hr,
                eda_mean_us=mean_eda,
                eda_phasic_index=phasic,
                pnn50=td.get("pnn50"),
                sd1_sd2_ratio=poincare.get("sd1_sd2_ratio"),
                lf_nu=freq.get("lf_nu"),
                rsa_amplitude=rsa_amp,
            )
            stats["stress_v2"] = round(float(stress_v2), 3) if stress_v2 is not None else None

            decomp = decompose_stress(
                rmssd_ms=rmssd_val,
                mean_hr_bpm=mean_hr,
                eda_mean_us=mean_eda,
                eda_phasic_index=phasic,
                rsa_amplitude=rsa_amp,
            )
            stats["stress_v1"] = round(decomp.total_score, 3)
        except Exception:
            stats["stress_v2"] = None
            stats["stress_v1"] = None

        results.append(stats)

    return results


def _extract_room_intervals(markers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Extract room onset/offset pairs from event markers.

    Handles room markers named `roomN_onset` / `roomN_offset` and
    `baseline_onset` / `baseline_offset`.

    Returns list of dicts with: key, room_number, onset_ms, offset_ms.
    """
    by_key: dict[str, dict[str, Any]] = {}

    for marker in markers:
        code = str(marker.get("event_code", ""))
        try:
            utc_ms = int(marker.get("utc_ms"))
        except (TypeError, ValueError):
            continue

        if code.endswith("_onset"):
            key = code[:-6]
            by_key.setdefault(key, {"key": key})["onset_ms"] = utc_ms
        elif code.endswith("_offset"):
            key = code[:-7]
            by_key.setdefault(key, {"key": key})["offset_ms"] = utc_ms

    # Sort by onset_ms ASCENDING = chronological visit order.
    # For negative-offset timestamps (relative to recording end), the most
    # negative value is the earliest event in the session.
    sorted_intervals = sorted(
        [v for v in by_key.values() if "onset_ms" in v and "offset_ms" in v],
        key=lambda iv: iv.get("onset_ms", 0),
    )

    for idx, interval in enumerate(sorted_intervals):
        key = str(interval["key"])

        # Determine room number from the marker key name
        room_number = 0  # baseline
        if key.lower().startswith("room") and key[4:].isdigit():
            room_number = int(key[4:])
        elif key.lower() == "baseline":
            room_number = 0

        intervals.append({
            "key": key,
            "room_number": room_number,
            "room_index": idx,  # chronological position (0 = first visited)
            "onset_ms": interval["onset_ms"],
            "offset_ms": interval["offset_ms"],
        })

    return intervals


def export_room_comparison_csv(sessions: list[dict[str, Any]]) -> bytes:
    """Generate a cross-subject room comparison CSV for R analysis.

    Produces one row per room per subject:
        subject_id, room_type, room_number, mean_hr, sd_hr, mean_eda, sd_eda,
        rmssd, stress_v2, stress_v1, valence, arousal, duration_s, sample_count

    Args:
        sessions: list of session store records, each containing
            subject_id, room_stats, and optionally order_affect.

    Returns:
        CSV bytes.
    """
    import csv
    import io

    headers = [
        "subject_id", "room_type", "room_number", "room_key",
        "mean_hr", "sd_hr", "mean_eda", "sd_eda",
        "rmssd", "stress_v2", "stress_v1",
        "valence", "arousal",
        "duration_s", "sample_count",
    ]

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=headers)
    writer.writeheader()

    for session in sessions:
        subject_id = session.get("subject_id", "")
        room_stats = session.get("room_stats") or []

        for rs in room_stats:
            writer.writerow({
                "subject_id": subject_id,
                "room_type": rs.get("room_type", ""),
                "room_number": rs.get("room_number", ""),
                "room_key": rs.get("room_key", ""),
                "mean_hr": _fmt(rs.get("mean_hr"), 1),
                "sd_hr": _fmt(rs.get("sd_hr"), 1),
                "mean_eda": _fmt(rs.get("mean_eda"), 2),
                "sd_eda": _fmt(rs.get("sd_eda"), 2),
                "rmssd": _fmt(rs.get("rmssd"), 1),
                "stress_v2": _fmt(rs.get("stress_v2"), 3),
                "stress_v1": _fmt(rs.get("stress_v1"), 3),
                "valence": _fmt(rs.get("valence"), 2),
                "arousal": _fmt(rs.get("arousal"), 2),
                "duration_s": _fmt(rs.get("duration_s"), 1),
                "sample_count": rs.get("sample_count", ""),
            })

    return buf.getvalue().encode("utf-8")


def _fmt(value: float | None, digits: int) -> str:
    return "" if value is None else f"{value:.{digits}f}"

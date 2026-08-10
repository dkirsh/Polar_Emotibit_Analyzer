"""Baseline-relative normalization helpers for physiological signals.

The analyzer keeps raw values intact, but also computes within-subject
normalized derivatives for cross-subject and cross-room comparison.

Design:
- HR: baseline-relative delta and percent change
- HRV: log-RMSSD delta from baseline
- EDA tonic: baseline-relative delta
- EDA phasic: baseline-relative delta
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

import numpy as np
import pandas as pd

from app.services.processing.features import compute_time_domain_features


@dataclass
class BaselineReference:
    onset_ms: float
    offset_ms: float
    mean_hr_bpm: float | None
    tonic_eda_us: float | None
    phasic_eda_index: float | None
    rmssd_ms: float | None


def compute_eda_phasic_index(values: pd.Series | np.ndarray | list[float]) -> float | None:
    arr = np.asarray(values, dtype=float)
    arr = arr[np.isfinite(arr)]
    if len(arr) < 2:
        return None
    return float(np.mean(np.abs(np.diff(arr))))


def _baseline_bounds(markers: list[dict[str, Any]]) -> tuple[float, float] | None:
    onset = None
    offset = None
    for marker in markers:
        code = str(marker.get("event_code", "")).lower()
        try:
            ts = float(marker.get("utc_ms"))
        except (TypeError, ValueError):
            continue
        if code.endswith("baseline_onset"):
            onset = ts
        elif code.endswith("baseline_offset"):
            offset = ts
    if onset is None or offset is None or offset <= onset:
        return None
    return onset, offset


def compute_baseline_reference(df: pd.DataFrame, markers: list[dict[str, Any]]) -> BaselineReference | None:
    if df is None or len(df) < 2 or "timestamp_ms" not in df.columns:
        return None
    bounds = _baseline_bounds(markers)
    if bounds is None:
        return None
    onset_ms, offset_ms = bounds
    chunk = df[(df["timestamp_ms"] >= onset_ms) & (df["timestamp_ms"] <= offset_ms)].copy()
    if len(chunk) < 2:
        return None

    mean_hr = None
    if "hr_bpm" in chunk.columns:
        hr = pd.to_numeric(chunk["hr_bpm"], errors="coerce").dropna()
        if len(hr) > 0:
            mean_hr = float(hr.mean())

    tonic_eda = None
    phasic_eda = None
    if "eda_us" in chunk.columns:
        eda = pd.to_numeric(chunk["eda_us"], errors="coerce").dropna()
        if len(eda) > 0:
            tonic_eda = float(eda.mean())
            phasic_eda = compute_eda_phasic_index(eda)

    rmssd = None
    try:
        td = compute_time_domain_features(chunk)
        if td.get("rmssd_ms") is not None:
            rmssd = float(td["rmssd_ms"])
    except Exception:
        rmssd = None

    return BaselineReference(
        onset_ms=onset_ms,
        offset_ms=offset_ms,
        mean_hr_bpm=mean_hr,
        tonic_eda_us=tonic_eda,
        phasic_eda_index=phasic_eda,
        rmssd_ms=rmssd,
    )


def delta_from_baseline(value: float | None, baseline: float | None, digits: int | None = None) -> float | None:
    if value is None or baseline is None:
        return None
    out = float(value) - float(baseline)
    return round(out, digits) if digits is not None else out


def pct_change_from_baseline(value: float | None, baseline: float | None, digits: int | None = None) -> float | None:
    if value is None or baseline is None:
        return None
    baseline = float(baseline)
    if abs(baseline) < 1e-9:
        return None
    out = 100.0 * (float(value) - baseline) / baseline
    return round(out, digits) if digits is not None else out


def log_delta_from_baseline(value: float | None, baseline: float | None, digits: int | None = None) -> float | None:
    if value is None or baseline is None:
        return None
    value = float(value)
    baseline = float(baseline)
    if value <= 0 or baseline <= 0:
        return None
    out = math.log(value) - math.log(baseline)
    return round(out, digits) if digits is not None else out


def normalize_room_rows(rows: list[dict[str, Any]], baseline: BaselineReference | None) -> list[dict[str, Any]]:
    for row in rows:
        row["baseline_hr_bpm"] = baseline.mean_hr_bpm if baseline else None
        row["baseline_eda_tonic_us"] = baseline.tonic_eda_us if baseline else None
        row["baseline_eda_phasic_index"] = baseline.phasic_eda_index if baseline else None
        row["baseline_rmssd_ms"] = baseline.rmssd_ms if baseline else None
        if str(row.get("room_key", "")).lower() == "baseline":
            row["mean_hr_delta_bpm"] = 0.0
            row["mean_hr_pct_change"] = 0.0
            row["mean_eda_delta_us"] = 0.0
            row["eda_phasic_delta"] = 0.0
            row["ln_rmssd_delta"] = 0.0 if row.get("rmssd") not in (None, 0) else None
            continue
        row["mean_hr_delta_bpm"] = delta_from_baseline(row.get("mean_hr"), baseline.mean_hr_bpm if baseline else None, 1)
        row["mean_hr_pct_change"] = pct_change_from_baseline(row.get("mean_hr"), baseline.mean_hr_bpm if baseline else None, 2)
        row["mean_eda_delta_us"] = delta_from_baseline(row.get("mean_eda"), baseline.tonic_eda_us if baseline else None, 3)
        row["eda_phasic_delta"] = delta_from_baseline(row.get("eda_phasic_index"), baseline.phasic_eda_index if baseline else None, 4)
        row["ln_rmssd_delta"] = log_delta_from_baseline(row.get("rmssd"), baseline.rmssd_ms if baseline else None, 4)
    return rows


def normalized_window_payload(windowed: dict[str, list[float | None]], baseline: BaselineReference | None) -> dict[str, list[float | None]]:
    hr_values = windowed.get("hr_mean") or []
    eda_values = windowed.get("eda_mean") or []
    rmssd_values = windowed.get("rmssd") or []
    phasic_values = windowed.get("eda_phasic_index") or []
    return {
        "hr_delta_bpm": [delta_from_baseline(v, baseline.mean_hr_bpm if baseline else None) for v in hr_values],
        "hr_pct_change": [pct_change_from_baseline(v, baseline.mean_hr_bpm if baseline else None) for v in hr_values],
        "eda_tonic_delta_us": [delta_from_baseline(v, baseline.tonic_eda_us if baseline else None) for v in eda_values],
        "eda_phasic_delta": [delta_from_baseline(v, baseline.phasic_eda_index if baseline else None) for v in phasic_values],
        "ln_rmssd_delta": [log_delta_from_baseline(v, baseline.rmssd_ms if baseline else None) for v in rmssd_values],
    }


def annotate_cleaned_timeseries(points: list[dict[str, Any]], baseline: BaselineReference | None) -> list[dict[str, Any]]:
    if baseline is None:
        return points
    annotated: list[dict[str, Any]] = []
    for point in points:
        row = dict(point)
        hr = row.get("hr_bpm")
        eda = row.get("eda_us")
        row["hr_delta_bpm"] = delta_from_baseline(float(hr), baseline.mean_hr_bpm) if isinstance(hr, (int, float)) else None
        row["hr_pct_change"] = pct_change_from_baseline(float(hr), baseline.mean_hr_bpm) if isinstance(hr, (int, float)) else None
        row["eda_tonic_delta_us"] = delta_from_baseline(float(eda), baseline.tonic_eda_us) if isinstance(eda, (int, float)) else None
        annotated.append(row)
    return annotated


# ─────────────────────────────────────────────────────────────────────────────
# Within-subject normalization (panel-endorsed; see
# contracts/CLEANING_AND_NORMALIZATION_CONTRACT_2026-06-07.md).
#
# Baseline-relative normalization (above) references a baseline *window*. For
# cohort comparison — and for the common request "express each value as the
# difference from the subject's own mean" — we also need whole-session
# within-subject centring. Between-subject EDA/HRV *levels* are dominated by
# individual physiology (skin properties, fitness), so referencing each subject
# to their own distribution is what makes condition contrasts comparable across
# people (Laborde, Mosley & Thayer, 2017; SPR EDA committee / Boucsein et al.,
# 2012). This is the field-standard alternative when no clean baseline window
# exists, and it is reversible because the subject mean/SD are returned too.
# ─────────────────────────────────────────────────────────────────────────────

def within_subject_center(
    values: list[float] | np.ndarray | pd.Series,
    *,
    standardize: bool = False,
    ddof: int = 1,
) -> dict[str, Any]:
    """Center a subject's values on their own mean (the user's stated method).

    Returns the subject's own mean and SD (so the transform is auditable and
    reversible), the centred series (value − subject mean), and — when
    ``standardize`` is True — the z-scored series ((value − mean) / SD).

    Non-finite inputs are ignored in computing the mean/SD and pass through as
    None in the outputs, so a few bad samples cannot silently shift the centre.
    """
    arr = pd.to_numeric(pd.Series(list(values)), errors="coerce").to_numpy(dtype=float)
    finite = arr[np.isfinite(arr)]
    if finite.size == 0:
        return {"subject_mean": None, "subject_sd": None,
                "centered": [None] * len(arr), "z": [None] * len(arr), "n": 0}
    mean = float(finite.mean())
    sd = float(finite.std(ddof=ddof)) if finite.size > ddof else 0.0
    centered = [None if not np.isfinite(v) else round(float(v) - mean, 6) for v in arr]
    z: list[float | None]
    if standardize and sd > 0:
        z = [None if not np.isfinite(v) else round((float(v) - mean) / sd, 6) for v in arr]
    else:
        z = [None] * len(arr)
    return {"subject_mean": round(mean, 6), "subject_sd": round(sd, 6),
            "centered": centered, "z": z, "n": int(finite.size)}


def within_subject_condition_means(
    rows: list[dict[str, Any]],
    measure_key: str,
    condition_key: str = "condition",
    *,
    standardize: bool = False,
) -> dict[str, Any]:
    """Per-condition means expressed relative to the subject's own grand mean.

    `rows` are per-condition (or per-window) records for ONE subject, each with a
    numeric `measure_key` and a label under `condition_key`. Returns, per
    condition, the raw mean and the within-subject-centred mean (raw − subject
    grand mean), plus the subject grand mean/SD. This is the unit a cohort table
    aggregates so that, e.g., plant vs no-plant is compared on each subject's own
    scale before pooling across subjects.
    """
    vals = [r.get(measure_key) for r in rows]
    norm = within_subject_center(
        [v for v in vals if isinstance(v, (int, float))], standardize=standardize
    )
    grand_mean = norm["subject_mean"]
    grand_sd = norm["subject_sd"]
    by_cond: dict[str, list[float]] = {}
    for r in rows:
        v = r.get(measure_key)
        c = str(r.get(condition_key, "")).strip()
        if c and isinstance(v, (int, float)) and np.isfinite(v):
            by_cond.setdefault(c, []).append(float(v))
    out: dict[str, Any] = {"subject_mean": grand_mean, "subject_sd": grand_sd, "conditions": {}}
    for c, vs in by_cond.items():
        raw_mean = float(np.mean(vs))
        entry = {
            "n": len(vs),
            "raw_mean": round(raw_mean, 6),
            "centered_mean": round(raw_mean - grand_mean, 6) if grand_mean is not None else None,
        }
        if standardize and grand_sd:
            entry["z_mean"] = round((raw_mean - grand_mean) / grand_sd, 6) if grand_mean is not None else None
        out["conditions"][c] = entry
    return out

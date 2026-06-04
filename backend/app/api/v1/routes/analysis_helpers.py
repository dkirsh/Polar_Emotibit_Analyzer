"""Shared utilities for analysis route sub-modules.

Contains the in-process session store, helper functions for markers,
timeseries, statistics, and stress decomposition used by both the core
analysis and export endpoints.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from app.services.processing.features import (
    compute_edr_detailed_from_rr_ms,
    rr_source_confidence_for,
    rr_source_note_for,
)

log = logging.getLogger(__name__)


# ----- In-process session store ------------------------------------------
# A researcher running this locally does not need a full PostgreSQL layer
# for the first cut; an in-memory dict plus a JSON snapshot on disk is
# enough to make the "Recent sessions" table work across a browser refresh.
# The snapshot file lives beside the backend's working directory.

_SESSION_STORE: dict[str, dict[str, Any]] = {}
_STORE_PATH = Path(__file__).resolve().parents[4] / "data" / "session_store.json"


def _load_store_from_disk() -> None:
    if _STORE_PATH.exists():
        try:
            _SESSION_STORE.update(json.loads(_STORE_PATH.read_text()))
        except Exception:  # noqa: BLE001
            pass


def _persist_store() -> None:
    try:
        _STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
        # Atomic write: write to temp file then rename, preventing partial
        # writes or clobbering on concurrent requests.
        import tempfile, os
        fd, tmp_path = tempfile.mkstemp(
            dir=_STORE_PATH.parent, suffix=".tmp", prefix="session_store_"
        )
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(_SESSION_STORE, f, indent=2, default=str)
            os.replace(tmp_path, str(_STORE_PATH))
        except BaseException:
            # Clean up temp file on failure
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
    except OSError as exc:
        # The in-memory store is already updated before this function is
        # called, so a local filesystem permission failure should not turn
        # a successful analysis into a failed upload. The session will be
        # available until the backend process exits.
        log.warning("Could not persist session store to %s: %s", _STORE_PATH, exc)


_session_store_initialized = False


def init_session_store() -> None:
    """Explicitly load the session store from disk.

    Called from the FastAPI lifespan handler, NOT at import time.
    Idempotent — safe to call more than once.
    """
    global _session_store_initialized
    if _session_store_initialized:
        return
    _load_store_from_disk()
    _migrate_stored_sessions()
    if _SESSION_STORE:
        _persist_store()
    _session_store_initialized = True


def _migrate_stored_sessions() -> bool:
    """Upgrade older stored sessions to the current frontend contract."""
    changed = False
    for record in _SESSION_STORE.values():
        if _maybe_backfill_edr_proxy(record):
            changed = True
    return changed


def _maybe_backfill_edr_proxy(record: dict[str, Any]) -> bool:
    extended = record.get("extended")
    if not isinstance(extended, dict):
        return False
    rr_source = (
        ((extended.get("psd") or {}).get("rr_source"))
        or ((record.get("result") or {}).get("feature_summary") or {}).get("rr_source")
        or "none"
    )
    rr_source_note = (
        ((record.get("result") or {}).get("feature_summary") or {}).get("rr_source_note")
        or rr_source_note_for(rr_source)
    )

    feature_summary = ((record.get("result") or {}).get("feature_summary") or {})
    changed = False
    if isinstance(feature_summary, dict) and not feature_summary.get("rr_source_note"):
        feature_summary["rr_source_note"] = rr_source_note
        changed = True

    edr_proxy = extended.get("edr_proxy")
    if not isinstance(edr_proxy, dict):
        rr_series = extended.get("rr_series_ms")
        if not isinstance(rr_series, list) or len(rr_series) < 30:
            return changed
        edr_proxy = compute_edr_detailed_from_rr_ms(rr_series)
        if not edr_proxy.get("time_s"):
            return changed
        extended["edr_proxy"] = edr_proxy
        changed = True

    if edr_proxy.get("rr_source") != rr_source:
        edr_proxy["rr_source"] = rr_source
        changed = True
    if edr_proxy.get("rr_source_note") != rr_source_note:
        edr_proxy["rr_source_note"] = rr_source_note
        changed = True
    quality = edr_proxy.get("quality")
    if not isinstance(quality, dict):
        quality = {}
        edr_proxy["quality"] = quality
        changed = True
    signal_confidence = quality.get("signal_confidence")
    source_confidence = rr_source_confidence_for(rr_source)
    overall_confidence = (
        round(float((float(signal_confidence) + source_confidence) / 2.0), 3)
        if isinstance(signal_confidence, (int, float))
        else round(float(source_confidence), 3)
    )
    rounded_source_confidence = round(float(source_confidence), 3)
    if quality.get("source_confidence") != rounded_source_confidence:
        quality["source_confidence"] = rounded_source_confidence
        changed = True
    if quality.get("overall_confidence") != overall_confidence:
        quality["overall_confidence"] = overall_confidence
        changed = True
    if overall_confidence >= 0.8:
        verdict = "strong"
    elif overall_confidence >= 0.6:
        verdict = "usable"
    elif overall_confidence >= 0.4:
        verdict = "weak"
    else:
        verdict = "insufficient"
    if quality.get("verdict") != verdict:
        quality["verdict"] = verdict
        changed = True
    return changed


# NOTE: _load_store_from_disk() is NOT called here at module level.
# It is called explicitly by init_session_store() during FastAPI startup.
# This prevents importing this module from triggering filesystem I/O.


# ----- Helper functions --------------------------------------------------


def _is_zip(raw: bytes) -> bool:
    return raw[:4] == b"PK\x03\x04" or raw[:4] == b"PK\x05\x06"


def _is_zip_bytes(raw: bytes) -> bool:
    return raw[:4] == b"PK\x03\x04" or raw[:4] == b"PK\x05\x06"


def _baseline_window_stress_v2(
    markers_summary: Optional[dict[str, Any]],
    cleaned: pd.DataFrame,
    centers_s: list[float],
    stress_v2: list[float],
) -> float | None:
    """Find the participant's neutral baseline from the baseline interval."""
    if len(centers_s) != len(stress_v2) or len(stress_v2) == 0:
        return None
    origin = None
    if "timestamp_ms" in cleaned.columns and len(cleaned) > 0:
        origin = float(cleaned["timestamp_ms"].iloc[0])

    if markers_summary and origin is not None:
        events = markers_summary.get("event_markers") or []
        onset = next((e for e in events if e.get("event_code") == "baseline_onset"), None)
        offset = next((e for e in events if e.get("event_code") == "baseline_offset"), None)
        if onset and offset:
            try:
                start_s = (float(onset["utc_ms"]) - origin) / 1000.0
                end_s = (float(offset["utc_ms"]) - origin) / 1000.0
                ys = [
                    score
                    for t, score in zip(centers_s, stress_v2, strict=False)
                    if start_s <= t <= end_s and score is not None
                ]
                if ys:
                    return float(sum(ys) / len(ys))
            except (KeyError, TypeError, ValueError):
                pass

    fallback = [score for score in stress_v2[:3] if score is not None]
    if not fallback:
        return None
    return float(sum(fallback) / len(fallback))


def _filter_markers_to_data_range(
    markers_summary: Optional[dict[str, Any]],
    data_min_ms: int,
    data_max_ms: int,
) -> Optional[dict[str, Any]]:
    """Keep only marker events whose timestamps overlap the analyzed data."""
    if not markers_summary or not isinstance(markers_summary.get("event_markers"), list):
        return markers_summary

    kept: list[dict[str, Any]] = []
    for marker in markers_summary["event_markers"]:
        try:
            utc_ms = int(marker.get("utc_ms"))
        except (TypeError, ValueError):
            continue
        if data_min_ms <= utc_ms <= data_max_ms:
            kept.append(marker)

    if not kept:
        return markers_summary

    filtered = dict(markers_summary)
    filtered["event_markers"] = kept
    filtered["codes"] = sorted({str(marker.get("event_code", "")) for marker in kept})
    filtered["n_rows"] = len(kept)
    filtered["source_n_rows"] = markers_summary.get("n_rows", len(markers_summary["event_markers"]))
    return filtered


def _stress_v2_components(
    contributions: dict[str, float | None] | None,
) -> list[dict[str, float | str]]:
    if not contributions:
        return []
    rows: list[dict[str, float | str]] = []
    specs = [
        ("hr", "HR"),
        ("eda", "EDA tonic"),
        ("phasic", "EDA phasic"),
        ("vagal", "Vagal deficit"),
        ("sympathovagal", "LF_nu balance"),
        ("rigidity", "SD1/SD2 rigidity"),
        ("rsa", "RSA deficit"),
    ]
    for key, label in specs:
        contribution = contributions.get(key)
        if contribution is None:
            continue
        rows.append(
            {
                "name": label,
                "component": float(contributions.get(f"{key}_value") or 0.0),
                "contribution": float(contribution),
                "weight": float(contributions.get(f"{key}_weight") or 0.0),
            }
        )
    return rows


def _subsample_timeseries(df: pd.DataFrame, max_points: int = 1000) -> list[dict]:
    """Downsample the cleaned dataframe to ≤ max_points for chart delivery."""
    if df is None or len(df) == 0:
        return []
    if len(df) <= max_points:
        sub = df
    else:
        step = max(1, len(df) // max_points)
        sub = df.iloc[::step]
    cols = [c for c in ("timestamp_ms", "hr_bpm", "eda_us", "acc_x", "acc_y", "acc_z") if c in sub.columns]
    return [{c: (None if pd.isna(row[c]) else float(row[c])) for c in cols} for _, row in sub.iterrows()]


def _series_stats(series: pd.Series) -> dict[str, float]:
    vals = pd.to_numeric(series, errors="coerce").dropna()
    if len(vals) == 0:
        return _empty_stats()
    return {
        "mean": float(vals.mean()),
        "std": float(vals.std(ddof=1)) if len(vals) > 1 else 0.0,
        "min": float(vals.min()),
        "max": float(vals.max()),
        "p05": float(vals.quantile(0.05)),
        "p95": float(vals.quantile(0.95)),
    }


def _empty_stats() -> dict[str, float]:
    return {"mean": 0.0, "std": 0.0, "min": 0.0, "max": 0.0, "p05": 0.0, "p95": 0.0}


def _summary_stats(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"n": 0, "mean": None, "sd": None, "min": None, "max": None}
    mean = sum(values) / len(values)
    sd = None
    if len(values) > 1:
        sd = (sum((value - mean) ** 2 for value in values) / (len(values) - 1)) ** 0.5
    return {
        "n": len(values),
        "mean": round(float(mean), 4),
        "sd": round(float(sd), 4) if sd is not None else None,
        "min": round(float(min(values)), 4),
        "max": round(float(max(values)), 4),
    }


def _markers_overlap_dataframe(markers: list[dict[str, Any]], df: pd.DataFrame) -> bool:
    if df.empty or "timestamp_ms" not in df.columns:
        return False
    times = pd.to_numeric(df["timestamp_ms"], errors="coerce").dropna()
    marker_times = [
        int(marker["utc_ms"])
        for marker in markers
        if isinstance(marker.get("utc_ms"), (int, float)) or str(marker.get("utc_ms", "")).isdigit()
    ]
    if times.empty or not marker_times:
        return False
    data_min = float(times.min())
    data_max = float(times.max())
    return max(marker_times) >= data_min and min(marker_times) <= data_max


def _polar_room_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Return a light-cleaned Polar-only frame for room HR/HRV/RSA stats."""
    work = df.copy()
    if "timestamp_ms" in work.columns:
        work["timestamp_ms"] = pd.to_numeric(work["timestamp_ms"], errors="coerce")
    if "hr_bpm" in work.columns:
        work["hr_bpm"] = pd.to_numeric(work["hr_bpm"], errors="coerce")
        work = work[(work["hr_bpm"] >= 35) & (work["hr_bpm"] <= 220)]
    if "rr_ms" in work.columns:
        work["rr_ms"] = pd.to_numeric(work["rr_ms"], errors="coerce")
        rr_valid = work["rr_ms"].isna() | ((work["rr_ms"] >= 300) & (work["rr_ms"] <= 2000))
        work = work[rr_valid]
    return work.dropna(subset=["timestamp_ms"]).sort_values("timestamp_ms").reset_index(drop=True)

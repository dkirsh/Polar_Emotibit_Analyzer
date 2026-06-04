"""Vernier respiration-belt Excel parser.

Reads Vernier respiration-belt .xlsx exports and converts them to
the internal timeseries schema used by the analysis pipeline.

Expected columns:
  - timestamp: human-readable datetime
  - timestamp_unix: Unix epoch seconds (float)
  - force: respiratory force sensor reading
  - RR: respiratory rate (vendor-computed, used for validation only)
  - event_marker: experimental phase markers
  - condition: experimental condition labels

Output:
  - Uniform 20 Hz respiratory force timeseries (timestamp_ms, value columns)
  - Extracted event markers and conditions as metadata

The respiratory processing pipeline mirrors the Estelita standalone scripts
(RespInPeace ALS baseline removal + cycle detection).
"""

from __future__ import annotations

from io import BytesIO
from typing import Any

import numpy as np
import pandas as pd
import scipy.sparse
import scipy.sparse.linalg
import scipy.signal


# Expected columns in a Vernier respiration-belt export
REQUIRED_VERNIER_COLUMNS = {"timestamp_unix", "force"}
OPTIONAL_VERNIER_COLUMNS = ("timestamp", "RR", "event_marker", "condition")
VERNIER_SAMPLE_RATE_HZ = 20  # target uniform sampling rate


class VernierParseResult:
    """Container for parsed Vernier respiration data."""

    def __init__(
        self,
        timeseries: pd.DataFrame,
        metadata: dict[str, Any],
        event_markers: list[dict[str, Any]],
        respiratory_features: dict[str, Any] | None = None,
    ) -> None:
        self.timeseries = timeseries
        self.metadata = metadata
        self.event_markers = event_markers
        self.respiratory_features = respiratory_features


def parse_vernier_xlsx(file_bytes: bytes) -> VernierParseResult:
    """Parse a Vernier respiration-belt .xlsx file.

    Args:
        file_bytes: Raw bytes of the .xlsx file.

    Returns:
        VernierParseResult with uniform 20 Hz timeseries and metadata.

    Raises:
        ValueError: If required columns are missing or data is insufficient.
    """
    try:
        df = pd.read_excel(BytesIO(file_bytes), sheet_name=0, header=0)
    except Exception as exc:
        raise ValueError(f"Could not read Vernier Excel file: {exc}") from exc

    # Strip whitespace from column names
    df.columns = [c.strip() for c in df.columns]

    # Validate required columns
    present = set(df.columns)
    missing = REQUIRED_VERNIER_COLUMNS - present
    if missing:
        raise ValueError(
            f"Vernier file missing required columns: {sorted(missing)}. "
            f"Found: {sorted(present)}"
        )

    if len(df) < 10:
        raise ValueError(
            f"Vernier file has only {len(df)} rows; need at least 10 for analysis."
        )

    # Parse timestamps and force
    t = pd.to_numeric(df["timestamp_unix"], errors="coerce").values.astype(float)
    force = pd.to_numeric(df["force"], errors="coerce").values.astype(float)

    # Drop NaN timestamps
    valid_mask = np.isfinite(t) & np.isfinite(force)
    if valid_mask.sum() < 10:
        raise ValueError(
            "Vernier file has too few valid (non-NaN) timestamp/force samples."
        )
    t = t[valid_mask]
    force = force[valid_mask]

    t0 = float(t[0])
    elapsed = t - t0
    dur = float(elapsed[-1])

    if dur <= 0:
        raise ValueError("Vernier recording has zero or negative duration.")

    # Resample to uniform 20 Hz grid
    fs = VERNIER_SAMPLE_RATE_HZ
    tu = np.arange(0.0, dur, 1.0 / fs)
    force_u = np.interp(tu, elapsed, force)
    n_samples = len(force_u)

    # Convert to millisecond timestamps (relative to recording start)
    timestamp_ms = np.round(tu * 1000.0).astype(int)

    # Build output timeseries
    timeseries = pd.DataFrame({
        "timestamp_ms": timestamp_ms,
        "force": force_u,
        "elapsed_s": np.round(tu, 4),
    })

    # Extract event markers
    event_markers: list[dict[str, Any]] = []
    if "event_marker" in df.columns:
        ev_df = df[valid_mask].copy()
        ev_df["_elapsed"] = elapsed
        # Find transitions
        ev = ev_df["event_marker"].values
        prev = None
        for i, marker in enumerate(ev):
            marker_str = str(marker).strip() if pd.notna(marker) else ""
            if marker_str and marker_str != prev:
                event_markers.append({
                    "event_code": marker_str,
                    "elapsed_s": round(float(ev_df["_elapsed"].iloc[i]), 3),
                    "timestamp_unix": round(float(t[i]), 3),
                })
            prev = marker_str

    # Extract conditions
    conditions: list[str] = []
    if "condition" in df.columns:
        conditions = sorted(
            set(
                str(c).strip()
                for c in df["condition"].dropna().unique()
                if str(c).strip()
            )
        )

    # RR validation from vendor column
    rr_validation: dict[str, Any] | None = None
    if "RR" in df.columns:
        rr = pd.to_numeric(df["RR"], errors="coerce").dropna()
        rr = rr[(rr > 0) & (rr < 60)]
        if len(rr) > 0:
            rr_validation = {
                "vendor_rr_n": int(len(rr)),
                "vendor_rr_median": round(float(rr.median()), 2),
                "vendor_rr_mean": round(float(rr.mean()), 2),
            }

    # Parse original timestamps for metadata
    recording_start: str | None = None
    if "timestamp" in df.columns:
        try:
            ts = pd.to_datetime(df["timestamp"].iloc[0])
            recording_start = str(ts)
        except Exception:
            pass

    metadata = {
        "source_type": "vernier_respiration_belt",
        "n_raw_samples": int(valid_mask.sum()),
        "n_resampled": n_samples,
        "sample_rate_hz": fs,
        "duration_s": round(dur, 2),
        "duration_min": round(dur / 60.0, 2),
        "recording_start": recording_start,
        "unix_epoch_start": round(t0, 3),
        "conditions": conditions,
        "n_event_markers": len(event_markers),
        "columns_present": sorted(present),
        "rr_validation": rr_validation,
    }

    return VernierParseResult(
        timeseries=timeseries,
        metadata=metadata,
        event_markers=event_markers,
    )


# ---- Respiratory processing (ALS baseline + cycle detection) ---------------
# Mirrors the Estelita RespInPeace pipeline from rip.py.


def _baseline_als(
    signal: np.ndarray,
    lam: float = 1e10,
    p: float = 0.01,
    niter: int = 10,
) -> np.ndarray:
    """Asymmetric Least Squares baseline estimation.

    Identical to rip.py Resp.baseline_als.
    """
    n = len(signal)
    D = scipy.sparse.diags([1, -2, 1], [0, -1, -2], shape=(n, n - 2))
    w = np.ones(n)
    for _ in range(niter):
        W = scipy.sparse.spdiags(w, 0, n, n)
        Z = W + lam * D.dot(D.transpose())
        z = scipy.sparse.linalg.spsolve(Z, w * signal)
        w = p * (signal > z) + (1 - p) * (signal < z)
    return z


def _peakdetect_simple(
    y: np.ndarray,
    lookahead: int = 1,
    delta: float = 1.0,
) -> tuple[list[int], list[int]]:
    """Simplified peak detection matching peakdetect.py's main function.

    Returns (max_peaks, min_peaks) as lists of indices.
    """
    max_peaks: list[int] = []
    min_peaks: list[int] = []
    dump: list[bool] = []

    length = len(y)
    mn, mx = np.inf, -np.inf
    mxpos = mnpos = 0

    for index in range(length - lookahead):
        val = y[index]
        if val > mx:
            mx = val
            mxpos = index
        if val < mn:
            mn = val
            mnpos = index

        if val < mx - delta and mx != np.inf:
            if y[index : index + lookahead].max() < mx:
                max_peaks.append(mxpos)
                dump.append(True)
                mx = np.inf
                mn = np.inf
                if index + lookahead >= length:
                    break
                continue

        if val > mn + delta and mn != -np.inf:
            if y[index : index + lookahead].min() > mn:
                min_peaks.append(mnpos)
                dump.append(False)
                mn = -np.inf
                mx = -np.inf
                if index + lookahead >= length:
                    break

    # Remove false first hit
    if dump:
        if dump[0]:
            if max_peaks:
                max_peaks.pop(0)
        else:
            if min_peaks:
                min_peaks.pop(0)

    return max_peaks, min_peaks


def compute_respiratory_features(
    force_uniform: np.ndarray,
    fs: int = VERNIER_SAMPLE_RATE_HZ,
) -> dict[str, Any]:
    """Run the RespInPeace-equivalent pipeline on a uniformly sampled force signal.

    Steps:
      1. ALS baseline removal
      2. Moving z-score normalization
      3. Peak/trough detection (cycle finding)
      4. Per-breath feature extraction
      5. Summary statistics

    Args:
        force_uniform: Uniformly sampled force signal at `fs` Hz.
        fs: Sampling frequency in Hz.

    Returns:
        Dictionary with respiratory features:
          - n_breaths: total breath count
          - resp_rate_bpm: mean respiratory rate
          - mean_cycle_dur_s: mean cycle duration
          - ie_ratio_mean: mean I:E ratio
          - per_breath: list of per-breath feature dicts
          - holds: placeholder (empty list; full hold detection requires tgt)
    """
    if len(force_uniform) < fs * 5:
        return {
            "n_breaths": 0,
            "resp_rate_bpm": None,
            "mean_cycle_dur_s": None,
            "ie_ratio_mean": None,
            "duty_cycle_mean": None,
            "per_breath": [],
            "holds": [],
            "error": "Recording too short for respiratory analysis (< 5 seconds).",
        }

    # Step 1: ALS baseline removal
    baseline = _baseline_als(force_uniform)
    detrended = force_uniform - baseline

    # Step 2: Moving z-score for peak detection
    win_len = 10 * fs  # 10-second window
    rolling = pd.Series(detrended).rolling(win_len, center=True)
    window_mean = rolling.mean().values
    window_std = rolling.std().values
    # Replace NaN edges with global stats
    global_mean = float(np.nanmean(detrended))
    global_std = float(np.nanstd(detrended))
    window_mean = np.where(np.isfinite(window_mean), window_mean, global_mean)
    window_std = np.where(np.isfinite(window_std) & (window_std > 0), window_std, global_std)
    resp_scaled = (detrended - window_mean) / (window_std + 1e-12)

    # Step 3: Peak/trough detection
    peaks, troughs = _peakdetect_simple(resp_scaled, lookahead=1, delta=1.0)

    if len(peaks) < 2 or len(troughs) < 2:
        return {
            "n_breaths": 0,
            "resp_rate_bpm": None,
            "mean_cycle_dur_s": None,
            "ie_ratio_mean": None,
            "duty_cycle_mean": None,
            "per_breath": [],
            "holds": [],
            "error": "Could not detect respiratory cycles.",
        }

    # Ensure we start with inhalation (trough) and end with exhalation (trough)
    # Convention: peaks are end-of-inhalation, troughs are end-of-exhalation
    if peaks[0] < troughs[0]:
        peaks = peaks[1:]
    if peaks[-1] > troughs[-1]:
        peaks = peaks[:-1]

    n_usable = min(len(peaks), len(troughs) - 1)
    if n_usable < 1:
        return {
            "n_breaths": 0,
            "resp_rate_bpm": None,
            "mean_cycle_dur_s": None,
            "ie_ratio_mean": None,
            "duty_cycle_mean": None,
            "per_breath": [],
            "holds": [],
            "error": "Insufficient peaks/troughs for cycle extraction.",
        }

    # Step 4: Per-breath feature extraction
    per_breath: list[dict[str, Any]] = []
    for k in range(n_usable):
        tr1_idx = troughs[k]
        pk_idx = peaks[k]
        tr2_idx = troughs[k + 1]

        tr1_s = tr1_idx / fs
        pk_s = pk_idx / fs
        tr2_s = tr2_idx / fs

        inhale = pk_s - tr1_s
        exhale = tr2_s - pk_s
        cyc = tr2_s - tr1_s

        if cyc <= 0:
            continue

        ie_ratio = round(inhale / exhale, 4) if exhale > 0 else None
        amplitude = float(detrended[pk_idx] - detrended[tr1_idx])

        per_breath.append({
            "breath": k + 1,
            "start_s": round(tr1_s, 3),
            "peak_s": round(pk_s, 3),
            "end_s": round(tr2_s, 3),
            "inhale_dur_s": round(inhale, 3),
            "exhale_dur_s": round(exhale, 3),
            "cycle_dur_s": round(cyc, 3),
            "rate_bpm": round(60.0 / cyc, 3),
            "ie_ratio": ie_ratio,
            "duty_cycle": round(inhale / cyc, 4),
            "amplitude": round(amplitude, 5),
        })

    if not per_breath:
        return {
            "n_breaths": 0,
            "resp_rate_bpm": None,
            "mean_cycle_dur_s": None,
            "ie_ratio_mean": None,
            "duty_cycle_mean": None,
            "per_breath": [],
            "holds": [],
        }

    # Step 5: Summary statistics
    cycles = [b["cycle_dur_s"] for b in per_breath]
    ie_ratios = [b["ie_ratio"] for b in per_breath if b["ie_ratio"] is not None]
    duty_cycles = [b["duty_cycle"] for b in per_breath]
    mean_cycle = float(np.mean(cycles))

    return {
        "n_breaths": len(per_breath),
        "resp_rate_bpm": round(60.0 / mean_cycle, 2) if mean_cycle > 0 else None,
        "mean_cycle_dur_s": round(mean_cycle, 3),
        "sd_cycle_dur_s": round(float(np.std(cycles, ddof=1) if len(cycles) > 1 else 0.0), 3),
        "ie_ratio_mean": round(float(np.mean(ie_ratios)), 3) if ie_ratios else None,
        "duty_cycle_mean": round(float(np.mean(duty_cycles)), 3) if duty_cycles else None,
        "per_breath": per_breath,
        "holds": [],  # Full hold detection requires the tgt library
    }


def parse_and_analyze_vernier(file_bytes: bytes) -> VernierParseResult:
    """Parse a Vernier .xlsx file and compute respiratory features.

    Convenience wrapper combining parse_vernier_xlsx and
    compute_respiratory_features.
    """
    result = parse_vernier_xlsx(file_bytes)
    features = compute_respiratory_features(
        result.timeseries["force"].values,
        fs=VERNIER_SAMPLE_RATE_HZ,
    )
    result.respiratory_features = features
    return result

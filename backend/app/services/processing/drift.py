"""Drift estimation and correction utilities.

Supports both simple two-anchor linear drift and multi-anchor piecewise
linear drift correction for improved accuracy over long sessions.
"""

from __future__ import annotations

import numpy as np

from app.models.signals import DriftModel, PiecewiseDriftModel


# ---------------------------------------------------------------------------
# Simple two-anchor linear drift (backward compatible)
# ---------------------------------------------------------------------------

def estimate_drift(source_ts: list[int], reference_ts: list[int]) -> DriftModel:
    """Estimate linear drift from source clock to reference clock.

    Uses first and last anchor timestamps.
    """
    if len(source_ts) < 2 or len(reference_ts) < 2:
        return DriftModel(slope=1.0, intercept_ms=0.0)

    s0, s1 = source_ts[0], source_ts[-1]
    r0, r1 = reference_ts[0], reference_ts[-1]
    if s1 == s0:
        return DriftModel(slope=1.0, intercept_ms=float(r0 - s0))

    slope = (r1 - r0) / (s1 - s0)
    intercept = r0 - slope * s0
    return DriftModel(slope=float(slope), intercept_ms=float(intercept))


def apply_drift(ts_ms: list[int], model: DriftModel) -> list[int]:
    """Apply drift model to timestamp list."""
    return [int(model.slope * t + model.intercept_ms) for t in ts_ms]


# ---------------------------------------------------------------------------
# Multi-anchor piecewise linear drift
# ---------------------------------------------------------------------------

def estimate_piecewise_drift(
    source_ts: list[int],
    reference_ts: list[int],
    *,
    anchor_interval_ms: int = 60_000,
    sync_markers: list[tuple[int, int]] | None = None,
) -> PiecewiseDriftModel:
    """Estimate piecewise linear drift using multiple anchor points.

    V2.1 [Repair 3.3]: Added optional sync_markers parameter.

    Divides the overlapping time range into segments of *anchor_interval_ms*
    and fits a separate linear model to each segment.  This handles
    nonlinear drift caused by temperature-dependent crystal oscillator
    behaviour over long sessions.

    When fewer than 3 anchor pairs are available, falls back to a single
    global linear segment.

    Parameters
    ----------
    source_ts : list[int]
        Timestamps from the source clock (e.g. Polar) in ms.
    reference_ts : list[int]
        Timestamps from the reference clock (e.g. EmotiBit) in ms.
    anchor_interval_ms : int
        Target width of each piecewise segment, default 60 seconds.
    sync_markers : list[tuple[int, int]] | None
        V2.1 NEW: Explicit synchronization event pairs (source_ms,
        reference_ms) from LSL, WiFi timesync, or manual markers.
        When provided, used as anchor points instead of inferring
        from overlapping data. More accurate when available.

    Returns
    -------
    PiecewiseDriftModel
    """
    # V2.1 [Repair 3.3]: Use explicit sync markers when available
    if sync_markers and len(sync_markers) >= 2:
        src_m = [float(m[0]) for m in sync_markers]
        ref_m = [float(m[1]) for m in sync_markers]
        segments: list[DriftModel] = []
        breakpoints: list[int] = []
        for i in range(len(src_m) - 1):
            s0, s1 = src_m[i], src_m[i + 1]
            r0, r1 = ref_m[i], ref_m[i + 1]
            if s1 == s0:
                slope, intercept = 1.0, r0 - s0
            else:
                slope = (r1 - r0) / (s1 - s0)
                intercept = r0 - slope * s0
            segments.append(DriftModel(slope=slope, intercept_ms=intercept))
            if i < len(src_m) - 2:
                breakpoints.append(int(src_m[i + 1]))
        return PiecewiseDriftModel(segments=segments, breakpoints_ms=breakpoints)

    if len(source_ts) < 2 or len(reference_ts) < 2:
        return PiecewiseDriftModel(
            segments=[DriftModel(slope=1.0, intercept_ms=0.0)],
            breakpoints_ms=[],
        )

    src = np.array(source_ts, dtype=float)
    ref = np.array(reference_ts, dtype=float)

    # V2.1 FIX (new finding): Pair by NEAREST TIMESTAMP, not by index.
    # V2.0 used min(len(src), len(ref)) and paired by array position.
    # This fails when devices have different sampling rates (e.g., Polar
    # at 1 Hz and EmotiBit at 15 Hz): index 100 of Polar = 100s, but
    # index 100 of EmotiBit = 6.7s. Slope becomes ~0.067 instead of ~1.0.
    #
    # Fix: For each source timestamp, find the nearest reference timestamp.
    # This produces properly aligned pairs regardless of sampling rate.
    ref_sorted = np.sort(ref)
    nearest_idx = np.searchsorted(ref_sorted, src, side="left")
    nearest_idx = np.clip(nearest_idx, 0, len(ref_sorted) - 1)

    # For each source ts, pick the closer of the two bracketing ref timestamps
    paired_ref = np.empty_like(src)
    for i, (s_val, ni) in enumerate(zip(src, nearest_idx)):
        candidates = []
        if ni > 0:
            candidates.append(ni - 1)
        candidates.append(ni)
        if ni < len(ref_sorted) - 1:
            candidates.append(ni + 1)
        best = min(candidates, key=lambda c: abs(ref_sorted[c] - s_val))
        paired_ref[i] = ref_sorted[best]

    n = len(src)

    # If too few points, use global linear fit
    if n < 4:
        m = estimate_drift(source_ts, reference_ts)
        return PiecewiseDriftModel(segments=[m], breakpoints_ms=[])

    # Build anchor pairs at regular intervals through the overlap
    s_min, s_max = float(src[0]), float(src[-1])
    span = s_max - s_min
    if span <= 0:
        m = estimate_drift(source_ts, reference_ts)
        return PiecewiseDriftModel(segments=[m], breakpoints_ms=[])

    n_segments = max(1, int(span / anchor_interval_ms))
    boundaries = np.linspace(s_min, s_max, n_segments + 1)

    segments: list[DriftModel] = []
    breakpoints: list[int] = []

    for i in range(n_segments):
        lo, hi = boundaries[i], boundaries[i + 1]
        if i < n_segments - 1:
            mask = (src >= lo) & (src < hi)
        else:
            mask = (src >= lo) & (src <= hi)

        seg_src = src[mask]
        seg_ref = paired_ref[mask]

        if len(seg_src) < 2:
            # Reuse previous segment if this one has too few points
            if segments:
                segments.append(segments[-1])
            else:
                segments.append(DriftModel(slope=1.0, intercept_ms=0.0))
        else:
            s0, s1 = float(seg_src[0]), float(seg_src[-1])
            r0, r1 = float(seg_ref[0]), float(seg_ref[-1])
            if s1 == s0:
                slope = 1.0
                intercept = r0 - s0
            else:
                slope = (r1 - r0) / (s1 - s0)
                intercept = r0 - slope * s0
            segments.append(DriftModel(slope=slope, intercept_ms=intercept))

        if i < n_segments - 1:
            breakpoints.append(int(boundaries[i + 1]))

    return PiecewiseDriftModel(segments=segments, breakpoints_ms=breakpoints)


def apply_piecewise_drift(
    ts_ms: list[int],
    model: PiecewiseDriftModel,
) -> list[int]:
    """Apply piecewise drift correction to a list of timestamps."""
    if model.is_trivial:
        return apply_drift(ts_ms, model.segments[0])

    result: list[int] = []
    for t in ts_ms:
        # Find the segment this timestamp belongs to
        seg_idx = 0
        for bp in model.breakpoints_ms:
            if t >= bp:
                seg_idx += 1
            else:
                break
        seg_idx = min(seg_idx, len(model.segments) - 1)
        seg = model.segments[seg_idx]
        result.append(int(seg.slope * t + seg.intercept_ms))
    return result


# ---------------------------------------------------------------------------
# Cross-correlation offset estimation
# ---------------------------------------------------------------------------

def estimate_offset_by_xcorr(
    series_a: list[float],
    series_b: list[float],
    sample_interval_ms: float = 1000.0,
    max_lag_samples: int = 30,
) -> float:
    """Estimate temporal offset between two time series via cross-correlation.

    Useful for estimating the residual lag between two HR signals
    (e.g. EmotiBit PPG-derived HR and Polar ECG-derived HR) after
    initial drift correction.  The dominant lag captures both residual
    clock error and pulse transit time.

    Parameters
    ----------
    series_a, series_b : list[float]
        Two time series of equal length (or will be truncated to min length).
    sample_interval_ms : float
        Sampling interval in ms (default 1000 = 1 Hz).
    max_lag_samples : int
        Maximum lag to search in both directions.

    Returns
    -------
    float
        Estimated offset in milliseconds (positive = B lags A).
    """
    a = np.array(series_a, dtype=float)
    b = np.array(series_b, dtype=float)
    n = min(len(a), len(b))
    if n < 10:
        return 0.0

    a, b = a[:n], b[:n]
    # ddof=0 (population std) is correct here: we are z-scoring the full
    # observed trace for cross-correlation, not estimating a population
    # parameter from a sample.
    a = (a - np.mean(a)) / (np.std(a) or 1.0)
    b = (b - np.mean(b)) / (np.std(b) or 1.0)

    max_lag = min(max_lag_samples, n - 1)
    best_lag = 0
    best_corr = -np.inf

    for lag in range(-max_lag, max_lag + 1):
        if lag >= 0:
            corr = float(np.mean(a[lag:] * b[: n - lag]))
        else:
            corr = float(np.mean(a[: n + lag] * b[-lag:]))
        if corr > best_corr:
            best_corr = corr
            best_lag = lag

    return float(best_lag * sample_interval_ms)

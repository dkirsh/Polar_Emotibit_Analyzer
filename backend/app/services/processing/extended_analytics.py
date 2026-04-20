"""Extended analytics: decomposed stress, windowed time series, spectral details.

Version: 2.1 (NEW)

PURPOSE: The V2.0/2.1 pipeline produces a single stress score and aggregate
features. For scientific interpretation, researchers need to see:

  1. COMPONENT DECOMPOSITION: Which channels drive the stress composite?
     A score of 0.6 could mean "high HR + normal EDA" or "normal HR + high EDA".
     These have different autonomic interpretations (cardiac vs electrodermal).

  2. TEMPORAL DYNAMICS: How do features evolve over the session?
     Aggregate RMSSD obscures whether HRV dropped suddenly during a stressor
     or declined gradually over 5 minutes.

  3. SPECTRAL DETAILS: The LF/HF ratio is a single number that loses the
     full PSD shape. Researchers inspecting sympathovagal balance need to
     see the actual spectrum.

  4. AUTONOMIC BALANCE TRAJECTORY: LF/HF over time (windowed) reveals
     autonomic state transitions that aggregate LF/HF cannot detect.

DESIGN DECISION — Window sizes:
    Physiological signals have different time constants:
    - HR: responds in 1-2 beats (~1-2s)
    - EDA tonic: time constant ~10-30s (Boucsein, 2012)
    - HRV (RMSSD): needs ~30s minimum for stable estimate (Munoz et al., 2015)
    - HRV (LF/HF): needs ~120s minimum (Task Force, 1996)

    We use 60s windows with 30s overlap for time-domain features (HR, EDA,
    RMSSD). For spectral features we use 120s windows with 60s overlap.
    These are configurable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd
from scipy.signal import welch as scipy_welch

from app.services.processing.features import _get_rr_intervals
from app.services.processing.stress import compute_stress_score


# ---------------------------------------------------------------------------
# Stress component decomposition
# ---------------------------------------------------------------------------

@dataclass
class StressDecomposition:
    """Decomposed stress score showing each component's contribution."""
    total_score: float = 0.0
    hr_component: float = 0.0
    hr_contribution: float = 0.0       # hr_component * weight
    eda_component: float = 0.0
    eda_contribution: float = 0.0
    phasic_component: float = 0.0
    phasic_contribution: float = 0.0
    hrv_protection: float = 0.0
    hrv_contribution: float = 0.0     # (1-hrv_protection) * weight
    dominant_driver: str = ""           # which channel contributes most


def decompose_stress(
    rmssd_ms: float,
    mean_hr_bpm: float,
    eda_mean_us: float,
    eda_phasic_index: float,
) -> StressDecomposition:
    """Decompose stress score into channel-level contributions.

    Shows exactly how much each physiological channel contributes to
    the composite, enabling interpretation like:
      "Stress is 0.65, driven primarily by HR (0.28/0.35 max) with
       moderate EDA contribution (0.18/0.35 max) and low HRV protection."
    """
    hr_c = max(0.0, min(1.0, (mean_hr_bpm - 60.0) / 60.0))
    eda_c = max(0.0, min(1.0, eda_mean_us / 20.0))
    phasic_c = max(0.0, min(1.0, eda_phasic_index / 2.5))
    hrv_prot = min(rmssd_ms, 80.0) / 80.0

    hr_contrib = 0.35 * hr_c
    eda_contrib = 0.35 * eda_c
    phasic_contrib = 0.20 * phasic_c
    hrv_contrib = 0.10 * (1.0 - hrv_prot)

    total = hr_contrib + eda_contrib + phasic_contrib + hrv_contrib
    total = max(0.0, min(1.0, total))

    contributions = {
        "HR": hr_contrib,
        "EDA_tonic": eda_contrib,
        "EDA_phasic": phasic_contrib,
        "HRV_deficit": hrv_contrib,
    }
    dominant = max(contributions, key=contributions.get)

    return StressDecomposition(
        total_score=total,
        hr_component=hr_c,
        hr_contribution=hr_contrib,
        eda_component=eda_c,
        eda_contribution=eda_contrib,
        phasic_component=phasic_c,
        phasic_contribution=phasic_contrib,
        hrv_protection=hrv_prot,
        hrv_contribution=hrv_contrib,
        dominant_driver=dominant,
    )


# ---------------------------------------------------------------------------
# Windowed time-series features
# ---------------------------------------------------------------------------

@dataclass
class WindowedFeatures:
    """Time series of features computed in sliding windows."""
    window_centers_s: list[float] = field(default_factory=list)
    hr_mean: list[float] = field(default_factory=list)
    hr_std: list[float] = field(default_factory=list)
    eda_mean: list[float] = field(default_factory=list)
    rmssd: list[float] = field(default_factory=list)
    stress: list[float] = field(default_factory=list)
    # Stress decomposition per window
    hr_contribution: list[float] = field(default_factory=list)
    eda_contribution: list[float] = field(default_factory=list)
    hrv_contribution: list[float] = field(default_factory=list)


def compute_windowed_features(
    df: pd.DataFrame,
    *,
    window_s: float = 60.0,
    step_s: float = 30.0,
) -> WindowedFeatures:
    """Compute physiological features in sliding windows.

    Parameters
    ----------
    df : DataFrame
        Cleaned, synchronized data with timestamp_ms, hr_bpm, eda_us.
    window_s : float
        Window width in seconds (default 60).
    step_s : float
        Step size in seconds (default 30, giving 50% overlap).
    """
    result = WindowedFeatures()

    if len(df) < 2 or "timestamp_ms" not in df.columns:
        return result

    ts = df["timestamp_ms"].to_numpy(dtype=float)
    t_start = ts[0]
    t_end = ts[-1]

    window_ms = window_s * 1000
    step_ms = step_s * 1000
    center = t_start + window_ms / 2

    while center + window_ms / 2 <= t_end:
        lo = center - window_ms / 2
        hi = center + window_ms / 2
        mask = (ts >= lo) & (ts < hi)
        chunk = df.loc[mask]

        if len(chunk) < 5:
            center += step_ms
            continue

        hr = chunk["hr_bpm"].to_numpy(dtype=float)
        eda = chunk["eda_us"].to_numpy(dtype=float)

        mean_hr = float(np.mean(hr))
        mean_eda = float(np.mean(eda))
        std_hr = float(np.std(hr, ddof=1)) if len(hr) > 1 else 0.0

        # Window RMSSD from RR intervals
        rr, _ = _get_rr_intervals(chunk)
        rmssd_val = 0.0
        if len(rr) >= 3:
            diff = np.diff(rr)
            rmssd_val = float(np.sqrt(np.mean(diff ** 2)))

        # Phasic EDA in this window
        phasic = float(np.mean(np.abs(np.diff(eda)))) if len(eda) > 1 else 0.0

        # Stress decomposition
        decomp = decompose_stress(rmssd_val, mean_hr, mean_eda, phasic)

        result.window_centers_s.append(float((center - t_start) / 1000))
        result.hr_mean.append(mean_hr)
        result.hr_std.append(std_hr)
        result.eda_mean.append(mean_eda)
        result.rmssd.append(rmssd_val)
        result.stress.append(decomp.total_score)
        result.hr_contribution.append(decomp.hr_contribution)
        result.eda_contribution.append(decomp.eda_contribution)
        result.hrv_contribution.append(decomp.hrv_contribution)

        center += step_ms

    return result


# ---------------------------------------------------------------------------
# Windowed spectral features (LF/HF trajectory)
# ---------------------------------------------------------------------------

@dataclass
class SpectralTrajectory:
    """LF/HF ratio over time — reveals autonomic state transitions."""
    window_centers_s: list[float] = field(default_factory=list)
    lf_power: list[Optional[float]] = field(default_factory=list)
    hf_power: list[Optional[float]] = field(default_factory=list)
    lf_hf_ratio: list[Optional[float]] = field(default_factory=list)


def compute_spectral_trajectory(
    df: pd.DataFrame,
    *,
    window_s: float = 120.0,
    step_s: float = 60.0,
    resample_hz: float = 4.0,
) -> SpectralTrajectory:
    """Compute LF/HF ratio in sliding windows.

    Uses 120s windows (minimum for LF estimation) with 60s steps.
    Returns None for windows where LF or HF cannot be estimated.
    """
    result = SpectralTrajectory()
    _integrate = getattr(np, "trapezoid", None) or getattr(np, "trapz")

    if len(df) < 2 or "timestamp_ms" not in df.columns:
        return result

    ts = df["timestamp_ms"].to_numpy(dtype=float)
    t_start, t_end = ts[0], ts[-1]
    window_ms = window_s * 1000
    step_ms = step_s * 1000
    center = t_start + window_ms / 2

    while center + window_ms / 2 <= t_end:
        lo = center - window_ms / 2
        hi = center + window_ms / 2
        mask = (ts >= lo) & (ts < hi)
        chunk = df.loc[mask]

        rr, _ = _get_rr_intervals(chunk)

        lf_val, hf_val, ratio_val = None, None, None

        if len(rr) >= 30:
            try:
                t_ms = np.cumsum(rr)
                t_s = (t_ms - t_ms[0]) / 1000.0
                dur = t_s[-1] - t_s[0]

                if dur >= window_s * 0.8:  # At least 80% of window covered
                    t_uniform = np.arange(t_s[0], t_s[-1], 1.0 / resample_hz)
                    rr_uniform = np.interp(t_uniform, t_s, rr)
                    rr_detrended = rr_uniform - np.mean(rr_uniform)

                    nperseg = min(128, len(rr_detrended))
                    freqs, psd = scipy_welch(
                        rr_detrended, fs=resample_hz, window="hann",
                        nperseg=nperseg, noverlap=nperseg // 2)

                    lf_mask = (freqs >= 0.04) & (freqs < 0.15)
                    hf_mask = (freqs >= 0.15) & (freqs < 0.40)

                    if np.any(lf_mask) and dur >= 120:
                        lf_val = float(_integrate(psd[lf_mask], freqs[lf_mask]))
                    if np.any(hf_mask) and dur >= 60:
                        hf_val = float(_integrate(psd[hf_mask], freqs[hf_mask]))
                    if lf_val is not None and hf_val is not None and hf_val > 0:
                        ratio_val = lf_val / hf_val
            except Exception:
                pass

        result.window_centers_s.append(float((center - t_start) / 1000))
        result.lf_power.append(round(lf_val, 2) if lf_val is not None else None)
        result.hf_power.append(round(hf_val, 2) if hf_val is not None else None)
        result.lf_hf_ratio.append(round(ratio_val, 4) if ratio_val is not None else None)

        center += step_ms

    return result


# ---------------------------------------------------------------------------
# Full PSD for visualization
# ---------------------------------------------------------------------------

def compute_full_psd(
    df: pd.DataFrame,
    resample_hz: float = 4.0,
) -> dict:
    """Compute full power spectral density for visualization.

    Returns frequencies and PSD values suitable for plotting, plus
    band boundaries for visual annotation.
    """
    rr, source = _get_rr_intervals(df)
    if len(rr) < 30:
        return {"frequencies_hz": [], "psd_ms2_hz": [], "rr_source": source, "bands": {}}

    _integrate = getattr(np, "trapezoid", None) or getattr(np, "trapz")

    try:
        t_ms = np.cumsum(rr)
        t_s = (t_ms - t_ms[0]) / 1000.0
        t_uniform = np.arange(t_s[0], t_s[-1], 1.0 / resample_hz)
        rr_uniform = np.interp(t_uniform, t_s, rr)
        rr_detrended = rr_uniform - np.mean(rr_uniform)

        nperseg = min(256, len(rr_detrended))
        freqs, psd = scipy_welch(
            rr_detrended, fs=resample_hz, window="hann",
            nperseg=nperseg, noverlap=nperseg // 2)

        bands = {
            "vlf": {"lo": 0.003, "hi": 0.04, "color": "#8B5CF6", "label": "VLF"},
            "lf": {"lo": 0.04, "hi": 0.15, "color": "#3B82F6", "label": "LF"},
            "hf": {"lo": 0.15, "hi": 0.40, "color": "#10B981", "label": "HF"},
        }

        return {
            "frequencies_hz": freqs.tolist(),
            "psd_ms2_hz": psd.tolist(),
            "rr_source": source,
            "bands": bands,
        }
    except Exception:
        return {"frequencies_hz": [], "psd_ms2_hz": [], "rr_source": source, "bands": {}}

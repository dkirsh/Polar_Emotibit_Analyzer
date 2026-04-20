"""Feature extraction for HRV and EDA.

Version: 2.1 (repaired)
Changes from V2.0:
  - [Repair 2.1] Welch's method replaces simple periodogram for freq HRV
  - [Repair 2.1] Per-band minimum duration enforced (VLF>=300s, LF>=120s, HF>=60s)

DESIGN DECISION — Welch's method:
    The simple periodogram (DFT-based PSD) is an inconsistent estimator:
    its variance does NOT decrease as record length increases (Priestley,
    1981). Welch's method reduces variance by segmenting, windowing, and
    averaging. The Task Force (1996) explicitly recommends Welch or AR
    modeling. Every major HRV toolkit (Kubios, PhysioNet HRV Toolkit,
    pyHRV) uses Welch by default.

    Skeptic's FAQ: "The periodogram is unbiased. Why does variance matter?"
    Answer: An unbiased estimator with infinite variance is useless for a
    single realization (which is all we have — one session). Welch trades
    a small amount of frequency resolution for dramatically reduced variance.
    For HRV bands that are 0.11 Hz wide (LF: 0.04-0.15), the resolution
    loss from 256-sample segments at 4 Hz (df = 0.016 Hz) is negligible.

    Ref: Welch (1967). IEEE Trans Audio Electroacoustics, 15(2), 70-73.
    Ref: Task Force ESC/NASPE (1996). Circulation, 93(5), 1043-1065.

DESIGN DECISION — Per-band minimum duration:
    The Task Force (1996) states that VLF estimation requires recordings
    of at least 5 minutes (300s) because the VLF band (0.003-0.04 Hz)
    has oscillation periods of 25-333 seconds. You need multiple full
    cycles for a meaningful spectral estimate. V2.0 required only 120 RR
    intervals (~30s), meaning VLF values from short recordings were noise.

    We enforce: VLF >= 300s, LF >= 120s, HF >= 60s. Bands that don't
    meet their minimum return None instead of a garbage number.

    Ref: Shaffer & Ginsberg (2017). Front Public Health, 5, 258.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.signal import welch as scipy_welch
from scipy.signal import butter, filtfilt, find_peaks


# ---------------------------------------------------------------------------
# RR interval extraction
# ---------------------------------------------------------------------------

def _get_rr_intervals(df: pd.DataFrame) -> tuple[np.ndarray, str]:
    """Extract RR intervals, preferring native Polar data.

    V2.1 FIX (found during integration testing): When sync merge matches
    each 1 Hz Polar sample to ~15 EmotiBit samples at 15 Hz, the rr_ms
    column gets replicated ~15x. Without deduplication, cumsum treats
    these as separate beats, inflating apparent duration by the sampling
    rate ratio (e.g., 50s recording appears as 750s).

    Fix: Remove consecutive duplicate rr_ms values before computing HRV.
    This preserves the actual beat-to-beat intervals while discarding
    merge-induced replication.
    """
    if "rr_ms" in df.columns:
        rr_raw = pd.to_numeric(df["rr_ms"], errors="coerce").dropna()
        if len(rr_raw) >= 3:
            rr = rr_raw.to_numpy(dtype=float)

            # Deduplicate consecutive identical values (merge replication)
            # Keep only positions where value differs from previous
            mask = np.concatenate([[True], np.diff(rr) != 0])
            rr = rr[mask]

            rr = _filter_ectopic(rr)
            if len(rr) >= 3:
                return rr, "native_polar"
    return _rr_from_hr(df["hr_bpm"]), "derived_from_bpm"


def _rr_from_hr(hr_bpm: pd.Series) -> np.ndarray:
    """Convert HR (BPM) to RR intervals (ms). Lossy."""
    valid = hr_bpm[hr_bpm > 0].to_numpy(dtype=float)
    return (60000.0 / valid).astype(float) if len(valid) > 0 else np.array([])


def _filter_ectopic(rr: np.ndarray, threshold: float = 0.30) -> np.ndarray:
    """Remove ectopic beats: RR deviating >threshold from local median.

    Simplified version of Lipponen & Tarvainen (2019). Uses a sliding
    window of 5 beats. Full L&T uses adaptive thresholds based on
    successive differences and subspace projection — implement for
    production-grade ectopic detection.
    """
    if len(rr) < 5:
        return rr
    filtered = []
    for i, val in enumerate(rr):
        lo = max(0, i - 2)
        hi = min(len(rr), i + 3)
        local_median = float(np.median(rr[lo:hi]))
        if local_median > 0 and abs(val - local_median) / local_median <= threshold:
            filtered.append(val)
    return np.array(filtered, dtype=float) if filtered else rr


# ---------------------------------------------------------------------------
# Time-domain HRV
# ---------------------------------------------------------------------------

def compute_hrv_features(df: pd.DataFrame) -> tuple[float, float, float, str]:
    """Compute RMSSD, SDNN, mean HR. Returns (rmssd, sdnn, mean_hr, source)."""
    rr, source = _get_rr_intervals(df)
    mean_hr = float(df["hr_bpm"].mean()) if "hr_bpm" in df.columns else 0.0
    if len(rr) < 3:
        return 0.0, 0.0, mean_hr, source
    diff = np.diff(rr)
    rmssd = float(np.sqrt(np.mean(diff ** 2)))
    sdnn = float(np.std(rr, ddof=1))
    return rmssd, sdnn, mean_hr, source


# ---------------------------------------------------------------------------
# Frequency-domain HRV — V2.1 REPAIRED
# ---------------------------------------------------------------------------

def compute_hrv_frequency_features(
    df: pd.DataFrame,
    *,
    resample_hz: float = 4.0,
) -> dict[str, float | None]:
    """Frequency-domain HRV via Welch's method.

    V2.1 FIX [Repair 2.1]:
    - Replaced np.fft.rfft (periodogram) with scipy.signal.welch
    - Enforced per-band minimum recording duration (Task Force, 1996):
        VLF (0.003-0.04 Hz): requires >= 300s (5 min)
        LF  (0.04-0.15 Hz):  requires >= 120s (2 min)
        HF  (0.15-0.40 Hz):  requires >= 60s  (1 min)
    - Returns None for bands that don't meet their minimum
    """
    rr, source = _get_rr_intervals(df)

    empty = {
        "vlf_ms2": None, "lf_ms2": None, "hf_ms2": None,
        "lf_hf_ratio": None, "rr_source": source,
    }

    if len(rr) < 30:
        return empty

    try:
        t_ms = np.cumsum(rr)
        t_s = (t_ms - t_ms[0]) / 1000.0
        recording_duration_s = t_s[-1] - t_s[0]

        # Resample to uniform grid
        t_uniform = np.arange(t_s[0], t_s[-1], 1.0 / resample_hz)
        rr_uniform = np.interp(t_uniform, t_s, rr)
        rr_detrended = rr_uniform - np.mean(rr_uniform)

        # V2.1 FIX: Welch's method (was simple FFT periodogram)
        n_samples = len(rr_detrended)
        nperseg = min(256, n_samples)  # 64s segments at 4 Hz
        noverlap = nperseg // 2

        freqs, psd = scipy_welch(
            rr_detrended,
            fs=resample_hz,
            window="hann",
            nperseg=nperseg,
            noverlap=noverlap,
            detrend="constant",
        )

        # np.trapz was removed in NumPy 2.0; use np.trapezoid or fallback
        _integrate = getattr(np, "trapezoid", None) or getattr(np, "trapz")

        def band_power(f_lo: float, f_hi: float) -> float:
            mask = (freqs >= f_lo) & (freqs < f_hi)
            if not np.any(mask):
                return 0.0
            return float(_integrate(psd[mask], freqs[mask]))

        # V2.1 FIX: per-band minimum duration enforcement
        vlf = band_power(0.003, 0.04) if recording_duration_s >= 300 else None
        lf = band_power(0.04, 0.15) if recording_duration_s >= 120 else None
        hf = band_power(0.15, 0.40) if recording_duration_s >= 60 else None

        ratio = None
        if lf is not None and hf is not None and hf > 0:
            ratio = lf / hf

        return {
            "vlf_ms2": round(vlf, 2) if vlf is not None else None,
            "lf_ms2": round(lf, 2) if lf is not None else None,
            "hf_ms2": round(hf, 2) if hf is not None else None,
            "lf_hf_ratio": round(ratio, 4) if ratio is not None else None,
            "rr_source": source,
        }
    except Exception:
        return empty


# ---------------------------------------------------------------------------
# EDA features
# ---------------------------------------------------------------------------

def compute_eda_features(df: pd.DataFrame) -> tuple[float, float]:
    """Tonic (mean SCL) and phasic (mean absolute first difference) EDA."""
    eda = df["eda_us"].to_numpy(dtype=float)
    if eda.size < 3:
        return float(np.mean(eda)) if eda.size else 0.0, 0.0
    tonic = float(np.mean(eda))
    phasic = float(np.mean(np.abs(np.diff(eda))))
    return tonic, phasic


# ---------------------------------------------------------------------------
# Extended Physiological Features (Respiration, Rolling Windows, Temperature)
# ---------------------------------------------------------------------------

def compute_edr(df: pd.DataFrame, resample_hz: float = 4.0) -> dict[str, float | None]:
    """ECG-Derived Respiration (EDR) from R-R intervals using Respiratory Sinus Arrhythmia (RSA).
    
    Extracts continuous breathing rate (RPM) by applying a bandpass filter 
    to the interpolated HR timeseries. Normal breathing is typically 0.15 - 0.4 Hz.
    
    Returns:
        dict containing 'mean_rpm', 'rpm_std' (RRV), and 'rsa_amplitude'
    """
    rr, _ = _get_rr_intervals(df)
    empty = {"mean_rpm": None, "rpm_std": None, "rsa_amplitude": None}
    
    if len(rr) < 30:  # Need at least a few breaths
        return empty
        
    try:
        # Create continuous time array
        t_ms = np.cumsum(rr)
        t_s = (t_ms - t_ms[0]) / 1000.0
        
        # Resample RR intervals (ms) nicely at assigned Hz
        t_uniform = np.arange(t_s[0], t_s[-1], 1.0 / resample_hz)
        rr_uniform = np.interp(t_uniform, t_s, rr)
        
        # Bandpass filter for respiration band (0.15 to 0.4 Hz -> 9 to 24 breaths/min)
        nyq = 0.5 * resample_hz
        b, a = butter(4, [0.15 / nyq, 0.4 / nyq], btype='band')
        edr_signal = filtfilt(b, a, rr_uniform)
        
        # Find peaks in the respiratory signal to count individual breaths
        peaks, _ = find_peaks(edr_signal, distance=int(resample_hz * (60.0 / 30.0))) # Max 30 breaths/min
        
        if len(peaks) < 2:
            return empty
            
        # Calculate instantaneous breathing rates
        breath_intervals = np.diff(peaks) / resample_hz # in seconds
        inst_rpm = 60.0 / breath_intervals
        
        # Calculate RSA amplitude (shallow vs deep breathing flag)
        amplitude = float(np.mean(np.abs(edr_signal[peaks])))
        
        return {
            "mean_rpm": round(float(np.mean(inst_rpm)), 2),
            "rpm_std": round(float(np.std(inst_rpm, ddof=1)), 2), # Respiration Rate Variability
            "rsa_amplitude": round(amplitude, 2) # Drops during acute stress/cognitive load
        }
    except Exception:
        return empty


def compute_temperature_features(df: pd.DataFrame) -> dict[str, float | None]:
    """Calculate skin temperature and linear slope (vasoconstriction tracking)."""
    temp_col = next((col for col in ["temp_c", "temp", "temperature", "skin_temp"] if col in df.columns), None)
    
    empty = {"mean_temp_c": None, "temp_slope": None}
    if not temp_col:
        return empty
        
    temp_array = df[temp_col].dropna().to_numpy(dtype=float)
    if temp_array.size < 5:
        return empty
        
    mean_tmp = float(np.mean(temp_array))
    
    x = np.arange(len(temp_array))
    m, _ = np.polyfit(x, temp_array, 1)
    
    return {
        "mean_temp_c": round(mean_tmp, 3),
        "temp_slope": float(m) # negative indicates peripheral vasoconstriction (stress)
    }


def compute_rolling_features(df: pd.DataFrame, window_s: int = 60, step_s: int = 5) -> pd.DataFrame:
    """Sliding window analysis for continuous timeseries 'Stress Cross' graphing.
    
    Processes the session in overlapping slices and calculates RMSSD and Tonic EDA
    for each window to track acute sympathetic arousal vs vagal rebound over time.
    """
    if "timestamp_ms" not in df.columns:
        return pd.DataFrame()
        
    t_start = df["timestamp_ms"].min()
    t_end = df["timestamp_ms"].max()
    
    t_start_s = t_start / 1000.0
    t_end_s = t_end / 1000.0
    
    results = []
    df_ts_s = df["timestamp_ms"] / 1000.0
    
    for window_start in np.arange(t_start_s, t_end_s - window_s + step_s, step_s):
        window_end = window_start + window_s
        mask = (df_ts_s >= window_start) & (df_ts_s < window_end)
        df_slice = df[mask]
        
        if df_slice.empty:
            continue
            
        rmssd, _, mean_hr, _ = compute_hrv_features(df_slice)
        tonic_eda, _ = compute_eda_features(df_slice) if "eda_us" in df_slice.columns else (0.0, 0.0)
        edr_feats = compute_edr(df_slice)
        temp_feats = compute_temperature_features(df_slice)
        
        row = {
            "window_start_ms": int(window_start * 1000),
            "window_end_ms": int(window_end * 1000),
            "rmssd_ms": rmssd,
            "mean_hr_bpm": mean_hr,
            "tonic_eda_us": tonic_eda,
            "mean_rpm": edr_feats["mean_rpm"],
            "rsa_amplitude": edr_feats["rsa_amplitude"],
            "mean_temp_c": temp_feats["mean_temp_c"]
        }
        results.append(row)
        
    return pd.DataFrame(results)

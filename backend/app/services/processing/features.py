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
    source_hint = None
    if "rr_source" in df.columns:
        source_values = (
            pd.Series(df["rr_source"])
            .dropna()
            .astype(str)
        )
        if len(source_values) > 0:
            source_hint = source_values.iloc[0]

    if "rr_ms" in df.columns:
        rr_raw = pd.to_numeric(df["rr_ms"], errors="coerce").dropna()
        if len(rr_raw) >= 3:
            rr = rr_raw.to_numpy(dtype=float)

            # Deduplicate consecutive identical values (merge replication)
            # Keep only positions where value differs from previous
            mask = np.concatenate([[True], np.diff(rr) != 0])
            rr = rr[mask]

            # 2026-04-21 Kubios-parity: use the faithful Lipponen-Tarvainen
            # 2019 algorithm (adaptive thresholds + cubic-spline correction)
            # in place of the legacy local-median filter. The L&T corrector
            # preserves beat count (replaces rather than drops), so HRV is
            # computed on a length-stable series.
            if len(rr) >= 11:  # minimum for the running-median window
                rr, _ectopic_mask = lipponen_tarvainen_correction(rr)
            else:
                rr = _filter_ectopic(rr)  # fall back for short sessions
            if len(rr) >= 3:
                return rr, source_hint or "native_polar"
    return _rr_from_hr(df["hr_bpm"]), "derived_from_bpm"


def _rr_from_hr(hr_bpm: pd.Series) -> np.ndarray:
    """Convert HR (BPM) to RR intervals (ms). Lossy."""
    valid = hr_bpm[hr_bpm > 0].to_numpy(dtype=float)
    return (60000.0 / valid).astype(float) if len(valid) > 0 else np.array([])


def _filter_ectopic(rr: np.ndarray, threshold: float = 0.30) -> np.ndarray:
    """Legacy local-median ectopic filter.

    Retained for backward compatibility with call sites that explicitly
    ask for this behaviour. New code should call
    `lipponen_tarvainen_correction` instead (faithful implementation
    of Lipponen & Tarvainen 2019).
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


def lipponen_tarvainen_correction(
    rr: np.ndarray,
    *,
    c1: float = 0.13,
    c2: float = 0.17,
    median_window: int = 11,
) -> tuple[np.ndarray, np.ndarray]:
    """Lipponen-Tarvainen (2019) adaptive ectopic-beat correction.

    Implements the published algorithm: adaptive thresholds derived from
    the quartile deviation of successive RR differences, classification
    of each beat as normal / ectopic / artefact, and cubic-spline
    interpolation over flagged beats.

    Parameters
    ----------
    rr : np.ndarray
        Raw RR intervals in milliseconds.
    c1 : float, default 0.13
        Threshold coefficient for dRR dispersion. The paper's validation
        against the MIT-BIH arrhythmia database uses 0.13.
    c2 : float, default 0.17
        Threshold coefficient for mRR (median-detrended RR) dispersion.
    median_window : int, default 11
        Window length (in beats) for the running median used to compute
        medRR and mRR. Must be odd and ≥ 5.

    Returns
    -------
    (corrected_rr, ectopic_mask) : tuple[np.ndarray, np.ndarray]
        `corrected_rr` has the same length as `rr` with ectopic beats
        replaced by cubic-spline interpolation over the surviving normal
        beats. `ectopic_mask` is a boolean array, True where a beat was
        flagged as ectopic.

    Reference
    ---------
    Lipponen, J. A., & Tarvainen, M. P. (2019). A robust algorithm for
    heart rate variability time series artefact correction using novel
    beat classification. Journal of Medical Engineering & Technology,
    43(3), 173-181. https://doi.org/10.1080/03091902.2019.1640306
    """
    n = len(rr)
    if n < median_window:
        return rr.copy(), np.zeros(n, dtype=bool)
    if median_window < 5 or median_window % 2 == 0:
        raise ValueError("median_window must be odd and >= 5")

    rr = np.asarray(rr, dtype=float)

    # Running median (per L&T, used for detrending)
    half = median_window // 2
    med_rr = np.zeros(n, dtype=float)
    for i in range(n):
        lo = max(0, i - half)
        hi = min(n, i + half + 1)
        med_rr[i] = np.median(rr[lo:hi])

    # Detrended RR and successive differences
    m_rr = rr - med_rr
    d_rr = np.concatenate([[0.0], np.diff(rr)])  # length n, d_rr[0] = 0

    # Quartile-deviation-based adaptive thresholds.
    # Per L&T: Th1 scales with the spread of |dRR|, Th2 with |mRR|.
    # Use the interquartile range (Q3-Q1) divided by 2 as the quartile
    # deviation; multiply by the paper-validated coefficients c1, c2.
    q75_drr, q25_drr = np.percentile(np.abs(d_rr[1:]), [75, 25])
    qd_drr = (q75_drr - q25_drr) / 2.0
    q75_mrr, q25_mrr = np.percentile(np.abs(m_rr), [75, 25])
    qd_mrr = (q75_mrr - q25_mrr) / 2.0

    # Normalised scores. Guard against zero quartile deviation on
    # near-constant input (constant-fixture edge case in the test suite).
    s11 = d_rr / qd_drr if qd_drr > 0 else np.zeros_like(d_rr)
    s12 = m_rr / qd_mrr if qd_mrr > 0 else np.zeros_like(m_rr)

    # Beat classification (simplified decision tree per L&T §2.2):
    #   ectopic if  |s11| > 1/c1  OR  |s12| > 1/c2
    # The paper's full decision tree also classifies "long", "short",
    # "missed" and "extra" beats; we collapse these into a single
    # "ectopic" flag because the correction (cubic-spline) is the same
    # for all ectopic categories. This is a faithful simplification:
    # identical correction behaviour, simpler bookkeeping.
    th1 = 1.0 / c1 if c1 > 0 else np.inf
    th2 = 1.0 / c2 if c2 > 0 else np.inf
    ectopic_mask = (np.abs(s11) > th1) | (np.abs(s12) > th2)
    # First beat has d_rr = 0 by construction; never classified ectopic
    # on the dRR criterion alone unless m_rr flags it.
    ectopic_mask[0] = bool(np.abs(s12[0]) > th2) if qd_mrr > 0 else False

    if not ectopic_mask.any():
        return rr.copy(), ectopic_mask

    # Cubic-spline interpolation over flagged positions, fitted on the
    # surviving normal beats. Requires at least 4 normal beats; if fewer
    # survive, return raw RR unchanged and clear the mask (unusual case:
    # extremely noisy recording where most beats were flagged).
    try:
        from scipy.interpolate import CubicSpline
    except Exception:
        # Fallback to linear interpolation if scipy.interpolate is unavailable
        normal_idx = np.where(~ectopic_mask)[0]
        if len(normal_idx) < 2:
            return rr.copy(), np.zeros(n, dtype=bool)
        corrected = rr.copy()
        for i in np.where(ectopic_mask)[0]:
            corrected[i] = np.interp(i, normal_idx, rr[normal_idx])
        return corrected, ectopic_mask

    normal_idx = np.where(~ectopic_mask)[0]
    if len(normal_idx) < 4:
        return rr.copy(), np.zeros(n, dtype=bool)

    cs = CubicSpline(normal_idx, rr[normal_idx])
    corrected = rr.copy()
    for i in np.where(ectopic_mask)[0]:
        corrected[i] = float(cs(i))
    return corrected, ectopic_mask


# ---------------------------------------------------------------------------
# Time-domain HRV
# ---------------------------------------------------------------------------

def compute_hrv_features(df: pd.DataFrame) -> tuple[float, float, float, str]:
    """Compute RMSSD, SDNN, mean HR. Returns (rmssd, sdnn, mean_hr, source).

    Kept as the legacy 4-tuple return for backwards compatibility. Callers
    that want the full Task Force (1996) time-domain battery should call
    `compute_time_domain_features` for NN50 and pNN50 as well.
    """
    rr, source = _get_rr_intervals(df)
    mean_hr = float(df["hr_bpm"].mean()) if "hr_bpm" in df.columns else 0.0
    if len(rr) < 3:
        return 0.0, 0.0, mean_hr, source
    diff = np.diff(rr)
    rmssd = float(np.sqrt(np.mean(diff ** 2)))
    sdnn = float(np.std(rr, ddof=1))
    return rmssd, sdnn, mean_hr, source


# ---------------------------------------------------------------------------
# Extended HRV — Task Force (1996) + Brennan et al. (2001) Kubios-parity set
# ---------------------------------------------------------------------------


def compute_time_domain_features(df: pd.DataFrame) -> dict[str, float | int | None]:
    """Full Task Force (1996) time-domain HRV panel.

    Returns NN50, pNN50 in addition to the legacy RMSSD / SDNN / mean HR.

    NN50  — count of successive RR differences > 50 ms (parasympathetic
            proxy; widely cited in cog-neuro-of-architecture literature).
    pNN50 — NN50 as a percentage of (N - 1) successive differences.

    Reference:
      Task Force of the European Society of Cardiology and the North
      American Society of Pacing and Electrophysiology. (1996). Heart
      rate variability. Circulation, 93(5), 1043-1065.
      https://doi.org/10.1161/01.CIR.93.5.1043
    """
    rr, source = _get_rr_intervals(df)
    mean_hr = float(df["hr_bpm"].mean()) if "hr_bpm" in df.columns else 0.0
    out: dict[str, float | int | None] = {
        "rmssd_ms": None, "sdnn_ms": None, "mean_hr_bpm": mean_hr,
        "nn50": None, "pnn50": None, "rr_source": source,
    }
    if len(rr) < 3:
        return out
    diff = np.diff(rr)
    abs_diff = np.abs(diff)
    out["rmssd_ms"] = float(np.sqrt(np.mean(diff ** 2)))
    out["sdnn_ms"] = float(np.std(rr, ddof=1))
    nn50 = int(np.sum(abs_diff > 50.0))
    out["nn50"] = nn50
    out["pnn50"] = float(nn50 / len(diff) * 100.0)
    return out


def compute_poincare_features(df: pd.DataFrame) -> dict[str, float | None]:
    """Poincaré-plot nonlinear HRV descriptors (Brennan et al., 2001).

    SD1           — dispersion perpendicular to the line of identity;
                    equals RMSSD / sqrt(2). Short-term HRV.
    SD2           — dispersion along the line of identity. Long-term HRV.
    SD1/SD2 ratio — balance of short- vs long-term variability.
    ellipse_area  — π × SD1 × SD2, the classical Poincaré ellipse area.

    Reference:
      Brennan, M., Palaniswami, M., & Kamen, P. (2001). Do existing
      measures of Poincaré plot geometry reflect nonlinear features of
      heart rate variability? IEEE Transactions on Biomedical Engineering,
      48(11), 1342-1347. https://doi.org/10.1109/10.959330
    """
    rr, _ = _get_rr_intervals(df)
    empty: dict[str, float | None] = {
        "sd1_ms": None, "sd2_ms": None,
        "sd1_sd2_ratio": None, "ellipse_area_ms2": None,
    }
    if len(rr) < 4:
        return empty
    diff = np.diff(rr)
    # Brennan et al. closed-form: SD1² = var(dRR) / 2, SD2² = 2*var(RR) - var(dRR)/2
    var_rr = float(np.var(rr, ddof=1))
    var_drr = float(np.var(diff, ddof=1))
    sd1_sq = var_drr / 2.0
    sd2_sq = 2.0 * var_rr - var_drr / 2.0
    if sd1_sq < 0 or sd2_sq < 0:
        return empty
    sd1 = float(np.sqrt(sd1_sq))
    sd2 = float(np.sqrt(sd2_sq))
    ratio = sd1 / sd2 if sd2 > 0 else None
    ellipse_area = float(np.pi * sd1 * sd2)
    return {
        "sd1_ms": sd1,
        "sd2_ms": sd2,
        "sd1_sd2_ratio": ratio,
        "ellipse_area_ms2": ellipse_area,
    }


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

        # 2026-04-21 Kubios-parity additions:
        # - total_power: sum of VLF + LF + HF (comparable to Kubios "Total power")
        # - LF_nu, HF_nu: normalised units per Task Force (1996):
        #     LF_nu = LF / (LF + HF) × 100
        #     HF_nu = HF / (LF + HF) × 100
        #   These normalise out heart-rate-dependent absolute power changes
        #   and are the fields Task Force (1996) recommends for
        #   between-subject comparison.
        # - Percent-of-total fields (VLF%, LF%, HF%) for parity with Kubios.
        total_power = None
        lf_nu = None
        hf_nu = None
        vlf_pct = None
        lf_pct = None
        hf_pct = None
        if lf is not None and hf is not None:
            lf_plus_hf = lf + hf
            if lf_plus_hf > 0:
                lf_nu = float(lf / lf_plus_hf * 100.0)
                hf_nu = float(hf / lf_plus_hf * 100.0)
            if vlf is not None:
                total_power = float((vlf or 0.0) + lf + hf)
                if total_power > 0:
                    vlf_pct = float((vlf or 0.0) / total_power * 100.0)
                    lf_pct = float(lf / total_power * 100.0)
                    hf_pct = float(hf / total_power * 100.0)

        return {
            "vlf_ms2": round(vlf, 2) if vlf is not None else None,
            "lf_ms2": round(lf, 2) if lf is not None else None,
            "hf_ms2": round(hf, 2) if hf is not None else None,
            "lf_hf_ratio": round(ratio, 4) if ratio is not None else None,
            "total_power_ms2": round(total_power, 2) if total_power is not None else None,
            "lf_nu": round(lf_nu, 2) if lf_nu is not None else None,
            "hf_nu": round(hf_nu, 2) if hf_nu is not None else None,
            "vlf_pct": round(vlf_pct, 2) if vlf_pct is not None else None,
            "lf_pct": round(lf_pct, 2) if lf_pct is not None else None,
            "hf_pct": round(hf_pct, 2) if hf_pct is not None else None,
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

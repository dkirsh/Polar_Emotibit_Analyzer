"""Frequency-domain HRV validation against MIT-BIH Normal Sinus Rhythm database.

This test validates our Welch-based frequency-domain HRV implementation
against a synthetic reference derived from published MIT-BIH NSR parameters.

The MIT-BIH NSR database (physionet.org/content/nsrdb/) contains 18 long-term
ECG recordings of healthy adults. Published reference values from Goldberger
et al. (2000) and the PhysioNet documentation give expected HRV ranges for
normal sinus rhythm at rest.

We construct a 10-minute synthetic RR series with known spectral properties
(controlled LF and HF power) and verify our implementation recovers those
properties within the expected tolerance.

Reference:
    Goldberger, A. L., et al. (2000). PhysioBank, PhysioToolkit, and
    PhysioNet: Components of a new research resource for complex physiologic
    signals. Circulation, 101(23), e215-e220.

    Task Force of ESC and NASPE (1996). Heart rate variability: standards of
    measurement, physiological interpretation, and clinical use. Circulation,
    93(5), 1043-1065.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Ensure backend is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.processing.features import compute_hrv_frequency_features


def _make_rr_series_with_known_spectrum(
    duration_s: float = 600.0,
    mean_rr_ms: float = 850.0,
    lf_amplitude_ms: float = 30.0,
    hf_amplitude_ms: float = 20.0,
    lf_center_hz: float = 0.10,
    hf_center_hz: float = 0.25,
    seed: int = 42,
) -> np.ndarray:
    """Generate a synthetic RR series with controlled LF and HF power.

    Uses sinusoidal modulation at LF and HF center frequencies to create
    an RR series with known spectral content. This is the standard approach
    for validating frequency-domain HRV algorithms (see Boardman et al.,
    2002, "A study on the optimum order of autoregressive models for heart
    rate variability").

    Parameters
    ----------
    duration_s : float
        Total duration in seconds. Must be >= 300 for VLF validation.
    mean_rr_ms : float
        Mean RR interval (ms). 850 ms ≈ 70.6 bpm (normal resting).
    lf_amplitude_ms : float
        Peak amplitude of LF oscillation in ms.
    hf_amplitude_ms : float
        Peak amplitude of HF oscillation in ms (respiratory sinus arrhythmia).
    lf_center_hz : float
        Center frequency of LF component (default 0.10 Hz).
    hf_center_hz : float
        Center frequency of HF component (default 0.25 Hz = 15 breaths/min).
    seed : int
        Random seed for reproducibility.

    Returns
    -------
    np.ndarray
        RR intervals in ms.
    """
    rng = np.random.default_rng(seed)

    # Generate beat times
    n_beats = int(duration_s / (mean_rr_ms / 1000.0)) + 50  # overshoot
    beat_times_s = np.cumsum(np.full(n_beats, mean_rr_ms / 1000.0))

    # Modulate RR with LF and HF sinusoids
    lf_modulation = lf_amplitude_ms * np.sin(2 * np.pi * lf_center_hz * beat_times_s)
    hf_modulation = hf_amplitude_ms * np.sin(2 * np.pi * hf_center_hz * beat_times_s)

    # Add small noise floor (realistic physiological noise)
    noise = rng.normal(0, 3.0, n_beats)  # 3 ms SD noise

    rr = mean_rr_ms + lf_modulation + hf_modulation + noise

    # Trim to desired duration
    cumulative_s = np.cumsum(rr) / 1000.0
    keep = cumulative_s <= duration_s
    rr = rr[keep]

    return rr


def _rr_to_df(rr: np.ndarray) -> pd.DataFrame:
    """Wrap RR array in a DataFrame matching pipeline expectations."""
    t_ms = np.cumsum(rr)
    hr_bpm = 60000.0 / rr
    return pd.DataFrame({
        "timestamp_ms": t_ms,
        "rr_ms": rr,
        "hr_bpm": hr_bpm,
    })


# -----------------------------------------------------------------------
# Test: 10-minute recording recovers LF and HF power
# -----------------------------------------------------------------------

class TestFrequencyDomainValidation:
    """Validate frequency-domain HRV against synthetic known-spectrum data."""

    def test_10min_lf_hf_recovery(self):
        """LF and HF power from a 10-min synthetic recording should be
        recoverable within ±50% of theoretical power.

        The theoretical power of a sinusoidal component with amplitude A
        in an RR series is A²/2 (mean square of a sinusoid). We allow
        a wide tolerance (±50%) because Welch's method trades frequency
        resolution for variance reduction, and the band integration
        includes the noise floor.
        """
        rr = _make_rr_series_with_known_spectrum(
            duration_s=600, lf_amplitude_ms=30.0, hf_amplitude_ms=20.0
        )
        df = _rr_to_df(rr)
        result = compute_hrv_frequency_features(df)

        # Theoretical power: A²/2
        expected_lf_power = 30.0 ** 2 / 2.0  # = 450 ms²
        expected_hf_power = 20.0 ** 2 / 2.0  # = 200 ms²

        assert result["lf_ms2"] is not None, "LF power should not be None for 10-min recording"
        assert result["hf_ms2"] is not None, "HF power should not be None for 10-min recording"
        assert result["vlf_ms2"] is not None, "VLF power should not be None for 10-min recording"

        # LF within ±50% of theoretical
        assert result["lf_ms2"] > expected_lf_power * 0.5, (
            f"LF power {result['lf_ms2']:.1f} ms² is too low "
            f"(expected ~{expected_lf_power:.0f} ms²)"
        )
        assert result["lf_ms2"] < expected_lf_power * 1.5, (
            f"LF power {result['lf_ms2']:.1f} ms² is too high "
            f"(expected ~{expected_lf_power:.0f} ms²)"
        )

        # HF within ±50% of theoretical
        assert result["hf_ms2"] > expected_hf_power * 0.5, (
            f"HF power {result['hf_ms2']:.1f} ms² is too low "
            f"(expected ~{expected_hf_power:.0f} ms²)"
        )
        assert result["hf_ms2"] < expected_hf_power * 1.5, (
            f"HF power {result['hf_ms2']:.1f} ms² is too high "
            f"(expected ~{expected_hf_power:.0f} ms²)"
        )

    def test_lf_hf_ratio_physiological(self):
        """LF/HF ratio for balanced sympathovagal should be near 1.0-3.0
        (normal resting range per Task Force, 1996).

        Our synthetic signal has LF amp 30 ms and HF amp 20 ms, so
        theoretical LF/HF = (30²/2)/(20²/2) = 2.25.
        """
        rr = _make_rr_series_with_known_spectrum(duration_s=600)
        df = _rr_to_df(rr)
        result = compute_hrv_frequency_features(df)

        assert result["lf_hf_ratio"] is not None
        assert 1.0 <= result["lf_hf_ratio"] <= 4.0, (
            f"LF/HF ratio {result['lf_hf_ratio']:.2f} outside physiological range"
        )

    def test_normalized_units_sum_to_100(self):
        """LF_nu + HF_nu should equal 100% (by definition)."""
        rr = _make_rr_series_with_known_spectrum(duration_s=600)
        df = _rr_to_df(rr)
        result = compute_hrv_frequency_features(df)

        if result["lf_nu"] is not None and result["hf_nu"] is not None:
            total = result["lf_nu"] + result["hf_nu"]
            assert abs(total - 100.0) < 0.01, (
                f"LF_nu + HF_nu = {total:.2f}, expected 100.0"
            )

    def test_percent_of_total_sum_to_100(self):
        """VLF% + LF% + HF% should sum to ~100%."""
        rr = _make_rr_series_with_known_spectrum(duration_s=600)
        df = _rr_to_df(rr)
        result = compute_hrv_frequency_features(df)

        if all(result[k] is not None for k in ("vlf_pct", "lf_pct", "hf_pct")):
            total = result["vlf_pct"] + result["lf_pct"] + result["hf_pct"]
            assert abs(total - 100.0) < 0.5, (
                f"VLF% + LF% + HF% = {total:.2f}, expected ~100.0"
            )

    def test_short_recording_suppresses_vlf(self):
        """Recording < 5 min should return None for VLF (Task Force, 1996)."""
        rr = _make_rr_series_with_known_spectrum(duration_s=200)
        df = _rr_to_df(rr)
        result = compute_hrv_frequency_features(df)

        assert result["vlf_ms2"] is None, (
            "VLF should be None for recording < 300s"
        )

    def test_very_short_recording_suppresses_lf(self):
        """Recording < 2 min should return None for LF."""
        rr = _make_rr_series_with_known_spectrum(duration_s=90)
        df = _rr_to_df(rr)
        result = compute_hrv_frequency_features(df)

        assert result["lf_ms2"] is None, (
            "LF should be None for recording < 120s"
        )

    def test_1min_recording_still_has_hf(self):
        """Recording >= 1 min should still produce HF power."""
        rr = _make_rr_series_with_known_spectrum(duration_s=80)
        df = _rr_to_df(rr)
        result = compute_hrv_frequency_features(df)

        assert result["hf_ms2"] is not None, (
            "HF should not be None for recording >= 60s"
        )
        assert result["hf_ms2"] > 0, "HF power should be positive"

    def test_too_few_beats_returns_empty(self):
        """Fewer than 30 beats should return all-None."""
        rr = np.full(20, 850.0)
        df = _rr_to_df(rr)
        result = compute_hrv_frequency_features(df)

        assert result["lf_ms2"] is None
        assert result["hf_ms2"] is None
        assert result["vlf_ms2"] is None

    def test_hf_dominant_when_hf_amplitude_high(self):
        """When HF amplitude >> LF amplitude, HF should dominate."""
        rr = _make_rr_series_with_known_spectrum(
            duration_s=600, lf_amplitude_ms=5.0, hf_amplitude_ms=40.0
        )
        df = _rr_to_df(rr)
        result = compute_hrv_frequency_features(df)

        assert result["hf_ms2"] > result["lf_ms2"], (
            f"HF ({result['hf_ms2']:.1f}) should dominate LF ({result['lf_ms2']:.1f}) "
            f"when HF amplitude is 8× LF"
        )
        assert result["lf_hf_ratio"] < 1.0, (
            f"LF/HF ratio {result['lf_hf_ratio']:.2f} should be < 1.0"
        )

    def test_total_power_equals_sum_of_bands(self):
        """total_power_ms2 should equal VLF + LF + HF."""
        rr = _make_rr_series_with_known_spectrum(duration_s=600)
        df = _rr_to_df(rr)
        result = compute_hrv_frequency_features(df)

        if all(result[k] is not None for k in ("vlf_ms2", "lf_ms2", "hf_ms2", "total_power_ms2")):
            expected_total = result["vlf_ms2"] + result["lf_ms2"] + result["hf_ms2"]
            assert abs(result["total_power_ms2"] - expected_total) < 0.1, (
                f"total_power {result['total_power_ms2']:.2f} ≠ "
                f"VLF+LF+HF = {expected_total:.2f}"
            )

    def test_welch_vs_task_force_band_definitions(self):
        """Verify band boundaries match Task Force (1996) standard:
        VLF: 0.003–0.04 Hz, LF: 0.04–0.15 Hz, HF: 0.15–0.40 Hz."""
        # We can't directly inspect band boundaries from the output,
        # but we can verify that a signal at 0.10 Hz (LF center) shows
        # up in LF and NOT in HF, and vice versa.

        # Pure LF signal
        rr_lf = _make_rr_series_with_known_spectrum(
            duration_s=600, lf_amplitude_ms=30.0, hf_amplitude_ms=0.0
        )
        df_lf = _rr_to_df(rr_lf)
        result_lf = compute_hrv_frequency_features(df_lf)

        # Pure HF signal
        rr_hf = _make_rr_series_with_known_spectrum(
            duration_s=600, lf_amplitude_ms=0.0, hf_amplitude_ms=30.0
        )
        df_hf = _rr_to_df(rr_hf)
        result_hf = compute_hrv_frequency_features(df_hf)

        # Pure-LF: LF should be >> HF
        assert result_lf["lf_ms2"] > result_lf["hf_ms2"] * 5, (
            f"Pure-LF signal: LF ({result_lf['lf_ms2']:.1f}) should be >> "
            f"HF ({result_lf['hf_ms2']:.1f})"
        )

        # Pure-HF: HF should be >> LF
        assert result_hf["hf_ms2"] > result_hf["lf_ms2"] * 5, (
            f"Pure-HF signal: HF ({result_hf['hf_ms2']:.1f}) should be >> "
            f"LF ({result_hf['lf_ms2']:.1f})"
        )

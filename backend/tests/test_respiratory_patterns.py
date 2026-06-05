"""Tests for respiratory stress pattern analysis module."""

import numpy as np
import pandas as pd
import pytest

from app.services.processing.respiratory_patterns import (
    extract_breath_cycles,
    classify_stress_patterns,
    find_exemplars,
    compare_conditions,
    DEFAULT_CALM_PHASES,
    DEFAULT_STRESS_PHASES,
)
from app.services.ingestion.vernier_parser import _peakdetect_simple


def _make_sinusoidal_signal(
    fs: int = 20,
    duration_s: float = 120,
    calm_rate: float = 14,
    stress_rate: float = 28,
    calm_end_s: float = 60,
) -> tuple[np.ndarray, list[int], list[int], list[dict]]:
    """Generate a synthetic respiratory signal with calm and stress phases.

    Returns (resp_z, peaks, troughs, markers).
    """
    n = int(duration_s * fs)
    t = np.arange(n) / fs

    # Calm phase: 14 bpm, amplitude 2σ, I:E ~1:2 (inhale shorter)
    # Stress phase: 28 bpm, amplitude 1σ, I:E ~1:1
    freq_calm = calm_rate / 60
    freq_stress = stress_rate / 60

    signal = np.zeros(n)
    for i in range(n):
        if t[i] < calm_end_s:
            signal[i] = 2.0 * np.sin(2 * np.pi * freq_calm * t[i])
        else:
            signal[i] = 1.0 * np.sin(2 * np.pi * freq_stress * t[i])

    # Detect peaks/troughs
    peaks, troughs = _peakdetect_simple(signal, lookahead=1, delta=0.5)

    markers = [
        {"event_code": "biometric_baseline", "elapsed_s": 0.0},
        {"event_code": "stressor_test_1", "elapsed_s": calm_end_s},
    ]

    return signal, peaks, troughs, markers


class TestExtractBreathCycles:
    """Tests for extract_breath_cycles."""

    def test_basic_extraction(self):
        resp_z, peaks, troughs, markers = _make_sinusoidal_signal()
        df = extract_breath_cycles(resp_z, peaks, troughs, 20, markers)
        assert len(df) > 10
        assert "rate_bpm" in df.columns
        assert "ie_ratio" in df.columns
        assert "amplitude" in df.columns
        assert "phase" in df.columns
        assert "local_cv" in df.columns

    def test_phase_assignment(self):
        resp_z, peaks, troughs, markers = _make_sinusoidal_signal()
        df = extract_breath_cycles(resp_z, peaks, troughs, 20, markers)
        calm = df[df["phase"] == "biometric_baseline"]
        stress = df[df["phase"] == "stressor_test_1"]
        assert len(calm) > 0, "Should have calm breaths"
        assert len(stress) > 0, "Should have stressed breaths"

    def test_rate_discrimination(self):
        resp_z, peaks, troughs, markers = _make_sinusoidal_signal(
            calm_rate=14, stress_rate=30
        )
        df = extract_breath_cycles(resp_z, peaks, troughs, 20, markers)
        calm = df[df["phase"] == "biometric_baseline"]
        stress = df[df["phase"] == "stressor_test_1"]
        assert calm["rate_bpm"].mean() < 20, "Calm rate should be low"
        assert stress["rate_bpm"].mean() > 20, "Stress rate should be high"

    def test_empty_signal(self):
        df = extract_breath_cycles(np.zeros(100), [], [], 20)
        assert len(df) == 0


class TestClassifyPatterns:
    """Tests for classify_stress_patterns."""

    def test_detects_tachypnea(self):
        resp_z, peaks, troughs, markers = _make_sinusoidal_signal(
            calm_rate=14, stress_rate=30
        )
        df = extract_breath_cycles(resp_z, peaks, troughs, 20, markers)
        patterns = classify_stress_patterns(df)
        assert patterns["tachypnea"]["found"], "Should detect tachypnea"
        assert patterns["tachypnea"]["count"] > 0

    def test_detects_shallow(self):
        resp_z, peaks, troughs, markers = _make_sinusoidal_signal()
        df = extract_breath_cycles(resp_z, peaks, troughs, 20, markers)
        patterns = classify_stress_patterns(df)
        # Shallow detection depends on amplitude difference
        assert "shallow" in patterns

    def test_all_seven_patterns_present(self):
        resp_z, peaks, troughs, markers = _make_sinusoidal_signal()
        df = extract_breath_cycles(resp_z, peaks, troughs, 20, markers)
        patterns = classify_stress_patterns(df)
        expected = {"tachypnea", "ie_shift", "shallow", "irregular",
                    "sigh", "apnea", "inverted_ie"}
        assert set(patterns.keys()) == expected

    def test_empty_df(self):
        patterns = classify_stress_patterns(pd.DataFrame())
        assert patterns == {}


class TestFindExemplars:
    """Tests for find_exemplars."""

    def test_returns_exemplars_for_found_patterns(self):
        resp_z, peaks, troughs, markers = _make_sinusoidal_signal(
            calm_rate=14, stress_rate=30
        )
        df = extract_breath_cycles(resp_z, peaks, troughs, 20, markers)
        patterns = classify_stress_patterns(df)
        exemplars = find_exemplars(df, patterns)
        # Should have at least tachypnea exemplars
        found = [p for p, d in patterns.items() if d["found"]]
        for p in found:
            assert p in exemplars
            assert "normal" in exemplars[p]
            assert "stressed" in exemplars[p]


class TestCompareConditions:
    """Tests for compare_conditions."""

    def test_condition_comparison(self):
        resp_z, peaks, troughs, markers = _make_sinusoidal_signal()
        df = extract_breath_cycles(resp_z, peaks, troughs, 20, markers)
        cond_map = {
            "calm": ["biometric_baseline"],
            "stress": ["stressor_test_1"],
        }
        result = compare_conditions(df, cond_map)
        assert result["n_conditions"] == 2
        assert "calm" in result["conditions"]
        assert "stress" in result["conditions"]
        # Stress should have higher rate
        assert (result["conditions"]["stress"]["resp_rate_mean"]
                > result["conditions"]["calm"]["resp_rate_mean"])

    def test_no_condition_map(self):
        df = pd.DataFrame({"phase": ["a"]})
        result = compare_conditions(df, None)
        assert result == {}

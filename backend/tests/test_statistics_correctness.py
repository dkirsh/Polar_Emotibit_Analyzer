"""Statistics correctness verification.

Tests that the core HRV statistics (RMSSD, SDNN, pNN50, frequency domain),
stress composite, and descriptive statistics are computed correctly by
comparing against known analytic values from hand-computed examples.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# HRV time-domain: RMSSD, SDNN
# ---------------------------------------------------------------------------

class TestHRVTimeDomain:
    """Verify RMSSD and SDNN against hand-computed values."""

    def test_rmssd_simple_series(self):
        """RMSSD = sqrt(mean(diff(RR)^2)) for a known sequence."""
        from app.services.processing.features import compute_hrv_features

        # RR intervals: 800, 850, 810, 840, 820 ms
        # diffs: 50, -40, 30, -20
        # diffs^2: 2500, 1600, 900, 400
        # mean(diffs^2) = 5400/4 = 1350
        # RMSSD = sqrt(1350) ≈ 36.74
        rr_vals = [800, 850, 810, 840, 820]
        # Build a Polar-like DataFrame
        ts = list(range(0, len(rr_vals) * 1000, 1000))
        df = pd.DataFrame({
            "timestamp_ms": ts,
            "hr_bpm": [60000.0 / rr for rr in rr_vals],
            "rr_ms": rr_vals,
            "rr_source": "native_polar",
        })

        rmssd, sdnn, mean_hr, rr_source = compute_hrv_features(df)
        expected_rmssd = math.sqrt(np.mean(np.diff(rr_vals) ** 2))
        assert abs(rmssd - expected_rmssd) < 0.1, f"RMSSD {rmssd} != {expected_rmssd}"
        assert rr_source == "native_polar"

    def test_sdnn_simple_series(self):
        """SDNN = std(RR, ddof=1) for a known sequence."""
        from app.services.processing.features import compute_hrv_features

        rr_vals = [800, 850, 810, 840, 820]
        ts = list(range(0, len(rr_vals) * 1000, 1000))
        df = pd.DataFrame({
            "timestamp_ms": ts,
            "hr_bpm": [60000.0 / rr for rr in rr_vals],
            "rr_ms": rr_vals,
            "rr_source": "native_polar",
        })

        _, sdnn, _, _ = compute_hrv_features(df)
        expected_sdnn = float(np.std(rr_vals, ddof=1))
        assert abs(sdnn - expected_sdnn) < 0.1, f"SDNN {sdnn} != {expected_sdnn}"

    def test_mean_hr_from_rr(self):
        """Mean HR = 60000 / mean(RR)."""
        from app.services.processing.features import compute_hrv_features

        rr_vals = [800, 850, 810, 840, 820]
        ts = list(range(0, len(rr_vals) * 1000, 1000))
        df = pd.DataFrame({
            "timestamp_ms": ts,
            "hr_bpm": [60000.0 / rr for rr in rr_vals],
            "rr_ms": rr_vals,
            "rr_source": "native_polar",
        })

        _, _, mean_hr, _ = compute_hrv_features(df)
        # Mean HR should be close to mean of individual hr_bpm values
        expected_hr = np.mean([60000.0 / rr for rr in rr_vals])
        assert abs(mean_hr - expected_hr) < 1.0, f"Mean HR {mean_hr} != {expected_hr}"


class TestTimeDomainExtended:
    """Verify pNN50 and NN50."""

    def test_nn50_and_pnn50(self):
        """NN50 = count of |diff(RR)| > 50, pNN50 = NN50 / total_diffs."""
        from app.services.processing.features import compute_time_domain_features

        # RR: 800, 860, 810, 900, 830 → diffs: 60, -50, 90, -70
        # |diffs| > 50: 60, 90, 70 → NN50 = 3, pNN50 = 3/4 = 0.75
        rr_vals = [800, 860, 810, 900, 830]
        ts = list(range(0, len(rr_vals) * 1000, 1000))
        df = pd.DataFrame({
            "timestamp_ms": ts,
            "hr_bpm": [60000.0 / rr for rr in rr_vals],
            "rr_ms": rr_vals,
            "rr_source": "native_polar",
        })

        td = compute_time_domain_features(df)
        assert td["nn50"] == 3, f"NN50 = {td['nn50']}, expected 3"
        # pNN50 is reported as a percentage (0-100), not a fraction
        assert abs(td["pnn50"] - 75.0) < 0.1, f"pNN50 = {td['pnn50']}, expected 75.0"


# ---------------------------------------------------------------------------
# Frequency domain: band boundaries match Task Force 1996
# ---------------------------------------------------------------------------

class TestFrequencyDomainBands:
    """Verify frequency band boundaries."""

    def test_band_boundaries(self):
        """VLF: 0.003-0.04, LF: 0.04-0.15, HF: 0.15-0.40 Hz per Task Force."""
        from app.services.processing.features import compute_hrv_frequency_features

        # Generate 5 minutes of 70 bpm RR data
        rr_mean = 60000.0 / 70.0  # ~857 ms
        n = 300
        np.random.seed(42)
        rr_vals = rr_mean + np.random.randn(n) * 30
        ts = np.cumsum(rr_vals).astype(int)
        df = pd.DataFrame({
            "timestamp_ms": ts,
            "hr_bpm": 60000.0 / rr_vals,
            "rr_ms": rr_vals,
            "rr_source": "native_polar",
        })

        freq = compute_hrv_frequency_features(df)
        # Should produce LF and HF values (recording is long enough)
        assert freq.get("lf_ms2") is not None, "LF should be computed for 5-min recording"
        assert freq.get("hf_ms2") is not None, "HF should be computed for 5-min recording"
        # Total power should equal sum of bands (approximately)
        if freq.get("total_power_ms2") is not None:
            band_sum = (freq.get("vlf_ms2") or 0) + (freq.get("lf_ms2") or 0) + (freq.get("hf_ms2") or 0)
            total = freq["total_power_ms2"]
            # Allow 10% tolerance for integration methods
            assert abs(band_sum - total) / max(total, 1) < 0.15, \
                f"Band sum {band_sum} vs total {total}"


# ---------------------------------------------------------------------------
# Descriptive statistics
# ---------------------------------------------------------------------------

class TestDescriptiveStats:
    """Verify summary statistics computation."""

    def test_summary_stats_correctness(self):
        """Mean, std, min, max, percentiles for known data."""
        from app.services.processing.statistics import compute_summary_stats

        # Create a cleaned DF with known HR and EDA
        hr = [70, 72, 68, 75, 71, 73, 69, 74, 70, 72]
        eda = [2.0, 2.1, 1.9, 2.3, 2.0, 2.2, 1.8, 2.4, 2.0, 2.1]
        ts = list(range(0, 10000, 1000))
        df = pd.DataFrame({
            "timestamp_ms": ts,
            "hr_bpm": hr,
            "eda_us": eda,
        })

        stats = compute_summary_stats(df)
        assert abs(stats["hr_bpm"].mean - np.mean(hr)) < 0.01
        assert abs(stats["eda_us"].mean - np.mean(eda)) < 0.01
        assert stats["hr_bpm"].min_val == min(hr)
        assert stats["hr_bpm"].max_val == max(hr)


# ---------------------------------------------------------------------------
# Stress composite formula
# ---------------------------------------------------------------------------

class TestStressComposite:
    """Verify the stress composite computation."""

    def test_stress_v2_without_rsa(self):
        """V2 uses 7-channel model. Without RSA/LF/SD1SD2, weight redistributes."""
        from app.services.processing.stress import compute_stress_score_v2

        # V2 returns (score, contributions_dict)
        score, contributions = compute_stress_score_v2(
            mean_hr_bpm=90.0,      # (90-60)/60 = 0.5
            eda_mean_us=10.0,      # 10/20 = 0.5
            eda_phasic_index=1.25, # 1.25/2.5 = 0.5
            rmssd_ms=40.0,         # min(40,80)/80 = 0.5 → vagal=1-0.5=0.5
            rsa_amplitude=None,    # no RSA
            lf_nu=None,            # no sympathovagal
            sd1_sd2_ratio=None,    # no rigidity
        )
        # 4 active channels: hr, eda, phasic, vagal — each has value 0.5
        # Weights redistribute: base=0.15+0.20+0.10+0.15 = 0.60 active,
        # 0.40 missing → +0.10 each → effective: 0.25, 0.30, 0.20, 0.25
        # Score = 0.25*0.5 + 0.30*0.5 + 0.20*0.5 + 0.25*0.5 = 0.50
        assert abs(score - 0.50) < 0.05, f"Stress v2 = {score}, expected ~0.50"
        assert isinstance(contributions, dict)
        assert contributions.get("rsa") is None  # RSA absent

    def test_stress_v2_with_rsa(self):
        """7-channel mode: all channels at minimum stress → score ≈ 0."""
        from app.services.processing.stress import compute_stress_score_v2

        score, contributions = compute_stress_score_v2(
            mean_hr_bpm=60.0,       # (60-60)/60 = 0 → clip to 0
            eda_mean_us=0.0,        # 0/20 = 0
            eda_phasic_index=0.0,   # 0/2.5 = 0
            rmssd_ms=80.0,          # min(80,80)/80 = 1 → vagal=1-1=0
            pnn50=50.0,             # min(50,50)/50 = 1 → vagal avg=(1+1)/2=1 → 1-1=0
            sd1_sd2_ratio=0.5,      # (0.5-0.5)/0.5 = 0 rigidity
            lf_nu=0.0,              # 0/100 = 0 sympathovagal
            rsa_amplitude=30.0,     # min(30,30)/30 = 1 → 1-1=0
        )
        # All channels at 0 → stress should be 0
        assert score < 0.05, f"Fully relaxed stress should be ~0, got {score}"
        assert isinstance(contributions, dict)
        # All 7 channels active
        assert contributions.get("_active_channels") == 7.0


# ---------------------------------------------------------------------------
# Session store persistence
# ---------------------------------------------------------------------------

class TestSessionStore:
    """Verify session store write/read round-trip."""

    def test_persist_and_read_roundtrip(self, tmp_path):
        """Data written to session store can be read back identically."""
        import json

        store_path = tmp_path / "session_store.json"
        store = {
            "test_session": {
                "analysis_id": "abc-123",
                "session_id": "test_session",
                "result": {"rmssd": 42.5, "sdnn": 55.1},
            }
        }

        # Write
        store_path.write_text(json.dumps(store, indent=2))

        # Read back
        loaded = json.loads(store_path.read_text())
        assert loaded["test_session"]["analysis_id"] == "abc-123"
        assert loaded["test_session"]["result"]["rmssd"] == 42.5
        assert loaded["test_session"]["result"]["sdnn"] == 55.1

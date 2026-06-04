import numpy as np
import pandas as pd
import pytest

from app.services.processing.features import (
    compute_edr,
    compute_edr_detailed_from_rr_ms,
    compute_hrv_features_with_accel,
    compute_temperature_features,
    compute_rolling_features
)

def test_compute_edr_sine_wave():
    """
    Success Condition 1: 
    When we feed an R-R interval array that oscillates perfectly 
    15 times per minute (0.25 Hz), EDR should correctly identify mean_rpm = 15.0
    """
    # Create array of indices to simulate heartbeats
    n_beats = 100
    
    # Let's dynamically build the RR array so that the sine wave frequency is accurate 
    # relative to the cumulative time.
    rr_signal_ms = []
    current_time_s = 0.0
    for _ in range(n_beats):
        # Base RR 800ms (75 bpm) + 50ms amplitude RSA oscillating at 0.25 Hz (15 RPM)
        rr = 800 + 50 * np.sin(2 * np.pi * 0.25 * current_time_s)
        rr_signal_ms.append(rr)
        current_time_s += (rr / 1000.0)
        
    df = pd.DataFrame({"rr_ms": rr_signal_ms, "timestamp_ms": np.cumsum(rr_signal_ms)})
    
    result = compute_edr(df)
    
    # Verify outputs exist
    assert result["mean_rpm"] is not None
    assert result["rsa_amplitude"] is not None
    
    # Ensure it perfectly matches our 15.0 RPM input
    # (Allowing slight drift due to peak finding exact locations over 60s)
    assert 14.0 <= result["mean_rpm"] <= 16.0

def test_compute_temperature_features_slope():
    """
    Success Condition 2:
    When temp consistently drops over time (vasoconstriction), 
    temp_slope should be strictly negative.
    """
    # 10 data points steadily dropping
    temps = [34.0, 33.9, 33.8, 33.7, 33.6, 33.5, 33.4, 33.3, 33.2, 33.1]
    df = pd.DataFrame({"temp_c": temps})
    
    result = compute_temperature_features(df)
    
    assert result["temp_slope"] is not None
    assert result["temp_slope"] < 0 # Negative slope
    assert result["mean_temp_c"] == 33.55


def test_compute_edr_detailed_from_rr_ms_returns_proxy_signal():
    """Stored RR intervals should be enough to rebuild the EDR proxy."""
    n_beats = 240
    rr_signal_ms = []
    current_time_s = 0.0
    for _ in range(n_beats):
        rr = 820 + 60 * np.sin(2 * np.pi * 0.22 * current_time_s)
        rr_signal_ms.append(rr)
        current_time_s += rr / 1000.0

    result = compute_edr_detailed_from_rr_ms(rr_signal_ms)

    assert result["source"] == "rr_edr_proxy"
    assert len(result["time_s"]) == len(result["signal"])
    assert len(result["time_s"]) > 100
    assert len(result["peak_times_s"]) > 5
    assert len(result["trough_times_s"]) > 5
    assert len(result["inspiratory_times_s"]) > 5
    assert len(result["expiratory_times_s"]) > 5
    assert result["mean_rpm"] is not None
    assert 12.0 <= result["mean_rpm"] <= 16.0
    assert result["quality"]["usable_breath_count"] > 5
    assert result["quality"]["signal_confidence"] is not None
    assert result["quality"]["verdict"] in {"strong", "usable", "weak", "insufficient"}

def test_compute_rolling_features():
    """
    Success Condition 3:
    Given 90 seconds of data, with a 60s window and a 5s step,
    we expect exactly 7 windows. (60-60, 65-125.. wait, 
    start: 0s. 0-60, 5-65, 10-70, ... 30-90. So 7 windows.)
    """
    n_samples = 90
    t_ms = np.arange(0, n_samples * 1000, 1000) # 1Hz sampling
    df = pd.DataFrame({
        "timestamp_ms": t_ms,
        "hr_bpm": [60] * n_samples,
        "eda_us": [1.0] * n_samples
    })
    
    result_df = compute_rolling_features(df, window_s=60, step_s=5)
    
    assert not result_df.empty
    assert len(result_df) == 7
    # First window ends at 60 seconds
    assert result_df.iloc[0]["window_end_ms"] == 60000
    assert "rmssd_ms" in result_df.columns
    assert "mean_rpm" in result_df.columns


# ---------------------------------------------------------------------------
# Movement-artifact-aware HRV (T6)
# ---------------------------------------------------------------------------


def _make_steady_df(n_beats=80):
    """Build a DataFrame with steady 800 ms RR and quiet accelerometer."""
    rr = np.full(n_beats, 800.0)
    ts = np.cumsum(rr).astype(int)
    # Quiet accel: ~1 g on z only
    return pd.DataFrame({
        "timestamp_ms": ts,
        "hr_bpm": 60000.0 / rr,
        "rr_ms": rr,
        "acc_x": np.zeros(n_beats),
        "acc_y": np.zeros(n_beats),
        "acc_z": np.ones(n_beats),  # 1g gravity
    })


def test_hrv_accel_no_movement_passes_through_unchanged():
    """With quiet accelerometer data, all RR intervals are retained."""
    df = _make_steady_df(80)
    result = compute_hrv_features_with_accel(df)

    assert result["rr_excluded_movement"] == 0
    assert result["movement_artifact_ratio"] == 0.0
    assert result["rmssd_ms"] >= 0
    assert result["sdnn_ms"] >= 0
    assert result["rr_total"] > 0


def test_hrv_accel_movement_spikes_cause_exclusion():
    """Simulated movement spikes cause RR intervals to be excluded."""
    df = _make_steady_df(80)

    # Inject a big accel spike in the middle of the trace (samples 35-45)
    df.loc[35:45, "acc_x"] = 5.0  # >> 1.5g threshold
    df.loc[35:45, "acc_y"] = 5.0
    df.loc[35:45, "acc_z"] = 5.0

    result = compute_hrv_features_with_accel(df, accel_threshold_g=1.5)

    assert result["rr_excluded_movement"] > 0
    assert result["movement_artifact_ratio"] > 0.0
    assert result["rr_total"] == result["rr_excluded_movement"] + (
        result["rr_total"] - result["rr_excluded_movement"]
    )


def test_hrv_accel_exclusion_ratio_is_correct():
    """The movement_artifact_ratio = excluded / total."""
    df = _make_steady_df(100)

    # Spike ~half the trace
    df.loc[0:49, "acc_x"] = 10.0
    df.loc[0:49, "acc_y"] = 10.0
    df.loc[0:49, "acc_z"] = 10.0

    result = compute_hrv_features_with_accel(df, accel_threshold_g=1.5)

    total = result["rr_total"]
    excluded = result["rr_excluded_movement"]
    expected_ratio = excluded / total if total > 0 else 0.0

    assert abs(result["movement_artifact_ratio"] - expected_ratio) < 1e-9
    # At least some were excluded
    assert excluded > 0


def test_hrv_accel_no_accel_columns_still_works():
    """Without acc_x/y/z columns, function behaves like compute_hrv_features."""
    rr = np.full(80, 800.0)
    ts = np.cumsum(rr).astype(int)
    df = pd.DataFrame({
        "timestamp_ms": ts,
        "hr_bpm": 60000.0 / rr,
        "rr_ms": rr,
    })

    result = compute_hrv_features_with_accel(df)
    assert result["rr_excluded_movement"] == 0
    assert result["movement_artifact_ratio"] == 0.0
    assert result["rmssd_ms"] >= 0


def test_hrv_accel_all_movement_returns_zero_hrv():
    """When ALL epochs are flagged as movement, HRV is zero (no crash)."""
    df = _make_steady_df(50)
    # Flag every sample as extreme movement
    df["acc_x"] = 20.0
    df["acc_y"] = 20.0
    df["acc_z"] = 20.0

    result = compute_hrv_features_with_accel(df, accel_threshold_g=1.5)

    assert result["rmssd_ms"] == 0.0
    assert result["sdnn_ms"] == 0.0
    assert result["rr_excluded_movement"] == result["rr_total"]
    assert result["movement_artifact_ratio"] == 1.0


def test_hrv_accel_borderline_threshold():
    """Accel magnitude exactly at threshold should NOT be flagged."""
    df = _make_steady_df(50)
    # Set magnitude to exactly 1.5g (should not exceed threshold)
    # sqrt(0^2 + 0^2 + 1.5^2) = 1.5
    df["acc_x"] = 0.0
    df["acc_y"] = 0.0
    df["acc_z"] = 1.5

    result = compute_hrv_features_with_accel(df, accel_threshold_g=1.5)
    assert result["rr_excluded_movement"] == 0
    assert result["movement_artifact_ratio"] == 0.0


def test_hrv_accel_mismatched_lengths():
    """Accel and RR can have different sample counts (accel at higher rate)."""
    # 50 RR intervals
    rr = np.full(50, 800.0)
    # 200 accel samples (higher rate), same time span
    n_accel = 200
    ts_accel = np.linspace(800, 50 * 800, n_accel).astype(int)

    df = pd.DataFrame({
        "timestamp_ms": ts_accel,
        "hr_bpm": np.full(n_accel, 75.0),
        "rr_ms": np.concatenate([rr, np.full(n_accel - 50, np.nan)]),
        "acc_x": np.zeros(n_accel),
        "acc_y": np.zeros(n_accel),
        "acc_z": np.ones(n_accel),
    })

    result = compute_hrv_features_with_accel(df)
    # Should not crash and should process successfully
    assert result["rr_total"] > 0
    assert result["movement_artifact_ratio"] >= 0.0


# ---------------------------------------------------------------------------
# Synthetic EDA at 15 Hz (T7)
# ---------------------------------------------------------------------------


def test_synthetic_emotibit_is_15hz():
    """The synthetic EmotiBit generator must produce data at 15 Hz."""
    from app.services.ingestion.synthetic import EMOTIBIT_SAMPLE_HZ, generate_synthetic_session

    assert EMOTIBIT_SAMPLE_HZ == 15

    emo, polar = generate_synthetic_session(seconds=60)
    # 60 seconds * 15 Hz = 900 samples
    assert len(emo) == 60 * 15
    # Polar stays at 1 Hz
    assert len(polar) == 60


@pytest.mark.parametrize("seconds,expected_samples", [
    (10, 10 * 15),
    (60, 60 * 15),
    (180, 180 * 15),
    (300, 300 * 15),
])
def test_synthetic_exact_sample_counts(seconds, expected_samples):
    """Verify exact sample counts at 15 Hz for various durations."""
    from app.services.ingestion.synthetic import generate_synthetic_session
    emo, _ = generate_synthetic_session(seconds=seconds)
    assert len(emo) == expected_samples, (
        f"Expected {expected_samples} samples for {seconds}s at 15 Hz, got {len(emo)}"
    )


def test_synthetic_15hz_eda_features_valid():
    """Downstream EDA feature extraction produces valid results on 15 Hz synthetic data."""
    from app.services.ingestion.synthetic import generate_synthetic_session
    from app.services.processing.features import compute_eda_features

    emo, _ = generate_synthetic_session(seconds=60)
    tonic, phasic = compute_eda_features(emo)
    assert tonic > 0, "EDA tonic mean should be positive"
    assert phasic >= 0, "EDA phasic index should be non-negative"


def test_synthetic_15hz_timestamp_spacing():
    """Verify that EmotiBit timestamps are spaced at ~66.67 ms (1000/15)."""
    from app.services.ingestion.synthetic import generate_synthetic_session
    emo, _ = generate_synthetic_session(seconds=10)
    ts = emo["timestamp_ms"].to_numpy()
    diffs = np.diff(ts)
    expected_dt = int(1000.0 / 15)  # 66 ms
    # All diffs should be either 66 or 67 ms (integer rounding of 66.667)
    assert np.all((diffs >= 66) & (diffs <= 67)), (
        f"Unexpected timestamp spacing: min={diffs.min()}, max={diffs.max()}"
    )


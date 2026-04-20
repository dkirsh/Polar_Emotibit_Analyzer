import numpy as np
import pandas as pd
import pytest

from app.services.processing.features import (
    compute_edr,
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

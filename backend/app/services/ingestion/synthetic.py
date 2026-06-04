"""Synthetic data generation for hardware-free test validation."""

from __future__ import annotations

import numpy as np
import pandas as pd


# EmotiBit samples EDA (and accelerometer) at ~15 Hz; Polar HR is at 1 Hz.
EMOTIBIT_SAMPLE_HZ = 15


def generate_synthetic_session(seconds: int = 180) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Generate synthetic EmotiBit and Polar traces for test workflows.

    EmotiBit channels (EDA, accelerometer, respiration) are generated at
    15 Hz to match real EmotiBit hardware sampling rate.  Polar HR is
    generated at 1 Hz (beat-level).
    """
    rng = np.random.default_rng(42)

    # EmotiBit at 15 Hz: one sample every 1000/15 ≈ 66.67 ms
    dt_ms = 1000.0 / EMOTIBIT_SAMPLE_HZ
    n_emotibit = seconds * EMOTIBIT_SAMPLE_HZ
    emotibit_ts = np.arange(0, n_emotibit) * dt_ms

    # Polar at 1 Hz
    polar_base = np.arange(0, seconds * 1000, 1000)

    # Time arrays in seconds for signal generation
    t_emo_s = emotibit_ts / 1000.0
    t_pol_s = polar_base / 1000.0

    hr = 72 + 8 * np.sin(np.linspace(0, 3.14, len(polar_base))) + rng.normal(0, 1.2, len(polar_base))
    eda = 2.8 + 0.25 * np.sin(np.linspace(0, 7, n_emotibit)) + rng.normal(0, 0.05, n_emotibit)
    resp = 14.0 + 1.5 * np.sin(np.linspace(0, 10, n_emotibit)) + rng.normal(0, 0.3, n_emotibit)
    acc_x = rng.normal(0.0, 0.015, n_emotibit)
    acc_y = rng.normal(0.0, 0.015, n_emotibit)
    acc_z = 1.0 + rng.normal(0.0, 0.02, n_emotibit)

    # Inject two brief movement bursts for artifact-filter testing.
    # Bursts at ~33% and ~90% through the trace; scaled to 15 Hz sample count.
    n = n_emotibit
    burst_starts = [n // 3, int(n * 0.9)] if n >= 12 else []
    burst_len_samples = 6 * EMOTIBIT_SAMPLE_HZ  # ~6 seconds of motion
    for start in burst_starts:
        if start >= n:
            continue
        end = min(start + burst_len_samples, n)
        burst_len = end - start
        if burst_len <= 0:
            continue
        acc_x[start:end] += rng.normal(0.45, 0.08, burst_len)
        acc_y[start:end] += rng.normal(0.35, 0.08, burst_len)
        acc_z[start:end] += rng.normal(0.25, 0.06, burst_len)

    emotibit = pd.DataFrame(
        {
            "timestamp_ms": emotibit_ts.astype(int),
            "eda_us": eda,
            "acc_x": acc_x,
            "acc_y": acc_y,
            "acc_z": acc_z,
            "resp_bpm": resp,
        }
    )
    # Inject slight device drift in Polar timestamps.
    polar_ts = (polar_base * 1.0006 + 125).astype(int)
    polar = pd.DataFrame({"timestamp_ms": polar_ts, "hr_bpm": hr})
    return emotibit, polar


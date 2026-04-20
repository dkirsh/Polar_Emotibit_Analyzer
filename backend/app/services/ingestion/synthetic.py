"""Synthetic data generation for hardware-free test validation."""

from __future__ import annotations

import numpy as np
import pandas as pd


def generate_synthetic_session(seconds: int = 180) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Generate synthetic EmotiBit and Polar traces for test workflows."""
    rng = np.random.default_rng(42)
    base = np.arange(0, seconds * 1000, 1000)

    hr = 72 + 8 * np.sin(np.linspace(0, 3.14, len(base))) + rng.normal(0, 1.2, len(base))
    eda = 2.8 + 0.25 * np.sin(np.linspace(0, 7, len(base))) + rng.normal(0, 0.05, len(base))
    resp = 14.0 + 1.5 * np.sin(np.linspace(0, 10, len(base))) + rng.normal(0, 0.3, len(base))
    acc_x = rng.normal(0.0, 0.015, len(base))
    acc_y = rng.normal(0.0, 0.015, len(base))
    acc_z = 1.0 + rng.normal(0.0, 0.02, len(base))

    # Inject two brief movement bursts for artifact-filter testing.
    # Place bursts at ~33% and ~90% through the trace; skip any burst
    # whose start falls beyond the available samples.
    n = len(base)
    burst_starts = [n // 3, int(n * 0.9)] if n >= 12 else []
    for start in burst_starts:
        if start >= n:
            continue
        end = min(start + 6, n)
        burst_len = end - start
        if burst_len <= 0:
            continue
        acc_x[start:end] += rng.normal(0.45, 0.08, burst_len)
        acc_y[start:end] += rng.normal(0.35, 0.08, burst_len)
        acc_z[start:end] += rng.normal(0.25, 0.06, burst_len)

    emotibit = pd.DataFrame(
        {
            "timestamp_ms": base,
            "eda_us": eda,
            "acc_x": acc_x,
            "acc_y": acc_y,
            "acc_z": acc_z,
            "resp_bpm": resp,
        }
    )
    # Inject slight device drift in Polar timestamps.
    polar_ts = (base * 1.0006 + 125).astype(int)
    polar = pd.DataFrame({"timestamp_ms": polar_ts, "hr_bpm": hr})
    return emotibit, polar

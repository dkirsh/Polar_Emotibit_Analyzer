"""Signal synchronization utilities."""

from __future__ import annotations

import numpy as np
import pandas as pd


def synchronize_signals(
    emotibit: pd.DataFrame,
    polar: pd.DataFrame,
    *,
    tolerance_ms: int = 1000,
    ptt_offset_ms: int = 0,
) -> pd.DataFrame:
    """Synchronize EmotiBit and Polar streams by nearest timestamp.

    Parameters
    ----------
    emotibit:
        EmotiBit frame with at least ``timestamp_ms`` and ``eda_us``.
    polar:
        Polar frame with at least ``timestamp_ms`` and ``hr_bpm``.
    tolerance_ms:
        Maximum nearest-neighbor distance allowed for merge.
    ptt_offset_ms:
        Optional offset applied to EmotiBit timestamps during matching.
        Useful when compensating pulse transit delay between modalities.
    """
    emo_cols = ["timestamp_ms", "eda_us"]
    for optional in ("acc_x", "acc_y", "acc_z", "resp_bpm"):
        if optional in emotibit.columns:
            emo_cols.append(optional)

    emo = emotibit[emo_cols].copy()
    emo["timestamp_ms"] = emo["timestamp_ms"].astype(int)
    emo["match_timestamp_ms"] = emo["timestamp_ms"] - int(ptt_offset_ms)
    emo = emo.sort_values("match_timestamp_ms")

    pol_cols = ["timestamp_ms", "hr_bpm"]
    if "rr_ms" in polar.columns:
        pol_cols.append("rr_ms")
    pol = polar[pol_cols].copy()
    pol["timestamp_ms"] = pol["timestamp_ms"].astype(int)
    pol = pol.rename(columns={"timestamp_ms": "polar_timestamp_ms"}).sort_values("polar_timestamp_ms")

    merged = pd.merge_asof(
        emo,
        pol,
        left_on="match_timestamp_ms",
        right_on="polar_timestamp_ms",
        direction="nearest",
        tolerance=int(tolerance_ms),
    )
    merged = merged.dropna(subset=["hr_bpm", "eda_us"]).drop(columns=["match_timestamp_ms"])

    if "rr_ms" in merged.columns:
        rr_numeric = pd.to_numeric(merged["rr_ms"], errors="coerce")
        derived_rr = 60000.0 / pd.to_numeric(merged["hr_bpm"], errors="coerce")
        merged["rr_source"] = np.where(rr_numeric.notna(), "native_polar", "derived_from_bpm")
        merged["rr_ms"] = rr_numeric.fillna(derived_rr)
    else:
        merged["rr_source"] = "derived_from_bpm"
        merged["rr_ms"] = 60000.0 / pd.to_numeric(merged["hr_bpm"], errors="coerce")

    return merged.reset_index(drop=True)


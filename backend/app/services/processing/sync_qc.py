"""Synchronization quality control for multi-device physiological data.

Version: 2.1 (NEW)
Created for [Repair 1.4]: Extracts core QC logic from standalone
scripts/run_sync_qc.py and integrates it into the runtime pipeline.

V2.0 had a 356-line standalone sync QC script that was never called by the
pipeline. The pipeline ran synchronize_signals -> clean_signals -> features
unconditionally, without checking whether the synchronization was any good.
A session with 5% temporal overlap and 20% drift still produced analysis
results presented with the same confidence as a perfect session.

This module provides compute_sync_qc() which returns a structured report
with:
  - sync_confidence_score (0-100)
  - sync_confidence_band ("green"/"yellow"/"red")
  - sync_confidence_gate ("go"/"conditional_go"/"no_go")
  - failure_reasons and recommended_fixes

DESIGN DECISION — Scoring components:
    The composite score weights five aspects of synchronization quality:
    1. Overlap ratio (30%): fraction of temporal overlap after drift correction
    2. Drift deviation (25%): |slope - 1.0|, how far drift deviates from unity
    3. Sync ratio (20%): matched_samples / total_samples
    4. Residual lag (15%): mean absolute time difference between matched pairs
    5. Jitter (10%): temporal jitter as fraction of median inter-sample interval

    These weights are engineering heuristics, not empirically optimized. They
    reflect the relative importance of each factor for downstream feature
    validity. Overlap and drift are weighted highest because they determine
    whether the signals genuinely correspond to the same time period.

DESIGN DECISION — Gate thresholds:
    green (>= 80): good sync, all features reliable
    yellow (>= 50): marginal sync, time-domain features OK, frequency questionable
    red (< 50): poor sync, features unreliable

    These thresholds are conservative. A score of 50 typically means either
    <50% temporal overlap or >1% drift — either of which would concern a
    careful researcher.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from app.models.signals import PiecewiseDriftModel


@dataclass
class SyncQcReport:
    """Structured synchronization quality report."""
    sync_confidence_score: float = 0.0
    sync_confidence_band: str = "red"
    sync_confidence_gate: str = "no_go"
    corrected_overlap_ms: float = 0.0
    drift_pct_from_unity: float = 0.0
    sync_ratio: float = 0.0
    residual_lag_ms: float = 0.0
    jitter_pct_avg: float = 0.0
    failure_reasons: list[str] = field(default_factory=list)
    recommended_fixes: list[str] = field(default_factory=list)
    overall_pass: bool = False


def compute_sync_qc(
    emotibit_df: pd.DataFrame,
    polar_df: pd.DataFrame,
    synced_df: pd.DataFrame,
    drift_model: PiecewiseDriftModel,
) -> SyncQcReport:
    """Compute synchronization quality metrics.

    Called by pipeline.py after synchronize_signals() to gate analysis
    quality. Returns a SyncQcReport that the pipeline uses to add
    quality flags and optionally halt processing.
    """
    report = SyncQcReport()
    reasons: list[str] = []
    fixes: list[str] = []

    # --- 1. Temporal overlap ---
    if len(emotibit_df) > 0 and len(polar_df) > 0:
        emo_start = int(emotibit_df["timestamp_ms"].min())
        emo_end = int(emotibit_df["timestamp_ms"].max())
        pol_start = int(polar_df["timestamp_ms"].min())
        pol_end = int(polar_df["timestamp_ms"].max())

        overlap_start = max(emo_start, pol_start)
        overlap_end = min(emo_end, pol_end)
        overlap_ms = max(0, overlap_end - overlap_start)
        total_span = max(1, max(emo_end, pol_end) - min(emo_start, pol_start))
        overlap_ratio = overlap_ms / total_span

        report.corrected_overlap_ms = float(overlap_ms)
    else:
        overlap_ratio = 0.0
        reasons.append("One or both input dataframes are empty")

    if overlap_ratio < 0.5:
        reasons.append(f"Low temporal overlap: {overlap_ratio:.1%}")
        fixes.append("Verify devices were recording simultaneously")

    # --- 2. Drift deviation from unity ---
    if drift_model.segments:
        primary_slope = drift_model.segments[0].slope
        drift_pct = abs(primary_slope - 1.0) * 100
        report.drift_pct_from_unity = drift_pct
    else:
        drift_pct = 0.0

    if drift_pct > 1.0:
        reasons.append(f"High drift: {drift_pct:.2f}% from unity")
        fixes.append("Check if device clocks were reset during session")

    # --- 3. Sync ratio ---
    total_input = max(1, len(emotibit_df) + len(polar_df))
    sync_ratio = (2 * len(synced_df)) / total_input if total_input > 0 else 0.0
    report.sync_ratio = sync_ratio

    if sync_ratio < 0.3:
        reasons.append(f"Low sync ratio: {sync_ratio:.1%} of samples matched")
        fixes.append("Check merge tolerance; sampling rates may need alignment")

    # --- 4. Residual lag ---
    if "polar_timestamp_ms" in synced_df.columns and "timestamp_ms" in synced_df.columns:
        time_diffs = np.abs(
            synced_df["timestamp_ms"].to_numpy(dtype=float)
            - synced_df["polar_timestamp_ms"].to_numpy(dtype=float)
        )
        residual_lag = float(np.mean(time_diffs))
        report.residual_lag_ms = residual_lag
    else:
        residual_lag = 0.0

    if residual_lag > 500:
        reasons.append(f"High residual lag: {residual_lag:.0f} ms mean")
        fixes.append("Consider tighter merge tolerance or piecewise drift with more anchors")

    # --- 5. Jitter ---
    jitter_pcts = []
    for col_name, source_df in [("timestamp_ms", emotibit_df), ("timestamp_ms", polar_df)]:
        if len(source_df) > 2:
            ts = source_df[col_name].to_numpy(dtype=float)
            intervals = np.diff(ts)
            if len(intervals) > 0:
                median_interval = float(np.median(intervals))
                if median_interval > 0:
                    mad = float(np.median(np.abs(intervals - median_interval)))
                    jitter_pcts.append(mad / median_interval * 100)
    jitter_avg = float(np.mean(jitter_pcts)) if jitter_pcts else 0.0
    report.jitter_pct_avg = jitter_avg

    if jitter_avg > 20:
        reasons.append(f"High timestamp jitter: {jitter_avg:.1f}%")
        fixes.append("Check for Bluetooth packet loss or WiFi timesync gaps")

    # --- Composite score ---
    # Weighted components (see module docstring for rationale)
    overlap_score = min(1.0, overlap_ratio / 0.8) * 100  # full score at 80%+ overlap
    drift_score = max(0, 100 - drift_pct * 50)  # 0 at 2%+ drift
    sync_score = min(1.0, sync_ratio / 0.6) * 100  # full score at 60%+ sync
    lag_score = max(0, 100 - residual_lag / 5)  # 0 at 500ms+ lag
    jitter_score = max(0, 100 - jitter_avg * 2)  # 0 at 50%+ jitter

    composite = (
        0.30 * overlap_score
        + 0.25 * drift_score
        + 0.20 * sync_score
        + 0.15 * lag_score
        + 0.10 * jitter_score
    )
    report.sync_confidence_score = round(composite, 1)

    # --- Gate classification ---
    if composite >= 80:
        report.sync_confidence_band = "green"
        report.sync_confidence_gate = "go"
        report.overall_pass = True
    elif composite >= 50:
        report.sync_confidence_band = "yellow"
        report.sync_confidence_gate = "conditional_go"
        report.overall_pass = True
    else:
        report.sync_confidence_band = "red"
        report.sync_confidence_gate = "no_go"
        report.overall_pass = False

    report.failure_reasons = reasons
    report.recommended_fixes = fixes
    return report

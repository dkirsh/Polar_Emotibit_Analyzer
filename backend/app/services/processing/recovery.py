"""Recovery index computation for post-stressor physiological recovery.

Quantifies HOW FAST and HOW COMPLETELY a participant recovers from a
stressor, across multiple physiological channels. Designed for biophilic
recovery studies (plants vs no-plants).

Metrics per channel:
  - recovery_slope: rate of change during recovery phase
  - t50: time (seconds) to reach 50% of stressor-baseline difference
  - completeness: fraction of stressor-baseline difference recovered
  - area_under_curve: integrated recovery trajectory

Channels:
  - HR (heart rate deceleration)
  - RMSSD (vagal rebound)
  - EDA (SCL return to baseline)
  - Respiratory rate (breathing rate normalization)
  - Temperature (peripheral vasodilation rewarming)

References:
  - Gladwell et al. (2012). Int J Environ Res Public Health, 9(10), 3612-3624.
  - Ulrich et al. (1991). J Environ Psychol, 11(3), 201-230.
  - Parsons & Tassinary (2009). Int J Psychophysiol, 73(2), 95-100.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np


@dataclass
class ChannelRecovery:
    """Recovery metrics for a single physiological channel."""
    channel: str = ""
    baseline_value: float | None = None
    stressor_value: float | None = None
    recovery_value: float | None = None
    delta_stressor: float | None = None  # stressor - baseline
    delta_recovery: float | None = None  # recovery - stressor
    recovery_slope: float | None = None  # units per second during recovery
    t50_s: float | None = None  # seconds to 50% recovery
    completeness: float | None = None  # fraction recovered (0-1)
    auc: float | None = None  # area under recovery curve
    direction: str = ""  # 'decrease' or 'increase' indicates recovery direction


@dataclass
class RecoveryIndex:
    """Multi-channel recovery assessment."""
    channels: list[ChannelRecovery] = field(default_factory=list)
    composite_score: float | None = None  # weighted composite (0=no recovery, 1=full)
    recovery_duration_s: float | None = None
    stressor_duration_s: float | None = None
    baseline_duration_s: float | None = None


def compute_channel_recovery(
    timeseries: np.ndarray,
    timestamps_s: np.ndarray,
    baseline_mask: np.ndarray,
    stressor_mask: np.ndarray,
    recovery_mask: np.ndarray,
    channel_name: str,
    recovery_direction: str = "decrease",
) -> ChannelRecovery:
    """Compute recovery metrics for a single physiological channel.

    Args:
        timeseries: 1D signal array (e.g., HR values over time).
        timestamps_s: Corresponding timestamps in seconds.
        baseline_mask: Boolean mask for baseline phase.
        stressor_mask: Boolean mask for stressor phase.
        recovery_mask: Boolean mask for recovery phase.
        channel_name: Human-readable channel name.
        recovery_direction: 'decrease' if recovery means the signal drops
            (e.g., HR, EDA, resp rate), 'increase' if recovery means the
            signal rises (e.g., RMSSD, HRV, temperature).

    Returns:
        ChannelRecovery with all computed metrics.
    """
    result = ChannelRecovery(channel=channel_name, direction=recovery_direction)

    # Extract phase values
    bl_vals = timeseries[baseline_mask]
    st_vals = timeseries[stressor_mask]
    rc_vals = timeseries[recovery_mask]
    rc_times = timestamps_s[recovery_mask]

    if len(bl_vals) < 3 or len(st_vals) < 3 or len(rc_vals) < 3:
        return result

    bl_mean = float(np.nanmean(bl_vals))
    st_mean = float(np.nanmean(st_vals))
    rc_mean = float(np.nanmean(rc_vals))

    result.baseline_value = bl_mean
    result.stressor_value = st_mean
    result.recovery_value = rc_mean
    result.delta_stressor = st_mean - bl_mean
    result.delta_recovery = rc_mean - st_mean

    # Recovery slope (linear fit during recovery phase)
    if len(rc_vals) >= 5:
        valid = np.isfinite(rc_vals) & np.isfinite(rc_times)
        if np.sum(valid) >= 5:
            t_rel = rc_times[valid] - rc_times[valid][0]
            slope, _ = np.polyfit(t_rel, rc_vals[valid], 1)
            result.recovery_slope = float(slope)

    # T50: time to reach 50% of stressor-baseline difference
    diff_total = st_mean - bl_mean
    if abs(diff_total) > 1e-12 and len(rc_vals) >= 3:
        target_50 = st_mean - 0.5 * diff_total  # midpoint between stressor and baseline
        t_rel = rc_times - rc_times[0]
        
        if recovery_direction == "decrease":
            # Signal should drop: find first time below target
            crossings = np.where(rc_vals <= target_50)[0]
        else:
            # Signal should rise: find first time above target
            crossings = np.where(rc_vals >= target_50)[0]

        if len(crossings) > 0:
            result.t50_s = float(t_rel[crossings[0]])

    # Completeness: what fraction of the stressor-baseline gap was recovered?
    if abs(diff_total) > 1e-12:
        if recovery_direction == "decrease":
            recovered = st_mean - rc_mean
        else:
            recovered = rc_mean - st_mean
        result.completeness = float(np.clip(recovered / abs(diff_total), 0.0, 1.5))

    # AUC: area under the recovery curve (normalized by duration)
    if len(rc_vals) >= 3 and len(rc_times) >= 3:
        t_rel = rc_times - rc_times[0]
        duration = t_rel[-1] - t_rel[0]
        if duration > 0:
            _integrate = getattr(np, 'trapezoid', None) or getattr(np, 'trapz')
            # Normalize relative to baseline
            shifted = np.abs(rc_vals - bl_mean)
            result.auc = float(_integrate(shifted, t_rel) / duration)

    return result


def compute_recovery_index(
    channels: list[ChannelRecovery],
    weights: dict[str, float] | None = None,
) -> RecoveryIndex:
    """Compute composite recovery index from multiple channels.

    Default weights optimized for biophilic recovery studies:
      - RMSSD (vagal rebound): 0.30
      - Resp rate: 0.20
      - EDA: 0.20
      - HR: 0.15
      - Temperature: 0.10
      - SD1/SD2 rigidity: 0.05

    Args:
        channels: List of per-channel recovery results.
        weights: Optional channel_name -> weight mapping.

    Returns:
        RecoveryIndex with composite score.
    """
    default_weights = {
        'rmssd': 0.30,
        'resp_rate': 0.20,
        'eda': 0.20,
        'hr': 0.15,
        'temperature': 0.10,
        'rigidity': 0.05,
    }
    w = weights or default_weights

    result = RecoveryIndex(channels=channels)

    # Compute weighted composite from completeness scores
    total_weight = 0.0
    weighted_sum = 0.0
    for ch in channels:
        ch_weight = w.get(ch.channel, 0.0)
        if ch.completeness is not None and ch_weight > 0:
            weighted_sum += ch_weight * ch.completeness
            total_weight += ch_weight

    if total_weight > 0:
        result.composite_score = float(np.clip(weighted_sum / total_weight, 0.0, 1.0))

    return result


def compute_recovery_from_phase_stats(
    phase_stats: dict[str, dict[str, float]],
    recovery_duration_s: float | None = None,
) -> RecoveryIndex:
    """Convenience wrapper: compute recovery from pre-aggregated phase statistics.

    Args:
        phase_stats: Dict with keys 'baseline', 'stressor', 'recovery',
            each mapping to a dict of channel_name -> mean_value.
            Example:
                {
                    'baseline': {'hr': 72, 'rmssd': 45, 'eda': 3.2, 'resp_rate': 14},
                    'stressor': {'hr': 88, 'rmssd': 22, 'eda': 8.1, 'resp_rate': 22},
                    'recovery': {'hr': 78, 'rmssd': 35, 'eda': 5.0, 'resp_rate': 16},
                }
        recovery_duration_s: Duration of recovery phase.

    Returns:
        RecoveryIndex with per-channel and composite metrics.
    """
    bl = phase_stats.get('baseline', {})
    st = phase_stats.get('stressor', {})
    rc = phase_stats.get('recovery', {})

    # Define recovery direction for each channel
    directions = {
        'hr': 'decrease',
        'rmssd': 'increase',
        'eda': 'decrease',
        'resp_rate': 'decrease',
        'temperature': 'increase',
        'pnn50': 'increase',
        'sd1_sd2_ratio': 'increase',
        'rigidity': 'decrease',
    }

    channels: list[ChannelRecovery] = []
    all_keys = set(bl.keys()) | set(st.keys()) | set(rc.keys())

    for key in sorted(all_keys):
        if key not in bl or key not in st or key not in rc:
            continue
        direction = directions.get(key, 'decrease')

        ch = ChannelRecovery(
            channel=key,
            direction=direction,
            baseline_value=bl[key],
            stressor_value=st[key],
            recovery_value=rc[key],
            delta_stressor=st[key] - bl[key],
            delta_recovery=rc[key] - st[key],
        )

        # Completeness
        diff_total = st[key] - bl[key]
        if abs(diff_total) > 1e-12:
            if direction == 'decrease':
                recovered = st[key] - rc[key]
            else:
                recovered = rc[key] - st[key]
            ch.completeness = float(np.clip(recovered / abs(diff_total), 0.0, 1.5))

        channels.append(ch)

    result = compute_recovery_index(channels)
    result.recovery_duration_s = recovery_duration_s
    return result

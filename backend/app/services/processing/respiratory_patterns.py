"""Respiratory stress pattern analysis.

Extracts individual breath cycles from Vernier belt data, classifies them
into 7 canonical stress-breathing patterns, finds exemplar waveforms, and
generates superimposed comparison figures (normal vs stressed).

Patterns detected:
  1. Tachypnea — elevated respiratory rate (>18 bpm)
  2. I:E ratio shift — exhale shortens toward 1:1 (normal ~1:2)
  3. Shallow breathing — reduced tidal volume / amplitude
  4. Irregular rhythm — high cycle-duration CV (>0.30)
  5. Stress sigh — abnormally deep breath disrupting rhythm
  6. Breath-hold / apnea — extended cycle with suppressed amplitude
  7. Inverted I:E — inhale >> exhale (I:E > 1.5)

References:
  - Russo et al. (2017). Front Psychol, 8, 874
  - Homma & Masaoka (2008). Neurosci Res, 61(2), 129-138
"""

from __future__ import annotations

import base64
import io
import logging
import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from scipy.ndimage import uniform_filter1d

from app.services.ingestion.vernier_parser import (
    VERNIER_SAMPLE_RATE_HZ,
    baseline_als,
    peakdetect_simple,
)

# Backward-compatible local aliases for any in-module references
_baseline_als = baseline_als
_peakdetect_simple = peakdetect_simple

log = logging.getLogger(__name__)

# Phase classification defaults
DEFAULT_CALM_PHASES = frozenset({
    "biometric_baseline", "ser_baseline", "break_1", "break_2",
})
DEFAULT_STRESS_PHASES = frozenset({
    "stressor_test_1", "stressor_test_2",
    "sart_1", "sart_2", "sart_3", "sart_4", "sart_5", "sart_6",
    "practice_stressor_test",
})

# Pattern classification thresholds
FAST_RATE_BPM = 18
PROLONGED_EXHALE_IE = 0.75
EQUAL_IE_MIN = 0.85
EQUAL_IE_MAX = 1.15
HIGH_IE_THRESHOLD = 1.5
CV_REGULAR = 0.15
CV_IRREGULAR = 0.30
SIGH_AMP_FACTOR = 1.5  # std above median
APNEA_MIN_DUR_S = 8
MIN_BREATH_DUR_S = 1.5
MAX_BREATH_DUR_S = 15
MIN_PHASE_DUR_S = 0.3


@dataclass(frozen=True)
class PatternConfig:
    """All threshold constants and phase labels for pattern analysis."""
    fast_rate_bpm: float = FAST_RATE_BPM
    prolonged_exhale_ie: float = PROLONGED_EXHALE_IE
    equal_ie_min: float = EQUAL_IE_MIN
    equal_ie_max: float = EQUAL_IE_MAX
    high_ie_threshold: float = HIGH_IE_THRESHOLD
    cv_regular: float = CV_REGULAR
    cv_irregular: float = CV_IRREGULAR
    sigh_amp_factor: float = SIGH_AMP_FACTOR
    apnea_min_dur_s: float = APNEA_MIN_DUR_S
    min_breath_dur_s: float = MIN_BREATH_DUR_S
    max_breath_dur_s: float = MAX_BREATH_DUR_S
    min_phase_dur_s: float = MIN_PHASE_DUR_S
    calm_phases: frozenset[str] = field(default_factory=lambda: DEFAULT_CALM_PHASES)
    stress_phases: frozenset[str] = field(default_factory=lambda: DEFAULT_STRESS_PHASES)


# ── Core: extract breath cycles ──────────────────────────────────────────────

def extract_breath_cycles(
    resp_z: np.ndarray,
    peaks: list[int],
    troughs: list[int],
    fs: int = VERNIER_SAMPLE_RATE_HZ,
    phase_markers: list[dict[str, Any]] | None = None,
    detrended: np.ndarray | None = None,
) -> pd.DataFrame:
    """Extract individual breath cycles from z-scored respiratory signal.

    Each cycle is trough → peak → trough (one full breath).

    Args:
        resp_z: Z-scored respiratory signal.
        peaks: Peak indices (end-of-inhale).
        troughs: Trough indices (end-of-exhale).
        fs: Sampling frequency.
        phase_markers: List of dicts with 'event_code' and 'elapsed_s'.

    Returns:
        DataFrame with one row per breath cycle: idx, t1_idx, pk_idx, t2_idx,
        t1_s, pk_s, t2_s, dur, rate_bpm, inhale, exhale, ie_ratio,
        duty_cycle, amplitude, phase, local_cv.
    """
    # Build phase lookup
    phases_sorted: list[tuple[float, str]] = []
    if phase_markers:
        for m in phase_markers:
            phases_sorted.append((m["elapsed_s"], m["event_code"]))
        phases_sorted.sort()

    def _phase_at(t: float) -> str:
        result = "unknown"
        for start, name in phases_sorted:
            if t >= start:
                result = name
            else:
                break
        return result

    cycles: list[dict[str, Any]] = []
    for i in range(len(troughs) - 1):
        t1_idx = troughs[i]
        t2_idx = troughs[i + 1]
        if t1_idx >= len(resp_z) or t2_idx >= len(resp_z):
            continue

        t1_s = t1_idx / fs
        t2_s = t2_idx / fs
        dur = t2_s - t1_s

        if dur < MIN_BREATH_DUR_S or dur > MAX_BREATH_DUR_S:
            continue

        pk_between = [p for p in peaks if t1_idx < p < t2_idx]
        if not pk_between:
            continue
        pk_idx = pk_between[0]
        pk_s = pk_idx / fs

        inhale = pk_s - t1_s
        exhale = t2_s - pk_s
        if inhale < MIN_PHASE_DUR_S or exhale < MIN_PHASE_DUR_S:
            continue

        segment = resp_z[t1_idx:t2_idx + 1]
        if detrended is not None:
            amplitude_raw = float(np.max(detrended[t1_idx:t2_idx + 1]) - np.min(detrended[t1_idx:t2_idx + 1]))
        else:
            amplitude_raw = float(np.max(segment) - np.min(segment))

        cycles.append({
            "idx": i,
            "t1_idx": t1_idx, "pk_idx": pk_idx, "t2_idx": t2_idx,
            "t1_s": t1_s, "pk_s": pk_s, "t2_s": t2_s,
            "dur": dur, "rate_bpm": 60.0 / dur,
            "inhale": inhale, "exhale": exhale,
            "ie_ratio": inhale / exhale,
            "duty_cycle": inhale / dur,
            "amplitude": amplitude_raw,
            "amplitude_z": float(np.max(segment) - np.min(segment)),
            "phase": _phase_at(t1_s),
        })

    df = pd.DataFrame(cycles)
    if len(df) > 0:
        df["local_cv"] = (
            df["dur"]
            .rolling(5, center=True, min_periods=5)
            .apply(lambda x: x.std() / x.mean() if x.mean() > 0 else 0)
        )
        if len(df) > 1:
            df['breath_rmssd'] = np.sqrt(
                df['dur'].diff().pow(2).rolling(5, center=True, min_periods=3).mean()
            )
    return df


# ── Pattern classification ───────────────────────────────────────────────────

def classify_stress_patterns(
    cycles_df: pd.DataFrame,
    calm_phases: frozenset[str] = DEFAULT_CALM_PHASES,
    stress_phases: frozenset[str] = DEFAULT_STRESS_PHASES,
    config: PatternConfig | None = None,
) -> dict[str, Any]:
    """Classify breath cycles into 7 canonical stress patterns.

    Returns:
        Dict with pattern name → {count, calm_count, examples_df, description}.
    """
    if config is None:
        config = PatternConfig()
    if len(cycles_df) == 0:
        return {}

    calm = cycles_df[cycles_df["phase"].isin(calm_phases)]
    stressed = cycles_df[cycles_df["phase"].isin(stress_phases)]

    amp_median = cycles_df["amplitude"].median()
    amp_std = cycles_df["amplitude"].std()
    dur_median = cycles_df["dur"].median()

    patterns: dict[str, dict[str, Any]] = {}

    # 1. Tachypnea
    fast = stressed[stressed["rate_bpm"] > FAST_RATE_BPM]
    normal_rate = calm[(calm["rate_bpm"] >= 12) & (calm["rate_bpm"] <= 16)]
    patterns["tachypnea"] = {
        "label": "Tachypnea (fast rate)",
        "description": "Respiratory rate >18 bpm during stress phases",
        "count": len(fast),
        "calm_count": len(normal_rate),
        "stressed_df": fast,
        "calm_df": normal_rate,
        "found": len(fast) > 0 and len(normal_rate) > 0,
    }

    # 2. I:E ratio shift
    equal_ie = stressed[stressed["ie_ratio"].between(EQUAL_IE_MIN, EQUAL_IE_MAX)]
    prolonged_exhale = calm[calm["ie_ratio"] < PROLONGED_EXHALE_IE]
    patterns["ie_shift"] = {
        "label": "I:E Ratio Shift (lost exhale)",
        "description": "I:E ratio approaches 1:1 (normal ~1:2)",
        "count": len(equal_ie),
        "calm_count": len(prolonged_exhale),
        "stressed_df": equal_ie,
        "calm_df": prolonged_exhale,
        "found": len(equal_ie) > 0 and len(prolonged_exhale) > 0,
    }

    # 3. Shallow breathing
    # Use calm amplitude to set the threshold (not self-referential)
    if len(calm) > 0 and calm['amplitude'].notna().any():
        shallow_threshold = calm['amplitude'].quantile(0.10)
    else:
        shallow_threshold = cycles_df['amplitude'].quantile(0.10)
    shallow = stressed[stressed['amplitude'] < shallow_threshold]
    deep = calm[calm["amplitude"] > calm["amplitude"].quantile(0.75)]
    patterns["shallow"] = {
        "label": "Shallow Breathing",
        "description": "Reduced breath amplitude (tidal volume) under stress",
        "count": len(shallow),
        "calm_count": len(deep),
        "stressed_df": shallow,
        "calm_df": deep,
        "found": len(shallow) > 0 and len(deep) > 0,
    }

    # 4. Irregular rhythm
    irregular = stressed[stressed["local_cv"] > CV_IRREGULAR].dropna(subset=["local_cv"])
    regular = calm[calm["local_cv"] < CV_REGULAR].dropna(subset=["local_cv"])
    patterns["irregular"] = {
        "label": "Irregular Rhythm",
        "description": "High cycle-duration CV (>0.30) — erratic breathing",
        "count": len(irregular),
        "calm_count": len(regular),
        "stressed_df": irregular,
        "calm_df": regular,
        "found": len(irregular) > 0 and len(regular) > 0,
    }

    # 5. Stress sigh
    sighs = stressed[
        (stressed["amplitude"] > amp_median + SIGH_AMP_FACTOR * amp_std)
        & (stressed["dur"] > dur_median)
    ]
    patterns["sigh"] = {
        "label": "Stress Sigh",
        "description": "Abnormally deep breath (>1.5σ above median) disrupting rhythm",
        "count": len(sighs),
        "calm_count": 0,
        "stressed_df": sighs,
        "calm_df": pd.DataFrame(),
        "found": len(sighs) > 0,
    }

    # 6. Breath-hold / apnea
    # Also require low intra-cycle variance (signal is near-flat)
    apnea_candidates = stressed[
        (stressed['dur'] > APNEA_MIN_DUR_S)
        & (stressed['amplitude'] < amp_median)
    ]
    # Filter to only those with low amplitude_z (z-scored flatness)
    if 'amplitude_z' in apnea_candidates.columns:
        apnea_candidates = apnea_candidates[apnea_candidates['amplitude_z'] < 1.0]
    apneas = apnea_candidates
    patterns["apnea"] = {
        "label": "Breath-Hold / Apnea",
        "description": "Extended cycle (>8s) with suppressed amplitude",
        "count": len(apneas),
        "calm_count": 0,
        "stressed_df": apneas,
        "calm_df": pd.DataFrame(),
        "found": len(apneas) > 0,
    }

    # 7. Inverted I:E
    inverted = stressed[stressed["ie_ratio"] > HIGH_IE_THRESHOLD]
    patterns["inverted_ie"] = {
        "label": "Inverted I:E",
        "description": "Inhale much longer than exhale (I:E >1.5)",
        "count": len(inverted),
        "calm_count": 0,
        "stressed_df": inverted,
        "calm_df": pd.DataFrame(),
        "found": len(inverted) > 0,
    }

    return patterns


# ── Exemplar selection ───────────────────────────────────────────────────────

def find_exemplars(
    cycles_df: pd.DataFrame,
    patterns: dict[str, Any],
    config: PatternConfig | None = None,
) -> dict[str, dict[str, Any]]:
    """Find the best exemplar breath cycle for each detected pattern.

    Also finds the best 'ideal normal' breath from calm phases.

    Returns:
        Dict with pattern name → {normal: row_dict, stressed: row_dict}
    """
    if config is None:
        config = PatternConfig()
    _calm_phases = config.calm_phases
    calm = cycles_df[cycles_df["phase"].isin(_calm_phases)]

    # Find ideal normal: closest to 15 bpm, I:E ~0.5
    normal_rate = calm[(calm["rate_bpm"] >= 12) & (calm["rate_bpm"] <= 18)]
    best_normal = None
    if len(normal_rate) > 0:
        scores = (normal_rate["rate_bpm"] - 15).abs() + (normal_rate["ie_ratio"] - 0.5).abs() * 5
        best_idx = scores.idxmin()
        best_normal = normal_rate.loc[best_idx].to_dict()
    elif len(calm) > 0:
        # Fallback: median calm breath
        scores = (calm["rate_bpm"] - calm["rate_bpm"].median()).abs()
        best_idx = scores.idxmin()
        best_normal = calm.loc[best_idx].to_dict()

    exemplars: dict[str, dict[str, Any]] = {}

    for pname, pdata in patterns.items():
        if not pdata["found"]:
            continue

        stressed_df = pdata["stressed_df"]
        if len(stressed_df) == 0:
            continue

        # Pick the most extreme exemplar for each pattern
        if pname == "tachypnea":
            ex = stressed_df.nlargest(1, "rate_bpm").iloc[0].to_dict()
        elif pname == "ie_shift":
            ex = stressed_df.iloc[
                (stressed_df["ie_ratio"] - 1.0).abs().argsort()[:1]
            ].iloc[0].to_dict()
        elif pname == "shallow":
            ex = stressed_df.nsmallest(1, "amplitude").iloc[0].to_dict()
        elif pname == "irregular":
            ex = stressed_df.nlargest(1, "local_cv").iloc[0].to_dict()
        elif pname == "sigh":
            ex = stressed_df.nlargest(1, "amplitude").iloc[0].to_dict()
        elif pname == "apnea":
            ex = stressed_df.nlargest(1, "dur").iloc[0].to_dict()
        elif pname == "inverted_ie":
            ex = stressed_df.nlargest(1, "ie_ratio").iloc[0].to_dict()
        else:
            ex = stressed_df.iloc[0].to_dict()

        # Use pattern-specific calm exemplar if available
        calm_ex = best_normal
        if pname == "ie_shift" and len(pdata["calm_df"]) > 0:
            scores = (pdata["calm_df"]["ie_ratio"] - 0.5).abs()
            calm_ex = pdata["calm_df"].loc[scores.idxmin()].to_dict()
        elif pname == "shallow" and len(pdata["calm_df"]) > 0:
            calm_ex = pdata["calm_df"].nlargest(1, "amplitude").iloc[0].to_dict()

        exemplars[pname] = {"normal": calm_ex, "stressed": ex}

    return exemplars


# ── Figure generation ────────────────────────────────────────────────────────

def _get_cycle_waveform(
    resp_z: np.ndarray,
    troughs: list[int],
    trough_array_idx: int,
    fs: int,
    normalize_time: bool = False,
    normalize_amp: bool = False,
    n_cycles: int = 1,
) -> tuple[np.ndarray, np.ndarray, float, float]:
    """Extract waveform for one or more breath cycles.

    Returns (time_array, signal_array, duration_s, peak_fraction).
    """
    s = troughs[trough_array_idx]
    e = troughs[min(trough_array_idx + n_cycles, len(troughs) - 1)]
    seg = resp_z[s:e + 1].copy()
    t = np.arange(len(seg)) / fs

    if normalize_time:
        t = np.linspace(0, 1, len(seg))
    if normalize_amp:
        rng = seg.max() - seg.min()
        if rng > 1e-12:
            seg = (seg - seg.min()) / rng

    dur = (e - s) / fs
    # Peak fraction for the first cycle
    pk_frac = 0.5
    return t, seg, dur, pk_frac


def _find_trough_array_idx(troughs: list[int], target_idx: int) -> int:
    """Find the trough array position closest to target sample index."""
    arr = np.array(troughs)
    return int(np.argmin(np.abs(arr - target_idx)))


def generate_pattern_figures(
    resp_z: np.ndarray,
    peaks: list[int],
    troughs: list[int],
    exemplars: dict[str, dict[str, Any]],
    patterns: dict[str, Any],
    fs: int = VERNIER_SAMPLE_RATE_HZ,
) -> tuple[dict[str, bytes], dict[str, str]]:
    """Generate PNG figures for each detected stress pattern.

    Returns ``(figures, skipped)`` where ``figures`` maps pattern_name → PNG
    bytes and ``skipped`` maps the name of any figure that could not be built to
    a human-readable reason. Per RESP_VIZ_CONTRACT this function never raises:
    each figure is attempted independently, so one bad figure cannot suppress
    the others or take down the surrounding table/stat computation.
    """
    skipped: dict[str, str] = {}
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        log.warning("matplotlib not available; skipping pattern figure generation")
        return {}, {"_all": "matplotlib not available"}

    CALM_COLOR = "#4CAF50"
    STRESS_COLOR = "#E53935"
    SIGH_COLOR = "#FF9800"
    APNEA_COLOR = "#9C27B0"

    COLORS = {
        "tachypnea": STRESS_COLOR,
        "ie_shift": STRESS_COLOR,
        "shallow": STRESS_COLOR,
        "irregular": STRESS_COLOR,
        "sigh": SIGH_COLOR,
        "apnea": APNEA_COLOR,
        "inverted_ie": STRESS_COLOR,
    }

    TITLES = {
        "tachypnea": "Tachypnea\n(faster breathing under stress)",
        "ie_shift": "I:E Ratio Shift\n(exhale shortens under stress)",
        "shallow": "Shallow Breathing\n(reduced tidal volume under stress)",
        "irregular": "Irregular Rhythm\n(erratic cycle durations under stress)",
        "sigh": "Stress Sigh\n(abnormally deep breath disrupting rhythm)",
        "apnea": "Breath-Hold\n(extended cycle with suppressed amplitude)",
        "inverted_ie": "Inverted I:E\n(inhale longer than exhale)",
    }

    figures: dict[str, bytes] = {}

    for pname, ex_data in exemplars.items():
        if ex_data.get("normal") is None or ex_data.get("stressed") is None:
            skipped[pname] = "no paired normal/stressed exemplar to contrast"
            continue

        normal = ex_data["normal"]
        stressed = ex_data["stressed"]
        color = COLORS.get(pname, STRESS_COLOR)
        title = TITLES.get(pname, pname)

        n_tidx = _find_trough_array_idx(troughs, int(normal["t1_idx"]))
        s_tidx = _find_trough_array_idx(troughs, int(stressed["t1_idx"]))

        fig, ax = plt.subplots(figsize=(7, 4.5))

        if pname == "tachypnea":
            # Same time axis — stress cycle fits inside calm
            t_n, s_n, dur_n, _ = _get_cycle_waveform(resp_z, troughs, n_tidx, fs)
            t_s, s_s, dur_s, _ = _get_cycle_waveform(resp_z, troughs, s_tidx, fs)
            ax.plot(t_n, s_n, color=CALM_COLOR, lw=2.5,
                    label=f"Calm: {60/dur_n:.0f} bpm ({dur_n:.1f}s)")
            ax.plot(t_s, s_s, color=color, lw=2.5,
                    label=f"Stressed: {60/dur_s:.0f} bpm ({dur_s:.1f}s)")
            ax.set_xlabel("Time (seconds)")

        elif pname in ("ie_shift", "inverted_ie"):
            # Time-normalized, amplitude-normalized shape comparison
            t_n, s_n, _, _ = _get_cycle_waveform(resp_z, troughs, n_tidx, fs,
                                                   normalize_time=True, normalize_amp=True)
            t_s, s_s, _, _ = _get_cycle_waveform(resp_z, troughs, s_tidx, fs,
                                                   normalize_time=True, normalize_amp=True)
            n_ie = normal.get("ie_ratio", 0)
            s_ie = stressed.get("ie_ratio", 0)
            ax.plot(t_n, s_n, color=CALM_COLOR, lw=2.5,
                    label=f"Normal: I:E = {n_ie:.2f}")
            ax.plot(t_s, s_s, color=color, lw=2.5,
                    label=f"Stressed: I:E = {s_ie:.2f}")
            ax.set_xlabel("Normalized Cycle (0 = exhale end, 1 = next exhale end)")
            ax.set_ylabel("Amplitude (normalized)")

        elif pname == "shallow":
            # Amplitude comparison, time-normalized
            t_n, s_n, _, _ = _get_cycle_waveform(resp_z, troughs, n_tidx, fs,
                                                   normalize_time=True)
            t_s, s_s, _, _ = _get_cycle_waveform(resp_z, troughs, s_tidx, fs,
                                                   normalize_time=True)
            n_amp = normal.get("amplitude", 0)
            s_amp = stressed.get("amplitude", 0)
            ax.plot(t_n, s_n, color=CALM_COLOR, lw=2.5,
                    label=f"Calm: amplitude = {n_amp:.1f}σ")
            ax.fill_between(t_n, s_n.min(), s_n, alpha=0.1, color=CALM_COLOR)
            ax.plot(t_s, s_s, color=color, lw=2.5,
                    label=f"Stressed: amplitude = {s_amp:.1f}σ")
            ax.fill_between(t_s, s_s.min(), s_s, alpha=0.1, color=color)
            ax.set_xlabel("Normalized Cycle")

        elif pname == "irregular":
            # 5-breath sequences side by side
            # Find regular sequence from calm
            reg_start = _find_regular_sequence(troughs, resp_z, normal, fs)
            irr_start = _find_irregular_sequence(troughs, resp_z, stressed, fs)
            if reg_start is not None:
                s_idx = troughs[reg_start]
                e_idx = troughs[min(reg_start + 5, len(troughs) - 1)]
                t_reg = (np.arange(s_idx, e_idx + 1) - s_idx) / fs
                s_reg = resp_z[s_idx:e_idx + 1]
                cv_r = normal.get("local_cv", 0)
                ax.plot(t_reg, s_reg, color=CALM_COLOR, lw=2,
                        label=f"Calm: 5 breaths, CV={cv_r:.2f}")
                for j in range(min(6, len(troughs) - reg_start)):
                    tidx = troughs[reg_start + j]
                    if tidx <= e_idx:
                        ax.plot((tidx - s_idx) / fs, resp_z[tidx], "v",
                                color=CALM_COLOR, ms=8)

            if irr_start is not None:
                s_idx2 = troughs[irr_start]
                e_idx2 = troughs[min(irr_start + 5, len(troughs) - 1)]
                t_irr = (np.arange(s_idx2, e_idx2 + 1) - s_idx2) / fs
                s_irr = resp_z[s_idx2:e_idx2 + 1]
                cv_i = stressed.get("local_cv", 0)
                ax.plot(t_irr, s_irr - 5, color=color, lw=2,
                        label=f"Stressed: 5 breaths, CV={cv_i:.2f}")
                for j in range(min(6, len(troughs) - irr_start)):
                    tidx = troughs[irr_start + j]
                    if tidx <= e_idx2:
                        ax.plot((tidx - s_idx2) / fs, resp_z[tidx] - 5, "v",
                                color=color, ms=8)

            ax.set_xlabel("Time (seconds)")

        elif pname == "sigh":
            # Sigh in context vs normal 3 breaths
            t_n, s_n, _, _ = _get_cycle_waveform(resp_z, troughs, n_tidx, fs,
                                                   n_cycles=3)
            ax.plot(t_n, s_n, color=CALM_COLOR, lw=2, alpha=0.7,
                    label="Calm: 3 even breaths")
            # Sigh with context
            ctx_start = max(0, s_tidx - 1)
            ctx_end = min(len(troughs) - 1, s_tidx + 2)
            s_s_idx = troughs[ctx_start]
            e_s_idx = troughs[ctx_end]
            t_sigh = (np.arange(s_s_idx, e_s_idx + 1) - s_s_idx) / fs
            s_sigh = resp_z[s_s_idx:e_s_idx + 1]
            s_amp = stressed.get("amplitude", 0)
            n_amp = normal.get("amplitude", 0)
            ax.plot(t_sigh, s_sigh, color=color, lw=2.5,
                    label=f"Sigh: amp={s_amp:.1f}σ (vs {n_amp:.1f}σ normal)")
            # Highlight sigh breath
            sh_s = troughs[s_tidx]
            sh_e = troughs[min(s_tidx + 1, len(troughs) - 1)]
            t_sh = (np.arange(sh_s, sh_e + 1) - s_s_idx) / fs
            ax.fill_between(t_sh, resp_z[sh_s:sh_e + 1], alpha=0.2, color=color)
            ax.set_xlabel("Time (seconds)")

        elif pname == "apnea":
            # Same time axis — normal vs extended hold
            t_n, s_n, dur_n, _ = _get_cycle_waveform(resp_z, troughs, n_tidx, fs)
            t_s, s_s, dur_s, _ = _get_cycle_waveform(resp_z, troughs, s_tidx, fs)
            ax.plot(t_n, s_n, color=CALM_COLOR, lw=2.5,
                    label=f"Normal: {dur_n:.1f}s cycle")
            ax.plot(t_s, s_s, color=color, lw=2.5,
                    label=f"Breath-hold: {dur_s:.1f}s cycle")
            ax.axvspan(t_n[-1], t_s[-1], alpha=0.08, color=color)
            ax.set_xlabel("Time (seconds)")

        ax.set_ylabel("Respiratory Force (z-scored)")
        ax.set_title(title, fontsize=11, fontweight="bold")
        ax.legend(fontsize=9, loc="best")
        ax.grid(True, alpha=0.15)

        buf = io.BytesIO()
        fig.tight_layout()
        fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
        plt.close(fig)
        figures[pname] = buf.getvalue()

    # ── Combined overview figure ──
    found_patterns = [p for p in exemplars if patterns.get(p, {}).get("found")]
    if len(found_patterns) >= 2:
        try:
            overview = _build_overview_figure(
                resp_z, peaks, troughs, exemplars, patterns, found_patterns, fs
            )
            if overview:
                figures["overview"] = overview
        except Exception as exc:  # noqa: BLE001 — viz must never raise
            skipped["overview"] = str(exc)
            try:
                plt.close("all")
            except Exception:  # noqa: BLE001
                pass

    return figures, skipped


def _find_regular_sequence(
    troughs: list[int],
    resp_z: np.ndarray,
    normal_row: dict[str, Any],
    fs: int,
) -> int | None:
    """Find a 5-breath regular sequence near the normal exemplar."""
    target_s = normal_row.get("t1_s", 0)
    target_idx = _find_trough_array_idx(troughs, int(target_s * fs))
    # Search ±20 troughs around the target
    for offset in range(20):
        for sign in [0, -1, 1]:
            i = target_idx + sign * offset
            if 0 <= i < len(troughs) - 5:
                durs = [(troughs[i + j + 1] - troughs[i + j]) / fs for j in range(5)]
                if all(1.5 < d < 8 for d in durs):
                    cv = np.std(durs) / np.mean(durs) if np.mean(durs) > 0 else 999
                    if cv < 0.20:
                        return i
    return None


def _find_irregular_sequence(
    troughs: list[int],
    resp_z: np.ndarray,
    stressed_row: dict[str, Any],
    fs: int,
) -> int | None:
    """Find a 5-breath irregular sequence near the stressed exemplar."""
    target_s = stressed_row.get("t1_s", 0)
    target_idx = _find_trough_array_idx(troughs, int(target_s * fs))
    for offset in range(30):
        for sign in [0, -1, 1]:
            i = target_idx + sign * offset
            if 0 <= i < len(troughs) - 5:
                durs = [(troughs[i + j + 1] - troughs[i + j]) / fs for j in range(5)]
                if all(1.4 < d < 12 for d in durs):
                    cv = np.std(durs) / np.mean(durs) if np.mean(durs) > 0 else 0
                    if cv > 0.25:
                        return i
    return None


def _build_overview_figure(
    resp_z: np.ndarray,
    peaks: list[int],
    troughs: list[int],
    exemplars: dict[str, dict[str, Any]],
    patterns: dict[str, Any],
    found_patterns: list[str],
    fs: int,
) -> bytes | None:
    """Build a multi-panel overview figure of all detected patterns."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return None

    # A pattern can be 'found' (has stressed breaths) yet lack a paired normal
    # exemplar; such panels cannot be drawn and must be excluded rather than
    # crashing the whole overview (RESP_VIZ_CONTRACT: viz never raises).
    found_patterns = [
        p for p in found_patterns
        if exemplars.get(p, {}).get("normal") is not None
        and exemplars.get(p, {}).get("stressed") is not None
    ]
    n = len(found_patterns)
    if n == 0:
        return None

    cols = min(n, 2)
    rows = (n + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(14, 5 * rows))
    fig.suptitle("Respiratory Stress Patterns Detected",
                 fontsize=14, fontweight="bold", y=0.98)

    if n == 1:
        axes = [axes]
    elif rows > 1 or cols > 1:
        axes = np.array(axes).flatten()

    COLORS = {
        "tachypnea": "#E53935", "ie_shift": "#E53935", "shallow": "#E53935",
        "irregular": "#E53935", "sigh": "#FF9800", "apnea": "#9C27B0",
        "inverted_ie": "#E53935",
    }

    for panel_idx, pname in enumerate(found_patterns):
        if panel_idx >= len(axes):
            break
        ax = axes[panel_idx]
        pdata = patterns[pname]
        ex = exemplars[pname]
        color = COLORS.get(pname, "#E53935")

        n_tidx = _find_trough_array_idx(troughs, int(ex["normal"]["t1_idx"]))
        s_tidx = _find_trough_array_idx(troughs, int(ex["stressed"]["t1_idx"]))

        # Simple: both waveforms time-normalized and amp-normalized
        t_n, s_n, dur_n, _ = _get_cycle_waveform(resp_z, troughs, n_tidx, fs,
                                                    normalize_time=True, normalize_amp=True)
        t_s, s_s, dur_s, _ = _get_cycle_waveform(resp_z, troughs, s_tidx, fs,
                                                    normalize_time=True, normalize_amp=True)
        ax.plot(t_n, s_n, color="#4CAF50", lw=2, label="Normal")
        ax.plot(t_s, s_s, color=color, lw=2, label="Stressed")
        ax.set_title(f"{pdata['label']} (n={pdata['count']})", fontsize=10, fontweight="bold")
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.15)

    # Hide unused
    for i in range(len(found_patterns), len(axes)):
        axes[i].set_visible(False)

    fig.tight_layout(rect=[0, 0, 1, 0.95])
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    return buf.getvalue()


# ── Cross-condition comparison ───────────────────────────────────────────────

def compare_conditions(
    cycles_df: pd.DataFrame,
    condition_map: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    """Compare respiratory patterns across experimental conditions.

    Args:
        cycles_df: Full breath-cycle DataFrame with 'phase' column.
        condition_map: Maps condition label → list of phase names.
            Example: {"no_plants": ["task_1"], "plants": ["task_2"]}

    Returns:
        Dict with per-condition summary stats and cross-condition comparison.
    """
    if condition_map is None or len(cycles_df) == 0:
        return {}

    summaries: dict[str, dict[str, Any]] = {}
    for cond_label, phases in condition_map.items():
        subset = cycles_df[cycles_df["phase"].isin(phases)]
        if len(subset) == 0:
            continue
        summaries[cond_label] = {
            "n_breaths": len(subset),
            "resp_rate_mean": round(float(subset["rate_bpm"].mean()), 1),
            "resp_rate_sd": round(float(subset["rate_bpm"].std()), 1),
            "ie_ratio_mean": round(float(subset["ie_ratio"].mean()), 2),
            "ie_ratio_sd": round(float(subset["ie_ratio"].std()), 2),
            "amplitude_mean": round(float(subset["amplitude"].mean()), 2),
            "amplitude_sd": round(float(subset["amplitude"].std()), 2),
            "cv_mean": round(float(subset["local_cv"].dropna().mean()), 3)
            if subset["local_cv"].notna().any() else None,
            "duty_cycle_mean": round(float(subset["duty_cycle"].mean()), 3),
        }

    return {
        "conditions": summaries,
        "n_conditions": len(summaries),
    }


# ── Top-level entry point ───────────────────────────────────────────────────



# ─────────────────────────────────────────────────────────────────────────────
# Public entry points — thin wrappers over the modular respiratory pipeline
# (app/services/processing/respiratory/). The heavy assembly that used to live
# here was superseded by the staged pipeline (signal → tables → stats → viz)
# so there is one assembly path, not two that drift. The pipeline is imported
# lazily inside each wrapper to avoid an import cycle (the pipeline's stages
# import the primitives defined above in this module).
# ─────────────────────────────────────────────────────────────────────────────

def analyze_respiratory_patterns(
    vernier_result: dict[str, Any],
    markers: list[dict[str, Any]] | None = None,
    condition_map: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    """Full respiratory stress pattern analysis (delegates to the pipeline).

    `condition_map` (name→phases) is treated as comparison-only groupings;
    stress/calm pattern detection uses the defaults, matching prior behaviour.
    The returned dict carries `_recompute` (the source-of-truth inputs) for the
    caller to persist.
    """
    from app.services.processing.respiratory import pipeline as _pipeline

    conditions = None
    if condition_map:
        conditions = [
            {"name": k, "markers": v, "role": "comparison"}
            for k, v in condition_map.items()
        ]
    res = _pipeline.run(vernier_result=vernier_result, markers=markers, conditions=conditions)
    out = dict(res.result)
    if res.recompute_payload is not None:
        out["_recompute"] = res.recompute_payload
    return out


def recompute_respiratory_patterns(
    recompute_payload: dict[str, Any],
    conditions: list[dict[str, Any]],
) -> dict[str, Any]:
    """Re-run pattern detection, figures, and comparison under a researcher-chosen
    grouping (delegates to the pipeline; single assembly path)."""
    from app.services.processing.respiratory import pipeline as _pipeline

    res = _pipeline.run(recompute_payload=recompute_payload, conditions=conditions)
    return res.result

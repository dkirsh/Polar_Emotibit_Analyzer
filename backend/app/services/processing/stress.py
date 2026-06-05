"""Experimental stress composite (NOT VALIDATED).

Version: 2.1 (caveat added)
Change from V2.0: [Repair 1.6] Added explicit "experimental, not validated"
    labeling throughout.

WARNING: This module computes an exploratory stress index from multiple
physiological channels. The formula and component weights are HEURISTIC,
not derived from psychometric validation against established stress
instruments (PSS, DASS-21) or physiological ground truth (cortisol).

Use this score for WITHIN-SESSION RELATIVE COMPARISON ONLY. Do not
interpret as an absolute measure of psychological stress. Do not use
for clinical decision-making.

SKEPTIC'S FAQ — "Why keep it at all if it's not validated?"
    Answer: Within-session relative change in a multimodal composite is
    informative even without absolute calibration. If a participant's
    stress score rises from 0.3 to 0.7 during a task, this reflects
    concurrent increases in sympathetic activation across multiple
    channels — a meaningful signal even if 0.3 and 0.7 have no absolute
    interpretation. The label ensures no one mistakes this for a
    validated psychometric instrument.

    For validated composites, see:
    - Healey & Picard (2005): LDA-derived weights from labeled driving data
    - Koldijk et al. (2016): SWELL dataset with concurrent DASS/NASA-TLX
    - Gjoreski et al. (2017): Random forest on lab/field stress data

    Validation against PSS/DASS is a 90-day task (Repair 3.4).

FORMULA (V2.2, respiratory channel added):
    stress = 0.25 * HR_norm + 0.25 * EDA_norm + 0.15 * phasic_norm
             + 0.15 * (1 - HRV_protection) + 0.20 * (1 - RSA_norm)

    HR_norm:   (mean_hr - 60) / (120 - 60), clipped to [0, 1]
    EDA_norm:  mean_eda / 20.0, clipped to [0, 1]
    phasic_norm: phasic_index / 2.5, clipped to [0, 1]
    HRV_protection: min(rmssd, 80) / 80  (higher RMSSD = lower stress)
    RSA_norm:  min(rsa_amplitude, 30) / 30 (higher RSA = deeper breathing
               = more vagal tone = lower stress; drops under cognitive load)

    Weights are informed by WESAD feature importance (Schmidt et al., 2018)
    but NOT empirically calibrated on this pipeline's data. The respiratory
    channel (RSA amplitude derived from RR intervals via EDR) receives high
    weight because respiration was the single strongest predictor in the
    WESAD benchmark (importance=0.35 for binary stress classification).
    Normalization ranges are approximate population ranges.
"""

from __future__ import annotations

import numpy as np

# Module-level flag for downstream consumers
STRESS_SCORE_VALIDATED = False
STRESS_SCORE_LABEL = "experimental composite (not psychometrically validated)"


def compute_stress_score(
    rmssd_ms: float,
    mean_hr_bpm: float,
    eda_mean_us: float,
    eda_phasic_index: float,
    rsa_amplitude: float | None = None,
    baseline_hr_bpm: float | None = None,
) -> float:
    """Compute exploratory stress composite (v1).

    Returns a value in [0.0, 1.0]. Higher = greater estimated sympathetic
    activation. NOT a validated stress measure — see module docstring.

    If rsa_amplitude is None (EDR could not be computed), falls back to
    4-channel mode with redistributed weights.
    """
    # Normalize each component to [0, 1]
    if baseline_hr_bpm is not None and baseline_hr_bpm > 0:
        # Baseline-relative: deviation from individual baseline
        hr_component = max(0.0, min(1.0, (mean_hr_bpm - baseline_hr_bpm) / 30.0))
    else:
        # Population-level fallback
        hr_component = max(0.0, min(1.0, (mean_hr_bpm - 60.0) / 60.0))
    eda_component = max(0.0, min(1.0, eda_mean_us / 20.0))
    phasic_component = max(0.0, min(1.0, eda_phasic_index / 2.5))
    # Log-transform RMSSD (distributions are log-normal; Shaffer & Ginsberg 2017)
    ln_rmssd = np.log(max(rmssd_ms, 1.0))  # avoid log(0)
    # ln(RMSSD) range: ~2.3 (rmssd=10) to ~4.4 (rmssd=80)
    hrv_protection = max(0.0, min(1.0, (ln_rmssd - 2.3) / (4.4 - 2.3)))

    if rsa_amplitude is not None:
        # 5-channel mode: weights informed by WESAD (Schmidt et al., 2018)
        rsa_norm = min(rsa_amplitude, 30.0) / 30.0  # higher RSA = more vagal tone = less stress
        score = (
            0.25 * hr_component
            + 0.25 * eda_component
            + 0.15 * phasic_component
            + 0.15 * (1.0 - hrv_protection)
            + 0.20 * (1.0 - rsa_norm)
        )
    else:
        # 4-channel fallback (no respiratory data available)
        score = (
            0.30 * hr_component
            + 0.30 * eda_component
            + 0.20 * phasic_component
            + 0.20 * (1.0 - hrv_protection)
        )
    return max(0.0, min(1.0, score))


# ---------------------------------------------------------------------------
# Stress composite v2 (Kubios-parity inputs) — 2026-04-21
# ---------------------------------------------------------------------------

STRESS_V2_LABEL = "experimental composite v2, Kubios-grade inputs (NOT validated)"


def compute_stress_score_v2(
    *,
    rmssd_ms: float,
    mean_hr_bpm: float,
    eda_mean_us: float,
    eda_phasic_index: float,
    pnn50: float | None = None,
    sd1_sd2_ratio: float | None = None,
    lf_nu: float | None = None,
    rsa_amplitude: float | None = None,
    baseline_hr_bpm: float | None = None,
    hf_nu: float | None = None,
    temp_slope: float | None = None,
) -> tuple[float, dict[str, float | None]]:
    """Second-generation stress composite using Kubios-parity inputs.

    Same 0-to-1 scale and same "exploratory, not validated" status as v1.
    Adds three Kubios-grade inputs that let the composite respond to
    information v1 missed:

      pNN50             — robust vagal-tone proxy; more stable than RMSSD
                          on short segments (Shaffer & Ginsberg 2017).
      SD1/SD2 ratio     — Poincaré-based autonomic-balance marker;
                          collapses under sympathetic stress even when
                          SD1 and SD2 individually look normal.
      LF_nu             — canonical normalised-units sympathovagal
                          marker (Task Force 1996) for between-subject
                          comparison.
      HF_nu             — high-frequency normalised units; purer vagal
                          index than LF_nu (Billman, 2013).
      temp_slope        — skin temperature slope; negative slope indicates
                          peripheral vasoconstriction (sympathetic).

    Missing-field handling: any of pnn50 / sd1_sd2_ratio / lf_nu /
    rsa_amplitude / hf_nu / temp_slope can be None; the weight of each
    absent field is proportionally redistributed across the present
    fields. This is important because LF_nu needs a ≥ 120 s session,
    SD1/SD2 ratio needs ≥ 4 beats, and RSA needs a PPG or respiratory
    channel.

    Parameters
    ----------
    All inputs keyword-only for clarity. Keep v1 callable by position
    via compute_stress_score for backward compatibility.

    Returns
    -------
    (score, component_contributions) : tuple[float, dict]
        `score` is the final v2 composite in [0, 1]. The second element
        is a per-channel contribution dict for auditability — what each
        active channel contributed and what the effective weight was,
        so a reader can see where the score came from.

    References
    ----------
    Shaffer, F., & Ginsberg, J. P. (2017). An overview of heart rate
    variability metrics and norms. Frontiers in Public Health, 5, 258.
    https://doi.org/10.3389/fpubh.2017.00258

    Thayer, J. F., Åhs, F., Fredrikson, M., Sollers, J. J., & Wager,
    T. D. (2012). A meta-analysis of heart rate variability and
    neuroimaging studies. Neuroscience & Biobehavioral Reviews, 36(2),
    747-756. https://doi.org/10.1016/j.neubiorev.2011.11.009

    Task Force of the European Society of Cardiology and the North
    American Society of Pacing and Electrophysiology. (1996). Heart
    rate variability. Circulation, 93(5), 1043-1065.
    """
    # Per-channel normalisations (all → [0, 1]) -----------------------
    if baseline_hr_bpm is not None and baseline_hr_bpm > 0:
        # Baseline-relative: deviation from individual baseline
        hr_n = max(0.0, min(1.0, (mean_hr_bpm - baseline_hr_bpm) / 30.0))
    else:
        # Population-level fallback
        hr_n = max(0.0, min(1.0, (mean_hr_bpm - 60.0) / 60.0))
    eda_n = max(0.0, min(1.0, eda_mean_us / 20.0))
    phasic_n = max(0.0, min(1.0, eda_phasic_index / 2.5))

    # Vagal composite: average of available vagal-tone proxies.
    # Log-transform RMSSD (distributions are log-normal; Shaffer & Ginsberg 2017)
    vagal_parts: list[float] = []
    ln_rmssd = np.log(max(rmssd_ms, 1.0))
    vagal_parts.append(max(0.0, min(1.0, (ln_rmssd - 2.3) / (4.4 - 2.3))))
    if pnn50 is not None:
        vagal_parts.append(min(pnn50, 50.0) / 50.0)
    if hf_nu is not None:
        # HF_nu is a purer vagal index than LF_nu (Billman, 2013)
        # Higher HF_nu = more vagal = less stress
        hf_vagal = max(0.0, min(1.0, hf_nu / 100.0))
        vagal_parts.append(hf_vagal)
    vagal_protection = sum(vagal_parts) / len(vagal_parts)

    # Sympathovagal balance: prefer LF_nu if available. LF_nu is already
    # in [0, 100], higher = more sympathetic dominance.
    sympathovagal = None
    if lf_nu is not None:
        sympathovagal = max(0.0, min(1.0, lf_nu / 100.0))

    # Autonomic rigidity from Poincaré: SD1/SD2 typically ≈ 0.5 in a
    # relaxed healthy adult. Below 0.3 suggests rigidity under stress.
    rigidity = None
    if sd1_sd2_ratio is not None:
        # Map 0.5 → 0.0 (normal balance, no rigidity score), 0.0 → 1.0
        rigidity = max(0.0, min(1.0, (0.5 - sd1_sd2_ratio) / 0.5))

    # Respiratory: higher RSA = more vagal tone = lower stress
    rsa_low = None
    if rsa_amplitude is not None:
        rsa_n = min(rsa_amplitude, 30.0) / 30.0
        rsa_low = 1.0 - rsa_n

    # Temperature: negative slope indicates vasoconstriction (sympathetic)
    temp_stress = None
    if temp_slope is not None:
        # Map: -0.01 °C/s → 1.0 (strong vasoconstriction), 0 → 0.5, +0.01 → 0.0
        temp_stress = max(0.0, min(1.0, 0.5 - temp_slope * 50.0))

    # Weights ---------------------------------------------------------
    # Intent:
    #   HR                0.13
    #   EDA (tonic)       0.18
    #   EDA (phasic)      0.09
    #   Vagal composite   0.14  (always present)
    #   Sympathovagal     0.18  (LF_nu; redistributes if absent)
    #   Rigidity          0.09  (SD1/SD2; redistributes if absent)
    #   Respiratory       0.09  (RSA; redistributes if absent)
    #   Temperature       0.10  (temp_slope; redistributes if absent)
    # Absent-channel weights redistribute proportionally across
    # present channels to preserve inter-channel ratios.
    base_weights = {
        "hr": 0.13,
        "eda": 0.18,
        "phasic": 0.09,
        "vagal": 0.14,
        "sympathovagal": 0.18,
        "rigidity": 0.09,
        "rsa": 0.09,
        "temp": 0.10,
    }
    active = {"hr": True, "eda": True, "phasic": True, "vagal": True,
              "sympathovagal": sympathovagal is not None,
              "rigidity": rigidity is not None,
              "rsa": rsa_low is not None,
              "temp": temp_stress is not None}
    missing_weight = sum(base_weights[k] for k, v in active.items() if not v)
    active_total = sum(base_weights[k] for k, v in active.items() if v)
    if active_total > 0 and missing_weight > 0:
        scale_factor = 1.0 / (1.0 - missing_weight)  # Scale to sum to 1.0
        effective_weights = {
            k: (base_weights[k] * scale_factor) if active[k] else 0.0
            for k in base_weights
        }
    else:
        effective_weights = {
            k: base_weights[k] if active[k] else 0.0
            for k in base_weights
        }

    # Assemble ------------------------------------------------------
    channel_values = {
        "hr": hr_n,
        "eda": eda_n,
        "phasic": phasic_n,
        "vagal": 1.0 - vagal_protection,   # stress rises as vagal tone falls
        "sympathovagal": sympathovagal or 0.0,
        "rigidity": rigidity or 0.0,
        "rsa": rsa_low or 0.0,
        "temp": temp_stress or 0.0,
    }
    score = sum(
        effective_weights[k] * channel_values[k] for k in base_weights if active[k]
    )
    score = max(0.0, min(1.0, score))

    # Audit trail ---------------------------------------------------
    contributions: dict[str, float | None] = {}
    for k in base_weights:
        if active[k]:
            contributions[k] = round(effective_weights[k] * channel_values[k], 4)
        else:
            contributions[k] = None
        contributions[f"{k}_weight"] = round(effective_weights[k], 4) if active[k] else None
        contributions[f"{k}_value"] = round(channel_values[k], 4) if active[k] else None
    n_active = sum(1 for v in active.values() if v)
    contributions["_active_channels"] = float(n_active)
    contributions["_vagal_protection"] = round(vagal_protection, 4)

    return score, contributions


def rescale_stress_v2_to_arousal_index(
    score_01: float | None,
    baseline_01: float | None,
) -> float | None:
    """Re-express the v2 stress composite as baseline-neutral arousal.

    The raw composite lives on [0, 1]. For the room-by-room analyses we
    treat the participant's own resting baseline as the neutral point and
    rescale deviations around it onto [-1, +1]:

        arousal = 2 * (score - baseline)

    A value of 0 therefore means "at baseline", positive values mean
    greater activation/arousal than baseline, and negative values mean
    lower activation than baseline. Values are clipped to [-1, +1].
    """
    if score_01 is None or baseline_01 is None:
        return None
    try:
        arousal = 2.0 * (float(score_01) - float(baseline_01))
    except (TypeError, ValueError):
        return None
    return max(-1.0, min(1.0, arousal))

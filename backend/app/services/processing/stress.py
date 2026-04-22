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

# Module-level flag for downstream consumers
STRESS_SCORE_VALIDATED = False
STRESS_SCORE_LABEL = "experimental composite (not psychometrically validated)"


def compute_stress_score(
    rmssd_ms: float,
    mean_hr_bpm: float,
    eda_mean_us: float,
    eda_phasic_index: float,
    rsa_amplitude: float | None = None,
) -> float:
    """Compute exploratory stress composite.

    Returns a value in [0.0, 1.0]. Higher = greater estimated sympathetic
    activation. NOT a validated stress measure — see module docstring.

    If rsa_amplitude is None (EDR could not be computed), falls back to
    4-channel mode with redistributed weights.
    """
    # Normalize each component to [0, 1]
    hr_component = max(0.0, min(1.0, (mean_hr_bpm - 60.0) / 60.0))
    eda_component = max(0.0, min(1.0, eda_mean_us / 20.0))
    phasic_component = max(0.0, min(1.0, eda_phasic_index / 2.5))
    hrv_protection = min(rmssd_ms, 80.0) / 80.0  # higher HRV = less stress

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

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

FORMULA (V2.0, unchanged):
    stress = 0.35 * HR_norm + 0.35 * EDA_norm + 0.20 * phasic_norm
             + 0.10 * (1 - HRV_protection)

    HR_norm:   (mean_hr - 60) / (120 - 60), clipped to [0, 1]
    EDA_norm:  mean_eda / 20.0, clipped to [0, 1]
    phasic_norm: phasic_index / 2.5, clipped to [0, 1]
    HRV_protection: min(rmssd, 80) / 80  (higher RMSSD = lower stress)

    Weights are arbitrary. Normalization ranges (60-120 BPM, 0-20 uS,
    0-2.5 phasic, 0-80 RMSSD) are approximate population ranges, not
    derived from published norms.
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
) -> float:
    """Compute exploratory stress composite.

    Returns a value in [0.0, 1.0]. Higher = greater estimated sympathetic
    activation. NOT a validated stress measure — see module docstring.
    """
    # Normalize each component to [0, 1]
    hr_component = max(0.0, min(1.0, (mean_hr_bpm - 60.0) / 60.0))
    eda_component = max(0.0, min(1.0, eda_mean_us / 20.0))
    phasic_component = max(0.0, min(1.0, eda_phasic_index / 2.5))
    hrv_protection = min(rmssd_ms, 80.0) / 80.0  # higher HRV = less stress

    # Weighted composite (weights are heuristic, not empirically derived)
    score = (
        0.35 * hr_component
        + 0.35 * eda_component
        + 0.20 * phasic_component
        + 0.10 * (1.0 - hrv_protection)
    )
    return max(0.0, min(1.0, score))

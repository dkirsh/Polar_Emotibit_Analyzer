"""End-to-end analysis pipeline for synchronized bio-signal data.

Version: 2.1 (repaired)
Changes from V2.0:
  - [Repair 1.3] XCorr disabled (was using wrong signals: HR vs EDA)
  - [Repair 1.4] Sync QC integrated into runtime pipeline with quality gate
  - [Repair 1.6] Stress formula labeled as experimental/unvalidated

Key features (from V2.0):
  - Piecewise linear drift correction
  - Native Polar RR interval passthrough for accurate HRV
  - Frequency-domain HRV (LF, HF, LF/HF ratio) via Welch (V2.1)
  - RR source metadata in all outputs
"""

from __future__ import annotations

import pandas as pd

from app.schemas.analysis import AnalysisResponse, FeatureSummary
from app.services.ai.adapters import NON_DIAGNOSTIC_NOTICE
from app.services.processing.clean import clean_signals


# Minimum-sample thresholds (F2 + F6 fix 2026-04-21).
# MIN_BEATS_FOR_HRV: Kubios user-guide recommendation for RMSSD stability;
#   Task Force 1996 guideline for short-term HRV time-domain analysis.
# MIN_SAMPLES_FOR_SYNC: 30 s at 1 Hz is the practical floor for any
#   cross-sensor synchronization claim.
MIN_BEATS_FOR_HRV = 50
MIN_SAMPLES_FOR_SYNC = 30


class InsufficientDataError(ValueError):
    """Raised when the input DataFrames are too small for meaningful analysis.

    The route handler translates this into an HTTP 422 with a structured
    detail body so clients can distinguish "endpoint failed" (500) from
    "input insufficient" (422).
    """

    def __init__(self, detail: str, *, n_polar: int, n_emotibit: int) -> None:
        super().__init__(detail)
        self.detail = detail
        self.n_polar = n_polar
        self.n_emotibit = n_emotibit
from app.services.processing.drift import (
    apply_piecewise_drift,
    estimate_piecewise_drift,
)
from app.services.processing.features import (
    compute_eda_features,
    compute_hrv_features,
    compute_hrv_frequency_features,
    compute_poincare_features,
    compute_time_domain_features,
)
from app.services.processing.stress import (
    STRESS_SCORE_LABEL,
    compute_stress_score,
    compute_stress_score_v2,
)
from app.services.processing.sync import synchronize_signals
from app.services.processing.sync_qc import compute_sync_qc
from app.services.reporting.report_builder import build_markdown_report


def run_analysis(emotibit_df: pd.DataFrame, polar_df: pd.DataFrame) -> AnalysisResponse:
    """Run full processing pipeline from raw dataframes to API response."""

    # -- Step 0: Minimum-sample guard (F2 + F6 fix 2026-04-21) ---------------
    # Reject inputs too small for meaningful analysis. Empty or tiny inputs
    # previously produced HTTP 200 with default feature values including
    # stress_score 0.5 — an affirmative wrong answer. Now they produce 422
    # with a structured reason.
    n_polar = int(len(polar_df))
    n_emotibit = int(len(emotibit_df))
    if n_polar < MIN_BEATS_FOR_HRV:
        raise InsufficientDataError(
            f"Polar file has {n_polar} beats; HRV analysis requires "
            f"at least {MIN_BEATS_FOR_HRV} beats for RMSSD stability "
            f"(Kubios user-guide convention; Task Force 1996 guideline).",
            n_polar=n_polar, n_emotibit=n_emotibit,
        )
    if n_emotibit < MIN_SAMPLES_FOR_SYNC:
        raise InsufficientDataError(
            f"EmotiBit file has {n_emotibit} samples; cross-sensor "
            f"synchronization requires at least {MIN_SAMPLES_FOR_SYNC} "
            f"samples (~30 s at 1 Hz).",
            n_polar=n_polar, n_emotibit=n_emotibit,
        )

    # -- Step 1: Piecewise drift correction -----------------------------------
    drift_model = estimate_piecewise_drift(
        source_ts=polar_df["timestamp_ms"].astype(int).tolist(),
        reference_ts=emotibit_df["timestamp_ms"].astype(int).tolist(),
        anchor_interval_ms=60_000,
    )

    corrected_polar = polar_df.copy()
    corrected_polar["timestamp_ms"] = apply_piecewise_drift(
        corrected_polar["timestamp_ms"].astype(int).tolist(),
        drift_model,
    )

    # -- Step 2: Synchronize signals ------------------------------------------
    synced = synchronize_signals(emotibit_df, corrected_polar)

    # -- Step 2b: Sync quality gate (V2.1 NEW [Repair 1.4]) ------------------
    # V2.0 had run_sync_qc.py as a standalone script that was never called.
    # The pipeline ran unconditionally. Now we check sync quality and add
    # quality flags / gate if sync is poor.
    sync_qc_report = compute_sync_qc(
        emotibit_df=emotibit_df,
        polar_df=corrected_polar,
        synced_df=synced,
        drift_model=drift_model,
    )

    quality_flags: list[str] = []

    if sync_qc_report.sync_confidence_gate == "no_go":
        quality_flags.append(
            f"SYNC QUALITY GATE: NO GO (score={sync_qc_report.sync_confidence_score:.0f}/100). "
            f"Reasons: {'; '.join(sync_qc_report.failure_reasons)}"
        )
    elif sync_qc_report.sync_confidence_gate == "conditional_go":
        quality_flags.append(
            f"SYNC QUALITY: CONDITIONAL (score={sync_qc_report.sync_confidence_score:.0f}/100). "
            f"Fixes: {'; '.join(sync_qc_report.recommended_fixes)}"
        )
    else:
        quality_flags.append(
            f"Sync quality: GOOD (score={sync_qc_report.sync_confidence_score:.0f}/100)"
        )

    # -- Step 3: Cross-correlation offset (V2.1 DISABLED [Repair 1.3]) -------
    # DISABLED: V2.0 cross-correlated Polar HR with EmotiBit EDA to estimate
    # clock offset. This is scientifically wrong. HR and EDA are different
    # physiological signals with different temporal dynamics. Their cross-
    # correlation measures sympathetic coupling latency (1-5 seconds), NOT
    # clock offset (Boucsein, 2012; Berntson et al., 1997).
    #
    # To estimate clock offset via xcorr, you need the SAME signal from BOTH
    # devices (e.g., Polar ECG-HR vs EmotiBit PPG-HR). Until EmotiBit PPG-
    # derived HR is available as a separate column, xcorr is disabled.
    #
    # Skeptic's FAQ: "Can't HR-EDA xcorr still be useful?"
    # Answer: Yes — as a measure of AUTONOMIC COUPLING, not clock offset.
    # But the variable name is xcorr_offset_ms and it's in the sync
    # diagnostics panel. Repurposing a sync metric as a physiology metric
    # without renaming would be misleading. If coupling analysis is desired,
    # add it as a separate feature with its own name and interpretation.
    xcorr_offset_ms = 0.0

    # -- Step 4: Clean signals ------------------------------------------------
    cleaned, movement_artifact_ratio = clean_signals(synced)

    # -- Step 5: Extract features ---------------------------------------------
    #
    # [F12 fix 2026-04-21]: HRV features read from the drift-corrected raw
    # Polar DataFrame, NOT from the merged `cleaned` DataFrame. The
    # merge_asof sync with 1000 ms tolerance silently decimates beat-level
    # RR intervals (60–80 Hz native) to 1 Hz (EmotiBit-aligned), losing
    # ~21 % of beats at 74 bpm and biasing RMSSD by ~30 %. Real-data proof
    # on Welltory subject_05: pre-fix RMSSD 45.79 ms vs ground-truth
    # 35.28 ms (29.8 % error). EDA features stay on the synced DataFrame
    # because they need cross-sensor time alignment.
    #
    # Tradeoff: HRV now skips movement-artifact filtering (which is
    # applied in clean_signals via EmotiBit accel). An artifact-aware
    # HRV filter that drops RR beats falling inside accel-flagged
    # movement epochs is a future enhancement. The current state is
    # a strict improvement over the decimation bug.
    rmssd_ms, sdnn_ms, mean_hr_bpm, rr_source = compute_hrv_features(corrected_polar)
    # 2026-04-21 Kubios-parity: extended time-domain and Poincaré descriptors.
    time_domain_ext = compute_time_domain_features(corrected_polar)
    poincare = compute_poincare_features(corrected_polar)
    freq_features = compute_hrv_frequency_features(corrected_polar)
    eda_mean_us, eda_phasic_index = compute_eda_features(cleaned)
    stress_score = compute_stress_score(rmssd_ms, mean_hr_bpm, eda_mean_us, eda_phasic_index)

    # v2 composite with Kubios-grade inputs (pNN50, SD1/SD2 ratio, LF_nu).
    # Published evidence that each adds information over v1's RMSSD-only
    # vagal channel: Shaffer & Ginsberg (2017) on pNN50 stability on
    # short segments; Thayer et al. (2012) on Poincaré descriptors under
    # sympathetic stress; Task Force (1996) on LF_nu for between-subject
    # comparison. Emitted alongside v1; both carry the experimental /
    # not-validated caveat.
    stress_v2, stress_v2_contrib = compute_stress_score_v2(
        rmssd_ms=rmssd_ms,
        mean_hr_bpm=mean_hr_bpm,
        eda_mean_us=eda_mean_us,
        eda_phasic_index=eda_phasic_index,
        pnn50=time_domain_ext.get("pnn50"),
        sd1_sd2_ratio=poincare.get("sd1_sd2_ratio"),
        lf_nu=freq_features.get("lf_nu"),
        rsa_amplitude=None,  # wire when RSA is available
    )

    # -- Step 6: Quality flags ------------------------------------------------
    if len(cleaned) < 60:
        quality_flags.append("Low synchronized sample count (< 60 samples)")
    if len(corrected_polar) < 50:
        quality_flags.append("Low beat count for HRV (< 50 beats; RMSSD stability uncertain)")
    if rmssd_ms <= 1.0:
        quality_flags.append("RMSSD unusually low")
    if movement_artifact_ratio > 0.2:
        quality_flags.append("High motion artifact ratio (>20% of synchronized samples)")

    if rr_source == "derived_from_bpm":
        quality_flags.append(
            "HRV computed from BPM-derived RR intervals (reduced accuracy). "
            "Provide native Polar RR intervals (rr_ms column) for research-grade HRV."
        )
    else:
        quality_flags.append("HRV computed from native Polar H10 RR intervals (research-grade)")

    if drift_model.n_segments > 1:
        quality_flags.append(
            f"Piecewise drift correction applied ({drift_model.n_segments} segments)"
        )

    # V2.1 FIX [Repair 1.6]: stress formula caveat
    quality_flags.append(f"Stress score is {STRESS_SCORE_LABEL}. Use for within-session relative comparison only.")
    # 2026-04-21: v2 composite note — says what was added and that it's
    # likewise unvalidated.
    v2_active = int(stress_v2_contrib.get("_active_channels", 0) or 0)
    quality_flags.append(
        f"Stress v2 composite = {stress_v2:.3f} using {v2_active} active channels "
        f"(Kubios-grade inputs pNN50, SD1/SD2, LF_nu, RSA where available). "
        f"Still experimental; use alongside v1 for triangulation, not as a validated instrument."
    )

    # -- Step 7: Build response -----------------------------------------------
    primary_drift = drift_model.segments[0] if drift_model.segments else None

    feature_summary = FeatureSummary(
        rmssd_ms=rmssd_ms,
        sdnn_ms=sdnn_ms,
        mean_hr_bpm=mean_hr_bpm,
        eda_mean_us=eda_mean_us,
        eda_phasic_index=eda_phasic_index,
        stress_score=stress_score,
        rr_source=rr_source,
        vlf_ms2=freq_features.get("vlf_ms2"),
        lf_ms2=freq_features.get("lf_ms2"),
        hf_ms2=freq_features.get("hf_ms2"),
        lf_hf_ratio=freq_features.get("lf_hf_ratio"),
        # 2026-04-21 Kubios-parity fields
        nn50=time_domain_ext.get("nn50"),
        pnn50=time_domain_ext.get("pnn50"),
        sd1_ms=poincare.get("sd1_ms"),
        sd2_ms=poincare.get("sd2_ms"),
        sd1_sd2_ratio=poincare.get("sd1_sd2_ratio"),
        ellipse_area_ms2=poincare.get("ellipse_area_ms2"),
        total_power_ms2=freq_features.get("total_power_ms2"),
        lf_nu=freq_features.get("lf_nu"),
        hf_nu=freq_features.get("hf_nu"),
        vlf_pct=freq_features.get("vlf_pct"),
        lf_pct=freq_features.get("lf_pct"),
        hf_pct=freq_features.get("hf_pct"),
        stress_score_v2=stress_v2,
        stress_v2_contributions=stress_v2_contrib,
    )
    report_markdown = build_markdown_report(feature_summary, quality_flags)

    return AnalysisResponse(
        synchronized_samples=int(len(cleaned)),
        drift_slope=primary_drift.slope if primary_drift else 1.0,
        drift_intercept_ms=primary_drift.intercept_ms if primary_drift else 0.0,
        drift_segments=drift_model.n_segments,
        xcorr_offset_ms=xcorr_offset_ms,
        feature_summary=feature_summary,
        quality_flags=quality_flags,
        movement_artifact_ratio=movement_artifact_ratio,
        report_markdown=report_markdown,
        non_diagnostic_notice=NON_DIAGNOSTIC_NOTICE,
        sync_qc_score=sync_qc_report.sync_confidence_score,
        sync_qc_band=sync_qc_report.sync_confidence_band,
        sync_qc_gate=sync_qc_report.sync_confidence_gate,
        sync_qc_failure_reasons=sync_qc_report.failure_reasons,
    )

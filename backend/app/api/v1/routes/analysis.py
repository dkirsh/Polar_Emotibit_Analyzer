"""Analysis endpoint — the primary workload.

Accepts a pre-synched pair of Polar H10 + EmotiBit CSVs (plus optional
markers and metadata) and returns the V2.1 pipeline's structured response.
Session metadata is persisted to an in-process session store so the
frontend's "Recent sessions" table and view 2 re-read both work without
a full database layer in the first cut.
"""
from __future__ import annotations

import io
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import pandas as pd
from fastapi import APIRouter, Form, HTTPException, Response, UploadFile, status

from app.services.ai.adapters import NON_DIAGNOSTIC_NOTICE
from app.schemas.analysis import (
    AnalysisResponse,
    BlandAltmanMetric,
    FeatureSummary,
    SessionDetail,
    SessionSummary,
)
from app.services.ingestion.parsers import parse_emotibit_csv, parse_polar_csv
from app.services.processing.benchmark import bland_altman
from app.services.processing.clean import clean_signals
from app.services.processing.drift import apply_piecewise_drift, estimate_piecewise_drift
from app.services.processing.extended_analytics import (
    compute_full_psd,
    compute_spectral_trajectory,
    compute_windowed_features,
    decompose_stress,
)
from app.services.processing.features import (
    _get_rr_intervals,
    compute_edr,
    compute_edr_detailed,
    compute_edr_detailed_from_rr_ms,
    rr_source_confidence_for,
    rr_source_note_for,
)
from app.services.processing.features import (
    compute_eda_features,
    compute_hrv_features,
    compute_hrv_frequency_features,
    compute_poincare_features,
    compute_time_domain_features,
)
from app.services.processing.kubios_benchmark import compare_with_kubios
from app.services.processing.pipeline import InsufficientDataError, run_analysis
from app.services.processing.stress import rescale_stress_v2_to_arousal_index
from app.services.processing.statistics import compute_inference_summary, compute_summary_stats
from app.services.processing.sync import synchronize_signals
from app.services.reporting.report_builder import build_markdown_report


router = APIRouter(tags=["analysis"])
log = logging.getLogger(__name__)


# ----- In-process session store ------------------------------------------
# A researcher running this locally does not need a full PostgreSQL layer
# for the first cut; an in-memory dict plus a JSON snapshot on disk is
# enough to make the "Recent sessions" table work across a browser refresh.
# The snapshot file lives beside the backend's working directory.

_SESSION_STORE: dict[str, dict[str, Any]] = {}
_STORE_PATH = Path(__file__).resolve().parents[4] / "data" / "session_store.json"


def _load_store_from_disk() -> None:
    if _STORE_PATH.exists():
        try:
            _SESSION_STORE.update(json.loads(_STORE_PATH.read_text()))
        except Exception:  # noqa: BLE001
            pass


def _persist_store() -> None:
    try:
        _STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _STORE_PATH.write_text(json.dumps(_SESSION_STORE, indent=2, default=str))
    except OSError as exc:
        # The in-memory store is already updated before this function is
        # called, so a local filesystem permission failure should not turn
        # a successful analysis into a failed upload. The session will be
        # available until the backend process exits.
        log.warning("Could not persist session store to %s: %s", _STORE_PATH, exc)


def _migrate_stored_sessions() -> bool:
    """Upgrade older stored sessions to the current frontend contract."""
    changed = False
    for record in _SESSION_STORE.values():
        if _maybe_backfill_edr_proxy(record):
            changed = True
    return changed


def _maybe_backfill_edr_proxy(record: dict[str, Any]) -> bool:
    extended = record.get("extended")
    if not isinstance(extended, dict):
        return False
    rr_source = (
        ((extended.get("psd") or {}).get("rr_source"))
        or ((record.get("result") or {}).get("feature_summary") or {}).get("rr_source")
        or "none"
    )
    rr_source_note = (
        ((record.get("result") or {}).get("feature_summary") or {}).get("rr_source_note")
        or rr_source_note_for(rr_source)
    )

    feature_summary = ((record.get("result") or {}).get("feature_summary") or {})
    changed = False
    if isinstance(feature_summary, dict) and not feature_summary.get("rr_source_note"):
        feature_summary["rr_source_note"] = rr_source_note
        changed = True

    edr_proxy = extended.get("edr_proxy")
    if not isinstance(edr_proxy, dict):
        rr_series = extended.get("rr_series_ms")
        if not isinstance(rr_series, list) or len(rr_series) < 30:
            return changed
        edr_proxy = compute_edr_detailed_from_rr_ms(rr_series)
        if not edr_proxy.get("time_s"):
            return changed
        extended["edr_proxy"] = edr_proxy
        changed = True

    if edr_proxy.get("rr_source") != rr_source:
        edr_proxy["rr_source"] = rr_source
        changed = True
    if edr_proxy.get("rr_source_note") != rr_source_note:
        edr_proxy["rr_source_note"] = rr_source_note
        changed = True
    quality = edr_proxy.get("quality")
    if not isinstance(quality, dict):
        quality = {}
        edr_proxy["quality"] = quality
        changed = True
    signal_confidence = quality.get("signal_confidence")
    source_confidence = rr_source_confidence_for(rr_source)
    overall_confidence = (
        round(float((float(signal_confidence) + source_confidence) / 2.0), 3)
        if isinstance(signal_confidence, (int, float))
        else round(float(source_confidence), 3)
    )
    rounded_source_confidence = round(float(source_confidence), 3)
    if quality.get("source_confidence") != rounded_source_confidence:
        quality["source_confidence"] = rounded_source_confidence
        changed = True
    if quality.get("overall_confidence") != overall_confidence:
        quality["overall_confidence"] = overall_confidence
        changed = True
    if overall_confidence >= 0.8:
        verdict = "strong"
    elif overall_confidence >= 0.6:
        verdict = "usable"
    elif overall_confidence >= 0.4:
        verdict = "weak"
    else:
        verdict = "insufficient"
    if quality.get("verdict") != verdict:
        quality["verdict"] = verdict
        changed = True
    return changed


_load_store_from_disk()


# ----- Analysis ----------------------------------------------------------


@router.post("/analyze", response_model=AnalysisResponse)
async def analyze(
    emotibit_file: UploadFile,
    polar_file: UploadFile,
    markers_file: Optional[UploadFile] = None,
    session_id: str = Form(...),
    subject_id: str = Form(...),
    study_id: str = Form(...),
    session_date: str = Form(...),
    operator: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
) -> AnalysisResponse:
    """Run the V2.1 pipeline on a pre-synched pair of CSVs.

    All metadata fields are stored alongside the analysis for later recall
    by the "Recent sessions" list in view 1 and the session-identity bar
    in view 2.
    """
    try:
        em_text = (await emotibit_file.read()).decode("utf-8", errors="replace")
        pol_text = (await polar_file.read()).decode("utf-8", errors="replace")
        em_df = parse_emotibit_csv(em_text)
        pol_df = parse_polar_csv(pol_text)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"CSV schema validation failed: {exc}",
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Parse error: {exc.__class__.__name__}: {exc}",
        )

    # Phase 1 of the GUI leaves phase-window analysis to a follow-up commit;
    # the markers file is parsed and stored so the response can cite it but
    # the pipeline here runs whole-session.
    markers_summary: Optional[dict[str, Any]] = None
    if markers_file is not None:
        try:
            mk_text = (await markers_file.read()).decode("utf-8", errors="replace")
            mk_df = pd.read_csv(io.StringIO(mk_text))
            event_markers: list[dict[str, Any]] = []
            if {"event_code", "utc_ms"}.issubset(set(mk_df.columns)):
                for row in mk_df.to_dict(orient="records"):
                    try:
                        event_markers.append(
                            {
                                "event_code": str(row.get("event_code", "")),
                                "utc_ms": int(row.get("utc_ms")),
                                "note": str(row.get("note", "")) if "note" in row and pd.notna(row.get("note")) else "",
                            }
                        )
                    except Exception:
                        continue
            markers_summary = {
                "n_rows": int(len(mk_df)),
                "codes": sorted(set(mk_df.get("event_code", pd.Series()).astype(str).tolist())),
                "event_markers": event_markers,
            }
        except Exception:  # noqa: BLE001
            markers_summary = {"error": "markers file could not be parsed; ignored"}

    try:
        result = run_analysis(em_df, pol_df)
        result.feature_summary.rr_source_note = str(
            pol_df.attrs.get("rr_source_note", rr_source_note_for(result.feature_summary.rr_source))
        )
    except InsufficientDataError as exc:
        # F2 + F6 fix 2026-04-21: insufficient input is a client-data
        # problem, not a pipeline failure. Return 422 with a structured
        # detail so the frontend can distinguish from a true 500.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "reason": "insufficient_data",
                "message": exc.detail,
                "n_polar": exc.n_polar,
                "n_emotibit": exc.n_emotibit,
            },
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Pipeline error: {exc.__class__.__name__}: {exc}",
        )

    # ------ Extended analytics bundle -----------------------------------
    # Re-derive the cleaned dataframe so the frontend can render windowed,
    # spectral, and decomposition views without a second round-trip.
    try:
        drift_model = estimate_piecewise_drift(
            source_ts=pol_df["timestamp_ms"].astype(int).tolist(),
            reference_ts=em_df["timestamp_ms"].astype(int).tolist(),
        )
        corrected = pol_df.copy()
        corrected["timestamp_ms"] = apply_piecewise_drift(
            corrected["timestamp_ms"].astype(int).tolist(), drift_model,
        )
        synced = synchronize_signals(em_df, corrected)
        cleaned, _mar = clean_signals(synced)

        # Compute session-level EDR for the decomposition
        session_edr = compute_edr(cleaned)
        session_edr_detailed = compute_edr_detailed(cleaned)
        session_rsa = session_edr["rsa_amplitude"]
        has_rsa = session_rsa is not None

        fs = result.feature_summary
        decomp = decompose_stress(
            fs.rmssd_ms, fs.mean_hr_bpm, fs.eda_mean_us, fs.eda_phasic_index,
            rsa_amplitude=session_rsa,
        )
        wf = compute_windowed_features(cleaned, window_s=60.0, step_s=30.0)
        arousal_baseline = _baseline_window_stress_v2(markers_summary, cleaned, wf.window_centers_s, wf.stress_v2)
        wf.arousal_index = [
            rescale_stress_v2_to_arousal_index(score, arousal_baseline)
            for score in wf.stress_v2
        ]
        st = compute_spectral_trajectory(cleaned, window_s=120.0, step_s=60.0)
        psd = compute_full_psd(cleaned)
        rr_arr, rr_source = _get_rr_intervals(cleaned)
        rr_source_note = str(pol_df.attrs.get("rr_source_note", rr_source_note_for(rr_source)))
        summ = compute_summary_stats(cleaned)
        inf = compute_inference_summary(cleaned) if len(cleaned) >= 10 else None
        edr_quality = session_edr_detailed.get("quality")
        if not isinstance(edr_quality, dict):
            edr_quality = {}
        signal_confidence = edr_quality.get("signal_confidence")
        source_confidence = rr_source_confidence_for(rr_source)
        overall_confidence = (
            round(float((float(signal_confidence) + source_confidence) / 2.0), 3)
            if isinstance(signal_confidence, (int, float))
            else round(float(source_confidence), 3)
        )
        edr_quality["source_confidence"] = round(float(source_confidence), 3)
        edr_quality["overall_confidence"] = overall_confidence
        if overall_confidence >= 0.8:
            edr_quality["verdict"] = "strong"
        elif overall_confidence >= 0.6:
            edr_quality["verdict"] = "usable"
        elif overall_confidence >= 0.4:
            edr_quality["verdict"] = "weak"
        else:
            edr_quality["verdict"] = "insufficient"

        # Prefer the richer v2 decomposition when the session summary
        # includes it; fall back to the older v1 decomposition only for
        # legacy payloads.
        stress_components = _stress_v2_components(fs.stress_v2_contributions)
        stress_total = fs.stress_score_v2 if fs.stress_score_v2 is not None else decomp.total_score
        stress_driver = (
            max(stress_components, key=lambda c: c["contribution"])["name"]
            if stress_components
            else decomp.dominant_driver
        )
        if not stress_components:
            stress_components = [
                {"name": "HR", "component": decomp.hr_component, "contribution": decomp.hr_contribution, "weight": 0.25 if has_rsa else 0.30},
                {"name": "EDA_tonic", "component": decomp.eda_component, "contribution": decomp.eda_contribution, "weight": 0.25 if has_rsa else 0.30},
                {"name": "EDA_phasic", "component": decomp.phasic_component, "contribution": decomp.phasic_contribution, "weight": 0.15 if has_rsa else 0.20},
                {"name": "HRV_deficit", "component": 1.0 - decomp.hrv_protection, "contribution": decomp.hrv_contribution, "weight": 0.15 if has_rsa else 0.20},
            ]
            if has_rsa:
                stress_components.append(
                    {"name": "RSA_deficit", "component": 1.0 - decomp.rsa_component, "contribution": decomp.rsa_contribution, "weight": 0.20}
                )
        extended = {
            "stress_decomposition": {
                "total": stress_total,
                "dominant_driver": stress_driver,
                "components": stress_components,
            },
            "windowed": {
                "t_s": wf.window_centers_s,
                "hr_mean": wf.hr_mean,
                "hr_std": wf.hr_std,
                "eda_mean": wf.eda_mean,
                "rmssd": wf.rmssd,
                "stress": wf.stress,
                "stress_v2": wf.stress_v2,
                "arousal_index": wf.arousal_index,
                "arousal_baseline": arousal_baseline,
                "hr_contribution": wf.hr_contribution,
                "eda_contribution": wf.eda_contribution,
                "hrv_contribution": wf.hrv_contribution,
                "mean_rpm": wf.mean_rpm,
                "rsa_amplitude": wf.rsa_amplitude,
                "rsa_contribution": wf.rsa_contribution,
                "v2_hr_contribution": wf.v2_hr_contribution,
                "v2_eda_contribution": wf.v2_eda_contribution,
                "v2_phasic_contribution": wf.v2_phasic_contribution,
                "v2_vagal_contribution": wf.v2_vagal_contribution,
                "v2_sympathovagal_contribution": wf.v2_sympathovagal_contribution,
                "v2_rigidity_contribution": wf.v2_rigidity_contribution,
                "v2_rsa_contribution": wf.v2_rsa_contribution,
            },
            "spectral_trajectory": {
                "t_s": st.window_centers_s,
                "lf_power": st.lf_power,
                "hf_power": st.hf_power,
                "lf_hf_ratio": st.lf_hf_ratio,
            },
            "edr_proxy": {
                "source": session_edr_detailed.get("source"),
                "rr_source": rr_source,
                "rr_source_note": rr_source_note,
                "time_s": session_edr_detailed.get("time_s", []),
                "signal": session_edr_detailed.get("signal", []),
                "peak_times_s": session_edr_detailed.get("peak_times_s", []),
                "trough_times_s": session_edr_detailed.get("trough_times_s", []),
                "breath_intervals_s": session_edr_detailed.get("breath_intervals_s", []),
                "inspiratory_times_s": session_edr_detailed.get("inspiratory_times_s", []),
                "expiratory_times_s": session_edr_detailed.get("expiratory_times_s", []),
                "mean_rpm": session_edr_detailed.get("mean_rpm"),
                "rpm_std": session_edr_detailed.get("rpm_std"),
                "rsa_amplitude": session_edr_detailed.get("rsa_amplitude"),
                "quality": edr_quality,
            },
            "psd": {
                "frequencies_hz": psd.get("frequencies_hz", []),
                "psd_ms2_hz": psd.get("psd_ms2_hz", []),
                "rr_source": psd.get("rr_source", rr_source),
                "bands": psd.get("bands", {}),
            },
            "rr_series_ms": rr_arr.tolist() if hasattr(rr_arr, "tolist") else list(rr_arr),
            "descriptive_stats": {
                "hr_bpm": {
                    "mean": summ["hr_bpm"].mean, "std": summ["hr_bpm"].std,
                    "min": summ["hr_bpm"].min_val, "max": summ["hr_bpm"].max_val,
                    "p05": summ["hr_bpm"].p05, "p95": summ["hr_bpm"].p95,
                },
                "eda_us": {
                    "mean": summ["eda_us"].mean, "std": summ["eda_us"].std,
                    "min": summ["eda_us"].min_val, "max": summ["eda_us"].max_val,
                    "p05": summ["eda_us"].p05, "p95": summ["eda_us"].p95,
                },
            },
            "inference": inf,
            # Subsampled cleaned timeseries for overlay charting (≤ 1000 pts).
            "cleaned_timeseries": _subsample_timeseries(cleaned, max_points=1000),
            "motion_artifact_ratio": _mar,
        }
    except Exception:  # noqa: BLE001
        extended = None

    # Persist in the in-process store keyed by session_id (latest-wins).
    analysis_id = str(uuid.uuid4())
    stored = {
        "analysis_id": analysis_id,
        "session_id": session_id,
        "subject_id": subject_id,
        "study_id": study_id,
        "session_date": session_date,
        "operator": operator,
        "notes": notes,
        "analyzed_at": datetime.now(tz=timezone.utc).isoformat(),
        "markers_summary": markers_summary,
        "result": result.model_dump() if hasattr(result, "model_dump") else result.dict(),
        "extended": extended,
    }
    _SESSION_STORE[session_id] = stored
    _persist_store()

    return result


def _baseline_window_stress_v2(
    markers_summary: Optional[dict[str, Any]],
    cleaned: pd.DataFrame,
    centers_s: list[float],
    stress_v2: list[float],
) -> float | None:
    """Find the participant's neutral baseline from the baseline interval."""
    if len(centers_s) != len(stress_v2) or len(stress_v2) == 0:
        return None
    origin = None
    if "timestamp_ms" in cleaned.columns and len(cleaned) > 0:
        origin = float(cleaned["timestamp_ms"].iloc[0])

    if markers_summary and origin is not None:
        events = markers_summary.get("event_markers") or []
        onset = next((e for e in events if e.get("event_code") == "baseline_onset"), None)
        offset = next((e for e in events if e.get("event_code") == "baseline_offset"), None)
        if onset and offset:
            try:
                start_s = (float(onset["utc_ms"]) - origin) / 1000.0
                end_s = (float(offset["utc_ms"]) - origin) / 1000.0
                ys = [
                    score
                    for t, score in zip(centers_s, stress_v2, strict=False)
                    if start_s <= t <= end_s and score is not None
                ]
                if ys:
                    return float(sum(ys) / len(ys))
            except (KeyError, TypeError, ValueError):
                pass

    fallback = [score for score in stress_v2[:3] if score is not None]
    if not fallback:
        return None
    return float(sum(fallback) / len(fallback))


def _stress_v2_components(
    contributions: dict[str, float | None] | None,
) -> list[dict[str, float | str]]:
    if not contributions:
        return []
    rows: list[dict[str, float | str]] = []
    specs = [
        ("hr", "HR"),
        ("eda", "EDA tonic"),
        ("phasic", "EDA phasic"),
        ("vagal", "Vagal deficit"),
        ("sympathovagal", "LF_nu balance"),
        ("rigidity", "SD1/SD2 rigidity"),
        ("rsa", "RSA deficit"),
    ]
    for key, label in specs:
        contribution = contributions.get(key)
        if contribution is None:
            continue
        rows.append(
            {
                "name": label,
                "component": float(contributions.get(f"{key}_value") or 0.0),
                "contribution": float(contribution),
                "weight": float(contributions.get(f"{key}_weight") or 0.0),
            }
        )
    return rows


@router.post("/analyze/single", response_model=AnalysisResponse)
async def analyze_single(
    file: UploadFile,
    source_type: str = Form(...),
    session_id: str = Form(...),
    subject_id: str = Form(...),
    study_id: str = Form(...),
    session_date: str = Form(...),
    operator: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
) -> AnalysisResponse:
    """Run a one-sensor analysis for presentation and data inspection.

    `source_type` is `polar` or `emotibit`. This endpoint deliberately
    avoids cross-sensor synchronization and emits quality flags naming the
    limits of a single-sensor interpretation.
    """
    mode = source_type.strip().lower()
    if mode not in {"polar", "emotibit"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="source_type must be 'polar' or 'emotibit'",
        )

    try:
        csv_text = (await file.read()).decode("utf-8", errors="replace")
        if mode == "polar":
            df = parse_polar_csv(csv_text)
            result, extended = _build_polar_only_result(df)
        else:
            df = parse_emotibit_csv(csv_text)
            result, extended = _build_emotibit_only_result(df)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"CSV schema validation failed: {exc}",
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Single-file analysis error: {exc.__class__.__name__}: {exc}",
        )

    analysis_id = str(uuid.uuid4())
    stored = {
        "analysis_id": analysis_id,
        "session_id": session_id,
        "subject_id": subject_id,
        "study_id": study_id,
        "session_date": session_date,
        "operator": operator,
        "notes": notes,
        "analyzed_at": datetime.now(tz=timezone.utc).isoformat(),
        "markers_summary": None,
        "analysis_mode": f"{mode}_only",
        "result": result.model_dump() if hasattr(result, "model_dump") else result.dict(),
        "extended": extended,
    }
    _SESSION_STORE[session_id] = stored
    _persist_store()
    return result


def _build_polar_only_result(df: pd.DataFrame) -> tuple[AnalysisResponse, dict[str, Any]]:
    rmssd_ms, sdnn_ms, mean_hr_bpm, rr_source = compute_hrv_features(df)
    time_domain = compute_time_domain_features(df)
    poincare = compute_poincare_features(df)
    freq = compute_hrv_frequency_features(df)
    rr_arr, rr_series_source = _get_rr_intervals(df)
    quality_flags = [
        "Polar-only analysis: HR and HRV charts are available; EDA, motion, stress, and synchronization charts require an EmotiBit file.",
        f"RR source: {rr_source.replace('_', ' ')}",
    ]
    if len(df) < 50:
        quality_flags.append("Low beat count for HRV (< 50 beats; RMSSD stability uncertain)")
    feature_summary = FeatureSummary(
        rmssd_ms=rmssd_ms,
        sdnn_ms=sdnn_ms,
        mean_hr_bpm=mean_hr_bpm,
        eda_mean_us=0.0,
        eda_phasic_index=0.0,
        stress_score=0.0,
        rr_source=rr_source,
        rr_source_note=rr_source_note_for(rr_source),
        vlf_ms2=freq.get("vlf_ms2"),
        lf_ms2=freq.get("lf_ms2"),
        hf_ms2=freq.get("hf_ms2"),
        lf_hf_ratio=freq.get("lf_hf_ratio"),
        nn50=time_domain.get("nn50"),
        pnn50=time_domain.get("pnn50"),
        sd1_ms=poincare.get("sd1_ms"),
        sd2_ms=poincare.get("sd2_ms"),
        sd1_sd2_ratio=poincare.get("sd1_sd2_ratio"),
        ellipse_area_ms2=poincare.get("ellipse_area_ms2"),
        total_power_ms2=freq.get("total_power_ms2"),
        lf_nu=freq.get("lf_nu"),
        hf_nu=freq.get("hf_nu"),
        vlf_pct=freq.get("vlf_pct"),
        lf_pct=freq.get("lf_pct"),
        hf_pct=freq.get("hf_pct"),
        stress_score_v2=None,
        stress_v2_contributions=None,
    )
    result = AnalysisResponse(
        synchronized_samples=0,
        drift_slope=1.0,
        drift_intercept_ms=0.0,
        drift_segments=0,
        xcorr_offset_ms=0.0,
        feature_summary=feature_summary,
        quality_flags=quality_flags,
        movement_artifact_ratio=0.0,
        report_markdown=build_markdown_report(feature_summary, quality_flags),
        non_diagnostic_notice=NON_DIAGNOSTIC_NOTICE,
        sync_qc_score=0.0,
        sync_qc_band="unknown",
        sync_qc_gate="single_file",
        sync_qc_failure_reasons=["Synchronization not run in Polar-only mode."],
    )
    extended = {
        "analysis_mode": "polar_only",
        "psd": {
            "frequencies_hz": compute_full_psd(df).get("frequencies_hz", []),
            "psd_ms2_hz": compute_full_psd(df).get("psd_ms2_hz", []),
            "rr_source": rr_series_source,
            "bands": compute_full_psd(df).get("bands", {}),
        },
        "rr_series_ms": rr_arr.tolist() if hasattr(rr_arr, "tolist") else list(rr_arr),
        "cleaned_timeseries": _subsample_timeseries(df, max_points=1000),
        "descriptive_stats": {
            "hr_bpm": _series_stats(df.get("hr_bpm", pd.Series(dtype=float))),
            "eda_us": _empty_stats(),
        },
        "windowed": None,
        "spectral_trajectory": None,
        "stress_decomposition": None,
        "inference": None,
        "motion_artifact_ratio": 0.0,
    }
    return result, extended


def _build_emotibit_only_result(df: pd.DataFrame) -> tuple[AnalysisResponse, dict[str, Any]]:
    eda_mean_us, eda_phasic_index = compute_eda_features(df)
    feature_summary = FeatureSummary(
        rmssd_ms=0.0,
        sdnn_ms=0.0,
        mean_hr_bpm=0.0,
        eda_mean_us=eda_mean_us,
        eda_phasic_index=eda_phasic_index,
        stress_score=0.0,
        rr_source="none",
        rr_source_note=rr_source_note_for("none"),
    )
    quality_flags = [
        "EmotiBit-only analysis: EDA and motion inspection are available; HRV, stress, and synchronization charts require a Polar file.",
    ]
    result = AnalysisResponse(
        synchronized_samples=0,
        drift_slope=1.0,
        drift_intercept_ms=0.0,
        drift_segments=0,
        xcorr_offset_ms=0.0,
        feature_summary=feature_summary,
        quality_flags=quality_flags,
        movement_artifact_ratio=0.0,
        report_markdown=build_markdown_report(feature_summary, quality_flags),
        non_diagnostic_notice=NON_DIAGNOSTIC_NOTICE,
        sync_qc_score=0.0,
        sync_qc_band="unknown",
        sync_qc_gate="single_file",
        sync_qc_failure_reasons=["Synchronization not run in EmotiBit-only mode."],
    )
    extended = {
        "analysis_mode": "emotibit_only",
        "cleaned_timeseries": _subsample_timeseries(df, max_points=1000),
        "rr_series_ms": [],
        "psd": {"frequencies_hz": [], "psd_ms2_hz": [], "rr_source": "none", "bands": {}},
        "descriptive_stats": {
            "hr_bpm": _empty_stats(),
            "eda_us": _series_stats(df.get("eda_us", pd.Series(dtype=float))),
        },
        "windowed": None,
        "spectral_trajectory": None,
        "stress_decomposition": None,
        "inference": None,
        "motion_artifact_ratio": 0.0,
    }
    return result, extended


def _series_stats(series: pd.Series) -> dict[str, float]:
    vals = pd.to_numeric(series, errors="coerce").dropna()
    if len(vals) == 0:
        return _empty_stats()
    return {
        "mean": float(vals.mean()),
        "std": float(vals.std(ddof=1)) if len(vals) > 1 else 0.0,
        "min": float(vals.min()),
        "max": float(vals.max()),
        "p05": float(vals.quantile(0.05)),
        "p95": float(vals.quantile(0.95)),
    }


def _empty_stats() -> dict[str, float]:
    return {"mean": 0.0, "std": 0.0, "min": 0.0, "max": 0.0, "p05": 0.0, "p95": 0.0}


def _subsample_timeseries(df: pd.DataFrame, max_points: int = 1000) -> list[dict]:
    """Downsample the cleaned dataframe to ≤ max_points for chart delivery."""
    if df is None or len(df) == 0:
        return []
    if len(df) <= max_points:
        sub = df
    else:
        step = max(1, len(df) // max_points)
        sub = df.iloc[::step]
    cols = [c for c in ("timestamp_ms", "hr_bpm", "eda_us", "acc_x", "acc_y", "acc_z") if c in sub.columns]
    return [{c: (None if pd.isna(row[c]) else float(row[c])) for c in cols} for _, row in sub.iterrows()]


@router.get("/sessions", response_model=list[SessionSummary])
def list_sessions(limit: int = 10) -> list[SessionSummary]:
    """List recent sessions (for the view 1 Recent-Sessions table)."""
    _migrate_stored_sessions()
    items = sorted(
        _SESSION_STORE.values(),
        key=lambda s: s.get("analyzed_at", ""),
        reverse=True,
    )
    return [
        SessionSummary(
            session_id=s["session_id"],
            subject_id=s["subject_id"],
            session_date=s["session_date"],
            analyzed_at=s["analyzed_at"],
            sync_qc_gate=s["result"].get("sync_qc_gate"),
            sync_qc_score=s["result"].get("sync_qc_score"),
        )
        for s in items[:limit]
    ]


@router.get("/sessions/{session_id}", response_model=SessionDetail)
def get_session(session_id: str) -> SessionDetail:
    """Fetch one session's full metadata + analysis response."""
    _migrate_stored_sessions()
    if session_id not in _SESSION_STORE:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No session found for session_id={session_id!r}",
        )
    record = _SESSION_STORE[session_id]
    return SessionDetail(**record)


@router.get("/sessions/{session_id}/export")
def export_session(session_id: str, format: str = "csv") -> Response:
    """Export a stored session in one of four Kubios-parity formats.

    Supported formats: csv, xlsx (Excel), mat (MATLAB), pdf.
    """
    from app.services.reporting.exporters import EXPORTERS, MIME_TYPES

    if session_id not in _SESSION_STORE:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No session found for session_id={session_id!r}",
        )
    fmt = format.lower()
    if fmt not in EXPORTERS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Unsupported format {format!r}; use one of {sorted(EXPORTERS)}",
        )

    record = _SESSION_STORE[session_id]
    # The stored result is already AnalysisResponse-shaped; rehydrate.
    analysis = AnalysisResponse(**record["result"])
    exporter = EXPORTERS[fmt]
    payload = (
        exporter(analysis, session_id=session_id)
        if fmt == "pdf"
        else exporter(analysis)
    )
    filename = f"{session_id}.{fmt}"
    return Response(
        content=payload,
        media_type=MIME_TYPES[fmt],
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/benchmark/kubios", response_model=list[BlandAltmanMetric])
async def benchmark_against_kubios(
    system_file: UploadFile,
    kubios_file: UploadFile,
    join_col: str = Form("session_id"),
) -> list[BlandAltmanMetric]:
    """Bland-Altman agreement vs a Kubios HRV Premium export."""
    try:
        sys_text = (await system_file.read()).decode("utf-8", errors="replace")
        kub_text = (await kubios_file.read()).decode("utf-8", errors="replace")
        sys_df = pd.read_csv(io.StringIO(sys_text))
        kub_df = pd.read_csv(io.StringIO(kub_text))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Parse error: {exc.__class__.__name__}: {exc}",
        )

    try:
        comparisons = compare_with_kubios(sys_df, kub_df, join_col=join_col)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        )

    # FastAPI + Pydantic handle serialization; return the models as-is.
    return list(comparisons)

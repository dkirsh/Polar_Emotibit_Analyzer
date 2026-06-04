"""Core analysis endpoints — /analyze, /analyze/single, and session CRUD.

This is the main analysis module containing the primary /analyze endpoint,
single-file analysis, and session management endpoints.
"""
from __future__ import annotations

import io
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import pandas as pd
from fastapi import APIRouter, Form, HTTPException, UploadFile, status

from app.services.ai.adapters import NON_DIAGNOSTIC_NOTICE
from app.schemas.analysis import (
    AnalysisResponse,
    FeatureSummary,
    SessionDetail,
    SessionSummary,
    MarkerUpdateRequest,
)
from app.services.ingestion.parsers import parse_emotibit_csv, parse_polar_csv
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
from app.services.processing.pipeline import InsufficientDataError, run_analysis
from app.services.processing.stress import rescale_stress_v2_to_arousal_index
from app.services.processing.statistics import compute_inference_summary, compute_summary_stats
from app.services.processing.sync import synchronize_signals
from app.services.reporting.report_builder import build_markdown_report

from app.api.v1.routes.analysis_helpers import (
    _SESSION_STORE,
    _baseline_window_stress_v2,
    _empty_stats,
    _filter_markers_to_data_range,
    _is_zip,
    _is_zip_bytes,
    _markers_overlap_dataframe,
    _migrate_stored_sessions,
    _persist_store,
    _polar_room_dataframe,
    _series_stats,
    _stress_v2_components,
    _subsample_timeseries,
    _summary_stats,
)


router = APIRouter(tags=["analysis"])
log = logging.getLogger(__name__)


# ----- Analysis ----------------------------------------------------------


@router.post("/analyze", response_model=AnalysisResponse)
async def analyze(
    emotibit_file: UploadFile,
    polar_file: UploadFile,
    markers_file: Optional[UploadFile] = None,
    order_affect_file: Optional[UploadFile] = None,
    session_id: str = Form(...),
    subject_id: str = Form(...),
    study_id: str = Form(...),
    session_date: str = Form(...),
    operator: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
) -> AnalysisResponse:
    """Run the V2.1 pipeline on a pre-synched pair of CSVs (or ZIPs).

    All metadata fields are stored alongside the analysis for later recall
    by the "Recent sessions" list in view 1 and the session-identity bar
    in view 2.
    """
    from app.services.ingestion.zip_ingestion import extract_and_classify_zip
    from app.services.ingestion.parsers import parse_native_emotibit

    try:
        em_raw = await emotibit_file.read()
        if _is_zip(em_raw):
            contents = extract_and_classify_zip(em_raw)
            if contents.emotibit_channels:
                em_df = parse_native_emotibit(contents.emotibit_channels)
            elif contents.emotibit_formatted:
                em_df = parse_emotibit_csv(contents.emotibit_formatted)
            else:
                # Brute-force: try each CSV in the ZIP
                import io as _io, zipfile as _zf
                frames = []
                with _zf.ZipFile(_io.BytesIO(em_raw)) as zf:
                    for info in zf.infolist():
                        if info.is_dir():
                            continue
                        name = info.filename.split("/")[-1]
                        if not name.lower().endswith(".csv") or name.startswith("."):
                            continue
                        try:
                            text = zf.read(info.filename).decode("utf-8", errors="replace")
                            frames.append(parse_emotibit_csv(text))
                        except Exception:
                            continue
                if not frames:
                    raise ValueError("ZIP does not contain recognizable EmotiBit data.")
                em_df = pd.concat(frames, ignore_index=True).sort_values("timestamp_ms")
        else:
            em_df = parse_emotibit_csv(em_raw.decode("utf-8", errors="replace"))

        pol_raw = await polar_file.read()
        if _is_zip(pol_raw):
            contents = extract_and_classify_zip(pol_raw)
            if contents.polar_text:
                pol_df = parse_polar_csv(contents.polar_text)
            else:
                import io as _io, zipfile as _zf
                frames = []
                last_attrs: dict = {}
                with _zf.ZipFile(_io.BytesIO(pol_raw)) as zf:
                    for info in zf.infolist():
                        if info.is_dir():
                            continue
                        name = info.filename.split("/")[-1]
                        if not name.lower().endswith(".csv") or name.startswith("."):
                            continue
                        try:
                            text = zf.read(info.filename).decode("utf-8", errors="replace")
                            df = parse_polar_csv(text)
                            last_attrs = dict(df.attrs)
                            frames.append(df)
                        except Exception:
                            continue
                if not frames:
                    raise ValueError("ZIP does not contain recognizable Polar data.")
                pol_df = pd.concat(frames, ignore_index=True).sort_values("timestamp_ms")
                pol_df.attrs.update(last_attrs)
        else:
            pol_df = parse_polar_csv(pol_raw.decode("utf-8", errors="replace"))
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
    mk_raw_for_aggregate: bytes | None = None
    if markers_file is not None:
        try:
            mk_raw = await markers_file.read()
            mk_raw_for_aggregate = mk_raw
            if _is_zip(mk_raw):
                import zipfile as _zf
                mk_frames = []
                with _zf.ZipFile(io.BytesIO(mk_raw)) as zf:
                    for info in zf.infolist():
                        if info.is_dir():
                            continue
                        name = info.filename.split("/")[-1]
                        if not name.lower().endswith(".csv") or name.startswith("."):
                            continue
                        try:
                            text = zf.read(info.filename).decode("utf-8", errors="replace")
                            df = pd.read_csv(io.StringIO(text))
                            if "event_code" in df.columns and "utc_ms" in df.columns:
                                mk_frames.append(df)
                            elif "event_code" in df.columns:
                                mk_frames.append(df)
                        except Exception:
                            continue
                if mk_frames:
                    mk_df = pd.concat(mk_frames, ignore_index=True)
                else:
                    mk_df = pd.DataFrame(columns=["event_code", "utc_ms"])
            else:
                mk_text = mk_raw.decode("utf-8", errors="replace")
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

    # ── Diagnostic: log timestamp ranges so misalignment is visible ──────
    _diag_em_min = int(em_df["timestamp_ms"].min()) if "timestamp_ms" in em_df.columns and len(em_df) > 0 else None
    _diag_em_max = int(em_df["timestamp_ms"].max()) if _diag_em_min is not None else None
    _diag_pol_min = int(pol_df["timestamp_ms"].min()) if "timestamp_ms" in pol_df.columns and len(pol_df) > 0 else None
    _diag_pol_max = int(pol_df["timestamp_ms"].max()) if _diag_pol_min is not None else None
    _diag_marker_utcs: list[int] = []
    if markers_summary and isinstance(markers_summary.get("event_markers"), list):
        _diag_marker_utcs = [int(m["utc_ms"]) for m in markers_summary["event_markers"] if "utc_ms" in m]
    _diag_mk_min = min(_diag_marker_utcs) if _diag_marker_utcs else None
    _diag_mk_max = max(_diag_marker_utcs) if _diag_marker_utcs else None
    log.warning(
        "TIMESTAMP DIAGNOSTIC: "
        "EmotiBit[%s..%s] Polar[%s..%s] Markers[%s..%s] "
        "n_em=%d n_pol=%d n_markers=%d",
        _diag_em_min, _diag_em_max,
        _diag_pol_min, _diag_pol_max,
        _diag_mk_min, _diag_mk_max,
        len(em_df), len(pol_df), len(_diag_marker_utcs),
    )
    if _diag_em_min is not None and _diag_mk_min is not None:
        overlap = not (_diag_mk_max < _diag_em_min or _diag_mk_min > _diag_em_max)
        log.warning(
            "TIMESTAMP DIAGNOSTIC: markers %s data range. "
            "Diff = marker_min - data_min = %s ms (%.1f s)",
            "OVERLAP" if overlap else "DO NOT OVERLAP WITH",
            _diag_mk_min - _diag_em_min,
            (_diag_mk_min - _diag_em_min) / 1000.0,
        )

    # ------ Extended analytics bundle -----------------------------------
    # Re-derive the cleaned dataframe so the frontend can render windowed,
    # spectral, and decomposition views without a second round-trip.
    cleaned: pd.DataFrame | None = None
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

        # Diagnostic: cleaned DF timestamp range
        if "timestamp_ms" in cleaned.columns and len(cleaned) > 0:
            _c_min = int(cleaned["timestamp_ms"].min())
            _c_max = int(cleaned["timestamp_ms"].max())
            log.warning(
                "TIMESTAMP DIAGNOSTIC: cleaned[%s..%s] span=%.1fs n=%d",
                _c_min, _c_max, (_c_max - _c_min) / 1000.0, len(cleaned),
            )
            if _diag_mk_min is not None:
                c_overlap = not (_diag_mk_max < _c_min or _diag_mk_min > _c_max)
                log.warning(
                    "TIMESTAMP DIAGNOSTIC: markers vs cleaned: %s. "
                    "marker_min - cleaned_min = %s ms (%.1f s)",
                    "OVERLAP" if c_overlap else "NO OVERLAP",
                    _diag_mk_min - _c_min,
                    (_diag_mk_min - _c_min) / 1000.0,
                )
            markers_summary = _filter_markers_to_data_range(markers_summary, _c_min, _c_max)

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

    # Parse Order & Affect file if provided
    order_affect_data: Optional[dict[str, Any]] = None
    oa_raw_for_aggregate: bytes | None = None
    if order_affect_file is not None:
        try:
            from app.services.ingestion.order_affect import parse_order_affect_csv
            from app.services.ingestion.zip_ingestion import extract_and_classify_zip

            oa_raw = await order_affect_file.read()
            oa_raw_for_aggregate = oa_raw
            if _is_zip(oa_raw):
                contents = extract_and_classify_zip(oa_raw)
                if not contents.order_affect_text:
                    raise ValueError("ZIP does not contain recognizable Order & Affect data.")
                oa_text = contents.order_affect_text
            else:
                oa_text = oa_raw.decode("utf-8", errors="replace")
            oa_parsed = parse_order_affect_csv(oa_text)
            order_affect_data = oa_parsed.to_dict()
        except Exception:  # noqa: BLE001
            order_affect_data = None

    # Compute room-level stats if markers are present
    room_stats: Optional[list[dict[str, Any]]] = None
    if markers_summary and extended is not None:
        try:
            from app.services.processing.room_analysis import compute_room_stats
            event_markers = markers_summary.get("event_markers") or []
            # Use the full cleaned DataFrame (not the subsampled timeseries).
            # The cleaned DF has timestamp_ms in UTC epoch ms (from EmotiBit).
            # Markers have utc_ms in the same epoch. These must be on the same
            # timeline for onset/offset gating to find matching data points.
            if cleaned is not None and len(cleaned) > 0:
                room_stats = compute_room_stats(cleaned, event_markers, order_affect_data)
            else:
                # Fallback to subsampled timeseries if cleaned was not built
                ts_data = extended.get("cleaned_timeseries") or []
                if ts_data:
                    room_df = pd.DataFrame(ts_data).dropna(subset=["timestamp_ms"])
                    room_stats = compute_room_stats(room_df, event_markers, order_affect_data)
        except Exception as exc:  # noqa: BLE001
            log.warning("Room stats computation failed: %s", exc)
            room_stats = None

    condition_aggregate: Optional[dict[str, Any]] = None
    if mk_raw_for_aggregate is not None and oa_raw_for_aggregate is not None:
        try:
            condition_aggregate = _condition_aggregate_from_zip_uploads(
                em_raw,
                pol_raw,
                mk_raw_for_aggregate,
                oa_raw_for_aggregate,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("Condition aggregate computation failed: %s", exc)
            condition_aggregate = None

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
        "order_affect": order_affect_data,
        "room_stats": room_stats,
        "condition_aggregate": condition_aggregate,
    }
    _SESSION_STORE[session_id] = stored
    _persist_store()

    return result


def _condition_aggregate_from_zip_uploads(
    emotibit_raw: bytes,
    polar_raw: bytes,
    markers_raw: bytes,
    order_affect_raw: bytes,
) -> dict[str, Any] | None:
    """Compute Latin-square condition aggregates from matched subject ZIPs."""
    if not (_is_zip_bytes(emotibit_raw) and _is_zip_bytes(polar_raw) and _is_zip_bytes(markers_raw) and _is_zip_bytes(order_affect_raw)):
        return None

    from app.services.ingestion.order_affect import parse_order_affect_csv
    from app.services.processing.room_analysis import compute_room_stats
    import re
    import zipfile

    def subject_from_name(name: str) -> str | None:
        match = re.search(r"p(\d{3})", name.lower())
        return f"p{match.group(1)}" if match else None

    def csv_texts_by_subject(raw: bytes) -> dict[str, str]:
        out: dict[str, str] = {}
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                basename = info.filename.split("/")[-1]
                if not basename.lower().endswith(".csv") or basename.startswith(".") or basename.startswith("__"):
                    continue
                subject = subject_from_name(basename)
                if subject is None:
                    continue
                out[subject] = zf.read(info.filename).decode("utf-8", errors="replace")
        return out

    em_texts = csv_texts_by_subject(emotibit_raw)
    pol_texts = csv_texts_by_subject(polar_raw)
    marker_texts = csv_texts_by_subject(markers_raw)
    order_texts = csv_texts_by_subject(order_affect_raw)

    subjects = sorted(set(em_texts) & set(pol_texts) & set(marker_texts) & set(order_texts))
    rows: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    for subject in subjects:
        try:
            em_df_s = parse_emotibit_csv(em_texts[subject])
            pol_df_s = parse_polar_csv(pol_texts[subject])
            markers_df = pd.read_csv(io.StringIO(marker_texts[subject]))
            markers = [
                {
                    "event_code": str(row.get("event_code", "")),
                    "utc_ms": int(row.get("utc_ms")),
                    "note": str(row.get("note", "")) if "note" in row and pd.notna(row.get("note")) else "",
                }
                for row in markers_df.to_dict(orient="records")
                if pd.notna(row.get("utc_ms"))
            ]
            order_data = parse_order_affect_csv(order_texts[subject]).to_dict()

            drift_model = estimate_piecewise_drift(
                source_ts=pol_df_s["timestamp_ms"].astype(int).tolist(),
                reference_ts=em_df_s["timestamp_ms"].astype(int).tolist(),
            )
            corrected = pol_df_s.copy()
            corrected["timestamp_ms"] = apply_piecewise_drift(
                corrected["timestamp_ms"].astype(int).tolist(),
                drift_model,
            )
            synced = synchronize_signals(em_df_s, corrected)
            cleaned_s, _ = clean_signals(synced)
            stats = compute_room_stats(cleaned_s, markers, order_data)
            room_stats_present = any(str(row.get("room_key", "")).lower().startswith("room") for row in stats)
            if not room_stats_present and _markers_overlap_dataframe(markers, pol_df_s):
                stats = compute_room_stats(_polar_room_dataframe(pol_df_s), markers, order_data)
                for stat in stats:
                    stat["data_mode"] = "polar_only"
            baseline = next((row for row in stats if str(row.get("room_key", "")).lower() == "baseline"), None)
            baseline_stress = baseline.get("stress_v2") if isinstance(baseline, dict) else None
            for stat in stats:
                if not str(stat.get("room_key", "")).lower().startswith("room"):
                    continue
                row = dict(stat)
                row["subject_id"] = subject
                row["data_mode"] = row.get("data_mode", "synchronized_multimodal")
                row["visit_number"] = row.get("room_number")
                if isinstance(row.get("stress_v2"), (int, float)) and isinstance(baseline_stress, (int, float)):
                    row["arousal_index"] = max(-1.0, min(1.0, 2.0 * (float(row["stress_v2"]) - float(baseline_stress))))
                else:
                    row["arousal_index"] = None
                rows.append(row)
        except Exception as exc:  # noqa: BLE001
            skipped.append({"subject_id": subject, "reason": f"{exc.__class__.__name__}: {exc}"})

    if not rows:
        return None

    metrics = {
        "arousal_index": "arousal_index",
        "stress_v2": "stress_v2",
        "mean_hr": "mean_hr",
        "mean_eda": "mean_eda",
        "rmssd": "rmssd",
        "mean_rpm": "mean_rpm",
        "rsa_amplitude": "rsa_amplitude",
        "self_report_valence": "valence",
        "self_report_arousal": "arousal",
    }
    conditions: list[dict[str, Any]] = []
    for condition in sorted({str(row.get("room_type", "")) for row in rows if row.get("room_type")}):
        cond_rows = [row for row in rows if str(row.get("room_type", "")) == condition]
        summary: dict[str, Any] = {"condition": condition, "n_subjects": len({row["subject_id"] for row in cond_rows}), "n_rows": len(cond_rows)}
        for output_key, row_key in metrics.items():
            vals = [float(row[row_key]) for row in cond_rows if isinstance(row.get(row_key), (int, float))]
            summary[output_key] = _summary_stats(vals)
        visit_counts: dict[str, int] = {}
        for row in cond_rows:
            visit = str(row.get("visit_number"))
            visit_counts[visit] = visit_counts.get(visit, 0) + 1
        summary["visit_counts"] = visit_counts
        conditions.append(summary)

    return {
        "kind": "latin_square_condition_aggregate",
        "n_subjects": len({row["subject_id"] for row in rows}),
        "n_rows": len(rows),
        "conditions": conditions,
        "rows": rows,
        "skipped": skipped,
    }


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
        quality_flags.append("Low beat count for HRV (<50 beats; RMSSD stability uncertain)")
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


# ----- Session CRUD endpoints -------------------------------------------


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


@router.put("/sessions/{session_id}/markers", response_model=SessionDetail)
def update_session_markers(session_id: str, request: MarkerUpdateRequest) -> SessionDetail:
    """Update event markers for a stored session and recompute baseline arousal."""
    _migrate_stored_sessions()
    if session_id not in _SESSION_STORE:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No session found for session_id={session_id!r}",
        )
    record = _SESSION_STORE[session_id]
    
    # Update markers summary
    markers = [m.model_dump() if hasattr(m, "model_dump") else m.dict() for m in request.markers]
    codes = sorted({str(m.get("event_code", "")) for m in markers})
    record["markers_summary"] = {
        "n_rows": len(markers),
        "codes": codes,
        "event_markers": markers,
    }

    # Recompute arousal_baseline and arousal_index if extended data exists
    extended = record.get("extended")
    if isinstance(extended, dict) and isinstance(extended.get("windowed"), dict):
        windowed = extended["windowed"]
        cleaned_ts = extended.get("cleaned_timeseries") or []
        if cleaned_ts and windowed.get("t_s") and windowed.get("stress_v2"):
            import pandas as pd
            df = pd.DataFrame(cleaned_ts)
            new_baseline = _baseline_window_stress_v2(
                record["markers_summary"],
                df,
                windowed["t_s"],
                windowed["stress_v2"]
            )
            windowed["arousal_baseline"] = new_baseline
            windowed["arousal_index"] = [
                rescale_stress_v2_to_arousal_index(score, new_baseline)
                for score in windowed["stress_v2"]
            ]

    _persist_store()
    return SessionDetail(**record)

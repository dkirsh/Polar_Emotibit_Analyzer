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
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import pandas as pd
from fastapi import APIRouter, Form, HTTPException, UploadFile, status

from app.schemas.analysis import AnalysisResponse
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
from app.services.processing.features import _get_rr_intervals, compute_edr
from app.services.processing.kubios_benchmark import compare_with_kubios
from app.services.processing.pipeline import run_analysis
from app.services.processing.statistics import compute_inference_summary, compute_summary_stats
from app.services.processing.sync import synchronize_signals


router = APIRouter(tags=["analysis"])


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
    _STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _STORE_PATH.write_text(json.dumps(_SESSION_STORE, indent=2, default=str))


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
            markers_summary = {
                "n_rows": int(len(mk_df)),
                "codes": sorted(set(mk_df.get("event_code", pd.Series()).astype(str).tolist())),
            }
        except Exception:  # noqa: BLE001
            markers_summary = {"error": "markers file could not be parsed; ignored"}

    try:
        result = run_analysis(em_df, pol_df)
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
        session_rsa = session_edr["rsa_amplitude"]
        has_rsa = session_rsa is not None

        fs = result.feature_summary
        decomp = decompose_stress(
            fs.rmssd_ms, fs.mean_hr_bpm, fs.eda_mean_us, fs.eda_phasic_index,
            rsa_amplitude=session_rsa,
        )
        wf = compute_windowed_features(cleaned, window_s=60.0, step_s=30.0)
        st = compute_spectral_trajectory(cleaned, window_s=120.0, step_s=60.0)
        psd = compute_full_psd(cleaned)
        rr_arr, rr_source = _get_rr_intervals(cleaned)
        summ = compute_summary_stats(cleaned)
        inf = compute_inference_summary(cleaned) if len(cleaned) >= 10 else None

        # Build stress decomposition components list
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
                "total": decomp.total_score,
                "dominant_driver": decomp.dominant_driver,
                "components": stress_components,
            },
            "windowed": {
                "t_s": wf.window_centers_s,
                "hr_mean": wf.hr_mean,
                "hr_std": wf.hr_std,
                "eda_mean": wf.eda_mean,
                "rmssd": wf.rmssd,
                "stress": wf.stress,
                "hr_contribution": wf.hr_contribution,
                "eda_contribution": wf.eda_contribution,
                "hrv_contribution": wf.hrv_contribution,
                "mean_rpm": wf.mean_rpm,
                "rsa_amplitude": wf.rsa_amplitude,
                "rsa_contribution": wf.rsa_contribution,
            },
            "spectral_trajectory": {
                "t_s": st.window_centers_s,
                "lf_power": st.lf_power,
                "hf_power": st.hf_power,
                "lf_hf_ratio": st.lf_hf_ratio,
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


@router.get("/sessions")
def list_sessions(limit: int = 10) -> list[dict[str, Any]]:
    """List recent sessions (for the view 1 Recent-Sessions table)."""
    items = sorted(
        _SESSION_STORE.values(),
        key=lambda s: s.get("analyzed_at", ""),
        reverse=True,
    )
    slim = [
        {
            "session_id": s["session_id"],
            "subject_id": s["subject_id"],
            "session_date": s["session_date"],
            "analyzed_at": s["analyzed_at"],
            "sync_qc_gate": s["result"].get("sync_qc_gate"),
            "sync_qc_score": s["result"].get("sync_qc_score"),
        }
        for s in items[:limit]
    ]
    return slim


@router.get("/sessions/{session_id}")
def get_session(session_id: str) -> dict[str, Any]:
    """Fetch one session's full metadata + analysis response."""
    if session_id not in _SESSION_STORE:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No session found for session_id={session_id!r}",
        )
    return _SESSION_STORE[session_id]


@router.post("/benchmark/kubios")
async def benchmark_against_kubios(
    system_file: UploadFile,
    kubios_file: UploadFile,
    join_col: str = Form("session_id"),
) -> list[dict[str, Any]]:
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

    return [
        c.model_dump() if hasattr(c, "model_dump") else c.dict()
        for c in comparisons
    ]

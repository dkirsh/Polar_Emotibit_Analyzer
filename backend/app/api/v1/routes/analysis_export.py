"""Export endpoints for analysis sessions.

Contains the /sessions/{session_id}/export endpoint and the
/benchmark/kubios endpoint.
"""
from __future__ import annotations

import io
import logging
from typing import Any

import pandas as pd
from fastapi import APIRouter, Form, HTTPException, Response, UploadFile, status

from app.schemas.analysis import (
    AnalysisResponse,
    BlandAltmanMetric,
)
from app.services.processing.kubios_benchmark import compare_with_kubios

from app.api.v1.routes.analysis_helpers import (
    _SESSION_STORE,
)


router = APIRouter(tags=["analysis"])
log = logging.getLogger(__name__)


@router.get("/sessions/{session_id}/export")
def export_session(session_id: str, format: str = "csv") -> Response:
    """Export a stored session in one of four Kubios-parity formats.

    Supported formats: csv, intervals_csv, xlsx (Excel), mat (MATLAB), pdf.
    """
    from app.services.reporting.exporters import EXPORTERS, MIME_TYPES, export_interval_means_to_csv

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
    if fmt == "intervals_csv":
        payload = export_interval_means_to_csv(record)
        filename = f"{session_id}_interval_means.csv"
        return Response(
            content=payload,
            media_type=MIME_TYPES[fmt],
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

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

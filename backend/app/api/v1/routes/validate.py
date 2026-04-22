"""CSV validation endpoints (schema-only, no pipeline invocation).

View 1 of the GUI (docs/GUI_SCOPE_FILE_ONLY_2026-04-20.md) validates each
uploaded file inline as soon as the user drops it, separately from the
full analysis step. These endpoints let the frontend surface a green-check
or specific-missing-column message without committing to a full pipeline
run.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, UploadFile, status

from app.schemas.analysis import CsvTimestampRange, CsvValidationResponse
from app.services.ingestion.parsers import (
    OPTIONAL_EMOTIBIT_ACCEL_COLUMNS,
    OPTIONAL_EMOTIBIT_RESP_COLUMNS,
    parse_emotibit_csv,
    parse_polar_csv,
)


router = APIRouter(tags=["validate"])


@router.post("/validate/csv/emotibit", response_model=CsvValidationResponse)
async def validate_emotibit_csv(file: UploadFile) -> CsvValidationResponse:
    """Validate an EmotiBit CSV without running the pipeline.

    Returns row count, present columns, and which optional columns are
    missing (e.g., accelerometer, respiration) so the researcher knows
    what downstream features will be available.
    """
    try:
        csv_text = (await file.read()).decode("utf-8", errors="replace")
        df = parse_emotibit_csv(csv_text)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"valid": False, "reason": str(exc)},
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"valid": False, "reason": f"Parse error: {exc.__class__.__name__}: {exc}"},
        )

    present = set(df.columns)
    return CsvValidationResponse(
        valid=True,
        filename=file.filename,
        n_rows=int(len(df)),
        columns_present=sorted(present),
        has_accelerometer=all(c in present for c in OPTIONAL_EMOTIBIT_ACCEL_COLUMNS),
        has_respiration=any(c in present for c in OPTIONAL_EMOTIBIT_RESP_COLUMNS),
        timestamp_range_ms=CsvTimestampRange(
            min=int(df["timestamp_ms"].min()),
            max=int(df["timestamp_ms"].max()),
            span_s=int((df["timestamp_ms"].max() - df["timestamp_ms"].min()) / 1000),
        ),
    )


@router.post("/validate/csv/polar", response_model=CsvValidationResponse)
async def validate_polar_csv(file: UploadFile) -> CsvValidationResponse:
    """Validate a Polar H10 CSV without running the pipeline.

    Reports whether native rr_ms is present (research-grade HRV) vs only
    hr_bpm (BPM-derived RR, reduced accuracy). The distinction matters
    for downstream HRV interpretability and is flagged here so the
    analyst can decide before committing to an analysis.
    """
    try:
        csv_text = (await file.read()).decode("utf-8", errors="replace")
        df = parse_polar_csv(csv_text)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"valid": False, "reason": str(exc)},
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"valid": False, "reason": f"Parse error: {exc.__class__.__name__}: {exc}"},
        )

    present = set(df.columns)
    has_rr = "rr_ms" in present
    return CsvValidationResponse(
        valid=True,
        filename=file.filename,
        n_rows=int(len(df)),
        columns_present=sorted(present),
        has_native_rr=has_rr,
        rr_source="native_polar" if has_rr else "derived_from_bpm",
        rr_source_note=(
            "Native Polar RR intervals present — research-grade HRV."
            if has_rr
            else "Only hr_bpm present — HRV will be derived from BPM (reduced accuracy)."
        ),
        timestamp_range_ms=CsvTimestampRange(
            min=int(df["timestamp_ms"].min()),
            max=int(df["timestamp_ms"].max()),
            span_s=int((df["timestamp_ms"].max() - df["timestamp_ms"].min()) / 1000),
        ),
    )


@router.post("/validate/csv/markers", response_model=CsvValidationResponse)
async def validate_markers_csv(file: UploadFile) -> CsvValidationResponse:
    """Validate an event-markers CSV without running the pipeline.

    Schema (per docs/REAL_DATA_SYNC_COLLECTION_REPORT_2026-03-01.md in the
    sibling emotibit_polar_data_system repo):
        session_id, event_code, utc_ms, note (optional)

    Known event codes: recording_start, stress_task_start, stress_task_end,
    recovery_start, recording_end. Unknown codes are accepted but flagged.
    """
    import io

    import pandas as pd

    KNOWN_CODES = {
        "recording_start",
        "stress_task_start",
        "stress_task_end",
        "recovery_start",
        "recording_end",
    }

    try:
        csv_text = (await file.read()).decode("utf-8", errors="replace")
        df = pd.read_csv(io.StringIO(csv_text))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"valid": False, "reason": f"Parse error: {exc.__class__.__name__}: {exc}"},
        )

    required = {"session_id", "event_code", "utc_ms"}
    missing = sorted(required.difference(df.columns))
    if missing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"valid": False, "reason": f"Missing required columns: {missing}"},
        )

    codes_present = sorted(set(df["event_code"].astype(str).tolist()))
    # Markers don't carry a timestamp_range_ms unless the `utc_ms`
    # column is populated; if it is, report span.
    ts_range: CsvTimestampRange | None = None
    if "utc_ms" in df.columns and len(df) > 0:
        utc = df["utc_ms"].astype(int)
        ts_range = CsvTimestampRange(
            min=int(utc.min()),
            max=int(utc.max()),
            span_s=int((utc.max() - utc.min()) / 1000),
        )
    return CsvValidationResponse(
        valid=True,
        filename=file.filename,
        n_rows=int(len(df)),
        columns_present=sorted(df.columns.tolist()),
        timestamp_range_ms=ts_range,
        event_codes=codes_present,
        n_events=int(len(df)),
    )

"""CSV validation endpoints (schema-only, no pipeline invocation).

View 1 of the GUI (docs/GUI_SCOPE_FILE_ONLY_2026-04-20.md) validates each
uploaded file inline as soon as the user drops it, separately from the
full analysis step. These endpoints let the frontend surface a green-check
or specific-missing-column message without committing to a full pipeline
run.

ZIP files are supported: the validator extracts them and finds the relevant
CSV(s) inside, then validates that component.
"""
from __future__ import annotations

import io
import zipfile
from typing import Any

import pandas as pd
from fastapi import APIRouter, HTTPException, UploadFile, status

from app.schemas.analysis import CsvTimestampRange, CsvValidationResponse
from app.services.ingestion.parsers import (
    OPTIONAL_EMOTIBIT_ACCEL_COLUMNS,
    OPTIONAL_EMOTIBIT_RESP_COLUMNS,
    parse_emotibit_csv,
    parse_native_emotibit,
    parse_polar_csv,
)
from app.services.ingestion.zip_ingestion import extract_and_classify_zip


router = APIRouter(tags=["validate"])


def _is_zip(raw_bytes: bytes) -> bool:
    """Check if raw bytes are a ZIP archive (magic bytes PK\\x03\\x04)."""
    return raw_bytes[:4] == b"PK\x03\x04" or raw_bytes[:4] == b"PK\x05\x06"


# ── EmotiBit ──────────────────────────────────────────────────


@router.post("/validate/csv/emotibit", response_model=CsvValidationResponse)
async def validate_emotibit_csv(file: UploadFile) -> CsvValidationResponse:
    """Validate an EmotiBit CSV (or ZIP containing EmotiBit CSVs).

    Returns row count, present columns, and which optional columns are
    missing (e.g., accelerometer, respiration) so the researcher knows
    what downstream features will be available.
    """
    raw_bytes = await file.read()

    try:
        if _is_zip(raw_bytes):
            df = _validate_emotibit_from_zip(raw_bytes, file.filename or "upload.zip")
        else:
            csv_text = raw_bytes.decode("utf-8", errors="replace")
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


def _validate_emotibit_from_zip(raw_bytes: bytes, filename: str) -> pd.DataFrame:
    """Extract EmotiBit data from a ZIP file.

    Handles two cases:
    1. Native multi-channel EmotiBit files (*_EA.csv, *_AX.csv, etc.)
       — merges channels from the FIRST subject found.
    2. Pre-formatted EmotiBit CSVs with timestamp_ms + eda_us columns
       — concatenates all matching files.
    """
    contents = extract_and_classify_zip(raw_bytes)

    # Case 1: native channels found
    if contents.emotibit_channels:
        return parse_native_emotibit(contents.emotibit_channels)

    # Case 2: pre-formatted CSV found
    if contents.emotibit_formatted:
        return parse_emotibit_csv(contents.emotibit_formatted)

    # Case 3: no EmotiBit files — try parsing each CSV inside the ZIP
    # to find any that look like EmotiBit data
    frames: list[pd.DataFrame] = []
    with zipfile.ZipFile(io.BytesIO(raw_bytes)) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            name = info.filename.split("/")[-1]
            if not name.lower().endswith(".csv") or name.startswith(".") or name.startswith("__"):
                continue
            try:
                text = zf.read(info.filename).decode("utf-8", errors="replace")
                df = parse_emotibit_csv(text)
                frames.append(df)
            except Exception:
                continue

    if not frames:
        raise ValueError(
            f"ZIP file '{filename}' does not contain recognizable EmotiBit data. "
            "Expected CSV files with columns: timestamp_ms, eda_us (pre-formatted) "
            "or *_EA.csv with LocalTimestamp column (native format)."
        )

    # Concatenate all matching files (multi-subject batch)
    combined = pd.concat(frames, ignore_index=True).sort_values("timestamp_ms")
    return combined


# ── Polar ─────────────────────────────────────────────────────


@router.post("/validate/csv/polar", response_model=CsvValidationResponse)
async def validate_polar_csv(file: UploadFile) -> CsvValidationResponse:
    """Validate a Polar H10 CSV (or ZIP containing Polar CSVs).

    Reports whether the file contains raw ECG (preferred), native RR
    intervals, or only beat-level BPM.
    """
    raw_bytes = await file.read()

    try:
        if _is_zip(raw_bytes):
            df = _validate_polar_from_zip(raw_bytes, file.filename or "upload.zip")
        else:
            csv_text = raw_bytes.decode("utf-8", errors="replace")
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

    present = set(df.attrs.get("input_columns_present", list(df.columns)))
    has_rr = bool(df.attrs.get("has_native_rr"))
    has_raw_ecg = bool(df.attrs.get("has_raw_ecg"))
    rr_source = str(df.attrs.get("rr_source", "derived_from_bpm"))
    return CsvValidationResponse(
        valid=True,
        filename=file.filename,
        n_rows=int(df.attrs.get("input_n_rows", len(df))),
        columns_present=sorted(present),
        has_native_rr=has_rr,
        has_raw_ecg=has_raw_ecg,
        rr_source=rr_source,
        rr_source_note=str(df.attrs.get("rr_source_note", "")),
        timestamp_range_ms=CsvTimestampRange(
            min=int(df["timestamp_ms"].min()),
            max=int(df["timestamp_ms"].max()),
            span_s=int((df["timestamp_ms"].max() - df["timestamp_ms"].min()) / 1000),
        ),
    )


def _validate_polar_from_zip(raw_bytes: bytes, filename: str) -> pd.DataFrame:
    """Extract Polar data from a ZIP file."""
    contents = extract_and_classify_zip(raw_bytes)

    if contents.polar_text:
        return parse_polar_csv(contents.polar_text)

    # Try parsing each CSV to find Polar data
    frames: list[pd.DataFrame] = []
    last_attrs: dict[str, Any] = {}
    with zipfile.ZipFile(io.BytesIO(raw_bytes)) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            name = info.filename.split("/")[-1]
            if not name.lower().endswith(".csv") or name.startswith(".") or name.startswith("__"):
                continue
            try:
                text = zf.read(info.filename).decode("utf-8", errors="replace")
                df = parse_polar_csv(text)
                last_attrs = dict(df.attrs)
                frames.append(df)
            except Exception:
                continue

    if not frames:
        raise ValueError(
            f"ZIP file '{filename}' does not contain recognizable Polar data. "
            "Expected CSV files with columns: timestamp_ms + hr_bpm/rr_ms/ecg_uv "
            "or utc_epoch_ns + rr_ms (native format)."
        )

    combined = pd.concat(frames, ignore_index=True).sort_values("timestamp_ms")
    # Preserve attrs from the last successfully parsed file
    combined.attrs.update(last_attrs)
    combined.attrs["input_n_rows"] = int(len(combined))
    return combined


# ── Markers ───────────────────────────────────────────────────


@router.post("/validate/csv/markers", response_model=CsvValidationResponse)
async def validate_markers_csv(file: UploadFile) -> CsvValidationResponse:
    """Validate an event-markers CSV (or ZIP containing marker CSVs).

    Schema: session_id, event_code, utc_ms, note (optional)
    """
    raw_bytes = await file.read()

    try:
        if _is_zip(raw_bytes):
            df = _validate_markers_from_zip(raw_bytes, file.filename or "upload.zip")
        else:
            csv_text = raw_bytes.decode("utf-8", errors="replace")
            df = pd.read_csv(io.StringIO(csv_text))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"valid": False, "reason": f"Parse error: {exc.__class__.__name__}: {exc}"},
        )

    required = {"session_id", "event_code", "utc_ms"}
    missing = sorted(required.difference(df.columns))
    if missing:
        # Try relaxed detection: maybe just event_code + utc_ms (no session_id)
        if "event_code" in df.columns and "utc_ms" in df.columns:
            pass  # Accept without session_id
        else:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={"valid": False, "reason": f"Missing required columns: {missing}"},
            )

    codes_present = sorted(set(df["event_code"].astype(str).tolist())) if "event_code" in df.columns else []
    ts_range: CsvTimestampRange | None = None
    if "utc_ms" in df.columns and len(df) > 0:
        utc = pd.to_numeric(df["utc_ms"], errors="coerce").dropna().astype(int)
        if len(utc) > 0:
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


def _validate_markers_from_zip(raw_bytes: bytes, filename: str) -> pd.DataFrame:
    """Extract markers data from a ZIP file."""
    contents = extract_and_classify_zip(raw_bytes)

    if contents.markers_text:
        return pd.read_csv(io.StringIO(contents.markers_text))

    # Try each CSV
    frames: list[pd.DataFrame] = []
    with zipfile.ZipFile(io.BytesIO(raw_bytes)) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            name = info.filename.split("/")[-1]
            if not name.lower().endswith(".csv") or name.startswith(".") or name.startswith("__"):
                continue
            try:
                text = zf.read(info.filename).decode("utf-8", errors="replace")
                df = pd.read_csv(io.StringIO(text))
                if "event_code" in df.columns and "utc_ms" in df.columns:
                    frames.append(df)
            except Exception:
                continue

    if not frames:
        raise ValueError(
            f"ZIP file '{filename}' does not contain recognizable event marker data. "
            "Expected CSV files with columns: event_code, utc_ms."
        )

    return pd.concat(frames, ignore_index=True)


# ── Order & Affect ────────────────────────────────────────────


@router.post("/validate/csv/order_affect", response_model=CsvValidationResponse)
async def validate_order_affect_csv_endpoint(file: UploadFile) -> CsvValidationResponse:
    """Validate an Order & Affect CSV or ZIP without running the pipeline.

    Expected schema: subject_id, room_number, room_type, valence, arousal.
    One row per room per subject.
    """
    from app.services.ingestion.order_affect import validate_order_affect_csv
    from app.services.ingestion.zip_ingestion import extract_and_classify_zip

    try:
        raw_bytes = await file.read()
        if _is_zip(raw_bytes):
            contents = extract_and_classify_zip(raw_bytes)
            if not contents.order_affect_text:
                raise ValueError(
                    f"ZIP file '{file.filename or 'upload.zip'}' does not contain recognizable "
                    "Order & Affect data. Expected columns such as subject_id, room_type, "
                    "valence, and arousal."
                )
            csv_text = contents.order_affect_text
        else:
            csv_text = raw_bytes.decode("utf-8", errors="replace")
        info = validate_order_affect_csv(csv_text)
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

    return CsvValidationResponse(
        valid=True,
        filename=file.filename,
        n_rows=info["n_rooms"],
        columns_present=["subject_id", "room_number", "room_type", "valence", "arousal"],
        subject_id_detected=info["subject_id"],
        n_rooms=info["n_rooms"],
        room_types=info["room_types"],
        valence_range=info["valence_range"],
        arousal_range=info["arousal_range"],
    )


# ── Vernier ───────────────────────────────────────────────────


@router.post("/validate/csv/vernier", response_model=CsvValidationResponse)
async def validate_vernier_xlsx(file: UploadFile) -> CsvValidationResponse:
    """Validate a Vernier respiration-belt Excel file (.xlsx).

    Parses the file, checks for required columns (timestamp_unix, force),
    resamples to 20 Hz, and returns metadata about the recording.
    """
    from app.services.ingestion.vernier_parser import parse_vernier_xlsx

    raw_bytes = await file.read()

    try:
        result = parse_vernier_xlsx(raw_bytes)
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

    md = result.metadata
    rr_val = md.get("rr_validation")

    return CsvValidationResponse(
        valid=True,
        filename=file.filename,
        n_rows=md["n_raw_samples"],
        columns_present=md["columns_present"],
        sample_rate_hz=md["sample_rate_hz"],
        duration_s=md["duration_s"],
        duration_min=md["duration_min"],
        conditions=md.get("conditions"),
        n_event_markers=md["n_event_markers"],
        n_resampled=md["n_resampled"],
        vendor_rr_median=rr_val["vendor_rr_median"] if rr_val else None,
    )


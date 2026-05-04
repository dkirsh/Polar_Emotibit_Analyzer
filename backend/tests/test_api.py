"""Integration tests for the FastAPI surface.

Covers the five user-facing endpoints:
  - GET  /health
  - POST /api/v1/validate/csv/{emotibit,polar,markers}
  - POST /api/v1/analyze
  - GET  /api/v1/sessions, /api/v1/sessions/{id}
"""
from __future__ import annotations

import csv
import io

from fastapi.testclient import TestClient

from app.main import app
from app.api.v1.routes import analysis as analysis_routes
from app.services.ingestion.synthetic import generate_synthetic_session


client = TestClient(app)


def _raw_ecg_csv(seconds: int = 120, sample_hz: int = 130) -> bytes:
    import numpy as np
    import pandas as pd

    rng = np.random.default_rng(7)
    rr_ms = np.full(max(55, int(seconds / 0.8)), 800.0)
    total_ms = int((len(rr_ms) + 2) * 800)
    dt_ns = int(round(1_000_000_000 / sample_hz))
    ts_ns = np.arange(0, int(total_ms * 1_000_000), dt_ns, dtype=np.int64)
    ecg_uv = rng.normal(0.0, 18.0, len(ts_ns))
    sample_ms = ts_ns / 1_000_000.0
    kernel = [80.0, 240.0, 900.0, 240.0, 80.0]
    beat_times_ms = np.cumsum(rr_ms)
    for beat_ms in beat_times_ms:
        idx = int(np.argmin(np.abs(sample_ms - beat_ms)))
        for offset, amp in enumerate(kernel, start=-2):
            j = idx + offset
            if 0 <= j < len(ecg_uv):
                ecg_uv[j] += amp
    return pd.DataFrame({"timestamp_ns": ts_ns, "ecg_uv": ecg_uv}).to_csv(index=False).encode()


def _synthetic_csvs(seconds: int = 180) -> tuple[bytes, bytes]:
    # Note: generate_synthetic_session injects motion bursts at fixed
    # positions (frame 40 and 110) in its bundled implementation, so
    # the shortest safe duration is ≥ 120 s. Callers should not pass
    # less than 120 s until the synthetic generator is made length-aware.
    em, pol = generate_synthetic_session(seconds=max(seconds, 120))
    return em.to_csv(index=False).encode(), pol.to_csv(index=False).encode()


# ----- health -----------------------------------------------------------


def test_health_returns_200_and_scope_tag():
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] in (True, 1)
    assert body["version"].startswith("2.1")
    assert "file-only" in body["scope"]


# ----- validation -------------------------------------------------------


def test_validate_emotibit_csv_reports_rows_and_accelerometer():
    em_bytes, _ = _synthetic_csvs(60)
    r = client.post(
        "/api/v1/validate/csv/emotibit",
        files={"file": ("em.csv", em_bytes, "text/csv")},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["valid"] is True
    assert body["n_rows"] > 0
    assert body["has_accelerometer"] is True  # synthetic includes acc_{x,y,z}


def test_validate_polar_csv_reports_rr_source():
    _, pol_bytes = _synthetic_csvs(60)
    r = client.post(
        "/api/v1/validate/csv/polar",
        files={"file": ("pol.csv", pol_bytes, "text/csv")},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["valid"] is True
    # synthetic has no rr_ms column -> derived_from_bpm
    assert body["rr_source"] == "derived_from_bpm"


def test_validate_polar_csv_accepts_raw_ecg():
    r = client.post(
        "/api/v1/validate/csv/polar",
        files={"file": ("polar_raw_ecg.csv", _raw_ecg_csv(), "text/csv")},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["valid"] is True
    assert body["has_raw_ecg"] is True
    assert body["rr_source"] == "derived_from_ecg"
    assert "computed in-app" in body["rr_source_note"]


def test_validate_markers_csv_reports_event_codes():
    markers = b"session_id,event_code,utc_ms,note\nS1,recording_start,1000,start\nS1,stress_task_start,2000,task\n"
    r = client.post(
        "/api/v1/validate/csv/markers",
        files={"file": ("event_markers.csv", markers, "text/csv")},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["valid"] is True
    assert body["n_events"] == 2
    assert body["event_codes"] == ["recording_start", "stress_task_start"]
    assert body["timestamp_range_ms"]["span_s"] == 1


def test_analyze_stores_event_marker_timestamps():
    em_bytes, pol_bytes = _synthetic_csvs(90)
    markers = b"session_id,event_code,utc_ms,note\nTEST_MARKERS,recording_start,0,start\nTEST_MARKERS,stress_task_start,30000,task\n"
    r = client.post(
        "/api/v1/analyze",
        files={
            "emotibit_file": ("em.csv", em_bytes, "text/csv"),
            "polar_file": ("pol.csv", pol_bytes, "text/csv"),
            "markers_file": ("event_markers.csv", markers, "text/csv"),
        },
        data={
            "session_id": "TEST_MARKERS",
            "subject_id": "P01",
            "study_id": "STUDY01",
            "session_date": "2026-04-20",
        },
    )
    assert r.status_code == 200, r.text
    detail = client.get("/api/v1/sessions/TEST_MARKERS").json()
    events = detail["markers_summary"]["event_markers"]
    assert events[0]["event_code"] == "recording_start"
    assert events[1]["utc_ms"] == 30000


def test_interval_means_csv_export_contains_rows_and_r2_footer():
    em_bytes, pol_bytes = _synthetic_csvs(180)
    markers = (
        b"session_id,event_code,utc_ms,note\n"
        b"TEST_INTERVAL_EXPORT,baseline_onset,0,baseline starts\n"
        b"TEST_INTERVAL_EXPORT,baseline_offset,60000,baseline ends\n"
        b"TEST_INTERVAL_EXPORT,room1_onset,60000,room starts\n"
        b"TEST_INTERVAL_EXPORT,room1_offset,120000,room ends\n"
    )
    r = client.post(
        "/api/v1/analyze",
        files={
            "emotibit_file": ("em.csv", em_bytes, "text/csv"),
            "polar_file": ("pol.csv", pol_bytes, "text/csv"),
            "markers_file": ("event_markers.csv", markers, "text/csv"),
        },
        data={
            "session_id": "TEST_INTERVAL_EXPORT",
            "subject_id": "P01",
            "study_id": "STUDY01",
            "session_date": "2026-05-04",
        },
    )
    assert r.status_code == 200, r.text

    exported = client.get("/api/v1/sessions/TEST_INTERVAL_EXPORT/export?format=intervals_csv")
    assert exported.status_code == 200, exported.text
    assert "TEST_INTERVAL_EXPORT_interval_means.csv" in exported.headers["content-disposition"]

    rows = list(csv.reader(io.StringIO(exported.text)))
    assert rows[0][:12] == [
        "Key",
        "Interval",
        "Seconds",
        "Arousal",
        "Main Driver",
        "Hr Mean",
        "HR SD",
        "EDA mean",
        "Stress V2",
        "Resp Rate",
        "RMSSD",
        "RSA Amp",
    ]
    assert rows[1][0:3] == ["A", "Baseline", "0.0-60.0"]
    assert rows[2][0:3] == ["B", "Room 1", "60.0-120.0"]
    assert any(row[:1] == ["Equation"] and "SS_res" in row[1] for row in rows)
    assert any(row[:1] == ["Meaning"] and "fraction of outcome variance" in row[1] for row in rows)


def test_validate_emotibit_csv_rejects_missing_columns():
    bad = b"timestamp_ms,not_eda\n0,1.0\n1000,1.1\n"
    r = client.post(
        "/api/v1/validate/csv/emotibit",
        files={"file": ("bad.csv", bad, "text/csv")},
    )
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert detail["valid"] is False
    assert "eda_us" in detail["reason"]


# ----- analyze ----------------------------------------------------------


def test_analyze_on_synthetic_pair_returns_feature_summary():
    em_bytes, pol_bytes = _synthetic_csvs(180)
    r = client.post(
        "/api/v1/analyze",
        files={
            "emotibit_file": ("em.csv", em_bytes, "text/csv"),
            "polar_file": ("pol.csv", pol_bytes, "text/csv"),
        },
        data={
            "session_id": "TEST_ANALYZE_01",
            "subject_id": "P01",
            "study_id": "STUDY01",
            "session_date": "2026-04-20",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["sync_qc_gate"] in {"go", "conditional_go", "no_go"}
    assert body["feature_summary"]["rmssd_ms"] > 0
    assert body["synchronized_samples"] > 0
    assert isinstance(body["quality_flags"], list)
    assert body["non_diagnostic_notice"]  # required per AI safety notice
    assert body["feature_summary"]["rr_source"] == "derived_from_bpm"
    assert "BPM" in body["feature_summary"]["rr_source_note"]

    detail = client.get("/api/v1/sessions/TEST_ANALYZE_01").json()
    edr_proxy = detail["extended"]["edr_proxy"]
    assert edr_proxy["source"] == "rr_edr_proxy"
    assert edr_proxy["rr_source"] == "derived_from_bpm"
    assert "BPM" in edr_proxy["rr_source_note"]
    assert len(edr_proxy["time_s"]) == len(edr_proxy["signal"])
    assert edr_proxy["quality"]["source_confidence"] == 0.4
    assert edr_proxy["quality"]["overall_confidence"] is not None


def test_analyze_accepts_raw_ecg_polar_csv():
    em_bytes, _ = _synthetic_csvs(180)
    r = client.post(
        "/api/v1/analyze",
        files={
            "emotibit_file": ("em.csv", em_bytes, "text/csv"),
            "polar_file": ("polar_raw_ecg.csv", _raw_ecg_csv(180), "text/csv"),
        },
        data={
            "session_id": "TEST_ANALYZE_RAW_ECG",
            "subject_id": "P01",
            "study_id": "STUDY01",
            "session_date": "2026-04-20",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["feature_summary"]["rr_source"] == "derived_from_ecg"
    assert "computed in-app" in body["feature_summary"]["rr_source_note"]
    assert body["feature_summary"]["rmssd_ms"] >= 0

    detail = client.get("/api/v1/sessions/TEST_ANALYZE_RAW_ECG").json()
    assert detail["extended"]["edr_proxy"]["rr_source"] == "derived_from_ecg"
    assert "Raw Polar ECG" in detail["extended"]["edr_proxy"]["rr_source_note"]


def test_edr_proxy_backfill_uses_existing_rr_source():
    record = {
        "result": {"feature_summary": {"rr_source": "derived_from_bpm"}},
        "extended": {
            "rr_series_ms": [800.0 + (i % 5) * 5.0 for i in range(80)],
            "psd": {"rr_source": "derived_from_ecg"},
        },
    }
    changed = analysis_routes._maybe_backfill_edr_proxy(record)
    assert changed is True
    assert record["extended"]["edr_proxy"]["rr_source"] == "derived_from_ecg"
    assert "raw polar ecg" in record["extended"]["edr_proxy"]["rr_source_note"].lower()
    assert record["result"]["feature_summary"]["rr_source_note"]
    assert record["extended"]["edr_proxy"]["quality"]["overall_confidence"] is not None


def test_analyze_single_polar_saves_chart_bundle():
    _, pol_bytes = _synthetic_csvs(180)
    r = client.post(
        "/api/v1/analyze/single",
        files={"file": ("pol.csv", pol_bytes, "text/csv")},
        data={
            "source_type": "polar",
            "session_id": "TEST_SINGLE_POLAR",
            "subject_id": "P01",
            "study_id": "STUDY01",
            "session_date": "2026-04-20",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["sync_qc_gate"] == "single_file"
    assert body["feature_summary"]["mean_hr_bpm"] > 0
    detail = client.get("/api/v1/sessions/TEST_SINGLE_POLAR").json()
    assert detail["extended"]["analysis_mode"] == "polar_only"
    assert detail["extended"]["rr_series_ms"]


def test_analyze_single_emotibit_saves_chart_bundle():
    em_bytes, _ = _synthetic_csvs(180)
    r = client.post(
        "/api/v1/analyze/single",
        files={"file": ("em.csv", em_bytes, "text/csv")},
        data={
            "source_type": "emotibit",
            "session_id": "TEST_SINGLE_EMOTIBIT",
            "subject_id": "P01",
            "study_id": "STUDY01",
            "session_date": "2026-04-20",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["sync_qc_gate"] == "single_file"
    assert body["feature_summary"]["eda_mean_us"] > 0
    detail = client.get("/api/v1/sessions/TEST_SINGLE_EMOTIBIT").json()
    assert detail["extended"]["analysis_mode"] == "emotibit_only"
    assert detail["extended"]["cleaned_timeseries"]


def test_analyze_missing_metadata_returns_422():
    em_bytes, pol_bytes = _synthetic_csvs(60)
    r = client.post(
        "/api/v1/analyze",
        files={
            "emotibit_file": ("em.csv", em_bytes, "text/csv"),
            "polar_file": ("pol.csv", pol_bytes, "text/csv"),
        },
        data={"session_id": "X"},  # subject_id / study_id / session_date missing
    )
    assert r.status_code == 422, r.text


# ----- recent sessions --------------------------------------------------


def test_sessions_list_includes_most_recent_analysis():
    # Seed one
    em_bytes, pol_bytes = _synthetic_csvs(60)
    client.post(
        "/api/v1/analyze",
        files={
            "emotibit_file": ("em.csv", em_bytes, "text/csv"),
            "polar_file": ("pol.csv", pol_bytes, "text/csv"),
        },
        data={
            "session_id": "TEST_LIST_01",
            "subject_id": "P02",
            "study_id": "STUDY01",
            "session_date": "2026-04-20",
        },
    )
    r = client.get("/api/v1/sessions")
    assert r.status_code == 200
    assert any(s["session_id"] == "TEST_LIST_01" for s in r.json())


def test_session_detail_returns_full_result():
    r = client.get("/api/v1/sessions/TEST_LIST_01")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["session_id"] == "TEST_LIST_01"
    assert "result" in body
    assert body["result"]["feature_summary"]["rmssd_ms"] > 0
    assert body["extended"] is not None
    assert body["extended"]["cleaned_timeseries"]


def test_session_detail_404_for_unknown():
    r = client.get("/api/v1/sessions/NOT_A_REAL_SESSION_ID")
    assert r.status_code == 404

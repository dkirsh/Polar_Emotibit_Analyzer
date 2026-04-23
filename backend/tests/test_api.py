"""Integration tests for the FastAPI surface.

Covers the five user-facing endpoints:
  - GET  /health
  - POST /api/v1/validate/csv/{emotibit,polar,markers}
  - POST /api/v1/analyze
  - GET  /api/v1/sessions, /api/v1/sessions/{id}
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
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
    assert body["feature_summary"]["rmssd_ms"] >= 0


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


def test_session_detail_404_for_unknown():
    r = client.get("/api/v1/sessions/NOT_A_REAL_SESSION_ID")
    assert r.status_code == 404

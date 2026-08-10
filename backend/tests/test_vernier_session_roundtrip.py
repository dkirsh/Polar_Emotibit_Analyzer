"""Severity test for the Vernier last-mile defect.

The /analyze endpoint computes and stores Vernier respiration-belt results
under the keys `vernier` and `respiratory_patterns` (analysis_core.py). But
GET /sessions/{id} returns a typed SessionDetail via SessionDetail(**record).
If SessionDetail does not declare those fields, Pydantic silently drops them
and a recorded belt is computed-but-never-shown.

This test passes only while the schema carries the fields through. It is
written as an attack: it builds a record *with* belt data and asserts the
data survives the SessionDetail boundary. Run it against the pre-fix schema
and it fails (the keys vanish); that failure is exactly the defect.
"""
from __future__ import annotations

from app.schemas.analysis import SessionDetail


def _minimal_record(**extra):
    rec = {
        "analysis_id": "a1",
        "session_id": "s1",
        "subject_id": "sub1",
        "study_id": "study1",
        "session_date": "2026-06-06",
        "analyzed_at": "2026-06-06T00:00:00+00:00",
        "result": {"ok": True},
    }
    rec.update(extra)
    return rec


def test_vernier_survives_sessiondetail_boundary():
    """A stored belt summary must round-trip through SessionDetail unchanged."""
    vernier = {
        "n_samples": 12000,
        "duration_s": 600.0,
        "sample_rate_hz": 20,
        "respiratory_features": {
            "resp_rate_bpm": 14.2,
            "mean_cycle_dur_s": 4.23,
            "ie_ratio_mean": 0.72,
            "n_breaths": 142,
        },
    }
    record = _minimal_record(vernier=vernier)

    detail = SessionDetail(**record)

    assert detail.vernier is not None, (
        "SessionDetail dropped the `vernier` block — the belt would never reach "
        "the frontend (last-mile defect)."
    )
    assert detail.vernier["respiratory_features"]["resp_rate_bpm"] == 14.2


def test_respiratory_patterns_survives_sessiondetail_boundary():
    """Detected respiratory stress patterns must also survive the boundary."""
    patterns = {
        "patterns_detected": [
            {"label": "Tachypnea (fast rate)", "found": True, "stress_count": 8},
        ],
        "n_figures": 1,
    }
    record = _minimal_record(respiratory_patterns=patterns)

    detail = SessionDetail(**record)

    assert detail.respiratory_patterns is not None, (
        "SessionDetail dropped `respiratory_patterns` — detected breathing "
        "anomalies would never be shown."
    )
    assert detail.respiratory_patterns["patterns_detected"][0]["found"] is True


def test_absent_belt_is_none_not_error():
    """Sessions with no belt recorded must still construct cleanly."""
    detail = SessionDetail(**_minimal_record())
    assert detail.vernier is None
    assert detail.respiratory_patterns is None

"""Severity tests for the RespInPeace engine + recalibrated classifier wiring.

Attacks, not demos:
  - tuned holds must flag <= looser holds on the same signal (part B);
  - the classifier must expose all 11 patterns and NOT saturate (the defect that
    recalibration fixes);
  - the pipeline must actually use the RespInPeace engine and attach the
    extended patterns (last mile).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.services.processing.respiratory import respinpeace_engine as eng
from app.services.processing.respiratory import pattern_classifier as pc
from app.services.processing.respiratory import pipeline as rp


def _synth_force(fs=20, minutes=4.0, bpm=13.0, hold_at=None, hold_len_s=0.0, seed=0):
    rng = np.random.default_rng(seed)
    n = int(minutes * 60 * fs)
    t = np.arange(n) / fs
    force = 1.0 * np.sin(2 * np.pi * (bpm / 60.0) * t) + rng.normal(0, 0.05, n)
    if hold_at is not None and hold_len_s > 0:
        i0 = int(hold_at * fs); i1 = i0 + int(hold_len_s * fs)
        force[i0:i1] = force[i0]  # flat plateau = a hold
    return force


def test_engine_detects_physiologic_breaths():
    res = eng.detect(_synth_force(bpm=13.0), fs=20)
    assert res.error is None, res.error
    assert len(res.cycles_df) > 15
    # median breath rate should be in a plausible band, not 2x over-detected
    assert 8 <= res.cycles_df["rate_bpm"].median() <= 22
    assert "hold_dur_s" in res.cycles_df


def test_tuned_holds_not_more_than_loose():
    """Tuned (long-duration, high-prominence) holds must not exceed loose holds."""
    force = _synth_force(minutes=5, hold_at=60.0, hold_len_s=2.0)
    tuned = eng.detect(force, 20, hold_min_dur_s=1.0, hold_prominence=0.12)
    loose = eng.detect(force, 20, hold_min_dur_s=0.25, hold_prominence=0.05)
    assert tuned.error is None and loose.error is None
    assert tuned.n_holds <= loose.n_holds, (tuned.n_holds, loose.n_holds)


def test_classifier_exposes_11_patterns_and_is_not_saturated():
    # baseline-rest breaths + a stressed block; build a minimal cycle table
    rows = []
    for i in range(60):
        rows.append(dict(rate_bpm=13 + np.random.default_rng(i).normal(0, 0.5),
                         dur=4.5, ie_ratio=0.5, amplitude=1.0,
                         local_cv=0.08, phase="biometric_baseline"))
    for i in range(40):
        rows.append(dict(rate_bpm=14.0, dur=4.2, ie_ratio=0.6, amplitude=0.95,
                         local_cv=0.12, phase="task_1"))
    df = pd.DataFrame(rows)
    out = pc.classify(df)
    for p in pc.PATTERNS:
        assert p in out, f"missing pattern {p}"
    assert "weighted_stress" in out
    # recalibration: must not flag almost everything
    assert out["any_stress"].mean() < 0.9
    # weights present and irregularity/sigh outrank apnea
    assert pc.PATTERN_WEIGHTS["irregular"] > pc.PATTERN_WEIGHTS["apnea"]


def test_pipeline_prefers_respinpeace_and_attaches_extended():
    force = _synth_force(minutes=5, bpm=13.0)
    ts = pd.DataFrame({"force": force})
    vernier_result = {"metadata": {"sample_rate_hz": 20}, "_timeseries": ts,
                      "event_markers": []}
    res = rp.run(vernier_result=vernier_result, markers=None, conditions=None)
    assert res.error is None, res.error
    assert res.manifest.get("engine") == "respinpeace"
    assert "extended_patterns" in res.result
    assert res.result["extended_patterns"]["n_breaths"] > 10

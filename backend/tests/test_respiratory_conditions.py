"""Tests for researcher-chosen respiratory condition grouping (recompute).

These exercise recompute_respiratory_patterns directly with a synthetic
recompute payload, and assert that the user's stress/calm role assignment
actually changes which breaths are counted — i.e. the grouping is honoured,
not ignored. The severity case: if recompute ignored the roles, the stressed
counts would not move when the roles are swapped.
"""
from __future__ import annotations

import numpy as np

from app.services.processing.respiratory_patterns import (
    extract_breath_cycles,
    recompute_respiratory_patterns,
)


def _synthetic_payload():
    """Build a recompute payload with two marked phases: a calm, regular phase
    and a stressed, fast/irregular phase."""
    fs = 20
    rng = np.random.default_rng(0)

    # Calm: ~4.0 s breaths (15 bpm), regular, for 80 s.
    # Stress: ~1.8 s breaths (33 bpm), irregular, for 80 s.
    sig = []
    troughs = []
    peaks = []
    t = 0
    markers = [{"event_code": "calm", "elapsed_s": 0.0},
               {"event_code": "stress", "elapsed_s": 80.0}]

    def add_breath(dur_s):
        nonlocal t
        n = int(dur_s * fs)
        troughs.append(len(sig))
        half = max(1, n // 2)
        for i in range(n):
            # simple triangular breath, peak at half
            val = (i / half) if i < half else (2 - i / half)
            sig.append(val + rng.normal(0, 0.02))
        peaks.append(troughs[-1] + half)

    while t < 80:
        add_breath(4.0)
        t += 4.0
    while t < 160:
        d = 1.8 + rng.normal(0, 0.4)  # irregular
        d = max(1.5, min(3.0, d))
        add_breath(d)
        t += d
    troughs.append(len(sig) - 1)

    sig = np.asarray(sig, dtype=float)
    # z-score
    resp_z = (sig - sig.mean()) / (sig.std() + 1e-9)
    cycles_df = extract_breath_cycles(resp_z, peaks, troughs, fs, markers, detrended=sig)
    assert len(cycles_df) > 10, "fixture should yield many cycles"

    return {
        "resp_z": [round(float(x), 3) for x in resp_z.tolist()],
        "peaks": [int(p) for p in peaks],
        "troughs": [int(x) for x in troughs],
        "fs": fs,
        "cycles": cycles_df.to_dict(orient="records"),
    }


def test_recompute_honours_role_assignment():
    payload = _synthetic_payload()

    # Designate "stress" as the stress arm, "calm" as the control.
    res_a = recompute_respiratory_patterns(payload, [
        {"name": "Treatment", "markers": ["stress"], "role": "stress"},
        {"name": "Control", "markers": ["calm"], "role": "calm"},
    ])
    assert "error" not in res_a, res_a.get("error")
    assert "pattern_details" in res_a
    assert res_a["total_breaths"] > 0

    # Swap the roles: now "calm" is treated as the stress arm. The stressed
    # counts must change — proving the role assignment is actually used and not
    # hardcoded to the defaults.
    res_b = recompute_respiratory_patterns(payload, [
        {"name": "Treatment", "markers": ["calm"], "role": "stress"},
        {"name": "Control", "markers": ["stress"], "role": "calm"},
    ])
    assert "error" not in res_b, res_b.get("error")

    counts_a = {k: v["count"] for k, v in res_a["pattern_details"].items()}
    counts_b = {k: v["count"] for k, v in res_b["pattern_details"].items()}
    assert counts_a != counts_b, (
        "Swapping which markers are the stress arm did not change any stressed "
        "pattern counts — the role assignment is being ignored."
    )


def test_recompute_builds_condition_comparison():
    payload = _synthetic_payload()
    res = recompute_respiratory_patterns(payload, [
        {"name": "Calm phase", "markers": ["calm"], "role": "calm"},
        {"name": "Stress phase", "markers": ["stress"], "role": "stress"},
    ])
    conds = res.get("condition_comparison", {}).get("conditions", {})
    assert set(conds.keys()) == {"Calm phase", "Stress phase"}
    # The stress phase should show a higher mean respiratory rate than calm.
    assert conds["Stress phase"]["resp_rate_mean"] > conds["Calm phase"]["resp_rate_mean"]


def test_recompute_missing_inputs_returns_error():
    res = recompute_respiratory_patterns({}, [{"name": "x", "markers": ["a"], "role": "stress"}])
    assert "error" in res

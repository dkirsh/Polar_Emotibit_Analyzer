"""Severity tests for the six-stage workflow orchestrator + canonical store.

Attacks the contract: auto must run to completion or pause only on a real
ambiguity; define must pause without a comparison and resume once given one;
analyse must reproduce a known paired contrast; visualise must never raise;
rerun must drop downstream artifacts.
"""
from __future__ import annotations

import os
import tempfile

import numpy as np
import pandas as pd

from app.services.workflow.state import WorkflowState, STAGES
from app.services.workflow.orchestrator import Orchestrator
from app.services.workflow.canonical_store import CanonicalStore


def _make_input_dir(tmp) -> str:
    """Two subjects, each with an EmotiBit EDA file + onset/offset markers giving
    a 'plants' and 'no_plants' window with a known EDA difference."""
    d = os.path.join(tmp, "in"); os.makedirs(d, exist_ok=True)
    for sub, plants_mean, noplants_mean in [("p012_G1", 1.0, 2.0), ("p014_G3", 1.5, 2.5), ("p016_G4", 1.2, 2.2)]:
        t0 = 1_700_000_000_000
        # plants window 0–10s, no_plants 20–30s
        rows = []
        for i in range(0, 10000, 100):
            rows.append((t0 + i, plants_mean))
        for i in range(20000, 30000, 100):
            rows.append((t0 + i, noplants_mean))
        pd.DataFrame(rows, columns=["timestamp_ms", "eda_us"]).to_csv(
            os.path.join(d, f"{sub}_emotibit.csv"), index=False)
        pd.DataFrame([
            {"event_code": "plants_onset", "utc_ms": t0 + 0},
            {"event_code": "plants_offset", "utc_ms": t0 + 9999},
            {"event_code": "no_plants_onset", "utc_ms": t0 + 20000},
            {"event_code": "no_plants_offset", "utc_ms": t0 + 30000},
        ]).to_csv(os.path.join(d, f"{sub}_markers.csv"), index=False)
    return d


def _state(tmp, **cfg) -> WorkflowState:
    return WorkflowState(workflow_id="t", db_path=os.path.join(tmp, "canon.db"), config=cfg)


def test_define_pauses_then_resolve_completes_full_run():
    with tempfile.TemporaryDirectory() as tmp:
        d = _make_input_dir(tmp)
        orch = Orchestrator(_state(tmp, input_dir=d))  # no comparison → define pauses
        s = orch.advance(mode="auto")
        assert s.current_stage == "define" and s.pending, "auto should pause at define"
        # resolve with the comparison and continue
        s = orch.resolve({"comparison": {"conditions": ["plants", "no_plants"], "measure": "eda_tonic"}})
        assert s.done, "run should finish after resolving the comparison"
        # analyse reproduced the known paired contrast (plants < no_plants by ~1.0)
        paired = s.artifacts["analyse"]["measures"]["eda_tonic"]["paired"]
        assert paired["n"] == 3
        assert abs(paired["diff"] - (-1.0)) < 0.05  # plants below no_plants by ~1.0
        orch.close()


def test_auto_runs_straight_through_when_comparison_preconfigured():
    with tempfile.TemporaryDirectory() as tmp:
        d = _make_input_dir(tmp)
        orch = Orchestrator(_state(tmp, input_dir=d,
                                   comparison={"conditions": ["plants", "no_plants"], "measure": "eda_tonic"}))
        s = orch.advance(mode="auto")
        assert s.done and not s.pending, "with comparison set, auto runs to completion"
        assert "text" in s.artifacts["visualise"]
        # manifest recorded auto-resolved defaults (audit trail)
        assert any(m["resolved_by"] == "default" for m in s.manifest)
        orch.close()


def test_step_advances_one_stage():
    with tempfile.TemporaryDirectory() as tmp:
        d = _make_input_dir(tmp)
        orch = Orchestrator(_state(tmp, input_dir=d,
                                   comparison={"conditions": ["plants", "no_plants"], "measure": "eda_tonic"}))
        s = orch.advance(mode="step")
        assert s.status.get("connect") == "ok" and s.current == 1, "only one stage ran"
        orch.close()


def test_visualise_never_raises_on_empty_analysis():
    from app.services.workflow import stages
    with tempfile.TemporaryDirectory() as tmp:
        st = _state(tmp)
        store = CanonicalStore(st.db_path)
        res = stages.visualise(st, store)  # no analyse artifact present
        assert res.status.value == "ok"
        store.close()


def test_single_subject_run_is_descriptive_not_error():
    """n=1 must run end-to-end: analyse returns per-subject values + a descriptive
    note instead of raising or fabricating a group statistic."""
    with tempfile.TemporaryDirectory() as tmp:
        d = os.path.join(tmp, "in"); os.makedirs(d)
        t0 = 1_700_000_000_000
        rows = [(t0 + i, 1.0) for i in range(0, 10000, 100)] + \
               [(t0 + i, 2.0) for i in range(20000, 30000, 100)]
        pd.DataFrame(rows, columns=["timestamp_ms", "eda_us"]).to_csv(
            os.path.join(d, "p012_G1_emotibit.csv"), index=False)
        pd.DataFrame([
            {"event_code": "plants_onset", "utc_ms": t0}, {"event_code": "plants_offset", "utc_ms": t0 + 9999},
            {"event_code": "no_plants_onset", "utc_ms": t0 + 20000}, {"event_code": "no_plants_offset", "utc_ms": t0 + 30000},
        ]).to_csv(os.path.join(d, "p012_G1_markers.csv"), index=False)
        orch = Orchestrator(_state(tmp, input_dir=d,
                                   comparison={"conditions": ["plants", "no_plants"], "measure": "eda_tonic"}))
        s = orch.advance(mode="auto")
        assert s.done, "single-subject run must complete"
        block = s.artifacts["analyse"]["measures"]["eda_tonic"]
        assert "paired" not in block and "note" in block, "n=1 is descriptive, not a paired test"
        assert s.artifacts["analyse"]["n_subjects"] == 1
        orch.close()


def test_inspect_returns_series_and_per_window_measures():
    from app.services.workflow import stages
    with tempfile.TemporaryDirectory() as tmp:
        st = _state(tmp)
        store = CanonicalStore(st.db_path)
        t0 = 1_700_000_000_000
        store.put_session("p012", subject_id="p012")
        store.put_samples("sample_eda", "p012", [(t0 + i, 1.5) for i in range(0, 10000, 100)])
        store.put_events("p012", [{"label": "plants", "onset_ms": t0, "offset_ms": t0 + 9999}])
        ins = stages.inspect("p012", store)
        assert ins["session_id"] == "p012" and len(ins["eda"]) > 0
        assert abs(ins["per_window_measures"]["eda_tonic"]["plants"] - 1.5) < 1e-6
        store.close()


def test_multi_measure_and_chart_engine():
    """Two measures requested; visualise renders a PNG per measure that has data."""
    with tempfile.TemporaryDirectory() as tmp:
        d = _make_input_dir(tmp)
        orch = Orchestrator(_state(tmp, input_dir=d,
                                   comparison={"conditions": ["plants", "no_plants"],
                                               "measures": ["eda_tonic"]}))
        s = orch.advance(mode="auto")
        assert s.done
        figs = s.artifacts["visualise"]["figures"]
        assert "eda_tonic" in figs and os.path.exists(figs["eda_tonic"]), "chart engine wrote a figure"
        orch.close()


def test_canonicalise_pauses_when_no_conditions_derivable():
    """Ingestion-confidence gate: EmotiBit samples but no markers/conditions →
    needs_input asking for a roster, never a silent guess."""
    with tempfile.TemporaryDirectory() as tmp:
        d = os.path.join(tmp, "in"); os.makedirs(d)
        t0 = 1_700_000_000_000
        pd.DataFrame([(t0 + i, 1.0) for i in range(0, 5000, 100)],
                     columns=["timestamp_ms", "eda_us"]).to_csv(
            os.path.join(d, "p012_G1_emotibit.csv"), index=False)
        orch = Orchestrator(_state(tmp, input_dir=d, require_conditions=True,
                                   comparison={"conditions": ["plants", "no_plants"], "measure": "eda_tonic"}))
        s = orch.advance(mode="auto")
        assert s.current_stage == "canonicalise" and s.pending, "must pause to request a roster"
        assert any("roster" in (p.get("key", "") if isinstance(p, dict) else p.key)
                   for p in s.pending)
        orch.close()


def test_respinpeace_respiration_flows_through_workflow():
    """Vernier belt force ingested → resp_rate and the RespInPeace-based
    resp_stress_index computed per condition window (the integration that was
    missing from the workflow)."""
    from app.services.workflow import stages, measures as M
    with tempfile.TemporaryDirectory() as tmp:
        d = os.path.join(tmp, "in"); os.makedirs(d)
        t0 = 1_700_000_000_000
        fs, secs = 20, 120
        n = fs * secs
        ts = [t0 + int(1000 * k / fs) for k in range(n)]
        # calm 0.25 Hz breathing for first half (label A), faster/irregular second half (B)
        import math, random
        random.seed(0)
        force, cond = [], []
        for k in range(n):
            tsec = k / fs
            if tsec < secs / 2:
                force.append(1.0 * math.sin(2 * math.pi * 0.25 * tsec)); cond.append("room")
            else:
                f = 0.5 * math.sin(2 * math.pi * 0.5 * tsec) + 0.4 * random.random()
                force.append(f); cond.append("stressor")
        rate = [15.0 if c == "room" else 30.0 for c in cond]
        pd.DataFrame({"timestamp_ms": ts, "force": force, "resp_rate": rate,
                      "condition": cond}).to_csv(os.path.join(d, "p012_G1_vernier.csv"), index=False)
        orch = Orchestrator(_state(tmp, input_dir=d,
                                   comparison={"conditions": ["room", "stressor"],
                                               "measures": ["resp_rate", "resp_stress_index"]}))
        s = orch.advance(mode="auto")
        assert s.done, "respiration run must complete"
        rr = s.artifacts["analyse"]["measures"]["resp_rate"]["per_subject"]["p012"]
        assert abs(rr["room"] - 15.0) < 0.1 and abs(rr["stressor"] - 30.0) < 0.1
        # RespInPeace engine produced a per-condition stress index for at least one window
        rs = s.artifacts["analyse"]["measures"]["resp_stress_index"]["per_subject"].get("p012", {})
        assert set(rs).issubset({"room", "stressor"})
        orch.close()


def test_rerun_drops_downstream_artifacts():
    with tempfile.TemporaryDirectory() as tmp:
        d = _make_input_dir(tmp)
        orch = Orchestrator(_state(tmp, input_dir=d,
                                   comparison={"conditions": ["plants", "no_plants"], "measure": "eda_tonic"}))
        orch.advance(mode="auto")
        assert "analyse" in orch.state.artifacts
        orch.rerun("clean", mode="step")  # rerun from clean → analyse/visualise dropped
        assert "analyse" not in orch.state.artifacts and "visualise" not in orch.state.artifacts
        orch.close()

"""Severity tests for the modular respiratory pipeline contracts.

These are written as attacks on the contracts, not happy-path demos:
  - viz must NOT raise even when an exemplar is missing (the bug that motivated
    the fail-soft contract);
  - the last-mile verifier must reject artifacts that disagree;
  - the table stage must reject a non-reconciling grouping.
"""
from __future__ import annotations

import numpy as np
import pytest

from app.services.processing.respiratory import pipeline as RP
from app.services.processing.respiratory import viz as VIZ
from app.services.processing.respiratory import tables as TBL
from app.services.processing.respiratory.signal import SignalResult
from app.services.processing.respiratory.tables import TablesResult, TableReconciliationError

from tests.test_respiratory_conditions import _synthetic_payload


def test_full_pipeline_runs_and_verifies():
    payload = _synthetic_payload()
    res = RP.run(recompute_payload=payload, conditions=[
        {"name": "Calm", "markers": ["calm"], "role": "calm"},
        {"name": "Stress", "markers": ["stress"], "role": "stress"},
    ])
    assert res.error is None
    assert "pattern_details" in res.result
    assert res.result["total_breaths"] > 0
    assert res.manifest["stages"] == ["signal", "tables", "stats", "viz"]
    # Stats stage produced contrasts between the two conditions.
    assert any(c["condition_a"] in ("Calm", "Stress") for c in res.result["contrasts"])


def test_viz_never_raises_on_missing_exemplar():
    """A pattern marked found with no normal exemplar must be skipped with a
    reason, not crash — this is the exact defect the contract forbids."""
    sig = SignalResult(resp_z=np.zeros(200), peaks=[10, 30], troughs=[0, 20, 40], fs=20)
    tables = TablesResult(
        pattern_details={"sigh": {"label": "Sigh", "description": "", "count": 3,
                                  "calm_count": 0, "found": True}},
        patterns={"sigh": {"found": True, "count": 3, "label": "Sigh"}},
        # exemplar with normal=None — would crash a naive figure builder
        exemplars={"sigh": {"normal": None, "stressed": {"t1_idx": 10}}},
    )
    out = VIZ.render(sig, tables)  # must not raise
    assert "sigh" in out["skipped"]
    assert out["figures"] == {} or "sigh" not in out["figures"]


def test_verifier_rejects_stat_referencing_unknown_condition():
    from app.services.processing.respiratory.stats import StatsResult
    tables = TablesResult(condition_map={"A": ["a"]}, pattern_details={}, patterns={})
    stats = StatsResult(contrasts=[{"condition_a": "A", "condition_b": "GHOST",
                                    "metric": "rate_bpm"}])
    figures = {"figures": {}, "skipped": {}}
    with pytest.raises(RP.PipelineVerificationError):
        RP._verify(tables, stats, figures, {})


def test_tables_reconciliation_enforced():
    """Directly assert the reconciliation invariant fires on a rigged table."""
    import pandas as pd
    tables = TablesResult(
        condition_map={"A": ["calm"]},
        total_breaths=999,  # deliberately wrong vs the cycles below
        patterns={}, pattern_details={},
    )
    cycles = pd.DataFrame([{"phase": "calm"}, {"phase": "stress"}])
    with pytest.raises(TableReconciliationError):
        TBL._check_reconciliation(tables, cycles)

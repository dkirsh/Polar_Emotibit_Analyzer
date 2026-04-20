"""Benchmark utilities for agreement testing against reference outputs."""

from __future__ import annotations

import numpy as np

from app.schemas.analysis import BlandAltmanMetric


def bland_altman(metric: str, system_values: list[float], reference_values: list[float]) -> BlandAltmanMetric:
    """Compute Bland-Altman bias and limits of agreement for one metric."""
    if len(system_values) != len(reference_values):
        raise ValueError("system and reference vectors must have equal length")
    if len(system_values) < 2:
        raise ValueError("at least two paired samples are required")

    system = np.array(system_values, dtype=float)
    reference = np.array(reference_values, dtype=float)
    diffs = system - reference

    bias = float(np.mean(diffs))
    std = float(np.std(diffs, ddof=1))
    loa_lower = float(bias - 1.96 * std)
    loa_upper = float(bias + 1.96 * std)
    return BlandAltmanMetric(
        metric=metric,
        n_pairs=len(diffs),
        bias=bias,
        loa_lower=loa_lower,
        loa_upper=loa_upper,
    )


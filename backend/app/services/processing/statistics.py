"""Statistical analysis for physiological session data.

Version: 2.1 (repaired)
Changes from V2.0:
  - [Repair 1.1] CI uses t-distribution instead of z=1.96
  - [Repair 1.2] ddof=1 consistently (Bessel's correction)
  - [Repair 3.5] Benjamini-Hochberg FDR for multiple comparisons

DESIGN DECISION — ddof=1 throughout:
    All standard deviations use ddof=1 because session data is always a
    sample, never the complete population. Using ddof=0 systematically
    underestimates population variance. V2.0 inconsistently used ddof=0
    in _summary() but ddof=1 in _mean_ci95() — internally contradictory.
    Ref: Boos & Hughes-Oliver (2000). Am Stat, 54(2), 121-128.

DESIGN DECISION — t-distribution for CI:
    scipy.stats.t.ppf(0.975, df=n-1) instead of z=1.96. At n=10 the
    difference is 15.4% wider CI. Using z unconditionally overstates
    precision. For large n, t converges to z, so t is always correct.
    Ref: Cumming (2014). Psych Sci, 25(1), 7-29.

DESIGN DECISION — Benjamini-Hochberg FDR:
    Testing both HR and EDA trends inflates FWER to ~0.0975 for k=2 at
    alpha=0.05. BH controls FDR (more appropriate for exploratory analysis
    than Bonferroni FWER), has greater power under positive dependence
    (HR/EDA share sympathetic drive).
    Ref: Benjamini & Hochberg (1995). JRSS-B, 57(1), 289-300.
"""

from __future__ import annotations

import math
from typing import NamedTuple

import numpy as np
import pandas as pd
from scipy import stats as sp_stats


class SummaryResult(NamedTuple):
    mean: float
    std: float
    min_val: float
    max_val: float
    p05: float
    p95: float


def _summary(values: np.ndarray) -> SummaryResult:
    """Descriptive statistics. Uses ddof=1 (sample std)."""
    if len(values) == 0:
        return SummaryResult(0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    return SummaryResult(
        mean=float(np.mean(values)),
        # V2.1 FIX [1.2]: ddof=1 (was ddof=0 in V2.0)
        std=float(np.std(values, ddof=1)) if len(values) > 1 else 0.0,
        min_val=float(np.min(values)),
        max_val=float(np.max(values)),
        p05=float(np.percentile(values, 5)),
        p95=float(np.percentile(values, 95)),
    )


def compute_summary_stats(df: pd.DataFrame) -> dict[str, SummaryResult]:
    """Descriptive statistics for HR and EDA."""
    return {
        "hr_bpm": _summary(df["hr_bpm"].to_numpy(dtype=float)),
        "eda_us": _summary(df["eda_us"].to_numpy(dtype=float)),
    }


class MeanCI95Result(NamedTuple):
    mean: float
    lower: float
    upper: float


def _mean_ci95(values: np.ndarray) -> MeanCI95Result:
    """95% CI using t-distribution.

    V2.1 FIX [1.1]: t-distribution replaces z=1.96.

    Example (n=10, mean=70, std=5):
      z-margin: 1.960 * 5/sqrt(10) = 3.10  -> CI width 6.20
      t-margin: 2.262 * 5/sqrt(10) = 3.58  -> CI width 7.15
      z-CI is 13.3% too narrow (overstates precision)
    """
    n = len(values)
    if n < 2:
        m = float(values[0]) if n == 1 else 0.0
        return MeanCI95Result(mean=m, lower=m, upper=m)

    m = float(np.mean(values))
    s = float(np.std(values, ddof=1))
    se = s / math.sqrt(n)
    t_crit = float(sp_stats.t.ppf(0.975, df=n - 1))
    margin = t_crit * se
    return MeanCI95Result(mean=m, lower=m - margin, upper=m + margin)


def _cohens_d(pre: np.ndarray, post: np.ndarray) -> float:
    """Cohen's d (pooled SD, ddof=1)."""
    if len(pre) < 2 or len(post) < 2:
        return 0.0
    m1, m2 = float(np.mean(pre)), float(np.mean(post))
    s1, s2 = float(np.var(pre, ddof=1)), float(np.var(post, ddof=1))
    n1, n2 = len(pre), len(post)
    pooled_var = ((n1 - 1) * s1 + (n2 - 1) * s2) / (n1 + n2 - 2)
    pooled_sd = math.sqrt(pooled_var) if pooled_var > 0 else 1.0
    return (m2 - m1) / pooled_sd


def _trend_pvalue(values: np.ndarray) -> float:
    """P-value for linear trend via Pearson r.

    NOTE: Physiological time series have temporal autocorrelation, making
    this p-value anticonservative. Interpret as a liberal lower bound.
    """
    if len(values) < 3:
        return 1.0
    x = np.arange(len(values), dtype=float)
    _, p = sp_stats.pearsonr(x, values)
    return float(p)


def apply_fdr_correction(p_values: list[float]) -> list[float]:
    """Benjamini-Hochberg FDR correction. V2.1 NEW [3.5]."""
    n = len(p_values)
    if n <= 1:
        return list(p_values)
    indexed = sorted(enumerate(p_values), key=lambda x: x[1])
    adjusted = [0.0] * n
    for rank, (orig_idx, pval) in enumerate(indexed, 1):
        adjusted[orig_idx] = pval * n / rank
    for i in range(n - 2, -1, -1):
        orig_idx = indexed[i][0]
        next_orig_idx = indexed[i + 1][0]
        adjusted[orig_idx] = min(adjusted[orig_idx], adjusted[next_orig_idx])
    return [min(p, 1.0) for p in adjusted]


def compute_inference_summary(df: pd.DataFrame, *, n_windows: int = 4) -> dict:
    """Inferential statistics for within-session analysis."""
    hr = df["hr_bpm"].to_numpy(dtype=float)
    eda = df["eda_us"].to_numpy(dtype=float)

    hr_ci, eda_ci = _mean_ci95(hr), _mean_ci95(eda)
    mid = len(hr) // 2
    hr_d = _cohens_d(hr[:mid], hr[mid:]) if mid >= 2 else 0.0
    eda_d = _cohens_d(eda[:mid], eda[mid:]) if mid >= 2 else 0.0
    hr_p_raw, eda_p_raw = _trend_pvalue(hr), _trend_pvalue(eda)

    # V2.1 [3.5]: FDR correction
    adjusted = apply_fdr_correction([hr_p_raw, eda_p_raw])

    return {
        "hr_mean_ci95": {"mean": hr_ci.mean, "lower": hr_ci.lower, "upper": hr_ci.upper},
        "eda_mean_ci95": {"mean": eda_ci.mean, "lower": eda_ci.lower, "upper": eda_ci.upper},
        "hr_change_effect_size_d": round(hr_d, 4),
        "eda_change_effect_size_d": round(eda_d, 4),
        "repeated_measures_windows": n_windows,
        "hr_trend_pvalue": round(adjusted[0], 6),
        "eda_trend_pvalue": round(adjusted[1], 6),
        "hr_trend_pvalue_raw": round(hr_p_raw, 6),
        "eda_trend_pvalue_raw": round(eda_p_raw, 6),
    }

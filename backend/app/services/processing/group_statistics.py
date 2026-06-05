"""Group-level repeated-measures and blocked-model statistics.

The purpose is modest and specific: for the Latin-square room bundle,
distinguish condition effects from visit-order effects while respecting
within-subject dependence.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats as sp_stats


@dataclass(frozen=True)
class MetricSpec:
    key: str
    label: str
    digits: int


NORMALIZED_METRICS: tuple[MetricSpec, ...] = (
    MetricSpec("mean_hr_delta_bpm", "HR delta from baseline", 1),
    MetricSpec("mean_hr_pct_change", "HR percent change from baseline", 2),
    MetricSpec("mean_eda_delta_us", "EDA tonic delta from baseline", 3),
    MetricSpec("eda_phasic_delta", "EDA phasic delta from baseline", 4),
    MetricSpec("ln_rmssd_delta", "log RMSSD delta from baseline", 4),
)


def _summary(values: pd.Series) -> dict[str, Any]:
    clean = pd.to_numeric(values, errors="coerce").dropna()
    if clean.empty:
        return {"n": 0, "mean": None, "sd": None, "min": None, "max": None}
    arr = clean.to_numpy(dtype=float)
    return {
        "n": int(len(arr)),
        "mean": float(arr.mean()),
        "sd": float(arr.std(ddof=1)) if len(arr) > 1 else 0.0,
        "min": float(arr.min()),
        "max": float(arr.max()),
    }


def _friedman_complete_case(
    df: pd.DataFrame,
    *,
    value_col: str,
    factor_col: str,
    subject_col: str = "subject_id",
) -> dict[str, Any] | None:
    subset = df[[subject_col, factor_col, value_col]].copy()
    subset[value_col] = pd.to_numeric(subset[value_col], errors="coerce")
    subset[factor_col] = subset[factor_col].astype(str)
    subset = subset.dropna()
    if subset.empty:
        return None
    levels = sorted(str(v) for v in subset[factor_col].unique())
    pivot = subset.pivot_table(index=subject_col, columns=factor_col, values=value_col, aggfunc="first")
    pivot = pivot.reindex(columns=levels).dropna()
    if len(pivot) < 3 or len(levels) < 2:
        return None
    stat, p = sp_stats.friedmanchisquare(*[pivot[level].to_numpy(dtype=float) for level in levels])
    return {
        "levels": levels,
        "n_subjects_complete": int(len(pivot)),
        "statistic": float(stat),
        "p": float(p),
    }


def _holm_adjust(p_values: list[float]) -> list[float]:
    indexed = sorted(enumerate(p_values), key=lambda row: row[1])
    m = len(indexed)
    adjusted = [1.0] * m
    running = 0.0
    for i, (orig_idx, p) in enumerate(indexed):
        val = min(1.0, (m - i) * p)
        running = max(running, val)
        adjusted[orig_idx] = running
    return adjusted


def _pairwise_wilcoxon(
    df: pd.DataFrame,
    *,
    value_col: str,
    factor_col: str,
    subject_col: str = "subject_id",
) -> list[dict[str, Any]]:
    subset = df[[subject_col, factor_col, value_col]].copy()
    subset[value_col] = pd.to_numeric(subset[value_col], errors="coerce")
    subset[factor_col] = subset[factor_col].astype(str)
    subset = subset.dropna()
    if subset.empty:
        return []
    levels = sorted(str(v) for v in subset[factor_col].unique())
    pivot = subset.pivot_table(index=subject_col, columns=factor_col, values=value_col, aggfunc="first")
    pairs: list[tuple[str, str, float, float, int, float]] = []
    raw_ps: list[float] = []
    for i, left in enumerate(levels):
        for right in levels[i + 1 :]:
            pair = pivot[[left, right]].dropna()
            if len(pair) < 3:
                continue
            x = pair[left].to_numpy(dtype=float)
            y = pair[right].to_numpy(dtype=float)
            try:
                stat, p = sp_stats.wilcoxon(x, y, zero_method="wilcox", alternative="two-sided", method="auto")
            except ValueError:
                continue
            mean_diff = float(np.mean(y - x))
            pairs.append((left, right, float(stat), float(p), int(len(pair)), mean_diff))
            raw_ps.append(float(p))
    if not pairs:
        return []
    holm = _holm_adjust(raw_ps)
    out: list[dict[str, Any]] = []
    for (left, right, stat, p, n, mean_diff), p_holm in zip(pairs, holm):
        out.append(
            {
                "left": left,
                "right": right,
                "n": n,
                "mean_diff": mean_diff,
                "statistic": stat,
                "p_raw": p,
                "p_holm": float(p_holm),
            }
        )
    return out


def _design_matrix(df: pd.DataFrame, columns: list[str]) -> np.ndarray:
    pieces = [np.ones((len(df), 1), dtype=float)]
    for col in columns:
        series = df[col]
        if pd.api.types.is_numeric_dtype(series):
            values = pd.to_numeric(series, errors="coerce").to_numpy(dtype=float).reshape(-1, 1)
            pieces.append(values)
        else:
            dummies = pd.get_dummies(series.astype(str), drop_first=True, dtype=float)
            if not dummies.empty:
                pieces.append(dummies.to_numpy(dtype=float))
    return np.concatenate(pieces, axis=1)


def _fit_rss(y: np.ndarray, x: np.ndarray) -> tuple[float, int]:
    beta, residuals, rank, _ = np.linalg.lstsq(x, y, rcond=None)
    if residuals.size > 0:
        rss = float(residuals[0])
    else:
        fitted = x @ beta
        rss = float(np.sum((y - fitted) ** 2))
    return rss, int(rank)


def _partial_f_test(y: np.ndarray, x_reduced: np.ndarray, x_full: np.ndarray) -> dict[str, Any] | None:
    rss_r, rank_r = _fit_rss(y, x_reduced)
    rss_f, rank_f = _fit_rss(y, x_full)
    df_num = rank_f - rank_r
    df_den = len(y) - rank_f
    if df_num <= 0 or df_den <= 0:
        return None
    improvement = max(0.0, rss_r - rss_f)
    ms_num = improvement / df_num
    ms_den = rss_f / df_den if rss_f > 0 else 0.0
    if ms_den <= 0:
        return None
    f_stat = ms_num / ms_den
    p = float(sp_stats.f.sf(f_stat, df_num, df_den))
    return {
        "df_num": int(df_num),
        "df_den": int(df_den),
        "rss_reduced": float(rss_r),
        "rss_full": float(rss_f),
        "f_statistic": float(f_stat),
        "p": p,
    }


def _blocked_model(
    df: pd.DataFrame,
    *,
    value_col: str,
    subject_col: str = "subject_id",
    visit_col: str = "visit_number",
    condition_col: str = "room_type",
) -> dict[str, Any] | None:
    subset = df[[subject_col, visit_col, condition_col, value_col]].copy()
    subset[value_col] = pd.to_numeric(subset[value_col], errors="coerce")
    subset = subset.dropna()
    if len(subset) < 12:
        return None
    y = subset[value_col].to_numpy(dtype=float)
    x_subject = _design_matrix(subset, [subject_col])
    x_subject_visit = _design_matrix(subset, [subject_col, visit_col])
    x_subject_condition = _design_matrix(subset, [subject_col, condition_col])
    x_full = _design_matrix(subset, [subject_col, visit_col, condition_col])
    return {
        "n_rows": int(len(subset)),
        "visit_given_subject": _partial_f_test(y, x_subject, x_subject_visit),
        "condition_given_subject": _partial_f_test(y, x_subject, x_subject_condition),
        "condition_given_subject_and_visit": _partial_f_test(y, x_subject_visit, x_full),
        "visit_given_subject_and_condition": _partial_f_test(y, x_subject_condition, x_full),
    }


def build_condition_aggregate_inference(rows: list[dict[str, Any]]) -> dict[str, Any]:
    df = pd.DataFrame(rows)
    metrics: list[dict[str, Any]] = []
    visit_summaries: dict[str, list[dict[str, Any]]] = {}
    for spec in NORMALIZED_METRICS:
        if spec.key not in df.columns:
            continue
        by_condition = _friedman_complete_case(df, value_col=spec.key, factor_col="room_type")
        by_visit = _friedman_complete_case(df, value_col=spec.key, factor_col="visit_number")
        pairwise_condition = _pairwise_wilcoxon(df, value_col=spec.key, factor_col="room_type") if by_condition else []
        pairwise_visit = _pairwise_wilcoxon(df, value_col=spec.key, factor_col="visit_number") if by_visit else []
        blocked = _blocked_model(df, value_col=spec.key)
        visit_summary_rows: list[dict[str, Any]] = []
        if "visit_number" in df.columns:
            for visit in sorted(v for v in df["visit_number"].dropna().unique()):
                visit_df = df[df["visit_number"] == visit]
                summary = _summary(visit_df[spec.key])
                visit_summary_rows.append({"visit_number": int(visit), **summary})
        visit_summaries[spec.key] = visit_summary_rows
        metrics.append(
            {
                "key": spec.key,
                "label": spec.label,
                "digits": spec.digits,
                "condition_friedman": by_condition,
                "condition_pairwise_holm": pairwise_condition,
                "visit_friedman": by_visit,
                "visit_pairwise_holm": pairwise_visit,
                "blocked_model": blocked,
            }
        )
    return {"normalized_metrics": metrics, "visit_summaries": visit_summaries}

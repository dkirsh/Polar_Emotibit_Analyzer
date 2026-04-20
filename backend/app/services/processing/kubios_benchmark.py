"""Helpers to benchmark system outputs against Kubios exports."""

from __future__ import annotations

from dataclasses import dataclass
import math

import pandas as pd

from app.schemas.analysis import BlandAltmanMetric
from app.services.processing.benchmark import bland_altman


@dataclass(frozen=True)
class KubiosNormalized:
    """Normalized metric table for Kubios/system agreement."""

    join_col: str
    frame: pd.DataFrame


def _to_numeric(series: pd.Series) -> pd.Series:
    """Convert numeric-like values including decimal comma."""
    as_text = series.astype(str).str.strip().str.replace(",", ".", regex=False)
    return pd.to_numeric(as_text, errors="coerce")


def normalize_kubios_export(kubios_df: pd.DataFrame, join_col: str) -> KubiosNormalized:
    """Normalize Kubios column names to system metric names."""
    if join_col not in kubios_df.columns:
        raise ValueError(f"Kubios file missing join column: {join_col}")

    candidates: dict[str, list[str]] = {
        "rmssd_ms": ["RMSSD", "RMSSD (ms)", "rmssd", "rmssd_ms"],
        "sdnn_ms": ["SDNN", "SDNN (ms)", "sdnn", "sdnn_ms"],
        "mean_hr_bpm": ["Mean HR", "Mean HR (beats/min)", "mean_hr_bpm", "HR mean"],
    }

    out = pd.DataFrame({join_col: kubios_df[join_col]})
    for target, aliases in candidates.items():
        selected = next((col for col in aliases if col in kubios_df.columns), None)
        if selected is None:
            raise ValueError(f"Kubios file missing metric column for {target}; tried {aliases}")
        out[target] = _to_numeric(kubios_df[selected])

    out = out.dropna(subset=["rmssd_ms", "sdnn_ms", "mean_hr_bpm"])
    return KubiosNormalized(join_col=join_col, frame=out)


def normalize_system_metrics(system_df: pd.DataFrame, join_col: str) -> pd.DataFrame:
    """Validate and coerce system metric CSV format."""
    required = {join_col, "rmssd_ms", "sdnn_ms", "mean_hr_bpm"}
    missing = sorted(required.difference(set(system_df.columns)))
    if missing:
        raise ValueError(f"System file missing required columns: {missing}")

    out = system_df[[join_col, "rmssd_ms", "sdnn_ms", "mean_hr_bpm"]].copy()
    out["rmssd_ms"] = pd.to_numeric(out["rmssd_ms"], errors="coerce")
    out["sdnn_ms"] = pd.to_numeric(out["sdnn_ms"], errors="coerce")
    out["mean_hr_bpm"] = pd.to_numeric(out["mean_hr_bpm"], errors="coerce")
    return out.dropna(subset=["rmssd_ms", "sdnn_ms", "mean_hr_bpm"])


def compare_with_kubios(system_df: pd.DataFrame, kubios_df: pd.DataFrame, join_col: str) -> list[BlandAltmanMetric]:
    """Return Bland-Altman comparisons for core HRV metrics."""
    system_norm = normalize_system_metrics(system_df, join_col=join_col)
    kubios_norm = normalize_kubios_export(kubios_df, join_col=join_col).frame

    merged = system_norm.merge(kubios_norm, on=join_col, suffixes=("_system", "_kubios"))
    if len(merged) < 2:
        raise ValueError("Need at least two matched rows between system and Kubios files")

    return [
        bland_altman(
            "rmssd_ms",
            merged["rmssd_ms_system"].astype(float).tolist(),
            merged["rmssd_ms_kubios"].astype(float).tolist(),
        ),
        bland_altman(
            "sdnn_ms",
            merged["sdnn_ms_system"].astype(float).tolist(),
            merged["sdnn_ms_kubios"].astype(float).tolist(),
        ),
        bland_altman(
            "mean_hr_bpm",
            merged["mean_hr_bpm_system"].astype(float).tolist(),
            merged["mean_hr_bpm_kubios"].astype(float).tolist(),
        ),
    ]


def evaluate_agreement(
    comparisons: list[BlandAltmanMetric],
    max_abs_bias: dict[str, float],
    max_loa_width: dict[str, float],
) -> list[dict[str, float | bool | str]]:
    """Evaluate each metric against configured acceptance thresholds."""
    checks: list[dict[str, float | bool | str]] = []
    for comp in comparisons:
        bias_limit = float(max_abs_bias.get(comp.metric, math.inf))
        loa_limit = float(max_loa_width.get(comp.metric, math.inf))
        abs_bias = abs(comp.bias)
        loa_width = comp.loa_upper - comp.loa_lower
        passed = abs_bias <= bias_limit and loa_width <= loa_limit
        checks.append(
            {
                "metric": comp.metric,
                "abs_bias": abs_bias,
                "loa_width": loa_width,
                "max_abs_bias": bias_limit,
                "max_loa_width": loa_limit,
                "pass": passed,
            }
        )
    return checks

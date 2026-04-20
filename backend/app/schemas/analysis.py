"""Schemas for ingestion and analysis endpoints."""

from pydantic import BaseModel, Field


class IngestionSummary(BaseModel):
    """Result of parsing raw files."""

    emotibit_rows: int
    polar_rows: int
    emotibit_start_ms: int
    emotibit_end_ms: int
    polar_start_ms: int
    polar_end_ms: int
    polar_has_native_rr: bool = False


class AnalysisRequest(BaseModel):
    """Run analysis on pre-parsed records payload."""

    emotibit: list[dict[str, float | int | str]]
    polar: list[dict[str, float | int | str]]


class FeatureSummary(BaseModel):
    """Feature set emitted by the processing pipeline."""

    rmssd_ms: float
    sdnn_ms: float
    mean_hr_bpm: float
    eda_mean_us: float
    eda_phasic_index: float
    stress_score: float = Field(ge=0.0, le=1.0)
    rr_source: str = "derived_from_bpm"

    # Frequency-domain HRV (available when native RR intervals are present)
    vlf_ms2: float | None = None
    lf_ms2: float | None = None
    hf_ms2: float | None = None
    lf_hf_ratio: float | None = None


class AnalysisResponse(BaseModel):
    """Top-level analysis response."""

    synchronized_samples: int
    drift_slope: float
    drift_intercept_ms: float
    drift_segments: int = 1
    xcorr_offset_ms: float = 0.0
    feature_summary: FeatureSummary
    quality_flags: list[str]
    movement_artifact_ratio: float = Field(ge=0.0, le=1.0)
    report_markdown: str
    non_diagnostic_notice: str

    # V2.1 NEW [Repair 1.4]: Sync quality gate fields
    sync_qc_score: float = 0.0
    sync_qc_band: str = "unknown"
    sync_qc_gate: str = "unknown"
    sync_qc_failure_reasons: list[str] = []


class SummaryStats(BaseModel):
    """Descriptive statistics for one physiological channel."""

    mean: float
    std: float
    min: float
    max: float
    p05: float
    p95: float


class MeanCI95(BaseModel):
    """95% confidence interval for a channel mean."""

    mean: float
    lower: float
    upper: float


class InferenceSummary(BaseModel):
    """Inferential statistics for within-session trend and shift."""

    hr_mean_ci95: MeanCI95
    eda_mean_ci95: MeanCI95
    hr_change_effect_size_d: float
    eda_change_effect_size_d: float
    repeated_measures_windows: int
    hr_trend_pvalue: float = Field(ge=0.0, le=1.0)
    eda_trend_pvalue: float = Field(ge=0.0, le=1.0)


class RespiratorySummary(BaseModel):
    """Respiratory feature bundle from direct sensor or proxy estimate."""

    source: str
    respiratory_rate_bpm_mean: float | None
    respiratory_rate_bpm_std: float | None
    rsa_proxy_bpm: float | None
    hr_resp_coupling: float | None


class BlandAltmanMetric(BaseModel):
    """Agreement statistics for one metric."""

    metric: str
    n_pairs: int
    bias: float
    loa_lower: float
    loa_upper: float


class BenchmarkSummaryResponse(BaseModel):
    """Reference-comparison summary for benchmark studies."""

    comparisons: list[BlandAltmanMetric]
    note: str
    non_diagnostic_notice: str

    # V2.1 NEW [Repair 1.4]: Sync quality gate fields
    sync_qc_score: float = 0.0
    sync_qc_band: str = "unknown"
    sync_qc_gate: str = "unknown"
    sync_qc_failure_reasons: list[str] = []


class StatisticalSummaryResponse(BaseModel):
    """Statistical output for downstream analysis and visualization."""

    n_samples: int
    hr_bpm: SummaryStats
    eda_us: SummaryStats
    hr_eda_corr: float
    stress_trend_slope_per_min: float
    respiratory_proxy_hz: float | None
    respiratory: RespiratorySummary
    inference: InferenceSummary
    movement_artifact_ratio: float = Field(ge=0.0, le=1.0)
    non_diagnostic_notice: str

    # V2.1 NEW [Repair 1.4]: Sync quality gate fields
    sync_qc_score: float = 0.0
    sync_qc_band: str = "unknown"
    sync_qc_gate: str = "unknown"
    sync_qc_failure_reasons: list[str] = []


class StatisticalTimelinePoint(BaseModel):
    """One time-aligned point for statistical visualization."""

    timestamp_ms: int
    hr_bpm: float
    eda_us: float
    stress_proxy: float
    resp_bpm: float | None = None


class StatisticalTimelineResponse(BaseModel):
    """Timeline payload for linked small-multiple visualization."""

    points: list[StatisticalTimelinePoint]
    available_channels: list[str]
    movement_artifact_ratio: float = Field(ge=0.0, le=1.0)
    non_diagnostic_notice: str

    # V2.1 NEW [Repair 1.4]: Sync quality gate fields
    sync_qc_score: float = 0.0
    sync_qc_band: str = "unknown"
    sync_qc_gate: str = "unknown"
    sync_qc_failure_reasons: list[str] = []

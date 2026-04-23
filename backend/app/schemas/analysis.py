"""Schemas for ingestion and analysis endpoints."""

from typing import Any

from pydantic import BaseModel, Field


# F3 fix 2026-04-21: response models for the seven endpoints that
# previously returned untyped dict[str, Any]. Every endpoint now has
# an OpenAPI schema, which enables client-side type generation and
# catches response-shape drift at test time.


class HealthResponse(BaseModel):
    """Liveness probe response from GET /health."""

    ok: bool
    version: str
    scope: str


class SessionSummary(BaseModel):
    """Slim session row for the recent-sessions list."""

    session_id: str
    subject_id: str
    session_date: str
    analyzed_at: str
    sync_qc_gate: str | None = None
    sync_qc_score: float | None = None


class SessionDetail(BaseModel):
    """Full session record stored in the in-memory session store.

    The `result` field carries the full AnalysisResponse-shaped dict
    that the analyze endpoint emitted; kept as dict[str, Any] here
    because the session store dates from before AnalysisResponse was
    a first-class schema and migrating every write site is Phase 3
    polish, not P1 work.
    """

    session_id: str
    subject_id: str
    study_id: str
    session_date: str
    analyzed_at: str
    operator: str | None = None
    notes: str | None = None
    markers_summary: dict[str, Any] | None = None
    result: dict[str, Any]


class CsvTimestampRange(BaseModel):
    """Timestamp extent of an uploaded CSV."""

    min: int
    max: int
    span_s: int


class CsvValidationResponse(BaseModel):
    """Response for the three /validate/csv/* endpoints.

    The three endpoints share most fields. Optional fields carry
    per-source information (accelerometer/respiration for EmotiBit;
    native RR presence for Polar; event-code inventory for markers)
    and are None on the other sources.
    """

    valid: bool
    filename: str | None = None
    n_rows: int | None = None
    columns_present: list[str] = Field(default_factory=list)
    timestamp_range_ms: CsvTimestampRange | None = None

    # EmotiBit-specific
    has_accelerometer: bool | None = None
    has_respiration: bool | None = None

    # Polar-specific
    has_native_rr: bool | None = None
    has_raw_ecg: bool | None = None
    rr_source: str | None = None         # "native_polar" | "derived_from_ecg" | "derived_from_bpm"
    rr_source_note: str | None = None    # human-readable summary of the choice

    # Markers-specific
    event_codes: list[str] | None = None
    n_events: int | None = None


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

    # 2026-04-21 Kubios-parity extensions ----------------------------------
    # Task Force (1996) time-domain additions
    nn50: int | None = None
    pnn50: float | None = None

    # Brennan et al. (2001) Poincaré nonlinear descriptors
    sd1_ms: float | None = None
    sd2_ms: float | None = None
    sd1_sd2_ratio: float | None = None
    ellipse_area_ms2: float | None = None

    # Task Force (1996) frequency-domain normalised units + percentages
    total_power_ms2: float | None = None
    lf_nu: float | None = None
    hf_nu: float | None = None
    vlf_pct: float | None = None
    lf_pct: float | None = None
    hf_pct: float | None = None

    # Second-generation stress composite using Kubios-grade inputs.
    # See app/services/processing/stress.py::compute_stress_score_v2 for
    # the rationale, citations, and channel weights. Still experimental,
    # still not validated — use for within-session relative comparison
    # alongside v1.
    stress_score_v2: float | None = None
    stress_v2_contributions: dict[str, float | None] | None = None


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

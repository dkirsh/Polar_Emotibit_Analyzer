// Typed fetch wrappers for the Polar-EmotiBit Analyzer backend.
// All routes are proxied through Vite's dev server (/api/* → :8000).

export type FeatureSummary = {
  rmssd_ms: number;
  sdnn_ms: number;
  mean_hr_bpm: number;
  eda_mean_us: number;
  eda_phasic_index: number;
  stress_score: number;
  rr_source: "native_polar" | "derived_from_ecg" | "derived_from_bpm" | "none";
  rr_source_note?: string | null;
  vlf_ms2: number | null;
  lf_ms2: number | null;
  hf_ms2: number | null;
  lf_hf_ratio: number | null;

  // 2026-04-21 Kubios-parity additions. All optional so legacy
  // AnalysisResponse payloads continue to roundtrip cleanly.
  nn50?: number | null;
  pnn50?: number | null;
  sd1_ms?: number | null;
  sd2_ms?: number | null;
  sd1_sd2_ratio?: number | null;
  ellipse_area_ms2?: number | null;
  total_power_ms2?: number | null;
  lf_nu?: number | null;
  hf_nu?: number | null;
  vlf_pct?: number | null;
  lf_pct?: number | null;
  hf_pct?: number | null;
  stress_score_v2?: number | null;
  stress_v2_contributions?: Record<string, number | null> | null;
};

// Report-export formats (GET /api/v1/sessions/{id}/export?format=...)
export type ExportFormat = "csv" | "xlsx" | "mat" | "pdf";

/** URL for downloading a stored session in one of the four formats. */
export function sessionExportUrl(sessionId: string, format: ExportFormat): string {
  return `/api/v1/sessions/${encodeURIComponent(sessionId)}/export?format=${format}`;
}

export type AnalysisResponse = {
  synchronized_samples: number;
  drift_slope: number;
  drift_intercept_ms: number;
  drift_segments: number;
  xcorr_offset_ms: number;
  feature_summary: FeatureSummary;
  quality_flags: string[];
  movement_artifact_ratio: number;
  report_markdown: string;
  non_diagnostic_notice: string;
  sync_qc_score: number;
  sync_qc_band: "green" | "yellow" | "red" | "unknown";
  sync_qc_gate: "go" | "conditional_go" | "no_go" | "single_file" | "unknown";
  sync_qc_failure_reasons: string[];
};

export type ValidateEmotibitResponse = {
  valid: true;
  filename: string;
  n_rows: number;
  columns_present: string[];
  has_accelerometer: boolean;
  has_respiration: boolean;
  timestamp_range_ms: { min: number; max: number; span_s: number };
};

export type ValidatePolarResponse = {
  valid: true;
  filename: string;
  n_rows: number;
  columns_present: string[];
  has_native_rr: boolean;
  has_raw_ecg?: boolean;
  rr_source: "native_polar" | "derived_from_ecg" | "derived_from_bpm";
  rr_source_note: string;
  timestamp_range_ms: { min: number; max: number; span_s: number };
};

export type ValidateMarkersResponse = {
  valid: true;
  filename: string;
  n_rows: number;
  columns_present: string[];
  timestamp_range_ms?: { min: number; max: number; span_s: number } | null;
  event_codes: string[] | null;
  n_events: number | null;
};

export type RecentSession = {
  session_id: string;
  subject_id: string;
  session_date: string;
  analyzed_at: string;
  sync_qc_gate: "go" | "conditional_go" | "no_go" | "single_file" | "unknown";
  sync_qc_score: number;
};

export type StressDecomposition = {
  total: number;
  dominant_driver: string;
  components: Array<{ name: string; component: number; contribution: number; weight: number }>;
};

export type WindowedFeatures = {
  t_s: number[];
  hr_mean: number[];
  hr_std: number[];
  eda_mean: number[];
  rmssd: number[];
  stress: number[];
  stress_v2?: number[];
  arousal_index?: Array<number | null>;
  arousal_baseline?: number | null;
  hr_contribution: number[];
  eda_contribution: number[];
  hrv_contribution: number[];
  mean_rpm: Array<number | null>;
  rsa_amplitude: Array<number | null>;
  rsa_contribution: number[];
  v2_hr_contribution?: number[];
  v2_eda_contribution?: number[];
  v2_phasic_contribution?: number[];
  v2_vagal_contribution?: number[];
  v2_sympathovagal_contribution?: Array<number | null>;
  v2_rigidity_contribution?: Array<number | null>;
  v2_rsa_contribution?: Array<number | null>;
};

export type SpectralTrajectory = {
  t_s: number[];
  lf_power: Array<number | null>;
  hf_power: Array<number | null>;
  lf_hf_ratio: Array<number | null>;
};

export type PsdData = {
  frequencies_hz: number[];
  psd_ms2_hz: number[];
  rr_source: string;
  bands: Record<string, { lo: number; hi: number; color: string; label: string }>;
};

export type DescriptiveStats = {
  hr_bpm: { mean: number; std: number; min: number; max: number; p05: number; p95: number };
  eda_us: { mean: number; std: number; min: number; max: number; p05: number; p95: number };
};

export type InferenceStats = {
  hr_mean_ci95: { mean: number; lower: number; upper: number };
  eda_mean_ci95: { mean: number; lower: number; upper: number };
  hr_change_effect_size_d: number;
  eda_change_effect_size_d: number;
  repeated_measures_windows: number;
  hr_trend_pvalue: number;
  eda_trend_pvalue: number;
  hr_trend_pvalue_raw: number;
  eda_trend_pvalue_raw: number;
};

export type ExtendedAnalytics = {
  analysis_mode?: "paired" | "polar_only" | "emotibit_only";
  stress_decomposition: StressDecomposition | null;
  windowed: WindowedFeatures | null;
  spectral_trajectory: SpectralTrajectory | null;
  edr_proxy?: {
    source?: string | null;
    rr_source?: "native_polar" | "derived_from_ecg" | "derived_from_bpm" | "none" | string | null;
    rr_source_note?: string | null;
    time_s: number[];
    signal: number[];
    peak_times_s: number[];
    trough_times_s: number[];
    breath_intervals_s: number[];
    inspiratory_times_s: number[];
    expiratory_times_s: number[];
    mean_rpm?: number | null;
    rpm_std?: number | null;
    rsa_amplitude?: number | null;
    quality?: {
      duration_s?: number | null;
      peak_count: number;
      trough_count: number;
      usable_breath_count: number;
      paired_cycle_fraction?: number | null;
      interval_cv?: number | null;
      plausible_rate_fraction?: number | null;
      signal_confidence?: number | null;
      source_confidence?: number | null;
      overall_confidence?: number | null;
      verdict?: string | null;
    } | null;
  } | null;
  psd: PsdData;
  rr_series_ms: number[];
  descriptive_stats: DescriptiveStats;
  inference: InferenceStats | null;
  cleaned_timeseries: Array<{
    timestamp_ms?: number;
    hr_bpm?: number;
    eda_us?: number;
    acc_x?: number;
    acc_y?: number;
    acc_z?: number;
  }>;
  motion_artifact_ratio: number;
};

export type StoredSession = {
  analysis_id: string;
  session_id: string;
  subject_id: string;
  study_id: string;
  session_date: string;
  operator?: string;
  notes?: string;
  analyzed_at: string;
  markers_summary?: {
    n_rows?: number;
    codes?: string[];
    event_markers?: Array<{ event_code: string; utc_ms: number; note?: string }>;
    error?: string;
  } | null;
  result: AnalysisResponse;
  extended: ExtendedAnalytics | null;
};

type ValidateResponse =
  | ValidateEmotibitResponse
  | ValidatePolarResponse
  | ValidateMarkersResponse;

async function readError(r: Response): Promise<string> {
  const err = await r.json().catch(() => ({ detail: r.statusText }));
  if (typeof err.detail === "string") return err.detail;
  if (err.detail?.reason) return err.detail.reason;
  if (err.detail?.message) return err.detail.message;
  return JSON.stringify(err.detail ?? err);
}

async function postFile<T>(path: string, file: File): Promise<T> {
  const body = new FormData();
  body.append("file", file);
  const r = await fetch(path, { method: "POST", body });
  if (!r.ok) {
    throw new Error(await readError(r));
  }
  return (await r.json()) as T;
}

export async function validateEmotibitCsv(file: File) {
  return postFile<ValidateEmotibitResponse>("/api/v1/validate/csv/emotibit", file);
}
export async function validatePolarCsv(file: File) {
  return postFile<ValidatePolarResponse>("/api/v1/validate/csv/polar", file);
}
export async function validateMarkersCsv(file: File) {
  return postFile<ValidateMarkersResponse>("/api/v1/validate/csv/markers", file);
}

export type AnalyzePayload = {
  emotibit_file: File;
  polar_file: File;
  markers_file?: File | null;
  session_id: string;
  subject_id: string;
  study_id: string;
  session_date: string;
  operator?: string;
  notes?: string;
};

export type AnalyzeSinglePayload = {
  file: File;
  source_type: "polar" | "emotibit";
  session_id: string;
  subject_id: string;
  study_id: string;
  session_date: string;
  operator?: string;
  notes?: string;
};

export async function analyze(payload: AnalyzePayload): Promise<AnalysisResponse> {
  const body = new FormData();
  body.append("emotibit_file", payload.emotibit_file);
  body.append("polar_file", payload.polar_file);
  if (payload.markers_file) body.append("markers_file", payload.markers_file);
  body.append("session_id", payload.session_id);
  body.append("subject_id", payload.subject_id);
  body.append("study_id", payload.study_id);
  body.append("session_date", payload.session_date);
  if (payload.operator) body.append("operator", payload.operator);
  if (payload.notes) body.append("notes", payload.notes);
  const r = await fetch("/api/v1/analyze", { method: "POST", body });
  if (!r.ok) {
    throw new Error(await readError(r));
  }
  return (await r.json()) as AnalysisResponse;
}

export async function analyzeSingle(payload: AnalyzeSinglePayload): Promise<AnalysisResponse> {
  const body = new FormData();
  body.append("file", payload.file);
  body.append("source_type", payload.source_type);
  body.append("session_id", payload.session_id);
  body.append("subject_id", payload.subject_id);
  body.append("study_id", payload.study_id);
  body.append("session_date", payload.session_date);
  if (payload.operator) body.append("operator", payload.operator);
  if (payload.notes) body.append("notes", payload.notes);
  const r = await fetch("/api/v1/analyze/single", { method: "POST", body });
  if (!r.ok) {
    throw new Error(await readError(r));
  }
  return (await r.json()) as AnalysisResponse;
}

export async function listRecentSessions(limit = 10): Promise<RecentSession[]> {
  const r = await fetch(`/api/v1/sessions?limit=${limit}`);
  if (!r.ok) return [];
  return (await r.json()) as RecentSession[];
}

export async function getSession(sessionId: string): Promise<StoredSession> {
  const r = await fetch(`/api/v1/sessions/${encodeURIComponent(sessionId)}`);
  if (!r.ok) {
    const detail = await readError(r);
    throw new Error(
      `No completed analysis found for session "${sessionId}". ${detail}`,
    );
  }
  return (await r.json()) as StoredSession;
}

// Re-export to avoid unused-import warnings when consumers only need one.
export type { ValidateResponse };

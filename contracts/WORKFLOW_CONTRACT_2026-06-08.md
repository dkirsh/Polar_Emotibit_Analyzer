# Contract — Analysis workflow (six-stage orchestrator + canonical store)

Modules: `backend/app/services/workflow/` (`state`, `canonical_store`, `stages`,
`orchestrator`). Design: `docs/ANALYZER_WIZARD_ARCHITECTURE_2026-06-08.md`.

## Stages
`connect → canonicalise → clean → define → analyse → visualise`. Each stage is a
function `(WorkflowState, CanonicalStore) → StageResult`. A stage returns:
- `ok` with its outputs, a `qc` summary, and the `decisions` it auto-resolved
  (each with the chosen default and the alternatives), **or**
- `needs_input` with a non-empty `pending` list (a genuine ambiguity), **or**
- `failed` / `skipped`.

## Orchestration invariants
- **Auto runs to completion or to the first real pause.** `advance(mode="auto")`
  executes stages in order and returns only when a stage is `needs_input`/`failed`
  or a stage is pinned in `pause_before`. It never blocks on a decision a stage
  resolved by default.
- **Step advances exactly one stage.**
- **Auditability.** Every auto-resolved decision is appended to `state.manifest`
  with `resolved_by="default"`; user choices via `resolve()` are appended with
  `resolved_by="user"`. The manifest is the record of *what was assumed*.
- **Resumability.** `WorkflowState` is fully serialisable; a run resumes from
  `state.current` after reload.
- **Supersession.** `rerun(stage)` drops that stage's and all downstream
  artifacts/status before re-running (no stale results survive).

## Canonical store invariants
- One SQLite file; all sample timestamps and event bounds are UTC milliseconds.
- Every condition/marker is stored as an explicit `(label, onset_ms, offset_ms)`
  window regardless of source convention (onset/offset, active-until-next,
  inline, counterbalanced order).
- Writes are idempotent per session (replace, not duplicate); provenance is
  recorded on `session`.

## Success conditions (severity-tested)
- A complete `auto` run over valid inputs ends with `done == True` and an
  `analyse`/`visualise` result.
- Removing the comparison config makes `define` return `needs_input`; supplying
  it via `resolve()` lets the run finish.
- `analyse` reproduces a known paired contrast from a seeded store.
- `visualise` never raises.

## Measures, respiration, single-subject, ingestion confidence (2026-06-08 addendum)

Modules added: `measures.py`, `figures.py`; `stages.inspect()`; routes in
`backend/app/api/v1/routes/workflow.py`.

### Measure registry (`measures.py`)
- A measure is `(id, label, aggregator, kind)`. `kind ∈ {window_mean, rr_window,
  resp_session}` selects the aggregator. Registry: `eda_tonic`, `resp_rate`,
  `mean_hr`, `rmssd`, `pnn50`, `resp_stress_index`.
- `define` accepts `comparison.measures: [id,…]` (or legacy single `measure`);
  `analyse` returns `outputs.measures[id] = {per_subject, paired?, note?}`.
- **Honest labels carry through.** RMSSD applies the wrist-implausibility gate
  (returns `None`, not a default, when RMSSD > 200 ms); a measure below its
  minimum sample count returns `None`.

### Respiration / RespInPeace (the workflow integration)
- Canonicalise ingests Vernier belt files into `sample_resp` (force + device
  rate); condition windows are derived from an inline `condition` column when no
  separate markers file exists (`source_convention="inline_condition"`).
- `resp_stress_index` runs the vendored RespInPeace engine + recalibrated
  classifier **once per session**, assigns each breath to a condition window by
  its trough timestamp, and reports the flagged-breath fraction per window. The
  engine call is wrapped — a detection failure yields `{}`, never an exception.

### Single-subject mode
- Every stage is valid at `n = 1`. `analyse` with one paired subject returns the
  per-subject values plus a `note` ("descriptive only") and **omits** `paired`;
  it never fabricates a group statistic or raises. `outputs.n_subjects` and a
  top-level `note` mark single-subject runs.
- `stages.inspect(session_id, store)` returns sub-sampled raw series (`eda`,
  `rr`, `resp`), the condition `windows`, and `per_window_measures` for the
  Inspect view. Exposed at `GET /workflow/{id}/inspect/{session_id}`.

### Ingestion confidence
- Canonicalise reports `qc.confidence`. With `config.require_conditions` (default
  true) and **zero** derivable condition windows, it returns `needs_input` with a
  `roster_or_markers` decision (options: `upload_roster`, `map_manually`,
  `ai_assist`) — it never guesses a mapping. Nothing low-confidence is committed.

### Chart engine (`figures.py`, fail-soft)
- `render_analysis(db_path, analyse_out)` writes one paired-slope PNG per measure
  that has paired data to `<db>/figures/`; measures without data are recorded in
  `skipped`, never raised. `render_inspect` writes the single-subject timeseries
  with condition windows shaded. `visualise` returns `figures`/`skipped` maps.

### HTTP surface (last-mile: the pipeline is reachable)
`POST /workflow`, `POST /workflow/{id}/advance`, `GET /workflow/{id}`,
`POST /workflow/{id}/resolve`, `POST /workflow/{id}/rerun/{stage}`,
`GET /workflow/{id}/inspect/{sid}`, `GET /workflow/{id}/figure?name=`. State is
persisted atomically (temp file + `os.replace`) to `data/workflow_runs/<id>.json`;
the canonical DB sits beside it. The figure route serves basenames only (no path
traversal).

### Added severity tests (`test_workflow.py`, `test_workflow_routes.py`)
single-subject is descriptive-not-error; inspect returns series + per-window
measures; multi-measure run writes a real PNG; canonicalise pauses for a roster
when no conditions derivable; Vernier+RespInPeace flow end-to-end; full HTTP
start→resolve→inspect→figure round-trip with persisted resume. Suite: 168 passed.

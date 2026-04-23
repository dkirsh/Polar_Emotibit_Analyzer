# GUI scope — file-only pre-synched pair ingestion (2026-04-20)

*Date*: 2026-04-20
*Supersedes*: the GUI paragraphs in `docs/INTEGRATION_PLAN_WITH_SIBLING_REPO_2026-04-20.md` § 4 step 5 and in `docs/RUTHLESS_REVIEW_PROMPT_FOR_CODEX_2026-04-20.md` probe 5 — narrows the GUI requirements to what the revised scope actually needs.
*Owner*: DK scoped; CW documenting; Codex will execute.

---

## The scope clarification

This system does not collect data. It ingests a **pre-synchronised pair of CSVs** — one Polar H10 export, one EmotiBit export — and runs the existing post-hoc pipeline on them. The Bluetooth-scanning, USB-enumeration, real-time-streaming work catalogued in the sibling repo's `docs/GAP_ANALYSIS_POTEMKIN_2026-03-02.md` is **out of scope forever**, not "deferred". The twelve to fifteen thousand lines of wizard scaffolding that imply live acquisition are therefore not a target for porting.

What remains is a lightweight upload-and-analyse surface. The file-only scope means the GUI is essentially two views: a session-metadata-plus-upload form, and a results dashboard. The rest of the sibling's wizard is noise.

## The two views the GUI needs

### View 1 — New Analysis Session (one page replacing `StartPage.tsx`)

The page captures session identity *and* the two (optionally three) files in a single submission. No multi-step wizard; no claim of "device setup" or "data collection" phases that the system does not perform.

**Metadata panel** (block on the left):

- **Session ID** — free text, required, pattern `[A-Za-z0-9_-]+`, example `S204_2026_04_08`. Used as the key for subsequent artifact filenames and the persisted DB row.
- **Subject ID** — free text, required, example `P01`. Separate from session ID so multiple sessions per subject can be analysed without path collisions.
- **Study / Project ID** — free text, required, example `STRESS_001`.
- **Session date** — HTML5 `<input type="date">`, default to today. Stored as ISO 8601; surfaced on the results page header so the researcher always sees "this analysis is of the session recorded on YYYY-MM-DD".
- **Operator / analyst** — free text, optional. Useful for multi-researcher labs; written to the DB row and the markdown report.
- **Notes** — free text, optional, up to 500 characters. A place to record "ran the stress protocol version B" or "participant reported feeling cold".

**Upload panel** (block on the right):

- **EmotiBit CSV** — drag-drop zone + click-to-browse fallback. Required. On drop, client-side POSTs the file to `/api/v1/validate/csv/emotibit` for schema check; renders the validator's response inline (pass → green check with row count and column list; fail → red with the specific missing-column message). No multi-file selection.
- **Polar H10 CSV** — same pattern, separately. Required. Posted to `/api/v1/validate/csv/polar`. Preferred input is a raw ECG export (`timestamp_ms` or `timestamp_ns` plus `ecg_uv`/`ecg_mv`/`ecg`), because the app can derive HR and RR itself from the raw trace. Legacy beat-level exports are still accepted: `timestamp_ms` + `hr_bpm`, with `rr_ms` optional. The validator reports whether the file is raw ECG, native RR, or BPM-only, because that distinction matters for HRV interpretability.
- **Event markers CSV** — optional drag-drop. Holds phase timings (`recording_start`, `stress_task_start`, `stress_task_end`, `recovery_start`, `recording_end`) in the format `docs/REAL_DATA_SYNC_COLLECTION_REPORT_2026-03-01.md` of the sibling repo specifies. Absent → analysis runs across the full temporal overlap only; present → the results page computes features window-by-window per declared phase. Schema validation via `/api/v1/validate/csv/markers` (a new endpoint; schema: `session_id`, `event_code`, `utc_ms`, `note_optional`).

**Phase-timing fallback** (shown only when no markers CSV was uploaded):

Four `<input type="datetime-local">` fields — baseline start, stress-task start, stress-task end, recovery end — that a user can fill manually if they recorded phase transitions by hand. Optional; absent → whole-session analysis only. If any one is filled, all four must be, to avoid half-specified windows.

**Submit button**: "Run Synchronization & Feature Extraction" with a spinner on click, disabled until both required CSVs have validated green. On submit, builds a `multipart/form-data` POST to `/api/v1/analyze` with both (or three) files plus the metadata as form fields, stores the returned analysis ID in `sessionStorage`, and navigates to view 2.

**Recent sessions list** (optional, lower-priority — footer of the page):

A table of the last 10 sessions this browser has run (`session_id`, `subject_id`, `date`, `sync_qc_gate` pill), each row linking to view 2 for that session. Reads from the backend `GET /api/v1/sessions?limit=10` if the DB persistence layer is wired (probe 4 in the ruthless-review prompt), or from `localStorage` otherwise. Saves a user the pain of re-uploading for a re-read of yesterday's results.

### View 2 — Results Dashboard (adapted from the existing `PostHocDashboard.tsx`)

The scaffold is already there — it just needs to read from the API response rather than from JSX literals.

**Header strip** — replaces the "Setup New Project / Go to Dashboard" route toggle with a **session-identity bar**: `Session {session_id} · Subject {subject_id} · {date} · {operator}`, followed by a secondary line `Analyzed at {timestamp} · {rr_source: native_polar | derived_from_ecg | derived_from_bpm}`. This is where "which analysis am I looking at" is answered; a dashboard that has no identity bar is trivially confusing on a second session.

**Sync-QC panel** — the existing "Drift Corrected ✓ / Overlap Confirmed ✓ / Confidence: Green" markup stays, but **each check reads from the response**. The pill colour comes from `sync_qc_band` (`green|yellow|red`). The numeric score comes from `sync_qc_score` (0–100). Below the pill, render `sync_qc_failure_reasons` as a list if any — the point of the sync-QC gate (per the sibling's `sync_qc.py`) is that the user is supposed to see *why* a session is yellow or red, not just that it is.

**Chart area** — the existing `[Interactive Charting Area]` placeholder. Phase 1 of the GUI work can leave this as a static "Charts coming in v2" note rather than render a misleading placeholder. Phase 2 (not in scope for the first cut) plots HR and EDA overlays with phase boundaries marked. A chart now without an honest data source would be worse than a blank-state panel.

**HRV + EDA feature table** — replaces the hardcoded `134.16 / 330.57 / 57.13` literals with the response's `feature_summary` fields: `rmssd_ms`, `sdnn_ms`, `mean_hr_bpm`, `eda_mean_us`, `eda_phasic_index`, `stress_score`, plus `vlf_ms2`, `lf_ms2`, `hf_ms2`, `lf_hf_ratio` when the recording is long enough for each (display em-dash `—` for `None`, with a tooltip explaining the per-band minimum duration). If phase timings were supplied, render one row per phase plus a final whole-session row; if not, just the whole-session row.

**Quality flags panel** — a bulleted list reading `quality_flags` verbatim from the response. These come from the pipeline's `run_analysis` function (`backend/app/services/processing/pipeline.py` in the sibling) and include things like "HRV computed from native Polar H10 RR intervals (research-grade)", "High motion artifact ratio (>20%)", "Stress score is experimental composite (not psychometrically validated)". The point is honest user-visible provenance; a results dashboard that hides its quality flags is scientifically irresponsible.

**Report download button** — the pipeline already produces `report_markdown` in the response. Button renders a download of `session_id_report.md` with that content, plus a paired `session_id_analysis.json` download for the full typed response. No PDF generation in phase 1; markdown is reproducible and diffable.

## What the GUI explicitly does *not* have

- **No Lab Setup step.** The system does not configure a lab.
- **No Sensor Setup step.** The system does not talk to sensors. The hardcoded `useState(true)` connection checkboxes from the sibling's `SensorSetupStep.tsx` that the gap analysis flagged as theatrical are not ported.
- **No Data Collection step.** The system does not record. There is no "press start", "recording" state, or live signal view.
- **No live validation step.** Schema validation happens on drop (per-file, client-side POST to the validator endpoint). There is no separate "Validation" page whose job is to re-render the same check.
- **No device-status or battery indicator.** There are no devices.
- **No "Real Session" vs "Synthetic" mode toggle.** Every session is a real session; the user always supplies real files. Synthetic data remains available for backend pytest fixtures (`data/synthetic/*.csv`) but is not a user-facing mode.

## What this means for the sibling's files

Porting strategy for the frontend, concretely:

**Port wholesale** — these are reusable:
- `frontend/src/api/*` — typed fetch wrappers for `/api/v1/*`. Direct copy.
- `frontend/src/types/*` — TypeScript types for the API response. Direct copy (Codex may need to regenerate from pydantic models if they drift).
- `frontend/src/hooks/*` — any `useApi` / `useQuery` hooks. Direct copy.
- `frontend/src/components/StepPanel.tsx` — the layout primitive, if we keep any card-like styling.
- `frontend/src/wizard/AnalysisStep.tsx` — the piece that actually renders analysis results. **This is the view 2 content**; port it and strip the "you are on wizard step 5 of 5" chrome.

**Do not port** — these are wizard theatre:
- `frontend/src/wizard/LabSetupStep.tsx`.
- `frontend/src/wizard/SensorSetupStep.tsx`.
- `frontend/src/wizard/DataCollectionStep.tsx`.
- `frontend/src/wizard/ValidationStep.tsx` (validation is now inline on upload).
- Any `WizardNav` / step-sequencer component.
- Any Cypress test that exercises the wizard step-sequence (they will fail against the simpler GUI and are irrelevant).

**Rewrite against the simpler contract**:
- `StartPage.tsx` → the metadata-plus-upload view 1 described above.
- `PostHocDashboard.tsx` → the results-only view 2 described above.
- `App.tsx` → a two-route renderer (`'/'` and `'/results/:sessionId'` with React Router, not a `useState` toggle).

## Revised step 5 for the 90-minute Codex plan

The integration plan's step 5 ("wire the frontend to the backend") is replaced by these sub-steps, in order:

- 5a. Port `api/`, `types/`, `hooks/`, `components/StepPanel.tsx`, and `wizard/AnalysisStep.tsx` from the sibling. Adjust imports.
- 5b. Replace `frontend/src/App.tsx` with a two-route renderer. Add React Router and `ProjectContext` for session identity.
- 5c. Replace `frontend/src/pages/StartPage.tsx` with the metadata-plus-upload form per view 1 above. Wire per-file drag-drop, per-file schema validation, submit button state.
- 5d. Replace `frontend/src/pages/PostHocDashboard.tsx` with the results view per view 2 above. **Remove the hardcoded 134.16 / 330.57 / 57.13 literals entirely.** Read `feature_summary` from `sessionStorage` or fetch from `GET /api/v1/sessions/:id`. Render `quality_flags`, `sync_qc_*`, and `report_markdown`.
- 5e. Add a new endpoint `POST /api/v1/validate/csv/markers` (schema: `session_id`, `event_code`, `utc_ms`, optional `note`). Wire to view 1's optional event-markers drop zone.
- 5f. Write one Cypress spec per view that exercises the happy path end-to-end against the Chung et al. (2026) OSF sample (per `docs/POLAR_H10_REFERENCE_DATA_AND_PAPER_2026-04-20.md`). Happy-path only; failure-mode specs are a follow-up.

## Scope acknowledgements

A lab that records real sessions still needs to get the files *into* this tool's input. That is not this tool's job. The expected external workflow is the one documented in the sibling repo's `docs/REAL_DATA_SYNC_COLLECTION_REPORT_2026-03-01.md`: Polar H10 recorded via the Polar Sensor Logger Android app or the Polar Beat iOS app, EmotiBit recorded via its own SD-card export flow, phase timings recorded by an operator with a stopwatch or via `scripts/log_event_sequence.py` (which the sibling supplies and which can be kept as a separate utility independent of this GUI). The files arrive on the analyst's machine; the analyst drops them into this tool's view 1; the pipeline runs and view 2 renders.

This is a narrower scope than the sibling aspired to and a much more honest one given the device-integration gap. It is also the scope the newer repo's own README describes.

## References

Chung, V., Chopin, L., Karadayi, J., & Grèzes, J. (2026). Validity of the Polar H10 for continuous measures of heart rate and heart rate synchrony analysis. *Sensors, 26*(3), 855. https://doi.org/10.3390/s26030855 — for the positive-case smoke test described in step 5f.

Nielsen, J. (1994). Enhancing the explanatory power of usability heuristics. In *CHI '94 Proceedings* (pp. 152–158). https://doi.org/10.1145/191666.191729 — H1 (visibility), H2 (match between system and the real world), H5 (error prevention). The "no device-status indicator if there are no devices" choice is H2 made concrete: the interface should not lie about what the system does.

Norman, D. A. (1988). *The design of everyday things*. Basic Books. — the visible-state / system-model alignment argument behind removing the Lab Setup / Sensor Setup / Data Collection wizard steps.

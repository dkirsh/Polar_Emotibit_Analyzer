# Integration plan — using the sibling repo to complete the Polar-Emotibit Analyzer

*Date*: 2026-04-20
*Author*: CW (audit + plan); Codex executes
*Sibling repo*: `/Users/davidusa/REPOS/emotibit_polar_data_system` — the older, more mature codebase
*Companion docs*: `docs/RUTHLESS_REVIEW_AUDIT_2026-04-20.md`, `docs/RUTHLESS_REVIEW_PROMPT_FOR_CODEX_2026-04-20.md`

---

## 1. Headline finding

The six modules that the Polar-Emotibit Analyzer's `pipeline.py` imports but cannot find **all exist, fully written, in the sibling `emotibit_polar_data_system` repo**. They are not speculative dependencies; they are working code that has been stranded by the extraction into this smaller repo. The older repo's own `docs/GAP_ANALYSIS_POTEMKIN_2026-03-02.md` confirms 115 passing pytest cases against what is effectively the same processing library, organised as:

| Polar_Emotibit_Analyzer needs | Exists in sibling at | Status in sibling |
|---|---|---|
| `app/schemas/analysis.py` (`AnalysisResponse`, `FeatureSummary`, `BlandAltmanMetric`) | `emotibit_polar_data_system/backend/app/schemas/analysis.py` | present + tested |
| `app/models/signals.py` (`DriftModel`, `PiecewiseDriftModel`) | `emotibit_polar_data_system/backend/app/models/signals.py` | present + tested |
| `app/services/ai/adapters.py` (`NON_DIAGNOSTIC_NOTICE`) | `emotibit_polar_data_system/backend/app/services/ai/adapters.py` | present with provider-fallback logic |
| `app/services/processing/sync.py` (`synchronize_signals`) | `emotibit_polar_data_system/backend/app/services/processing/sync.py` | present + tested (9 tests) |
| `app/services/processing/stress.py` (`STRESS_SCORE_LABEL`, `compute_stress_score`) | `emotibit_polar_data_system/backend/app/services/processing/stress.py` | present with validated-vs-experimental flag |
| `app/services/reporting/report_builder.py` (`build_markdown_report`) | `emotibit_polar_data_system/backend/app/services/reporting/report_builder.py` | present |

The sibling also ships substantial additional material that the newer repo does not have: a full FastAPI surface at `backend/app/main.py` with routes under `backend/app/api/v1/`, an Alembic-migrated PostgreSQL/SQLite persistence layer under `backend/app/db/` + `backend/alembic/`, a Vite/React wizard with five steps (`LabSetupStep.tsx`, `SensorSetupStep.tsx`, `DataCollectionStep.tsx`, `ValidationStep.tsx`, `AnalysisStep.tsx`) plus Cypress end-to-end tests, an Electron desktop launcher, and a mature operational surface (`install.sh`, `start`, `stop`, `scripts/doctor.sh`, auto-repair and AI-debug helpers, signed-DMG build scripts).

The headline, put bluntly: **the newer Polar_Emotibit_Analyzer repo is a Potemkin extraction from a sibling that is already 80% built**. The audit I wrote yesterday (`docs/RUTHLESS_REVIEW_AUDIT_2026-04-20.md`) is accurate for the newer repo taken alone; it is far too pessimistic when the sibling is in the picture. The right intervention is not to write the six missing modules from scratch — Codex would produce adequate stubs but would not match the cited papers, the docstring-level "Skeptic's FAQ" style, or the test fixtures that already exist. The right intervention is to **lift** the sibling's modules into this repo and re-run the audit's remaining probes against the integrated state.

## 2. What is of independent value in `emotibit_polar_data_system/docs/`

The docs directory in the sibling is unusually rich. I walked it and classified each file by relevance to getting the Polar-Emotibit Analyzer working. The items below are the ones worth reading in priority order before Codex starts the integration work.

**Primary — read first (≈ 30 minutes reading total).**

`docs/GAP_ANALYSIS_POTEMKIN_2026-03-02.md` is the single most important file. It catalogues, in concrete code-evidence form, exactly where the wizard UI is theatrical rather than functional — the hardcoded `useState(true)` connection checkboxes in `SensorSetupStep.tsx`, the static-HTML validation results in `ValidationStep.tsx`, the fact that analysis always runs on synthetic data because no real data-collection layer exists. Its tier-1 / tier-2 missing-component table names the exact device-integration work that is still unbuilt (BLE scanning via `bleak`, USB enumeration, packet parsing for both Polar and EmotiBit protocols, recording start/stop control, WebSocket/SSE streaming). This is the honest gap register.

`docs/REAL_DATA_SYNC_COLLECTION_REPORT_2026-03-01.md` documents the expected lab protocol end-to-end: what columns the CSVs must have, the four synchronization strategies (clock-synced absolute timestamps, clock-sync + event marker, physiological pattern, audio-only) with pros and cons for each, and a specific recommendation (NTP + one event marker at start). It also lists the guided single-command pipeline `python3 scripts/run_real_session_pipeline.py --session-id … --mode full --append-metrics` that threads every stage together, and the strict-sync gate that blocks metrics export when synchronization confidence is below threshold. This is the operational contract a successful integration must honour.

`docs/03-01_06_RUTHLESS_V2.1_Final.md` is an 11-panelist adversarial audit prompt that was run against the sibling repo at the v2.1 milestone. The panelist roster (psychophysiologist, biosignal engineer, statistician, research methodologist, infosec, macOS platform engineer, clinical data governance, DevOps, frontend/UX, test engineer, research software engineer) is directly reusable as the Codex prompt for an integrated Polar-Emotibit Analyzer once it can run. The "red flag patterns" section names the exact failure modes (circular benchmarks, wrong-signal xcorr, fixed-rate data removal, processing-order errors, standalone QC not integrated, frontend mock drift, minimum window violations, distribution assumption errors, ddof inconsistency) that the v2.1 repairs were supposed to fix — all of which are worth checking the lifted modules still respect.

`docs/03-01_07_Self_Audit_Results_V2.1.md` is the sibling's self-reported closeout of those repairs: each claimed V2.1 fix mapped back to its panelist concern, with a status and evidence pointer. If the integration is going to copy the v2.1 modules, it should also copy the test evidence that each fix actually works.

`docs/STUDENT_GETTING_STARTED.md` is the user-facing onboarding doc and the model for what the Polar-Emotibit Analyzer's eventual user-facing README should look like. It documents the `./install.sh` → `./start` → five-minute smoke-test flow that the sibling already runs; an integrated Polar-Emotibit Analyzer should keep this exact interaction pattern.

**Secondary — read when relevant.**

`docs/API.md` and `docs/ARCHITECTURE.md` are short reference docs; the architecture doc is only 24 lines but the API doc captures the endpoint surface the frontend expects. `docs/EXTENDED_TEST_BATTERY_2026-03-02.md`, `docs/RUTHLESS_EVALUATION_REPORT_2026-03-03.md`, and `docs/REFERENCE_BENCHMARK_PROTOCOL.md` document the test regime and the acceptance thresholds against Kubios.

`docs/INSTALLER_BEST_PRACTICES_2026-03-01.md`, `docs/MAC_ENTERPRISE_RELEASE.md`, and `docs/MAC_HANDOFF.md` capture the macOS deployment work — relevant only if the Polar-Emotibit Analyzer is going to go beyond a dev-local tool.

`docs/EXPERIMENTALIST_PANEL_TRANSCRIPT_2026-02-28.md`, `docs/PANEL_SIMULATED_TRANSCRIPT_2026-02-28.md`, `docs/SCIENCE_GRAPHICS_PANEL_SIMULATED_2026-03-01.md`, and `docs/SCIENCE_GRAPHICS_PLAYBOOK_2026-03-01.md` are panel-simulation transcripts in the style Codex later refined for the Knowledge Atlas work. They're worth reading as examples of the method but do not contain material needed for the integration.

**Tertiary — unlikely to be load-bearing.**

`docs/03-01_05_emotibit_polar_full_fixes_V2.0.tar.gz`, `docs/claude revision 2.zip`, `docs/files.zip`, and `docs/Older.zip` (at repo root) are snapshots of prior states. Not worth unpacking unless a specific historical question arises.

`docs/Claude query on HRV Kubios.docx` is a chat transcript with questions about HRV measurement and Kubios parity. Interesting but not authoritative.

## 3. The plan to get the Polar-Emotibit Analyzer working

Three paths are available, ranked by CW's recommendation.

### Path A (recommended) — Lift the six missing modules, keep the newer repo's identity

Copy the six required source files, plus `extended_analytics.py` which the sibling has as a bonus, from `emotibit_polar_data_system/backend/app/...` into `Polar_Emotibit_Analyzer/backend/app/...` at identical paths. Copy the corresponding tests. Run `pytest` and confirm the imports resolve and the existing tests plus the lifted tests all pass. This is a mechanical lift that takes perhaps an hour of Codex-time and produces a runnable `run_analysis` function.

Write `backend/app/main.py` using the sibling's `backend/app/main.py` as a template but scoped to the subset of routes the Polar-Emotibit Analyzer actually wants — at minimum `/api/v1/analyze`, `/api/v1/validate/csv/{type}`, `/api/v1/benchmark/kubios`, and `/health`. The sibling's `backend/app/api/v1/routes/analysis.py` is the source file; pull the functions verbatim.

Wire the frontend's "Run Synchronization & Feature Extraction" button to the new `/api/v1/analyze` endpoint, replace the JSX literals with the response's `feature_summary` fields, and add loading/error states. The sibling's `frontend/src/wizard/AnalysisStep.tsx` and the Cypress test `frontend/cypress/e2e/analysis_flow.cy.ts` are the templates to follow.

Outcome: a Polar-Emotibit Analyzer that imports cleanly, has a runnable backend with a test-covered pipeline, and has a dashboard that renders real analysis results from a user-uploaded CSV pair — in roughly the same footprint as the current repo, without inheriting the sibling's Electron launcher, install.sh, or macOS packaging. The sibling's device-integration gap (no BLE, no USB, no real-time streaming) is inherited; file-only post-hoc analysis is explicitly this repo's scope per its own README.

### Path B — Adopt the sibling wholesale, migrate new work from the newer repo

Archive the newer `Polar_Emotibit_Analyzer` repo and keep the sibling as the canonical codebase. The sibling has everything the newer repo has plus much more. If there is any net new work in the newer repo that is not in the sibling, migrate it (the generator-style API, any new frontend patterns, new tests). This is the strictly technically superior path but loses the newer repo's cleaner scope and its cleaner docstrings in the V2.1-repaired modules.

Decision for DK: is the newer repo a deliberate narrower scope (file-only post-hoc analyzer, no device integration, no Electron, no install.sh) or is it an accident of a partial extraction? If the former, Path A; if the latter, Path B.

### Path C — Write the six missing modules from scratch

The audit I wrote yesterday took this path by default. It is fine as a fallback if for some reason the sibling is off-limits, but it is strictly worse than Path A: it recapitulates the V2.1 repair work without access to the citation-backed rationales and test fixtures the sibling already has. Recommend only if there is a licensing, policy, or branching reason the sibling's code cannot be reused.

## 4. Concrete Codex commands for Path A

Assuming Path A, the step-by-step execution is tight enough to be a single-session Codex brief:

```bash
# Working copy
cd /Users/davidusa/REPOS/Polar_Emotibit_Analyzer

# Step 1: lift six missing modules + one bonus (extended_analytics.py)
SIB=/Users/davidusa/REPOS/emotibit_polar_data_system
mkdir -p backend/app/schemas backend/app/models backend/app/services/ai backend/app/services/reporting

cp "$SIB/backend/app/schemas/analysis.py"              backend/app/schemas/analysis.py
cp "$SIB/backend/app/schemas/__init__.py"              backend/app/schemas/__init__.py  2>/dev/null || touch backend/app/schemas/__init__.py
cp "$SIB/backend/app/models/signals.py"                backend/app/models/signals.py
cp "$SIB/backend/app/models/__init__.py"               backend/app/models/__init__.py   2>/dev/null || touch backend/app/models/__init__.py
cp "$SIB/backend/app/services/ai/adapters.py"          backend/app/services/ai/adapters.py
cp "$SIB/backend/app/services/ai/__init__.py"          backend/app/services/ai/__init__.py 2>/dev/null || touch backend/app/services/ai/__init__.py
cp "$SIB/backend/app/services/processing/sync.py"      backend/app/services/processing/sync.py
cp "$SIB/backend/app/services/processing/stress.py"    backend/app/services/processing/stress.py
cp "$SIB/backend/app/services/processing/extended_analytics.py" backend/app/services/processing/extended_analytics.py
cp "$SIB/backend/app/services/reporting/__init__.py"   backend/app/services/reporting/__init__.py 2>/dev/null || touch backend/app/services/reporting/__init__.py
cp "$SIB/backend/app/services/reporting/report_builder.py" backend/app/services/reporting/report_builder.py

# Step 2: lift the tests that exercise the lifted modules
cp -R "$SIB/backend/tests/"*.py backend/tests/
# Remove or skip tests that reference device integration / Alembic / full API
# (Codex: identify them; put in a 'skipped_for_lift' fixture rather than delete)

# Step 3: ensure the import graph works
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install scipy pandas numpy scikit-learn pydantic fastapi uvicorn sqlalchemy pytest --break-system-packages
python3 -c "from app.services.processing import pipeline; print('imports OK')"
python3 -m pytest tests -q

# Step 4: minimum FastAPI surface
# Codex: adapt $SIB/backend/app/main.py and $SIB/backend/app/api/v1/routes/analysis.py
# into backend/app/main.py + backend/app/api/v1/routes/analysis.py, scoped to:
#   POST /api/v1/analyze
#   POST /api/v1/validate/csv/{emotibit|polar}
#   POST /api/v1/benchmark/kubios
#   GET  /health

# Step 5: frontend wiring
# Codex: adapt $SIB/frontend/src/wizard/AnalysisStep.tsx into
# Polar_Emotibit_Analyzer/frontend/src/pages/PostHocDashboard.tsx.
# Replace the hardcoded RMSSD/SDNN/HR/Stress literals with response data.
# Add drag-drop handlers to the two upload zones.
# Add onClick to "Run Synchronization & Feature Extraction" that POSTs to /api/v1/analyze.

# Step 6: smoke-test with a real sample pair (see § 5 below)
```

Each step is a commit. Step 1 commit: `Lift six modules from sibling emotibit_polar_data_system (Path A)`. Step 2: `Lift sibling tests; skip device-integration specs`. Step 3: `Confirm imports + pytest green post-lift`. Steps 4-5 as described in probes 4-5 of `docs/RUTHLESS_REVIEW_PROMPT_FOR_CODEX_2026-04-20.md`.

## 5. Polar H10 data — was I able to find any?

Short answer: **public sample datasets exist on GitHub, but no real Polar H10 data has ever been stored in either repo**. Here is the picture in one paragraph so you can decide whether to buy a Polar H10 and generate your own or pull down someone else's.

**Inside the two repos.** The newer `Polar_Emotibit_Analyzer` has a `data/synthetic/` directory that is entirely empty. The older `emotibit_polar_data_system` has `data/examples/polar_example.csv` (6 rows — a toy) and `data/synthetic/polar_synthetic.csv` (300 rows from its `synthetic.py` generator). The older repo's `data/raw/`, `data/real_sessions/`, `data/processed/`, `data/benchmarks/`, and `data/pdfs/` directories exist but are empty or contain only a header-only CSV. The `data/benchmarks/system_metrics.csv` file contains one header row and zero data rows — no real sessions have ever been run through this pipeline. The older repo's `docs/REAL_DATA_SYNC_COLLECTION_REPORT_2026-03-01.md` documents how a real session would be structured but does not contain the recording from one.

**On public GitHub.** Three repos publish sample Polar H10 CSVs in formats close enough to map onto this repo's `parse_polar_csv` with a column-rename or two. [`iitis/Polar-HRV-data-analysis`](https://github.com/iitis/Polar-HRV-data-analysis) (a Python HRV-analysis library) bundles example sessions collected via the Polar Sensor Logger Android app, with RR-interval data in milliseconds and accelerometer columns. [`BeaconBrigade/polar-arctic`](https://github.com/BeaconBrigade/polar-arctic) logs HR + RR + ECG + acceleration to CSV; sample sessions live in its wiki. [`RGreinacher/polar-h10-ecg-viewer`](https://github.com/RGreinacher/polar-h10-ecg-viewer) has 130 Hz ECG voltage traces, which are now directly useful because the Polar-Emotibit Analyzer now accepts raw ECG and derives HR/RR internally. The [Wearipedia Polar H10 notebook](https://wearipedia.readthedocs.io/en/latest/notebooks/polar_h10.html) walks through extracting HR + RR from the Polar Accesslink API.

**For EmotiBit's half of the pair**, [`gmaione1098/EmotiData`](https://github.com/gmaione1098/EmotiData) bundles three EmotiBit sessions (relax / gym / run) in the standard DataParser output format (one file per data type). The schema mapping is documented in [`EmotiBit/EmotiBit_Docs`](https://github.com/EmotiBit/EmotiBit_Docs/blob/master/Working_with_emotibit_data.md).

**For a paired corpus that is not Polar H10 specifically but can substitute**, PhysioNet's [Pulse Transit Time PPG v1.0.0](https://www.physionet.org/content/pulse-transit-time-ppg/1.0.0/csv/) has 22 subjects with paired PPG and ECG in standardised CSV form, which the pipeline could accept with minimal column-renaming.

None of these are *truly matched* Polar-H10-and-EmotiBit-from-the-same-wrist sessions; the public landscape does not appear to have such a corpus. The minimum viable test pair would be a Polar H10 five-minute baseline from the Polar Sensor Logger app and a separately-collected EmotiBit five-minute baseline from the SD-card export, recorded in the same sitting. That is the collection Codex should plan around once the integration is done.

**Recommendation**: for the integration smoke test, pull one Polar H10 session from `iitis/Polar-HRV-data-analysis` and one EmotiBit relax session from `gmaione1098/EmotiData`, rename columns to `timestamp_ms`/`hr_bpm`/`rr_ms` and `timestamp_ms`/`eda_us`/`acc_{x,y,z}` respectively, and drop them into `data/samples/`. The pair will have different recording dates so the sync-QC gate will flag a "no overlap" condition — which is exactly the *negative* test case the pipeline needs. A *positive* test case requires a real paired collection, which DK or a student in the 160sp cohort would need to record.

## 6. What this plan is not

Not a deployment plan. Getting the repo running locally is in scope; shipping it to a staging server, notarising a macOS DMG, or exposing it to non-DK users is separate work and belongs in a second document.

Not a scientific validation. Once the repo runs, the V2.1 repair claims (Welch PSD, t-distribution CIs, absolute-g motion threshold, ddof=1 consistency) still need to be audited against their cited papers on the *lifted* code, not just on the sibling's original copy. That is probe 6 of the ruthless-review prompt and is still required.

Not a device-integration project. Both the newer and older repos are file-only post-hoc analyzers; neither does BLE scanning, USB enumeration, or real-time streaming. The sibling's own gap analysis estimates 8-12 weeks of developer time to close that gap, and that work is explicitly out of scope here.

## 7. Concrete "next 90 minutes" to-do list

If Codex were handed this today:

- [ ] (0:00) Read `docs/GAP_ANALYSIS_POTEMKIN_2026-03-02.md` and `docs/REAL_DATA_SYNC_COLLECTION_REPORT_2026-03-01.md` in the sibling repo.
- [ ] (0:20) Execute Steps 1-3 from § 4 above (lift six modules, lift tests, confirm green pytest).
- [ ] (0:40) Execute Step 4 (minimum FastAPI surface, four routes, integration tests).
- [ ] (1:00) Execute Step 5 (frontend wiring, replace JSX literals, add handlers, add loading state).
- [ ] (1:20) Pull one Polar H10 sample from `iitis/Polar-HRV-data-analysis` and one EmotiBit sample from `gmaione1098/EmotiData`; rename columns; drop into `data/samples/`. Run the pipeline end-to-end.
- [ ] (1:30) Write `docs/SAMPLE_DATA_SMOKE_TEST_2026-04-20.md` capturing: sync-QC verdict on the mismatched sample pair (expected: red/no_go because different dates), plus RMSSD/SDNN/HR/EDA on each CSV independently. Commit and push.

**Blocking status after 90 minutes**: the repo imports cleanly, runs a real HTTP surface, accepts file uploads from the dashboard, and has one documented end-to-end exercise against public data. It does *not* yet have a positive-case real-data test pair from the same session; that is DK's hardware collection task for the 160sp lab. Everything software-side is unblocked.

## References

Benedek, M., & Kaernbach, C. (2010). A continuous measure of phasic electrodermal activity. *Journal of Neuroscience Methods, 190*(1), 80–91. https://doi.org/10.1016/j.jneumeth.2010.04.028

Healey, J. A., & Picard, R. W. (2005). Detecting stress during real-world driving tasks using physiological sensors. *IEEE Transactions on Intelligent Transportation Systems, 6*(2), 156–166. https://doi.org/10.1109/TITS.2005.848368

Koldijk, S., Neerincx, M. A., & Kraaij, W. (2016). Detecting work stress in offices by combining unobtrusive sensors. *IEEE Transactions on Affective Computing, 9*(2), 227–239. https://doi.org/10.1109/TAFFC.2016.2610975

Task Force of the European Society of Cardiology and the North American Society of Pacing and Electrophysiology. (1996). Heart rate variability: Standards of measurement, physiological interpretation, and clinical use. *Circulation, 93*(5), 1043–1065.

## Sources

- Sibling repo: [`/Users/davidusa/REPOS/emotibit_polar_data_system`](file:///Users/davidusa/REPOS/emotibit_polar_data_system) (local)
- [iitis/Polar-HRV-data-analysis](https://github.com/iitis/Polar-HRV-data-analysis)
- [BeaconBrigade/polar-arctic](https://github.com/BeaconBrigade/polar-arctic)
- [RGreinacher/polar-h10-ecg-viewer](https://github.com/RGreinacher/polar-h10-ecg-viewer)
- [Wearipedia — Polar H10 notebook](https://wearipedia.readthedocs.io/en/latest/notebooks/polar_h10.html)
- [gmaione1098/EmotiData](https://github.com/gmaione1098/EmotiData)
- [EmotiBit/EmotiBit_Docs — Working with data](https://github.com/EmotiBit/EmotiBit_Docs/blob/master/Working_with_emotibit_data.md)
- [PhysioNet — Pulse Transit Time PPG v1.0.0](https://www.physionet.org/content/pulse-transit-time-ppg/1.0.0/csv/)
- [polarofficial/polar-ble-sdk](https://github.com/polarofficial/polar-ble-sdk/blob/master/documentation/products/PolarH10.md)

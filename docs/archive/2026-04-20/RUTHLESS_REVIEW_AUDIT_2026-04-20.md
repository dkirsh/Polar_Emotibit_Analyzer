# Polar-Emotibit Analyzer — Ruthless Review Audit

*Date*: 2026-04-20
*Requested by*: DK
*Executor*: CW (audit); Codex (to execute the ruthless-review prompt at § 6)
*Scope*: the entire repo at `/Users/davidusa/REPOS/Polar_Emotibit_Analyzer`

---

## 1. What the repo is trying to do

The README and `docs/GDOCS_SOURCE_MANAGEMENT.md` describe a Python + React/Vite "post-hoc physiological signal analyzer" whose purpose is to take a matched pair of CSV exports — one from a Polar H10 chest strap (heart rate plus, critically, native R-R interval data) and one from an EmotiBit wearable (electrodermal activity, 9-axis IMU, optional temperature and respiration) — temporally align them despite independent device clocks, clean motion-contaminated epochs, and compute Kubios-comparable HRV and EDA features window-by-window for within-session analysis. The system's intended selling point is *scientific parity with Kubios*: the code contains an explicit Bland-Altman agreement module (`benchmark.py`, `kubios_benchmark.py`) and a Welch-based frequency-domain HRV path that cites the ESC/NASPE Task Force (1996) and Shaffer & Ginsberg (2017). The version-2.1 docstrings repeatedly flag themselves as *repair* passes over a "version 2.0" predecessor, which tells us the repo was refactored at least once before the current snapshot.

The **intended architecture** is a FastAPI + SQLite + React/Vite stack: the `backend/app/db/models.py` file declares SQLAlchemy `Project` and `Session` tables, and `frontend/src/App.tsx` is a React component hierarchy whose visible affordances (drag-and-drop uploads, a "Run Synchronization & Feature Extraction" button, a dashboard with a QC confidence pill and an HRV table) imply a live backend. The **actual state** is that the repo is a half-built scaffold in which major pieces are declared but never written, several active modules cannot import because they reference absent files, and the frontend renders static mock data with no button handlers wired to any API. The audit that follows makes this concrete.

## 2. Active file set — a call-graph trace

What is actually reachable from an entry point? I traced imports from every declared entry point (the pipeline function, the test module, and the React root component) and classified each file in the tree by whether something eventually calls it. The result is startling in its density of unreferenced code.

### 2.1 Declared entry points

There are exactly two entry points in the repository, and neither is an HTTP server:

1. `backend/app/services/processing/pipeline.py::run_analysis(emotibit_df, polar_df)` — the advertised end-to-end pipeline function. It has no caller. There is no `main.py`, no `uvicorn` invocation, no FastAPI `@app.post` route; `run_analysis` would have to be called by some wrapper that does not exist.
2. `backend/tests/test_features.py` — three pytest functions exercising `compute_edr`, `compute_temperature_features`, and `compute_rolling_features` out of `features.py`. This is the only code that actually runs against the current tree.

On the frontend, `frontend/src/App.tsx` renders two pages but neither page calls `fetch`, `axios`, `XMLHttpRequest`, nor any other network API. The "Run Synchronization & Feature Extraction" button has **no `onClick` handler at all**; the drag-and-drop panels have no `onDragOver` or `onDrop` handlers; the Kubios-benchmark table shows hardcoded numeric literals (RMSSD 134.16 in baseline vs 45.22 in stress, etc.) — the dashboard is a Figma mockup rendered in JSX, not a functioning dashboard.

### 2.2 What pipeline.py tries to import (and what is missing)

`pipeline.py` opens with nine import statements. The following dependencies **do not exist anywhere in the tree**:

| Imported symbol | Expected file | Present? |
|---|---|---|
| `AnalysisResponse`, `FeatureSummary` | `backend/app/schemas/analysis.py` | **absent — `app/schemas/` directory does not exist** |
| `NON_DIAGNOSTIC_NOTICE` | `backend/app/services/ai/adapters.py` | **absent — `app/services/ai/` directory does not exist** |
| `STRESS_SCORE_LABEL`, `compute_stress_score` | `backend/app/services/processing/stress.py` | **absent** |
| `synchronize_signals` | `backend/app/services/processing/sync.py` | **absent** |
| `build_markdown_report` | `backend/app/services/reporting/report_builder.py` | **absent — `app/services/reporting/` directory does not exist** |

Two further modules inside the processing package (`sync_qc.py` and `drift.py`) import `PiecewiseDriftModel` and `DriftModel` from `app.models.signals`. The `app/models/` directory **does not exist** either. `benchmark.py` and `kubios_benchmark.py` import `BlandAltmanMetric` from the same absent `app.schemas.analysis`.

The arithmetic consequence: **nine of the twelve declared Python files in `backend/app/services/` and `backend/app/db/` either fail to import, or import successfully but are never called from anywhere**. Only `features.py` is demonstrably exercised (by `test_features.py`), `clean.py` and `statistics.py` would import cleanly if the absent modules were stubbed, and `parsers.py` and `synthetic.py` are standalone utilities with no caller.

### 2.3 Summary table

| Module | Imports | Imported by | Status |
|---|---|---|---|
| `app/services/processing/pipeline.py` | 9 (**5 missing**) | nothing | **broken + dead** — cannot import, has no caller |
| `app/services/processing/sync_qc.py` | 1 missing (`app.models.signals`) | `pipeline.py` only | broken + orphaned |
| `app/services/processing/drift.py` | 1 missing | `pipeline.py` only | broken + orphaned |
| `app/services/processing/clean.py` | 0 internal | `pipeline.py` only | imports OK, orphaned |
| `app/services/processing/features.py` | 0 internal | `pipeline.py` + tests | imports OK, exercised |
| `app/services/processing/statistics.py` | 0 internal | **nothing** | dead — orphan |
| `app/services/processing/benchmark.py` | 1 missing | `kubios_benchmark.py` | broken + orphan |
| `app/services/processing/kubios_benchmark.py` | 1 missing | nothing | broken + orphan |
| `app/services/ingestion/parsers.py` | 0 | nothing | dead — no caller |
| `app/services/ingestion/synthetic.py` | 0 | nothing | dead — no caller |
| `app/db/models.py` | sqlalchemy only | nothing | dead — no caller, no session-maker |
| `frontend/src/App.tsx` | 2 (both present) | Vite root (implicit) | UI-only; no API wiring |
| `frontend/src/pages/StartPage.tsx` | React only | App.tsx | mock only; no submit handler |
| `frontend/src/pages/PostHocDashboard.tsx` | React only | App.tsx | mock only; no upload/run handlers |
| `backend/tests/test_features.py` | features.py | pytest | **exercised** — the only live code path |

**Active set (anything a user can actually trigger)**: `features.py` via the three `test_features.py` tests. That is literally it.

### 2.4 Missing infrastructure

Beyond the missing Python modules, the repo is missing several standard-ish files whose absence suggests it was never run:

- No `pyproject.toml`, `setup.py`, `requirements.txt`, or `Pipfile` — no Python dependency manifest anywhere (yet `features.py` imports `scipy`, `pandas`, `numpy`, and `statistics.py` imports `scipy.stats`).
- No `package.json`, `tsconfig.json`, `vite.config.ts`, `index.html`, or `main.tsx` in `frontend/` — the React app has no build entry point.
- No `.gitignore` at the repo root.
- No FastAPI `main.py`, no `uvicorn` entry, no route definitions.
- No Alembic or equivalent migration for the SQLAlchemy models in `db/models.py`.
- `data/synthetic/` exists but is empty; no sample CSVs of any kind in the repo.
- The docstring on `sync_qc.py` mentions a prior "356-line standalone `scripts/run_sync_qc.py`" that *did* exist in v2.0 "but was never called". There is no `scripts/` directory at all, so the v2.0 script is also gone.

## 3. What works — the bright spots worth preserving

Despite the structural problems, the code that *does* exist has two notable strengths:

First, the **docstrings are unusually honest**. `pipeline.py`'s header acknowledges three v2.0 bugs by name (the xcorr-on-wrong-signals bug, the never-called sync-QC gate, the undocumented stress formula); `features.py` explains its v2.1 switch from a simple periodogram to Welch's method with a citation-backed rationale; `clean.py` derives its 0.3 g motion threshold from Kleckner et al. (2018) and defends the processing order (range → motion → winsorize) against the v2.0 order with a Benedek & Kaernbach (2010) citation; `statistics.py` replaces an inconsistent `ddof=0`/`z=1.96` pair with `ddof=1` and a t-distribution CI and defends each with a specific reference. The "Skeptic's FAQ" style in the module headers is the kind of self-critical documentation that a researcher can audit. **This is the repo's genuine contribution and any refactor must preserve it.**

Second, the three tests in `test_features.py` are unusually well constructed for such a small suite. The sine-wave respiration test, the monotonic-drop temperature test, and the window-count-arithmetic rolling-features test all check actual numerical correctness against analytic ground truth — they are not tautological. A more extensive test suite that imitates this style would be a sound foundation for development.

## 4. What is wrong — the twelve highest-leverage defects

The defects are not uniformly distributed. A small number of them account for most of the "the repo does not run" symptom; the rest are about correctness once it does. Ranked from most- to least-load-bearing:

1. **Five missing Python modules break all pipeline imports.** The pipeline cannot be invoked from any entry point until `app/schemas/analysis.py`, `app/models/signals.py`, `app/services/ai/adapters.py`, `app/services/processing/sync.py`, `app/services/processing/stress.py`, and `app/services/reporting/report_builder.py` are written. Without these, nothing in `backend/app/services/processing/pipeline.py` runs and no FastAPI endpoint could ever call it.
2. **No API layer wires backend to frontend.** There is no FastAPI `main.py` and no route definitions. The frontend's "Run Synchronization & Feature Extraction" button has no `onClick`. A user *cannot* submit files from the GUI to the pipeline; the GUI is purely decorative.
3. **No dependency manifests.** `scipy`, `pandas`, `numpy`, `sqlalchemy`, `fastapi`, `uvicorn`, `pydantic` are all implicitly required but nothing declares them. Neither `pip install -r requirements.txt` nor `npm install` works.
4. **The dashboard renders hardcoded numbers.** The HRV table in `PostHocDashboard.tsx` uses literals — 134.16, 330.57, 57.13 for baseline and 45.22, 110.12, 95.40 for "Stress Task". A demo viewer that lies about the data is worse than one that shows a blank state.
5. **No file-upload state or handlers.** The file-upload zones in the dashboard use dashed borders and placeholder text but no `onDragOver`/`onDragLeave`/`onDrop` handlers. The `<input type="file">` for markers has no `onChange`. Selecting a file does nothing.
6. **The StartPage "Create Session" button is a dead end.** No submit handler, no navigation, no state-lifting to the dashboard; the two pages are disconnected.
7. **`db/models.py` has no session-maker or migration.** SQLAlchemy `Project` and `Session` tables are declared but never created at startup; no Alembic; no `sessionmaker`. If a route tried to use them it would fail at runtime.
8. **Circular-looking feature-extraction risk in `compute_rolling_features`.** Every rolling window calls `compute_edr`, which itself re-runs the entire RR-extraction and Welch/bandpass pipeline. For a 1-hour session at 5 s stride this is ~700 windows × full re-extraction — O(n²) cost for no reason. A single resample once, then per-window peak-find, would be the right refactor.
9. **`_filter_ectopic` is too aggressive.** The Lipponen & Tarvainen (2019) note in the docstring is honest about the simplification, but a flat 30% threshold from local median will drop genuine sinus arrhythmia during slow breathing. A proper Malik or adaptive threshold is a small change and the note already flags it.
10. **`clean.py` range-filters EDA in the input dataframe but the sync step merges on `timestamp_ms`, which `clean_signals` does not preserve across winsorization.** The winsorize step clips HR and EDA to 5th/95th percentiles but this silently compresses the dynamic range — a legitimate high-stress spike of 120 BPM becomes clipped to (say) 95. For a tool marketed as "Kubios-parity", winsorizing the physiologically real signal is scientifically suspect; it should be a post-extraction robustness check, not a pre-extraction transform.
11. **`synthetic.py` injects drift with a 0.06% slope (`polar_ts = base * 1.0006 + 125`).** The sync-QC gate in `sync_qc.py` flags drift > 1% as a failure. So the synthetic data this codebase ships with would always pass the gate — useful for happy-path testing, useless as a regression check for the drift-correction path. There is no synthetic dataset that would *fail* the gate.
12. **No Kubios reference export is bundled.** `kubios_benchmark.py` expects a user-supplied Kubios CSV to Bland-Altman against; without one the agreement module is untestable. A small bundled reference export from (say) Kubios HRV Premium run on a published dataset would make the benchmark demonstrable.

## 5. GUI usability — what happens if a user tries to use it

I walked the two pages as a first-time user would. The walk is brief because most actions have no effect.

**StartPage (`ka equivalent ≈ home`).** The page asks for a *Project ID* and a *Subject ID* and shows a "Create Session →" button. Typing text into the inputs updates local React state but nothing leaves the component: clicking the button is a no-op. The amber notice below says "Please ensure your Raw CSVs … are managed in your secure Google Drive … See `docs/GDOCS_SOURCE_MANAGEMENT.md`" — a link that, in the browser, does nothing because `docs/` is not served by a Vite build. A first-time user's most reasonable next action (fill form, click button, see dashboard) fails silently. Against Nielsen's H1 (Visibility of system status), the page is a first-rate violation: after clicking the button, the user sees exactly what they saw before clicking it.

**PostHocDashboard.** Two drag-and-drop zones — "Upload EmotiBit CSV (EDA/Acc)" and "Upload Polar H10 CSV (HR)" — show dashed borders and green placeholder text. Dragging a CSV over either zone produces no visual feedback and no state change; dropping a CSV does nothing. Below, a "Timeline Markers" row has a native `<input type="file">` with no `onChange` handler and a free-text "Or add UTC timestamp manually" field equally disconnected. The big green "Run Synchronization & Feature Extraction" button has no `onClick`. The right-hand QC panel declares "Drift Corrected ✓" and "Overlap Confirmed ✓" with a green "Confidence: Green" pill as static markup — before any data has been uploaded. The chart area is a `[Interactive Charting Area: HR / EDA Overlaid Timeseries]` placeholder. The HRV table below the chart shows pre-populated RMSSD/SDNN/HR/Stress numbers for "Baseline" and "Stress Task" rows. The implication to any user is that *some session has been analysed*, but of course none has: the numbers are JSX literals. Nielsen H1 (status), H2 (match to real world), H5 (error prevention — by giving the user an obvious path to a meaningless result), and H10 (help and documentation) are all failing here.

The top nav has a "Setup New Project" / "Go to Dashboard" button pair that swaps the route. This is the only interaction that works as visibly intended, and it isn't enough.

## 6. Sample Polar H10 and EmotiBit data for testing

The repo ships no sample data. Publicly available sources suitable for a regression-test corpus include:

- **`iitis/Polar-HRV-data-analysis`** — a Python library and a small bundled-example workflow for RR-interval data collected via the Polar Sensor Logger app. The README includes a CSV format spec (timestamp in ms, RR in ms, plus accelerometer columns) that maps one-to-one onto what this repo's `parse_polar_csv` expects; a couple of lines of renaming would make the data loadable. https://github.com/iitis/Polar-HRV-data-analysis
- **`BeaconBrigade/polar-arctic`** — a cross-platform recorder that logs HR, RR, ECG, and IMU from the Polar H10 to CSV. The wiki contains a few example sessions. https://github.com/BeaconBrigade/polar-arctic
- **`RGreinacher/polar-h10-ecg-viewer`** — ECG-grade records (with `participant_id`, `polar_timestamp_s`, `ecg_voltage_uv`). These are ECG streams rather than RR-interval streams and would need a local R-peak detector; useful for stressing the pipeline on native ECG. https://github.com/RGreinacher/polar-h10-ecg-viewer
- **Wearipedia's Polar H10 notebook** has a worked example of extracting HR + RR from the Polar Accesslink API and saving to CSV. https://wearipedia.readthedocs.io/en/latest/notebooks/polar_h10.html
- **`gmaione1098/EmotiData`** — a GitHub repo that bundles EmotiBit CSV sessions from three conditions (relax / gym / run) in the canonical EmotiBit DataParser output format, which produces one file per data type (EDA, accelerometer, temperature, PPG). https://github.com/gmaione1098/EmotiData
- **EmotiBit's official docs** describe the parsed-file layout and sampling rates and link to `Working_with_emotibit_data.md` in the `EmotiBit/EmotiBit_Docs` repo; the canonical schema match for this project's `parse_emotibit_csv` would come from there. https://github.com/EmotiBit/EmotiBit_Docs
- **PhysioNet's Pulse Transit Time PPG Dataset (v1.0.0)** has paired PPG + ECG CSVs from 22 subjects with a standard schema; not Polar H10 specifically but suitable for building an analogous synthetic pair. https://www.physionet.org/content/pulse-transit-time-ppg/1.0.0/csv/

For a first validation corpus I would recommend: (a) a 5-minute baseline record from the Polar H10 via the Polar Sensor Logger app, paired to (b) a 5-minute EmotiBit SD-card export from the same wrist, (c) a 1-minute deliberate arm-motion record for testing the 0.3 g motion gate, and (d) a synthetic pair produced by `synthetic.py` but with the drift amplitude cranked from 0.06% to 2% so the sync-QC gate has a failing case to exercise.

## 7. The ruthless-review prompt — ready to hand to Codex

A ready-to-execute prompt for Codex is at `docs/RUTHLESS_REVIEW_PROMPT_FOR_CODEX_2026-04-20.md`. The short form is:

> You have terminal access to `/Users/davidusa/REPOS/Polar_Emotibit_Analyzer`. Execute the seven probes below in order. Each probe lists concrete commands; output a section per probe with verbatim findings and either a commit closing the gap or an explicit flag escalating to DK. Write your status note to `docs/RUTHLESS_REVIEW_STATUS_POLAR_EMOTIBIT_2026-04-20.md` at the end.
>
> - **Probe 1 — Broken imports.** Run `python3 -c "from app.services.processing import pipeline"` from `backend/`. Capture the `ImportError`. Enumerate every module referenced by a missing import and produce a spec-level stub for each (type hints, docstring, `raise NotImplementedError`) so the import chain succeeds. The five missing modules are `app.schemas.analysis`, `app.models.signals`, `app.services.ai.adapters`, `app.services.processing.sync`, `app.services.processing.stress`, and `app.services.reporting.report_builder`. Stubs go into commits of their own so a reviewer can see the scope separately.
> - **Probe 2 — Dead-file census.** Build a call-graph from `pipeline.py` and from `test_features.py`. Any `.py` under `backend/app/` that is not reachable from either is flagged. Do not delete flagged files; list them in the status note under `§ candidates for removal or wiring` and wait for DK decision.
> - **Probe 3 — Dependency manifest.** Produce a minimum `backend/pyproject.toml` (or `requirements.txt`) that captures every `import` statement across the backend tree, including `scipy`, `pandas`, `numpy`, `fastapi`, `uvicorn`, `pydantic`, `sqlalchemy`. Then `pip install` into a fresh venv and confirm `pytest backend/tests` exits green. Repeat for the frontend: produce `frontend/package.json`, `tsconfig.json`, `vite.config.ts`, `index.html`, and `main.tsx`; confirm `npm install && npm run dev` boots Vite without error.
> - **Probe 4 — Wire the backend to an HTTP surface.** Create `backend/app/main.py` with FastAPI endpoints `POST /api/v1/analyze` (multipart upload of EmotiBit + Polar CSVs), `POST /api/v1/validate/csv/{type}` (schema check only), `POST /api/v1/benchmark/kubios` (Bland-Altman against a user-uploaded Kubios export), and `GET /health`. Include a SQLAlchemy session-maker for `db/models.py` and create tables at startup. Add integration tests that `POST` against the synthetic-generated pair from `synthetic.py`.
> - **Probe 5 — Wire the frontend to the backend.** The `StartPage` "Create Session →" button must lift `projectId`/`subjectId` into a `ProjectContext` and navigate to the dashboard. The `PostHocDashboard` upload zones must implement `onDragOver` / `onDragLeave` / `onDrop` with hover states. The markers `<input type="file">` must have an `onChange` handler. The "Run Synchronization & Feature Extraction" button must `POST` to `/api/v1/analyze` with the three files and render the real response into the existing table shell — **replace the JSX literals** (134.16, 330.57, etc.) with numbers from the API. A loading state (spinner + disabled button) is required. Error states must render the backend's `quality_flags` verbatim, not a generic toast.
> - **Probe 6 — Scientific honesty audit.** Re-read every `V2.1 FIX` docstring block and confirm the fix actually does what the docstring claims. Specifically: (a) does `clean.py` winsorize *after* the motion filter as the docstring claims? (b) does `features.py::compute_hrv_frequency_features` return `None` for bands whose minimum duration is unmet, or does it quietly return a noisy number? (c) does `statistics.py::_mean_ci95` use `scipy.stats.t.ppf(0.975, df=n-1)` rather than a hard-coded `1.96`? Where docstring and code disagree, trust the code and fix the docstring, or trust the docstring and fix the code — whichever matches the cited reference. Land each fix as its own commit, cite the paper in the commit message.
> - **Probe 7 — Sample-data smoke test.** Pull a sample Polar H10 session from `iitis/Polar-HRV-data-analysis` and a sample EmotiBit session from `gmaione1098/EmotiData`. Rename columns to match `parse_polar_csv` / `parse_emotibit_csv` expectations; drop the resulting CSVs into `data/samples/`. Run the pipeline end-to-end and write a short `docs/SAMPLE_DATA_SMOKE_TEST_2026-04-20.md` reporting: synchronized sample count, sync-QC score, RMSSD/SDNN/mean-HR values, and any exception traces. A sample pair that the pipeline can process end-to-end is the minimum bar for "the repo works".
>
> When all seven probes are clean, verdict **CLEAN** or **CLEANED (n fixes landed)**. When any probe surfaces a scope question only DK can decide (e.g., "is the winsorize step scientifically desired or should it be removed?"), escalate under a `§ DK decision needed` heading in the status note. Do not delete modules without DK sign-off; dead-code flagging is separate from dead-code removal.

## 8. Verdict

This is a repo with **a strong documentary core and a dangerously thin execution layer**. The module docstrings cite real papers, understand the failure modes of naive periodograms and z-approximations, and are refreshingly self-critical. But the code that implements those docstrings is an incomplete skeleton: the entry-point function cannot import, the frontend cannot talk to any backend, and the dashboard's green "Confidence" pill is literally a static `<div>` regardless of whether any data has been uploaded. A T4-style redesign here is plausible but premature: the first-order work is to (a) ship the missing modules, (b) wire a minimal FastAPI surface, (c) replace the JSX literals with real API output, and (d) produce a runnable end-to-end example using one of the public Polar-H10 and EmotiBit sample datasets.

Once those four things land, the repo is a candidate for a methodology-focused second review that takes the docstring-level scientific claims (Welch, BH-FDR, the 0.3 g motion threshold, the Lipponen-and-Tarvainen ectopic filter) and audits the numerical behaviour against reference implementations (Kubios HRV Premium; PhysioNet's `pyhrv`). Until then, any review is a review of a spec document, not of running software.

## References

Benedek, M., & Kaernbach, C. (2010). A continuous measure of phasic electrodermal activity. *Journal of Neuroscience Methods, 190*(1), 80–91. https://doi.org/10.1016/j.jneumeth.2010.04.028 — Google cites ≈ 1,700.

Benjamini, Y., & Hochberg, Y. (1995). Controlling the false discovery rate: A practical and powerful approach to multiple testing. *Journal of the Royal Statistical Society: Series B, 57*(1), 289–300. — Google cites ≈ 115,000.

Berntson, G. G., Bigger, J. T., Eckberg, D. L., Grossman, P., Kaufmann, P. G., Malik, M., Nagaraja, H. N., Porges, S. W., Saul, J. P., Stone, P. H., & van der Molen, M. W. (1997). Heart rate variability: Origins, methods, and interpretive caveats. *Psychophysiology, 34*(6), 623–648. https://doi.org/10.1111/j.1469-8986.1997.tb02140.x — Google cites ≈ 5,600.

Boucsein, W., Fowles, D. C., Grimnes, S., Ben-Shakhar, G., Roth, W. T., Dawson, M. E., & Filion, D. L. (2012). Publication recommendations for electrodermal measurements. *Psychophysiology, 49*(8), 1017–1034. https://doi.org/10.1111/j.1469-8986.2012.01384.x — Google cites ≈ 2,400.

Greco, A., Valenza, G., Lanata, A., Scilingo, E. P., & Citi, L. (2016). cvxEDA: A convex optimization approach to electrodermal activity processing. *IEEE Transactions on Biomedical Engineering, 63*(4), 797–804. https://doi.org/10.1109/TBME.2015.2474131 — Google cites ≈ 950.

Kleckner, I. R., Jones, R. M., Wilder-Smith, O., Wormwood, J. B., Akcakaya, M., Quigley, K. S., Lord, C., & Goodwin, M. S. (2018). Simple, transparent, and flexible automated quality assessment procedures for ambulatory electrodermal activity data. *IEEE Transactions on Biomedical Engineering, 65*(7), 1460–1467. https://doi.org/10.1109/TBME.2017.2758643 — Google cites ≈ 400.

Lipponen, J. A., & Tarvainen, M. P. (2019). A robust algorithm for heart rate variability time series artefact correction using novel beat classification. *Journal of Medical Engineering & Technology, 43*(3), 173–181. https://doi.org/10.1080/03091902.2019.1640306 — Google cites ≈ 300.

Nielsen, J. (1994). Enhancing the explanatory power of usability heuristics. In *CHI '94 Proceedings* (pp. 152–158). https://doi.org/10.1145/191666.191729 — Google cites ≈ 2,400.

Shaffer, F., & Ginsberg, J. P. (2017). An overview of heart rate variability metrics and norms. *Frontiers in Public Health, 5*, 258. https://doi.org/10.3389/fpubh.2017.00258 — Google cites ≈ 4,000.

Task Force of the European Society of Cardiology and the North American Society of Pacing and Electrophysiology. (1996). Heart rate variability: Standards of measurement, physiological interpretation, and clinical use. *Circulation, 93*(5), 1043–1065. — Google cites ≈ 22,000.

Welch, P. D. (1967). The use of fast Fourier transform for the estimation of power spectra. *IEEE Transactions on Audio and Electroacoustics, 15*(2), 70–73. https://doi.org/10.1109/TAU.1967.1161901 — Google cites ≈ 13,000.

## Sources

- [iitis/Polar-HRV-data-analysis](https://github.com/iitis/Polar-HRV-data-analysis)
- [BeaconBrigade/polar-arctic](https://github.com/BeaconBrigade/polar-arctic)
- [RGreinacher/polar-h10-ecg-viewer](https://github.com/RGreinacher/polar-h10-ecg-viewer)
- [Wearipedia — Polar H10](https://wearipedia.readthedocs.io/en/latest/notebooks/polar_h10.html)
- [gmaione1098/EmotiData](https://github.com/gmaione1098/EmotiData)
- [EmotiBit/EmotiBit_Docs — Working with data](https://github.com/EmotiBit/EmotiBit_Docs/blob/master/Working_with_emotibit_data.md)
- [PhysioNet — Pulse Transit Time PPG v1.0.0](https://www.physionet.org/content/pulse-transit-time-ppg/1.0.0/csv/)
- [polarofficial/polar-ble-sdk — Polar H10 product doc](https://github.com/polarofficial/polar-ble-sdk/blob/master/documentation/products/PolarH10.md)

# Ruthless-review prompt for Codex — Polar-Emotibit Analyzer

*Date*: 2026-04-20
*Requested by*: DK
*Target*: `/Users/davidusa/REPOS/Polar_Emotibit_Analyzer`
*Authority*: terminal access to DK's Mac; git commit + push to this repo; no SSH needed
*Companion audit*: `docs/RUTHLESS_REVIEW_AUDIT_2026-04-20.md`

---

## Your job

Turn this half-built scaffold into a repo that runs end-to-end. The call-graph audit in `docs/RUTHLESS_REVIEW_AUDIT_2026-04-20.md` shows that the declared pipeline (`backend/app/services/processing/pipeline.py`) cannot import because five modules are missing, that the frontend's buttons have no handlers and its dashboard shows hardcoded numeric literals, and that the only code currently exercised is three pytest functions in `backend/tests/test_features.py`. Your remit is the seven probes below. Execute them in order; each has concrete commands and a clear verdict condition. Write your progress to `docs/RUTHLESS_REVIEW_STATUS_POLAR_EMOTIBIT_2026-04-20.md` as you go, one section per probe, commit after each probe. Do not batch; a reader should be able to see the landing of each probe independently.

## Ground rules

1. **Commit attribution**: `--author="Codex <codex@openai.com>"` on every commit. Commit messages lead with `Polar-Emotibit probe N:` and a one-line subject; use the body for reasoning and the paper citation where a fix is scientific.
2. **No `rm -rf`, no `git push --force`, no `git reset --hard` without asking DK.** Dead files get *flagged* in the status note under `§ candidates for removal or wiring`; they are not deleted without DK sign-off.
3. **Scientific fixes carry citations** in the commit message. If a fix changes behaviour prescribed by a paper, cite the paper.
4. **Escalate**, don't guess, on scope questions: "is the winsorize step scientifically desired?" is a DK decision, not yours. Put those in `§ DK decisions needed` and move on.
5. **Every probe ends in a runnable state.** After probe 1 the imports resolve; after probe 3 `pytest` passes in a fresh venv; after probe 4 `curl localhost:8000/health` returns 200; after probe 5 the dashboard submits a real file. If a probe's end state is broken, either fix it or roll back before committing.

## Probe 1 — Unbreak the pipeline's imports

Run this from `backend/`:

```bash
cd /Users/davidusa/REPOS/Polar_Emotibit_Analyzer/backend
python3 -c "from app.services.processing import pipeline" 2>&1 | head -20
```

You will see an `ImportError` on one of five absent modules. Enumerate them all by repeatedly running the command, fixing one at a time. The five known-absent modules are:

| Module path | Must export |
|---|---|
| `app/schemas/analysis.py` | `AnalysisResponse`, `FeatureSummary`, `BlandAltmanMetric` (pydantic BaseModel classes) |
| `app/models/signals.py` | `DriftModel`, `PiecewiseDriftModel` (pydantic or dataclass) |
| `app/services/ai/adapters.py` | `NON_DIAGNOSTIC_NOTICE` (a string constant) |
| `app/services/processing/sync.py` | `synchronize_signals(emotibit_df, polar_df) -> pd.DataFrame` |
| `app/services/processing/stress.py` | `STRESS_SCORE_LABEL` (str), `compute_stress_score(rmssd_ms, mean_hr_bpm, eda_mean, eda_phasic) -> float` |
| `app/services/reporting/report_builder.py` | `build_markdown_report(summary, flags) -> str` |

For each absent module: write a **spec-level stub** with full type hints, a docstring that explains what the real implementation would do, and either a naive correct implementation (preferred) or `raise NotImplementedError` with a clear message (acceptable for the scoring/reporting modules). The goal is that `from app.services.processing import pipeline` succeeds; the pipeline's runtime behaviour with stub bodies can be deferred to probe 4.

For `synchronize_signals` specifically: the correct naive implementation is a `pandas.merge_asof` keyed on `timestamp_ms` with a tolerance of `1000` ms, producing a single dataframe with both sources' columns. The docstring should note that `merge_asof` is O(n log n), requires pre-sorted input (which `parsers.py` already guarantees), and that the merge tolerance is conservative; production use would probably want per-device resampling to a common grid first.

Land each module as its own commit (`Polar-Emotibit probe 1a: app.schemas.analysis stub`, `... 1b: app.models.signals`, ...). Final probe-1 commit: `Polar-Emotibit probe 1: pipeline imports resolve end-to-end` with body listing the six new modules.

## Probe 2 — Dead-file census

Build the reachability set from two entry points:
1. `backend/app/services/processing/pipeline.py::run_analysis`
2. `backend/tests/test_features.py` (every test function)

Use `grep -R "from app" backend/app/` and `grep -R "import app" backend/app/` to walk the call graph, or use `pydeps` / `snakeviz` if installed. For each `.py` file under `backend/app/`, classify as:

- **Live** — reachable from at least one entry point.
- **Orphan (will-be-live)** — not reachable now but is being wired by probe 4 (FastAPI HTTP layer).
- **Orphan (speculative)** — cannot be placed in either category above.

Write a `§ File reachability` table to the status note. Do not delete any file; DK decides after seeing the table. The expected orphans are `app/services/ingestion/parsers.py`, `app/services/ingestion/synthetic.py`, `app/services/processing/benchmark.py`, `app/services/processing/kubios_benchmark.py`, `app/services/processing/statistics.py`, and `app/db/models.py` — all of which should transition to "live" once probe 4 wires HTTP routes around them.

## Probe 3 — Dependency manifests

Backend: produce `backend/pyproject.toml` (or `backend/requirements.txt`) listing every third-party module actually imported anywhere under `backend/`. The audit in `docs/RUTHLESS_REVIEW_AUDIT_2026-04-20.md` lists the ones I spotted; double-check by running:

```bash
grep -hR "^import\|^from" backend/app/ backend/tests/ | grep -v "^from app\|^import app" | sort -u
```

Pin minor versions. Then:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt    # or: pip install -e .
python3 -m pytest tests -q
```

The three tests in `test_features.py` must all pass. Commit `Polar-Emotibit probe 3a: backend dependency manifest + green pytest`.

Frontend: produce the missing build-system files. `frontend/package.json` with React 18, Vite 5, TypeScript 5; `frontend/tsconfig.json`; `frontend/vite.config.ts`; `frontend/index.html`; `frontend/src/main.tsx` that mounts `App` into `#root`. Then:

```bash
cd frontend
npm install
npm run build
```

Build must succeed. Commit `Polar-Emotibit probe 3b: frontend build system`.

## Probe 4 — Wire a minimum FastAPI surface

Create `backend/app/main.py` with:

```python
from fastapi import FastAPI
# ... add CORS middleware permitting http://localhost:5173 for local dev
app = FastAPI(title="Polar-Emotibit Analyzer", version="2.1")
# include routers (below)

@app.get("/health")
def health(): return {"ok": True, "version": "2.1"}
```

Then add routers at `backend/app/api/v1/`:
- `POST /api/v1/validate/csv/emotibit` — multipart upload of one CSV, runs `parse_emotibit_csv`, returns `{valid, n_rows, columns_present}` or 422 with the validation error.
- `POST /api/v1/validate/csv/polar` — same for Polar.
- `POST /api/v1/analyze` — multipart upload of both CSVs, runs `pipeline.run_analysis`, returns the `AnalysisResponse` pydantic model as JSON. Integration test: POST the pair produced by `synthetic.generate_synthetic_session(seconds=180)` serialised to CSV-in-memory.
- `POST /api/v1/benchmark/kubios` — multipart upload of system export + Kubios export + `join_col` query param; runs `compare_with_kubios`; returns the Bland-Altman list.

Wire `app/db/models.py`: on startup, create a SQLAlchemy engine against `sqlite:///data/polar_emotibit.db`, call `Base.metadata.create_all`, and inject a session-maker dependency into the analyze route that inserts a `Session` row after each successful analysis.

Add `backend/tests/test_api.py` with:
- `test_health_returns_200`
- `test_analyze_on_synthetic_pair_returns_feature_summary`
- `test_analyze_missing_required_column_returns_422`
- `test_benchmark_rejects_mismatched_lengths`

Run `pytest` and confirm all tests (old + new) pass. Start `uvicorn app.main:app --reload` and verify `/health`, `/docs`, and one `POST /api/v1/analyze` work end-to-end via `curl` or `httpie`. Commit `Polar-Emotibit probe 4: FastAPI HTTP surface + integration tests`.

## Probe 5 — Wire the frontend to the backend

`StartPage.tsx`:
- The `onChange` handlers on the two inputs already update local state. Good.
- The "Create Session →" button needs an `onClick` that:
  - Validates `projectId` non-empty and `subjectId` non-empty; show inline errors otherwise.
  - Lifts state into a `ProjectContext` (`React.createContext`) mounted in `App.tsx`.
  - Sets `App`'s `route` to `'dashboard'`.
- Wrap both inputs in proper `<label>` elements so screen readers work (Nielsen H10).

`PostHocDashboard.tsx`:
- Replace the two `<div>`-with-dashed-border drop zones with components that wire `onDragOver`, `onDragLeave`, and `onDrop`. On drop, capture `e.dataTransfer.files[0]`, stash into state, and POST to `/api/v1/validate/csv/{emotibit|polar}` for instant schema feedback. Render the validation response inline.
- The markers `<input type="file">` needs an `onChange`.
- The "Run Synchronization & Feature Extraction" button needs an `onClick` that:
  - Builds a `FormData` with the two CSVs + the markers file (if any).
  - POSTs to `/api/v1/analyze`.
  - Shows a loading state (spinner + disabled button).
  - On response, replaces the hardcoded RMSSD/SDNN/HR/Stress literals with real numbers from the response's `feature_summary`.
  - On non-200, renders `response.quality_flags` inline; do NOT show a generic toast.
- The QC confidence pill and the chart area must also read from the response, not from JSX literals. If the chart area is out of scope for this probe, render "No chart yet — full charting in probe 6" rather than the misleading `[Interactive Charting Area]` placeholder.

Confirm with the existing `npm run dev` + `uvicorn` pair that a user can start the Vite dev server, fill the start form, click through, drop the synthetic-sample pair that the tests produce (or any of the sample CSVs from probe 7), click Run, and see real numbers populate the table. Commit `Polar-Emotibit probe 5: frontend→backend wiring + hardcoded literal replacement`.

## Probe 6 — Scientific honesty audit

Re-read every `V2.1 FIX` block in the processing modules. For each claimed fix, **verify the code matches the docstring**. Three specific audits:

6a. `clean.py` claims processing order is range → motion → winsorize. Read the code: is winsorize *after* motion filter? If the docstring says "V2.1 fixed the order from winsorize-before-motion to motion-before-winsorize", confirm that's what the code actually does. Commit a fix to whichever of (code, docstring) is wrong.

6b. `features.py::compute_hrv_frequency_features` claims to return `None` for bands whose minimum duration is unmet (VLF ≥ 300 s, LF ≥ 120 s, HF ≥ 60 s). Write a unit test that feeds a 60-second RR sequence and confirms VLF and LF are `None` while HF is a number.

6c. `statistics.py::_mean_ci95` claims to use `scipy.stats.t.ppf(0.975, df=n-1)` rather than a hard-coded `1.96`. Write a unit test that confirms at n=10 the margin is wider than 1.96·σ/√n. The expected t-critical at df=9 is 2.262; if the code returns 1.96, that is a bug and a regression.

Each fix lands as its own commit with a cited reference (Welch 1967; Task Force 1996; Shaffer & Ginsberg 2017; Boucsein et al. 2012; Kleckner et al. 2018; Lipponen & Tarvainen 2019). Commit `Polar-Emotibit probe 6: scientific honesty audit + unit tests`.

## Probe 7 — Sample-data smoke test

The repo ships no sample data. Pull one session per device from public sources:

- Polar H10: clone `iitis/Polar-HRV-data-analysis` into `/tmp`; pick one session from its examples; rename columns so the CSV has `timestamp_ms`, `hr_bpm`, and `rr_ms`. Drop to `data/samples/polar_sample_01.csv`.
- EmotiBit: clone `gmaione1098/EmotiData`; pick one "relax" session; run EmotiBit DataParser if necessary; merge the EDA file and the accelerometer file on timestamp; rename columns to `timestamp_ms`, `eda_us`, `acc_x`, `acc_y`, `acc_z`. Drop to `data/samples/emotibit_sample_01.csv`.

**Inspect the licenses first.** Both repos appear MIT-licensed but verify before committing data; if a license is restrictive, store only a `data/samples/README.md` with fetch instructions and a `.gitignore` for the actual CSVs.

Run the pipeline end-to-end against the sample pair via the analyze endpoint. Write `docs/SAMPLE_DATA_SMOKE_TEST_2026-04-20.md` with:
- Polar and EmotiBit provenance (repo, path, license)
- Raw n_rows for each
- Pipeline output: `synchronized_samples`, `sync_qc_score`, `sync_qc_gate`, `rmssd_ms`, `sdnn_ms`, `mean_hr_bpm`, `eda_mean_us`, `stress_score`
- Any exception traces (or "clean run" if none)
- Time-on-wall for the analyze call (`time curl ...`)

A successful smoke test is the first time the repo has demonstrably processed real data. Commit `Polar-Emotibit probe 7: end-to-end smoke test on public sample pair`.

## Verdict line

When all seven probes are green, write the status note's final verdict as one of:
- **CLEAN** — no defects beyond what DK explicitly deferred.
- **CLEANED (n fixes landed)** — the common outcome; list hashes.
- **BLOCKED (reason)** — if a probe can't finish without DK input; quote the blocker.

Post a plain-text summary to DK: "Polar-Emotibit review complete. Status at docs/RUTHLESS_REVIEW_STATUS_POLAR_EMOTIBIT_2026-04-20.md. Verdict: …"

## What this review is not

- Not a full numerical validation against Kubios. That is probe 7-adjacent future work; this review's bar is "the repo runs end-to-end on one sample pair" not "the repo's RMSSD matches Kubios HRV Premium to within 1 ms bias and 5 ms LoA".
- Not a UX redesign of the dashboard. Replacing the hardcoded literals in probe 5 gets the dashboard to "honest", not to "beautiful". A proper redesign is a follow-up project.
- Not a security hardening pass. The analyze endpoint as specced accepts multipart uploads without authentication; that is deliberate for localhost development and should NOT be exposed to the public internet without an auth layer, which is out of scope for this review.

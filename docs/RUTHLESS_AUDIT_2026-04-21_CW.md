# Ruthless audit — Polar-Emotibit Analyzer, second pass

**Date**: 2026-04-21
**Auditor**: CW
**Previous pass**: `docs/RUTHLESS_REVIEW_AUDIT_2026-04-20.md` (7 probes, all closed)
**Repo tip at audit start**: `b995da0` (chore: update .gitignore)

Second ruthless pass, broader and data-driven. 18 probes across 6 dimensions. Each probe cites the command or file + line where the evidence was produced. Findings sorted P0 (blocker) / P1 (priority fix) / P2 (deferred).

---

## Summary

- **D1 Build & runtime**: 4/4 probes pass. Repo installs, pytest is green, TypeScript strict compiles, Vite builds. Good baseline.
- **D2 API contract integrity**: 1/3 pass. **Only 1 of 8 endpoints has `response_model`**; untyped dicts leak through the OpenAPI surface for the other 7.
- **D3 Data plausibility**: **P0 — `rr_source` mislabel**. The sync step silently synthesises `rr_ms = 60000/hr_bpm` when the input has no native RR, then `compute_hrv_features` looks at the merged dataframe, sees `rr_ms` present, and reports `rr_source = "native_polar"` plus the quality flag "HRV computed from native Polar H10 RR intervals (research-grade)". Same label fires whether or not any native RR ever entered the pipeline.
- **D4 Analytics catalog integrity**: 22 entries vs README's claim of 21 (minor drift); **P1 — glossary fully orphaned**, 23 definitions shipped and zero references from the rest of the frontend.
- **D5 Frontend correctness**: ChartRenderer has 12 empty-data branches and 2 `isFinite` checks but **zero `NaN` checks**; 1 chart-kind case (`phase_comparison`) in renderer with no catalog entry (dead code).
- **D6 Endpoint edge cases**: **P0 — empty-CSV returns HTTP 200** with default feature values including `stress_score: 0.5`; NumPy `RuntimeWarning: Mean of empty slice` on the same path; 1-row inputs succeed with RMSSD silently zero.

**P0 count**: 2 (rr_source mislabel; empty-CSV → 200 with stress_score 0.5)
**P1 count**: 4 (response_model gap; glossary orphaned; 1-row degenerate success; NaN guard gap)
**P2 count**: 3 (phase_comparison dead case; hardcoded colour literals; README entry-count drift)

## Probes and evidence

### D1. Build & runtime

**P1.1 — Backend deps install and import.**  `python3 -c "import fastapi, pandas, scipy, pydantic, numpy, sqlalchemy"` → OK with fastapi 0.136.0, pandas 2.3.3, scipy 1.15.3, pydantic 2.13.2, numpy 2.2.6, sqlalchemy 2.0.49. **Pass.**

**P1.2 — Backend pytest green.**  `python3 -m pytest tests/ -q` → `12 passed in 1.49s`. **Pass.**

**P1.3 — Frontend TypeScript strict.**  `npx tsc --noEmit` → clean, zero errors. **Pass.**

**P1.4 — Frontend Vite build.**  `npx vite build` → `41 modules transformed. dist/index.html 0.38 kB ... dist/assets/index.js 256 kB ... built in 596ms`. **Pass.**

### D2. API contract integrity

**P2.1 — Response models on every endpoint.**  8 endpoints registered on `app.routes`: `/health`, `/api/v1/analyze`, `/api/v1/sessions`, `/api/v1/sessions/{id}`, `/api/v1/benchmark/kubios`, three `/api/v1/validate/csv/*`. Only `/api/v1/analyze` carries `response_model=AnalysisResponse` (`app/api/v1/routes/analysis.py:71`). The other 7 return untyped `dict`s. **P1 — document-and-type the other seven.** Fix template:

```python
# app/schemas/analysis.py
class HealthResponse(BaseModel):
    ok: int; version: str; scope: str

class SessionListResponse(BaseModel):
    sessions: list[SessionStub]

# app/main.py
@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse: ...
```

**P2.2 — Pydantic roundtrip on example data.**  `run_analysis(synthetic)` → `AnalysisResponse.model_dump()` produces valid JSON (confirmed by running through `TestClient.post('/api/v1/analyze')` and reading `r.json()`). **Pass on the happy path.**

**P2.3 — Frontend/backend type alignment.**  `frontend/src/api.ts` defines response types that mirror `AnalysisResponse`, but because 7 of 8 endpoints lack `response_model`, the OpenAPI schema is empty for those paths. No automated alignment check possible. **P1 — blocked by P2.1.**

### D3. Data plausibility

**P3.1 — Synthetic generator output ranges.**  `generate_synthetic_session(seconds=900)` → EDA mean 2.81 µS (SD 0.18), resp 14.3 bpm (SD 1.0), HR 77.0 bpm (SD 2.8), acc_z 1.00 (gravity). All physiologically plausible for a healthy at-rest adult. **Pass on ranges.**

But the sampling rates are off: synthetic EDA is 1 Hz (900 samples / 900 s) while real EmotiBit samples at 15 Hz. Synthetic Polar is 1 Hz with `hr_bpm` instead of real Polar's RR intervals sampled at each heartbeat. **P2 — doc drift; not a bug but means the synthetic data does not exercise the 15× replication handling in `features.py:55-64`.**

**P3.2 — Full pipeline output on synthetic.**  `run_analysis(emo, polar)` → `rmssd_ms=16.1`, `sdnn_ms=28.3`, `mean_hr_bpm=77.0`, `eda_mean_us=2.81`, `stress_score=0.29`. All plausible for at-rest. VLF/LF/HF bands however are 1–2 orders of magnitude below typical published ranges (`vlf=4.6 lf=21.8 hf=46.0` ms² vs typical hundreds to thousands), because the derived-from-HR RR chain produces an over-smoothed signal.

**P3.3 — `rr_source` mislabel (P0).**  **Scenario A**: polar frame has only `hr_bpm`. `sync.py:64` adds `merged["rr_ms"] = 60000.0 / merged["hr_bpm"]`. Downstream `compute_hrv_features` at `features.py:64` reads `if "rr_ms" in df.columns:` → True, so it returns `(rr, "native_polar")`. Output: `rr_source: native_polar`, RMSSD 16.1 ms, quality flag "HRV computed from native Polar H10 RR intervals (research-grade)". **Scenario B**: polar frame has `rr_ms` injected from `rng.normal(850, 40)` — genuine variability. Output: `rr_source: native_polar`, RMSSD 53.3 ms, same quality flag.

The label is the same in both scenarios; the RMSSD differs by 3.3×. A user cannot tell from the output whether they received native-quality HRV or arithmetically-derived HRV. **P0 — research integrity bug.**

Proposed fix (one-line): change `sync.py:64` to not add the derived `rr_ms` column at all. Let `features.py` detect the absence and call `_rr_from_hr` directly, returning the honest label `derived_from_bpm`. Alternative: tag the synthesised column with an attribute so `compute_hrv_features` can tell the difference.

### D4. Analytics catalog integrity

**P4.1 — Catalog entry count.**  22 entries (`ns-01` through `ns-06`, `dg-01` through `dg-05`, `q-s-01` through `q-s-07`, `q-d-01` through `q-d-04`). README claims 21. **P2 — doc drift.**

**P4.2 — Chart-kind coverage.**  15 chart kinds used by catalog entries, 16 handled by `ChartRenderer.tsx`. Extra renderer case: `phase_comparison`. **P2 — dead code; either wire an entry to use it or delete the case.**

**P4.3 — Glossary reach.**  `src/analytics/glossary.ts` exports `lookupGlossary(term)` and `allGlossaryTerms()`; `grep -R 'from.*glossary' src/` returns no matches outside glossary.ts itself. The 23 carefully-written entries (RMSSD, SDNN, mean HR, RR interval, VLF/LF/HF, LF/HF ratio, PSD, tonic SCL, phasic EDA, EDA, stress composite, sync-QC score/band/gate, drift slope, movement-artifact ratio, ectopic beat, tachogram, Bland-Altman, Kubios, non-diagnostic notice) render nowhere. **P1 — wire glossary tooltips into caption / howToRead / architecturalMeaning text, or delete the module.**

### D5. Frontend correctness

**P5.1 — Empty-data handling in ChartRenderer.**  12 empty-data branches, 10 `.length === 0` guards, 2 `isFinite` checks, **0 `isNaN` or `Number.isNaN` checks** in `src/analytics/ChartRenderer.tsx`. If the pipeline emits `NaN` (e.g., empty denominator in an EDA phasic calculation), the chart will pass `NaN` to SVG coordinates. **P1 — add a single `sanitize(value)` helper that returns `null` for NaN/∞ and use it at every chart's numeric entry point.**

**P5.2 — Hardcoded colour literals.**  20+ hex colour codes in `ChartRenderer.tsx` rather than CSS variables. Makes theme work awkward. **P2 — pull into a palette module or CSS custom properties.**

### D6. Endpoint edge cases

**P6.1 — Empty CSV returns 200.**  `POST /api/v1/analyze` with header-only CSVs (`timestamp_ms,eda_us\n` and `timestamp_ms,hr_bpm\n`) + all required form fields → **200** with `synchronized_samples=0`, `stress_score=0.5`, `sync_qc_gate="NO GO"`, `rr_source="derived_from_bpm"`, NumPy runtime warnings `Mean of empty slice` and `invalid value encountered in scalar divide`. The gate flag is correct but the status code is not. A client that trusts 200 as "analysis succeeded" reads the response and sees `stress_score: 0.5` — a default middle value — and may record it.

**P0** — either return 422 with an explicit `{"detail": "insufficient samples"}` or return 200 with an explicit `analyzable: false` field that the frontend can check before rendering any chart. Current behaviour mixes the two: success code, NO-GO gate, zero-valued features. Should pick one story.

**P6.2 — 1-row input returns 200 with RMSSD=0.**  `POST /api/v1/analyze` with single-sample CSVs → **200**, `rmssd_ms=0.0`, `sdnn_ms=0.0`, `mean_hr_bpm=72.0`. RMSSD from one sample is undefined (it's `sqrt(mean(diff^2))` of an empty diff array), not 0. **P1 — minimum-sample guard; compute features or explicitly return `rmssd_ms: null` when n < k for some prespecified k (3 or 10 beats).**

**P6.3 — Malformed input handled correctly.**  Wrong columns → 422 with `"EmotiBit missing required columns: ['eda_us', 'timestamp_ms']"`. Binary junk → same 422. **Pass.**

### D7. Research-integrity cross-checks

**P7.1 — Chung et al. (2026) validation claim.**  README: "Validated against Kubios HRV Premium (Chung et al., 2026: r > 0.99, MAE < 1 bpm)." `docs/EXECUTION_LOG_2026-04-20.md` documents a `scripts/chung2026_to_polar_schema.py` that converts Chung's IBI file to the Polar schema, and `docs/CW_FOLLOWUP_STATUS_2026-04-20.md` line 65 reports "MAE 0.062 bpm" from reproducing Chung et al. But no test or benchmark is automated against the dataset; the claim rests on a single one-off reproduction documented in prose. **P1 — automate the Chung reproduction as a pytest fixture** (requires downloading one participant from the OSF WYM3S deposit). **See also: this audit's next pass uses real Polar data, per DK's directive.**

**P7.2 — Non-diagnostic notice surfaces.**  `app/services/ai/adapters.py` exports `NON_DIAGNOSTIC_NOTICE`. `AnalysisResponse.non_diagnostic_notice` is in every `/analyze` response body. Frontend renders it on result pages (`AnalyticDetailPage.tsx`, `ResultsCoverPage.tsx`). **Pass.**

---

## Priority-ordered fix list

| ID | Severity | Probe | Fix |
|----|----------|-------|-----|
| F1 | **P0** | P3.3 | Fix `rr_source` mislabel: make `sync.py` not create a derived `rr_ms` column, or tag it so `features.py` returns `derived_from_bpm` honestly. Update the quality-flag text to match. |
| F2 | **P0** | P6.1 | Empty-CSV handling: either 422 on zero samples, or add `analyzable: bool` to `AnalysisResponse` and make 200 mean "endpoint ran" not "analysis succeeded". |
| F3 | P1 | P2.1 | Add `response_model` to the seven untyped endpoints + corresponding Pydantic response classes in `schemas/analysis.py`. |
| F4 | P1 | P4.3 | Wire `lookupGlossary` into ChartRenderer captions so jargon in prose is tooltippable, or delete the orphaned module. |
| F5 | P1 | P5.1 | Add a NaN sanitiser to ChartRenderer numeric inputs. |
| F6 | P1 | P6.2 | Minimum-sample-count guard on `compute_hrv_features`; return `null` rather than 0.0 when n < threshold. |
| F7 | P1 | P7.1 | Automate Chung et al. (2026) reproduction as a pytest fixture; currently substantiated only in prose notes. |
| F8 | P2 | P4.1 | README says 21 analytics; catalog has 22. Sync. |
| F9 | P2 | P4.2 | Dead `phase_comparison` case in ChartRenderer — wire or delete. |
| F10 | P2 | P5.2 | Hex colour literals → CSS variables. |
| F11 | P2 | P3.1 | Synthetic generator sampling rates don't match hardware (EDA 1 Hz vs 15 Hz real). Either document as "nominal rate" or upsample the generator. |

## Next pass — real Polar H10 data

This audit used the synthetic generator. DK has asked for a pass with real Polar data from the Chung et al. (2026) OSF WYM3S deposit (or equivalent public Polar H10 CSV). That pass is queued as `docs/RUTHLESS_AUDIT_2026-04-21_CW_REAL_DATA.md`; running it is the immediate next step.

---

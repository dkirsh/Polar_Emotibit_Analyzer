# Ruthless review execution — Polar-Emotibit Analyzer

*Date*: 2026-05-01  
*Prompt used*: `docs/RUTHLESS_REVIEW_PROMPT_2026-05-01.md`

## Findings

### P1 — The respiration page overstates signal provenance when RR is not native

- **Files**:
  - `frontend/src/analytics/catalog.ts:517-523`
  - `backend/app/api/v1/routes/analysis.py:304-315`
  - `backend/app/services/processing/features.py:572-590`
- **Problem**:
  The new respiration page prose says the views are “derived from the Polar H10 RR series,” and the science note describes EDR extraction from “the RR intervals” without qualification. But the backend payload does not carry the original RR provenance into `extended.edr_proxy`; it stores only `source: "rr_edr_proxy"`. On this repo’s own broader contract, RR may be native Polar RR, raw-ECG-derived RR, or BPM-derived RR. The chart therefore speaks as though the respiration proxy always comes from true beat intervals even when the underlying RR may be a weaker derivative.
- **Why it matters**:
  This is not a cosmetic phrasing issue. It changes how much trust a reader should place in the top waveform and in the resulting stress/arousal interpretation. A BPM-derived RR surrogate is not the same evidential object as native RR.
- **What would make it honest**:
  Carry `rr_source` into `extended.edr_proxy`, surface it on the chart, and make the prose conditional: native RR, raw-ECG-derived RR, and BPM-derived RR should not be described identically.

### P2 — The SVG export fix still depends too heavily on `getBBox()` success

- **File**: `frontend/src/pages/AnalyticDetailPage.tsx:68-80`
- **Problem**:
  The standalone-SVG repair now adds namespaces and corrected geometry, but all of that still lives inside the `try` that depends on `svg.getBBox()`. If `getBBox()` throws, the catch path silently falls back to serializing the clone without the repaired geometry or namespace normalization.
- **Why it matters**:
  The exact defect just fixed can reappear on the failure path: a user may again download a fragment that is not a robust standalone SVG, especially in browser or rendering edge cases.
- **What would make it honest**:
  Move the namespace attributes and minimum standalone normalization outside the `try`, and let only the `viewBox`/width/height recomputation depend on `getBBox()`.

### P2 — Importing the analysis router can rewrite repository data on disk

- **Files**:
  - `backend/app/api/v1/routes/analysis.py:75-80`
  - `backend/app/api/v1/routes/analysis.py:97-122`
- **Problem**:
  Module import loads `session_store.json`, attempts migration, and persists the migrated result immediately. That means a mere import of the route module can mutate tracked repo data as a side effect.
- **Why it matters**:
  This is poor operational hygiene. It makes test runs, local imports, and tooling reads potentially stateful. It also blurs the line between “reading old sessions” and “upgrading old sessions.”
- **What would make it honest**:
  Make migration an explicit command or startup step with a visible log, or at minimum isolate it behind a clear opt-in flag and provenance marker in the stored session.

## Open assumptions

- The visual inspection was done against the live local page and the saved SVG for `alice_1` on `q-s-07`. I did not repeat the same save-and-render procedure for every chart kind.
- I assumed the repo still supports sessions whose RR provenance is not always native, because the broader codebase and prior audits explicitly distinguish those modes.

## Brief state summary

What passed:
- targeted backend tests: `19 passed`
- frontend production build: passed
- live respiration page now shows the top EDR waveform
- saved SVG now renders as a standalone SVG and is no longer clipped in the inspected case

What remains risky:
- respiration provenance is still under-specified at the chart level
- the export fallback path is not fully hardened
- stored-session migration is still too implicit

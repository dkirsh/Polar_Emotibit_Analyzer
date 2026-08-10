# Sprint plan — Polar–EmotiBit Analyzer upgrades (2026-06-06)

This plan operationalizes the recommendations of the June 2026 review. Every
claim of present-state below was measured against the code this session; where my
earlier review was wrong, the correction is noted, because a discrepancy between
a description and the artifact is itself a finding.

## Corrections to the prior review (measured this session)
- **Confidence intervals are already rendered** for the HR and EDA means
  (`frontend/src/analytics/ChartRenderer.tsx:739–740`). The gap is dispersion on
  the *other* metrics and on the timeseries — not CIs in general.
- **A marker editor already exists and is wired in**
  (`frontend/src/components/MarkerEditor.tsx`, mounted at
  `ResultsCoverPage.tsx:99`). The gap is *on-chart* click-to-place, not marker
  editing as such.
- **An RR-derived (ECG) respiration proxy is already a catalogued analytic**
  (`edr_respiration`, catalog id `q-s-07`). The gap is the **direct Vernier belt
  signal**, which is parsed and analyzed but never displayed.

## The defect that anchors Sprint 1 (last-mile)
The Vernier respiration belt is parsed and analyzed (`parse_and_analyze_vernier`),
and the result is written to the session store
(`analysis_core.py:591` → keys `vernier`, `respiratory_patterns`). But
`GET /sessions/{id}` returns a typed `SessionDetail`
(`analysis_core.py:999`, `SessionDetail(**record)`), and `SessionDetail`
(`backend/app/schemas/analysis.py:33`) **declares no `vernier` field**, so
Pydantic silently drops it at the API boundary. The frontend `StoredSession`
type never references it either. Net effect: a researcher who records a
respiration belt gets it computed, persisted, and never shown. Correct
computation, unwritten last mile — the canonical failure mode for this codebase.

---

## Sprint 1 — Surface the Vernier belt (last-mile fix). EXECUTING NOW.
**Goal.** The belt's respiratory summary and any detected stress patterns reach
the results screen. Additive only; no existing analytic changes.

- **1a (backend).** Add `vernier` and `respiratory_patterns` optional fields to
  `SessionDetail`. `get_session` and `update_session_markers` already pass
  `**record`, so the values flow once declared.
- **1b (frontend).** Add the two fields to the `StoredSession` type and render a
  "Respiration (belt)" card on `ResultsCoverPage`: resp. rate (bpm), mean cycle
  duration, mean I:E ratio, breath count, and a list of any detected patterns
  (e.g. tachypnea), with an honest "no belt recorded" empty state.
- **Verification.** A pytest severity test that round-trips a stored record
  through `SessionDetail` and **fails if `vernier` is dropped** (passes only
  while the bug is unfixed → becomes the regression guard). Frontend `tsc
  --noEmit` and `vite build` must stay green.
- **Why first.** Highest value per unit risk: it makes an entire recorded sensor
  visible, it is purely additive, and it is verifiable on both sides without a
  running browser.

## Sprint 2 — Belt respiration waveform + dispersion on all metrics
**Goal.** Turn the belt summary into an inspectable trace and extend uncertainty
display beyond the two means.

- A new `chartKind: "belt_respiration"` in `ChartRenderer.tsx` plotting the
  detrended belt waveform with detected peaks/troughs, plus a per-breath
  rate(bpm) strip; a matching catalogue entry beside `q-s-07` so the direct belt
  sits next to the RR-derived proxy.
- Extend the inference summary so RMSSD, SDNN, and per-phase means carry their
  dispersion (error bars / shaded ranges), per HRV reporting standards
  (Laborde et al., 2017). Backend already returns the inputs for the means;
  add SD/CI for the rest.
- **Verification.** Snapshot the response→chart data binding in a unit test;
  build stays green. Confirm the new analytic appears in `catalog.ts`, renders,
  and survives PDF/CSV export (last-mile invariant for new analytics).

## Sprint 3 — Direct manipulation: zoom, pan, brushing
**Goal.** Move from a reporting surface to an exploratory one
(Shneiderman, 1996: overview, zoom/filter, details-on-demand).

- A reusable pan/zoom layer over the SVG renderer (one transform applied to the
  shared coordinate system) so all timeseries panels gain zoom at once.
- Brushing on the HR/EDA timeseries with linked highlight in the Poincaré plot
  and tachogram, and live recomputation of the brushed-window statistics.
- On-chart click-to-place markers, building on the existing `MarkerEditor` and
  its additive `updateMarkers` path (edits as new records, not overwrites).
- **Verification.** Interaction-logic unit tests (coordinate↔time mapping);
  manual smoke check noted explicitly as "not machine-verified."

## Sprint 4 — EDA decomposition + cohort layer (roadmap-dependent)
**Goal.** Strengthen the arousal science and enable group questions.

- Replace moving-average EDA detrending with model-based decomposition
  (Benedek & Kaernbach, 2010, or cvxEDA: Greco et al., 2016); surface the phasic
  driver beside the raw signal. Keep the old method available and labelled so
  results remain comparable.
- Persist derived intermediates (drift-corrected Polar, synced/cleaned series)
  to a per-session directory with a manifest (input hashes, parameters, code
  version, run id) — provenance is cheap now, expensive to reconstruct later.
- Introduce a local SQLite store (still single-file, no server) for indexed
  cohort queries, and a comparison view with effect sizes (Lakens, 2013).
- **Verification.** Migration is fill-only, dry-run-first, idempotent; a
  reconciler/invariant checks the SQLite copy against the JSON source of truth
  during transition (one ledger per fact).

---

## Discipline applied throughout
Each sprint ends by stating what was **verified this session** (with the command),
what is **stipulated pending calibration**, and what was **not checked** — the
vocabulary the `contracts/` and `docs/` audits depend on. New analytics are not
"done" until they appear in `catalog.ts`, render in `ChartRenderer.tsx`, and
survive export. Fixed bugs leave a regression guard behind.

## References
Benedek, M., & Kaernbach, C. (2010). A continuous measure of phasic electrodermal
activity. *Journal of Neuroscience Methods, 190*(1), 80–91.
Greco, A., Valenza, G., Lanata, A., Scilingo, E. P., & Citi, L. (2016). cvxEDA.
*IEEE TBME, 63*(4), 797–804.
Laborde, S., Mosley, E., & Thayer, J. F. (2017). HRV in psychophysiological
research. *Frontiers in Psychology, 8*, 213.
Lakens, D. (2013). Calculating and reporting effect sizes. *Frontiers in
Psychology, 4*, 863.
Shneiderman, B. (1996). The eyes have it. *Proc. IEEE VL*, 336–343.

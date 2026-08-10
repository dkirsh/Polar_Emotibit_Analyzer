# Analyzer v3 — Wizard architecture, module refactor, and implementation spec

Author: Claude (with D. Kirsh). Status: proposal. This document is written so it
can double as the implementation prompt referenced at the end.

## Motivation
The current app is a two-view, file-only SPA over a single JSON session store.
It analyses one session well but cannot (a) ingest heterogeneous file layouts
reliably, (b) hold a cohort, or (c) run the condition×measure statistics and
comparisons researchers actually want. The week's work (timezone reversals,
schema variants, ns/ms units, second-quantized belt timestamps, email↔ID
mapping, counterbalanced room order, SART order confounds) shows the real
difficulty is **ingestion → canonicalisation → comparison**, not the per-signal
maths. A guided pipeline with a real datastore addresses this.

## Target architecture — five contracted stages + a guided GUI

```
 CONNECT ──► CANONICALISE ──► CLEAN/NORMALISE ──► DEFINE ──► ANALYSE ──► VISUALISE/EXPORT
 (files)     (→ SQLite)       (QC-gated)          (cond×    (stats)     (charts, report)
                                                   measure)
```

Each stage is a pure, contracted module (mirroring the respiratory `signal →
tables → stats → viz → pipeline` package already in the repo) with: typed inputs/
outputs, success conditions, a last-mile verifier, and fail-soft visualisation.

### Stage 1 — CONNECT
Accept any of the known layouts (EmotiBit biometrics 7/8-col, Polar ms/ns,
Vernier xlsx/csv, separate marker files, inline per-row markers, SART trial CSVs,
ZIPERS/survey sheets, condition-assignment rosters). Detect type by header +
magnitude, never by filename alone. Surface every file's detected type and let
the user correct it.

### Stage 2 — CANONICALISE → SQLite (the key new capability)
Adopt the regimentation layer (`scripts/regiment_data.py`) as the app's canonical
store. One local SQLite file (still single-file, no server — respects the
existing constraint) with tables:
- `session(session_id, subject_id, group, date, provenance_json, …)`
- `sample_eda / sample_rr / sample_resp(session_id, t_ms, value…)` — all UTC ms
- `event(session_id, label, onset_ms, offset_ms, source_convention)` — every
  condition/marker normalised to explicit windows regardless of source
  convention (onset/offset, active-until-next, inline, counterbalanced order)
- `roster(subject_id, email, group, condition1, condition2, …)` — the ID↔email↔
  room-order mapping, so email-keyed files bind to subjects authoritatively
- `metric(session_id, window_label, measure, value, qc_flags)` — derived results
Invariants: all timestamps one epoch in ms; every event window inside its
session's span; provenance (file hashes, detected unit/convention) recorded;
idempotent, fill-only writes. **This is the database. It is the fix for the
"different file arrangements" problem.**

### Stage 3 — CLEAN / NORMALISE (QC-gated)
Formalise `clean.py` + `normalization.py` and add the panel-required items:
- Range → motion → winsorize (kept); EDA model-based decomposition
  (Benedek–Kaernbach / cvxEDA) alongside the simple index.
- HRV: Lipponen–Tarvainen correction **plus** an artifact-fraction ceiling
  (~25%) that invalidates HF-band metrics, and a physiological-plausibility gate
  (the wrist-BI "impossible HRV" guard).
- Within-subject normalisation (centring / z / range-correction) as a first-class
  option, not just baseline-window-relative.
- **A QC review screen**: per-subject ectopic %, corrected-fraction, motion-loss,
  plausibility flags — surfaced for human screening before stats. (This is what
  would have caught the bad HRV automatically.)

### Stage 4 — DEFINE (conditions × measures)
A measure registry grouped by aggregator (Stress, Cardiac/HRV, Electrodermal,
Respiratory incl. RespInPeace patterns, Self-report/affect, SART attention). The
user picks conditions (marker groups, with roles: treatment/control/comparison),
the measures, and the contrast (between-condition, restoration = post−pre,
within-subject normalised). Counterbalancing/order is handled here so SART-style
order confounds cannot recur.

### Stage 5 — ANALYSE → VISUALISE/EXPORT
One stats engine over the canonical metrics: paired t / Wilcoxon, Friedman for
3+ conditions, Cohen's dz, CIs, explicit underpowered/multiple-comparison
labels. Visualisations: the existing SVG charts driven generically (paired-slope,
forest of effect sizes, per-pattern bars, heatmaps) + one-click PPTX/PDF/CSV
report in the established style.

## GUI — guided, with escape hatches
A left-rail stepper for the six stages, each showing what it inferred and its
options, with a QC gate between CLEAN and DEFINE. Every step is directly
addressable and re-runnable; an "Expert mode" collapses the rail to the old
two-view flow. Default path is linear; power users are never trapped in it.

## Single-subject mode (first-class)
Group statistics need many subjects, but **debugging encoding/cleaning needs
exactly one.** The pipeline must run end-to-end on a single subject so a
researcher can confirm there are no bugs in unit detection, marker→window
assignment, cleaning, or measure computation before trusting any cohort number.
- Every stage operates per session and is valid at **n = 1**. Only the
  group-statistics part of *Analyse* requires multiple subjects; with one
  subject it returns the per-subject/per-window values (and skips the paired
  test with an explicit "single subject — descriptive only" note), never an
  error.
- A dedicated **Inspect** view (reachable from any stage, and the natural output
  of a one-subject run) shows that subject's **raw vs cleaned signals** overlaid
  (EDA, beat-intervals, respiration), the **detected marker windows shaded on the
  timeline**, the per-window measure values, and the QC flags — so an encoding or
  cleaning bug is visible, not hidden behind an aggregate.
- Backend: `analyse` already emits `per_subject`; add `inspect(session_id)`
  returning raw+cleaned series, windows, and per-window metrics for the Inspect
  view.

## Ingestion confidence — ask for help (a file or an AI) when unsure
File names and CSV columns are not always assemblable into the canonical store
with confidence (we have hit exactly this: email-keyed files vs ID-keyed rosters,
counterbalanced order, typo'd logins). The system must **score its confidence**
and, when low, **stop and request the missing information rather than guess.**
- Canonicalise computes a per-binding confidence (unit detection, marker
  convention, subject↔email↔condition mapping). Below a threshold it returns
  `needs_input` with a typed request: *"Provide a roster/condition-assignment
  file"* or *"Confirm this mapping"*, listing exactly which subjects/columns are
  ambiguous.
- **AI-assisted resolution.** The request panel offers an "Ask AI to help map
  this" action: the user supplies the extra file(s) (a roster sheet, a
  condition-assignment tab, a column key), and an LLM step proposes the
  mapping/columns, which the user confirms before it is written. The mapping is
  recorded in the `roster` table and the run manifest, so it is reusable and
  auditable. Nothing low-confidence is committed without human confirmation.

## Visualization controls — user control over how data is drawn
The Define stage controls *what* is represented (conditions, measures, contrast);
this panel, on the Visualise stage, controls *how* it is drawn. It is driven
generically off the canonical `metric` table and the per-subject values, so no new
computation is needed — chart type and layout are render choices, and raw↔
normalised reuses the existing `within_subject_*` functions.

- **Chart type (per measure).** Paired-slope (default for two within-subject
  conditions), grouped bar with 95% CI, box/violin, raincloud, line time-series,
  or heatmap (pattern × condition). A sensible default is auto-selected from the
  data shape; the user can override per measure.
- **Scaling.** Raw vs within-subject normalised (mean-centred / z / range-
  corrected); linear or log y; axis range auto or fixed; shared vs independent y
  across small multiples.
- **Grouping & layout.** Group/facet by condition, room type, or subject;
  colour-by; sort order (by effect size, by value, or alphabetical); show/hide
  individual-subject overlays; toggle CI/error bars and significance annotations;
  a colour-blind-safe palette switch.
- **Persistence.** Choices are remembered per run and per measure, so reopening
  restores the view, and an exported figure matches exactly what was on screen
  (the chosen options are recorded alongside the export in the manifest).
- **Honest-label guards stay on.** Invalid or sub-minimum values render as "—",
  never imputed; the axis always states raw vs normalised; experimental measures
  (Stress V2) keep their flag regardless of chart type.
- **Fail-soft.** An unsupported chart-type × measure combination falls back to the
  default with a note, never an error (consistent with the Visualise contract).

## Orchestration — "press Go, it runs; pause only when there's a real choice"
The pipeline runs the six stages **automatically and in order once the user says
Go**, and stops to ask only when a stage genuinely needs a human decision.

- **Run modes.** `auto` (default): run every stage to completion, pausing only on
  a stage that reports *pending options*. `step`: run exactly one stage, then
  return for review. `auto-from(stage)` / `rerun(stage)`: resume or redo from a
  point (downstream results are invalidated, superseded not deleted).
- **Stage contract.** Every stage returns a `StageResult` with `status` ∈
  {`ok`, `needs_input`, `failed`, `skipped`}, its outputs, a `qc` summary, and —
  when applicable — an `options` object: a list of decisions each with a chosen
  default and the alternatives. A stage that can proceed on sensible defaults
  returns `ok` with the defaults recorded (auto mode never blocks on those); a
  stage facing a genuine ambiguity returns `needs_input` and the orchestrator
  pauses.
- **Where pauses legitimately happen** (everything else auto-resolves with a
  recorded default): Connect — an unrecognised file type; Canonicalise — an
  ambiguous unit/marker convention or an unmapped email↔subject; Clean — a
  subject failing a QC gate (proceed / exclude / adjust threshold); Define — no
  saved comparison yet (which conditions/measures/contrast); Visualise — never
  pauses (fail-soft).
- **Auto-advance with guardrails.** In `auto`, the orchestrator records the
  chosen default for every auto-resolved decision in the run manifest, so the
  whole chain is auditable and a reviewer can see *what was assumed* and rerun a
  stage with a different choice. A global `pause_before` list lets a user pin
  specific stages to always stop at (e.g. "always let me review Clean").
- **State.** A persisted `WorkflowState` (current stage, per-stage status,
  chosen options, artifact ids, manifest) drives both the API and the wizard, so
  closing and reopening the app resumes exactly where it left off.
- **API surface.** `POST /workflow {mode}` → starts/advances; `GET
  /workflow/{id}` → state + any pending options; `POST /workflow/{id}/resolve`
  → submit option choices and continue; `POST /workflow/{id}/rerun/{stage}`.
  The wizard is a thin client over this.

## Migration discipline
Additive and reversible, per the repo's CLAUDE.md: introduce SQLite alongside the
JSON store (reconciler/invariant during transition — one ledger per fact);
reuse the respiratory package as the template; each stage ships with a contract
in `contracts/` and severity tests; nothing deleted until its replacement is
proven equivalent (supersession).

## Open decisions for the human
1. SQLite as canonical store — confirm (vs keep JSON + a derived analytics DB).
2. Wizard scope — full six-stage guided flow vs guided ingestion only.
3. Build order — ingestion/DB first (highest value) vs stats/viz first.
4. UI design — have Figma generate the wizard, or implement directly in the
   existing React/SVG stack.

---

## Implementation prompt (the "do everything" spec)
> Refactor the Polar–EmotiBit Analyzer into a six-stage, contracted pipeline
> (Connect → Canonicalise → Clean/Normalise → Define → Analyse → Visualise) with
> a guided-but-escapable wizard GUI. Adopt a single local SQLite file as the
> canonical store using the schema in §Stage 2, fed by the format-detecting
> regimentation layer; bind email-keyed files to subjects via the roster table.
> Formalise cleaning/normalisation with the QC review screen and the panel's
> required additions (artifact-fraction ceiling, model-based EDA, within-subject
> normalisation, plausibility gates). Generalise statistics into one engine over
> the canonical `metric` table (paired t / Wilcoxon / Friedman, effect sizes,
> CIs, underpowered + multiple-comparison labels), driven by a measure registry
> grouped by aggregator and a condition editor that encodes counterbalancing.
> Drive the existing SVG charts generically and add one-click PPTX/PDF/CSV report
> export. Orchestrate the six stages so that pressing **Go** runs them
> automatically in order, pausing only when a stage returns `needs_input` (a real
> ambiguity); support `step`, `rerun(stage)`, and a `pause_before` pin list, and
> record every auto-resolved default in an auditable run manifest; persist a
> `WorkflowState` so the run resumes after reload. Mirror the respiratory
> `signal→tables→stats→viz→pipeline` package: each
> stage is a pure module with a contract in `contracts/`, a last-mile verifier,
> fail-soft viz, and severity tests; migrate additively (SQLite beside JSON with a
> reconciler), deleting nothing until proven equivalent. Build order: ingestion/DB
> → clean/QC → stats → viz → wizard shell.
```
```

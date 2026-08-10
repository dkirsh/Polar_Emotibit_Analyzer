# Condition × Measure comparison — design (2026-06-06)

## Goal
Turn the condition editor into the way into the analytic system: pick a measure
(or an aggregator group), pick the conditions, and get a focused contrast of
those conditions under that one measure — with effect size, CI, and the
underpowered-honesty already built into the stats stage. Leads with the **stress**
aggregator; the registry holds all groups.

## What already exists (verified this session)
`room_analysis.compute_room_stats(cleaned_df, markers, ...)` computes, per
marker-defined window and correctly aligned by absolute `timestamp_ms`:
- **Stress/arousal:** `stress_v2` and its 7 channel contributions, `stress_v1`,
  arousal index.
- **Cardiac/HRV:** `mean_hr`, `rmssd`, SD1/SD2, LF/HF (via features).
- **Electrodermal:** `mean_eda` (tonic), `eda_phasic_index`.
- **Respiratory:** `mean_rpm`, `rsa_amplitude` (RR-derived); belt measures via the
  respiratory pipeline.
- **Self-report:** `valence`, `arousal` (from order_affect).
The per-window time series of the same measures exists in `extended.windowed`.

So no new physiology is required — only (a) a measure registry, (b) a per-
condition aggregation keyed to the researcher's marker groups, and (c) the
contrast (reuse `respiratory/stats.py`'s effect-size + CI logic, generalised).

## Proposed structure (mirrors the respiratory pipeline's discipline)
```
backend/app/services/processing/conditions/
├── measures.py   # registry: id, label, aggregator group, source field, unit, direction
├── windows.py    # condition (marker group) → time intervals → per-condition measure values
└── contrast.py   # per-condition aggregate + pairwise contrast for a selected measure
```
- **measures.py** — a typed registry grouped by aggregator (Stress, Cardiac/HRV,
  Electrodermal, Respiratory, Self-report). Each entry names the source field in
  `room_stats`/`windowed` so the UI dropdown is generated from one place.
- **windows.py** — maps each condition's markers to time intervals (see open
  question below) and computes the measure values per condition, reusing the
  proven `timestamp_ms`-based alignment rather than re-deriving it.
- **contrast.py** — for the selected measure(s): per-condition mean ± sd ± n, and
  pairwise contrasts with Cohen's d, 95% CI, and the `underpowered` flag.
- **Endpoint:** extend `POST /sessions/{id}/conditions` to accept an optional
  `measures` list and return `measure_comparison` alongside the respiratory
  result; default to the stress aggregator.
- **Contract:** `CONDITION_COMPARISON_CONTRACT` — registry completeness, the
  alignment invariant (every aggregated window's centre lies inside its
  condition's intervals), and the same stats honesty rules.

## Frontend
A grouped measure dropdown in `ConditionEditor` (default: Stress / arousal). On
apply, render the chosen measure's contrast (table + effect size + CI, and a
simple bar/box per condition) beside the existing respiratory output.

## The one decision that governs correctness
How does a condition (a set of markers) define the time spans to aggregate? This
depends on how the data is actually marked, which is also the open ingestion
question — so a sample file from each student resolves both at once.
- **A — onset/offset pairs:** `X_onset … X_offset` bound each window (the current
  room convention).
- **B — active-until-next:** a marker starts a segment that runs until the next
  marker of any kind (phase semantics; matches the breath-cycle `phase`).
- **C — fixed window after marker:** e.g. 60 s following each marker.

Picking the wrong semantics yields confidently-wrong comparisons, so this is
settled before building, not after.

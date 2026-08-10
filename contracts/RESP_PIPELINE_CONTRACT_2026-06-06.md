# Contract — Respiratory Pipeline (orchestrator)

Module: `backend/app/services/processing/respiratory/pipeline.py`

## Purpose
Single assembly path for respiratory analysis, used by both the `/analyze`
route and the condition-recompute endpoint, so the two cannot drift. Runs the
stages, attaches a manifest, and runs a last-mile verifier before returning.

## Entry point
`run(*, vernier_result=None, markers=None, conditions=None, recompute_payload=None)
-> RespiratoryResult`. Provide `vernier_result` (first analysis) **or**
`recompute_payload` (recompute). Stage order: signal → tables → stats → viz.

## Outputs (`RespiratoryResult`)
- `result` — `patterns_detected`, `pattern_counts`, `pattern_details`,
  `condition_comparison`, `contrasts`, `figures`, `figures_skipped`,
  `n_figures`, `total_breaths`, `breath_cycle_table`.
- `recompute_payload` — source-of-truth inputs for the caller to persist
  (one ledger per fact: this is the ledger; `result` is derived).
- `manifest` — stages run, n_cycles, conditions, patterns detected, figures
  rendered/skipped, n_contrasts.

## Last-mile verifier (must pass before return; raises `PipelineVerificationError`)
1. Every rendered/skipped figure name corresponds to a classified pattern (or
   the `overview`/`_all` sentinels).
2. Every condition referenced by a statistic exists in the tables' condition map.
3. `pattern_counts` ⊆ `pattern_details`, all marked `found`.

## Invariants
- If Stage 0 fails, `run` returns early with `{"error": ...}` and a manifest
  marking the signal stage failed — later stages are not attempted.
- Persistence (caller's responsibility): only the derived `respiratory_patterns`
  field is overwritten on recompute; the `recompute_payload` ledger is left
  intact.

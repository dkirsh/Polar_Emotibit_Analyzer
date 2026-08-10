# Contract — Respiratory Stage 1: Tables

Module: `backend/app/services/processing/respiratory/tables.py`

## Purpose
Produce the data tables (no plotting, no inference) from the source-of-truth
signal and the researcher's condition grouping.

## Inputs
- `sig: SignalResult` (Stage 0).
- `conditions`: list of `{name, markers, role}` where `role ∈ {stress, calm,
  comparison}`. `stress`/`calm` define the dichotomy that drives pattern
  detection; `comparison` conditions appear in the comparison table only. When
  no stress/calm roles are given, detection falls back to the module defaults.

## Outputs (`TablesResult`)
- `pattern_details` — per pattern: label, description, `count` (stressed),
  `calm_count`, `found`.
- `pattern_counts` — found patterns → stressed count.
- `condition_comparison` — per condition: n, mean ± sd of rate / I:E / amplitude
  / CV / duty cycle.
- `breath_cycle_records` — one row per breath (the raw data table; NaN→null).
- `patterns`, `exemplars` — carried for the viz stage.

## Invariants & success conditions (enforced; raise `TableReconciliationError`)
- **Reconciliation:** breaths assigned to conditions + unassigned == total cycle
  count.
- **Completeness:** every pattern the classifier produced has a `pattern_details`
  row; `pattern_counts` ⊆ found patterns.

## Failure modes
Reconciliation/completeness violations raise (a non-reconciling table is a defect,
not a rounding note). Empty input yields empty tables, not fabricated rows.

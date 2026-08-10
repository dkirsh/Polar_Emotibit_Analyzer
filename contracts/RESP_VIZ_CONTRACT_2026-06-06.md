# Contract — Respiratory Stage 3: Visualizations

Module: `backend/app/services/processing/respiratory/viz.py`
(rendering primitive: `respiratory_patterns.generate_pattern_figures`)

## Purpose
Render the pattern figures from the Stage-1 classification and the source signal.

## The governing rule
**This stage may never raise.** A figure defect must not be able to take down
the tables and statistics that were already computed correctly. (This contract
exists because a `None` exemplar in the overview figure once crashed an entire
recompute, discarding correct tables and stats.)

## Inputs
`sig: SignalResult`, `tables: TablesResult`.

## Outputs
`{"figures": {name: base64_png}, "skipped": {name: reason}}`.

## Invariants & success conditions
- Every requested figure appears in exactly one of `figures` or `skipped`.
- A figure that cannot be built (e.g. no paired normal exemplar, matplotlib
  absent) is recorded in `skipped` with a human-readable reason; the others
  still render.
- `render()` returns normally for all inputs — it catches and records, never
  propagates, exceptions.

## Failure modes
Wholesale failure (e.g. matplotlib import error) → `{figures: {}, skipped:
{"_all": reason}}`. Never an exception.

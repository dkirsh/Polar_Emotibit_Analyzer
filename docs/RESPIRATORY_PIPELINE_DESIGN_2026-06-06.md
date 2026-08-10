# Modular respiratory analysis pipeline — design proposal (2026-06-06)

## Why this exists
The respiratory analysis grew as one function, `analyze_respiratory_patterns`,
that ingests, builds tables, classifies patterns, runs cross-condition stats,
*and* renders matplotlib figures, returning everything in a single dict. The
`/analyze` route and the new condition-recompute path both call into that
monolith. Two consequences observed this session:

1. **A visualization bug crashed the data.** A `None` "normal" exemplar in
   `_build_overview_figure` raised `TypeError`, which aborted the entire
   recompute — including the breath tables and condition statistics that had
   already been computed correctly (verified: role-swap changes counts; stress
   rate 33.4 bpm vs calm 15.0 bpm). Tables and stats should not be able to fail
   because a figure failed.
2. **Logic is duplicated.** The recompute path re-implements the assembly that
   `analyze_respiratory_patterns` already does, so the two will drift.

This is the "last mile" and "one ledger per fact" problem in miniature. The fix
is to regiment the work into contracted stages with explicit success conditions.

## The stages
A `respiratory/` subpackage, each stage a pure function with a typed result and
a contract. Data flows one direction; later stages never mutate earlier ones.

```
backend/app/services/processing/respiratory/
├── signal.py    # Stage 0 — raw belt → resp_z, peaks, troughs, cycle table
├── tables.py    # Stage 1 — cycles → BreathCycleTable, PatternCountTable, ConditionTable
├── stats.py     # Stage 2 — tables → ConditionContrast (effect size, CI, power)
├── viz.py       # Stage 3 — tables (+signal) → figures, fail-soft
└── pipeline.py  # Orchestrator — runs stages, assembles result + manifest, verifies
```

### Stage 0 — Signal (mostly exists in `vernier_parser` + the z-score block)
**Input:** belt force timeseries. **Output:** `resp_z`, `peaks`, `troughs`,
`fs`, and the per-breath cycle table. **This is the single source of truth**;
everything downstream is derived and recomputable from it. It is what we persist
under `_resp_recompute`.
**Success condition:** ≥ N cycles extracted, or an explicit, typed
"insufficient signal" result — never a partial table presented as complete.

### Stage 1 — Tables (`tables.py`)
Pure data, no plotting, no inference. Produces:
- `BreathCycleTable` — one row per breath (rate, I:E, duty, amplitude, phase).
- `PatternCountTable` — per pattern: stressed count, calm count, detected flag.
- `ConditionTable` — per condition: n, mean ± sd of rate/I:E/amplitude/CV.
Takes the user's condition grouping (stress/calm/comparison roles) as input.
**Success condition / invariant:** counts reconcile — the per-condition breath
counts sum to the total cycle count; every classified pattern has a row. A
mismatch is a hard error, not a rounding note.

### Stage 2 — Statistics (`stats.py`)
Pure numeric inference over the tables. Produces `ConditionContrast`: for each
pair (or each condition vs control), the difference, an effect size, a 95% CI,
and an explicit `underpowered` flag when n is too small (honest label rather
than a confident p-value on three breaths). No plotting, no data mutation.
**Success condition:** every reported contrast carries n, an effect size, and
either a CI or an `underpowered` reason.

### Stage 3 — Visualizations (`viz.py`)
Takes the tables (and `resp_z` for waveform panels) and renders figures.
**Contract: this stage may never raise.** Each figure is attempted
independently; a figure that cannot be built (e.g. no normal exemplar) is
recorded in a `skipped: {figure_name: reason}` map and omitted, while the others
still render. (This is exactly the bug that bit us — the contract makes it
impossible to repeat.)
**Success condition:** returns `{figures, skipped}` where every requested figure
appears in exactly one of the two.

### Orchestrator (`pipeline.py`)
Runs Stage 0 → 1 → 2 → 3, assembles the result, and attaches a **manifest**:
which stages ran, what each produced, what was skipped and why, plus provenance
(condition grouping used, code version, recompute-from hash). Both `/analyze`
and the condition-recompute endpoint call this one orchestrator — eliminating
the duplicated assembly.

**Last-mile verifier.** A final invariant asserts the three artifacts agree:
the conditions named in the tables, the stats, and the figure set are the same;
the count totals match the source cycle table. The result is not returned until
the verifier passes. A new analytic/figure is "done" only when it appears in the
manifest, renders (or is explicitly skipped with a reason), and survives export.

## Contracts to add (`contracts/`)
- `RESP_SIGNAL_CONTRACT` — source-of-truth guarantees, persistence shape.
- `RESP_TABLES_CONTRACT` — table schemas + the count-reconciliation invariant.
- `RESP_STATS_CONTRACT` — required fields per contrast; underpowered semantics.
- `RESP_VIZ_CONTRACT` — the never-raise / figures+skipped guarantee.
- `RESP_PIPELINE_CONTRACT` — stage order, manifest fields, last-mile verifier.

## Migration (additive, low-risk, reversible)
1. Carve `tables.py`, `stats.py`, `viz.py` out of `respiratory_patterns.py` as
   pure functions; keep the old function as a thin wrapper that calls the
   orchestrator, so existing callers and tests keep working (no behaviour change
   yet — verify by re-running the current test suite green).
2. Repoint `/analyze` and the recompute endpoint at the orchestrator; delete the
   duplicated assembly in the recompute path.
3. Add the contracts and the last-mile verifier; convert this session's
   role-swap test and a new "viz never raises" attack test into regression
   guards.
4. Fold the figure `None`-exemplar crash into the Stage-3 fail-soft path (it
   becomes a `skipped` entry, not an exception).

Each step is independently verifiable and leaves the system working; nothing is
deleted until its replacement is proven equivalent (supersession, not deletion).

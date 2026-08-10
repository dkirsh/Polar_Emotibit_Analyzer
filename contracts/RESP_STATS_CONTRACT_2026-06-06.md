# Contract — Respiratory Stage 2: Statistics

Module: `backend/app/services/processing/respiratory/stats.py`

## Purpose
Inferential contrasts between conditions over the Stage-1 tables. Pure numeric;
no plotting, no mutation of upstream data.

## Inputs
`tables: TablesResult` (uses `breath_cycle_records` and `condition_map`).

## Outputs (`StatsResult`)
`contrasts`: for each pair of named conditions and each metric (respiratory rate,
I:E ratio, amplitude): `n_a`, `n_b`, `mean_a`, `mean_b`, `diff`, `cohens_d`,
`ci95_low`, `ci95_high`, `underpowered`, `underpowered_reason`. `note` when fewer
than two conditions are defined.

## Invariants & success conditions
- Every contrast carries n for both arms and an effect size (or null when n<2).
- Every contrast carries either a 95% CI **or** `underpowered = true` with a
  reason. An honest "underpowered" label is preferred over a confident interval
  computed on a handful of breaths (`MIN_ARM_N` is the threshold).
- CI uses the t-distribution with Welch–Satterthwaite df, not z.

## Failure modes
Insufficient conditions → empty `contrasts` with an explanatory `note`, never an
exception.

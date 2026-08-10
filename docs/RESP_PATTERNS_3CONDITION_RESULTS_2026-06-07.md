# Respiratory stress patterns across three conditions (plants / no-plants / stressor)

*Script: `scripts/resp_patterns_three_conditions.py`. Outputs in
`outputs/resp_patterns_3cond/`.*

## The seven stress-indicating respiratory patterns (analyzer definitions)
| pattern | flag (canonical thresholds) |
|---|---|
| tachypnea | rate > 18 bpm |
| I:E shift | 0.85 ≤ I:E ≤ 1.15 (approaching 1:1) |
| inverted I:E | I:E > 1.5 |
| shallow | amplitude < subject 10th percentile |
| irregular | cycle-duration CV > 0.30 |
| stress sigh | amplitude > median + 1.5·SD and dur > median |
| breath-hold / apnea | dur > 8 s and suppressed amplitude |

**Note on RespInPeace.** RespInPeace (`rip.py`) is present in
`Estelita/RespInPeace_Output/code/` and computes breath features, but the
backend analyzer does **not** import it — it reimplements breath detection, and
the seven stress-pattern definitions live only in
`backend/.../respiratory_patterns.py`. So the system *should* be using
RespInPeace (per your design intent) but currently uses a duplicate. This is the
known duplication flagged in the repo's CLAUDE.md; reconciling them (delete the
duplicate or have the backend call RespInPeace) is a recommended fix.

## Conditions
- **plants** / **no_plants** = the two room-exposure `condition` windows.
- **stressor** = `stressor_test_1` / `stressor_test_2` event markers.
- 16 subjects (15 with all three conditions; `sub_1.9_G4` has no plants).

## Normalization
Conditions differ in length, so each pattern count is converted to a **rate per
100 breaths**, then expressed **within-subject as the deviation from that
subject's own three-condition average** ("more / less than the subject's
average"). The small comparison table aggregates and tests those within-subject
values.

## Big table — per subject (`table_per_subject_3conditions.csv`)
One row per subject × condition with `n_breaths`, the count of each of the seven
patterns, `total_stress` breaths, and `stress_rate_per100`.

## Per-pattern totals by condition (`table_pattern_totals_matrix.csv`)
| pattern | plants | no_plants | stressor |
|---|---|---|---|
| tachypnea | 547 | 525 | 373 |
| ie_shift | 569 | 520 | 410 |
| inverted_ie | 320 | 323 | 349 |
| shallow | 185 | 146 | 88 |
| irregular | 1224 | 1214 | 1051 |
| sigh | 240 | 218 | 211 |
| apnea | 0 | 0 | 0 |

## Small table — totals + significance (`table_totals_by_condition.csv`, `table_significance.csv`)
| condition | total stress breaths (all subjects) | mean stress rate /100 | within-subj dev from avg | direction |
|---|---|---|---|---|
| plants | 1786 | 82.5 | +0.81 | more than avg |
| no_plants | 1701 | 79.8 | −1.50 | less than avg |
| stressor | 1442 | 82.8 | +0.69 | more than avg |

**Significance (within-subject, n = 15 complete):** Friedman χ²(2) = 2.53,
**p = 0.28 — not significant.** Pairwise Wilcoxon: stressor vs plants p = 0.89,
stressor vs no_plants p = 0.36, plants vs no_plants p = 0.11. **The number of
respiratory stress patterns does not differ significantly across the three
conditions.**

## Why — and the important caveat
Two things matter for interpreting this null:
1. **`irregular` dominates and saturates the index** (~58 of every 100 breaths
   flagged in every condition). On belt data, cycle-duration CV > 0.30 is tripped
   constantly, so the total stress rate sits near 80% with little dynamic range
   to detect condition differences.
2. **The categorical pattern flags are less sensitive than continuous rate.**
   Recall the stressor raised mean respiration rate significantly (13.3 → 15.1
   bpm) — yet that rise mostly stays below the 18 bpm tachypnea threshold, so the
   *flag* count barely moves. The continuous measure detects the manipulation;
   the categorical patterns do not.

So: by the analyzer's pattern definitions, respiratory stress-pattern counts are
statistically indistinguishable across plants, no-plants, and stressor. The
trustworthy signal of stress in this dataset is the **continuous respiration
rate** (significantly elevated in the stressor), not the pattern counts. If the
pattern scale is to be used, the `irregular` threshold needs recalibration for
belt data (and ideally RespInPeace should be the single producer).

## Figures (`outputs/resp_patterns_3cond/`)
- `fig_pattern_rates_by_condition.png` — per-pattern rate/100 by condition.
- `fig_total_stress_by_condition.png` — overall stress rate by condition, within-subject.

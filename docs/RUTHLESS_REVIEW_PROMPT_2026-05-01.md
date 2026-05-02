# Ruthless review prompt — Polar-Emotibit Analyzer

*Date*: 2026-05-01  
*Target*: `/Users/davidusa/REPOS/Polar_Emotibit_Analyzer`  
*Purpose*: find the defects that would mislead a scientifically literate user, not the defects that merely offend aesthetic taste.

## Instruction

Review this repo as if you were trying to stop a bad paper, a bad demo, or a bad student inference before it escaped into the world.

You are not to be impressed by:
- green builds,
- passing tests,
- plausible-looking charts,
- long explanatory prose,
- or the fact that a metric has a Greek-sounding physiological story attached to it.

You are to ask four blunt questions:

1. **Is the computation honest?**
   - Does each chart say what the code actually computes?
   - Does each physiological claim match the provenance of the underlying signal?
   - Are “native RR”, “derived RR”, “proxy respiration”, and “true respiration” kept distinct?

2. **Is the presentation honest?**
   - Are exported figures actually valid standalone SVGs?
   - Are charts clipped, compressed, or visually misleading?
   - Does the prose overclaim what the chart can support?

3. **Is the persistence layer honest?**
   - Does loading old data silently rewrite it?
   - Are migrations explicit, reversible, and provenance-preserving?
   - Can a reader tell whether a chart was computed live or backfilled later?

4. **Is the repo operationally disciplined?**
   - Do tests cover the new behaviour rather than merely the old summary path?
   - Are there hidden side effects at import time?
   - Are there places where one failure path quietly reintroduces the defect supposedly fixed?

## Scope to inspect first

- `backend/app/api/v1/routes/analysis.py`
- `backend/app/services/processing/features.py`
- `backend/tests/test_features.py`
- `frontend/src/analytics/ChartRenderer.tsx`
- `frontend/src/analytics/catalog.ts`
- `frontend/src/api.ts`
- `frontend/src/pages/AnalyticDetailPage.tsx`

## Required method

1. Read the actual diff or changed files.
2. Run the relevant targeted tests.
3. Inspect at least one real rendered output if the change concerns visual presentation.
4. Prefer a small number of high-confidence findings over a large number of speculative complaints.
5. For every finding, state:
   - severity,
   - exact file and line,
   - what is wrong,
   - why it matters,
   - and what would make it honest.

## Severity rubric

- **P0**: scientifically or operationally dangerous; likely to mislead a user materially.
- **P1**: important defect; should be fixed before relying on the feature.
- **P2**: real but non-blocking defect.
- **P3**: cosmetic or stylistic; omit unless it illuminates a larger issue.

## Output format

Return only:

1. **Findings**, ordered by severity, with file/line references.
2. **Open assumptions**, if any.
3. **Brief state summary**: what passed and what remains risky.

If there are no findings, say so explicitly and name the residual risks rather than pretending the repo is perfect.

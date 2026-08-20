# CLAUDE.md — operating instructions for this repository

This file governs how an AI agent should plan, review, and write code in the
Polar–EmotiBit Analyzer. It exists because this codebase is built and reviewed
partly by agents, and the dominant failure mode in such systems is not wrong
computation but **confident description that has drifted from the artifact.**
Keep descriptions and disk in agreement.

If a `production-discipline` skill is installed, use it; this file is the
repo-specific application of its rules.

## What this project is
A local, file-only, post-hoc analyzer of psychological/physiological stress from
EmotiBit (EDA, accelerometer, temperature, optical) + Polar H10 (ECG/RR) +
optional Vernier respiration-belt data. FastAPI backend (`backend/app`, ~11k LOC),
React/Vite frontend (`frontend/src`, ~7k LOC, **pure-SVG charts, no chart
library**), session state in `data/session_store.json` (no database). It is
**not a medical device**; outputs are research-grade and several indices
(notably the stress composites) are explicitly experimental.

## Standing rules

1. **The last mile is the failure mode.** A stage is not "done" until its result
   reaches its real destination. Make the write part of the success condition,
   and give each writer an invariant that cross-checks it (cf. the existing
   sync-QC gate and `rr_source` provenance). Before claiming a feature works,
   confirm it is wired into the consumer — e.g. a new analytic must appear in
   `catalog.ts`, render in `ChartRenderer.tsx`, and survive export, not merely
   be computed in the backend.

2. **Verify with severity tests, not demonstrations.** New checks should be
   executable attacks that pass *only while the defect exists*. When you fix a
   bug, leave a regression guard behind (the repo already does this well — keep
   it up). Do not mark work complete on the strength of green happy-path cases.

3. **Re-measure your own claims.** Ground any count or "X is unused" statement in
   evidence produced this session. **Exclude `backend/.venv`, `node_modules`,
   `__pycache__`, and the multi-gigabyte `Estelita/` raw data** from any line/
   file/TODO counts — including these has already produced ~15–70× overcounts.
   A discrepancy between a doc/contract and the code is itself a finding.

4. **Mutations are additive, dry-run-first, idempotent.** The session store is
   written atomically (temp file + `os.replace`); preserve that. Prefer
   fill-only backfills (the v2.2.1 EDR provenance migration is the model) and
   supersession over deletion. Never overwrite a non-null provenance field.

5. **One ledger per fact.** `rr_source`, quality flags, and per-phase windows
   should have a single authoritative producer and be derived downstream. When
   the same value appears in two stores, reconcile rather than double-write.

6. **Provenance is cheap now, expensive later.** Keep populating `rr_source`,
   `rr_source_confidence`, quality flags, and analyzed-at timestamps at the
   point of computation. If you add an ingest path, add its provenance columns
   in the same change.

7. **Honest labels.** Maintain the existing discipline: experimental indices
   stay flagged experimental; metrics below band-minimum duration return `None`,
   not a plausible default; degraded RR sources are marked degraded. Prefer a
   nullable "not earned" to a fake-complete value.

8. **Check the import graph before calling code dead.** The `Estelita/` analysis
   scripts (`RespInPeace_Output/code/`) duplicate logic now living in
   `backend/app/services/processing/respiratory_patterns.py` and
   `ingestion/vernier_parser.py`. Treat that duplication as a known liability:
   when you touch respiratory logic, change the backend copy and either delete
   or clearly mark the Estelita copy — do not let the two drift further.

9. **Respect the executor.** This is a single-writer JSON store and a local
   two-process app (Uvicorn + Vite). Keep operations resumable and avoid
   designs that assume a database, a queue, or multi-user concurrency unless you
   are deliberately introducing one (see the roadmap in `docs/`).

## Before you finish a task
State, in the final summary: what you **verified this session** (with the
command/evidence), what is **stipulated pending calibration**, and what you
**did not check**. This vocabulary is what keeps the contracts in `contracts/`
and the audit docs in `docs/` meaningful.

## Where things live
- Pipeline orchestration: `backend/app/services/processing/pipeline.py`
- HRV/EDA features: `backend/app/services/processing/features.py`
- Sync & drift: `backend/app/services/processing/{sync,drift,sync_qc}.py`
- Ingestion/parsers: `backend/app/services/ingestion/`, `parsers.py`
- HTTP routes: `backend/app/api/v1/routes/`
- Analytics catalog (single source of truth for the 26 analytics): `frontend/src/analytics/catalog.ts`
- Chart rendering: `frontend/src/analytics/ChartRenderer.tsx`
- Module guarantees: `contracts/` — read the relevant contract before changing a subsystem.

---

## Extends Root CLAUDE.md — global rules apply (pointer added 2026-08-01)

This repo extends `/Users/davidusa/REPOS/CLAUDE.md`; read it and apply all its global rules here.
Notably (added 2026-08-01): **Build Ledger for Multi-Component Builds** — when building a system of more than a
few interacting components, maintain `BUILD_LEDGER.md` + `build_ledger.json` regenerated by a generator whose
status fields are populated by ACTUALLY RUNNING each component's test/harness (so the ledger can't drift from
reality). Full spec: the root CLAUDE.md section "Build Ledger for Multi-Component Builds".


<!-- ATLAS-WRITING-NORMS v1 (managed block — keep the markers; edit the canonical docs, not this) -->
## Writing norms — BINDING

Before writing or editing ANY extended prose in this repo — papers, reports, briefings, proposals,
design docs, READMEs, or any output over ~300 words — you MUST read and apply the ATLAS
science-communication norms, and record a short provenance note (which norm docs you read) at the
top of the deliverable. Producing prose here without reading the norms is a process violation; if it
happens, say so plainly.

Canonical sources (single source of truth), in the shared module `atlas_shared`:
  - contracts/WRITING_STYLE_GUIDE.md
  - contracts/SCIENCE_COMMUNICATION_NORMS.md   (Norms 1–14; Norms 13–14 are David Kirsh's own voice)
Locate on this machine:  find ~/REPOS -path '*contracts/SCIENCE_COMMUNICATION_NORMS.md' 2>/dev/null
Read those in full when reachable. The digest below is a fallback, not a replacement.

### Digest (fallback if the canonical docs are unreachable)
Voice: a smart non-specialist reader; bias toward the popular end; define every technical term on
first use; warm and direct, never casual.
Norms 1–12 (Pinker / Williams / Lanham):
  1  Lead with the point — open each paragraph with its conclusion, then give the evidence.
  2  Given–New — begin a sentence with familiar information, end with the new.
  3  Stress position — put the most important thing at the sentence's end.
  4  Kill nominalizations — restore the buried verb (-tion/-ment/-ness/-ity → verb).
  5  Paramedic Method — cut lard; active verb; agent as subject; start fast.
  6  Curse of knowledge — name every skipped inferential step; define terms.
  7  Narrative thread — the document tells one story; make the arc visible.
  8  Scaffold — one new idea at a time; concrete before abstract.
  9  Honest uncertainty — match language to the evidence; never "clearly/obviously/interestingly".
  10 Defamiliarize — show the reader what they think they know but do not.
  11 Structure carries meaning — headings state the claim, not the topic.
  12 Ethical embedding — show consequences with evidence; let the reader draw the conclusion.
  Also: one idea per sentence; active voice; 4–7 sentence paragraphs; weave citations (no clusters);
  no throat-clearing ("It is worth noting…"); never "one" as a pronoun, never "the authors".
Norm 13 — six Kirsh reflexes: (1) enrich one example into 3–4 uneven variants and lean on them;
  (2) soften absolutes (may / can be thought of as / typically); (3) ground abstractions in the senses
  (verbs of perception over verbs of cognition); (4) split two-card "X but Y" sentences; (5) invert for
  emphasis sparingly; (6) strip forward-references and meta-housekeeping.
Norm 14 — the Kirsh voice (structure, not words): the "reads like AI" tell is structural. Restore by
  re-fusing short paragraphs into accreting ones; planting a real question at each section head and
  leaving it open a beat; restoring the puzzling first person ("I suspect", "my sense is");
  un-balancing even triads; opening sentences with conjunctions (So / And / But). CRITICAL: the crisp
  punchy fix is itself an AI tell — the authentic repair is LONGER, more hedged, conjunction-led.
<!-- /ATLAS-WRITING-NORMS v1 -->

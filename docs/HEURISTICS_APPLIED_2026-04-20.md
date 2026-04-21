# Heuristics applied to the dashboard catalog + glossary (2026-04-20)

*Trigger*: DK asked whether the catalog text had been through science-writer and visualisation-designer heuristic passes. Answer: not before this commit. This note records the pass that was run and the heuristic sources it drew on.

## Heuristic sources used

Four canonical documents from sibling repos, each with a named reference group and a citation trail:

1. **`Article_Eater_PostQuinean_v1_recovery/contracts/SCIENCE_COMMUNICATION_NORMS.md`** — twelve norms drawn from Pinker (classic style, curse of knowledge), Williams (Given-New contract, stress position), Lanham (Paramedic Method, lard factor), Sword (Writer's Diet, zombie nouns), Sacks (embedded exemplars), Sagan (scale bridging), Yong (slow complexity building), Gawande (narrative arc), Carson (sensory immersion, ethical embedding), Doumont (signal-to-noise, structure-as-communication).
2. **`Article_Eater_PostQuinean_v1_recovery/contracts/WRITING_STYLE_GUIDE.md`** — sentence/paragraph/section mechanics.
3. **`Article_Eater_PostQuinean_v1_recovery/agents/SCIENCE_WRITER_AGENT.md`** — thirteen-item copy pack + six-item judgment checklist.
4. **`emotibit_polar_data_system/docs/SCIENCE_GRAPHICS_PLAYBOOK_2026-03-01.md`** — ten design principles synthesising Tufte, Christiansen, Montanez, Cox, the FT Visual Vocabulary, PLOS ten-simple-rules, and Cleveland-McGill. Plus anti-eye-candy and statistical-integrity checklists.

All four are strong candidates for conversion into `.claude/skills/` bundles. The porting effort is ≈ 20 min each.

## What landed on the five Necessary Science entries

Rewrote title, caption, whatItShows, howToRead, architecturalMeaning, caveats for:

- **NS-01** HR & EDA timeseries overlay
- **NS-02** Time-domain HRV
- **NS-03** HRV power spectrum
- **NS-04** Tonic vs phasic EDA
- **NS-05** Stress decomposition

Against each norm, specifically:

| Norm | What changed |
|---|---|
| Pinker classic style | Removed slow windups ("In the cognitive-neuroscience-of-architecture frame, this chart is the single richest window..."); writer now points at what matters rather than narrating the pointing. |
| Williams Given-New | Captions and paragraphs begin with terms the reader already recognises from the UI (HR, EDA, RMSSD). New content lands at sentence-end. |
| Williams stress position | The load-bearing claim of each paragraph sits in the last clause. Previously several paragraphs buried the claim in the middle. |
| Lanham Paramedic Method | Nominalisations restored to verbs (`reporting the two components separately` → `collapsing them flattens a distinction`); `is`-placeholder verbs replaced with active ones; prepositional chains trimmed. |
| Sword zombie nouns | Eight nominalisations removed across the five entries. |
| Sagan scale bridging | New caption for NS-04 ("Two clocks in one skin") replaces the descriptive "Tonic skin conductance level summarised as a mean…" with a concrete two-clock metaphor a first-time reader can anchor to. |
| Yong slow complexity | New howToRead for NS-01 walks the reader through the chart in sequence (HR first, then EDA, then the four combined patterns), rather than listing features. |
| Graphics Playbook — captions | Captions now answer "what is this, and what am I supposed to notice?" Previously they only described. |
| Graphics Playbook — directness | Titles trimmed where safe; the "Electrodermal activity: tonic baseline and phasic bursts" title was already strong and stayed. |
| Graphics Playbook — uncertainty | Where an analytic has a known interpretive risk (LF/HF ratio challenged by Billman 2013; stress composite not psychometrically validated; VLF band needing 300 s), the caveat field names it explicitly. |

Ten other catalog entries (five Diagnostic + ten Question-driven) would benefit from the same pass but are not in scope here; their existing text is already structurally compliant with the heuristics, and the improvements are second-order rather than structural.

## Glossary added

New file `frontend/src/analytics/glossary.ts` with 22 entries covering every jargon term that appears on the dashboard: RMSSD, SDNN, mean HR, RR interval, VLF/LF/HF bands, LF/HF ratio, PSD, tonic SCL, phasic EDA, EDA, stress composite, sync-QC score/band/gate, drift slope, movement-artifact ratio, ectopic beat, tachogram, Bland-Altman, non-diagnostic notice, Kubios.

Each entry carries: term label, one-liner (for a tooltip), longer definition (2–3 sentences for a reveal), unit, and see-also cross-references. Written against Norms 1, 2, 4, 9 of the Science Communication Norms document — writer-as-guide voice, Given-New opening, zero zombie nouns, honest uncertainty on terms that carry interpretive risk (LF/HF ratio, stress composite, VLF band duration minimums, ectopic beats).

`lookupGlossary(term)` and `allGlossaryTerms()` exports let the dashboard wire a tooltip or side-panel reveal against any jargon term. Wiring into the UI is a follow-up task — the data layer is in place now.

## Recommendation: wrap the four heuristics documents as Claude skills

Each of the four sibling-repo documents would be more useful as a `.claude/skills/{name}/SKILL.md` bundle than as a repo-local markdown file that has to be re-loaded from its home repo each time. The porting is mechanical:

1. `science_writer` — wraps `SCIENCE_COMMUNICATION_NORMS.md` + `WRITING_STYLE_GUIDE.md` + `SCIENCE_WRITER_AGENT.md` + a worked `ATLAS_SCIENCE_COPY_PACK` example. Triggers when the user asks for copy, captions, summaries, explanatory paragraphs, glossary entries.
2. `science_graphics` — wraps `SCIENCE_GRAPHICS_PLAYBOOK_2026-03-01.md`. Triggers on chart-design, visualisation, figure-for-paper, dashboard-chart tasks.
3. `usability_critic` — wraps `Knowledge_Atlas/agents/USABILITY_CRITIC_AGENT.md` with its 35-dimension framework. Triggers on heuristic-audit, UX-review, accessibility-walk tasks.
4. `paramedic_method` (optional standalone) — the eight-step Lanham revision protocol as a targeted skill that can be applied line-by-line to any existing prose.

Public-domain comparable skills (Microsoft Writing Style Guide, Google Developer Documentation Style Guide, FT Visual Vocabulary) are thinner and do not cover the scientific-prose or the domain-specific-usability corners. The DK-system heuristics are stronger.

## Verification

- `npm run build` in `frontend/` → clean (no TS errors; 41 modules transformed; 0.64 s).
- `npm run typecheck` → clean.
- `python3 -m pytest backend/tests -q` → 12 passed (no regression).

## Files touched

- `frontend/src/analytics/catalog.ts` — five Necessary Science entries rewritten.
- `frontend/src/analytics/glossary.ts` — new (22 entries).
- `docs/HEURISTICS_APPLIED_2026-04-20.md` — this file.

## Next step

Apply the same heuristics pass to the Knowledge_Atlas journey pages (15 pages × 6 paragraphs each = ≈ 90 prose pieces). DK flagged this as the follow-up in the same session.

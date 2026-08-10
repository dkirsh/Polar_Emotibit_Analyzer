# Explainer content — handoff so the kit coheres with the backend

This reconciles two explainer efforts that were diverging: the analyzer wizard
(an **E / Explain** control) and the Claude Design kit (`GlossaryTerm` +
`ExplainGlyph`). They now share **one content source of truth**:
`frontend/src/workflow/explainerContent.ts`. Please point the kit's primitives at
this content (or copy it verbatim into the kit) rather than authoring parallel
strings — duplicated definitions drift, and several of these map to exact backend
producers that must not be misstated.

## The two primitives (confirmed model)
- **GlossaryTerm** — *quick jargon.* Inline term with a dotted underline; on
  hover/focus shows **one line + unit**. Use it for any acronym in running text
  (RMSSD, LF/HF, tonic SCL, Stress V2, sync-QC, FDR q). Source: `GLOSSARY[term]`.
- **Explain (E)** — *substantial narrative.* A circular serif **E** ("Explain")
  that opens a panel teaching the stats/science to a newcomer, with a **plain-
  language** paragraph and a **go-deeper** paragraph, an optional **caveat**, and
  **references** (APA + DOI). Source: `EXPLAINERS[id]`.

**Glyph decision: E / Explain confirmed** (italic serif E in a circle). The
wizard now uses the same glyph, so the two surfaces match. GlossaryTerm keeps the
dotted-underline treatment; the two must look distinct (quick vs substantial).

## Content schema (consume this shape)
```ts
GlossaryEntry { term; oneLiner; unit?; longer?; backend? }
Explainer     { id; title; plain; deeper; caveat?; references[]; backend? }
Ref           { apa; url? }
```
`backend` names the exact producing function/field. Surface it (or at least honor
it) so the interface cannot claim something the pipeline doesn't compute.

## Honest-labels constraints (please preserve in the UI)
- **Stress V2 is experimental** — its Explain panel and glossary line say so. Do
  not present it as a calibrated absolute; keep the "directional, not validated"
  caveat visible.
- **Survives-FDR** means q < .05 after Benjamini–Hochberg across all measures
  tested — only colour a cell as significant on that basis, not raw p.
- **Underpowered ≠ null.** A non-significant small-n contrast must read as
  "not enough evidence", never "no effect".
- A measure below its minimum window returns **no value** (show "—"), not a
  plausible-looking default; RMSSD/SDNN over the plausibility ceiling are invalid.

## Room Summary — drop-in Explain content
Place an **E** on each panel; use these `EXPLAINERS` ids (full text in the module):
- Ranked arousal bars → `arousal_ranking`
  (plain: taller bar = more sympathetic arousal; deeper: EDA tonic SCL + HR,
  normalise within-subject; caveat: arousal ≠ stress). Backend: `metric(eda_tonic,
  mean_hr)`.
- Stress V2 bars → `stress_v2`
  (deeper: weighted cardiac + vagal-HRV + electrodermal composite with
  per-component contributions; caveat: experimental/uncalibrated). Backend:
  `compute_stress_score_v2`.
- Significance-summary panel → `significance_fdr`
  (paired t / Wilcoxon / Friedman; BH FDR → q; "survives FDR" = q<.05; report
  Cohen's dz). Backend: `analyse`.
- Room-type aggregate table → `room_type_aggregate`
  (room-aligned pooling, *not* by presentation position — avoids the
  counterbalanced-order confound). Backend: `roster` condition assignment.

Glossary chips to show in the Room Summary "Key terms" row: `stress_v2`,
`eda_tonic`, `rmssd`, `fdr_q`, `cohens_dz`, `sync_qc`.

## Analytic Detail — per-chart Explain + glossary
- Each chart title gets an **E**. For the RMSSD chart use `rmssd_method`
  (plain: beat-to-beat fluctuation, drops under stress; deeper: successive-diff
  RMS after ectopic correction + plausibility gate + rr_source provenance).
  Backend: `features.py · compute_hrv`.
- "Key terms" chip row per analytic: pull the relevant `GLOSSARY` entries (e.g.
  RMSSD chart → `rmssd`, `rr_interval`, `pnn50`; an EDA chart → `eda_tonic`,
  `eda_phasic`; a spectral chart → `lf_hf`, `sd1_sd2`).

## If you need a term/explainer that isn't here
Tell me the chart or number and I'll author the entry **with its backend
producer**, so the copy stays true to what's computed. Please don't invent the
methodology text in the kit — that's the bifurcation we're closing. New entries
land in `explainerContent.ts` and both surfaces pick them up.

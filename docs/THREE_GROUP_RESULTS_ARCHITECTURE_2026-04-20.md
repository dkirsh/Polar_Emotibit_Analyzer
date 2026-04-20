# Three-group results architecture — 2026-04-20

*Context*: DK directive, 2026-04-20 — organise the analytics into three groups (Necessary Science · Diagnostic · Question-Driven), each with its own cards, each analytic chained to prev/next within its group, each with a caption and an interpretation paragraph written in the voice of a science/visualisation writer, relating the measure to the dependent variables of cognitive neuroscience of architecture.

## What landed

### Backend — extended analytics now in the analyze response

`backend/app/api/v1/routes/analysis.py` now computes the full extended-analytics bundle on every `/api/v1/analyze` call and persists it to the session store. The response carries, in addition to the V2.1 `AnalysisResponse`, an `extended` field with: stress decomposition (four channel contributions plus dominant-driver label); windowed features trajectory (HR mean, HR std, EDA mean, RMSSD, stress score, per-channel stress contributions in 60 s / 30 s-step windows); spectral trajectory (LF, HF, LF/HF ratio in 120 s / 60 s-step windows); the full Welch PSD with band annotations; the raw RR series for tachogram and Poincaré rendering; descriptive statistics (mean/SD/min/max/p5/p95) per channel; inferential statistics (t-distribution 95 % CIs, Cohen's *d* first-half vs second-half, Benjamini-Hochberg-corrected trend p-values); and a subsampled cleaned timeseries (capped at 1000 points) for overlay plotting. Integration tests still green at 12/12.

### Frontend — three-group architecture

The page set is now four pages, routed:

```
/                                              → StartPage (unchanged)
/results/:sessionId                            → ResultsCoverPage (NEW)
/results/:sessionId/group/:groupId             → GroupPage (NEW)
/results/:sessionId/analytic/:analyticId       → AnalyticDetailPage (NEW)
```

The old `PostHocDashboard.tsx` is removed; its content is redistributed across the cover and detail pages.

**`src/analytics/catalog.ts`** is the single source of truth for the analytics. Fifteen entries total: five Necessary Science, five Diagnostic, ten Question-Driven (six Science subcategory, four Diagnostics subcategory). Each entry carries seven content fields: `title`, `caption`, `whatItShows`, `howToRead`, `architecturalMeaning`, optional `caveats`, and APA references with DOIs. The architectural-meaning paragraphs frame every measure in the vocabulary of cognitive neuroscience of architecture — HRV as the vagal-tone index that drops under environmental stress (Ulrich et al., 1991); EDA tonic and phasic as the sustained-arousal and orienting-response axes that architectural variables like acoustic load and spatial compression are known to modulate (Evans & Cohen, 1987; Boucsein, 2012); LF/HF as the autonomic-balance shift seen across slow environmental transitions; Poincaré ellipse shape as the Kubios-canonical variability geometry that distinguishes restorative from demanding environments.

**`src/analytics/ChartRenderer.tsx`** is a library-free SVG renderer supporting all fifteen chart kinds in the catalog: timeseries overlay, summary table, stacked bar, log-log spectrum with band shading, windowed line, Poincaré scatter with SD1/SD2 ellipse, tachogram, histogram, sync-QC composite, motion strip, band-duration gauge, and forest plot. Production swap to Plotly would be a component-level substitution; the component API is stable.

### Three views, three levels of detail

**Results cover page (`/results/:sessionId`)**: the landing page. Session-identity bar at the top with the sync-QC pill in the header line. One short orienting paragraph explaining the three-layer reading order (science first, diagnostics before trusting the science, question-driven for specific research questions). Three large cards — Necessary Science (teal), Diagnostic (amber), Question-Driven (blue) — each showing its icon, title, one-line caption, and its analytic count. Quality flags list and non-diagnostic notice at the bottom. Link back to New Analysis.

**Group page (`/results/:sessionId/group/:groupId`)**: the entry point for one of the three groups. The Necessary and Diagnostic groups render their analytics as cards in a responsive grid (Necessary cards are slightly larger than Diagnostic cards per DK's guidance). The Question-Driven group renders a two-section list with Science questions in teal and Diagnostics questions in amber — each list item carries the question as the primary headline, the analytic title as the secondary line, and the caption as the tertiary line. Every card and list item links to its analytic detail page.

**Analytic detail page (`/results/:sessionId/analytic/:analyticId`)**: the full presentation. Breadcrumb trail at the top (Cover / Group / NN). For question-driven items, the research question renders above the title as an uppercase eyebrow. The graphic title follows, in Georgia serif, with the caption as a secondary paragraph. The chart renders next in a 920 × 360 frame. Four interpretation blocks follow: "What this chart shows" (what the visual encodes), "How to read it" (what visual patterns mean), "What it means for cognitive neuroscience of architecture" (relation to the dependent variables the field tracks), and an optional "Caveat" block in amber when common misinterpretations exist. A references block lists APA citations with DOIs. At the bottom, prev/next chain cards navigate within the group, so a student walking the five Necessary Science charts in order can step through them without returning to the group page.

### The chain-navigation design

Within each group, analytics are ordered. Necessary Science: HR+EDA overlay → time-domain HRV → frequency-domain PSD → EDA tonic/phasic → stress decomposition. Diagnostic: sync-QC composite → drift residuals → motion timeline → tachogram → band-duration gauge. Question-Driven: the six Science questions then the four Diagnostics questions. Each detail page's footer has `prev` and `next` cards styled with the group hue, so chain reading is one click per step.

## The writer's voice

The captions and interpretations are written in clean academic prose; they avoid technical terms where plain ones work and earn their jargon where the jargon is load-bearing. Per-chart breakdown: titles are sentence-case Georgia serif at 1.85 rem; captions are single-sentence summaries in one-and-a-half-line-height grey; `whatItShows` is 80–140 words describing the visual; `howToRead` is 50–100 words naming the patterns a reader should look for; `architecturalMeaning` is 80–140 words relating the measure to the field's dependent variables (arousal, stress, attention, recovery) and its canonical manipulations (noise, spatial compression, daylight, crowding, thermal gradient). Every claim that rests on a published result is accompanied by an APA reference with a DOI.

## Interpretation paragraph — structure

A representative example, for the RMSSD chart:

> Time-domain HRV — RMSSD in particular — is the single most responsive index to environmental stressors and the one most used in the architecture-cognition literature (Ulrich et al., 1991; Ottaviani et al., 2016). A depressed RMSSD during the task phase relative to baseline is evidence that the environmental manipulation engaged the sympathetic nervous system; a stable RMSSD across phases is evidence that whatever-else happened, the participant did not perceive an autonomic stressor. SDNN and mean HR are complementary but coarser indices; in a short five-minute session RMSSD usually moves first and most reliably.

Every Necessary Science analytic carries a paragraph at this weight. The Question-Driven analytics are slightly lighter because the research question itself is doing some of the interpretive scaffolding.

## What is complete and what is not

**Complete now, running on the Mac tonight:** the three-group architecture, all fifteen analytics catalogued, the SVG renderer for every chart kind, the cover / group / detail / prev-next flow, the extended-analytics bundle in the backend response, the twelve backend tests still passing.

**Deliberately deferred to v2:** per-phase analysis when markers are supplied (the pipeline currently runs whole-session; per-phase computation is a twenty-line wrapper once markers are parsed); a Plotly swap for Poincaré and PSD (the SVG versions are legible but Plotly's interactive zoom and log-axis controls are better); the Bland-Altman chart beyond placeholder (it needs a companion Kubios CSV upload flow on the cover page); chart export to PNG/SVG for paper figures (one function per chart kind once a chart library is in place).

**References used in the catalog (for later re-export as a bibliography page):**

Benedek, M., & Kaernbach, C. (2010). A continuous measure of phasic electrodermal activity. *Journal of Neuroscience Methods, 190*, 80–91. doi:10.1016/j.jneumeth.2010.04.028

Benjamini, Y., & Hochberg, Y. (1995). Controlling the false discovery rate. *Journal of the Royal Statistical Society B, 57*, 289–300.

Berntson, G. G., et al. (1997). Heart rate variability: Origins, methods, and interpretive caveats. *Psychophysiology, 34*, 623–648. doi:10.1111/j.1469-8986.1997.tb02140.x

Billman, G. E. (2013). The LF/HF ratio does not accurately measure cardiac sympatho-vagal balance. *Frontiers in Physiology, 4*, 26. doi:10.3389/fphys.2013.00026

Bland, J. M., & Altman, D. G. (1986). Statistical methods for assessing agreement. *The Lancet, 327*, 307–310. doi:10.1016/S0140-6736(86)90837-8

Boucsein, W. (2012). *Electrodermal Activity* (2nd ed.). Springer.

Brennan, M., Palaniswami, M., & Kamen, P. (2001). Do existing measures of Poincaré plot geometry reflect nonlinear features of HRV? *IEEE TBME, 48*, 1342–1347. doi:10.1109/10.959330

Chung, V., Chopin, L., Karadayi, J., & Grèzes, J. (2026). Validity of the Polar H10 for continuous HR and HR synchrony. *Sensors, 26*, 855. doi:10.3390/s26030855

Cumming, G. (2014). The new statistics. *Psychological Science, 25*, 7–29. doi:10.1177/0956797613504966

Evans, G. W., & Cohen, S. (1987). Environmental stress. In *Handbook of Environmental Psychology* (pp. 571–610). Wiley.

Gilfriche, P., et al. (2022). Validity of the Polar H10 sensor for HRV analysis. *Sensors, 22*, 6536. doi:10.3390/s22176536

Healey, J. A., & Picard, R. W. (2005). Detecting stress during real-world driving. *IEEE TITS, 6*, 156–166. doi:10.1109/TITS.2005.848368

Kleckner, I. R., et al. (2018). Simple, transparent, and flexible automated quality assessment for ambulatory EDA. *IEEE TBME, 65*, 1460–1467. doi:10.1109/TBME.2017.2758643

Lipponen, J. A., & Tarvainen, M. P. (2019). A robust algorithm for HRV time-series artefact correction. *JMET, 43*, 173–181. doi:10.1080/03091902.2019.1640306

Ottaviani, C., et al. (2016). Physiological concomitants of perseverative cognition. *Psychological Bulletin, 142*, 231–259. doi:10.1037/bul0000036

Shaffer, F., & Ginsberg, J. P. (2017). An overview of HRV metrics and norms. *Frontiers in Public Health, 5*, 258. doi:10.3389/fpubh.2017.00258

Task Force of the European Society of Cardiology and the North American Society of Pacing and Electrophysiology. (1996). HRV standards. *Circulation, 93*, 1043–1065.

Ulrich, R. S., et al. (1991). Stress recovery during exposure to natural and urban environments. *Journal of Environmental Psychology, 11*, 201–230. doi:10.1016/S0272-4944(05)80184-7

Welch, P. D. (1967). The use of FFT for the estimation of power spectra. *IEEE Trans. Audio Electroacoustics, 15*, 70–73. doi:10.1109/TAU.1967.1161901

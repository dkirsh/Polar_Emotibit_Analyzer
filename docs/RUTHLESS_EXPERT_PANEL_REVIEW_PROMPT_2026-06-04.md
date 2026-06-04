# Ruthless Expert Panel Review — Polar-EmotiBit Analyzer

**Date**: 2026-06-04
**Repo**: `/Users/davidusa/REPOS/Polar_Emotibit_Analyzer`
**Scope**: Full-system adversarial audit by 5 world-class domain experts
**Rule**: Do not praise. Every finding must be actionable. Silence means you found nothing wrong — and you are not being paid to find nothing wrong.

---

## Panel Composition

### Panelist 1: Dr. PSYCHOPHYSIOLOGY (Signal Processing)
**Modeled after**: John Allen (Cardiff, _Photoplethysmography and its application in clinical physiological measurement_), Hugo Critchley (Sussex, interoception + autonomic neuroscience), Sylvia Kreibig (Stanford, autonomic specificity of emotion)

**Your expertise**: HRV time-domain and frequency-domain computation, EDA decomposition (tonic/phasic), respiratory inductance plethysmography, artifact rejection in ambulatory physiological recordings, Kubios-parity validation, EmotiBit hardware limitations.

**Your mandate**: Find every place the signal processing pipeline produces numbers that would be rejected by a psychophysiology journal reviewer. Specifically:

1. **HRV computation chain**: Trace from raw Polar H10 RR intervals through ectopic correction (Lipponen-Tarvainen) → time-domain (RMSSD, SDNN, NN50, pNN50) → frequency-domain (LF, HF, VLF, LF/HF ratio, normalized units) → Poincaré (SD1, SD2, ellipse area). For each:
   - Is the implementation mathematically correct?
   - Does it match Kubios / the Task Force (1996) standard?
   - Are edge cases handled (< 5 min recording for frequency domain, < 50 beats, ectopic burden > 20%)?
   - Is the Lipponen-Tarvainen implementation faithful to the 2019 paper?
   - Does the new accelerometer cross-check correctly exclude movement epochs WITHOUT biasing the remaining HRV toward rest-only values?

2. **EDA chain**: Trace from raw EmotiBit EDA → tonic/phasic decomposition → SCR detection. 
   - Is the sampling rate correct (15 Hz from EmotiBit)?
   - Is the decomposition method documented and defensible?
   - Are motion artifacts from the wrist-worn device addressed?

3. **Respiratory chain**: Trace from Vernier belt force signal → ALS baseline removal → cycle detection → per-breath features (rate, I:E ratio, amplitude, irregularity) → sigh detection.
   - Does the RespInPeace implementation match the Wlodarczak (2019) paper?
   - Is the 20 Hz resampling adequate?
   - Is the ALS regularization parameter documented?

4. **ECG-Derived Respiration (EDR)**: 
   - Is the Butterworth bandpass (0.15–0.4 Hz) appropriate? That's 9–24 breaths/min — does it clip slow breathers?
   - Is the RSA amplitude computation correct?
   - Does the `rr_source` provenance correctly degrade when RR is derived from BPM?

5. **Stress composite (v1 + v2)**:
   - Are the 7 channels and their weights defensible?
   - Is the WESAD-based weight derivation script (`derive_stress_weights_wesad.py`) sound?
   - Is the composite normalized to [0, 1]? Does it saturate?

6. **Sync QC**: Does the go/conditional_go/no_go gate correctly catch clock drift, sample drops, and timestamp misalignment between Polar and EmotiBit?

---

### Panelist 2: Dr. STATISTICS (Methodology)
**Modeled after**: Andrew Gelman (Columbia, _Bayesian Data Analysis_), Frank Harrell (Vanderbilt, _Regression Modeling Strategies_), Sander Greenland (UCLA, causal inference + bias analysis)

**Your expertise**: Repeated-measures designs, within-subjects experiments, multiple comparisons, effect sizes (Cohen's d, η²), non-parametric alternatives, missing data, statistical power, p-value interpretation.

**Your mandate**: Find every place the statistical analysis could mislead a researcher. Specifically:

1. **Room-level analysis**: The factorial design (geometry × chromaticity) uses windowed physiological data gated by onset/offset markers.
   - Is the independence assumption violated (within-subjects = correlated observations)?
   - Are the statistical tests appropriate for the design (repeated-measures ANOVA vs. mixed models vs. what's actually implemented)?
   - Is the FDR correction applied correctly?
   - Are effect sizes computed correctly (Cohen's d for between-groups, but the design is within-subjects — should this be dz or dav)?

2. **Cross-subject comparison**: The CSV export has one row per room per subject.
   - Are subject-level random effects accounted for?
   - Is the N sufficient for the number of conditions?
   - Are outlier subjects handled?

3. **Plants vs. no-plants analysis** (Estelita scripts):
   - Welch t-test and Mann-Whitney U — are these appropriate for the data structure?
   - Is Cohen's d computed with the correct pooled SD formula?
   - Is there a multiple comparisons problem across the many respiratory features?

4. **Rolling windows**: The "Stress Cross" uses 60s windows with 5s increments.
   - Is the temporal autocorrelation addressed?
   - Are the rolling statistics interpretable given the overlap?

5. **Missing data**: What happens when subjects have incomplete recordings?
   - Is listwise deletion used? If so, what's the bias risk?
   - Are missingness patterns reported?

---

### Panelist 3: Dr. CLINICAL SOFTWARE SAFETY
**Modeled after**: Nancy Leveson (MIT, _Engineering a Safer World_), the IEC 62304 medical device software standard, FDA 21 CFR Part 11 compliance

**Your expertise**: Safety-critical software, medical device regulations, data integrity, audit trails, non-diagnostic disclaimers, operator error modes, failure containment.

**Your mandate**: Find every place the system could harm a user, produce a misleading clinical result, or violate medical device software norms. Specifically:

1. **NON_DIAGNOSTIC_NOTICE**: Is it displayed prominently enough? Does it appear on every output? Could a clinician mistake this tool's output for a clinical assessment?

2. **Data integrity**:
   - Can the pipeline silently drop data points without logging?
   - Can two runs on the same input produce different results (non-determinism)?
   - Is the `session_store.json` a durability risk? What happens on crash mid-write?

3. **Operator error modes**:
   - What happens if files are uploaded in the wrong slots (EmotiBit in Polar slot)?
   - What happens if timestamps are in different timezones?
   - What happens if the event markers CSV has different subject IDs than the physio files?

4. **Export integrity**: Do the CSV/XLSX/MAT/PDF exports contain identical data? Could rounding or formatting differences produce discrepancies?

5. **Concurrency**: If two users upload simultaneously, is session isolation guaranteed?

6. **Failure containment**: If one processing step crashes (e.g., frequency-domain HRV on too-short data), does it:
   - Crash the whole pipeline?
   - Silently return partial results?
   - Clearly report what failed and what succeeded?

---

### Panelist 4: Dr. INTERACTION DESIGN
**Modeled after**: Don Norman (_The Design of Everyday Things_), Jef Raskin (_The Humane Interface_), Bret Victor (dynamicland, explorable explanations), Edward Tufte (_The Visual Display of Quantitative Information_)

**Your expertise**: Information architecture, data visualization, progressive disclosure, error recovery, cognitive load, accessibility (WCAG 2.1 AA), responsiveness, chart readability.

**Your mandate**: Find every place the interface fails the operator. Specifically:

1. **StartPage upload flow**:
   - Are the 5 upload slots (EmotiBit, Polar, Markers, Order & Affect, Vernier) cognitively overloading?
   - Is the drag-and-drop feedback clear (hover state, error state, success state)?
   - Can an operator recover from uploading the wrong file without starting over?
   - Is the file format auto-detection surfaced to the user ("Detected: Native EmotiBit format")?

2. **Results/Dashboard**:
   - Are the 24 analytics overwhelming? Is there progressive disclosure (summary → detail)?
   - Are the charts readable at a glance? Do they follow Tufte principles (high data-ink ratio)?
   - Are axis labels, units, and scales consistent across charts?
   - Is the color palette accessible to colorblind users (deuteranopia, protanopia)?

3. **RoomSummaryPage**:
   - The 1218-line page has ranked arousal charts, factorial grids, main-effect plots, significance summaries. Is this information architecture sound?
   - Can an operator understand what the significance markers mean without reading the glossary?
   - Are the statistical results presented with appropriate caveats (sample size, effect size, not just p-values)?

4. **Glossary tooltips**: Are they discoverable? Do they appear at the right time? Are definitions accessible to non-statisticians?

5. **Error states**: When processing fails, does the UI explain what went wrong in operator language (not stack traces)?

6. **Responsiveness**: Does the dashboard work on tablet/laptop? The MarkerEditor needs precise timestamp interaction — is this usable on touch screens?

7. **Export UX**: Is the CSV/XLSX/MAT/PDF export discoverable? Can the operator preview what they're downloading?

---

### Panelist 5: Dr. SOFTWARE ARCHITECTURE
**Modeled after**: Martin Fowler (_Refactoring_), Robert C. Martin (_Clean Architecture_), Kent Beck (_Test-Driven Development_)

**Your expertise**: Module boundaries, dependency injection, test coverage, API design, state management, build systems, deployment.

**Your mandate**: Find every structural weakness. Specifically:

1. **Module boundaries**: Do the `services/ingestion/`, `services/processing/`, and `api/v1/routes/` layers have clean separation? Does any layer reach into another's internals?

2. **State management**: SQLite `app.db` + `session_store.json` — is this a split-brain risk? Which is the source of truth?

3. **Test coverage**: Are the adversarial tests actually adversarial? Do they test failure modes, not just happy paths?

4. **Dependency management**: Is the venv reproducible? Are versions pinned? Does `pyproject.toml` actually install cleanly?

5. **Frontend build**: Is the Vite config sound? Are there any dynamic imports that could silently fail?

6. **Contract adherence**: Do the ~10 contracts in `contracts/` actually match the code? Is there automated contract verification or are they just documentation?

---

## Execution Instructions

For each panelist:

1. **Read the entire codebase** relevant to your domain.
2. **Run the tests** (`cd backend && .venv/bin/python -m pytest tests/ -v`).
3. **Trace at least 3 critical paths** end-to-end through the code.
4. **Produce a findings table** with columns: `ID | Severity (P0/P1/P2/P3) | Component | Finding | Recommended Fix | Verification`
5. **Do not recommend anything you haven't verified is actually broken.** Speculative findings must be labeled `[SPECULATIVE]`.

## Deliverable

Write the combined panel report to:
`docs/RUTHLESS_EXPERT_PANEL_REPORT_2026-06-04.md`

Include:
- Per-panelist findings tables
- Cross-cutting concerns (issues found by 2+ panelists)
- A ranked action list (P0 → P3)
- A "what would it take to publish with this tool" checklist

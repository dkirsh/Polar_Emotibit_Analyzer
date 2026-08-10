# Plant vs No-Plant — cohort analysis (cleaning, normalization, results)

*Source: `david_resp_emotibit_hadoff` (May 30 dataset). Scripts:
`scripts/cohort_plant_analysis.py` (clean → measure) and
`scripts/cohort_tables_and_figures.py` (tables → stats → figures). Outputs in
`outputs/cohort/`.*

## 1. How the data were cleaned

**Inclusion.** 24 subject folders; `sub_1.1_G1` ignored as instructed. Six
folders had vernier but no EmotiBit biometrics (`1.11, 1.13, 2.13, 2.4, 2.6,
2.7`) → excluded (your "must have both" rule). `sub_2.14_G1`'s biometrics export
is corrupted (wrong schema, unparseable) → excluded. **16 subjects analyzed**;
15 have both plant and no-plant conditions (`sub_1.9_G4` has only no-plants).

**A timezone trap, fixed.** The biometrics files come in two layouts — a 7-column
one with a local-time ISO `timestamp`, and an 8-column one that *also* carries
`timestamp_unix` (the UTC epoch of that local time). The vernier files use a
local-time ISO string. Mixing `timestamp_unix` (UTC) with the vernier local
string put the two recordings ~7 hours apart, so condition windows landed on
empty data. Fix: align **both** files on their ISO `timestamp` column parsed
tz-naive. This is exactly the silent-misalignment failure these instruments are
prone to.

**EDA.** Range-filtered to 0–60 µS, then winsorized to each subject's 5th–95th
percentile before computing per-condition tonic means.

**Heart / HRV — and a key caveat.** The only beat-to-beat heart data is the
EmotiBit wrist `BI` (beat interval); the vernier belt has no heart signal (its
`RR` column is respiration rate). We range-filtered BI to 300–2000 ms, applied
Lipponen–Tarvainen (2019) ectopic correction, and invalidated HRV when the
corrected fraction exceeded 25% (Peters et al., 2008). **Even so, most subjects'
HRV is physiologically impossible** — RMSSD of 300–620 ms (normal ≈ 20–60 ms) —
because wrist optical beat detection is too noisy for HRV. We therefore added a
plausibility gate (RMSSD > 200 ms or SDNN > 300 ms → invalid). **Only 7 of 16
subjects yield trustworthy HRV.** This is the same "impossibly high HRV" you saw
before; the honest conclusion is that HRV is not analyzable from this wrist BI.

**Respiration.** From the vernier belt. Mean **respiratory rate** uses the
device's own rate column (reliable; cohort median ≈ 13 bpm). Stress *patterns*
are detected per breath from the force signal (low-pass filtered to suppress
over-detection) against each subject's own distribution. These per-breath
pattern flags are **experimental and noisy** on belt data and are used only for
within-subject (paired) contrasts, never as absolute rates.

## 2. How the data were normalized

Between-subject EDA and HRV *levels* differ enormously (EDA tonic ranged 0.1–3.7
µS across subjects), so a raw cohort mean would be dominated by individual
physiology, not by condition. Each measure is therefore expressed **relative to
the subject's own two-condition mean** (within-subject centering;
`table2_within_subject_normalized.csv`). Because the design is two conditions,
this is equivalent to a **paired, within-subject difference** (plants −
no_plants), which is what the statistics below test. This is the field-standard
referencing (Laborde et al., 2017; SPR EDA committee, 2012) and the method you
proposed.

## 3. Plant vs No-Plant — results (paired, within-subject)

| Measure | n | mean diff (plants − no_plants) | Cohen's dz | paired t p | Wilcoxon p |
|---|---|---|---|---|---|
| EDA tonic (µS) | 15 | +0.06 | 0.09 | 0.72 | 0.68 |
| Respiration rate (bpm) | 15 | −0.45 | −0.21 | 0.42 | 0.68 |
| Resp. stress index (frac, *exp.*) | 15 | +0.045 | 0.53 | 0.058 | 0.073 |
| Resp. stress weighted (*exp.*) | 15 | +0.03 | 0.32 | 0.23 | 0.19 |
| RMSSD (ms, *valid HRV only*) | 7 | −11.7 | −0.70 | 0.11 | 0.11 |

**Reading it.** On the trustworthy measures there is **no significant plant vs
no-plant effect**: EDA tonic arousal is essentially identical between conditions
(dz = 0.09), and respiration rate is slightly lower in plants (−0.45 bpm) but not
significant. The experimental respiratory **stress index** trends *higher* in
plants (dz = 0.53, p = 0.058) — the opposite of a restorative effect — but this
is the noisy belt-pattern measure and should not be over-interpreted. HRV is
suggestive (RMSSD lower in plants in 6 of 7) but underpowered and from the
unreliable BI source.

**Bottom line.** In this sample, with defensible cleaning and within-subject
normalization, **the data do not show a plant vs no-plant difference** in the
measures that can be trusted (EDA, respiration rate). The HRV channel is not
usable from wrist BI, and the respiratory-pattern stress scale is too noisy to
support a directional claim. This is a genuine null/underpowered result, not a
positive restorative effect.

## 4. What would make this conclusive
A trustworthy heart source (chest ECG / Polar H10 rather than wrist optical) for
HRV; more subjects with both conditions (n = 15 gives ~80% power only for dz ≳
0.75); and a validated respiratory-pattern measure. The cleaning, normalization,
and comparison pipeline is in place and will re-run on better data unchanged.

## Figures (in `outputs/cohort/`)
- `fig1_paired_measures.png` — per-subject paired change, four key measures.
- `fig2_effect_sizes.png` — forest plot of within-subject effect sizes.
- `fig3_pattern_heatmap.png` — respiratory pattern counts per subject.
- `fig4_resp_stress_scale.png` — respiratory stress scale by condition.

## References
Laborde, S., Mosley, E., & Thayer, J. F. (2017). *Front. Psychol., 8*, 213.
Lipponen, J. A., & Tarvainen, M. P. (2019). *J. Med. Eng. Technol., 43*(3), 173–181.
Peters, C. H. L., et al. (2008). *Proc. IEEE EMBS*, 2669–2672.
Society for Psychophysiological Research Ad Hoc Committee on Electrodermal
Measures (Boucsein, W., et al.). (2012). *Psychophysiology, 49*(8), 1017–1034.

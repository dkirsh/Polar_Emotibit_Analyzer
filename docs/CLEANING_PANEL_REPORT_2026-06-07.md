# Expert panel — cleaning & normalization of EDA / HRV / respiration data

*A convened panel of expert perspectives on preprocessing psychophysiological
data, each grounded in the literature (retrieved via scite) and mapped to what
the Polar–EmotiBit Analyzer currently does. Status key: ✓ implemented, ◑ partial,
✗ missing. The framing is "the case these specialists would make," not attributed
quotations.*

The motivating concern is concrete: a prior cohort analysis contained
**impossibly high HRV**. Every panelist converges on the same diagnosis — that is
the signature of unscreened artifact correction and missing within-subject
referencing, and it is preventable with the steps below.

## Panelist 1 — HRV methodologist (cardiac psychophysiology)
- **Artifact correction is the single most consequential step, and must be
  surfaced, not trusted blindly.** Laborde, Mosley & Thayer (2017) explicitly
  warn against relying solely on automatic correction (e.g. Kubios), because
  auto-flagged "artifacts" can be real beats and vice-versa. *Status:* ◑ — the
  analyzer applies Lipponen–Tarvainen (2019) correction and flags >5% ectopic,
  but does not expose per-subject corrected-fraction for human screening.
- **There is a ceiling on how much correction is admissible.** Peters et al.
  (2008) show HF-band power becomes unreliable once correction/interpolation
  exceeds ~25% of beats. *Status:* ✗ — recommend returning `None` for HF metrics
  above that ceiling. **This is the most direct guard against impossibly high
  HRV.**
- **Report a parsimonious, non-redundant index set.** Pham et al. (2025) cluster
  89 HRV indices into ~21 families and recommend ~13 (RMSSD, SDNN, SD1/SD2,
  HF/lnHF, a nonlinear index, …). *Status:* ◑ — the analyzer computes a sensible
  core already; just avoid over-reporting correlated indices.

## Panelist 2 — Electrodermal (EDA) specialist
- **Follow the SPR electrodermal guidelines** (Society for Psychophysiological
  Research Ad Hoc Committee on Electrodermal Measures; Boucsein et al., 2012):
  preprocess, detect and discard artifacts, then extract tonic (SCL) and phasic
  (SCR) features. *Status:* ◑ — range filter + winsorize + a phasic index, but no
  formal SCR detection.
- **Use model-based decomposition for tonic/phasic separation** — continuous
  decomposition analysis (Benedek & Kaernbach, 2010) or cvxEDA (Greco et al.,
  2016). *Status:* ✗ — the code references these as the right approach but
  implements only a moving-average index.
- **Between-subject EDA level is dominated by individual skin properties, not
  psychology — so normalize within subject** (range-correction / standardization
  is the classic remedy). *Status:* ✗→✓ — addressed by the within-subject
  centring added in this change.

## Panelist 3 — Wearable-sensor signal engineer
- **Wrist EDA is motion-corrupted; use an absolute accelerometer threshold, not
  a fixed percentile.** Kleckner et al. (2018) validate ~0.2–0.5 g for wrist
  sensors. *Status:* ✓ — the analyzer uses 0.3 g (data-dependent), having
  explicitly replaced a defensible-looking but wrong percentile(90) rule.
- **Default toolbox parameters mislead across devices/contexts.** Thammasan
  et al. (2020) show automatic preprocessing with defaults yields misleading
  results when device and context differ. *Status:* ✓ in spirit — the analyzer's
  thresholds are explicit and configurable; the new regimentation layer makes
  device/format differences explicit rather than assumed.

## Panelist 4 — Statistician / reproducibility methodologist
- **Normalize within subject before pooling.** With ~16 subjects and large
  between-person offsets, a raw cohort mean is dominated by level differences.
  Centring each subject on their own mean (or standardizing) makes condition
  contrasts comparable — exactly the user's proposed method. *Status:* ✓ (added).
- **Report dispersion and effect sizes, flag underpowered cells.** Already the
  stance of the condition-comparison stats stage.
- **Keep raw and derived side by side, with provenance** so any normalization
  is reversible and auditable. *Status:* ✓ — raw values retained; provenance
  recorded.

## Panelist 5 — Respiration physiologist
- **HF-HRV is respiration-driven; interpret it as vagal tone only with
  respiration observed** (Laborde et al., 2017; Grossman & Taylor). *Status:* ◑ —
  belt respiration exists but is not yet shown beside HF. Recommend surfacing
  mean respiratory rate next to HF in the cohort view.
- **A respiratory-pattern stress scale is reasonable but must be labelled
  derived/experimental**, anchored to interpretable per-breath features (rate,
  I:E, amplitude, variability), not presented as a validated index.

## Consensus recommendations → incorporation
1. **Within-subject mean-centring normalization** — *incorporated now* in
   `normalization.py` (and recorded as DONE in the cleaning contract).
2. **Artifact-fraction ceiling (~25%) invalidates HF metrics** — recorded as a
   REQUIRED addition in the contract; small, high-value next code step.
3. **Model-based EDA decomposition** — REQUIRED; larger, scheduled.
4. **Expose per-subject ectopic %, corrected-fraction, motion-loss in the cohort
   table** — REQUIRED; directly prevents the impossibly-high-HRV failure.
5. **Respiration beside HF** — REQUIRED in the cohort/condition view.

## References (APA; citation counts via scite where available, else approximate)
Benedek, M., & Kaernbach, C. (2010). A continuous measure of phasic electrodermal
activity. *Journal of Neuroscience Methods, 190*(1), 80–91. (≈1,400, approx.)

Greco, A., Valenza, G., Lanata, A., Scilingo, E. P., & Citi, L. (2016). cvxEDA: A
convex optimization approach to electrodermal activity processing. *IEEE
Transactions on Biomedical Engineering, 63*(4), 797–804. (≈800, approx.)

Kleckner, I. R., Jones, R. M., Wilder-Smith, O., et al. (2018). Simple, transparent,
and flexible automated quality assessment procedures for ambulatory electrodermal
activity. *IEEE Transactions on Biomedical Engineering, 65*(7), 1460–1467.

Laborde, S., Mosley, E., & Thayer, J. F. (2017). Heart rate variability and cardiac
vagal tone in psychophysiological research. *Frontiers in Psychology, 8*, 213.
(≈2,570 citing publications, scite)

Lipponen, J. A., & Tarvainen, M. P. (2019). A robust algorithm for heart rate
variability time series artefact correction. *Journal of Medical Engineering &
Technology, 43*(3), 173–181.

Peters, C. H. L., Vullings, R., Bergmans, J. W. M., et al. (2008). The effect of
artifact correction on spectral estimates of heart rate variability. *Proceedings
of the IEEE EMBS*, 2669–2672. (≈24 citing publications, scite)

Pham, T., Johnco, C. J., Lau, Z. J., et al. (2025). Which HRV indices should I use
for psychophysiological research? *Psychophysiology, 62*(10). (new)

Quigley, K. S., Gianaros, P. J., Norman, G. J., et al. (2024). Publication
guidelines for human heart rate and heart rate variability studies in
psychophysiology — Part 1. *Psychophysiology, 61*(9), e14604. (≈86, scite)

Society for Psychophysiological Research Ad Hoc Committee on Electrodermal Measures
(Boucsein, W., et al.). (2012). Publication recommendations for electrodermal
measurements. *Psychophysiology, 49*(8), 1017–1034. (very high, approx.)

Thammasan, N., Stuldreher, I. V., Schreuders, E., et al. (2020). A usability study
of physiological measurement in school using wearable sensors. *Sensors, 20*(18),
5380. (≈43, scite)

Task Force of the European Society of Cardiology and the North American Society of
Pacing and Electrophysiology. (1996). Heart rate variability: Standards of
measurement. *Circulation, 93*(5), 1043–1065. (very high, approx.)

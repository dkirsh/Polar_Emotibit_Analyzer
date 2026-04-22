# Stress Composite Contract

**Module**: `app/services/processing/stress.py`
**Date**: 2026-04-22
**Status**: In force. The composite is **experimental**; it is not
psychometrically validated against standardised instruments.

## Scope

The stress composite module computes two exploratory, multimodal
physiological indices of autonomic activation: `stress_score` (v1,
five channels) and `stress_score_v2` (v2, seven channels with
Kubios-grade HRV inputs). Both return a scalar in [0, 1] where higher
values indicate greater estimated sympathetic activation. The scheme
is documented in full in
[`docs/STRESS_COMPOSITE_V2_PANEL_JUSTIFICATION_2026-04-21.md`](../docs/STRESS_COMPOSITE_V2_PANEL_JUSTIFICATION_2026-04-21.md),
the five-expert panel consultation record that accompanied the
v2 launch.

## Inputs

**v1 — `compute_stress_score(rmssd_ms, mean_hr_bpm, eda_mean_us,
eda_phasic_index, rsa_amplitude=None)`**. Positional inputs; all
floats. `rsa_amplitude` may be `None`, which triggers the four-channel
fallback with redistributed weights.

**v2 — `compute_stress_score_v2(*, rmssd_ms, mean_hr_bpm, eda_mean_us,
eda_phasic_index, pnn50=None, sd1_sd2_ratio=None, lf_nu=None,
rsa_amplitude=None)`**. Keyword-only. Any of the four optional
channels may be `None`, in which case the absent channel's weight
redistributes equally across the present channels.

## Outputs

**v1**: a single float in [0, 1].

**v2**: a tuple `(score, contributions)` where `score` is a float in
[0, 1] and `contributions` is a dict mapping each of seven channel
names (`hr`, `eda`, `phasic`, `vagal`, `sympathovagal`, `rigidity`,
`rsa`) to the per-channel contribution to the final score, or `None`
if the channel was inactive. The dict also carries
`_active_channels` (float, count 4–7) and `_vagal_protection` (float,
raw vagal composite value 0–1) for audit.

## Success conditions

1. **Output range.** Both versions return a score in [0, 1] for any
   legal input. Enforced by construction (explicit clip in both
   functions) and by existing `test_features.py` cases.
2. **v2 channel count.** `contributions["_active_channels"]` equals
   the count of non-None optional channels plus 4 (the four always-
   present channels). Verified by inspection of Welltory
   subject_01 and subject_05 outputs (both 5-channel; LF_nu and RSA
   missing on sessions shorter than 120 s).
3. **v2 weight redistribution.** When a channel is absent, its base
   weight (from `base_weights`) redistributes equally across the
   present channels. The effective weights therefore always sum to
   1.0 within floating-point rounding.
4. **v1/v2 divergence is interpretable.** On sessions where vagal
   tone is high (Welltory subject 01), v2 ≤ v1; on sessions where
   the SD1/SD2 ratio signals rigidity (Welltory subject 05), v2 ≥ v1.
   Documented in the commit message of `526bd21`.

## Non-promises

- **Not psychometrically validated.** Neither score is calibrated
  against the Perceived Stress Scale (Cohen, Kamarck & Mermelstein,
  1983) or the Depression Anxiety Stress Scales (Lovibond & Lovibond,
  1995). Validation is a 90-day task flagged in the v1 module
  docstring.
- **Not an absolute between-subject measure.** The normalisation
  constants are approximate population bands, not individually
  calibrated. A score of 0.6 in one subject and a score of 0.6 in
  another do not warrant the claim that the two are equally stressed.
- **Not a diagnostic instrument.** See
  [`NON_DIAGNOSTIC_CONTRACT_2026-04-22.md`](NON_DIAGNOSTIC_CONTRACT_2026-04-22.md).
- **Not a substitute for concurrent psychometric measurement.** For
  any between-subject claim, pair the composite with a validated
  instrument administered in the same session.
- **Does not establish causation.** A within-session rise is
  consistent with a stress response but also with posture change,
  thermal load, breathing-pattern change, or physical movement.

## Test coverage

Basic coverage in `backend/tests/test_features.py`. End-to-end
integration on real Welltory data in
`backend/tests/test_real_data_audit.py`. Panel-level justification of
the weighting scheme is prose, not pytest — see the panel document
for the seven channels' rationale and citations.

## References

See the panel document for the full reference list. Key citations
for the weighting scheme:

Thayer, J. F., Åhs, F., Fredrikson, M., Sollers, J. J., & Wager,
T. D. (2012). A meta-analysis of heart rate variability and
neuroimaging studies. *Neuroscience & Biobehavioral Reviews*, 36(2),
747–756. https://doi.org/10.1016/j.neubiorev.2011.11.009

Shaffer, F., & Ginsberg, J. P. (2017). An overview of heart rate
variability metrics and norms. *Frontiers in Public Health*, 5, 258.
https://doi.org/10.3389/fpubh.2017.00258

Porges, S. W. (2007). The polyvagal perspective. *Biological
Psychology*, 74(2), 116–143.
https://doi.org/10.1016/j.biopsycho.2006.06.009

Schmidt, P., Reiss, A., Duerichen, R., Marberger, C., & Van
Laerhoven, K. (2018). Introducing WESAD, a multimodal dataset for
wearable stress and affect detection. *Proc. ICMI*, 400–408.
https://doi.org/10.1145/3242969.3242985

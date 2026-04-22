# HRV Feature Contract

**Module**: `app/services/processing/features.py`
**Date**: 2026-04-22
**Status**: In force.

## Scope

The HRV feature module computes time-domain, Poincaré nonlinear, and
frequency-domain heart rate variability indices from a DataFrame of
inter-beat intervals. The feature set is a Kubios-parity subset,
covering the panels a Kubios HRV Premium user would expect (RMSSD,
SDNN, mean HR, NN50, pNN50, SD1, SD2, SD1/SD2 ratio, ellipse area,
VLF, LF, HF, total power, LF_nu, HF_nu, VLF%, LF%, HF%, LF/HF ratio).

## Inputs

A `pandas.DataFrame` with either column `rr_ms` (native RR intervals
in milliseconds) or column `hr_bpm` (heart rate in beats per minute).
When `rr_ms` is present it is preferred; when absent RR is derived as
`60000 / hr_bpm` and the degraded accuracy is reported via
`rr_source = "derived_from_bpm"`.

Minimum preconditions: at least 3 beats for time-domain features; at
least 11 beats for Lipponen-Tarvainen ectopic correction (shorter
inputs fall back to the legacy local-median filter); at least 30
beats (≥ 60 s at the HF band minimum) for any frequency-domain band.
Each frequency band additionally requires a minimum recording duration
per Task Force (1996): HF ≥ 60 s, LF ≥ 120 s, VLF ≥ 300 s.

## Outputs

Four functions:

**`compute_hrv_features(df)`** returns `(rmssd_ms, sdnn_ms,
mean_hr_bpm, rr_source)` as a legacy 4-tuple.

**`compute_time_domain_features(df)`** returns a dict with keys
`rmssd_ms`, `sdnn_ms`, `mean_hr_bpm`, `nn50`, `pnn50`, `rr_source`.

**`compute_poincare_features(df)`** returns a dict with keys
`sd1_ms`, `sd2_ms`, `sd1_sd2_ratio`, `ellipse_area_ms2`. Any key may
be `None` if the input has fewer than 4 beats.

**`compute_hrv_frequency_features(df, *, resample_hz=4.0)`** returns a
dict with keys `vlf_ms2`, `lf_ms2`, `hf_ms2`, `lf_hf_ratio`,
`total_power_ms2`, `lf_nu`, `hf_nu`, `vlf_pct`, `lf_pct`, `hf_pct`,
`rr_source`. Any band may be `None` if the recording is shorter than
the band's minimum duration per Task Force (1996).

Ectopic correction: `lipponen_tarvainen_correction(rr, c1=0.13,
c2=0.17, median_window=11)` returns `(corrected_rr, ectopic_mask)`.
Flagged beats are replaced by cubic-spline interpolation over the
surviving normal beats; beat count is preserved.

## Success conditions

1. **Textbook-formula parity on real data.** Pipeline RMSSD, SDNN,
   and mean HR match direct calculation on Welltory subjects 01 and
   05 within 1 unit of their respective scales, after L&T ectopic
   correction is applied to the reference. Enforced by
   `test_welltory_hrv_matches_ground_truth`.
2. **NN50 exact match.** `compute_time_domain_features` returns an
   NN50 count that matches `sum(abs(diff(rr)) > 50)` on the raw RR
   series. Verified on Welltory data.
3. **Normalised-unit constraint.** When both LF and HF are defined,
   `lf_nu + hf_nu` equals 100 (to within floating-point rounding).
4. **Poincaré closed-form identities.** SD1 equals RMSSD divided by
   the square root of 2 within floating-point rounding. SD2²
   equals 2·var(RR) − var(dRR)/2 within floating-point rounding.
5. **L&T length stability.** `lipponen_tarvainen_correction` returns
   a corrected array of identical length to its input.

## Non-promises

- The module does **not** compute geometric HRV descriptors beyond
  Poincaré: no triangular index, no TINN.
- The module does **not** compute nonlinear HRV beyond Poincaré:
  no approximate entropy, no sample entropy, no detrended-fluctuation
  analysis α-1 or α-2, no recurrence-plot density.
- The module does **not** detrend the RR series with smoothness
  priors (Tarvainen et al. 2002). Detrending is `detrend="constant"`
  inside the Welch method.
- The module does **not** enforce a minimum recording length beyond
  the Task Force (1996) band minima. Sessions shorter than the LF
  minimum silently return `None` for LF-dependent fields rather than
  raising; callers check for `None`.

## Test coverage

`backend/tests/test_features.py` and
`backend/tests/test_real_data_audit.py`. Real-data parity on Welltory
subjects 01 and 05 locks items 1–2 above.

## References

Task Force of the European Society of Cardiology and the North
American Society of Pacing and Electrophysiology. (1996). Heart rate
variability. *Circulation*, 93(5), 1043–1065.
https://doi.org/10.1161/01.CIR.93.5.1043

Brennan, M., Palaniswami, M., & Kamen, P. (2001). Do existing
measures of Poincaré plot geometry reflect nonlinear features of
heart rate variability? *IEEE Transactions on Biomedical
Engineering*, 48(11), 1342–1347.
https://doi.org/10.1109/10.959330

Lipponen, J. A., & Tarvainen, M. P. (2019). A robust algorithm for
heart rate variability time series artefact correction using novel
beat classification. *Journal of Medical Engineering & Technology*,
43(3), 173–181. https://doi.org/10.1080/03091902.2019.1640306

Shaffer, F., & Ginsberg, J. P. (2017). An overview of heart rate
variability metrics and norms. *Frontiers in Public Health*, 5, 258.
https://doi.org/10.3389/fpubh.2017.00258

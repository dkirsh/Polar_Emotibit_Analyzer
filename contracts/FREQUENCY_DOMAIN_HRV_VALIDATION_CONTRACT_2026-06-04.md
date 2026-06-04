# Frequency-Domain HRV Validation Contract

**Module**: `backend/app/services/processing/features.py::compute_hrv_frequency_features`
**Test**: `backend/tests/test_frequency_domain_validation.py`
**Version**: 1.0
**Date**: 2026-06-04

---

## Purpose

Validates that the Welch-based frequency-domain HRV implementation faithfully
computes spectral power in the VLF, LF, and HF bands per the Task Force of
the European Society of Cardiology (1996) standard.

## Invariants

1. **Band definitions** match Task Force (1996):
   - VLF: 0.003–0.04 Hz
   - LF:  0.04–0.15 Hz
   - HF:  0.15–0.40 Hz

2. **Welch's method** is used (not simple periodogram), reducing spectral
   variance per Welch (1967). Parameters: Hann window, nperseg=min(256, N),
   50% overlap, constant detrend.

3. **Per-band minimum recording duration** enforced per Task Force:
   - VLF: ≥ 300s (5 min)
   - LF:  ≥ 120s (2 min)
   - HF:  ≥ 60s  (1 min)
   - Bands below minimum return `None`, not zero.

4. **Normalized units** (LF_nu, HF_nu) sum to exactly 100%.

5. **Total power** = VLF + LF + HF (when all bands available).

6. **Percent-of-total** (VLF%, LF%, HF%) sum to ~100%.

## Preconditions

- Input DataFrame must contain `rr_ms` or `hr_bpm` column.
- At least 30 RR intervals required for any output.

## Postconditions

- A 10-minute synthetic recording with known LF amplitude 30 ms and HF
  amplitude 20 ms recovers LF power within ±50% of theoretical (450 ms²)
  and HF power within ±50% of theoretical (200 ms²).
- LF/HF ratio for balanced sympathovagal input falls in [1.0, 4.0].
- Pure-LF signal yields LF > 5× HF; pure-HF signal yields HF > 5× LF.

## Failure Modes

| Condition | Response | Error |
|-----------|----------|-------|
| < 30 beats | All bands return None | No error |
| < 60s recording | VLF and LF return None, HF computed | No error |
| < 120s recording | VLF returns None, LF and HF computed | No error |
| < 300s recording | VLF returns None | No error |
| scipy.signal.welch fails | All bands return None (caught exception) | No error |

## Verification

11 automated tests in `test_frequency_domain_validation.py`:
1. 10-min LF/HF power recovery (±50% of theoretical)
2. LF/HF ratio in physiological range
3. LF_nu + HF_nu = 100%
4. VLF% + LF% + HF% ≈ 100%
5. Short recording (200s) suppresses VLF
6. Very short recording (90s) suppresses LF
7. 1-min recording retains HF
8. < 30 beats returns all-None
9. HF-dominant signal yields HF > LF
10. total_power = VLF + LF + HF
11. Band boundary integrity (pure-LF vs pure-HF separation)

## References

- Task Force (1996). Circulation, 93(5), 1043-1065.
- Welch (1967). IEEE Trans Audio Electroacoustics, 15(2), 70-73.
- Goldberger et al. (2000). Circulation, 101(23), e215-e220.

# EDR Proxy RR Provenance Contract

**Module**: `app/services/processing/features.py`
**Date**: 2026-06-04
**Status**: In force.

## Scope

The ECG-derived respiration (EDR) proxy estimates breath timing from
RR-interval modulation. This contract governs the propagation of
`rr_source` through the EDR computation so that downstream consumers
know whether the input RR intervals came from native Polar data
(strong provenance) or were arithmetically derived from BPM (weak
provenance).

## Invariants

1. **`rr_source` propagated.** The dict returned by
   `compute_edr_detailed()` and `compute_edr_detailed_from_rr_ms()`
   includes `rr_source` and `rr_source_note` fields at the top level.

2. **Quality includes source confidence.** The `quality` sub-dict
   contains `source_confidence` (float, 0–1) derived from
   `rr_source_confidence_for(rr_source)`, and `overall_confidence`
   that blends signal and source confidence.

3. **BPM-derived degradation flag.** When `rr_source` is
   `"derived_from_bpm"`, the quality dict includes `degraded: True`
   and the `verdict` is capped at `"weak"` regardless of signal
   quality.

4. **Source confidence tiers.**
   - `native_polar` → 1.0
   - `derived_from_ecg` → 0.8
   - `derived_from_bpm` → 0.4
   - unknown/other → 0.2

## Preconditions

- `_get_rr_intervals(df)` returns a `(rr_array, source_string)` tuple.
- Callers of `compute_edr_detailed_from_rr_ms()` should pass
  `rr_source` when known.

## Postconditions

- The EDR proxy output is self-documenting: any consumer can read
  `rr_source`, `rr_source_note`, and `quality.degraded` to decide
  whether to trust the breath-timing estimates.
- The analysis router's `edr_proxy` payload in the session store
  carries matching provenance fields.

## Failure modes

| Symptom | Cause | Resolution |
|---------|-------|------------|
| `rr_source` missing from EDR output | `compute_edr_detailed` discards the source with `rr, _ = _get_rr_intervals(df)` | Capture source: `rr, source = _get_rr_intervals(df)` |
| BPM-derived EDR shows "strong" verdict | Degradation flag not checked | Ensure `_is_degraded` caps verdict at "weak" |
| `source_confidence` is None | `rr_source` not passed to inner function | Pass `rr_source` kwarg through |

## Test coverage

- `backend/tests/test_quickfixes.py::test_t4_bpm_derived_edr_flagged_degraded`
- `backend/tests/test_quickfixes.py::test_t4_native_polar_edr_not_degraded`
- `backend/tests/test_quickfixes.py::test_t4_edr_from_rr_ms_with_rr_source`
- `backend/tests/test_api.py::test_edr_proxy_backfill_uses_existing_rr_source`

## References

- Task Force ESC/NASPE (1996). Circulation, 93(5), 1043-1065.

# Contract — Respiratory Stage 0: Signal (source of truth)

Module: `backend/app/services/processing/respiratory/signal.py`

## Purpose
Turn a raw Vernier belt recording into the analysis substrate and serve as the
single source of truth from which all downstream tables, statistics, and figures
are derived and recomputable.

## Inputs
- `from_vernier(vernier_result, markers)` — parsed belt result containing
  `_timeseries` (force), `metadata.sample_rate_hz`, and optional event markers.
- `from_payload(payload)` — the persisted recompute payload (`resp_z`, `peaks`,
  `troughs`, `fs`, `cycles`), requiring no raw file.

## Outputs
`SignalResult`: `resp_z`, `peaks`, `troughs`, `fs`, `cycles_df`,
`event_markers`, `error`. `to_recompute_payload()` yields the serialisable
source-of-truth block (NaN/inf sanitised to null).

## Invariants & success conditions
- Either a usable signal (`error is None` and `len(cycles_df) >= MIN_CYCLES`) or
  `error` set with a typed reason. Never a partial signal presented as complete.
- `to_recompute_payload()` round-trips: `from_payload(sig.to_recompute_payload())`
  yields an equivalent `SignalResult`.

## Failure modes (all return a typed `error`, never raise)
Missing timeseries; recording too short; insufficient peaks/troughs; no cycles.

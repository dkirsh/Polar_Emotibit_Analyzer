"""Analysis endpoint — the primary workload.

Accepts a pre-synched pair of Polar H10 + EmotiBit CSVs (plus optional
markers and metadata) and returns the V2.1 pipeline's structured response.
Session metadata is persisted to an in-process session store so the
frontend's "Recent sessions" table and view 2 re-read both work without
a full database layer in the first cut.

Refactored 2026-06-04: split into sub-modules while preserving all public
names and the API surface. This file re-exports everything for backward
compatibility.

Sub-modules:
  - analysis_helpers.py — session store, helper functions
  - analysis_core.py   — /analyze, /analyze/single, session CRUD endpoints
  - analysis_export.py — /export, /benchmark/kubios endpoints
"""
from __future__ import annotations

from fastapi import APIRouter

# Import routers from sub-modules
from app.api.v1.routes.analysis_core import router as _core_router
from app.api.v1.routes.analysis_export import router as _export_router

# Re-export all public helpers so existing imports like
# `from app.api.v1.routes.analysis import _SESSION_STORE` keep working.
from app.api.v1.routes.analysis_helpers import (  # noqa: F401
    _SESSION_STORE,
    _STORE_PATH,
    _session_store_initialized,
    _baseline_window_stress_v2,
    _empty_stats,
    _filter_markers_to_data_range,
    _is_zip,
    _is_zip_bytes,
    _load_store_from_disk,
    _markers_overlap_dataframe,
    _maybe_backfill_edr_proxy,
    _migrate_stored_sessions,
    _persist_store,
    _polar_room_dataframe,
    _series_stats,
    _stress_v2_components,
    _subsample_timeseries,
    _summary_stats,
    init_session_store,
)

# Composite router that merges all sub-module routes.
router = APIRouter(tags=["analysis"])
router.include_router(_core_router)
router.include_router(_export_router)

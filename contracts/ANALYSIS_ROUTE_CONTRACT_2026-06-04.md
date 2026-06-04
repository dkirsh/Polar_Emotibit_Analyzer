# Analysis Route Refactor Contract

**Module**: `backend/app/api/v1/routes/analysis.py` → sub-modules
**Version**: 1.0
**Date**: 2026-06-04

---

## Purpose

Guarantees that the analysis route refactoring (splitting the monolithic
320+ line `analysis.py` into sub-modules) preserves the API surface exactly.

## Module Boundaries

| Module | Responsibility |
|--------|---------------|
| `analysis.py` | Thin wrapper: re-exports all public names, merges sub-routers |
| `analysis_helpers.py` | Session store, helper functions, statistics utilities |
| `analysis_core.py` | `/analyze`, `/analyze/single`, session CRUD endpoints |
| `analysis_export.py` | `/export`, `/benchmark/kubios` endpoints |

## Invariants

1. **API surface identity**: Every endpoint URL, HTTP method, request/response
   schema, and status code is identical before and after the refactor.

2. **Import compatibility**: All existing imports from
   `app.api.v1.routes.analysis` continue to work (re-exported from wrapper).

3. **No test modifications**: All existing tests pass without any changes
   to test files (tests import from `analysis`, which re-exports everything).

4. **State coherence**: `_SESSION_STORE`, `_STORE_PATH`, and `init_session_store`
   live in `analysis_helpers.py` and are re-exported through `analysis.py`.

## Failure Modes

| Condition | Response |
|-----------|----------|
| Missing re-export | ImportError at startup — caught by any test run |
| Route duplication | FastAPI raises on duplicate routes at startup |
| Circular import | ImportError at startup |

## Verification

- All 109 tests pass with zero changes to test files
- `from app.api.v1.routes.analysis import _SESSION_STORE, init_session_store` works
- FastAPI app starts without errors

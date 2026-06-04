# Session Store Initialization Contract

**Module**: `app/api/v1/routes/analysis.py`, `app/main.py`
**Date**: 2026-06-04
**Status**: In force.

## Scope

The in-process session store (`_SESSION_STORE`) persists analysis
results to a JSON file on disk. This contract governs *when* that
store is loaded and migrated, specifically that it must NOT happen at
module import time.

## Invariants

1. **No import-time I/O.** Importing `app.api.v1.routes.analysis`
   must NOT read from or write to `session_store.json`. The module-
   level `_SESSION_STORE` dict starts empty.

2. **Explicit initialization.** The function `init_session_store()`
   must be called exactly once, during the FastAPI app's `lifespan`
   startup phase. It loads the JSON snapshot, runs migration, and
   persists if migration changed anything.

3. **Idempotent init.** Calling `init_session_store()` more than once
   is safe — a `_session_store_initialized` guard prevents double-
   loading.

4. **Migration writes only when needed.** `_persist_store()` is
   called during init only if `_migrate_stored_sessions()` returns
   `True` (i.e., at least one record was actually modified).

## Preconditions

- `app.main` must wire the `lifespan` context manager to the FastAPI
  app so `init_session_store()` runs before the first request.

## Postconditions

- After `init_session_store()` completes, the `_SESSION_STORE` dict
  contains all records from the on-disk snapshot (if the file exists).
- All stored records have been migrated to the current schema.

## Failure modes

| Symptom | Cause | Resolution |
|---------|-------|------------|
| `session_store.json` rewritten on import | `init_session_store()` called at module level or `_load_store_from_disk()` left at module level | Ensure the only module-level code is the empty dict and the guard variable |
| Empty session list on first request | `init_session_store()` not wired to lifespan | Verify `app/main.py` uses the `lifespan=lifespan` kwarg |
| Double-load corruption | `init_session_store()` called from two places | Guard variable prevents this |

## Test coverage

`backend/tests/test_quickfixes.py::test_t2_import_does_not_trigger_session_store_io`

## References

- [FastAPI Lifespan Events](https://fastapi.tiangolo.com/advanced/events/)

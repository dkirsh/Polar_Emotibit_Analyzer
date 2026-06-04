# Build Metadata Contract

**Module**: `backend/pyproject.toml`
**Date**: 2026-06-04
**Status**: In force.

## Scope

The `pyproject.toml` file declares the build metadata for the backend
package. This contract covers the `readme` field specifically — the
field that previously referenced a non-existent `README.md` inside
`backend/`, causing editable installs to emit a warning or fail.

## Invariants

1. **`readme` must resolve at build time.** The `readme` value must
   either point to a file that exists relative to `backend/`, or use
   the inline `{text = "...", content-type = "..."}` form so that
   `pip install -e '.[dev]'` succeeds without warnings about a missing
   file.

2. **Editable install must succeed.** Running
   `cd backend && .venv/bin/python -m pip install -e '.[dev]'` from a
   clean venv with Python ≥ 3.10 must exit 0.

## Preconditions

- Python ≥ 3.10 with `pip` and `setuptools ≥ 68`.
- A virtual environment at `backend/.venv`.

## Postconditions

- The package `polar-emotibit-analyzer-backend` is importable.
- `pip show polar-emotibit-analyzer-backend` reports version `2.1.0`.

## Failure modes

| Symptom | Cause | Resolution |
|---------|-------|------------|
| `FileNotFoundError: README.md` during install | `readme` points to a file path that doesn't exist | Use inline text form or create the file |
| Install succeeds with warning about missing readme | Same root cause, lenient pip version | Same resolution |

## Test coverage

`backend/tests/test_quickfixes.py::test_t1_editable_install_metadata`

## References

- [PEP 621 – Storing project metadata in pyproject.toml](https://peps.python.org/pep-0621/)

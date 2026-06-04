# Estelita Analyze Script Contract

**Module**: `Estelita/RespInPeace_Output/code/analyze.py`
**Date**: 2026-06-04
**Status**: In force.

## Scope

The Estelita analysis script uses the `HERE` variable to locate
sibling modules (`rip.py`, `peakdetect.py`) and data files. This
contract ensures `HERE` is defined before any code that references it.

## Invariants

1. **`HERE` defined before first use.** The assignment
   `HERE = os.path.dirname(os.path.abspath(__file__))` must appear
   before any statement that references `HERE`, including
   `sys.path.insert(0, HERE)`.

2. **Single definition.** `HERE` is defined exactly once; there is no
   duplicate assignment later in the file.

3. **`sys.path` injection uses `HERE`.** The `sys.path.insert` that
   makes `rip.py` importable must reference `HERE`, not a hardcoded
   path.

## Preconditions

- Python ≥ 3.8 with `os` and `sys` available.
- The script is run from any working directory (not assumed to be the
  script's own directory).

## Postconditions

- `from rip import Resp` succeeds regardless of the caller's working
  directory.
- `XLSX`, `OUT`, and `STATUS` paths resolve to the correct locations
  beside the script.

## Failure modes

| Symptom | Cause | Resolution |
|---------|-------|------------|
| `NameError: name 'HERE' is not defined` | `HERE` used before definition | Move `HERE = ...` above the first use |
| `ModuleNotFoundError: No module named 'rip'` | `sys.path.insert` uses wrong path | Verify `HERE` points to the script's directory |

## Test coverage

`backend/tests/test_quickfixes.py::test_t3_here_defined_before_use`

## References

Internal to this repository. The Estelita script is a standalone
analysis of Vernier respiration-belt data.

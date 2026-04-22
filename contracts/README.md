# contracts/ — module-level contracts and success conditions

This directory holds formal specifications of what each load-bearing
module of the Polar-EmotiBit Analyzer promises its callers. Each
contract is immutable once merged; a change in module behaviour ships
as a new contract with a new date-suffix filename, and the old
contract stays in place as the historical record.

## Convention

- **Filename**: `<MODULE>_CONTRACT_<YYYY-MM-DD>.md`
- **Body structure** (seven sections, in order):
  1. **Scope** — what this module is for; one paragraph.
  2. **Inputs** — every argument the module accepts, with units and
     schemas. Name the minimum and maximum preconditions.
  3. **Outputs** — every field the module returns, with units and
     schemas. Name the output dataclass / Pydantic model name.
  4. **Success conditions** — declarative list of the testable
     properties the module must satisfy. Name at least one pytest
     test that enforces each.
  5. **Non-promises** — what the module explicitly does not do. This
     section is load-bearing: it protects the module from being
     conscripted into tasks it was not designed for.
  6. **Test coverage** — the pytest tests that demonstrate conformance.
  7. **References** — primary-literature citations for any scientific
     decisions embedded in the contract.

- **Immutability**: once a contract is merged, it is not edited. If
  the module changes, ship a new contract with today's date. The
  previous contract stays as the record of what the module promised
  between its ship-date and the new contract's ship-date.

## Contracts in force

| Contract | Module | Scope |
|----------|--------|-------|
| [`PIPELINE_SCOPE_CONTRACT_2026-04-22.md`](PIPELINE_SCOPE_CONTRACT_2026-04-22.md) | `app/services/processing/pipeline.py::run_analysis` | End-to-end analysis pipeline |
| [`HRV_FEATURE_CONTRACT_2026-04-22.md`](HRV_FEATURE_CONTRACT_2026-04-22.md) | `app/services/processing/features.py` | Time-domain + Poincaré + frequency-domain HRV |
| [`STRESS_COMPOSITE_CONTRACT_2026-04-22.md`](STRESS_COMPOSITE_CONTRACT_2026-04-22.md) | `app/services/processing/stress.py` | v1 and v2 stress composites |
| [`EXPORT_FORMAT_CONTRACT_2026-04-22.md`](EXPORT_FORMAT_CONTRACT_2026-04-22.md) | `app/services/reporting/exporters.py` | CSV / XLSX / MAT / PDF exports |
| [`SYNC_QC_CONTRACT_2026-04-22.md`](SYNC_QC_CONTRACT_2026-04-22.md) | `app/services/processing/sync_qc.py` | Cross-sensor sync quality gate |
| [`NON_DIAGNOSTIC_CONTRACT_2026-04-22.md`](NON_DIAGNOSTIC_CONTRACT_2026-04-22.md) | `app/services/ai/adapters.py::NON_DIAGNOSTIC_NOTICE` | Binding research-use-only disclaimer |

## How to use these contracts

- **Students** writing thesis chapters citing a module should cite the
  matching contract alongside the source-code path and commit hash.
- **AI workers** reviewing proposed changes should read the relevant
  contract first to see what is explicitly out of scope.
- **Reviewers** merging a PR that changes module behaviour should
  require either a matching update to the contract (shipped as a new
  dated file) or a paragraph in the PR description explaining why the
  contract need not change.

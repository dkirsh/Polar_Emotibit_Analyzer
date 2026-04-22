# Export Format Contract

**Module**: `app/services/reporting/exporters.py`
**Endpoint**: `GET /api/v1/sessions/{session_id}/export?format=...`
**Date**: 2026-04-22
**Status**: In force.

## Scope

The export module ships a completed `AnalysisResponse` as one of four
formats matching the Kubios HRV Premium export set: CSV, XLSX, MAT,
and PDF. Each format carries the same underlying feature data in a
layout appropriate to its downstream reader.

## Inputs

A Pydantic `AnalysisResponse` and, for PDF only, an optional
`session_id: str` that is rendered in the PDF header.

## Outputs

Four exporters, each returning `bytes`:

**`export_to_csv(analysis)`** — UTF-8 CSV with header
`group,metric,value,unit` followed by roughly twenty-five rows, one
per metric, grouped in the order Time-Domain HRV / Poincaré /
Frequency-Domain HRV / EDA / Stress / Sync QC / Metadata. A
`# Quality flags` comment block at the bottom lists each quality
flag on its own line.

**`export_to_xlsx(analysis)`** — XLSX workbook with ten sheets:
`Summary`, one sheet per group (`Time-Domain HRV`, `Poincare`,
`Frequency-Domain HRV`, `EDA`, `Stress`, `Sync QC`, `Metadata`),
`Quality flags`, `Non-diagnostic notice`. Header rows styled with a
dark teal fill and bold white text.

**`export_to_mat(analysis)`** — MATLAB `.mat` file with a top-level
struct named `analysis` carrying seven nested sub-structs:
`time_domain`, `poincare`, `frequency_domain`, `eda`, `stress`,
`sync_qc`, `metadata`. `None` values are serialised as NaN.

**`export_to_pdf(analysis, session_id=None)`** — A4 / Letter PDF with
a session-identity header, one table per group, a quality-flags
section, and a dedicated page for the non-diagnostic notice.

HTTP MIME types (from `MIME_TYPES` in the module):

- `csv`  → `text/csv`
- `xlsx` → `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`
- `mat`  → `application/x-matlab-data`
- `pdf`  → `application/pdf`

## Success conditions

1. **CSV parses cleanly.** Header row is `group,metric,value,unit`;
   no unescaped commas in values. Enforced by
   `test_export_csv_is_parseable`.
2. **XLSX opens.** `openpyxl.load_workbook` round-trips the output;
   the three required sheets (`Summary`, `Quality flags`,
   `Non-diagnostic notice`) are present. Enforced by
   `test_export_xlsx_has_expected_sheets`.
3. **MAT is MATLAB-readable.** `scipy.io.loadmat` reads the output
   and exposes the `analysis` struct with its seven nested
   sub-structs. Enforced by `test_export_mat_has_analysis_struct`.
4. **PDF has a valid header.** Output begins with `%PDF-` and is
   larger than 1 000 bytes. Enforced by
   `test_export_pdf_has_pdf_header`.
5. **Endpoint 404 on missing session.** `GET
   /api/v1/sessions/<unknown>/export` returns 404. Enforced by
   `test_export_endpoint_roundtrip_404_on_missing`.
6. **Endpoint 422 on unknown format.** `GET
   /api/v1/sessions/<known>/export?format=exe` returns 422. Enforced
   by `test_export_endpoint_rejects_unknown_format`.

## Non-promises

- The exporters do **not** embed chart images in the PDF. Only tables.
  Chart rendering lives in the frontend; a future enhancement could
  screenshot the rendered charts via a headless-browser step.
- The exporters do **not** include raw timeseries. Only the summary
  feature set.
- The exporters do **not** apply any additional computation. What
  `AnalysisResponse` carries is what the export carries.
- The exporters do **not** sign the output or embed a tamper-evident
  hash. Exported files should be treated as a convenient serialisation
  of the analysis, not as a legal artefact.

## Test coverage

Six tests in `backend/tests/test_real_data_audit.py`, all exercising
the exporters against a real Welltory-derived `AnalysisResponse`. All
passing as of 2026-04-22.

## References

Tarvainen, M. P., Niskanen, J.-P., Lipponen, J. A., Ranta-aho, P. O.,
& Karjalainen, P. A. (2014). Kubios HRV — Heart rate variability
analysis software. *Computer Methods and Programs in Biomedicine*,
113(1), 210–220. https://doi.org/10.1016/j.cmpb.2013.07.024 (cited
as the reference export-format taxonomy; Kubios ships PDF, XLSX,
MAT, CSV.)

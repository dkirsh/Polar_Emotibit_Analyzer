# Non-Diagnostic Contract

**Module**: `app/services/ai/adapters.py::NON_DIAGNOSTIC_NOTICE`
**Date**: 2026-04-22
**Status**: In force. Binding on all outputs of the analyser.

## Scope

The non-diagnostic notice is the binding disclaimer that travels with
every `AnalysisResponse` and every exported report. It declares that
the outputs of this software are for research and engineering-support
use only, not for clinical diagnosis, triage, or treatment decisions.
This contract specifies what the notice must say, where it must
appear, and what claims it implicitly forbids.

## Inputs

None. The notice is a module-level constant string, versioned by the
dated filename of this contract.

## Outputs

Every `AnalysisResponse` carries the notice in its
`non_diagnostic_notice` field. Every exported report (CSV, XLSX, MAT,
PDF) carries the notice in a form appropriate to the format:

- **CSV** — not embedded; CSV is a pipeline-consumption format.
- **XLSX** — dedicated `Non-diagnostic notice` sheet.
- **MAT** — stored at `analysis.metadata.non_diagnostic_notice`.
- **PDF** — dedicated section at the end of the report, on its own
  page.

The frontend renders the notice on `ResultsCoverPage` footer and on
every `AnalyticDetailPage`.

## Success conditions

1. **Notice travels with every response.** Any `AnalysisResponse`
   emitted by the pipeline contains a non-empty
   `non_diagnostic_notice` field. Enforced by schema (Pydantic field
   is required) and by the pipeline's construction of the response.
2. **Notice appears in every exported format.** XLSX workbook
   contains a sheet named `Non-diagnostic notice`; PDF contains a
   section with the same title; MAT contains the notice at
   `analysis.metadata.non_diagnostic_notice`. Enforced by
   `test_export_xlsx_has_expected_sheets` (sheet presence) and by
   inspection of MAT + PDF outputs.
3. **Frontend surfaces the notice.** `ResultsCoverPage` renders a
   `Non-diagnostic notice` block before the analytics cards. Visual
   regression captured in `frontend/src/pages/ResultsCoverPage.tsx`.

## Non-promises — claims this module's output forbids

The non-diagnostic notice is load-bearing precisely because it
forecloses four categories of claim:

- **Clinical diagnosis.** No output of this analyser may be used to
  diagnose, rule out, or triage any medical condition.
- **Treatment decisions.** No output may inform a clinical treatment
  plan or medication adjustment.
- **Regulatory claims.** The software is not registered with any
  medical-device authority (FDA, CE, PMDA, TGA, or equivalent). No
  output may be represented as medical-device output.
- **Absolute between-subject interpretation.** The analyser is
  validated for within-subject relative change; between-subject
  absolute score comparisons are not supported.

Any future module, page, or export must preserve the notice. Removing
or softening the notice requires an explicit new dated contract
documenting the regulatory or editorial decision behind the change.

## Test coverage

The XLSX contract test (`test_export_xlsx_has_expected_sheets`)
asserts the presence of the `Non-diagnostic notice` sheet. The
existing `backend/tests/test_features.py` asserts
`non_diagnostic_notice` is non-empty on any `AnalysisResponse`.

## References

Internal policy document. Aligns with the general conventions for
non-CE-marked consumer physiological sensors in research settings and
with the Polar H10 manufacturer's own disclaimer that the device is
not intended for medical use. No external citation is load-bearing
here — the contract is a product-policy decision, not a scientific
one.

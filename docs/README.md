# docs/ — documentation index

Current reference documents for the Polar-EmotiBit Analyzer.
Module-level contracts and success conditions live under
[`contracts/`](../contracts/); archived working documents from earlier
passes live under `archive/`.

## Audits and fix plans

| File | Purpose |
|------|---------|
| [`RUTHLESS_AUDIT_2026-04-21_CW.md`](RUTHLESS_AUDIT_2026-04-21_CW.md) | Second-pass audit: 18 probes on synthetic data + 6 probes on real Welltory Polar H10 data. Surfaced three P0s (F1, F2/F6, F12); all resolved by 2026-04-22. |
| [`FIX_PLAN_2026-04-21.md`](FIX_PLAN_2026-04-21.md) | Three-phase fix plan for the audit findings. Phase 1 (P0) complete; Phase 2 (P1) complete; Phase 3 (P2) complete. |

## Scientific-methodology records

| File | Purpose |
|------|---------|
| [`STRESS_COMPOSITE_V2_PANEL_JUSTIFICATION_2026-04-21.md`](STRESS_COMPOSITE_V2_PANEL_JUSTIFICATION_2026-04-21.md) | Five-expert panel (Thayer, Shaffer, Tarvainen, Porges, Lakens) consultation on the v2 stress composite's weighting scheme. Cite alongside source code when using the composite in thesis work. |
| [`POLAR_H10_REFERENCE_DATA_AND_PAPER_2026-04-20.md`](POLAR_H10_REFERENCE_DATA_AND_PAPER_2026-04-20.md) | Background on Chung et al. (2026) validation paper and the OSF WYM3S deposit. |

## Architecture and planning

| File | Purpose |
|------|---------|
| [`GUI_SCOPE_FILE_ONLY_2026-04-20.md`](GUI_SCOPE_FILE_ONLY_2026-04-20.md) | GUI scope decision: file-only post-hoc analyser (no live streaming, no recording control). |
| [`THREE_GROUP_RESULTS_ARCHITECTURE_2026-04-20.md`](THREE_GROUP_RESULTS_ARCHITECTURE_2026-04-20.md) | Necessary Science / Diagnostic / Question-Driven three-group information architecture. |
| [`INTEGRATION_PLAN_WITH_SIBLING_REPO_2026-04-20.md`](INTEGRATION_PLAN_WITH_SIBLING_REPO_2026-04-20.md) | Path-A plan for lifting six modules from the sibling `emotibit_polar_data_system` repo. |

## Operational

| File | Purpose |
|------|---------|
| [`GDOCS_SOURCE_MANAGEMENT.md`](GDOCS_SOURCE_MANAGEMENT.md) | Clinical-integrity policy: raw consent forms and source-of-truth data live outside this software stack. |

## Archived working documents

Earlier status notes, Codex prompts, and integration-pass logs from
the 2026-04-20 pass live at [`archive/2026-04-20/`](archive/2026-04-20/).
See that directory's `README.md` for the inventory.

## Convention for adding new documents

- Use a dated filename suffix (`_YYYY-MM-DD`) so the publication date
  is visible without opening the file.
- Put the audience (CW / AG / Codex / Panel / Student) in the filename
  if the document is written for a specific reader.
- Add a row to the table above when the document is current; move
  it to `archive/<date>/` when it is superseded.
- Contract-style specifications (what a module guarantees, what its
  inputs and outputs are, what counts as success) belong in
  [`contracts/`](../contracts/), not here.

# Claude Design / Figma prompt — Analyzer wizard UI (v2)

This supersedes `CLAUDE_DESIGN_PROMPT_wizard.md`. It adds the three screens whose
backends now exist and are tested: **single-subject Inspect**, the **ingestion-
confidence pause**, and a **multi-measure picker + figure gallery**. The backend
is real (`backend/app/services/workflow/`, routes in
`backend/app/api/v1/routes/workflow.py`; contract:
`contracts/WORKFLOW_CONTRACT_2026-06-08.md`). Hand the designer this whole file.

A working React reference implementation already exists at
`frontend/src/workflow/` (WorkflowWizard, InspectView, api). Treat it as the
information architecture to make beautiful — not as the visual target.

---

## PROMPT

Design a calm, rigorous **desktop web app** called **"Polar–EmotiBit Analyzer"**
for psychology/neuroscience researchers (non-developers) who run a physiological-
data analysis pipeline locally. It is a research instrument, not a consumer
product: precise, data-forward, trustworthy, unflashy. Light mode, ~1440 wide.

### Product model
A **guided pipeline with escape hatches.** Six stages run in order —
**1 Connect → 2 Canonicalise → 3 Clean & QC → 4 Define comparison → 5 Analyse →
6 Visualise & Export.** The user presses **Go** and the system runs every stage
automatically, stopping only when a stage genuinely needs a decision. They can
also **Step** one stage at a time, **re-run** any stage, and pin stages to always
pause at. An **Expert mode** collapses the wizard to a dense two-pane screen.

### Global layout
- **Left:** a vertical **stepper** of the six stages, each with a status icon —
  pending (hollow ○), running (spinner), done (green ✓), **needs input (amber
  ●)**, failed (red ✕). A completed stage shows a small "rerun" link. Clicking a
  done stage opens its result; clicking ahead is disabled.
- **Top bar:** app name, the active **run name**, the **dataset folder**, a
  primary **Go / Continue** control, a **Step** button, a **Guided/Expert**
  toggle, and a quiet "resume — last run 3m ago" affordance.
- **Center:** the current stage panel.
- **Right (slim, collapsible): the Run-manifest drawer** — every choice the
  system made automatically, in plain language ("Marker convention for p012 →
  onset/offset", "Kept 2 low-EDA subjects"), each tagged *default* or *user* and
  each with an **override** link. This is the trust surface: *what was assumed.*

### Visual language
- Palette **Charcoal Minimal**: charcoal `#36454F` structure, off-white `#F4F6F1`
  background, near-black text, one **forest-green accent `#2C5F2D`** for primary
  actions and "good/significant", **amber `#C9A227`** for "needs input",
  restrained red for errors. Generous whitespace.
- Type: a serif for headings (Georgia/Cambria feel), a clean sans for body. Tables
  are first-class: thin rules, zebra rows, a charcoal header, **right-aligned
  monospaced numbers**. Never put an accent underline beneath a title.
- One motif: a thin colored left-border on cards to signal stage/status. No
  gradients, no heavy drop-shadows.

### The six stage screens
1. **Connect** — folder picker, then a **detected-files table**: filename ·
   detected type (EmotiBit / Polar / Vernier / Markers / Survey / Roster /
   Unknown) · type-override dropdown · green/amber validity chip. Unknown rows
   amber.
2. **Canonicalise** — progress → **per-session summary table**: subject · group ·
   #EDA · #RR · #resp · #events · timestamp unit · **marker convention**
   (onset-offset / active-until-next / **inline-condition**) · provenance hash ·
   a **confidence chip** (high green / low amber). Emphasise "everything is now
   one canonical store."
3. **Clean & QC** — the **QC review gate**: subjects × EDA coverage, ectopic %,
   corrected-fraction, motion-loss %, **plausibility flag** ("implausible HRV").
   Failing rows amber with Keep / Exclude / Adjust-threshold; thresholds are
   editable chips.
4. **Define comparison** — a **condition editor**: pick two conditions (A/B) from
   detected marker labels, and **check one or more measures from a grouped
   list** with these aggregator groups and members:
   *Electrodermal* → EDA tonic; *Cardiac/HRV* → Heart rate, RMSSD, pNN50;
   *Respiratory* → Respiration rate, **Respiratory stress index (RespInPeace)**.
   Show a one-line natural-language summary of the contrast. (Multi-select is
   real: the results table has one row per chosen measure.)
5. **Analyse** — a **results table** in the house style: one row per measure ×
   (n, Δ A−B, Cohen's dz, paired-t p), significant cells green, with honest
   **"underpowered"** and **"single subject — descriptive only"** labels where
   they apply; a compact **effect-size forest** beside it.
6. **Visualise & Export** — a **figure gallery** of generated charts (paired-slope
   per measure, effect-size forest, per-pattern bars, heatmaps) and a one-click
   **Export** menu (PPTX / PDF / CSV) in this same visual style. This screen
   carries the **visualization-controls panel** described next.

### NEW screen C — **Visualization-controls panel** (on Visualise)
Define controls *what* is shown; this controls *how* it is drawn. Design a slim
controls rail (or a popover per figure) giving the user real control while staying
quiet and rigorous:
- **Chart type (per measure):** segmented control — paired-slope (default for two
  within-subject conditions), grouped bar with 95% CI, box/violin, raincloud, line
  time-series, heatmap (pattern × condition). The default is auto-picked from the
  data shape; the user can override per measure.
- **Scaling:** a **raw ↔ within-subject-normalised** toggle (centred / z / range),
  linear/log y, axis range auto/fixed, and shared-vs-independent y across small
  multiples. The y-axis label must always state raw vs normalised.
- **Grouping & layout:** group/facet by condition, room type, or subject;
  colour-by; sort order (by effect size / value / alphabetical); show/hide
  individual-subject overlays; toggle CI bars and significance annotations; a
  colour-blind-safe palette switch.
- **States to design:** the default auto-picked view; a user-overridden view
  (e.g. raincloud, normalised, faceted by room); the **fallback note** when a
  chart-type × measure combination isn't supported (falls back to default, never
  errors); and missing/invalid values shown as "—", never imputed. Experimental
  measures (Stress V2) keep their flag in every chart type.
- Choices persist per run/measure and are recorded with any export, so a saved
  figure matches what was on screen.

### NEW screen A — Single-subject **Inspect** (first-class)
Reachable from any stage and the natural output of a one-subject run. Purpose:
**catch encoding/cleaning bugs at n = 1 before trusting any aggregate.** Show, for
one chosen subject, three stacked time-series panels — **EDA (µS), beat-intervals
RR (ms), respiration force** — sharing an x-axis in seconds, with the **condition
windows shaded** (green, labelled) across all three. Below: a small table of
**per-window measure values** (EDA tonic, HR, RMSSD, resp rate) per condition,
and the **QC flags** for that subject. A subject-picker row sits above. Design
both the "looks correct" state and a "suspicious" state (e.g., a window that
clearly misaligns the signal) so the view's diagnostic value is visible.

### NEW screen B — **Ingestion-confidence pause**
When Canonicalise cannot derive condition windows with confidence (e.g. an
email-keyed file with no roster, counterbalanced order, typo'd logins), the stage
turns **amber** and the center shows a calm **"Ingestion needs help"** panel: a
plain statement of *which subjects/columns are ambiguous*, and three actions —
**Upload a roster/markers file**, **Map manually** (a small mapping editor:
subject ↔ email ↔ condition columns), and **Ask AI to help map this** (the user
adds a sheet; an AI proposes the mapping; the user sees the proposal and confirms
before anything is written). Make clear that **nothing low-confidence is
committed without confirmation**, and that the resolved mapping is recorded in the
run manifest. Design the request state, the AI-proposed-mapping review state, and
the confirmed state.

### Key states to show
- **Auto-running** (stepper spinner, Go→Continue).
- **Paused needs-input** with the **recommended default preselected** ("Use
  default & continue" vs "Apply choice").
- **A QC-gate stop** (Clean, amber subjects).
- **The ingestion-confidence pause** (screen B) and its AI-assist review.
- **The Inspect view** (screen A), correct and suspicious.
- **The visualization-controls panel** (screen C): default auto-view vs a
  user-overridden view, plus the unsupported-combination fallback note.
- **Done** (all green, export ready) and **Resume after reload**.
- **Expert mode** (one screen: left = canonical-store/QC tables, right =
  condition editor + results + manifest).

### Deliverables
A clickable multi-screen flow for all six stages **plus the Inspect view and the
ingestion-confidence pause**, and the salient states above, light mode, ~1440.
Include the left stepper, top bar, and the run-manifest drawer on at least the
Analyse and Inspect screens. Keep it quiet and rigorous — a tool scientists trust
with their data.

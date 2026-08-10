# Claude Design / Figma prompt — Analyzer wizard UI

Paste the prompt below into Claude Design (Figma Make). It is written to design the
front end for the six-stage workflow whose backend already exists
(`backend/app/services/workflow/`; see `contracts/WORKFLOW_CONTRACT` and
`docs/ANALYZER_WIZARD_ARCHITECTURE`). Hand the designer this whole file.

---

## PROMPT

Design a desktop web app called **"Polar–EmotiBit Analyzer"** for psychology/
neuroscience researchers (non-developers) to run a physiological-data analysis
pipeline. It is a local research tool, not a consumer product: calm, precise,
data-forward, trustworthy. Not flashy.

### Product model
A **guided pipeline with escape hatches.** Six stages run in order:
**1 Connect → 2 Canonicalise → 3 Clean & QC → 4 Define comparison → 5 Analyse →
6 Visualise & Export.** The user presses **Go** and the system runs every stage
automatically, stopping only when a stage genuinely needs a decision. The user
can also **Step** one stage at a time, **re-run** any stage, and pin stages to
always pause at. An **Expert mode** collapses the wizard to a single dense
two-pane screen for power users.

### Global layout
- Left: a **vertical stepper** of the six stages. Each item shows a status icon:
  pending (hollow), running (spinner), done (check), **needs input (amber dot)**,
  failed (red). Clicking a completed stage opens its result; clicking ahead is
  disabled until reached.
- Top bar: app name, the active **dataset/run name**, a primary **Go / Pause**
  control, a **Step** button, a **mode toggle (Guided / Expert)**, and a small
  "resume — last run 3m ago" affordance.
- Center: the **current stage panel**. Right (optional): a slim **Run manifest**
  drawer listing, in plain language, every choice the system made automatically
  ("Marker convention for p012 → onset/offset", "Kept 2 low-EDA subjects"), each
  with an "override" link. This is the trust surface — what was assumed.

### Visual language
- Palette: **Charcoal Minimal** — charcoal `#36454F` as the structural color,
  off-white `#F4F6F1` background, near-black text, a single **forest-green
  accent `#2C5F2D`** for primary actions and "good/significant", amber `#C9A227`
  for "needs input", restrained red for errors. Lots of whitespace.
- Type: a serif for headings (Georgia/Cambria feel), clean sans for body
  (Calibri/Inter feel). Tables are first-class: thin rules, zebra rows, a
  charcoal header row, right-aligned numbers, monospaced figures.
- One motif: a thin colored left-border on cards to signal stage/status. No
  gradients, no drop-shadow-heavy "SaaS" cards. NEVER use an accent line under a
  title.

### The six stage screens
1. **Connect** — a drop-zone / folder picker, then a **detected-files table**:
   filename · detected type (EmotiBit / Polar / Vernier / Markers / Survey /
   Roster / Unknown) · a type override dropdown · a green/amber validity chip.
   "Unknown" rows are amber. Primary action: **Continue**.
2. **Canonicalise** — a progress view that becomes a **per-session summary
   table**: subject · group · #EDA samples · #events · detected timestamp unit
   (ms/ns) · marker convention (onset-offset / active-until-next / inline) ·
   provenance hash. Emphasise that everything is now one canonical store. Any
   ambiguous unit/convention or unmapped subject surfaces as an amber row with a
   chooser.
3. **Clean & QC** — the **QC review gate**. A table of subjects with: EDA
   coverage, beat-interval ectopic %, corrected-fraction, motion-loss %, and a
   **plausibility flag** (e.g. "implausible HRV"). Rows failing a gate are amber
   with a per-row choice: Keep / Exclude / Adjust threshold. Show the thresholds
   as editable chips. This is where the user catches bad data before stats.
4. **Define comparison** — a **condition editor**: pick conditions from the
   detected marker labels, drag each into **Treatment / Control / Comparison**
   roles, choose a **measure** from a grouped dropdown (aggregators: Stress,
   Cardiac/HRV, Electrodermal, Respiratory, Self-report, Attention/SART), and a
   **contrast** (between-condition / restoration = post−pre / within-subject
   normalised). Show a one-line natural-language summary of the chosen contrast.
5. **Analyse** — the **results table** in the house style: measure rows ×
   (Condition A, Condition B, Δ, Cohen's dz, paired-t p, Wilcoxon p, n).
   Significant cells in green; "underpowered" and "multiple-comparison" labels
   shown honestly. A compact effect-size forest plot beside it.
6. **Visualise & Export** — gallery of generated charts (paired-slope, effect
   sizes, per-pattern bars, heatmaps) and a one-click **Export** menu (PPTX / PDF
   / CSV) producing the report in this same visual style.

### Key states to show in the design
- **Auto-running** (stepper spinner on the active stage, Go→Pause).
- **Paused needs-input** (amber stage, a modal/inline panel with the decision,
  its **recommended default preselected**, and the alternatives; "Use default &
  continue" vs "Apply choice").
- **A QC gate stop** (Clean stage with amber subjects).
- **Done** (all checks green, export ready) and **Resume after reload**.
- **Expert mode** (single screen: left = canonical-store/QC tables, right =
  condition editor + results, top = Run-all).

### Deliverables
A clickable multi-screen flow for all six stages plus the three salient states
(auto-running, needs-input pause, done/export), in light mode, desktop width
(~1440). Include the left stepper, top bar, and the run-manifest drawer on at
least the Analyse screen. Keep it quiet and rigorous — this is a tool scientists
trust with their data.

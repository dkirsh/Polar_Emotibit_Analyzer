# Contract — Data cleaning & normalization (current rules + required additions)

This records (A) exactly what the analyzer does today, verified by reading the
code this session, and (B) additions that an expert panel judged it **must**
adopt (see `docs/CLEANING_PANEL_REPORT_2026-06-07.md`). Items in (B) are
requirements, not suggestions; each is marked DONE / PARTIAL / REQUIRED.

## A. What the analyzer does now

### Signal cleaning — `processing/clean.py::clean_signals`
Order is **range → motion → winsorize** (deliberate; winsorizing first would
mask motion spikes — Benedek & Kaernbach, 2010; Greco et al., 2016):
1. **Range filter (physiologically impossible values removed):**
   HR 35–220 bpm; EDA 0–60 µS; respiration 4–50 bpm; RR 300–2000 ms.
2. **Motion filter:** drop samples with accelerometer deviation > **0.3 g**
   above gravitational baseline (Kleckner et al., 2018). Data-dependent: a still
   participant loses ~0%, a moving one may lose 30–50%. Reports
   `movement_artifact_ratio`.
3. **Winsorize:** clip HR and EDA to their [5th, 95th] percentiles, computed on
   the motion-cleaned data.

### HRV / RR artifact handling — `processing/features.py`
- **Lipponen–Tarvainen (2019)** adaptive ectopic-beat detection with
  cubic-spline replacement (length-stable). Ectopic rate computed; a quality
  flag is raised when **> 5%** of beats are flagged.
- **Accelerometer-aware HRV** (`compute_hrv_features_with_accel`) excludes
  motion-contaminated epochs from RR before HRV.
- **Per-band minimum duration** for frequency-domain HRV: VLF ≥ 300 s, LF ≥
  120 s, HF ≥ 60 s; below-threshold bands return `None` (Task Force, 1996).

### Normalization — `processing/normalization.py`
- **Within-subject, baseline-relative** only: HR Δ and % change; EDA tonic Δ;
  EDA phasic Δ; ln(RMSSD) Δ — all relative to a baseline window defined by
  `baseline_onset` / `baseline_offset` markers. Raw values are preserved
  alongside.

### Provenance & honesty
`rr_source` + confidence tiers; sync-QC go/conditional/no-go gate; experimental
indices flagged; metrics below earned thresholds return `None`.

## B. Required additions (panel-endorsed)

1. **Within-subject mean-centring normalization — DONE (this change).**
   The analyzer previously normalized only to a *baseline window*. For cohort
   comparison and for the user's stated method (difference from each subject's
   own mean), `normalization.py` now also provides whole-session within-subject
   centring (and optional SD-standardization). Rationale: between-subject EDA/HRV
   level differences are large; within-subject referencing is the field norm
   (Laborde et al., 2017; SPR EDA committee / Boucsein et al., 2012).

2. **Cap the artifact-corrected fraction — REQUIRED.**
   Frequency-domain HRV (esp. HF) becomes unreliable once a large fraction of
   beats are interpolated; ~25% corrected is a common ceiling (Peters et al.,
   2008). The analyzer flags >5% ectopic but does not yet **invalidate** a
   metric when correction exceeds the ceiling. Requirement: return `None`
   (not a number) for HF-band metrics when corrected fraction > 25%, with a flag.

3. **Model-based EDA decomposition — REQUIRED (currently PARTIAL).**
   Phasic activity is approximated by winsorize + a phasic index. The field
   standard is continuous decomposition (Benedek & Kaernbach, 2010) or cvxEDA
   (Greco et al., 2016), separating tonic SCL from phasic SCR drivers.
   Requirement: offer a model-based phasic/tonic decomposition; keep the simple
   index as a labelled fallback.

4. **Surface, don't just auto-correct — REQUIRED.**
   Laborde et al. (2017) caution against relying solely on automatic artifact
   correction. Requirement: expose per-subject ectopic %, corrected-fraction,
   and motion-loss % in the cohort table so a human can screen them (the
   "impossibly high HRV" failure is exactly an unscreened-correction artifact).

5. **Report respiration beside HF-HRV — REQUIRED.**
   HF power is respiration-driven; HF is interpretable as vagal tone only when
   respiration is observed (Laborde et al., 2017). Requirement: when belt
   respiration exists, surface mean respiratory rate next to HF in the same view.

6. **Parsimonious HRV index set — RECOMMENDED.**
   Many HRV indices are redundant; a data-driven core (RMSSD, SDNN, SD1/SD2,
   HF/lnHF, plus a nonlinear index) avoids multiple-comparison inflation
   (Pham et al., 2025).

## References
Benedek, M., & Kaernbach, C. (2010). *J. Neurosci. Methods, 190*(1), 80–91.
Greco, A., et al. (2016). cvxEDA. *IEEE TBME, 63*(4), 797–804.
Kleckner, I. R., et al. (2018). *IEEE TBME, 65*(7), 1460–1467.
Laborde, S., Mosley, E., & Thayer, J. F. (2017). *Front. Psychol., 8*, 213.
Lipponen, J. A., & Tarvainen, M. P. (2019). *J. Med. Eng. Technol., 43*(3), 173–181.
Peters, C. H. L., et al. (2008). *Proc. IEEE EMBS*, 2669–2672.
Pham, T., et al. (2025). *Psychophysiology, 62*(10).
Quigley, K. S., et al. (2024). *Psychophysiology, 61*(9), e14604.
Society for Psychophysiological Research Ad Hoc Committee on Electrodermal
Measures (Boucsein, W., et al.). (2012). *Psychophysiology, 49*(8), 1017–1034.
Task Force of the ESC/NASPE. (1996). *Circulation, 93*(5), 1043–1065.

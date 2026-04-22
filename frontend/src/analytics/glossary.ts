// Dashboard glossary — plain-language definitions for every jargon term
// that appears on the Polar-EmotiBit Analyzer's user-facing views.
//
// Written against Article_Eater's SCIENCE_COMMUNICATION_NORMS.md:
//   Norm 1 (Pinker classic style): writer-as-guide, not writer-as-oracle.
//   Norm 2 (Williams Given-New): entries open with a term the reader
//     already recognises from the UI; then give the new content.
//   Norm 4 (Lanham/Sword): no zombie nouns; no "is" as placeholder verb.
//   Norm 9 (Carson/Sagan): honest uncertainty — every term that carries
//     interpretive risk names the risk.
//
// Every entry has:
//   term          the label as it appears on-screen
//   oneLiner      a single-sentence gloss for a tooltip
//   longer        a 2–3 sentence expansion for a side-panel reveal
//   unit          the unit or "(unitless)" so the reader can rely on it
//   seeAlso       sibling terms to check next
//
// Target audience: a researcher, 160 student, or practitioner who has
// not seen HRV/EDA terminology before and is reading the dashboard
// for the first time. Definitions assume nothing beyond high-school
// biology plus an understanding of what "autonomic nervous system" is.

export type GlossaryEntry = {
  term: string;
  oneLiner: string;
  longer: string;
  unit: string;
  seeAlso?: string[];
};

export const GLOSSARY: Record<string, GlossaryEntry> = {

  // ── Heart-rate-variability terms ─────────────────────────────────

  RMSSD: {
    term: "RMSSD",
    oneLiner:
      "Root-mean-square of successive RR-interval differences — the fastest index of parasympathetic (vagal) tone.",
    longer:
      "RMSSD measures how much each heartbeat differs from the one before it. Higher RMSSD means the vagus nerve is actively varying heart rate from beat to beat — a healthy sign of autonomic flexibility. It drops under acute stress and rebounds during recovery. In architecture-cognition studies it is usually the first HRV index to move when an environmental manipulation engages the sympathetic nervous system.",
    unit: "ms",
    seeAlso: ["SDNN", "HF", "vagal tone", "parasympathetic"],
  },
  SDNN: {
    term: "SDNN",
    oneLiner:
      "Standard deviation of all normal RR intervals — the total-variability index across time scales.",
    longer:
      "SDNN captures the full spread of heartbeat intervals during the recording. It includes both the fast (vagal) variability RMSSD measures and the slower (sympathetic + baroreflex) variability. Below 50 ms over a five-minute resting recording suggests restricted autonomic range.",
    unit: "ms",
    seeAlso: ["RMSSD", "LF", "HF"],
  },
  "mean HR": {
    term: "Mean HR",
    oneLiner:
      "Simple arithmetic mean of heart rate across the session, in beats per minute.",
    longer:
      "The plainest summary of cardiac state. At rest, above ≈ 90 bpm in a non-exercising adult suggests sympathetic dominance; below ≈ 50 bpm suggests either athletic resting state or a bradyarrhythmia (for which medical context matters). Mean HR alone is a blunt instrument — pair it with RMSSD before drawing autonomic conclusions.",
    unit: "bpm",
    seeAlso: ["RMSSD", "SDNN", "tonic SCL"],
  },
  "RR interval": {
    term: "RR interval",
    oneLiner:
      "Time between two successive R-wave peaks on the ECG — the raw currency of HRV analysis.",
    longer:
      "Each RR interval is the gap between one heartbeat and the next, in milliseconds. A resting adult RR series sits between 600 ms (100 bpm) and 1200 ms (50 bpm). All HRV indices — RMSSD, SDNN, frequency-domain bands — are derived from the RR series, so it must be clean of ectopic beats and detection failures before any downstream number is trustworthy.",
    unit: "ms",
    seeAlso: ["tachogram", "ectopic beat", "RMSSD"],
  },
  VLF: {
    term: "VLF (very-low-frequency) band",
    oneLiner:
      "Spectral power of HRV between 0.003 and 0.04 Hz — reliably estimated only for recordings ≥ 300 seconds.",
    longer:
      "The slowest HRV oscillation the standard spectrum reports. Physiologically it reflects thermoregulatory, humoral, and renin-angiotensin rhythms rather than autonomic reactivity. For recordings shorter than five minutes this band returns an em-dash, not a number — the signal has not had enough cycles to estimate cleanly (Task Force, 1996).",
    unit: "ms²",
    seeAlso: ["LF", "HF", "PSD"],
  },
  LF: {
    term: "LF (low-frequency) band",
    oneLiner:
      "Spectral power between 0.04 and 0.15 Hz — a mix of sympathetic and parasympathetic drive plus baroreflex oscillation.",
    longer:
      "Dominated by the Mayer wave at ≈ 0.1 Hz, the LF band is sometimes read as a sympathetic index but is more honestly a joint index of sympathetic drive, parasympathetic drive, and the baroreflex. Needs ≥ 120 s of recording for a stable estimate.",
    unit: "ms²",
    seeAlso: ["HF", "LF/HF ratio", "Mayer wave", "baroreflex"],
  },
  HF: {
    term: "HF (high-frequency) band",
    oneLiner:
      "Spectral power between 0.15 and 0.40 Hz — primarily parasympathetic, driven by respiratory sinus arrhythmia.",
    longer:
      "The HF band sits in the breathing-rate band (≈ 12–24 breaths/min) and reflects respiratory sinus arrhythmia — the vagal modulation of HR that tracks the breath. HF drops under cognitive load and attention demand and rebounds quickly on removal. Needs ≥ 60 s of recording for a stable estimate.",
    unit: "ms²",
    seeAlso: ["LF", "RMSSD", "respiratory sinus arrhythmia", "vagal tone"],
  },
  "LF/HF ratio": {
    term: "LF/HF ratio",
    oneLiner:
      "The ratio of LF to HF spectral power — an ambiguous sympathovagal-balance marker; read direction, not magnitude.",
    longer:
      "Historically interpreted as a sympathetic-to-parasympathetic balance index, the LF/HF ratio has been challenged on physiological grounds (Billman, 2013) because both bands carry mixed autonomic contributions. A rising ratio means something is changing; whether that change is a sympathetic lift, a parasympathetic drop, or both can only be read by looking at the LF and HF trajectories separately.",
    unit: "(dimensionless)",
    seeAlso: ["LF", "HF", "sympathovagal balance"],
  },
  PSD: {
    term: "Power spectral density (PSD)",
    oneLiner:
      "How HRV's variance is distributed across frequency — computed here by Welch's method, not a raw periodogram.",
    longer:
      "The PSD shows which rhythmic components dominate the RR series. Two peaks are diagnostic: ≈ 0.1 Hz (Mayer wave, LF) and ≈ 0.25 Hz (respiratory sinus arrhythmia, HF). Welch's method segments, windows, and averages — producing a lower-variance estimate than the simple periodogram, which is what every serious HRV tool uses (Welch, 1967; Task Force, 1996).",
    unit: "ms²/Hz",
    seeAlso: ["VLF", "LF", "HF", "Welch's method"],
  },

  // ── Electrodermal terms ──────────────────────────────────────────

  "tonic SCL": {
    term: "Tonic SCL",
    oneLiner:
      "Tonic skin-conductance level — the slow baseline of electrodermal activity, an arousal-state index.",
    longer:
      "Tonic SCL is the slowly-drifting baseline of the electrodermal trace, reflecting sustained sympathetic activation. Healthy adult values sit in 2–20 µS depending on sensor site and electrode preparation; values below ≈ 1 µS or above ≈ 30 µS usually indicate electrode-placement artifact. Tonic SCL rises and falls over tens of seconds and is the EDA axis most responsive to sustained environmental stressors — noise load, thermal discomfort, crowding.",
    unit: "µS",
    seeAlso: ["phasic EDA", "EDA", "SCL"],
  },
  "phasic EDA": {
    term: "Phasic EDA",
    oneLiner:
      "Fast electrodermal bursts — the orienting-response axis, triggered by discrete environmental events.",
    longer:
      "Phasic bursts are the fast, event-locked spikes superimposed on the tonic baseline. They index the orienting response to discrete stimuli — a door closing, a face in the periphery, a sudden pitch change. Reported here as the mean of the EDA trace's absolute first difference (a simple intensity proxy) plus peak count and burst density per minute (Benedek & Kaernbach, 2010).",
    unit: "µS/s (proxy)",
    seeAlso: ["tonic SCL", "EDA", "orienting response"],
  },
  EDA: {
    term: "EDA (electrodermal activity)",
    oneLiner:
      "Skin conductance, measured in microsiemens — the sympathetic-only autonomic axis.",
    longer:
      "EDA is the conductance of the skin, modulated by sweat-gland activity under sympathetic-nervous-system control. Because the skin-sweat pathway is sympathetic-only (no parasympathetic contribution), EDA is the cleanest single window onto sympathetic arousal. Split into tonic (slow baseline) and phasic (fast bursts) components, which tell different stories about the same participant.",
    unit: "µS",
    seeAlso: ["tonic SCL", "phasic EDA", "sympathetic"],
  },

  // ── Stress composite ─────────────────────────────────────────────

  "stress composite": {
    term: "Stress composite",
    oneLiner:
      "An experimental 0–1 index combining HR, EDA-tonic, EDA-phasic, and HRV-deficit — use for within-session comparison only.",
    longer:
      "A weighted composite with channel weights 0.35 / 0.35 / 0.20 / 0.10. Not psychometrically validated against standard stress instruments (PSS, DASS-21) or cortisol. Interpret *direction* and *relative magnitude* across phases of the same session, not absolute stress. The companion decomposition chart names which channel dominates, which is a more defensible finding than the scalar itself.",
    unit: "(0–1)",
    seeAlso: ["RMSSD", "tonic SCL", "phasic EDA"],
  },

  // ── Synchronisation terms ────────────────────────────────────────

  "sync-QC score": {
    term: "Sync-QC score",
    oneLiner:
      "A 0–100 composite gauging the cleanliness of the Polar↔EmotiBit clock alignment; gates whether other numbers are interpretable.",
    longer:
      "A weighted blend of five sub-components: temporal overlap (30 %), drift deviation from unity (25 %), sync ratio (20 %), residual lag (15 %), and timestamp jitter (10 %). A recording that produces a low sync-QC score can still return numeric RMSSD and SCL values that look plausible, but those values may be about clock drift rather than about the participant — which is why the gate exists.",
    unit: "/ 100",
    seeAlso: ["sync-QC band", "sync-QC gate", "drift slope"],
  },
  "sync-QC band": {
    term: "Sync-QC band",
    oneLiner:
      "Green / yellow / red classification of the sync-QC score.",
    longer:
      "Green (≥ 80) means all features are interpretable. Yellow (50–79) means time-domain features (RMSSD, mean HR, tonic SCL) are usable but frequency-domain features (LF, HF, LF/HF) are questionable. Red (< 50) means features are unreliable; re-collect with NTP-synchronised devices before publishing.",
    unit: "(category)",
    seeAlso: ["sync-QC score", "sync-QC gate"],
  },
  "sync-QC gate": {
    term: "Sync-QC gate",
    oneLiner:
      "Go / conditional-go / no-go verdict derived from the sync-QC score.",
    longer:
      "The gate is the single word the dashboard uses to tell a researcher whether the session is usable. 'Go' means everything checks out; 'conditional go' means the session is usable with noted limitations; 'no-go' means the downstream numbers are not interpretable and the data should be re-collected. This is a more committal statement than the raw score.",
    unit: "(verdict)",
    seeAlso: ["sync-QC score", "sync-QC band"],
  },
  "drift slope": {
    term: "Drift slope",
    oneLiner:
      "The slope of the piecewise linear map from Polar clock to EmotiBit clock; 1.000 means perfect clock sync.",
    longer:
      "A drift slope of 1.0006 means the Polar clock is advancing 0.06 % faster than the EmotiBit's — small, correctable. A slope of 1.02 means 2 % drift — large, indicating the clocks were materially diverging, and the drift-diagnostic chart should be checked for non-linearity. Temperature-dependent crystal drift is the most common cause of large slopes in walking protocols.",
    unit: "(dimensionless)",
    seeAlso: ["sync-QC score", "drift intercept"],
  },
  "movement-artifact ratio": {
    term: "Movement-artifact ratio",
    oneLiner:
      "Fraction of samples dropped by the 0.3 g accelerometer-based motion gate.",
    longer:
      "Below 5 % is consistent with a seated participant; above 20 % means the participant was moving (exercise, walking) or the wrist sensor was poorly adhered. In the first case the HRV/EDA numbers should not be interpreted as rest-state indices. In the second case the numbers are partly noise. The threshold of 0.3 g above gravitational baseline comes from Kleckner et al. (2018).",
    unit: "(0–1 fraction)",
    seeAlso: ["ectopic beat", "RR interval"],
  },

  // ── Diagnostics ──────────────────────────────────────────────────

  "ectopic beat": {
    term: "Ectopic beat",
    oneLiner:
      "A heartbeat whose timing deviates sharply from its neighbours — either a real arrhythmia or a detection failure.",
    longer:
      "Ectopic beats appear as sharp single-beat excursions on the tachogram (e.g., a 400 ms beat sandwiched between two 1000 ms beats). They can be genuine atrial or ventricular premature contractions (clinically meaningful) or artifacts of the Polar's R-wave detector struggling with a sweaty or loose chest strap. Either way they must be filtered before HRV indices are computed — otherwise RMSSD is inflated by the artifact rather than reflecting true variability.",
    unit: "(count)",
    seeAlso: ["tachogram", "RR interval", "Lipponen filter"],
  },
  tachogram: {
    term: "Tachogram",
    oneLiner:
      "A line plot of RR interval against beat index — the first chart every HRV analyst looks at.",
    longer:
      "The tachogram is the raw RR series plotted beat-by-beat. Sharp single-beat excursions mark ectopics; clustered excursions mark detection-failure bursts; smooth slow modulation is healthy autonomic flexibility. Because every downstream HRV number is derived from this series, a bad-looking tachogram invalidates the statistics.",
    unit: "RR in ms, beat index on x-axis",
    seeAlso: ["RR interval", "ectopic beat", "Poincaré plot"],
  },
  "Bland-Altman": {
    term: "Bland-Altman agreement",
    oneLiner:
      "Scatter plot of mean-of-two vs difference-of-two — the standard way to compare two measurement systems.",
    longer:
      "Bland & Altman (1986) introduced this plot as the canonical agreement test between two measurement methods. Bias (mean difference) appears as a horizontal line; limits of agreement (±1.96 × SD of differences) appear as two more horizontal lines. A narrow band means the two systems are interchangeable. Here used to compare this pipeline's HRV against Kubios HRV Premium on the same data.",
    unit: "(depends on metric)",
    seeAlso: ["Kubios", "RMSSD", "SDNN"],
  },

  // ── Non-obvious terms on the dashboard ──────────────────────────

  "non-diagnostic notice": {
    term: "Non-diagnostic notice",
    oneLiner:
      "Binding disclaimer: these outputs are for research and engineering support, not medical diagnosis.",
    longer:
      "Appears on every analysis download and on view 2's footer. States that the composite scores, HRV indices, and quality flags are intended for research-grade within-session comparison — not for clinical decision-making. Required on any HRV-derived output that a non-clinician might otherwise over-interpret.",
    unit: "(notice text)",
  },
  // 2026-04-21 Kubios-parity additions ----------------------------------
  "nn50": {
    term: "NN50",
    oneLiner: "Count of successive RR-interval differences larger than 50 milliseconds.",
    longer: "NN50 counts the beats whose preceding interval differed from the next interval by more than 50 ms. Parasympathetic (vagal) activation produces fast, large beat-to-beat changes, so NN50 rises when the body is at rest and falls under sympathetic dominance.",
    unit: "beats",
    seeAlso: ["pNN50", "RMSSD"],
  },
  "pnn50": {
    term: "pNN50",
    oneLiner: "NN50 expressed as a percentage of the total successive-difference count.",
    longer: "pNN50 normalises NN50 by the number of RR intervals, so sessions of different length can be compared. Healthy resting adults typically sit between 10 % and 40 %; the number falls to near zero under strong sympathetic activation or in older participants whose autonomic flexibility has declined.",
    unit: "%",
    seeAlso: ["NN50", "RMSSD"],
  },
  "sd1": {
    term: "SD1",
    oneLiner: "Short-term variability axis of the Poincaré plot; equals RMSSD divided by √2.",
    longer: "SD1 measures how far points in the Poincaré plot spread perpendicular to the line of identity. It is mathematically equivalent to RMSSD scaled by 1/√2, so it carries the same parasympathetic-tone information; the Poincaré geometry makes the index visually interpretable rather than abstract.",
    unit: "ms",
    seeAlso: ["SD2", "SD1/SD2 ratio", "RMSSD"],
  },
  "sd2": {
    term: "SD2",
    oneLiner: "Long-term variability axis of the Poincaré plot.",
    longer: "SD2 measures spread along the line of identity — variability across longer timescales that folds slow changes into the same geometric picture. Large SD2 relative to SD1 indicates long-wave HRV (slow baseline shifts) dominating over beat-to-beat variability.",
    unit: "ms",
    seeAlso: ["SD1", "SD1/SD2 ratio"],
  },
  "sd1-sd2-ratio": {
    term: "SD1/SD2 ratio",
    oneLiner: "Balance of short-term to long-term HRV on the Poincaré plot.",
    longer: "The ratio summarises the shape of the Poincaré ellipse: near 0.5 in healthy resting adults, shrinking under stress as the short-term axis collapses relative to the long-term one. A collapsed ratio therefore flags autonomic rigidity even when individual SD1 or SD2 values look normal.",
    unit: "ratio",
    seeAlso: ["SD1", "SD2"],
  },
  "ellipse-area": {
    term: "Poincaré ellipse area",
    oneLiner: "π × SD1 × SD2 — the classical geometric size of the Poincaré cloud.",
    longer: "The ellipse area expresses total HRV magnitude as a single number derived from both Poincaré axes. Larger area means more variability overall; it drops when either short-term (SD1) or long-term (SD2) variability collapses.",
    unit: "ms²",
    seeAlso: ["SD1", "SD2"],
  },
  "total-power": {
    term: "Total power",
    oneLiner: "Sum of VLF, LF, and HF band powers in the HRV frequency spectrum.",
    longer: "Total power is the integral of power spectral density across all three HRV bands, a scalar that captures the overall autonomic activity of the heart. Use it alongside the percent-of-total and normalised-unit fields for a complete spectral picture.",
    unit: "ms²",
    seeAlso: ["VLF (very-low-frequency) band", "LF (low-frequency) band", "HF (high-frequency) band"],
  },
  "lf-nu": {
    term: "LF_nu (LF normalised units)",
    oneLiner: "LF power as a percentage of (LF + HF) — the canonical sympathovagal balance marker.",
    longer: "Normalised units divide each band by the sum of LF and HF (not by total power), so they are unaffected by the heart-rate-dependent absolute-power differences that plague cross-subject comparisons. Task Force (1996) recommends LF_nu and HF_nu as the primary between-subject fields.",
    unit: "n.u. (0–100)",
    seeAlso: ["HF_nu (HF normalised units)", "LF/HF ratio"],
  },
  "hf-nu": {
    term: "HF_nu (HF normalised units)",
    oneLiner: "HF power as a percentage of (LF + HF); the parasympathetic-dominant complement of LF_nu.",
    longer: "HF_nu equals 100 − LF_nu by construction. It rises with vagal tone (respiratory-sinus-arrhythmia dominance) and falls with sympathetic drive. Together with LF_nu it gives the normalised sympathovagal-balance picture.",
    unit: "n.u. (0–100)",
    seeAlso: ["LF_nu (LF normalised units)", "LF/HF ratio"],
  },
  "lipponen-tarvainen": {
    term: "Lipponen-Tarvainen correction",
    oneLiner: "Adaptive-threshold ectopic-beat detector plus cubic-spline interpolation.",
    longer: "Published in 2019, the algorithm computes thresholds from the spread of successive RR differences and of median-detrended RR, classifies each beat as normal or ectopic, and replaces flagged beats with cubic-spline interpolation. This is the algorithm Kubios HRV Premium uses by default; applying it is the difference between research-grade and exploratory HRV output.",
    unit: "(method)",
    seeAlso: ["Ectopic beat", "Kubios HRV Premium"],
  },
  "cubic-spline": {
    term: "Cubic-spline interpolation",
    oneLiner: "A smooth curve through known data points used to estimate missing values.",
    longer: "For HRV, cubic-spline interpolation replaces ectopic-beat RR values with a smooth estimate fitted from the surviving normal beats. Unlike linear interpolation it preserves first-derivative continuity, which matters because RMSSD and other beat-to-beat metrics are themselves functions of first differences.",
    unit: "(method)",
    seeAlso: ["Lipponen-Tarvainen correction", "Ectopic beat"],
  },
  "quartile-deviation": {
    term: "Quartile deviation",
    oneLiner: "Half the interquartile range — a robust measure of spread.",
    longer: "QD equals (Q3 − Q1) / 2. It resists outliers the way the standard deviation does not, which is why the Lipponen-Tarvainen corrector uses it to set adaptive thresholds for ectopic detection.",
    unit: "(same as the quantity)",
    seeAlso: ["Lipponen-Tarvainen correction"],
  },
  Kubios: {
    term: "Kubios HRV Premium",
    oneLiner:
      "The commercial reference tool the HRV literature pools around; this pipeline benchmarks against it.",
    longer:
      "Kubios HRV Premium (Tarvainen et al., 2014) is the de facto reference tool for HRV computation in research. Most HRV methods sections cite Kubios values. A pipeline claiming 'Kubios parity' should produce HRV indices within narrow limits of agreement against Kubios on the same data — the Bland-Altman chart on this dashboard is what answers that claim.",
    unit: "(tool name)",
    seeAlso: ["Bland-Altman", "RMSSD", "SDNN"],
  },
};

/** Look up a glossary entry by term (case-insensitive). */
export function lookupGlossary(term: string): GlossaryEntry | undefined {
  const k = term.trim().toLowerCase();
  for (const [key, entry] of Object.entries(GLOSSARY)) {
    if (key.toLowerCase() === k) return entry;
    if (entry.term.toLowerCase() === k) return entry;
  }
  return undefined;
}

/** Return all glossary terms, sorted. */
export function allGlossaryTerms(): string[] {
  return Object.keys(GLOSSARY).sort((a, b) => a.localeCompare(b));
}

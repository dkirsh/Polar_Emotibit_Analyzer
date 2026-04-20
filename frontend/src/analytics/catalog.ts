// Analytics catalog for the Polar-EmotiBit Analyzer results pages.
//
// Every analytic is an entry in this file. Each entry carries the
// writer-voice title, caption, and interpretation paragraph plus the
// metadata the renderer needs to assemble its chart. The catalog is the
// single source of truth for the three groups — Necessary Science,
// Diagnostic, and Question-Driven — and drives the cover page, the
// group pages, the detail pages, and the prev/next chaining.
//
// Interpretations are written for a cognitive-neuroscience-for-
// architecture audience: they relate each measure to the dependent
// variables the field tracks (stress, attention, arousal, recovery)
// and to the built-environment manipulations that perturb them.

export type AnalyticGroup = "necessary" | "diagnostic" | "question";
export type QuestionCategory = "science" | "diagnostics";

export type ChartKind =
  | "timeseries_overlay"
  | "summary_table"
  | "stacked_bar"
  | "spectrum"
  | "line"
  | "scatter"
  | "histogram"
  | "phase_comparison"
  | "forest"
  | "bland_altman"
  | "radar"
  | "strip"
  | "tachogram"
  | "poincare"
  | "gauge";

export type AnalyticEntry = {
  id: string;
  group: AnalyticGroup;
  question?: string;          // for question-driven items
  category?: QuestionCategory; // science | diagnostics, within question-driven
  order: number;              // ordering within its group for prev/next chaining
  title: string;              // the chart title (graphic header)
  caption: string;            // one sentence beneath the title
  chartKind: ChartKind;
  dataPaths: string[];        // which fields of extended[] this chart reads
  minimumPreconditions?: string[]; // human-readable blockers if data missing
  whatItShows: string;        // plain-language description of the chart
  howToRead: string;          // how to interpret the visual encoding
  architecturalMeaning: string; // what it means for cog-neuro-of-architecture
  caveats?: string;           // common misinterpretations to avoid
  references?: Array<{ apa: string; doi?: string }>;
};

// -- Necessary Science analytics --------------------------------------

const NECESSARY: AnalyticEntry[] = [
  {
    id: "ns-01-hr-eda-timeseries",
    group: "necessary",
    order: 1,
    title: "Heart rate and electrodermal activity across the session",
    caption:
      "The two primary physiological channels, overlaid on a shared time axis, " +
      "with the sync-QC-validated synchronized sample set.",
    chartKind: "timeseries_overlay",
    dataPaths: ["extended.cleaned_timeseries"],
    whatItShows:
      "The top panel plots heart rate in beats per minute over the full recorded session. " +
      "The bottom panel plots tonic electrodermal level in microsiemens on the same time axis. " +
      "When event markers are present, translucent vertical bands separate baseline, task, and recovery phases so that onset-related excursions are visible without the analyst doing alignment math in their head.",
    howToRead:
      "Look first for sustained step-changes in the HR trace at phase boundaries: a ten-to-twenty-beat-per-minute elevation during a stressor is the classic cardiovascular response pattern. In the EDA trace, look for a slow baseline drift — the tonic component, reflecting arousal level — together with faster upward deflections that mark phasic orienting responses to specific events.",
    architecturalMeaning:
      "In the cognitive-neuroscience-of-architecture frame, this chart is the single richest window onto how a participant responded to the environmental manipulation. Heart rate indexes the fast cardiac response to perceived demand (Berntson et al., 1997); electrodermal activity indexes the slower, sympathetic-only arousal response that architectural variables like acoustic load, spatial compression, and visual complexity are known to modulate (Boucsein, 2012). When the two channels rise and fall together you are seeing integrated sympathetic activation; when they dissociate you may be seeing a motor or orienting response without a sustained arousal state, or conversely a slowly accumulating stress load without an overt cardiac reaction.",
    caveats:
      "Motion artifacts in the EDA trace look like phasic bursts. Cross-check against the motion-artifact timeline diagnostic before concluding that a late-session rise in tonic SCL is a real arousal signal.",
    references: [
      { apa: "Berntson, G. G., et al. (1997). Heart rate variability: Origins, methods, and interpretive caveats. Psychophysiology, 34, 623–648.", doi: "10.1111/j.1469-8986.1997.tb02140.x" },
      { apa: "Boucsein, W. (2012). Electrodermal Activity (2nd ed.). Springer.", },
    ],
  },
  {
    id: "ns-02-hrv-time-domain",
    group: "necessary",
    order: 2,
    title: "Time-domain heart-rate variability",
    caption:
      "RMSSD, SDNN, and mean HR with their population-norm reference ranges and the session's bootstrapped confidence intervals.",
    chartKind: "summary_table",
    dataPaths: ["feature_summary", "extended.descriptive_stats"],
    whatItShows:
      "Three scalar HRV indices summarised with their sample mean, sample standard deviation, and a 95 percent confidence interval computed using the t-distribution rather than z = 1.96. Each row also carries a reference-range annotation based on Shaffer and Ginsberg (2017). RMSSD reflects the rapid, vagally-mediated, beat-to-beat variability that drops during sympathetic activation; SDNN captures the total variance of successive RR intervals across time scales; mean HR is the simple average.",
    howToRead:
      "RMSSD below roughly 25 ms in an adult at rest is low-normal and indicates reduced parasympathetic tone; values in the 40 to 80 ms range are typical for healthy adults at rest (Shaffer and Ginsberg, 2017). SDNN below 50 ms over a five-minute recording is consistent with restricted autonomic range. Mean HR above approximately 90 bpm at rest in a non-exercising participant suggests sympathetic dominance.",
    architecturalMeaning:
      "RMSSD is the single most responsive HRV index to environmental stressors and the one most used in the architecture-cognition literature (Ulrich et al., 1991; Ottaviani et al., 2016). A depressed RMSSD during the task phase relative to baseline is evidence that the environmental manipulation engaged the sympathetic nervous system; a stable RMSSD across phases is evidence that whatever-else happened, the participant did not perceive an autonomic stressor. SDNN and mean HR are complementary but coarser indices; in a short five-minute session RMSSD usually moves first and most reliably.",
    references: [
      { apa: "Shaffer, F., & Ginsberg, J. P. (2017). An overview of heart rate variability metrics and norms. Frontiers in Public Health, 5, 258.", doi: "10.3389/fpubh.2017.00258" },
      { apa: "Task Force ESC/NASPE (1996). Heart rate variability: Standards of measurement. Circulation, 93, 1043–1065." },
    ],
  },
  {
    id: "ns-03-psd-frequency-domain",
    group: "necessary",
    order: 3,
    title: "Heart-rate variability power spectrum",
    caption:
      "The Welch power spectral density of the RR series with VLF, LF, and HF bands annotated and each band's integrated power reported as a shaded region.",
    chartKind: "spectrum",
    dataPaths: ["extended.psd", "feature_summary"],
    whatItShows:
      "A log-log plot of spectral power density against frequency from 0 to 0.4 Hz, computed by Welch's method rather than the raw periodogram so that variance is properly controlled. The three physiologically-named bands are rendered as colored vertical strips: VLF from 0.003 to 0.04 Hz, LF from 0.04 to 0.15 Hz, HF from 0.15 to 0.40 Hz. The integrated power in each band is reported numerically alongside the plot. Bands whose recording duration is below the Task Force (1996) minimum are rendered with a striped pattern and the numeric value is replaced with an em dash.",
    howToRead:
      "Two visible peaks are diagnostic: one near 0.1 Hz (the Mayer wave, in the LF band) and one in the breathing-rate band near 0.20 to 0.30 Hz (respiratory sinus arrhythmia, in the HF band). Their relative heights set the LF/HF ratio. A flat spectrum is a sign of either reduced autonomic variability or a too-short recording.",
    architecturalMeaning:
      "The LF band carries a mix of sympathetic and parasympathetic drive plus baroreflex oscillation; the HF band is parasympathetic and largely respiration-driven (Berntson et al., 1997). In architectural contexts the HF band is what drops when a participant is asked to hold attention on a demanding visual or auditory task, and it rebounds rapidly on removal of the demand. The spectrum is the chart that distinguishes a participant who shifted vagally from one whose sympathetic axis actually rose, which the LF/HF scalar alone cannot.",
    caveats:
      "The LF/HF ratio has been critiqued as not a clean index of sympathovagal balance (Billman, 2013); interpret it as one marker of autonomic state rather than a decisive measure.",
    references: [
      { apa: "Welch, P. D. (1967). IEEE Trans. Audio Electroacoustics, 15, 70–73.", doi: "10.1109/TAU.1967.1161901" },
      { apa: "Billman, G. E. (2013). The LF/HF ratio does not accurately measure cardiac sympatho-vagal balance. Frontiers in Physiology, 4, 26.", doi: "10.3389/fphys.2013.00026" },
    ],
  },
  {
    id: "ns-04-eda-tonic-phasic",
    group: "necessary",
    order: 4,
    title: "Electrodermal activity: tonic baseline and phasic bursts",
    caption:
      "Tonic skin conductance level summarised as a mean with dispersion, and phasic bursts catalogued with their count, mean amplitude, and temporal density.",
    chartKind: "summary_table",
    dataPaths: ["feature_summary", "extended.descriptive_stats"],
    whatItShows:
      "The upper table reports tonic SCL in microsiemens with min, max, and the 5th to 95th percentile range. The lower table reports phasic activity as a mean of the absolute first difference of the EDA trace, a simple proxy for burst intensity, plus the count of peaks above a 0.05 µS threshold and the density of bursts per minute.",
    howToRead:
      "Healthy adult tonic SCL ranges approximately 2 to 20 µS depending on sensor and site; a tonic level below roughly 1 µS or above roughly 30 µS is often electrode-placement artifact rather than physiology (Boucsein, 2012). Phasic density above two to three bursts per minute is a meaningful orienting response rate; zero bursts over a several-minute recording is inconsistent with an engaged participant and worth investigating at the hardware level.",
    architecturalMeaning:
      "Tonic SCL is the slow autonomic axis most sensitive to sustained environmental stressors — noise load, thermal discomfort, dense-crowd conditions (Evans & Cohen, 1987). It rises over tens of seconds. Phasic bursts, by contrast, are the fast orienting responses to discrete events — a door closing, a face appearing in the periphery, a sudden pitch change. In architecture-cognition experiments the two components often tell different stories: a participant can show elevated tonic SCL across a noisy environment without phasic bursts (a chronic arousal state), or conversely phasic bursts to each sound event without a tonic rise (a well-adapted but reactive participant). Reporting the two components separately is not optional.",
    references: [
      { apa: "Boucsein, W. (2012). Electrodermal Activity (2nd ed.). Springer." },
      { apa: "Benedek, M., & Kaernbach, C. (2010). A continuous measure of phasic electrodermal activity. Journal of Neuroscience Methods, 190, 80–91.", doi: "10.1016/j.jneumeth.2010.04.028" },
    ],
  },
  {
    id: "ns-05-stress-decomposition",
    group: "necessary",
    order: 5,
    title: "Stress composite, decomposed by channel",
    caption:
      "The experimental stress index split into its four weighted contributions so the dominant driver is visible at a glance.",
    chartKind: "stacked_bar",
    dataPaths: ["extended.stress_decomposition"],
    whatItShows:
      "A single horizontal bar from 0 to 1 stacked into four coloured segments whose widths are the per-channel contributions to the composite: heart rate (0.35 weight), electrodermal tonic (0.35), electrodermal phasic (0.20), and the inverted HRV protection term (0.10). The total score is marked as a vertical tick; the dominant driver is labelled above the bar.",
    howToRead:
      "A stress score of 0.60 built from a 0.35 HR contribution plus a 0.25 EDA-tonic contribution is a very different physiological state from a 0.60 built from a 0.50 phasic contribution plus a 0.10 HRV-deficit; the two would point to different environmental causes and different redesign choices. Read the dominant-driver label first and the individual contributions second.",
    architecturalMeaning:
      "This is the single chart that makes the difference between 'the participant was stressed' and 'the participant was stressed because X'. HR-dominated stress in an architectural context typically points to cardiovascular demand from space-use (stairs, standing), to anticipatory arousal, or to an acoustic/visual startle stimulus. EDA-tonic-dominated stress points to sustained sympathetic activation from environmental load — noise, thermal, or cognitive-task demand. Phasic-dominated stress points to a high rate of discrete orienting events — interruptions or stimulus-dense environments. HRV-deficit dominance is the slowest of the four to appear and indicates a chronically low vagal tone reserve.",
    caveats:
      "The stress composite is experimental and not psychometrically validated; use it for within-session relative comparison, not as an absolute clinical measure.",
    references: [
      { apa: "Healey, J. A., & Picard, R. W. (2005). Detecting stress during real-world driving. IEEE TITS, 6, 156–166.", doi: "10.1109/TITS.2005.848368" },
    ],
  },
];

// -- Diagnostic analytics ---------------------------------------------

const DIAGNOSTIC: AnalyticEntry[] = [
  {
    id: "dg-01-sync-qc",
    group: "diagnostic",
    order: 1,
    title: "Synchronization quality composite",
    caption:
      "The five sub-components of the sync-QC score — overlap, drift deviation, sync ratio, residual lag, and jitter — displayed as weighted horizontal bars.",
    chartKind: "radar",
    dataPaths: ["sync_qc_score", "sync_qc_band", "sync_qc_failure_reasons"],
    whatItShows:
      "The composite 0-to-100 sync-QC score at the centre, with five bars around it: temporal overlap (30 percent weight), drift deviation from unity (25 percent), sync ratio (20 percent), residual lag (15 percent), and timestamp jitter (10 percent). Each bar is coloured green/yellow/red against its component threshold.",
    howToRead:
      "A green composite score with one red component is a warning: the aggregate looks fine but one sub-component is failing and may dominate a specific downstream feature. The reasons list below names every failing component in natural language. A yellow composite with all components in the 50 to 80 range is a cleaner failure mode to interpret than a green composite with one red component.",
    architecturalMeaning:
      "Sync quality is the gate between 'data' and 'interpretable data' in a two-device physiological recording. The sibling repo's V2.1 repair list documents why: a pipeline that runs unconditionally on 5 percent temporal overlap produces numbers indistinguishable from numbers produced on 95 percent overlap, and a researcher cannot tell the difference by looking at the numbers alone. This is the chart that tells you whether to trust the other twelve.",
    references: [
      { apa: "Sibling repo docs/GAP_ANALYSIS_POTEMKIN_2026-03-02.md." },
    ],
  },
  {
    id: "dg-02-drift",
    group: "diagnostic",
    order: 2,
    title: "Clock-drift diagnostic: piecewise linear fit and residuals",
    caption:
      "The piecewise drift correction that was applied, plus the residuals of the fit so over-corrected or under-corrected sessions are visible.",
    chartKind: "line",
    dataPaths: ["drift_slope", "drift_intercept_ms", "drift_segments"],
    whatItShows:
      "An upper panel shows source timestamps on the x-axis and reference timestamps on the y-axis with the piecewise linear fit overlaid; breakpoints between segments are marked as dashed vertical lines. A lower panel shows residuals — observed minus predicted — with ±1 SD and ±3 SD horizontal reference lines.",
    howToRead:
      "A good drift correction produces residuals that hover tightly around zero across the session. A single-segment fit whose residuals grow monotonically at the tails is the classic signature of temperature-dependent crystal drift in at least one of the devices (Gilfriche et al., 2022), which the piecewise fit is designed to catch. More than five segments on a five-minute recording usually indicates timestamp-jitter noise that should have been filtered upstream; the drift model is being asked to compensate for something it was not designed for.",
    architecturalMeaning:
      "This chart is only load-bearing when the sync-QC gate returned yellow. It answers the follow-up question: was the sync failure a drift problem, a jitter problem, or a true non-overlap problem? The answer determines whether to re-collect with NTP or to accept the session with a noted limitation.",
    references: [
      { apa: "Gilfriche, P., et al. (2022). Validity of the Polar H10 sensor for HRV analysis. Sensors, 22, 6536.", doi: "10.3390/s22176536" },
    ],
  },
  {
    id: "dg-03-motion",
    group: "diagnostic",
    order: 3,
    title: "Motion-artifact timeline",
    caption:
      "A per-second indicator of which samples the 0.3 g motion gate flagged as contaminated, overlaid against the HR trace for context.",
    chartKind: "strip",
    dataPaths: ["extended.cleaned_timeseries", "movement_artifact_ratio"],
    whatItShows:
      "A slim strip plot along the session timeline with coloured ticks at every second the motion gate fired. Beneath it, the HR trace is rendered at reduced opacity so the analyst can cross-reference whether a spike in HR coincides with flagged motion.",
    howToRead:
      "A motion-artifact ratio below roughly 5 percent is consistent with a participant sitting still. A ratio above 20 percent is either a participant who was in fact moving (exercise, a walking task) or a poorly-adhered wrist sensor that is being jostled by small wrist movements. The distinction matters because the former is legitimate data that should not be analysed as if it were rest, and the latter is artifact contamination that the gate should be catching.",
    architecturalMeaning:
      "In architectural experiments that involve movement — walking through a space, moving between rooms — a high motion-artifact ratio is expected and the resulting HRV/EDA numbers should not be interpreted as indices of arousal. In seated protocols, this chart's role is to catch silent failures in electrode adherence.",
    references: [
      { apa: "Kleckner, I. R., et al. (2018). Simple, transparent, and flexible automated quality assessment procedures for ambulatory EDA. IEEE TBME, 65, 1460–1467.", doi: "10.1109/TBME.2017.2758643" },
    ],
  },
  {
    id: "dg-04-tachogram",
    group: "diagnostic",
    order: 4,
    title: "RR tachogram with ectopic detection",
    caption:
      "The raw beat-to-beat interval series with ectopic-filtered beats marked, so missed detections or true arrhythmias are visible.",
    chartKind: "tachogram",
    dataPaths: ["extended.rr_series_ms"],
    whatItShows:
      "A line plot of RR interval in milliseconds on the y-axis against cumulative beat index on the x-axis. Beats that the Lipponen-and-Tarvainen-inspired filter flagged as ectopic are marked with red dots; beats that deviate by more than 30 percent from the local median are highlighted as candidates for manual review.",
    howToRead:
      "A clean tachogram shows a smooth, slowly-modulated series between approximately 600 and 1200 ms at rest. Sharp single-beat excursions — a beat at 400 ms followed immediately by a beat at 1600 ms — are the classic atrial-premature-contraction pattern. Sharp excursions clustered together indicate either a real arrhythmia or a burst of detection failures from signal dropout.",
    architecturalMeaning:
      "The tachogram is the first chart that every HRV analyst looks at, because every downstream HRV number is only as clean as this series. A tachogram with 5 percent ectopic beats will produce an RMSSD that is materially corrupted regardless of how sophisticated the downstream pipeline is. If this chart looks bad, no amount of statistical correction will save the analysis.",
    references: [
      { apa: "Lipponen, J. A., & Tarvainen, M. P. (2019). A robust algorithm for HRV time-series artefact correction. JMET, 43, 173–181.", doi: "10.1080/03091902.2019.1640306" },
    ],
  },
  {
    id: "dg-05-band-duration-gauge",
    group: "diagnostic",
    order: 5,
    title: "Recording duration against frequency-band minimums",
    caption:
      "Three horizontal gauges showing how much of the Task Force (1996) per-band minimum duration the recording actually covered.",
    chartKind: "gauge",
    dataPaths: ["extended.cleaned_timeseries", "feature_summary"],
    whatItShows:
      "Three horizontal bars, one per frequency band, extending to the recording's total duration with the band's required minimum marked as a vertical line: VLF 300 s, LF 120 s, HF 60 s. Bars that meet their minimum turn green; those that fall short turn amber, with the numeric shortfall displayed.",
    howToRead:
      "VLF power is the most fragile estimate — it requires at least 300 seconds of stationary recording to contain enough full cycles of the slowest oscillation (Task Force, 1996). HF is the most forgiving. A five-minute recording will meet the LF and HF minimums but produce no VLF estimate; a two-minute recording produces only HF. This gauge tells you, before you look at the PSD, which bands your recording is even entitled to report.",
    architecturalMeaning:
      "Short recordings in architecture-cognition experiments — a three-minute walking-through-a-space condition, a two-minute baseline-then-stimulus block — are scientifically valid for HR and EDA but not for full-spectrum HRV. The gauge exists to prevent researchers from accidentally reporting a VLF number from a 90-second recording and then having a reviewer ask why.",
    references: [
      { apa: "Task Force ESC/NASPE (1996). Heart rate variability. Circulation, 93, 1043–1065." },
    ],
  },
];

// -- Question-driven analytics ----------------------------------------

const QUESTION_DRIVEN: AnalyticEntry[] = [
  // Science questions
  {
    id: "q-s-01-phase-comparison",
    group: "question",
    category: "science",
    question: "Did the stressor produce a measurable physiological change?",
    order: 1,
    title: "Phase-comparison forest plot",
    caption:
      "Mean with 95 percent confidence interval for RMSSD, mean HR, EDA tonic, and stress composite in each declared phase (baseline, task, recovery).",
    chartKind: "forest",
    dataPaths: ["markers_summary", "extended.windowed"],
    minimumPreconditions: ["Event markers CSV or manual phase timings must have been supplied."],
    whatItShows:
      "Four rows, one per feature. Each row has three dots — baseline, task, recovery — with horizontal bars showing the 95 percent t-distribution confidence interval on the phase mean. Phases whose confidence intervals do not overlap the baseline are annotated with Cohen's d effect size.",
    howToRead:
      "A Cohen's d of 0.5 or larger for RMSSD between baseline and task — with non-overlapping confidence intervals — is a reasonable bar for 'the stressor worked'. A d of 0.2 or less with overlapping intervals is a null result regardless of whether the task condition 'looks' different on the raw trace.",
    architecturalMeaning:
      "This is the academic-paper-ready figure for an architecture-cognition study. It answers the first question a reviewer will ask: did your environmental manipulation actually do anything to the participant? A null result on this chart — a condition that was supposed to be stressful producing no HRV or EDA change — is not a pipeline failure, it is a scientifically meaningful result that often indicates either participant non-engagement or an insufficiently strong manipulation.",
    references: [
      { apa: "Cumming, G. (2014). The new statistics: Why and how. Psychological Science, 25, 7–29.", doi: "10.1177/0956797613504966" },
    ],
  },
  {
    id: "q-s-02-lfhf-trajectory",
    group: "question",
    category: "science",
    question: "Is sympathovagal balance shifting over the session?",
    order: 2,
    title: "LF/HF ratio trajectory in sliding windows",
    caption:
      "The LF-to-HF ratio computed in 120-second windows with 60-second steps, with shaded LF and HF power bands below.",
    chartKind: "line",
    dataPaths: ["extended.spectral_trajectory"],
    whatItShows:
      "A line plot of LF/HF ratio against time, with gaps where the window duration was insufficient for a stable estimate. The two bands are rendered as stacked areas below the main trace so the analyst can see whether a rise in the ratio is driven by rising LF, falling HF, or both.",
    howToRead:
      "A rising ratio that is being driven by rising LF with roughly stable HF is the signature of a sympathetic-axis shift. A rising ratio driven primarily by falling HF with stable LF is the signature of parasympathetic withdrawal — a different autonomic interpretation. Reading the components matters.",
    architecturalMeaning:
      "Autonomic transitions in response to environmental change (entering a noisy zone, stepping into a dim corridor, encountering a crowd) are often too slow to see in a five-minute snapshot but visible across twenty minutes of windowed spectral analysis. This is the chart for experiments whose manipulation acts on slower timescales — ambient light cycle, thermal gradient over time — that cardiac-only analyses miss.",
    caveats:
      "LF/HF as a direct index of sympathovagal balance has been disputed (Billman, 2013). Interpret direction of change rather than absolute magnitude.",
    references: [
      { apa: "Billman, G. E. (2013). The LF/HF ratio does not accurately measure cardiac sympatho-vagal balance. Frontiers in Physiology, 4, 26.", doi: "10.3389/fphys.2013.00026" },
    ],
  },
  {
    id: "q-s-03-poincare",
    group: "question",
    category: "science",
    question: "How is the beat-to-beat variability shaped geometrically?",
    order: 3,
    title: "Poincaré plot with SD1 and SD2",
    caption:
      "A scatter of each RR interval against its successor, with the SD1/SD2 ellipse fit so the vagally-mediated and total variability are visible simultaneously.",
    chartKind: "poincare",
    dataPaths: ["extended.rr_series_ms"],
    whatItShows:
      "A square scatter plot with RR(n) on the x-axis and RR(n+1) on the y-axis and the identity diagonal drawn. A 95 percent coverage ellipse is fit to the cluster, with its two principal axes — SD1 (short-term, perpendicular to the diagonal) and SD2 (long-term, along the diagonal) — labelled and their numeric values reported.",
    howToRead:
      "A rounder cluster means SD1 and SD2 are of comparable magnitude, indicating substantial parasympathetic contribution. An elongated cluster along the diagonal means SD2 dominates, indicating sympathetic predominance. Scattered points outside the main cluster are almost always ectopic beats that the tachogram diagnostic should also have flagged.",
    architecturalMeaning:
      "Poincaré is Kubios's default HRV visualisation and the one researchers familiar with Kubios will reach for first. In architecture-cognition the shape of the ellipse across conditions is one of the more stable group-level effects: healthy participants in restorative environments (views of nature, daylit spaces) show rounder ellipses than the same participants in demanding environments (compression, noise, clutter).",
    references: [
      { apa: "Brennan, M., Palaniswami, M., & Kamen, P. (2001). Do existing measures of Poincaré plot geometry reflect nonlinear features of HRV? IEEE TBME, 48, 1342–1347.", doi: "10.1109/10.959330" },
    ],
  },
  {
    id: "q-s-04-habituation",
    group: "question",
    category: "science",
    question: "Did the participant habituate over the session?",
    order: 4,
    title: "First-half vs second-half effect sizes with trend p-values",
    caption:
      "Cohen's d for each feature comparing the first half of the session against the second, with FDR-corrected trend p-values from Pearson regression.",
    chartKind: "forest",
    dataPaths: ["extended.inference"],
    whatItShows:
      "A small forest plot with d values and 95 percent confidence intervals for HR and EDA means, plus Benjamini-Hochberg-corrected trend p-values.",
    howToRead:
      "A negative d on HR with a significant trend p-value means HR decayed across the session — the canonical habituation signature. A positive d on HR with a significant trend means sensitization or accumulating load. A d near zero with a non-significant p means the participant's state was stable.",
    architecturalMeaning:
      "Habituation within a session complicates architecture-cognition inference: a participant whose arousal decays over ten minutes of a stressful environment may be telling you the environment stopped stressing them or may be telling you they stopped paying attention to it. Reporting the habituation result explicitly is methodologically essential when comparing early-exposure and late-exposure responses.",
    references: [
      { apa: "Benjamini, Y., & Hochberg, Y. (1995). Controlling the false discovery rate. JRSS-B, 57, 289–300." },
    ],
  },
  {
    id: "q-s-05-hr-eda-coupling",
    group: "question",
    category: "science",
    question: "How tightly coupled are the cardiac and electrodermal responses?",
    order: 5,
    title: "Rolling HR-EDA coupling (Pearson r in sliding windows)",
    caption:
      "The instantaneous correlation between HR and EDA computed in 60-second windows with 30-second overlap.",
    chartKind: "line",
    dataPaths: ["extended.windowed"],
    whatItShows:
      "A line plot of windowed Pearson r against time, bounded to ±1. Values above roughly 0.5 mean the two channels are moving together; values below about -0.3 mean they are antagonistic; values near zero mean they are decoupled.",
    howToRead:
      "Tight positive coupling during a stressor is the sympathetic-integration signature. Decoupling during a rest phase but coupling during tasks suggests the environmental demand recruited both autonomic axes together. Persistent decoupling throughout means the two systems are acting on different inputs — worth a methodological check.",
    architecturalMeaning:
      "Architecture-cognition experiments sometimes produce the puzzling result of 'stress shown in one channel but not the other'. This chart distinguishes between a true dissociation (different environmental perceptions driving different autonomic pathways) and a measurement-artifact dissociation (poor electrode adherence, motion bleed).",
    references: [
      { apa: "Berntson, G. G., et al. (1997). Heart rate variability: Origins, methods, and interpretive caveats. Psychophysiology, 34, 623–648.", doi: "10.1111/j.1469-8986.1997.tb02140.x" },
    ],
  },
  {
    id: "q-s-06-bland-altman",
    group: "question",
    category: "science",
    question: "Do the computed metrics match a Kubios reference?",
    order: 6,
    title: "Bland-Altman agreement against Kubios",
    caption:
      "Bias and 95 percent limits of agreement between this pipeline's RMSSD, SDNN, and mean HR and those computed by Kubios HRV Premium on the same data.",
    chartKind: "bland_altman",
    dataPaths: ["benchmark"],
    minimumPreconditions: ["A Kubios CSV export must be uploaded via the benchmark endpoint first."],
    whatItShows:
      "Three scatter plots, one per metric. Each plots the mean of the two systems on the x-axis against their difference on the y-axis, with the mean bias and the ±1.96 × SD limits of agreement drawn as horizontal lines.",
    howToRead:
      "Chung et al. (2026) report Pearson r > 0.99 between the Polar H10 and a gold-standard ECG; a pipeline that claims Kubios parity should produce a bias near zero and limits of agreement narrow enough to be uninformative at the session level. A non-zero bias means this pipeline has a systematic offset; wide LoAs mean precision is lower than Kubios.",
    architecturalMeaning:
      "This is the chart that lets you claim, in a methods section, that your numbers are interchangeable with Kubios — or, crucially, that they are not. Either answer is scientifically publishable; silence on the question is not.",
    references: [
      { apa: "Bland, J. M., & Altman, D. G. (1986). Statistical methods for assessing agreement. The Lancet, 327, 307–310.", doi: "10.1016/S0140-6736(86)90837-8" },
      { apa: "Chung, V., et al. (2026). Validity of the Polar H10 for continuous HR and HR synchrony. Sensors, 26, 855.", doi: "10.3390/s26030855" },
    ],
  },

  // Diagnostics questions
  {
    id: "q-d-01-rr-histogram",
    group: "question",
    category: "diagnostics",
    question: "Are the RR intervals biologically plausible?",
    order: 7,
    title: "RR-interval histogram with physiological bounds",
    caption:
      "A density histogram of the beat-to-beat intervals with vertical reference lines at the physiological floor (300 ms) and ceiling (2000 ms).",
    chartKind: "histogram",
    dataPaths: ["extended.rr_series_ms"],
    whatItShows:
      "A histogram of RR intervals in millisecond bins from 300 to 2000 ms with vertical markers at common reference points (600, 1000, 1500 ms). A single well-centred peak is healthy; bimodal or spread distributions indicate either arrhythmia or signal contamination.",
    howToRead:
      "A well-centred unimodal distribution around 800 to 1000 ms is typical at rest. A secondary peak at twice the main mode is the signature of every-other-beat detection failures. A primary mode below 500 ms suggests exercise or a detector that is counting T-waves as R-waves.",
    architecturalMeaning:
      "This is a data-hygiene chart before it is a physiology chart. Its purpose is to answer 'can I trust this RR series?' before any of the HRV numbers are reported.",
    references: [
      { apa: "Task Force ESC/NASPE (1996). Heart rate variability. Circulation, 93, 1043–1065." },
    ],
  },
  {
    id: "q-d-02-motion-timeline",
    group: "question",
    category: "diagnostics",
    question: "When did motion contaminate the signal?",
    order: 8,
    title: "Motion-gate activations against the HR trace",
    caption:
      "A strip plot of motion-flagged seconds overlaid on the heart-rate timeseries.",
    chartKind: "strip",
    dataPaths: ["extended.cleaned_timeseries"],
    whatItShows: "Motion-flagged seconds as coloured ticks on a timeline, with the HR trace at reduced opacity behind.",
    howToRead:
      "Coincidence between a flagged second and a spike in HR is the signature of motion artifact masquerading as physiology. Flagged seconds with no HR excursion are clean motion events that the gate caught without corrupting the primary signal.",
    architecturalMeaning:
      "Useful in any protocol where the participant is asked to move — point-of-interest walking, door-opening tasks — to decide which HR excursions to treat as environmental responses and which to treat as motion-driven.",
    references: [
      { apa: "Kleckner, I. R., et al. (2018). Simple, transparent, and flexible automated quality assessment for ambulatory EDA. IEEE TBME, 65, 1460–1467.", doi: "10.1109/TBME.2017.2758643" },
    ],
  },
  {
    id: "q-d-03-drift-residuals",
    group: "question",
    category: "diagnostics",
    question: "Are the two device clocks drifting apart?",
    order: 9,
    title: "Drift-correction residuals over time",
    caption:
      "Residuals of the piecewise linear drift fit with reference bands at ±1 SD and ±3 SD.",
    chartKind: "line",
    dataPaths: ["drift_slope", "drift_intercept_ms", "drift_segments"],
    whatItShows: "A residual plot showing how much each timestamp remained misaligned after correction.",
    howToRead: "Residuals that fan outward at the tails indicate uncorrected nonlinear drift; residuals that step-change at segment boundaries indicate poorly-placed breakpoints.",
    architecturalMeaning:
      "A long-duration (>30 minute) experiment in a thermally-unstable setting (an outdoor walking study) is more likely to show temperature-dependent crystal drift; this chart is the confirmation that the piecewise correction caught it.",
  },
  {
    id: "q-d-04-ectopic-rate",
    group: "question",
    category: "diagnostics",
    question: "How many ectopic beats were filtered, and where?",
    order: 10,
    title: "Ectopic-beat timeline with rate summary",
    caption:
      "Positions of ectopic-flagged beats along the session, plus an overall ectopic rate in beats per minute.",
    chartKind: "tachogram",
    dataPaths: ["extended.rr_series_ms"],
    whatItShows:
      "A timeline of cumulative-beat positions with ectopic-flagged beats marked. A numeric summary reports total beats, ectopic beats, and ectopic rate in beats per minute.",
    howToRead:
      "An ectopic rate below 1 beat per minute is typical for a healthy participant at rest. Clusters of ectopics at specific time points suggest either arrhythmia episodes or signal dropout. An ectopic rate above 5 per minute with no clinical context is almost always a detection problem rather than a physiology problem.",
    architecturalMeaning: "The ectopic timeline, not just the ectopic count, is what lets you tell 'one burst of dropout early' from 'distributed misdetection throughout'.",
    references: [
      { apa: "Lipponen, J. A., & Tarvainen, M. P. (2019). A robust algorithm for HRV time-series artefact correction. JMET, 43, 173–181.", doi: "10.1080/03091902.2019.1640306" },
    ],
  },
];

export const CATALOG: AnalyticEntry[] = [...NECESSARY, ...DIAGNOSTIC, ...QUESTION_DRIVEN];

export function analyticsByGroup(group: AnalyticGroup): AnalyticEntry[] {
  return CATALOG.filter((a) => a.group === group).sort((a, b) => a.order - b.order);
}

export function analyticsByCategory(category: QuestionCategory): AnalyticEntry[] {
  return CATALOG.filter((a) => a.group === "question" && a.category === category)
    .sort((a, b) => a.order - b.order);
}

export function getAnalytic(id: string): AnalyticEntry | undefined {
  return CATALOG.find((a) => a.id === id);
}

export function adjacentAnalytics(id: string): { prev?: AnalyticEntry; next?: AnalyticEntry } {
  const a = getAnalytic(id);
  if (!a) return {};
  const peers = analyticsByGroup(a.group);
  const idx = peers.findIndex((p) => p.id === id);
  return {
    prev: idx > 0 ? peers[idx - 1] : undefined,
    next: idx >= 0 && idx < peers.length - 1 ? peers[idx + 1] : undefined,
  };
}

export const GROUP_META: Record<AnalyticGroup, { title: string; caption: string; icon: string; hue: string }> = {
  necessary: {
    title: "Necessary Science Analytics",
    caption: "The five charts a research-grade HRV + EDA analysis is expected to produce and defend.",
    icon: "◈",
    hue: "#2A7868",
  },
  diagnostic: {
    title: "Diagnostic Analytics",
    caption: "Data-quality and pipeline-health checks — read these before trusting the science.",
    icon: "◇",
    hue: "#E8872A",
  },
  question: {
    title: "Question-Driven Analytics",
    caption: "Analyses organised by the research question each one answers.",
    icon: "◯",
    hue: "#4A6FA8",
  },
};

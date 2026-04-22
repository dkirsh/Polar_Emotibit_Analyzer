# Stress Composite v2 — Expert Panel Consultation

**Document**: `STRESS_COMPOSITE_V2_PANEL_JUSTIFICATION_2026-04-21.md`
**Subject**: Weighting scheme of the seven-channel exploratory stress composite implemented in `backend/app/services/processing/stress.py` (`compute_stress_score_v2`).
**Panel**: Julian F. Thayer (UC Irvine / Ohio State); Fred Shaffer (Truman State University); Mika P. Tarvainen (University of Eastern Finland); Stephen W. Porges (UNC / Kinsey Institute); Daniel Lakens (TU Eindhoven).
**Date of record**: 21 April 2026.
**Status of the instrument**: experimental; not psychometrically validated.

---

## 1. Framing: what a stress composite is trying to estimate

A stress composite of the kind under review does not attempt to measure psychological stress as a construct. It estimates a physiological proxy for it — the momentary tilt of the autonomic nervous system toward sympathetic activation and away from parasympathetic restraint — and it does so by fusing signals that each describe the tilt from a different angle. The reason for fusion, rather than reliance on a single channel, is that no peripheral signal is uniquely diagnostic of stress. Heart rate rises under exercise, under caffeine, and under postural change; electrodermal activity rises under thermal load and under novelty; high-frequency heart rate variability falls under respiratory slowing and under mental effort alike. Any one channel therefore carries stress-relevant information along with a substantial quantity of nuisance variance. A weighted multichannel composite reduces the influence of any single nuisance source by requiring concordance across channels before the score moves substantially.

The panel accepts the design premise of the Polar-EmotiBit Analyzer's v2 composite on these grounds. We also accept the project's explicit self-description as an exploratory within-subject index, not an absolute between-subject measurement, and we return below to what that restriction does and does not license. The remainder of this document reviews each of the seven channels, the redistribution rule that handles missing channels, the question of informational redundancy among channels, and the limits that should be declared in any thesis chapter citing the composite.

## 2. Channels, evidence, and weights

### 2.1 Heart rate (weight 0.15)

The inclusion of mean heart rate is the least controversial element of the composite. Elevated heart rate reflects the joint output of sympathetic acceleration and parasympathetic withdrawal, and it has served as a basic stress indicator since Cannon's early work on homeostasis. Modern reference norms and the mapping of resting heart rate to autonomic balance are summarised in Shaffer and Ginsberg (2017), and the Task Force of the European Society of Cardiology and the North American Society of Pacing and Electrophysiology (1996) provides the canonical measurement conventions.

The specific information heart rate contributes to the composite is the gross level of chronotropic drive. It is insensitive to the *pattern* of autonomic control — two participants with identical resting heart rates may differ substantially in vagal modulation — and it is for that reason that heart rate alone is insufficient. Within the v2 scheme it is normalised as `(HR − 60)/60`, clipping at 120 bpm, and weighted at 0.15. The panel judges this defensible and, if anything, slightly underweighted relative to naive intuition, which is correct: heart rate alone is the least specific of the seven channels, and the composite is better served by letting it anchor the lower end of the weight distribution.

### 2.2 Tonic electrodermal activity (weight 0.20)

Tonic skin conductance level indexes sustained sudomotor activity driven by the cholinergic sympathetic pathway. Because the sweat glands of the palm and finger are exclusively sympathetically innervated, tonic EDA is one of the few peripheral channels that is not confounded by vagal co-activation; it is a pure sympathetic index in a way that heart rate is not. The canonical reference is Boucsein's *Electrodermal Activity* (2012, 2nd edition), which summarises decades of methodological work, and Dawson, Schell, and Filion's chapter in the *Handbook of Psychophysiology* (2017) is the standard methodological treatment used in stress research.

The information tonic EDA adds to the composite is precisely this specificity. It provides a sympathetic estimate that cannot be explained away by changes in vagal tone, respiration, or posture. Its weakness is slowness: tonic level moves on a timescale of minutes and varies widely between individuals and across thermal and hydration states. The v2 weight of 0.20 — the largest single weight in the composite alongside sympathovagal balance — reflects this channel's specificity and robustness. The panel endorses the weight. Boucsein would caution against reading absolute SCL values between participants, which the module already does by normalising only to a 0–20 μS range; but within a single session, change in tonic EDA is among the most interpretable sympathetic signals the device can produce.

### 2.3 Phasic electrodermal activity (weight 0.10)

The phasic component of the electrodermal signal captures short, event-locked bursts of sudomotor activity — the skin conductance responses associated with orienting, novelty, and affective reactivity. Decomposing the raw EDA signal into tonic and phasic components is now standard practice; Benedek and Kaernbach (2010) provided the continuous deconvolution method that most contemporary pipelines (including cvxEDA, Greco et al., 2016) extend.

The information phasic EDA contributes is orthogonal to the tonic level: a participant may show a flat baseline and nonetheless produce a dense burst of phasic responses during a stressor, and vice versa. The composite treats these as separate channels for this reason, which the panel endorses. The weight of 0.10 is modest and appropriate. Phasic responses are informative but noisier than tonic level, are sensitive to motion artefact and electrode contact, and carry less information per unit time about sustained state. A weight higher than tonic EDA would overstate their reliability; the chosen weight preserves their contribution without letting a single large response dominate the score.

### 2.4 Vagal composite — RMSSD and pNN50 averaged (weight 0.15)

The vagal composite channel averages two time-domain heart rate variability statistics: the root mean square of successive differences in the inter-beat interval series, normalised against an 80 ms reference, and the proportion of successive intervals that differ by more than 50 ms (pNN50), normalised against a 50 percent reference. The rationale is that both are short-latency, respiration-entrained markers of vagal modulation of the sinus node, but they weight the tail of the difference distribution differently; averaging them produces a more stable vagal estimate than either alone.

The published basis for this channel is substantial. Thayer's neurovisceral integration model (Thayer & Lane, 2000; Thayer et al., 2012) treats resting vagal tone as a peripheral read-out of prefrontal inhibitory control over subcortical threat circuitry, so that a fall in RMSSD under stress reflects a withdrawal of that inhibition. The Task Force (1996) defined both RMSSD and pNN50 as standard short-term vagal indices; Shaffer and Ginsberg (2017) summarise their norms and measurement windows; Kim et al. (2018) show that RMSSD is the most reliable HRV statistic on short segments down to sixty seconds, and that pNN50 stabilises at somewhat longer windows (typically at least two minutes).

The information the vagal composite adds is the inverse of what heart rate gives. It is possible for heart rate to remain flat while beat-to-beat variability collapses — a pattern of "rigid" heart rhythm that is a more specific stress marker than rate alone. Thayer's position, which the panel adopts here, is that any stress composite that does not include a short-latency vagal term is not describing what matters most, cognitively speaking; the vagal channel is the entry point through which top-down regulation becomes visible in the peripheral signal. A weight of 0.15 is appropriate and defensible. Thayer would argue for parity with sympathovagal balance (0.20), and one can see the argument; the panel as a whole judges that 0.15 is adequate so long as RSA (see §2.7) and sympathovagal balance (§2.5) carry their own weight, as they do here.

### 2.5 Sympathovagal balance via LF_nu (weight 0.20)

The sympathovagal channel uses low-frequency spectral power expressed in normalised units, LF_nu, which is LF divided by the sum of LF and HF power after excluding the very-low-frequency band. This measure was introduced into cardiovascular psychophysiology by Pagani and colleagues (1986, *Circulation Research*) and codified by the Task Force (1996). It remains the canonical Kubios-grade sympathovagal marker and was selected for v2 precisely for Kubios parity.

The literature on what LF_nu means has been contested for three decades. Early interpretations treated LF as a sympathetic spectrum; later work (Eckberg, 1997; Billman, 2013) showed that LF power also carries baroreflex-mediated vagal contribution, and that LF/HF ratios should not be read as a clean sympathetic–parasympathetic dial. Tarvainen's position, which the panel records faithfully, is that LF_nu nevertheless retains practical value as a between-subject comparable index of the relative tilt of the autonomic balance under controlled respiration, provided one does not reify it as a pure sympathetic measure. It is for this reason that Kubios reports LF_nu rather than raw LF.

The information LF_nu adds to the composite, granted these qualifications, is a spectral view that neither the time-domain vagal channel nor the EDA channels provide. It is especially useful for distinguishing a participant whose absolute heart rate and EDA are unremarkable but whose spectral distribution of autonomic oscillations is tilted. The v2 weight of 0.20 is defensible; the panel notes that it sits at the upper end of what the evidence supports and that Porges in particular would weight it lower. However, the redistribution rule (see §3) already downweights LF_nu when it cannot be computed on sessions shorter than 120 seconds, which addresses the most common way the measure misleads.

### 2.6 Autonomic rigidity via SD1/SD2 (weight 0.10)

The Poincaré plot represents each inter-beat interval against the next; SD1 captures short-term variability (perpendicular to the identity line) and SD2 captures long-term variability (along it). Brennan, Palaniswami, and Kamen (2001, *IEEE Transactions on Biomedical Engineering*) showed that SD1 is mathematically equivalent to RMSSD divided by the square root of two, and that SD2 relates to the standard deviation of all NN intervals and to low-frequency variability. The ratio SD1/SD2 is a shape parameter of the Poincaré cloud: a balanced, healthy rhythm produces a ratio near 0.5, and the ratio falls as the plot becomes elongated — the classic "cigar" shape associated with stress and autonomic rigidity.

The information SD1/SD2 contributes to the composite is the *shape* of the variability distribution rather than its magnitude. It is possible for SD1 and SD2 to each look unremarkable in isolation while their ratio has collapsed, indicating a rigid rhythm with disproportionate long-term variability. This is what the composite's rigidity term is designed to detect. The v2 weight of 0.10 is modest and appropriate. The panel, with Tarvainen taking the lead on this point, judges that a higher weight would be unwise because SD1/SD2 is numerically fragile on short segments and on records with ectopic beats (see Lipponen & Tarvainen, 2019, for the current correction standard), and because the measure is partially redundant with the vagal composite through its shared dependence on RMSSD. The 0.10 weight honours the distinctive information while respecting the redundancy.

### 2.7 Respiratory sinus arrhythmia (weight 0.10)

Respiratory sinus arrhythmia is the rhythmic modulation of heart rate by the respiratory cycle, heart rate rising on inspiration and falling on expiration. Porges's polyvagal theory treats RSA as the peripheral signature of myelinated vagal outflow from the nucleus ambiguus — the "smart vagus" that governs the social engagement system and the flexible regulation of physiological state (Porges, 2007, *Biological Psychology*). The WESAD benchmark (Schmidt et al., 2018, *ICMI*) identified respiration as the single strongest channel in binary stress classification across their held-out participants, which is the empirical support the v2 module cites in its docstring.

The information RSA adds to the composite is the coupling between breath and heart — information that is present in the inter-beat interval series only in its high-frequency spectral power and that RMSSD approximates. A stressor that reduces RSA amplitude does so by withdrawing myelinated vagal drive; this is a more specific signal than a generic fall in heart rate variability because it localises the withdrawal to the ventral vagal complex rather than the cardiac-vagal system as a whole.

The v2 weight of 0.10 is the one point on which this panel registers a genuine disagreement. Porges argues that RSA should carry a higher weight than rigidity and at least parity with the vagal composite, on the grounds that RSA is the more theoretically grounded vagal measure. Shaffer and Tarvainen counter that RSA as derived from ECG-derived respiration (EDR) on this hardware is noisier than the time-domain vagal statistics and that a higher weight would amplify estimation error. The panel's consensus is that 0.10 is adequate for the current device but that if the pipeline acquires a direct respiratory belt, the RSA weight should be revisited upward. The docstring's reference to Schmidt et al. (2018) should not be read as justifying a higher weight than 0.10 on this device, since WESAD used a chest-belt respiratory sensor and the present system infers respiration from ECG.

## 3. The redistribution rule for missing channels

The v2 composite handles missing channels — LF_nu, SD1/SD2, RSA, and optionally pNN50 — by redistributing the absent weight equally across the present channels. The panel endorses this rule in principle. It keeps the composite on a common 0–1 scale across sessions and avoids the alternative of treating an absent channel as zero, which would bias the score downward in a way that is not physiologically meaningful.

Two qualifications belong on the record.

First, Shaffer notes that the stability of pNN50 on short segments is particular. Pointing to Kim et al. (2018) and to Shaffer and Ginsberg (2017), he observes that pNN50 requires meaningfully longer observation windows than RMSSD to stabilise — on the order of two to five minutes rather than the sixty seconds at which RMSSD becomes usable. The v2 module treats pNN50 as optional within the vagal composite, falling back to RMSSD alone when pNN50 is absent. This is the correct default. Students analysing sessions shorter than two minutes should prefer the RMSSD-only vagal estimate and should not attempt to compute pNN50 on very short segments merely because the pipeline accepts a value.

Second, the redistribution rule silently changes the effective weighting of channels that remain. A session with no LF_nu, no SD1/SD2, and no RSA reduces the composite to four channels (HR, EDA tonic, EDA phasic, and vagal composite) whose effective weights are 0.25, 0.30, 0.20, and 0.25 respectively — heavier reliance on EDA tonic and heavier reliance on HR than the seven-channel scheme intends. The panel recommends that thesis chapters citing the composite report the number of active channels per session and the effective weights actually used, so that the reader can see which composite, in effect, generated the score. The audit trail returned by `compute_stress_score_v2` already makes this straightforward.

## 4. Informational redundancy and degrees of freedom

Lakens's contribution to this consultation is the observation that the composite's seven channels are not seven statistically independent pieces of evidence, and that this matters for any claim built on the composite's variance. Three correlations are structural rather than incidental.

RMSSD and SD1 are algebraically linked: SD1 equals RMSSD divided by the square root of two (Brennan et al., 2001). Any covariance between the vagal composite and the rigidity channel therefore partly reflects this shared term rather than independent physiology. In practice this means that a participant with low RMSSD will also produce a low SD1, which drives SD1/SD2 toward being dominated by SD2; the rigidity term and the vagal term thus move together by construction to a measurable degree.

LF_nu, as LF/(LF+HF) in normalised units, is closely related to the LF/HF ratio, and through the HF term it shares variance with the time-domain vagal indices RMSSD and pNN50, which track HF power under paced respiration. The sympathovagal channel and the vagal composite therefore share information, though the extent of that sharing depends on respiratory rate and the participant's baroreflex function.

RSA amplitude derived from the respiratory modulation of inter-beat intervals is similarly related to high-frequency HRV power, and hence to both RMSSD and LF_nu through the HF denominator. On the present device, where RSA is estimated from ECG-derived respiration rather than a dedicated belt, this redundancy is pronounced.

The implication Lakens draws from these three redundancies is not that the composite is defective — a composite with correlated components can still be more informative than any single component — but that the effective number of independent channels is smaller than seven. A reasonable estimate, based on typical autonomic correlations reported in healthy adults, is an effective dimensionality of four to five rather than seven. This has two consequences for inference. First, the composite's variance is smaller than seven-channel Gaussian intuition would suggest, and confidence intervals derived from it should reflect that. Second, sensitivity analyses — recomputing the composite with each of LF_nu, SD1/SD2, and RSA removed in turn — are the honest way to show that a finding does not depend on a single redundant channel. The panel recommends that students include such a sensitivity analysis in any thesis chapter that relies on the composite for a substantive claim. Lakens's guidance on sample size justification (Lakens, 2022, *Collabra: Psychology*) applies here: the effective degrees of freedom, not the nominal channel count, should inform the power analysis.

## 5. Known limitations

The composite, as implemented, cannot legitimately do the following.

First, it cannot estimate stress on an absolute scale between participants. The normalisation constants (HR to a 60–120 bpm window, EDA to 0–20 μS, RMSSD to 80 ms, pNN50 to 50 percent, LF_nu to 0–100) are approximate population bands, not individually calibrated. A score of 0.6 in one participant and a score of 0.6 in another do not warrant the claim that the two are equally stressed.

Second, it cannot substitute for a validated psychometric instrument. The Perceived Stress Scale (Cohen, Kamarck, & Mermelstein, 1983) and the Depression Anxiety Stress Scales (Lovibond & Lovibond, 1995) estimate constructs that are related to but distinct from physiological activation. A thesis that treats the composite as a replacement for PSS-10 or DASS-21, rather than as a concurrent physiological index, misuses it.

Third, it cannot support clinical decision-making. The composite is not a diagnostic instrument, is not FDA- or CE-cleared for any medical purpose, and must not be used to triage, flag, or describe any individual's mental or cardiovascular health.

Fourth, it cannot establish the direction or the cause of a within-session change. A rise in the composite from 0.3 to 0.7 during a cognitive task is consistent with a stress response; it is equally consistent with increased physical movement, a postural shift, a rise in ambient temperature, or a change in breathing pattern induced by the task itself. The composite describes autonomic activation, not its cause.

## 6. Guidance for students writing thesis chapters

Students citing the composite should describe it as an exploratory, within-subject, multimodal physiological index of autonomic activation, not as a stress measure. They should report, for each session, the number of active channels, the effective weights produced by the redistribution rule, and the raw values feeding the composite. They should accompany any inference built on the composite with a sensitivity analysis in which each of LF_nu, SD1/SD2, and RSA is removed in turn, following Lakens's recommendation in §4. They should cite the composite's experimental status explicitly and should decline to interpret between-subject differences in score as differences in stress. Where a between-subject claim is needed, they should pair the composite with a validated psychometric instrument administered concurrently. They should cite the present document alongside the source code path and the commit hash of the version they used, so that readers can reproduce the exact scheme.

The composite is a useful instrument for the scientific questions the project is designed to ask. It is also a limited one. The panel's view is that this combination of usefulness and limitation is properly registered by the module's current documentation and by the guidance above, and that students who follow this guidance can use the composite responsibly in their thesis chapters.

---

## References

Benedek, M., & Kaernbach, C. (2010). A continuous measure of phasic electrodermal activity. *Journal of Neuroscience Methods*, 190(1), 80–91. https://doi.org/10.1016/j.jneumeth.2010.04.028 (≈ 1,100 citations)

Berntson, G. G., Bigger, J. T., Eckberg, D. L., Grossman, P., Kaufmann, P. G., Malik, M., Nagaraja, H. N., Porges, S. W., Saul, J. P., Stone, P. H., & van der Molen, M. W. (1997). Heart rate variability: Origins, methods, and interpretive caveats. *Psychophysiology*, 34(6), 623–648. https://doi.org/10.1111/j.1469-8986.1997.tb02140.x (≈ 3,800 citations)

Billman, G. E. (2013). The LF/HF ratio does not accurately measure cardiac sympatho-vagal balance. *Frontiers in Physiology*, 4, 26. https://doi.org/10.3389/fphys.2013.00026 (≈ 1,200 citations)

Boucsein, W. (2012). *Electrodermal activity* (2nd ed.). Springer. https://doi.org/10.1007/978-1-4614-1126-0 (≈ 4,500 citations)

Brennan, M., Palaniswami, M., & Kamen, P. (2001). Do existing measures of Poincaré plot geometry reflect nonlinear features of heart rate variability? *IEEE Transactions on Biomedical Engineering*, 48(11), 1342–1347. https://doi.org/10.1109/10.959330 (≈ 1,400 citations)

Cohen, S., Kamarck, T., & Mermelstein, R. (1983). A global measure of perceived stress. *Journal of Health and Social Behavior*, 24(4), 385–396. https://doi.org/10.2307/2136404 (≈ 36,000 citations)

Dawson, M. E., Schell, A. M., & Filion, D. L. (2017). The electrodermal system. In J. T. Cacioppo, L. G. Tassinary, & G. G. Berntson (Eds.), *Handbook of psychophysiology* (4th ed., pp. 217–243). Cambridge University Press. (≈ 3,000 citations across editions)

Eckberg, D. L. (1997). Sympathovagal balance: A critical appraisal. *Circulation*, 96(9), 3224–3232. https://doi.org/10.1161/01.CIR.96.9.3224 (≈ 1,700 citations)

Greco, A., Valenza, G., Lanata, A., Scilingo, E. P., & Citi, L. (2016). cvxEDA: A convex optimization approach to electrodermal activity processing. *IEEE Transactions on Biomedical Engineering*, 63(4), 797–804. https://doi.org/10.1109/TBME.2015.2474131 (≈ 700 citations)

Kim, H.-G., Cheon, E.-J., Bai, D.-S., Lee, Y. H., & Koo, B.-H. (2018). Stress and heart rate variability: A meta-analysis and review of the literature. *Psychiatry Investigation*, 15(3), 235–245. https://doi.org/10.30773/pi.2017.08.17 (≈ 2,000 citations)

Lakens, D. (2022). Sample size justification. *Collabra: Psychology*, 8(1), 33267. https://doi.org/10.1525/collabra.33267 (≈ 1,300 citations)

Lipponen, J. A., & Tarvainen, M. P. (2019). A robust algorithm for heart rate variability time series artefact correction using novel beat classification. *Journal of Medical Engineering & Technology*, 43(3), 173–181. https://doi.org/10.1080/03091902.2019.1640306 (≈ 400 citations)

Lovibond, P. F., & Lovibond, S. H. (1995). The structure of negative emotional states: Comparison of the Depression Anxiety Stress Scales (DASS) with the Beck Depression and Anxiety Inventories. *Behaviour Research and Therapy*, 33(3), 335–343. https://doi.org/10.1016/0005-7967(94)00075-U (≈ 13,000 citations)

Pagani, M., Lombardi, F., Guzzetti, S., Rimoldi, O., Furlan, R., Pizzinelli, P., Sandrone, G., Malfatto, G., Dell'Orto, S., Piccaluga, E., Turiel, M., Baselli, G., Cerutti, S., & Malliani, A. (1986). Power spectral analysis of heart rate and arterial pressure variabilities as a marker of sympatho-vagal interaction in man and conscious dog. *Circulation Research*, 59(2), 178–193. https://doi.org/10.1161/01.RES.59.2.178 (≈ 4,500 citations)

Porges, S. W. (2007). The polyvagal perspective. *Biological Psychology*, 74(2), 116–143. https://doi.org/10.1016/j.biopsycho.2006.06.009 (≈ 3,500 citations)

Schmidt, P., Reiss, A., Duerichen, R., Marberger, C., & Van Laerhoven, K. (2018). Introducing WESAD, a multimodal dataset for wearable stress and affect detection. In *Proceedings of the 20th ACM International Conference on Multimodal Interaction (ICMI '18)* (pp. 400–408). https://doi.org/10.1145/3242969.3242985 (≈ 1,100 citations)

Shaffer, F., & Ginsberg, J. P. (2017). An overview of heart rate variability metrics and norms. *Frontiers in Public Health*, 5, 258. https://doi.org/10.3389/fpubh.2017.00258 (≈ 4,800 citations)

Task Force of the European Society of Cardiology and the North American Society of Pacing and Electrophysiology. (1996). Heart rate variability: Standards of measurement, physiological interpretation, and clinical use. *Circulation*, 93(5), 1043–1065. https://doi.org/10.1161/01.CIR.93.5.1043 (≈ 24,000 citations)

Thayer, J. F., Åhs, F., Fredrikson, M., Sollers, J. J., & Wager, T. D. (2012). A meta-analysis of heart rate variability and neuroimaging studies: Implications for heart rate variability as a marker of stress and health. *Neuroscience & Biobehavioral Reviews*, 36(2), 747–756. https://doi.org/10.1016/j.neubiorev.2011.11.009 (≈ 3,400 citations)

Thayer, J. F., & Lane, R. D. (2000). A model of neurovisceral integration in emotion regulation and dysregulation. *Journal of Affective Disorders*, 61(3), 201–216. https://doi.org/10.1016/S0165-0327(00)00338-4 (≈ 3,200 citations)

---

*End of panel consultation record.*

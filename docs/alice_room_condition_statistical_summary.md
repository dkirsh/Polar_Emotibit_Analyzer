# Alice Room Condition Statistical Summary

This memo summarizes the current statistical interpretation of the Alice room-condition dataset in `alice_1`. It is written for poster preparation. The central question is whether room geometry or chromaticity affects physiological arousal, stress-related physiology, or self-reported affect.

## Experimental Coding

The Order & Affect condition dictionary maps the eight room-type letters onto a 4 x 2 design:

| Room type | Geometry | Chromaticity |
|---|---|---|
| A | Rectilinear | High |
| B | Rectilinear | Low |
| C | Curved-walls | High |
| D | Curved-walls | Low |
| E | Cloister-vault | High |
| F | Cloister-vault | Low |
| G | Quasi-geodesic | High |
| H | Quasi-geodesic | Low |

`room_number` is visit order. It is not a condition label. All condition-level statistics should be interpreted using `room_type` A-H, geometry, and chromaticity.

## Data Included

The current aggregate includes:

```text
32 subjects
251 room rows
```

`p021` is included only for Polar-derived room measures because its EmotiBit file is timestamp-mismatched. It contributes HR, HRV RMSSD, respiration/RSA, and self-report affect, but not EDA or full Stress V2.

`p024` and `p034` have partial room-type coverage:

```text
p024 missing C, D
p034 missing A, B, D
```

## Meaning Of The Main Measures

Stress V2 is an exploratory physiological composite. It is not a validated psychological stress scale. It combines HR, EDA tonic level, EDA phasic activity, HRV vagal deficit, LF_nu balance, SD1/SD2 rigidity, and RSA deficit where available. Higher values mean more stress-like physiological activation.

Unified arousal is Stress V2 re-expressed relative to baseline. It is useful for comparing activation above or below a participant's resting level.

HRV RMSSD is the root mean square of successive differences between heartbeats. It is a short-window heart-rate variability measure, largely reflecting vagal or parasympathetic flexibility. Lower RMSSD usually suggests reduced vagal regulation.

RSA amplitude is respiratory sinus arrhythmia amplitude: the extent to which heart rate rises and falls with breathing. It is another vagal regulation index. Lower RSA amplitude usually suggests weaker parasympathetic modulation, assuming the respiration proxy is reliable.

Self-report valence and self-report arousal come from the Order & Affect files. Valence should not be inferred from HR or EDA.

## What FDR Correction Means

FDR means false discovery rate. It is needed because this analysis tests many possible effects:

```text
8 room types produce 28 pairwise room comparisons per measure.
8 outcome measures produce 224 room-pair-by-measure tests.
```

At an uncorrected threshold of `p < .05`, some apparently significant results are expected by chance. Benjamini-Hochberg FDR correction asks whether a result remains credible after accounting for the number of tests performed.

Plainly:

```text
Uncorrected p-value:
Would this pair look this different by chance if this were the only test?

FDR-corrected p-value:
Would I still trust this result after considering all the tests I ran?
```

In this dataset, several effects are suggestive before correction, but no room pair, geometry effect, or chromaticity effect survives FDR correction.

## Room-Type Results

For Stress V2 by room type, there is no significant room-pair difference.

```text
28 room-type pairs tested
0 significant after FDR correction
0 significant even before correction for Stress V2
```

Current Stress V2 descriptive order, low to high:

```text
D  0.4235
E  0.4286
B  0.4297
F  0.4344
G  0.4346
C  0.4388
A  0.4414
H  0.4526
```

These differences are small and should be treated as descriptive only.

Across all tested measures, no room pair survives FDR correction. The strongest uncorrected room-pair signals are:

| Measure | Comparison | Direction | Uncorrected p | FDR q |
|---|---:|---|---:|---:|
| HR mean | A vs G | G lower than A by about 3.0 bpm | 0.0035 | 0.0988 within HR |
| HR mean | A vs E | E lower than A by about 2.3 bpm | 0.0078 | 0.1090 within HR |
| EDA mean | G vs H | H lower than G by about 0.30 uS | 0.0099 | 0.2782 within EDA |
| HR mean | A vs B | B lower than A by about 1.9 bpm | 0.0337 | 0.3145 within HR |
| HR mean | D vs G | G lower than D by about 2.0 bpm | 0.0457 | 0.3196 within HR |

These are exploratory only.

## Geometry Main Effects

Geometry was tested by averaging each subject's High and Low chromaticity rooms within each geometry:

```text
Rectilinear = mean(A, B)
Curved-walls = mean(C, D)
Cloister-vault = mean(E, F)
Quasi-geodesic = mean(G, H)
```

The strongest geometry signal was HR:

```text
Rectilinear       98.09 bpm
Curved-walls      98.12 bpm
Cloister-vault    96.90 bpm
Quasi-geodesic    96.33 bpm

Repeated-measures ANOVA p = 0.0307
Friedman p = 0.1540
FDR q = 0.2458
```

This is not a corrected significant result. It is best described as a weak exploratory hint that quasi-geodesic and cloister-vault geometry may be associated with slightly lower heart rate than rectilinear and curved-wall geometry.

Geometry did not show reliable effects on Stress V2, unified arousal, EDA, HRV RMSSD, RSA, valence, or self-report arousal.

## Chromaticity Main Effects

Chromaticity was tested by averaging all High rooms and all Low rooms for each subject:

```text
High = mean(A, C, E, G)
Low = mean(B, D, F, H)
```

Chromaticity showed no meaningful effect:

```text
Stress V2 High vs Low: p = 0.807
HR High vs Low:        p = 0.383
EDA High vs Low:       p = 0.910
Valence High vs Low:   p = 0.743
Arousal High vs Low:   p = 0.610
```

The present data do not support a claim that high versus low chromatic intensity changed physiology or affect.

## Arousal Results

There is no significant arousal effect by room type, geometry, or chromaticity.

Physiological arousal:

```text
By geometry: p = 0.947
By chromaticity: p = 0.849
By room type A-H: not significant
```

Self-report arousal:

```text
By geometry: p = 0.603
By chromaticity: p = 0.610
By room type A-H: p = 0.573
```

Thus, the data do not show that room geometry or color reliably changed arousal.

## Affect Results

Self-report valence was flat across room types:

```text
A 5.43
B 5.60
C 5.70
D 5.37
E 5.47
F 5.63
G 5.57
H 5.53

Repeated-measures ANOVA p = 0.780
Friedman p = 0.513
No FDR-significant pairwise differences
```

Self-report arousal was also flat:

```text
A 3.53
B 3.53
C 3.30
D 3.37
E 3.33
F 3.60
G 3.57
H 3.23

Repeated-measures ANOVA p = 0.573
Friedman p = 0.340
No FDR-significant pairwise differences
```

Factor-level affect tests:

```text
Valence by geometry:      p = 0.996
Valence by chromaticity:  p = 0.743
Arousal by geometry:      p = 0.603
Arousal by chromaticity:  p = 0.610
```

The affect data do not support effects of geometry or chromaticity.

## Best Poster Story

The strongest honest poster claim is:

> No room, geometry, or chromaticity effect survived FDR correction. The strongest exploratory pattern was a geometry-related reduction in heart rate, with quasi-geodesic and cloister-vault rooms showing slightly lower HR than rectilinear and curved-wall rooms. Chromaticity showed little evidence of an independent effect. Physiological and self-report arousal did not differ significantly by geometry, chromaticity, or room type. These results are hypothesis-generating rather than confirmatory.

Possible poster titles:

```text
Room Geometry Shows Weak Exploratory Associations With Heart Rate, While Chromaticity Shows No Reliable Main Effect
```

or:

```text
Exploratory Evidence That Room Geometry, More Than Color, May Modulate Cardiac Arousal
```

The first title is more statistically defensible.

## Recommended Charts

### 1. Geometry Main Effect Plot

Show four point estimates or bars:

```text
Rectilinear
Curved-walls
Cloister-vault
Quasi-geodesic
```

Primary outcome: HR mean.

Use subject-level paired lines in the background if possible. This shows the within-subject design and makes the exploratory geometry pattern visible without overstating it.

### 2. Chromaticity Main Effect Plot

Show High versus Low chromaticity as paired subject dots.

Recommended outcomes:

```text
HR mean
Stress V2
Self-report arousal
Self-report valence
```

This plot will show the null result clearly.

### 3. 2 x 4 Factor Grid

Show the actual factorial structure:

```text
Columns: Rectilinear, Curved-walls, Cloister-vault, Quasi-geodesic
Rows: High chromaticity, Low chromaticity
Cells: HR mean or Stress V2
```

This is better than a simple A-H bar chart because it shows how the room letters decompose into geometry and chromaticity.

### 4. Room-Type Stress V2 Plot

Show A-H room types sorted from low to high Stress V2. Label it explicitly as descriptive. Do not imply significance.

### 5. Arousal Null Plot

Show physiological arousal index by geometry and chromaticity. This is useful because the null result is substantively important: the dataset does not support an arousal effect.

### 6. Affect Plot

Show self-report valence and self-report arousal by geometry and chromaticity. The flatness of these plots is informative and helps prevent a misleading physiological-only story.

### 7. Exploratory Pairwise Plot

If space allows, show only the strongest uncorrected comparisons:

```text
HR: A vs G
HR: A vs E
EDA: G vs H
```

Label clearly:

```text
Exploratory only; does not survive FDR correction.
```

## Interpretation For Poster Discussion

The most plausible follow-up hypothesis is about geometry, not color. The exploratory HR pattern suggests that quasi-geodesic and cloister-vault geometries may be associated with lower cardiac activation. However, because the effect does not survive FDR correction and does not appear robustly in arousal, Stress V2, or affect ratings, it should be framed as a lead for future study rather than a confirmed result.

The chromaticity manipulation does not show evidence of an independent main effect in this dataset. If color has an effect, it is either smaller than this design can detect, masked by individual differences, dependent on interaction with geometry, or not captured by these physiological and affect measures.

The affect ratings are notably flat. That suggests either the rooms did not produce conscious affective differences, the SAM ratings were insensitive to these manipulations, or the physiological differences, if present, were below the threshold of conscious report.

## Bottom Line

The poster should emphasize restraint:

```text
Confirmed result:
No corrected significant effects of room type, geometry, or chromaticity.

Exploratory suggestion:
Geometry may influence HR, with lower HR in quasi-geodesic and cloister-vault rooms.

Not supported:
Reliable arousal differences, reliable Stress V2 differences, reliable chromaticity effects, or reliable self-report affect effects.
```


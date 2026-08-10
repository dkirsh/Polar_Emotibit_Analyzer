# Re-identifying respiratory stress patterns from RespInPeace output

*Script: `scripts/resp_patterns_respinpeace.py`. Outputs in
`outputs/resp_patterns_respinpeace/` and the Cleaned folder.*

## What changed
Instead of ad-hoc force peak-detection, breaths are now produced by the
**RespInPeace engine** (`rip.Resp`): ALS baseline removal, prominence-based
cycle detection, and its **dedicated breath-hold detector** (`resp.holds`). The
seven patterns are classified on top of that output. Apnea is now the real
detected holds, not a crude duration threshold.

**Run it on the full-resolution `.xlsx`, not the cleaned `.csv`.** The cleaned
CSV timestamps are quantized to whole seconds (10 rows all stamped `…:27`), which
destroys sub-second breath timing and makes *any* cycle detector over-segment.
The `.xlsx` has millisecond timestamps (`…:26.584, .674, .763`). Switching to the
xlsx brought breath counts down toward physiologic.

## Result (RespInPeace, full-resolution xlsx, 16 subjects)
- **Real breath-holds detected: 3,327 hold-containing breaths** (the crude
  detector found 0). This is the clearest win from RespInPeace.
- Per-pattern totals by condition (`table_pattern_totals_matrix_RIP.csv`):

| pattern | plants | no_plants | stressor |
|---|---|---|---|
| tachypnea | 1493 | 1505 | 1618 |
| ie_shift | 317 | 314 | 408 |
| inverted_ie | 172 | 152 | 188 |
| shallow | 320 | 294 | 242 |
| irregular | 1640 | 1668 | 1514 |
| sigh | 231 | 175 | 190 |
| apnea (holds) | 1155 | 1173 | 999 |

- Overall stress rate per 100 breaths: plants 94.1, no_plants 93.5, stressor 93.7.
- **Significance: Friedman χ²(2)=0.13, p=0.94 — still no condition difference;**
  all pairwise Wilcoxon n.s.

## Honest interpretation
1. **RespInPeace is the better engine and should be wired in** — it adds real
   hold/apnea detection and a principled baseline + cycle detector. Run it on the
   xlsx (or the raw belt stream), never the second-quantized CSV.
2. **Better breath detection did not make the categorical pattern scale
   discriminate.** The rate still saturates (~94/100) because `tachypnea`,
   `irregular`, and `apnea` together flag almost every breath at current
   thresholds, and the holds detector flags ~40% of breaths with default
   sensitivity. The thresholds (and the hold detector's prominence/duration
   parameters) need recalibration for this belt before the scale is useful.
3. **The discriminating respiratory signal remains the continuous rate** (faster
   under the stressor), not the categorical pattern counts.

## Are there more than seven patterns?
The seven are the analyzer's curated set. The dysfunctional-breathing /
respiratory-stress literature recognizes more, and several are detectable from a
single belt (others need extra signals):
- **Frequent / excessive sighing** — the *rate* of sighs (a strong anxiety
  marker), distinct from the single-sigh flag.
- **Periodic / cyclic breathing** — waxing–waning amplitude (Cheyne-Stokes-like).
- **Sustained hyperventilation** and **hypoventilation / bradypnea** — episodes,
  not single breaths.
- **Breath-stacking / incomplete exhalation** — a rising end-expiratory baseline.
- **Air hunger** — clusters of deep recovery breaths.
- **Thoracic-dominant / paradoxical breathing** — needs a *second* belt
  (rib-cage vs abdomen); not recoverable from one belt.
- RespInPeace also natively flags **breath-holds** (now used) and can flag
  **laughter / speech overlap** (artifacts to exclude).

So yes — more than seven are recognizable. A sensible next set to add (single
belt): sigh-rate, periodic breathing, sustained hyper/hypoventilation, and
breath-stacking, with paradoxical breathing deferred until a two-belt montage is
available.

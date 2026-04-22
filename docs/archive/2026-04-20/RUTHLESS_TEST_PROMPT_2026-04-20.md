# Ruthless test prompt — Polar-EmotiBit Analyzer (2026-04-20)

*Date*: 2026-04-20
*Requested by*: DK
*Executor*: Codex (GPT-5.x) with terminal + GitHub + OSF.io fetch access
*Target*: `/Users/davidusa/REPOS/Polar_Emotibit_Analyzer` at its current tip
*Expected output*: a verdict (CLEAN / CLEANED / BLOCKED) and a status note at `docs/RUTHLESS_TEST_STATUS_2026-04-20.md`, plus any fix commits landed under Codex authorship
*Companion docs*: `docs/INTEGRATION_PLAN_WITH_SIBLING_REPO_2026-04-20.md`, `docs/GUI_SCOPE_FILE_ONLY_2026-04-20.md`, `docs/POLAR_H10_REFERENCE_DATA_AND_PAPER_2026-04-20.md`, `docs/THREE_GROUP_RESULTS_ARCHITECTURE_2026-04-20.md`, `docs/EXECUTION_LOG_2026-04-20.md`

---

## Why this exists

CW executed the integration plan today: lifted the six missing modules from the sibling `emotibit_polar_data_system` repo, wrote a minimum FastAPI surface with eight endpoints, rewrote the frontend around a two-view file-only scope with a three-group results architecture (Necessary Science · Diagnostic · Question-Driven) plus chain-navigated detail pages for fifteen analytics, and delivered a library-free SVG renderer so the repo works without a chart-library `npm install`. The integration tests run 12/12 green on synthetic data. What this brief does is apply the same ruthless-prompt methodology that produced the Chung et al. test plan against the delivered code on real data — the Chung, Chopin, Karadayi & Grèzes (2026) OSF WYM3S dataset is the positive-case smoke test the integration plan names explicitly. The goal is not polite review. The goal is to find real problems against a real-world dataset before the tool is used in a 160sp lab session.

## The one hard rule

**Do not modify any file under `data/samples/` after fetching.** The fetched datasets are the reference truth; mutating them in place would destroy the reproducibility of the smoke test. All column-renaming and schema-conversion work belongs in `scripts/chung2026_to_polar_schema.py` and writes new files, not edits existing ones. Any apparent need to modify fetched data is a signal that the conversion script is wrong — fix the script, not the data.

## Ground rules

1. **Commit attribution**: `--author="Codex <codex@openai.com>"` on every fix commit. Subject lines lead with `Polar-Emotibit test probe N:`.
2. **No destructive ops** without DK's explicit OK: no `rm -rf`, `git reset --hard`, `git push --force`, or sudo operations outside Homebrew installs needed by pytest/npm.
3. **Run the numbers yourself, don't trust my docstrings.** If a module claims "per Task Force 1996 the VLF band requires ≥ 300 s" and the test harness feeds it a 240-second recording, verify that the pipeline returns `None` for VLF rather than a computed number. Same for every other documented scientific guardrail.
4. **Cite the paper when you cite the fix.** Scientific commits carry a reference; the reference goes in the commit message body.
5. **Stop and ask DK** for any finding that involves a scope or scientific interpretation decision: e.g., "the stress composite weights 0.35/0.35/0.20/0.10 are arbitrary and unvalidated" is a DK question, not a Codex fix.

## Pre-flight — what you should see before probe 1

From a clean `git status` in `/Users/davidusa/REPOS/Polar_Emotibit_Analyzer`:

```bash
cd /Users/davidusa/REPOS/Polar_Emotibit_Analyzer
ls backend/app/services/processing/   # expect: clean.py, drift.py, features.py,
                                      # pipeline.py, sync.py, stress.py, sync_qc.py,
                                      # extended_analytics.py, benchmark.py,
                                      # kubios_benchmark.py, statistics.py
ls backend/app/schemas/               # expect: analysis.py
ls backend/app/models/                # expect: signals.py
ls backend/app/services/ai/           # expect: adapters.py
ls backend/app/services/reporting/    # expect: report_builder.py
ls backend/app/api/v1/routes/         # expect: analysis.py, validate.py
ls frontend/src/pages/                # expect: StartPage.tsx, ResultsCoverPage.tsx,
                                      # GroupPage.tsx, AnalyticDetailPage.tsx
ls frontend/src/analytics/            # expect: catalog.ts, ChartRenderer.tsx
```

If any of those are missing, stop and tell DK the integration plan did not land as documented.

---

## Probe 1 — Backend imports + pytest

```bash
cd /Users/davidusa/REPOS/Polar_Emotibit_Analyzer/backend
python3 -m venv .venv && source .venv/bin/activate
pip install -e .[dev]
python3 -c "from app.services.processing import pipeline; print('imports OK')"
python3 -m pytest tests -q
```

**Expected:** `imports OK`; `12 passed, 1 warning`. Any red is a Probe-1 finding.

**Look specifically for**: the `DeprecationWarning: 'HTTP_422_UNPROCESSABLE_ENTITY' is deprecated` warning that is benign; anything else in the warning stream is worth treating as a finding.

---

## Probe 2 — End-to-end synthetic pipeline

```bash
cd /Users/davidusa/REPOS/Polar_Emotibit_Analyzer/backend
python3 -c "
from app.services.ingestion.synthetic import generate_synthetic_session
from app.services.processing.pipeline import run_analysis
em, pol = generate_synthetic_session(seconds=360)
r = run_analysis(em, pol)
assert r.sync_qc_gate == 'go', r.sync_qc_gate
assert r.feature_summary.rmssd_ms > 0
assert r.feature_summary.lf_ms2 is not None
assert r.feature_summary.hf_ms2 is not None
print('OK sync=%s rmssd=%.2f lf=%.2f hf=%.2f' % (r.sync_qc_score, r.feature_summary.rmssd_ms, r.feature_summary.lf_ms2, r.feature_summary.hf_ms2))
"
```

**Expected:** `OK sync=99.2 rmssd=~15 lf=~20 hf=~40`. Materially different numbers on a fixed-seed synthetic generator indicate a pipeline regression.

**Bug to watch for:** `generate_synthetic_session(seconds < 120)` crashes. Confirm this is still the case and land a fix that makes the motion-burst injection length-aware (not a `max(seconds, 120)` caller-side workaround — a real fix inside `synthetic.py`).

---

## Probe 3 — All eight API endpoints

Start the server:

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 &
sleep 3
```

Run this script and verify each assertion:

```bash
python3 -c "
import requests, tempfile
from io import StringIO
from app.services.ingestion.synthetic import generate_synthetic_session
em, pol = generate_synthetic_session(seconds=180)
em_bytes = em.to_csv(index=False).encode()
pol_bytes = pol.to_csv(index=False).encode()

BASE = 'http://127.0.0.1:8000'

r = requests.get(f'{BASE}/health'); assert r.status_code == 200, r.text
r = requests.post(f'{BASE}/api/v1/validate/csv/emotibit', files={'file': ('e.csv', em_bytes, 'text/csv')}); assert r.status_code == 200
assert r.json()['has_accelerometer'] is True, r.json()
r = requests.post(f'{BASE}/api/v1/validate/csv/polar', files={'file': ('p.csv', pol_bytes, 'text/csv')}); assert r.status_code == 200
r = requests.post(f'{BASE}/api/v1/validate/csv/markers', files={'file': ('m.csv', b'session_id,event_code,utc_ms\\nX,recording_start,0\\n', 'text/csv')}); assert r.status_code == 200

# Analyze
r = requests.post(
    f'{BASE}/api/v1/analyze',
    files={'emotibit_file': ('e.csv', em_bytes, 'text/csv'),
           'polar_file': ('p.csv', pol_bytes, 'text/csv')},
    data={'session_id':'CDX01','subject_id':'P','study_id':'S','session_date':'2026-04-20','operator':'Codex'})
assert r.status_code == 200, r.text
assert r.json()['sync_qc_gate'] == 'go'

# List + detail
r = requests.get(f'{BASE}/api/v1/sessions'); assert any(s['session_id'] == 'CDX01' for s in r.json())
r = requests.get(f'{BASE}/api/v1/sessions/CDX01'); assert r.status_code == 200
assert 'extended' in r.json() and r.json()['extended'] is not None
e = r.json()['extended']
assert 'stress_decomposition' in e and len(e['stress_decomposition']['components']) == 4
assert 'windowed' in e and len(e['windowed']['t_s']) > 0
assert 'psd' in e and len(e['psd']['frequencies_hz']) > 10
assert 'rr_series_ms' in e and len(e['rr_series_ms']) > 10
assert 'cleaned_timeseries' in e and len(e['cleaned_timeseries']) > 10
assert 'inference' in e and e['inference'] is not None
print('ALL 8 endpoints OK; extended bundle complete')
"
```

**Expected:** `ALL 8 endpoints OK`.

**Look for:** any field in the `extended` bundle that is empty on a 180-second recording but should not be (except VLF, which is correctly `None` below 300 s); any endpoint returning 500; any CORS preflight failure from `http://localhost:5173`.

---

## Probe 4 — Frontend build + typecheck

```bash
cd /Users/davidusa/REPOS/Polar_Emotibit_Analyzer/frontend
npm install
npm run build
```

**Expected:** `tsc --noEmit` clean, `vite build` produces `dist/` without error.

**Specifically audit:** any TypeScript unused-locals or unused-parameters warnings; the `StoredSession.extended` type must match the backend shape (test by running `curl /api/v1/sessions/...` and comparing fields to the TS type); any React `key` warnings in the browser console when rendering analytic detail pages.

---

## Probe 5 — Real-data smoke test against Chung et al. (2026) OSF WYM3S

This is the probe. The other four establish that the tool runs; this one establishes that it produces the right numbers on real-world data.

```bash
pip install osfclient --break-system-packages
cd /Users/davidusa/REPOS/Polar_Emotibit_Analyzer/data/samples
mkdir -p chung2026 && cd chung2026
osf -p wym3s list | head -40      # inspect folder layout
osf -p wym3s clone .              # may be 100s of MB; let it run

# Pick ONE dyad folder. The archive's layout varies per dyad; inspect.
find . -name "*.csv" | head -20
# Identify the RR-interval / IBI file for participant 1 of dyad 1.
# Typical names: P1_ibi.csv, d1_p1_rri.csv, etc.

cd /Users/davidusa/REPOS/Polar_Emotibit_Analyzer
python3 scripts/chung2026_to_polar_schema.py \
    --ibi-file data/samples/chung2026/<path-you-found>/<ibi-file>.csv \
    --out data/samples/polar_sample_01.csv

# Inspect the output; expect ~ 1000-4000 rows, hr_bpm in 50-120 range.
head data/samples/polar_sample_01.csv
wc -l data/samples/polar_sample_01.csv
```

Now run the pipeline. **Chung et al. report Pearson r > 0.99 between the Polar H10 and a gold-standard ECG**; our HR computation on their RR series must reproduce their published per-participant HR to within ≤ 1 bpm mean absolute error or there is a pipeline bug:

```bash
# Use the synthetic EmotiBit as a stand-in since the WYM3S dataset does
# not include EmotiBit recordings. The sync-QC gate will likely fail
# because the two sources were not collected together; that is
# EXPECTED and not a Polar pipeline bug.
python3 -c "
from app.services.ingestion.synthetic import generate_synthetic_session
em, _ = generate_synthetic_session(seconds=600)
em.to_csv('data/samples/emotibit_stand_in.csv', index=False)
"

# POST through /analyze (server must be running from probe 3)
curl -s -X POST http://127.0.0.1:8000/api/v1/analyze \
    -F 'emotibit_file=@data/samples/emotibit_stand_in.csv' \
    -F 'polar_file=@data/samples/polar_sample_01.csv' \
    -F 'session_id=CHUNG_P01' \
    -F 'subject_id=P01' \
    -F 'study_id=CHUNG2026' \
    -F 'session_date=2026-01-28' \
    -F 'operator=Codex' \
    | python3 -m json.tool | head -60
```

**Record in the status note:**

- Participant path (which dyad, which ibi file).
- Number of beats in the Polar sample.
- Our computed `mean_hr_bpm`, `rmssd_ms`, `sdnn_ms`.
- Our `sync_qc_gate` — expected `no_go` given the mismatched EmotiBit stand-in.
- Whether `rr_source` is `native_polar` (it must be, since Chung et al. ship IBI).

**Positive-case verification:** compare the computed `mean_hr_bpm` against the Chung et al. per-participant published mean HR (from the paper's supplementary tables). A discrepancy larger than 1 bpm is a **Probe-5 finding** and a blocker for release; the paper's whole claim is Pearson r > 0.99 against the gold standard, so our numbers on their data should be within 1 bpm of their numbers.

**Bonus — repeat with two more participants** to establish that the mean-HR reproduction is not a coincidence. Commit the three results as `docs/SAMPLE_DATA_SMOKE_TEST_2026-04-20.md` with a small table.

---

## Probe 6 — Three-group architecture rendering

Start the Vite dev server:

```bash
cd /Users/davidusa/REPOS/Polar_Emotibit_Analyzer/frontend
npm run dev &
sleep 5
# open http://localhost:5173 in a real browser (Cypress or Playwright
# if you want an automated pass; manual walk is fine for the first cut)
```

Run this walk. For each step, record PASS / FAIL with a one-line note:

1. `http://localhost:5173/` — the StartPage renders. Topbar shows "Polar-EmotiBit Analyzer" + two links. Left panel has six metadata fields. Right panel has three drop zones.
2. Type a session ID. Drop two synthetic CSVs (generate via `generate_synthetic_session` then save). Each drop zone shows green validation with row count + accel/RR note.
3. Submit button is disabled until both required files validate green. Click Submit. Loading overlay appears. Navigation to `/results/<id>` follows.
4. Results cover page renders. Session-identity bar at top shows the correct subject/date/operator. Three large cards render in teal/amber/blue with icon, title, caption, count. Quality flags and non-diagnostic notice visible at bottom.
5. Click the Necessary Science card. Group page renders with five medium cards. Each card shows its order number, chart-kind tag, title, caption.
6. Click the first card (HR+EDA timeseries). Detail page renders with breadcrumb, title, caption, SVG chart, three interpretation blocks (What this shows / How to read it / Architectural meaning), references list, and prev/next chain at the bottom. `next` points to "Time-domain HRV".
7. Click `next`. Arrives at the HRV summary table. Verify the cell values match the response's `feature_summary`.
8. Walk through all five Necessary Science charts via the `next` button. None should throw a console error.
9. Return to the cover. Click Diagnostic. Five slightly smaller cards render.
10. Walk the Diagnostic group via `next`. The band-duration gauge is the last one.
11. Return to cover. Click Question-Driven. A two-section list renders: Science (teal) with 6 rows, Diagnostics (amber) with 4 rows. Each row shows its research question as the primary headline.
12. Click one Science question. The detail page carries an uppercase eyebrow with the research question above the title.
13. Verify: zero hardcoded numeric literals appear anywhere in the UI. Every cell in the HRV table, every chart datum, every statistic reads from the API response.
14. Resize the browser to 480 px wide. Confirm cards collapse to one column and the drop zones remain usable. No horizontal scroll on main content.
15. Open the analysis JSON download from view 2. Confirm it includes the `extended` bundle with all nine data streams.

---

## Probe 7 — Writer-voice text quality

Open `frontend/src/analytics/catalog.ts`. For each of the fifteen entries, verify:

- `title` is sentence-case, not Title Case.
- `caption` is a single sentence.
- `whatItShows` is 80–140 words.
- `howToRead` is 50–100 words.
- `architecturalMeaning` is 80–140 words AND relates the measure to cognitive-neuroscience-of-architecture dependent variables (stress, attention, arousal, recovery) AND to canonical built-environment manipulations (noise, light, compression, daylight, crowding, thermal). A paragraph that only describes the measure without naming the architectural context does not pass this probe.
- `references` has at least one APA entry with a DOI for any Necessary Science or Science-category analytic; Diagnostic and Diagnostics-category analytics may have fewer or no references.
- `caveats` is present for any analytic whose literature includes a notable critique (LF/HF ratio per Billman 2013; stress composite per Healey & Picard 2005 validation gap).

**Expected finding count:** 0–3 places where the architectural-meaning paragraph drifts away from the architecture frame. Land a fix with the rewrite.

---

## Probe 8 — Scientific honesty audit

Re-verify each V2.1-repair claim against the lifted code. For each block below, run the test and record PASS/FAIL:

**8a. Welch vs periodogram.** `compute_hrv_frequency_features` must call `scipy.signal.welch`, not `np.fft.rfft`. Confirm by `grep -n 'welch\|rfft' backend/app/services/processing/features.py`.

**8b. Per-band minimum duration enforcement.** Feed the pipeline a 90-second synthetic pair. Verify: `lf_ms2` is not None but `hf_ms2` is the only band populated (LF requires 120 s, VLF requires 300 s). Feed a 45-second pair. Verify all three bands return None.

**8c. t-distribution for CI.** Verify `statistics._mean_ci95` uses `scipy.stats.t.ppf(0.975, df=n-1)` and not a hardcoded `1.96`. Unit test: at n=10, σ=5, the margin must be 2.262 × σ/√10 ≈ 3.58, not 1.960 × σ/√10 ≈ 3.10.

**8d. ddof=1 consistency.** Grep for every `np.std` and `np.var` call across the backend. Every one must carry `ddof=1` or be paired with a comment explaining why population variance is correct at that site.

**8e. Benjamini-Hochberg FDR.** `compute_inference_summary` must return both `hr_trend_pvalue_raw` and `hr_trend_pvalue` with the latter FDR-adjusted. Confirm by running with n=2 tests and checking the adjusted p is `min(1.0, raw_p * n / rank)`.

**8f. Motion threshold is absolute.** `clean._apply_motion_filter` must use `threshold_g` (default 0.3), not `np.percentile`. Grep confirms.

**8g. Processing order: range → motion → winsorize.** Visual inspection of `clean.clean_signals`.

**8h. Xcorr-disabled repair.** `pipeline.run_analysis` should not invoke any cross-correlation of HR against EDA for clock alignment. `xcorr_offset_ms` in the response should always be 0.0 on current synthetic data.

Any failing audit is a Probe-8 finding and carries the paper citation in the commit message.

---

## Probe 9 — Cross-browser + accessibility spot-check

Open the results cover page in: (a) Chrome 132, (b) Safari 18, (c) Firefox 133. Confirm:

- Colour contrast is WCAG AA compliant in all three. The `#00C896` teal on `#141414` dark-grey must exceed 4.5:1 for normal text. Use the Chrome DevTools Lighthouse Accessibility audit; target score ≥ 95.
- Tab order is sensible on the StartPage (metadata fields → drop zones → submit button).
- Screen reader reads the session-identity bar as "Session X subject Y date Z" via the `aria-label` on the SVG charts.

Any WCAG violation that requires more than a CSS one-liner to fix is a DK decision, not a Codex fix.

---

## Probe 10 — Sibling-repo drift audit

The lifted modules should match their sibling sources byte-for-byte at the time of the lift. Run:

```bash
for f in app/schemas/analysis.py app/models/signals.py \
         app/services/ai/adapters.py \
         app/services/processing/sync.py \
         app/services/processing/stress.py \
         app/services/reporting/report_builder.py \
         app/services/processing/extended_analytics.py \
         app/core/config.py; do
  diff /Users/davidusa/REPOS/Polar_Emotibit_Analyzer/backend/$f \
       /Users/davidusa/REPOS/emotibit_polar_data_system/backend/$f \
    | head -20
  echo "--- $f ---"
done
```

**Expected:** all diffs empty. Any drift means either (a) the lift was incomplete, (b) the sibling has moved since the lift, or (c) a fix landed in one but not the other. If (b), decide whether to re-lift; if (c), commit the same fix to both.

---

## How to land fixes

Each fix is its own commit on `master`:

```bash
git add <files>
git -c user.name="Codex" -c user.email="codex@openai.com" \
    commit --author="Codex <codex@openai.com>" \
    -m "Polar-Emotibit test probe N: <one-line subject>" \
    -m "<paragraph explaining the bug and the fix; cite the paper>"
```

When all probes are clean, write `docs/RUTHLESS_TEST_STATUS_2026-04-20.md` with: probe-by-probe verdicts, commit hashes for any fixes, the Chung et al. participant-level HR reproduction table, any DK-decision items. Verdict: **CLEAN** / **CLEANED (N fixes)** / **BLOCKED (reason)**.

## What this test is not

- Not a full scientific validation of the stress composite. The composite is explicitly experimental (see `stress.py` docstring) and not psychometrically validated; that is a 90-day research task, not a test-probe.
- Not a performance benchmark. An on-the-box pipeline run should complete in ≤ 5 s for a 10-minute recording on an M1 Mac; times materially worse than that are findings, but cycle-time optimisation is not the primary concern.
- Not a device-integration test. The tool is file-only-post-hoc; BLE/USB/streaming work is explicitly out of scope per `docs/GUI_SCOPE_FILE_ONLY_2026-04-20.md`.

## References

Chung, V., Chopin, L., Karadayi, J., & Grèzes, J. (2026). Validity of the Polar H10 for continuous measures of heart rate and heart rate synchrony analysis. *Sensors, 26*(3), 855. https://doi.org/10.3390/s26030855 — OSF deposit https://doi.org/10.17605/OSF.IO/WYM3S. The ground-truth corpus for probe 5.

Cumming, G. (2014). The new statistics: Why and how. *Psychological Science, 25*(1), 7–29. https://doi.org/10.1177/0956797613504966 — why probe 8c checks for t-distribution CIs.

Task Force of the European Society of Cardiology and the North American Society of Pacing and Electrophysiology. (1996). Heart rate variability: Standards of measurement, physiological interpretation, and clinical use. *Circulation, 93*(5), 1043–1065. — the per-band minimum-duration thresholds probe 8b enforces.

Welch, P. D. (1967). The use of fast Fourier transform for the estimation of power spectra. *IEEE Trans. Audio Electroacoustics, 15*(2), 70–73. https://doi.org/10.1109/TAU.1967.1161901 — the PSD method probe 8a requires.

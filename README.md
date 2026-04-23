# Polar-EmotiBit Analyzer

A local desktop tool for synchronising Polar H10 heart-rate data with
EmotiBit electrodermal and motion data, computing HRV, EDA, stress,
and related physiological features, and presenting the results through
a browser-based dashboard of 24 analytics. Built for
cognitive-neuroscience-of-architecture research at UCSD COGS 160.

**This analyser runs on your own machine.** It is not a hosted web
service. You clone the repository, install the dependencies once,
and launch the backend and frontend from this repo. On macOS and
Linux there is a single launcher command; on Windows PowerShell, use
the two-terminal method below. Your browser then connects to
`http://localhost:5173` on your own machine. Your recording files
never leave your computer.

---

## Install and run (precise commands)

### Prerequisites

| Tool | Version | Install from |
|------|---------|--------------|
| Python | 3.10 or newer | https://www.python.org |
| Node.js | 18 or newer | https://nodejs.org |
| Git | any recent version | https://git-scm.com |

Verify each is present before proceeding:

```bash
python3 --version   # expect 3.10 or higher
node --version      # expect v18 or higher
git --version       # expect any version
```

### One-time setup

Run these commands from an empty directory where you want the repo
to live.

```bash
# 1. Clone the repo
git clone https://github.com/dkirsh/Polar_Emotibit_Analyzer.git
cd Polar_Emotibit_Analyzer

# 2. Install the backend (Python)
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[dev]"
cd ..

# 3. Install the frontend (Node)
cd frontend
npm install
cd ..

# 4. Verify the install worked
cd backend && source .venv/bin/activate && python -m pytest tests/ -q && cd ..
cd frontend && npx tsc --noEmit && cd ..
```

Expected results after step 4: pytest reports that all backend tests
passed, and TypeScript reports no errors. If either check fails, the
install did not complete. Do not proceed until both are clean. See
the **Troubleshooting** section below.

On Windows PowerShell the activation step differs:
`.venv\Scripts\Activate.ps1` replaces `source .venv/bin/activate`.
Also note that `run.sh` is a Unix shell launcher and assumes
`.venv/bin/...` paths. Windows users should use the two-terminal
method below, not `./run.sh`.

### Daily run

On macOS or Linux, from the repo root, one command:

```bash
./run.sh
```

This starts the FastAPI backend on `http://localhost:8000` and the
Vite frontend on `http://localhost:5173`. Open `http://localhost:5173`
in your browser. Press `Ctrl-C` in the terminal to stop both servers.

If you prefer to run the two servers in separate terminals (easier to
read the logs of each), open two terminal windows and run:

```bash
# Terminal 1 — backend (macOS/Linux)
cd backend
source .venv/bin/activate
python -m uvicorn app.main:app --reload --port 8000
```

```bash
# Terminal 2 — frontend (macOS/Linux or Windows)
cd frontend
npm run dev
```

Then open `http://localhost:5173`.

On Windows PowerShell, the backend terminal is:

```powershell
cd backend
.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --reload --port 8000
```

### Updating to a new version

When you `git pull` a new version, the backend dependencies may have
changed. Re-install once after every pull:

```bash
cd backend
source .venv/bin/activate
pip install -e ".[dev]"
cd ..
```

Frontend dependencies update the same way:

```bash
cd frontend
npm install
cd ..
```

Then start the app again using `./run.sh` on macOS/Linux or the
two-terminal method above on any platform. Skipping the reinstall
after a pull produces puzzling failures — typically a missing-module
import error the next time you run pytest or open the dashboard.

---

## How to use the analyser

### Step 1 — Prepare your data

You need two CSV files from a recording session:

| File | Source | Accepted columns |
|------|--------|------------------|
| Polar H10 CSV | Polar Sensor Logger or ECG export | Preferred: `timestamp_ms` or `timestamp_ns` plus one raw ECG column such as `ecg_uv`, `ecg_mv`, `ecg`, `raw_ecg`, `raw_ecg_uv`, or `voltage_uv`. Legacy beat-level input also works with `timestamp_ms` plus `hr_bpm`, with optional `rr_ms`. |
| EmotiBit CSV | EmotiBit Oscilloscope export | `timestamp_ms`, `eda_us`; optional `acc_x`, `acc_y`, `acc_z`, `resp_bpm` |

The preferred Polar path is the raw ECG trace. When that trace is
present, the app detects R peaks itself and computes beat timings,
`rr_ms`, and `hr_bpm` in-app. If you instead upload beat-level Polar
data with native `rr_ms`, the app preserves that directly. If you
upload only `hr_bpm`, the app derives approximate RR intervals from
BPM and marks the result as a lower-confidence fallback in the quality
flags. An optional `event_markers.csv` with columns `session_id`,
`event_code`, `utc_ms` and optional `note` can be uploaded alongside.

### Step 2 — Upload and analyse

1. Open the app in your browser (`http://localhost:5173`).
2. Fill in the session metadata (session ID, subject ID, study ID, date).
3. Drag-and-drop or browse your Polar and EmotiBit CSV files.
4. Click **Analyze**.
5. The pipeline runs end to end: piecewise linear drift correction,
   signal cleaning, HRV time-domain features, Poincaré nonlinear
   features, frequency-domain HRV with Task Force (1996) normalised
   units, EDA tonic and phasic decomposition, ECG-derived respiration
   with RSA amplitude, the v1 and v2 stress composites, and the
   Lipponen-Tarvainen (2019) ectopic correction as used by Kubios.

### Step 3 — Read the results

The results page presents twenty-four analytics organised into three
groups:

| Group | Count | Purpose |
|-------|-------|---------|
| Necessary Science | 6 | The charts a research-grade analysis must produce |
| Diagnostic | 5 | Data-quality checks — read these before trusting the science |
| Question-Driven | 13 | "Does this participant show X?" organised by research question |

Each analytic page carries four interpretation blocks: what the chart
shows, how to read it, what it means for the cognitive neuroscience
of architecture, and (where relevant) caveats and science rationale.
Jargon terms are annotated on first occurrence with a hover tooltip
carrying a one-line gloss; the full glossary has 35 entries and lives
at `frontend/src/analytics/glossary.ts`.

### Step 4 — Export the analysis

The results cover page has five download buttons, matching the Kubios
HRV Premium format set:

| Button | Format | Typical use |
|--------|--------|-------------|
| JSON | structured dump | pipeline-friendly for R or Python |
| CSV | flat (group, metric, value, unit) | Excel / quick re-analysis |
| XLSX | multi-sheet workbook | clinical or research colleague who lives in Excel |
| MAT | MATLAB struct | physiology labs and signal-processing courses |
| PDF | formatted report | paper appendix or lab notebook |

Every format carries the same underlying features in a layout
appropriate to its downstream reader. The endpoint serving them is
`GET /api/v1/sessions/{id}/export?format={csv|xlsx|mat|pdf}`.

---

## Troubleshooting

### `pytest` reports missing `reportlab` or `openpyxl`

You pulled a new version without reinstalling the backend
dependencies. Fix:

```bash
cd backend
source .venv/bin/activate
pip install -e ".[dev]"
```

Then re-run pytest and confirm that the backend suite is green.

### `./run.sh` immediately exits with "Python 3 not found"

Either Python 3 is not installed or it is not named `python3` on your
`$PATH`. On macOS, `brew install python@3.12` is the standard install.
On Windows, `python --version` (without the `3`) may be the right
command; run `py -3 --version` to be sure.

### The dashboard opens but says "Failed to fetch" on every API call

The backend is not running. Either the backend process died with an
error that scrolled past (check the first terminal for a Python
traceback) or the port is already in use by something else. Test the
backend independently with:

```bash
curl http://localhost:8000/health
# expect: {"ok":true,"version":"2.1.0","scope":"file-only post-hoc"}
```

If `curl` also fails, restart the backend with the Terminal-1 command
above and watch for the error.

### A `.venv` directory exists but pip complains about broken installs

Delete and recreate:

```bash
cd backend
rm -rf .venv
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[dev]"
```

---

## Repository layout

```
Polar_Emotibit_Analyzer/
├── README.md                       # This file
├── CHANGELOG.md                    # Version history
├── LICENSE
├── run.sh                          # Single-command launcher
├── backend/
│   ├── pyproject.toml              # Python dependencies
│   ├── app/
│   │   ├── main.py                 # FastAPI application
│   │   ├── api/v1/routes/          # Eight HTTP endpoints
│   │   ├── schemas/                # Pydantic request/response models
│   │   └── services/
│   │       ├── ingestion/          # CSV parsers, synthetic data
│   │       ├── processing/         # The analysis pipeline
│   │       ├── reporting/          # CSV / XLSX / MAT / PDF exporters
│   │       └── ai/                 # Non-diagnostic notice
│   └── tests/                      # Backend pytest suite
├── frontend/
│   ├── package.json
│   └── src/
│       ├── App.tsx                 # Router
│       ├── api.ts                  # Typed API client
│       ├── analytics/              # Catalog + glossary + charts
│       └── pages/                  # Upload, results, group, detail
├── scripts/                        # Utility scripts
├── data/samples/welltory/          # Real Polar H10 fixtures (CC0-1.0)
├── contracts/                      # Module-level contracts
└── docs/                           # Reference documents and audits
```

---

## Validation status

HR reproduction is validated within 1 bpm against Chung et al. (2026),
who compared the Polar H10 against a gold-standard Lead II ECG system.
Time-domain and Poincaré HRV features (RMSSD, SDNN, NN50, pNN50, SD1,
SD2, SD1/SD2 ratio, ellipse area) reproduce textbook-formula references
within 1 % on real Polar H10 data from the Welltory PPG dataset,
committed under `data/samples/welltory/`. Normalised-unit
frequency-domain features (LF_nu, HF_nu, total power, VLF/LF/HF %)
follow the Task Force (1996) definitions. Ectopic correction uses the
Lipponen-Tarvainen (2019) adaptive-threshold algorithm with
cubic-spline interpolation, the Kubios default. A paired Bland-Altman
comparison against Kubios HRV Premium's own output on identical
sessions is still pending.

See `docs/RUTHLESS_AUDIT_2026-04-21_CW.md` for the full
feature-by-feature parity comparison, `docs/FIX_PLAN_2026-04-21.md`
for the audit-driven work that landed, and `contracts/` for
module-level guarantees.

---

## The stress composite

The pipeline produces two experimental exploratory stress composites
alongside every analysis. Both return a value in [0, 1] with higher
values indicating greater estimated sympathetic activation. Neither is
psychometrically validated.

**v1** — five channels: HR, tonic EDA, phasic EDA, RMSSD-based vagal
protection, and RSA. Weights 0.25 / 0.25 / 0.15 / 0.15 / 0.20 in the
5-channel mode; 0.30 / 0.30 / 0.20 / 0.20 in the 4-channel fallback
when RSA is unavailable.

**v2** — seven channels: HR (0.15), tonic EDA (0.20), phasic EDA
(0.10), vagal composite combining RMSSD and pNN50 (0.15),
sympathovagal balance via LF_nu (0.20), Poincaré rigidity via
SD1/SD2 ratio (0.10), RSA (0.10). Absent channels (short session, no
RSA, no PPG) redistribute their weight equally across the present
channels.

Justification of the v2 weighting scheme by a five-expert panel
(Thayer, Shaffer, Tarvainen, Porges, Lakens) lives at
`docs/STRESS_COMPOSITE_V2_PANEL_JUSTIFICATION_2026-04-21.md`. Both
versions carry an `experimental, not psychometrically validated` flag
in the quality-flag stream. Use the scores for within-session relative
comparison only.

---

## API endpoints (for developers)

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/health` | Health check |
| `POST` | `/api/v1/analyze` | Run the full pipeline |
| `GET` | `/api/v1/sessions` | List recent sessions |
| `GET` | `/api/v1/sessions/{id}` | Get one session's full results |
| `GET` | `/api/v1/sessions/{id}/export?format=…` | Export as CSV, XLSX, MAT, or PDF |
| `POST` | `/api/v1/validate/csv/emotibit` | Validate EmotiBit CSV schema |
| `POST` | `/api/v1/validate/csv/polar` | Validate Polar CSV schema |
| `POST` | `/api/v1/validate/csv/markers` | Validate markers CSV |
| `POST` | `/api/v1/benchmark/kubios` | Bland-Altman vs Kubios export |

Every endpoint carries a typed OpenAPI response schema; visit
`http://localhost:8000/docs` while the backend is running to browse
them interactively.

---

## Running the tests

```bash
# Backend — pytest suite including real-data regression against Welltory
cd backend && source .venv/bin/activate && python -m pytest tests/ -q

# Frontend — TypeScript strict compile
cd frontend && npx tsc --noEmit

# Frontend — production build
cd frontend && npm run build
```

The real-data regression tests at
`backend/tests/test_real_data_audit.py` use the Welltory Polar H10
fixtures under `data/samples/welltory/` (CC0-1.0) to lock the HRV
feature pipeline against hand-computed reference values within 1 % on
every metric. They are the test-suite floor for any future change to
the HRV math.

---

## Non-diagnostic notice

This software is research output. It is not a medical device, has not
been cleared by any regulatory authority, and must not be used for
clinical diagnosis, triage, treatment planning, or any medical
decision. Outputs are intended for within-subject relative comparison
in research settings only. See
`contracts/NON_DIAGNOSTIC_CONTRACT_2026-04-22.md` for the full
statement.

---

## Key references

Chung, V., Chopin, L., Karadayi, J., & Grèzes, J. (2026). Validity of
the Polar H10 for continuous measures of heart rate and heart rate
synchrony analysis. *Sensors*, 26(3), 855.
https://doi.org/10.3390/s26030855

Lipponen, J. A., & Tarvainen, M. P. (2019). A robust algorithm for
heart rate variability time series artefact correction using novel
beat classification. *Journal of Medical Engineering & Technology*,
43(3), 173–181. https://doi.org/10.1080/03091902.2019.1640306

Schmidt, P., Reiss, A., Duerichen, R., Marberger, C., & Van Laerhoven,
K. (2018). Introducing WESAD, a multimodal dataset for wearable
stress and affect detection. *Proc. ICMI*, 400–408.
https://doi.org/10.1145/3242969.3242985

Shaffer, F., & Ginsberg, J. P. (2017). An overview of heart rate
variability metrics and norms. *Frontiers in Public Health*, 5, 258.
https://doi.org/10.3389/fpubh.2017.00258

Task Force of the European Society of Cardiology and the North
American Society of Pacing and Electrophysiology. (1996). Heart rate
variability. *Circulation*, 93(5), 1043–1065.
https://doi.org/10.1161/01.CIR.93.5.1043

Thayer, J. F., Åhs, F., Fredrikson, M., Sollers, J. J., & Wager, T. D.
(2012). A meta-analysis of heart rate variability and neuroimaging
studies. *Neuroscience & Biobehavioral Reviews*, 36(2), 747–756.
https://doi.org/10.1016/j.neubiorev.2011.11.009

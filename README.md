# Polar-EmotiBit Analyzer

A research-grade physiological data analysis tool for synchronizing Polar H10 heart-rate data with EmotiBit electrodermal/motion data, computing HRV, EDA, and stress features, and presenting results through an interactive browser-based dashboard with 24 science-writer-voice analytics.

Built for cognitive-neuroscience-of-architecture research.

**Validation status.** HR reproduction is validated within 1 bpm against Chung et al. (2026), who compared the Polar H10 against a gold-standard Lead II ECG system. Time-domain and Poincaré HRV features (RMSSD, SDNN, NN50, pNN50, SD1, SD2, SD1/SD2 ratio, ellipse area) reproduce textbook-formula references within 1 % on real Polar H10 data from the Welltory PPG dataset (committed under `data/samples/welltory/`). Normalised-unit frequency-domain features (LF_nu, HF_nu, total power, VLF/LF/HF %) follow the Task Force (1996) definitions; ectopic correction uses the Lipponen-Tarvainen (2019) adaptive-threshold algorithm with cubic-spline interpolation (the Kubios default). A paired Bland-Altman comparison against Kubios HRV Premium's own output on identical sessions is still pending. See `docs/RUTHLESS_AUDIT_2026-04-21_CW.md` for the full feature-by-feature parity comparison and `docs/FIX_PLAN_2026-04-21.md` for remaining work.

---

## Quick Start (students)

### Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Python | 3.12+ | [python.org](https://python.org) |
| Node.js | 18+ | [nodejs.org](https://nodejs.org) |
| Git | any | [git-scm.com](https://git-scm.com) |

### One-command launch

```bash
# 1. Clone the repo
git clone https://github.com/dkirsh/Polar_Emotibit_Analyzer.git
cd Polar_Emotibit_Analyzer

# 2. Run
./run.sh
```

This will:
- Create a Python virtual environment and install backend dependencies
- Install frontend npm packages
- Start the FastAPI backend on `http://localhost:8000`
- Start the Vite frontend on `http://localhost:5173`

**Open `http://localhost:5173` in your browser.**

Press `Ctrl-C` to stop both servers.

---

## How to use

### Step 1 — Prepare your data

You need two CSV files from a recording session:

| File | Source | Required columns |
|------|--------|-----------------|
| **Polar H10 CSV** | Polar Sensor Logger or ECG Export | `timestamp_ms`, `hr_bpm`, `rr_ms` |
| **EmotiBit CSV** | EmotiBit Oscilloscope export | `timestamp_ms`, `eda_us`, `acc_x`, `acc_y`, `acc_z` |

Optional: an `event_markers.csv` with columns `timestamp_ms` and `event_code`.

### Step 2 — Upload and analyze

1. Open the app in your browser (`http://localhost:5173`)
2. Fill in the session metadata (session ID, subject ID, study ID, date)
3. Drag-and-drop (or browse) your Polar and EmotiBit CSV files
4. Click **Analyze**
5. The pipeline will:
   - Synchronize the two device clocks (piecewise linear drift correction)
   - Clean signals (physiological range gating, motion artifact detection, winsorization)
   - Extract HRV features (RMSSD, SDNN, Welch PSD, LF/HF)
   - Extract EDA features (tonic SCL, phasic index)
   - Derive ECG-based respiration (RSA amplitude, breathing rate)
   - Compute the 5-channel stress composite
   - Generate all 21 analytics with full interpretation text

### Step 3 — Read the results

The results page presents analytics in three groups:

| Group | Count | Purpose |
|-------|-------|---------|
| **Necessary Science** | 6 | The charts a research-grade analysis must produce |
| **Diagnostic** | 5 | Data-quality checks — read these before trusting the science |
| **Question-Driven** | 11 | "Does this participant show X?" organized by research question |

Each analytic page includes:
- **What this chart shows** — plain-language description
- **How to read it** — interpretation guide with reference values
- **What it means for architecture** — how the measure relates to stress, arousal, attention, and recovery DVs in built-environment research
- **References** — APA citations for the underlying methods

### Step 4 — Export

Click the **Download JSON** button on the results page to export the full analysis (all features, windowed timeseries, stress decomposition) as a structured JSON file for further analysis in R, Python, or Excel.

---

## Repository structure

```
Polar_Emotibit_Analyzer/
├── run.sh                          # Single-command launcher
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI application
│   │   ├── api/v1/routes/          # API endpoints
│   │   ├── schemas/                # Pydantic response models
│   │   └── services/
│   │       ├── ingestion/          # CSV parsers, synthetic data
│   │       └── processing/         # The pipeline
│   │           ├── sync.py         # Device synchronization
│   │           ├── drift.py        # Piecewise drift correction
│   │           ├── clean.py        # Signal cleaning
│   │           ├── features.py     # HRV, EDA, EDR extraction
│   │           ├── stress.py       # 5-channel stress composite
│   │           ├── extended_analytics.py  # Windowed + spectral
│   │           ├── statistics.py   # CIs, effect sizes, FDR
│   │           └── benchmark.py    # Bland-Altman vs Kubios
│   ├── tests/                      # 12 pytest tests
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.tsx                 # Router
│   │   ├── api.ts                  # API client + types
│   │   ├── analytics/
│   │   │   ├── catalog.ts          # 21 analytics with interpretation text
│   │   │   └── ChartRenderer.tsx   # SVG chart renderers
│   │   ├── pages/
│   │   │   ├── StartPage.tsx       # Upload + metadata form
│   │   │   ├── ResultsCoverPage.tsx # Results overview
│   │   │   ├── GroupPage.tsx       # Analytics by group
│   │   │   └── AnalyticDetailPage.tsx # Individual analytic
│   │   └── styles.css              # Dark-mode design system
│   ├── package.json
│   └── tsconfig.json
├── scripts/
│   └── derive_stress_weights_wesad.py  # WESAD weight calibration
└── docs/
```

---

## The stress composite

The pipeline computes a 5-channel stress composite (V2.2):

```
stress = 0.25 × HR_norm + 0.25 × EDA_norm + 0.15 × phasic_norm
         + 0.15 × (1 − HRV_protection) + 0.20 × (1 − RSA_norm)
```

| Channel | What it captures | Weight |
|---------|-----------------|--------|
| HR | Cardiovascular demand | 0.25 |
| EDA tonic | Sustained sympathetic activation | 0.25 |
| EDA phasic | Stimulus-driven orienting responses | 0.15 |
| HRV deficit | Low vagal tone reserve (1 − RMSSD/80) | 0.15 |
| RSA deficit | Vagal withdrawal via respiratory proxy | 0.20 |

⚠️ **These weights are WESAD-informed heuristics, not empirically calibrated.** Run `scripts/derive_stress_weights_wesad.py` against the public WESAD dataset to derive data-backed weights. See the EDR respiration page (q-s-07) in the app for full instructions.

---

## API endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/v1/analyze` | Run the full pipeline |
| `GET` | `/api/v1/sessions` | List recent sessions |
| `GET` | `/api/v1/sessions/{id}` | Get one session's full results |
| `POST` | `/api/v1/validate/emotibit` | Validate EmotiBit CSV schema |
| `POST` | `/api/v1/validate/polar` | Validate Polar CSV schema |
| `POST` | `/api/v1/validate/markers` | Validate markers CSV |
| `POST` | `/api/v1/benchmark/kubios` | Bland-Altman vs Kubios export |
| `GET` | `/api/v1/health` | Health check |

---

## Running tests

```bash
# Backend (12 tests)
cd backend && source .venv/bin/activate && python -m pytest tests/ -v

# Frontend (build = type check)
cd frontend && npm run build
```

---

## Key references

- Chung, V., et al. (2026). Validity of the Polar H10 for continuous HR and HR synchrony. *Sensors*, 26, 855.
- Schmidt, P., et al. (2018). Introducing WESAD. *Proc. ICMI*, 400–408.
- Task Force ESC/NASPE (1996). Heart rate variability. *Circulation*, 93, 1043–1065.
- Berntson, G. G., et al. (1997). Heart rate variability: Origins, methods, and interpretive caveats. *Psychophysiology*, 34, 623–648.
- Healey, J. A., & Picard, R. W. (2005). Detecting stress during real-world driving. *IEEE TITS*, 6, 156–166.

# Polar-EmotiBit Analyzer Backend

FastAPI backend for the Polar-EmotiBit Analyzer.

The full user guide is in the repository root `README.md`. This local
README exists so Python packaging tools can install the backend from the
`backend/` directory without trying to read files outside the package
root.

## Install

From the repository root:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[dev]"
python -m pytest -q
```

## Run

```bash
cd backend
source .venv/bin/activate
python -m uvicorn app.main:app --reload --port 8000
```

The frontend development server proxies `/api` requests to this backend.

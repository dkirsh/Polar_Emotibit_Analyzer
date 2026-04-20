# Physiological Post-Hoc Analyzer

A lightweight, rigorous post-hoc synchronization and feature extraction engine designed specifically for aligning physiological data (EmotiBit EDA/Accelerometry and Polar H10 Heart Rate).

This repository was specifically constructed to serve as an honest, purely file-driven mathematical engine that guarantees scientific parity with Kubios via built-in HRV/EDA statistical validators.

## Repository Layout
- `backend/app/services/processing/`: The core synchronization scripts (`sync_qc.py`), drift calculators, and Kubios-parity feature extractors.
- `backend/app/db/`: Simplified SQLite models to securely track local session processing states.
- `frontend/`: A React/Vite web application offering an explicit workflow (Project Setup -> Drag-And-Drop File Import -> Visual QC -> Metric Extraction).
- `docs/`: Critical operational standards.

## Core Operations

### 1. Data Ingestion
This system is NOT a live streaming platform. It operates solely against robust, locally saved `.csv` outputs.

Prior to use, all data components (Raw Polar H10 CSV, raw EmotiBit CSV, Consent PDFs, and UTC Event logs) MUST be securely archived in a structured environment like Google Drive. See the `docs/GDOCS_SOURCE_MANAGEMENT.md` for specific formatting instructions on preserving your ground truth.

### 2. Processing Flow
1. Load your `session_id`.
2. Provide the hardware CSVs.
3. Supply an `event_markers.csv` (or input start/stop UTC times manually).
4. The system determines overlap, checks monotonic gaps, applies linear drift corrections, and merges the data.
5. EmotiBit accelerometry is used to gate out motion artifacts from HR measurements.
6. The exact Kubios metrics (`RMSSD_ms`, `SDNN_ms`, `mean_HR_bpm`, `Stress_Score`) are computed across your requested event windows.

#!/usr/bin/env python3
"""Write analyzer-assimilable cleaned files per subject into
Cleaned_for_David_by_Claude (inside the data folder). Reuses the cohort loaders.

Per subject: {sub}_emotibit.csv (timestamp_ms,eda_us), {sub}_polar.csv
(timestamp_ms,rr_ms from BI, range-filtered), {sub}_markers.csv
(session_id,event_code,utc_ms — condition onset/offset), {sub}_vernier.csv
(timestamp_unix,force,RR,event_marker,condition).
"""
from __future__ import annotations
import importlib.util, sys
from pathlib import Path
import numpy as np, pandas as pd

spec = importlib.util.spec_from_file_location("ca", str(Path(__file__).parent / "cohort_plant_analysis.py"))
ca = importlib.util.module_from_spec(spec); sys.argv = ["x"]; spec.loader.exec_module(ca)

ROOT = ca.DATA_ROOT
CLEAN = ROOT / "Cleaned_for_David_by_Claude"
CLEAN.mkdir(parents=True, exist_ok=True)

written = []
for s in ca.discover_subjects():
    d = ROOT / s
    bio_path = sorted(d.rglob("*biometrics.csv"))[0]
    vp = [p for p in d.rglob("*clean_respiratory_data*.csv") if "markers" not in p.name.lower()]
    ver_path = vp[0] if vp else sorted(d.rglob("*clean_respiratory_data*_markers.csv"))[0]
    bio = ca.load_biometrics(bio_path); ver = ca.load_vernier(ver_path)

    # emotibit EDA (range-filtered)
    e = bio[["t_ms", "eda_us"]].dropna()
    e = e[(e.eda_us >= ca.EDA_MIN) & (e.eda_us <= ca.EDA_MAX)]
    e.rename(columns={"t_ms": "timestamp_ms"}).assign(timestamp_ms=lambda x: x.timestamp_ms.astype("int64")).to_csv(CLEAN / f"{s}_emotibit.csv", index=False)

    # polar/heart from BI (range-filtered) — flagged unreliable in README
    h = bio[["t_ms", "bi_ms"]].dropna()
    h = h[(h.bi_ms >= ca.RR_MIN) & (h.bi_ms <= ca.RR_MAX)].rename(columns={"t_ms": "timestamp_ms", "bi_ms": "rr_ms"})
    h.assign(timestamp_ms=lambda x: x.timestamp_ms.astype("int64")).to_csv(CLEAN / f"{s}_polar.csv", index=False)

    # markers: condition onset/offset windows
    wins = ca.condition_windows(ver)
    if not wins[ca.COND_PLANTS] and not wins[ca.COND_NOPLANTS]:
        wins = ca.condition_windows(bio)
    mrows = []
    for cond, base in [(ca.COND_PLANTS, "plants"), (ca.COND_NOPLANTS, "no_plants")]:
        for (a, b) in wins[cond]:
            mrows.append({"session_id": s, "event_code": f"{base}_onset", "utc_ms": int(a)})
            mrows.append({"session_id": s, "event_code": f"{base}_offset", "utc_ms": int(b)})
    pd.DataFrame(mrows).sort_values("utc_ms").to_csv(CLEAN / f"{s}_markers.csv", index=False)

    # vernier passthrough (cleaned columns)
    v = ver.rename(columns={"t_ms": "timestamp_unix", "resp_rate": "RR"}).copy()
    v["timestamp_unix"] = (v["timestamp_unix"] / 1000.0)
    v[["timestamp_unix", "force", "RR", "condition"]].to_csv(CLEAN / f"{s}_vernier.csv", index=False)
    written.append(s)

(CLEAN / "README.md").write_text(f"""# Cleaned_for_David_by_Claude

Cleaned, analyzer-assimilable files for {len(written)} subjects (both EmotiBit +
Vernier present; sub_1.1_G1 and corrupted sub_2.14_G1 excluded; 6 subjects
without biometrics excluded).

Per subject:
- `{{sub}}_emotibit.csv` — timestamp_ms, eda_us (EDA range-filtered 0-60 µS).
- `{{sub}}_polar.csv` — timestamp_ms, rr_ms from EmotiBit BI (range-filtered
  300-2000 ms). NOTE: wrist BI yields physiologically implausible HRV for most
  subjects; treat HRV from this source as unreliable (see
  docs/PLANT_VS_NOPLANT_RESULTS_2026-06-07.md).
- `{{sub}}_markers.csv` — session_id, event_code, utc_ms: condition windows as
  plants_onset/offset and no_plants_onset/offset.
- `{{sub}}_vernier.csv` — timestamp_unix, force, RR (respiration rate), condition.

All timestamps aligned on the local-time ISO clock shared by both devices
(tz-naive) to avoid the ~7 h timezone mismatch in the raw 8-column biometrics.

Results, tables, and figures: see the bundled `results/` subfolder and
docs/PLANT_VS_NOPLANT_RESULTS_2026-06-07.md in the repo.
""")
print(f"Wrote cleaned files for {len(written)} subjects to {CLEAN}")

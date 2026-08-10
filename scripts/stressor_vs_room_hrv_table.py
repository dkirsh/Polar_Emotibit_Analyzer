#!/usr/bin/env python3
"""Stressor vs Room paired comparison for a fixed measure set:
HR, EDA tonic, RMSSD, pNN50, SD1/SD2 ratio, Stress V2.

Same cleaning as the cohort analysis. HRV measures use EmotiBit BI with range
filter + Lipponen-Tarvainen correction + a plausibility gate (RMSSD<=200 ms);
HRV-derived rows use only subjects with valid HRV in BOTH periods.
"""
from __future__ import annotations
import importlib.util, sys
from pathlib import Path
import numpy as np, pandas as pd
from scipy import stats as sp

spec = importlib.util.spec_from_file_location("ca", "/sessions/friendly-charming-hamilton/mnt/Polar_Emotibit_Analyzer/scripts/cohort_plant_analysis.py")
ca = importlib.util.module_from_spec(spec); sys.argv = ["x"]; spec.loader.exec_module(ca)
from app.services.processing.features import lipponen_tarvainen_correction
from app.services.processing.stress import compute_stress_score_v2

OUT = Path("/sessions/friendly-charming-hamilton/mnt/outputs/stressor_room_hrv"); OUT.mkdir(parents=True, exist_ok=True)
STRESSOR = {"stressor_test_1", "stressor_test_2"}
ROOM = {ca.COND_PLANTS, ca.COND_NOPLANTS}
RR_MIN, RR_MAX, RMSSD_MAX = 300.0, 2000.0, 200.0


def hrv_block(bi):
    raw = bi[np.isfinite(bi)]; inr = raw[(raw >= RR_MIN) & (raw <= RR_MAX)]
    if len(inr) < 10: return None
    rr, ect = lipponen_tarvainen_correction(inr)
    if np.mean(ect) > 0.25: return None
    d = np.diff(rr); sdsd = np.std(d, ddof=1) if len(d) > 1 else 0.0
    sdnn = np.std(rr, ddof=1); rmssd = float(np.sqrt(np.mean(d**2)))
    if rmssd > RMSSD_MAX or sdnn > 300: return None
    sd1 = np.sqrt(0.5)*sdsd; sd2 = np.sqrt(max(2*sdnn**2 - 0.5*sdsd**2, 0))
    pnn50 = 100.0*np.mean(np.abs(d) > 50) if len(d) else 0.0
    return {"mean_hr": 60000.0/np.mean(rr), "rmssd": rmssd, "pnn50": pnn50,
            "sd1_sd2": (sd1/sd2) if sd2 > 0 else np.nan}


def phasic_index(eda):
    e = eda[np.isfinite(eda)]
    return float(np.mean(np.abs(np.diff(e)))) if len(e) > 1 else 0.0


rows = []
for s in ca.discover_subjects():
    d = ca.DATA_ROOT / s
    bp = sorted(d.rglob("*biometrics.csv"))[0]
    try: bio = ca.load_biometrics(bp)
    except Exception: continue
    em = bio["event_marker"].fillna("").to_numpy(); cond = bio["condition"].fillna("").to_numpy()
    for period, mask in [("stressor", np.isin(em, list(STRESSOR))), ("room", np.isin(cond, list(ROOM)))]:
        if mask.sum() == 0: continue
        eda = bio["eda_us"].to_numpy()[mask]; eda = eda[np.isfinite(eda) & (eda >= 0) & (eda <= 60)]
        hb = hrv_block(bio["bi_ms"].to_numpy()[mask])
        rec = {"subject": s, "period": period,
               "eda_tonic_us": float(np.mean(eda)) if len(eda) else np.nan,
               "mean_hr_bpm": hb["mean_hr"] if hb else np.nan,
               "rmssd_ms": hb["rmssd"] if hb else np.nan,
               "pnn50_pct": hb["pnn50"] if hb else np.nan,
               "sd1_sd2": hb["sd1_sd2"] if hb else np.nan}
        if hb and len(eda):
            sv2, _ = compute_stress_score_v2(rmssd_ms=hb["rmssd"], mean_hr_bpm=hb["mean_hr"],
                eda_mean_us=float(np.mean(eda)), eda_phasic_index=phasic_index(bio["eda_us"].to_numpy()[mask]),
                pnn50=hb["pnn50"], sd1_sd2_ratio=hb["sd1_sd2"])
            rec["stress_v2"] = sv2
        else:
            rec["stress_v2"] = np.nan
        rows.append(rec)

df = pd.DataFrame(rows)
df.to_csv(OUT / "per_subject_period_measures.csv", index=False)

MEAS = [("mean_hr_bpm", "Heart Rate (bpm)"), ("eda_tonic_us", "EDA Tonic (µS)"),
        ("rmssd_ms", "RMSSD (ms)"), ("pnn50_pct", "pNN50 (%)"),
        ("stress_v2", "Stress V2 (0–1)"), ("sd1_sd2", "SD1/SD2 Ratio")]
comp = []
for key, lab in MEAS:
    w = df.pivot_table(index="subject", columns="period", values=key)
    w = w.dropna(subset=["stressor", "room"]) if {"stressor", "room"}.issubset(w.columns) else w.dropna()
    if len(w) < 3: continue
    a, b = w["stressor"].to_numpy(), w["room"].to_numpy(); diff = a - b; n = len(diff)
    dz = float(diff.mean()/diff.std(ddof=1)) if diff.std(ddof=1) > 0 else np.nan
    try: wil = sp.wilcoxon(a, b).pvalue
    except Exception: wil = np.nan
    comp.append({"Measure": lab, "n": n, "Stressor": round(float(a.mean()), 2),
                 "Room": round(float(b.mean()), 2), "Δ (S−R)": round(float(diff.mean()), 2),
                 "Cohen's dz": round(dz, 2), "paired t p": round(float(sp.ttest_rel(a, b).pvalue), 3),
                 "Wilcoxon p": round(float(wil), 3)})
out = pd.DataFrame(comp); out.to_csv(OUT / "stressor_vs_room_table.csv", index=False)
print(out.to_string(index=False))

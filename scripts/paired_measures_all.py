#!/usr/bin/env python3
"""Per-subject, per-condition measures for two paired contrasts:
Stressor vs Room and Plants vs No-Plants.

Measures: Heart Rate, EDA Tonic, RMSSD, pNN50, Stress V2, SD1/SD2 ratio,
Respiration Rate. HRV measures gated for plausibility; respiration from the
vernier device rate column.
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

OUT = Path("/sessions/friendly-charming-hamilton/mnt/outputs/paired_measures"); OUT.mkdir(parents=True, exist_ok=True)
STRESSOR = {"stressor_test_1", "stressor_test_2"}
PLANTS, NOPL = ca.COND_PLANTS, ca.COND_NOPLANTS
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
    return {"mean_hr": 60000.0/np.mean(rr), "rmssd": rmssd,
            "pnn50": 100.0*np.mean(np.abs(d) > 50) if len(d) else 0.0,
            "sd1_sd2": (sd1/sd2) if sd2 > 0 else np.nan}


def measures_for(bio_mask, ver_mask, bio, ver):
    eda = bio["eda_us"].to_numpy()[bio_mask]; eda = eda[np.isfinite(eda) & (eda >= 0) & (eda <= 60)]
    hb = hrv_block(bio["bi_ms"].to_numpy()[bio_mask])
    rr = ver["resp_rate"].to_numpy()[ver_mask]; rr = rr[np.isfinite(rr) & (rr >= 4) & (rr <= 60)]
    rec = {"eda_tonic_us": float(np.mean(eda)) if len(eda) else np.nan,
           "resp_rate_bpm": float(np.mean(rr)) if len(rr) else np.nan,
           "mean_hr_bpm": hb["mean_hr"] if hb else np.nan,
           "rmssd_ms": hb["rmssd"] if hb else np.nan,
           "pnn50_pct": hb["pnn50"] if hb else np.nan,
           "sd1_sd2": hb["sd1_sd2"] if hb else np.nan}
    if hb and len(eda):
        ph = float(np.mean(np.abs(np.diff(eda)))) if len(eda) > 1 else 0.0
        sv2, _ = compute_stress_score_v2(rmssd_ms=hb["rmssd"], mean_hr_bpm=hb["mean_hr"],
            eda_mean_us=float(np.mean(eda)), eda_phasic_index=ph,
            pnn50=hb["pnn50"], sd1_sd2_ratio=hb["sd1_sd2"])
        rec["stress_v2"] = sv2
    else:
        rec["stress_v2"] = np.nan
    return rec


rows = []
for s in ca.discover_subjects():
    d = ca.DATA_ROOT / s
    try:
        bio = ca.load_biometrics(sorted(d.rglob("*biometrics.csv"))[0])
        vp = [p for p in d.rglob("*clean_respiratory_data*.csv") if "markers" not in p.name.lower()]
        ver = ca.load_vernier(vp[0] if vp else sorted(d.rglob("*clean_respiratory_data*_markers.csv"))[0])
    except Exception:
        continue
    bem, bco = bio["event_marker"].fillna("").to_numpy(), bio["condition"].fillna("").to_numpy()
    vem, vco = ver["event_marker"].fillna("").to_numpy(), ver["condition"].fillna("").to_numpy()
    periods = {
        "stressor": (np.isin(bem, list(STRESSOR)), np.isin(vem, list(STRESSOR))),
        "room": (np.isin(bco, [PLANTS, NOPL]), np.isin(vco, [PLANTS, NOPL])),
        "plants": (bco == PLANTS, vco == PLANTS),
        "no_plants": (bco == NOPL, vco == NOPL),
    }
    for per, (bm, vm) in periods.items():
        if bm.sum() == 0 and vm.sum() == 0: continue
        rec = measures_for(bm, vm, bio, ver); rec.update(subject=s, period=per)
        rows.append(rec)

df = pd.DataFrame(rows); df.to_csv(OUT / "per_subject_period_measures.csv", index=False)

MEAS = [("mean_hr_bpm", "Heart Rate (bpm)"), ("eda_tonic_us", "EDA Tonic (µS)"),
        ("rmssd_ms", "RMSSD (ms)"), ("pnn50_pct", "pNN50 (%)"),
        ("stress_v2", "Stress V2 (0–1)"), ("sd1_sd2", "SD1/SD2 Ratio"),
        ("resp_rate_bpm", "Respiration Rate (bpm)")]


def compare(a_label, b_label, fname):
    out = []
    for key, lab in MEAS:
        w = df[df.period.isin([a_label, b_label])].pivot_table(index="subject", columns="period", values=key)
        if not {a_label, b_label}.issubset(w.columns): continue
        w = w.dropna(subset=[a_label, b_label])
        if len(w) < 3: continue
        a, b = w[a_label].to_numpy(), w[b_label].to_numpy(); diff = a - b; n = len(diff)
        dz = float(diff.mean()/diff.std(ddof=1)) if diff.std(ddof=1) > 0 else np.nan
        try: wil = sp.wilcoxon(a, b).pvalue
        except Exception: wil = np.nan
        out.append({"Measure": lab, "n": n, "A": round(float(a.mean()), 2), "B": round(float(b.mean()), 2),
                    "diff": round(float(diff.mean()), 2), "dz": round(dz, 2),
                    "t_p": round(float(sp.ttest_rel(a, b).pvalue), 3), "wil_p": round(float(wil), 3)})
    t = pd.DataFrame(out); t.to_csv(OUT / fname, index=False)
    print(f"\n=== {a_label} vs {b_label} ===\n", t.to_string(index=False))
    return t


compare("stressor", "room", "stressor_vs_room.csv")
compare("plants", "no_plants", "plants_vs_noplants.csv")

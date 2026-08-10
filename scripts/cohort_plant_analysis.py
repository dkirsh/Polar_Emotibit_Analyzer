#!/usr/bin/env python3
"""Controlled cohort analysis: plant vs no-plant — EDA + HRV + respiration.

Cleaning per contracts/CLEANING_AND_NORMALIZATION_CONTRACT_2026-06-07.md.

Alignment note: both biometrics and vernier carry a local-time ISO `timestamp`
column; the 8-column biometrics also carry `timestamp_unix` (UTC epoch of that
local time). Mixing them introduces a ~7 h offset, so we align BOTH files on the
ISO `timestamp` parsed tz-naive (internally consistent within a subject).

Heart/HRV uses EmotiBit BI (beat interval) — the only beat-to-beat heart data
present — range-filtered (300–2000 ms) + Lipponen–Tarvainen ectopic correction;
HRV is INVALIDATED for a condition if corrected fraction > 25% (Peters 2008).

Respiratory stress patterns are classified PER BREATH against each subject's own
breath distribution (phase-independent), then counted by condition. A respiratory
stress index = fraction of breaths flagged with any stress pattern; a weighted
variant applies severity weights (both EXPERIMENTAL, documented).

Run:  PYTHONPATH=backend python3 scripts/cohort_plant_analysis.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from app.services.processing.features import lipponen_tarvainen_correction
from app.services.ingestion.vernier_parser import baseline_als, peakdetect_simple
from app.services.processing.respiratory_patterns import extract_breath_cycles

DATA_ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
    "/sessions/friendly-charming-hamilton/mnt/david_resp_emotibit_hadoff")
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(
    "/sessions/friendly-charming-hamilton/mnt/outputs/cohort")
CLEAN_DIR = DATA_ROOT / "Cleaned_for_David_by_Claude"
OUT.mkdir(parents=True, exist_ok=True); CLEAN_DIR.mkdir(parents=True, exist_ok=True)

RR_MIN, RR_MAX = 300.0, 2000.0
EDA_MIN, EDA_MAX = 0.0, 60.0
CORRECTED_FRACTION_CEILING = 0.25
# Physiological plausibility ceilings — wrist optical BI can pass the range/ectopic
# filters yet still yield impossible HRV; these gates surface that (panel finding).
RMSSD_PLAUSIBLE_MAX = 200.0   # ms; task HRV above this is implausible
SDNN_PLAUSIBLE_MAX = 300.0    # ms
EXCLUDE_SUBJECTS = {"sub_2.14_G1"}  # malformed biometrics export
COND_PLANTS, COND_NOPLANTS = "physical_plants", "physical_no_plants"

# Per-breath stress thresholds (EXPERIMENTAL). Tightened to clearly-abnormal
# events because belt-derived per-cycle features are noisy; loose thresholds
# (e.g. CV>0.30) flag a majority of breaths and do not discriminate.
FAST_RATE_BPM = 20.0
IE_EQUAL = (0.9, 1.15)     # approaching 1:1 (normal ~0.5); narrow band
IE_INVERTED = 1.5
CV_IRREGULAR = 0.50
APNEA_DUR_S = 8.0
SIGH_SIGMA = 1.5
PATTERN_WEIGHTS = {"tachypnea": 1.0, "shallow": 1.0, "ie_shift": 0.75, "sigh": 0.5,
                   "irregular": 1.25, "apnea": 1.25, "inverted_ie": 1.0}


def to_ms(series: pd.Series, colname: str) -> pd.Series:
    name = colname.lower()
    if "unix" in name:
        return pd.to_numeric(series, errors="coerce") * 1000.0
    num = pd.to_numeric(series, errors="coerce")
    if num.notna().mean() > 0.9:
        med = float(num.dropna().median())
        if med > 1e17: return num / 1e6
        if med > 1e11: return num
        return num * 1000.0
    dt = pd.to_datetime(series, errors="coerce")        # tz-naive, local frame
    return dt.astype("int64").where(dt.notna(), np.nan) / 1e6


def _pick_time_col(cols: dict[str, str]) -> str:
    return cols.get("timestamp") or cols.get("timestamp_unix") or list(cols.values())[0]


def load_biometrics(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, low_memory=False, on_bad_lines="skip")
    cols = {c.lower(): c for c in df.columns}
    tcol = _pick_time_col(cols)
    out = pd.DataFrame({"t_ms": to_ms(df[tcol], tcol)})
    out["eda_us"] = pd.to_numeric(df.get(cols.get("eda")), errors="coerce")
    out["bi_ms"] = pd.to_numeric(df.get(cols.get("bi")), errors="coerce")
    out["condition"] = df[cols["condition"]].astype(str) if "condition" in cols else ""
    out["event_marker"] = df[cols["event_marker"]].astype(str) if "event_marker" in cols else ""
    return out.dropna(subset=["t_ms"]).sort_values("t_ms").reset_index(drop=True)


def load_vernier(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, low_memory=False, on_bad_lines="skip")
    cols = {c.lower(): c for c in df.columns}
    tcol = _pick_time_col(cols)
    out = pd.DataFrame({"t_ms": to_ms(df[tcol], tcol)})
    out["force"] = pd.to_numeric(df.get(cols.get("force")), errors="coerce")
    out["resp_rate"] = pd.to_numeric(df[cols["rr"]], errors="coerce") if "rr" in cols else np.nan
    out["condition"] = df[cols["condition"]].astype(str) if "condition" in cols else ""
    out["event_marker"] = df[cols["event_marker"]].astype(str) if "event_marker" in cols else ""
    return out.dropna(subset=["t_ms"]).sort_values("t_ms").reset_index(drop=True)


def condition_windows(df: pd.DataFrame) -> dict[str, list[tuple[float, float]]]:
    wins = {COND_PLANTS: [], COND_NOPLANTS: []}
    if "condition" not in df:
        return wins
    cond = df["condition"].fillna("").to_numpy(); t = df["t_ms"].to_numpy()
    start = 0
    for i in range(1, len(cond) + 1):
        if i == len(cond) or cond[i] != cond[start]:
            if cond[start] in wins:
                wins[cond[start]].append((float(t[start]), float(t[i - 1])))
            start = i
    return wins


def mask_in_windows(t_ms: np.ndarray, windows) -> np.ndarray:
    m = np.zeros(len(t_ms), dtype=bool)
    for a, b in windows:
        m |= (t_ms >= a) & (t_ms <= b)
    return m


def hrv_for(bi_ms: np.ndarray) -> dict:
    raw = bi_ms[np.isfinite(bi_ms)]
    inr = raw[(raw >= RR_MIN) & (raw <= RR_MAX)]
    qc = {"n_beats": int(len(raw)), "n_out_of_range": int(len(raw) - len(inr)),
          "corrected_fraction": None, "rmssd_ms": None, "sdnn_ms": None,
          "mean_hr_bpm": None, "hrv_valid": False, "hrv_reason": ""}
    if len(inr) < 10:
        qc["hrv_reason"] = "fewer than 10 in-range beats"; return qc
    corrected, ectopic = lipponen_tarvainen_correction(inr)
    frac = float(np.sum(ectopic)) / len(ectopic)
    qc["corrected_fraction"] = round(frac, 4)
    if frac > CORRECTED_FRACTION_CEILING:
        qc["hrv_reason"] = f"corrected {frac:.0%} > {CORRECTED_FRACTION_CEILING:.0%}"; return qc
    diff = np.diff(corrected)
    rmssd = float(np.sqrt(np.mean(diff ** 2))); sdnn = float(np.std(corrected, ddof=1))
    qc.update(rmssd_ms=round(rmssd, 2), sdnn_ms=round(sdnn, 2),
              mean_hr_bpm=round(60000.0 / float(np.mean(corrected)), 2))
    if rmssd > RMSSD_PLAUSIBLE_MAX or sdnn > SDNN_PLAUSIBLE_MAX:
        qc["hrv_reason"] = (f"implausible HRV (RMSSD={rmssd:.0f}, SDNN={sdnn:.0f} ms) — "
                            "noisy wrist BI; not trustworthy")
        qc["hrv_valid"] = False
    else:
        qc["hrv_valid"] = True
    return qc


def build_breaths(ver: pd.DataFrame, fs: float) -> pd.DataFrame:
    """Whole-session breath cycles with a per-breath condition label."""
    f = ver["force"].to_numpy(); t = ver["t_ms"].to_numpy()
    cond = ver["condition"].fillna("").to_numpy()
    good = np.isfinite(f)
    f = f[good]; t = t[good]; cond = cond[good]
    if len(f) < int(20 * fs):
        return pd.DataFrame()
    detr = f - baseline_als(f)
    # Low-pass the force (~1.5 s moving average) to suppress sub-respiratory noise
    # that otherwise causes peak over-detection (inflated breath rate).
    lp = max(3, int(1.5 * fs))
    detr = np.convolve(detr, np.ones(lp) / lp, mode="same")
    win = max(10, min(int(10 * fs), len(detr) // 2))
    m = np.convolve(detr, np.ones(win) / win, mode="same")
    sd = np.sqrt(np.convolve((detr - m) ** 2, np.ones(win) / win, mode="same")); sd[sd < 1e-9] = 1e-9
    resp_z = (detr - m) / sd
    # Enforce a minimum peak spacing (≥1.5 s → ≤40 bpm) so noise isn't read as breaths.
    peaks, troughs = peakdetect_simple(resp_z, lookahead=max(3, int(1.5 * fs)), delta=0.5)
    if len(peaks) < 3 or len(troughs) < 3:
        return pd.DataFrame()
    cyc = extract_breath_cycles(resp_z, peaks, troughs, int(round(fs)), None, detrended=detr)
    if len(cyc) == 0:
        return pd.DataFrame()
    # condition + event_marker for each breath = vernier value at its trough sample
    em = ver["event_marker"].fillna("").to_numpy()[good] if "event_marker" in ver else np.array([""] * len(cond))
    t1 = cyc["t1_idx"].to_numpy().astype(int).clip(0, len(cond) - 1)
    cyc = cyc.copy(); cyc["condition"] = cond[t1]; cyc["event_marker"] = em[t1]
    return cyc


def flag_breath_stress(cyc: pd.DataFrame) -> pd.DataFrame:
    """Per-breath stress flags vs the SUBJECT's own distribution."""
    if len(cyc) == 0:
        return cyc
    cyc = cyc.copy()
    amp_med = cyc["amplitude"].median(); amp_std = cyc["amplitude"].std()
    dur_med = cyc["dur"].median(); shallow_thr = cyc["amplitude"].quantile(0.10)
    cyc["f_tachypnea"] = cyc["rate_bpm"] > FAST_RATE_BPM
    cyc["f_ie_shift"] = cyc["ie_ratio"].between(*IE_EQUAL)
    cyc["f_inverted_ie"] = cyc["ie_ratio"] > IE_INVERTED
    cyc["f_shallow"] = cyc["amplitude"] < shallow_thr
    cyc["f_irregular"] = cyc["local_cv"] > CV_IRREGULAR
    cyc["f_sigh"] = (cyc["amplitude"] > amp_med + SIGH_SIGMA * amp_std) & (cyc["dur"] > dur_med)
    apnea = (cyc["dur"] > APNEA_DUR_S) & (cyc["amplitude"] < amp_med)
    if "amplitude_z" in cyc:
        apnea &= cyc["amplitude_z"] < 1.0
    cyc["f_apnea"] = apnea
    flagcols = [c for c in cyc.columns if c.startswith("f_")]
    cyc["any_stress"] = cyc[flagcols].any(axis=1)
    cyc["weighted_stress"] = sum(
        cyc[f"f_{p}"].astype(float) * w for p, w in PATTERN_WEIGHTS.items() if f"f_{p}" in cyc)
    return cyc


def estimate_fs(t_ms: np.ndarray) -> float:
    if len(t_ms) < 2: return 20.0
    dur = (t_ms[-1] - t_ms[0]) / 1000.0
    return float(len(t_ms) / dur) if dur > 0 else 20.0


PATTERNS = ["tachypnea", "ie_shift", "inverted_ie", "shallow", "irregular", "sigh", "apnea"]


def discover_subjects() -> list[str]:
    subs = []
    for d in sorted(DATA_ROOT.glob("sub_*")):
        if d.name == "sub_1.1_G1" or d.name in EXCLUDE_SUBJECTS:
            continue
        bio = list(d.rglob("*biometrics.csv"))
        ver = [p for p in d.rglob("*clean_respiratory_data*.csv") if "markers" not in p.name.lower()] \
            or list(d.rglob("*clean_respiratory_data*_markers.csv"))
        if bio and ver:
            subs.append(d.name)
    return subs


def main() -> int:
    subjects = discover_subjects()
    rows, clean_log = [], []
    for s in subjects:
        d = DATA_ROOT / s
        bio_path = sorted(d.rglob("*biometrics.csv"))[0]
        ver_cands = [p for p in d.rglob("*clean_respiratory_data*.csv") if "markers" not in p.name.lower()]
        ver_path = ver_cands[0] if ver_cands else sorted(d.rglob("*clean_respiratory_data*_markers.csv"))[0]
        try:
            bio = load_biometrics(bio_path); ver = load_vernier(ver_path)
        except Exception as e:
            clean_log.append({"subject": s, "status": "load_error", "detail": str(e)}); continue

        wins = condition_windows(ver)
        if not wins[COND_PLANTS] and not wins[COND_NOPLANTS]:
            wins = condition_windows(bio)
        fs = estimate_fs(ver["t_ms"].to_numpy())

        # subject-level EDA winsorization (range then 5/95 clip)
        eda = bio["eda_us"].to_numpy()
        eda_ok = np.isfinite(eda) & (eda >= EDA_MIN) & (eda <= EDA_MAX)
        edastats = bio["eda_us"].where(pd.Series(eda_ok))
        lo, hi = (np.nanpercentile(edastats, [5, 95]) if eda_ok.sum() else (np.nan, np.nan))

        breaths = flag_breath_stress(build_breaths(ver, fs))

        clean_log.append({"subject": s, "status": "ok",
                          "eda_n": int(eda_ok.sum()),
                          "eda_dropped_range": int(np.isfinite(eda).sum() - eda_ok.sum()),
                          "fs_vernier_hz": round(fs, 2),
                          "n_breaths_total": int(len(breaths)),
                          "plants_bouts": len(wins[COND_PLANTS]),
                          "noplants_bouts": len(wins[COND_NOPLANTS]),
                          "bio_start": bio["t_ms"].min(), "ver_start": ver["t_ms"].min()})

        bt = bio["t_ms"].to_numpy()
        for cond, label in [(COND_PLANTS, "plants"), (COND_NOPLANTS, "no_plants")]:
            if not wins[cond]:
                continue
            bm = mask_in_windows(bt, wins[cond])
            e = bio["eda_us"].to_numpy()[bm]
            e = e[np.isfinite(e) & (e >= EDA_MIN) & (e <= EDA_MAX)]
            if np.isfinite(lo) and np.isfinite(hi):
                e = np.clip(e, lo, hi)
            hrv = hrv_for(bio["bi_ms"].to_numpy()[bm])
            bc = breaths[breaths["condition"] == cond] if len(breaths) else breaths
            nb = len(bc)
            pcounts = {p: int(bc[f"f_{p}"].sum()) for p in PATTERNS} if nb else {}
            # Mean respiration rate from the device's own RR column (more reliable
            # than force-derived rate), within this condition's vernier rows.
            vm = mask_in_windows(ver["t_ms"].to_numpy(), wins[cond])
            dev_rr = ver["resp_rate"].to_numpy()[vm]
            dev_rr = dev_rr[np.isfinite(dev_rr) & (dev_rr >= 4) & (dev_rr <= 60)]
            row = {"subject": s, "condition": label,
                   "eda_tonic_us": round(float(np.mean(e)), 4) if len(e) else None,
                   "eda_n": int(len(e)),
                   **{k: hrv[k] for k in ("rmssd_ms", "sdnn_ms", "mean_hr_bpm",
                                          "hrv_valid", "corrected_fraction", "n_beats", "hrv_reason")},
                   "mean_resp_rate_bpm": round(float(np.mean(dev_rr)), 2) if len(dev_rr) else (
                       round(float(bc["rate_bpm"].mean()), 2) if nb else None),
                   "n_breaths": int(nb),
                   "n_stress_breaths": int(bc["any_stress"].sum()) if nb else 0,
                   "resp_stress_index": round(float(bc["any_stress"].mean()), 4) if nb else None,
                   "resp_stress_weighted": round(float(bc["weighted_stress"].mean()), 4) if nb else None,
                   **{f"pat_{p}": pcounts.get(p, 0) for p in PATTERNS}}
            rows.append(row)

    per_cond = pd.DataFrame(rows)
    per_cond.to_csv(OUT / "per_subject_condition.csv", index=False)
    pd.DataFrame(clean_log).to_csv(OUT / "cleaning_log.csv", index=False)
    print(f"subjects={len(subjects)} rows={len(per_cond)} "
          f"HRV_valid={int(per_cond['hrv_valid'].sum())} "
          f"resp_index_nonzero={(per_cond['resp_stress_index']>0).sum()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

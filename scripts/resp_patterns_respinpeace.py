#!/usr/bin/env python3
"""Identify the seven respiratory stress patterns from RespInPeace's output.

This replaces the ad-hoc force peak-detection with the RespInPeace engine
(rip.Resp): ALS baseline removal, prominence-based cycle detection, and a real
breath-hold detector. Per-breath features come from RespInPeace; the seven
patterns are then classified on top. Apnea is taken from RespInPeace's detected
holds (the ad-hoc detector found none).

Conditions: plants / no_plants / stressor. Output: per-subject counts, totals by
condition, and significance (Friedman + pairwise Wilcoxon).
"""
from __future__ import annotations
import importlib.util, sys
from pathlib import Path
import numpy as np, pandas as pd
from scipy import stats as sp

RIP_DIR = Path("/sessions/friendly-charming-hamilton/mnt/Polar_Emotibit_Analyzer/Estelita/RespInPeace_Output/code")
sys.path.insert(0, str(RIP_DIR))
from rip import Resp  # noqa: E402

spec = importlib.util.spec_from_file_location("ca", "/sessions/friendly-charming-hamilton/mnt/Polar_Emotibit_Analyzer/scripts/cohort_plant_analysis.py")
ca = importlib.util.module_from_spec(spec); sys.argv = ["x"]; spec.loader.exec_module(ca)

OUT = Path("/sessions/friendly-charming-hamilton/mnt/outputs/resp_patterns_respinpeace")
OUT.mkdir(parents=True, exist_ok=True)
FS = 20
STRESSOR = {"stressor_test_1", "stressor_test_2"}
PATTERNS = ["tachypnea", "ie_shift", "inverted_ie", "shallow", "irregular", "sigh", "apnea"]
CONDS = ["plants", "no_plants", "stressor"]
FAST, IE_LO, IE_HI, IE_INV, CV, SIGH_SD = 18.0, 0.85, 1.15, 1.5, 0.30, 1.5


def load_vernier_xlsx(path: Path) -> pd.DataFrame:
    """Load the full-resolution xlsx belt file (millisecond timestamps) so breath
    detection isn't degraded by the CSV's second-resolution quantization."""
    df = pd.read_excel(path)
    cols = {c.lower(): c for c in df.columns}
    t = pd.to_datetime(df[cols["timestamp"]], errors="coerce")
    out = pd.DataFrame({"t_ms": t.astype("int64") / 1e6})
    out["force"] = pd.to_numeric(df[cols["force"]], errors="coerce")
    out["condition"] = df[cols["condition"]].astype(str) if "condition" in cols else ""
    out["event_marker"] = df[cols["event_marker"]].astype(str) if "event_marker" in cols else ""
    return out.dropna(subset=["t_ms"]).sort_values("t_ms").reset_index(drop=True)


def breaths_from_respinpeace(ver: pd.DataFrame):
    el = (ver["t_ms"].to_numpy() - ver["t_ms"].to_numpy()[0]) / 1000.0
    force = ver["force"].to_numpy(); ev = ver["event_marker"].fillna("").to_numpy()
    cond = ver["condition"].fillna("").to_numpy()
    good = np.isfinite(force)
    el, force, ev, cond = el[good], force[good], ev[good], cond[good]
    dur = float(el[-1]) if len(el) else 0.0
    if dur < 30:
        return pd.DataFrame()
    tu = np.arange(0.0, dur, 1.0 / FS)
    fu = np.interp(tu, el, force)
    resp = Resp(fu, FS)
    resp.remove_baseline(method="als")
    resp.find_cycles(include_holds=True)
    seg = resp.segments; ncyc = len(seg) // 2
    def oidx(tsec): return min(max(int(np.searchsorted(el, tsec)), 0), len(el) - 1)
    def mode_str(a):
        v = [x for x in a if isinstance(x, str) and x]
        return max(set(v), key=v.count) if v else ""
    rows = []
    for k in range(ncyc):
        ins, outs = seg[2 * k], seg[2 * k + 1]
        tr1, pk, tr2 = ins.start_time, ins.end_time, outs.end_time
        cyc = tr2 - tr1
        if cyc <= 0:
            continue
        inhale, exhale = pk - tr1, tr2 - pk
        try:
            amp = resp.extract_features(tr1, pk, norm=False).get("amplitude", np.nan)
        except Exception:
            amp = np.nan
        hs = resp.holds.get_annotations_between_timepoints(tr1, tr2, left_overlap=True, right_overlap=True)
        i0, i1 = oidx(tr1), max(oidx(tr2), oidx(tr1) + 1)
        rows.append(dict(rate_bpm=60.0 / cyc, dur=cyc, inhale=inhale, exhale=exhale,
                         ie_ratio=(inhale / exhale) if exhale > 0 else np.nan,
                         amplitude=float(amp), n_holds=len(hs),
                         condition=mode_str(cond[i0:i1]), event_marker=mode_str(ev[i0:i1])))
    df = pd.DataFrame(rows)
    if len(df):
        df["local_cv"] = df["dur"].rolling(5, center=True, min_periods=5).apply(
            lambda x: x.std() / x.mean() if x.mean() > 0 else 0)
    return df


def classify(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    amp_med, amp_sd = df["amplitude"].median(), df["amplitude"].std()
    dur_med, shallow_thr = df["dur"].median(), df["amplitude"].quantile(0.10)
    df["tachypnea"] = df["rate_bpm"] > FAST
    df["ie_shift"] = df["ie_ratio"].between(IE_LO, IE_HI)
    df["inverted_ie"] = df["ie_ratio"] > IE_INV
    df["shallow"] = df["amplitude"] < shallow_thr
    df["irregular"] = df["local_cv"] > CV
    df["sigh"] = (df["amplitude"] > amp_med + SIGH_SD * amp_sd) & (df["dur"] > dur_med)
    df["apnea"] = df["n_holds"] > 0          # REAL holds from RespInPeace
    df["any_stress"] = df[PATTERNS].any(axis=1)
    return df


def period_of(r):
    if r["event_marker"] in STRESSOR: return "stressor"
    if r["condition"] == ca.COND_PLANTS: return "plants"
    if r["condition"] == ca.COND_NOPLANTS: return "no_plants"
    return None


def main():
    rows = []
    for s in ca.discover_subjects():
        d = ca.DATA_ROOT / s
        xp = list(d.rglob("*clean_respiratory_data*.xlsx"))
        if not xp:
            print("skip", s, "no xlsx"); continue
        ver_path = xp[0]
        try:
            ver = load_vernier_xlsx(ver_path)
            br = classify(breaths_from_respinpeace(ver)) if True else None
        except Exception as e:
            print("skip", s, e); continue
        if not len(br):
            continue
        br["period"] = br.apply(period_of, axis=1)
        for cond in CONDS:
            sub = br[br["period"] == cond]
            if not len(sub):
                continue
            rec = {"subject": s, "condition": cond, "n_breaths": int(len(sub)),
                   "total_holds": int(sub["n_holds"].sum())}
            for p in PATTERNS:
                rec[p] = int(sub[p].sum())
            rec["total_stress"] = int(sub["any_stress"].sum())
            rec["stress_rate_per100"] = round(100.0 * sub["any_stress"].mean(), 2)
            rows.append(rec)
        print("done", s, "breaths", len(br), "holds", int(br["n_holds"].sum()))
    big = pd.DataFrame(rows)
    big.to_csv(OUT / "table_per_subject_3conditions_RIP.csv", index=False)

    permat = big.groupby("condition")[PATTERNS].sum().reindex(CONDS)
    permat.to_csv(OUT / "table_pattern_totals_matrix_RIP.csv")

    norm = big.copy()
    norm["stress_rate_per100"] = 100.0 * big["total_stress"] / big["n_breaths"]
    rate = norm.pivot_table(index="subject", columns="condition", values="stress_rate_per100")
    complete = rate.dropna(subset=CONDS) if set(CONDS).issubset(rate.columns) else rate.dropna()
    sig = {}
    if len(complete) >= 3 and set(CONDS).issubset(complete.columns):
        fr = sp.friedmanchisquare(complete["plants"], complete["no_plants"], complete["stressor"])
        sig = {"friedman_chi2": round(float(fr.statistic), 3), "friedman_p": round(float(fr.pvalue), 4),
               "n_complete": int(len(complete))}
        for a, b in [("stressor", "plants"), ("stressor", "no_plants"), ("plants", "no_plants")]:
            try: sig[f"wilcoxon_{a}_vs_{b}_p"] = round(float(sp.wilcoxon(complete[a], complete[b]).pvalue), 4)
            except Exception: sig[f"wilcoxon_{a}_vs_{b}_p"] = None
    small = []
    for cond in CONDS:
        sc = big[big.condition == cond]
        small.append({"condition": cond,
                      "total_stress_breaths": int(sc["total_stress"].sum()),
                      "total_apnea_breaths": int(sc["apnea"].sum()),
                      "total_holds": int(sc["total_holds"].sum()),
                      "mean_stress_rate_per100": round(float(norm[norm.condition == cond]["stress_rate_per100"].mean()), 2)})
    pd.DataFrame(small).to_csv(OUT / "table_totals_by_condition_RIP.csv", index=False)
    pd.DataFrame([sig]).to_csv(OUT / "table_significance_RIP.csv", index=False)

    print("\n=== per-pattern totals (RespInPeace) ===\n", permat.to_string())
    print("\n=== totals by condition ===\n", pd.DataFrame(small).to_string(index=False))
    print("\n=== significance ===\n", sig)
    print("\n=== apnea total (RespInPeace holds) vs prior crude (0):", int(big["apnea"].sum()))


if __name__ == "__main__":
    main()

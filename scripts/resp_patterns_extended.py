#!/usr/bin/env python3
"""Extended, recalibrated respiratory stress-pattern classifier on RespInPeace
output.

Two changes versus the earlier RespInPeace pass:

1. RECALIBRATION — thresholds are made relative to each subject's own REST
   baseline (event markers biometric_baseline / subject_idle / ser_baseline /
   startup), not fixed clinical cutoffs that saturate this belt. A breath is
   flagged when it deviates from what is normal *for that person at rest*, which
   is both more discriminating and within-subject normalized. Apnea uses a real
   hold of >= 1.0 s (RespInPeace holds), not "any hold".

2. EXTENDED PATTERN SET — adds bradypnea / hypoventilation, sustained
   hyperventilation, breath-stacking (rising end-expiratory baseline), and
   periodic (waxing-waning) breathing, plus a sigh-rate flag. Paradoxical /
   thoracic breathing is NOT included (needs a second belt).

Conditions: plants / no_plants / stressor. Output: per-subject counts, totals by
condition, significance (Friedman + pairwise Wilcoxon), and a figure.
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
from scipy import stats as sp

RIP_DIR = Path("/sessions/friendly-charming-hamilton/mnt/Polar_Emotibit_Analyzer/Estelita/RespInPeace_Output/code")
sys.path.insert(0, str(RIP_DIR))
from rip import Resp  # noqa: E402

import importlib.util
spec = importlib.util.spec_from_file_location("ca", "/sessions/friendly-charming-hamilton/mnt/Polar_Emotibit_Analyzer/scripts/cohort_plant_analysis.py")
ca = importlib.util.module_from_spec(spec); sys.argv = ["x"]; spec.loader.exec_module(ca)

OUT = Path("/sessions/friendly-charming-hamilton/mnt/outputs/resp_patterns_extended")
OUT.mkdir(parents=True, exist_ok=True)
FS = 20
STRESSOR = {"stressor_test_1", "stressor_test_2"}
REST = {"biometric_baseline", "subject_idle", "ser_baseline", "startup"}
CONDS = ["plants", "no_plants", "stressor"]
CORE = ["tachypnea", "bradypnea", "ie_shift", "inverted_ie", "shallow",
        "irregular", "sigh", "apnea", "hyperventilation", "breath_stacking", "periodic"]


def load_xlsx(path: Path) -> pd.DataFrame:
    df = pd.read_excel(path)
    cols = {c.lower(): c for c in df.columns}
    t = pd.to_datetime(df[cols["timestamp"]], errors="coerce")
    out = pd.DataFrame({"t_ms": t.astype("int64") / 1e6})
    out["force"] = pd.to_numeric(df[cols["force"]], errors="coerce")
    out["condition"] = df[cols["condition"]].astype(str) if "condition" in cols else ""
    out["event_marker"] = df[cols["event_marker"]].astype(str) if "event_marker" in cols else ""
    return out.dropna(subset=["t_ms"]).sort_values("t_ms").reset_index(drop=True)


def extract_breaths(ver: pd.DataFrame) -> pd.DataFrame:
    el = (ver["t_ms"].to_numpy() - ver["t_ms"].to_numpy()[0]) / 1000.0
    force = ver["force"].to_numpy(); ev = ver["event_marker"].fillna("").to_numpy()
    cond = ver["condition"].fillna("").to_numpy()
    good = np.isfinite(force); el, force, ev, cond = el[good], force[good], ev[good], cond[good]
    dur = float(el[-1]) if len(el) else 0
    if dur < 30: return pd.DataFrame()
    tu = np.arange(0, dur, 1.0 / FS); fu = np.interp(tu, el, force)
    resp = Resp(fu, FS); resp.remove_baseline(method="als"); resp.find_cycles(include_holds=True)
    seg = resp.segments; ncyc = len(seg) // 2
    def oi(t): return min(max(int(np.searchsorted(el, t)), 0), len(el) - 1)
    def mode(a):
        v = [x for x in a if isinstance(x, str) and x]; return max(set(v), key=v.count) if v else ""
    rows = []
    for k in range(ncyc):
        ins, outs = seg[2*k], seg[2*k+1]; tr1, pk, tr2 = ins.start_time, ins.end_time, outs.end_time
        cyc = tr2 - tr1
        if cyc <= 0: continue
        try:
            fin = resp.extract_features(tr1, pk, norm=False)
            amp, onset = fin.get("amplitude", np.nan), fin.get("onset_level", np.nan)
        except Exception:
            amp, onset = np.nan, np.nan
        hs = resp.holds.get_annotations_between_timepoints(tr1, tr2, left_overlap=True, right_overlap=True)
        hold_dur = sum(min(h.end_time, tr2) - max(h.start_time, tr1) for h in hs) if hs else 0.0
        i0, i1 = oi(tr1), max(oi(tr2), oi(tr1)+1)
        rows.append(dict(rate_bpm=60.0/cyc, dur=cyc, ie_ratio=((pk-tr1)/(tr2-pk)) if (tr2-pk) > 0 else np.nan,
                         amplitude=float(amp), onset_level=float(onset), hold_dur=hold_dur,
                         condition=mode(cond[i0:i1]), event_marker=mode(ev[i0:i1])))
    df = pd.DataFrame(rows)
    if len(df):
        df["local_cv"] = df["dur"].rolling(5, center=True, min_periods=5).apply(lambda x: x.std()/x.mean() if x.mean() > 0 else 0)
        df["rate_med5"] = df["rate_bpm"].rolling(5, center=True, min_periods=3).median()
        df["onset_slope4"] = df["onset_level"].rolling(4, min_periods=4).apply(lambda x: np.polyfit(range(4), x, 1)[0] if x.notna().all() else 0)
        # periodic: amplitude waxing-waning within an 8-breath window
        df["amp_osc"] = df["amplitude"].rolling(8, center=True, min_periods=8).apply(_oscillation, raw=True)
    return df


def _oscillation(x):
    x = np.asarray(x, float)
    if np.nanstd(x) == 0: return 0.0
    d = np.diff(x - np.nanmean(x))
    sign_changes = np.sum(np.diff(np.sign(d)) != 0)
    return sign_changes * (np.nanstd(x))  # high when alternating AND variable


def classify(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    base = df[df["event_marker"].isin(REST)]
    if len(base) < 10:
        base = df
    r_mu, r_sd = base["rate_bpm"].mean(), max(base["rate_bpm"].std(), 0.5)
    a_mu, a_sd = base["amplitude"].mean(), max(base["amplitude"].std(), 1e-6)
    a_p10 = base["amplitude"].quantile(0.10)
    cv_p90 = max(base["local_cv"].quantile(0.90), 0.20)
    dur_med = base["dur"].median()
    osc_p90 = max(base["amp_osc"].quantile(0.90) if base["amp_osc"].notna().any() else 0, 1e-6)
    slope_p90 = max(base["onset_slope4"].quantile(0.90) if base["onset_slope4"].notna().any() else 0, 1e-9)

    df["tachypnea"] = df["rate_bpm"] > r_mu + 2*r_sd
    df["bradypnea"] = (df["rate_bpm"] < r_mu - 2*r_sd) & (df["rate_bpm"] > 4)
    df["ie_shift"] = df["ie_ratio"].between(0.85, 1.15)
    df["inverted_ie"] = df["ie_ratio"] > 1.5
    df["shallow"] = df["amplitude"] < a_p10
    df["irregular"] = df["local_cv"] > cv_p90
    df["sigh"] = (df["amplitude"] > a_mu + 2*a_sd) & (df["dur"] > dur_med)
    df["apnea"] = df["hold_dur"] >= 1.0
    df["hyperventilation"] = df["rate_med5"] > r_mu + 1.5*r_sd
    df["breath_stacking"] = df["onset_slope4"] > slope_p90
    df["periodic"] = df["amp_osc"] > osc_p90
    df["any_stress"] = df[CORE].any(axis=1)
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
        if not xp: continue
        try:
            br = classify(extract_breaths(load_xlsx(xp[0])))
        except Exception as e:
            print("skip", s, e); continue
        if not len(br): continue
        br["period"] = br.apply(period_of, axis=1)
        for cond in CONDS:
            sub = br[br["period"] == cond]
            if not len(sub): continue
            rec = {"subject": s, "condition": cond, "n_breaths": int(len(sub))}
            for p in CORE: rec[p] = int(sub[p].sum())
            rec["total_stress"] = int(sub["any_stress"].sum())
            rec["stress_rate_per100"] = round(100.0*sub["any_stress"].mean(), 2)
            rows.append(rec)
        print("done", s, "breaths", len(br), "stress_rate %.0f%%" % (100*br["any_stress"].mean()))
    big = pd.DataFrame(rows)
    big.to_csv(OUT / "table_per_subject_extended.csv", index=False)
    permat = big.groupby("condition")[CORE].sum().reindex(CONDS); permat.to_csv(OUT / "table_pattern_totals_extended.csv")

    rate = big.pivot_table(index="subject", columns="condition", values="stress_rate_per100")
    comp = rate.dropna(subset=CONDS) if set(CONDS).issubset(rate.columns) else rate.dropna()
    sig = {}
    if len(comp) >= 3 and set(CONDS).issubset(comp.columns):
        fr = sp.friedmanchisquare(comp["plants"], comp["no_plants"], comp["stressor"])
        sig = {"friedman_chi2": round(float(fr.statistic), 3), "friedman_p": round(float(fr.pvalue), 4), "n": int(len(comp))}
        for a, b in [("stressor","plants"), ("stressor","no_plants"), ("plants","no_plants")]:
            try: sig[f"{a}_vs_{b}_p"] = round(float(sp.wilcoxon(comp[a], comp[b]).pvalue), 4)
            except Exception: sig[f"{a}_vs_{b}_p"] = None
    # per-pattern Friedman (which patterns discriminate?)
    perpat_sig = []
    for p in CORE:
        pr = big.pivot_table(index="subject", columns="condition", values=p)
        pr = pr.dropna(subset=CONDS) if set(CONDS).issubset(pr.columns) else pd.DataFrame()
        if len(pr) >= 3:
            try:
                fp = sp.friedmanchisquare(pr["plants"], pr["no_plants"], pr["stressor"]).pvalue
            except Exception:
                fp = np.nan
            perpat_sig.append({"pattern": p, "plants": int(big[big.condition=="plants"][p].sum()),
                               "no_plants": int(big[big.condition=="no_plants"][p].sum()),
                               "stressor": int(big[big.condition=="stressor"][p].sum()),
                               "friedman_p": round(float(fp), 4) if fp == fp else None})
    perpat = pd.DataFrame(perpat_sig); perpat.to_csv(OUT / "table_perpattern_significance.csv", index=False)
    small = []
    for cond in CONDS:
        sc = big[big.condition == cond]
        small.append({"condition": cond, "mean_stress_rate_per100": round(float(big[big.condition==cond]["stress_rate_per100"].mean()), 2),
                      "total_stress": int(sc["total_stress"].sum())})
    pd.DataFrame(small).to_csv(OUT / "table_totals_extended.csv", index=False)
    pd.DataFrame([sig]).to_csv(OUT / "table_significance_extended.csv", index=False)

    # figure: per-pattern rate per 100 by condition
    plt.rcParams.update({"figure.dpi": 130, "font.size": 9})
    fig, ax = plt.subplots(figsize=(13, 5.5)); x = np.arange(len(CORE)); w = 0.26
    colors = {"plants": "#2E8B57", "no_plants": "#B0651F", "stressor": "#C0392B"}
    for i, cond in enumerate(CONDS):
        vals = []
        for p in CORE:
            sc = big[big.condition == cond]
            vals.append(100.0 * sc[p].sum() / sc["n_breaths"].sum() if sc["n_breaths"].sum() else 0)
        ax.bar(x + (i-1)*w, vals, w, label=cond, color=colors[cond])
    ax.set_xticks(x); ax.set_xticklabels(CORE, rotation=35, ha="right")
    ax.set_ylabel("flagged per 100 breaths"); ax.legend(title="condition")
    ax.set_title("Extended respiratory stress patterns by condition (RespInPeace, baseline-recalibrated)", fontweight="bold")
    fig.tight_layout(); fig.savefig(OUT / "fig_extended_patterns.png", bbox_inches="tight"); plt.close(fig)

    print("\n=== per-pattern totals ===\n", permat.to_string())
    print("\n=== totals ===\n", pd.DataFrame(small).to_string(index=False))
    print("\n=== overall significance ===\n", sig)
    print("\n=== per-pattern significance ===\n", perpat.to_string(index=False))


if __name__ == "__main__":
    main()

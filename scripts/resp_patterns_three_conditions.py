#!/usr/bin/env python3
"""Respiratory stress-pattern counts across three conditions: plants, no_plants,
stressor — per subject, then totals with within-subject normalization and
significance testing.

Patterns use the analyzer's canonical thresholds (respiratory_patterns.py):
  tachypnea  rate > 18 bpm
  ie_shift   0.85 <= I:E <= 1.15  (approaching 1:1)
  inverted_ie I:E > 1.5
  shallow    amplitude < subject 10th percentile
  irregular  local_cv > 0.30
  sigh       amplitude > median + 1.5*SD  AND  dur > median
  apnea      dur > 8 s AND amplitude < median (and amplitude_z < 1)

Counts are normalized to a RATE per 100 breaths (conditions differ in length),
then expressed within-subject as the deviation from that subject's own
three-condition mean ("more/less than the subject's average"), which is what the
small comparison table aggregates and tests.
"""
from __future__ import annotations
import importlib.util, sys
from pathlib import Path
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
from scipy import stats as sp

spec = importlib.util.spec_from_file_location("ca", str(Path(__file__).parent / "cohort_plant_analysis.py"))
ca = importlib.util.module_from_spec(spec); sys.argv = ["x"]; spec.loader.exec_module(ca)

OUT = Path("/sessions/friendly-charming-hamilton/mnt/outputs/resp_patterns_3cond")
OUT.mkdir(parents=True, exist_ok=True)

STRESSOR = {"stressor_test_1", "stressor_test_2"}
PATTERNS = ["tachypnea", "ie_shift", "inverted_ie", "shallow", "irregular", "sigh", "apnea"]
CONDS = ["plants", "no_plants", "stressor"]

# canonical analyzer thresholds
FAST, IE_LO, IE_HI, IE_INV, CV, SIGH_SD, APNEA = 18.0, 0.85, 1.15, 1.5, 0.30, 1.5, 8.0


def flag_canonical(cyc: pd.DataFrame) -> pd.DataFrame:
    cyc = cyc.copy()
    amp_med, amp_sd = cyc["amplitude"].median(), cyc["amplitude"].std()
    dur_med, shallow_thr = cyc["dur"].median(), cyc["amplitude"].quantile(0.10)
    cyc["tachypnea"] = cyc["rate_bpm"] > FAST
    cyc["ie_shift"] = cyc["ie_ratio"].between(IE_LO, IE_HI)
    cyc["inverted_ie"] = cyc["ie_ratio"] > IE_INV
    cyc["shallow"] = cyc["amplitude"] < shallow_thr
    cyc["irregular"] = cyc["local_cv"] > CV
    cyc["sigh"] = (cyc["amplitude"] > amp_med + SIGH_SD * amp_sd) & (cyc["dur"] > dur_med)
    ap = (cyc["dur"] > APNEA) & (cyc["amplitude"] < amp_med)
    if "amplitude_z" in cyc: ap &= cyc["amplitude_z"] < 1.0
    cyc["apnea"] = ap
    cyc["any_stress"] = cyc[PATTERNS].any(axis=1)
    return cyc


def period_of(row):
    if row["event_marker"] in STRESSOR: return "stressor"
    if row["condition"] == ca.COND_PLANTS: return "plants"
    if row["condition"] == ca.COND_NOPLANTS: return "no_plants"
    return None


def main():
    rows = []
    for s in ca.discover_subjects():
        d = ca.DATA_ROOT / s
        vp = [p for p in d.rglob("*clean_respiratory_data*.csv") if "markers" not in p.name.lower()]
        ver_path = vp[0] if vp else sorted(d.rglob("*clean_respiratory_data*_markers.csv"))[0]
        try:
            ver = ca.load_vernier(ver_path)
        except Exception:
            continue
        fs = ca.estimate_fs(ver["t_ms"].to_numpy())
        cyc = ca.build_breaths(ver, fs)
        if not len(cyc):
            continue
        cyc = flag_canonical(cyc)
        cyc["period"] = cyc.apply(period_of, axis=1)
        for cond in CONDS:
            sub = cyc[cyc["period"] == cond]
            nb = len(sub)
            if nb == 0:
                continue
            rec = {"subject": s, "condition": cond, "n_breaths": int(nb)}
            for p in PATTERNS:
                rec[p] = int(sub[p].sum())
            rec["total_stress"] = int(sub["any_stress"].sum())
            rec["stress_rate_per100"] = round(100.0 * sub["any_stress"].mean(), 2)
            rows.append(rec)
    big = pd.DataFrame(rows)
    big.to_csv(OUT / "table_per_subject_3conditions.csv", index=False)

    # within-subject normalization on stress_rate_per100 + each pattern rate/100
    def per100(df, col): return 100.0 * df[col] / df["n_breaths"]
    norm = big.copy()
    for p in PATTERNS:
        norm[f"{p}_per100"] = per100(big, p)
    # centre each measure on the subject's own across-condition mean
    rate_cols = ["stress_rate_per100"] + [f"{p}_per100" for p in PATTERNS]
    centered = norm.copy()
    for col in rate_cols:
        centered[col + "_centered"] = norm.groupby("subject")[col].transform(lambda x: x - x.mean())
    centered.to_csv(OUT / "table_per_subject_normalized.csv", index=False)

    # ---- small table: totals per condition + significance ----
    # require subjects with all three conditions for repeated-measures tests
    counts = big.pivot_table(index="subject", columns="condition", values="total_stress", aggfunc="sum")
    rate = norm.pivot_table(index="subject", columns="condition", values="stress_rate_per100", aggfunc="mean")
    complete = rate.dropna(subset=CONDS) if set(CONDS).issubset(rate.columns) else rate.dropna()
    small_rows = []
    for cond in CONDS:
        col_total = int(big[big.condition == cond]["total_stress"].sum())
        col_rate = float(norm[norm.condition == cond]["stress_rate_per100"].mean())
        # within-subject deviation from own mean (more/less than average)
        dev = float(complete[cond].mean() - complete[CONDS].mean(axis=1).mean()) if cond in complete else np.nan
        small_rows.append({"condition": cond,
                           "total_stress_breaths_all_subjects": col_total,
                           "mean_stress_rate_per100": round(col_rate, 2),
                           "within_subj_dev_from_avg": round(dev, 2),
                           "direction": "MORE than avg" if dev > 0 else "less than avg"})
    small = pd.DataFrame(small_rows)

    # significance: Friedman across the 3 conditions (within-subject), pairwise Wilcoxon
    sig = {}
    if len(complete) >= 3 and set(CONDS).issubset(complete.columns):
        fr = sp.friedmanchisquare(complete["plants"], complete["no_plants"], complete["stressor"])
        sig["friedman_chi2"] = round(float(fr.statistic), 3)
        sig["friedman_p"] = round(float(fr.pvalue), 4)
        sig["n_complete"] = int(len(complete))
        for a, b in [("stressor", "plants"), ("stressor", "no_plants"), ("plants", "no_plants")]:
            try:
                w = sp.wilcoxon(complete[a], complete[b]).pvalue
            except Exception:
                w = np.nan
            sig[f"wilcoxon_{a}_vs_{b}_p"] = round(float(w), 4)
    pd.DataFrame([sig]).to_csv(OUT / "table_significance.csv", index=False)
    small.to_csv(OUT / "table_totals_by_condition.csv", index=False)

    # per-pattern totals by condition (the descriptive matrix)
    permat = big.groupby("condition")[PATTERNS].sum().reindex(CONDS)
    permat.to_csv(OUT / "table_pattern_totals_matrix.csv")

    # ---- figures ----
    plt.rcParams.update({"figure.dpi": 130, "font.size": 10})
    # Fig 1: grouped bars — mean per-pattern rate/100 by condition
    fig, ax = plt.subplots(figsize=(12, 5.5))
    x = np.arange(len(PATTERNS)); w = 0.26
    colors = {"plants": "#2E8B57", "no_plants": "#B0651F", "stressor": "#C0392B"}
    for i, cond in enumerate(CONDS):
        vals = [norm[norm.condition == cond][f"{p}_per100"].mean() for p in PATTERNS]
        ax.bar(x + (i - 1) * w, vals, w, label=cond, color=colors[cond])
    ax.set_xticks(x); ax.set_xticklabels(PATTERNS, rotation=30, ha="right")
    ax.set_ylabel("Mean breaths flagged per 100"); ax.legend(title="condition")
    ax.set_title("Respiratory stress patterns per 100 breaths, by condition", fontweight="bold")
    fig.tight_layout(); fig.savefig(OUT / "fig_pattern_rates_by_condition.png", bbox_inches="tight"); plt.close(fig)

    # Fig 2: total stress rate by condition with within-subject lines
    fig, ax = plt.subplots(figsize=(7, 5.5))
    cmp = complete
    for subj, r in cmp.iterrows():
        ax.plot(range(3), [r[c] for c in CONDS], "-o", color="#888", alpha=0.5, ms=4)
    ax.plot(range(3), [cmp[c].mean() for c in CONDS], "-s", color="black", lw=2.6, ms=10, label="group mean")
    ax.set_xticks(range(3)); ax.set_xticklabels(CONDS)
    ax.set_ylabel("Stress breaths per 100"); ax.legend()
    ax.set_title("Overall respiratory stress rate by condition (within-subject)", fontweight="bold")
    fig.tight_layout(); fig.savefig(OUT / "fig_total_stress_by_condition.png", bbox_inches="tight"); plt.close(fig)

    print("=== totals by condition ===")
    print(small.to_string(index=False))
    print("\n=== per-pattern totals matrix ==="); print(permat.to_string())
    print("\n=== significance ==="); print(sig)
    print("\nWrote outputs to", OUT)


if __name__ == "__main__":
    main()

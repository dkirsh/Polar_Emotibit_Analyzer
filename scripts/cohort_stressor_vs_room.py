#!/usr/bin/env python3
"""Stressor vs Room — same controlled pipeline as the plant/no-plant analysis,
but the within-subject contrast is Stressor periods vs Room periods.

  Stressor period = event_marker in {stressor_test_1, stressor_test_2}
  Room period     = condition in {physical_plants, physical_no_plants} (pooled)

Cleaning, HRV plausibility gating, respiration measures, and within-subject
normalization are identical to scripts/cohort_plant_analysis.py (imported).
"""
from __future__ import annotations
import importlib.util, sys
from pathlib import Path
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
from scipy import stats as sp

spec = importlib.util.spec_from_file_location("ca", str(Path(__file__).parent / "cohort_plant_analysis.py"))
ca = importlib.util.module_from_spec(spec); sys.argv = ["x"]; spec.loader.exec_module(ca)

OUT = Path("/sessions/friendly-charming-hamilton/mnt/outputs/cohort_stressor_room")
OUT.mkdir(parents=True, exist_ok=True)

STRESSOR = {"stressor_test_1", "stressor_test_2"}
ROOM_COND = {ca.COND_PLANTS, ca.COND_NOPLANTS}
PATTERNS = ca.PATTERNS


def main_measure() -> pd.DataFrame:
    rows = []
    for s in ca.discover_subjects():
        d = ca.DATA_ROOT / s
        bio_path = sorted(d.rglob("*biometrics.csv"))[0]
        vp = [p for p in d.rglob("*clean_respiratory_data*.csv") if "markers" not in p.name.lower()]
        ver_path = vp[0] if vp else sorted(d.rglob("*clean_respiratory_data*_markers.csv"))[0]
        try:
            bio = ca.load_biometrics(bio_path); ver = ca.load_vernier(ver_path)
        except Exception:
            continue
        fs = ca.estimate_fs(ver["t_ms"].to_numpy())
        breaths = ca.flag_breath_stress(ca.build_breaths(ver, fs))
        # period masks
        bio_em = bio["event_marker"].fillna("").to_numpy()
        bio_cond = bio["condition"].fillna("").to_numpy()
        ver_em = ver["event_marker"].fillna("").to_numpy()
        ver_cond = ver["condition"].fillna("").to_numpy()
        # subject-level EDA winsor bounds
        eda = bio["eda_us"].to_numpy(); ok = np.isfinite(eda) & (eda >= ca.EDA_MIN) & (eda <= ca.EDA_MAX)
        lo, hi = (np.nanpercentile(eda[ok], [5, 95]) if ok.sum() else (np.nan, np.nan))

        for period in ("stressor", "room"):
            if period == "stressor":
                bm = np.isin(bio_em, list(STRESSOR)); vm = np.isin(ver_em, list(STRESSOR))
                if len(breaths):
                    bc = breaths[breaths["event_marker"].isin(STRESSOR)]
            else:
                bm = np.isin(bio_cond, list(ROOM_COND)); vm = np.isin(ver_cond, list(ROOM_COND))
                if len(breaths):
                    bc = breaths[breaths["condition"].isin(ROOM_COND)]
            if not len(breaths):
                bc = breaths
            e = eda[bm]; e = e[np.isfinite(e) & (e >= ca.EDA_MIN) & (e <= ca.EDA_MAX)]
            if np.isfinite(lo): e = np.clip(e, lo, hi)
            hrv = ca.hrv_for(bio["bi_ms"].to_numpy()[bm])
            dev_rr = ver["resp_rate"].to_numpy()[vm]
            dev_rr = dev_rr[np.isfinite(dev_rr) & (dev_rr >= 4) & (dev_rr <= 60)]
            nb = len(bc)
            rows.append({
                "subject": s, "period": period,
                "eda_tonic_us": round(float(np.mean(e)), 4) if len(e) else None,
                "rmssd_ms": hrv["rmssd_ms"], "sdnn_ms": hrv["sdnn_ms"],
                "hrv_valid": hrv["hrv_valid"], "corrected_fraction": hrv["corrected_fraction"],
                "mean_resp_rate_bpm": round(float(np.mean(dev_rr)), 2) if len(dev_rr) else (
                    round(float(bc["rate_bpm"].mean()), 2) if nb else None),
                "n_breaths": int(nb),
                "resp_stress_index": round(float(bc["any_stress"].mean()), 4) if nb else None,
                "resp_stress_weighted": round(float(bc["weighted_stress"].mean()), 4) if nb else None,
                **{f"pat_{p}": int(bc[f"f_{p}"].sum()) if nb else 0 for p in PATTERNS},
            })
    return pd.DataFrame(rows)


def wide(d, m, valid=False):
    df = d[d.hrv_valid == True] if valid else d  # noqa: E712
    p = df.pivot_table(index="subject", columns="period", values=m, aggfunc="first")
    return p.dropna(subset=[c for c in ("stressor", "room") if c in p.columns])


MEAS = [("eda_tonic_us", "EDA tonic (µS)\nhigher = more stress"),
        ("mean_resp_rate_bpm", "Respiration rate (bpm)\nhigher = more stress"),
        ("resp_stress_weighted", "Resp. stress scale (weighted)\nexperimental"),
        ("rmssd_ms", "RMSSD (ms) — valid HRV only\nlower = more stress")]


def main():
    d = main_measure()
    d.to_csv(OUT / "per_subject_period.csv", index=False)

    # Table: per-subject means already per period; comparison table (paired)
    comp = []
    for m, label in [("eda_tonic_us", "EDA tonic (µS)"), ("mean_resp_rate_bpm", "Respiration rate (bpm)"),
                     ("resp_stress_index", "Resp stress index (exp)"),
                     ("resp_stress_weighted", "Resp stress weighted (exp)"),
                     ("rmssd_ms", "RMSSD (ms, valid only)")]:
        p = wide(d, m, valid=(m == "rmssd_ms"))
        if not {"stressor", "room"}.issubset(p.columns) or len(p) < 3:
            continue
        a, b = p["stressor"].to_numpy(), p["room"].to_numpy(); diff = a - b; n = len(diff)
        dz = float(diff.mean() / diff.std(ddof=1)) if diff.std(ddof=1) > 0 else np.nan
        ci = sp.t.interval(0.95, n - 1, loc=diff.mean(), scale=sp.sem(diff))
        try: w = sp.wilcoxon(a, b).pvalue
        except Exception: w = np.nan
        comp.append({"measure": label, "n": n, "mean_stressor": round(float(a.mean()), 3),
                     "mean_room": round(float(b.mean()), 3), "mean_diff": round(float(diff.mean()), 3),
                     "ci95_low": round(ci[0], 3), "ci95_high": round(ci[1], 3), "cohens_dz": round(dz, 3),
                     "paired_t_p": round(float(sp.ttest_rel(a, b).pvalue), 4), "wilcoxon_p": round(float(w), 4),
                     "pct_stressor_higher": round(float((a > b).mean()) * 100, 1)})
    comp_df = pd.DataFrame(comp); comp_df.to_csv(OUT / "table_stressor_vs_room.csv", index=False)
    d.groupby(["subject"]).apply(lambda x: x).to_csv(OUT / "per_subject_period_full.csv", index=False)

    # Figure 1 — paired slopes
    plt.rcParams.update({"figure.dpi": 130, "font.size": 10, "axes.grid": True, "grid.alpha": 0.25})
    RED, BLUE = "#C0392B", "#2C7FB8"
    fig, axes = plt.subplots(1, 4, figsize=(17, 5))
    for ax, (m, title) in zip(axes, MEAS):
        p = wide(d, m, valid=(m == "rmssd_ms"))
        if not {"stressor", "room"}.issubset(p.columns) or len(p) == 0:
            ax.set_visible(False); continue
        for _, r in p.iterrows():
            up = r["stressor"] > r["room"] if m != "rmssd_ms" else r["stressor"] < r["room"]
            ax.plot([0, 1], [r["room"], r["stressor"]], "-o", color=RED if up else BLUE, alpha=0.55, ms=4, lw=1.2)
        ax.plot([0, 1], [p["room"].mean(), p["stressor"].mean()], "-s", color="black", lw=2.6, ms=8, label="group mean")
        ax.set_xticks([0, 1]); ax.set_xticklabels(["Room", "Stressor"]); ax.set_xlim(-0.3, 1.3)
        ax.set_title(title, fontsize=10); ax.legend(fontsize=8)
    fig.suptitle("Stressor vs Room — within-subject paired change (red = higher arousal in stressor, as expected)",
                 fontsize=13, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.95]); fig.savefig(OUT / "fig1_paired_measures.png", bbox_inches="tight"); plt.close(fig)

    # Figure 2 — effect sizes
    fig, ax = plt.subplots(figsize=(9, 4.5)); y = np.arange(len(comp_df))[::-1]
    for i, (_, r) in zip(y, comp_df.iterrows()):
        half = 1.96 / np.sqrt(r["n"])
        ax.plot([r["cohens_dz"] - half, r["cohens_dz"] + half], [i, i], color="#444", lw=2)
        ax.plot(r["cohens_dz"], i, "o", color="#C0392B", ms=8)
    ax.axvline(0, color="gray", ls="--"); ax.set_yticks(y)
    ax.set_yticklabels([f"{r['measure']} (n={r['n']})" for _, r in comp_df.iterrows()])
    ax.set_xlabel("Within-subject Cohen's dz  (positive = higher in stressor)")
    ax.set_title("Stressor − Room effect sizes (paired)", fontweight="bold")
    fig.tight_layout(); fig.savefig(OUT / "fig2_effect_sizes.png", bbox_inches="tight"); plt.close(fig)

    # Figure 3 — pattern heatmap per period (difference stressor-room)
    hp_s = d[d.period == "stressor"].set_index("subject")[[f"pat_{p}" for p in PATTERNS]]
    hp_r = d[d.period == "room"].set_index("subject")[[f"pat_{p}" for p in PATTERNS]]
    common = hp_s.index.intersection(hp_r.index)
    diff = (hp_s.loc[common] - hp_r.loc[common])
    fig, ax = plt.subplots(figsize=(9, 7))
    vmax = float(np.nanmax(np.abs(diff.to_numpy()))) or 1
    im = ax.imshow(diff.to_numpy(), aspect="auto", cmap="RdBu_r", vmin=-vmax, vmax=vmax)
    ax.set_xticks(range(len(PATTERNS))); ax.set_xticklabels(PATTERNS, rotation=40, ha="right")
    ax.set_yticks(range(len(common))); ax.set_yticklabels(common, fontsize=8)
    for i in range(len(common)):
        for j in range(len(PATTERNS)):
            ax.text(j, i, int(diff.to_numpy()[i, j]), ha="center", va="center", fontsize=7)
    fig.colorbar(im, ax=ax, label="stressor − room breath count")
    ax.set_title("Respiratory pattern counts: Stressor minus Room (red = more in stressor)", fontweight="bold")
    fig.tight_layout(); fig.savefig(OUT / "fig3_pattern_diff_heatmap.png", bbox_inches="tight"); plt.close(fig)

    print("Wrote stressor-vs-room outputs to", OUT)
    print(comp_df.to_string(index=False))


if __name__ == "__main__":
    main()

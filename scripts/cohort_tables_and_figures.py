#!/usr/bin/env python3
"""Build cohort tables, within-subject normalization, plant vs no-plant stats,
and revealing figures from per_subject_condition.csv.

Within-subject normalization: each measure is expressed relative to the
subject's own two-condition mean, so between-subject level differences (large in
EDA/HRV) are removed before pooling. The plant–no_plant contrast is therefore a
paired, within-subject difference.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy import stats as sp

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
    "/sessions/friendly-charming-hamilton/mnt/outputs/cohort")
d = pd.read_csv(OUT / "per_subject_condition.csv")

MEASURES = [
    ("eda_tonic_us", "EDA tonic (µS)", "lower = calmer", None),
    ("mean_resp_rate_bpm", "Respiration rate (bpm)", "lower = calmer", None),
    ("resp_stress_index", "Resp. stress index (frac)", "lower = calmer", "experimental"),
    ("resp_stress_weighted", "Resp. stress (weighted)", "lower = calmer", "experimental"),
    ("rmssd_ms", "RMSSD (ms, HRV)", "higher = calmer", "valid HRV only"),
]
PATTERNS = ["tachypnea", "ie_shift", "inverted_ie", "shallow", "irregular", "sigh", "apnea"]


def wide(measure: str, valid_only: bool = False) -> pd.DataFrame:
    df = d.copy()
    if valid_only:
        df = df[df["hrv_valid"] == True]  # noqa: E712
    p = df.pivot_table(index="subject", columns="condition", values=measure, aggfunc="first")
    return p.dropna(subset=[c for c in ("plants", "no_plants") if c in p.columns])


# ── Table 1: per-subject whole-session means (broad table) ───────────────────
sess = d.groupby("subject").agg(
    eda_tonic_us=("eda_tonic_us", "mean"),
    rmssd_ms=("rmssd_ms", lambda s: s[d.loc[s.index, "hrv_valid"]].mean()),
    hrv_valid_any=("hrv_valid", "any"),
    mean_resp_rate_bpm=("mean_resp_rate_bpm", "mean"),
    resp_stress_index=("resp_stress_index", "mean"),
    resp_stress_weighted=("resp_stress_weighted", "mean"),
    n_breaths=("n_breaths", "sum"),
).round(3).reset_index()
sess.to_csv(OUT / "table1_per_subject_means.csv", index=False)

# ── Table 2: within-subject normalized + paired diffs ────────────────────────
norm_rows = []
for measure, label, _, _ in MEASURES:
    p = wide(measure, valid_only=(measure == "rmssd_ms"))
    if not {"plants", "no_plants"}.issubset(p.columns):
        continue
    for subj, r in p.iterrows():
        own_mean = (r["plants"] + r["no_plants"]) / 2.0
        norm_rows.append({"subject": subj, "measure": measure,
                          "plants": r["plants"], "no_plants": r["no_plants"],
                          "diff_plant_minus_noplant": round(r["plants"] - r["no_plants"], 4),
                          "plants_centered": round(r["plants"] - own_mean, 4),
                          "no_plants_centered": round(r["no_plants"] - own_mean, 4)})
pd.DataFrame(norm_rows).to_csv(OUT / "table2_within_subject_normalized.csv", index=False)

# ── Table 3: plant vs no-plant cohort comparison (paired) ────────────────────
comp = []
for measure, label, direction, note in MEASURES:
    p = wide(measure, valid_only=(measure == "rmssd_ms"))
    if not {"plants", "no_plants"}.issubset(p.columns) or len(p) < 3:
        continue
    a = p["plants"].to_numpy(); b = p["no_plants"].to_numpy()
    diff = a - b
    n = len(diff)
    dz = float(diff.mean() / diff.std(ddof=1)) if diff.std(ddof=1) > 0 else np.nan
    t_p = sp.ttest_rel(a, b).pvalue
    try:
        w_p = sp.wilcoxon(a, b).pvalue
    except Exception:
        w_p = np.nan
    ci = sp.t.interval(0.95, n - 1, loc=diff.mean(), scale=sp.sem(diff)) if n > 1 else (np.nan, np.nan)
    comp.append({"measure": measure, "label": label, "direction": direction, "note": note or "",
                 "n_subjects": n,
                 "mean_plants": round(float(a.mean()), 3), "mean_no_plants": round(float(b.mean()), 3),
                 "mean_diff": round(float(diff.mean()), 3),
                 "ci95_low": round(ci[0], 3), "ci95_high": round(ci[1], 3),
                 "cohens_dz": round(dz, 3),
                 "paired_t_p": round(float(t_p), 4), "wilcoxon_p": round(float(w_p), 4),
                 "pct_plants_lower": round(float((a < b).mean()) * 100, 1)})
comp_df = pd.DataFrame(comp)
comp_df.to_csv(OUT / "table3_plant_vs_noplant.csv", index=False)

# ── Table 4: respiratory pattern counts per subject × condition ──────────────
patt = d[["subject", "condition"] + [f"pat_{p}" for p in PATTERNS]].copy()
patt.to_csv(OUT / "table4_resp_pattern_counts.csv", index=False)

# ════════════════════════ FIGURES ════════════════════════
plt.rcParams.update({"figure.dpi": 130, "font.size": 10, "axes.grid": True, "grid.alpha": 0.25})
GREEN, GREY = "#2E8B57", "#B0651F"

# Figure 1 — paired slope plots for the key measures
keymeas = [("eda_tonic_us", "EDA tonic (µS)\nlower = calmer"),
           ("mean_resp_rate_bpm", "Respiration rate (bpm)\nlower = calmer"),
           ("resp_stress_weighted", "Resp. stress scale (weighted)\nexperimental"),
           ("rmssd_ms", "RMSSD (ms) — valid HRV only")]
fig, axes = plt.subplots(1, 4, figsize=(17, 5))
for ax, (m, title) in zip(axes, keymeas):
    p = wide(m, valid_only=(m == "rmssd_ms"))
    if not {"plants", "no_plants"}.issubset(p.columns) or len(p) == 0:
        ax.set_visible(False); continue
    for _, r in p.iterrows():
        improve = r["plants"] < r["no_plants"] if m != "rmssd_ms" else r["plants"] > r["no_plants"]
        ax.plot([0, 1], [r["no_plants"], r["plants"]], "-o", color=GREEN if improve else GREY,
                alpha=0.55, ms=4, lw=1.2)
    ax.plot([0, 1], [p["no_plants"].mean(), p["plants"].mean()], "-s", color="black", lw=2.6, ms=8,
            label="group mean")
    ax.set_xticks([0, 1]); ax.set_xticklabels(["No plants", "Plants"])
    ax.set_title(title, fontsize=10); ax.set_xlim(-0.3, 1.3)
    ax.legend(fontsize=8, loc="best")
fig.suptitle("Plant vs No-Plant — within-subject paired change (green = lower arousal/calmer in plants)",
             fontsize=13, fontweight="bold")
fig.tight_layout(rect=[0, 0, 1, 0.95])
fig.savefig(OUT / "fig1_paired_measures.png", bbox_inches="tight"); plt.close(fig)

# Figure 2 — forest plot of standardized within-subject effects (Cohen's dz)
fig, ax = plt.subplots(figsize=(9, 4.5))
cc = comp_df.copy()
# standardized effect with CI in dz units
y = np.arange(len(cc))[::-1]
for i, (_, r) in zip(y, cc.iterrows()):
    sd = (r["ci95_high"] - r["ci95_low"]) / (2 * 1.96) if r["ci95_high"] == r["ci95_high"] else np.nan
    dz = r["cohens_dz"]
    # CI of dz approx: dz ± 1.96/sqrt(n)
    half = 1.96 / np.sqrt(r["n_subjects"])
    ax.plot([dz - half, dz + half], [i, i], color="#444", lw=2)
    ax.plot(dz, i, "o", color="#1f77b4", ms=8)
ax.axvline(0, color="red", ls="--", lw=1)
ax.set_yticks(y); ax.set_yticklabels([f"{r['label']}  (n={r['n_subjects']})" for _, r in cc.iterrows()])
ax.set_xlabel("Within-subject effect size, Cohen's dz  (negative = lower in plants)")
ax.set_title("Plant − No-plant effect sizes (paired)", fontweight="bold")
fig.tight_layout(); fig.savefig(OUT / "fig2_effect_sizes.png", bbox_inches="tight"); plt.close(fig)

# Figure 3 — respiratory pattern heatmap (subject × pattern, summed over conditions)
hp = d.groupby("subject")[[f"pat_{p}" for p in PATTERNS]].sum()
fig, ax = plt.subplots(figsize=(9, 7))
im = ax.imshow(hp.to_numpy(), aspect="auto", cmap="YlOrRd")
ax.set_xticks(range(len(PATTERNS))); ax.set_xticklabels(PATTERNS, rotation=40, ha="right")
ax.set_yticks(range(len(hp))); ax.set_yticklabels(hp.index, fontsize=8)
for i in range(len(hp)):
    for j in range(len(PATTERNS)):
        ax.text(j, i, int(hp.to_numpy()[i, j]), ha="center", va="center", fontsize=7,
                color="black")
fig.colorbar(im, ax=ax, label="breath count")
ax.set_title("Respiratory stress-pattern counts per subject (experimental)", fontweight="bold")
fig.tight_layout(); fig.savefig(OUT / "fig3_pattern_heatmap.png", bbox_inches="tight"); plt.close(fig)

# Figure 4 — resp stress scale by condition, paired
fig, ax = plt.subplots(figsize=(7, 5))
p = wide("resp_stress_weighted")
for _, r in p.iterrows():
    ax.plot([0, 1], [r["no_plants"], r["plants"]],
            "-o", color=GREEN if r["plants"] < r["no_plants"] else GREY, alpha=0.6, ms=4)
ax.plot([0, 1], [p["no_plants"].mean(), p["plants"].mean()], "-s", color="black", lw=2.6, ms=9,
        label="group mean")
ax.set_xticks([0, 1]); ax.set_xticklabels(["No plants", "Plants"]); ax.set_xlim(-0.3, 1.3)
ax.set_ylabel("Weighted respiratory stress scale"); ax.legend()
ax.set_title("Respiratory stress scale by condition (experimental)", fontweight="bold")
fig.tight_layout(); fig.savefig(OUT / "fig4_resp_stress_scale.png", bbox_inches="tight"); plt.close(fig)

print("Wrote tables 1-4 and figures 1-4 to", OUT)
print("\n=== Plant vs No-plant summary ===")
print(comp_df[["label", "n_subjects", "mean_diff", "cohens_dz", "paired_t_p", "wilcoxon_p", "pct_plants_lower"]].to_string(index=False))

#!/usr/bin/env python3
"""SART (Sustained Attention to Response Task) analysis.

Per-run metrics from a trial-level file, and the biophilic-vs-control comparison
from the summary file. SART = high-Go / low-No-Go (target digit 3 withheld).

Metrics (Robertson et al., 1997; Helton, 2009; Wilson et al., 2016):
  commission error rate = 1 - nogo_accuracy   (responding to a No-Go; the primary
                                                sustained-attention/inhibition lapse)
  omission error rate   = 1 - go_accuracy      (missing a Go; usually rare)
  mean RT (correct Go), RT SD, RT CV           (RT variability indexes attention)
Speed-accuracy tradeoff: faster RT ↔ more commission errors, so RT and errors
must be read together — slowing is not the same as better attention.

Design: SART1 (pre-stressor), SART2 (post-stressor), SART3 (post-room1),
SART4/5 (pre/post-stressor cond2), SART6 (post-room2). Each subject has one
Plants and one No-Plants post-room SART (counterbalanced across SART3/SART6).
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np, pandas as pd
from scipy import stats as sp

ROOT = Path("/sessions/friendly-charming-hamilton/mnt/Polar_Emotibit_Analyzer/Estelita/SART/granny-green")
OUT = Path("/sessions/friendly-charming-hamilton/mnt/outputs/sart"); OUT.mkdir(parents=True, exist_ok=True)


def per_run(trial_csv: Path) -> dict:
    d = pd.read_csv(trial_csv, encoding="utf-8-sig")
    d = d[pd.to_numeric(d["trial"], errors="coerce").notna()].copy()
    d["is_target"] = d["is_target"].astype(str).str.lower().eq("true")
    d["correct"] = d["correct"].astype(str).str.lower().eq("true")
    d["rt"] = pd.to_numeric(d["rt"], errors="coerce")
    go, nogo = d[~d.is_target], d[d.is_target]
    gc = go[go.correct & go.rt.notna()]
    return {
        "file": trial_csv.name, "n_trials": len(d), "n_go": len(go), "n_nogo": len(nogo),
        "go_accuracy": round(go.correct.mean(), 4),
        "omission_err_rate": round(1 - go.correct.mean(), 4),
        "nogo_accuracy": round(nogo.correct.mean(), 4),
        "commission_err_rate": round(1 - nogo.correct.mean(), 4),
        "mean_rt_s": round(gc.rt.mean(), 4), "rt_sd_s": round(gc.rt.std(), 4),
        "rt_cv": round(gc.rt.std() / gc.rt.mean(), 4) if gc.rt.mean() else None,
    }


def comparison(summary_csv: Path):
    s = pd.read_csv(summary_csv)
    acc = s.pivot_table(index="participant", columns="task", values="nogo_accuracy")
    rt = s.pivot_table(index="participant", columns="task", values="mean_rt")
    room = s[s.task.isin(["SART3", "SART6"])].pivot_table(
        index="participant", columns="task", values="room_condition", aggfunc="first")
    pre = {"SART3": "SART2", "SART6": "SART5"}

    def collect(piv):
        rows = []
        for pid in piv.index:
            rc = {t: (room.loc[pid, t] if t in room.columns else None) for t in ("SART3", "SART6")}
            pt = next((t for t in ("SART3", "SART6") if rc[t] == "Plants"), None)
            nt = next((t for t in ("SART3", "SART6") if rc[t] == "No Plants"), None)
            if not pt or not nt:
                continue
            v = lambda t: piv.loc[pid, t] if t in piv.columns else np.nan
            rows.append(dict(participant=pid, plants_post=v(pt), noplants_post=v(nt),
                             plants_restore=v(pt) - v(pre[pt]), noplants_restore=v(nt) - v(pre[nt])))
        return pd.DataFrame(rows)

    out = []
    for name, piv in [("nogo_accuracy", acc), ("mean_rt", rt)]:
        c = collect(piv)
        for a, b, lab in [("plants_post", "noplants_post", "post-room"),
                          ("plants_restore", "noplants_restore", "restoration")]:
            x = c[[a, b]].dropna()
            if len(x) < 3:
                continue
            da, db = x[a].to_numpy(), x[b].to_numpy(); diff = da - db
            dz = diff.mean() / diff.std(ddof=1) if diff.std(ddof=1) > 0 else np.nan
            try: w = sp.wilcoxon(da, db).pvalue
            except Exception: w = np.nan
            out.append({"measure": name, "contrast": lab, "n": len(x),
                        "plants": round(float(da.mean()), 3), "no_plants": round(float(db.mean()), 3),
                        "diff": round(float(diff.mean()), 3), "cohens_dz": round(dz, 2),
                        "paired_t_p": round(float(sp.ttest_rel(da, db).pvalue), 3),
                        "wilcoxon_p": round(float(w), 3)})
    # stressor validity SART1->SART2
    val = []
    for name, piv in [("nogo_accuracy", acc), ("mean_rt", rt)]:
        x = piv[["SART1", "SART2"]].dropna()
        val.append({"measure": name, "SART1": round(float(x.SART1.mean()), 3),
                    "SART2": round(float(x.SART2.mean()), 3),
                    "diff_post_minus_pre": round(float((x.SART2 - x.SART1).mean()), 3),
                    "paired_t_p": round(float(sp.ttest_rel(x.SART2, x.SART1).pvalue), 3), "n": len(x)})
    return pd.DataFrame(out), pd.DataFrame(val)


if __name__ == "__main__":
    f = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data/SART_yajin@ucsd.edu_6_2025-12-15.csv"
    pr = per_run(f)
    pd.DataFrame([pr]).to_csv(OUT / "single_run_metrics.csv", index=False)
    comp, val = comparison(ROOT / "sart_summary_data.csv")
    comp.to_csv(OUT / "biophilic_vs_control.csv", index=False)
    val.to_csv(OUT / "stressor_validity.csv", index=False)
    print("=== single run ==="); [print(f"  {k}: {v}") for k, v in pr.items()]
    print("\n=== biophilic vs control ===\n", comp.to_string(index=False))
    print("\n=== stressor validity (SART1→2) ===\n", val.to_string(index=False))
    print("\nWrote ->", OUT)

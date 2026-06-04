#!/usr/bin/env python3
# RespInPeace analysis of the Estelita Vernier respiration-belt recording.
#
# REPRODUCIBILITY NOTES
# - rip.py and peakdetect.py in this folder are the RespInPeace toolkit
#   (Wlodarczak, 2019) with minor compatibility patches for modern NumPy/SciPy
#   (np.int -> int, np.Inf -> np.inf, scipy.fft import). The upstream 2020 code
#   does not run unmodified on NumPy >= 2.0.
# - Requires: pandas, numpy, scipy, matplotlib, openpyxl, tgt  (pip install tgt)
# - To re-run: place this script, rip.py, peakdetect.py and the raw .xlsx in one
#   folder, adjust XLSX below if needed, then:  python3 analyze.py

# RespInPeace analysis of Estelita Vernier respiration-belt data (v2)
import os, sys, json, time, warnings
from collections import Counter
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy import stats

HERE = os.path.dirname(os.path.abspath(__file__))

warnings.simplefilter("ignore")
sys.path.insert(0, HERE)
from rip import Resp

plt.rcParams.update({"font.size": 10, "axes.titlesize": 11, "axes.grid": True,
                     "grid.alpha": 0.25, "axes.spines.top": False,
                     "axes.spines.right": False, "figure.facecolor": "white",
                     "savefig.facecolor": "white"})

XLSX = os.path.join(HERE, "Estelita_Vernier Belt_Raw Respiratory Data_Sub ID_1.13_G2.xlsx")
OUT  = os.path.join(HERE, "results")
os.makedirs(OUT, exist_ok=True)
STATUS = os.path.join(OUT, "run_log.txt")
open(STATUS, "w").write("")
def log(m):
    with open(STATUS, "a") as f: f.write(m + "\n")
    print(m, flush=True)

try:
    # ================= Load =================
    log("Loading Excel ...")
    df = pd.read_excel(XLSX, sheet_name=0, header=0)
    t = df["timestamp_unix"].astype(float).values
    t0 = float(t[0]); elapsed = t - t0
    force = df["force"].astype(float).values
    ev = df["event_marker"].values; cond = df["condition"].values
    orig_ts = pd.to_datetime(df["timestamp"])
    dur = float(elapsed[-1])
    log(f"  N={len(df)}  duration={dur/60:.2f} min")

    # ================= Resample =================
    FS = 20
    tu = np.arange(0.0, dur, 1.0/FS)
    force_u = np.interp(tu, elapsed, force)
    N = len(force_u)
    log(f"Resampled to {FS} Hz uniform grid ({N} samples)")

    # ================= RespInPeace pipeline =================
    resp = Resp(force_u, FS)
    _t = time.time(); resp.remove_baseline(method="als")
    log(f"ALS baseline removal: {time.time()-_t:.1f}s")
    resp.find_cycles(include_holds=True)
    log(f"find_cycles: {len(resp.segments)} segments, {len(resp.holds)} holds")
    rel = resp.estimate_rel(method="dynamic")
    resp.samples = resp.samples - rel
    resp.estimate_range()
    sig_proc = resp.samples.copy()
    log(f"range={resp.range:.3f}")
    try:
        resp.save_annotations(os.path.join(OUT, "Estelita_resp_annotations.TextGrid"),
                              tiers=["cycles", "holds"])
    except Exception as e:
        log(f"TextGrid skipped: {e}")

    # ================= Helpers =================
    def orig_idx(tsec):
        i = int(np.searchsorted(elapsed, tsec))
        return min(max(i, 0), len(elapsed)-1)
    def mode_str(a):
        v = [x for x in a if isinstance(x, str) and x != ""]
        return Counter(v).most_common(1)[0][0] if v else "unmarked"
    def collapse(m):
        if not isinstance(m, str): return "unmarked"
        if m.startswith("prs_1"): return "prs_1"
        if m.startswith("prs_2"): return "prs_2"
        return m

    # ================= Per-breath features =================
    seg = resp.segments; ncyc = len(seg)//2
    rows = []
    for k in range(ncyc):
        ins, outs = seg[2*k], seg[2*k+1]
        tr1, pk, tr2 = ins.start_time, ins.end_time, outs.end_time
        inhale, exhale, cyc = pk-tr1, tr2-pk, tr2-tr1
        if cyc <= 0: continue
        f_in  = resp.extract_features(tr1, pk, norm=True)
        f_out = resp.extract_features(pk, tr2, norm=True)
        f_in_r = resp.extract_features(tr1, pk, norm=False)
        i0 = orig_idx(tr1); i1 = max(orig_idx(tr2), i0+1)
        marker = mode_str(ev[i0:i1]); condition = mode_str(cond[i0:i1])
        hs = resp.holds.get_annotations_between_timepoints(tr1, tr2,
                left_overlap=True, right_overlap=True)
        hold_dur = sum(min(h.end_time,tr2)-max(h.start_time,tr1) for h in hs) if hs else 0.0
        rows.append(dict(
            breath=k+1, clock=str(orig_ts.iloc[i0]),
            start_s=round(tr1,3), peak_s=round(pk,3), end_s=round(tr2,3),
            inhale_dur_s=round(inhale,3), exhale_dur_s=round(exhale,3),
            cycle_dur_s=round(cyc,3), rate_bpm=round(60.0/cyc,3),
            ie_ratio=round(inhale/exhale,4) if exhale>0 else np.nan,
            duty_cycle=round(inhale/cyc,4),
            inhale_amp_norm=round(f_in["amplitude"],4),
            exhale_amp_norm=round(f_out["amplitude"],4),
            inhale_amp_raw=round(f_in_r["amplitude"],4),
            inhale_slope_norm=round(f_in["slope"],4),
            exhale_slope_norm=round(f_out["slope"],4),
            onset_level=round(f_in["onset_level"],4),
            peak_level=round(f_in["offset_level"],4),
            offset_level=round(f_out["offset_level"],4),
            n_holds=len(hs), hold_dur_s=round(hold_dur,3),
            event_marker=marker, phase=collapse(marker), condition=condition))
    breaths = pd.DataFrame(rows)
    breaths.to_csv(os.path.join(OUT, "Estelita_per_breath_features.csv"), index=False)
    log(f"{len(breaths)} breaths tabulated")

    # ================= Holds table =================
    hrows = []
    for h in resp.holds:
        mid = (h.start_time + h.end_time)/2
        oi = orig_idx(mid)
        hrows.append(dict(
            start_s=round(h.start_time,3), end_s=round(h.end_time,3),
            dur_s=round(h.end_time-h.start_time,3),
            clock=str(orig_ts.iloc[oi]),
            event_marker=mode_str(ev[orig_idx(h.start_time):max(orig_idx(h.end_time),orig_idx(h.start_time)+1)]),
            phase=collapse(ev[oi] if isinstance(ev[oi],str) else None),
            condition=cond[oi] if isinstance(cond[oi],str) else "unmarked"))
    holds = pd.DataFrame(hrows)
    holds.to_csv(os.path.join(OUT, "Estelita_holds.csv"), index=False)

    # ================= Aggregation =================
    def summarize(g, hdf):
        span = float(g["end_s"].max()-g["start_s"].min())
        mc = float(g["cycle_dur_s"].mean())
        return dict(
            n_breaths=int(len(g)),
            span_min=round(span/60,2),
            mean_cycle_s=round(mc,3),
            sd_cycle_s=round(float(g["cycle_dur_s"].std()),3),
            resp_rate_bpm=round(60.0/mc,2),
            median_breath_bpm=round(float(g["rate_bpm"].median()),2),
            count_rate_bpm=round(len(g)/(span/60),2) if span>0 else float("nan"),
            mean_inhale_dur_s=round(float(g["inhale_dur_s"].mean()),3),
            mean_exhale_dur_s=round(float(g["exhale_dur_s"].mean()),3),
            ie_ratio_mean=round(float(g["ie_ratio"].mean()),3),
            duty_cycle_mean=round(float(g["duty_cycle"].mean()),3),
            inhale_amp_norm_mean=round(float(g["inhale_amp_norm"].mean()),4),
            n_holds=int(len(hdf)))

    phase_order = breaths.groupby("phase")["start_s"].min().sort_values().index.tolist()
    prows = []
    for ph in phase_order:
        g = breaths[breaths.phase == ph]
        hd = holds[holds.phase == ph]
        d = summarize(g, hd); d["phase"] = ph; prows.append(d)
    phase_summary = pd.DataFrame(prows).set_index("phase")
    phase_summary.to_csv(os.path.join(OUT, "Estelita_summary_by_phase.csv"))

    cond_order = [c for c in ["physical_no_plants","physical_plants","unmarked"]
                  if c in breaths["condition"].unique()]
    crows = []
    for c in cond_order:
        g = breaths[breaths.condition == c]
        hd = holds[holds.condition == c]
        d = summarize(g, hd); d["condition"] = c; crows.append(d)
    cond_summary = pd.DataFrame(crows).set_index("condition")
    cond_summary.to_csv(os.path.join(OUT, "Estelita_summary_by_condition.csv"))

    ct = pd.crosstab(breaths["phase"], breaths["condition"]).reindex(phase_order)
    ct.to_csv(os.path.join(OUT, "Estelita_phase_by_condition_crosstab.csv"))

    # ================= Plants vs no-plants stats =================
    pl  = breaths[breaths.condition == "physical_plants"]
    npl = breaths[breaths.condition == "physical_no_plants"]
    def cohen_d(a, b):
        na, nb = len(a), len(b)
        sp = np.sqrt(((na-1)*a.std()**2 + (nb-1)*b.std()**2)/(na+nb-2))
        return float((a.mean()-b.mean())/sp) if sp > 0 else float("nan")
    stat = {}
    if len(pl) > 2 and len(npl) > 2:
        tt_r = stats.ttest_ind(pl.rate_bpm, npl.rate_bpm, equal_var=False)
        mw_r = stats.mannwhitneyu(pl.rate_bpm, npl.rate_bpm, alternative="two-sided")
        tt_d = stats.ttest_ind(pl.cycle_dur_s, npl.cycle_dur_s, equal_var=False)
        mw_d = stats.mannwhitneyu(pl.cycle_dur_s, npl.cycle_dur_s, alternative="two-sided")
        stat = dict(
            plants_n=int(len(pl)), noplants_n=int(len(npl)),
            plants_resp_rate_bpm=round(60.0/pl.cycle_dur_s.mean(),2),
            noplants_resp_rate_bpm=round(60.0/npl.cycle_dur_s.mean(),2),
            plants_mean_cycle_s=round(float(pl.cycle_dur_s.mean()),3),
            noplants_mean_cycle_s=round(float(npl.cycle_dur_s.mean()),3),
            plants_median_breath_bpm=round(float(pl.rate_bpm.median()),2),
            noplants_median_breath_bpm=round(float(npl.rate_bpm.median()),2),
            cycle_dur_welch_t=round(float(tt_d.statistic),3),
            cycle_dur_welch_p=round(float(tt_d.pvalue),5),
            cycle_dur_mannwhitney_p=round(float(mw_d.pvalue),5),
            cycle_dur_cohens_d=round(cohen_d(pl.cycle_dur_s, npl.cycle_dur_s),3),
            rate_welch_t=round(float(tt_r.statistic),3),
            rate_welch_p=round(float(tt_r.pvalue),5),
            rate_mannwhitney_p=round(float(mw_r.pvalue),5),
            rate_cohens_d=round(cohen_d(pl.rate_bpm, npl.rate_bpm),3))

    # ================= RR-column validation =================
    rr = df["RR"].dropna(); rr = rr[(rr > 0) & (rr < 60)]
    rr_val = dict(
        file_RR_n=int(len(rr)),
        file_RR_median=round(float(rr.median()),2),
        file_RR_mean=round(float(rr.mean()),2),
        rip_count_rate_bpm=round(len(breaths)/(dur/60),2),
        rip_duration_rate_bpm=round(60.0/breaths.cycle_dur_s.mean(),2),
        rip_median_breath_bpm=round(float(breaths.rate_bpm.median()),2))

    summary = dict(
        subject="Estelita", source_file=os.path.basename(XLSX),
        recording_date=str(orig_ts.iloc[0])[:10],
        duration_min=round(dur/60,2), n_raw_samples=int(len(df)),
        resample_hz=FS, n_cycles=int(len(breaths)), n_holds=int(len(holds)),
        resp_rate_bpm_duration_based=round(60.0/breaths.cycle_dur_s.mean(),2),
        resp_rate_bpm_count_based=round(len(breaths)/(dur/60),2),
        median_breath_bpm=round(float(breaths.rate_bpm.median()),2),
        mean_cycle_dur_s=round(float(breaths.cycle_dur_s.mean()),3),
        sd_cycle_dur_s=round(float(breaths.cycle_dur_s.std()),3),
        ie_ratio_mean=round(float(breaths.ie_ratio.mean()),3),
        duty_cycle_mean=round(float(breaths.duty_cycle.mean()),3),
        resp_range=round(float(resp.range),4),
        plants_vs_noplants=stat, rr_validation=rr_val)
    json.dump(summary, open(os.path.join(OUT, "Estelita_summary.json"), "w"), indent=2)

    # ================= Figures =================
    # Fig 1: overview + zoom
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(11, 7))
    a1.plot(tu/60.0, sig_proc, lw=0.35, color="#33548e")
    a1.axhline(0, color="grey", lw=0.6, ls="--")
    a1.set_title("Processed respiratory signal — full session (REL-corrected)")
    a1.set_xlabel("Time (min)"); a1.set_ylabel("Belt signal (a.u.)")
    z0, z1 = 900.0, 990.0
    m = (tu >= z0) & (tu <= z1)
    a2.plot(tu[m], sig_proc[m], color="#33548e", lw=1.1)
    pk_a, tr_a = resp.peaks, resp.troughs
    pkz = pk_a[(pk_a >= z0) & (pk_a <= z1)]; trz = tr_a[(tr_a >= z0) & (tr_a <= z1)]
    if len(pkz): a2.plot(pkz, resp.idt[pkz], "o", color="#c0504d", ms=5, label="peak (end of inhalation)")
    if len(trz): a2.plot(trz, resp.idt[trz], "o", color="#4f8a4f", ms=5, label="trough (end of exhalation)")
    for h in resp.holds:
        if h.end_time >= z0 and h.start_time <= z1:
            a2.axvspan(h.start_time, h.end_time, color="#e8c33a", alpha=0.4)
    a2.set_title(f"Detail: {z0:.0f}-{z1:.0f} s — detected cycles; breath-holds shaded")
    a2.set_xlabel("Time (s)"); a2.set_ylabel("Belt signal (a.u.)")
    a2.legend(loc="upper right", fontsize=8)
    fig.tight_layout(); fig.savefig(os.path.join(OUT, "fig1_signal_overview.png"), dpi=150); plt.close(fig)

    # Fig 2: rate timeline
    fig, ax = plt.subplots(figsize=(12, 5.2))
    bt = breaths["start_s"]/60.0
    ax.plot(bt, breaths["rate_bpm"], ".", ms=3, color="#999", label="per-breath rate")
    roll = breaths["rate_bpm"].rolling(15, center=True, min_periods=3).median()
    ax.plot(bt, roll, "-", color="#33548e", lw=1.9, label="rolling median (15 breaths)")
    def runs(values, target):
        out, s = [], None
        for i, v in enumerate(values):
            if v == target and s is None: s = i
            elif v != target and s is not None:
                out.append((elapsed[s], elapsed[i-1])); s = None
        if s is not None: out.append((elapsed[s], elapsed[-1]))
        return out
    for a, b in runs(cond, "physical_plants"):
        ax.axvspan(a/60, b/60, color="#5fae5f", alpha=0.18)
    for a, b in runs(cond, "physical_no_plants"):
        ax.axvspan(a/60, b/60, color="#888888", alpha=0.18)
    prev = None; ytop = float(np.nanpercentile(breaths["rate_bpm"], 99))
    for _, r in breaths.iterrows():
        if r["phase"] != prev:
            ax.axvline(r["start_s"]/60, color="k", lw=0.4, alpha=0.3)
            ax.text(r["start_s"]/60, ytop, " "+str(r["phase"]), rotation=90,
                    fontsize=6, va="top", ha="left", color="#444")
            prev = r["phase"]
    ax.set_xlabel("Time (min)"); ax.set_ylabel("Respiratory rate (breaths/min)")
    ax.set_title("Respiratory rate across the session (green = plants, grey = no-plants windows)")
    ax.legend(loc="upper left", fontsize=8); ax.set_ylim(0, ytop*1.15)
    fig.tight_layout(); fig.savefig(os.path.join(OUT, "fig2_rate_timeline.png"), dpi=150); plt.close(fig)

    # Fig 3: rate by phase (duration-based)
    fig, ax = plt.subplots(figsize=(12, 5.2))
    x = np.arange(len(phase_summary))
    ax.bar(x, phase_summary["resp_rate_bpm"], color="#33548e", alpha=0.88)
    ax.set_xticks(x); ax.set_xticklabels(phase_summary.index, rotation=45, ha="right", fontsize=8)
    ax.set_ylabel("Respiratory rate (breaths/min)")
    ax.set_title("Respiratory rate by experimental phase  [rate = 60 / mean cycle duration]")
    for i in range(len(phase_summary)):
        ax.text(i, phase_summary["resp_rate_bpm"].iloc[i]+0.3,
                f"n={int(phase_summary['n_breaths'].iloc[i])}", ha="center", fontsize=6)
    fig.tight_layout(); fig.savefig(os.path.join(OUT, "fig3_rate_by_phase.png"), dpi=150); plt.close(fig)

    # Fig 4: plants vs no-plants
    if len(pl) > 2 and len(npl) > 2:
        fig, (a, b) = plt.subplots(1, 2, figsize=(11, 4.6))
        rates = [60.0/npl.cycle_dur_s.mean(), 60.0/pl.cycle_dur_s.mean()]
        a.bar([0,1], rates, color=["#888888","#5fae5f"], alpha=0.9)
        a.set_xticks([0,1]); a.set_xticklabels(["No plants","Plants"])
        a.set_ylabel("Respiratory rate (breaths/min)")
        a.set_title("Respiratory rate by condition\n[60 / mean cycle duration]")
        for i,v in enumerate(rates): a.text(i, v+0.2, f"{v:.1f}", ha="center", fontsize=9)
        data = [npl.cycle_dur_s.values, pl.cycle_dur_s.values]
        bp = b.boxplot(data, labels=["No plants","Plants"], patch_artist=True, showfliers=False)
        for patch,c in zip(bp["boxes"], ["#888888","#5fae5f"]):
            patch.set_facecolor(c); patch.set_alpha(0.6)
        b.set_ylabel("Respiratory cycle duration (s)")
        b.set_title("Cycle-duration distribution by condition")
        fig.tight_layout(); fig.savefig(os.path.join(OUT, "fig4_plants_vs_noplants.png"), dpi=150); plt.close(fig)

    log("ALL DONE")
    print("\n=== KEY NUMBERS ===")
    print(json.dumps(summary, indent=2))
except Exception as e:
    import traceback
    log("ERROR: " + str(e)); log(traceback.format_exc()); sys.exit(1)

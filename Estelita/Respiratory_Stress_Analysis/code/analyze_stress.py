#!/usr/bin/env python3
# Expanded respiratory STRESS analysis of a Vernier respiration-belt recording.
# Anonymised subject label: Sub-1.13_G2.
#
# REPRODUCIBILITY
# - rip.py / peakdetect.py in this folder are the RespInPeace toolkit
#   (Wlodarczak, 2019) patched for modern NumPy/SciPy.
# - Requires: pandas, numpy, scipy, matplotlib, openpyxl, tgt  (pip install tgt)
# - Place this script, rip.py, peakdetect.py and the raw .xlsx export in one
#   folder. Set XLSX below to the raw file name, then run:  python3 analyze_stress.py

import os, sys, json, warnings
HERE=os.path.dirname(os.path.abspath(__file__))
from collections import Counter
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy import stats, signal as sig
warnings.simplefilter("ignore")
sys.path.insert(0, HERE)
from rip import Resp

plt.rcParams.update({"font.size":10,"axes.titlesize":11,"axes.grid":True,
  "grid.alpha":0.25,"axes.spines.top":False,"axes.spines.right":False,
  "figure.facecolor":"white","savefig.facecolor":"white"})

XLSX = os.path.join(HERE, "raw_respiration.xlsx")  # <-- set to your raw Vernier-belt .xlsx
OUT  = os.path.join(HERE, "results"); os.makedirs(OUT, exist_ok=True)
PFX  = "Sub-1.13_G2_"
NAVY="1F3864"; STRESSCOL="#c0504d"
def log(m): print(m, flush=True)

# ================= Load + resample =================
log("Loading + resampling ...")
df = pd.read_excel(XLSX, sheet_name=0, header=0)
t = df["timestamp_unix"].astype(float).values; t0=float(t[0]); elapsed=t-t0
force = df["force"].astype(float).values
ev = df["event_marker"].values
orig_ts = pd.to_datetime(df["timestamp"])
dur = float(elapsed[-1])
FS = 20
tu = np.arange(0.0, dur, 1.0/FS)
force_u = np.interp(tu, elapsed, force)
N = len(force_u)

# ================= RespInPeace pipeline =================
log("RespInPeace pipeline ...")
resp = Resp(force_u, FS)
resp.remove_baseline(method="als")
resp.find_cycles(include_holds=True)
rel = resp.estimate_rel(method="dynamic")
resp.samples = resp.samples - rel
resp.estimate_range()
sig_proc = resp.samples.copy()
log(f"  cycles segs={len(resp.segments)} holds={len(resp.holds)}")

def orig_idx(s):
    i=int(np.searchsorted(elapsed,s)); return min(max(i,0),len(elapsed)-1)
def mode_str(a):
    v=[x for x in a if isinstance(x,str) and x!=""]
    return Counter(v).most_common(1)[0][0] if v else "unmarked"
def collapse(m):
    if not isinstance(m,str): return "unmarked"
    if m.startswith("prs_1"): return "prs_1"
    if m.startswith("prs_2"): return "prs_2"
    return m

# ================= Per-breath table =================
log("Per-breath features ...")
seg=resp.segments; ncyc=len(seg)//2; rows=[]
for k in range(ncyc):
    ins,outs=seg[2*k],seg[2*k+1]
    tr1,pk,tr2=ins.start_time,ins.end_time,outs.end_time
    inh,exh,cyc=pk-tr1,tr2-pk,tr2-tr1
    if cyc<=0: continue
    fi=resp.extract_features(tr1,pk,norm=True)
    fo=resp.extract_features(pk,tr2,norm=True)
    fir=resp.extract_features(tr1,pk,norm=False)
    i0=orig_idx(tr1); i1=max(orig_idx(tr2),i0+1)
    marker=mode_str(ev[i0:i1])
    hs=resp.holds.get_annotations_between_timepoints(tr1,tr2,left_overlap=True,right_overlap=True)
    hold_dur=sum(min(h.end_time,tr2)-max(h.start_time,tr1) for h in hs) if hs else 0.0
    rows.append(dict(breath=k+1,start_s=round(tr1,3),mid_s=round((tr1+tr2)/2,3),
        peak_s=round(pk,3),end_s=round(tr2,3),clock=str(orig_ts.iloc[i0]),
        inhale_dur_s=round(inh,3),exhale_dur_s=round(exh,3),cycle_dur_s=round(cyc,3),
        rate_bpm=round(60.0/cyc,3),ie_ratio=round(inh/exh,4) if exh>0 else np.nan,
        duty_cycle=round(inh/cyc,4),inhale_amp_norm=round(fi["amplitude"],4),
        exhale_amp_norm=round(fo["amplitude"],4),inhale_amp_raw=round(fir["amplitude"],5),
        inhale_slope_norm=round(fi["slope"],4),n_holds=len(hs),hold_dur_s=round(hold_dur,3),
        event_marker=marker,phase=collapse(marker)))
b=pd.DataFrame(rows)
NB=len(b)
log(f"  {NB} breaths")

# ================= Sigh detection (>= 2x local median inhalation amplitude) =================
log("Sigh detection ...")
amp=b["inhale_amp_raw"]
locmed=amp.rolling(21,center=True,min_periods=7).median()
b["amp_local_median"]=locmed.round(5)
b["amp_ratio"]=(amp/locmed).round(3)
b["is_sigh"]=((b["amp_ratio"]>=2.0)&(b["inhale_dur_s"]>=0.8)).astype(int)
n_artifact=int(((b["amp_ratio"]>=2.0)&(b["inhale_dur_s"]<0.8)).sum())
nsigh=int(b["is_sigh"].sum())
log(f"  {nsigh} sigh-like breaths (>=2x local median amp, inhale>=0.8s); "
    f"{n_artifact} short-duration large breaths excluded as likely artifact")

# ================= Windowed irregularity =================
log("Breath-cycle irregularity ...")
W=21
cyc=b["cycle_dur_s"]
b["cv_cycle_w"]=(cyc.rolling(W,center=True,min_periods=9).std()/
                 cyc.rolling(W,center=True,min_periods=9).mean()).round(4)
dd=cyc.diff().abs()
b["succ_diff_w"]=dd.rolling(W,center=True,min_periods=9).mean().round(4)
def ac1(x):
    x=np.asarray(x,float); x=x[~np.isnan(x)]
    if len(x)<6: return np.nan
    x0,x1=x[:-1],x[1:]
    if np.std(x0)==0 or np.std(x1)==0: return np.nan
    return np.corrcoef(x0,x1)[0,1]
b["autocorr1_w"]=cyc.rolling(W,center=True,min_periods=9).apply(ac1,raw=True).round(4)

# ================= Composite arousal index (heuristic: z-rate + z-irregularity) =================
zr=(b["rate_bpm"]-b["rate_bpm"].mean())/b["rate_bpm"].std()
zi=(b["cv_cycle_w"]-b["cv_cycle_w"].mean())/b["cv_cycle_w"].std()
b["arousal_index_z"]=((zr+zi)/2).round(4)
b.to_csv(f"{OUT}/{PFX}per_breath_features.csv",index=False)

# ================= Holds table =================
hrows=[]
for h in resp.holds:
    mid=(h.start_time+h.end_time)/2; oi=orig_idx(mid)
    hrows.append(dict(start_s=round(h.start_time,3),end_s=round(h.end_time,3),
        dur_s=round(h.end_time-h.start_time,3),clock=str(orig_ts.iloc[oi]),
        phase=collapse(ev[oi] if isinstance(ev[oi],str) else None)))
holds=pd.DataFrame(hrows)
holds.to_csv(f"{OUT}/{PFX}breath_holds.csv",index=False)

# ================= Sighs table + post-sigh reset =================
srows=[]
sigh_idx=b.index[b["is_sigh"]==1].tolist()
for k in sigh_idx:
    pre=b["cycle_dur_s"].iloc[max(0,k-10):k]
    post=b["cycle_dur_s"].iloc[k+1:k+11]
    pre_rate=b["rate_bpm"].iloc[max(0,k-10):k]
    post_rate=b["rate_bpm"].iloc[k+1:k+11]
    srows.append(dict(breath=int(b["breath"].iloc[k]),time_s=round(b["mid_s"].iloc[k],1),
        clock=b["clock"].iloc[k],phase=b["phase"].iloc[k],
        amp_ratio=b["amp_ratio"].iloc[k],
        inhale_dur_s=b["inhale_dur_s"].iloc[k],
        cv_cycle_pre=round(pre.std()/pre.mean(),4) if len(pre)>2 and pre.mean()>0 else np.nan,
        cv_cycle_post=round(post.std()/post.mean(),4) if len(post)>2 and post.mean()>0 else np.nan,
        rate_pre=round(pre_rate.mean(),2) if len(pre_rate)>0 else np.nan,
        rate_post=round(post_rate.mean(),2) if len(post_rate)>0 else np.nan))
sighs=pd.DataFrame(srows)
sighs.to_csv(f"{OUT}/{PFX}sighs.csv",index=False)

# ================= Respiratory phase (Hilbert) =================
log("Respiratory phase ...")
bb,ba=sig.butter(2,[0.08/(FS/2),0.6/(FS/2)],btype="band")
filt=sig.filtfilt(bb,ba,sig_proc)
analytic=sig.hilbert(filt)
resp_phase=np.angle(analytic)
ds=2  # downsample 20 -> 10 Hz
sigts=pd.DataFrame(dict(time_s=np.round(tu[::ds],3),
    signal_processed=np.round(sig_proc[::ds],5),
    resp_phase_rad=np.round(resp_phase[::ds],4)))
sigts.to_csv(f"{OUT}/{PFX}continuous_signals_10Hz.csv",index=False)

# ================= Per-phase stress-marker summary =================
log("Per-phase stress markers ...")
phase_order=b.groupby("phase")["start_s"].min().sort_values().index.tolist()
BASE="biometric_baseline"
def phase_rate(g): return 60.0/g["cycle_dur_s"].mean()
base_rate=phase_rate(b[b.phase==BASE])
base_amp=b[b.phase==BASE]["inhale_amp_raw"].mean()
base_cv=b[b.phase==BASE]["cycle_dur_s"].std()/b[b.phase==BASE]["cycle_dur_s"].mean()
prows=[]
for ph in phase_order:
    g=b[b.phase==ph]; span=(g["end_s"].max()-g["start_s"].min())/60
    hold_n=len(holds[holds.phase==ph]); sigh_n=int(g["is_sigh"].sum())
    rate=phase_rate(g); amp=g["inhale_amp_raw"].mean()
    cv=g["cycle_dur_s"].std()/g["cycle_dur_s"].mean()
    prows.append(dict(phase=ph,n_breaths=len(g),span_min=round(span,2),
        resp_rate_bpm=round(rate,2),rate_vs_baseline_pct=round(100*(rate/base_rate-1),1),
        mean_amplitude=round(amp,4),amp_vs_baseline_pct=round(100*(amp/base_amp-1),1),
        cv_cycle=round(cv,4),cv_vs_baseline_pct=round(100*(cv/base_cv-1),1),
        ie_ratio=round(g["ie_ratio"].mean(),3),duty_cycle=round(g["duty_cycle"].mean(),3),
        sigh_rate_per_min=round(sigh_n/span,3) if span>0 else 0,
        hold_rate_per_min=round(hold_n/span,3) if span>0 else 0,
        n_sighs=sigh_n,n_holds=hold_n,
        arousal_index_z=round(g["arousal_index_z"].mean(),3)))
phase_sum=pd.DataFrame(prows).set_index("phase")
phase_sum.to_csv(f"{OUT}/{PFX}stress_markers_by_phase.csv")

# ================= Windowed time series (60 s bins) =================
binw=60.0
nbin=int(np.ceil(dur/binw))
trows=[]
for i in range(nbin):
    lo,hi=i*binw,(i+1)*binw
    g=b[(b["mid_s"]>=lo)&(b["mid_s"]<hi)]
    if len(g)<2: continue
    trows.append(dict(t_start_min=round(lo/60,2),t_mid_min=round((lo+binw/2)/60,2),
        n_breaths=len(g),resp_rate_bpm=round(60.0/g["cycle_dur_s"].mean(),2),
        mean_amplitude=round(g["inhale_amp_raw"].mean(),4),
        cv_cycle=round(g["cycle_dur_s"].std()/g["cycle_dur_s"].mean(),4),
        ie_ratio=round(g["ie_ratio"].mean(),3),
        n_sighs=int(g["is_sigh"].sum()),
        arousal_index_z=round(g["arousal_index_z"].mean(),3)))
tser=pd.DataFrame(trows)
tser.to_csv(f"{OUT}/{PFX}timeseries_60s_bins.csv",index=False)

# ================= Recovery after stressors =================
log("Recovery dynamics ...")
stressors=["practice_stressor_test","stressor_test_1","stressor_test_2"]
rec_rows=[]
for st in stressors:
    g=b[b.phase==st]
    if len(g)==0: continue
    off=g["end_s"].max(); st_rate=60.0/g["cycle_dur_s"].mean()
    for bi in range(6):  # 6 x 60s post-stressor bins
        lo,hi=off+bi*60,off+(bi+1)*60
        gg=b[(b["mid_s"]>=lo)&(b["mid_s"]<hi)]
        if len(gg)<2: continue
        r=60.0/gg["cycle_dur_s"].mean()
        rec_rows.append(dict(stressor=st,stressor_rate_bpm=round(st_rate,2),
            bin_min_after=bi+1,resp_rate_bpm=round(r,2),
            elevation_over_baseline_bpm=round(r-base_rate,2)))
recovery=pd.DataFrame(rec_rows)
recovery.to_csv(f"{OUT}/{PFX}recovery_after_stressors.csv",index=False)

# ================= Event-locked rate =================
rate1=np.interp(np.arange(0,dur,1.0), b["mid_s"].values, b["rate_bpm"].values)
def locked(onsets,pre=60,post=150):
    M=[]
    for o in onsets:
        i0,i1=int(o-pre),int(o+post)
        if i0<0 or i1>=len(rate1): continue
        M.append(rate1[i0:i1])
    if not M: return None,None
    L=min(len(x) for x in M)
    M=np.array([x[:L] for x in M])
    return np.arange(-pre,-pre+L), M.mean(axis=0)
def onsets_for(phs):
    return [b[b.phase==p]["start_s"].min() for p in phs if (b.phase==p).any()]
st_x,st_y=locked(onsets_for(stressors))
sart_x,sart_y=locked(onsets_for([f"sart_{i}" for i in range(1,7)]))

# ================= Summary JSON =================
summ=dict(subject="Sub-1.13_G2",source_file="Vernier respiration-belt recording (Sub-1.13_G2)",
    recording_date=str(orig_ts.iloc[0])[:10],duration_min=round(dur/60,2),
    n_breaths=NB,n_holds=len(holds),n_sighs=nsigh,
    n_artifact_large_breaths_excluded=n_artifact,
    overall_resp_rate_bpm=round(60.0/b["cycle_dur_s"].mean(),2),
    overall_cv_cycle=round(b["cycle_dur_s"].std()/b["cycle_dur_s"].mean(),4),
    overall_ie_ratio=round(b["ie_ratio"].mean(),3),
    baseline_phase=BASE,baseline_rate_bpm=round(base_rate,2),
    sigh_rate_per_min_overall=round(nsigh/(dur/60),3),
    hold_rate_per_min_overall=round(len(holds)/(dur/60),3),
    post_sigh_cv_pre=round(float(sighs["cv_cycle_pre"].mean()),4) if len(sighs) else None,
    post_sigh_cv_post=round(float(sighs["cv_cycle_post"].mean()),4) if len(sighs) else None,
    highest_arousal_phase=phase_sum["arousal_index_z"].idxmax(),
    lowest_arousal_phase=phase_sum["arousal_index_z"].idxmin())
json.dump(summ,open(f"{OUT}/{PFX}summary.json","w"),indent=2)
log("DATA SAVED. Summary:")
log(json.dumps(summ,indent=2))

# ================= FIGURES =================
log("Rendering figures ...")
tmin=b["mid_s"]/60.0
def shade(ax):
    prev=None
    for _,r in b.iterrows():
        if r["phase"]!=prev:
            ax.axvline(r["start_s"]/60,color="k",lw=0.3,alpha=0.22); prev=r["phase"]
    for st in stressors:
        g=b[b.phase==st]
        if len(g): ax.axvspan(g["start_s"].min()/60,g["end_s"].max()/60,
                              color="#c0504d",alpha=0.14,zorder=0)

# --- Fig 1: signal overview + zoom ---
fig,(a1,a2)=plt.subplots(2,1,figsize=(11,7))
a1.plot(tu/60,sig_proc,lw=0.35,color="#33548e"); a1.axhline(0,color="grey",lw=.6,ls="--")
a1.set_title("Processed respiratory signal — full session"); a1.set_xlabel("Time (min)")
a1.set_ylabel("Belt signal (a.u.)")
z0,z1=900,990; m=(tu>=z0)&(tu<=z1)
a2.plot(tu[m],sig_proc[m],color="#33548e",lw=1.1)
pk=resp.peaks; tr=resp.troughs
pkz=pk[(pk>=z0)&(pk<=z1)]; trz=tr[(tr>=z0)&(tr<=z1)]
if len(pkz): a2.plot(pkz,resp.idt[pkz],"o",color="#c0504d",ms=5,label="peak")
if len(trz): a2.plot(trz,resp.idt[trz],"o",color="#4f8a4f",ms=5,label="trough")
for h in resp.holds:
    if h.end_time>=z0 and h.start_time<=z1:
        a2.axvspan(h.start_time,h.end_time,color="#e8c33a",alpha=.4)
a2.set_title("Detail: 900-990 s — cycles and breath-holds (shaded)")
a2.set_xlabel("Time (s)"); a2.set_ylabel("Belt signal (a.u.)"); a2.legend(fontsize=8)
fig.tight_layout(); fig.savefig(f"{OUT}/fig1_signal_overview.png",dpi=150); plt.close(fig)

# --- Fig 2: stress timeline (4 panels) ---
fig,axs=plt.subplots(4,1,figsize=(12,11),sharex=True)
axs[0].plot(tmin,b["rate_bpm"],".",ms=2.5,color="#bbb")
axs[0].plot(tmin,b["rate_bpm"].rolling(15,center=True,min_periods=3).median(),
            color="#33548e",lw=1.8,label="rolling median")
sg=sighs["time_s"]/60
axs[0].plot(sg,[b["rate_bpm"].max()*0.99]*len(sg),"v",color="#c0504d",ms=5,label="sigh-like breath")
axs[0].set_ylabel("Resp. rate\n(breaths/min)")
axs[0].set_title("Respiratory stress-marker timeline  (red bands = stressor tests)")
axs[0].legend(fontsize=8,loc="upper right",ncol=2)
axs[1].plot(tmin,b["inhale_amp_raw"].rolling(15,center=True,min_periods=3).median(),
            color="#4f8a4f",lw=1.5)
axs[1].set_ylabel("Breath amplitude\n(a.u., uncalibrated)")
axs[2].plot(tmin,b["cv_cycle_w"],color="#b9770e",lw=1.3)
axs[2].set_ylabel("Irregularity\n(CV of cycle, 21-breath win.)")
axs[3].plot(tmin,b["arousal_index_z"].rolling(15,center=True,min_periods=3).median(),
            color="#7d3c98",lw=1.8)
axs[3].axhline(0,color="grey",lw=.7,ls="--")
axs[3].set_ylabel("Composite arousal\nindex (z, heuristic)")
axs[3].set_xlabel("Time (min)")
for ax in axs: shade(ax)
fig.tight_layout(); fig.savefig(f"{OUT}/fig2_stress_timeline.png",dpi=150); plt.close(fig)

# --- Fig 3: per-phase stress heatmap ---
mk=pd.DataFrame(index=phase_order)
mk["Resp. rate"]=phase_sum["resp_rate_bpm"]
mk["Irregularity (CV)"]=phase_sum["cv_cycle"]
mk["Sigh rate"]=phase_sum["sigh_rate_per_min"]
mk["Hold rate"]=phase_sum["hold_rate_per_min"]
mk["Shallowness (-amp)"]=-phase_sum["mean_amplitude"]
Z=(mk-mk.mean())/mk.std()
fig,ax=plt.subplots(figsize=(8.5,9))
im=ax.imshow(Z.values,aspect="auto",cmap="RdBu_r",vmin=-2.2,vmax=2.2)
ax.set_xticks(range(len(Z.columns))); ax.set_xticklabels(Z.columns,rotation=35,ha="right")
ax.set_yticks(range(len(Z.index))); ax.set_yticklabels(Z.index,fontsize=8)
for i in range(len(Z.index)):
    for j in range(len(Z.columns)):
        ax.text(j,i,f"{Z.values[i,j]:.1f}",ha="center",va="center",fontsize=7,
                color="white" if abs(Z.values[i,j])>1.3 else "black")
ax.set_title("Stress-marker profile by phase\n(z-scored across phases; red = more stress-like)")
fig.colorbar(im,ax=ax,shrink=0.6,label="z-score")
fig.tight_layout(); fig.savefig(f"{OUT}/fig3_stress_heatmap.png",dpi=150); plt.close(fig)

# --- Fig 4: sighs ---
fig,(a,c)=plt.subplots(1,2,figsize=(12,4.8))
x=np.arange(len(phase_order))
a.bar(x,phase_sum["sigh_rate_per_min"],color="#c0504d",alpha=.85)
a.set_xticks(x); a.set_xticklabels(phase_order,rotation=45,ha="right",fontsize=7)
a.set_ylabel("Sigh-like breaths / min"); a.set_title("Sigh rate by phase")
pre=sighs["cv_cycle_pre"].dropna(); post=sighs["cv_cycle_post"].dropna()
c.bar([0,1],[pre.mean(),post.mean()],yerr=[pre.std(),post.std()],
      color=["#888","#7d3c98"],capsize=5,alpha=.85)
c.set_xticks([0,1]); c.set_xticklabels(["10 breaths\nbefore sigh","10 breaths\nafter sigh"])
c.set_ylabel("CV of cycle duration")
c.set_title(f"Breathing variability around sighs (n={len(pre)})")
fig.tight_layout(); fig.savefig(f"{OUT}/fig4_sighs.png",dpi=150); plt.close(fig)

# --- Fig 5: irregularity + I:E by phase ---
fig,(a,c)=plt.subplots(1,2,figsize=(12,4.8))
a.bar(x,phase_sum["cv_cycle"],color="#b9770e",alpha=.85)
a.axhline(phase_sum.loc["biometric_baseline","cv_cycle"],color="k",ls="--",lw=.8,
          label="baseline phase")
a.set_xticks(x); a.set_xticklabels(phase_order,rotation=45,ha="right",fontsize=7)
a.set_ylabel("CV of cycle duration"); a.set_title("Breath-cycle irregularity by phase")
a.legend(fontsize=8)
c.bar(x,phase_sum["ie_ratio"],color="#33548e",alpha=.85)
c.axhline(1.0,color="grey",ls=":",lw=.8)
c.set_xticks(x); c.set_xticklabels(phase_order,rotation=45,ha="right",fontsize=7)
c.set_ylabel("Inhale : exhale ratio"); c.set_title("I:E ratio by phase (1.0 = equal)")
fig.tight_layout(); fig.savefig(f"{OUT}/fig5_irregularity_ie.png",dpi=150); plt.close(fig)

# --- Fig 6: recovery after stressors ---
fig,ax=plt.subplots(figsize=(9,5))
cols={"practice_stressor_test":"#e8a33a","stressor_test_1":"#c0504d","stressor_test_2":"#7d3c98"}
for st in stressors:
    g=recovery[recovery.stressor==st]
    if len(g): ax.plot(g["bin_min_after"],g["resp_rate_bpm"],"o-",color=cols[st],label=st)
ax.axhline(base_rate,color="k",ls="--",lw=1,label=f"baseline ({base_rate:.1f})")
ax.set_xlabel("Minutes after stressor offset"); ax.set_ylabel("Respiratory rate (breaths/min)")
ax.set_title("Respiratory rate following stressor tests\n(note: protocol places further tasks after stressors)")
ax.legend(fontsize=8)
fig.tight_layout(); fig.savefig(f"{OUT}/fig6_recovery.png",dpi=150); plt.close(fig)

# --- Fig 7: event-locked rate ---
fig,ax=plt.subplots(figsize=(9,5))
def smooth(y,w=11):
    if y is None: return None
    return np.convolve(y,np.ones(w)/w,mode="same")
if st_y is not None: ax.plot(st_x,smooth(st_y),color="#c0504d",lw=2.2,label="stressor onsets (n=3)")
if sart_y is not None: ax.plot(sart_x,smooth(sart_y),color="#33548e",lw=2.2,label="SART-block onsets (n=6)")
ax.axvline(0,color="k",lw=1,ls="--",label="event onset")
ax.set_xlabel("Time relative to event onset (s)")
ax.set_ylabel("Respiratory rate (breaths/min)")
ax.set_title("Event-locked respiratory rate (averaged across events)")
ax.legend(fontsize=8)
fig.tight_layout(); fig.savefig(f"{OUT}/fig7_event_locked.png",dpi=150); plt.close(fig)
log("Figures done.")

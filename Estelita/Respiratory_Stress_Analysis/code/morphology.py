#!/usr/bin/env python3
# Breath-cycle morphology by phase. Run AFTER analyze_stress.py
# (reads the CSVs it writes into ./results/). Requires: pandas, numpy, matplotlib, pillow.
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import cm
import os
HERE=os.path.dirname(os.path.abspath(__file__))
R=os.path.join(HERE,"results"); PFX="Sub-1.13_G2_"
plt.rcParams.update({"font.size":9,"figure.facecolor":"white","savefig.facecolor":"white"})

b=pd.read_csv(f"{R}/{PFX}per_breath_features.csv")
sg=pd.read_csv(f"{R}/{PFX}continuous_signals_10Hz.csv")
ps=pd.read_csv(f"{R}/{PFX}stress_markers_by_phase.csv").set_index("phase")
t_sig=sg["time_s"].values; y_sig=sg["signal_processed"].values
NPL=50  # samples per limb

def breath_shape(s,p,e):
    if not (e>p>s): return None
    yi=np.interp(np.linspace(s,p,NPL),t_sig,y_sig)
    ye=np.interp(np.linspace(p,e,NPL),t_sig,y_sig)
    w=np.concatenate([yi,ye[1:]])
    w=w-np.linspace(w[0],w[-1],len(w))   # endpoint-detrend -> clean closed cycle
    return w

phase_order=b.groupby("phase")["start_s"].min().sort_values().index.tolist()
M={}
for ph in phase_order:
    g=b[(b.phase==ph)&(b.is_sigh==0)]
    W=[breath_shape(r.start_s,r.peak_s,r.end_s) for r in g.itertuples()]
    W=np.array([w for w in W if w is not None])
    M[ph]=dict(mean=W.mean(0),sd=W.std(0),
        inhale=float(g.inhale_dur_s.mean()),exhale=float(g.exhale_dur_s.mean()),
        cycle=float(g.cycle_dur_s.mean()),rate=ps.loc[ph,"resp_rate_bpm"],
        ie=ps.loc[ph,"ie_ratio"],cv=ps.loc[ph,"cv_cycle"],
        sigh=ps.loc[ph,"sigh_rate_per_min"],arous=ps.loc[ph,"arousal_index_z"])
ymax=max((d["mean"]+d["sd"]).max() for d in M.values())*1.08
ymin=min((d["mean"]-d["sd"]).min() for d in M.values())*1.08
WIN=14.0
INH="#c0504d"; EXH="#33548e"
norm=plt.Normalize(-0.8,0.8); cmap=matplotlib.colormaps["RdBu_r"]

def draw(ax,ph,small=True):
    d=M[ph]; cyc=d["cycle"]; nL=NPL
    # x for one cycle: inhale limb over d['inhale'], exhale limb over d['exhale']
    xc=np.concatenate([np.linspace(0,d["inhale"],nL),
                       np.linspace(d["inhale"],cyc,nL)[1:]])
    k=0
    while k*cyc < WIN:
        xo=k*cyc; x=xc+xo
        m=(x<=WIN)
        ax.fill_between(x[m],(d["mean"]-d["sd"])[m],(d["mean"]+d["sd"])[m],
                        color="#b0b0b0",alpha=0.30,lw=0)
        inh=np.arange(nL); exh=np.arange(nL-1,2*nL-1)
        ax.plot(x[inh][x[inh]<=WIN],d["mean"][inh][x[inh]<=WIN],color=INH,lw=1.6)
        ax.plot(x[exh][x[exh]<=WIN],d["mean"][exh][x[exh]<=WIN],color=EXH,lw=1.6)
        k+=1
    ax.set_xlim(0,WIN); ax.set_ylim(ymin,ymax)
    ax.axhline(0,color="#999",lw=0.5,ls=":")
    ax.set_facecolor(cmap(norm(d["arous"])))
    ax.patch.set_alpha(0.16)

# ===== FIG A: small-multiples grid =====
ncol=5; nrow=int(np.ceil(len(phase_order)/ncol))
fig,axs=plt.subplots(nrow,ncol,figsize=(13.5,2.0*nrow))
axs=axs.flatten()
for i,ph in enumerate(phase_order):
    ax=axs[i]; d=M[ph]; draw(ax,ph)
    ax.set_title(ph,fontsize=8.5,fontweight="bold",pad=2)
    ax.text(0.5,0.965,f"{d['rate']:.0f} br/min   I:E {d['ie']:.2f}   CV {d['cv']:.2f}",
            transform=ax.transAxes,ha="center",va="top",fontsize=6.3,color="#333")
    ax.tick_params(labelsize=6)
    if i%ncol==0: ax.set_ylabel("belt signal\n(a.u.)",fontsize=6.5)
    if i>=len(phase_order)-ncol: ax.set_xlabel("time (s)",fontsize=6.5)
for j in range(len(phase_order),len(axs)): axs[j].axis("off")
fig.subplots_adjust(hspace=0.66,wspace=0.30,top=0.94)
sm=cm.ScalarMappable(norm=norm,cmap=cmap); sm.set_array([])
cb=fig.colorbar(sm,ax=axs.tolist(),shrink=0.4,pad=0.015,aspect=30)
cb.set_label("composite arousal index (z)",fontsize=8)
fig.suptitle("Breath-cycle morphology by phase  —  ensemble-averaged waveform tiled over a fixed 14-second window\n"
  "red = inhalation limb, blue = exhalation limb, grey band = ±1 SD across breaths; "
  "panel tint = composite arousal",fontsize=10,y=1.005)
fig.savefig(f"{R}/fig8_breath_morphology_grid.png",dpi=150,bbox_inches="tight")
plt.close(fig)

# ===== FIG B: key-phase overlay (single representative breath) =====
keys=["biometric_baseline","sart_1","prs_2","break_1"]
labs={"biometric_baseline":"Baseline (calm)","sart_1":"SART block 1 (early acute arousal)",
      "prs_2":"Questionnaire 2 (late, irregular)","break_1":"Rest break 1 (recovery)"}
cols={"biometric_baseline":"#4f8a4f","sart_1":"#c0504d","prs_2":"#7d3c98","break_1":"#2e75b6"}
fig,ax=plt.subplots(figsize=(9,5.2))
for ph in keys:
    d=M[ph]; nL=NPL
    x=np.concatenate([np.linspace(0,d["inhale"],nL),
                      np.linspace(d["inhale"],d["cycle"],nL)[1:]])
    ax.fill_between(x,d["mean"]-d["sd"],d["mean"]+d["sd"],color=cols[ph],alpha=0.13,lw=0)
    ax.plot(x,d["mean"],color=cols[ph],lw=2.4,
            label=f"{labs[ph]} — {d['rate']:.0f} br/min, I:E {d['ie']:.2f}, CV {d['cv']:.2f}")
    ax.plot(d["inhale"],d["mean"][nL-1],"o",color=cols[ph],ms=6)
ax.axhline(0,color="#999",lw=0.6,ls=":")
ax.set_xlabel("Time within breath cycle (s)"); ax.set_ylabel("Belt signal (a.u.)")
ax.set_title("Representative breath-cycle morphology — four contrasting phases\n"
  "(dot = inhalation peak; shaded band = ±1 SD across breaths)",fontsize=10)
ax.legend(fontsize=8,loc="upper right"); ax.grid(alpha=0.25)
ax.set_xlim(0,6.2)
fig.tight_layout(); fig.savefig(f"{R}/fig9_breath_morphology_overlay.png",dpi=150)
plt.close(fig)
print("morphology figures written: fig8 (grid), fig9 (overlay)")
print(f"phases={len(phase_order)}  y-range=({ymin:.2f},{ymax:.2f})")

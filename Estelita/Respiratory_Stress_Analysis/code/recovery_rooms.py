#!/usr/bin/env python3
# Biophilic vs non-biophilic post-stressor recovery comparison.
# Run AFTER analyze_stress.py (reads ./results/ CSVs + the raw .xlsx).
import pandas as pd, numpy as np, json
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
plt.rcParams.update({"font.size":10,"axes.grid":True,"grid.alpha":0.25,
  "axes.spines.top":False,"axes.spines.right":False,"figure.facecolor":"white","savefig.facecolor":"white"})
import os
HERE=os.path.dirname(os.path.abspath(__file__))
R=os.path.join(HERE,"results"); PFX="Sub-1.13_G2_"
b=pd.read_csv(f"{R}/{PFX}per_breath_features.csv")
raw=pd.read_excel(os.path.join(HERE,"raw_respiration.xlsx"),  # <-- set to your raw Vernier-belt .xlsx
                  sheet_name=0,header=0)
t=raw["timestamp_unix"].astype(float).values; t0=t[0]; el=t-t0
cond=raw["condition"].values
idx=np.clip(np.searchsorted(el,b["mid_s"].values),0,len(el)-1)
b["condition"]=[cond[i] if isinstance(cond[i],str) else "unmarked" for i in idx]
base_rate=60/b[b.phase=="biometric_baseline"]["cycle_dur_s"].mean()

def seg(g,label):
    return dict(label=label,n=int(len(g)),rate=round(60/g["cycle_dur_s"].mean(),2),
        cv=round(g["cycle_dur_s"].std()/g["cycle_dur_s"].mean(),3),
        arousal=round(g["arousal_index_z"].mean(),3),amp=round(g["inhale_amp_raw"].mean(),3),
        sigh_per_min=round(g["is_sigh"].sum()/max((g["end_s"].max()-g["start_s"].min())/60,0.1),2))
S1=seg(b[b.phase=="stressor_test_1"],"stressor_test_1")
S2=seg(b[b.phase=="stressor_test_2"],"stressor_test_2")
NP=b[b.condition=="physical_no_plants"].sort_values("mid_s")
PL=b[b.condition=="physical_plants"].sort_values("mid_s")
roomNP=seg(NP,"no_plants_room"); roomPL=seg(PL,"plants_room")
def thirds(g):
    n=len(g); k=n//3
    return seg(g.iloc[:k],"early"),seg(g.iloc[k:2*k],"mid"),seg(g.iloc[2*k:],"late")
npE,npM,npL=thirds(NP); plE,plM,plL=thirds(PL)
def fracrec(sr,rr): return round(100*(1-(rr-base_rate)/(sr-base_rate)),1)

# trajectory + within-room linear slope
off1=b[b.phase=="stressor_test_1"]["end_s"].max()
off2=b[b.phase=="stressor_test_2"]["end_s"].max()
def traj(offset,lo=-5,hi=16):
    xs,rate,cv=[],[],[]
    for m in np.arange(lo,hi):
        g=b[((b["mid_s"]-offset)/60>=m)&((b["mid_s"]-offset)/60<m+1)]
        if len(g)>=2:
            xs.append(m+0.5); rate.append(60/g["cycle_dur_s"].mean())
            cv.append(g["cycle_dur_s"].std()/g["cycle_dur_s"].mean())
    return np.array(xs),np.array(rate),np.array(cv)
x1,r1,c1=traj(off1); x2,r2,c2=traj(off2)
RX0,RX1=4.3,15.3
def slope(x,y):
    m=(x>=RX0)&(x<=RX1)
    return np.polyfit(x[m],y[m],1) if m.sum()>2 else np.array([np.nan,np.nan])
pNP=slope(x1,r1); pPL=slope(x2,r2)

print("="*64)
print(f"baseline respiratory rate: {base_rate:.2f} br/min")
print(f"\nNON-BIOPHILIC: stressor_1 rate {S1['rate']} -> no-plants room rate {roomNP['rate']}")
print(f"  room early/mid/late rate: {npE['rate']} -> {npM['rate']} -> {npL['rate']}")
print(f"  within-room rate slope  : {pNP[0]:+.2f} br/min per min")
print(f"  fraction recovered      : {fracrec(S1['rate'],roomNP['rate'])}%   cv {npE['cv']}->{npL['cv']}")
print(f"\nBIOPHILIC: stressor_2 rate {S2['rate']} -> plants room rate {roomPL['rate']}")
print(f"  room early/mid/late rate: {plE['rate']} -> {plM['rate']} -> {plL['rate']}")
print(f"  within-room rate slope  : {pPL[0]:+.2f} br/min per min")
print(f"  fraction recovered      : {fracrec(S2['rate'],roomPL['rate'])}%   cv {plE['cv']}->{plL['cv']}")

pd.DataFrame([S1,roomNP,npE,npM,npL,S2,roomPL,plE,plM,plL]).to_csv(
    f"{R}/{PFX}room_recovery_comparison.csv",index=False)
json.dump(dict(baseline_rate=round(base_rate,2),stressor1=S1,no_plants_room=roomNP,
  stressor2=S2,plants_room=roomPL,
  np_room_rate_thirds=[npE['rate'],npM['rate'],npL['rate']],
  pl_room_rate_thirds=[plE['rate'],plM['rate'],plL['rate']],
  np_within_room_rate_slope=round(float(pNP[0]),3),
  pl_within_room_rate_slope=round(float(pPL[0]),3),
  np_fraction_recovered_pct=fracrec(S1['rate'],roomNP['rate']),
  pl_fraction_recovered_pct=fracrec(S2['rate'],roomPL['rate']),
  np_cv_change=round(npL['cv']-npE['cv'],3),pl_cv_change=round(plL['cv']-plE['cv'],3)),
  open(f"{R}/{PFX}room_recovery_summary.json","w"),indent=2)

# ---- figure ----
GREY="#7a7a7a"; GREEN="#3f8f3f"
fig,(a1,a2)=plt.subplots(2,1,figsize=(11,8.6),sharex=True)
for ax in (a1,a2):
    ax.axvspan(RX0,RX1,color="#cfe3cf",alpha=0.45,zorder=0)
    ax.axvline(0,color="#c0504d",lw=1.2,ls=":")
a1.plot(x1,r1,"o-",color=GREY,lw=1.5,ms=4,label="Non-biophilic sequence (after stressor 1)")
a1.plot(x2,r2,"o-",color=GREEN,lw=1.5,ms=4,label="Biophilic sequence (after stressor 2)")
a1.axhline(base_rate,color="k",ls="--",lw=1,label=f"baseline ({base_rate:.0f} br/min)")
xx=np.array([RX0,RX1])
a1.plot(xx,np.polyval(pNP,xx),"--",color=GREY,lw=2.8)
a1.plot(xx,np.polyval(pPL,xx),"--",color=GREEN,lw=2.8)
yt=a1.get_ylim()[1]
a1.text(0,yt*0.98,"stressor offset  ",color="#c0504d",fontsize=8,va="top",ha="right")
a1.text((RX0+RX1)/2,yt*0.98,"room period",ha="center",va="top",fontsize=9,color="#356635")
a1.text(RX1,np.polyval(pNP,RX1)+0.6,f"non-biophilic trend {pNP[0]:+.2f}/min",
        color=GREY,fontsize=8.5,ha="right",va="bottom",fontweight="bold")
a1.text(RX1,np.polyval(pPL,RX1)-0.6,f"biophilic trend {pPL[0]:+.2f}/min",
        color=GREEN,fontsize=8.5,ha="right",va="top",fontweight="bold")
a1.set_ylabel("Respiratory rate (breaths/min)")
a1.set_title("Post-stressor respiratory recovery: biophilic vs non-biophilic room\n"
  "within-room rate trend (dashed) falls in the biophilic room, rises in the non-biophilic room",fontsize=11)
a1.legend(fontsize=8,loc="lower right")
a2.plot(x1,c1,"o-",color=GREY,lw=1.5,ms=4,label="Non-biophilic")
a2.plot(x2,c2,"o-",color=GREEN,lw=1.5,ms=4,label="Biophilic")
a2.set_xlabel("Minutes since stressor-test offset")
a2.set_ylabel("Breath-cycle irregularity (CV)")
a2.legend(fontsize=8,loc="upper left")
fig.tight_layout(); fig.savefig(f"{R}/fig10_room_recovery.png",dpi=150); plt.close(fig)
print("\nfig10 + CSV + JSON saved")

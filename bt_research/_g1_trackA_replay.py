#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
G1 × 完整 Track A 卖出规则 replay（ticket: bt_research/G1_trackA_replay_ticket.md）

两层：
  core : 严格复刻 §九（`_post_issue6_trade_caliber_body.md`）的 peel 核心近似，
         D..D+1 两日窗、不强制 T+1 —— 用于**硬门自检**（须复现 +0.55 / +0.73 / +0.77）
  full : 生产忠实 Track A v2.45 / v2.38 —— T+1 锁定 + D..D+3 + 全部可离线分支
         （跌停/异常/固定止损-4%/硬止损自适应/T+2动态floor+延期/VWAP破位次晨/自适应peel）

未纳入（需服务器评分链路，做敏感性）：TSDOWN 半卖、D8 观察仓豁免、Wyckoff BC。
"""
import json, math, os, sys
import pandas as pd
import numpy as np

ROOT="/home/ubuntu/alphapilot"
K5=os.path.join(ROOT,"data/kline5m")
KALL=os.path.join(ROOT,"data/kline_cache/kline_all.parquet")
SCORES=os.path.join(ROOT,"output/qmt_scores")

ARM=0.03
DEF_HARD_STOP=-0.10; DEF_TRAIL_ARM=0.03; DEF_PEEL_PB=0.015
PEEL_PB_MAX=0.02; PEEL_MAX_STEPS=2; VOL_BASELINE=0.30
LIMIT_DOWN_PCT=-9.7; ANOMALY_PCT=-21.0; FIXED_STOP_PCT=4.0
T2_FORCE_HHMM=14*60+45; T2_EXTEND_MAX_DAYS=3
T2_FORCE_AMP_FRAC=0.50; T2_FORCE_AMP_MIN=4.0; T2_FORCE_VOL_K=0.10; T2_FORCE_FLOOR_MAX=-0.10
VWAP_CONFIRM_MIN=T2_FORCE_HHMM; VWAP_SELL_START=9*60+35; VWAP_SELL_END=9*60+50
WEAK_FLOOR_MULT=0.6; WEAK_TREND_MA=25

_G=None; _M5={}; _C={}
def _load():
    global _G
    if _G is not None: return
    df=pd.read_parquet(KALL); ren={}
    for c in df.columns:
        lc=str(c).lower()
        if lc in ("symbol","code"): ren[c]="symbol"
        elif lc in ("date","datetime","trade_date","time"): ren[c]="date"
        elif lc in ("close","open","high","low","volume","amount"): ren[c]=lc
    df=df.rename(columns=ren)
    df["symbol"]=df["symbol"].astype(str).str.zfill(6)
    df["date"]=df["date"].astype(str).str.slice(0,10)
    df=df.sort_values(["symbol","date"])
    _G={s:g.reset_index(drop=True) for s,g in df.groupby("symbol")}

def _d(sym,upto,n):
    g=_G.get(sym)
    return None if g is None else g[g["date"]<=upto].tail(n)

def load_5m(sym):
    if sym in _M5: return _M5[sym]
    p=os.path.join(K5,sym+".parquet")
    if not os.path.exists(p): _M5[sym]=None; return None
    m=pd.read_parquet(p,columns=["datetime","high","low","close","volume"])
    m["dt"]=pd.to_datetime(m["datetime"])
    m["ds"]=m["dt"].dt.strftime("%Y-%m-%d"); m["hm"]=m["dt"].dt.strftime("%H:%M")
    m=m.sort_values("dt").reset_index(drop=True); _M5[sym]=m; return m

def annual_vol(sym,day):
    k=("av",sym,day)
    if k in _C: return _C[k]
    s=_d(sym,day,22); r=None
    if s is not None and len(s)>=3:
        cl=[float(x) for x in s["close"].tolist() if x and x>0]
        if len(cl)>=3:
            lr=[math.log(cl[i]/cl[i-1]) for i in range(1,len(cl)) if cl[i-1]>0 and cl[i]>0]
            if len(lr)>=2:
                mu=sum(lr)/len(lr); var=sum((x-mu)**2 for x in lr)/(len(lr)-1)
                r=max(0.10,min(0.80,math.sqrt(var)*math.sqrt(252)))
    _C[k]=r; return r

def adaptive_params(sym,day,sim=True):
    k=("ap",sym,day,sim)
    if k in _C: return _C[k]
    vol=annual_vol(sym,day)
    if vol is None: r=(DEF_HARD_STOP,DEF_TRAIL_ARM,DEF_PEEL_PB)
    else:
        dev=vol-VOL_BASELINE
        hs=round(DEF_HARD_STOP-dev*0.10,3); ta=round(max(0.01,DEF_TRAIL_ARM-dev*0.05),3)
        pb=round(min(PEEL_PB_MAX if sim else 0.05,DEF_PEEL_PB+dev*0.03),3)
        r=(hs,ta,pb)
    _C[k]=r; return r

def prev_close(sym,day):
    k=("pc",sym,day)
    if k in _C: return _C[k]
    s=_G.get(sym); r=None
    if s is not None:
        ss=s[s["date"]<day]
        if len(ss): r=float(ss["close"].iloc[-1])
    _C[k]=r; return r

def ma25(sym,day):
    k=("ma",sym,day)
    if k in _C: return _C[k]
    s=_G.get(sym); r=None
    if s is not None:
        ss=s[s["date"]<=day].tail(WEAK_TREND_MA+6)
        cl=[float(x) for x in ss["close"].tolist() if x]
        if len(cl)>=WEAK_TREND_MA:
            cl=cl[:-1] if len(cl)>WEAK_TREND_MA else cl   # drop today's partial
            if len(cl)>=WEAK_TREND_MA: r=sum(cl[-WEAK_TREND_MA:])/WEAK_TREND_MA
    _C[k]=r; return r

def weak_regime(day):
    k=("wk",day)
    if k in _C: return _C[k]
    try:
        p=os.path.join(SCORES,day+".candidates.json")
        r=bool((json.load(open(p)).get("market_env") or {}).get("weak_regime"))
    except Exception: r=False
    _C[k]=r; return r

# ---- core：严格复刻 §九 ----
def core(ob,bars,mode='hold',pb=0.015,maxsteps=2,hard=-0.10,limd=-0.097,nextbar=False):
    pos=1.0; cash=0.0; peak=ob; armed=False; pend=False; ptrig=0.0; peels=0; last=ob
    for ds,hm,h,l,c in bars:
        last=c
        if pos<=1e-9: break
        if mode=='hold': continue
        if l<=ob*(1+limd): cash+=pos*ob*(1+limd); pos=0; break
        if l<=ob*(1+hard): cash+=pos*ob*(1+hard); pos=0; break
        if not armed and h>=ob*(1+ARM): armed=True; peak=h
        if armed:
            if h>peak: peak=h
            trig=peak*(1-pb)
            if nextbar:
                if pend and l<=ptrig:
                    q=min(0.5,pos); cash+=q*ptrig; pos-=q; peels+=1; pend=False; peak=h
                    if peels>=maxsteps: cash+=pos*ptrig; pos=0; break
                elif (not pend) and l<=trig: pend=True; ptrig=trig
            else:
                if l<=trig:
                    q=min(0.5,pos); cash+=q*trig; pos-=q; peels+=1; peak=h
                    if peels>=maxsteps: cash+=pos*trig; pos=0; break
    if pos>1e-9: cash+=pos*last
    return cash/ob-1

# ---- full：生产忠实 Track A ----
USE_FIXED=True; USE_VWAP=True; USE_T2=True; USE_HARD=True
def full(ob,sym,day,m,sim=True):
    hs,ta,pb=adaptive_params(sym,day,sim=sim)
    pc=prev_close(sym,day); weak=weak_regime(day); ma=ma25(sym,day)
    nds=sorted(set(m["ds"]))
    if day not in nds: return None
    i=nds.index(day); days=nds[i:i+4]
    pos=1.0; cash=0.0; peak=ob; trail=False; peels=0
    pend=False; pend_peak=0.0; awaiting=False; snaphigh=0.0
    vwap_broken=False; vwap_ref=None; t2_ext=False; last=ob
    # 逐 bar
    for di,ds in enumerate(days):
        d0=m[m["ds"]==ds]
        amp_hi=None; amp_lo=None
        # 当日振幅（用于 floor）：用当日 5m 全程
        if len(d0):
            amp_hi=float(d0["high"].max()); amp_lo=float(d0["low"].min())
        for _,r in d0.iterrows():
            hm=r["hm"]
            if di==0 and hm<"09:35": continue
            h=float(r["high"]); l=float(r["low"]); c=float(r["close"]); last=c
            if pos<=1e-9: break
            hh,mm=(int(x) for x in hm.split(":")); nowm=hh*60+mm
            if h>peak: peak=h
            daily=(c/pc-1)*100 if pc and pc>0 else 0.0
            ret=(c/ob-1)*100
            if daily<=ANOMALY_PCT: continue
            if daily<=LIMIT_DOWN_PCT: cash+=pos*ob*(1+LIMIT_DOWN_PCT/100.0); pos=0.0; break
            if di==0: continue                      # T+1 锁定
            if USE_FIXED and l<=ob*(1-FIXED_STOP_PCT/100.0):   # 固定止损 -4%
                cash+=pos*ob*(1-FIXED_STOP_PCT/100.0); pos=0.0; break
            # VWAP 破位确认（>=14:45）
            if USE_VWAP and (not vwap_broken) and nowm>=VWAP_CONFIRM_MIN:
                dd=d0[d0["hm"]<=hm]
                if len(dd):
                    tv=float(dd["volume"].sum())*100.0
                    ta_=float((dd["close"].astype(float)*dd["volume"].astype(float)).sum())*100.0
                    if tv>0:
                        vw=ta_/tv
                        if vw>0 and c<vw: vwap_broken=True; vwap_ref=vw
            if USE_VWAP and vwap_broken and VWAP_SELL_START<=nowm<=VWAP_SELL_END and vwap_ref and c<vwap_ref:
                cash+=pos*c; pos=0.0; break
            # 硬止损（仅 >=14:45）
            if USE_HARD and nowm>=T2_FORCE_HHMM and ret<=hs*100:
                cash+=pos*c; pos=0.0; break
            # T+2 条件强平 / 延期（>=14:45，D+1 起）
            if USE_T2 and nowm>=T2_FORCE_HHMM:
                if t2_ext:
                    if di>=T2_EXTEND_MAX_DAYS and (not weak or (ma and c<ma)):
                        cash+=pos*c; pos=0.0; break
                else:
                    if amp_hi and amp_lo and pc and pc>0:
                        ampc=(amp_hi-amp_lo)/pc*100.0
                    else: ampc=0.0
                    vol=annual_vol(sym,ds) or VOL_BASELINE
                    tol=max(0.0,ampc-T2_FORCE_AMP_MIN)*T2_FORCE_AMP_FRAC/100.0 if ampc>0 else 0.0
                    if vol>VOL_BASELINE: tol+=(vol-VOL_BASELINE)*T2_FORCE_VOL_K
                    fl=-tol
                    if fl<T2_FORCE_FLOOR_MAX: fl=T2_FORCE_FLOOR_MAX
                    if weak: fl=round(fl*WEAK_FLOOR_MULT,2)
                    if ret<fl*100: cash+=pos*c; pos=0.0; break
                    if di>=T2_EXTEND_MAX_DAYS: pass
                    elif weak:
                        if not (ma and c<ma): t2_ext=True
                    else: t2_ext=True
            # 自适应 peel
            if ret>=ta*100: trail=True
            elif ret<0: trail=False; awaiting=False
            if trail and not awaiting and nowm>=9*60+31:
                pbk=(peak-c)/peak*100 if peak>0 else 0.0
                if sim and pend and peak>pend_peak+1e-9: pend=False
                if pbk>=pb*100:
                    trig=peak*(1-pb)
                    if sim:
                        if not pend: pend=True; pend_peak=peak
                        else:
                            pend=False
                            if peels>=PEEL_MAX_STEPS or pos<0.5: cash+=pos*trig; pos=0.0
                            else: cash+=0.5*trig; pos-=0.5; peels+=1; awaiting=True; snaphigh=peak
                    else:
                        if peels>=PEEL_MAX_STEPS or pos<0.5: cash+=pos*trig; pos=0.0
                        else: cash+=0.5*trig; pos-=0.5; peels+=1; awaiting=True; snaphigh=peak
                    if pos<=1e-9: break
            if awaiting and peak>snaphigh+1e-9: awaiting=False
    if pos>1e-9: cash+=pos*last
    return cash/ob-1

def main():
    global USE_FIXED,USE_VWAP,USE_T2,USE_HARD
    _load()
    d=json.load(open(sys.argv[1] if len(sys.argv)>1 else "/tmp/wb_gap.json"))
    tr=[(t["date"],str(t["code"]).zfill(6),t["cat"]) for t in d["prod_main"]+d["prod_exp"]]
    rows=[]; ctx=[]
    for date,code,cat in tr:
        m=load_5m(code)
        if m is None: continue
        d0=m[m["ds"]==date]; eb=d0[d0["hm"]=="09:35"]
        if not len(eb): continue
        ob=float(eb["close"].iloc[0])
        nds=sorted(set(m["ds"])); i=nds.index(date) if date in nds else -1
        if i<0 or i+1>=len(nds): continue
        d1=nds[i+1]
        sel=m[((m["ds"]==date)&(m["hm"]>="09:35"))|((m["ds"]==d1)&(m["hm"]<="15:00"))]
        bc=list(zip(sel["ds"],sel["hm"],sel["high"].astype(float),sel["low"].astype(float),sel["close"].astype(float)))
        ctx.append((date,code,cat,ob,m))
        try:
            rows.append(dict(date=date,code=code,cat=cat,
                hold_core=core(ob,bc,'hold'),
                live_core=core(ob,bc,'live',pb=0.015,nextbar=False),
                sim_core=core(ob,bc,'sim',pb=0.015,nextbar=True),
                full_live=full(ob,code,date,m,sim=False),
                full_sim=full(ob,code,date,m,sim=True)))
        except Exception as e:
            print("ERR",code,date,repr(e))
    df=pd.DataFrame(rows)
    df.to_parquet("/tmp/g1_trackA_replay.parquet",index=False)
    print("n =",len(df))
    def rep(col):
        u=df[df["cat"].str.contains("走高")]; dn=df[df["cat"].str.contains("走低")]
        def tt(s):
            g=s.groupby("date")[col].mean().values
            return g.mean(),(g.mean()/(g.std(ddof=1)/np.sqrt(len(g))) if len(g)>1 else float('nan'))
        m1,t1=tt(u); m2,t2=tt(dn)
        pr=(u.groupby("date")[col].mean()-dn.groupby("date")[col].mean()).dropna().values
        tp=pr.mean()/(pr.std(ddof=1)/np.sqrt(len(pr))) if len(pr)>1 else float('nan')
        print(f"  {col:10s} 全体={100*df[col].mean():+6.2f}% 胜={100*(df[col]>0).mean():5.1f}% | "
              f"走高 {100*m1:+.2f}% t={t1:5.2f} | 走低 {100*m2:+.2f}% t={t2:6.2f} | 配对 {100*pr.mean():+.2f}% t={tp:.2f}")
    print("=== 硬门自检（须复现 §九：hold +0.55/49.4, live +0.73/66.5, sim +0.77/66.5）===")
    for c in ["hold_core","live_core","sim_core"]: rep(c)
    print("=== 生产忠实全套（T+1 锁定 + D..D+3 + 全分支）===")
    for c in ["full_live","full_sim"]: rep(c)
    print("=== 分支归因（sim v2.45，逐条关掉）===")
    variants=[("全开",(True,True,True,True)),("关VWAP",(True,False,True,True)),
              ("关-4%固定",(False,True,True,True)),("关T+2",(True,True,False,True)),
              ("关硬止损",(True,True,True,False)),("仅peel(T+1+跌停)",(False,False,False,False))]
    for nm,(f,v,t,hd) in variants:
        USE_FIXED,USE_VWAP,USE_T2,USE_HARD=f,v,t,hd
        vals=[full(ob,code,date,m,sim=True) for (date,code,cat,ob,m) in ctx]
        df["var"]=vals
        u=df[df["cat"].str.contains("走高")]; dn=df[df["cat"].str.contains("走低")]
        def tt(s):
            g=s.groupby("date")["var"].mean().values
            return g.mean(),(g.mean()/(g.std(ddof=1)/np.sqrt(len(g))) if len(g)>1 else float('nan'))
        m1,t1=tt(u); m2,t2=tt(dn)
        pr=(u.groupby("date")["var"].mean()-dn.groupby("date")["var"].mean()).dropna().values
        tp=pr.mean()/(pr.std(ddof=1)/np.sqrt(len(pr))) if len(pr)>1 else float('nan')
        print(f"  {nm:18s} 全体={100*df['var'].mean():+6.2f}% 胜={100*(df['var']>0).mean():5.1f}% | "
              f"走高 {100*m1:+.2f}% t={t1:5.2f} | 走低 {100*m2:+.2f}% t={t2:6.2f} | 配对 {100*pr.mean():+.2f}% t={tp:.2f}")

if __name__=="__main__": main()

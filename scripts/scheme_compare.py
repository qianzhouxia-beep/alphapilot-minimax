#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AlphaPilot 3-Scheme Factor Weighting Comparison
Evaluates A) Pure ICIR, B) XGBoost ML, C) Hybrid ICIR+ML
via walk-forward train/test IC comparison.
"""
import json, os, sys, time, warnings, argparse
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any
warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parent.parent
os.chdir(str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import run_icir_analysis as _icir

MIN_CROSS = 20
TRAIN_RATIO = 0.7
TOP_K = 30
STEP = 2
ALL_FACTORS = _icir.ALL_FACTORS

np = pd = xgb = sr = None
def _lazy():
    global np, pd, xgb, sr
    if np is None:
        import numpy as _np; np = _np
    if pd is None:
        import pandas as _pd; pd = _pd
    if xgb is None:
        import xgboost as _xgb; xgb = _xgb
    if sr is None:
        from scipy.stats import spearmanr as _sr; sr = _sr

def split_panel(panel, ratio=0.7):
    _lazy()
    all_dates = sorted(set(d for rows in panel.values() for d in rows.keys()))
    n = len(all_dates)
    si = int(n * ratio)
    tr = set(all_dates[:si])
    te = set(all_dates[si:])
    tp, tep = {}, {}
    for reg, by_date in panel.items():
        tb = {d: v for d, v in by_date.items() if d in tr}
        teb = {d: v for d, v in by_date.items() if d in te}
        if tb: tp[reg] = tb
        if teb: tep[reg] = teb
    return tp, tep

def eval_scheme_A(train_panel, test_panel, flist, top_k=30):
    _lazy()
    icir_r = _icir.compute_icir(train_panel, flist, label_idx=1)
    wo = _icir.compute_weights(icir_r, regime_w={"normal":0.5,"weak":0.3,"severe":0.2}, top_k=top_k)
    wm = {w["factor"]: w["weight"] for w in wo["weights"]}
    if not wm: return []
    ics = []
    for reg in sorted(test_panel):
        for d in sorted(test_panel[reg]):
            rows = test_panel[reg][d]
            if len(rows) < MIN_CROSS: continue
            fv = {f: [] for f in flist}
            for vec, y1, y2 in rows:
                for f in flist:
                    fv[f].append(vec.get(f, 0.0))
            alphas, actuals = [], []
            for i, (vec, y1, y2) in enumerate(rows):
                al = 0.0
                for f, w in wm.items():
                    vals = np.array(fv.get(f, [0.0]))
                    z = (vals[i] - np.mean(vals)) / (np.std(vals) + 1e-12)
                    al += z * w
                alphas.append(al)
                actuals.append(y1)
            if len(alphas) < MIN_CROSS: continue
            icv, _ = sr(alphas, actuals)
            if np.isfinite(icv): ics.append(icv)
    return ics

def eval_scheme_B(train_panel, test_panel, flist):
    _lazy()
    X, y = [], []
    for reg, by_date in train_panel.items():
        for d, rows in by_date.items():
            for vec, y1, y2 in rows:
                X.append([vec.get(f, 0.0) for f in flist])
                y.append(y1)
    if len(X) < 30: return []
    Xa, ya = np.array(X), np.array(y)
    model = xgb.XGBRegressor(n_estimators=100, max_depth=4, learning_rate=0.1,
                             subsample=0.8, colsample_bytree=0.8, random_state=42, verbosity=0)
    model.fit(Xa, ya)
    ics = []
    for reg in sorted(test_panel):
        for d in sorted(test_panel[reg]):
            rows = test_panel[reg][d]
            if len(rows) < MIN_CROSS: continue
            Xt = np.array([[vec.get(f, 0.0) for f in flist] for vec, y1, y2 in rows])
            pr = model.predict(Xt)
            ac = np.array([y1 for _, y1, _ in rows])
            icv, _ = sr(pr, ac)
            if np.isfinite(icv): ics.append(icv)
    return ics

def eval_scheme_C(train_panel, test_panel, flist, top_k=30):
    _lazy()
    icir_r = _icir.compute_icir(train_panel, flist, label_idx=1)
    all_ic = {}
    for reg, rows in icir_r.items():
        for r in rows:
            all_ic[r["factor"]] = max(all_ic.get(r["factor"], 0), abs(r["icir"]))
    top_f = sorted(all_ic, key=all_ic.get, reverse=True)[:top_k]
    if len(top_f) < 5: return [], top_f
    X, y = [], []
    for reg, by_date in train_panel.items():
        for d, rows in by_date.items():
            for vec, y1, y2 in rows:
                X.append([vec.get(f, 0.0) for f in top_f])
                y.append(y1)
    if len(X) < 30: return [], top_f
    Xa, ya = np.array(X), np.array(y)
    model = xgb.XGBRegressor(n_estimators=100, max_depth=4, learning_rate=0.1,
                             subsample=0.8, colsample_bytree=0.8, random_state=42, verbosity=0)
    model.fit(Xa, ya)
    ics = []
    for reg in sorted(test_panel):
        for d in sorted(test_panel[reg]):
            rows = test_panel[reg][d]
            if len(rows) < MIN_CROSS: continue
            Xt = np.array([[vec.get(f, 0.0) for f in top_f] for vec, y1, y2 in rows])
            pr = model.predict(Xt)
            ac = np.array([y1 for _, y1, _ in rows])
            icv, _ = sr(pr, ac)
            if np.isfinite(icv): ics.append(icv)
    return ics, top_f

def comp_metrics(name, ics):
    _lazy()
    if len(ics) < 3: return {"name": name, "error": "insufficient data"}
    arr = np.array(ics)
    mu = float(np.mean(arr))
    sd = float(np.std(arr)) + 1e-12
    return {"name": name, "n_test_days": len(arr), "mean_rankic": round(mu,4),
            "rankic_std": round(float(sd),4), "rank_icir": round(mu/sd,4),
            "hit_rate": round(float(np.mean(arr>0)),4)}

def gen_html(metrics, daily_data, flist, out_path, top_f_c=None):
    _lazy()
    colors = {"A_ICIR":"#4C72B0","B_XGBoost":"#DD8452","C_Hybrid":"#55A868"}
    labels = {"A_ICIR":"A) Pure ICIR","B_XGBoost":"B) XGBoost ML","C_Hybrid":"C) Hybrid ICIR+ML"}
    cd = {}
    for s in ["A_ICIR","B_XGBoost","C_Hybrid"]:
        ics = daily_data.get(s,[])
        if ics: cd[s] = [round(v,4) for v in ics]
    best = max(metrics, key=lambda k: metrics[k].get("rank_icir", -999))

    html = """<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>AlphaPilot - Factor Weighting Scheme Comparison</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#f0f2f5;color:#1a1a2e;line-height:1.6}
.container{max-width:1200px;margin:0 auto;padding:24px}
.header{background:linear-gradient(135deg,#1a1a2e 0%,#16213e 100%);color:#fff;padding:40px;border-radius:16px;margin-bottom:24px}
.header h1{font-size:28px;font-weight:700;margin-bottom:8px}
.header p{opacity:0.8;font-size:14px;margin:2px 0}
.cards{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-bottom:24px}
.card{background:#fff;border-radius:12px;padding:20px;box-shadow:0 2px 8px rgba(0,0,0,0.06);border-top:4px solid #ccc}
.card h3{font-size:16px;margin-bottom:12px}
.card table{width:100%;font-size:13px}
.card td{padding:3px 0}
.card td:first-child{color:#888}
.card td:last-child{font-weight:600;text-align:right}
.sec{background:#fff;border-radius:12px;padding:24px;margin-bottom:24px;box-shadow:0 2px 8px rgba(0,0,0,0.06)}
.sec h2{font-size:18px;margin-bottom:16px}
.cw{position:relative;height:300px}
.rec{background:linear-gradient(135deg,#1a1a2e 0%,#16213e 100%);color:#fff;border-radius:12px;padding:24px;margin-bottom:24px}
.rec h2{font-size:18px;margin-bottom:12px}
.rec p{font-size:14px;opacity:0.9;line-height:1.7}
.ft{text-align:center;color:#888;font-size:12px;padding:20px 0}
.bdg{display:inline-block;padding:4px 12px;border-radius:20px;font-size:12px;font-weight:600;margin-bottom:12px}
.bdgw{background:#d4edda;color:#155724}
.bdgr{background:#fff3cd;color:#856404}
</style></head>
<body><div class="container">
<div class="header"><h1>AlphaPilot Factor Weighting Scheme Comparison</h1>
<p>Evaluation: synthetic stocks | Factors: N_FACTORS effective | Train/Test: TRAIN_PCT/TEST_PCT split</p>
<p>Metric: Daily cross-sectional Spearman RankIC(alpha, next-day return)</p></div>
<div class="cards">"""

    for s in ["A_ICIR","B_XGBoost","C_Hybrid"]:
        m = metrics.get(s,{})
        if "error" in m:
            html += '<div class="card" style="border-top-color:' + colors[s] + '"><h3>' + labels[s] + '</h3><p style="color:#999">Insufficient data</p></div>'
            continue
        iw = s == best
        bg = '<span class="bdg bdgw">Best</span>' if iw else '<span class="bdg bdgr">--</span>'
        html += '<div class="card" style="border-top-color:' + colors[s] + '">' + bg + '<h3>' + labels[s] + '</h3><table>'
        html += '<tr><td>Rank ICIR</td><td style="color:' + colors[s] + '">' + str(m.get("rank_icir","N/A")) + '</td></tr>'
        html += '<tr><td>Mean RankIC</td><td>' + str(m.get("mean_rankic","N/A")) + '</td></tr>'
        hr = m.get("hit_rate","N/A")
        html += '<tr><td>Hit Rate</td><td>' + (f"{hr:.1%}" if isinstance(hr,float) else str(hr)) + '</td></tr>'
        html += '<tr><td>RankIC Std</td><td>' + str(m.get("rankic_std","N/A")) + '</td></tr>'
        html += '<tr><td>Test Days</td><td>' + str(m.get("n_test_days","N/A")) + '</td></tr></table></div>'

    html += """</div>
<div class="sec"><h2>Daily RankIC Comparison</h2><div class="cw"><canvas id="c1"></canvas></div></div>
<div class="sec"><h2>Cumulative RankIC (Stability View)</h2><div class="cw"><canvas id="c2"></canvas></div></div>
<div class="rec"><h2>Recommendation</h2><p id="rt">Loading...</p></div>
<div class="ft">AlphaPilot ICIR Analysis Engine | Generated TIMESTAMP_DATA</div></div>
<script>
const C = COLORS_DATA, L = LABELS_DATA, D = CHART_DATA, M = METRICS_DATA, TF = TOP_FACTORS_DATA;
let best = null, bi = -999;
for(const[k,v]of Object.entries(M)){if(v.rank_icir&&v.rank_icir>bi){bi=v.rank_icir;best=k}}
function mkDS(label,data,color){return{label,data:data.map((v,i)=>({x:i,y:v})),borderColor:color,backgroundColor:color,borderWidth:2,pointRadius:0,tension:.1}}
new Chart(document.getElementById('c1').getContext('2d'),{type:'line',data:{datasets:Object.entries(D).map(([k,v])=>mkDS(L[k]||k,v,C[k]))},options:{responsive:true,maintainAspectRatio:false,interaction:{intersect:false,mode:'index'},plugins:{legend:{position:'top'}},scales:{x:{title:{display:true,text:'Test Day'}},y:{title:{display:true,text:'Spearman RankIC'}}}}});
const ds2=[];for(const[k,v]of Object.entries(D)){let c=0;ds2.push(mkDS(L[k]||k,v.map(x=>(c+=x,c)),C[k]))}
new Chart(document.getElementById('c2').getContext('2d'),{type:'line',data:{datasets:ds2},options:{responsive:true,maintainAspectRatio:false,interaction:{intersect:false,mode:'index'},plugins:{legend:{position:'top'}},scales:{x:{title:{display:true,text:'Test Day'}},y:{title:{display:true,text:'Cumulative RankIC'}}}}});
const rt=document.getElementById('rt');
if(best&&M[best]){const bm=M[best],lm={'A_ICIR':'Pure ICIR','B_XGBoost':'XGBoost ML','C_Hybrid':'Hybrid ICIR+ML'};
rt.innerHTML='<strong>Winner: '+(lm[best]||best)+'</strong> -- Rank ICIR='+bm.rank_icir+', Hit Rate='+(bm.hit_rate*100).toFixed(0)+'%. '+
'This scheme shows the highest prediction stability on the test set. Recommend using this scheme for factor weighting in production, with monthly ICIR recalibration.'+
(TF&&TF.length?('<br>Hybrid selected top factors: '+TF.slice(0,10).join(', ')+(TF.length>10?'...':'')):'');
}else{rt.textContent='Insufficient data to determine recommendation.'}
</script></body></html>"""

    html = html.replace("COLORS_DATA", json.dumps(colors, ensure_ascii=False))
    html = html.replace("LABELS_DATA", json.dumps(labels, ensure_ascii=False))
    html = html.replace("CHART_DATA", json.dumps(cd, ensure_ascii=False))
    html = html.replace("METRICS_DATA", json.dumps(metrics, ensure_ascii=False))
    html = html.replace("TOP_FACTORS_DATA", json.dumps(top_f_c or [], ensure_ascii=False))
    html = html.replace("TIMESTAMP_DATA", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    html = html.replace("N_FACTORS", str(len(flist)))
    html = html.replace("TRAIN_PCT", str(int(TRAIN_RATIO * 100)))
    html = html.replace("TEST_PCT", str(int((1 - TRAIN_RATIO) * 100)))
    out_path.write_text(html, "utf-8")
    print("  HTML report saved:", out_path)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["demo","prod"], default="demo")
    ap.add_argument("--sample", type=int, default=200)
    ap.add_argument("--days", type=int, default=120)
    ap.add_argument("--top-k", type=int, default=TOP_K)
    args = ap.parse_args()
    t0 = time.time()
    _lazy()
    out_dir = ROOT / "output" / "scheme_compare"
    out_dir.mkdir(parents=True, exist_ok=True)
    print()
    print("AlphaPilot 3-Scheme Comparison | mode=" + args.mode)

    # 1. Data
    print("[1/5] Generating data...")
    klines = _icir._demo_generate_klines(args.sample, args.days)
    print("  " + str(len(klines)) + " stocks")

    # 2. Factors
    print("[2/5] Computing factors (" + str(len(ALL_FACTORS)) + " total)...")
    fd = {}
    for code, kl in klines.items():
        fe = _icir.compute_factors_from_klines(kl)
        if fe: fd[code] = fe
    present = set()
    for fe in fd.values(): present.update(fe.keys())
    flist = [c for c in ALL_FACTORS if c in present]
    print("  ok=" + str(len(fd)) + " effective_factors=" + str(len(flist)))

    # 3. Panel
    print("[3/5] Building cross-section panel...")
    all_dates = sorted(set(d for kl in klines.values() for r in kl for d in [r["date"]]))
    cd = all_dates[::STEP]
    panel = defaultdict(lambda: defaultdict(list))
    for d in cd:
        rows = []
        for code, fe in fd.items():
            kl = klines.get(code)
            if not kl: continue
            idx = -1
            for j, r in enumerate(kl):
                if r["date"] == d: idx = j; break
            if idx < 0 or idx+2 >= len(kl): continue
            vec = {f: float(fe.get(f,[0.0])[idx]) if isinstance(fe.get(f),list) else 0.0 for f in flist}
            y1 = kl[idx+1]["close"] / kl[idx]["close"] - 1.0
            buy, sell = kl[idx+1]["open"], kl[idx+2]["close"]
            y2 = sell/buy - 1.0 if buy > 1e-6 else float("nan")
            if not np.isfinite(y2): continue
            rows.append((vec, y1, y2))
        if len(rows) >= MIN_CROSS:
            panel["all"][d] = rows
    ns = sum(len(v) for v in panel["all"].values())
    print("  " + str(len(cd)) + " days, " + str(ns) + " cross-sections")

    # 4. Evaluate
    tp, tep = split_panel(panel)
    td = sum(len(v) for v in tp["all"].values())
    ted = sum(len(v) for v in tep["all"].values())
    print("[4/5] Evaluating 3 schemes (train=" + str(int(TRAIN_RATIO*100)) + "%, test=" + str(int((1-TRAIN_RATIO)*100)) + "%)...")
    print("  train_cross_sections=" + str(td) + " test_cross_sections=" + str(ted))

    print("  A) Pure ICIR...")
    ica = eval_scheme_A(tp, tep, flist, args.top_k)
    print("    valid test days: " + str(len(ica)))

    print("  B) XGBoost ML...")
    icb = eval_scheme_B(tp, tep, flist)
    print("    valid test days: " + str(len(icb)))

    print("  C) Hybrid ICIR+ML...")
    icc, tfc = eval_scheme_C(tp, tep, flist, args.top_k)
    print("    valid test days: " + str(len(icc)))
    if tfc:
        print("    top factors: " + str(tfc[:10]) + ("..." if len(tfc)>10 else ""))

    metrics = {}
    for s, ics in [("A_ICIR",ica),("B_XGBoost",icb),("C_Hybrid",icc)]:
        metrics[s] = comp_metrics(s, ics)

    print()
    print("  " + "="*55)
    print("  " + "{:<25s} {:>10s} {:>10s} {:>10s} {:>6s}".format("Scheme","RankICIR","MeanIC","HitRate","Days"))
    print("  " + "="*55)
    for s in ["A_ICIR","B_XGBoost","C_Hybrid"]:
        m = metrics.get(s,{})
        if "error" in m:
            print("  " + "{:<25s} {:>10s}".format(s,"--"))
        else:
            print("  " + "{:<25s} {:>+10.4f} {:>+10.4f} {:>10.1%} {:>6d}".format(
                s, m.get("rank_icir",0), m.get("mean_rankic",0), m.get("hit_rate",0), m.get("n_test_days",0)))
    print("  " + "="*55)

    # 5. Save
    print("[5/5] Saving results and generating report...")
    output = {"time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
              "config": {"sample":args.sample,"days":args.days,"factors":len(flist),"top_k":args.top_k},
              "metrics": metrics,
              "test_daily_ics": {k: [round(v,4) for v in vals] for k,vals in {"A_ICIR":ica,"B_XGBoost":icb,"C_Hybrid":icc}.items()},
              "top_factors_c": tfc}
    jp = out_dir / "scheme_compare.json"
    jp.write_text(json.dumps(output, ensure_ascii=False, indent=2, default=str), "utf-8")
    print("  JSON: " + str(jp))
    hp = out_dir / "scheme_report.html"
    gen_html(metrics, {"A_ICIR":ica,"B_XGBoost":icb,"C_Hybrid":icc}, flist, hp, tfc)
    print("  Report: " + str(hp))
    print()
    print("  Total time: " + str(round(time.time()-t0,1)) + "s")

if __name__ == "__main__":
    main()
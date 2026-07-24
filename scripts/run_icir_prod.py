#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AlphaPilot ICIR Analysis + 3-Scheme Comparison (Production)
===========================================================
Runs on Linux server using real A-share kline data + VM2.5 production features.

Usage:
  cd /home/ubuntu/alphapilot
  python3 -u scripts/run_icir_prod.py --start 2026-01-01 --end 2026-07-17 --sample 800

Output:
  output/icir_prod/icir_ranking.json         ICIR results + weights
  output/icir_prod/scheme_compare.json       3-scheme comparison metrics
  output/icir_prod/scheme_report.html        Interactive HTML report
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import warnings
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

warnings.filterwarnings("ignore")

ROOT = Path("/home/ubuntu/alphapilot")
os.chdir(str(ROOT))
sys.path.insert(0, str(ROOT))

# ─── Config ────────────────────────────────────
MIN_CROSS = 20
MIN_IC_DAYS = 5
STEP = 2
TOP_K = 30
TRAIN_RATIO = 0.7


# ════════════════════════════════════════════════
# 1. Data Loading (from parquet + VM2.5 Scorer)
# ════════════════════════════════════════════════
def bare(sym: str) -> str:
    s = str(sym).strip()
    if "." in s:
        s = s.split(".")[0]
    return s.zfill(6)[-6:]


def load_data(start: str, end: str, sample: int) -> tuple[dict, dict]:
    """Load kline parquet + build features via VM25Scorer.
    Returns (by_symbol_dfs, feats_names_list).
    """
    from vm25_scorer import VM25Scorer

    kdf = pd.read_parquet(ROOT / "data/kline_cache/kline_all.parquet")
    kdf["date"] = kdf["date"].astype(str).str[:10]
    kdf["symbol"] = kdf["symbol"].map(bare)
    syms = sorted(kdf["symbol"].unique())
    rng = np.random.default_rng(42)
    sample_syms = list(rng.choice(syms, size=min(sample, len(syms)), replace=False))

    by = {
        s: g.sort_values("date").reset_index(drop=True)
        for s, g in kdf[kdf["symbol"].isin(sample_syms)].groupby("symbol")
    }

    scorer = VM25Scorer(prefer="opt")
    assert scorer.load()
    feats_names = list(scorer.feature_names)

    return by, feats_names, scorer


def get_regime_map() -> dict[str, str]:
    """Fetch SH index from East Money, compute 5d return buckets."""
    out: dict[str, str] = {}
    try:
        import requests

        r = requests.get(
            "https://push2his.eastmoney.com/api/qt/stock/kline/get",
            params={
                "secid": "1.000001",
                "fields1": "f1,f2,f3,f4,f5,f6",
                "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
                "klt": 101,
                "fqt": 1,
                "end": "20500101",
                "lmt": 200,
            },
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"},
        )
        rows = (r.json().get("data") or {}).get("klines") or []
        dates, closes = [], []
        for row in rows:
            p = str(row).split(",")
            dates.append(p[0][:10])
            closes.append(float(p[2]))
        s = pd.Series(closes, index=dates)
        ret5 = s.pct_change(5)
        for d, v in ret5.items():
            if pd.isna(v):
                continue
            if v <= -0.05:
                out[d] = "severe"
            elif v <= -0.02:
                out[d] = "weak"
            else:
                out[d] = "normal"
    except Exception as e:
        print("  [warn] regime fetch failed: " + str(e), flush=True)
    return out


# ════════════════════════════════════════════════
# 2. Cross-Section Panel Builder
# ════════════════════════════════════════════════
def build_panel(
    by: dict,
    scorer,
    feats_names: list[str],
    dates: list[str],
    regimes: dict[str, str],
) -> dict[str, dict[str, list]]:
    """Build regime -> date -> [(factor_vec, y1, y2)] panel."""
    buckets: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))

    for di, d in enumerate(dates):
        reg = regimes.get(d, "unknown")
        n_ok = 0
        for sym, g in by.items():
            date_set = set(g["date"].values)
            if d not in date_set:
                continue
            ai = int(g.index[g["date"] == d][0])
            if ai < 80 or ai + 2 >= len(g):
                continue
            sub = g.iloc[: ai + 1].tail(180).copy()
            full = scorer.build_features(sub, sym)
            if full is None or len(full) < 1:
                continue
            row = full.iloc[-1]
            # labels
            y1 = float(g.iloc[ai + 1]["close"] / g.iloc[ai]["close"] - 1.0)
            buy = float(g.iloc[ai + 1]["open"])
            sell = float(g.iloc[ai + 2]["close"])
            y2 = sell / buy - 1.0 if buy > 0 else np.nan
            if np.isnan(y2):
                continue
            vec = {c: float(row.get(c, 0.0) or 0.0) for c in feats_names}
            buckets[reg][d].append((vec, y1, y2))
            n_ok += 1
        if di == 0 or (di + 1) % 20 == 0 or di == len(dates) - 1:
            print(f"  section {di+1}/{len(dates)}  {d} [{reg}]  cross={n_ok}", flush=True)

    # Filter low-cross days
    for reg in list(buckets.keys()):
        for d in list(buckets[reg].keys()):
            if len(buckets[reg][d]) < MIN_CROSS:
                del buckets[reg][d]
        if not buckets[reg]:
            del buckets[reg]

    return dict(buckets)


# ════════════════════════════════════════════════
# 3. ICIR Core
# ════════════════════════════════════════════════
def compute_icir(
    panel: dict[str, dict[str, list]],
    factor_list: list[str],
    label_idx: int = 1,
) -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = {}
    for reg, by_date in panel.items():
        ic_dict: dict[str, list[float]] = defaultdict(list)
        for d, rows in by_date.items():
            if len(rows) < MIN_CROSS:
                continue
            ys = np.array([r[label_idx] for r in rows], dtype=float)
            for f in factor_list:
                xs = np.array([r[0].get(f, 0.0) for r in rows], dtype=float)
                if np.nanstd(xs) < 1e-12:
                    continue
                corr, _ = spearmanr(xs, ys)
                if corr == corr:
                    ic_dict[f].append(float(corr))
        rows_out = []
        for f, arr in ic_dict.items():
            if len(arr) < MIN_IC_DAYS:
                continue
            arr_np = np.array(arr)
            mu = float(np.mean(arr_np))
            sd = float(np.std(arr_np)) + 1e-12
            rows_out.append({
                "factor": f, "n_days": len(arr),
                "mean_ic": round(mu, 4), "icir": round(mu / sd, 4),
                "ic_std": round(float(sd), 4),
                "pos_ic_rate": round(float(np.mean(arr_np > 0)), 4),
            })
        rows_out.sort(key=lambda x: -abs(x["icir"] if x["icir"] != 0 else x["mean_ic"]))
        result[reg] = rows_out
    return result


def compute_weights(
    icir_data: dict[str, list[dict]],
    regime_w: dict[str, float] | None = None,
    top_k: int = TOP_K,
) -> dict:
    if regime_w is None:
        regime_w = {"normal": 1.0, "weak": 1.0, "severe": 1.0}
    all_f: set[str] = set()
    for rows in icir_data.values():
        for r in rows:
            all_f.add(r["factor"])
    weighted: dict[str, float] = {}
    for f in all_f:
        total, ws = 0.0, 0.0
        for reg, rows in icir_data.items():
            rw = regime_w.get(reg, 1.0)
            for r in rows:
                if r["factor"] == f:
                    total += r["icir"] * rw
                    ws += rw
                    break
        if ws > 0:
            weighted[f] = total / ws
    pos = {f: v for f, v in weighted.items() if v > 0}
    if not pos:
        pos = {f: abs(v) for f, v in weighted.items() if v != 0}
    sorted_f = sorted(pos.items(), key=lambda x: -x[1])[:top_k]
    total_v = sum(v for _, v in sorted_f) + 1e-12
    weights = [{"factor": f, "icir": round(v, 4), "weight": round(v / total_v, 6)}
               for f, v in sorted_f]
    return {"top_k": top_k, "regime_weights": regime_w,
            "n_factors": len(weights), "weights": weights,
            "note": "weight_i = ICIR_i / sum(ICIR) for positive-ICIR factors"}


def group_stats(
    icir_data: dict[str, list[dict]],
    factor_groups: dict[str, list[str]],
) -> dict[str, dict]:
    stats = {}
    for g_name, cols in factor_groups.items():
        total_abs, cnt = 0.0, 0
        best = {"factor": "", "icir": -999, "regime": ""}
        for reg, rows in icir_data.items():
            fm = {r["factor"]: r for r in rows}
            for f in cols:
                if f in fm:
                    v = abs(fm[f]["icir"])
                    total_abs += v
                    cnt += 1
                    if v > best["icir"]:
                        best = {"factor": f, "icir": round(v, 4), "regime": reg}
        stats[g_name] = {"n_total": len(cols), "n_present": cnt,
                         "avg_abs_icir": round(total_abs / max(cnt, 1), 4), "best": best}
    return stats


# ════════════════════════════════════════════════
# 4. 3-Scheme Evaluation
# ════════════════════════════════════════════════
def split_panel(panel, ratio=0.7):
    all_dates = sorted(set(d for rows in panel.values() for d in rows.keys()))
    n = len(all_dates)
    si = int(n * ratio)
    tr = set(all_dates[:si])
    te = set(all_dates[si:])
    tp, tep = {}, {}
    for reg, by_date in panel.items():
        tb = {d: v for d, v in by_date.items() if d in tr}
        teb = {d: v for d, v in by_date.items() if d in te}
        if tb:
            tp[reg] = tb
        if teb:
            tep[reg] = teb
    return tp, tep


def eval_scheme_A(train_panel, test_panel, flist, top_k=30):
    """Pure ICIR weighting."""
    icir_r = compute_icir(train_panel, flist, label_idx=1)
    wo = compute_weights(icir_r, regime_w={"normal": 0.5, "weak": 0.3, "severe": 0.2}, top_k=top_k)
    wm = {w["factor"]: w["weight"] for w in wo["weights"]}
    if not wm:
        return []
    ics = []
    for reg in sorted(test_panel):
        for d in sorted(test_panel[reg]):
            rows = test_panel[reg][d]
            if len(rows) < MIN_CROSS:
                continue
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
            if len(alphas) < MIN_CROSS:
                continue
            icv, _ = spearmanr(alphas, actuals)
            if np.isfinite(icv):
                ics.append(icv)
    return ics


def eval_scheme_B(train_panel, test_panel, flist):
    """XGBoost ML on all factors."""
    try:
        import xgboost as xgb
    except ImportError:
        print("    [warn] xgboost not available, scheme B skipped")
        return []
    X, y = [], []
    for reg, by_date in train_panel.items():
        for d, rows in by_date.items():
            for vec, y1, y2 in rows:
                X.append([vec.get(f, 0.0) for f in flist])
                y.append(y1)
    if len(X) < 30:
        return []
    Xa, ya = np.array(X), np.array(y)
    model = xgb.XGBRegressor(
        n_estimators=100, max_depth=4, learning_rate=0.1,
        subsample=0.8, colsample_bytree=0.8, random_state=42, verbosity=0,
    )
    model.fit(Xa, ya)
    ics = []
    for reg in sorted(test_panel):
        for d in sorted(test_panel[reg]):
            rows = test_panel[reg][d]
            if len(rows) < MIN_CROSS:
                continue
            Xt = np.array([[vec.get(f, 0.0) for f in flist] for vec, y1, y2 in rows])
            pr = model.predict(Xt)
            ac = np.array([y1 for _, y1, _ in rows])
            icv, _ = spearmanr(pr, ac)
            if np.isfinite(icv):
                ics.append(icv)
    return ics


def eval_scheme_C(train_panel, test_panel, flist, top_k=30):
    """Hybrid: ICIR filter -> XGBoost on top factors."""
    try:
        import xgboost as xgb
    except ImportError:
        print("    [warn] xgboost not available, scheme C skipped")
        return [], []
    icir_r = compute_icir(train_panel, flist, label_idx=1)
    all_ic: dict[str, float] = {}
    for reg, rows in icir_r.items():
        for r in rows:
            all_ic[r["factor"]] = max(all_ic.get(r["factor"], 0), abs(r["icir"]))
    top_f = sorted(all_ic, key=all_ic.get, reverse=True)[:top_k]
    if len(top_f) < 5:
        return [], top_f
    X, y = [], []
    for reg, by_date in train_panel.items():
        for d, rows in by_date.items():
            for vec, y1, y2 in rows:
                X.append([vec.get(f, 0.0) for f in top_f])
                y.append(y1)
    if len(X) < 30:
        return [], top_f
    Xa, ya = np.array(X), np.array(y)
    model = xgb.XGBRegressor(
        n_estimators=100, max_depth=4, learning_rate=0.1,
        subsample=0.8, colsample_bytree=0.8, random_state=42, verbosity=0,
    )
    model.fit(Xa, ya)
    ics = []
    for reg in sorted(test_panel):
        for d in sorted(test_panel[reg]):
            rows = test_panel[reg][d]
            if len(rows) < MIN_CROSS:
                continue
            Xt = np.array([[vec.get(f, 0.0) for f in top_f] for vec, y1, y2 in rows])
            pr = model.predict(Xt)
            ac = np.array([y1 for _, y1, _ in rows])
            icv, _ = spearmanr(pr, ac)
            if np.isfinite(icv):
                ics.append(icv)
    return ics, top_f


def comp_metrics(name: str, ics: list) -> dict:
    if len(ics) < 3:
        return {"name": name, "error": "insufficient data"}
    arr = np.array(ics)
    mu = float(np.mean(arr))
    sd = float(np.std(arr)) + 1e-12
    return {
        "name": name, "n_test_days": len(arr), "mean_rankic": round(mu, 4),
        "rankic_std": round(float(sd), 4), "rank_icir": round(mu / sd, 4),
        "hit_rate": round(float(np.mean(arr > 0)), 4),
    }


# ════════════════════════════════════════════════
# 5. HTML Report Generator
# ════════════════════════════════════════════════
def gen_html(
    metrics: dict,
    daily_data: dict[str, list[float]],
    flist: list[str],
    out_path: Path,
    top_f_c: list[str] | None = None,
    run_config: dict | None = None,
):
    colors = {"A_ICIR": "#4C72B0", "B_XGBoost": "#DD8452", "C_Hybrid": "#55A868"}
    labels = {"A_ICIR": "A) Pure ICIR", "B_XGBoost": "B) XGBoost ML", "C_Hybrid": "C) Hybrid ICIR+ML"}
    cd = {}
    for s in ["A_ICIR", "B_XGBoost", "C_Hybrid"]:
        ics = daily_data.get(s, [])
        if ics:
            cd[s] = [round(v, 4) for v in ics]
    best = max(metrics, key=lambda k: metrics[k].get("rank_icir", -999)) if metrics else ""

    nf = len(flist)
    tr_pct = int(TRAIN_RATIO * 100)
    te_pct = int((1 - TRAIN_RATIO) * 100)
    rc = run_config or {}

    html = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>AlphaPilot - ICIR Prod Analysis</title>
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
@media(max-width:768px){.cards{grid-template-columns:1fr}}
</style></head>
<body><div class="container">
<div class="header"><h1>AlphaPilot ICIR Prod Analysis</h1>
<p>Data: real A-share (kline_all.parquet + VM2.5 production features)</p>
<p>Factors: N_FAC factors | Sample: N_SAM stocks | Period: START_D ~ END_D</p>
<p>Metric: Daily cross-sectional Spearman RankIC(alpha, next-day return)</p></div>
<div class="cards">""".replace("N_FAC", str(nf)).replace("N_SAM", str(rc.get("sample", "?"))).replace("START_D", str(rc.get("start", "?"))).replace("END_D", str(rc.get("end", "?")))

    for s in ["A_ICIR", "B_XGBoost", "C_Hybrid"]:
        m = metrics.get(s, {})
        if "error" in m:
            html += '<div class="card" style="border-top-color:' + colors[s] + '"><h3>' + labels[s] + '</h3><p style="color:#999">Insufficient data</p></div>'
            continue
        iw = s == best
        bg = '<span class="bdg bdgw">Best</span>' if iw else '<span class="bdg bdgr">--</span>'
        html += '<div class="card" style="border-top-color:' + colors[s] + '">' + bg + '<h3>' + labels[s] + '</h3><table>'
        html += '<tr><td>Rank ICIR</td><td style="color:' + colors[s] + '">' + str(m.get("rank_icir", "N/A")) + '</td></tr>'
        html += '<tr><td>Mean RankIC</td><td>' + str(m.get("mean_rankic", "N/A")) + '</td></tr>'
        hr = m.get("hit_rate", "N/A")
        html += '<tr><td>Hit Rate</td><td>' + (f"{hr:.1%}" if isinstance(hr, float) else str(hr)) + '</td></tr>'
        html += '<tr><td>RankIC Std</td><td>' + str(m.get("rankic_std", "N/A")) + '</td></tr>'
        html += '<tr><td>Test Days</td><td>' + str(m.get("n_test_days", "N/A")) + '</td></tr></table></div>'

    html += r"""</div>
<div class="sec"><h2>Daily RankIC Comparison</h2><div class="cw"><canvas id="c1"></canvas></div></div>
<div class="sec"><h2>Cumulative RankIC (Stability View)</h2><div class="cw"><canvas id="c2"></canvas></div></div>
<div class="rec"><h2>Recommendation</h2><p id="rt">Loading...</p></div>
<div class="ft">AlphaPilot ICIR Prod | Generated TS</div></div>
<script>
const C = COLS, L = LABS, D = CDATA, M = MDATA, TF = TFDATA;
let best=null,bi=-999;
for(const[k,v]of Object.entries(M)){if(v.rank_icir&&v.rank_icir>bi){bi=v.rank_icir;best=k}}
function mkDS(l,data,c){return{label:l,data:data.map((v,i)=>({x:i,y:v})),borderColor:c,backgroundColor:c,borderWidth:2,pointRadius:0,tension:.1}}
new Chart(document.getElementById('c1').getContext('2d'),{type:'line',data:{datasets:Object.entries(D).map(([k,v])=>mkDS(L[k]||k,v,C[k]))},options:{responsive:true,maintainAspectRatio:false,interaction:{intersect:false,mode:'index'},plugins:{legend:{position:'top'}},scales:{x:{title:{display:true,text:'Test Day'}},y:{title:{display:true,text:'Spearman RankIC'}}}}});
const ds2=[];for(const[k,v]of Object.entries(D)){let c=0;ds2.push(mkDS(L[k]||k,v.map(x=>(c+=x,c)),C[k]))}
new Chart(document.getElementById('c2').getContext('2d'),{type:'line',data:{datasets:ds2},options:{responsive:true,maintainAspectRatio:false,interaction:{intersect:false,mode:'index'},plugins:{legend:{position:'top'}},scales:{x:{title:{display:true,text:'Test Day'}},y:{title:{display:true,text:'Cumulative RankIC'}}}}});
const rt=document.getElementById('rt');
if(best&&M[best]){const bm=M[best],lm={'A_ICIR':'Pure ICIR','B_XGBoost':'XGBoost ML','C_Hybrid':'Hybrid ICIR+ML'};
rt.innerHTML='<strong>Winner: '+(lm[best]||best)+'</strong> -- Rank ICIR='+bm.rank_icir+', Hit Rate='+(bm.hit_rate*100).toFixed(0)+'%. '+
'This scheme shows the highest prediction stability on the test set. Recommend using this scheme for factor weighting in production, with monthly ICIR recalibration.'+
(TF&&TF.length?'<br><br><strong>Hybrid Top Factors:</strong> '+TF.slice(0,15).join(', ')+(TF.length>15?', ...':'') :'');
}else{rt.textContent='Insufficient data to determine recommendation.'}
</script></body></html>"""

    html = html.replace("COLS", json.dumps(colors, ensure_ascii=False))
    html = html.replace("LABS", json.dumps(labels, ensure_ascii=False))
    html = html.replace("CDATA", json.dumps(cd, ensure_ascii=False))
    html = html.replace("MDATA", json.dumps(metrics, ensure_ascii=False))
    html = html.replace("TFDATA", json.dumps(top_f_c or [], ensure_ascii=False))
    html = html.replace("TS", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    out_path.write_text(html, "utf-8")
    print("  HTML report saved: " + str(out_path), flush=True)


# ════════════════════════════════════════════════
# 6. Main
# ════════════════════════════════════════════════
def main():
    ap = argparse.ArgumentParser(description="ICIR Production Analysis + 3-Scheme Comparison")
    ap.add_argument("--start", default="2026-01-01", help="Start date (YYYY-MM-DD)")
    ap.add_argument("--end", default="2026-07-17", help="End date (YYYY-MM-DD)")
    ap.add_argument("--sample", type=int, default=600, help="Number of stocks to sample")
    ap.add_argument("--step", type=int, default=2, help="Cross-section step (days)")
    ap.add_argument("--top-k", type=int, default=30, help="Top K factors for ICIR weighting")
    args = ap.parse_args()

    global STEP, TOP_K
    STEP = args.step
    TOP_K = args.top_k

    t0 = time.time()
    out_dir = ROOT / "output" / "icir_prod"
    out_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("  AlphaPilot ICIR Prod Analysis")
    print("  Period: " + str(args.start) + " ~ " + str(args.end))
    print("  Sample: " + str(args.sample) + " stocks")
    print("=" * 60)

    # ── 1. Load data ──
    print("\n[1/6] Loading data + building VM2.5 features...")
    by, feats_names, scorer = load_data(args.start, args.end, args.sample)
    print("  stocks: " + str(len(by)) + "  features: " + str(len(feats_names)))

    # ── 2. Fetch regime ──
    print("\n[2/6] Fetching SH index regimes...")
    regimes = get_regime_map()
    print("  regimes: " + str(len(regimes)) + " days")
    reg_cnt = defaultdict(int)
    for r in regimes.values():
        reg_cnt[r] += 1
    for reg, cnt in sorted(reg_cnt.items()):
        print("    " + str(reg) + ": " + str(cnt) + " days")

    # ── 3. Build panel ──
    print("\n[3/6] Building cross-section panel (step=" + str(STEP) + "d)...")
    all_dates = sorted(d for d in by[next(iter(by))]["date"].unique()
                       if args.start <= d <= args.end)
    all_dates = all_dates[::max(STEP, 1)]
    print("  cross-section dates: " + str(len(all_dates)))

    panel = build_panel(by, scorer, feats_names, all_dates, regimes)

    total_sec = sum(len(v) for v in panel.values())
    print("  effective cross-sections: " + str(total_sec))
    for reg, by_date in sorted(panel.items()):
        avg = sum(len(v) for v in by_date.values()) // max(len(by_date), 1)
        print("    " + str(reg) + ": " + str(len(by_date)) + "d  avg=" + str(avg) + " stocks")

    # ── 4. ICIR + Weights ──
    print("\n[4/6] Computing ICIR and weights...")
    icir_data = compute_icir(panel, feats_names, label_idx=1)

    w_regime = compute_weights(icir_data,
                                regime_w={"normal": 0.5, "weak": 0.3, "severe": 0.2},
                                top_k=TOP_K)
    w_equal = compute_weights(icir_data,
                               regime_w={"normal": 1.0, "weak": 1.0, "severe": 1.0},
                               top_k=TOP_K)

    # Build factor groups from VM2.5 feature name heuristics
    factor_groups: dict[str, list[str]] = {
        "momentum": [f for f in feats_names if "ret" in f.lower() or "mom" in f.lower() or "macd" in f.lower()],
        "volume": [f for f in feats_names if "vol" in f.lower() or "turnover" in f.lower() or "amount" in f.lower()],
        "volatility": [f for f in feats_names if "atr" in f.lower() or "std" in f.lower() or "skew" in f.lower() or "kurt" in f.lower()],
        "price_pattern": [f for f in feats_names if "ma" in f.lower() or "sma" in f.lower() or "bb" in f.lower() or "rsi" in f.lower()],
        "fundamental": [f for f in feats_names if "eps" in f.lower() or "roe" in f.lower() or "pe" in f.lower() or "pb" in f.lower() or "profit" in f.lower()],
        "fund_flow": [f for f in feats_names if "main" in f.lower() or "net" in f.lower() or "margin" in f.lower()],
        "event": [f for f in feats_names if "lhb" in f.lower() or "forecast" in f.lower() or "yg" in f.lower()],
        "chip": [f for f in feats_names if "chip" in f.lower() or "cost" in f.lower() or "distribution" in f.lower()],
        "other": [f for f in feats_names if f not in [
            x for group in [
                [g for g in feats_names if "ret" in g.lower() or "mom" in g.lower() or "macd" in g.lower()],
                [g for g in feats_names if "vol" in g.lower() or "turnover" in g.lower() or "amount" in g.lower()],
                [g for g in feats_names if "atr" in g.lower() or "std" in g.lower() or "skew" in g.lower() or "kurt" in g.lower()],
                [g for g in feats_names if "ma" in g.lower() or "sma" in g.lower() or "bb" in g.lower() or "rsi" in g.lower()],
                [g for g in feats_names if "eps" in g.lower() or "roe" in g.lower() or "pe" in g.lower() or "pb" in g.lower() or "profit" in g.lower()],
                [g for g in feats_names if "main" in g.lower() or "net" in g.lower() or "margin" in g.lower()],
                [g for g in feats_names if "lhb" in g.lower() or "forecast" in g.lower() or "yg" in g.lower()],
                [g for g in feats_names if "chip" in g.lower() or "cost" in g.lower() or "distribution" in g.lower()],
            ] for x in group
        ]],
    }

    gs = group_stats(icir_data, factor_groups)

    # Print top ICIR per regime
    print("\n  == [ICIR Ranking - VM2.5 features] ==")
    for reg, rows in sorted(icir_data.items()):
        print("\n  [" + str(reg) + "]")
        print("  {:<30s} {:>8s} {:>8s} {:>6s} {:>5s}".format("factor", "IC", "ICIR", "pos%", "days"))
        print("  " + "-" * 60)
        for r in rows[:10]:
            print("  {:<30s} {:>+8.4f} {:>+8.4f} {:>5.0%} {:>5d}".format(
                r["factor"], r["mean_ic"], r["icir"], r["pos_ic_rate"], r["n_days"]))
        if len(rows) > 10:
            print("  ... " + str(len(rows) - 10) + " more factors")

    # Print weights
    print("\n  == [ICIR Weights (regime-weighted) top " + str(TOP_K) + "] ==")
    print("  {:<30s} {:>8s} {:>10s}".format("factor", "ICIR", "weight"))
    for w in w_regime["weights"][:15]:
        print("  {:<30s} {:>+8.4f} {:>10.4%}".format(w["factor"], w["icir"], w["weight"]))

    print("\n  == [Factor Group |ICIR| Ranking] ==")
    sorted_gs = sorted(gs.items(), key=lambda x: -x[1]["avg_abs_icir"])
    for g_name, st in sorted_gs:
        print("    {:<15s}: avg|ICIR|={:.4f}  best={}({})".format(
            g_name, st["avg_abs_icir"], st["best"]["factor"], st["best"]["icir"]))

    # ── 5. 3-Scheme Comparison ──
    print("\n[5/6] 3-Scheme Comparison...")
    tp, tep = split_panel(panel, TRAIN_RATIO)
    td = sum(len(v) for v in tp["all"].values()) if "all" in tp else sum(len(v) for v in tp.values())
    ted = sum(len(v) for v in tep["all"].values()) if "all" in tep else sum(len(v) for v in tep.values())
    print("  train=" + str(int(TRAIN_RATIO * 100)) + "% test=" + str(int((1 - TRAIN_RATIO) * 100)) + "%")
    print("  train_cross_sections: " + str(td) + "  test_cross_sections: " + str(ted))

    print("  A) Pure ICIR...", end=" ", flush=True)
    ica = eval_scheme_A(tp, tep, feats_names, TOP_K)
    print(str(len(ica)) + " valid test days")

    print("  B) XGBoost ML (all factors)...", end=" ", flush=True)
    icb = eval_scheme_B(tp, tep, feats_names)
    print(str(len(icb)) + " valid test days")

    print("  C) Hybrid ICIR+ML...", end=" ", flush=True)
    icc, tfc = eval_scheme_C(tp, tep, feats_names, TOP_K)
    print(str(len(icc)) + " valid test days")
    if tfc:
        print("    top factors: " + ", ".join(tfc[:10]) + ("..." if len(tfc) > 10 else ""))

    metrics = {}
    for s, ics in [("A_ICIR", ica), ("B_XGBoost", icb), ("C_Hybrid", icc)]:
        metrics[s] = comp_metrics(s, ics)

    print()
    print("  " + "=" * 60)
    print("  {:<25s} {:>10s} {:>10s} {:>10s} {:>6s}".format("Scheme", "RankICIR", "MeanIC", "HitRate", "Days"))
    print("  " + "=" * 60)
    for s in ["A_ICIR", "B_XGBoost", "C_Hybrid"]:
        m = metrics.get(s, {})
        if "error" in m:
            print("  {:<25s} {:>10s}".format(s, "--"))
        else:
            print("  {:<25s} {:>+10.4f} {:>+10.4f} {:>10.1%} {:>6d}".format(
                s, m.get("rank_icir", 0), m.get("mean_rankic", 0),
                m.get("hit_rate", 0), m.get("n_test_days", 0)))
    print("  " + "=" * 60)

    # ── 6. Save ──
    print("\n[6/6] Saving results...")

    # Unified output
    run_config = {"start": args.start, "end": args.end, "sample": args.sample,
                  "step": STEP, "top_k": TOP_K, "n_features": len(feats_names)}
    output = {
        "analysis_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "config": run_config,
        "regime_distribution": dict(reg_cnt),
        "icir_by_regime": icir_data,
        "icir_weights": {"regime_weighted": w_regime, "equal_regime": w_equal},
        "factor_group_stats": gs,
        "factor_names": feats_names,
        "scheme_compare": {
            "train_test_split": {"train_pct": TRAIN_RATIO, "train_sections": td, "test_sections": ted},
            "metrics": metrics,
            "test_daily_ics": {k: [round(v, 4) for v in vals]
                                for k, vals in {"A_ICIR": ica, "B_XGBoost": icb, "C_Hybrid": icc}.items()},
            "hybrid_top_factors": tfc,
        },
        "note": "IC = cross-sectional Spearman RankIC(factor, next-day return) | ICIR = mean(IC)/std(IC)",
    }
    json_path = out_dir / "icir_ranking.json"
    json_path.write_text(json.dumps(output, ensure_ascii=False, indent=2, default=str), "utf-8")
    print("  JSON: " + str(json_path))

    # Scheme compare json
    sc_path = out_dir / "scheme_compare.json"
    sc_path.write_text(json.dumps(output["scheme_compare"], ensure_ascii=False, indent=2, default=str), "utf-8")
    print("  Scheme JSON: " + str(sc_path))

    # HTML report
    html_path = out_dir / "scheme_report.html"
    gen_html(metrics, {"A_ICIR": ica, "B_XGBoost": icb, "C_Hybrid": icc},
             feats_names, html_path, tfc, run_config)

    # Also save weights as standalone CSV-friendly JSON
    w_path = out_dir / "icir_weights.json"
    w_path.write_text(json.dumps({
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "regime_weighted": w_regime,
        "equal_regime": w_equal,
        "scheme_summary": {
            "A_ICIR": "ICIR normalized weights, explicit factor portfolio",
            "B_XGBoost": "Current XGBoost ensemble, implicit ML weighting on all factors",
            "C_Hybrid": "ICIR filter top {top_k} factors -> XGBoost fine ranking".format(top_k=TOP_K),
        }
    }, ensure_ascii=False, indent=2), "utf-8")
    print("  Weights: " + str(w_path))

    elapsed = time.time() - t0
    print("\n" + "=" * 60)
    print("  ICIR Prod Analysis Complete")
    print("  Elapsed: " + str(round(elapsed, 1)) + "s")
    print("  Files: " + str(out_dir))
    print("=" * 60)

    # Print final summary
    print("\n  == [Final Recommendation] ==")
    best_s = max(metrics, key=lambda k: metrics[k].get("rank_icir", -999))
    bm = metrics.get(best_s, {})
    scheme_names = {"A_ICIR": "Pure ICIR", "B_XGBoost": "XGBoost ML", "C_Hybrid": "Hybrid ICIR+ML"}
    print("  Best scheme: " + scheme_names.get(best_s, best_s))
    print("  Rank ICIR: " + str(bm.get("rank_icir", "N/A")))
    print("  Hit Rate: " + str(bm.get("hit_rate", "N/A")))
    print("  Test days: " + str(bm.get("n_test_days", "N/A")))


if __name__ == "__main__":
    main()

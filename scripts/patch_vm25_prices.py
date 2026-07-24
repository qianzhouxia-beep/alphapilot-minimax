#!/usr/bin/env python3
from pathlib import Path
import py_compile

ROOT = Path("/home/ubuntu/alphapilot")

# 1) vm25_scorer return fields
vp = ROOT / "vm25_scorer.py"
vs = vp.read_text(encoding="utf-8")
old = '''        return {
            "score": round(final, 4),
            "lgb_score": round(proba, 4),
            "ml_score": round(proba, 4),
            "sector_heat": round(float(sector_heat), 4),
            "buy_price": close,
            "model": "vm25",
            "n_features": len(self.feature_names),
        }'''
new = '''        target_price = round(close * 1.04, 2)
        stop_price = round(close * 0.97, 2)
        return {
            "score": round(final, 4),
            "lgb_score": round(proba, 4),
            "ml_score": round(proba, 4),
            "sector_heat": round(float(sector_heat), 4),
            "buy_price": close,
            "target_price": target_price,
            "stop_price": stop_price,
            "model": "vm25",
            "n_features": len(self.feature_names),
        }'''
if old not in vs:
    raise SystemExit("vm25 return block not found")
vp.write_text(vs.replace(old, new, 1), encoding="utf-8")
py_compile.compile(str(vp), doraise=True)
print("OK vm25_scorer")

# 2) recommend print resilient
rp = ROOT / "recommend.py"
rs = rp.read_text(encoding="utf-8")
oldp = '''        print(f"   {i}. {r['symbol']} {r['name']} | 评分: {r['score']:.4f}{_ov} | "
              f"买入: {r['buy_price']:.2f} | 目标: {r['target_price']:.2f}")'''
newp = '''        print(f"   {i}. {r['symbol']} {r['name']} | 评分: {r['score']:.4f}{_ov} | "
              f"买入: {float(r.get('buy_price') or 0):.2f} | 目标: {float(r.get('target_price') or 0):.2f}")'''
if oldp not in rs:
    # try already patched
    if "r.get('target_price')" in rs or 'r.get("target_price")' in rs:
        print("recommend print already resilient")
    else:
        raise SystemExit("recommend print block not found")
else:
    rp.write_text(rs.replace(oldp, newp, 1), encoding="utf-8")
    print("OK recommend print")
py_compile.compile(str(rp), doraise=True)
print("PATCH_DONE")

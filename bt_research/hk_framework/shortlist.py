#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""shortlist: 生成港股「做空候选 + 风险状态」清单（Cursor 2026-09-10）。

逻辑（经长样本 + 样本外验证）：
  - 做空候选 = 打分最差的一端（高分波动 + 南向拥挤），即 score 最低的 bottom_n
  - 只在 regime=risk_off（指数下跌 + 广度弱）时给出；risk_on 时返回空（不逆势裸空）
  - 逐票过现实约束：港交所可卖空名单 + 非仙股 + 非妖股
输出: output/shortlist_{date}.json  （给香港直投券商的执行候选；本脚本只读，不下单）
"""
import argparse
import datetime as dt
import json

import config as C
import dataio as io
import factors as F
import regime as R
import signals as S


def _ok(ctx, code, date):
    bars, i = ctx.bar(code, date)
    if not bars or i < 2:
        return False, "no_bar"
    if bars[i]["c"] < C.SHORT_MIN_PRICE:
        return False, "penny"
    prev, prev2 = bars[i - 1]["c"], bars[i - 2]["c"]
    if prev2 and abs(prev / prev2 - 1) > C.SHORT_MAX_ABS_1D:
        return False, "limit_move"
    sk = io.load(C.F_SHORTABLE, {}) or {}
    if sk.get("codes") and code not in set(sk["codes"]):
        return False, "not_shortable"
    return True, "ok"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bottom", type=int, default=10)
    ap.add_argument("--date", default=None)
    args = ap.parse_args()

    kline = io.load(C.F_KLINE, {}) or {}
    south = io.load(C.F_SOUTH, {}) or {}
    pool = io.load(C.F_POOL, {}) or {}
    codes = pool.get("codes") or list(south[max(south.keys())].keys())
    ctx = F.Context(kline, south, codes)
    date = args.date or pool.get("date") or max(south.keys())

    tr = R.index_trend(ctx, date)
    br = R.breadth(ctx, date)
    risk_on = (tr == 1) or (tr == 0 and (br or 0) >= 0.5)
    ranked = S.score(ctx, date)          # 降序：高分=防/空候选在末
    cands = []
    for r in ranked[-args.bottom * 4:][::-1]:   # 从最差一端取
        ok, why = _ok(ctx, r["code"], date)
        if ok:
            cands.append({**r, "reason": why})
        if len(cands) >= args.bottom:
            break

    out = {
        "date": date,
        "generated_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "regime": {"index_trend": tr, "breadth": round(br, 3) if br else None,
                   "risk_on": risk_on},
        "action": "no_short_recommended" if risk_on else "short_candidates",
        "n_universe": len(codes),
        "short_bottom_n": args.bottom,
        "candidates": cands,
        "weight_file": C.F_WEIGHTS,
        "note": "仅研究/纸盘；实盘做空需自行确认可借券与费率。",
    }
    path = C.F_PICKS.format(date=date).replace("picks_", "shortlist_")
    io.save_atomic(out, path)
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()

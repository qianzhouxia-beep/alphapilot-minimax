#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""拉取近 N 日龙虎榜，写入 data/lhb_history.json

格式: {code: {"dates": {"YYYY-MM-DD": buy_inst_count}, "has_lhb_days": n}}
供 train_v25 / vm25 在对应日期打 has_lhb / buy_inst_count。
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path("/home/ubuntu/alphapilot")
os.chdir(ROOT)


def bare(sym: str) -> str:
    s = str(sym).strip()
    if "." in s:
        s = s.split(".")[0]
    return s.zfill(6)[-6:]


def main(days: int = 40):
    import akshare as ak

    out: dict[str, dict] = {}
    d0 = datetime.now()
    for i in range(days):
        d = (d0 - timedelta(days=i)).strftime("%Y%m%d")
        d_dash = f"{d[:4]}-{d[4:6]}-{d[6:8]}"
        try:
            df = ak.stock_lhb_detail_em(start_date=d, end_date=d)
        except Exception as e:
            print(f"  skip {d}: {e}")
            continue
        if df is None or df.empty:
            continue
        code_col = next((c for c in df.columns if "代码" in str(c)), None)
        if not code_col:
            continue
        print(f"  {d}: {len(df)} rows")
        for _, row in df.iterrows():
            code = bare(row[code_col])
            if len(code) != 6:
                continue
            # 买方机构家数（列名因接口版本而异）
            inst = 0
            for k in ("买方机构数", "买入营业部数量", "机构买入次数"):
                if k in row.index:
                    try:
                        inst = int(float(row.get(k) or 0))
                        break
                    except Exception:
                        pass
            slot = out.setdefault(code, {"dates": {}, "has_lhb_days": 0})
            prev = int(slot["dates"].get(d_dash, 0) or 0)
            slot["dates"][d_dash] = max(prev, inst, 1)
    for code, slot in out.items():
        slot["has_lhb_days"] = len(slot["dates"])

    path = ROOT / "data" / "lhb_history.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(f"saved {path} symbols={len(out)}")


if __name__ == "__main__":
    main()

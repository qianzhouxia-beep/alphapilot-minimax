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


def main(days: int = 250):
    import akshare as ak

    out: dict[str, dict] = {}
    # 保留已有历史，只补充新日期（增量 + 回填）
    path = ROOT / "data" / "lhb_history.json"
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(existing, dict):
                out = existing
        except Exception:
            out = {}

    d0 = datetime.now()
    seen_days = 0
    for i in range(days):
        d = (d0 - timedelta(days=i)).strftime("%Y%m%d")
        d_dash = f"{d[:4]}-{d[4:6]}-{d[6:8]}"
        # 已有该日期的完整数据则跳过（节省请求）
        already = all(d_dash in (slot.get("dates") or {}) for slot in out.values()) if out else False
        if already:
            continue
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
        seen_days += 1
        if seen_days % 20 == 0:
            print(f"  ...{d} 已处理 {seen_days} 个有数据交易日")
        for _, row in df.iterrows():
            code = bare(row[code_col])
            if len(code) != 6:
                continue
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

    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(f"saved {path} symbols={len(out)}")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=250)
    args = ap.parse_args()
    main(days=args.days)

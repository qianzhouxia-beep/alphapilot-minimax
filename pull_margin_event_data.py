#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""拉取融资融券 + 业绩预告，写入 data/margin_data.json / data/event_forecast.json。

改进:
  - 失败时不覆盖已有非空文件
  - 多日期回退（今日/昨日/近 5 个交易日）
  - 统一 6 位代码
"""
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

os.chdir("/home/ubuntu/alphapilot")
DATA = Path("data")
DATA.mkdir(exist_ok=True)


def load_existing(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        d = json.load(open(path, encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def save_json(path: Path, data: dict):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def candidate_dates(n=7):
    """生成候选日期 YYYYMMDD（含周末，接口内部会忽略非交易日）。"""
    out = []
    d = datetime.now()
    for i in range(n):
        out.append((d - timedelta(days=i)).strftime("%Y%m%d"))
    return out


def extract_code(row, cols):
    for c in cols:
        if c in row.index:
            return str(row[c]).strip().zfill(6)[-6:]
    # fallback: 任意含「代码」列
    for c in row.index:
        if "代码" in str(c):
            return str(row[c]).strip().zfill(6)[-6:]
    return ""


def pull_margin(ak) -> dict:
    margin_all = {}
    for date in candidate_dates():
        for label, fn in (
            ("深交所", ak.stock_margin_detail_szse),
            ("上交所", ak.stock_margin_detail_sse),
        ):
            try:
                df = fn(date=date)
            except Exception as e:
                print(f"  {label} {date} 失败: {e}")
                continue
            if df is None or df.empty:
                continue
            print(f"  {label} {date}: {len(df)} 条")
            code_cols = [c for c in df.columns if "代码" in str(c)]
            for _, row in df.iterrows():
                code = extract_code(row, code_cols)
                if not code or len(code) != 6:
                    continue
                bal = 0.0
                buy = 0.0
                for k in ("融资余额", "本日融资余额", "融资余额(元)"):
                    if k in row.index and row.get(k) is not None:
                        try:
                            bal = float(row.get(k) or 0)
                            break
                        except Exception:
                            pass
                for k in ("融资买入额", "本日融资买入额", "融资买入额(元)"):
                    if k in row.index and row.get(k) is not None:
                        try:
                            buy = float(row.get(k) or 0)
                            break
                        except Exception:
                            pass
                # 后写覆盖前写：同一只股票保留最新成功日期
                margin_all[code] = {"margin_balance": bal, "margin_buy": buy}
        if margin_all:
            # 已有数据就先收下；继续扫日期可补另一交易所
            pass
    return margin_all


def pull_event(ak) -> dict:
    yjyg_data = {}
    # 东财业绩预告接口常用报告期：本季度末 / 上季度末
    today = datetime.now()
    quarter_ends = []
    y, m = today.year, today.month
    # 当前与最近两个季报截止日
    for yy, mm in ((y, 3), (y, 6), (y, 9), (y, 12), (y - 1, 12), (y - 1, 9)):
        if (yy, mm) <= (y, ((m - 1) // 3 + 1) * 3):
            quarter_ends.append(f"{yy}{mm:02d}{(31 if mm in (3, 12) else 30):02d}")
    # 也试今天
    dates = [today.strftime("%Y%m%d")] + quarter_ends

    for date in dates:
        try:
            yjyg = ak.stock_yjyg_em(date=date)
        except Exception as e:
            print(f"  业绩预告 {date} 失败: {e}")
            continue
        if yjyg is None or yjyg.empty:
            print(f"  业绩预告 {date}: 空")
            continue
        print(f"  业绩预告 {date}: {len(yjyg)} 条")
        for _, row in yjyg.iterrows():
            code = str(row.get("股票代码", "")).strip().zfill(6)[-6:]
            if not code or len(code) != 6:
                continue
            chg = row.get("业绩变动幅度", row.get("预测上限", 0))
            try:
                chg = float(chg or 0)
            except Exception:
                chg = 0.0
            yjyg_data[code] = {
                "has_forecast": 1,
                "yjyg_max_change": chg,
                "forecast_type": str(row.get("业绩变动", row.get("业绩变动原因", "")) or ""),
            }
        if yjyg_data:
            break
    return yjyg_data


def main():
    try:
        import akshare as ak
    except ImportError:
        print("❌ 未安装 akshare")
        sys.exit(1)

    margin_path = DATA / "margin_data.json"
    event_path = DATA / "event_forecast.json"
    old_margin = load_existing(margin_path)
    old_event = load_existing(event_path)

    print("=== 拉取融资融券数据 ===")
    try:
        margin_all = pull_margin(ak)
        if margin_all:
            save_json(margin_path, margin_all)
            sh = sum(1 for k in margin_all if k.startswith("6"))
            sz = sum(1 for k in margin_all if k.startswith(("0", "3")))
            print(f"✅ 融资融券已保存: {len(margin_all)} 只 (沪{sh}/深{sz})")
        else:
            print("⚠️ 本次未拉到两融；保留旧文件")
            if not old_margin:
                save_json(margin_path, {})
    except Exception as e:
        print(f"❌ 融资融券拉取失败: {e}")
        if not old_margin:
            save_json(margin_path, {})

    print("\n=== 拉取业绩预告数据 ===")
    try:
        yjyg_data = pull_event(ak)
        if yjyg_data:
            save_json(event_path, yjyg_data)
            print(f"✅ 业绩预告已保存: {len(yjyg_data)} 只")
        else:
            print("⚠️ 本次未拉到业绩预告；保留旧文件（若旧文件也为空，训练时事件维将全零）")
            if not old_event:
                save_json(event_path, {})
    except Exception as e:
        print(f"❌ 业绩预告拉取失败: {e}")
        if not old_event:
            save_json(event_path, {})


if __name__ == "__main__":
    main()

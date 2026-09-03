#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""刷新当日行业/概念资金流榜到 data/sector_flow_*.json、concept_flow_*.json。

口径：东财「今日」= 当个交易日累计（盘中实时、收盘后为当日终值）。
写入后校验 asof == 今天（自然日）；失败非 0 退出，供 cron / refresh_all_data 感知。

用法:
  python3 scripts/refresh_sector_board_flows.py
  python3 scripts/refresh_sector_board_flows.py --require-today
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _to_rows(df, name_cols: list[str], kind: str) -> list[dict]:
    rows: list[dict] = []
    for _, r in df.iterrows():
        name = ""
        for c in name_cols:
            if c in df.columns and str(r.get(c) or "").strip():
                name = str(r.get(c)).strip()
                break
        if not name:
            continue
        net_yi = float(
            r.get("今日主力净流入-净额")
            or r.get("主力净流入-净额")
            or r.get("净额")
            or 0
        )
        main_net = net_yi if abs(net_yi) > 1e6 else net_yi * 1e8
        chg = float(
            r.get("今日涨跌幅")
            or r.get("行业-涨跌幅")
            or r.get("涨跌幅")
            or r.get("changePercent")
            or 0
        )
        code = str(r.get("行业代码") or r.get("概念代码") or r.get("代码") or "").strip()

        def _scale(v):
            try:
                x = float(v or 0)
            except (TypeError, ValueError):
                return 0.0
            return x if abs(x) > 1e6 else x * 1e8

        rows.append(
            {
                "code": code,
                "name": name,
                "changePercent": chg,
                "mainNetInflow": main_net,
                "mainNetInflowPercent": float(
                    r.get("今日主力净流入-净占比") or r.get("主力净流入-净占比") or 0
                ),
                "superLargeNetInflow": _scale(r.get("今日超大单净流入-净额")),
                "largeNetInflow": _scale(r.get("今日大单净流入-净额")),
                "mediumNetInflow": _scale(r.get("今日中单净流入-净额")),
                "smallNetInflow": _scale(r.get("今日小单净流入-净额")),
                "topStockCode": str(
                    r.get("今日主力净流入最大股") or r.get("主力净流入最大股") or ""
                ),
                "kind": kind,
                "asof": _today(),
                "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
    rows.sort(key=lambda x: -float(x["mainNetInflow"]))
    return rows


def _write(path: Path, rows: list[dict], source: str, indicator: str | None = None) -> None:
    payload = {
        "total": len(rows),
        "data": rows,
        "asof": _today(),
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": source,
    }
    if indicator:
        payload["indicator"] = indicator
    DATA.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    print(f"OK {path.name} n={len(rows)} asof={payload['asof']}", flush=True)


def refresh_today_industry(ak) -> bool:
    try:
        ind = ak.stock_sector_fund_flow_rank(indicator="今日", sector_type="行业资金流")
        rows = _to_rows(ind, ["名称", "行业"], "industry")
        _write(DATA / "sector_flow_today.json", rows, "akshare.stock_sector_fund_flow_rank")
        return True
    except Exception as e:
        print(f"FAIL sector_flow_today primary: {e}", flush=True)
        try:
            ind = ak.stock_fund_flow_industry()
            rows = []
            for _, r in ind.iterrows():
                name = str(r.get("行业") or r.get("名称") or "").strip()
                if not name:
                    continue
                net_yi = float(r.get("净额") or 0)
                rows.append(
                    {
                        "code": "",
                        "name": name,
                        "changePercent": float(r.get("行业-涨跌幅") or r.get("涨跌幅") or 0),
                        "mainNetInflow": net_yi * 1e8,
                        "asof": _today(),
                        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    }
                )
            rows.sort(key=lambda x: -x["mainNetInflow"])
            _write(DATA / "sector_flow_today.json", rows, "akshare.stock_fund_flow_industry")
            return True
        except Exception as e2:
            print(f"FAIL sector_flow_today fallback: {e2}", flush=True)
            return False


def refresh_today_concept(ak) -> bool:
    try:
        con = ak.stock_sector_fund_flow_rank(indicator="今日", sector_type="概念资金流")
        rows = _to_rows(con, ["名称", "概念", "行业"], "concept")
        if not rows:
            raise RuntimeError("empty rows from sector_type=概念资金流")
        _write(DATA / "concept_flow_today.json", rows, "akshare.stock_sector_fund_flow_rank")
        return True
    except Exception as e:
        print(f"FAIL concept_flow_today: {e}", flush=True)
        try:
            con = ak.stock_fund_flow_concept()
            rows = []
            for _, r in con.iterrows():
                # akshare 概念接口列名常为「行业」而非「概念」
                name = str(r.get("概念") or r.get("行业") or r.get("名称") or "").strip()
                if not name:
                    continue
                net_yi = float(r.get("净额") or 0)
                rows.append(
                    {
                        "code": "",
                        "name": name,
                        "changePercent": float(
                            r.get("行业-涨跌幅") or r.get("涨跌幅") or 0
                        ),
                        "mainNetInflow": net_yi * 1e8,
                        "asof": _today(),
                        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    }
                )
            rows.sort(key=lambda x: -x["mainNetInflow"])
            if not rows:
                raise RuntimeError("empty concept fallback")
            _write(DATA / "concept_flow_today.json", rows, "akshare.stock_fund_flow_concept")
            return True
        except Exception as e2:
            print(f"FAIL concept fallback: {e2}", flush=True)
            return False


def _to_rows_old_rank(df, kind: str) -> list[dict]:
    """老接口 stock_fund_flow_industry/concept(symbol='X日排行') → gate 兼容 rows。

    列: 序号/行业(或概念)/公司家数/行业指数/阶段涨跌幅/流入资金/流出资金/净额
    净额单位为「亿」。mainNetInflow 统一转「元」（gate load 时再 /1e8）。
    """
    rows: list[dict] = []
    for _, r in df.iterrows():
        name = str(r.get("行业") or r.get("概念") or r.get("名称") or "").strip()
        if not name:
            continue
        net_yi = float(r.get("净额") or 0)  # 亿
        chg_raw = r.get("阶段涨跌幅") or r.get("涨跌幅") or 0
        try:
            chg = float(str(chg_raw).replace("%", "").strip())  # 老接口 '6.69%' 去百分号
        except (TypeError, ValueError):
            chg = 0.0
        rows.append(
            {
                "code": "",
                "name": name,
                "changePercent": chg,
                "mainNetInflow": net_yi * 1e8,  # 亿 → 元
                "mainNetInflowPercent": 0.0,
                "kind": kind,
                "asof": _today(),
                "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
    rows.sort(key=lambda x: -float(x["mainNetInflow"]))
    return rows


def refresh_nday_old(ak, indicator: str, out_name: str, kind: str) -> bool:
    """3/5 日榜 → 老接口 stock_fund_flow_{industry|concept}(symbol='X日排行')。

    2026-09-04 修复：akshare 1.18.64 升版后 stock_sector_fund_flow_rank 移除
    "3日" indicator（只剩 今日/5日/10日），传 "3日" 必 KeyError；且 5日/10日走
    push2.eastmoney clist 易被风控断连。老接口走另一链路，凌晨实测 4 组合全通。
    单次调用失败/空数据 → 抛异常，由调用方 _retry 决定重试（不再静默）。
    """
    fn_name = f"stock_fund_flow_{kind}"
    df = getattr(ak, fn_name)(symbol=indicator + "排行")
    rows = _to_rows_old_rank(df, "nday")
    if not rows:
        raise RuntimeError(f"{out_name} empty (no rows)")
    _write(DATA / out_name, rows, f"akshare.{fn_name}", indicator=indicator)
    print(f"OK {out_name} n={len(rows)} asof={_today()}", flush=True)
    return True


def _retry(fn, times: int = 3, sleep_sec: float = 2.0):
    last = None
    for i in range(times):
        try:
            return fn()
        except Exception as e:
            last = e
            print(f"retry {i+1}/{times}: {e}", flush=True)
            time.sleep(sleep_sec * (i + 1))
    raise last  # type: ignore


def assert_today(path: Path, min_n: int = 1) -> bool:
    if not path.exists():
        print(f"MISSING {path}", flush=True)
        return False
    raw = json.loads(path.read_text(encoding="utf-8"))
    asof = str(raw.get("asof") or "")
    n = int(raw.get("total") or len(raw.get("data") or []))
    ok = asof == _today() and n >= min_n
    print(f"CHECK {path.name} asof={asof} n={n} expect={_today()} ok={ok}", flush=True)
    return ok


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--require-today", action="store_true", help="asof 必须等于今天")
    ap.add_argument("--skip-nday", action="store_true")
    args = ap.parse_args()

    t0 = time.time()
    import akshare as ak

    ok = True
    # 带重试
    def _ind():
        return refresh_today_industry(ak)

    def _con():
        return refresh_today_concept(ak)

    try:
        ok = _retry(_ind) and ok
    except Exception as e:
        print(f"FATAL industry: {e}", flush=True)
        ok = False
    try:
        ok = _retry(_con) and ok
    except Exception as e:
        print(f"FATAL concept: {e}", flush=True)
        ok = False

    if not args.skip_nday:
        # 3/5 日榜 → 老接口（见 refresh_nday_old 注释）；重试 3 次，失败计入 ok（非静默）
        for ind, out, kind in [
            ("3日", "sector_flow_3day.json", "industry"),
            ("3日", "concept_flow_3day.json", "concept"),
            ("5日", "sector_flow_5day.json", "industry"),
        ]:
            try:
                nday_ok = _retry(lambda: refresh_nday_old(ak, ind, out, kind), times=3, sleep_sec=3.0)
            except Exception as e:
                print(f"FAIL {out} after 3 retries: {e}", flush=True)
                nday_ok = False
            if not nday_ok:
                ok = False

    if args.require_today:
        ok = assert_today(DATA / "sector_flow_today.json", min_n=20) and ok
        ok = assert_today(DATA / "concept_flow_today.json", min_n=20) and ok

    # 重建板块轮动快照，供 pipeline / 看板 / 旁路池直接读盘
    try:
        import sys as _sys

        _sys.path.insert(0, str(ROOT))
        from sector_rotation_gate import build_snapshot

        snap = build_snapshot()
        allow_n = len((snap.get("classes") or {}).get("allow") or [])
        print(f"OK rebuilt sector_rotation_snapshot allow={allow_n} ts={snap.get('ts')}", flush=True)
    except Exception as e:
        print(f"WARN rebuild snapshot failed: {e}", flush=True)

    print(f"DONE ok={ok} elapsed={int(time.time()-t0)}s", flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

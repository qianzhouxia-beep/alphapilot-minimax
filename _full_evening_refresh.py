#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""盘后全量补齐：把落后数据刷到最新交易日。"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path("/home/ubuntu/alphapilot")
LOG = ROOT / "output" / "logs" / "full_refresh_evening.log"


def log(msg: str) -> None:
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def run(name: str, cmd: str, timeout_min: int = 40) -> bool:
    log(f"START {name}: {cmd}")
    t0 = time.time()
    try:
        r = subprocess.run(
            cmd,
            shell=True,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=timeout_min * 60,
        )
        elapsed = int(time.time() - t0)
        tail = ((r.stdout or "") + "\n" + (r.stderr or "")).strip()[-800:]
        if r.returncode == 0:
            log(f"OK {name} ({elapsed}s)")
            if tail:
                for ln in tail.splitlines()[-8:]:
                    log(f"  | {ln}")
            return True
        log(f"FAIL {name} ({elapsed}s) rc={r.returncode}")
        for ln in tail.splitlines()[-12:]:
            log(f"  | {ln}")
        return False
    except subprocess.TimeoutExpired:
        log(f"TIMEOUT {name} ({timeout_min}min)")
        return False
    except Exception as e:
        log(f"EXC {name}: {e}")
        return False


def refresh_board_flows_ak() -> bool:
    """用 akshare 刷新行业/概念今日+3日资金缓存。"""
    try:
        import akshare as ak
    except Exception as e:
        log(f"akshare import fail: {e}")
        return False

    def _to_rows(df, name_col_candidates, kind: str):
        rows = []
        for _, r in df.iterrows():
            name = ""
            for c in name_col_candidates:
                if c in df.columns and str(r.get(c) or "").strip():
                    name = str(r.get(c)).strip()
                    break
            if not name:
                continue
            # 东财净额单位多为亿
            net_yi = float(r.get("今日主力净流入-净额") or r.get("主力净流入-净额") or r.get("净额") or 0)
            # 有的接口已是元量级（绝对值很大）
            if abs(net_yi) > 1e6:
                main_net = net_yi
            else:
                main_net = net_yi * 1e8
            chg = float(
                r.get("今日涨跌幅")
                or r.get("行业-涨跌幅")
                or r.get("涨跌幅")
                or r.get("changePercent")
                or 0
            )
            code = str(r.get("行业代码") or r.get("概念代码") or r.get("代码") or "").strip()
            item = {
                "code": code,
                "name": name,
                "changePercent": chg,
                "mainNetInflow": main_net,
                "mainNetInflowPercent": float(r.get("今日主力净流入-净占比") or r.get("主力净流入-净占比") or 0),
                "superLargeNetInflow": float(r.get("今日超大单净流入-净额") or 0) * (1 if abs(float(r.get("今日超大单净流入-净额") or 0)) > 1e6 else 1e8),
                "largeNetInflow": float(r.get("今日大单净流入-净额") or 0) * (1 if abs(float(r.get("今日大单净流入-净额") or 0)) > 1e6 else 1e8),
                "mediumNetInflow": float(r.get("今日中单净流入-净额") or 0) * (1 if abs(float(r.get("今日中单净流入-净额") or 0)) > 1e6 else 1e8),
                "smallNetInflow": float(r.get("今日小单净流入-净额") or 0) * (1 if abs(float(r.get("今日小单净流入-净额") or 0)) > 1e6 else 1e8),
                "topStockCode": str(r.get("今日主力净流入最大股") or r.get("主力净流入最大股") or ""),
                "kind": kind,
                "asof": datetime.now().strftime("%Y-%m-%d"),
                "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            rows.append(item)
        rows.sort(key=lambda x: -float(x["mainNetInflow"]))
        return rows

    ok = True
    try:
        ind = ak.stock_sector_fund_flow_rank(indicator="今日", sector_type="行业资金流")
        rows = _to_rows(ind, ["名称", "行业"], "industry")
        payload = {"total": len(rows), "data": rows, "asof": datetime.now().strftime("%Y-%m-%d"), "source": "akshare.stock_sector_fund_flow_rank"}
        (ROOT / "data" / "sector_flow_today.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        log(f"OK sector_flow_today n={len(rows)}")
    except Exception as e:
        log(f"FAIL sector_flow_today: {e}")
        ok = False
        # fallback
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
                        "asof": datetime.now().strftime("%Y-%m-%d"),
                    }
                )
            rows.sort(key=lambda x: -x["mainNetInflow"])
            payload = {"total": len(rows), "data": rows, "asof": datetime.now().strftime("%Y-%m-%d"), "source": "akshare.stock_fund_flow_industry"}
            (ROOT / "data" / "sector_flow_today.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            log(f"OK sector_flow_today fallback n={len(rows)}")
            ok = True
        except Exception as e2:
            log(f"FAIL sector fallback: {e2}")

    try:
        con = ak.stock_sector_fund_flow_rank(indicator="今日", sector_type="概念资金流")
        rows = _to_rows(con, ["名称", "概念"], "concept")
        payload = {"total": len(rows), "data": rows, "asof": datetime.now().strftime("%Y-%m-%d"), "source": "akshare.stock_sector_fund_flow_rank"}
        (ROOT / "data" / "concept_flow_today.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        log(f"OK concept_flow_today n={len(rows)}")
    except Exception as e:
        log(f"FAIL concept_flow_today: {e}")
        try:
            con = ak.stock_fund_flow_concept()
            rows = []
            for _, r in con.iterrows():
                name = str(r.get("概念") or r.get("名称") or "").strip()
                if not name:
                    continue
                net_yi = float(r.get("净额") or 0)
                rows.append(
                    {
                        "code": "",
                        "name": name,
                        "changePercent": float(r.get("涨跌幅") or 0),
                        "mainNetInflow": net_yi * 1e8,
                        "asof": datetime.now().strftime("%Y-%m-%d"),
                    }
                )
            rows.sort(key=lambda x: -x["mainNetInflow"])
            payload = {"total": len(rows), "data": rows, "asof": datetime.now().strftime("%Y-%m-%d"), "source": "akshare.stock_fund_flow_concept"}
            (ROOT / "data" / "concept_flow_today.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            log(f"OK concept_flow_today fallback n={len(rows)}")
        except Exception as e2:
            log(f"FAIL concept fallback: {e2}")
            ok = False

    # 3日
    for indicator, out_name, sector_type in [
        ("3日", "sector_flow_3day.json", "行业资金流"),
        ("3日", "concept_flow_3day.json", "概念资金流"),
    ]:
        try:
            df = ak.stock_sector_fund_flow_rank(indicator=indicator, sector_type=sector_type)
            rows = _to_rows(df, ["名称", "行业", "概念"], "3day")
            payload = {"total": len(rows), "data": rows, "asof": datetime.now().strftime("%Y-%m-%d"), "source": "akshare.stock_sector_fund_flow_rank", "indicator": indicator}
            (ROOT / "data" / out_name).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            log(f"OK {out_name} n={len(rows)}")
        except Exception as e:
            log(f"WARN {out_name}: {e}")
    return ok


def main() -> int:
    log("=" * 60)
    log("FULL EVENING REFRESH start")
    results = {}

    # 1) 个股资金流（已补过，再拉一次确保最新）
    results["fund_flow"] = run("fund_flow", f"{sys.executable} -u build_fund_flow_history.py", 10)

    # 2) 日K 增量（源站晚间通常更全）
    results["kline"] = run("kline", f"{sys.executable} -u cache_kline.py update", 45)

    # 3) 筹码
    results["chip"] = run("chip", f"{sys.executable} -u scripts/pull_chip_from_kline.py --workers 1", 20)

    # 4) 板块/概念资金
    log("START board_flows_ak")
    results["board_flows"] = refresh_board_flows_ak()

    # 5) 两融/龙虎榜/基本面（轻量）
    results["margin"] = run("margin", f"{sys.executable} pull_margin_event_data.py", 10)
    results["lhb"] = run("lhb", f"{sys.executable} scripts/pull_lhb_history.py", 10)
    results["fundamentals"] = run("fundamentals", f"{sys.executable} scripts/build_fundamental_data.py", 15)

    # 6) 通达信板块看板快照（依赖最新个股资金流）
    results["sector_dashboard"] = run("sector_dashboard", f"{sys.executable} -u sector_dashboard.py", 10)

    # 7) 板块下午研报（用最新资金）
    results["sector_afternoon"] = run(
        "sector_afternoon",
        f"{sys.executable} -u sector_research_report.py --session afternoon",
        20,
    )

    # 8) 日推荐（资金流更新后重跑）
    results["recommend"] = run("recommend", f"{sys.executable} -u run_pipeline_standalone.py", 40)

    # 9) readiness
    results["readiness"] = run(
        "readiness",
        f"{sys.executable} -u scripts/data_readiness_gate.py --repair",
        15,
    )

    log("=" * 60)
    for k, v in results.items():
        log(f"RESULT {k}={'OK' if v else 'FAIL'}")
    fails = [k for k, v in results.items() if not v]
    log(f"DONE fails={fails or 'none'}")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())

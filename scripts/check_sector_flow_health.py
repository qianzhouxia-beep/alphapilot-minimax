# -*- coding: utf-8 -*-
"""sector_flow 修复健康检查（2026-09-04 Cursor 加）。

用途：05:00 管线后 / 21:05 盘后刷新后 / 手动随时，确认 3day/5day 数据新鲜度与 gate 消费链路正常。
幂等只读，不写数据文件。退出码：0=全健康；1=有异常。

验证点：
  1) data/sector_flow_3day.json / concept_flow_3day.json / sector_flow_5day.json 的 asof 是否==预期日期
  2) 每个文件 source 是否为新链路 (akshare.stock_fund_flow_industry/concept) + n>0
  3) cron 是否存在盘后完整刷新 (sector_flow_evening.log)
  4) sector_rotation_gate 实时 build_snapshot 可正常构建（供 pipeline 消费）
"""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path("/home/ubuntu/alphapilot")
DATA = ROOT / "data"
EXPECT_ASOF = sys.argv[1] if len(sys.argv) > 1 else ""

FILES = [
    ("sector_flow_3day.json", "akshare.stock_fund_flow_industry"),
    ("concept_flow_3day.json", "akshare.stock_fund_flow_concept"),
    ("sector_flow_5day.json", "akshare.stock_fund_flow_industry"),
]


def main() -> int:
    global EXPECT_ASOF
    ok = True
    if not EXPECT_ASOF:
        # 默认：最近一个工作日。周五~周日期望本周五；周一二三期望当天/周五？
        # 简单策略：期望 = 服务器本地"今天"（交易日盘后任务都刷 today）；非交易日手动跑不判死。
        import datetime

        EXPECT_ASOF = datetime.date.today().isoformat()

    print(f"== sector_flow health check asof_expect={EXPECT_ASOF} ==")
    for fn, src in FILES:
        p = DATA / fn
        if not p.exists():
            print(f"[FAIL] {fn}: MISSING")
            ok = False
            continue
        raw = json.loads(p.read_text(encoding="utf-8"))
        asof = str(raw.get("asof") or "")
        source = str(raw.get("source") or "")
        n = len(raw.get("data") or [])
        is_new = source.startswith("akshare.stock_fund_flow")
        date_ok = asof == EXPECT_ASOF
        state = "OK" if (date_ok and is_new and n > 0) else "BAD"
        if state == "BAD":
            ok = False
        print(f"[{state}] {fn}: asof={asof} source={source} n={n} (expect {EXPECT_ASOF}, new-api={is_new})")

    # cron 存在性
    cur = subprocess.run(["crontab", "-l"], capture_output=True, text=True).stdout
    has_eve = "sector_flow_evening.log" in cur
    has_skip = "--skip-nday" in cur
    print(f"[{'OK' if has_eve else 'FAIL'}] evening full-refresh cron present: {has_eve}")
    print(f"[{'OK' if has_skip else 'WARN'}] midday --skip-nday cron present: {has_skip}")
    if not has_eve:
        ok = False

    # gate 实时构建
    try:
        sys.path.insert(0, str(ROOT))
        from sector_rotation_gate import build_snapshot

        snap = build_snapshot()
        allow_n = len((snap.get("classes") or {}).get("allow") or [])
        deny_n = len((snap.get("classes") or {}).get("deny") or [])
        print(f"[OK] build_snapshot live: allow={allow_n} deny={deny_n} ts={snap.get('ts')}")
    except Exception as e:
        print(f"[FAIL] build_snapshot: {e}")
        ok = False

    print(f"RESULT: {'ALL-HEALTHY' if ok else 'HAS-ISSUES'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""一次性部署「开盘最终方案」crontab（幂等）。

链路：
  05:00  pipeline → overnight_recommend + ICIR（先验）
  09:25:55  pre_market_gate → call_auction_snapshot
  09:35  live_momentum_scanner + morning_live Top2
  09:36  paper_trading + executor（REQUIRE_ORDER_APPROVAL=0 全自动）
  09:40  archive score + daily picks（TOP2/门控TOP10/无门槛TOP10）
  16:15  feedback loop（Kelly 重训 + 轻确认权重）
"""
from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = "/home/ubuntu/alphapilot"
ENV = f"set -a; [ -f {ROOT}/config/opening_scheme.env ] && . {ROOT}/config/opening_scheme.env; set +a"

BLOCKS = [
    (
        "# 09:25:55 - 集合竞价快照+硬门控（供 09:35 终选）",
        f"25 9 * * 1-5 cd {ROOT} && sleep 55 && "
        f"python3 -u pre_market_gate.py >> output/logs/pre_market_gate.log 2>&1",
        ("pre_market_gate.py",),
    ),
    (
        "# 09:35 - 全市场终选 → Top2",
        f"35 9 * * 1-5 cd {ROOT} && {ENV} && "
        f"python3 -u live_momentum_scanner.py >> output/logs/live_momentum_scanner.log 2>&1 && "
        f"MORNING_RANK_MODE=model python3 -u morning_live_fund_select.py >> output/logs/l2_refresh.log 2>&1",
        ("live_momentum_scanner.py", "morning_live_fund_select.py"),
    ),
    (
        "# 09:36 - TOP2 全自动模拟交易（无人工确认）",
        f"36 9 * * 1-5 cd {ROOT} && {ENV} && "
        f"python3 -u paper_trading_signals.py >> output/logs/paper_trading.log 2>&1 && "
        f"python3 -u trade_executor.py >> output/logs/executor.log 2>&1",
        ("paper_trading_signals.py",),
    ),
    (
        "# 09:40 - 归档分数快照 + 每日选股 TOP2/TOP10",
        f"40 9 * * 1-5 cd {ROOT} && "
        f"python3 -u rd_workshop/research_factory/archive_score_snapshot.py >> /tmp/rf_score_archive.log 2>&1 && "
        f"python3 -u scripts/archive_daily_picks.py >> output/logs/daily_picks_archive.log 2>&1",
        ("archive_score_snapshot.py", "archive_daily_picks.py"),
    ),
    (
        "# 16:15 - 反馈闭环（Kelly 重训 + 轻确认权重）",
        f"15 16 * * 1-5 cd {ROOT} && {ENV} && "
        f"python3 -u scripts/run_feedback_loop.py >> output/logs/feedback_loop.log 2>&1",
        ("run_feedback_loop.py",),
    ),
]


def main() -> None:
    raw = subprocess.check_output(["crontab", "-l"], text=True, stderr=subprocess.DEVNULL)
    lines = raw.splitlines()
    skip_needles = set()
    for _, _, patterns in BLOCKS:
        skip_needles.update(patterns)
    # also remove old 09:36 paper line without env / old archive-only 09:40
    out: list[str] = []
    for line in lines:
        if any(p in line for p in skip_needles):
            continue
        if "36 9" in line and "trade_executor.py" in line:
            continue
        if line.strip().startswith("#") and any(
            x in line
            for x in (
                "09:25:55",
                "09:35 - 全市场",
                "09:36",
                "09:40 - 归档",
                "16:15 - 反馈",
                "集合竞价快照",
            )
        ):
            continue
        out.append(line)

    # insert new blocks before first remaining 09:xx trading line or append
    insert_at = None
    for i, line in enumerate(out):
        if "45 14" in line and "eod_s2" in line:
            insert_at = i
            break
    block_lines: list[str] = []
    for comment, cmd, _ in BLOCKS:
        block_lines.append(comment)
        block_lines.append(cmd)
    if insert_at is None:
        out.extend([""] + block_lines)
    else:
        out[insert_at:insert_at] = [""] + block_lines + [""]

    text = "\n".join(out) + "\n"
    Path("/tmp/crontab_opening_scheme").write_text(text, encoding="utf-8")
    subprocess.check_call(["crontab", "/tmp/crontab_opening_scheme"])
    print("opening scheme cron installed (auto TOP2 + archive + feedback)")
    subprocess.check_call(
        [
            "bash",
            "-lc",
            "crontab -l | grep -E '25 9|35 9|36 9|40 9|15 16|0 5 |pre_market|live_momentum|paper_trading|archive_daily|feedback'",
        ]
    )


if __name__ == "__main__":
    main()

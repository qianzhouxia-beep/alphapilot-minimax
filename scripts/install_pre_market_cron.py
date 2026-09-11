#!/usr/bin/env python3
"""Idempotent: 09:25:55 跑集合竞价门控（sleep 55），再交给 09:35 三轨扫描。"""
import subprocess
from pathlib import Path

COMMENT = "# 09:25:55 - 集合竞价快照+隔夜池门控（供 09:35 资金/动量/竞价三轨）"
NEW_LINE = (
    "25 9 * * 1-5 cd /home/ubuntu/alphapilot && "
    "sleep 55 && python3 -u pre_market_gate.py >> output/logs/pre_market_gate.log 2>&1"
)


def main() -> None:
    raw = subprocess.check_output(["crontab", "-l"], text=True, stderr=subprocess.DEVNULL)
    lines = raw.splitlines()
    out: list[str] = []
    replaced = False
    skip_next_comment_dup = False
    for line in lines:
        if "pre_market_gate.py" in line:
            if not replaced:
                # drop adjacent old comment about 09:25 pre_market
                if out and ("09:25" in out[-1] and "集合竞价" in out[-1] and out[-1].strip().startswith("#")):
                    out.pop()
                out.append(COMMENT)
                out.append(NEW_LINE)
                replaced = True
            continue
        if line.strip() == COMMENT:
            continue
        if line.strip().startswith("#") and "09:25" in line and "集合竞价" in line:
            # will be re-added with NEW_LINE
            continue
        out.append(line)

    if not replaced:
        final: list[str] = []
        inserted = False
        for line in out:
            if (not inserted) and (
                ("35 9" in line and "live_momentum_scanner" in line)
                or ("35 9" in line and "morning_live_fund_select" in line)
            ):
                final.append(COMMENT)
                final.append(NEW_LINE)
                inserted = True
            final.append(line)
        out = final
        replaced = inserted
        if not inserted:
            out.append("")
            out.append(COMMENT)
            out.append(NEW_LINE)
            replaced = True

    text = "\n".join(out) + "\n"
    Path("/tmp/crontab_pre_market").write_text(text, encoding="utf-8")
    subprocess.check_call(["crontab", "/tmp/crontab_pre_market"])
    print("cron updated, replaced=", replaced)
    subprocess.check_call(
        ["bash", "-lc", "crontab -l | grep -E '09:25|25 9|pre_market|live_momentum'"]
    )


if __name__ == "__main__":
    main()

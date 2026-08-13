#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""每日决策单 + 市场环境日记（知识库 L2 动态沉淀）。

读取当日产物：
  output/morning_live_picks.json   — 09:35 终选 Top2
  output/score_top10.json          — 09:38 三路融合 Top10
  output/daily_picks_archive/YYYY-MM-DD/ — 09:40 归档
  output/market_env_snapshot.json  — 05:00 管线环境
  output/fund_strength.json        — 04:30 资金强度
写出知识库：
  knowledge/daily/YYYY-MM-DD.md    — 今日决策单
  knowledge/market_env/YYYY-MM-DD.md — 市场环境日记
建议 cron：工作日 09:45
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

SCRIPT_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("ALPHAPILOT_ROOT") or str(SCRIPT_ROOT))
for _candidate in (ROOT, SCRIPT_ROOT):
    if (_candidate / "alphapilot_pipeline_v3.py").exists() or (_candidate / "knowledge").exists():
        ROOT = _candidate
        break
else:
    ROOT = SCRIPT_ROOT
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

OUT = ROOT / "output"
KB = ROOT / "knowledge"
KB_DAILY = KB / "daily"
KB_ENV = KB / "market_env"


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def load(path: Path) -> dict | list:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        log(f"  read fail {path.name}: {e}")
        return {}


def bare(s: str) -> str:
    x = str(s or "")
    for p in ("sh", "sz", "bj", "SH", "SZ", "BJ"):
        x = x.replace(p, "")
    return x[-6:] if len(x) >= 6 else x


def today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def find_asof_day() -> str:
    """从当日产物推断交易日（避免周末/假期归档到非交易日）。"""
    for p in (OUT / "morning_live_picks.json", OUT / "score_top10.json"):
        d = load(p)
        if isinstance(d, dict):
            for k in ("asof", "trade_date", "date", "run_at", "generated_at"):
                v = str(d.get(k) or "")
                if len(v) >= 10 and v[0].isdigit():
                    return v[:10]
    return today_str()


def format_item(it: dict, rank: int) -> list[str]:
    sym = bare(it.get("symbol"))
    name = it.get("name") or sym
    score = float(it.get("score") or it.get("lgb_score") or 0)
    fusion = it.get("_fusion_weight")
    chg = it.get("change_pct")
    main_net = it.get("main_net") or it.get("live_main_net")
    sector = it.get("industry_l1") or it.get("sector") or ""
    parts = [f"{rank}. **{name}** ({sym})"]
    bits = []
    if fusion is not None:
        bits.append(f"综合分 {float(fusion):.3f}")
    if score:
        bits.append(f"模型分 {score:.3f}")
    if chg is not None:
        bits.append(f"实时 {float(chg):+.2f}%")
    if main_net:
        bits.append(f"主力净 {float(main_net) / 1e4:.0f}万")
    if sector:
        bits.append(f"板块 {sector}")
    if bits:
        parts.append(" — " + " · ".join(bits))
    return parts


def gen_daily_decision(day: str) -> bool:
    KB_DAILY.mkdir(parents=True, exist_ok=True)
    picks = load(OUT / "morning_live_picks.json")
    score10 = load(OUT / "score_top10.json")
    archive = load(OUT / "daily_picks_archive" / day / "_meta.json")
    rec = load(OUT / "daily_recommend.json")

    top2 = picks.get("picks") or [] if isinstance(picks, dict) else []
    top10 = (score10.get("items") or []) if isinstance(score10, dict) else []
    top2_slim = [t for t in top2[:2] if isinstance(t, dict)]
    top10_slim = [t for t in top10[:10] if isinstance(t, dict)]

    exposure = rec.get("position_exposure") if isinstance(rec, dict) else None
    protocol = rec.get("protocol") if isinstance(rec, dict) else None
    exposure_mode = rec.get("exposure_mode") if isinstance(rec, dict) else None
    morning_mode = rec.get("morning_live_mode") if isinstance(rec, dict) else None
    env_flags = (rec.get("market_env_flags") or rec.get("env") or {}) if isinstance(rec, dict) else {}

    md = [
        f"# 每日决策单 — {day}",
        "",
        f"> 自动生成：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ｜ 脚本：`scripts/kb_daily_snapshot.py`",
        "",
        "## 今日交易候选（Top2，09:35 终选）",
        "",
    ]
    if top2_slim:
        for i, t in enumerate(top2_slim, 1):
            md += format_item(t, i)
            buy = t.get("buy_price")
            if buy:
                md.append(f"   参考买入价：{buy}")
    else:
        md.append("_暂无终选数据（非交易日或管线未跑）_")

    md += ["", "## 综合评分 Top10（09:35 定格，三路融合）", ""]
    if top10_slim:
        for i, t in enumerate(top10_slim, 1):
            md += format_item(t, i)
    else:
        md.append("_暂无_")

    md += ["", "## 市场环境与仓位", ""]
    md.append(f"- position_exposure：`{exposure}`")
    if protocol:
        md.append(f"- protocol：`{protocol}` ｜ exposure_mode：`{exposure_mode}` ｜ morning_live_mode：`{morning_mode}`")
    if isinstance(env_flags, dict) and env_flags:
        md.append(f"- market_env_flags：`{json.dumps(env_flags, ensure_ascii=False)}`")
    if isinstance(archive, dict) and "counts" in archive:
        md.append(f"- 归档：Top2×{archive['counts'].get('top2')} / 门控Top10×{archive['counts'].get('top10_gated')} / 无门槛Top10×{archive['counts'].get('top10_ungated')}")

    md += ["", "## 决策要点（给 Agent 下次检索）", ""]
    md.append("- 今日买入候选以上方 Top2 为准；实际成交价看前端（VWAP 回踩低位）。")
    md.append("- 卖出执行：T+2 收盘（可交易协议）；止损峰值回撤。")
    md.append("- 详细规则见 `knowledge/strategies/buy_sell_rules.md`。")

    target = KB_DAILY / f"{day}.md"
    target.write_text("\n".join(md) + "\n", encoding="utf-8")
    log(f"written {target}")
    return True


def gen_market_env(day: str) -> bool:
    KB_ENV.mkdir(parents=True, exist_ok=True)
    rec = load(OUT / "daily_recommend.json")
    snap = load(OUT / "market_env_snapshot.json")
    rec_env = (rec.get("market_env_flags") or rec.get("env") or {}) if isinstance(rec, dict) else {}
    snap_env = snap if isinstance(snap, dict) else {}

    md = [
        f"# 市场环境日记 — {day}",
        "",
        f"> 自动生成：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## 管线环境判定",
        "",
    ]
    if isinstance(rec_env, dict) and rec_env:
        md.append(f"```json\n{json.dumps(rec_env, ensure_ascii=False, indent=2)}\n```")
    else:
        md.append("_今日无环境判定记录_")

    md += ["", "## 环境快照（market_env_snapshot.json）", ""]
    if snap_env:
        keys = ("exposure", "position_exposure", "verdict", "flags", "indices", "up3_width", "sustained_industries")
        for k in keys:
            if k in snap_env:
                md.append(f"- `{k}`: `{json.dumps(snap_env[k], ensure_ascii=False) if not isinstance(snap_env[k], str) else snap_env[k]}`")
    else:
        md.append("_暂无快照_")

    md += ["", "## 环境对策略的含义", ""]
    md.append("- exposure=0 → 当日不交易（nuclear）；0.25 → Top1；0.5/1.0 → Top2。")
    md.append("- severe/crash_day → 板块与仓位收紧，见 `knowledge/strategies/buy_sell_rules.md`。")

    target = KB_ENV / f"{day}.md"
    target.write_text("\n".join(md) + "\n", encoding="utf-8")
    log(f"written {target}")
    return True


def main() -> int:
    day = find_asof_day()
    log(f"kb_daily_snapshot day={day}")
    ok1 = gen_daily_decision(day)
    ok2 = gen_market_env(day)
    return 0 if (ok1 and ok2) else 2


if __name__ == "__main__":
    raise SystemExit(main())

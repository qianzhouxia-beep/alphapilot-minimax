#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""每日选股落盘：TOP2 / 门控 TOP10 / 无门槛 TOP10。

写入：
  output/daily_picks_archive/YYYY-MM-DD/
    top2.json              — 当日实际交易候选（morning_live_picks）
    top10_gated.json       — 资金+竞价等门控后的推荐池 Top10
    top10_ungated.json     — 无资金门验证的评分 Top10（score_top10）
    _meta.json

建议 cron：09:40（终选与 score_top10 之后）
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(os.environ.get("ALPHAPILOT_ROOT") or "/home/ubuntu/alphapilot")
if not ROOT.exists():
    ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

OUT_ROOT = ROOT / "output" / "daily_picks_archive"
REC = ROOT / "output" / "daily_recommend.json"
PICKS = ROOT / "output" / "morning_live_picks.json"
SCORE10 = ROOT / "output" / "score_top10.json"


def _day() -> str:
    for p in (PICKS, REC, SCORE10):
        if not p.exists():
            continue
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        for k in ("asof", "trade_date", "date", "run_at", "generated_at", "scanned_at"):
            v = str(d.get(k) or "")
            if len(v) >= 10 and v[0].isdigit():
                return v[:10]
    return datetime.now().strftime("%Y-%m-%d")


def _load(path: Path) -> dict | list:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _ensure_score_top10() -> dict:
    data = _load(SCORE10)
    items = []
    if isinstance(data, dict):
        items = data.get("items") or data.get("recommendations") or data.get("stocks") or []
    if isinstance(items, list) and len(items) >= 5:
        return data if isinstance(data, dict) else {"items": items}
    # 重建无门槛榜
    try:
        subprocess.check_call(
            [sys.executable, str(ROOT / "scripts" / "build_score_top10.py")],
            cwd=str(ROOT),
            timeout=180,
        )
        data = _load(SCORE10)
    except Exception as e:
        print(f"build_score_top10 failed: {e}", flush=True)
    return data if isinstance(data, dict) else {}


def _slim(it: dict, rank: int) -> dict:
    keys = (
        "symbol",
        "name",
        "score",
        "ml_score",
        "momentum_score",
        "icir_alpha",
        "main_net",
        "live_main_net",
        "active_buy_ratio",
        "change_pct",
        "auction_gap_pct",
        "overnight_overlap",
        "sector",
        "industry_l1",
        "buy_price",
        "price",
        "money_phase_label",
        "research_tier",
    )
    out = {k: it.get(k) for k in keys if k in it}
    out["rank"] = rank
    out["symbol"] = str(out.get("symbol") or it.get("symbol") or "")[-6:]
    return out


def main() -> int:
    day = _day()
    dest = OUT_ROOT / day
    dest.mkdir(parents=True, exist_ok=True)

    picks = _load(PICKS)
    top2_raw = list(picks.get("picks") or []) if isinstance(picks, dict) else []
    top2 = [_slim(x, i + 1) for i, x in enumerate(top2_raw[:2]) if isinstance(x, dict)]

    rec = _load(REC)
    gated = list(rec.get("recommendations") or []) if isinstance(rec, dict) else []
    # 再过一次资金门（与网页今日推荐同口径）
    try:
        from money_flow_gate import apply_money_flow_gate

        gated = apply_money_flow_gate(gated, top_n=None)
        gated = [x for x in gated if x.get("money_flow_pass") is not False]
    except Exception as e:
        print(f"money_flow_gate skip: {e}", flush=True)
    top10_gated = [_slim(x, i + 1) for i, x in enumerate(gated[:10]) if isinstance(x, dict)]

    score = _ensure_score_top10()
    ungated_items = (
        score.get("items")
        or score.get("recommendations")
        or score.get("stocks")
        or []
    )
    top10_ungated = [
        _slim(x, i + 1) for i, x in enumerate(ungated_items[:10]) if isinstance(x, dict)
    ]

    payload_top2 = {
        "asof": day,
        "role": "trade_top2",
        "n": len(top2),
        "mode": picks.get("mode") if isinstance(picks, dict) else None,
        "picks": top2,
        "note": "当日自动交易候选（与 morning_live_picks 一致）",
    }
    payload_g10 = {
        "asof": day,
        "role": "top10_gated",
        "n": len(top10_gated),
        "picks": top10_gated,
        "note": "终选池经资金门后 Top10（含竞价/动量门控后的 daily_recommend）",
    }
    payload_u10 = {
        "asof": day,
        "role": "top10_ungated",
        "n": len(top10_ungated),
        "picks": top10_ungated,
        "note": "无资金门验证的评分 Top10（score_top10）",
    }
    meta = {
        "archived_at": datetime.now().isoformat(timespec="seconds"),
        "day": day,
        "files": ["top2.json", "top10_gated.json", "top10_ungated.json"],
        "counts": {
            "top2": len(top2),
            "top10_gated": len(top10_gated),
            "top10_ungated": len(top10_ungated),
        },
        "protocol": "live_momentum_fund_auction_auto",
    }

    (dest / "top2.json").write_text(
        json.dumps(payload_top2, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (dest / "top10_gated.json").write_text(
        json.dumps(payload_g10, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (dest / "top10_ungated.json").write_text(
        json.dumps(payload_u10, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (dest / "_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 最新指针，方便 API/人工查看
    latest = ROOT / "output" / "daily_picks_latest.json"
    latest.write_text(
        json.dumps(
            {
                "asof": day,
                "top2": top2,
                "top10_gated": top10_gated,
                "top10_ungated": top10_ungated,
                "archive_dir": str(dest),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(json.dumps(meta, ensure_ascii=False, indent=2), flush=True)
    return 0 if top2 or top10_gated or top10_ungated else 2


if __name__ == "__main__":
    raise SystemExit(main())

# -*- coding: utf-8 -*-
"""Issue#6 D4/D5: 每日风险档位计算 → output/qmt_scores/alert_state.json（nginx 供 QMT 端拉取）

拍板口径（Issue#6 comment 5558361228 / 5558449951）:
  D4  ALERT(裸突破族 roll8<-1pp) → risk REDUCED（单笔仓位 ×0.5）；
      从 REDUCED 起连续 2 个 WATCH 日自动恢复 NORMAL；OK/数据不足即恢复 NORMAL。
  D5  市场宽度(20日新高占比) >= 过去60交易日 p80 → 降档 REDUCED（仅降档不否决）；
      宽度回落且无 D4 触发 → 与 D4 共用"连续 2 个清空日恢复"确认，偏保守。

数据源（都在服务器 output/，16:28 由 wb_breakout_monitor 每日更新）:
  output/wb_breakout_monitor.json   -> summary.verdict(ALERT/WATCH/OK/INSUFFICIENT_HISTORY)
                                       + breadth_by_day({date: 20日新高占比})
                                       + asof（K线最新交易日）

用法:
  python3 -u scripts/compute_risk_state.py            # 读最新 monitor，落 alert_state.json
  python3 -u scripts/compute_risk_state.py --asof YYYY-MM-DD   # 指定交易日回看（探针/测试）
  python3 -u scripts/compute_risk_state.py --dry      # 只打印不落盘
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, date
from pathlib import Path

_ROOT0 = Path(os.environ.get("ALPHAPILOT_ROOT") or Path(__file__).resolve().parents[1])
if not (_ROOT0 / "output" / "wb_breakout_monitor.json").exists() and len(Path(__file__).resolve().parents) > 2:
    if (_ROOT0.parent / "output" / "wb_breakout_monitor.json").exists():
        _ROOT0 = _ROOT0.parent
ROOT = _ROOT0
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

MONITOR = ROOT / "output" / "wb_breakout_monitor.json"
STATE = ROOT / "output" / "qmt_scores" / "alert_state.json"
WINDOW = 60          # D5 宽度 p80 回看交易日数
RECOVER_DAYS = 2     # D4: 连续 N 个 WATCH 日恢复
RECOVER_CLEAR_DAYS = 2  # D5: 连续 N 个无触发日恢复（含 D4 OK 场景的 D5 恢复）

_ALERT = "ALERT"
_WATCH = "WATCH"
_OK = "OK"
_INSUF = "INSUFFICIENT_HISTORY"


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def _prev_state(asof: str) -> dict:
    """读上一交易日 alert_state.json（只认连续自然日紧邻，节假日不连续则视为重置）。"""
    if not STATE.exists():
        return {}
    try:
        d = json.loads(STATE.read_text(encoding="utf-8"))
        if not isinstance(d, dict) or not d.get("date"):
            return {}
        pday = d["date"]
        try:
            gap = (date.fromisoformat(asof) - date.fromisoformat(pday)).days
        except Exception:
            return {}
        # 允许 1-4 天gap(周末/节假日)，>4 视为长期未跑/重置
        return d if 1 <= gap <= 4 else {}
    except Exception:
        return {}


def compute(asof: str) -> dict:
    if not MONITOR.exists():
        log(f"MONITOR 缺失 {MONITOR}")
        raise SystemExit(2)
    mon = json.loads(MONITOR.read_text(encoding="utf-8"))
    summary = mon.get("summary") or {}
    mon_asof = str(summary.get("asof") or "")
    if not mon_asof or mon_asof > asof:
        # monitor 更新于 asof 当日 16:28；回看历史日时用 <= asof 的最新已覆盖数据即可
        pass
    verdict = str(summary.get("verdict") or _INSUF)
    bbd = mon.get("breadth_by_day") or {}
    # 每日序列排序
    days = sorted(bbd.keys())
    if days:
        # 只取 <= asof 的日（回看历史时避免用未来宽度）
        days = [x for x in days if x <= asof]
    # 今日宽度 = 序列最后一日（= asof 当日或最近已更新日）
    today_breadth = None
    if days:
        today_breadth = bbd[days[-1]]

    # ---- D5: 宽度 >= 过去60交易日 p80 ----
    d5_breach = False
    p80 = None
    hist_vals = [v for k, v in bbd.items() if k <= asof and v is not None]
    if len(hist_vals) >= 30 and today_breadth is not None:
        win = hist_vals[-WINDOW:]
        sv = sorted(win)
        idx = min(len(sv) - 1, int(0.80 * len(sv)))  # 保守下分位: ceil 改 floor 偏严
        p80 = sv[idx]
        d5_breach = bool(today_breadth >= p80)

    # ---- 状态机 ----
    prev = _prev_state(asof)
    d4_state = "NORMAL"
    d5_state = "NORMAL"
    watch_days = int(prev.get("watch_days") or 0)
    clear_days = int(prev.get("clear_days") or 0)

    d4_trigger = verdict in (_ALERT,)
    d4_watch = verdict in (_WATCH,)
    trigger = d4_trigger or d5_breach
    clear = (not trigger) and (verdict in (_OK, _INSUF) or not d4_watch)

    if trigger:
        watch_days = 0
        clear_days = 0
        d4_state = "REDUCED" if d4_trigger else prev.get("d4_state", "NORMAL")
        d5_state = "REDUCED" if d5_breach else prev.get("d5_state", "NORMAL")
    else:
        # D4 恢复: 从 REDUCED 起连续 2 WATCH 日 → NORMAL
        if prev.get("d4_state") == "REDUCED" and d4_watch:
            watch_days += 1
            if watch_days >= RECOVER_DAYS:
                d4_state = "NORMAL"
                watch_days = 0
            else:
                d4_state = "REDUCED"
        elif verdict == _INSUF:
            d4_state = "NORMAL"  # 历史不足 → 不降（无依据不乱降）
        else:
            d4_state = "NORMAL"
            watch_days = 0
        # D5 恢复: 无 D5 触发连续 RECOVER_CLEAR_DAYS 日 → NORMAL
        if prev.get("d5_state") == "REDUCED":
            if not d5_breach:
                clear_days += 1
                if clear_days >= RECOVER_CLEAR_DAYS:
                    d5_state = "NORMAL"
                    clear_days = 0
                else:
                    d5_state = "REDUCED"
            else:
                d5_state = "REDUCED"
                clear_days = 0
        else:
            d5_state = "NORMAL"
            clear_days = 0

    # 合并: 任一 REDUCED → risk_level REDUCED
    risk = "REDUCED" if (d4_state == "REDUCED" or d5_state == "REDUCED") else "NORMAL"
    reasons = []
    if d4_state == "REDUCED":
        reasons.append(f"D4_ALERT(verdict={verdict})")
    if d5_state == "REDUCED":
        reasons.append(f"D5_BREADTH(today={today_breadth:.4f}>=p80={p80:.4f})" if today_breadth is not None and p80 is not None else "D5_BREADTH")

    payload = {
        "date": asof,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "risk_level": risk,          # NORMAL / REDUCED → 客户端单笔仓位 = POSITION_PCT × (1.0 or 0.5)
        "position_scale": 0.5 if risk == "REDUCED" else 1.0,
        "d4": {"verdict": verdict, "state": d4_state,
               "watch_days": watch_days,
               "roll8_mean_exc5": summary.get("roll8_mean_exc5")},
        "d5": {"state": d5_state, "breadth_today": today_breadth,
               "p80_60d": p80, "breach": d5_breach,
               "clear_days": clear_days, "n_days_hist": len(hist_vals)},
        "reasons": reasons,
        "source_monitor_asof": mon_asof,
    }
    return payload


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--asof", type=str, default=None)
    ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()
    asof = args.asof or datetime.now().strftime("%Y-%m-%d")
    payload = compute(asof)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if not args.dry:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        tmp = STATE.with_name(STATE.name + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(STATE)
        log(f"saved {STATE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

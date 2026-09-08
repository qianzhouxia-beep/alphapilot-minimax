#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""交易反馈闭环：把平仓结果喂回次日仓位/轻确认权重。

已有路径：
  trade_executor 平仓 → kelly_learner.record_trade → 次日 paper_trading_signals 重训 Kelly

本脚本补强：
  1) 强制重训 KellyLearner 并写出反馈摘要
  2) 按隔夜重合 / 竞价命中等标签统计滚动胜率
  3) 在安全区间内微调 OVERNIGHT_OVERLAP_BOOST 写入 config/opening_scheme.env
     （仅轻确认，不替换生产 XGBoost 权重；完整换模仍走 RD Workshop）

建议 cron：16:15（日审计之后）
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(os.environ.get("ALPHAPILOT_ROOT") or "/home/ubuntu/alphapilot")
if not ROOT.exists():
    ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

TRADES = ROOT / "data" / "kelly_learner_trades.json"
FUSION_CLOSED_PATHS = [
    ROOT / "data" / "fusion_closed_trades.jsonl",
    Path(r"C:/alphapilot/fusion_closed_trades.jsonl"),
]
OUT = ROOT / "output" / "feedback" / "latest.json"
ENV_PATH = ROOT / "config" / "opening_scheme.env"
BOOST_MIN = 1.00
BOOST_MAX = 1.08
BOOST_DEFAULT = 1.03


def _load_trades() -> list[dict]:
    if not TRADES.exists():
        rows: list[dict] = []
    else:
        try:
            d = json.loads(TRADES.read_text(encoding="utf-8"))
        except Exception:
            d = []
        if isinstance(d, list):
            rows = [x for x in d if isinstance(x, dict)]
        elif isinstance(d, dict):
            rows = [x for x in (d.get("trades") or []) if isinstance(x, dict)]
        else:
            rows = []
    rows.extend(_load_fusion_closed())
    return rows


def _load_fusion_closed() -> list[dict]:
    """QMT live / QMT sim / TDX sim closed trades with fusion_scores + pnl."""
    out: list[dict] = []
    seen: set[tuple] = set()
    for p in FUSION_CLOSED_PATHS:
        if not p.exists():
            continue
        try:
            lines = p.read_text(encoding="utf-8").splitlines()
        except Exception:
            continue
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                t = json.loads(line)
            except Exception:
                continue
            if not isinstance(t, dict):
                continue
            key = (
                t.get("source"),
                t.get("symbol"),
                t.get("sell_time"),
                t.get("action"),
                t.get("volume"),
            )
            if key in seen:
                continue
            seen.add(key)
            out.append(t)
    return out


def _read_boost() -> float:
    if not ENV_PATH.exists():
        return BOOST_DEFAULT
    text = ENV_PATH.read_text(encoding="utf-8")
    m = re.search(r"^OVERNIGHT_OVERLAP_BOOST\s*=\s*([0-9.]+)", text, re.M)
    if not m:
        return BOOST_DEFAULT
    try:
        return float(m.group(1))
    except ValueError:
        return BOOST_DEFAULT


def _write_boost(v: float) -> None:
    v = max(BOOST_MIN, min(BOOST_MAX, round(v, 3)))
    lines = []
    if ENV_PATH.exists():
        lines = ENV_PATH.read_text(encoding="utf-8").splitlines()
    out = []
    found = False
    for line in lines:
        if line.startswith("OVERNIGHT_OVERLAP_BOOST="):
            out.append(f"OVERNIGHT_OVERLAP_BOOST={v}")
            found = True
        else:
            out.append(line)
    if not found:
        out.append(f"OVERNIGHT_OVERLAP_BOOST={v}")
    ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
    ENV_PATH.write_text("\n".join(out) + "\n", encoding="utf-8")


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description="交易反馈闭环（Kelly 重训 + 融合权重 + 轻确认）")
    ap.add_argument(
        "--no-retrain",
        action="store_true",
        help="跳过滚动窗口模型重训（重训已移至 21:30 独立 cron: scripts/run_daily_retrain.py）",
    )
    args = ap.parse_args()

    trades = _load_trades()
    n_fusion = sum(1 for t in trades if t.get("source") in ("qmt_live", "qmt_sim", "tdx_sim"))
    print(f"  trades={len(trades)} fusion_closed={n_fusion}")
    n = len(trades)
    wins = [t for t in trades if float(t.get("pnl") or 0) > 0]
    losses = [t for t in trades if float(t.get("pnl") or 0) < 0]
    total_pnl = sum(float(t.get("pnl") or 0) for t in trades)

    # Kelly 重训
    kelly_meta = {"ok": False}
    try:
        from kelly_learner import KellyLearner

        kl = KellyLearner()
        kl.train()
        hist = kl.get_hist_stats()
        kelly_meta = {
            "ok": True,
            "n_trades": hist.get("n_trades"),
            "ml_ready": hist.get("ml_ready"),
            "bins": hist.get("bins") if isinstance(hist.get("bins"), dict) else None,
        }
    except Exception as e:
        kelly_meta = {"ok": False, "error": str(e)}

    # 轻确认权重：样本不足则保持；足够则按近 40 笔胜率微调
    boost_now = _read_boost()
    boost_new = boost_now
    boost_note = "unchanged_insufficient_samples"
    recent = trades[-40:]
    if len(recent) >= 20:
        wr = sum(1 for t in recent if float(t.get("pnl") or 0) > 0) / len(recent)
        # 胜率高略增确认权重，低则降回 1.0
        if wr >= 0.55:
            boost_new = min(BOOST_MAX, boost_now + 0.01)
            boost_note = f"wr={wr:.2f} nudge_up"
        elif wr <= 0.45:
            boost_new = max(BOOST_MIN, boost_now - 0.01)
            boost_note = f"wr={wr:.2f} nudge_down"
        else:
            boost_note = f"wr={wr:.2f} hold"
        if abs(boost_new - boost_now) > 1e-9:
            _write_boost(boost_new)

    # ── 滚动窗口模型重训（自动检测日期增量）──
    retrain_meta = {"ok": False, "log": None, "duration_s": None}
    if not args.no_retrain:
        try:
            import subprocess, time
            t0 = time.time()
            log_path = ROOT / "output" / "logs" / "train_v25_retrain.log"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            rc = subprocess.run(
                [sys.executable or "python3", "-u", str(ROOT / "train_v25.py")],
                capture_output=True, text=True, timeout=1200, cwd=str(ROOT),
            )
            elapsed = round(time.time() - t0, 1)
            retrain_meta = {
                "ok": rc.returncode == 0,
                "rc": rc.returncode,
                "duration_s": elapsed,
                "stdout_tail": rc.stdout.strip().splitlines()[-5:] if rc.stdout else [],
                "stderr_tail": rc.stderr.strip().splitlines()[-5:] if rc.stderr else [],
            }
            log_path.write_text(
                f"=== train_v25 retrain @ {datetime.now().isoformat()} ===\n"
                f"rc={rc.returncode} elapsed={elapsed}s\n"
                f"--- stdout ---\n{rc.stdout}\n--- stderr ---\n{rc.stderr}\n",
                encoding="utf-8",
            )
            if rc.returncode == 0:
                print(f"  ✅ 滚动窗口重训完成 ({elapsed}s)")
            else:
                print(f"  ⚠️ 滚动窗口重训异常 rc={rc.returncode} ({elapsed}s)")
        except subprocess.TimeoutExpired as te:
            retrain_meta = {"ok": False, "error": "timeout_1200s"}
            try:
                tail = (te.stderr or "")[-2000:] if hasattr(te, "stderr") else ""
                log_path.write_text(
                    f"=== train_v25 retrain @ {datetime.now().isoformat()} ===\n"
                    f"TIMEOUT 1200s\n"
                    f"--- stderr tail ---\n{tail}\n",
                    encoding="utf-8",
                )
            except Exception:
                pass
            print("  ⚠️ 滚动窗口重训超时（>1200s 跳过）")
        except Exception as e:
            retrain_meta = {"ok": False, "error": str(e)}
            print(f"  ⚠️ 滚动窗口重训异常: {e}")
    else:
        retrain_meta = {"ok": None, "note": "skipped_by_no_retrain"}

    # ── 三路融合评分权重更新（IC 衰减 EMA）──
    fusion_meta = {"ok": False}
    try:
        from fusion_scorer import update_ic_weights
        fusion_meta = update_ic_weights(trades)
        if fusion_meta.get("ok"):
            w = fusion_meta["weights"]
            ic = fusion_meta.get("rolling_ic", {})
            print(
                "  融合权重更新: VM2.5={} 资金流={} 板块={} | IC={} | {}笔".format(
                    round(w.get("vm25", 0), 3),
                    round(w.get("fund_flow", 0), 3),
                    round(w.get("sector_heat", 0), 3),
                    {k: round(v, 3) for k, v in ic.items()},
                    fusion_meta.get("n_used", 0),
                )
            )
        else:
            print(f"  融合权重未更新: {fusion_meta.get('note', 'unknown')}")
    except Exception as e:
        fusion_meta = {"ok": False, "error": str(e)}
        print(f"  ⚠️ 融合权重更新异常: {e}")

    summary = {
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "kelly_learner": kelly_meta,
        "model_retrain": retrain_meta,
        "fusion_scorer": fusion_meta,
        "closed_loop": {
            "record_on_exit": "trade_executor → kelly_learner.record_trade",
            "retrain_on_open": "paper_trading_signals → KellyLearner.train + apply_kelly (KELLY_ENABLE=1)",
            "model_retrain": "scripts/run_daily_retrain.py (21:30 独立 cron，资金流/RD因子就绪后)",
            "soft_param_feedback": "OVERNIGHT_OVERLAP_BOOST in opening_scheme.env",
            "note": "不自动覆盖生产 VM2.5（tech id v25）；换模仍走 RD Workshop + 人工审核",
        },
        "trade_stats": {
            "n_trades": n,
            "n_wins": len(wins),
            "n_losses": len(losses),
            "win_rate": round(len(wins) / n, 4) if n else None,
            "total_pnl": round(total_pnl, 2),
        },
        "overnight_overlap_boost": {
            "before": boost_now,
            "after": boost_new,
            "note": boost_note,
            "bounds": [BOOST_MIN, BOOST_MAX],
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    # 给扫描器可读的旁路文件
    (ROOT / "output" / "feedback_weights.json").write_text(
        json.dumps(
            {
                "overnight_overlap_boost": boost_new,
                "kelly_ml_ready": bool(kelly_meta.get("ml_ready")),
                "updated_at": summary["updated_at"],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

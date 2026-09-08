#!/usr/bin/env python3
"""
P2 反馈闭环 — 自动追踪因子 IC + 调整选股参数权重

每天 16:15 运行，统计当日选股的实际表现（开→收收益），计算各因子的
日频 IC（皮尔逊相关系数），近 IC_WINDOW 天内平均 IC 显著同向且符号
占优 >= 0.6 时，按 STEP 调整该因子权重。

只调整 live_momentum_scanner 真正消费的参数：
  W_ICIR:       ICIR ML 分权重 (默认 0.50, 09:35 资金轨 final 用)
  W_MOMENTUM:   实时动量权重 (默认 0.50, 09:35 资金轨 final 用)

不调整（历史遗留、scanner 无消费点，保留固定值写 env 供将来接线）：
  W_HEAT / W_PIPELINE / SURGE_ARM_B_MULT

因子字段映射（自适应 daily_recommend.json 两种路径的实际字段）：
  09:35 主路径(池>=100): ICIR<-ml_score | MOMENTUM<-_live_momentum_z | PIPELINE<-_pipeline_z
  09:35 资金轨(池<100):  ICIR<-_icir_z  | MOMENTUM<-_momentum_z  | HEAT<-热度命中字段
  HEAT 热度命中 = hot_sector_prefer / auction_sector_hit / wind_prefer_hit 任一非空

输出: output/feedback_tuned_weights.json
同步: config/feedback_params.env (live_momentum_scanner 启动时读取)
"""
import json
import os
import sys
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict

ROOT = Path("/home/ubuntu/alphapilot")
if not ROOT.exists():
    ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

OUTPUT = ROOT / "output" / "feedback_tuned_weights.json"
HISTORY = ROOT / "output" / "feedback" / "history.jsonl"
REC_PATH = ROOT / "output" / "daily_recommend.json"
KLINE_PATH = ROOT / "kline_all.parquet"

# 默认参数（W_HEAT/W_PIPELINE/SURGE_ARM_B_MULT 保留固定值写 env，不做自动调权）
DEFAULTS = {
    "W_ICIR": 0.50,
    "W_MOMENTUM": 0.50,
    "W_HEAT": 0.08,
    "W_PIPELINE": 0.08,
    "SURGE_ARM_B_MULT": 0.85,
}

# 调权参数
MIN_WEIGHT = 0.10
MAX_WEIGHT = 0.80
STEP = 0.05
IC_WINDOW = 10        # 近10天IC窗口
MIN_SAMPLES = 5       # 窗口内至少 5 天有效 IC 才评估
IC_TRIGGER = 0.03     # |平均IC| 触发阈值
SIGN_RATIO = 0.6      # 窗口内同向天数占比阈值

# 参与调权的因子 -> 参数（必须与 live_momentum_scanner 消费点一一对应）
TUNE_PARAMS = {
    "ICIR": "W_ICIR",
    "MOMENTUM": "W_MOMENTUM",
}


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def load_today_picks() -> list[dict]:
    if not REC_PATH.exists():
        return []
    try:
        data = json.loads(REC_PATH.read_text(encoding="utf-8"))
        return data.get("recommendations", data.get("items", []))
    except Exception:
        return []


def load_kline_for_date(date_str: str) -> dict[str, float]:
    """加载指定日期的个股收益率"""
    try:
        import pandas as pd
        df = pd.read_parquet(KLINE_PATH)
        df = df[df["date"] == date_str].copy()
        df["ret"] = (df["close"] / df["open"] - 1) * 100
        return dict(zip(df["symbol"].astype(str).str[-6:], df["ret"]))
    except Exception:
        return {}


def _to_f(v) -> float | None:
    """安全转 float；空/None/非数值返回 None。"""
    try:
        if v is None:
            return None
        f = float(v)
        return f if np.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def _pick_factor(p: dict, names: list[str]) -> float | None:
    """从多个候选字段取第一个有值的数值因子。

    daily_recommend.json 的字段随 09:35 路径变化：
      池>=100 主路径 -> ml_score/_live_momentum_z/_pipeline_z
      池<100  资金轨 -> _icir_z/_momentum_z
    """
    for name in names:
        if name in p and p.get(name) is not None:
            f = _to_f(p.get(name))
            if f is not None:
                return f
    return None


def _heat_hit(p: dict) -> float:
    """热度命中：任一路径的热度字段非空即 1.0。"""
    for name in ("hot_sector_prefer", "auction_sector_hit", "wind_prefer_hit"):
        v = p.get(name)
        if v not in (None, "", False, 0, 0.0):
            return 1.0
    return 0.0


def compute_ic(picks: list[dict], returns: dict[str, float]) -> dict[str, float | None]:
    """计算各因子的日频 IC (皮尔逊相关系数)。

    因子缺失/样本不足/恒值 → 返回 None，调用方不写入历史，避免假 0 拉低均值。
    收益口径 = 当日 open→close（与 T+N 置信度一致）。
    只评估 daily_recommend.json 实际排序输入因子（主路径 / 资金轨）。
    """
    rows = []
    for p in picks:
        sym = str(p.get("symbol", ""))[-6:]
        ret = returns.get(sym)
        if ret is None:
            continue
        rows.append({
            "ret": ret,
            "ICIR": _pick_factor(p, ["ml_score", "lgb_score", "_icir_z"]),
            "MOMENTUM": _pick_factor(p, ["_live_momentum_z", "_momentum_z"]),
            "HEAT": _heat_hit(p),
            "PIPELINE": _pick_factor(p, ["_pipeline_z"]),
        })

    if len(rows) < 5:
        return {}

    ic = {}
    for name in ("ICIR", "MOMENTUM", "HEAT", "PIPELINE"):
        pairs = [(r[name], r["ret"]) for r in rows if r[name] is not None]
        if len(pairs) < 5 or len(set(v for v, _ in pairs)) < 2:
            ic[name] = None
            continue
        xs = [v for v, _ in pairs]
        ys = [ret for _, ret in pairs]
        corr = np.corrcoef(xs, ys)[0, 1]
        ic[name] = round(float(corr), 4) if not np.isnan(corr) else None
    return ic


def load_ic_history() -> dict[str, list[float]]:
    if not HISTORY.exists():
        return defaultdict(list)
    hist = defaultdict(list)
    try:
        for line in HISTORY.read_text(encoding="utf-8").strip().split("\n"):
            if not line.strip():
                continue
            entry = json.loads(line)
            for k, v in entry.get("ic", {}).items():
                # 只收有效数值 IC；None(样本不足/恒值) 不写历史
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    hist[k].append(v)
    except Exception:
        pass
    return hist


def auto_tune(ic_history: dict[str, list[float]]) -> dict:
    """根据近期 IC 自动调整权重（只调 live_momentum_scanner 消费的参数）。"""
    current = json.loads(OUTPUT.read_text(encoding="utf-8")) if OUTPUT.exists() else {}
    weights = {**DEFAULTS, **current}

    changes = []
    for factor, param in TUNE_PARAMS.items():
        recent = [v for v in ic_history.get(factor, []) if v is not None][-IC_WINDOW:]
        if len(recent) < MIN_SAMPLES:
            continue

        mean_ic = float(np.mean(recent))
        n_pos = len([x for x in recent if x > 0])
        n_neg = len([x for x in recent if x < 0])
        pos_ratio = n_pos / len(recent)
        neg_ratio = n_neg / len(recent)
        current_w = float(weights.get(param, DEFAULTS[param]))

        if mean_ic <= -IC_TRIGGER and neg_ratio >= SIGN_RATIO:
            new_w = round(max(MIN_WEIGHT, current_w - STEP), 2)
            if new_w != current_w:
                changes.append(f"{param}: {current_w}→{new_w} (meanIC={mean_ic:.3f}, neg={neg_ratio:.0%}/{len(recent)}d)")
                weights[param] = new_w
        elif mean_ic >= IC_TRIGGER and pos_ratio >= SIGN_RATIO:
            new_w = round(min(MAX_WEIGHT, current_w + STEP), 2)
            if new_w != current_w:
                changes.append(f"{param}: {current_w}→{new_w} (meanIC={mean_ic:.3f}, pos={pos_ratio:.0%}/{len(recent)}d)")
                weights[param] = new_w

    weights["tuned_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    weights["ic_window"] = IC_WINDOW
    weights["changes"] = changes

    if changes:
        log(f"  权重调整: {', '.join(changes)}")
    else:
        log("  权重不变 — 窗口内无显著方向性信号")

    return weights


def main():
    log("P2 反馈闭环 — 因子IC追踪+自动调权")

    # 1. 加载今日选股和涨跌
    today = datetime.now().strftime("%Y-%m-%d")
    picks = load_today_picks()
    if not picks:
        log("无选股数据，跳过")
        return

    returns = load_kline_for_date(today)
    if not returns:
        # 用前一天
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        returns = load_kline_for_date(yesterday)

    # 2. 计算日频 IC
    ic = compute_ic(picks, returns)
    if not ic:
        log("IC计算失败（样本不足），跳过")
        return

    log(f"  今日IC: " + "  ".join(
        f"{k}={v:+.3f}" if isinstance(v, (int, float)) and not isinstance(v, bool)
        else f"{k}=-" for k, v in ic.items()
    ) + f"  (recs={len(picks)}, 收益样本={len(returns)})")

    # 3. 追加历史
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    with open(HISTORY, "a", encoding="utf-8") as f:
        f.write(json.dumps({"date": today, "ic": ic, "n": len(picks)}, ensure_ascii=False) + "\n")

    # 4. 自动调权
    ic_history = load_ic_history()
    for k, v in ic.items():
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            ic_history[k].append(v)

    weights = auto_tune(ic_history)

    # 5. 输出
    OUTPUT.write_text(json.dumps(weights, ensure_ascii=False, indent=2), encoding="utf-8")

    # 6. 同步到环境变量文件（供 live_momentum_scanner 消费）
    env_path = ROOT / "config" / "feedback_params.env"
    env_lines = []
    for k in ["W_ICIR", "W_MOMENTUM", "W_HEAT", "W_PIPELINE"]:
        env_lines.append(f"{k}={weights[k]}")
    env_lines.append(f"SURGE_ARM_B_MULT={weights['SURGE_ARM_B_MULT']}")
    env_path.write_text("\n".join(env_lines) + "\n", encoding="utf-8")

    log(f"  参数已写入 {env_path}")
    log(f"  完整输出: {OUTPUT}")


if __name__ == "__main__":
    main()

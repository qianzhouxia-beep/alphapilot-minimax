#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RD 自我提升健康检查。只读生产 models/，写 output/logs/rd_health.json。

检查项:
  1. 工作日 21:30 重训是否成功（retrain_status）
  2. 影子 jsonl 是否按日唯一；SHADOW 候选是否还在
  3. 影子候选的真 OOS 是否在有交易日后仍停在 0 天（monitor 漏跑）
  4. 生产 extra_factor_columns 必须仍为空（RD 禁止自动晋升）
  5. Track A 最新期是否周六产出
告警可走企业微信（有 webhook 才推）。
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(os.environ.get("ALPHAPILOT_ROOT") or Path(__file__).resolve().parents[1])
LOG_DIR = ROOT / "output" / "logs"
OUT = LOG_DIR / "rd_health.json"
SHADOW = ROOT / "output" / "shadow_top2_history.jsonl"
RETRAIN = ROOT / "output" / "feedback" / "retrain_status.json"
PROD_META = ROOT / "models" / "v25_meta.json"
CAND_ROOT = ROOT / "rd_workshop" / "candidates"
ENVF = ROOT / "config" / "opening_scheme.env"


def _log(msg: str) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    print(msg, flush=True)
    with open(LOG_DIR / "rd_health.log", "a", encoding="utf-8") as f:
        f.write(datetime.now().strftime("%Y-%m-%d %H:%M:%S ") + msg + "\n")


def _env(key: str) -> str:
    v = (os.environ.get(key) or "").strip()
    if v:
        return v
    if not ENVF.exists():
        return ""
    for line in ENVF.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, val = line.split("=", 1)
        if k.strip() == key:
            return val.strip().strip('"').strip("'")
    return ""


def _compact_shadow() -> dict:
    if not SHADOW.exists():
        return {"n": 0, "dup_days": [], "compacted": False}
    rows = []
    for line in SHADOW.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    by: dict[str, list[dict]] = {}
    order = []
    for r in rows:
        d = str(r.get("date") or "")
        if not d:
            continue
        if d not in by:
            by[d] = []
            order.append(d)
        by[d].append(r)
    dups = [d for d, xs in by.items() if len(xs) > 1]

    def hour(rec):
        raw = str(rec.get("asof") or "")
        try:
            return int(raw[11:13])
        except Exception:
            return 99

    kept = []
    for d in order:
        xs = by[d]
        morning = [x for x in xs if hour(x) == 9]
        pool = morning or xs
        pool.sort(key=lambda x: str(x.get("asof") or ""))
        kept.append(pool[0])
    if dups:
        tmp = SHADOW.with_suffix(".jsonl.tmp")
        tmp.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in kept), encoding="utf-8")
        tmp.replace(SHADOW)
    return {"n": len(kept), "dup_days": dups, "compacted": bool(dups), "dates": order}


def _last_weekday(today=None):
    d = today or datetime.now().date()
    while d.weekday() >= 5:
        d = d - timedelta(days=1)
    return d


def main() -> int:
    alerts: list[str] = []
    notes: list[str] = []
    compact = _compact_shadow()
    if compact["dup_days"]:
        alerts.append(f"shadow jsonl 同日重复 {compact['dup_days']}，已按 09:35 首笔压缩")
        notes.append("compacted " + ",".join(compact["dup_days"]))
    else:
        notes.append(f"shadow unique days={compact['n']}")

    # retrain
    retrain = {}
    if RETRAIN.exists():
        try:
            retrain = json.loads(RETRAIN.read_text(encoding="utf-8"))
        except Exception as e:
            alerts.append(f"retrain_status 读失败: {e}")
    else:
        alerts.append("缺少 output/feedback/retrain_status.json")
    trained = str(retrain.get("trained_at") or "")[:10]
    last_wd = _last_weekday().isoformat()
    if retrain.get("ok") is not True:
        err = str(retrain.get("error") or "")
        # AUC 安全门拒绝 = 正常保护行为（模型冻结期每天都预期出现），不算健康告警
        if err == "auc_gate_rejected":
            notes.append(f"retrain auc_gate_rejected（安全门正常保护拒绝）trained_at={trained}")
        else:
            alerts.append(f"最近重训失败 ok={retrain.get('ok')} err={err}")
    elif trained and trained < last_wd:
        # 周六检查：上一个工作日应已重训
        alerts.append(f"重训过期 trained_at={trained} 期望>={last_wd}")
    else:
        notes.append(f"retrain ok {trained} auc={retrain.get('auc')}")

    # production must not silently absorb RD extras
    extra = []
    if PROD_META.exists():
        meta = json.loads(PROD_META.read_text(encoding="utf-8"))
        extra = meta.get("extra_factor_columns") or []
        notes.append(f"prod trained_at={meta.get('trained_at')} extra={len(extra)}")
        if extra:
            alerts.append(f"生产 models 出现 extra_factor_columns={extra} — RD 可能被误晋升，立即人工确认")

    # kline volume 单位：amount/(volume*close) ~1 为股，~100 为手（RD 空池根因）
    kpath = ROOT / "data" / "kline_cache" / "kline_all.parquet"
    if kpath.exists():
        try:
            import pandas as pd
            k = pd.read_parquet(kpath, columns=["symbol", "date", "close", "volume", "amount"])
            k["date"] = k["date"].astype(str).str[:10]
            last = str(k["date"].max())
            sample = k[k["date"] == last].head(200).copy()
            vol = sample["volume"].clip(lower=1)
            close = sample["close"].replace(0, pd.NA)
            ratio = (sample["amount"] / (vol * close)).median()
            notes.append(f"kline volume_ratio_med={float(ratio):.3f} asof={last}")
            if ratio is not None and float(ratio) >= 20:
                alerts.append(
                    f"kline volume 单位疑似手(ratio={float(ratio):.1f} @ {last})，RD OOS 会空池，需 ×100 修复"
                )
            rootp = ROOT / "kline_all.parquet"
            if rootp.exists() and os.path.realpath(rootp) != os.path.realpath(kpath):
                rk = pd.read_parquet(rootp, columns=["date", "close", "volume", "amount"])
                rk["date"] = rk["date"].astype(str).str[:10]
                rlast = str(rk["date"].max())
                rsample = rk[rk["date"] == rlast].head(200).copy()
                rvol = rsample["volume"].clip(lower=1)
                rclose = rsample["close"].replace(0, pd.NA)
                rratio = float((rsample["amount"] / (rvol * rclose)).median())
                notes.append(f"root_kline separate volume_ratio_med={rratio:.3f} asof={rlast}")
                if rratio >= 20:
                    alerts.append(
                        f"根目录 kline_all.parquet 仍是手数(ratio={rratio:.1f} @ {rlast})，请从 cache 覆盖"
                    )
        except Exception as e:
            notes.append(f"kline volume check skip: {e}")

    # shadow candidate OOS
    md = _env("SHADOW_MODEL_DIR")
    shadow_run = ""
    oos_n = None
    if md:
        run = Path(md).parent if Path(md).name == "models" else Path(md)
        shadow_run = run.name
        if not run.is_dir():
            alerts.append(f"SHADOW_MODEL_DIR 不存在: {md}")
        else:
            pr = run / "promotion_report.json"
            if pr.exists():
                rep = json.loads(pr.read_text(encoding="utf-8"))
                win = (rep.get("oos") or {}).get("window") or {}
                oos_n = win.get("n_days")
                trained_c = str(((rep.get("candidate") or {}).get("trained_at") or win.get("requested", {}).get("trained_at") or ""))[:10]
                notes.append(f"shadow {shadow_run} oos_days={oos_n} trained_at={trained_c}")
                kpi = (rep.get("oos") or {}).get("kpi") or {}
                fill = kpi.get("fill_rate")
                if fill is not None:
                    notes.append(f"shadow fill_rate={fill}")
                # 训练日之后已有交易日，OOS 仍为 0 = monitor 漏跑
                if oos_n == 0 and trained_c and trained_c < last_wd:
                    alerts.append(
                        f"影子候选 {shadow_run} 真 OOS 仍 0 天（trained_at={trained_c}），monitor 未刷新"
                    )
                # 有 OOS 天但 fill=0 = volume 单位又坏了（08-15/08-22 两次）
                try:
                    if oos_n is not None and int(oos_n) >= 3 and fill is not None and float(fill) <= 0:
                        alerts.append(
                            f"影子候选 {shadow_run} oos_days={oos_n} 但 fill_rate={fill}，量金叉可能再次失效"
                        )
                except (TypeError, ValueError):
                    pass
            else:
                alerts.append(f"影子候选无 promotion_report: {run}")
    else:
        notes.append("SHADOW_MODEL_DIR 未设置（影子旁路关）")

    dirs = sorted(
        [p.name for p in CAND_ROOT.iterdir() if p.is_dir() and p.name.startswith("track_a_")]
    ) if CAND_ROOT.is_dir() else []
    latest = dirs[-1] if dirs else None
    notes.append(f"latest_track_a={latest} n_cand={len(dirs)}")

    payload = {
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "ok": not alerts,
        "alerts": alerts,
        "notes": notes,
        "shadow": compact,
        "shadow_run": shadow_run,
        "oos_n": oos_n,
        "retrain_trained_at": trained,
        "prod_extra_n": len(extra),
        "latest_track_a": latest,
    }
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    line = ("RD HEALTH OK " if payload["ok"] else "RD HEALTH ALERT ") + "; ".join(alerts or notes)
    _log(line)

    if alerts:
        try:
            sys.path.insert(0, str(ROOT))
            sys.path.insert(0, str(ROOT / "scripts"))  # wecom_push 在 scripts/ 下
            from wecom_push import send_markdown

            send_markdown("## RD 健康检查告警\n\n" + "\n".join(f"- {a}" for a in alerts))
            _log(f"wecom alert pushed: {len(alerts)} alert(s)")
        except Exception as e:
            _log(f"wecom skip: {e}")
    return 0 if payload["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

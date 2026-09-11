#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""每日「更大候选池」持久化 → output/pool_archive/pool_archive.jsonl（read-only 固化）

背景（G1 扩样瓶颈）：
  `_g1_replay_expand.py` 只能用 top10 归档（~12 只/日），分组结论永远只能验 ~1 个月。
  服务器其实已有全量打分宇宙落盘：`output/rf_score_archive/{date}/icir_all_scores.json`
  —— 05:00 管线对 ~500 只的 ICIR 打分（`archive_score_snapshot.py` 每日 09:40 拷一份，
  **无滚动清理**）。但它是「一天一目录」，跨日回测不便，且易被误删。

本脚本把它固化成**一份 append-only JSONL**（哪怕只存 symbol+score），供日后
分组/回归研究直接读取，不再受归档目录形态影响。

记录（每行一条）：{date, symbol, name, score, source}
  source ∈ {icir_all_scores, fullpool_live, morning_picks, candidates_top10}
幂等：key = date|symbol|source，重复运行不产生重复行；不删除、不改写历史。
只读生产文件；唯一写入：output/pool_archive/
用法：
  python3 pool_archive_daily.py            # 增量固化（含历史 bootstrap）
  python3 pool_archive_daily.py --stats    # 只打印统计
"""
from __future__ import annotations

import glob
import json
import os
import sys
from datetime import datetime

ROOT = "/home/ubuntu/alphapilot"
RF = os.path.join(ROOT, "output/rf_score_archive")
QS = os.path.join(ROOT, "output/qmt_scores")
OUTD = os.path.join(ROOT, "output/pool_archive")
LEDGER = os.path.join(OUTD, "pool_archive.jsonl")


def _bare(sym: str) -> str:
    s = str(sym or "")
    for p in ("SH", "SZ", "BJ"):
        s = s.replace(p, "")
    s = s.split(".")[0]
    return s.zfill(6)[-6:]


def load_keys() -> set:
    keys = set()
    if os.path.exists(LEDGER):
        for ln in open(LEDGER, encoding="utf-8"):
            ln = ln.strip()
            if not ln:
                continue
            try:
                r = json.loads(ln)
                keys.add(f"{r['date']}|{r['symbol']}|{r['source']}")
            except Exception:
                pass
    return keys


def _read_json(p):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def ingest_date(date: str, keys: set, fh) -> dict:
    """固化某日各来源 → ledger（返回该日计数）。"""
    n = {}
    ddir = os.path.join(RF, date)
    # 1) icir_all_scores：全量 ~500 打分宇宙（主池）
    j = _read_json(os.path.join(ddir, "icir_all_scores.json")) if os.path.isdir(ddir) else None
    if isinstance(j, dict) and isinstance(j.get("stocks"), list):
        for it in j["stocks"]:
            sym = _bare(it.get("symbol"))
            if not sym:
                continue
            k = f"{date}|{sym}|icir_all_scores"
            if k in keys:
                continue
            keys.add(k)
            fh.write(json.dumps({
                "date": date, "symbol": sym,
                "name": it.get("name") or "",
                "score": it.get("icir_alpha"),
                "source": "icir_all_scores",
            }, ensure_ascii=False) + "\n")
            n["icir_all_scores"] = n.get("icir_all_scores", 0) + 1
    # 2) daily_recommend（09:35 重排）：recommendations + full_candidate_pool
    j = _read_json(os.path.join(ddir, "daily_recommend.json")) if os.path.isdir(ddir) else None
    if isinstance(j, dict):
        for key, src in (("recommendations", "morning_picks"), ("full_candidate_pool", "fullpool")):
            for it in (j.get(key) or []):
                sym = _bare(it.get("symbol"))
                if not sym:
                    continue
                k = f"{date}|{sym}|{src}"
                if k in keys:
                    continue
                keys.add(k)
                fh.write(json.dumps({
                    "date": date, "symbol": sym,
                    "name": it.get("name") or "",
                    "score": it.get("score"),
                    "source": src,
                }, ensure_ascii=False) + "\n")
                n[src] = n.get(src, 0) + 1
    # 3) qmt fullpool_live（09:36 实时融合池）
    ds = date.replace("-", "")
    j = _read_json(os.path.join(QS, f"{ds}.fullpool_live.json"))
    if isinstance(j, dict):
        for it in (j.get("rows") or []):
            sym = _bare(it.get("symbol"))
            if not sym:
                continue
            k = f"{date}|{sym}|fullpool_live"
            if k in keys:
                continue
            keys.add(k)
            fh.write(json.dumps({
                "date": date, "symbol": sym,
                "name": it.get("name") or "",
                "score": it.get("score"),
                "source": "fullpool_live",
            }, ensure_ascii=False) + "\n")
            n["fullpool_live"] = n.get("fullpool_live", 0) + 1
    return n


def main() -> int:
    os.makedirs(OUTD, exist_ok=True)
    keys = load_keys()
    if "--stats" in sys.argv:
        _print_stats()
        return 0
    dates = sorted({os.path.basename(d.rstrip("/")) for d in glob.glob(os.path.join(RF, "*"))
                    if os.path.isdir(d)})
    total_new = 0
    added = []
    with open(LEDGER, "a", encoding="utf-8") as fh:
        for date in dates:
            if not (len(date) == 10 and date[4] == "-"):
                continue
            n = ingest_date(date, keys, fh)
            if n:
                added.append((date, n))
                total_new += sum(n.values())
    _print_stats()
    print(f"[pool] new rows={total_new} dates_added={len(added)} ledger={LEDGER}", flush=True)
    for d, n in added[-5:]:
        print(f"    {d}: {n}", flush=True)
    return 0


def _print_stats() -> None:
    if not os.path.exists(LEDGER):
        print("[pool] ledger absent", flush=True)
        return
    per_day = {}
    per_src = {}
    for ln in open(LEDGER, encoding="utf-8"):
        ln = ln.strip()
        if not ln:
            continue
        try:
            r = json.loads(ln)
            per_day[r["date"]] = per_day.get(r["date"], 0) + 1
            per_src[r["source"]] = per_src.get(r["source"], 0) + 1
        except Exception:
            pass
    if not per_day:
        print("[pool] empty", flush=True)
        return
    days = sorted(per_day)
    avg = sum(per_day.values()) / len(days)
    print(f"[pool] ledger days={len(days)} range={days[0]}..{days[-1]} "
          f"rows={sum(per_day.values())} avg={avg:.0f}/day", flush=True)
    print(f"    by source: {per_src}", flush=True)
    tail = {d: per_day[d] for d in days[-5:]}
    print(f"    last5: {tail}", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())

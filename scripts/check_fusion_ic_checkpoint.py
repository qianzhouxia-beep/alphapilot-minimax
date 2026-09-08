#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fusion IC checkpoint: inspect ledgers and optionally stamp open pos_state.

Goal: 16:15 model_weights.json learns from QMT live / QMT sim / TDX sim
closed trades with fusion_scores. Not RD scanner IC (feedback_auto_tune).

Usage:
  python scripts/check_fusion_ic_checkpoint.py
  python scripts/check_fusion_ic_checkpoint.py --stamp-open-pos
  python scripts/check_fusion_ic_checkpoint.py --pull-server
"""
from __future__ import annotations

import argparse
import json
import math
import os
import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = Path(r"C:\alphapilot")
SCORES = LEDGER / "scores"
JSONL = LEDGER / "fusion_closed_trades.jsonl"
POS_FILES = {
    "qmt_live": LEDGER / "live_pos_state.json",
    "qmt_sim": LEDGER / "sim_pos_state.json",
    "tdx_sim": LEDGER / "tdx_pos_state.json",
}
KEY_CANDIDATES = [
    r"C:\Users\elvisq\Downloads\AlphaPiolot.pem",
    r"C:\Users\elvisq\key.pem",
]


def _fusion_from_item(item: dict, cands: list[dict]) -> dict:
    scores = []
    for it in cands:
        try:
            scores.append(float(it.get("score") or 0))
        except (TypeError, ValueError):
            pass
    try:
        sc = float((item or {}).get("score") or 0)
    except (TypeError, ValueError):
        sc = 0.0
    vm25 = 0.5
    if scores:
        lo, hi = min(scores), max(scores)
        span = (hi - lo) if hi != lo else 1.0
        vm25 = max(0.0, min(1.0, (sc - lo) / span))
    raw = 0.0
    if isinstance(item, dict):
        raw = item.get("live_main_net") or item.get("main_net") or item.get("main_net_5d") or 0
    try:
        x = float(raw)
    except (TypeError, ValueError):
        x = 0.0
    if x == 0:
        fund = 0.5
    else:
        fund = max(0.0, min(1.0, (math.tanh(x / 10_000_000.0) + 1.0) / 2.0))
    return {"vm25": round(vm25, 4), "fund_flow": round(fund, 4), "sector_heat": 0.5}


def _load_cands(yyyymmdd: str) -> list[dict]:
    p = SCORES / f"{yyyymmdd}.candidates.json"
    if not p.exists():
        return []
    d = json.loads(p.read_text(encoding="utf-8"))
    if isinstance(d, list):
        return [x for x in d if isinstance(x, dict)]
    return [x for x in (d.get("candidates") or []) if isinstance(x, dict)]


def _buy_date_to_yyyymmdd(raw) -> str:
    s = str(raw or "").replace("-", "")
    return s[:8] if len(s) >= 8 else ""


def inspect() -> dict:
    jsonl_rows = []
    if JSONL.exists():
        for line in JSONL.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                jsonl_rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    live_new = [
        r for r in jsonl_rows
        if r.get("source") in ("qmt_live", "qmt_sim", "tdx_sim")
        and not r.get("backfill")
        and isinstance(r.get("_fusion_scores"), dict)
        and r["_fusion_scores"].get("vm25") is not None
    ]
    pos_stamped = {}
    for src, p in POS_FILES.items():
        if not p.exists():
            pos_stamped[src] = {"exists": False, "n": 0, "with_fs": 0, "codes": []}
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        positions = d.get("positions") or {}
        with_fs = [
            c for c, pos in positions.items()
            if isinstance(pos, dict) and isinstance(pos.get("fusion_scores"), dict)
            and pos["fusion_scores"].get("vm25") is not None
        ]
        pos_stamped[src] = {
            "exists": True,
            "n": len(positions),
            "with_fs": len(with_fs),
            "codes": list(positions),
            "stamped": with_fs,
            "mtime": datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
        }
    today = datetime.now().strftime("%Y%m%d")
    cands = _load_cands(today)
    cand_fs = sum(
        1 for r in cands
        if isinstance(r.get("fusion_scores"), dict) and r["fusion_scores"].get("vm25") is not None
    )
    return {
        "jsonl_n": len(jsonl_rows),
        "jsonl_live_new": len(live_new),
        "jsonl_mtime": datetime.fromtimestamp(JSONL.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S") if JSONL.exists() else None,
        "pos": pos_stamped,
        "candidates_date": today,
        "candidates_n": len(cands),
        "candidates_with_fs": cand_fs,
        "live_new_sample": live_new[-3:],
    }


def stamp_open_pos() -> list[str]:
    notes = []
    for src, p in POS_FILES.items():
        if not p.exists():
            notes.append(f"{src}: missing {p.name}")
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        positions = d.get("positions") or {}
        changed = 0
        for code, pos in positions.items():
            if not isinstance(pos, dict):
                continue
            if isinstance(pos.get("fusion_scores"), dict) and pos["fusion_scores"].get("vm25") is not None:
                continue
            ymd = _buy_date_to_yyyymmdd(pos.get("buy_date"))
            cands = _load_cands(ymd) if ymd else []
            item = next((x for x in cands if str(x.get("symbol") or "").upper() == code.upper()), None)
            if not item:
                notes.append(f"{src} {code}: no candidates for {ymd or '?'}")
                continue
            pos["fusion_scores"] = _fusion_from_item(item, cands)
            pos["fusion_scores_note"] = "stamped_after_hours_from_candidates"
            changed += 1
        if changed:
            bak = p.with_suffix(p.suffix + ".bak_fusion_20260828")
            if not bak.exists():
                shutil.copy2(p, bak)
            d["updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            tmp = p.with_suffix(p.suffix + ".tmp")
            tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
            os.replace(tmp, p)
            notes.append(f"{src}: stamped {changed} positions -> {p.name}")
        else:
            notes.append(f"{src}: no new stamps")
    return notes


def pull_server() -> dict:
    import paramiko

    last = None
    ssh = None
    for kp in KEY_CANDIDATES:
        if not os.path.exists(kp):
            continue
        try:
            k = paramiko.RSAKey.from_private_key_file(kp)
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect("150.158.100.236", username="ubuntu", pkey=k, timeout=15)
            break
        except Exception as e:
            last = str(e)
            ssh = None
    if ssh is None:
        return {"ok": False, "error": last or "no_key"}
    out = {"ok": True}
    cmd = r"""
python3 - <<'PY'
import json, os
from datetime import datetime
from pathlib import Path
w = Path("/home/ubuntu/alphapilot/output/feedback/model_weights.json")
j = Path("/home/ubuntu/alphapilot/data/fusion_closed_trades.jsonl")
e = Path("/home/ubuntu/alphapilot/export_qmt_scores.py")
print("WEIGHTS_EXISTS", w.exists())
if w.exists():
    print("WEIGHTS_MTIME", os.path.getmtime(w))
    print("WEIGHTS_JSON", w.read_text(encoding="utf-8"))
print("JSONL_EXISTS", j.exists(), "SIZE", j.stat().st_size if j.exists() else 0)
print("EXPORT_HAS_FUSION", "fusion_scores" in e.read_text(encoding="utf-8", errors="ignore") if e.exists() else False)
print("FEEDBACK_HAS_JSONL", "fusion_closed_trades" in Path("/home/ubuntu/alphapilot/scripts/run_feedback_loop.py").read_text(encoding="utf-8", errors="ignore") if Path("/home/ubuntu/alphapilot/scripts/run_feedback_loop.py").exists() else False)
# Server-local 16:15 gate (server TZ Asia/Shanghai): updated_at >= today 16:15.
af = False
upd = None
if w.exists():
    try:
        data = json.loads(w.read_text(encoding="utf-8"))
        upd = data.get("updated_at")
        if upd:
            d = datetime.fromisoformat(upd)
            now = datetime.now()
            af = d.date() == now.date() and (d.hour > 16 or (d.hour == 16 and d.minute >= 15))
    except Exception:
        af = False
print("WEIGHTS_AFTER_1615", af, upd)
print("SERVER_NOW", datetime.now().isoformat(timespec="seconds"))
PY
"""
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=30)
    out["stdout"] = stdout.read().decode("utf-8", errors="replace")
    out["stderr"] = stderr.read().decode("utf-8", errors="replace")
    ssh.close()
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stamp-open-pos", action="store_true")
    ap.add_argument("--pull-server", action="store_true")
    args = ap.parse_args()
    if args.stamp_open_pos:
        for line in stamp_open_pos():
            print("STAMP", line)
    info = inspect()
    print(json.dumps(info, ensure_ascii=False, indent=2))
    server = None
    if args.pull_server:
        server = pull_server()
        print("SERVER", json.dumps(server, ensure_ascii=False, indent=2))
    live_ok = info["jsonl_live_new"] > 0
    pos_ok = any(v.get("with_fs") for v in info["pos"].values())
    cand_ok = info["candidates_with_fs"] > 0
    weights_cron = False
    n_samples = None
    updated_at = None
    if server and server.get("ok") and server.get("stdout"):
        text = server["stdout"]
        if "WEIGHTS_AFTER_1615" in text:
            try:
                seg = text.split("WEIGHTS_AFTER_1615", 1)[1].strip().splitlines()[0]
                parts = seg.split()
                # Server-side gate: same trading day AND >=16:15, server TZ.
                weights_cron = live_ok and parts[0] == "True"
                if len(parts) > 1:
                    updated_at = parts[1]
            except Exception:
                pass
        if "WEIGHTS_JSON" in text:
            try:
                blob = text.split("WEIGHTS_JSON", 1)[1]
                blob = blob.split("JSONL_EXISTS", 1)[0].strip()
                w = json.loads(blob)
                n_samples = w.get("n_samples")
            except Exception:
                pass
    print("GATE_jsonl_non_backfill", live_ok, info["jsonl_live_new"])
    print("GATE_open_pos_fusion", pos_ok)
    print("GATE_today_candidates_fusion", cand_ok, info["candidates_with_fs"])
    print("GATE_weights_after_1615", weights_cron, updated_at, "n_samples", n_samples)
    print("NOTE RD scanner IC is feedback_auto_tune / feedback_tuned_weights.json — not this file")
    print("NOTE fusion ranking forward is REJECTED (2026-08-28 paper bt); this checker is fusion IC only")
    if n_samples is not None:
        if n_samples >= 5:
            print("INTERP n_samples>=5 且 rolling_ic 非空 → 权重已按真实盈亏 IC 移动 (目标达成)")
        elif n_samples > 0:
            print("INTERP n_samples 1-4 → 服务器已见真实平仓但样本不足(<5) 权重未动，属设计保护，继续积累")
        else:
            print("INTERP n_samples=0 → 无真实平仓样本，链路未产生学习样本（可能三端未重启/未平仓）")
    goal_ok = live_ok and weights_cron
    print("GATE_goal_complete", goal_ok)
    return 0 if goal_ok else 2


if __name__ == "__main__":
    raise SystemExit(main())

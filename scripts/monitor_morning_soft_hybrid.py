#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""晨间 soft_hybrid 监控 — 分两段：

  --stage pre   09:26 跑：仅预检「竞价热度 + 资金主线 + 研报 bias」三个输入信号，
                赶在 09:35 终选前发现异常（早预警）。
  --stage full  09:50 跑：全链路验证（默认），含 soft_hybrid 生效 + Top2 结果。

任一项失败 verdict=ATTENTION 并 exit code 2，便于外部发现。
结果写 output/morning_soft_hybrid_monitor.json
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path("/home/ubuntu/alphapilot")
if not ROOT.exists():
    ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)

OUT = ROOT / "output"
LOGS = OUT / "logs"
today = datetime.now().strftime("%Y-%m-%d")


def load(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def read_tail(p: Path, tail: int = 2000) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")[-tail:]
    except Exception:
        return ""


def _archive_daily_snapshot() -> None:
    """每日快照归档：竞价热度 / 资金主线 / daily_recommend / picks / bias。

    供日后 soft_hybrid 完整回测（当前竞价热度无历史归档，回测缺信号源）。
    归档到 output/soft_hybrid_archive/{date}/。不覆盖已存在文件。
    """
    try:
        dst = OUT / "soft_hybrid_archive" / today
        dst.mkdir(parents=True, exist_ok=True)
        files = [
            ("call_auction_sector_heat.json", OUT / "call_auction_sector_heat.json"),
            ("hot_sector_bypass_pool.json", OUT / "hot_sector_bypass_pool.json"),
            ("sector_research_bias.json", OUT / "sector_research_bias.json"),
            ("daily_recommend.json", OUT / "daily_recommend.json"),
            ("morning_live_picks.json", OUT / "morning_live_picks.json"),
            ("signal_conflicts.json", OUT / "signal_conflicts.json"),
            ("data_quality_audit.json", OUT / "data_quality_audit.json"),
            ("pseudo_signal_audit.json", OUT / "pseudo_signal_audit.json"),
        ]
        saved = []
        for name, src in files:
            if src.exists():
                tgt = dst / name
                if not tgt.exists():
                    import shutil

                    shutil.copy2(src, tgt)
                    saved.append(name)
        if saved:
            print(f"  归档快照 {today}: {saved}", flush=True)
    except Exception as e:
        print(f"  归档快照失败: {e}", flush=True)


checks: list[dict] = []


def add(name: str, ok: bool, detail: str) -> None:
    checks.append({"check": name, "ok": bool(ok), "detail": str(detail)})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=["pre", "full"], default="full")
    args = parser.parse_args()
    stage = args.stage

    # ══ pre 预检：09:26 跑，只验证三个输入信号（赶在 09:35 前） ══
    # 1. 集合竞价热度：今日 09:25 后生成，且存在 hot_sectors
    ah = load(OUT / "call_auction_sector_heat.json")
    ah_ok, ah_detail = False, "文件缺失或无法解析"
    if isinstance(ah, dict):
        g = ah.get("generated_at") or ""
        hot = ah.get("hot_sectors") or []
        ah_ok = g.startswith(today) and len(hot) > 0
        ah_detail = f"generated_at={g} hot_sectors={len(hot)} 板块={[x.get('sector') for x in hot[:5]]}"
    add("call_auction_sector_heat 今日竞价热度", ah_ok, ah_detail)

    # 2. 资金主线旁路池：今日 05:00 生成且 enabled
    bp = load(OUT / "hot_sector_bypass_pool.json")
    bp_ok, bp_detail = False, "文件缺失或无法解析"
    if isinstance(bp, dict):
        ts = (bp.get("ts") or "")[:10]
        inds = [x.get("name") for x in (bp.get("industries") or [])]
        bp_ok = ts == today and bp.get("enabled", True) and len(inds) > 0
        bp_detail = f"ts={bp.get('ts')} 主线板块={inds[:6]}"
    add("hot_sector_bypass_pool 今日资金主线", bp_ok, bp_detail)

    # 3. 研报 bias：今日 preopen bias 存在
    bias = load(OUT / "sector_research_bias.json")
    bias_ok, bias_detail = False, "文件缺失或无法解析"
    if isinstance(bias, dict):
        bd = (bias.get("date") or "")[:10]
        bias_ok = bd == today and (bias.get("prefer") or bias.get("avoid"))
        bias_detail = f"date={bias.get('date')} session={bias.get('session')} prefer={len(bias.get('prefer') or [])} avoid={len(bias.get('avoid') or [])}"
    add("sector_research_bias 今日研报偏好", bias_ok, bias_detail)

    if stage == "pre":
        ok_all = all(c["ok"] for c in checks)
        result = {
            "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "stage": "pre",
            "date": today,
            "verdict": "OK" if ok_all else "ATTENTION",
            "checks": checks,
            "note": "09:26 预检：竞价热度+资金主线+研报bias 三输入信号。ATTENTION 表示 09:35 终选前需人工处理。",
        }
        (OUT / "morning_soft_hybrid_monitor.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        sys.exit(0 if ok_all else 2)

    # ══ full 全链路：09:50 跑，同时做每日快照归档（供日后回测） ══
    _archive_daily_snapshot()

    # 数据真实性三件套：信号冲突 / 数据质量 / 伪信号
    sc = load(OUT / "signal_conflicts.json")
    sc_ok, sc_detail = True, "今日信号冲突检测未运行或文件缺失"
    if isinstance(sc, dict):
        scg = (sc.get("generated_at") or "")[:10]
        n = sc.get("n_conflicts") or 0
        high = [c.get("sector") for c in (sc.get("conflicts") or []) if c.get("severity") == "high"]
        sc_ok = scg == today and n >= 0
        sc_detail = f"generated_at={sc.get('generated_at')} 冲突={n} 个 high级={high} " \
                    f"优先级建议: {[c.get('sector')+':'+c.get('conflict') for c in (sc.get('conflicts') or [])[:3]]}"
        # high 级冲突视为需要人工研讨 → 不 OK
        sc_ok = scg == today and len(high) == 0
    add("signal_conflicts 信号冲突", sc_ok, sc_detail)

    qa = load(OUT / "data_quality_audit.json")
    qa_ok, qa_detail = True, "今日数据质量审计未运行或文件缺失"
    if isinstance(qa, dict):
        qg = (qa.get("generated_at") or "")[:10]
        qa_ok = qg == today and qa.get("verdict") == "OK"
        qa_detail = f"generated_at={qa.get('generated_at')} verdict={qa.get('verdict')} " \
                    f"问题={[f.get('check') for f in (qa.get('findings') or []) if not f.get('ok')]}"
    add("data_quality 数据质量审计", qa_ok, qa_detail)

    ps = load(OUT / "pseudo_signal_audit.json")
    ps_ok, ps_detail = True, "今日伪信号检测未运行或文件缺失"
    if isinstance(ps, dict):
        pg = (ps.get("generated_at") or "")[:10]
        ps_ok = pg == today and ps.get("verdict") == "OK"
        ps_detail = f"generated_at={ps.get('generated_at')} verdict={ps.get('verdict')} " \
                    f"问题={[f.get('check') for f in (ps.get('findings') or []) if not f.get('ok')]}"
    add("pseudo_signal 伪信号检测", ps_ok, ps_detail)

    # ══ full 全链路：09:50 跑 ══
    # 4. 研报门控 soft_hybrid 生效
    #   优先看 picks 的 research_gate.mode（精确），兜底看 l2_refresh.log
    pk_tmp = load(OUT / "morning_live_picks.json")
    rg_mode = None
    if isinstance(pk_tmp, dict):
        rg_mode = (pk_tmp.get("research_gate") or {}).get("mode")
    l2 = read_tail(LOGS / "l2_refresh.log", 6000)
    has_sh = "research_sector_gate[soft_hybrid]" in l2 or rg_mode == "soft_hybrid"
    l2_lines = [
        ln for ln in l2.splitlines()
        if "research_sector_gate[" in ln or "研报门控后" in ln or "morning picks" in ln
    ]
    l2_ok = has_sh and any("研报门控后" in ln for ln in l2_lines)
    l2_detail = "今日未见 soft_hybrid 生效记录（picks.mode=" + str(rg_mode) + "）"
    if l2_lines:
        l2_detail = "picks.mode=" + str(rg_mode) + " | " + " | ".join(l2_lines[-3:])
    add("morning_live soft_hybrid 生效", l2_ok, l2_detail)

    # 5. morning_live_picks 今日 Top2，且带加权字段
    pk = load(OUT / "morning_live_picks.json")
    pk_ok, pk_detail = False, "文件缺失或无法解析"
    if isinstance(pk, dict):
        asof = (pk.get("asof") or "")[:10]
        p = pk.get("picks") or []
        pk_ok = asof == today and len(p) > 0
        rows = [
            f"{x.get('name')}({x.get('symbol')}) score={x.get('score')} "
            f"tier={x.get('research_tier')} bypass={x.get('bypass_sector_hit')} "
            f"auction={x.get('auction_sector_hit')} conflict={x.get('signal_conflict_hit')} "
            f"boost={x.get('sector_hard_boost')}"
            for x in p
        ]
        rg = pk.get("research_gate") or {}
        pk_detail = (
            f"asof={pk.get('asof')} pool={pk.get('pool_size')} gated={pk.get('gated_size')} "
            f"mode={rg.get('mode')} auction_hits={rg.get('auction_hits')} bypass_hits={rg.get('bypass_hits')} "
            f"conflict_hits={rg.get('conflict_hits')} soft_avoid={rg.get('soft_avoid')} | "
            + " ; ".join(rows)
        )
    add("morning_live_picks 今日 Top2", pk_ok, pk_detail)

    # 6. live_momentum_scanner 今日成功
    sm = read_tail(LOGS / "live_momentum_scanner.log", 3000)
    sm_ok = ("全市场" in sm or "扫描" in sm) and ("写入" in sm or "完成" in sm or "推荐:" in sm)
    sm_detail = "今日 scanner 日志未见成功标记"
    m = re.findall(r"\[[^]]+\]\s*(?:推荐:.*|写入:.*|终选.*)", sm)
    if m:
        sm_detail = " | ".join(m[-3:])
        sm_ok = True
    add("live_momentum_scanner 09:35 终选", sm_ok, sm_detail)

    ok_all = all(c["ok"] for c in checks)
    result = {
        "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "stage": "full",
        "date": today,
        "verdict": "OK" if ok_all else "ATTENTION",
        "checks": checks,
        "note": "09:50 全链路监控：竞价热度+资金主线+研报软加权+Top2+数据真实性三件套(冲突/质量/伪信号)。ATTENTION 时需人工核对。",
    }
    (OUT / "morning_soft_hybrid_monitor.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if ok_all else 2)


if __name__ == "__main__":
    raise SystemExit(main())

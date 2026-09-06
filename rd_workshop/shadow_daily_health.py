# -*- coding: utf-8 -*-
"""每日影子/观察 健康体检(防空转) -- 2026-09-06 建。

背景: 资金三角影子空转 9 天无告警, 教训是"影子没写 = 没声音"。本脚本每日两次核对
"每个影子/观察在目标交易日是否写了新记录", 缺失即企微告警。
约定: PASS 静默 / FAIL 才报(对齐 MEMORY.md「日常验证分工约定」)。

两个 cron 时段(互补, 无重叠职责):
  A) 交易日 16:55  --asof=today:   校验当天 09:35 旁路影 + 盘后 monitor + 竞价归档 + C1/C2。
     此时 22:20/00:20 双跑尚未跑, 故不查。
  B) 周二~六 09:10 --prev-trading: 校验"上一交易日"完整闭环, 重点补查双跑 CSV
     (turnover 22:20 / weakscore 00:20 都在此时已覆盖上一交易日), 并对 A 复核一遍。

防误报: 若目标日疑似非交易日(8 个 09:35 影全部无该日 + market_tone 未到该日 + 竞价归档
缺失), 判 SKIP 退出 0, 不发告警(法定节假日 cron 仍会触发)。

用法: python3 -u rd_workshop/shadow_daily_health.py [--asof YYYY-MM-DD | --prev-trading] [--dry]
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import sys
from pathlib import Path

ROOT = Path(os.environ.get("ALPHAPILOT_ROOT") or Path(__file__).resolve().parents[1])
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
LOG = ROOT / "output" / "logs" / "shadow_daily_health.log"


def _log(msg: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"[{_dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def _json_last_date(p: Path):
    """jsonl/json 末尾记录里的日期字段 (asof/date/day/ts/...), 返回 YYYY-MM-DD 或 None。"""
    try:
        if not p.exists() or p.stat().st_size == 0:
            return None
        lines = [ln for ln in p.read_text(encoding="utf-8", errors="replace").splitlines() if ln.strip()]
        if not lines:
            return None
        objs = []
        try:
            objs.append(json.loads(lines[-1]))
        except Exception:
            pass
        if not objs:
            try:
                o = json.loads("\n".join(lines))
                objs.append(o)
            except Exception:
                pass
        for o in objs:
            if isinstance(o, list):
                o = o[-1] if o else {}
            for k in ("asof", "date", "day", "ts", "archived_at", "checked_at", "generated_at"):
                v = o.get(k) if isinstance(o, dict) else None
                if v:
                    return str(v)[:10]
        return None
    except Exception:
        return None


def _csv_last_date(p: Path):
    try:
        if not p.exists():
            return None
        lines = [ln for ln in p.read_text(encoding="utf-8", errors="replace").splitlines() if ln.strip()]
        return lines[-1].split(",")[0].strip()[:10] if len(lines) >= 2 else None
    except Exception:
        return None


def _logfile_touched_on(p: Path, asof: str) -> bool:
    try:
        return p.exists() and _dt.datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d") == asof
    except Exception:
        return False


def prev_trading_day(d: _dt.date) -> _dt.date:
    d = d - _dt.timedelta(days=1)
    while d.weekday() >= 5:
        d -= _dt.timedelta(days=1)
    return d


# (名称, 类型, 相对路径) ; 类型: jsonl=append按末行日期 / json=覆写按内容日期 / mtime=覆写按文件mtime日 / log=日志按mtime日 / file=存在即可
def build_checks(asof: str):
    O = ROOT / "output"
    return [
        # ---- 09:35 append jsonl(逐日一行) ----
        ("09:35 fund_bonus(资金三角)", "jsonl", "fund_bonus_shadow.jsonl"),
        ("09:35 market_regime", "jsonl", "market_regime_shadow.jsonl"),
        ("09:35 sector_quality", "jsonl", "sector_quality_shadow.jsonl"),
        ("09:35 market_flow_condition", "jsonl", "market_flow_condition_shadow.jsonl"),
        ("09:35 wind_regime", "jsonl", "wind_regime_shadow.jsonl"),
        ("09:35 weak_score", "jsonl", "weak_score_shadow.jsonl"),
        ("09:35 live_tone", "jsonl", "live_tone_shadow.jsonl"),
        ("09:35 vp_factor", "jsonl", "vp_factor_shadow.jsonl"),
        ("shadow_top2 history", "jsonl", "shadow_top2_history.jsonl"),
        ("reversal_shadow_history", "jsonl", "reversal_shadow_history.jsonl"),
        # ---- 每日整文件覆写 ----
        ("shadow_top2 report(16:26)", "mtime", "shadow_top2_report.json"),
        ("top2_t1t5(16:25)", "mtime", "top2_t1t5.json"),
        ("market_tone(09:33)", "mtime", "market_tone.json"),
        # ---- 归档 / C组日志 ----
        ("竞价归档 pre_market_archive(09:25)", "file", f"pre_market_archive/{asof}.json"),
        ("C1 breakout_monitor.log(16:28)", "log", "logs/breakout_monitor.log"),
        ("C2 top2_excess.log(16:29)", "log", "logs/top2_excess.log"),
    ]


def _eval(typ: str, p: Path, asof: str):
    """返回 (是否达标, 现状描述)。jsonl 看末行日期; json 看内容里日期; mtime/log 看文件mtime日; file 看存在。"""
    if typ in ("jsonl", "json"):
        got = _json_last_date(p)
        return (bool(got) and got >= asof), got
    if typ in ("mtime", "log"):
        return _logfile_touched_on(p, asof), None
    if typ == "file":
        return p.exists(), None
    return False, None


def _today_has_any_marker(asof: str) -> bool:
    """非交易日判定: 8 个 09:35 影若全无 asof 行,且 market_tone 文件也没在 asof 日被覆写,
    且竞价归档缺失 -> 疑似非交易日(法定节假日 cron 也会触发)。"""
    cnt09 = 0
    for rel in ("fund_bonus_shadow.jsonl", "market_regime_shadow.jsonl",
                "sector_quality_shadow.jsonl", "market_flow_condition_shadow.jsonl",
                "wind_regime_shadow.jsonl", "weak_score_shadow.jsonl",
                "live_tone_shadow.jsonl", "vp_factor_shadow.jsonl"):
        p = ROOT / "output" / rel
        if p.exists():
            got = _json_last_date(p)
            if got is not None and got >= asof:
                cnt09 += 1
    tone = _logfile_touched_on(ROOT / "output" / "market_tone.json", asof)
    arch = (ROOT / "output" / f"pre_market_archive/{asof}.json").exists()
    return not (cnt09 == 0 and not tone and not arch)


def main() -> int:
    args = sys.argv[1:]
    dry = "--dry" in args
    today = _dt.date.today()
    if "--asof" in args:
        asof = args[args.index("--asof") + 1]
    elif "--prev-trading" in args:
        asof = prev_trading_day(today).isoformat()
    else:
        asof = today.isoformat()

    if not _today_has_any_marker(asof):
        _log(f"shadow_daily_health asof={asof} -> SKIP (疑似非交易日: 09:35影全无/market_tone未写/竞价归档缺失)")
        return 0

    checks = build_checks(asof)
    fails: list[tuple[str, str]] = []
    oks: list[str] = []

    # 双跑 CSV 只在 prev-trading 模式校验(22:20/00:20 已覆盖), today 模式(16:55)尚未跑不查
    csv_checks = []
    if "--prev-trading" in args:
        csv_checks = [
            ("turnover 双跑 CSV", "csv", "shadow_turnover/shadow_log.csv"),
            ("weakscore 双跑 CSV", "csv", "shadow_weakscore/shadow_log.csv"),
        ]

    for name, typ, rel in checks + csv_checks:
        if typ == "csv":
            got = _csv_last_date(ROOT / "rd_workshop" / rel)
            if got and got >= asof:
                oks.append(name)
            else:
                fails.append((name, got or "MISSING"))
            continue
        ok, got = _eval(typ, ROOT / "output" / rel, asof)
        if ok:
            oks.append(name)
        else:
            fails.append((name, got or "MISSING"))

    summary = {
        "checked_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "asof": asof,
        "ok": not fails,
        "ok_count": len(oks),
        "fail_count": len(fails),
        "fails": fails,
    }
    (ROOT / "output" / "logs" / "shadow_daily_health.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    if fails:
        _log(f"shadow_daily_health asof={asof} -> ALERT ({len(fails)} fail): "
             + "; ".join(f"{n}={g}" for n, g in fails))
        if not dry:
            try:
                from wecom_push import send_markdown
                body = ("## 影子健康体检 ALERT\n\n"
                        f"目标交易日 {asof} 有 {len(fails)} 项没写新记录(疑似空转):\n\n"
                        + "\n".join(f"- {n} (last={g})" for n, g in fails)
                        + "\n\n> 排查: knowledge/ops/shadows_registry.md · 体检探针 _audit_shadows_20260906.py")
                ok, err = send_markdown(body)
                _log(f"wecom alert push ok={ok} err={err}")
            except Exception as e:
                _log(f"wecom alert skip: {e}")
        return 2
    _log(f"shadow_daily_health asof={asof} -> OK ({len(oks)} 项全齐)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RD 影子并行 Top2 对比自动分析（生产 vs 候选）。

数据源: output/shadow_top2_history.jsonl
  （09:35 morning_live_fund_select.py 写入，每行 = 1 个选股日，含 prod_picks + shadow_picks）
口径: 与 accumulate_top2_t1t5.py 一致 — T0 收盘买入，T+n 收盘累计涨幅%
产出:
  output/shadow_top2_report.json  — 明细 + 汇总（幂等，可反复运行）
  output/shadow_top2_report.md    — 人读报告（含"候选是否优于生产"的自动结论）
建议 cron: 工作日 16:26（accumulate_top2_t1t5 16:25 后、K线 16:18 已同步）
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(os.environ.get("ALPHAPILOT_ROOT") or "/home/ubuntu/alphapilot")
if not ROOT.exists():
    ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

HISTORY = ROOT / "output" / "shadow_top2_history.jsonl"
KLINE = ROOT / "data" / "kline_cache" / "kline_all.parquet"
OUT_JSON = ROOT / "output" / "shadow_top2_report.json"
OUT_MD = ROOT / "output" / "shadow_top2_report.md"
REPORT_MIN_DAYS = 8  # 有 T+2 数据的到期样本 >= 此值才下"候选更优/更差"结论
MAX_PUSH_DAYS = 5  # 微信推送里逐日对比最多显示最近几天


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


# ── 可选的 Excel 报告（与 send_daily_picks_excel.py 同依赖 openpyxl）────────────
try:
    import openpyxl
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    HAS_EXCEL = True
except Exception:
    HAS_EXCEL = False

EXCEL_DIR = ROOT / "output" / "excel_shadow"


def make_shadow_excel(rows: list[dict], summary: dict, pairs: list[dict], today: str) -> Path | None:
    """生成影子对比 Excel，返回路径（无 openpyxl 时返回 None）。"""
    if not HAS_EXCEL:
        return None
    EXCEL_DIR.mkdir(parents=True, exist_ok=True)
    path = EXCEL_DIR / f"AlphaPilot影子对比_{today}.xlsx"

    wb = openpyxl.Workbook()
    header_fill = PatternFill("solid", fgColor="1F4E79")
    header_font = Font(color="FFFFFF", bold=True, size=10)
    thin = Side(style="thin", color="CCCCCC")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    cand_fill = PatternFill("solid", fgColor="E2EFDA")  # 候选更优行
    title_font = Font(bold=True, size=13, color="1F4E79")

    def style_header(ws, headers):
        for c, h in enumerate(headers, 1):
            cell = ws.cell(row=1, column=c, value=h)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            cell.border = border
        ws.freeze_panes = "A2"

    def auto_width(ws, min_w=8, max_w=24):
        for col in ws.columns:
            letter = get_column_letter(col[0].column)
            width = max(min_w, min(max_w, max(len(str(c.value or "")) for c in col) + 2))
            ws.column_dimensions[letter].width = width

    def fmt(v):
        return None if v is None else (round(v, 2) if isinstance(v, (int, float)) else v)

    # Sheet1 汇总
    ws1 = wb.active
    ws1.title = "汇总"
    headers1 = ["组", "持有期", "样本", "平均%", "中位%", "正收益", "最好%", "最差%"]
    ws1.append(headers1)
    style_header(ws1, headers1)
    for which, label in (("prod", "生产"), ("cand", "候选")):
        for i in (1, 2):
            s = (summary.get(which) or {}).get(str(i))
            if not s:
                continue
            ws1.append([
                label, f"T+{i}", s["n"], s["avg_pct"], s["median_pct"],
                f"{s['pos_count']}/{s['n']}", s["best"], s["worst"],
            ])
    for row in ws1.iter_rows(min_row=2, max_row=ws1.max_row, max_col=len(headers1)):
        for cell in row:
            cell.border = border
    auto_width(ws1)

    # Sheet2 逐日对比
    ws2 = wb.create_sheet("逐日对比")
    headers2 = ["选股日", "生产 T+2 均%", "候选 T+2 均%", "候选更优?"]
    ws2.append(headers2)
    style_header(ws2, headers2)
    for p in pairs:
        r = ws2.max_row + 1
        ws2.append([p["date"], p["prod_avg_t2"], p["cand_avg_t2"], "是" if p["cand_better"] else "否"])
        if p["cand_better"]:
            for c in range(1, len(headers2) + 1):
                ws2.cell(row=r, column=c).fill = cand_fill
    for row in ws2.iter_rows(min_row=2, max_row=ws2.max_row, max_col=len(headers2)):
        for cell in row:
            cell.border = border
    auto_width(ws2)

    # Sheet3 明细
    ws3 = wb.create_sheet("明细")
    headers3 = ["选股日", "组", "代码", "名称", "T0收盘", "T+1%", "T+2%"]
    ws3.append(headers3)
    style_header(ws3, headers3)
    for r in rows:
        for which, label in (("prod", "生产"), ("cand", "候选")):
            for p in r[which]:
                ws3.append([
                    r["date"], label, p["symbol"], p["name"],
                    fmt(p.get("t0_close")),
                    fmt(p.get("rets", {}).get(1)),
                    fmt(p.get("rets", {}).get(2)),
                ])
    for row in ws3.iter_rows(min_row=2, max_row=ws3.max_row, max_col=len(headers3)):
        for cell in row:
            cell.border = border
    auto_width(ws3)

    # Sheet4 说明
    ws4 = wb.create_sheet("说明")
    ws4.cell(row=1, column=1, value=f"RD 影子并行 Top2 对比  {today}").font = title_font
    notes = [
        "口径：T0 收盘买入，T+1/T+2 收盘累计涨幅%（与 accumulate_top2_t1t5 同口径）。",
        "生产 = 09:35 morning_live 实际 Top2（money_flow_pass+score 选股）；",
        "候选 = RD 候选模型对同一 gated 池重打分 Top2（只记录，不改生产）。",
        f"到期门槛 {REPORT_MIN_DAYS} 天，未到持有期的格子为空。",
        "此表为量化研究参考，不构成投资建议。",
    ]
    for i, line in enumerate(notes, start=3):
        ws4.cell(row=i, column=1, value=line)
    ws4.column_dimensions["A"].width = 90

    wb.save(path)
    log(f"Excel 已生成: {path}")
    return path


def _asof_hour(rec: dict):
    raw = str(rec.get("asof") or "")
    try:
        return int(raw[11:13])
    except (TypeError, ValueError, IndexError):
        return 99


def load_history() -> list[dict]:
    if not HISTORY.exists():
        return []
    by_date: dict[str, dict] = {}
    order: list[str] = []
    for line in HISTORY.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        day = str(rec.get("date") or "")
        if not day:
            continue
        old = by_date.get(day)
        if old is None:
            by_date[day] = rec
            order.append(day)
            continue
        oh, nh = _asof_hour(old), _asof_hour(rec)
        if oh == 9 and nh != 9:
            continue
        if oh == 9 and nh == 9:
            if str(rec.get("asof") or "") < str(old.get("asof") or ""):
                by_date[day] = rec
            continue
        if nh == 9:
            by_date[day] = rec
            continue
        by_date[day] = rec
    return [by_date[d] for d in order]


def load_kline() -> pd.DataFrame:
    df = pd.read_parquet(KLINE, columns=["symbol", "date", "close"])
    df["date"] = pd.to_datetime(df["date"])
    return df


def main() -> int:
    log("Shadow Top2 对比分析开始")
    history = load_history()
    log(f"shadow 记录: {len(history)} 个选股日")

    if not history:
        payload = {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "rows": [],
            "summary": {},
            "verdict": "NO_DATA",
            "note": "周一 09:35 起每日自动累积；暂无 shadow 记录。",
        }
        OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        OUT_MD.write_text("# Shadow Top2 对比（生产 vs 候选）\n\n暂无数据，周一 09:35 起自动累积。\n", encoding="utf-8")
        log(f"已写空报告 {OUT_JSON}")
        return 0

    df = load_kline()
    trading_days = sorted(df["date"].unique())
    stock_series: dict[str, pd.Series] = {}

    def close_on(sym: str, d):
        s = stock_series.get(sym)
        if s is None or len(s) == 0:
            return None
        idx = np.searchsorted(s.index.values, np.datetime64(d), side="right")
        if idx == 0:
            return None
        exact = s.index.values[idx - 1]
        if exact != np.datetime64(d):
            return None
        return float(s.iloc[idx - 1])

    def next_n_days(after_d, n):
        arr = np.array(trading_days)
        pos = np.searchsorted(arr, np.datetime64(after_d), side="right")
        return trading_days[pos:pos + n]

    def get_series(sym: str):
        if sym not in stock_series:
            sub = df[df["symbol"] == sym][["date", "close"]].set_index("date")["close"]
            stock_series[sym] = sub
        return stock_series[sym]

    # 逐日解析：生产 Top2 vs 候选 Top2
    rows = []
    for rec in history:
        day = str(rec.get("date") or "")
        t0 = pd.Timestamp(day)
        future = next_n_days(t0, 3)  # T+1, T+2 (协议最多看到 T+2)
        prod_picks = (rec.get("prod_picks") or [])[:2]
        shadow_picks = (rec.get("shadow_picks") or [])[:2]

        groups = {"prod": [], "cand": []}
        for label, picks in (("prod", prod_picks), ("cand", shadow_picks)):
            for p in picks:
                sym = str(p.get("symbol") or "")[-6:]
                if not sym:
                    continue
                get_series(sym)
                base = close_on(sym, day)
                rets = {}
                dates = {}
                for i in range(1, 3):
                    if i > len(future):
                        break
                    d = future[i - 1]
                    dates[i] = str(d.date())
                    c = close_on(sym, d)
                    if c is None or base is None or base <= 0:
                        rets[i] = None
                    else:
                        rets[i] = round((c / base - 1) * 100, 2)
                groups[label].append({
                    "symbol": sym,
                    "name": p.get("name") or "",
                    "score": p.get("score"),
                    "proba": p.get("proba"),
                    "t0_close": round(base, 2) if base else None,
                    "rets": rets,
                    "dates": dates,
                })

        rows.append({
            "date": day,
            "asof": rec.get("asof"),
            "model_dir": rec.get("model_dir"),
            "n_gated": rec.get("n_gated"),
            "position_exposure": rec.get("position_exposure"),
            "prod": groups["prod"],
            "cand": groups["cand"],
        })

    # 汇总：只统计已到 T+2 的样本
    def collect(which: str, i: int):
        vals = []
        for r in rows:
            for p in r[which]:
                v = p.get("rets", {}).get(i)
                if v is not None:
                    vals.append((r["date"], p["symbol"], p["name"], v))
        return vals

    summary = {}
    for which in ("prod", "cand"):
        summary[which] = {}
        for i in (1, 2):
            vals = collect(which, i)
            if not vals:
                continue
            nums = [x[3] for x in vals]
            summary[which][str(i)] = {
                "n": len(nums),
                "avg_pct": round(float(np.mean(nums)), 2),
                "median_pct": round(float(np.median(nums)), 2),
                "pos_count": int(sum(1 for v in nums if v > 0)),
                "best": round(float(max(nums)), 2),
                "worst": round(float(min(nums)), 2),
            }

    # 逐日对比：候选 T+2 是否优于生产（用两只均值）
    pairs = []
    for r in rows:
        pv = [x.get("rets", {}).get(2) for x in r["prod"]]
        cv = [x.get("rets", {}).get(2) for x in r["cand"]]
        pv = [x for x in pv if x is not None]
        cv = [x for x in cv if x is not None]
        if not pv or not cv:
            continue
        pm = float(np.mean(pv))
        cm = float(np.mean(cv))
        pairs.append({"date": r["date"], "prod_avg_t2": round(pm, 2), "cand_avg_t2": round(cm, 2), "cand_better": bool(cm > pm)})

    n_done = len(pairs)
    cand_win = sum(1 for p in pairs if p["cand_better"])
    verdict = "NO_CONCLUSION"
    if n_done >= REPORT_MIN_DAYS:
        diff = sum((p["cand_avg_t2"] - p["prod_avg_t2"]) for p in pairs) / n_done
        if cand_win / n_done >= 0.6 and diff > 0:
            verdict = "CAND_BETTER"
        elif cand_win / n_done <= 0.4 and diff < 0:
            verdict = "PROD_BETTER"
        else:
            verdict = "INCONCLUSIVE"

    payload = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "method": "Shadow Top2: T0收盘买入, T+1/T+2收盘累计涨幅% (与 top2_t1t5 同口径)",
        "report_min_days": REPORT_MIN_DAYS,
        "rows": rows,
        "summary": summary,
        "pairwise": pairs,
        "n_done": n_done,
        "cand_better_days": cand_win,
        "verdict": verdict,
        "verdict_note": {
            "NO_DATA": "暂无 shadow 记录",
            "NO_CONCLUSION": f"到期样本 {n_done} < {REPORT_MIN_DAYS}，继续累积",
            "CAND_BETTER": "候选 Top2 T+2 优于生产，建议进入人工评审",
            "PROD_BETTER": "生产 Top2 T+2 更优，候选不建议晋升",
            "INCONCLUSIVE": "方向不稳定，继续累积",
        }[verdict],
    }
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    log(f"已写 {OUT_JSON} (n_done={n_done}, verdict={verdict})")

    # ── 报告 ──
    md = [f"# RD 影子并行 Top2 对比（生产 vs 候选）", "",
          f"生成时间: {payload['generated_at']}  ·  样本日: {n_done}  ·  到期门槛: {REPORT_MIN_DAYS} 天",
          ""]
    vmap = {
        "NO_DATA": "**待启动** — 暂无 shadow 记录",
        "NO_CONCLUSION": f"**累积中** — 到期样本 {n_done} < {REPORT_MIN_DAYS}，继续观察",
        "CAND_BETTER": f"**🟢 候选更优** — {n_done} 天中 {cand_win} 天候选 T+2 跑赢生产，建议人工评审晋升",
        "PROD_BETTER": f"**🔴 生产更优** — {n_done} 天中 {cand_win} 天候选 T+2 跑赢生产，候选不建议晋升",
        "INCONCLUSIVE": f"**🟡 方向不明** — 候选胜率 {cand_win}/{n_done}，继续累积",
    }
    md.append(vmap.get(verdict, ""))
    md.append("")

    # 汇总表
    md += ["## 汇总（T0 收盘买入）", "", "| 组 | 持有期 | 样本 | 平均% | 中位% | 正收益 | 最好% | 最差% |", "|---|---|---|---|---|---|---|---|"]
    for which, label in (("prod", "生产"), ("cand", "候选")):
        for i in (1, 2):
            s = (summary.get(which) or {}).get(str(i))
            if not s:
                continue
            md.append(f"| {label} | T+{i} | {s['n']} | {s['avg_pct']:+.2f} | {s['median_pct']:+.2f} | {s['pos_count']}/{s['n']} | {s['best']:+.2f} | {s['worst']:+.2f} |")
    md += [""]

    # 逐日对比
    if pairs:
        md += ["## 逐日对比（T+2 平均%）", "", "| 选股日 | 生产 avg | 候选 avg | 候选更优? |", "|---|---|---|---|"]
        for p in pairs:
            md.append(f"| {p['date']} | {p['prod_avg_t2']:+.2f} | {p['cand_avg_t2']:+.2f} | {'✅' if p['cand_better'] else '❌'} |")
        md += [""]

    # 明细
    md += ["## 明细", "", "| 选股日 | 组 | 代码 | 名称 | T0收盘 | T+1% | T+2% |", "|---|---|---|---|---|---|---|"]
    for r in rows:
        for which, label in (("prod", "生产"), ("cand", "候选")):
            for p in r[which]:
                def f(v):
                    return "—" if v is None else f"{v:+.2f}"
                md.append(f"| {r['date']} | {label} | {p['symbol']} | {p['name']} | {p.get('t0_close') or '—'} | "
                          f"{f(p.get('rets', {}).get(1))} | {f(p.get('rets', {}).get(2))} |")
    md += ["", "---", "*说明: 涨幅相对选股日 T0 收盘买入; 未到持有期显示 —。生产=09:35 终选, 候选=RD 影子模型(106+10 rd 因子)。同一天多笔记取 09:35 首笔。*"]
    OUT_MD.write_text("\n".join(md), encoding="utf-8")
    log(f"已写 {OUT_MD}")

    # ── 微信推送（企业微信群机器人，每个工作日都推）────────────────
    try:
        from wecom_push import send_markdown

        # 企业微信 markdown 不支持表格/代码块，用文本行直接渲染报告内容。
        # 上限 4096 字节：汇总全推 + 今日明细 + 最近 N 天逐日对比，完整版留在服务器 md。
        vmap_short = {
            "NO_DATA": "**待启动** — 暂无 shadow 记录",
            "NO_CONCLUSION": f"**累积中** — 到期样本 {n_done} < {REPORT_MIN_DAYS}，满 {REPORT_MIN_DAYS} 天下结论",
            "CAND_BETTER": f"**🟢 候选更优** — {n_done} 天中 {cand_win} 天候选跑赢，建议评审晋升",
            "PROD_BETTER": f"**🔴 生产更优** — {n_done} 天中 {cand_win} 天候选跑赢，不建议晋升",
            "INCONCLUSIVE": f"**🟡 方向不明** — 候选胜率 {cand_win}/{n_done}",
        }

        def fmt_pct(v):
            return "—" if v is None else f"{v:+.2f}%"

        push = [f"## RD 影子对比 {datetime.now().strftime('%m-%d')}", ""]
        push.append(vmap_short.get(verdict, ""))
        push.append("")

        # 汇总（T0 收盘买入口径）
        push.append("**汇总（T0 收盘买入）**")
        for which, label in (("prod", "生产"), ("cand", "候选")):
            seg = []
            for i in (1, 2):
                s = (summary.get(which) or {}).get(str(i))
                seg.append(
                    f"T+{i}: {s['avg_pct']:+.2f}% (n={s['n']}, 正{s['pos_count']})"
                    if s else f"T+{i}: —"
                )
            push.append(f"> {label}  " + "   ".join(seg))
        push.append("")

        # 今日对局明细（最近一天，生产 vs 候选）
        if rows:
            r = rows[-1]
            push.append(f"**今日对局（{r['date']}）**")
            for which, label in (("prod", "生产"), ("cand", "候选")):
                for p in r[which]:
                    t0 = p.get("t0_close")
                    push.append(
                        f"> {label} {p['symbol']} {p['name']}  T0收盘={t0 or '—'}  "
                        f"T+1:{fmt_pct(p.get('rets', {}).get(1))}  T+2:{fmt_pct(p.get('rets', {}).get(2))}"
                    )
            push.append("")

        # 逐日对比（T+2 平均%，最近 MAX_PUSH_DAYS 天）
        if pairs:
            push.append("**逐日对比（T+2 平均%）**")
            for p in pairs[-MAX_PUSH_DAYS:]:
                mark = "🟢" if p["cand_better"] else "🔴"
                push.append(
                    f"> {p['date']}  生产 {p['prod_avg_t2']:+.2f}%  vs  候选 {p['cand_avg_t2']:+.2f}%  {mark}"
                )
            push.append("")

        push.append(f"完整报告: {OUT_MD}")
        ok, err = send_markdown("\n".join(push))
        log(f"wecom push: ok={ok} {err}")

        # Excel 文件（与早盘选股 Excel 一样作为附件推送）
        try:
            from wecom_push import send_file

            xlsx = make_shadow_excel(rows, summary, pairs, datetime.now().strftime("%Y-%m-%d"))
            if xlsx:
                ok2, err2 = send_file(xlsx)
                log(f"wecom push excel: ok={ok2} {err2}")
        except Exception as e:
            log(f"wecom push excel skip: {e}")
    except Exception as e:
        log(f"wecom push skip: {e}")

    try:
        import subprocess
        rc_h = subprocess.call(
            [sys.executable, "-u", str(ROOT / "rd_workshop" / "rd_health_check.py")],
            cwd=str(ROOT),
        )
        log(f"rd_health_check rc={rc_h}")
    except Exception as e:
        log(f"rd_health_check skip: {e}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

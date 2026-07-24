#!/usr/bin/env python3
"""板块研报生成器 — 盘中深度版。

照搬 sector_forecast_updated_20260720.md 的报告格式：
以分析文字为主体，每个板块带"为什么强/弱"的推理逻辑、核心驱动、风险点。
图表为辅助。

用法:
  python3 sector_research_report.py --session morning   # 上午收盘(11:35)
  python3 sector_research_report.py --session afternoon  # 下午收盘(15:05)

输出:
  /home/ubuntu/alphapilot/output/sector_research/{date}/{session}/index.html
  /home/ubuntu/alphapilot/output/sector_research/index.html (归档索引)
  同时写入 /home/ubuntu/alphapilot/output/sector_reports/{date}_{session}.json (元数据)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

# ── 路径 ──
ROOT = Path(__file__).resolve().parent
OUT = ROOT / "output"
RESEARCH_OUT = ROOT / "output" / "sector_research"
REPORT_DIR = OUT / "sector_reports"

# ── API ──
API_BASE = "http://127.0.0.1:8000/api/v1/cn"

PERIODS = ["today", "5day", "10day", "20day", "60day"]
PERIOD_LABELS = {
    "today": "今日",
    "5day": "5日",
    "10day": "10日",
    "20day": "20日",
    "60day": "60日",
}

SESSION_LABELS = {
    "morning": "上午盘",
    "afternoon": "下午盘",
}


def fetch_json(url: str, timeout: int = 15) -> dict:
    """从本地API获取JSON"""
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        resp = urllib.request.urlopen(req, timeout=timeout)
        return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"[WARN] fetch {url} failed: {e}", file=sys.stderr)
        return {}


def fetch_index_data() -> dict:
    return fetch_json(f"{API_BASE}/indices", timeout=10)


def fetch_sector_dashboard(period: str) -> dict:
    return fetch_json(f"{API_BASE}/sectors?period={period}", timeout=20)


def fetch_market_overview() -> dict:
    return fetch_json(f"{API_BASE}/market-overview", timeout=10)


def load_wind_board_flow(max_age_hours: float = 36.0) -> dict | None:
    """读取盘后万得板块资金快照（咨询/研报主叙事；不改交易硬门）。"""
    path = ROOT / "data" / "wind_board_flow.json"
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[WARN] wind_board_flow read failed: {e}", file=sys.stderr)
        return None
    if not isinstance(raw, dict):
        return None
    updated = str(raw.get("updated_at") or "")
    if updated and max_age_hours > 0:
        try:
            ts = datetime.strptime(updated[:19], "%Y-%m-%d %H:%M:%S")
            age_h = (datetime.now() - ts).total_seconds() / 3600.0
            if age_h > max_age_hours:
                print(
                    f"[WARN] wind_board_flow stale age={age_h:.1f}h > {max_age_hours}h",
                    file=sys.stderr,
                )
        except ValueError:
            pass
    return raw


def _fmt(v: float) -> str:
    """格式化净额"""
    if v is None:
        return "—"
    return f"{v:+.1f}亿"


def _fmt_wind_row(item: dict) -> str:
    name = item.get("name") or item.get("windcode") or "—"
    days = item.get("consecutive_inflow_days")
    if days is None:
        days = item.get("inflow_days_5d")
    tag = item.get("rotation_tag") or ""
    tag_cn = {
        "fresh_inflow": "新鲜流入",
        "rotation_watch": "轮动观察",
        "rotation_high_risk": "轮动高风险",
        "outflow": "流出",
        "neutral": "",
    }.get(tag, tag)
    days_s = f"·连续流入{days}天" if days is not None else ""
    tag_s = f"·{tag_cn}" if tag_cn else ""
    return f"{name}({_fmt(item.get('main_net'))}{days_s}{tag_s})"


def analyze_sector_rotation(dashboards: dict[str, dict]) -> dict:
    """多周期板块轮动分析"""
    analysis = {
        "strong_sectors": [],
        "weak_sectors": [],
        "improving_sectors": [],
        "deteriorating_sectors": [],
    }

    all_sectors = set()
    for period, data in dashboards.items():
        for ind in data.get("industries", []):
            if ind.get("name"):
                all_sectors.add(ind["name"])

    for name in all_sectors:
        period_data = {}
        for period in PERIODS:
            dash = dashboards.get(period, {})
            for ind in dash.get("industries", []):
                if ind.get("name") == name:
                    period_data[period] = ind
                    break

        statuses = [pd.get("status", "neutral") for pd in period_data.values()]
        nets = {p: pd.get("net_yi", 0) for p, pd in period_data.items()}

        allow_count = statuses.count("allow")
        deny_count = statuses.count("deny")

        if allow_count >= 3:
            analysis["strong_sectors"].append({
                "name": name, "nets": nets,
                "allow_count": allow_count, "deny_count": deny_count,
            })
        elif deny_count >= 3:
            analysis["weak_sectors"].append({
                "name": name, "nets": nets,
                "allow_count": allow_count, "deny_count": deny_count,
            })
        elif allow_count >= 1 and deny_count == 0:
            analysis["improving_sectors"].append({"name": name, "nets": nets})
        elif deny_count >= 1 and allow_count == 0 and "today" in period_data:
            today_net = period_data["today"].get("net_yi", 0)
            if today_net < 0:
                analysis["deteriorating_sectors"].append({"name": name, "nets": nets})

    analysis["strong_sectors"].sort(key=lambda x: x["nets"].get("today", 0), reverse=True)
    analysis["weak_sectors"].sort(key=lambda x: x["nets"].get("today", 0))
    analysis["improving_sectors"].sort(key=lambda x: x["nets"].get("today", 0), reverse=True)
    analysis["deteriorating_sectors"].sort(key=lambda x: x["nets"].get("today", 0))

    return analysis


def generate_forecast(dashboards: dict, indices: dict, rotation: dict) -> dict:
    """生成板块预测"""
    today_dash = dashboards.get("today", {})

    tier1 = []
    tier2 = []
    tier3 = []

    for s in rotation["strong_sectors"]:
        tier1.append({
            "name": s["name"],
            "today_net": s["nets"].get("today", 0),
            "score": s["allow_count"] * 10 + s["nets"].get("today", 0),
        })

    for s in rotation["improving_sectors"]:
        tier2.append({
            "name": s["name"],
            "today_net": s["nets"].get("today", 0),
        })

    for s in rotation["deteriorating_sectors"]:
        tier3.append({
            "name": s["name"],
            "today_net": s["nets"].get("today", 0),
        })

    return {
        "tier1": tier1[:5],
        "tier2": tier2[:5],
        "tier3_watch": tier3[:5],
        "weak": [s["name"] for s in rotation["weak_sectors"][:5]],
    }


# ══════════════════════════════════════════════════════════════
#  分析文字生成 —— 照搬 sector_forecast_updated_20260720.md 格式
# ══════════════════════════════════════════════════════════════

def _sector_detail_html(name: str, nets: dict, allow_count: int, deny_count: int, rank: int = 0) -> str:
    """生成单个板块的分析文字段落（仿照报告里每个板块的格式）"""
    today_v = nets.get("today", 0)
    d5 = nets.get("5day", 0)
    d10 = nets.get("10day", 0)
    d20 = nets.get("20day", 0)
    d60 = nets.get("60day", 0)

    # 判断资金趋势
    trend_parts = []
    if today_v is not None and today_v != 0:
        trend_parts.append(f"今日主力净流入{_fmt(today_v)}")
    if d5 is not None and d5 != 0:
        trend_parts.append(f"5日{_fmt(d5)}")
    if d10 is not None and d10 != 0:
        trend_parts.append(f"10日{_fmt(d10)}")
    if d20 is not None and d20 != 0:
        trend_parts.append(f"20日{_fmt(d20)}")
    if d60 is not None and d60 != 0:
        trend_parts.append(f"60日{_fmt(d60)}")

    trend_text = "，".join(trend_parts) if trend_parts else "数据不足"

    # 多周期一致性判断
    positive_periods = sum(1 for p in [today_v, d5, d10, d20, d60] if p and p > 0)
    negative_periods = sum(1 for p in [today_v, d5, d10, d20, d60] if p and p < 0)

    if positive_periods >= 4:
        consistency = "多周期一致放行，资金持续性强，是当前确定性最高的方向。"
    elif positive_periods >= 3:
        consistency = "多周期偏强，资金有一定持续性。"
    elif negative_periods >= 4:
        consistency = "多周期一致拦截，资金系统性撤退，短期不建议碰。"
    elif negative_periods >= 3:
        consistency = "多周期偏弱，资金持续流出。"
    else:
        consistency = "多周期信号不一致，方向不明确。"

    # 生成HTML
    rank_badge = f'<span class="rank-num">{rank}</span>' if rank else ''
    return f"""<div class="sector-detail">
  <h4>{rank_badge}{name}</h4>
  <p class="sector-data">{trend_text}。{allow_count}个周期放行，{deny_count}个周期拦截。{consistency}</p>
</div>"""


def generate_report_sections(
    date_str: str,
    session: str,
    indices: dict,
    dashboards: dict[str, dict],
    overview: dict,
    rotation: dict,
    forecast: dict,
    wind_flow: dict | None = None,
) -> str:
    """生成完整报告HTML — 照搬 sector_forecast_updated_20260720.md 的结构"""

    session_label = SESSION_LABELS.get(session, session)
    today = dashboards.get("today", {})
    summary = today.get("summary", {})
    idx_data = indices.get("indices", indices.get("data", []))
    wind_consult = (wind_flow or {}).get("consult") if isinstance(wind_flow, dict) else None

    # ── 指数数据 ──
    idx_list = [idx for idx in idx_data if isinstance(idx, dict) and idx.get("name")]

    # ── 板块数据 ──
    top10 = today.get("today_top10", [])
    bottom10 = today.get("today_bottom10", [])
    concept_top = today.get("concept_top10", [])
    watch_list = today.get("analysis", {}).get("watch", [])
    avoid_list = today.get("analysis", {}).get("avoid", [])

    # ── 多周期对比表 ──
    period_comparison = []
    all_names = set()
    for ind in today.get("industries", []):
        if ind.get("name"):
            all_names.add(ind["name"])
    for name in all_names:
        row = {"name": name}
        for period in PERIODS:
            dash = dashboards.get(period, {})
            for ind in dash.get("industries", []):
                if ind.get("name") == name:
                    row[period] = ind.get("net_yi", 0)
                    row[f"{period}_status"] = ind.get("status", "neutral")
                    break
        if any(k in row for k in PERIODS):
            period_comparison.append(row)
    period_comparison.sort(key=lambda x: x.get("today", 0), reverse=True)

    # ── ECharts 数据 ──
    bar_names = [b.get("name", "") for b in top10] + [b.get("name", "") for b in bottom10]
    bar_values = [b.get("net_yi", 0) for b in top10] + [b.get("net_yi", 0) for b in bottom10]
    concept_names = [c.get("name", "") for c in concept_top]
    concept_values = [c.get("net_yi", 0) for c in concept_top]
    heat_sectors = [pc["name"] for pc in period_comparison[:20]]
    heat_periods = [PERIOD_LABELS[p] for p in PERIODS]
    heat_data = []
    for i, pc in enumerate(period_comparison[:20]):
        for j, period in enumerate(PERIODS):
            val = pc.get(period)
            if val is not None:
                heat_data.append([j, i, val])

    chart_json = json.dumps({
        "bar": {"names": bar_names, "values": bar_values},
        "concept": {"names": concept_names, "values": concept_values},
        "heat": {"sectors": heat_sectors, "periods": heat_periods, "data": heat_data},
    }, ensure_ascii=False)

    # ── 1. 市场概览数据 ──
    total_net = summary.get("net_yi", 0)
    allow_count = summary.get("allow", 0)
    deny_count = summary.get("deny", 0)
    up_count = overview.get("up_count", 0)
    down_count = overview.get("down_count", 0)

    # 指数涨跌文字
    idx_parts = []
    for idx in idx_list[:3]:
        chg = idx.get("chg_pct", 0)
        idx_parts.append(f"{idx['name']}{chg:+.2f}%")
    idx_text = "、".join(idx_parts) if idx_parts else "数据待获取"

    # ── 2. 核心判断 ──
    if total_net is not None and total_net > 0:
        headline = f"主力净流入{_fmt(total_net)}，{allow_count}个板块获放行、{deny_count}个被拦截。{idx_text}。资金今日整体偏多，但需关注结构性分化。"
    elif total_net is not None and total_net < 0:
        headline = f"主力净流出{_fmt(total_net)}，{deny_count}个板块被拦截、{allow_count}个获放行。{idx_text}。资金今日整体偏空，防御优先。"
    else:
        headline = f"主力资金基本持平，{idx_text}。市场观望情绪浓厚，板块分化加剧。"

    # ── 3. 资金迁移路径 ──
    inflow_persistent = []
    outflow_persistent = []
    for s in rotation.get("strong_sectors", []):
        nets = s.get("nets", {})
        tv = nets.get("today", 0)
        d5 = nets.get("5day", 0)
        d10 = nets.get("10day", 0)
        if tv is not None and tv > 0 and d5 is not None and d5 > 0 and d10 is not None and d10 > 0:
            inflow_persistent.append(s)
    for s in rotation.get("weak_sectors", []):
        nets = s.get("nets", {})
        tv = nets.get("today", 0)
        d5 = nets.get("5day", 0)
        d10 = nets.get("10day", 0)
        if tv is not None and tv < 0 and d5 is not None and d5 < 0 and d10 is not None and d10 < 0:
            outflow_persistent.append(s)

    migration_parts = []
    if outflow_persistent:
        out_names = "、".join([
            f"{s['name']}(今日{_fmt(s['nets'].get('today',0))}、10日{_fmt(s['nets'].get('10day',0))})"
            for s in outflow_persistent[:3]
        ])
        migration_parts.append(f"多周期持续流出：{out_names}。这些方向资金在系统性撤退。")
    if inflow_persistent:
        in_names = "、".join([
            f"{s['name']}(今日{_fmt(s['nets'].get('today',0))}、10日{_fmt(s['nets'].get('10day',0))})"
            for s in inflow_persistent[:3]
        ])
        migration_parts.append(f"多周期持续流入：{in_names}。资金在这些方向有持续性。")

    if not migration_parts:
        migration_text = "今日板块资金流以脉冲式为主，多周期趋势性信号不明显。"
    else:
        migration_text = " ".join(migration_parts)

    # ── 4. 核心一句话 ──
    if inflow_persistent and outflow_persistent:
        core_sentence = (
            f"资金从{'、'.join([s['name'] for s in outflow_persistent[:2]])}"
            f"迁移到{'、'.join([s['name'] for s in inflow_persistent[:2]])}，"
            f"多周期数据确认这是趋势性轮动而非单日脉冲。"
        )
    elif rotation.get("strong_sectors"):
        core_sentence = f"当前强势方向集中在{'、'.join([s['name'] for s in rotation['strong_sectors'][:3]])}，但需观察资金持续性。"
    else:
        core_sentence = "今日板块信号混乱，建议观望。"

    # ── 5. 板块轮动分析文字 ──
    rotation_parts = []
    if rotation["strong_sectors"]:
        names = "、".join([s["name"] for s in rotation["strong_sectors"][:5]])
        rotation_parts.append(f"多周期强势板块：{names}——这些板块在今日、5日、10日多个周期均获主力放行，是当前资金最一致的方向。")
    if rotation["improving_sectors"]:
        names = "、".join([s["name"] for s in rotation["improving_sectors"][:3]])
        rotation_parts.append(f"改善信号：{names}——从弱势转强，值得跟踪是否形成趋势。")
    if rotation["deteriorating_sectors"]:
        names = "、".join([s["name"] for s in rotation["deteriorating_sectors"][:3]])
        rotation_parts.append(f"恶化信号：{names}——从强势转弱，需警惕格局破坏。")
    if rotation["weak_sectors"]:
        names = "、".join([s["name"] for s in rotation["weak_sectors"][:5]])
        rotation_parts.append(f"多周期弱势板块：{names}——多周期被拦截，短期不建议碰。")
    rotation_text = " ".join(rotation_parts) if rotation_parts else "轮动信号不明显。"

    # ══════════════════════════════════════════════════════════════
    #  构建 HTML
    # ══════════════════════════════════════════════════════════════

    # 用字符串拼接，不走f-string，避免ECharts的{}被转义
    html_parts = []

    # ── HEAD ──
    html_parts.append(f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>板块研报 {date_str} {session_label} | AlphaPilot</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
<style>
  :root {{
    --bg: #F5F5F7;
    --card: #FFFFFF;
    --bg-tertiary: #FAFAFA;
    --border: rgba(0,0,0,0.06);
    --text: #1D1D1F;
    --text-secondary: #3A3A40;
    --text-tertiary: #86868B;
    --purple: #7C5CFC;
    --purple-light: #EDE9FE;
    --red: #FF3B30;
    --green: #34C759;
    --yellow: #FF9500;
    --radius: 16px;
    --shadow: 0 1px 2px rgba(0,0,0,0.04), 0 1px 3px rgba(0,0,0,0.02);
    --font: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: var(--bg); color: var(--text); font-family: var(--font); line-height: 1.6; -webkit-font-smoothing: antialiased; }}
  .container {{ max-width: 1200px; margin: 0 auto; padding: 24px 16px; }}
  .header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; flex-wrap: wrap; gap: 12px; }}
  .header h1 {{ font-size: 28px; font-weight: 700; letter-spacing: -0.02em; }}
  .header .meta {{ font-size: 13px; color: var(--text-tertiary); }}
  .header .badge {{ background: var(--purple); color: white; padding: 4px 14px; border-radius: 20px; font-size: 12px; font-weight: 600; }}

  .section {{ background: var(--card); border: 1px solid var(--border); border-radius: var(--radius); padding: 28px 32px; margin-bottom: 20px; box-shadow: var(--shadow); }}
  .section h2 {{ font-size: 20px; font-weight: 700; margin-bottom: 16px; padding-bottom: 12px; border-bottom: 1px solid var(--border); color: var(--text); }}
  .section h3 {{ font-size: 17px; font-weight: 600; margin: 20px 0 10px; color: var(--text); }}
  .section h4 {{ font-size: 15px; font-weight: 600; margin: 16px 0 6px; color: var(--text-secondary); }}
  .section p {{ font-size: 14px; color: var(--text-secondary); line-height: 1.85; margin-bottom: 10px; }}
  .section .highlight {{ background: var(--purple-light); border-radius: 12px; padding: 14px 18px; margin: 12px 0; }}
  .section .highlight .label {{ font-size: 13px; font-weight: 600; color: var(--purple); margin-bottom: 4px; }}
  .section .highlight .text {{ font-size: 15px; color: var(--text); line-height: 1.6; }}

  .stat-row {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 16px; }}
  .stat {{ text-align: center; padding: 12px; background: var(--bg-tertiary); border-radius: 12px; }}
  .stat .label {{ font-size: 12px; color: var(--text-tertiary); }}
  .stat .value {{ font-size: 22px; font-weight: 700; margin-top: 4px; }}
  .stat .value.red {{ color: var(--red); }}
  .stat .value.green {{ color: var(--green); }}

  table {{ width: 100%; border-collapse: collapse; font-size: 13px; margin: 12px 0; }}
  th, td {{ padding: 8px 12px; text-align: left; border-bottom: 1px solid var(--border); }}
  th {{ color: var(--text-tertiary); font-weight: 500; background: var(--bg-tertiary); }}
  tr:hover td {{ background: var(--bg-tertiary); }}
  td.pos {{ color: var(--red); font-weight: 600; }}
  td.neg {{ color: var(--green); font-weight: 600; }}

  .tier {{ padding: 16px 20px; border-radius: 12px; margin-bottom: 16px; }}
  .tier.t1 {{ background: rgba(52,199,89,0.06); border-left: 4px solid var(--green); }}
  .tier.t2 {{ background: rgba(255,149,0,0.06); border-left: 4px solid var(--yellow); }}
  .tier.t3 {{ background: rgba(255,59,48,0.06); border-left: 4px solid var(--red); }}
  .tier .tier-label {{ font-weight: 700; margin-bottom: 10px; font-size: 15px; }}

  .sector-detail {{ margin-bottom: 14px; }}
  .sector-detail h4 {{ margin-bottom: 4px; }}
  .sector-detail .sector-data {{ font-size: 13px; color: var(--text-secondary); line-height: 1.7; }}
  .rank-num {{ display: inline-block; width: 24px; height: 24px; line-height: 24px; text-align: center; background: var(--purple); color: white; border-radius: 50%; font-size: 12px; margin-right: 8px; }}

  .chart-box {{ width: 100%; height: 400px; margin: 16px 0; }}
  .chart-box-sm {{ width: 100%; height: 300px; margin: 16px 0; }}

  .footer {{ text-align: center; padding: 24px; color: var(--text-tertiary); font-size: 12px; border-top: 1px solid var(--border); margin-top: 24px; }}
  .back-link {{ display: inline-block; margin-bottom: 16px; color: var(--purple); text-decoration: none; font-size: 13px; font-weight: 500; }}
  .back-link:hover {{ text-decoration: underline; }}

  @media (max-width: 640px) {{
    .section {{ padding: 20px 16px; }}
    .stat-row {{ grid-template-columns: 1fr; }}
    .chart-box {{ height: 300px; }}
  }}
</style>
</head>
<body>
<div class="container">

<a href="/cn" class="back-link">← 返回工作台</a>

<div class="header">
  <div>
    <h1>板块研报 · {session_label}</h1>
    <div class="meta">{date_str} | 数据源：通达信 + 万得行业流（咨询） | 生成于 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
  </div>
  <span class="badge">{session_label}</span>
</div>
""")

    # ── 〇、万得行业资金主叙事（咨询轨）──
    if wind_consult:
        sentiment = wind_consult.get("all_a_sentiment") or {}
        tone = sentiment.get("tone") or "—"
        tone_cn = {"risk_on": "偏多", "mixed": "分化", "risk_off": "偏空"}.get(tone, tone)
        top_in = wind_consult.get("industry_top_inflow") or []
        top_out = wind_consult.get("industry_top_outflow") or []
        prefer = wind_consult.get("prefer") or []
        avoid = wind_consult.get("avoid") or []
        rot_watch = wind_consult.get("rotation_watch") or []
        wind_asof = (wind_flow or {}).get("asof") or date_str
        html_parts.append(f"""
<div class="section">
  <h2>〇、万得行业资金（咨询主叙事）</h2>
  <p>用途：早报/午评/板块解释。交易硬门仍走通达信资金门，本段不直接下单。</p>
  <p>快照日 {wind_asof}。全A情绪：<strong>{tone_cn}</strong>
    （主力{_fmt(sentiment.get('main_net'))} /
     机构{_fmt(sentiment.get('inst_net'))} /
     大户{_fmt(sentiment.get('large_net'))} /
     散户{_fmt(sentiment.get('retail_net'))}）。</p>
""")
        if top_in:
            html_parts.append(
                "  <h3>行业流入 Top</h3>\n  <p>"
                + "；".join(_fmt_wind_row(x) for x in top_in[:8])
                + "</p>\n"
            )
        if top_out:
            html_parts.append(
                "  <h3>行业流出 Top</h3>\n  <p>"
                + "；".join(_fmt_wind_row(x) for x in top_out[:8])
                + "</p>\n"
            )
        html_parts.append(
            "  <div class=\"highlight\">"
            f"<div class=\"label\">动态因子 · 轮动</div>"
            f"<div class=\"text\">新鲜偏好：{'、'.join(prefer[:8]) or '—'}。"
            f"连续流入观察（约3–4日易轮换）：{'、'.join(rot_watch[:8]) or '—'}。"
            f"当日流出：{'、'.join(avoid[:8]) or '—'}。</div></div>\n"
        )
        html_parts.append("</div>\n")

    # ── 一、数据基础 & 市场概览 ──
    html_parts.append(f"""
<div class="section">
  <h2>一、数据基础 & 市场概览</h2>
  <p>数据来源：通达信THS行业指数多周期快照（今日/5日/10日/20日/60日）、主力资金净流入数据、市场概览；万得行业流见「〇」节。</p>

  <div class="stat-row">
    <div class="stat">
      <div class="label">上涨 / 下跌</div>
      <div class="value"><span class="{'red' if up_count >= down_count else 'green'}">{up_count}</span> / <span class="{'green' if down_count > up_count else 'red'}">{down_count}</span></div>
    </div>
    <div class="stat">
      <div class="label">主力净流入</div>
      <div class="value {'red' if (total_net or 0) > 0 else 'green'}">{_fmt(total_net)}</div>
    </div>
    <div class="stat">
      <div class="label">放行 / 拦截板块</div>
      <div class="value">{allow_count} / {deny_count}</div>
    </div>
  </div>

  <h3>三大指数</h3>
  <div class="stat-row">
""")

    for idx in idx_list[:3]:
        chg = idx.get("chg_pct", 0)
        chg_cls = "red" if chg > 0 else "green" if chg < 0 else ""
        html_parts.append(f"""    <div class="stat">
      <div class="label">{idx.get('name', '')}</div>
      <div class="value {chg_cls}">{idx.get('price', 0):.2f}</div>
      <div class="{chg_cls}" style="font-size:14px;">{chg:+.2f}%</div>
    </div>
""")

    html_parts.append("""  </div>
</div>
""")

    # ── 二、核心判断 ──
    html_parts.append(f"""
<div class="section">
  <h2>二、核心判断</h2>
  <p style="font-size:16px; font-weight:600; color:var(--text); line-height:1.8;">{headline}</p>
  <div class="highlight">
    <div class="label">💡 核心一句话</div>
    <div class="text">{core_sentence}</div>
  </div>
</div>
""")

    # ── 三、资金迁移路径 ──
    html_parts.append(f"""
<div class="section">
  <h2>三、资金迁移路径</h2>
  <p>{migration_text}</p>
""")

    # 资金流出Top 5表格
    if outflow_persistent:
        html_parts.append("""  <h3>持续流出板块（5日+10日+今日均为负）</h3>
  <table>
    <thead><tr><th>板块</th><th>今日(亿)</th><th>5日(亿)</th><th>10日(亿)</th><th>20日(亿)</th><th>60日(亿)</th></tr></thead>
    <tbody>
""")
        for s in outflow_persistent[:5]:
            nets = s.get("nets", {})
            html_parts.append(f"""      <tr><td>{s['name']}</td><td class="neg">{_fmt(nets.get('today',0))}</td><td class="neg">{_fmt(nets.get('5day',0))}</td><td class="neg">{_fmt(nets.get('10day',0))}</td><td>{_fmt(nets.get('20day',0))}</td><td>{_fmt(nets.get('60day',0))}</td></tr>
""")
        html_parts.append("""    </tbody>
  </table>
""")

    # 资金流入Top 5表格
    if inflow_persistent:
        html_parts.append("""  <h3>持续流入板块（5日+10日+今日均为正）</h3>
  <table>
    <thead><tr><th>板块</th><th>今日(亿)</th><th>5日(亿)</th><th>10日(亿)</th><th>20日(亿)</th><th>60日(亿)</th></tr></thead>
    <tbody>
""")
        for s in inflow_persistent[:5]:
            nets = s.get("nets", {})
            html_parts.append(f"""      <tr><td>{s['name']}</td><td class="pos">{_fmt(nets.get('today',0))}</td><td class="pos">{_fmt(nets.get('5day',0))}</td><td class="pos">{_fmt(nets.get('10day',0))}</td><td>{_fmt(nets.get('20day',0))}</td><td>{_fmt(nets.get('60day',0))}</td></tr>
""")
        html_parts.append("""    </tbody>
  </table>
""")

    html_parts.append("</div>\n")

    # ── 四、板块轮动分析 ──
    html_parts.append(f"""
<div class="section">
  <h2>四、板块轮动分析</h2>
  <p>{rotation_text}</p>
""")

    # 板块轮动分类
    html_parts.append("""  <h3>板块轮动分类</h3>
""")

    # 强势
    if rotation["strong_sectors"]:
        html_parts.append("""  <div class="tier t1">
    <div class="tier-label" style="color:var(--green);">⬆ 多周期强势</div>
""")
        for i, s in enumerate(rotation["strong_sectors"][:5]):
            nets = s.get("nets", {})
            html_parts.append(_sector_detail_html(s["name"], nets, s.get("allow_count", 0), s.get("deny_count", 0), i + 1))
        html_parts.append("  </div>\n")

    # 改善
    if rotation["improving_sectors"]:
        html_parts.append("""  <div class="tier t2">
    <div class="tier-label" style="color:var(--yellow);">↗ 改善信号</div>
""")
        for s in rotation["improving_sectors"][:5]:
            nets = s.get("nets", {})
            html_parts.append(_sector_detail_html(s["name"], nets, 0, 0))
        html_parts.append("  </div>\n")

    # 恶化
    if rotation["deteriorating_sectors"]:
        html_parts.append("""  <div class="tier t3">
    <div class="tier-label" style="color:var(--red);">↘ 恶化信号</div>
""")
        for s in rotation["deteriorating_sectors"][:5]:
            nets = s.get("nets", {})
            html_parts.append(_sector_detail_html(s["name"], nets, 0, 0))
        html_parts.append("  </div>\n")

    # 弱势
    if rotation["weak_sectors"]:
        html_parts.append("""  <div class="tier t3">
    <div class="tier-label" style="color:var(--green);">⬇ 多周期弱势</div>
""")
        for s in rotation["weak_sectors"][:5]:
            nets = s.get("nets", {})
            html_parts.append(_sector_detail_html(s["name"], nets, s.get("allow_count", 0), s.get("deny_count", 0)))
        html_parts.append("  </div>\n")

    html_parts.append("</div>\n")

    # ── 五、多周期资金流对比表 ──
    html_parts.append("""<div class="section">
  <h2>五、多周期资金流对比（全行业）</h2>
  <div style="overflow-x:auto;">
  <table>
    <thead>
      <tr>
        <th>板块</th>
        <th>今日(亿)</th>
        <th>5日(亿)</th>
        <th>10日(亿)</th>
        <th>20日(亿)</th>
        <th>60日(亿)</th>
        <th>状态</th>
      </tr>
    </thead>
    <tbody>
""")
    for pc in period_comparison:
        tv = pc.get("today", 0)
        tv_cls = "pos" if (tv and tv > 0) else "neg" if (tv and tv < 0) else ""
        status = pc.get("today_status", "neutral")
        if status == "allow":
            status_html = '<span style="color:var(--green);font-weight:600;">✓ 放行</span>'
        elif status == "deny":
            status_html = '<span style="color:var(--red);font-weight:600;">✗ 拦截</span>'
        else:
            status_html = '<span style="color:var(--text-tertiary);">— 中性</span>'

        html_parts.append(f"""      <tr>
        <td>{pc['name']}</td>
        <td class="{tv_cls}">{_fmt(tv)}</td>
        <td>{_fmt(pc.get('5day'))}</td>
        <td>{_fmt(pc.get('10day'))}</td>
        <td>{_fmt(pc.get('20day'))}</td>
        <td>{_fmt(pc.get('60day'))}</td>
        <td>{status_html}</td>
      </tr>
""")

    html_parts.append("""    </tbody>
  </table>
  </div>
</div>
""")

    # ── 六、图表 ──
    html_parts.append("""<div class="section">
  <h2>六、资金流图表</h2>

  <h3>板块资金流排行（Top10 + Bottom10）</h3>
  <div id="chart-bar" class="chart-box"></div>

  <h3>多周期板块轮动热力图</h3>
  <div id="chart-heat" class="chart-box"></div>

  <h3>概念板块资金流 Top10</h3>
  <div id="chart-concept" class="chart-box-sm"></div>
</div>
""")

    # ── 七、板块强势预测 ──
    html_parts.append("""<div class="section">
  <h2>七、板块强势预测</h2>
""")

    # 第一梯队
    html_parts.append("""  <div class="tier t1">
    <div class="tier-label" style="color:var(--green);">⭐ 第一梯队：高确定性强势</div>
""")
    for i, s in enumerate(forecast.get("tier1", [])):
        name = s["name"]
        today_net = s.get("today_net", 0)
        # 找rotation数据
        rot_data = None
        for r in rotation.get("strong_sectors", []):
            if r["name"] == name:
                rot_data = r
                break
        if rot_data:
            nets = rot_data["nets"]
            d20 = nets.get("20day", 0)
            d60 = nets.get("60day", 0)
            html_parts.append(f"""    <div class="sector-detail">
      <h4><span class="rank-num">{i+1}</span>{name}</h4>
      <p class="sector-data">今日主力净流入{_fmt(today_net)}，20日{_fmt(d20)}，60日{_fmt(d60)}。多周期一致放行，资金持续性强，是当前确定性最高的方向。</p>
    </div>
""")
        else:
            html_parts.append(f"""    <div class="sector-detail">
      <h4><span class="rank-num">{i+1}</span>{name}</h4>
      <p class="sector-data">今日主力净流入{_fmt(today_net)}，多周期强势。</p>
    </div>
""")
    if not forecast.get("tier1"):
        html_parts.append("    <p>暂无</p>\n")
    html_parts.append("  </div>\n")

    # 第二梯队
    html_parts.append("""  <div class="tier t2">
    <div class="tier-label" style="color:var(--yellow);">⭐ 第二梯队：改善中</div>
""")
    for s in forecast.get("tier2", []):
        name = s["name"]
        today_net = s.get("today_net", 0)
        html_parts.append(f"""    <div class="sector-detail">
      <h4>{name}</h4>
      <p class="sector-data">今日主力净流入{_fmt(today_net)}，出现改善信号但持续性待验证。</p>
    </div>
""")
    if not forecast.get("tier2"):
        html_parts.append("    <p>暂无</p>\n")
    html_parts.append("  </div>\n")

    # 第三梯队
    weak_names = forecast.get("weak", [])
    html_parts.append(f"""  <div class="tier t3">
    <div class="tier-label" style="color:var(--red);">⚠ 观望/回避</div>
    <p class="sector-data">{'、'.join(weak_names[:5]) if weak_names else '暂无'}</p>
  </div>
""")

    html_parts.append("</div>\n")

    # ── 八、今日关注 vs 回避 ──
    html_parts.append("""<div class="section">
  <h2>八、今日关注 vs 回避</h2>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;">
    <div>
      <h3 style="color:var(--red);">关注</h3>
      <table>
        <thead><tr><th>板块</th><th>净流入(亿)</th></tr></thead>
        <tbody>
""")
    for w in watch_list:
        html_parts.append(f"""          <tr><td>{w.get('name','')}</td><td class="pos">{w.get('net_yi',0):+.1f}</td></tr>
""")
    html_parts.append("""        </tbody>
      </table>
    </div>
    <div>
      <h3 style="color:var(--green);">回避</h3>
      <table>
        <thead><tr><th>板块</th><th>净流出(亿)</th></tr></thead>
        <tbody>
""")
    for a in avoid_list:
        html_parts.append(f"""          <tr><td>{a.get('name','')}</td><td class="neg">{a.get('net_yi',0):+.1f}</td></tr>
""")
    html_parts.append("""        </tbody>
      </table>
    </div>
  </div>
</div>
""")

    # ── Footer ──
    html_parts.append(f"""
<div class="footer">
  <p>通达信板块资金仅供研究，非投资建议</p>
  <p>本内容仅为信息整理与分析参考，不构成投资建议，投资有风险，决策需谨慎。</p>
  <p>AlphaPilot · {date_str} {session_label} · 自动生成</p>
</div>

</div>
""")

    # ── ECharts JS（用字符串拼接，不走f-string）──
    js_parts = []
    js_parts.append('<script>\n')
    js_parts.append('var chartData = ' + chart_json + ';\n\n')

    # 柱状图
    js_parts.append("""// 1. 板块资金流柱状图
var barChart = echarts.init(document.getElementById('chart-bar'));
barChart.setOption({
  backgroundColor: 'transparent',
  tooltip: { trigger: 'axis', formatter: '{b}<br/>{c}亿', backgroundColor: '#fff', borderColor: 'rgba(0,0,0,0.08)', textStyle: { color: '#1D1D1F' } },
  grid: { left: '3%', right: '4%', bottom: '15%', containLabel: true },
  xAxis: {
    type: 'category',
    data: chartData.bar.names,
    axisLabel: { rotate: 45, fontSize: 11, color: '#86868B' },
    axisLine: { lineStyle: { color: 'rgba(0,0,0,0.06)' } },
  },
  yAxis: {
    type: 'value',
    name: '净额(亿)',
    axisLabel: { color: '#86868B' },
    splitLine: { lineStyle: { color: 'rgba(0,0,0,0.06)' } },
  },
  series: [{
    type: 'bar',
    data: chartData.bar.values.map(function(v) { return { value: v, itemStyle: { color: v > 0 ? '#FF3B30' : '#34C759' } }; }),
    label: { show: true, position: 'top', formatter: '{c}', fontSize: 10, color: '#86868B' },
  }],
});

""")

    # 热力图
    js_parts.append("""// 2. 热力图
var heatChart = echarts.init(document.getElementById('chart-heat'));
heatChart.setOption({
  backgroundColor: 'transparent',
  tooltip: {
    position: 'top',
    formatter: function(params) {
      return chartData.heat.sectors[params.value[1]] + ' ' + chartData.heat.periods[params.value[0]] + '<br/>' + params.value[2].toFixed(1) + '亿';
    },
    backgroundColor: '#fff',
    borderColor: 'rgba(0,0,0,0.08)',
    textStyle: { color: '#1D1D1F' },
  },
  grid: { left: '15%', right: '5%', bottom: '20%', top: '5%' },
  xAxis: {
    type: 'category',
    data: chartData.heat.periods,
    splitArea: { show: true, areaStyle: { color: ['rgba(0,0,0,0.02)', 'transparent'] } },
    axisLabel: { color: '#86868B' },
  },
  yAxis: {
    type: 'category',
    data: chartData.heat.sectors,
    splitArea: { show: true, areaStyle: { color: ['rgba(0,0,0,0.02)', 'transparent'] } },
    axisLabel: { color: '#3A3A40', fontSize: 11 },
  },
  visualMap: {
    min: -500,
    max: 50,
    calculable: true,
    orient: 'horizontal',
    left: 'center',
    bottom: '2%',
    textStyle: { color: '#86868B' },
    inRange: { color: ['#34C759', '#F5F5F7', '#FF3B30'] },
  },
  series: [{
    type: 'heatmap',
    data: chartData.heat.data,
    label: { show: true, formatter: function(params) { return params.value[2].toFixed(0); }, fontSize: 10, color: '#1D1D1F' },
    emphasis: { itemStyle: { shadowBlur: 6, shadowColor: 'rgba(0,0,0,0.15)' } },
  }],
});

""")

    # 概念板块
    js_parts.append("""// 3. 概念板块
var conceptChart = echarts.init(document.getElementById('chart-concept'));
conceptChart.setOption({
  backgroundColor: 'transparent',
  tooltip: { trigger: 'axis', formatter: '{b}<br/>{c}亿', backgroundColor: '#fff', borderColor: 'rgba(0,0,0,0.08)', textStyle: { color: '#1D1D1F' } },
  grid: { left: '3%', right: '4%', bottom: '15%', containLabel: true },
  xAxis: {
    type: 'category',
    data: chartData.concept.names,
    axisLabel: { rotate: 30, fontSize: 11, color: '#86868B' },
    axisLine: { lineStyle: { color: 'rgba(0,0,0,0.06)' } },
  },
  yAxis: {
    type: 'value',
    name: '净额(亿)',
    axisLabel: { color: '#86868B' },
    splitLine: { lineStyle: { color: 'rgba(0,0,0,0.06)' } },
  },
  series: [{
    type: 'bar',
    data: chartData.concept.values.map(function(v) { return { value: v, itemStyle: { color: v > 0 ? '#FF3B30' : '#34C759' } }; }),
    label: { show: true, position: 'top', formatter: '{c}', fontSize: 10, color: '#86868B' },
  }],
});

// 响应式
window.addEventListener('resize', function() {
  barChart.resize();
  heatChart.resize();
  conceptChart.resize();
});
""")

    js_parts.append('\n</script>\n')
    js_parts.append('</body>\n</html>')

    html_parts.extend(js_parts)
    return "".join(html_parts)


def build_html(
    date_str: str,
    session: str,
    indices: dict,
    dashboards: dict[str, dict],
    overview: dict,
    rotation: dict,
    forecast: dict,
    wind_flow: dict | None = None,
) -> str:
    """构建HTML研报"""
    return generate_report_sections(
        date_str,
        session,
        indices,
        dashboards,
        overview,
        rotation,
        forecast,
        wind_flow=wind_flow,
    )


def main():
    parser = argparse.ArgumentParser(description="板块研报生成器")
    parser.add_argument("--session", choices=["morning", "afternoon"], required=True, help="盘次")
    parser.add_argument("--date", type=str, default=None, help="日期 YYYY-MM-DD（默认今天）")
    args = parser.parse_args()

    date_str = args.date or datetime.now().strftime("%Y-%m-%d")
    session = args.session

    print(f"[INFO] 生成板块研报 {date_str} {session}")

    print("[1/5] 获取指数数据...")
    indices = fetch_index_data()

    print("[2/5] 获取市场概览...")
    overview = fetch_market_overview()

    print("[3/5] 获取多周期板块数据...")
    dashboards = {}
    for period in PERIODS:
        print(f"  - {period}...")
        dashboards[period] = fetch_sector_dashboard(period)
        if dashboards[period]:
            print(f"    ✓ {dashboards[period].get('summary', {}).get('sector_count', 0)} 个板块")
        else:
            print(f"    ✗ 获取失败")

    print("[4/5] 板块轮动分析...")
    rotation = analyze_sector_rotation(dashboards)
    print(f"  强势: {len(rotation['strong_sectors'])} | 弱势: {len(rotation['weak_sectors'])} | 改善: {len(rotation['improving_sectors'])} | 恶化: {len(rotation['deteriorating_sectors'])}")

    print("[5/5] 生成预测...")
    forecast = generate_forecast(dashboards, indices, rotation)

    wind_flow = load_wind_board_flow()
    if wind_flow:
        c = wind_flow.get("consult") or {}
        print(
            f"[OK] 万得板块资金 asof={wind_flow.get('asof')} "
            f"prefer={len(c.get('prefer') or [])} "
            f"rotation_watch={len(c.get('rotation_watch') or [])}",
            flush=True,
        )
    else:
        print("[WARN] 无 wind_board_flow.json，研报跳过万得主叙事", flush=True)

    html = build_html(
        date_str, session, indices, dashboards, overview, rotation, forecast, wind_flow=wind_flow
    )

    report_path = RESEARCH_OUT / date_str / session / "index.html"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(html, encoding="utf-8")
    print(f"\n[OK] 研报已生成: {report_path}")
    print(f"[OK] 访问地址: https://alphapilot.api-tokenmaster.com/cn/sectors/research/{date_str}/{session}/")

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    meta = {
        "date": date_str,
        "session": session,
        "generated_at": datetime.now().isoformat(),
        "report_path": str(report_path),
        "url": f"https://alphapilot.api-tokenmaster.com/cn/sectors/research/{date_str}/{session}/",
        "indices_count": len(indices.get("indices", indices.get("data", []))),
        "sector_count": dashboards.get("today", {}).get("summary", {}).get("sector_count", 0),
        "strong_count": len(rotation["strong_sectors"]),
        "weak_count": len(rotation["weak_sectors"]),
    }
    meta_path = REPORT_DIR / f"{date_str.replace('-', '')}_{session}.json"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] 元数据: {meta_path}")

    # 同步写出晨间选股用的 prefer/avoid（与 HTML 同源）
    try:
        from scripts.build_sector_research_bias import build_bias_payload, write_bias

        bias = build_bias_payload(
            dashboards, session=session, date_str=date_str, wind_flow=wind_flow
        )
        bias_path = write_bias(bias)
        print(
            f"[OK] 选股偏好 bias: {bias_path} "
            f"prefer={bias.get('prefer')[:5]} avoid={bias.get('avoid')[:5]} "
            f"wind_prefer={bias.get('wind_prefer', [])[:5]} "
            f"rotation_watch={bias.get('rotation_watch', [])[:5]}",
            flush=True,
        )
    except Exception as e:
        print(f"[WARN] bias 写出失败（晨间可 08:50 补刷）: {e}", flush=True)

    generate_date_index()
    return 0


def generate_date_index():
    """生成研报日期索引页"""
    research_dir = RESEARCH_OUT
    if not research_dir.exists():
        return

    dates = []
    for d in sorted(research_dir.iterdir(), reverse=True):
        if d.is_dir():
            sessions = []
            for s in ["morning", "afternoon"]:
                if (d / s / "index.html").exists():
                    sessions.append(s)
            if sessions:
                dates.append({"date": d.name, "sessions": sessions})

    html = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>板块研报归档 | AlphaPilot</title>
<style>
  :root {
    --bg: #F5F5F7; --card: #FFFFFF; --border: rgba(0,0,0,0.06);
    --text: #1D1D1F; --secondary: #86868B; --tertiary: #3A3A40;
    --purple: #7C5CFC; --purple-light: #EDE9FE;
    --shadow: 0 1px 2px rgba(0,0,0,0.04), 0 1px 3px rgba(0,0,0,0.02);
    --font: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: var(--bg); color: var(--text); font-family: var(--font); -webkit-font-smoothing: antialiased; }
  .container { max-width: 800px; margin: 0 auto; padding: 40px 16px; }
  h1 { font-size: 26px; font-weight: 700; letter-spacing: -0.02em; margin-bottom: 8px; }
  .subtitle { color: var(--secondary); font-size: 14px; margin-bottom: 24px; }
  .back { color: var(--purple); text-decoration: none; font-size: 13px; font-weight: 500; display: inline-block; margin-bottom: 16px; }
  .back:hover { text-decoration: underline; }
  .date-item { background: var(--card); border: 1px solid var(--border); border-radius: 16px; padding: 16px 20px; margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center; box-shadow: var(--shadow); }
  .date-item .date { font-size: 18px; font-weight: 600; }
  .date-item .sessions { display: flex; gap: 8px; }
  .date-item a { color: var(--purple); text-decoration: none; padding: 6px 16px; border: 1px solid var(--purple); border-radius: 20px; font-size: 13px; font-weight: 500; transition: all 0.15s; }
  .date-item a:hover { background: var(--purple-light); }
  .footer { text-align: center; padding: 24px; color: var(--secondary); font-size: 12px; }
</style>
</head>
<body>
<div class="container">
  <a href="/cn" class="back">← 返回工作台</a>
  <h1>板块研报归档</h1>
  <p class="subtitle">按日期归档的盘中板块深度研报</p>
"""
    for d in dates:
        html += f"""  <div class="date-item">
    <span class="date">{d['date']}</span>
    <div class="sessions">
"""
        for s in d["sessions"]:
            label = "上午盘" if s == "morning" else "下午盘"
            html += f'      <a href="{d["date"]}/{s}/">{label}</a>\n'
        html += "    </div>\n  </div>\n"

    html += """  <div class="footer">
    <p>通达信板块资金仅供研究，非投资建议</p>
    <p>AlphaPilot · 自动生成</p>
  </div>
</div>
</body>
</html>"""

    index_path = research_dir / "index.html"
    index_path.write_text(html, encoding="utf-8")
    print(f"[OK] 索引页已更新: {index_path}")


if __name__ == "__main__":
    sys.exit(main())

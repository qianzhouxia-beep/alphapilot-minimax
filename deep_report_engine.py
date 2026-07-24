#!/usr/bin/env python3
"""
AlphaPilot 深度研报引擎
- 优先：TradingAgents（若已安装）
- 回退：DeepSeek 多角色结构化研报 + 本地 A 股行情/资金上下文

目标产品形态：输入股票代码 → 输出「值不值得买」的详细报告（非闲聊）。
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib import request as urlrequest

ROOT = Path(__file__).resolve().parent
JOB_DIR = ROOT / "output" / "deep_reports"
JOB_DIR.mkdir(parents=True, exist_ok=True)

DEEPSEEK_URL = os.getenv("DEEPSEEK_API_URL", "https://api.deepseek.com/v1/chat/completions")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")


def _load_llm_key() -> str:
    """优先环境变量，其次本地 .env / .secrets（均不入库）。"""
    for k in ("DEEPSEEK_API_KEY", "OPENAI_API_KEY"):
        v = os.getenv(k)
        if v:
            return v.strip()
    for path in (ROOT / ".env", ROOT / ".secrets" / "deepseek_key"):
        try:
            if not path.exists():
                continue
            text = path.read_text(encoding="utf-8").strip()
            if path.name == "deepseek_key":
                return text.splitlines()[0].strip()
            for line in text.splitlines():
                if line.startswith("DEEPSEEK_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
                if line.startswith("OPENAI_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
        except Exception:
            continue
    # 与 pipeline 共用同一 DeepSeek 配置（若已存在）
    try:
        from alphapilot_pipeline_v3 import LLM_KEY  # type: ignore

        if LLM_KEY:
            return str(LLM_KEY).strip()
    except Exception:
        pass
    return ""


def to_yf_ticker(symbol: str) -> str:
    """A 股代码 → Yahoo Finance ticker。600519 → 600519.SS；000524 → 000524.SZ"""
    s = re.sub(r"^(sh|sz)", "", str(symbol).strip().lower())
    s = re.sub(r"[^0-9]", "", s)
    if len(s) != 6:
        raise ValueError(f"无效股票代码: {symbol}")
    if s.startswith(("5", "6", "9")):
        return f"{s}.SS"
    return f"{s}.SZ"


def normalize_symbol(symbol: str) -> str:
    s = re.sub(r"^(sh|sz)", "", str(symbol).strip().lower())
    s = re.sub(r"[^0-9]", "", s)
    if len(s) != 6:
        raise ValueError(f"无效股票代码: {symbol}")
    return s


def _job_path(job_id: str) -> Path:
    return JOB_DIR / f"{job_id}.json"


def _save_job(job: dict) -> None:
    p = _job_path(job["job_id"])
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)


def get_job(job_id: str) -> Optional[dict]:
    p = _job_path(job_id)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def list_recent_jobs(limit: int = 20) -> list:
    files = sorted(JOB_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)
    out = []
    for f in files[:limit]:
        try:
            j = json.loads(f.read_text(encoding="utf-8"))
            out.append(
                {
                    "job_id": j.get("job_id"),
                    "symbol": j.get("symbol"),
                    "name": j.get("name"),
                    "status": j.get("status"),
                    "decision": j.get("decision"),
                    "created_at": j.get("created_at"),
                    "finished_at": j.get("finished_at"),
                    "engine": j.get("engine"),
                }
            )
        except Exception:
            continue
    return out


def _lookup_name(symbol: str) -> str:
    """尽力从本地推荐缓存 / 拼音搜索取中文名。"""
    for path in (
        ROOT / "output" / "daily_recommend.json",
        ROOT / "recommend_cache.json",
    ):
        try:
            if not path.exists():
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
            items = data.get("recommendations") or data.get("items") or []
            for it in items:
                sym = str(it.get("symbol", "")).replace("sh", "").replace("sz", "")
                if sym.endswith(symbol) or sym == symbol:
                    return it.get("name") or symbol
        except Exception:
            continue
    try:
        from api_server import search_stocks_pinyin  # type: ignore

        hits = search_stocks_pinyin(symbol) or []
        for h in hits:
            sym = re.sub(r"^(sh|sz)", "", str(h.get("symbol", "")).lower())
            if sym == symbol and h.get("name"):
                return str(h["name"])
    except Exception:
        pass
    return symbol


def _gather_local_context(symbol: str) -> dict:
    """收集本地上下文，供 LLM 研报使用（不依赖 Yahoo）。"""
    ctx: dict[str, Any] = {"symbol": symbol, "as_of": datetime.now().strftime("%Y-%m-%d")}
    try:
        from money_flow_gate import apply_money_flow_gate  # type: ignore

        # 轻量：从 recommend 缓存找该票
        for path in (ROOT / "output" / "daily_recommend.json", ROOT / "recommend_cache.json"):
            if not path.exists():
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
            for it in data.get("recommendations") or data.get("items") or []:
                sym = str(it.get("symbol", "")).replace("sh", "").replace("sz", "")
                if sym.endswith(symbol):
                    ctx["pipeline_hit"] = {
                        k: it.get(k)
                        for k in (
                            "name",
                            "score",
                            "money_phase",
                            "money_phase_label",
                            "active_buy_ratio",
                            "volume_ratio",
                            "turnover",
                            "change_pct",
                            "buy_price",
                            "industry_code",
                        )
                    }
                    break
    except Exception as e:
        ctx["pipeline_error"] = str(e)

    # 实时报价（若 api 同进程已有）
    try:
        import api_server  # type: ignore

        q = api_server._get_live_quote(symbol)
        if q:
            ctx["live_quote"] = q
    except Exception:
        pass

    return ctx


def _deepseek_chat(system: str, user: str, temperature: float = 0.3) -> str:
    api_key = _load_llm_key()
    if not api_key:
        raise RuntimeError("未配置 DEEPSEEK_API_KEY / OPENAI_API_KEY，无法生成研报")
    payload = {
        "model": DEEPSEEK_MODEL,
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    req = urlrequest.Request(
        DEEPSEEK_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    with urlrequest.urlopen(req, timeout=180) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"]


def _extract_decision(text: str) -> str:
    m = re.search(r"(强烈建议买入|建议买入|谨慎买入|观望|建议减持|建议卖出|不建议买入)", text)
    if m:
        return m.group(1)
    if re.search(r"不值得买|不宜买入|回避", text):
        return "不建议买入"
    if re.search(r"值得关注|可以买入|建议买入", text):
        return "建议买入"
    return "观望"


def run_tradingagents(symbol: str, trade_date: Optional[str] = None) -> dict:
    """调用官方 TradingAgents（需已 pip install）。"""
    from tradingagents.graph.trading_graph import TradingAgentsGraph  # type: ignore
    from tradingagents.default_config import DEFAULT_CONFIG  # type: ignore

    yf = to_yf_ticker(symbol)
    date = trade_date or datetime.now().strftime("%Y-%m-%d")
    config = DEFAULT_CONFIG.copy()
    config["llm_provider"] = os.getenv("TRADINGAGENTS_LLM_PROVIDER", "deepseek")
    config["deep_think_llm"] = os.getenv("TRADINGAGENTS_DEEP_THINK_LLM", "deepseek-chat")
    config["quick_think_llm"] = os.getenv("TRADINGAGENTS_QUICK_THINK_LLM", "deepseek-chat")
    config["max_debate_rounds"] = int(os.getenv("TRADINGAGENTS_MAX_DEBATE_ROUNDS", "1"))
    config["max_risk_discuss_rounds"] = int(os.getenv("TRADINGAGENTS_MAX_RISK_ROUNDS", "1"))
    config["output_language"] = "Chinese"

    ta = TradingAgentsGraph(debug=False, config=config)
    final_state, decision = ta.propagate(yf, date)

    # 尽量拼出可读报告
    sections = []
    if isinstance(final_state, dict):
        for key in (
            "market_report",
            "sentiment_report",
            "news_report",
            "fundamentals_report",
            "investment_plan",
            "trader_investment_plan",
            "final_trade_decision",
        ):
            val = final_state.get(key)
            if val:
                sections.append(f"## {key}\n\n{val}")
    report = "\n\n".join(sections) if sections else str(final_state)
    decision_text = decision if isinstance(decision, str) else json.dumps(decision, ensure_ascii=False)
    full = f"{report}\n\n---\n\n## 最终决策\n\n{decision_text}"
    return {
        "engine": "tradingagents",
        "yf_ticker": yf,
        "trade_date": date,
        "decision": _extract_decision(full + "\n" + decision_text),
        "report_markdown": full,
        "raw_decision": decision_text,
    }


def run_deepseek_report(symbol: str, name: str, ctx: dict) -> dict:
    """确定 Agent：多角色结构化中文研报 + 本地 A 股上下文。"""
    system = (
        "你是 AlphaPilot「确定 Agent」买方投研协作系统，需要为 A 股个股出具详细研究报告。"
        "角色包括：基本面分析师、技术分析师、资金面分析师、多头研究员、空头研究员、风控官、投资经理。"
        "必须用简体中文 Markdown 输出，结构完整、论据具体，禁止空话套话。"
        "最后必须给出明确结论：强烈建议买入 / 建议买入 / 谨慎买入 / 观望 / 不建议买入，并写清理由与风险。"
        "声明：内容仅供研究讨论，不构成投资建议。"
    )
    user = f"""请对以下 A 股出具完整深度研报。

股票：{name}（代码 {symbol}）
分析日：{ctx.get("as_of")}

本地系统已掌握的上下文（可能不完整，请结合常识与逻辑补全分析，勿编造精确财务数字；若上下文缺失请明确写「数据不足」）：
```json
{json.dumps(ctx, ensure_ascii=False, indent=2)}
```

请严格按以下章节输出：

# {name}（{symbol}）深度研报

## 1. 投资结论摘要
（3-6 句，先给结论）

## 2. 公司与行业画像
## 3. 基本面要点
## 4. 技术面与量价
## 5. 资金面与主力行为
## 6. 多头观点
## 7. 空头 / 风险观点
## 8. 多空辩论综合
## 9. 买卖建议与仓位
- 明确：买 / 不买 / 观望
- 建议买入区间、止损、目标（若数据不足用相对百分比）
- 持有周期建议

## 10. 最终评级
单行给出：【最终评级：xxx】
"""
    report = _deepseek_chat(system, user)
    return {
        "engine": "deepseek_multi_agent_style",
        "yf_ticker": to_yf_ticker(symbol),
        "trade_date": ctx.get("as_of"),
        "decision": _extract_decision(report),
        "report_markdown": report,
        "raw_decision": _extract_decision(report),
    }


def _run_job(job_id: str) -> None:
    job = get_job(job_id)
    if not job:
        return
    job["status"] = "running"
    job["started_at"] = datetime.now(timezone.utc).isoformat()
    job["progress"] = "正在收集本地行情与资金上下文…"
    _save_job(job)

    try:
        symbol = job["symbol"]
        name = job.get("name") or _lookup_name(symbol)
        job["name"] = name
        ctx = _gather_local_context(symbol)
        job["progress"] = "正在生成深度研报（可能需要 1–3 分钟）…"
        _save_job(job)

        result = None
        # 默认走「确定 Agent」主引擎；仅 engine=tradingagents 时才尝试外部包
        engine_pref = job.get("engine_pref") or os.getenv("DEEP_REPORT_ENGINE", "deepseek")

        if engine_pref == "tradingagents":
            try:
                job["progress"] = "正在调度多角色投研协作…"
                _save_job(job)
                result = run_tradingagents(symbol, job.get("trade_date"))
            except Exception as e:
                job["tradingagents_error"] = f"{type(e).__name__}: {e}"
                raise

        if result is None:
            job["progress"] = "确定 Agent 正在撰写研报（基本面 / 技术 / 资金 / 多空 / 风控）…"
            _save_job(job)
            result = run_deepseek_report(symbol, name, ctx)

        job.update(result)
        # 对外统一引擎品牌，不暴露第三方库名
        if job.get("engine") in ("deepseek_multi_agent_style", "tradingagents", None):
            job["engine"] = "确定 Agent"
            job["engine_id"] = result.get("engine")
        job["status"] = "done"
        job["progress"] = "研报已生成"
        job["finished_at"] = datetime.now(timezone.utc).isoformat()
        job["elapsed_seconds"] = round(
            (
                datetime.fromisoformat(job["finished_at"])
                - datetime.fromisoformat(job["started_at"])
            ).total_seconds(),
            1,
        )
        _save_job(job)
    except Exception as e:
        job["status"] = "error"
        job["error"] = str(e)
        job["traceback"] = traceback.format_exc()
        job["progress"] = "失败"
        job["finished_at"] = datetime.now(timezone.utc).isoformat()
        _save_job(job)


def start_job(
    symbol: str,
    trade_date: Optional[str] = None,
    engine_pref: str = "deepseek",
) -> dict:
    sym = normalize_symbol(symbol)
    job_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:8]
    job = {
        "job_id": job_id,
        "symbol": sym,
        "name": _lookup_name(sym),
        "trade_date": trade_date,
        "engine_pref": engine_pref,
        "status": "queued",
        "progress": "已排队",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "decision": None,
        "report_markdown": None,
    }
    _save_job(job)
    t = threading.Thread(target=_run_job, args=(job_id,), daemon=True)
    t.start()
    return {"job_id": job_id, "symbol": sym, "name": job["name"], "status": "queued"}

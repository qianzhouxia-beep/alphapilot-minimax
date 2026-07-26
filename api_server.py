"""
AlphaPilot 腾讯云 API Server
供 Zeabur 前端异步调用获取推荐结果
v0.3.0 — 推荐接入实时资金门控(腾讯盘口主动买卖占比)
"""
import json
import os
import warnings
import re
from pathlib import Path

from datetime import datetime
from typing import Optional

from fastapi import Depends, FastAPI, Header, Query, HTTPException, Request
from fastapi.responses import FileResponse
from watchlist import (
    add_to_watchlist as wl_add,
    remove_from_watchlist as wl_remove,
    get_watchlist as wl_get,
    get_db as wl_get_db,
    recompute_tracking as wl_recompute,
    update_prices as wl_update,
    claim_legacy_watchlist as wl_claim_legacy,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from auth_users import (
    authenticate as auth_authenticate,
    create_user as auth_create_user,
    ensure_owner_placeholder,
    ensure_owner_user,
    issue_token as auth_issue_token,
    verify_token as auth_verify_token,
    OWNER_EMAIL,
)

# 禁用 CDN 缓存中间件
class _NoCacheMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, private, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

from config import API_HOST, API_PORT, OUTPUT_DIR, MODELS_DIR
from data_fetcher import get_stock_list, get_kline_sina, get_sector_list
from ml_screener import screener
from analysis_engine import chat_reply, run_backtest, analyze_stock, run_backtest_for_symbols, search_stocks_pinyin
from money_flow_gate import apply_money_flow_gate, categorize_by_phase
from enriched_data import get_quote as _get_live_quote

warnings.filterwarnings("ignore")

app = FastAPI(
    title="AlphaPilot CN API",
    description="A股 AI 选股推理引擎（腾讯云节点）",
    version="0.3.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── 禁用缓存（防 CDN 缓存旧前端） ───
app.add_middleware(_NoCacheMiddleware)


# ─── 前端静态文件托管（仅挂载 /cn，不抢 API 路由） ───
_frontend_dir = Path(__file__).parent / "frontend_out"
if _frontend_dir.is_dir():
    _cn_dir = _frontend_dir / "cn"
    if _cn_dir.is_dir():
        app.mount("/cn", StaticFiles(directory=str(_cn_dir), html=True), name="frontend_cn")
        print(f"Frontend /cn mounted: {_cn_dir}")



@app.on_event("startup")
async def startup():
    """启动时预加载模型；把遗留收藏划归 root 管理员"""
    ensure_owner_placeholder()
    try:
        owner = ensure_owner_user()
        wl_claim_legacy(int(owner["id"]))
    except Exception as e:
        print(f"[auth] claim legacy watchlist skipped: {e}")
    screener.load_model()


def _bearer_token(authorization: Optional[str] = None) -> Optional[str]:
    if not authorization:
        return None
    parts = authorization.strip().split(None, 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip()
    return None


async def get_current_user(
    authorization: Optional[str] = Header(None),
) -> dict:
    token = _bearer_token(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="未登录：请先登录后再访问")
    user = auth_verify_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="登录已失效，请重新登录")
    return user


async def get_current_user_optional(
    authorization: Optional[str] = Header(None),
) -> Optional[dict]:
    token = _bearer_token(authorization)
    if not token:
        return None
    return auth_verify_token(token)


def _require_cron_or_owner(
    user: Optional[dict],
    x_cron_secret: Optional[str],
) -> None:
    secret = (os.environ.get("CRON_API_SECRET") or "").strip()
    if secret and x_cron_secret and x_cron_secret == secret:
        return
    if user and user.get("is_owner"):
        return
    raise HTTPException(status_code=403, detail="需要站长账号或 cron 密钥")


def _on_user_session(user: dict) -> None:
    """站长首次登录时认领遗留全局收藏。"""
    if user.get("is_owner"):
        try:
            wl_claim_legacy(int(user["id"]))
        except Exception:
            pass


def _empty_paper_account(user: dict) -> dict:
    return {
        "account": {
            "cash": 1_000_000.0,
            "market_value": 0.0,
            "total_assets": 1_000_000.0,
            "float_pnl": 0.0,
            "used_capital": 1_000_000.0,
            "total_pnl_pct": 0.0,
            "daily_pnl_pct": 0.0,
            "daily_pnl_amount": 0.0,
            "trade_count": 0,
            "win_rate": 0.0,
            "max_drawdown": 0.0,
        },
        "strategies": [],
        "trade_log": [],
        "personal": True,
        "owner_mode": False,
        "user_id": user["id"],
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "empty_reason": "personal_empty",
        "message": "个人模拟盘（空仓起步）。系统量化模拟盘仅账号本人可见。",
        "position_exposure": 1.0,
        "recommend_top_n": 2,
        "recommend_pool_n": 50,
        "protocol": {
            "name": "personal",
            "entry": "manual",
            "exit": "manual",
            "top_n": 0,
            "pool_n": 0,
        },
        "loop": {
            "audit": None,
            "oos": None,
            "empty_reason": "personal_empty",
            "cron": {},
        },
        "next_execution": {},
    }


def _paper_path_for_user(user: dict) -> Path:
    if user.get("is_owner"):
        return _PAPER_TRADING_PATH
    root = Path(__file__).resolve().parent
    d = root / "data" / "paper_accounts"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{int(user['id'])}.json"


# ─── 账号鉴权 ───


@app.post("/api/v1/auth/signup")
async def auth_signup(payload: dict = {}):
    try:
        user = auth_create_user(
            payload.get("email", ""),
            payload.get("password", ""),
            payload.get("full_name", "") or "",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    _on_user_session(user)
    token = auth_issue_token(user)
    return {"token": token, "user": user}


@app.post("/api/v1/auth/login")
async def auth_login(payload: dict = {}):
    user = auth_authenticate(payload.get("email", ""), payload.get("password", ""))
    if not user:
        raise HTTPException(status_code=401, detail="邮箱或密码错误")
    _on_user_session(user)
    token = auth_issue_token(user)
    return {"token": token, "user": user}


@app.get("/api/v1/auth/me")
async def auth_me(user: dict = Depends(get_current_user)):
    return {"user": user}


def _read_recommend_cache() -> dict:
    """读取推荐缓存，优先返回全量管线最新输出

    优先级:
        1. daily_recommend.json   (最新全量 V12 管线输出，~5000只)
        2. debate_v2_result.json  (备用：辩论系统 v2 旧输出，~323只)
        3. recommend_cache.json   (辩论系统旧版缓存)
    """
    from config import OUTPUT_DIR
    from pathlib import Path
    paths = [
        OUTPUT_DIR / "daily_recommend.json",
        OUTPUT_DIR / "debate_v2_result.json",
        Path("/home/ubuntu/alphapilot/recommend_cache.json"),
    ]

    for p in paths:
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue

    raise HTTPException(status_code=404, detail="暂无推荐结果，请先运行每日管线")


def _confidence_score(score: float) -> int:
    """把 0~1 模型概率映射为 75~99 信心分（仅展示，非考试百分制）。"""
    try:
        s = float(score or 0)
    except Exception:
        s = 0.0
    return int(min(99, max(75, round(s * 45 + 75))))


def _to_model_proba(score: float) -> float:
    """把原始 score 规范为 0~1。

    管线里 VM 概率通常在 [0,1]；live_momentum_scanner 的综合/z 分常 >1，
    若直接 *100 会在前端显示成 299 这种异常分。
    """
    try:
        s = float(score or 0)
    except Exception:
        return 0.0
    if s <= 0:
        return 0.0
    if s <= 1.0:
        return s
    import math

    return max(0.0, min(0.999, 1.0 / (1.0 + math.exp(-s / 2.0))))


def _normalize_recommend_item(item: dict) -> dict:
    """统一推荐项字段格式，兼容新旧两种输出"""
    raw = float(item.get("score", 0) or 0)
    # 显式 model_proba 优先（且必须是 0~1）
    proba = _to_model_proba(raw)
    try:
        mp = item.get("model_proba")
        if mp is not None:
            mp_f = float(mp)
            if 0 <= mp_f <= 1.0:
                proba = mp_f
    except Exception:
        pass
    lgb_raw = float(item.get("lgb_score", item.get("score", 0)) or 0)
    lgb_proba = _to_model_proba(lgb_raw)
    base = {
        "symbol": item.get("symbol", ""),
        "name": item.get("name", ""),
        "score": raw,
        # 兼容旧字段；前端应优先用 confidence_score / model_proba
        "score_pct": round(proba * 100, 1),
        "model_proba": round(proba, 4),
        "confidence_score": _confidence_score(proba),
        "score_note": "confidence_score=展示信心分(75-99); model_proba=VM2.5概率(0-1); 勿把score_pct当考试分",
        "score_composite": round(raw, 4) if raw > 1.0 else None,
        "lgb_score": round(lgb_proba, 4),
        "sector_heat": item.get("sector_heat", 0.5),
        "buy_price": item.get("buy_price"),
        "target_price": item.get("target_price"),
        "stop_price": item.get("stop_price"),
        # 资金门控信号
        "active_buy_ratio": item.get("active_buy_ratio"),
        "turnover": item.get("turnover"),
        "volume_ratio": item.get("volume_ratio"),
        "money_flow_pass": item.get("money_flow_pass"),
        "score_raw": item.get("score_raw"),
        "change_pct": item.get("change_pct"),
        "drop_reason": item.get("drop_reason"),
        # 市盈率（客户自选 PE≤30 / PE>30；勿在 normalize 时丢掉）
        "pe_ttm": item.get("pe_ttm", item.get("pe")),
        "pe": item.get("pe", item.get("pe_ttm")),
        "pe_bucket": item.get("pe_bucket"),
        # 趋势首选 / 下跌通道
        "trend_prefer": item.get("trend_prefer"),
        "trend_prefer_strong": item.get("trend_prefer_strong"),
        "trend_prefer_hits": item.get("trend_prefer_hits"),
        "trend_flags": item.get("trend_flags"),
        "downtrend_channel": item.get("downtrend_channel"),
        # 基本面信号（mootdx财务）
        "net_profit": item.get("net_profit"),
        "eps": item.get("eps"),
        "roe": item.get("roe"),
        "revenue": item.get("revenue"),
        "fundamental_pass": item.get("fundamental_pass"),
        "industry_code": item.get("industry_code"),
        # 主力资金阶段
        "money_phase": item.get("money_phase"),
        "money_phase_label": item.get("money_phase_label"),
        # 资金锋面/骨架
        "main_net": item.get("main_net"),
        "main_net_3d": item.get("main_net_3d"),
        "main_net_5d": item.get("main_net_5d"),
        "main_net_10d": item.get("main_net_10d"),
        "fund_pos_days_5": item.get("fund_pos_days_5"),
        "fund_soft_bonus": item.get("fund_soft_bonus"),
        "fund_gate_mode": item.get("fund_gate_mode"),
        "money_warning": item.get("money_warning"),
        "industry": item.get("industry"),
        "industry_l1": item.get("industry_l1"),
        "industry_l2": item.get("industry_l2"),
        "industry_l3": item.get("industry_l3"),
        "industry_path": item.get("industry_path"),
        "sector": item.get("sector") or item.get("industry") or item.get("industry_l3"),
        "soft_demote_reasons": item.get("soft_demote_reasons"),
        "sector_gate": item.get("sector_gate"),
        "exposure": item.get("exposure"),
        "position_exposure": item.get("position_exposure"),
    }
    # 辩论系统特有字段
    if "agent_votes" in item:
        base["agent_votes"] = item["agent_votes"]
        base["vote_count"] = len(item["agent_votes"])
    if "risk_flags" in item:
        base["risk_flags"] = item["risk_flags"]
    # 旧模型特征
    if "features" in item:
        base["features"] = item["features"]
    # 加实时价格
    _sym = base.get("symbol", "").replace("sh","").replace("sz","")
    if _sym:
        try:
            _q = _get_live_quote(_sym)
            if _q and _q.get("price"):
                base["live_price"] = _q["price"]
                base["live_change_pct"] = _q.get("change_pct", 0)
                # 覆盖 predicted fields 为实时值
                base["change_pct"] = _q.get("change_pct", base.get("change_pct", 0))
                base["price"] = _q["price"]
        except Exception:
            pass
    return base


@app.get("/health")
async def health():
    """健康检查"""
    return {
        "status": "healthy",
        "model_loaded": screener.model_loaded,
        "node": "tencent-cloud-shanghai",
    }


@app.get("/selection-framework")
async def selection_framework_page():
    """选股框架说明页（纯 HTML，手机浏览器可直接打开）"""
    path = Path(__file__).parent / "output" / "alphapilot_selection_framework.html"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="selection framework page not found")
    return FileResponse(
        path,
        media_type="text/html; charset=utf-8",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


def _attach_live_quotes(items: list) -> list:
    """给列表项补齐实时价/涨跌/市盈率TTM（腾讯行情）。"""
    if not items:
        return items
    try:
        from enriched_data import get_quotes_batch

        syms = []
        for it in items:
            code = str(it.get("symbol") or "")[-6:]
            if code and code not in syms:
                syms.append(code)
        quotes = get_quotes_batch(syms) or {}
        for it in items:
            code = str(it.get("symbol") or "")[-6:]
            q = quotes.get(code) or quotes.get(f"sh{code}") or quotes.get(f"sz{code}") or {}
            if q:
                if q.get("price") is not None:
                    it["price"] = q.get("price")
                if q.get("change_pct") is not None:
                    it["change_pct"] = q.get("change_pct")
                pe = q.get("pe_ttm", q.get("pe"))
                if pe is not None:
                    try:
                        pe_f = float(pe)
                        it["pe_ttm"] = pe_f
                        it["pe"] = pe_f
                    except (TypeError, ValueError):
                        pass
            # 无论行情是否命中，都回填 pe_bucket（保留文件中已有 pe）
            try:
                from money_flow_gate import classify_pe_bucket

                it["pe_bucket"] = classify_pe_bucket(it.get("pe_ttm", it.get("pe")))
            except Exception:
                pass
    except Exception:
        # 行情失败时仍尽量补 pe_bucket
        try:
            from money_flow_gate import classify_pe_bucket

            for it in items:
                if it.get("pe_bucket") not in ("le_30", "gt_30", "na"):
                    it["pe_bucket"] = classify_pe_bucket(it.get("pe_ttm", it.get("pe")))
        except Exception:
            pass
    return items


@app.get("/api/v1/cn/score-top10")
async def get_score_top10():
    """评分榜 Top10：只按 score 降序，无资金/板块门槛（与门控推荐分离）。"""
    path = Path("output/score_top10.json")
    if not path.exists():
        path = Path("/home/ubuntu/alphapilot/output/score_top10.json")
    if not path.exists():
        raise HTTPException(status_code=404, detail="暂无评分 Top10，请先运行 build_score_top10")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    items = _attach_live_quotes(list(data.get("items") or []))

    # recommend_compare：实时从 daily_recommend.json 拉最新推荐（而非 score_top10 文件里的旧快照）
    rec_cmp = []
    try:
        _rec_paths = [
            Path("output/daily_recommend.json"),
            Path("/home/ubuntu/alphapilot/output/daily_recommend.json"),
        ]
        for _rp in _rec_paths:
            if _rp.exists():
                _rd = json.loads(_rp.read_text(encoding="utf-8"))
                _recs = _rd.get("recommendations") or _rd.get("items") or []
                _top_n = int(_rd.get("recommend_top_n") or 2)
                rec_cmp = [
                    {**dict(x), "symbol": str(x.get("symbol", ""))[-6:]}
                    for x in _recs[:_top_n]
                    if x.get("symbol")
                ]
                break
    except Exception:
        rec_cmp = _attach_live_quotes(list(data.get("recommend_compare") or []))
    if rec_cmp:
        rec_cmp = _attach_live_quotes(rec_cmp)

    return {
        "asof": data.get("asof"),
        "mode": data.get("mode") or "score_only_no_threshold",
        "note": data.get("note")
        or "按评分降序第1–10名，无门槛；推荐池为另一路门控结果",
        "items": items[:10],
        "recommend_compare": rec_cmp,
        "n": min(10, len(items)),
    }


def _load_first_json(candidates: list[str | Path]) -> dict:
    """按候选路径顺序读第一个可用 JSON 对象。"""
    for c in candidates:
        p = Path(c)
        try:
            if p.exists():
                raw = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    return raw
        except Exception:
            continue
    return {}


_EMPTY_REASON_CN = {
    "awaiting_human_approval": "待人工确认 — 确认前不自动买入",
    "position_exposure_zero": "核武空仓 — 今日不新开仓",
    "no_morning_picks": "盘中资金重排后无候选",
    "fallback_empty": "候选为空",
}


def _expo_status(expo: float, empty_reason: str | None, n_picks: int) -> dict:
    reason = (empty_reason or "").strip()
    if reason == "position_exposure_zero" or expo <= 0:
        return {
            "code": "empty",
            "label": "空仓",
            "detail": "仓位曝光为 0（核武日），今日不新开仓",
        }
    if reason == "awaiting_human_approval":
        return {
            "code": "awaiting",
            "label": "待确认",
            "detail": "标的已出，需人工过目后才会写入买入信号",
        }
    if reason in ("no_morning_picks", "fallback_empty") or n_picks <= 0:
        return {
            "code": "no_picks",
            "label": "无标的",
            "detail": _EMPTY_REASON_CN.get(reason) or "今日暂无可执行买入标的",
        }
    if expo >= 0.99:
        return {"code": "buy", "label": "可买入", "detail": "满仓曝光，等权买入 TopN"}
    if expo >= 0.5:
        return {"code": "half", "label": "半仓", "detail": f"仓位曝光 {expo:.0%}，等权买入 TopN"}
    return {"code": "light", "label": "轻仓", "detail": f"仓位曝光 {expo:.0%}，薄仓买入"}


def _recommend_top_for_trade(rec: dict, top_n: int) -> tuple[list[dict], str]:
    """与「今日推荐」同口径：daily_recommend → 资金门控 → 按 score 取 TopN。

    对应生产 09:35 live_momentum_scanner 全市场重选后的池子，而不是
    过期的 morning_live_picks（旧 05:00 池资金截 Top2）。
    """
    items = rec.get("recommendations") or rec.get("items") or []
    if not isinstance(items, list):
        items = []
    try:
        from money_flow_gate import apply_money_flow_gate

        gated = apply_money_flow_gate(items, top_n=None)
    except Exception:
        gated = items
    normalized = [_normalize_recommend_item(it) for it in gated if isinstance(it, dict)]
    passed = [it for it in normalized if it.get("money_flow_pass") is True]
    if not passed:
        passed = sorted(
            normalized,
            key=lambda x: float(x.get("score", 0) or 0),
            reverse=True,
        )
    else:
        passed = sorted(
            passed,
            key=lambda x: float(x.get("score", 0) or 0),
            reverse=True,
        )
    asof = (
        str(rec.get("generated_at") or rec.get("run_at") or rec.get("asof") or "")
    )
    return passed[: max(0, int(top_n))], asof


def _build_cn_trade_plan(rec_data: dict | None = None) -> dict:
    """组装「今日交易指令」：买不买 / 买谁 / 买多少 / 出场四层。

    标的与网页「今日推荐」对齐（09:35 全市场动量/ICIR 重选 + 资金门控），
    不再优先使用可能过期的 morning_live_picks.json。
    """
    picks_raw = _load_first_json(
        [
            Path(OUTPUT_DIR) / "morning_live_picks.json",
            Path("output") / "morning_live_picks.json",
            Path("/home/ubuntu/alphapilot/output/morning_live_picks.json"),
        ]
    )
    paper = _load_first_json(
        [
            Path("/home/ubuntu/alphapilot/data/paper_trading.json"),
            Path("data") / "paper_trading.json",
        ]
    )
    rec = rec_data if isinstance(rec_data, dict) else {}
    if not rec:
        try:
            rec = _read_recommend_cache()
        except Exception:
            rec = {}

    try:
        expo = float(
            paper.get("position_exposure")
            if paper.get("position_exposure") is not None
            else rec.get("position_exposure")
            if rec.get("position_exposure") is not None
            else picks_raw.get("position_exposure")
            if picks_raw.get("position_exposure") is not None
            else 1.0
        )
    except Exception:
        expo = 1.0

    flags = (
        paper.get("market_env_flags")
        or rec.get("market_env_flags")
        or picks_raw.get("market_env_flags")
        or {}
    )
    if not isinstance(flags, dict):
        flags = {}

    exit_policy = paper.get("exit_policy") if isinstance(paper.get("exit_policy"), dict) else {}
    protocol = paper.get("protocol") if isinstance(paper.get("protocol"), dict) else {}

    try:
        top_n = int(
            paper.get("recommend_top_n")
            or protocol.get("top_n")
            or picks_raw.get("trade_top_n")
            or (1 if 0 < expo < 0.5 else (0 if expo <= 0 else 2))
        )
    except Exception:
        top_n = 2

    empty_reason = (
        paper.get("empty_reason")
        if paper.get("empty_reason") is not None
        else picks_raw.get("empty_reason")
    )

    # 主源：与今日推荐同池同排序
    raw_picks, rec_asof = _recommend_top_for_trade(rec, top_n if top_n > 0 else 2)
    pick_source = "daily_recommend_gated"

    # 仅当 morning picks 与推荐池同一交易日时，保留其 asof 备注（不覆盖标的）
    morning_asof = str(picks_raw.get("asof") or "")
    today = datetime.now().strftime("%Y-%m-%d")
    morning_same_day = bool(morning_asof) and morning_asof[:10] == today

    sized = []
    n_buy = max(0, min(top_n, len(raw_picks))) if expo > 0 else 0
    per_w = (expo / n_buy) if n_buy > 0 else 0.0
    for i, it in enumerate(raw_picks[: max(top_n, 0) or 0]):
        if not isinstance(it, dict):
            continue
        sym = str(it.get("symbol") or "")
        if not sym:
            continue
        buy_price = it.get("buy_price") or it.get("price")
        try:
            buy_price = float(buy_price) if buy_price is not None else None
        except Exception:
            buy_price = None
        sized.append(
            {
                "rank": i + 1,
                "symbol": sym,
                "name": it.get("name") or "",
                "score": it.get("score"),
                "buy_price": buy_price,
                "target_price": it.get("target_price"),
                "stop_price": it.get("stop_price"),
                "sector": it.get("research_prefer_hit")
                or it.get("sector")
                or it.get("industry")
                or it.get("industry_l1"),
                "money_phase_label": it.get("money_phase_label") or it.get("money_phase"),
                "weight_pct": round(per_w * 100, 1) if i < n_buy else 0.0,
                "weight_of_book": round(per_w, 4) if i < n_buy else 0.0,
                "action": "buy" if i < n_buy and expo > 0 else "skip",
            }
        )

    status = _expo_status(expo, empty_reason, len([x for x in sized if x.get("action") == "buy"]))

    trail_arm = float(exit_policy.get("trail_arm") or 0.03)
    peel_pb = float(exit_policy.get("peel_pullback") or 0.015)
    hard_stop = float(exit_policy.get("hard_stop_pct") or -0.10)

    exit_layers = [
        {
            "id": 1,
            "name": "动态止盈（peel）",
            "rule": (
                f"浮盈≥{trail_arm:.0%}仅激活跟踪；峰值回撤≥{peel_pb:.1%}→剩余仓减半；"
                "须再创新高才允许下一刀；第3刀清仓"
            ),
        },
        {
            "id": 2,
            "name": "E2 硬止损",
            "rule": f"成本{hard_stop:.0%}；仅≥14:45 收盘确认且现价仍≤止损才全清",
        },
        {
            "id": 3,
            "name": "T+2 强平",
            "rule": "持有满1个交易日于14:45后强平；资金净流入且价≥95%成本可延期1天（仅一次）",
        },
        {
            "id": 4,
            "name": "板块反转",
            "rule": "盘中板块急杀触发紧急卖出（intraday sector watch）",
        },
    ]

    entry_text = (
        exit_policy.get("entry")
        or protocol.get("entry")
        or "GapSoft：≤1.5% 全仓；1.5–3% 限价；3–5% 线性降权；≥5% 跳过"
    )

    approval = paper.get("approval_gate") if isinstance(paper.get("approval_gate"), dict) else {}
    asof = rec_asof or (morning_asof if morning_same_day else "") or ""

    return {
        "asof": asof,
        "arm": "A1_permission",
        "status": status,
        "position_exposure": round(expo, 4),
        "trade_top_n": top_n,
        "empty_reason": empty_reason,
        "empty_reason_label": _EMPTY_REASON_CN.get(str(empty_reason or ""), None),
        "execution_window": "09:37 后（09:35 全市场重选完成后）",
        "entry": entry_text,
        "entry_mode": exit_policy.get("entry_mode") or protocol.get("entry_mode") or "gap_soft",
        "market_env_flags": flags,
        "buys": sized,
        "exit_layers": exit_layers,
        "exit_policy_mode": exit_policy.get("mode"),
        "approval_gate": {
            "enabled": bool(approval.get("enabled", True)),
            "pending_n": int(approval.get("pending_n") or 0),
            "note": approval.get("note"),
        },
        "protocol_name": "live_momentum_full_universe",
        "pick_source": pick_source,
        "note": "标的与下方「今日推荐」同口径（09:35 全市场重选+资金门控 TopN）；非旧 morning_live_picks",
    }


@app.get("/api/v1/cn/trade-plan")
async def get_trade_plan():
    """今日交易指令（买不买 / 买谁 / 买多少 / 出场四层）"""
    try:
        rec = _read_recommend_cache()
    except Exception:
        rec = {}
    return _build_cn_trade_plan(rec)


@app.get("/api/v1/cn/recommend")
async def get_recommend():
    """获取最新推荐结果（已施加实时资金门控 + 加权）"""
    data = _read_recommend_cache()

    items = data.get("recommendations", data.get("items", []))
    # 实时资金门控：用腾讯真实盘口过滤弱资金流标的，并按主动买入占比加权
    try:
        gated = apply_money_flow_gate(items, top_n=None)
    except Exception:
        gated = items
    normalized = [_normalize_recommend_item(it) for it in gated]

    # 评分排名解释：把原始概率转换为相对排名（如 Top 1%）
    all_scores = [float(it.get("score", 0) or 0) for it in gated]
    sorted_scores = sorted(all_scores, reverse=True)
    for it in normalized:
        s = float(it.get("score", 0) or 0)
        if sorted_scores:
            rank = sorted_scores.index(s) + 1
            pct = rank / len(sorted_scores) * 100
            it["score_rank_pct"] = round(pct, 1)
            it["score_label"] = f"Top {pct:.0f}%" if pct <= 5 else f"前 {pct:.0f}%"
        else:
            it["score_rank_pct"] = None
            it["score_label"] = None

    # 只返回通过门控的股票（默认隐藏跌停/亏损/资金流出的）
    # 通过资金门控的（有实时盘口数据的）
    passed_items = [it for it in normalized if it.get("money_flow_pass") is True]
    # 无实时盘口数据时的降级：按评分排序取 Top
    if len(passed_items) == 0:
        passed_items = sorted(normalized, key=lambda x: float(x.get("score", 0) or 0), reverse=True)
    # 只返回 Top 10 最有可能涨的
    MAX_RETURN = 10
    passed_items = _attach_live_quotes(passed_items[:MAX_RETURN])
    filtered_count = len(normalized) - len(passed_items)

    trade_plan = _build_cn_trade_plan(data)

    return {
        "run_at": data.get("run_at", ""),
        "generated_at": data.get("generated_at", ""),
        "pipeline_version": data.get("pipeline_version", "v3.1_funnel_gated"),
        "model_version": data.get("model_version", "v25"),
        "position_exposure": data.get("position_exposure"),
        "trade_plan": trade_plan,
        "recommendations": passed_items,
        "stats": {
            "total_scanned": data.get("stats", {}).get(
                "total_scanned",
                data.get("stats", {}).get("universe_n", 0),
            ),
            "universe_n": data.get("stats", {}).get("universe_n"),
            "launch_hits": data.get("stats", {}).get("launch_hits"),
            "model_pool_scored": data.get("stats", {}).get("model_pool_scored"),
            "valid_scored": data.get("stats", {}).get("valid_scored", data.get("stocks_passed", 0)),
            "elapsed_seconds": data.get("stats", {}).get("elapsed_seconds", data.get("elapsed_seconds", 0)),
            "money_flow_gated": True,
            "filtered_out": filtered_count,
            "returned": len(passed_items),
            "score_scale": "confidence_score 75-99 display; model_proba 0-1",
        },
    }





@app.get("/api/v1/cn/recommend/categorized")
async def get_recommend_categorized():
    """按资金阶段分类推荐（每类 Top 5）"""
    data = _read_recommend_cache()
    items = data.get("recommendations", data.get("items", []))
    try:
        categories = categorize_by_phase(items)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"分类失败: {str(e)}")

    phase_labels = {
        "bear_trap": {"label": "诱空陷阱", "emoji": "🪤", "desc": "主力压价洗盘，暗中吸筹"},
        "rightside_ambush": {"label": "右侧潜伏", "emoji": "🎯", "desc": "吸筹完成，刚启动的起爆点"},
        "accumulation_end": {"label": "吸筹末期", "emoji": "🔔", "desc": "缩量蓄力完成"},
        "markup": {"label": "拉升", "emoji": "🚀", "desc": "主力正在拉升上涨"},
        "accumulation": {"label": "吸筹", "emoji": "📥", "desc": "主力在低位默默吸筹"},
        "suspicious": {"label": "诱多嫌疑", "emoji": "⚠️", "desc": "高位缩量，警惕回调"},
        "distribution": {"label": "出货", "emoji": "⚠️", "desc": "主力放量出货"},
        "pullback": {"label": "回调", "emoji": "📉", "desc": "短期回调中"},
        "sideways": {"label": "震荡", "emoji": "➡️", "desc": "方向不明"},
    }

    result_categories = {}
    for phase_key, stocks in categories.items():
        if not stocks:
            continue
        info = phase_labels.get(phase_key, {"label": phase_key, "emoji": "", "desc": ""})
        result_categories[phase_key] = {
            "label": info["label"],
            "emoji": info["emoji"],
            "desc": info["desc"],
            "count": len(stocks),
            "stocks": [
                {
                    "symbol": s.get("symbol"),
                    "name": s.get("name"),
                    "score": s.get("score"),
                    "score_pct": round(float(s.get("score", 0) or 0) * 100, 1),
                    "model_proba": round(float(s.get("score", 0) or 0), 4),
                    "confidence_score": _confidence_score(s.get("score", 0)),
                    "buy_price": s.get("buy_price"),
                    "price": s.get("price") or s.get("buy_price"),
                    "active_buy_ratio": s.get("active_buy_ratio"),
                    "change_pct": s.get("change_pct"),
                    "turnover": s.get("turnover"),
                    "volume_ratio": s.get("volume_ratio"),
                    "money_flow_pass": s.get("money_flow_pass"),
                    "money_phase_label": s.get("money_phase_label"),
                    "overheat_warning": s.get("overheat_warning"),
                    "accumulation_signal": s.get("accumulation_signal"),
                    "new_low_warning": s.get("new_low_warning"),
                }
                for s in stocks[:5]
            ],
        }

    return {
        "run_at": data.get("run_at", ""),
        "categories": result_categories,
        "stats": {
            "total_scanned": data.get("stats", {}).get("total_scanned", 0),
            "valid_scored": data.get("stats", {}).get("valid_scored", 0),
        },
    }

@app.get("/api/v1/cn/news")
async def get_news():
    """投资资讯 —— 全球产业链资讯看板（读取 investment-news 数据）"""
    import re as _re
    news_path = Path("/home/ubuntu/investment-news/data.js")
    if not news_path.exists():
        raise HTTPException(status_code=404, detail="暂无资讯数据")
    try:
        raw = news_path.read_text(encoding="utf-8")
        # 去掉注释行和 "window.DATA = " 前缀
        lines = [l for l in raw.splitlines() if not l.strip().startswith("//")]
        json_str = "\n".join(lines)
        json_str = _re.sub(r"^window\.DATA\s*=\s*", "", json_str)
        json_str = _re.sub(r";\s*$", "", json_str.strip())
        return json.loads(json_str)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"解析失败: {e}")


@app.get("/api/v1/cn/sectors")
async def get_sectors_dashboard(
    refresh: bool = Query(False, description="强制重建轮动快照/重算多日资金"),
    period: str = Query("today", description="today|5day|10day|20day|60day"),
):
    """A 股板块看板：资金流入/流出、涨跌散点、轮动状态（图表友好）。"""
    try:
        from sector_dashboard import build_dashboard, PERIODS

        if period not in PERIODS:
            raise HTTPException(status_code=400, detail=f"period 需为 {PERIODS}")
        return build_dashboard(force_refresh=refresh, period=period)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"板块看板失败: {e}")


@app.get("/api/v1/cn/sectors/detail")
async def get_sector_detail_api(
    name: str = Query(..., description="板块名称"),
    period: str = Query("today", description="today|5day|10day|20day|60day"),
):
    """单个板块详情（看板内点选）。"""
    try:
        from sector_dashboard import get_sector_detail

        detail = get_sector_detail(name.strip(), period=period)
        if not detail:
            raise HTTPException(status_code=404, detail="未找到该板块")
        return detail
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"板块详情失败: {e}")


@app.get("/api/v1/cn/search")
async def search_stocks(keyword: str = Query(..., description="股票代码或名称关键词")):
    """搜索股票"""
    stocks = get_stock_list()
    if stocks.empty:
        raise HTTPException(status_code=503, detail="股票列表获取失败")

    result = screener.search_stocks(keyword, stocks)
    return {
        "keyword": keyword,
        "results": result.to_dict(orient="records") if not result.empty else [],
    }


@app.get("/api/v1/cn/market-overview")
async def market_overview():
    """市场概览"""
    sectors = get_sector_list()
    stocks = get_stock_list()
    if stocks.empty:
        raise HTTPException(status_code=503, detail="数据获取失败")

    up_count = int((stocks["pct_chg"] > 0).sum()) if "pct_chg" in stocks.columns else 0
    down_count = int((stocks["pct_chg"] < 0).sum()) if "pct_chg" in stocks.columns else 0

    return {
        "total_stocks": len(stocks),
        "up_count": up_count,
        "down_count": down_count,
        "sector_count": len(sectors) if not sectors.empty else 0,
    }


INDICES_CODES = {
    "上证指数": "sh000001",
    "深证成指": "sz399001",
    "创业板指": "sz399006",
}


@app.get("/api/v1/cn/indices")
async def get_indices():
    """实时获取三大指数行情（新浪财经）"""
    import urllib.request
    codes = list(INDICES_CODES.values())
    url = f"https://hq.sinajs.cn/list={','.join(codes)}"
    req = urllib.request.Request(url, headers={"Referer": "https://finance.sina.com.cn"})
    try:
        resp = urllib.request.urlopen(req, timeout=5)
        raw = resp.read().decode("gbk")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"获取指数数据失败: {e}")

    result = []
    for line in raw.strip().splitlines():
        if not line.startswith("var hq_str_"):
            continue
        parts = line.split('"')[1].split(",") if '"' in line else []
        if len(parts) < 30:
            continue
        name = parts[0]
        open_p = float(parts[1]) if parts[1] else 0
        prev_close = float(parts[2]) if parts[2] else 0
        current = float(parts[3]) if parts[3] else 0
        high = float(parts[4]) if parts[4] else 0
        low = float(parts[5]) if parts[5] else 0
        chg = current - prev_close
        chg_pct = round(chg / prev_close * 100, 2) if prev_close else 0
        # 反向查找 name 对应的 key
        idx_name = next((k for k, v in INDICES_CODES.items() if v in line), name)
        result.append({
            "name": idx_name,
            "code": parts[-1] if len(parts) > 30 else "",
            "price": current,
            "change": round(chg, 2),
            "change_pct": chg_pct,
            "open": open_p,
            "high": high,
            "low": low,
            "prev_close": prev_close,
        })

    return {"indices": result, "count": len(result)}


def _clean_symbol(symbol: str) -> str:
    return re.sub(r"^(?:SH|SZ|BJ|sh|sz|bj)|\.(?:SH|SZ|BJ|sh|sz|bj)$", "", str(symbol or "").upper())


def _load_industry_map() -> dict:
    for p in (Path("data/stock_industry_map.json"), Path("/home/ubuntu/alphapilot/data/stock_industry_map.json")):
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
    return {}


def _load_fund_hist() -> dict:
    for p in (Path("data/fund_flow_history.json"), Path("/home/ubuntu/alphapilot/data/fund_flow_history.json")):
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
    return {}


def _fund_windows(sym: str) -> dict:
    """3日锋面 / 5日骨架 / 10日参考，来自本地资金流历史。"""
    hist = _load_fund_hist().get(_clean_symbol(sym), {}) or {}
    dates = sorted(hist.keys(), reverse=True)
    out = {
        "main_net_3d": None,
        "main_net_5d": None,
        "main_net_10d": None,
        "fund_pos_days_5": 0,
        "fund_series_5d": [],
    }
    if not dates:
        return out
    nets3 = [float(hist[d]) for d in dates[:3] if d in hist]
    nets5 = [float(hist[d]) for d in dates[:5] if d in hist]
    nets10 = [float(hist[d]) for d in dates[:10] if d in hist]
    if len(nets3) >= 2:
        out["main_net_3d"] = round(sum(nets3), 2)
    if len(nets5) >= 3:
        out["main_net_5d"] = round(sum(nets5), 2)
        out["fund_pos_days_5"] = sum(1 for x in nets5 if x > 0)
        out["fund_series_5d"] = [
            {"date": d, "main_net": round(float(hist[d]), 2)} for d in dates[:5] if d in hist
        ]
    if len(nets10) >= 5:
        out["main_net_10d"] = round(sum(nets10), 2)
    return out


def _enrich_stock_meta(result: dict, sym: str) -> dict:
    """补齐行业、资金窗口；前端板块字段用 industry。"""
    code = _clean_symbol(sym)
    imap = _load_industry_map()
    meta = imap.get(code) or {}
    if meta:
        result.setdefault("name", meta.get("name") or result.get("name"))
        result["industry"] = meta.get("industry") or meta.get("industry_l3")
        result["industry_l1"] = meta.get("industry_l1")
        result["industry_l2"] = meta.get("industry_l2")
        result["industry_l3"] = meta.get("industry_l3")
        result["industry_path"] = meta.get("industry_path")
        result["sector"] = result.get("sector") or result.get("industry") or meta.get("industry_l3")
        result["region"] = result.get("region") or meta.get("industry_l1")
    fw = _fund_windows(code)
    for k, v in fw.items():
        if result.get(k) in (None, 0, 0.0) or k == "fund_series_5d":
            result[k] = v
        elif k not in result:
            result[k] = v
    # 若推荐项已有资金字段则保留非空值
    for k in ("main_net_3d", "main_net_5d", "main_net_10d", "fund_pos_days_5"):
        if result.get(k) is None and fw.get(k) is not None:
            result[k] = fw[k]
    if not result.get("fund_series_5d"):
        result["fund_series_5d"] = fw.get("fund_series_5d") or []
    result["fund_gate_mode"] = result.get("fund_gate_mode") or "weak_hard_plus_soft"
    if result.get("fund_soft_bonus") is None:
        import math

        s3 = float(result.get("main_net_3d") or 0)
        s5 = float(result.get("main_net_5d") or 0)
        pos5 = int(result.get("fund_pos_days_5") or 0)
        bonus = math.tanh(s3 / 5e7) * 0.04 + math.tanh(s5 / 1e8) * 0.06 + min(pos5, 5) * 0.01
        if s3 > 0 and s5 > 0:
            bonus += 0.02
        result["fund_soft_bonus"] = round(max(-0.05, min(0.15, bonus)), 4)
    return result


@app.get("/api/v1/cn/stock/{symbol}")
async def get_cn_stock_detail(symbol: str):
    """单只股票详情: 优先查推荐缓存，未找到则按需评分；并补齐行业/资金窗口。"""
    try:
        from enriched_data import get_quote

        data = _read_recommend_cache()
        items = data.get("recommendations", data.get("items", []))
        sym_clean = _clean_symbol(symbol)

        # 1) 优先查推荐缓存
        if items:
            for item in items:
                item_clean = _clean_symbol(item.get("symbol", ""))
                if item_clean == sym_clean:
                    result = _normalize_recommend_item(item)
                    try:
                        _q = get_quote(sym_clean)
                        if _q and _q.get("price"):
                            result["live_price"] = _q["price"]
                            result["live_change_pct"] = _q.get("change_pct", 0)
                            result["price"] = _q["price"]
                            result["change_pct"] = _q.get("change_pct", result.get("change_pct"))
                            for fk in ("open", "high", "low", "prev_close", "volume", "turnover", "pe"):
                                if _q.get(fk) is not None:
                                    result[fk] = _q.get(fk)
                            live = float(_q["price"])
                            old_t = float(result.get("target_price") or 0)
                            old_s = float(result.get("stop_price") or 0)
                            # 详情卡买入价对齐现价；目标必须高于买入，否则 ATR 重算
                            if old_t > live > 0 and 0 < old_s < live:
                                result["buy_price"] = round(live, 2)
                                result["stop_price"] = round(min(old_s, live * 0.97), 2)
                                if result["stop_price"] >= live:
                                    result["stop_price"] = round(live * 0.97, 2)
                            else:
                                lv = _sanitize_long_levels(live, old_t, old_s)
                                result["buy_price"] = lv["buy_price"]
                                result["target_price"] = lv["target_price"]
                                result["stop_price"] = lv["stop_price"]
                    except Exception:
                        pass
                    result = _enrich_stock_meta(result, sym_clean)
                    # 详情页旧前端会把 score*100 当展示分；综合/z 分 >1 会显示成 299。
                    # 对外 score 改为 0~1 概率，原始综合分保留在 score_composite。
                    if float(result.get("score") or 0) > 1.0:
                        result["score_composite"] = round(float(result["score"]), 4)
                        result["score"] = float(result.get("model_proba") or _to_model_proba(result["score"]))
                    return result

        # 2) 不在缓存 → 按需评分
        on_demand = _analyze_on_demand(sym_clean)
        if on_demand:
            on_demand = _enrich_stock_meta(on_demand, sym_clean)
            if float(on_demand.get("score") or 0) > 1.0:
                on_demand["score_composite"] = round(float(on_demand["score"]), 4)
                on_demand["score"] = float(on_demand.get("model_proba") or _to_model_proba(on_demand["score"]))
            return on_demand

        raise HTTPException(status_code=404, detail=f"股票 {symbol} 未找到")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/cn/stock/{symbol}/peers")
async def get_cn_stock_peers(symbol: str, limit: int = Query(8, ge=1, le=20)):
    """同三级行业（不足则回退一级）的代表性股票。"""
    code = _clean_symbol(symbol)
    imap = _load_industry_map()
    meta = imap.get(code) or {}
    industry = str(meta.get("industry") or meta.get("industry_l3") or "")
    industry_l1 = str(meta.get("industry_l1") or "")
    if not industry and not industry_l1:
        return {"symbol": code, "sector": None, "peers": []}

    peers_codes = []
    for c, m in imap.items():
        if c == code or not isinstance(m, dict):
            continue
        ind = str(m.get("industry") or m.get("industry_l3") or "")
        if industry and ind == industry:
            peers_codes.append(c)
    if len(peers_codes) < 3 and industry_l1:
        for c, m in imap.items():
            if c == code or not isinstance(m, dict):
                continue
            if str(m.get("industry_l1") or "") == industry_l1 and c not in peers_codes:
                peers_codes.append(c)
            if len(peers_codes) >= 40:
                break

    peers_codes = peers_codes[:40]
    quotes = {}
    try:
        from enriched_data import get_quotes_batch

        quotes = get_quotes_batch(peers_codes[:20]) or {}
    except Exception:
        quotes = {}

    peers = []
    for c in peers_codes:
        m = imap.get(c) or {}
        q = quotes.get(c) or quotes.get(f"sh{c}") or quotes.get(f"sz{c}") or {}
        peers.append(
            {
                "symbol": c,
                "name": m.get("name") or c,
                "change_pct": q.get("change_pct"),
                "price": q.get("price"),
            }
        )
        if len(peers) >= limit:
            break
    # 有涨跌幅的优先排前
    peers.sort(key=lambda x: (x.get("change_pct") is None, -(x.get("change_pct") or 0)))
    return {
        "symbol": code,
        "sector": industry or industry_l1,
        "industry_l1": industry_l1,
        "peers": peers[:limit],
    }


@app.get("/api/v1/cn/stock/{symbol}/news")
async def get_cn_stock_news(symbol: str, limit: int = Query(8, ge=1, le=20)):
    """个股相关新闻（东财优先；失败返回空列表 + 外链提示）。"""
    code = _clean_symbol(symbol)
    items = []
    try:
        import akshare as ak

        df = ak.stock_news_em(symbol=code)
        if df is not None and not df.empty:
            for _, row in df.head(limit).iterrows():
                title = str(row.get("新闻标题") or row.get("title") or "").strip()
                if not title or len(title) < 4:
                    continue
                items.append(
                    {
                        "title": title[:120],
                        "url": str(row.get("新闻链接") or row.get("url") or f"https://finance.eastmoney.com/a/{code}.html"),
                        "time": str(row.get("发布时间") or row.get("time") or ""),
                        "source": str(row.get("文章来源") or row.get("source") or "东方财富"),
                    }
                )
    except Exception:
        pass
    return items


@app.post("/api/v1/cn/pipeline/run")
async def trigger_pipeline():
    """手动触发每日推荐管线（异步执行）"""
    from recommend import run_daily_recommend
    import threading

    def _run():
        try:
            run_daily_recommend()
        except Exception as e:
            print(f"管线运行异常: {e}")

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    return {"status": "started", "message": "管线已异步启动"}


def _atr_price_levels(ref_price: float, kline_df=None) -> dict:
    """做多口径：止损 < 买入 < 目标。目标/止损一律相对同一参考价（优先实时价）。"""
    buy = float(ref_price or 0)
    if buy <= 0:
        return {"buy_price": 0.0, "target_price": 0.0, "stop_price": 0.0}

    atr = None
    if kline_df is not None and len(kline_df) >= 14:
        try:
            hi = kline_df["high"].astype(float)
            lo = kline_df["low"].astype(float)
            atr = float((hi - lo).rolling(14).mean().iloc[-1])
        except Exception:
            atr = None

    if atr and atr > 0:
        # 约 1.5×ATR；目标至少 +3%，止损夹在 2%~7%
        target_pct = max(0.03, min(0.12, 1.5 * atr / buy))
        stop_pct = min(max(1.5 * atr / buy, 0.02), 0.07)
    else:
        target_pct, stop_pct = 0.04, 0.03

    target = round(buy * (1.0 + target_pct), 2)
    stop = round(buy * (1.0 - stop_pct), 2)
    if target <= buy:
        target = round(buy * 1.04, 2)
    if stop >= buy:
        stop = round(buy * 0.97, 2)
    return {
        "buy_price": round(buy, 2),
        "target_price": target,
        "stop_price": stop,
        "atr": round(atr, 4) if atr else None,
        "target_pct": round(target_pct, 4),
        "stop_pct": round(stop_pct, 4),
    }


def _sanitize_long_levels(buy: float, target: float, stop: float, kline_df=None) -> dict:
    """若目标≤买入或止损≥买入，按 ATR 相对买入价重算。"""
    buy = float(buy or 0)
    target = float(target or 0)
    stop = float(stop or 0)
    if buy <= 0:
        return {"buy_price": 0.0, "target_price": 0.0, "stop_price": 0.0}
    if target > buy > stop > 0:
        return {
            "buy_price": round(buy, 2),
            "target_price": round(target, 2),
            "stop_price": round(stop, 2),
        }
    return _atr_price_levels(buy, kline_df)


def _analyze_on_demand(symbol: str) -> dict | None:
    """对任意 A 股按需评分（非推荐缓存中的股票也支持）"""
    from datetime import datetime, timedelta
    from enriched_data import get_quote

    # 获取 K 线（至少 60 个交易日）
    start = (datetime.now() - timedelta(days=120)).strftime("%Y%m%d")
    try:
        kline = get_kline_sina(symbol, start_date=start)
    except Exception:
        return None
    if kline is None or kline.empty:
        return None

    # 股票名称
    try:
        stocks = get_stock_list()
        match = stocks[stocks["symbol"].str.contains(symbol, case=False, na=False)]
        name = str(match.iloc[0]["name"]) if not match.empty else symbol
    except Exception:
        name = symbol

    # ML 评分
    try:
        result = screener.score_stock(kline)
        if "error" in result:
            return None
    except Exception:
        return None

    # 实时报价：买入/目标/止损必须同一基准，禁止「现价买入 + 昨收目标」错位
    q = get_quote(symbol) or {}
    score = float(result.get("score", 0) or 0)
    latest_close = float(kline.iloc[-1]["close"])
    ref = float(q.get("price") or latest_close or 0)
    levels = _atr_price_levels(ref, kline)

    return {
        "symbol": symbol,
        "name": name,
        "score": round(score, 4),
        "score_raw": round(score, 4),
        "score_pct": round(score * 100, 1),
        "lgb_score": result.get("lgb_score", score),
        "sector_heat": result.get("sector_heat", 0.5),
        "buy_price": levels["buy_price"],
        "price": levels["buy_price"],
        "target_price": levels["target_price"],
        "stop_price": levels["stop_price"],
        "change_pct": float(q.get("change_pct", 0) or 0),
        "active_buy_ratio": float(q.get("active_buy_ratio", 0.5) or 0.5),
        "turnover": float(q.get("turnover", 0) or 0),
        "volume_ratio": float(q.get("volume_ratio", 1.0) or 1.0),
        "money_flow_pass": q.get("active_buy_ratio", 0.5) >= 0.52 if q else None,
        "on_demand": True,
        "note": "按需实时评分（ATR 目标相对现价）",
    }


@app.get("/api/v1/cn/chat")
async def chat(question: str = Query(..., description="用户问题（支持中文，URL 编码）")):
    """兼容旧问股接口（规则引擎，可选 LLM 增强）"""
    if not question or not question.strip():
        raise HTTPException(status_code=400, detail="question 不能为空")
    try:
        result = chat_reply(question)
        result["llm_enabled"] = bool(os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY"))
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"分析失败: {str(e)}")


@app.post("/api/v1/cn/deep-report")
async def deep_report_start(payload: dict = {}):
    """深度研报：输入股票代码，异步生成「值不值得买」详细报告。
    body: { "symbol": "000524", "trade_date": "2026-07-17"(可选), "engine": "deepseek|tradingagents" }
    """
    from deep_report_engine import start_job

    body = payload if isinstance(payload, dict) else {}
    symbol = str(body.get("symbol") or "").strip()
    if not symbol:
        raise HTTPException(status_code=400, detail="symbol 不能为空")
    engine = str(body.get("engine") or "auto")
    trade_date = body.get("trade_date") or None
    try:
        return start_job(symbol, trade_date=trade_date, engine_pref=engine)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建研报任务失败: {e}")


@app.get("/api/v1/cn/deep-report/{job_id}")
async def deep_report_status(job_id: str):
    """查询深度研报任务状态与结果。"""
    from deep_report_engine import get_job

    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在")
    # 轮询时不必回传超长 traceback
    out = {k: v for k, v in job.items() if k != "traceback"}
    return out


@app.get("/api/v1/cn/deep-report")
async def deep_report_list(limit: int = Query(20, ge=1, le=100)):
    """最近研报任务列表。"""
    from deep_report_engine import list_recent_jobs

    return {"items": list_recent_jobs(limit)}


@app.post("/api/v1/cn/backtest")
async def backtest(payload: dict = {}):
    """选股回测：基于真实历史 K 线计算收益"""
    cfg = payload if isinstance(payload, dict) else {}
    try:
        result = run_backtest(cfg)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"回测失败: {str(e)}")


# ============================================================
# 收藏追踪 API
# ============================================================

_wl_last_refresh_ts = 0.0


@app.get("/api/v1/cn/watchlist")
async def get_watchlist(
    status: str = "all",
    refresh: bool = Query(False, description="强制立刻重算 T+1/T+2/T+3"),
    user: dict = Depends(get_current_user),
):
    """获取当前登录用户的收藏列表（含实时价格）；默认最多每 2 分钟自动补算一次 T+n。"""
    import time as _time

    global _wl_last_refresh_ts
    now = _time.time()
    if refresh or (now - _wl_last_refresh_ts) >= 120:
        try:
            wl_recompute(force=True)
            _wl_last_refresh_ts = now
        except Exception:
            pass

    items = wl_get(status, user_id=int(user["id"]))
    # 批量获取实时价
    from enriched_data import get_quote
    for item in items:
        sym = item.get("symbol", "")
        try:
            q = get_quote(sym)
            if q:
                item["current_price"] = float(q.get("price", 0))
                item["current_change_pct"] = round(
                    (item["current_price"] - item["entry_price"]) / item["entry_price"] * 100, 2
                ) if item["entry_price"] else None
            else:
                item["current_price"] = None
                item["current_change_pct"] = None
        except Exception:
            item["current_price"] = None
            item["current_change_pct"] = None
    return {"watchlist": items, "count": len(items)}


@app.put("/api/v1/cn/watchlist/{symbol}")
async def update_watchlist_entry(
    symbol: str,
    payload: dict = {},
    user: dict = Depends(get_current_user),
):
    """更新收藏项的入场价或备注"""
    conn = wl_get_db()
    now = datetime.now().isoformat()
    sets = {"updated_at": now}
    if "entry_price" in payload:
        sets["entry_price"] = float(payload["entry_price"])
    if "notes" in payload:
        sets["notes"] = payload["notes"]
    set_clause = ", ".join([f"{k} = ?" for k in sets.keys()])
    values = list(sets.values()) + [symbol, int(user["id"])]
    cur = conn.execute(
        f"UPDATE watchlist SET {set_clause} WHERE symbol = ? AND user_id = ?",
        values,
    )
    conn.commit()
    n = cur.rowcount
    conn.close()
    if not n:
        raise HTTPException(status_code=404, detail=f"未找到 {symbol}")
    return {"success": True, "updated": symbol, "fields": list(sets.keys())}


@app.post("/api/v1/cn/watchlist")
async def add_watchlist(payload: dict = {}, user: dict = Depends(get_current_user)):
    """添加股票到收藏"""
    symbol = payload.get("symbol", "")
    name = payload.get("name", "")
    entry_price = payload.get("entry_price", 0)
    model_score = payload.get("model_score", 0)
    notes = payload.get("notes", "")

    if not symbol or not entry_price:
        raise HTTPException(status_code=400, detail="symbol 和 entry_price 必填")

    result = wl_add(
        symbol, name, float(entry_price), float(model_score), notes, user_id=int(user["id"])
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return {"success": True, "item": result}


@app.delete("/api/v1/cn/watchlist/{symbol}")
async def delete_watchlist(symbol: str, user: dict = Depends(get_current_user)):
    """从收藏移除"""
    result = wl_remove(symbol, user_id=int(user["id"]))
    if result["deleted"] == 0:
        raise HTTPException(status_code=404, detail=f"未找到 {symbol}")
    return {"success": True, "deleted": symbol}


@app.post("/api/v1/cn/watchlist/update")
async def update_watchlist_prices(
    force: bool = Query(True, description="是否用K线覆盖已有T+N"),
    user: Optional[dict] = Depends(get_current_user_optional),
    x_cron_secret: Optional[str] = Header(None, alias="X-Cron-Secret"),
):
    """按交易日K线重算/补全 T+1/T+2/T+3（站长或 cron）"""
    _require_cron_or_owner(user, x_cron_secret)
    try:
        result = wl_recompute(force=force)
        return {"success": True, "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"watchlist 更新失败: {e}")





@app.post("/api/v1/cn/backtest/stock")
async def backtest_stock(payload: dict = {}):
    """指定股票回测（无前视偏差）"""
    symbols = payload.get("symbols", [])
    if not symbols or not isinstance(symbols, list):
        raise HTTPException(status_code=400, detail="请输入至少1只股票代码")
    result = run_backtest_for_symbols(
        symbols,
        payload.get("startDate", "2026-06-01"),
        payload.get("endDate", "2026-07-06"),
        payload.get("holdingDays", 2)
    )
    return result

@app.get("/api/v1/cn/stock-search")
async def stock_search_ext(keyword: str = Query(..., description="代码/名称/拼音")):
    """扩展搜索：支持代码、中文名称、拼音首字母"""
    results = search_stocks_pinyin(keyword)
    return {"keyword": keyword, "results": results, "count": len(results)}


if __name__ == "__main__":
    import uvicorn
    print(f"启动 AlphaPilot API Server v0.2.0: {API_HOST}:{API_PORT}")
    uvicorn.run(app, host=API_HOST, port=API_PORT)


@app.get("/api/v1/cn/recommend/eod-s2/history")
async def get_eod_s2_history(
    date: str | None = Query(None, description="单日查询 YYYY-MM-DD"),
    date_from: str | None = Query(None, alias="from", description="起始日期 YYYY-MM-DD"),
    date_to: str | None = Query(None, alias="to", description="结束日期 YYYY-MM-DD"),
    limit: int = Query(90, ge=1, le=365),
):
    """尾盘狙击（S2）历史选股：日期列表 / 区间摘要 / 单日详情"""
    from eod_s2_history import query_history
    result = query_history(date=date, date_from=date_from, date_to=date_to, limit=limit)
    if result.get("error") == "invalid_date":
        raise HTTPException(status_code=400, detail=result.get("message") or "invalid date")
    return result


@app.get("/api/v1/cn/recommend/eod-s2")
async def get_eod_s2(date: str | None = Query(None, description="可选：查询历史某日 YYYY-MM-DD")):
    """S2最优版尾盘策略（当前日；也可 ?date= 查历史）。返回时注入实时价，选股快照保留在 pick_*。"""
    from eod_s2_history import archive_current_if_needed, load_current, load_history

    archive_current_if_needed()

    payload = None
    if date:
        payload = load_history(date)
        if not payload:
            cur = load_current()
            if cur and cur.get("date") == date:
                payload = cur
        if not payload:
            return {
                "date": date,
                "picks": [],
                "note": "该日无尾盘狙击记录",
                "strategy": "S2最优版",
                "found": False,
            }
        payload = dict(payload)
        payload["found"] = True
    else:
        payload = load_current()
        if not payload:
            return {
                "picks": [],
                "note": "S2策略结果未生成",
                "strategy": "S2最优版",
                "date": datetime.now().strftime("%Y-%m-%d"),
            }

    return _enrich_eod_s2_live(payload)


def _enrich_eod_s2_live(payload: dict) -> dict:
    """把 picks 的选股价存为 pick_price，price/change_pct 换成实时。"""
    out = dict(payload or {})
    picks = list(out.get("picks") or [])
    if not picks:
        return out
    try:
        from enriched_data import get_quotes_batch

        syms = []
        for p in picks:
            s = str(p.get("symbol") or "").strip()
            if s:
                syms.append(s[-6:] if len(s) >= 6 else s)
        quotes = get_quotes_batch(syms) if syms else {}
    except Exception:
        quotes = {}

    enriched = []
    for p in picks:
        item = dict(p)
        sym = str(item.get("symbol") or "").strip()
        bare = sym[-6:] if len(sym) >= 6 else sym
        pick_px = float(item.get("price") or item.get("buy_price") or 0)
        pick_chg = item.get("change_pct")
        item["pick_price"] = pick_px
        item["pick_change_pct"] = pick_chg
        q = quotes.get(bare) or quotes.get(sym) or {}
        live = float(q.get("price") or 0)
        if live > 0:
            item["price"] = live
            item["live_price"] = live
            if q.get("change_pct") is not None:
                item["change_pct"] = float(q.get("change_pct") or 0)
                item["live_change_pct"] = item["change_pct"]
            if q.get("volume_ratio") is not None:
                item["live_volume_ratio"] = q.get("volume_ratio")
        enriched.append(item)
    out["picks"] = enriched
    out["live_enriched"] = True
    out["live_asof"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return out


@app.get("/api/v1/cn/recommend/eod")
async def get_eod_recommend():
    """尾盘狙击独立选股（不与 Top 10 共用同一池子）"""
    import json as _json, urllib.request as _urllib, os as _os, datetime as _dt
    
    # 0. 优先读 14:00 管线缓存
    _cf = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "output", "eod_sniper_picks.json")
    if _os.path.isfile(_cf):
        try:
            with open(_cf) as _f:
                _c = _json.load(_f)
            if _c.get("stocks"):
                _c["from_cache"] = True
                _c["fetched_at"] = _dt.datetime.now().isoformat()
                return _c
        except Exception:
            pass
    
    # 1. 获取全量推荐并注入实时行情
    data = _read_recommend_cache()
    raw = data.get("recommendations", data.get("items", []))
    if not raw:
        return {"stocks": [], "message": "无候选数据"}
    
    # 用 _normalize_recommend_item 注入实时价格（不走 HTTP）
    live_data = []
    for it in raw[:50]:
        try:
            item = _normalize_recommend_item(it)
            live_data.append(item)
        except Exception:
            live_data.append(it)
    
    # 3. 尾盘专属筛选逻辑
    candidates = []
    for s in live_data:
        chg = float(s.get("change_pct", 0) or 0)
        abr = float(s.get("active_buy_ratio", 0) or 0)
        net = float(s.get("main_net", 0) or 0)
        vol_ratio = float(s.get("volume_ratio", 0) or 0)
        phase = s.get("money_phase", "")
        score = float(s.get("score", 0) or 0)
        
        # 排除涨停
        if chg >= 9.4:
            continue
        
        # 排除出货和诱多
        if phase in ("distribution", "suspicious", "pullback"):
            continue
        
        # ★ 尾盘核心条件：
        #   - 主力资金净流入（>0）
        #   - 主动买盘比例 >= 52%（吸筹/拉升信号）
        #   - 量比 > 0.8（不能严重缩量）
        #   - 评分 >= 0.2
        #   - 非过热
        if net > 0 and abr >= 0.52 and vol_ratio > 0.8 and score >= 0.2:
            if not s.get("overheat_warning"):
                candidates.append(s)
    
    # 4. 按综合得分排序（资金流强度 × 评分 × 量比）
    def _eod_score(s):
        _net = float(s.get("main_net", 0) or 0)
        _score = float(s.get("score", 0) or 0)
        _vol = float(s.get("volume_ratio", 0) or 1)
        _abr = float(s.get("active_buy_ratio", 0) or 0.5)
        # 资金流权重更高（尾盘看重资金确认）
        return _score * 0.3 + min(_net / 1e8, 0.5) * 0.4 + _abr * 0.2 + min(_vol / 3, 0.5) * 0.1
    
    candidates.sort(key=_eod_score, reverse=True)
    top3 = candidates[:3]
    
    # 5. 整理输出
    result = []
    for s in top3:
        result.append({
            "symbol": s.get("symbol"),
            "name": s.get("name"),
            "score": s.get("score"),
            "change_pct": s.get("change_pct"),
            "active_buy_ratio": s.get("active_buy_ratio"),
            "main_net": s.get("main_net"),
            "volume_ratio": s.get("volume_ratio"),
            "money_phase": s.get("money_phase"),
            "money_phase_label": s.get("money_phase_label"),
            "price": s.get("price") or s.get("buy_price"),
        })
    
    return {
        "stocks": result,
        "total_candidates": len(candidates),
        "note": "尾盘狙击独立筛选：资金净流入+主动买盘52%+量比>0.8+非涨停+非出货",
        "fetched_at": str(__import__("datetime").datetime.now()),
    }


import subprocess as _sp

_REFRESH_PID_FILE = "/tmp/refresh_all_data.pid"
_REFRESH_STATUS_FILE = "/tmp/refresh_all_data.status"

@app.post("/api/v1/cn/refresh-all-data")
async def trigger_refresh():
    """触发盘后数据全量刷新 (异步)"""
    if os.path.exists(_REFRESH_PID_FILE):
        try:
            with open(_REFRESH_PID_FILE) as f:
                pid = int(f.read().strip())
            os.kill(pid, 0)
            return {"status": "running", "message": "刷新任务已在运行中"}
        except (OSError, ValueError):
            pass
    script = "/home/ubuntu/alphapilot/refresh_all_data.py"
    p = _sp.Popen(
        [sys.executable, "-u", script],
        stdout=open("/tmp/refresh_all_data.log", "w"),
        stderr=_sp.STDOUT,
        start_new_session=True,
    )
    with open(_REFRESH_PID_FILE, "w") as f:
        f.write(str(p.pid))
    return {"status": "started", "pid": p.pid, "message": "刷新任务已启动"}

@app.get("/api/v1/cn/refresh-all-data/status")
async def get_refresh_status():
    """获取刷新进度"""
    default = {"step": "idle", "progress": 0, "detail": "无运行中的刷新任务"}
    try:
        if os.path.exists(_REFRESH_STATUS_FILE):
            with open(_REFRESH_STATUS_FILE) as f:
                return json.load(f)
    except Exception:
        pass
    return default

@app.get("/api/v1/cn/data-status")
async def get_data_status():
    """获取各数据文件的更新时间"""
    files = {
        "chip_data": "chip_data_all.json",
        "fund_flow": "data/fund_flow_history.json",
        "daily_recommend": "output/daily_recommend.json",
    }
    result = {}
    for name, path in files.items():
        full = os.path.join("/home/ubuntu/alphapilot", path)
        try:
            mtime = os.path.getmtime(full)
            size = os.path.getsize(full)
            result[name] = {
                "updated_at": datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M"),
                "size_kb": round(size / 1024, 1),
                "exists": True,
            }
        except OSError:
            result[name] = {"exists": False}
    return result

@app.post("/api/v1/cn/upload-chip-data")
async def upload_chip_data(data: dict):
    """接收本地上传的筹码数据"""
    import json
    path = "/home/ubuntu/alphapilot/chip_data_all.json"
    try:
        with open(path, "w") as f:
            json.dump(data, f)
        size = len(json.dumps(data))
        return {"status": "ok", "size": size, "path": path}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.get("/api/v1/cn/recommend/live")
async def get_live_recommend(top_n: int = 50, rerank: bool = False):
    """盘中实时推荐（含资金流合并 + 动态重排）"""
    import json as _json
    data = _read_recommend_cache()
    items = data.get("recommendations", data.get("items", []))
    
    # 对每条推荐添加实时资金流数据
    live_items = []
    for it in items[:top_n]:
        item = _normalize_recommend_item(it)
        sym = (item.get("symbol") or "").replace("sh", "").replace("sz", "")
        try:
            q = get_quote(sym)
            if q:
                item["main_inflow"] = q.get("main_inflow", 0)
                item["main_outflow"] = q.get("main_outflow", 0)
                item["main_net"] = q.get("main_net", 0)
                item["_data_source"] = "live"
                live_items.append(item)
                continue
        except Exception:
            pass
        item["_data_source"] = "daily_recommend"
        live_items.append(item)
    
    if rerank and live_items:
        def _score(x):
            s = float(x.get("score", 0) or 0)
            net = float(x.get("main_net", 0) or 0)
            return s * 0.4 + min(net / 5e7, 0.3) * 0.3 + (float(x.get("active_buy_ratio", 0.5) or 0.5) - 0.4) * 0.3
        live_items.sort(key=_score, reverse=True)
        return {
            "data": live_items[:top_n],
            "rerank": True,
            "ts": int(__import__("time").time()),
        }
    
    return {
        "data": live_items[:top_n],
        "rerank": False,
        "ts": int(__import__("time").time()),
    }



@app.get("/api/v1/cn/features")
async def get_features():
    """获取功能开关列表（根据用户角色过滤）"""
    flags = _load_json(_FEATURE_FLAGS_PATH)
    features = flags.get("features", {})
    user_role = "free"  # 默认 free
    result = {}
    for key, cfg in features.items():
        if cfg.get("enabled", False):
            roles = cfg.get("access_roles", ["free"])
            has_access = user_role in roles
            result[key] = {
                "enabled": True,
                "has_access": has_access,
                "label": cfg.get("label", key)
            }
        else:
            result[key] = {"enabled": False, "has_access": False, "label": cfg.get("label", key)}
    return {"features": result, "user_role": user_role}


@app.get("/api/v1/cn/paper-trading")
async def get_paper_trading(user: dict = Depends(get_current_user)):
    """模拟盘交易数据（含实时价格+前端计算字段）— 仅本人可见"""
    import json as _ptj, datetime as _ptdt, urllib.request as _pt_ur
    path = _paper_path_for_user(user)
    data = _load_json(path)
    if not data:
        if user.get("is_owner"):
            data = _load_json(_PAPER_TRADING_PATH) or _empty_paper_account(user)
        else:
            data = _empty_paper_account(user)
    data = dict(data)
    data["owner_mode"] = bool(user.get("is_owner"))
    data["personal"] = not bool(user.get("is_owner"))
    data["user_id"] = int(user["id"])
    acct = data.get("account") or {}
    if not isinstance(acct, dict):
        acct = {}
        data["account"] = acct
    trades = data.get("trade_log") or []
    if not isinstance(trades, list):
        trades = []
        data["trade_log"] = trades
    cash = float(acct.get("cash", 0) or 0)
    mv = float(acct.get("market_value", 0) or 0)
    acct["total_assets"] = round(cash + mv, 2)
    
    today = _ptdt.date.today().strftime("%Y-%m-%d")
    daily_settled = trade_count = win_count = total_sold = settled_pnl = 0
    for t in trades:
        a = t.get("action","")
        pn = float(t.get("pnl",0) or 0)
        if t.get("time","").startswith(today) and "卖出" in a:
            daily_settled += pn
        if a == "买入": trade_count += 1
        if "卖出" in a:
            total_sold += 1
            if pn > 0: win_count += 1
            settled_pnl += pn
    
    fp = float(acct.get("float_pnl", 0) or 0)
    acct["daily_pnl_amount"] = round(daily_settled + fp, 2)
    used = float(acct.get("used_capital", 0) or max(1, cash + mv))
    acct["daily_pnl_pct"] = round((daily_settled + fp) / used * 100, 2) if used > 0 else 0.0
    acct["trade_count"] = trade_count
    acct["win_rate"] = round(win_count / total_sold * 100, 1) if total_sold > 0 else 50.0
    # max_drawdown / total_pnl_* 在实时市值刷新后再算（见下方）
    
    data["next_execution"] = {
        "v19_daily": "09:36",
        "s2_eod": "14:45",
        "eod_sniper": "14:45",
    }

    # 协议字段（闭环）
    if "position_exposure" not in data:
        try:
            _rec = _load_json(_fl_path("/home/ubuntu/alphapilot/output/daily_recommend.json"))
            data["position_exposure"] = _rec.get("position_exposure", 1.0)
            data.setdefault("market_env_flags", _rec.get("market_env_flags") or {})
        except Exception:
            data["position_exposure"] = 1.0
    try:
        _expo = float(data.get("position_exposure") or 1.0)
    except Exception:
        _expo = 1.0
    _top_n = int(data.get("recommend_top_n") or (1 if 0 < _expo < 0.5 else (0 if _expo <= 0 else 2)))
    _pool_n = int(data.get("recommend_pool_n") or (10 if 0 < _expo < 0.5 else 50))
    data.setdefault("recommend_top_n", _top_n)
    data.setdefault("recommend_pool_n", _pool_n)
    data.setdefault("protocol", {
        "name": "tradable_top2",
        "entry": "T+1 open skip if limit-up",
        "exit": "T+2 close",
        "top_n": _top_n,
        "pool_n": _pool_n,
        "exposure_ladder": "v2_severe_crash",
    })

    # 人工确认闸门摘要（前端过目区）
    try:
        from order_tickets import list_tickets, load_broker_connection, public_broker_connection

        pending = list_tickets(user, status="pending_review", today_only=True)
        data["pending_orders"] = pending
        data["approval_gate"] = {
            "enabled": os.environ.get("REQUIRE_ORDER_APPROVAL", "1").strip() not in (
                "0",
                "false",
                "no",
                "off",
            ),
            "pending_n": len(pending),
        }
        data["broker_connection"] = public_broker_connection(load_broker_connection(user))
    except Exception as e:
        data["pending_orders"] = []
        data["approval_gate"] = {"enabled": True, "pending_n": 0, "error": str(e)}
    
    # 实时价格 + 金额字段
    for s in data.get("strategies", []):
        strat_cost = strat_mv = 0.0
        for p in s.get("positions", []):
            sym = p.get("symbol","")
            if not sym: continue
            prefix = "sh" if sym.startswith("6") else "sz"
            try:
                r = _pt_ur.urlopen("https://qt.gtimg.cn/q=" + prefix + sym, timeout=5)
                vals = r.read().decode("gbk").split('"')[1].split("~")
                if len(vals) > 3:
                    lp = float(vals[3]) or float(vals[4])
                    if lp > 0:
                        cost = float(p.get("buy_price",0) or p.get("entry_price",0) or 0)
                        qty = int(p.get("quantity",0) or 0)
                        p["current_price"] = round(lp, 2)
                        p["entry_price"] = float(p.get("entry_price") or cost or 0)
                        pnl = (lp - cost) / cost * 100 if cost > 0 else 0
                        p["pnl_pct"] = round(pnl, 2)
                        p["pnl_amount"] = round((lp - cost) * qty, 2) if qty else 0
            except: pass
            cost = float(p.get("buy_price",0) or p.get("entry_price",0) or 0)
            cur = float(p.get("current_price",0) or cost)
            qty = int(p.get("quantity",0) or 0)
            p["cost_amount"] = round(cost * qty, 2)
            p["market_amount"] = round(cur * qty, 2)
            strat_cost += p["cost_amount"]
            strat_mv += p["market_amount"]
        s["pnl_pct"] = round((strat_mv - strat_cost) / strat_cost * 100, 2) if strat_cost > 0 else float(s.get("pnl_pct") or 0)
        s["used"] = round(strat_cost, 2)
        # 对外策略名（不暴露内部模型代号）
        sid = str(s.get("id") or "")
        if sid == "v19_daily" or "VM2.5" in str(s.get("name") or ""):
            s["name"] = "日频精选"
        elif sid in ("s2_eod", "eod_sniper") or "尾盘" in str(s.get("name") or ""):
            s["name"] = "尾盘狙击"

    # 共用资金：各策略不再各锁一半；allocated 仅作权益参考，可用看账户现金
    _shared = str(data.get("capital_mode") or os.environ.get("SHARED_CAPITAL", "1")).strip().lower() in (
        "1", "true", "yes", "on", "shared",
    )
    data["capital_mode"] = "shared" if _shared else "split"
    _equity = float(acct.get("total_assets") or 0) or (float(acct.get("cash") or 0) + float(acct.get("market_value") or 0))
    for s in data.get("strategies", []):
        s["capital_mode"] = data["capital_mode"]
        if _shared:
            s["allocated"] = round(_equity, 2)
    
    total_mv = total_cost = 0
    for s in data.get("strategies", []):
        for p in s.get("positions", []):
            pr = float(p.get("current_price",0) or p.get("buy_price",0))
            q = p.get("quantity",0)
            total_mv += pr * q
            total_cost += float(p.get("buy_price",0) or 0) * q
    fp = total_mv - total_cost
    cash_now = float(acct.get("cash", 0) or 0)
    initial = float(
        acct.get("initial_capital")
        or data.get("initial_capital")
        or 1_000_000
    )
    # 累计收益 = 权益相对本金（注入已计入 initial_capital 时不再叠加 capital_injections）
    equity_now = cash_now + total_mv
    total_pnl_amount = equity_now - initial
    acct["initial_capital"] = initial
    acct["market_value"] = round(total_mv, 2)
    acct["total_assets"] = round(equity_now, 2)
    acct["float_pnl"] = round(fp, 2)
    acct["settled_pnl"] = round(settled_pnl, 2)
    acct["total_pnl_amount"] = round(total_pnl_amount, 2)
    acct["total_pnl_pct"] = round(total_pnl_amount / initial * 100, 2) if initial > 0 else 0.0
    acct["asset_pnl_pct"] = acct["total_pnl_pct"]
    acct["used_capital"] = round(total_cost, 2)
    acct["daily_pnl_amount"] = round(fp + daily_settled, 2)
    used = total_cost if total_cost > 0 else max(1.0, equity_now)
    acct["daily_pnl_pct"] = round((fp + daily_settled) / used * 100, 2) if used > 0 else 0.0
    acct["position_exposure"] = data.get("position_exposure")

    # 最大回撤：以本金为起点，按已实现盈亏近似权益曲线，末端加上浮动盈亏
    eq_curve = [initial]
    ce = initial
    for t in sorted(trades, key=lambda x: x.get("time", "")):
        if "卖出" in (t.get("action") or ""):
            ce += float(t.get("pnl", 0) or 0)
            eq_curve.append(ce)
    eq_curve.append(ce + fp)
    peak = eq_curve[0]
    dd = 0.0
    for eq in eq_curve:
        if eq > peak:
            peak = eq
        if peak > 0:
            d = (peak - eq) / peak * 100
            if d > dd:
                dd = d
    acct["max_drawdown"] = round(-dd, 2)

    # 闭环报告摘要（audit / oos）— 仅站长系统盘
    if user.get("is_owner"):
        def _loop_summary(path, kind):
            try:
                raw = _load_json(_fl_path(path))
                if not raw:
                    return None
                if kind == "audit":
                    return {
                        "generated_at": raw.get("generated_at"),
                        "counts": raw.get("counts"),
                        "kpi": raw.get("kpi"),
                        "checklist": raw.get("protocol_checklist"),
                        "position_exposure_today": raw.get("position_exposure_today"),
                    }
                gate = raw.get("gate") or {}
                return {
                    "generated_at": raw.get("generated_at"),
                    "verdict": gate.get("verdict"),
                    "reason": gate.get("reason"),
                    "oos_window": raw.get("oos_window"),
                    "kpi": raw.get("kpi"),
                    "reference_window": {
                        "window": (raw.get("reference_window") or {}).get("window"),
                        "in_sample_risk": (raw.get("reference_window") or {}).get("in_sample_risk"),
                        "kpi": (raw.get("reference_window") or {}).get("kpi"),
                    } if raw.get("reference_window") else None,
                }
            except Exception:
                return None

        data["loop"] = {
            "audit": _loop_summary("/home/ubuntu/alphapilot/output/paper_tradable_audit.json", "audit"),
            "oos": _loop_summary("/home/ubuntu/alphapilot/output/oos_tradable_top2.json", "oos"),
            "empty_reason": data.get("empty_reason"),
            "cron": {
                "signals": "09:36 Mon-Fri",
                "eod": "14:45 Mon-Fri",
                "audit": "16:10 Mon-Fri",
                "oos": "Sat 10:00",
            },
        }
    else:
        data["next_execution"] = {}
        data["protocol"] = {"name": "personal", "entry": "manual", "exit": "manual", "top_n": 0, "pool_n": 0}
        data["loop"] = {
            "audit": None,
            "oos": None,
            "empty_reason": data.get("empty_reason") or "personal",
            "cron": {},
        }
    
    return data


@app.get("/api/v1/cn/paper-trading/audit")
async def get_paper_trading_audit(user: dict = Depends(get_current_user)):
    """模拟盘可交易协议日复盘全文（仅站长系统盘）"""
    if not user.get("is_owner"):
        raise HTTPException(status_code=403, detail="系统复盘仅站长可见")
    return _load_json(_fl_path("/home/ubuntu/alphapilot/output/paper_tradable_audit.json")) or {"error": "not_ready"}


@app.get("/api/v1/cn/paper-trading/oos")
async def get_paper_trading_oos(user: dict = Depends(get_current_user)):
    """Top2 样本外验收报告全文（仅站长系统盘）"""
    if not user.get("is_owner"):
        raise HTTPException(status_code=403, detail="系统 OOS 仅站长可见")
    return _load_json(_fl_path("/home/ubuntu/alphapilot/output/oos_tradable_top2.json")) or {"error": "not_ready"}


@app.post("/api/v1/cn/paper-trading/update")
async def update_paper_trading(
    payload: dict = {},
    user: Optional[dict] = Depends(get_current_user_optional),
    x_cron_secret: Optional[str] = Header(None, alias="X-Cron-Secret"),
):
    """更新模拟盘数据：cron/站长写系统盘；登录用户写本人个人盘"""
    secret = (os.environ.get("CRON_API_SECRET") or "").strip()
    cron_ok = bool(secret and x_cron_secret and x_cron_secret == secret)
    if cron_ok or (user and user.get("is_owner")):
        path = _PAPER_TRADING_PATH
    elif user:
        path = _paper_path_for_user(user)
    else:
        raise HTTPException(status_code=401, detail="未登录")

    current = _load_json(path) or (_empty_paper_account(user) if user and not user.get("is_owner") else {})
    if not current:
        current = {"account": {}, "strategies": [], "trade_log": []}
    
    # 更新 account 级字段
    if "account" in payload:
        current.setdefault("account", {})
        for k, v in payload["account"].items():
            current["account"][k] = v
    
    # 更新策略级字段
    if "strategies" in payload:
        current.setdefault("strategies", [])
        for upd in payload["strategies"]:
            for i, s in enumerate(current["strategies"]):
                if s["id"] == upd.get("id"):
                    for k, v in upd.items():
                        if k != "id":
                            current["strategies"][i][k] = v
    
    # 追加交易日志
    if "trade_log_entry" in payload:
        current.setdefault("trade_log", [])
        current["trade_log"].append(payload["trade_log_entry"])
    
    current["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    _save_json(path, current)
    return {"success": True, "updated_at": current["updated_at"]}


# ─── 人工确认订单闸门 + 券商连接配置（多租户）───


@app.get("/api/v1/cn/live-orders")
async def get_live_orders(
    status: Optional[str] = None,
    today_only: bool = True,
    user: dict = Depends(get_current_user),
):
    """今日待确认 / 已确认订单列表（按登录用户隔离）。"""
    from order_tickets import list_tickets, load_broker_connection, public_broker_connection

    tickets = list_tickets(user, status=status, today_only=today_only)
    broker = public_broker_connection(load_broker_connection(user))
    pending = [t for t in tickets if t.get("status") == "pending_review"]
    expired = [t for t in tickets if t.get("status") == "expired"]
    return {
        "tickets": tickets,
        "pending": pending,
        "pending_n": len(pending),
        "expired": expired,
        "expired_n": len(expired),
        "expire_hhmm": os.environ.get("ORDER_TICKET_EXPIRE_HHMM", "14:55"),
        "broker": broker,
        "approval_required": os.environ.get("REQUIRE_ORDER_APPROVAL", "1").strip() not in (
            "0",
            "false",
            "no",
            "off",
        ),
    }


@app.post("/api/v1/cn/live-orders/approve")
async def approve_live_orders(payload: dict = {}, user: dict = Depends(get_current_user)):
    """确认买入：写入模拟盘 signals；若已配置真仓适配器则标记 exec_mode=live（P1 Agent 拉取）。"""
    from order_tickets import approve_tickets, sync_approved_to_paper_signals

    ids = payload.get("ticket_ids") or payload.get("ids") or []
    if isinstance(ids, str):
        ids = [ids]
    if not ids:
        raise HTTPException(status_code=400, detail="缺少 ticket_ids")
    weights = payload.get("weights") or {}
    done = approve_tickets(ids, user=user, weights=weights)
    if not done:
        raise HTTPException(status_code=404, detail="没有可确认的待审订单（可能已过期或已处理）")

    pt_path = _paper_path_for_user(user)
    synced = sync_approved_to_paper_signals(user=user, pt_path=pt_path)

    execute_now = bool(payload.get("execute_now"))
    exec_result = None
    if execute_now and user.get("is_owner"):
        # 仅站长可触发本机模拟执行；客户真仓由本机 Agent 拉取
        try:
            import subprocess

            r = subprocess.run(
                ["python3", "-u", "trade_executor.py"],
                cwd="/home/ubuntu/alphapilot",
                capture_output=True,
                text=True,
                timeout=120,
            )
            exec_result = {
                "returncode": r.returncode,
                "stdout_tail": (r.stdout or "")[-1500:],
                "stderr_tail": (r.stderr or "")[-500:],
            }
        except Exception as e:
            exec_result = {"error": str(e)}

    return {
        "success": True,
        "approved": done,
        "signals_synced": len(synced),
        "execute_now": execute_now,
        "exec_result": exec_result,
    }


@app.post("/api/v1/cn/live-orders/reject")
async def reject_live_orders(payload: dict = {}, user: dict = Depends(get_current_user)):
    from order_tickets import reject_tickets

    ids = payload.get("ticket_ids") or payload.get("ids") or []
    if isinstance(ids, str):
        ids = [ids]
    if not ids:
        raise HTTPException(status_code=400, detail="缺少 ticket_ids")
    done = reject_tickets(ids, user=user, reason=str(payload.get("reason") or "user_reject"))
    return {"success": True, "rejected": done}


@app.get("/api/v1/cn/broker-connection")
async def get_broker_connection(user: dict = Depends(get_current_user)):
    """客户券商对接配置（QMT 端口/账号等）。真连由本机 Agent 使用，云端只存配置。"""
    from order_tickets import load_broker_connection, public_broker_connection

    return public_broker_connection(load_broker_connection(user))


@app.put("/api/v1/cn/broker-connection")
async def put_broker_connection(payload: dict = {}, user: dict = Depends(get_current_user)):
    from order_tickets import save_broker_connection

    try:
        return save_broker_connection(payload or {}, user=user)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/v1/cn/live-orders/agent/pull")
async def agent_pull_orders(
    x_agent_token: Optional[str] = Header(None, alias="X-Agent-Token"),
    user_id: Optional[str] = None,
):
    """本机 QMT Agent 拉取已确认、待提交的真仓单（P1）。

    鉴权：Broker 配置里的 agent_token。多租户用 user_id 区分。
    """
    from order_tickets import (
        list_tickets,
        load_broker_connection,
        mark_ticket_status,
    )

    uid = user_id or "owner"
    broker = load_broker_connection(user_id=uid)
    expect = str((broker.get("config") or {}).get("agent_token") or "")
    if not expect or not x_agent_token or x_agent_token != expect:
        raise HTTPException(status_code=401, detail="无效 Agent Token")
    if not broker.get("enabled") or broker.get("adapter") == "paper_only":
        return {"orders": [], "note": "broker not enabled for live"}

    orders = [
        t
        for t in list_tickets(user_id=uid, today_only=True)
        if t.get("status") == "approved" and t.get("exec_mode") == "live"
    ]
    # 标记为 submitted，避免重复拉取（Agent 成交后再回写 filled）
    for t in orders:
        mark_ticket_status(t["id"], "submitted", user_id=uid, extra={"pulled_by": "agent"})
    return {
        "orders": orders,
        "adapter": broker.get("adapter"),
        "account_id": (broker.get("config") or {}).get("account_id"),
        "trade_host": (broker.get("config") or {}).get("trade_host"),
        "trade_port": (broker.get("config") or {}).get("trade_port"),
        "quote_host": (broker.get("config") or {}).get("quote_host"),
        "quote_port": (broker.get("config") or {}).get("quote_port"),
    }


@app.post("/api/v1/cn/live-orders/agent/report")
async def agent_report_order(payload: dict = {}, x_agent_token: Optional[str] = Header(None, alias="X-Agent-Token")):
    """Agent 回报成交/失败。"""
    from order_tickets import load_broker_connection, mark_ticket_status

    uid = payload.get("user_id") or "owner"
    broker = load_broker_connection(user_id=uid)
    expect = str((broker.get("config") or {}).get("agent_token") or "")
    if not expect or not x_agent_token or x_agent_token != expect:
        raise HTTPException(status_code=401, detail="无效 Agent Token")
    tid = payload.get("ticket_id")
    status = payload.get("status")  # filled | failed
    if not tid or status not in ("filled", "failed"):
        raise HTTPException(status_code=400, detail="需要 ticket_id 与 status=filled|failed")
    row = mark_ticket_status(
        tid,
        status,
        user_id=uid,
        extra={
            "fill_price": payload.get("fill_price"),
            "fill_qty": payload.get("fill_qty"),
            "broker_order_id": payload.get("broker_order_id"),
            "error": payload.get("error"),
        },
    )
    if not row:
        raise HTTPException(status_code=404, detail="ticket not found")
    return {"success": True, "ticket": row}


@app.get("/api/v1/cn/overnight")
async def get_overnight():
    """隔夜美股信号"""
    import json as _json

# ═══ Feature Flags & Paper Trading Helpers ═══
import json as _fl_json
from pathlib import Path as _fl_path

_FEATURE_FLAGS_PATH = _fl_path("/home/ubuntu/alphapilot/data/feature_flags.json")
_PAPER_TRADING_PATH = _fl_path("/home/ubuntu/alphapilot/data/paper_trading.json")

def _load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return _fl_json.load(f)
    except Exception:
        return {}

def _save_json(path, data):
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            _fl_json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False

    path = "/home/ubuntu/alphapilot/output/overnight_signals.json"
    try:
        with open(path) as f:
            return _json.load(f)
    except Exception:
        return {"sentiment_score": 0, "judgment": "暂无隔夜数据", "fetched_at": ""}

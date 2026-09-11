"""实时资金流 - 东财单只接口 + 退避重试 + 腾讯备选"""
import math
import pandas as pd, json, threading, time, requests

_CACHE = {"df": None, "ts": 0, "last_symbols": set(), "lock": threading.Lock()}
CACHE_TTL = 30
_HEADERS = {"User-Agent": "Mozilla/5.0"}
_EM_FAILED_TS = 0  # 东财被封后暂避时间
_SKIP_SECS = 120  # 被封后等 2 分钟再试


def _abr_from_f84(v) -> float | None:
    """f84=主动买入占比(0-100)，/100 后须∈[0,1]。

    东财表头漂移/接口异常时会把净额当 f84（如 588409646 → abr 5,884,096，
    2026-08-19 / 09-02 / 09-09 case），越界一律置 None，由下游当缺失处理，
    避免垃圾值污染 money gate / export 合理性兜底。
    """
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if 0.0 <= f <= 100.0:
        return round(f / 100.0, 4)
    return None


def _chg_from_f170(v) -> float | None:
    """f170=涨跌幅%，须∈[-30,30]（A 股涨跌停上限以内，含北交所 30%）。

    漂移时会塞进大数（如 273/489/1001/-254），越界置 None。
    """
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if -30.0 <= f <= 30.0:
        return round(f, 2)
    return None


def _cleanf(x) -> float | None:
    """DataFrame NaN/非法值 -> None（供读取端用），合法值原样返回。"""
    try:
        f = float(x)
        return None if math.isnan(f) else f
    except (TypeError, ValueError):
        return None

def _em_get_one(bare: str) -> dict | None:
    """获取单只股票东财资金流，带退避"""
    global _EM_FAILED_TS
    if time.time() < _EM_FAILED_TS:
        return None
    market = "1" if bare.startswith("6") else "0"
    try:
        r = requests.get(
            "https://push2.eastmoney.com/api/qt/stock/get",
            params={"secid": f"{market}.{bare}", "fields": "f43,f62,f66,f84,f170,f184,f185"},
            timeout=4, headers=_HEADERS
        )
        if r.status_code != 200:
            return None
        return r.json().get("data")
    except Exception:
        _EM_FAILED_TS = time.time() + _SKIP_SECS
        return None


def _fetch_batch(symbols: list[str]) -> pd.DataFrame:
    """按需拉取指定股票资金流"""
    rows = []
    for sym in symbols:
        bare = sym.replace("sh","").replace("sz","").replace("SH","").replace("SZ","")
        d = _em_get_one(bare)
        if d:
            main_net = float(d.get("f62") or 0)
            big_net = float(d.get("f184") or 0)
            xl_net = float(d.get("f185") or 0)
            abr = _abr_from_f84(d.get("f84"))     # 越界/缺失 -> None
            chg = _chg_from_f170(d.get("f170"))   # 越界/缺失 -> None
            rows.append({
                "symbol": bare,
                "main_net": main_net + big_net + xl_net,
                "main_inflow_raw": max(main_net + big_net + xl_net, 0),
                "main_outflow_raw": -min(main_net + big_net + xl_net, 0),
                "active_buy_ratio": abr,          # 允许 None(=缺失)
                "price": float(d.get("f43") or 0),
                "change_pct": chg,                # 允许 None(=缺失)
                "turnover": _cleanf(d.get("f66")),
            })
        time.sleep(0.2)
    return pd.DataFrame(rows)


def _get_cached_df(symbols: list[str]) -> pd.DataFrame:
    now = time.time()
    with _CACHE["lock"]:
        if _CACHE["df"] is None or (now - _CACHE["ts"]) > CACHE_TTL:
            t0 = time.time()
            _CACHE["df"] = _fetch_batch(symbols)
            _CACHE["ts"] = time.time()
            _CACHE["last_symbols"] = set(symbols)
            if len(_CACHE["df"]) > 0:
                print(f"[live_fund_flow] 拉取 {len(symbols)}只/实到{len(_CACHE['df'])}只 {time.time()-t0:.1f}s", flush=True)
            else:
                print(f"[live_fund_flow] 东财无数据({time.time()-t0:.1f}s), 用缓存/空", flush=True)
        return _CACHE["df"] if _CACHE["df"] is not None else pd.DataFrame()


def fetch_fund_flow(symbol: str) -> dict:
    df = _get_cached_df([symbol])
    sym = symbol.replace("sh","").replace("sz","").replace("SH","").replace("SZ","")
    row = df[df["symbol"] == sym]
    if row.empty:
        return {"found": False}
    r = row.iloc[0]
    return {"found": True, "name": "", "main_net": float(r["main_net"]),
            "price": float(r["price"]), "change_pct": _cleanf(r["change_pct"]),
            "turnover": _cleanf(r["turnover"])}


def batch_fund_flow(symbols: list) -> dict:
    if not symbols:
        return {}
    df = _get_cached_df(symbols)
    result = {}
    for sym in symbols:
        bare = sym.replace("sh","").replace("sz","").replace("SH","").replace("SZ","")
        row = df[df["symbol"] == bare]
        if row.empty:
            result[sym] = {"found": False}
            continue
        r = row.iloc[0]
        result[sym] = {
            "found": True, "name": "",
            "main_net": float(r["main_net"]),
            "main_inflow": float(r["main_inflow_raw"]),
            "main_outflow": float(r["main_outflow_raw"]),
            "active_buy_ratio": _cleanf(r["active_buy_ratio"]),
            "price": float(r["price"]), "change_pct": _cleanf(r["change_pct"]),
            "turnover": _cleanf(r["turnover"]),
        }
    return result


if __name__ == "__main__":
    d = fetch_fund_flow("000001")
    print(json.dumps(d, ensure_ascii=False))

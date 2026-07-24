"""实时资金流 - akshare同花顺即时接口 + 内存缓存"""
import time
import threading
import warnings
import pandas as pd

warnings.filterwarnings("ignore")

_CACHE = {"df": None, "ts": 0, "lock": threading.Lock()}
CACHE_TTL = 60  # 缓存60秒


def _parse_amount(s) -> float:
    """解析 '29.96亿' / '1234万' / '0' -> float"""
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return 0.0
    s = str(s).strip()
    try:
        if s.endswith("亿"):
            return float(s[:-1]) * 1e8
        elif s.endswith("万"):
            return float(s[:-1]) * 1e4
        else:
            return float(s)
    except (ValueError, AttributeError):
        return 0.0


def _parse_pct(s) -> float:
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return 0.0
    try:
        return float(str(s).replace("%", "").strip())
    except (ValueError, AttributeError):
        return 0.0


def _norm_code(symbol) -> str:
    s = str(symbol or "").replace("sh", "").replace("sz", "").replace("bj", "")
    s = s.replace("SH", "").replace("SZ", "").replace("BJ", "")
    s = s.strip()
    if s.isdigit():
        return s.zfill(6)
    return s[-6:] if len(s) >= 6 else s


def _fetch_all_fund_flow() -> pd.DataFrame:
    """拉取全市场资金流（5194只，~13秒）"""
    import akshare as ak

    df = ak.stock_fund_flow_individual(symbol="即时")
    df["code6"] = df["股票代码"].map(_norm_code)
    df["main_inflow_raw"] = df["流入资金"].apply(_parse_amount)
    df["main_outflow_raw"] = df["流出资金"].apply(_parse_amount)
    # 同花顺「净额」优先
    if "净额" in df.columns:
        df["main_net_raw"] = df["净额"].apply(_parse_amount)
    else:
        df["main_net_raw"] = df["main_inflow_raw"] - df["main_outflow_raw"]
    df["active_buy_ratio"] = df.apply(
        lambda r: round(
            r["main_inflow_raw"] / (r["main_inflow_raw"] + r["main_outflow_raw"]), 4
        )
        if (r["main_inflow_raw"] + r["main_outflow_raw"]) > 0
        else 0.5,
        axis=1,
    )
    return df


def _get_cached_df() -> pd.DataFrame:
    """获取缓存的全市场数据（60秒内复用）"""
    now = time.time()
    with _CACHE["lock"]:
        if _CACHE["df"] is None or (now - _CACHE["ts"]) > CACHE_TTL:
            t0 = time.time()
            _CACHE["df"] = _fetch_all_fund_flow()
            _CACHE["ts"] = time.time()
            print(
                f"[live_fund_flow] 缓存刷新：{len(_CACHE['df'])}只，耗时 {time.time()-t0:.1f}s",
                flush=True,
            )
        return _CACHE["df"]


def _row_to_dict(symbol: str, r) -> dict:
    return {
        "symbol": symbol,
        "name": r.get("股票简称", ""),
        "active_buy_ratio": float(r["active_buy_ratio"]),
        "main_inflow": float(r.get("main_inflow_raw", 0)),
        "main_outflow": float(r.get("main_outflow_raw", 0)),
        "main_net": float(r.get("main_net_raw", 0) or 0),
        "price": float(r.get("最新价", 0) or 0),
        "change_pct": _parse_pct(r.get("涨跌幅", 0)),
        "turnover": _parse_pct(r.get("换手率", 0)),
        "found": True,
    }


def fetch_fund_flow(symbol: str) -> dict:
    """单只股票实时资金（从缓存查，<1ms）"""
    df = _get_cached_df()
    sym = _norm_code(symbol)
    row = df[df["code6"] == sym]
    if row.empty:
        return {"symbol": symbol, "active_buy_ratio": 0.5, "found": False}
    return _row_to_dict(symbol, row.iloc[0])


def batch_fund_flow(symbols: list) -> dict:
    """批量查（共享一次缓存）"""
    df = _get_cached_df()
    result = {}
    for sym in symbols:
        s = _norm_code(sym)
        row = df[df["code6"] == s]
        if not row.empty:
            result[sym] = _row_to_dict(sym, row.iloc[0])
        else:
            result[sym] = {"symbol": sym, "active_buy_ratio": 0.5, "found": False}
    return result


if __name__ == "__main__":
    # 兼容旧 cron：转调盘中池子重排
    try:
        from morning_live_fund_select import main as morning_main

        raise SystemExit(morning_main())
    except ImportError:
        test = ["603228", "002670", "000893", "002115", "600116"]
        t0 = time.time()
        res = batch_fund_flow(test)
        print(f"\n耗时 {time.time()-t0:.2f}s")
        for sym in test:
            d = res[sym]
            print(
                f"  {sym} {d.get('name','')}: ABR={d['active_buy_ratio']:.4f} "
                f"净额={d.get('main_net')} 涨跌={d.get('change_pct')}%"
            )

"""实时资金流 - 东财单只接口 + 批量快照 + 退避重试

2026-08-18 修复（数据正确性）：
  旧实现把 f184(主力净占比%)/f185 当作"大单/超大单净额"叠加进 main_net，
  并把 f84(小单净额, 元) 当作"主动买占比(abr)"，产生垃圾值污染导出。
  现改用 CapitalPulse 已验证的东财字段语义（与 akshare stock_individual_fund_flow 一致）：
    f62  = 主力净流入(元)      f66 = 超大单净额(元)
    f72  = 大单净额(元)        f78 = 中单净额(元)
    f84  = 小单净额(元)        f124 = 数据时间戳
  批量 ulist.np/get + push2delay 回退 + fltt=2/invt=2/np=1/ut token。
  主动买占比(abr) 本接口不提供，不再伪造 —— 下游 live_abr 自动回退到腾讯外盘/内盘口径。
"""
import pandas as pd
import json
import threading
import time
import requests

_CACHE = {"df": None, "ts": 0, "last_symbols": set(), "lock": threading.Lock()}
CACHE_TTL = 30
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Referer": "https://data.eastmoney.com/",
}
_EM_FAILED_TS = 0  # 东财被封后暂避时间
_SKIP_SECS = 120  # 被封后等 2 分钟再试

_ULIST_URL = "https://push2.eastmoney.com/api/qt/ulist.np/get"
_ULIST_URL_FALLBACK = "https://push2delay.eastmoney.com/api/qt/ulist.np/get"
_UT = "7eea3edcaed734bea9telecast"
_FLOW_FIELDS = "f2,f3,f12,f14,f62,f66,f72,f78,f84,f124"


def _em_get_batch(secids: list[str]) -> dict[str, dict]:
    """批量拉取个股资金流快照（东财 ulist），带退避与 push2delay 回退。

    返回 {bare6: {main_net, super_large_net, large_net, mid_net, small_net,
                  price, change_pct, source_time}}
    """
    global _EM_FAILED_TS
    if time.time() < _EM_FAILED_TS:
        return {}
    params = {
        "secids": ",".join(secids),
        "fields": _FLOW_FIELDS,
        "fltt": "2",
        "invt": "2",
        "np": "1",
        "ut": _UT,
        "_": str(int(time.time() * 1000)),
    }
    urls = (_ULIST_URL, _ULIST_URL_FALLBACK)
    last_err: Exception | None = None
    for url in urls:
        try:
            r = requests.get(url, params=params, timeout=8, headers=_HEADERS)
            if r.status_code != 200:
                last_err = RuntimeError(f"status {r.status_code}")
                continue
            payload = r.json()
            diff = (payload.get("data") or {}).get("diff") or []
            out = {}
            for item in diff:
                if not isinstance(item, dict):
                    continue
                code = str(item.get("f12") or "").strip()
                if not code or not code.isdigit() or len(code) != 6:
                    continue
                try:
                    source_time = int(item.get("f124") or 0)
                except (TypeError, ValueError):
                    source_time = 0
                out[code] = {
                    "main_net": float(item.get("f62") or 0),
                    "super_large_net": float(item.get("f66") or 0),
                    "large_net": float(item.get("f72") or 0),
                    "mid_net": float(item.get("f78") or 0),
                    "small_net": float(item.get("f84") or 0),
                    "price": float(item.get("f2") or 0),
                    "change_pct": float(item.get("f3") or 0),
                    "source_time": source_time,
                }
            return out
        except Exception as e:  # noqa
            last_err = e
            time.sleep(1.0)
    _EM_FAILED_TS = time.time() + _SKIP_SECS
    if last_err is not None:
        print(f"[live_fund_flow] 东财批量资金流失败: {last_err}", flush=True)
    return {}


def _fetch_batch(symbols: list[str]) -> pd.DataFrame:
    """批量拉取指定股票资金流（按 50 只/请求分块）。"""
    rows = []
    chunk = 50
    for i in range(0, len(symbols), chunk):
        codes = [s.replace("sh", "").replace("sz", "").replace("SH", "").replace("SZ", "")
                 for s in symbols[i:i + chunk]]
        secids = [f"{'1' if c.startswith('6') else '0'}.{c}" for c in codes]
        data = _em_get_batch(secids)
        for bare in codes:
            d = data.get(bare)
            if not d or int(d.get("source_time") or 0) <= 0:
                continue
            main_net = float(d["main_net"])
            rows.append({
                "symbol": bare,
                "main_net": main_net,
                "super_large_net": float(d["super_large_net"]),
                "large_net": float(d["large_net"]),
                "mid_net": float(d["mid_net"]),
                "small_net": float(d["small_net"]),
                "main_inflow_raw": max(main_net, 0.0),
                "main_outflow_raw": -min(main_net, 0.0),
                "price": float(d["price"]),
                "change_pct": float(d["change_pct"]),
            })
        if i + chunk < len(symbols):
            time.sleep(0.3)
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
    sym = symbol.replace("sh", "").replace("sz", "").replace("SH", "").replace("SZ", "")
    row = df[df["symbol"] == sym]
    if row.empty:
        return {"found": False}
    r = row.iloc[0]
    return {
        "found": True, "name": "", "main_net": float(r["main_net"]),
        "super_large_net": float(r["super_large_net"]),
        "large_net": float(r["large_net"]),
        "mid_net": float(r["mid_net"]),
        "small_net": float(r["small_net"]),
        "price": float(r["price"]), "change_pct": float(r["change_pct"]),
    }


def batch_fund_flow(symbols: list) -> dict:
    if not symbols:
        return {}
    df = _get_cached_df(symbols)
    result = {}
    for sym in symbols:
        bare = sym.replace("sh", "").replace("sz", "").replace("SH", "").replace("SZ", "")
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
            "super_large_net": float(r["super_large_net"]),
            "large_net": float(r["large_net"]),
            "mid_net": float(r["mid_net"]),
            "small_net": float(r["small_net"]),
            "price": float(r["price"]), "change_pct": float(r["change_pct"]),
        }
    return result


if __name__ == "__main__":
    d = fetch_fund_flow("000001")
    print(json.dumps(d, ensure_ascii=False))

"""
AlphaPilot 特征增强层 v2 —— 基于腾讯财经公开行情（东财在腾讯云被封，腾讯源可用）

提供信号（全部真实、批量、带重试+缓存）：
  - 实时盘口: 外盘/内盘 → 主动买入占比 (active_buy_ratio)  ← 短线最强资金信号
  - 换手率 / 量比 / 振幅 / 涨跌幅
  - 总市值(规模因子) / 市盈率TTM / 市净率
  - 涨停价 / 跌停价

说明：
  - 历史主力资金/行业映射因东财被封无法获取，故训练期只用「静态规模+估值」类特征
    （市值/PE/PB 变化缓慢，可用当前值近似历史），推理期再用实时主动买卖占比做资金门控。
  - 2026-07-07：发现 mootdx（通达信 TCP 7709）在腾讯云可连通，可获取真实财务数据
    包括总资产/净资产/主营收入/净利润/每股净资产/行业代码等，用于基本面筛选+训练特征。
"""
import json
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
import pandas as pd
import numpy as np

from config import OUTPUT_DIR

CACHE_DIR = Path("output/enriched_cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://gu.qq.com/",
}
_TENCENT = "https://qt.gtimg.cn/q="


def _retry(fn, tries=4, base=1.0, label=""):
    last = None
    for i in range(tries):
        try:
            return fn()
        except Exception as e:  # noqa
            last = e
            time.sleep(base * (i + 1))
    return None


def _parse_quote(body: str) -> dict:
    """解析腾讯单只行情字符串 → dict"""
    f = body.split("~")
    if len(f) < 50:
        return {}
    try:
        out = {
            "name": f[1],
            "price": float(f[3]),
            "prev_close": float(f[4]),
            "open": float(f[5]),
            "volume": float(f[6]),          # 手
            "outer": float(f[7]),           # 外盘=主动买(手)
            "inner": float(f[8]),           # 内盘=主动卖(手)
            "change_pct": float(f[32]),
            "high": float(f[33]) if f[33] else 0.0,
            "low": float(f[34]) if f[34] else 0.0,
            "amplitude": float(f[43]) if f[43] else 0.0,
            "total_mv": float(f[44]) if f[44] else 0.0,   # 亿
            "volume_ratio": float(f[46]) if f[46] else 0.0,
            "high_limit": float(f[47]) if f[47] else 0.0,
            "low_limit": float(f[48]) if f[48] else 0.0,
            "turnover": float(f[38]) if f[38] else 0.0,
        }
        # 主动买入占比
        tot = out["outer"] + out["inner"]
        out["active_buy_ratio"] = (out["outer"] / tot) if tot > 0 else 0.5
        # 当日均价 VWAP = 累计成交额(元) / 累计成交量(股)；f[37]成交额(万元) f[36]成交量(手)
        try:
            _vol_hand = float(f[36])
            _amt_wan = float(f[37])
            out["vwap"] = (_amt_wan * 10000.0 / (_vol_hand * 100.0)) if _vol_hand > 0 else 0.0
        except (ValueError, IndexError):
            out["vwap"] = 0.0
        return out
    except (ValueError, IndexError):
        return {}


def get_quote(symbol: str, max_age_seconds: int = 300) -> dict | None:
    """单只实时行情（带缓存, max_age_seconds 秒内有效）"""
    from datetime import datetime, timezone
    cache = CACHE_DIR / f"q_{symbol}.json"
    if cache.exists():
        age = (datetime.now(timezone.utc).timestamp() - cache.stat().st_mtime)
        if age < max_age_seconds:
            try:
                return json.loads(cache.read_text(encoding="utf-8"))
            except Exception:
                pass
    sec = ("sh" if symbol.startswith("6") else "sz") + symbol

    def _call():
        r = requests.get(_TENCENT, params={"q": sec}, headers=_HEADERS, timeout=8)
        r.raise_for_status()
        for line in r.text.strip().split(";"):
            if sec in line:
                body = line.split('="', 1)[1].rsplit('"', 1)[0]
                d = _parse_quote(body)
                if d:
                    d["symbol"] = symbol
                    cache.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
                    return d
        return None

    return _retry(_call, label=symbol)


def get_quotes_batch(symbols: list[str], batch=80) -> dict:
    """批量实时行情 {symbol: quote}"""
    out = {}
    for i in range(0, len(symbols), batch):
        chunk = symbols[i : i + batch]
        secs = [("sh" if s.startswith("6") else "sz") + s for s in chunk]
        q = ",".join(secs)

        def _call():
            r = requests.get(_TENCENT, params={"q": q}, headers=_HEADERS, timeout=12)
            r.raise_for_status()
            res = {}
            for line in r.text.strip().split(";"):
                if not line.strip() or "=" not in line:
                    continue
                sec = line.split("=")[0].replace("v_", "")
                sym = sec[-6:]
                body = line.split('="', 1)[1].rsplit('"', 1)[0]
                d = _parse_quote(body)
                if d:
                    d["symbol"] = sym
                    res[sym] = d
            return res

        res = _retry(_call, label=f"batch{i}")
        if res:
            out.update(res)
    return out


def get_fundamentals(symbol: str) -> dict | None:
    """基本面（腾讯实时行情中的市值/估值，作为静态质量因子）"""
    q = get_quote(symbol)
    if not q:
        return None
    return {
        "symbol": symbol,
        "total_mv": q.get("total_mv"),
        "pe_ttm": None,   # 腾讯基础行情不含PE字段稳定位，留空
        "pb": None,
        "active_buy_ratio": q.get("active_buy_ratio"),
        "turnover": q.get("turnover"),
        "volume_ratio": q.get("volume_ratio"),
    }


if __name__ == "__main__":
    import sys
    syms = sys.argv[1].split(",") if len(sys.argv) > 1 else ["002979", "600519"]
    q = get_quotes_batch(syms)
    for s, d in q.items():
        print(s, d["name"], "主动买入占比=%.1f%%" % (d["active_buy_ratio"] * 100),
              "换手=%.2f%%" % d["turnover"], "量比=%.2f" % d["volume_ratio"],
              "市值=%.0f亿" % d["total_mv"])


# ════════════════════════════════════════════════════════════════
# mootdx 财务数据（通达信 TCP 7709，腾讯云可用，不封IP）
# ════════════════════════════════════════════════════════════════

from config import OUTPUT_DIR


def _mootdx_finance_one(symbol: str) -> dict | None:
    """获取单只股票财务快照（mootdx TCP）"""
    cache = OUTPUT_DIR / ".finance_cache" / f"{symbol}.json"
    cache.parent.mkdir(parents=True, exist_ok=True)
    if cache.exists():
        try:
            return json.loads(cache.read_text(encoding="utf-8"))
        except Exception:
            pass
    try:
        from mootdx.quotes import Quotes
        client = Quotes.factory(market="std")
        fin = client.finance(symbol=symbol)
        if fin is None or fin.empty:
            return None
        d = fin.iloc[0].to_dict()
        # 解析关键字段
        out = {
            "symbol": symbol,
            "total_shares": float(d.get("zongguben", 0) or 0),           # 总股本
            "float_shares": float(d.get("liutongguben", 0) or 0),        # 流通股本
            "total_assets": float(d.get("zongzichan", 0) or 0),          # 总资产
            "net_assets": float(d.get("jingzichan", 0) or 0),            # 净资产
            "revenue": float(d.get("zhuyingshouru", 0) or 0),            # 主营收入
            "operating_profit": float(d.get("zhuyinglirun", 0) or 0),    # 主营利润
            "net_profit": float(d.get("jinglirun", 0) or 0),             # 净利润
            "total_cash_flow": float(d.get("zongxianjinliu", 0) or 0),   # 总现金流
            "bps": float(d.get("meigujingzichan", 0) or 0),              # 每股净资产
            "industry_code": int(d.get("industry", 0) or 0),             # 行业代码
            "shareholders": int(d.get("gudongrenshu", 0) or 0),         # 股东人数
            "currency_funds": float(d.get("cunhuo", 0) or 0),            # 存货
        }
        # 计算衍生指标
        shares = out["total_shares"]
        if shares > 0:
            out["eps"] = out["net_profit"] / shares                      # 每股收益
            out["revenue_per_share"] = out["revenue"] / shares
            out["bps_derived"] = out["net_assets"] / shares
        else:
            out["eps"] = 0.0
        if out["net_assets"] > 0:
            out["roe"] = out["net_profit"] / out["net_assets"]           # 净资产收益率
        else:
            out["roe"] = 0.0

        # 确保所有值为可 JSON 序列化的 Python 原生类型
        import math
        out_clean = {}
        for k, v in out.items():
            if isinstance(v, (np.integer,)):
                out_clean[k] = int(v)
            elif isinstance(v, (np.floating,)):
                out_clean[k] = float(v) if not (isinstance(v, float) and math.isnan(v)) else 0.0
            elif isinstance(v, float) and math.isnan(v):
                out_clean[k] = 0.0
            else:
                out_clean[k] = v
        cache.write_text(json.dumps(out_clean, ensure_ascii=False), encoding="utf-8")
        return out
        return out
    except Exception as e:
        print(f"⚠ mootdx finance {symbol}: {e}")
        return None


def get_mootdx_finance_fundamentals(symbol: str) -> dict | None:
    """返回供 features.py compute_fundamental_features 使用的格式"""
    fin = _mootdx_finance_one(symbol)
    if not fin:
        return None
    return {
        "eps": fin.get("eps", 0.0),
        "revenue": fin.get("revenue", 0.0),
        "net_profit": fin.get("net_profit", 0.0),
        "bps": fin.get("bps", 0.0),
        "roe": fin.get("roe", 0.0),
        "profit_margin": (fin.get("net_profit", 0) / (fin.get("revenue", 1) + 1e-10)) if fin.get("revenue", 0) > 0 else 0.0,
        "total_shares": fin.get("total_shares", 0),
        "total_assets": fin.get("total_assets", 0),
        "industry_code": fin.get("industry_code", 0),
        "net_profit_yoy": 0.0,   # 暂无同比
        "revenue_yoy": 0.0,
        "gross_margin": 0.0,
    }


def batch_mootdx_finance(symbols: list[str]) -> dict:
    """批量获取财务数据（并行 TCP，快）"""
    out = {}
    with ThreadPoolExecutor(max_workers=20) as ex:
        fut = {ex.submit(_mootdx_finance_one, s): s for s in symbols}
        for f in as_completed(fut):
            r = f.result()
            if r:
                out[r["symbol"]] = r
    return out

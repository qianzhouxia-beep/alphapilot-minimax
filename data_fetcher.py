"""
AlphaPilot 数据获取层 v2 — 多源容灾
数据源：新浪日K线 + 同花顺板块 + AKShare 基本面/龙虎榜
支持自动重试和源切换
"""
import time
import random
import warnings
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path

import akshare as ak
import pandas as pd
import numpy as np

warnings.filterwarnings("ignore")

# ── 配置 ──
MAX_RETRIES = 3          # 单个请求最大重试次数
RETRY_BACKOFF = 2.0      # 重试间隔倍数
CACHE_DIR = Path("/home/ubuntu/alphapilot/.data_cache")
CACHE_DIR.mkdir(exist_ok=True)
CACHE_TTL = 3600         # 缓存有效期（秒）
REQUEST_DELAY = 0.0      # 请求间延迟（默认不延迟，线程池控制）


def _retry(fn, *args, label="", **kwargs):
    """带退避重试的请求封装"""
    last_err = None
    for attempt in range(MAX_RETRIES):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            last_err = e
            if attempt < MAX_RETRIES - 1:
                wait = RETRY_BACKOFF * (attempt + 1) + random.uniform(0, 0.5)
                if label:
                    print(f"  ⚠ {label} 重试 {attempt+1}/{MAX_RETRIES} (等待{wait:.1f}s): {str(e)[:60]}")
                time.sleep(wait)
    raise last_err


def _cached_or_fetch(name: str, fetch_fn, ttl: int = CACHE_TTL):
    """从文件缓存读取，过期则重新获取"""
    cache_path = CACHE_DIR / f"{name}.parquet"
    now = time.time()

    if cache_path.exists():
        mtime = cache_path.stat().st_mtime
        if now - mtime < ttl:
            try:
                df = pd.read_parquet(cache_path)
                if not df.empty:
                    return df
            except Exception:
                pass

    df = fetch_fn()
    if df is not None and not df.empty:
        df.to_parquet(cache_path, index=False)
    return df


# ──────────────────────────────────────
# 全 A 股票列表
# ──────────────────────────────────────

def get_stock_list_cninfo() -> pd.DataFrame:
    """东财 A 股代码+名称列表（容灾用）"""
    df = ak.stock_info_a_code_name()
    df = df.rename(columns={"code": "symbol", "name": "name"})
    df["symbol"] = df["symbol"].astype(str).str.zfill(6)
    return df


def _filter_stocks(df: pd.DataFrame) -> pd.DataFrame:
    """过滤退市/ST/北交所"""
    total_before = len(df)
    mask_delist = df["name"].str.contains("退", na=False)
    mask_st = df["name"].str.contains(r"\*?ST", na=False, regex=True)
    mask_bj = df["symbol"].str.startswith("bj") | df["symbol"].str.startswith("92")
    df = df[~mask_delist & ~mask_st & ~mask_bj].copy()
    removed = total_before - len(df)
    print(f"  ℹ️ 过滤退市/ST/BJ: {removed} 只")
    print(f"  ℹ️ 剩余可交易: {len(df)} 只")
    return df


@lru_cache(maxsize=1)
def get_stock_list() -> pd.DataFrame:
    """获取全A股列表（带多源容灾）"""
    for source_name, source_fn in [
        ("东财代码表", get_stock_list_cninfo),
    ]:
        try:
            print(f"  尝试 {source_name} 源...")
            df = _retry(source_fn, label=f"{source_name}股票列表")
            if df is not None and not df.empty:
                df = _filter_stocks(df)
                # 保存缓存
                df.to_parquet(CACHE_DIR / "stock_list.parquet", index=False)
                return df
        except Exception as e:
            print(f"  ❌ {source_name}源失败: {str(e)[:80]}")

    # 兜底：读取缓存
    cache_path = CACHE_DIR / "stock_list.parquet"
    if cache_path.exists():
        print("  ℹ️ 使用缓存股票列表（可能过期）")
        df = pd.read_parquet(cache_path)
        df = _filter_stocks(df)
        return df

    print("  ❌ 所有数据源均不可用，无法获取股票列表")
    return pd.DataFrame()


# ──────────────────────────────────────
# 日K线（多源容灾）
# ──────────────────────────────────────

def _get_kline_sina(symbol: str, start_date: str = "20200101") -> pd.DataFrame:
    """新浪单个K线"""
    clean = symbol[2:] if symbol[:2].lower() in ("sh", "sz", "bj") else symbol
    prefix = "sh" if clean.startswith("6") or clean.startswith("9") else "sz"
    df = ak.stock_zh_a_daily(symbol=f"{prefix}{clean}", start_date=start_date, adjust="qfq")
    if df.empty:
        return pd.DataFrame()
    df = df.rename(columns={
        "date": "date", "open": "open", "high": "high",
        "low": "low", "close": "close", "volume": "volume",
        "amount": "amount", "outstanding_share": "outstanding_share",
        "turnover": "turnover",
    })
    df["date"] = pd.to_datetime(df["date"])
    df["symbol"] = symbol
    return df.sort_values("date").reset_index(drop=True)


def get_kline_sina(symbol: str, start_date: str = "20200101") -> pd.DataFrame:
    """获取单只股票日K线（带重试+30s超时）"""
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(_retry, _get_kline_sina, symbol, start_date, label=f"{symbol} K线")
        try:
            return fut.result(timeout=30)
        except concurrent.futures.TimeoutError:
            return pd.DataFrame()
        except Exception:
            return pd.DataFrame()


# ──────────────────────────────────────
# 同花顺板块数据
# ──────────────────────────────────────

@lru_cache(maxsize=1)
def get_sector_list() -> pd.DataFrame:
    """获取行业板块列表"""
    try:
        df = ak.stock_board_industry_name_ths()
        df = df.rename(columns={"name": "sector_name", "code": "sector_code"})
        df["sector_code"] = df["sector_code"].astype(str)
        return df
    except Exception:
        return _cached_or_fetch("sector_list", lambda: None, ttl=86400)


@lru_cache(maxsize=1)
def get_concept_sector_list() -> pd.DataFrame:
    """获取概念板块列表"""
    try:
        df = ak.stock_board_concept_name_ths()
        df = df.rename(columns={"name": "sector_name", "code": "sector_code"})
        df["sector_code"] = df["sector_code"].astype(str)
        return df
    except Exception:
        return _cached_or_fetch("concept_list", lambda: None, ttl=86400)


# ──────────────────────────────────────
# 业绩预告、龙虎榜、涨停
# ──────────────────────────────────────

@lru_cache(maxsize=1)
def get_yjyg() -> pd.DataFrame:
    """业绩预告"""
    today = datetime.now().strftime("%Y-%m-%d")
    for date in [today, "2025-12-31"]:
        try:
            return ak.stock_yjyg_em(date=date)
        except Exception:
            continue
    return pd.DataFrame()


@lru_cache(maxsize=1)
def get_lhb() -> pd.DataFrame:
    """龙虎榜"""
    try:
        return ak.stock_lhb_detail_em()
    except Exception:
        return pd.DataFrame()


def get_zt_pool(date: str = None) -> pd.DataFrame:
    """涨停股池"""
    date = date or datetime.now().strftime("%Y-%m-%d")
    try:
        return ak.stock_zt_pool_em(date=date)
    except Exception:
        return pd.DataFrame()


if __name__ == "__main__":
    stocks = get_stock_list()
    print(f"A股数量: {len(stocks)}")
    print(stocks.head(3))

    kline = get_kline_sina("000001", "20250601")
    print(f"\n平安银行日K线: {len(kline)} 行")
    print(kline.tail(3))

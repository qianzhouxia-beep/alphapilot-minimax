"""
AlphaPilot 每日推荐管线 v2 — 多线程并行版
关键优化：ThreadPoolExecutor 并行获取K线 + 并行评分
"""
import json
import os
import time
import warnings
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import numpy as np

from config import TOP_N, OUTPUT_DIR
from data_fetcher import (
    get_stock_list, get_kline_sina,
    get_lhb, get_yjyg, get_zt_pool,
)
from ml_screener import screener
from features import _lookup_chip, load_chip_cache

# 预导入 auto_factor_engine（避免线程池中导入死锁）
import auto_factor_engine; del auto_factor_engine

# 隔夜情绪因子（美股收盘后板块映射到A股）
from overnight_sentiment import get_overnight_bonus, get_stock_sector_bonus

warnings.filterwarnings("ignore")

# 并行参数
MAX_WORKERS = 20        # V18 Fusion 每线程耗内存增大，需降低并发
BATCH_REPORT = 500     # 每 N 只报告一次进度
CHIP_CONC70_MAX = 12     # 筹码集中度过滤阈值：70%成本集中度>=该值视为筹码峰分散，剔除（仅对有真实筹码数据的票生效）
CHIP_CONC90_MAX = 15   # 90%成本集中度过滤阈值（>=该值且70%>=12即剔除）



def _tencent_prefix(sym: str) -> str:
    """腾讯行情市场前缀"""
    if sym.startswith("6"):
        return "sh"
    if sym.startswith(("4", "8", "9")):
        return "bj"
    return "sz"


def _is_suspended(sym: str) -> bool:
    """检查是否停牌：腾讯实时行情成交量为0或今开为0视为停牌。
    网络失败/解析失败一律返回 False（不误杀）。"""
    try:
        import urllib.request
        url = "http://qt.gtimg.cn/q=%s%s" % (_tencent_prefix(sym), sym)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        raw = urllib.request.urlopen(req, timeout=3).read().decode("gbk", "ignore")
        if "~" not in raw:
            return False
        parts = raw.split("~")
        if len(parts) < 10:
            return False
        price = float(parts[3] or 0)
        prev_close = float(parts[4] or 0)
        open_px = float(parts[5] or 0)
        volume = float(parts[6] or 0)  # 成交量(手)
        # 停牌判定：无成交量 且 (今开为0 或 现价等于昨收无波动)
        if volume == 0 and (open_px == 0 or price == 0 or price == prev_close):
            return True
        return False
    except Exception:
        return False


def _score_one_stock(sym: str, name: str, ov_sector_bonus: dict = None,
                     lhb_map: dict = None, yjyg_map: dict = None) -> dict | None:
    """对单只股票评分（可在线程池中运行，优先从缓存读取K线）"""
    try:
        # 从缓存读K线(优先)
        CACHE_DIR = "/home/ubuntu/alphapilot/backtest_cache"
        cache_path = os.path.join(CACHE_DIR, f"{sym}.pkl")
        kline = None
        if os.path.exists(cache_path) and os.path.getsize(cache_path) >= 1000:
            try:
                kline = pd.read_pickle(cache_path)
            except:
                pass
        if kline is None or kline.empty or len(kline) < 60:
            kline = get_kline_sina(sym, "20240701")
        if kline is None or kline.empty or len(kline) < 60:
            return None

        # 龙虎榜
        has_lhb = False
        buy_inst_count = 0
        if lhb_map and sym in lhb_map:
            has_lhb = True
            buy_inst_count = lhb_map[sym]

        # 业绩预告
        has_forecast = False
        yjyg_max_change = 0.0
        if yjyg_map and sym in yjyg_map:
            has_forecast = True
            yjyg_max_change = yjyg_map[sym]

        # 评分
        result = screener.score_stock(
            kline_df=kline,
            sector_heat=0.5,
            has_lhb=has_lhb,
            buy_inst_count=buy_inst_count,
            has_forecast=has_forecast,
            yjyg_max_change=yjyg_max_change,
        )

        if "error" not in result:
            # 隔夜情绪加分（美股板块映射）
            _ov_bonus = 0.0
            _ov_signals = []
            if ov_sector_bonus:
                _bonus, _matched = get_stock_sector_bonus(sym, name, ov_sector_bonus)
                if _bonus > 0:
                    _ov_bonus = _bonus * 0.20  # 隔夜加分权重
                    _ov_signals.append("隔夜美股板块利好")
            result["score"] = result["score"] * (1 + _ov_bonus)
            result["overnight_bonus"] = _ov_bonus
            result["overnight_signals"] = _ov_signals
            result.update({"symbol": sym, "name": name})
            return result

    except Exception:
        pass
    return None


def _build_lookup_maps(lhb_df: pd.DataFrame,
                       yjyg_df: pd.DataFrame) -> tuple[dict, dict]:
    """构建龙虎榜和业绩预告的快速查询表"""
    lhb_map = {}
    if not lhb_df.empty and "代码" in lhb_df.columns:
        for _, row in lhb_df.iterrows():
            code = str(row.get("代码", "")).zfill(6)
            lhb_map[code] = int(row.get("买方机构数", 0))

    yjyg_map = {}
    if not yjyg_df.empty and "股票代码" in yjyg_df.columns:
        for _, row in yjyg_df.iterrows():
            code = str(row.get("股票代码", "")).zfill(6)
            yjyg_map[code] = float(row.get("最大变动", 0) or 0)

    return lhb_map, yjyg_map


def run_daily_recommend(top_n: int = TOP_N) -> dict:
    """运行每日推荐管线（多线程并行版）"""
    run_time = datetime.now().isoformat()
    print(f"\n{'='*50}")
    print(f"🚀 AlphaPilot 每日推荐管线 v2 @ {run_time}")
    print(f"{'='*50}")

    # 1. 加载模型
    print("\n1. 加载模型...")
    if not screener.load_model(version="v25"):
        return {"error": "model_not_loaded", "run_at": run_time}

    # 2. 获取全A股列表
    print("\n2. 获取全A股列表...")
    stocks = get_stock_list()
    # v3.1 漏斗：启动形态池 ∪ 主线行业旁路池（旁路缺省则仅启动池）
    _gc_path = "output/volume_gc_pool.json"
    _bypass_path = "output/hot_sector_bypass_pool.json"
    try:
        import json as _json

        def _bare_sym(s: str) -> str:
            t = str(s or "").lower().replace("sh", "").replace("sz", "").replace("bj", "")
            return t[-6:] if len(t) >= 6 else t

        _pool = set()
        if os.path.exists(_gc_path):
            _gc_raw = _json.load(open(_gc_path, encoding="utf-8"))
            if isinstance(_gc_raw, list):
                _pool |= {_bare_sym(x) for x in _gc_raw}
            elif isinstance(_gc_raw, dict):
                _pool |= {_bare_sym(x) for x in (_gc_raw.get("symbols") or [])}
        if os.path.exists(_bypass_path):
            _bp = _json.load(open(_bypass_path, encoding="utf-8"))
            if isinstance(_bp, dict) and _bp.get("enabled", True):
                _pool |= {_bare_sym(x) for x in (_bp.get("symbols") or [])}
            elif isinstance(_bp, list):
                _pool |= {_bare_sym(x) for x in _bp}
        if _pool:
            _before = len(stocks)
            _sym_col = stocks["symbol"].astype(str).map(_bare_sym)
            stocks = stocks[_sym_col.isin(_pool)]
            print(f"  评分池(启动∪旁路): {_before} → {len(stocks)} 只 (pool={len(_pool)})")
    except Exception as _e:
        print(f"  评分池裁剪跳过: {_e}")
    total = len(stocks)
    print(f"   待评分: {total}")

    # 3. 获取事件数据
    print("\n3. 获取事件数据（并行获取）...")
    t_data = time.time()
    lhb_df = get_lhb()
    yjyg_df = get_yjyg()
    lhb_map, yjyg_map = _build_lookup_maps(lhb_df, yjyg_df)
    print(f"   龙虎榜: {len(lhb_df)} 行, 业绩预告: {len(yjyg_df)} 行 ({time.time()-t_data:.0f}s)")

    # 4. 加载隔夜情绪因子（美股收盘后板块映射）
    print("\n4. 加载隔夜情绪因子（美股→A股板块映射）...")
    try:
        _ov_data = get_overnight_bonus()
        _ov_sector_bonus = _ov_data.get("detail", {}).get("sector_bonus", {})
        _ov_score = _ov_data.get("score", 0.5)
        print(f"   隔夜美股情绪分: {_ov_score:.3f}")
        if _ov_sector_bonus:
            print(f"   板块映射: {len(_ov_sector_bonus)} 个受益板块")
            for _sec, _bonus in sorted(_ov_sector_bonus.items(), key=lambda x: -x[1])[:5]:
                print(f"     {_sec}: +{_bonus*100:.1f}%")
        else:
            print("   无板块映射（美股平盘/无数据）")
    except Exception as e:
        print(f"   ⚠️ 隔夜情绪加载失败: {e}")
        _ov_sector_bonus = {}

    # 5. 并行评分
    print(f"\n5. 并行评分（{MAX_WORKERS}线程, 含隔夜情绪加分）...")
    results = []
    scanned = 0
    start = time.time()

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {}
        for _, row in stocks.iterrows():
            sym = row["symbol"]
            name = row.get("name", "")
            future = executor.submit(
                _score_one_stock, sym, name,
                _ov_sector_bonus, lhb_map, yjyg_map,
            )
            futures[future] = sym

        for i, future in enumerate(as_completed(futures), 1):
            scanned += 1
            result = future.result()
            if result is not None:
                results.append(result)

            if scanned % BATCH_REPORT == 0 or scanned == total:
                elapsed = time.time() - start
                rate = scanned / elapsed if elapsed > 0 else 0
                print(f"   进度: {scanned}/{total}, 有效: {len(results)}, "
                      f"耗时: {elapsed:.0f}s ({rate:.1f}只/s)")

    # 6. 排序取 top N（展示用），缓存扩大至 CACHE_N 供资金门控筛选高质量池
    CACHE_N = 500
    results.sort(key=lambda x: x["score"], reverse=True)

    # === 停牌过滤：K线停更但仍被评分的停牌股，用实时行情剔除 ===
    from concurrent.futures import ThreadPoolExecutor as _TPE
    _check_pool = results[:130]
    _susp = set()
    try:
        with _TPE(max_workers=10) as _ex:
            _fut = {_ex.submit(_is_suspended, r["symbol"]): r["symbol"] for r in _check_pool}
            for _f in _fut:
                try:
                    if _f.result(timeout=6):
                        _susp.add(_fut[_f])
                except Exception:
                    pass
    except Exception:
        pass
    if _susp:
        print("   [停牌过滤] 剔除 %d 只: %s" % (len(_susp), ",".join(sorted(_susp))))
        results = [r for r in results if r["symbol"] not in _susp]

    # === 筹码集中度过滤：剔除筹码峰明显分散（70%成本集中度过高）的个股 ===
    # 与 features.py 中 chip_concentrated/chip_semi 定义一致：70%集中度<10 视为集中，
    # 否则视为筹码峰分散，直接剔除。仅对“有真实筹码数据”的个股生效，无数据则保留以免误伤。
    try:
        load_chip_cache()
        _chip_pool = results[:130]
        _chip_disp = set()
        for r in _chip_pool:
            _c = _lookup_chip(r["symbol"])
            if _c and (_c.get("chipConcentration70", 0) >= CHIP_CONC70_MAX or _c.get("chipConcentration90", 0) >= CHIP_CONC90_MAX):
                _chip_disp.add(r["symbol"])
        if _chip_disp:
            print("   [筹码集中度过滤] 剔除 %d 只: %s"
                  % (len(_chip_disp), ",".join(sorted(_chip_disp)[:15])
                     + ("..." if len(_chip_disp) > 15 else "")))
            results = [r for r in results if r["symbol"] not in _chip_disp]
    except Exception as _e:
        print("   [筹码集中度过滤] 跳过(异常): %s" % _e)

    top = results[:top_n]
    cached = results[:max(top_n, CACHE_N)]

    elapsed = time.time() - start
    print(f"\n{'='*50}")
    print(f"✅ 评分完成! 扫描 {scanned} 只, 有效评分 {len(results)} 只, "
          f"耗时 {elapsed:.0f}s ({scanned/elapsed:.1f}只/s)")
    print(f"🏆 Top {top_n} 推荐:")
    for i, r in enumerate(top, 1):
        _ov = f" | 隔夜: +{r.get('overnight_bonus', 0)*100:.1f}%" if r.get('overnight_bonus', 0) > 0 else ""
        print(f"   {i}. {r['symbol']} {r['name']} | 评分: {r['score']:.4f}{_ov} | "
              f"买入: {r['buy_price']:.2f} | 目标: {r['target_price']:.2f}")

    # 7. 保存结果（缓存 CACHE_N 只，供资金门控在更大池里筛选）
    output = {
        "run_at": run_time,
        "recommendations": cached,
        "stats": {
            "total_scanned": scanned,
            "valid_scored": len(results),
            "elapsed_seconds": round(elapsed, 1),
        },
    }
    
    output_path = OUTPUT_DIR / "daily_recommend.json"

    # === 合并旧文件的资金流数据（recommend.py本身不产生这些） ===
    _old_fund = {}
    if output_path.exists():
        try:
            _old = json.loads(output_path.read_text(encoding="utf-8"))
            for _r in _old.get("recommendations", []):
                _sym = _r.get("symbol", "")
                if _sym:
                    _old_fund[_sym] = {
                        k: _r.get(k) for k in [
                            "main_net", "active_buy_ratio", "fund_source",
                            "money_phase", "money_phase_label",
                            "price", "change_pct", "buy_price",
                            "turnover", "volume_ratio",
                            "sector", "sector_change_pct",
                            "main_inflow", "main_outflow",
                        ]
                    }
        except:
            pass
    for _r in output.get("recommendations", []):
        _sym = _r.get("symbol", "")
        if _sym in _old_fund:
            for _k, _v in _old_fund[_sym].items():
                if _v is not None:
                    _r[_k] = _v

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n📁 结果已保存: {output_path}")

    return output


if __name__ == "__main__":
    result = run_daily_recommend(top_n=5)
    print(f"\n推荐摘要:")
    for r in result.get("recommendations", []):
        _ov = f" [+隔夜]" if r.get('overnight_bonus', 0) > 0 else ""
        print(f"  - {r['symbol']} {r['name']} | 评分 {r['score']:.4f}{_ov}")

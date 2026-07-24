#!/usr/bin/env python3
"""
板块风向门控 (Sector Gate)
合并：美股因子 + 隔夜情绪 + A股板块自身趋势

A股板块趋势（多日）：
  - 5日涨跌幅（短期动量）
  - 10日涨跌幅（中期方向）
  - 5日日均资金净额
  - 今日领涨强度
"""
import os, sys, json, time, pandas as pd
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
sys.path.insert(0, "/home/ubuntu/alphapilot")
os.chdir("/home/ubuntu/alphapilot")

import akshare as ak

# 缓存
_CACHE = {}

def _get_sector_hist(sector_name: str, days: int = 15) -> pd.DataFrame:
    """获取板块历史K线（带缓存 + 10s超时）"""
    cache_key = f"sector_hist_{sector_name}"
    if cache_key in _CACHE:
        return _CACHE[cache_key]
    
    def _fetch():
        end = time.strftime("%Y%m%d")
        start_dt = pd.Timestamp(end) - pd.Timedelta(days=days + 10)
        start = start_dt.strftime("%Y%m%d")
        return ak.stock_board_industry_hist_em(symbol=sector_name, start_date=start, end_date=end)
    
    try:
        with ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(_fetch)
            df = fut.result(timeout=10)  # 10s超时
            if df is not None and not df.empty:
                _CACHE[cache_key] = df
            return df
    except FutureTimeout:
        print(f"  ⚠️ 板块超时: {sector_name}")
        return None
    except:
        return None


def _compute_sector_trend(sector_name: str) -> dict:
    """计算板块5日/10日趋势"""
    df = _get_sector_hist(sector_name)
    if df is None or len(df) < 12:
        return {"score_5d": 0, "score_10d": 0}

    closes = df["收盘"].values
    rets = df["涨跌幅"].values

    # 5日累计涨跌幅
    ret_5d = sum(rets[-5:]) if len(rets) >= 5 else 0
    # 10日累计涨跌幅
    ret_10d = sum(rets[-10:]) if len(rets) >= 10 else 0

    return {"ret_5d": round(ret_5d, 2), "ret_10d": round(ret_10d, 2)}


def _normalize(val: float, thresholds: list) -> float:
    """根据阈值返回 -2~+2 的分值"""
    if val > thresholds[0]: return 2.0
    if val > thresholds[1]: return 1.0
    if val > thresholds[2]: return 0.5
    if val > thresholds[3]: return 0.0
    if val > thresholds[4]: return -0.5
    if val > thresholds[5]: return -1.0
    return -2.0


def compute_sector_score(sector_name: str, sector_fund_flow: dict = None) -> dict:
    """
    计算单板块的综合趋势分

    Args:
        sector_name: 板块名称，如"半导体"
        sector_fund_flow: 板块资金流字典, 含净额和领涨股涨跌幅

    Returns:
        {"trend_score": float, "adjust_factor": float, "detail": dict}
    """
    trend = _compute_sector_trend(sector_name)
    ret_5d = trend.get("ret_5d", 0)
    ret_10d = trend.get("ret_10d", 0)

    # 5日动量分（-2~+2）
    score_5d = _normalize(ret_5d, [10, 5, 2, -2, -5, -10])
    # 10日方向分（-2~+2）
    score_10d = _normalize(ret_10d, [10, 5, 2, -2, -5, -10])

    # 资金分（-2~+2）
    net_amount = 0
    if sector_fund_flow and isinstance(sector_fund_flow, dict):
        net_amount = float(sector_fund_flow.get("net_amount", 0) or 0)
    score_fund = _normalize(net_amount, [5, 2, 0.5, -0.5, -2, -5])

    # 领涨强度分（-1~+1）
    leader_chg = 0
    if sector_fund_flow and isinstance(sector_fund_flow, dict):
        leader_chg = float(sector_fund_flow.get("leader_change_pct", 0) or 0)
    if leader_chg >= 10: score_leader = 1.0
    elif leader_chg >= 5: score_leader = 0.5
    elif leader_chg >= 0: score_leader = 0
    elif leader_chg >= -5: score_leader = -0.5
    else: score_leader = -1.0

    # 综合
    trend_score = score_5d * 0.40 + score_10d * 0.30 + score_fund * 0.20 + score_leader * 0.10
    adjust_factor = 1 + trend_score * 0.015  # ±3%

    return {
        "trend_score": round(trend_score, 4),
        "adjust_factor": round(adjust_factor, 4),
        "detail": {
            "ret_5d": ret_5d,
            "ret_10d": ret_10d,
            "score_5d": score_5d,
            "score_10d": score_10d,
            "net_amount": net_amount,
            "score_fund": score_fund,
            "leader_change_pct": leader_chg,
            "score_leader": score_leader,
        },
    }


def apply_sector_gate(items: list, sector_flow_df=None) -> list:
    """
    对推荐列表施加板块风向门控

    Args:
        items: 推荐列表（每只含 name, score, sector 等字段）
        sector_flow_df: akshare.stock_fund_flow_industry() 的 DataFrame（可选，省一次调用）

    Returns:
        调整后的推荐列表
    """
    # 获取板块资金流数据
    if sector_flow_df is None:
        try:
            sector_flow_df = ak.stock_fund_flow_industry()
        except:
            sector_flow_df = None

    # 构建板块快速查找 {板块名: {net_amount, leader_change_pct}}
    sector_map = {}
    if sector_flow_df is not None and not sector_flow_df.empty:
        for _, row in sector_flow_df.iterrows():
            name = str(row.get("行业", ""))
            if name:
                sector_map[name] = {
                    "net_amount": float(row.get("净额", 0) or 0),
                    "leader_change_pct": float(row.get("领涨股-涨跌幅", 0) or 0),
                }

    # 美股因子（从现有增强因子文件读取）
    us_data = {}
    try:
        us_path = "output/us_enhanced_factors.json"
        if os.path.exists(us_path):
            with open(us_path) as f:
                us_data = json.load(f)
    except:
        pass

    us_sector_impacts = us_data.get("sector_impacts", {})
    us_overnight = {k: v for k, v in us_data.get("overnight_stocks", {}).items()}

    # 美股整体情绪
    us_sentiment = us_data.get("sentiment_score", 0.5)
    apple_chg = 0
    for k, v in us_overnight.items():
        if "苹果" in k:
            apple_chg = v
            break
    ai_boost = max(0, apple_chg * 0.008)

    results = []
    for item in items:
        name = str(item.get("name", "") or "")
        sector = str(item.get("sector", "") or item.get("industry", "") or "")
        base_score = float(item.get("score", 0) or 0)

        # 1. A股板块趋势分
        flow_info = {}
        for s_name, info in sector_map.items():
            if s_name in sector or sector in s_name:
                flow_info = info
                break
        sector_res = compute_sector_score(sector, flow_info)

        # 2. 美股板块影响
        sector_bonus = 0
        for sec_key, impact in us_sector_impacts.items():
            if sec_key.startswith("_"):
                continue
            if sec_key in sector or sector in sec_key:
                sector_bonus = impact * 0.05
                break
        if not sector_bonus:
            sector_bonus = us_sector_impacts.get("__overall__", 0) * 0.03

        # 3. AI股加分（苹果→AI应用）
        ai_keywords = ["AI", "智能", "人工", "大模型", "机器视觉", "语音识别", "算法", "软件"]
        is_ai = any(k in name for k in ai_keywords) or any(k in sector for k in ai_keywords)
        if is_ai and ai_boost > 0:
            sector_bonus += ai_boost

        sector_bonus = max(-0.1, min(0.1, sector_bonus))

        # 综合调权
        new_score = base_score * sector_res["adjust_factor"] + sector_bonus
        new_score = max(0, round(new_score, 4))

        item["score"] = new_score
        item["sector_trend_score"] = sector_res["trend_score"]
        item["sector_adjust_factor"] = sector_res["adjust_factor"]
        item["us_bonus"] = round(sector_bonus, 4)
        item["us_sentiment"] = round(us_sentiment, 4)
        results.append(item)

    results.sort(key=lambda x: -float(x.get("score", 0) or 0))
    return results


if __name__ == "__main__":
    # 测试
    print("=" * 50)
    print("板块风向门控测试")
    print("=" * 50)

    # 获取板块资金流
    try:
        flow = ak.stock_fund_flow_industry()
        print("\n板块资金流 Top5:")
        if flow is not None and not flow.empty:
            for _, row in flow.head(5).iterrows():
                print(f"  {row['行业']}: 净额={row['净额']:.2f}亿  领涨={row['领涨股-涨跌幅']:.2f}%")
    except Exception as e:
        print(f"  获取失败: {e}")

    # 测试几个板块
    test_sectors = ["半导体", "计算机应用", "汽车整车", "证券", "银行"]
    print("\n板块趋势分析:")
    for sec in test_sectors:
        res = compute_sector_score(sec)
        d = res["detail"]
        print(f"  {sec}: 5日{d['ret_5d']:+.2f}% 10日{d['ret_10d']:+.2f}% "
              f"趋势分={res['trend_score']:.2f} 调整={res['adjust_factor']:.4f}")

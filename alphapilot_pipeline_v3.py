#!/usr/bin/env python3
"""
AlphaPilot 完整选股管线 v3.0 — 漏斗架构
全A股 5000+ → 四类启动形态 → V2.2+隔夜 → 资金门控 → 大盘环境 → 板块资金轮动(硬过滤) → LLM审核 → S2 → Top50

时间语义（不写死日历日）:
  asof = 最近已收盘的 A 股交易日收盘数据
  目标 = 预测「下一交易日」开盘后的可交易标的
  美股隔夜因子：中国约 05:00 ≈ 美东前一天下午，接上美股盘中/收盘映射
"""
import os, sys, json, time, subprocess, requests, numpy as np, pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

os.chdir("/home/ubuntu/alphapilot")
OUTPUT_DIR = "output"

# ── DeepSeek（LLM审核用） ──
LLM_KEY = os.getenv("DEEPSEEK_API_KEY") or "sk-7fed993c1a084f18bb420b19264b109f"
LLM_URL = "https://api.deepseek.com/v1/chat/completions"

# ── 全局缓存 ──
_SECTOR_HIST_CACHE = {}

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

def run_step(name, cmd, timeout=600):
    log(f"▶ {name} ...")
    t0 = time.time()
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
    elapsed = int(time.time() - t0)
    if r.returncode == 0:
        log(f"  ✅ {name} 完成 ({elapsed}s)")
    else:
        log(f"  ❌ {name} 失败: {r.stderr.strip()[-200:]}")
    return r.returncode == 0

# ═══════════════════════════════════════════════════════════════
# STEP 1: 全A股四类启动形态扫描（替代粗糙量价金叉）
# asof = 最近已收盘交易日 → 用于预测下一交易日（不写死日历日）
# ═══════════════════════════════════════════════════════════════
def scan_volume_gc() -> set:
    """兼容旧名：实际跑四类启动形态，产物仍写 volume_gc_pool.json。"""
    from launch_patterns import scan_launch_patterns

    hit_set, pattern_map = scan_launch_patterns(log=log)
    # 把形态标签写回，供后续过滤日志使用
    global _LAUNCH_PATTERNS
    _LAUNCH_PATTERNS = pattern_map
    return hit_set


_LAUNCH_PATTERNS: dict = {}
# ═══════════════════════════════════════════════════════════════
# STEP 2: 资金门控
# ═══════════════════════════════════════════════════════════════
def apply_money_gate(items: list) -> list:
    log("▶ 资金门控过滤...")
    try:
        from soft_universe_gate import surge_arm_b_enabled

        surge_on = surge_arm_b_enabled()
    except Exception:
        surge_on = os.environ.get("ENABLE_SURGE_ARM_B", "1").strip().lower() not in (
            "0",
            "false",
            "no",
            "off",
        )

    a_items = [x for x in items if str(x.get("arm") or "A") != "B"]
    b_items = [x for x in items if str(x.get("arm") or "") == "B"]

    gated_a: list = []
    gated_b: list = []

    # 臂 A：现有硬/弱硬资金门
    try:
        from money_flow_gate import apply_money_flow_gate

        pool_a = a_items if (surge_on and b_items) else items
        gated_a = apply_money_flow_gate(pool_a, top_n=None)
        log(f"  ✅ 臂A资金门: {len(gated_a)}/{len(pool_a)}")
    except Exception as e:
        log(f"  ⚠️ 资金门控失败: {e}")
        gated_a = a_items if (surge_on and b_items) else items

    # 臂 B：不走硬资金删；盘中软加权（东财缓存）
    if surge_on and b_items:
        try:
            from soft_intraday_gate import apply_soft_intraday_gate

            gated_b = apply_soft_intraday_gate(list(b_items), mode="soft")
            log(f"  ✅ 臂B软资金( soft_intraday ): {len(gated_b)}/{len(b_items)}（不硬删）")
        except Exception as e:
            log(f"  ⚠️ 臂B软资金跳过，原样保留: {e}")
            gated_b = list(b_items)
        merged = list(gated_a) + list(gated_b)
        merged.sort(key=lambda x: -float(x.get("score") or 0))
        log(f"  ✅ A+B 合并: A={len(gated_a)} B={len(gated_b)} total={len(merged)}")
        return merged

    # 无 B 臂：可选全局 soft_intraday（旧开关）
    gated = gated_a
    if os.environ.get("ENABLE_SOFT_INTRADAY", "").strip() in ("1", "true", "TRUE", "yes"):
        try:
            from soft_intraday_gate import apply_soft_intraday_gate

            before = len(gated)
            gated = apply_soft_intraday_gate(gated, mode="soft")
            log(f"  ✅ 盘中软门控加权: {before} 只（不删票）")
        except Exception as e:
            log(f"  ⚠️ 盘中软门控跳过: {e}")
    else:
        log("  ⏭ 盘中软门控关闭（生产硬门控主臂；ENABLE_SOFT_INTRADAY=1 可开）")
    return gated

# ═══════════════════════════════════════════════════════════════
# STEP 3a: 大盘/科技环境门控（指数多日趋势）
# ═══════════════════════════════════════════════════════════════
def apply_market_env(items: list) -> tuple:
    """指数环境硬过滤 + 仓位缩放；返回 (items, env_meta)。"""
    log("▶ 大盘环境门控...")
    try:
        from market_env_gate import (
            apply_market_env_gate,
            load_or_build_env,
            position_exposure,
            recommend_pool_n,
            recommend_top_n,
        )
        from permission_gate import enrich_env_with_permission
        import json as _json
        from pathlib import Path as _Path

        env = load_or_build_env(force=True)
        if env.get("exposure_mode") != "permission_v1":
            enrich_env_with_permission(env, asof=env.get("asof"))
        flags = env.get("flags") or {}
        expo = float(env.get("position_exposure", position_exposure(flags, env.get("permission"))))
        top_n = recommend_top_n(expo, default=2)  # 下单只数
        pool_n = recommend_pool_n(expo)  # 池保留只数（薄仓 10）
        idxs = env.get("indexes") or {}
        perm = env.get("permission") or {}
        for k in ("sh_main", "sz_main", "chinext", "star50"):
            st = idxs.get(k) or {}
            log(
                f"  {st.get('name', k)}: 5d={st.get('ret_5d')}% 10d={st.get('ret_10d')}% "
                f"day={st.get('day_chg')}% weak={st.get('weak')} severe={st.get('severe')}"
            )
        log(
            f"  flags: market_weak={flags.get('market_weak')} market_severe={flags.get('market_severe')} "
            f"crash_day={flags.get('market_crash_day')} "
            f"tech_weak={flags.get('tech_weak')} tech_severe={flags.get('tech_severe')} "
            f"perm_on={perm.get('permission_on')} up3={perm.get('up3_count')} "
            f"sustained={perm.get('n_sustained_in')} "
            f"position_exposure={expo} trade_top_n={top_n} pool_n={pool_n} mode={env.get('exposure_mode')}"
        )
        imap = {}
        ip = _Path("data/stock_industry_map.json")
        if ip.exists():
            try:
                imap = _json.loads(ip.read_text(encoding="utf-8"))
            except Exception:
                imap = {}
        before = len(items)
        result = apply_market_env_gate(
            items, env=env, hard_filter=True, mode="soft_demote", industry_map=imap
        )
        meta = {
            "flags": flags,
            "position_exposure": expo,
            "recommend_top_n": top_n,
            "recommend_pool_n": pool_n,
            "indexes": idxs,
            "permission": perm,
            "exposure_mode": env.get("exposure_mode"),
        }
        if expo <= 0:
            # nuclear：瀑布+轮动死+宽度极差；袖套仅研究，不自动下单
            try:
                from weak_rotation_sleeve import apply_weak_rotation_sleeve

                sleeve_items, sleeve_meta = apply_weak_rotation_sleeve([], mkt_meta=meta)
                meta["weak_rotation_sleeve"] = {
                    **(sleeve_meta or {}),
                    "auto_trade": False,
                    "n_research": len(sleeve_items or []),
                }
            except Exception as se:
                log(f"  ⚠️ 弱市袖套研究跳过: {se}")
                meta["weak_rotation_sleeve"] = {
                    "sleeve_applied": False,
                    "auto_trade": False,
                    "error": str(se),
                }
            log("  ⛔ nuclear（crash+rotation_dead）→ 空仓，不输出主臂推荐")
            return [], meta
        if expo < 0.5:
            log(f"  ⚠️ 薄仓执行：仓位 {expo:.0%}，池保留 Top{pool_n}，下单 Top{top_n}")
        elif expo < 1.0:
            log(f"  ⚠️ 降仓执行：建议仓位 {expo:.0%}（等权 Top{top_n} 按此缩放；池 Top{pool_n}）")
        log(f"  ✅ 环境门控: {before} → {len(result)} 只")
        return result, meta
    except Exception as e:
        log(f"  ⚠️ 大盘环境门控失败: {e}")
        return items, {"position_exposure": 1.0, "flags": {}, "error": str(e)}


# ═══════════════════════════════════════════════════════════════
# STEP 3b: 板块资金轮动硬门控（1–3日流入/流出；只过滤不改分）
# ═══════════════════════════════════════════════════════════════
def apply_sector_rotation(items: list) -> list:
    """行业×概念×趋势统一门控（原快门控+延爆门控合并）。"""
    log("▶ 板块资金统一门控（趋势+轮动）...")
    try:
        from sector_flow_gate import apply_sector_flow_gate, build_snapshot

        snap = build_snapshot()
        allow = [x["name"] for x in (snap.get("classes") or {}).get("allow", [])[:8]]
        deny = [x["name"] for x in (snap.get("classes") or {}).get("deny", [])[:8]]
        c_allow = [x["name"] for x in (snap.get("concept_classes") or {}).get("allow", [])[:8]]
        c_deny = [x["name"] for x in (snap.get("concept_classes") or {}).get("deny", [])[:8]]
        log(f"  行业流入: {allow}")
        log(f"  行业流出: {deny}")
        log(f"  概念流入: {c_allow}")
        log(f"  概念流出: {c_deny}")
        before = len(items)
        result = apply_sector_flow_gate(items, snap=snap, mode="soft_dual")
        log(f"  ✅ 统一板块门控 soft_dual: {before} → {len(result)} 只")
        return result
    except Exception as e:
        log(f"  ⚠️ 统一板块门控失败，回退旧轮动门控: {e}")
        try:
            from sector_rotation_gate import apply_sector_rotation_gate, build_snapshot

            snap = build_snapshot()
            return apply_sector_rotation_gate(items, snap=snap, mode="soft_dual")
        except Exception as e2:
            log(f"  ⚠️ 板块轮动门控失败: {e2}")
            return items


def apply_sector_gate(items: list) -> list:
    """兼容旧名：转发到统一板块门控。"""
    return apply_sector_rotation(items)

# ═══════════════════════════════════════════════════════════════
# STEP 4: LLM 双重审核（Top 50）
# ═══════════════════════════════════════════════════════════════
def llm_review(items: list) -> list:
    """LLM新闻情绪审核 Top 50"""
    log(f"▶ LLM双重审核: {min(50, len(items))} 只...")

    if not items:
        return items

    top50 = items[:50]
    bonus_count = 0

    def review_one(item):
        nonlocal bonus_count
        name = item.get("name", "")
        sym = item.get("symbol", "")
        if not name or not sym:
            return None

        # 拉取新闻（多源）
        news = []
        # 源1: akshare 东财新闻
        try:
            import akshare as ak
            df = ak.stock_news_em(symbol=sym.replace("sh","").replace("sz",""))
            if df is not None and not df.empty:
                for _, row in df.head(3).iterrows():
                    title = str(row.get("新闻标题", row.get("title", row.get("content", ""))))
                    if title and len(title) > 5:
                        news.append(title[:80])
        except:
            pass
        # 源2: 新浪快讯（备用）
        if len(news) < 2:
            try:
                r = requests.get("https://feed.mix.sina.com.cn/api/roll/get",
                    params={"pageid": "153", "lid": "2510", "num": 5},
                    headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
                if r.status_code == 200:
                    data = r.json()
                    for item in data.get("result", {}).get("data", []):
                        t = item.get("title", "")
                        if t and len(t) > 5:
                            news.append(t[:80])
            except:
                pass

        if not news:
            # soft-fail: keep stock, neutral sentiment (avoid emptying funnel)
            return (sym, 0.0, "无新闻-中性放行")

        # LLM分析
        prompt = (
            "分析以下股票最新新闻标题，判断其短期情绪（利好/中性/利空），返回一个情绪分（-0.02到+0.03）、以及一句话理由。"
            f"\n股票: {name}({sym})\n新闻:\n" + "\n".join(f"- {n}" for n in news) +
            "\n\n格式: JSON {\"sentiment\": float, \"reason\": str}"
        )
        try:
            r = requests.post(LLM_URL, json={
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1, "max_tokens": 200,
            }, headers={"Authorization": f"Bearer {LLM_KEY}"}, timeout=10)
            if r.status_code == 200:
                content = r.json()["choices"][0]["message"]["content"]
                import re
                m = re.search(r'"sentiment"\s*:\s*(-?[\d.]+)', content)
                if m:
                    sentiment = float(m.group(1))
                    sentiment = max(-0.02, min(0.03, sentiment))
                    return (sym, sentiment, content[:100])
        except:
            pass
        return None

    with ThreadPoolExecutor(max_workers=5) as ex:
        futs = {ex.submit(review_one, it): it for it in top50}
        llm_results = {}
        for fut in as_completed(futs):
            r = fut.result()
            if r:
                llm_results[r[0]] = {"sentiment": r[1], "reason": r[2]}

    # 应用LLM情绪分
    for item in items:
        sym = item.get("symbol", "")
        if sym in llm_results:
            lr = llm_results[sym]
            item["score"] = round(float(item.get("score", 0) or 0) + lr["sentiment"], 4)
            item["llm_sentiment"] = lr["sentiment"]
            item["llm_reason"] = lr["reason"][:80]
            bonus_count += 1

    items.sort(key=lambda x: -float(x.get("score", 0) or 0))
    log(f"  ✅ LLM: {bonus_count} 只有情绪分")
    return items

# ═══════════════════════════════════════════════════════════════
# STEP 5: S2 策略加权
# ═══════════════════════════════════════════════════════════════
def apply_s2_weight(items: list) -> list:
    """S2策略作为最终加权层（读取 s2_bonus / s2_score；资金门已加过一次加法分时跳过乘法以免双计）"""
    log("▶ S2策略加权...")
    n = 0
    for item in items:
        # 资金门控已把 s2_bonus 加进 score；此处仅在尚未标记时做乘法微调
        if item.get("s2_applied_in_money_gate"):
            continue
        s2 = item.get("s2_bonus", item.get("s2_score", 0)) or 0
        try:
            s2 = float(s2)
        except Exception:
            s2 = 0.0
        if s2:
            base = float(item.get("score", 0) or 0)
            item["score"] = round(base * (1 + s2 * 0.05), 4)
            n += 1
    items.sort(key=lambda x: -float(x.get("score", 0) or 0))
    log(f"  ✅ S2 微调 {n} 只（已在资金门加过的跳过）")
    return items

# ═══════════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════════
def run():
    log("🔥" * 25)
    log("AlphaPilot 选股管线 v3.1（VM2.5 + 硬门控漏斗）")
    log("🔥" * 25)

    t_start = time.time()

    # 0. 增强美股因子收集（前置数据）+ 隔夜映射落盘 + 新鲜度巡检
    ok = run_step("增强美股因子收集", "python3 us_enhanced_collector.py", 30)
    ok_ov = run_step(
        "隔夜情绪落盘",
        "python3 -c \"from overnight_sentiment import get_full_overnight_data; get_full_overnight_data()\"",
        5,
    )
    run_step(
        "隔夜新鲜度巡检",
        "python3 -u scripts/check_overnight_freshness.py --repair",
        10,
    )
    if not ok_ov:
        log("  ⚠️ 隔夜落盘失败，选股将缺少外盘加权（已告警）")

    # 1. 全市场启动形态扫描（asof=最近收盘日 → 预测下一交易日）
    gc_set = scan_volume_gc()
    # 代码集合兼容 sh/sz 前缀
    gc_bare = {str(s).replace("sh", "").replace("sz", "").replace("bj", "")[-6:] for s in gc_set}

    # 1b. 主线行业旁路池（盘前资金流入 Top 行业成分）— 与启动池合并进评分
    bypass_bare: set[str] = set()
    bypass_meta: dict = {}
    try:
        from hot_sector_bypass import build_hot_sector_bypass_pool, load_bypass_symbols

        bypass_meta = build_hot_sector_bypass_pool(log=log)
        bypass_bare = load_bypass_symbols()
    except Exception as e:
        log(f"  ⚠️ 主线旁路构建失败（不阻断 A 臂）: {e}")

    # 2. V2.2 评分 + 隔夜情绪（recommend.py 内部已有）
    ok = run_step("VM2.5模型选股", "python3 -u recommend.py", 1200)
    if not ok:
        log("❌ VM2.5选股失败，终止管线")
        return

    # 3. 读取评分结果：宇宙门控（P1: ENABLE_SURGE_ARM_B 默认开 → 软回流 arm=B）
    rec_path = f"{OUTPUT_DIR}/daily_recommend.json"
    recs = json.load(open(rec_path))
    items = recs.get("recommendations", [])

    before = len(items)
    from soft_universe_gate import apply_universe_gate

    items, uni_meta = apply_universe_gate(
        items,
        gc_bare=gc_bare,
        gc_set=gc_set,
        bypass_bare=bypass_bare,
        launch_patterns=_LAUNCH_PATTERNS,
        log=log,
    )
    n_after_launch_or_bypass = len(items)
    n_hot_bypass = int(bypass_meta.get("n") or len(bypass_bare) or 0)
    n_soft_universe = int(uni_meta.get("n_soft") or 0)
    n_arm_b = int(uni_meta.get("n_arm_b") or 0)
    if uni_meta.get("surge_arm_b"):
        log(
            f"  [P1] SURGE_ARM_B on mult={uni_meta.get('soft_mult')} "
            f"armB={n_arm_b} bypass_pool={n_hot_bypass} scored_in={before}"
        )
    elif uni_meta.get("soft_universe"):
        log(
            f"  [AUDIT] soft_universe mult={uni_meta.get('soft_mult')} "
            f"bypass_pool={n_hot_bypass} scored_in={before}"
        )
    # 4. 资金门控（A 硬 / B 软）
    items = apply_money_gate(items)
    log(f"  资金门控后: {len(items)} 只")
    # 4a. 万得板块 prefer/avoid → 仅 B 臂软加权
    #     （ENABLE_SURGE_AMBUSH=1 时 prefer 乘子关闭，防与埋伏分双计）
    try:
        from wind_sector_prefer_boost import apply_wind_b_sector_boost

        items = apply_wind_b_sector_boost(items, log=log)
    except Exception as e:
        log(f"  ⚠️ 万得B臂板块加权跳过: {e}")
    # 4a2. 涨停埋伏分（P2b）：默认 Watch 只写字段；ENABLE_SURGE_AMBUSH=1 才改分
    try:
        from surge_ambush_score import apply_surge_ambush_score

        items = apply_surge_ambush_score(items, log=log)
    except Exception as e:
        log(f"  ⚠️ 涨停埋伏分跳过: {e}")
    # 4b. 旁路票出货硬拒（防一日游独苗）
    try:
        from hot_sector_bypass import reject_bypass_distribution

        before_dist = len(items)
        items, n_dist = reject_bypass_distribution(items)
        if n_dist:
            log(f"  旁路出货硬拒: {before_dist} → {len(items)} 只（drop={n_dist}）")
    except Exception as e:
        log(f"  ⚠️ 旁路出货过滤跳过: {e}")

    # 5. 大盘/科技环境门控 + 仓位缩放
    items, mkt_meta = apply_market_env(items)
    log(f"  大盘环境门控后: {len(items)} 只  exposure={mkt_meta.get('position_exposure')}")

    # 6. 板块资金轮动硬门控（流出板块直接剔除，不加减分）— 90s超时
    if items:
        try:
            with ThreadPoolExecutor(max_workers=1) as ex:
                fut = ex.submit(apply_sector_rotation, items)
                items = fut.result(timeout=90)
        except Exception as e:
            log(f"  ⚠️ 板块轮动门控超时/失败: {e}")

    # 6b. K 系统位置/形态（默认只标注+弱加分；硬剔除需 ENABLE_K_LOCATION_GATE=1）
    # 回测结论(2026-04~07): 硬闸门相对 A0 总收益/胜率/回撤均变差，故生产默认关闭硬删。
    try:
        from k_system_factors import apply_k_location_gate

        before_k = len(items)
        asof = None
        try:
            asof = (recs.get("asof") or recs.get("date") or "")[:10] or None
        except Exception:
            asof = None
        hard = os.environ.get("ENABLE_K_LOCATION_GATE", "0").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
        items = apply_k_location_gate(items, asof=asof, hard=hard)
        if hard:
            log(f"  K位置硬闸门: {before_k} → {len(items)} 只")
        else:
            log(f"  K位置标注/弱校准: {len(items)} 只（硬闸门关闭，ENABLE_K_LOCATION_GATE=0）")
    except Exception as e:
        log(f"  ⚠️ K位置模块跳过: {e}")

    # 7. 草木皆兵软加分（不删票）→ 趋势首选软加分 → 按池大小截断 → LLM / S2
    try:
        from caomujiebing_factor import apply_caomujiebing_soft_boost

        items = apply_caomujiebing_soft_boost(items, mkt_meta=mkt_meta)
        log(f"  草木皆兵软加分后: {len(items)} 只")
    except Exception as e:
        log(f"  ⚠️ 草木皆兵跳过: {e}")

    try:
        from trend_prefer_boost import apply_trend_prefer_boost

        before_tp = len(items)
        items = apply_trend_prefer_boost(items)
        n_pref = sum(1 for x in items if x.get("trend_prefer"))
        n_down = before_tp - len(items)
        log(
            f"  趋势首选软加分后: {len(items)} 只（首选 {n_pref}/{before_tp}"
            + (f"，下跌通道剔除 {n_down}" if n_down else "")
            + "）"
        )
    except Exception as e:
        log(f"  ⚠️ 趋势首选跳过: {e}")

    # 7b. 热门板块优先（allow 行业/概念软加分 → 提高进 Top1–3 概率）
    try:
        from hot_sector_prefer_boost import apply_hot_sector_prefer_boost

        items = apply_hot_sector_prefer_boost(items, log=log)
    except Exception as e:
        log(f"  ⚠️ 热门板块优先跳过: {e}")

    pool_n = int(mkt_meta.get("recommend_pool_n") or 50)
    trade_n = int(mkt_meta.get("recommend_top_n") or 2)

    # 8. 执行层：近涨停不报，但向下补位（避免热门票被踢后池子只剩冷票）
    def _limit_frac(sym: str) -> float:
        s = str(sym or "").replace("sh", "").replace("sz", "")[-6:]
        if s.startswith(("300", "301", "688")):
            return 0.20
        return 0.10

    items_sorted = sorted(items, key=lambda x: -float(x.get("score") or 0))
    exec_notes = []
    filtered = []
    for it in items_sorted:
        if pool_n > 0 and len(filtered) >= pool_n:
            break
        chg = it.get("change_pct") or it.get("pct_chg") or it.get("signal_chg")
        try:
            chg_f = float(chg) / (100.0 if abs(float(chg)) > 1 else 1.0) if chg is not None else None
        except Exception:
            chg_f = None
        lim = _limit_frac(it.get("symbol", ""))
        if chg_f is not None and chg_f >= lim * 0.97:
            exec_notes.append({"symbol": it.get("symbol"), "reason": "signal_near_limit", "chg": chg_f})
            continue
        it = dict(it)
        it["position_exposure"] = mkt_meta.get("position_exposure", 1.0)
        it["exec_hint"] = "buy_t1_open_skip_if_limit; sell_t2_close"
        filtered.append(it)
    top_pool = filtered
    if exec_notes:
        log(f"  近涨停跳过并补位: drop={len(exec_notes)} pool={len(top_pool)}/{pool_n}")

    # 可选 LLM / S2（在已补位池上）
    if top_pool:
        top_pool = llm_review(top_pool)
        top_pool = apply_s2_weight(top_pool)
        top_pool = sorted(top_pool, key=lambda x: -float(x.get("score") or 0))[:pool_n] if pool_n > 0 else top_pool


    # 9. 保存最终结果（池=pool_n；下单只数见 recommend_top_n）
    recs["recommendations"] = top_pool
    recs["pipeline_version"] = "v3.1_funnel_gated"
    recs["model_version"] = recs.get("model_version") or "v25"
    recs["total_candidates"] = len(items)
    recs["position_exposure"] = mkt_meta.get("position_exposure", 1.0)
    recs["recommend_top_n"] = trade_n
    recs["recommend_pool_n"] = pool_n
    recs["market_env_flags"] = mkt_meta.get("flags") or {}
    recs["permission"] = mkt_meta.get("permission")
    recs["exposure_mode"] = mkt_meta.get("exposure_mode")
    if mkt_meta.get("weak_rotation_sleeve") is not None:
        recs["weak_rotation_sleeve"] = mkt_meta.get("weak_rotation_sleeve")
    recs["exec_excluded_near_limit"] = exec_notes
    recs["soft_universe"] = uni_meta
    recs["surge_arm_b"] = {
        "enabled": bool(uni_meta.get("surge_arm_b")),
        "mult": uni_meta.get("soft_mult"),
        "n_arm_b": n_arm_b,
        "n_arm_a_launch": uni_meta.get("n_launch"),
        "n_arm_a_bypass": uni_meta.get("n_bypass"),
    }
    try:
        from surge_ambush_score import enabled as _ambush_enabled

        ambush_apply = bool(_ambush_enabled())
    except Exception:
        ambush_apply = False
    n_amb_strong = sum(1 for x in items if str(x.get("arm")) == "B" and x.get("surge_ambush_tier") == "strong")
    n_amb_mid = sum(1 for x in items if str(x.get("arm")) == "B" and x.get("surge_ambush_tier") == "mid")
    n_amb_plain = sum(1 for x in items if str(x.get("arm")) == "B" and x.get("surge_ambush_tier") == "plain")
    recs["surge_ambush"] = {
        "apply": ambush_apply,
        "n_b_strong": n_amb_strong,
        "n_b_mid": n_amb_mid,
        "n_b_plain": n_amb_plain,
        "watch_mode": not ambush_apply,
    }
    if uni_meta.get("surge_arm_b"):
        recs["pipeline_version"] = "v3.5_surge_ambush" if ambush_apply else "v3.4_surge_arm_b"
    else:
        recs["pipeline_version"] = "v3.3_hot_prefer"
    if uni_meta.get("soft_universe") and not uni_meta.get("surge_arm_b"):
        recs["pipeline_version"] = "v3.3_soft_universe_hot_prefer"
    recs["generated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")

    # 统计：全量扫描 = 全A扫描只数（~5000），不是启动形态命中数
    elapsed = int(time.time() - t_start)
    old_stats = recs.get("stats") if isinstance(recs.get("stats"), dict) else {}
    universe_n = 0
    launch_hits = len(gc_set) if gc_set is not None else 0
    try:
        lp = json.load(open(f"{OUTPUT_DIR}/launch_patterns_pool.json", encoding="utf-8"))
        universe_n = int(lp.get("n_scan") or 0)
        launch_hits = int(lp.get("n_hit") or launch_hits)
    except Exception:
        pass
    if universe_n <= 0:
        universe_n = int(old_stats.get("universe_n") or 0)
    recs["stats"] = {
        "total_scanned": universe_n or int(old_stats.get("total_scanned") or 0),
        "universe_n": universe_n,
        "launch_hits": launch_hits,
        "hot_bypass_n": n_hot_bypass,
        "soft_universe_n": n_soft_universe,
        "model_pool_scored": int(old_stats.get("total_scanned") or 0),
        "valid_scored": int(old_stats.get("valid_scored") or len(top_pool)),
        "elapsed_seconds": elapsed,
        "funnel": {
            "universe": universe_n,
            "launch_hits": launch_hits,
            "hot_bypass_n": n_hot_bypass,
            "soft_universe_n": n_soft_universe,
            "after_universe_gate": n_after_launch_or_bypass,
            "after_launch_or_bypass": n_after_launch_or_bypass,
            "after_model_x_launch": n_after_launch_or_bypass,
            "after_money": None,
            "final_pool": len(top_pool),
            "soft_universe": bool(uni_meta.get("soft_universe")),
            "soft_mult": uni_meta.get("soft_mult"),
        },
    }
    json.dump(recs, open(rec_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    log("=" * 50)
    log(f"🚀 管线完成! 池内 {len(top_pool)} 只（pool_n={pool_n}），下单 Top{trade_n}")
    log(f"总耗时: {elapsed}s ({elapsed//60}分{elapsed%60}秒)")
    log(f"全量扫描: {universe_n} 只 | 启动形态命中: {launch_hits} 只 | 有效评分: {recs['stats'].get('valid_scored')}")
    log(f"Trade Top{trade_n}: {[x.get('name','') for x in top_pool[:trade_n]]}")
    log(f"Pool names: {[x.get('name','') for x in top_pool[:pool_n]]}")
    log("=" * 50)

if __name__ == "__main__":
    run()

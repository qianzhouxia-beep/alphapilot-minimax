// AlphaPilot A 股 Dashboard
// Zeabur HTTPS -> cn_proxy.py -> 腾讯云 150.158.100.236
// 2026-07-19: 浅色 UI 统一 · 信心分展示 · 版本文案对齐
"use client";

import { useEffect, useState, useCallback, useRef, useMemo } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { HeaderBar } from "@/components/HeaderBar";
import { useAuth } from "@/lib/auth";
import { useMarketStatus } from "@/lib/market-status";
import { LockedHint, useUnlocked } from "@/components/LoginGate";
import {
  fetchCNScreener, fetchWatchlist, addToWatchlist, removeFromWatchlist,
  fetchCategorizedRecommend, fetchLiveRecommend, fetchFundStrength,
  fetchPipelineBoard, fetchScoreTop10,
  type ScreenerItem, type ScreenerResponse, type WatchlistItem,
  type CategorizedResponse, type FundStrengthData, type FundStrengthItem,
  type PipelineBoardResponse, type PipelineBoardItem,
  type ScoreTop10Response, type ScoreTop10Item, type TradePlan,
} from "@/lib/cn-api";
import { DISCLAIMER_FULL } from "@/lib/disclaimer";

type PeFilter = "all" | "le_30" | "gt_30";

const scoreColor = (s: number) =>
  s >= 0.50 ? "text-status-success" : s >= 0.40 ? "text-status-info" : s >= 0.30 ? "text-status-warning" : "text-text-secondary";
/** 直接展示模型分 0–100，不再映射成 75–99 信心分 */
const displayScore = (s: number) => {
  const x = Number(s || 0);
  if (!Number.isFinite(x) || x <= 0) return 0;
  if (x <= 1) return Math.round(x * 100);
  return Math.round((1 / (1 + Math.exp(-x / 2))) * 100);
};

function peBucketOf(it: any): PeFilter | "na" {
  if (it?.pe_bucket === "le_30" || it?.pe_bucket === "gt_30" || it?.pe_bucket === "na") {
    return it.pe_bucket;
  }
  const pe = it?.pe_ttm ?? it?.pe;
  if (pe == null || Number(pe) <= 0 || Number.isNaN(Number(pe))) return "na";
  return Number(pe) > 30 ? "gt_30" : "le_30";
}

// ─── 价格日期标注工具 ───
function isTradingHours(): boolean {
  const now = new Date();
  const cst = new Date(now.toLocaleString("en-US", { timeZone: "Asia/Shanghai" }));
  const d = cst.getDay(), h = cst.getHours(), m = cst.getMinutes();
  return d >= 1 && d <= 5 && (h * 60 + m) >= 570 && (h * 60 + m) < 900; // 09:30-15:00
}
function getPriceLabel(): { label: string; date: string } {
  const now = new Date();
  const cst = new Date(now.toLocaleString("en-US", { timeZone: "Asia/Shanghai" }));
  const d = cst.getDay();
  const fmt = (dt: Date) => `${String(dt.getMonth()+1).padStart(2,"0")}/${String(dt.getDate()).padStart(2,"0")}`;
  if (isTradingHours()) return { label: "实时", date: fmt(cst) };
  // 非交易时间→最近收盘日
  let offset = 1;
  if (d === 1) offset = 3;  else if (d === 0) offset = 2;
  const last = new Date(cst);
  last.setDate(last.getDate() - offset);
  return { label: "收盘", date: fmt(last) };
}

const scoreLabel = (s: number) =>
  s >= 0.50 ? "A+" : s >= 0.35 ? "A" : s >= 0.25 ? "B+" : "B";

function passTrendFilter(
  item: any,
  filter: "all" | "uptrend" | "downtrend"
): boolean {
  if (filter === "all") return true;
  const isDowntrend = item.channel_reject === true || item.downtrend_channel === true;
  if (filter === "downtrend") return isDowntrend;
  return !isDowntrend;
}

export default function CNDashboard() {
  const { session, ready, openAuth } = useAuth();
  const router = useRouter();
  const mkt = useMarketStatus();
  const { unlocked: priceUnlocked } = useUnlocked();
  const [data, setData] = useState<ScreenerResponse | null>(null);
  const [fundStrength, setFundStrength] = useState<FundStrengthData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [watchlistSymbols, setWatchlistSymbols] = useState<Set<string>>(new Set());
  const [wlData, setWlData] = useState<WatchlistItem[]>([]);
  const [wlLoading, setWlLoading] = useState<Record<string, boolean>>({});
  const [wlMsg, setWlMsg] = useState<{ type: string; text: string } | null>(null);
  const [catData, setCatData] = useState<CategorizedResponse | null>(null);
  const [catLoading, setCatLoading] = useState(true);
  const [pbData, setPbData] = useState<PipelineBoardResponse | null>(null);
  const [top10, setTop10] = useState<ScoreTop10Response | null>(null);
  const [pbLoading, setPbLoading] = useState(true);
  const [top10Loading, setTop10Loading] = useState(true);
  const [priceDialog, setPriceDialog] = useState<{ item: any; price: string } | null>(null);
  const [priceDialogLoading, setPriceDialogLoading] = useState(false);
  // 实时状态标记
  const [liveTs, setLiveTs] = useState<number>(0);
  const [livePolling, setLivePolling] = useState<boolean>(false);
  const [overnightData, setOvernightData] = useState<any>(null);
  const [peFilter, setPeFilter] = useState<PeFilter>("all");
  const [trendFilter, setTrendFilter] = useState<"all" | "uptrend" | "downtrend">("all");
  const [slowLoad, setSlowLoad] = useState(false);

  // 加载超过 8 秒给出友好提示（生产接口偶尔较慢）
  useEffect(() => {
    if (!loading) { setSlowLoad(false); return; }
    const t = setTimeout(() => setSlowLoad(true), 8000);
    return () => clearTimeout(t);
  }, [loading]);

  const loadData = async (wlRefresh = false) => {
    try {
      const [d, cat, fs] = await Promise.all([
        fetchCNScreener(),
        fetchCategorizedRecommend(),
        fetchFundStrength().catch(() => null),
      ]);
      setData(d);
      setCatData(cat);
      if (fs) setFundStrength(fs);
      setError(null);
      try {
        const raw = typeof window !== "undefined" ? localStorage.getItem("alphapilot_session") : null;
        if (raw) {
          const wl = await fetchWatchlist(wlRefresh);
          setWlData(wl.watchlist || []);
          setWatchlistSymbols(new Set((wl.watchlist || []).map((w: WatchlistItem) => String(w.symbol || "").replace(/\D/g, "").slice(-6))));
        } else {
          setWlData([]);
          setWatchlistSymbols(new Set());
        }
      } catch {
        setWlData([]);
        setWatchlistSymbols(new Set());
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  // 侧栏：管线评分榜 + 评分Top10 定格（独立加载，失败不影响主区）
  const loadSidebar = useCallback(async () => {
    try {
      const [pb, t10] = await Promise.all([
        fetchPipelineBoard(200).catch(() => null),
        fetchScoreTop10().catch(() => null),
      ]);
      if (pb) setPbData(pb);
      if (t10) setTop10(t10);
    } catch {
      // 侧栏数据失败时静默，主区不受影响
    } finally {
      setPbLoading(false);
      setTop10Loading(false);
    }
  }, []);

  
  useEffect(() => {
    fetch("/api/v1/cn/overnight")
      .then(r => r.json())
      .then(d => setOvernightData(d))
      .catch(() => {});
  }, []);
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    Promise.all([loadData(true), loadSidebar()]).finally(() => {
      if (!cancelled) { setLoading(false); setCatLoading(false); setPbLoading(false); setTop10Loading(false); }
    });
    return () => { cancelled = true; };
  }, [loadSidebar]);

  // 30 min auto refresh (全量评分+分类)
  useEffect(() => {
    const id = setInterval(() => loadData(false), 30 * 60 * 1000);
    return () => clearInterval(id);
  }, []);

  // 30 min auto refresh (侧栏：管线评分榜 + 评分Top10 定格)
  useEffect(() => {
    const id = setInterval(() => loadSidebar(), 30 * 60 * 1000);
    return () => clearInterval(id);
  }, [loadSidebar]);

  // 收藏追踪与收藏页同源：交易时段每 60s 刷新一次（仅已登录）
  useEffect(() => {
    if (!ready || !session) return;
    const id = setInterval(() => {
      fetchWatchlist(false)
        .then((wl) => {
          setWlData(wl.watchlist || []);
          setWatchlistSymbols(
            new Set(
              (wl.watchlist || []).map((w: WatchlistItem) =>
                String(w.symbol || "").replace(/\D/g, "").slice(-6)
              )
            )
          );
        })
        .catch(() => {});
    }, 60_000);
    return () => clearInterval(id);
  }, [ready, session]);

  // 轮询计数器：每5次（5分钟）触发一次动态重排
  const rerankCounterRef = useRef(0);

  // 60秒实时资金流刷新 + 每5分钟动态重排

  useEffect(() => {
    const pollLive = async () => {
      if (document.hidden) return; // 标签页隐藏时不轮询
      // 非交易时间不轮询（9:25-15:05 为交易时段，仅工作日）
      const _now = new Date();
      const _h = _now.getHours(), _m = _now.getMinutes(), _d = _now.getDay();
      const _isWeekend = _d === 0 || _d === 6;
      const _isBeforeOpen = _h < 9 || (_h === 9 && _m < 25);
      const _isAfterClose = _h > 15 || (_h === 15 && _m > 5);
      const _isLunchBreak = _h === 11 && _m > 30;
      if (_isWeekend || _isBeforeOpen || _isAfterClose || _isLunchBreak) return;
      setLivePolling(true);
      rerankCounterRef.current += 1;
      // 第1次（页面加载5秒后）和此后每5次（每5分钟）做动态重排
      const isRerank = rerankCounterRef.current === 1 || rerankCounterRef.current % 5 === 0;

      try {
        // 重排时：rerank=true 获取 Top 100 动态重排
        // 其他时候：普通60秒字段合并
        const topN = isRerank ? 100 : 50;
        const live = await fetchLiveRecommend(topN, isRerank);
        setLiveTs(live.ts || Date.now() / 1000);

        // 重排时：直接替换整个推荐列表
        if (isRerank && live.rerank && live.data && live.data.length > 0) {
          // 只取重排后的前10只（提升性能）
          const reranked = live.data.slice(0, 10).map((it: any) => ({
            ...it,
            _reranked: true,
          }));
          setData((prev) => {
            if (!prev) return prev;
            // 从 trade_plan 提取今日交易 Top2，重排后仍保留「今日交易」标记
            const tradeSyms = new Set(
              (prev.trade_plan?.buys ?? [])
                .filter((b: any) => b?.action !== "skip" && b?.symbol)
                .map((b: any) => String(b.symbol).replace(/\D/g, "").slice(-6))
            );
            const withTradeMark = reranked.map((it: any) => {
              const sym = String(it.symbol || "").replace(/\D/g, "").slice(-6);
              return tradeSyms.has(sym) ? { ...it, is_trade_pick: true } : it;
            });
            return { ...prev, recommendations: withTradeMark };
          });
          console.log(`[rerank] ${new Date().toLocaleTimeString()} 动态重排完成`);
        } else if (live && live.data && live.data.length > 0) {
          // 普通60秒：字段级合并（不改变排名）
          setData((prev) => {
            if (!prev) return prev;
            const liveMap = new Map(live.data.map((it: any) => [it.symbol, it]));
            const updated = (prev.recommendations ?? []).map((it: any) => {
              const liveItem = liveMap.get(it.symbol);
              if (liveItem) {
                const isLiveReal = liveItem._data_source === "live";
                const currentAbr = it.active_buy_ratio;
                const liveAbr = liveItem.active_buy_ratio;
                const finalAbr = isLiveReal
                  ? liveAbr
                  : (currentAbr !== undefined && currentAbr !== null ? currentAbr : liveAbr);
                return {
                  ...it,
                  active_buy_ratio: finalAbr,
                  money_phase_label: isLiveReal
                    ? (liveItem.money_phase_label ?? it.money_phase_label)
                    : (it.money_phase_label ?? liveItem.money_phase_label),
                  change_pct: isLiveReal
                    ? (liveItem.change_pct ?? it.change_pct)
                    : (it.change_pct ?? liveItem.change_pct),
                  turnover: isLiveReal
                    ? (liveItem.turnover ?? it.turnover)
                    : (it.turnover ?? liveItem.turnover),
                  price: isLiveReal
                    ? (liveItem.price ?? it.price)
                    : (it.price ?? liveItem.price),
                };
              }
              return it;
            });
            return { ...prev, recommendations: updated };
          });
        }
      } catch (e) {
        console.warn("[live poll]", e);
      } finally {
        setLivePolling(false);
      }
    };
    // 首次延迟 5 秒，等初始 loadData 完成
    const initial = setTimeout(pollLive, 5000);
    const id = setInterval(pollLive, 60 * 1000);
    return () => { clearTimeout(initial); clearInterval(id); };
  }, []);

  const handleRefresh = async () => {
    setRefreshing(true);
    await loadData(true);
    setRefreshing(false);
  };

  const bareSym = (s?: string) => String(s || "").replace(/\D/g, "").slice(-6);

  const handleToggleWatchlist = async (item: ScreenerItem) => {
    if (!session) {
      openAuth("login", "/cn");
      return;
    }
    const sym = bareSym(item.symbol);
    if (watchlistSymbols.has(sym)) {
      try {
        await removeFromWatchlist(sym);
        setWatchlistSymbols(prev => { const n = new Set(prev); n.delete(sym); return n; });
        setWlMsg({ type: "success", text: `已取消收藏 ${item.name}` });
      } catch (e: any) {
        setWlMsg({ type: "error", text: e.message || "操作失败" });
      }
      setTimeout(() => setWlMsg(null), 3000);
      try {
        const wl = await fetchWatchlist(true);
        setWlData(wl.watchlist || []);
        setWatchlistSymbols(new Set((wl.watchlist || []).map((w) => bareSym(w.symbol))));
      } catch {}
    } else {
      const defaultPrice = item.buy_price || 0;
      setPriceDialog({ item, price: (defaultPrice > 0 ? defaultPrice : "").toString() });
    }
  };

  const confirmAddWatchlist = async () => {
    if (!session) {
      openAuth("login", "/cn");
      return;
    }
    if (!priceDialog) return;
    const item = priceDialog.item;
    const sym = bareSym(item.symbol);
    const price = parseFloat(priceDialog.price);
    if (isNaN(price) || price <= 0) {
      setWlMsg({ type: "error", text: "请输入有效的买入价格" });
      setTimeout(() => setWlMsg(null), 3000);
      return;
    }
    setPriceDialogLoading(true);
    try {
      await addToWatchlist(sym, item.name, price, item.score || 0);
      setWatchlistSymbols(prev => new Set(prev).add(sym));
      setWlMsg({ type: "success", text: `已添加收藏 ${item.name} @ ¥${price.toFixed(2)}` });
      setPriceDialog(null);
    } catch (e: any) {
      setWlMsg({ type: "error", text: e.message || "添加失败" });
    }
    setPriceDialogLoading(false);
    setTimeout(() => setWlMsg(null), 3000);
    try {
      const wl = await fetchWatchlist(true);
      setWlData(wl.watchlist || []);
      setWatchlistSymbols(new Set((wl.watchlist || []).map((w) => bareSym(w.symbol))));
    } catch {}
  };

  const items = data?.recommendations ?? [];
  const peCounts = useMemo(() => {
    const c = { all: items.length, le_30: 0, gt_30: 0, na: 0 };
    items.forEach((it) => {
      const b = peBucketOf(it);
      if (b === "le_30") c.le_30 += 1;
      else if (b === "gt_30") c.gt_30 += 1;
      else c.na += 1;
    });
    return c;
  }, [items]);
  const filteredItems = useMemo(() => {
    let f = items;
    if (peFilter !== "all") f = f.filter((it) => peBucketOf(it) === peFilter);
    if (trendFilter !== "all") f = f.filter((it) => passTrendFilter(it, trendFilter));
    return f;
  }, [items, peFilter, trendFilter]);
  const buildSectorChanges = (stockList: any[]) => {
    const groups: Record<string, number[]> = {};
    stockList.forEach((it: any) => {
      const sec = it.sector;
      const chg = it.change_pct;
      if (sec && chg != null) {
        if (!groups[sec]) groups[sec] = [];
        groups[sec].push(chg);
      }
    });
    const result: Record<string, number> = {};
    Object.entries(groups).forEach(([sec, chgs]) => {
      if (chgs.length < 2) return; // 只有1只股票时不显示板块涨跌幅，避免等于个股自身
      chgs.sort((a: number, b: number) => a - b);
      result[sec] = chgs[Math.floor(chgs.length / 2)];
    });
    return result;
  };
  const sectorChanges = buildSectorChanges(items);
  if (catData?.categories) {
    const catStocks = Object.values(catData.categories ?? {}).flatMap((cat: any) => cat?.stocks || []);
    const catChanges = buildSectorChanges(catStocks);
    Object.entries(catChanges).forEach(([k, v]) => { sectorChanges[k] = v; });
  }
  const markupStocks = catData?.categories?.markup?.stocks ?? [];
  const isMarkupTop = markupStocks.length > 0;
  const top = isMarkupTop
    ? markupStocks.reduce((best, s) => (s.score_pct ?? 0) > (best.score_pct ?? 0) ? s : best, markupStocks[0])
    : (items.find(it => it.money_flow_pass === true) || items[0]);
  const avgScore = items.length ? (items.reduce((s, i) => s + (Number(i.score) || 0), 0) / items.length) : 0;
  const returnedCount = data?.stats?.returned ?? items.length;
  const validScored = data?.stats?.valid_scored;
  const totalScanned = data?.stats?.total_scanned;

  // 实时状态显示
  const liveAgo = liveTs > 0 ? Math.max(0, Math.floor(Date.now() / 1000 - liveTs)) : null;
  const liveStatusText = liveAgo === null
    ? "等待首次实时刷新"
    : liveAgo < 5 ? "刚刚"
    : liveAgo < 60 ? `${liveAgo}秒前`
    : `${Math.floor(liveAgo / 60)}分钟前`;

  return (
    <main className="mx-auto max-w-[1200px] px-4 sm:px-6 lg:px-8 py-3 sm:py-5 lg:py-6 min-h-screen">
      <HeaderBar market="cn" />

      {/* ══ 页面标题 + 今日概览（顶部摘要） ══ */}
      <div className="mb-4 sm:mb-5">
        <h1 className="text-[26px] font-semibold tracking-tight text-text-primary sm:text-[30px]">工作台</h1>
        <p className="mt-1 text-[13px] leading-relaxed text-text-secondary">
          {mkt ? `${mkt.date} · ` : ""}今日研究概览。评分为模型输出的相对排序，不是上涨概率；内容仅供研究参考，不构成投资建议。
        </p>
      </div>

      <section aria-label="今日概览" className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
        <Stat
          label="市场状态"
          value={mkt ? mkt.label : "—"}
          sub={mkt ? `北京时间 ${mkt.clock}` : "读取中"}
          dot={mkt ? (mkt.tone === "live" ? "bg-status-success" : mkt.tone === "wait" ? "bg-status-warning" : "bg-black/30") : "bg-black/20"}
        />
        <Stat
          label="今日入选"
          value={data ? `${returnedCount} 只` : "—"}
          sub={data ? `名单内 ${items.length} 只` : "加载中"}
        />
        <Stat
          label="名单最高评分"
          value={top ? top.name : "—"}
          sub={
            top
              ? `${String(top.symbol ?? "").replace(/^(sh|sz)/, "")} · 评分 ${displayScore(top.score)}${
                  isMarkupTop ? " · 拉升确认" : top.money_phase_label ? " · " + top.money_phase_label : ""
                }`
              : "暂无"
          }
        />
        <Stat
          label="名单平均评分"
          value={data && items.length ? `${displayScore(avgScore)}` : "—"}
          sub="模型评分，非概率、非百分制"
        />
        <Stat
          label="实时资金"
          value={livePolling ? "更新中" : liveAgo != null ? "已同步" : "—"}
          sub={`${liveStatusText} · 每 60 秒刷新`}
        />
        <Stat
          label="扫描覆盖"
          value={validScored != null ? `${validScored} 只` : "—"}
          sub={totalScanned != null ? `共 ${totalScanned} 只 · 耗时约 ${((data?.stats?.elapsed_seconds || 0) / 60).toFixed(0)} 分钟` : "暂无统计"}
        />
      </section>

      <DataStatusCard />

      {wlMsg && (
        <div className={`fixed top-20 right-4 z-50 rounded-xl p-4 shadow-2xl ${
          wlMsg.type === "success" ? "bg-status-success/15 border border-status-success" : "bg-status-danger/15 border border-status-danger"
        }`}>
          <p className="text-[13px] text-text-primary">{wlMsg.text}</p>
        </div>
      )}

      {error && (
        <div className={`card-lift mb-6 rounded-2xl border p-4 shadow-sm ${
          /401|未登录/.test(error)
            ? "border-status-warning bg-surface-card"
            : "border-border-medium bg-surface-card"
        }`}>
          <div className="flex items-start gap-3">
            <svg className={`w-6 h-6 shrink-0 ${/401|未登录/.test(error) ? "text-status-warning" : "text-purple-primary"}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
            <div className="flex-1">
              {/401|未登录/.test(error) ? (
                <>
                  <p className="text-sm text-status-warning font-semibold">需要登录后查看个人数据</p>
                  <p className="mt-1 text-[12px] text-text-secondary">收藏夹与模拟盘已改为私有，公开行情仍可浏览。</p>
                  <div className="mt-3 flex gap-2">
                    <button
                      type="button"
                      onClick={() => {
                        setError(null);
                        openAuth("login", "/cn");
                      }}
                      className="rounded-lg bg-status-info px-4 py-2 text-[12px] font-semibold text-white hover:opacity-90"
                    >
                      去登录
                    </button>
                    <button onClick={() => setError(null)} className="rounded-lg border border-border-subtle px-4 py-2 text-[12px] text-text-secondary hover:text-text-primary">
                      关闭
                    </button>
                  </div>
                </>
              ) : (
                <>
                  <p className="text-sm text-text-primary font-semibold">数据暂时没能加载出来</p>
                  <p className="mt-1 text-[12px] leading-relaxed text-text-secondary">可能是网络波动或服务正在更新，请稍后重试。</p>
                  <button onClick={handleRefresh} className="mt-3 rounded-lg bg-purple-primary px-4 py-2 text-[12px] font-semibold text-white hover:opacity-90">
                    重新加载
                  </button>
                  <details className="mt-3 text-[11px] text-text-tertiary">
                    <summary className="cursor-pointer select-none">查看技术详情</summary>
                    <p className="mt-1 break-all">{error}</p>
                  </details>
                </>
              )}
            </div>
          </div>
        </div>
      )}

      <div className="space-y-6 sm:space-y-8">
      {/* ══ 今日重点名单（主区） ══ */}
      <section aria-labelledby="focus-title">
        <div className="mb-3 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h2 id="focus-title" className="text-[20px] font-semibold tracking-tight text-text-primary">今日重点名单</h2>
              {items[0]?._reranked && (
                <span className="inline-flex items-center gap-1 rounded-full border border-purple-primary/20 bg-purple-light px-2 py-0.5 text-[11px] text-purple-primary">
                  <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-purple-primary motion-reduce:animate-none" />
                  动态更新
                </span>
              )}
              {liveTs > 0 && (
                <span className="inline-flex items-center gap-1 rounded-full border border-border-subtle bg-white px-2 py-0.5 text-[11px] text-text-secondary">
                  资金实时 · {liveStatusText}
                </span>
              )}
            </div>
            <p className="mt-1 max-w-2xl text-[13px] leading-relaxed text-text-secondary">
              由量化模型综合筛选，按评分排序。评分是模型对标的的相对排序，不是上涨概率，仅供研究参考。
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <Link href="/cn/watchlist" className="rounded-full border border-border-subtle bg-surface-card px-3.5 py-1.5 text-[12px] text-text-secondary transition-colors hover:border-purple-primary/40 hover:text-purple-primary whitespace-nowrap">
              我的收藏
            </Link>
            <button
              onClick={handleRefresh}
              disabled={refreshing}
              className="flex cursor-pointer items-center gap-1.5 rounded-full border border-border-subtle bg-surface-card px-3.5 py-1.5 text-[12px] text-text-secondary transition-colors hover:border-purple-primary/40 hover:text-purple-primary disabled:cursor-not-allowed disabled:opacity-50 whitespace-nowrap"
            >
              <svg className={`h-3.5 w-3.5 ${refreshing ? "animate-spin" : ""}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                <polyline points="23 4 23 10 17 10" />
                <polyline points="1 20 1 14 7 14" />
                <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
              </svg>
              {refreshing ? "刷新中…" : "刷新名单"}
            </button>
          </div>
        </div>

        {/* 筛选：独立一行，窄屏可横向滑动，不撑破页面 */}
        <div className="mb-4 -mx-4 overflow-x-auto px-4 sm:mx-0 sm:overflow-visible sm:px-0" role="group" aria-label="筛选条件">
          <div className="flex w-max items-center gap-2 sm:w-auto sm:flex-wrap">
            <div className="inline-flex items-center gap-0.5 rounded-full bg-black/[0.045] p-0.5">
              {(
                [
                  { key: "all" as PeFilter, label: "全部", n: peCounts.all },
                  { key: "le_30" as PeFilter, label: "PE≤30", n: peCounts.le_30 },
                  { key: "gt_30" as PeFilter, label: "PE>30", n: peCounts.gt_30 },
                ] as const
              ).map((opt) => (
                <button
                  key={opt.key}
                  type="button"
                  aria-pressed={peFilter === opt.key}
                  onClick={() => setPeFilter(opt.key)}
                  className={`cursor-pointer whitespace-nowrap rounded-full px-3 py-1 text-[12px] transition-colors ${
                    peFilter === opt.key ? "bg-white font-medium text-purple-primary shadow-sm" : "text-text-secondary hover:text-text-primary"
                  }`}
                >
                  {opt.label}
                  <span className="ml-1 text-[10px] text-text-tertiary">{opt.n}</span>
                </button>
              ))}
            </div>
            <div className="inline-flex items-center gap-0.5 rounded-full bg-black/[0.045] p-0.5">
              {[
                { key: "all" as const, label: "趋势不限" },
                { key: "uptrend" as const, label: "↑ 上升" },
                { key: "downtrend" as const, label: "↓ 下跌" },
              ].map((opt) => (
                <button
                  key={opt.key}
                  type="button"
                  aria-pressed={trendFilter === opt.key}
                  onClick={() => setTrendFilter(opt.key)}
                  className={`cursor-pointer whitespace-nowrap rounded-full px-3 py-1 text-[12px] transition-colors ${
                    trendFilter === opt.key ? "bg-white font-medium text-purple-primary shadow-sm" : "text-text-secondary hover:text-text-primary"
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        {loading && (
          <div className="flex flex-col items-center justify-center py-14" role="status">
            <div className="h-10 w-10 animate-spin rounded-full border-4 border-border-subtle border-t-purple-primary"></div>
            <p className="mt-4 text-[14px] text-text-secondary">正在加载今日名单…</p>
            {slowLoad && (
              <p className="mt-2 max-w-sm text-center text-[12px] leading-relaxed text-text-tertiary">
                服务器响应较慢，请稍候片刻。如长时间没有内容，可点击上方“刷新”重试。
              </p>
            )}
          </div>
        )}

        {!loading && !error && data && items.length === 0 && (
          <div className="py-12 text-center">
            <p className="text-[16px] font-semibold text-text-primary">今日暂无入选标的</p>
            <p className="mx-auto mt-2 max-w-md text-[13px] leading-relaxed text-text-secondary">
              行情偏弱或没有满足条件的标的时，系统会主动留空，而不是为了凑数硬推名单。下一交易日开盘后会重新扫描。
            </p>
          </div>
        )}

        {data && filteredItems.length === 0 && (
          <p className="py-8 text-center text-[13px] text-text-secondary">
            当前市盈率筛选下暂无标的，请切换「全部 / PE≤30 / PE&gt;30」
          </p>
        )}

        {data && (
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 animate-fade-in">
            {filteredItems.map((item, i) => {
              const sym = bareSym(item.symbol);
              const isFav = watchlistSymbols.has(sym);
              const isWlLoading = wlLoading[sym] ?? false;
              const changePct = item.change_pct ?? 0;
              const isUp = changePct >= 0;
              const peVal = item.pe_ttm ?? item.pe;
              const peB = peBucketOf(item);
              const strength = fundStrength?.items?.[sym];
              return (
              <article key={item.symbol} className="card-lift flex flex-col rounded-2xl border border-border-subtle bg-surface-card p-4 shadow-sm">
                {/* 行 1：序号 + 名称 + 代码 | 现价 + 涨跌幅 */}
                <div className="flex items-start justify-between gap-3">
                  <div className="flex min-w-0 items-start gap-2.5">
                    <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-purple-light text-[11px] font-semibold text-purple-primary font-display-numeric">
                      {i + 1}
                    </span>
                    <div className="min-w-0">
                      <Link href={`/cn/stock?symbol=${item.symbol}`} className="block truncate text-[16px] font-semibold leading-tight text-text-primary transition-colors hover:text-purple-primary">
                        {item.name}
                      </Link>
                      <div className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[12px] text-text-tertiary">
                        <span className="font-mono">{sym}</span>
                        {item.sector && (
                          <span className="inline-flex items-center gap-1">
                            {item.channel_reject ? <span className="font-medium text-status-success">↓下跌通道</span> : item.downtrend_channel ? <span className="text-status-success">↓偏弱</span> : null}
                            <span>{item.sector}</span>
                            {item.sector_change_pct != null && (
                              <span className={`${item.sector_change_pct >= 0 ? "text-status-danger" : "text-status-success"}`}>
                                {item.sector_change_pct > 0 ? "+" : ""}{item.sector_change_pct.toFixed(1)}%
                              </span>
                            )}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                  <div className="shrink-0 text-right">
                    {(() => {
                      const pl = getPriceLabel();
                      const mainPrice = priceUnlocked ? (item.live_price || item.buy_price || 0) : (item.live_price || (item as any).price || 0);
                      return (
                        <>
                          <div className="text-[18px] font-bold font-display-numeric leading-tight text-text-primary">
                            ¥{mainPrice > 0 ? mainPrice.toFixed(2) : "—"}
                          </div>
                          <div className={`text-[13px] font-semibold font-display-numeric ${isUp ? "text-status-danger" : "text-status-success"}`}>
                            {changePct > 0 ? "+" : ""}{changePct.toFixed(2)}%
                          </div>
                          <div className="mt-0.5 text-[11px] text-text-tertiary">
                            {pl.label} {pl.date}
                            {priceUnlocked && item.buy_price > 0 && Math.abs(item.buy_price - mainPrice) > 0.004 ? ` · 名单参考价 ¥${item.buy_price.toFixed(2)}` : ""}
                          </div>
                          {!priceUnlocked && item.buy_price > 0 && (
                            <div className="mt-1"><LockedHint /></div>
                          )}
                        </>
                      );
                    })()}
                  </div>
                </div>

                {/* 行 2：评分条 */}
                <div className="mt-3 flex items-center gap-2.5">
                  <span className="text-[12px] text-text-tertiary shrink-0">评分</span>
                  <div className="h-1.5 min-w-0 flex-1 overflow-hidden rounded-full bg-surface-container-high">
                    <div className="h-full rounded-full bg-gradient-to-r from-primary/60 to-primary" style={{ width: `${displayScore(item.score)}%` }} />
                  </div>
                  <span className={`font-display-numeric text-[15px] font-bold ${scoreColor(item.score)}`}>
                    {displayScore(item.score)}
                  </span>
                  {item.score_label && (
                    <span className="rounded-full border border-primary/20 bg-primary/10 px-1.5 py-0.5 text-[10px] text-primary">{item.score_label}</span>
                  )}
                </div>

                {/* 行 3：标签 */}
                <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
                  {item.is_trade_pick && (
                    <span className="inline-flex items-center rounded-full bg-purple-primary px-2 py-0.5 text-[10px] font-medium text-white">
                      今日计划关注
                    </span>
                  )}
                  {peVal != null && Number(peVal) > 0 && (
                    <span className={`rounded-full border px-2 py-0.5 text-[11px] ${
                      peB === "gt_30"
                        ? "border-status-warning/25 bg-status-warning/12 text-status-warning"
                        : "border-border-subtle bg-surface-container-high text-text-secondary"
                    }`}>
                      PE {Number(peVal) >= 100 ? Number(peVal).toFixed(0) : Number(peVal).toFixed(1)}
                    </span>
                  )}
                  {item.money_phase_label && (
                    <span className="rounded-full border border-border-subtle bg-surface-container-high px-2 py-0.5 text-[11px] text-text-secondary">
                      {item.money_phase_label}
                    </span>
                  )}
                  {item.active_buy_ratio != null && (
                    <span className="rounded-full border border-border-subtle bg-surface-container-high px-2 py-0.5 text-[11px] text-text-secondary">
                      主动买入 {(item.active_buy_ratio * 100).toFixed(0)}%
                    </span>
                  )}
                  {item._signals?.includes("ths_hot") && (
                    <span className="rounded-full border border-status-info/25 bg-status-info/12 px-2 py-0.5 text-[11px] text-status-info">热点</span>
                  )}
                  {item._signals?.includes("margin_up") && (
                    <span className="rounded-full border border-border-subtle bg-surface-container-high px-2 py-0.5 text-[11px] text-text-secondary">融资</span>
                  )}
                </div>

                {/* 操作 */}
                <div className="mt-3 flex items-center justify-end gap-2">
                  <button
                    onClick={() => handleToggleWatchlist(item)}
                    disabled={isWlLoading}
                    className={`rounded-full px-3.5 py-1.5 text-[12px] font-medium transition-colors disabled:opacity-50 cursor-pointer ${
                      isFav
                        ? "bg-purple-light text-purple-primary hover:bg-purple-light/70"
                        : "border border-border-subtle bg-surface-card text-text-secondary hover:border-purple-primary/40 hover:text-purple-primary"
                    }`}>
                    {isWlLoading ? "..." : isFav ? "已收藏" : "收藏"}
                  </button>
                  <Link href={`/cn/stock?symbol=${item.symbol}`} className="rounded-full bg-purple-primary px-3.5 py-1.5 text-[12px] font-medium text-white transition-opacity hover:opacity-90">
                    详情
                  </Link>
                </div>

                {/* 盘中资金强度 */}
                {strength && (
                  <div className="mt-2 flex items-center justify-between gap-2 border-t border-border-subtle pt-2 text-[11px]">
                    <span className="relative inline-flex cursor-help" onMouseEnter={(e) => { (e.currentTarget.querySelector('[data-fund-tip]') as HTMLElement)?.style.setProperty('display', 'block'); }} onMouseLeave={(e) => { (e.currentTarget.querySelector('[data-fund-tip]') as HTMLElement)?.style.setProperty('display', 'none'); }}>
                      <span className="flex items-center gap-1 text-text-secondary">盘中资金
                        <svg className="h-3 w-3 text-text-disabled" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="9" /><path d="M12 8h.01M11 12h1v4h1" strokeLinecap="round" /></svg>
                      </span>
                      <span data-fund-tip className="absolute right-0 top-full z-30 mt-1.5 hidden w-[230px] rounded-xl border border-border-subtle bg-surface-card p-3 text-left shadow-xl" role="tooltip">
                        <div className="mb-1.5 flex items-center justify-between">
                          <span className="text-[11px] font-semibold text-text-primary">盘中资金强度</span>
                          <span className="text-[9px] text-text-disabled">每 3 分钟更新</span>
                        </div>
                          <div className="space-y-1.5 text-[10px] leading-relaxed text-text-secondary">
                          <div className="flex items-start gap-1.5"><span className="mt-0.5 shrink-0 text-status-danger">④</span><span><span className="font-semibold text-text-primary">机构净占比</span> {strength.super_net_pct != null && Math.abs(strength.super_net_pct) >= 2 ? `${strength.super_net_pct > 0 ? "+" : ""}${strength.super_net_pct.toFixed(1)}%` : strength.main_net_pct != null ? `${strength.main_net_pct > 0 ? "+" : ""}${strength.main_net_pct.toFixed(1)}%` : "—"}：超大单/主力净买入占当日成交额比例，越高说明机构买盘越占主导（免费源口径）。</span></div>
                          <div className="flex items-start gap-1.5"><span className="mt-0.5 shrink-0 text-status-info">①</span><span><span className="font-semibold text-text-primary">强度分位</span> {strength.rank_pct != null ? `前 ${(strength.rank_pct * 100).toFixed(0)}%` : "—"}：今日资金量放回该股近 60 日里比，历史只有 {strength.rank_pct != null ? ((1 - strength.rank_pct) * 100).toFixed(0) : "—"}% 的日子更强。</span></div>
                          <div className="flex items-start gap-1.5"><span className="mt-0.5 shrink-0 text-status-warning">②</span><span><span className="font-semibold text-text-primary">流速</span> {strength.speed_ratio != null ? `${strength.speed_ratio.toFixed(1)}x` : "—"}：每分钟流入是历史平均的 {strength.speed_ratio != null ? strength.speed_ratio.toFixed(1) : "—"} 倍，&gt;1 说明在加速进场。</span></div>
                          <div className="flex items-start gap-1.5"><span className="mt-0.5 shrink-0 text-status-danger">③</span><span><span className="font-semibold text-text-primary">冲板概率</span> {strength.limit_up_prob != null ? `${(strength.limit_up_prob * 100).toFixed(1)}%` : "—"}：按全市场同强度档位的历史统计，当日冲击涨停的概率。</span></div>
                        </div>
                      </span>
                    </span>
                    <span className={`font-medium text-right ${
                      (strength.rank_pct ?? 0) >= 0.7
                        ? "text-status-danger"
                        : (strength.rank_pct ?? 0) >= 0.5
                        ? "text-status-warning"
                        : "text-text-secondary"
                    }`}>
                      {strength.label || "数据不足"}
                    </span>
                  </div>
                )}
              </article>
            )})}
          </div>
        )}
      </section>

      {/* ══ 今日计划（研究参考） ══ */}
      {data && <TradePlanCard plan={(data as ScreenerResponse).trade_plan ?? null} />}

      {(() => {
        const activeWl = wlData.filter((w) => w.status === "active");
        const histWl = wlData.filter((w) => w.status !== "active");
        // 与收藏页一致：优先展示追踪中，不足再用历史补齐预览
        const wlPreview = [...activeWl, ...histWl].slice(0, 8);
        if (wlPreview.length === 0) return null;
        return (
        <section className="rounded-2xl border border-border-subtle bg-surface-card shadow-sm p-4 sm:p-5">
          <div className="mb-3 flex items-start justify-between gap-3">
            <div>
              <div className="flex items-center gap-2 mb-1">
                <h2 className="text-[17px] font-semibold text-text-primary">收藏追踪</h2>
              </div>
              <p className="text-[12px] text-text-tertiary">
                追踪中 {activeWl.length} · 历史 {histWl.length} · 收藏后自动记录 T+1 / T+2 / T+3 涨跌
              </p>
            </div>
            <Link href="/cn/watchlist" className="text-[13px] text-purple-primary hover:underline shrink-0">查看全部 →</Link>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {wlPreview.map((w) => {
              const day1 = w.day1_change;
              const day2 = w.day2_change;
              const day3 = w.day3_change;
              const latestChg = day3 ?? day2 ?? day1;
              const isPositive = latestChg != null ? latestChg >= 0 : null;
              return (
              <div key={w.id} className="rounded-xl p-3 border border-border-subtle bg-bg-primary/50">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-1.5 min-w-0">
                    <span className="font-semibold text-[14px] text-text-primary truncate">{w.name}</span>
                    <span className="text-[11px] text-text-disabled shrink-0">{w.symbol}</span>
                  </div>
                  {isPositive !== null && (
                    <span className={`text-[15px] font-bold font-display-numeric ${isPositive ? "text-status-danger" : "text-status-success"}`}>
                      {latestChg > 0 ? "+" : ""}{latestChg}%
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-4 text-[12px]">
                  <div>
                    <span className="text-text-disabled">入场 </span>
                    <span className="font-mono text-status-warning font-medium">¥{w.entry_price.toFixed(2)}</span>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="text-text-disabled">T+1 <span className={`font-mono ${day1 != null ? (day1 >= 0 ? "text-status-danger" : "text-status-success") : "text-text-disabled"}`}>{day1 != null ? `${day1 > 0 ? "+" : ""}${day1}%` : "—"}</span></span>
                    <span className="text-text-disabled">T+2 <span className={`font-mono ${day2 != null ? (day2 >= 0 ? "text-status-danger" : "text-status-success") : "text-text-disabled"}`}>{day2 != null ? `${day2 > 0 ? "+" : ""}${day2}%` : "—"}</span></span>
                    <span className="text-text-disabled hidden sm:inline">T+3 <span className={`font-mono ${day3 != null ? (day3 >= 0 ? "text-status-danger" : "text-status-success") : "text-text-disabled"}`}>{day3 != null ? `${day3 > 0 ? "+" : ""}${day3}%` : "—"}</span></span>
                  </div>
                  <span className={`ml-auto text-[10px] px-2 py-0.5 rounded-full ${w.status === "active" ? "bg-purple-light text-purple-primary" : "bg-black/[0.05] text-text-secondary"}`}>
                    {w.status === "active" ? "追踪中" : "历史"}
                  </span>
                </div>
              </div>
            )})}
          </div>
        </section>
        );
      })()}


      {/* ══ 更多榜单（次要，默认收起） ══ */}
      <section>
        <details className="group rounded-2xl border border-border-subtle bg-surface-card px-4 py-3 sm:px-5">
          <summary className="flex cursor-pointer list-none flex-wrap items-center gap-x-3 gap-y-1 [&::-webkit-details-marker]:hidden">
            <h2 className="text-[16px] font-semibold text-text-primary">更多评分榜单</h2>
            <span className="text-[12px] text-text-tertiary">09:35 定格 Top 10 · 管线评分榜</span>
            <span className="ml-auto text-[12px] text-text-tertiary group-open:hidden">展开 ▾</span>
            <span className="ml-auto hidden text-[12px] text-text-tertiary group-open:inline">收起 ▴</span>
          </summary>
          <div className="mt-4 grid grid-cols-1 items-start gap-4 lg:grid-cols-2">
            <ScoreTop10Panel top10={top10} top10Loading={top10Loading} fundStrength={fundStrength} />
            <PipelineBoardPanel pbData={pbData} pbLoading={pbLoading} fundStrength={fundStrength} />
          </div>
        </details>
      </section>

      {catData && (
        <section>
          <details className="group rounded-2xl border border-border-subtle bg-surface-card px-4 py-3 sm:px-5">
            <summary className="flex cursor-pointer list-none flex-wrap items-center gap-x-3 gap-y-1 [&::-webkit-details-marker]:hidden">
              <h2 className="text-[16px] font-semibold text-text-primary">资金阶段分类</h2>
              <span className="text-[12px] text-text-tertiary">
                {PHASE_GROUPS.map((g) => `${g.label} ${g.phases.reduce((n, pk) => n + ((catData.categories?.[pk]?.stocks?.length) || 0), 0)}`).join(" · ")}
              </span>
              <span className="ml-auto text-[12px] text-text-tertiary group-open:hidden">展开 ▾</span>
              <span className="ml-auto hidden text-[12px] text-text-tertiary group-open:inline">收起 ▴</span>
            </summary>
            <p className="mt-3 text-[12px] leading-relaxed text-text-secondary">
              按资金行为把全市场标的分成 4 组，用于理解资金处在什么阶段，仅供研究参考，不构成买卖建议。
              <span className="text-text-tertiary">（05:00 隔夜先验 · 09:35 开盘终选，含竞价）</span>
            </p>
            <div className="mt-4">
          {catLoading ? (
            <div className="flex items-center justify-center py-8">
              <div className="h-8 w-8 animate-spin rounded-full border-3 border-border-subtle border-t-purple-primary"></div>
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {PHASE_GROUPS.map(group => (
                <GroupCard key={group.key} group={group}
                  categories={catData.categories || {}}
                  watchlistSymbols={watchlistSymbols} wlLoading={wlLoading}
                  onToggleWatchlist={handleToggleWatchlist} sectorChanges={sectorChanges}
                  fundStrength={fundStrength} />
              ))}
            </div>
          )}
            </div>
          </details>
        </section>
      )}

      <section>
        <details className="group rounded-2xl border border-border-subtle bg-surface-card px-4 py-3 sm:px-5">
        <summary className="flex cursor-pointer list-none flex-wrap items-center gap-3 [&::-webkit-details-marker]:hidden">
          <h2 className="text-[16px] font-semibold text-text-primary">模型研发机制 <span className="text-[12px] font-normal text-text-tertiary">· 进阶了解</span></h2>
          <span className="text-[10px] px-2 py-0.5 rounded-full bg-purple-light text-purple-primary border border-purple-primary/20">R&amp;D Workshop</span>
          <span className="text-[10px] px-2 py-0.5 rounded-full bg-black/[0.05] text-text-secondary border border-border-subtle">与交易分轨</span>
          <span className="ml-auto text-[12px] text-text-tertiary group-open:hidden">展开 ▾</span>
        </summary>
        <div className="mt-4">
        <p className="mb-4 text-[12px] text-text-secondary leading-relaxed max-w-3xl">
          AlphaPilot 把「选股交易」和「模型研发」拆成两个独立部门：研发侧自动提出因子假设、生成代码并回测；
          只有通过可交易验证并经人工对照现网模型后，才会晋升上线——交易链路不会被实验干扰。
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 sm:gap-3 mb-3">
          <div className="rounded-2xl border border-border-subtle bg-surface-card p-4 card-lift shadow-sm border-t-2 border-t-purple-primary">
            <h3 className="text-[14px] font-semibold text-text-primary mb-1">Track A · 现网增益</h3>
            <p className="text-[11px] text-text-disabled leading-relaxed">
              每周在现有 VM2.5 特征空间自动挖掘增量因子，候选重训并对齐可交易 OOS，专为抬升当前生产模型。
            </p>
          </div>
          <div className="rounded-2xl border border-border-subtle bg-surface-card p-4 card-lift shadow-sm border-t-2 border-t-status-success">
            <h3 className="text-[14px] font-semibold text-text-primary mb-1">Track B · RD 自研</h3>
            <p className="text-[11px] text-text-disabled leading-relaxed">
              RD-Agent 独立提出假设、写因子代码并回测，探索现网特征之外的新结构；导出后再接入同一晋升闸门。
            </p>
          </div>
          <div className="rounded-2xl border border-border-subtle bg-surface-card p-4 card-lift shadow-sm border-t-2 border-t-status-warning">
            <h3 className="text-[14px] font-semibold text-text-primary mb-1">晋升闸门 · 人工终审</h3>
            <p className="text-[11px] text-text-disabled leading-relaxed">
              候选模型必须过可交易回测，并与生产模型对比；禁止自动热切换。审核通过才安装进线上打分槽位。
            </p>
          </div>
        </div>
        <div className="flex flex-col sm:flex-row sm:items-center gap-2 rounded-lg bg-surface-container-low px-3 py-2.5 border border-border-subtle">
          <p className="text-[12px] text-text-secondary">
            <span className="text-text-primary">时间表</span>
            ：周六 02:00 Track A 候选训练 · 工作日人工对照生产 OOS · 通过后才晋升 · 盘中交易链不受研发任务干扰
          </p>
        </div>
              </div>
        </details>
      </section>

      <footer className="pt-2 pb-6 mx-auto max-w-3xl text-center text-[11px] leading-relaxed text-text-tertiary">
        {DISCLAIMER_FULL}
      </footer>
      </div>

      {priceDialog && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/50 backdrop-blur-sm"
          onClick={() => !priceDialogLoading && setPriceDialog(null)}>
          <div className="w-[90vw] max-w-[380px] rounded-2xl border border-border-subtle bg-surface-card p-6 shadow-2xl mx-4"
            onClick={e => e.stopPropagation()}>
            <div className="flex items-center gap-2 mb-1"><h3 className="text-[18px] font-semibold text-text-primary">添加收藏</h3></div>
            <p className="text-[13px] text-text-secondary mb-4">
              {priceDialog.item.name} · {priceDialog.item.symbol?.replace(/^(sh|sz)/, "")}
            </p>
            <label className="block mb-1 text-[12px] text-text-disabled">买入价格（¥）</label>
            <input
              type="number"
              step="0.01"
              min="0.01"
              value={priceDialog.price}
              onChange={e => setPriceDialog(prev => prev ? { ...prev, price: e.target.value } : null)}
              className="w-full rounded-lg border border-border-subtle bg-background px-3 py-2.5 text-[16px] text-text-primary font-mono outline-none focus:border-status-info transition-colors"
              placeholder="输入买入价"
              autoFocus
              disabled={priceDialogLoading}
            />
            <div className="mt-4 flex gap-2">
              <button onClick={() => setPriceDialog(null)} disabled={priceDialogLoading}
                className="flex-1 rounded-lg border border-border-subtle bg-background py-2.5 text-[13px] text-text-secondary hover:border-status-info hover:text-text-primary transition-colors disabled:opacity-50">
                取消
              </button>
              <button onClick={confirmAddWatchlist} disabled={priceDialogLoading}
                className="flex-1 rounded-lg bg-status-info py-2.5 text-[13px] font-semibold text-on-primary hover:bg-primary/80 transition-colors disabled:opacity-50 flex items-center justify-center gap-2">
                {priceDialogLoading ? <span className="h-4 w-4 animate-spin rounded-full border-2 border-border-subtle border-t-transparent" /> : null}
                {priceDialogLoading ? "添加中..." : "确认添加"}
              </button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}

function Stat({ label, value, sub, dot }: { label: string; value: string; sub?: string; dot?: string }) {
  return (
    <div className="min-w-0 rounded-2xl border border-border-subtle bg-surface-card p-3.5 shadow-sm sm:p-4">
      <div className="flex items-center gap-1.5 text-[12px] text-text-tertiary">
        {dot && <span aria-hidden className={`h-1.5 w-1.5 shrink-0 rounded-full ${dot}`} />}
        <span className="truncate">{label}</span>
      </div>
      <div className="mt-1.5 truncate font-display-numeric text-[19px] font-semibold leading-tight text-text-primary sm:text-[21px]">
        {value}
      </div>
      {sub && <div className="mt-1 line-clamp-2 text-[11px] leading-snug text-text-secondary">{sub}</div>}
    </div>
  );
}

const PHASE_COLORS: Record<string, string> = {
  bear_trap: "#8B5CF6",
  rightside_ambush: "#F59E0B",
  accumulation_end: "#10B981",
  markup: "#EF4444",
  accumulation: "#3B82F6",
  suspicious: "#F97316",
  distribution: "#DC2626",
  pullback: "#6B7280",
  sideways: "#9CA3AF",
};

const PHASE_GROUPS = [
  { key: "buy_signal", label: "资金活跃", desc: "主力资金较为活跃，值得持续观察", color: "#EF4444", phases: ["markup", "rightside_ambush", "accumulation_end", "bear_trap"] },
  { key: "accumulation_watch", label: "吸筹观察", desc: "低位资金有持续流入迹象", color: "#3B82F6", phases: ["accumulation"] },
  { key: "risk_warning", label: "风险提示", desc: "留意回调或资金流出风险", color: "#F97316", phases: ["suspicious", "distribution"] },
  { key: "wait_and_see", label: "暂时观望", desc: "方向不明或回调中", color: "#6B7280", phases: ["pullback", "sideways"] }
];

function GroupCard({ group, categories, watchlistSymbols, wlLoading, onToggleWatchlist, sectorChanges, fundStrength }: {
  group: typeof PHASE_GROUPS[0];
  categories: Record<string, any>;
  watchlistSymbols: Set<string>;
  wlLoading: Record<string, boolean>;
  onToggleWatchlist: (item: any) => void;
  sectorChanges: Record<string, number>;
  fundStrength?: FundStrengthData | null;
}) {
  const phaseLabels: Record<string, string> = {
    markup: "拉升", rightside_ambush: "右侧潜伏", accumulation_end: "吸筹末期",
    bear_trap: "诱空陷阱", accumulation: "吸筹",
    suspicious: "诱多嫌疑", distribution: "出货",
    pullback: "回调", sideways: "震荡"
  };
  const { unlocked: priceUnlocked } = useUnlocked();
  const totalCount = group.phases.reduce((sum, pk) => sum + ((categories[pk]?.stocks?.length) || 0), 0);
  return (
    <div className="rounded-2xl border border-border-subtle bg-surface-card shadow-sm p-4 flex flex-col"
      style={{ borderLeftColor: group.color, borderLeftWidth: 3 }}>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <div>
            <h3 className="text-[16px] font-semibold text-text-primary">{group.label}</h3>
            <p className="text-[11px] text-text-disabled">{group.desc} · {totalCount} 只</p>
          </div>
        </div>
        {totalCount > 0 && (
          <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-status-warning/15 text-status-warning border border-status-warning/30 font-medium animate-pulse">
            今日有数据
          </span>
        )}
      </div>
      <div className="space-y-3 flex-1">
        {group.phases.map(pk => {
          const cat = categories[pk];
          const stocks = cat?.stocks || [];
          const subColor = PHASE_COLORS[pk] || "#6a5a7e";
          return (
            <div key={pk}>
              <div className="flex items-center gap-1.5 mb-1.5 px-1">
                <span className="inline-block w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: subColor }} />
                <span className="text-[12px] font-medium" style={{ color: subColor }}>
                  {phaseLabels[pk] || pk}
                </span>
                <span className="text-[10px] text-text-disabled">({stocks.length} 只)</span>
                {stocks.length > 0 && (
                  <span className="text-[8px] px-1 py-0.5 rounded-sm bg-status-warning/12 text-status-warning font-medium">热</span>
                )}
              </div>
              {stocks.length === 0 ? (
                <p className="text-[11px] text-text-disabled px-1 py-1.5 italic">暂无标的</p>
              ) : (
                <div className="space-y-1">
                  {stocks.slice(0, 5).map((s: any, i: number) => {
                    const sym = String(s.symbol || "").replace(/\D/g, "").slice(-6);
                    const isFav = watchlistSymbols.has(sym);
                    const isWlLoading = wlLoading[sym] ?? false;
                    const price = s.price || (priceUnlocked ? s.buy_price : 0) || 0;
                    const chg = s.change_pct;
                    const chgStr = chg != null ? `${chg > 0 ? "+" : ""}${chg.toFixed(1)}%` : "—";
                    const chgColor = chg != null ? (chg >= 0 ? "text-status-danger" : "text-status-success") : "text-text-disabled";
                    const fsItem = fundStrength?.items?.[sym];
                    const fsRank = fsItem?.rank_pct ?? 0;
                    return (
                      <div key={s.symbol} className="flex items-center gap-1.5 rounded-lg bg-surface-container-low p-1.5 hover:bg-surface-card transition-colors group">
                        <span className="text-[10px] text-text-disabled font-display-numeric w-[14px] text-center shrink-0">{i + 1}</span>
                        <Link href={`/cn/stock?symbol=${s.symbol}`} className="flex items-center gap-1 min-w-0 flex-1 overflow-hidden">
                          <span className="text-[12px] font-medium text-text-primary group-hover:text-status-info truncate transition-colors">{s.name}</span>
                          <span className="text-[9px] text-text-disabled shrink-0">{sym}</span>
                        </Link>
                        <span className={`text-[10px] font-bold font-display-numeric w-[24px] text-center ${
                          displayScore(s.score_raw || s.score) > 85 ? "text-status-success" : displayScore(s.score_raw || s.score) > 80 ? "text-primary" : "text-text-secondary"
                        }`}>{displayScore(s.score_raw || s.score)}</span>
                        {fsItem && (
                          <span className="text-[9px] px-1 py-0.5 rounded-full font-medium shrink-0 border"
                            title={fsItem.label || ""}
                            style={{
                              color: fsRank >= 0.7 ? "#dc2626" : fsRank >= 0.5 ? "#f59e0b" : "#6b7280",
                              borderColor: fsRank >= 0.7 ? "rgba(220,38,38,.3)" : fsRank >= 0.5 ? "rgba(245,158,11,.3)" : "rgba(107,114,128,.3)",
                              background: fsRank >= 0.7 ? "rgba(220,38,38,.08)" : fsRank >= 0.5 ? "rgba(245,158,11,.08)" : "rgba(107,114,128,.08)",
                            }}
                          >
                            {fsRank >= 0.9 ? "极强" : fsRank >= 0.7 ? "偏强" : fsRank >= 0.5 ? "中性" : fsRank >= 0.3 ? "偏弱" : "极弱"}
                          </span>
                        )}
                        <span className="text-[10px] font-display-numeric text-text-secondary w-[52px] text-right shrink-0">
                          ¥{(s.live_price || s.price || (priceUnlocked ? s.buy_price : 0) || 0).toFixed(2)}
                        </span>
                        <span className={`font-display-numeric text-[11px] font-medium w-[48px] text-right shrink-0 ${chgColor}`}>{chgStr}</span>
                        <button
                          onClick={(e) => { e.stopPropagation(); onToggleWatchlist(s); }}
                          disabled={isWlLoading}
                          className={`text-[13px] w-[20px] text-center shrink-0 transition-colors disabled:opacity-50 ${
                            isFav ? "text-status-warning" : "text-text-disabled hover:text-status-warning"
                          }`}>
                          {isWlLoading ? "..." : isFav ? "已收藏" : "收藏"}
                        </button>
                      </div>
                    );
                  })}
                  {stocks.length > 5 && (
                    <p className="text-[10px] text-status-info text-right pr-1">+{stocks.length - 5} 只更多</p>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ─── 数据状态卡片 ─── */
function DataStatusCard() {
  const [dataStatus, setDataStatus] = useState<any>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshStatus, setRefreshStatus] = useState<any>(null);
  const pollRef = useRef<any>(null);

  const loadStatus = useCallback(async () => {
    try { setDataStatus(await (await fetch("/api/v1/cn/data-status")).json()); } catch {}
  }, []);

  const loadRefreshStatus = useCallback(async () => {
    try {
      const s = await (await fetch("/api/v1/cn/refresh-all-data/status")).json();
      setRefreshStatus(s);
      if (s.step === "idle" || s.progress === 100 || s.progress === -1) {
        if (pollRef.current) clearInterval(pollRef.current);
        pollRef.current = null;
        setRefreshing(false);
        loadStatus();
      }
    } catch {}
  }, [loadStatus]);

  const handleRefresh = async () => {
    setRefreshing(true);
    try { await fetch("/api/v1/cn/refresh-all-data", { method: "POST" }); } catch {}
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(loadRefreshStatus, 5000);
    loadRefreshStatus();
  };

  useEffect(() => { loadStatus(); }, [loadStatus]);
  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current); }, []);

  const stepLabels: Record<string, string> = {
    fund_flow: "资金流", recommend: "推荐管线", chip: "筹码", done: "完成", idle: "空闲",
  };

  const upd = (v?: string) => v || "暂无";
  return (
    <div className="mb-6 flex flex-wrap items-center gap-x-4 gap-y-2 rounded-2xl border border-border-subtle bg-surface-card px-4 py-2.5 text-[12px] text-text-secondary">
      <span className="font-medium text-text-primary">数据更新</span>
      {dataStatus ? (
        <dl className="flex flex-wrap items-center gap-x-4 gap-y-1">
          <div className="flex items-center gap-1.5"><dt className="text-text-tertiary">推荐名单</dt><dd className="font-display-numeric">{upd(dataStatus.daily_recommend?.updated_at)}</dd></div>
          <div className="flex items-center gap-1.5"><dt className="text-text-tertiary">资金流</dt><dd className="font-display-numeric">{upd(dataStatus.fund_flow?.updated_at)}</dd></div>
          <div className="flex items-center gap-1.5"><dt className="text-text-tertiary">筹码</dt><dd className="font-display-numeric">{upd(dataStatus.chip_data?.updated_at)}</dd></div>
        </dl>
      ) : (
        <span className="text-text-tertiary">读取中…</span>
      )}
      {refreshStatus && refreshStatus.step !== "idle" && (
        <span className="text-purple-primary">
          {stepLabels[refreshStatus.step]}：{refreshStatus.progress}%
        </span>
      )}
      <button
        onClick={handleRefresh}
        disabled={refreshing}
        className="ml-auto flex cursor-pointer items-center gap-1.5 whitespace-nowrap rounded-full border border-border-subtle px-3 py-1 text-[12px] text-text-secondary transition-colors hover:border-purple-primary/40 hover:text-purple-primary disabled:cursor-not-allowed disabled:opacity-50"
      >
        <svg className={`h-3.5 w-3.5 ${refreshing ? "animate-spin" : ""}`}
          viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
          <polyline points="23 4 23 10 17 10" /><polyline points="1 20 1 14 7 14" />
          <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
        </svg>
        {refreshing ? "刷新中…" : "刷新盘后数据"}
      </button>
    </div>
  );
}

/* ─── 侧栏辅助函数（管线评分榜 / 评分Top10 / 交易指令） ─── */

function symCode(s?: string) {
  return String(s || "").replace(/\D/g, "").slice(-6);
}

/** 0–100 分颜色：与智能选股页评分榜一致 */
const scoreColor100 = (s: number) =>
  s >= 90 ? "text-status-success" : s >= 80 ? "text-status-info" : s >= 70 ? "text-status-warning" : "text-text-secondary";

const chgColor100 = (v: number | null | undefined) =>
  v == null ? "text-text-disabled" : v >= 0 ? "text-status-danger" : "text-status-success";

function fmtYi(v: number | null | undefined): string {
  if (v == null || Number.isNaN(Number(v))) return "—";
  const n = Number(v);
  const yi = n / 1e8;
  if (Math.abs(yi) >= 0.01) return `${yi > 0 ? "+" : ""}${yi.toFixed(2)}亿`;
  return `${n > 0 ? "+" : ""}${(n / 1e4).toFixed(0)}万`;
}

function statusTone(code?: string) {
  switch (code) {
    case "buy":
      return "border-status-success/35 bg-status-success/10 text-status-success";
    case "half":
    case "light":
      return "border-status-info/35 bg-status-info/10 text-status-info";
    case "awaiting":
      return "border-status-warning/40 bg-status-warning/10 text-status-warning";
    case "empty":
    case "no_picks":
      return "border-status-danger/35 bg-status-danger/10 text-status-danger";
    default:
      return "border-border-subtle bg-bg-secondary text-text-secondary";
  }
}

/** 出场规则层级徽章配色：按 id 1–4 映射，未知回退循环。 */
function layerBadgeTone(id: number | undefined, idx: number) {
  const tones = [
    "bg-status-info/10 text-status-info",
    "bg-status-danger/10 text-status-danger",
    "bg-status-warning/10 text-status-warning",
    "bg-primary/10 text-primary",
  ];
  if (id != null && id >= 1 && id <= 4) return tones[id - 1];
  return tones[idx % tones.length];
}

/** 盘中资金强度悬浮说明：解释 强度分位 / 流速 / 冲板概率。 */
function FundStrengthTip({ strength }: { strength: { rank_pct?: number | null; speed_ratio?: number | null; limit_up_prob?: number | null } }) {
  const [open, setOpen] = useState(false);
  const rank = strength?.rank_pct;
  const speed = strength?.speed_ratio;
  const prob = strength?.limit_up_prob;
  return (
    <span
      className="relative inline-flex cursor-help"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
    >
      <span className="flex items-center gap-1 text-text-secondary">
        盘中资金
        <svg
          className="h-3 w-3 text-text-disabled"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
        >
          <circle cx="12" cy="12" r="9" />
          <path d="M12 8h.01M11 12h1v4h1" strokeLinecap="round" />
        </svg>
      </span>
      {open && (
        <span
          className="absolute right-0 top-full z-30 mt-1.5 w-[230px] rounded-xl border border-border-subtle bg-bg-elevated/95 p-3 text-left shadow-xl backdrop-blur"
          role="tooltip"
        >
          <div className="mb-1.5 flex items-center justify-between">
            <span className="text-[11px] font-semibold text-text-primary">盘中资金强度</span>
            <span className="text-[9px] text-text-disabled">每 3 分钟更新</span>
          </div>
          <div className="space-y-1.5 text-[10px] leading-relaxed text-text-secondary">
            <div className="flex items-start gap-1.5">
              <span className="mt-0.5 shrink-0 text-status-info">①</span>
              <span>
                <span className="font-semibold text-text-primary">强度分位</span>{" "}
                {rank != null ? (
                  <>前 {(rank * 100).toFixed(0)}%</>
                ) : (
                  "数据不足"
                )}
                ：今日资金量放回该股近 60 日里比，历史只有{" "}
                {rank != null ? ((1 - rank) * 100).toFixed(0) : "—"}% 的日子更强。
              </span>
            </div>
            <div className="flex items-start gap-1.5">
              <span className="mt-0.5 shrink-0 text-status-warning">②</span>
              <span>
                <span className="font-semibold text-text-primary">流速</span>{" "}
                {speed != null ? `${speed.toFixed(1)}x` : "—"}：每分钟流入是历史平均的{" "}
                {speed != null ? `${speed.toFixed(1)}` : "—"} 倍，&gt;1 说明在加速进场。
              </span>
            </div>
            <div className="flex items-start gap-1.5">
              <span className="mt-0.5 shrink-0 text-status-danger">③</span>
              <span>
                <span className="font-semibold text-text-primary">冲板概率</span>{" "}
                {prob != null ? `${(prob * 100).toFixed(1)}%` : "—"}：按全市场同强度档位的历史
                统计，当日冲击涨停的概率。
              </span>
            </div>
          </div>
        </span>
      )}
    </span>
  );
}

/* ─── 管线评分榜：05:00 管线全量输出按评分降序（侧栏） ─── */
function PipelineBoardPanel({
  pbData,
  pbLoading,
  fundStrength,
}: {
  pbData: PipelineBoardResponse | null;
  pbLoading: boolean;
  fundStrength: FundStrengthData | null;
}) {
  const [peFilter, setPeFilter] = useState<PeFilter>("all");
  const [trendFilter, setTrendFilter] = useState<"all" | "uptrend" | "downtrend">("all");
  const PAGE = 10;
  const [shown, setShown] = useState(PAGE);

  const items = (pbData?.items ?? []) as PipelineBoardItem[];
  const allCount = items.length;

  // 管线综合分统一映射 0–100（模型分 + 资金流 + 板块热度，后端已算好 score）
  const scoreOf = (it: PipelineBoardItem) => displayScore(it.score ?? it.lgb_score ?? 0);

  const filtered = items.filter((it) => {
    if (peFilter !== "all") {
      const b = peBucketOf(it);
      if (peFilter === "le_30" && b !== "le_30") return false;
      if (peFilter === "gt_30" && b !== "gt_30") return false;
    }
    if (trendFilter === "uptrend" && (it.channel_reject === true || it.downtrend_channel === true)) return false;
    if (trendFilter === "downtrend" && !(it.channel_reject === true || it.downtrend_channel === true)) return false;
    return true;
  });

  const visible = filtered.slice(0, shown);

  return (
    <section className="rounded-2xl border border-border-subtle bg-surface-card shadow-sm overflow-hidden">
      <div className="px-4 pt-4 pb-3">
        <div className="flex items-center gap-2 mb-1">
          <h2 className="text-[16px] font-semibold text-text-primary">管线评分榜</h2>
          <span className="text-[10px] px-2 py-0.5 rounded-full bg-purple-light text-purple-primary border border-purple-primary/20">
            05:00 定格
          </span>
        </div>
        <p className="mt-0.5 text-[11px] text-text-disabled">
          全量 {allCount} 只 · 综合分降序
          {pbData?.asof ? ` · 定格 ${pbData.asof.slice(5, 16)}` : ""}
          {pbData?.model_version ? ` · ${pbData.model_version}` : ""}
        </p>
      </div>

      {/* 筛选器 */}
      <div className="px-4 pb-2 flex flex-wrap items-center gap-1.5">
        <div className="inline-flex items-center gap-0.5 rounded-lg border border-border-subtle bg-surface-card p-0.5">
          {([
            { key: "all" as PeFilter, label: "全部" },
            { key: "le_30" as PeFilter, label: "PE≤30" },
            { key: "gt_30" as PeFilter, label: "PE>30" },
          ]).map((opt) => (
            <button
              key={opt.key}
              type="button"
              onClick={() => setPeFilter(opt.key)}
              className={`rounded-md px-2 py-1 text-[11px] transition-colors cursor-pointer whitespace-nowrap ${
                peFilter === opt.key
                  ? "bg-primary/15 text-text-primary border border-primary/30"
                  : "text-text-secondary hover:text-text-primary border border-transparent"
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
        <div className="inline-flex items-center gap-0.5 rounded-lg border border-border-subtle bg-surface-card p-0.5">
          {([
            { key: "all" as const, label: "趋势:全部" },
            { key: "uptrend" as const, label: "↑上升" },
            { key: "downtrend" as const, label: "↓下跌" },
          ]).map((opt) => (
            <button key={opt.key} type="button" onClick={() => setTrendFilter(opt.key)}
              className={`rounded-md px-2 py-1 text-[11px] transition-colors cursor-pointer whitespace-nowrap ${
                trendFilter === opt.key
                  ? "bg-primary/15 text-text-primary border border-primary/30"
                  : "text-text-secondary hover:text-text-primary border border-transparent"
              }`}>
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      {pbLoading ? (
        <div className="flex items-center justify-center py-10">
          <div className="h-6 w-6 animate-spin rounded-full border-3 border-border-subtle border-t-purple-primary"></div>
        </div>
      ) : filtered.length === 0 ? (
        <p className="py-8 text-center text-[12px] text-text-secondary">当前筛选下暂无标的</p>
      ) : (
        <ul className="divide-y divide-border-subtle/60">
          {visible.map((it, i) => {
            const sym = symCode(it.symbol);
            const sc = scoreOf(it);
            const strength = fundStrength?.items?.[sym];
            const fsRank = strength?.rank_pct ?? null;
            const fsSpeed = strength?.speed_ratio ?? null;
            const fsProb = strength?.limit_up_prob ?? null;
            const chg = it.change_pct ?? null;
            const pe = it.pe_ttm ?? it.pe;
            const isDowntrend = it.channel_reject === true || it.downtrend_channel === true;
            return (
              <li key={sym} className="px-4 py-2.5 hover:bg-surface-container-low/50 transition-colors">
                <div className="flex items-center gap-2">
                  <span className="text-[11px] font-display-numeric text-text-disabled w-[22px] shrink-0 text-center">
                    {String(i + 1).padStart(2, "0")}
                  </span>
                  <Link href={`/cn/stock?symbol=${sym}`} className="min-w-0 flex-1 group">
                    <div className="flex items-center gap-1.5 min-w-0">
                      <span className="text-[13px] font-semibold text-text-primary group-hover:text-status-info truncate transition-colors">
                        {it.name || sym}
                      </span>
                      <span className="text-[10px] text-text-disabled shrink-0">{sym}</span>
                      {isDowntrend && (
                        <span className="text-[9px] px-1 py-0.5 rounded bg-status-danger/15 text-status-danger border border-status-danger/20 shrink-0">↓</span>
                      )}
                    </div>
                    <div className="text-[10px] text-text-disabled truncate mt-0.5">
                      {it.sector || it.industry || "—"}
                      {pe != null && pe > 0 ? ` · PE ${Number(pe).toFixed(1)}` : ""}
                    </div>
                  </Link>
                  <div className="text-right shrink-0">
                    <div className={`font-display-numeric text-[15px] font-bold leading-none ${scoreColor100(sc)}`}>
                      {sc}
                    </div>
                    <div className={`font-display-numeric text-[11px] mt-1 ${chgColor100(chg)}`}>
                      {chg != null ? `${chg > 0 ? "+" : ""}${Number(chg).toFixed(2)}%` : "—"}
                    </div>
                  </div>
                </div>
                {strength && (fsRank != null || fsSpeed != null || fsProb != null) && (
                  <div className="mt-1.5 flex items-center gap-1.5 text-[10px] text-text-secondary pl-[28px]">
                    <span className="inline-flex items-center gap-1">
                      <span className={`w-1.5 h-1.5 rounded-full ${fsRank != null && fsRank >= 0.7 ? "bg-status-danger" : fsRank != null && fsRank >= 0.5 ? "bg-status-warning" : "bg-text-disabled/50"}`} />
                      强度 {fsRank != null ? `前${(fsRank * 100).toFixed(0)}%` : "—"}
                    </span>
                    <span className="text-text-disabled">·</span>
                    <span>流速 {fsSpeed != null ? `${fsSpeed.toFixed(1)}x` : "—"}</span>
                    <span className="text-text-disabled">·</span>
                    <span className={fsProb != null && fsProb >= 0.3 ? "text-status-danger font-medium" : ""}>
                      冲板 {fsProb != null ? `${(fsProb * 100).toFixed(1)}%` : "—"}
                    </span>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}

      {filtered.length > PAGE && (
        <div className="flex border-t border-border-subtle/60 text-[11px]">
          {shown < filtered.length && (
            <button
              type="button"
              onClick={() => setShown((n) => n + 20)}
              className="flex-1 px-4 py-2.5 text-purple-primary hover:bg-surface-container-low/50 transition-colors cursor-pointer"
            >
              显示更多（{Math.min(shown, filtered.length)} / {filtered.length}）
            </button>
          )}
          {shown > PAGE && (
            <button
              type="button"
              onClick={() => setShown(PAGE)}
              className="flex-1 px-4 py-2.5 text-text-secondary hover:bg-surface-container-low/50 transition-colors cursor-pointer"
            >
              收起
            </button>
          )}
        </div>
      )}
    </section>
  );
}

/* ─── 评分 Top10 · 09:35 定格（侧栏） ─── */
function ScoreTop10Panel({
  top10,
  top10Loading,
  fundStrength,
}: {
  top10: ScoreTop10Response | null;
  top10Loading: boolean;
  fundStrength: FundStrengthData | null;
}) {
  const items = (top10?.items ?? []) as ScoreTop10Item[];
  return (
    <section className="rounded-2xl border border-border-subtle bg-surface-card shadow-sm overflow-hidden">
      <div className="px-4 pt-4 pb-3">
        <div className="flex items-center gap-2 mb-1">
          <h2 className="text-[16px] font-semibold text-text-primary">评分 Top 10 · 09:35 定格</h2>
        </div>
        <p className="mt-0.5 text-[11px] text-text-disabled">
          综合分降序（模型分 + 资金流 + 板块热度）
          {top10?.asof ? ` · 定格 ${top10.asof.slice(5, 16)}` : ""}
        </p>
      </div>
      {top10Loading ? (
        <div className="flex items-center justify-center py-8">
          <div className="h-6 w-6 animate-spin rounded-full border-3 border-border-subtle border-t-purple-primary"></div>
        </div>
      ) : items.length === 0 ? (
        <p className="py-6 text-center text-[12px] text-text-secondary">暂无评分榜（等待管线写入）</p>
      ) : (
        <ul className="divide-y divide-border-subtle/60">
          {items.map((it, i) => {
            const sym = symCode(it.symbol);
            const sc = displayScore(it.score ?? it.lgb_score ?? it._fusion_weight ?? 0);
            const chg = it.change_pct ?? null;
            const strength = fundStrength?.items?.[sym];
            const fsRank = strength?.rank_pct ?? null;
            return (
              <li key={sym} className="px-4 py-2.5 hover:bg-surface-container-low/50 transition-colors">
                <div className="flex items-center gap-2">
                  <span className="text-[11px] font-display-numeric text-text-disabled w-[22px] shrink-0 text-center">
                    {String(i + 1).padStart(2, "0")}
                  </span>
                  <Link href={`/cn/stock?symbol=${sym}`} className="min-w-0 flex-1 group">
                    <div className="flex items-center gap-1.5 min-w-0">
                      <span className="text-[13px] font-semibold text-text-primary group-hover:text-status-info truncate transition-colors">
                        {it.name || sym}
                      </span>
                      <span className="text-[10px] text-text-disabled shrink-0">{sym}</span>
                    </div>
                    <div className="text-[10px] text-text-disabled truncate mt-0.5">
                      {it.sector || it.industry || "—"}
                      {fsRank != null && (
                        <span className={`ml-1 ${fsRank >= 0.7 ? "text-status-danger" : fsRank >= 0.5 ? "text-status-warning" : "text-text-disabled"}`}>
                          强度前{(fsRank * 100).toFixed(0)}%
                        </span>
                      )}
                    </div>
                  </Link>
                  <div className="text-right shrink-0">
                    <div className={`font-display-numeric text-[15px] font-bold leading-none ${scoreColor100(sc)}`}>
                      {sc}
                    </div>
                    <div className={`font-display-numeric text-[11px] mt-1 ${chgColor100(chg)}`}>
                      {chg != null ? `${chg > 0 ? "+" : ""}${Number(chg).toFixed(2)}%` : "—"}
                    </div>
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

/* ─── 今日计划（研究参考；智能选股页并入） ─── */
function TradePlanCard({ plan }: { plan: TradePlan | null }) {
  const cardCls = "rounded-2xl border border-border-subtle bg-surface-card p-4 shadow-sm sm:p-5";
  if (!plan) {
    return (
      <section aria-labelledby="plan-title" className={cardCls}>
        <h2 id="plan-title" className="text-[18px] font-semibold tracking-tight text-text-primary">今日计划</h2>
        <p className="mt-2 text-[13px] text-text-secondary">计划尚未生成，请稍后刷新。</p>
      </section>
    );
  }

  const status = plan.status || { code: "unknown", label: "—", detail: "" };
  const buys = (plan.buys || []).filter((b) => b.action !== "skip");
  const expo = Number(plan.position_exposure ?? 0);
  const layers = plan.exit_layers || [];
  const isAwaiting = status.code === "awaiting";
  const { unlocked } = useUnlocked();

  const MiniStat = ({ label, children }: { label: string; children: React.ReactNode }) => (
    <div className="rounded-xl border border-border-subtle bg-bg-primary/50 p-3">
      <div className="mb-1 text-[11px] text-text-tertiary">{label}</div>
      <div className="text-[14px] font-medium leading-snug text-text-primary">{children}</div>
    </div>
  );

  return (
    <section aria-labelledby="plan-title" className={`${cardCls} overflow-hidden`}>
      <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 id="plan-title" className="text-[20px] font-semibold tracking-tight text-text-primary">今日计划</h2>
          <p className="mt-1 text-[13px] text-text-secondary">
            模型给出的研究参考{plan.asof ? ` · 信号 ${plan.asof}` : ""}，不构成投资建议。
          </p>
        </div>
        {unlocked ? (
          <div className={`shrink-0 rounded-full border px-3 py-1 text-[13px] font-semibold ${statusTone(status.code)}`}>
            {status.label}
          </div>
        ) : (
          <LockedHint label="登录后查看计划状态与参考仓位" className="shrink-0" />
        )}
      </div>

      {unlocked && (status.detail || (plan.empty_reason_label && isAwaiting)) && (
        <div
          className={`mb-4 rounded-xl border px-4 py-3 text-[13px] leading-relaxed ${
            isAwaiting
              ? "border-status-warning/25 bg-status-warning/5 text-text-secondary"
              : "border-border-subtle bg-bg-primary/50 text-text-secondary"
          }`}
        >
          {status.detail && <p>{status.detail}</p>}
          {plan.empty_reason_label && isAwaiting && (
            <p className="mt-1 text-[12px] text-status-warning">
              {plan.empty_reason_label}
              {" · "}
              <Link href="/cn/paper-trading" className="font-semibold underline underline-offset-2 hover:text-text-primary">
                去模拟盘确认
              </Link>
            </p>
          )}
        </div>
      )}

      <div>
        <h3 className="mb-2 text-[14px] font-semibold text-text-primary">{unlocked ? "计划关注标的与参考仓位" : "计划关注标的"}</h3>
        {buys.length === 0 ? (
          <div className="rounded-xl border border-dashed border-border-subtle px-4 py-6 text-center">
            <p className="text-[13px] text-text-secondary">今日暂无计划关注标的</p>
            <p className="mt-1 text-[12px] text-text-tertiary">09:35 开盘终选后会自动更新</p>
          </div>
        ) : (
          <ul className="grid gap-2 md:grid-cols-2">
            {buys.map((b) => {
              const code = symCode(b.symbol);
              return (
                <li
                  key={code}
                  className="flex items-center justify-between gap-3 rounded-xl border border-border-subtle bg-bg-primary/50 px-3 py-2.5"
                >
                  <div className="min-w-0">
                    <Link
                      href={`/cn/stock?symbol=${code}`}
                      className="block truncate text-[14px] font-semibold text-text-primary hover:text-purple-primary"
                    >
                      {b.name || code}
                    </Link>
                    <div className="mt-0.5 truncate text-[12px] text-text-tertiary">
                      <span className="font-mono">{code}</span>
                      {b.sector ? ` · ${b.sector}` : ""}
                    </div>
                  </div>
                  {unlocked ? (
                    <div className="shrink-0 text-right font-display-numeric">
                      <div className="text-[13px] font-semibold text-purple-primary">
                        参考仓位 {(b.weight_pct ?? 0).toFixed(1)}%
                      </div>
                      <div className="text-[12px] text-text-tertiary">
                        {b.buy_price != null ? `参考价 ¥${Number(b.buy_price).toFixed(2)}` : "—"}
                      </div>
                    </div>
                  ) : (
                    <LockedHint className="shrink-0" />
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </div>

      <details className="group mt-4 rounded-xl border border-border-subtle">
        <summary className="flex cursor-pointer list-none flex-wrap items-center gap-x-3 gap-y-1 px-4 py-3 text-[13px] [&::-webkit-details-marker]:hidden">
          <span className="font-medium text-text-primary">计划参数与风控规则</span>
          <span className="text-text-tertiary">
            {unlocked
              ? `参考总仓位 ${(expo * 100).toFixed(0)}% · 关注 ${plan.trade_top_n ?? buys.length} 只`
              : `关注 ${plan.trade_top_n ?? buys.length} 只 · 仓位与风控规则登录后查看`}
          </span>
          <span className="ml-auto text-[12px] text-text-tertiary group-open:hidden">展开 ▾</span>
          <span className="ml-auto hidden text-[12px] text-text-tertiary group-open:inline">收起 ▴</span>
        </summary>
        {!unlocked ? (
          <div className="border-t border-border-subtle px-4 pb-4 pt-3">
            <LockedHint variant="block" note="参考总仓位、各标的参考仓位与参考价、风控退出规则仅对登录用户展示，仅供研究参考，不构成投资建议。" />
          </div>
        ) : (
        <div className="border-t border-border-subtle px-4 pb-4 pt-3">
          <div className="mb-5 grid grid-cols-2 gap-3 lg:grid-cols-4">
            <MiniStat label="参考总仓位"><span className="font-display-numeric text-[20px] font-semibold">{(expo * 100).toFixed(0)}%</span></MiniStat>
            <MiniStat label="计划关注只数"><span className="font-display-numeric text-[20px] font-semibold">Top {plan.trade_top_n ?? buys.length}</span></MiniStat>
            <MiniStat label="参考执行窗口">{plan.execution_window || "09:37 后"}</MiniStat>
            <MiniStat label="入场方式"><span className="font-mono text-[13px]">{plan.entry_mode || "gap_soft"}</span></MiniStat>
          </div>

          <div className="mb-3 flex flex-wrap items-center gap-2 text-[13px] font-semibold text-text-primary">
            风控退出规则
            <span className="rounded-full border border-border-subtle bg-bg-primary/60 px-2 py-0.5 text-[11px] font-normal text-text-tertiary">
              四层 · 决策层 {plan.arm || "A1_permission"}
            </span>
          </div>
          <ol className="grid gap-2 md:grid-cols-2">
            {layers.map((layer) => (
              <li
                key={layer.id}
                className="flex gap-3 rounded-xl border border-border-subtle bg-bg-primary/40 px-3 py-2.5"
              >
                <span
                  className={`mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-md font-mono text-[11px] font-bold ${layerBadgeTone(layer.id, layers.indexOf(layer))}`}
                >
                  {layer.id}
                </span>
                <span className="min-w-0 text-[12px] leading-relaxed">
                  <span className="font-medium text-text-primary">{layer.name}</span>
                  <span className="text-text-secondary"> — {layer.rule}</span>
                </span>
              </li>
            ))}
          </ol>
        </div>
        )}
      </details>
    </section>
  );
}

// AlphaPilot A 股 Dashboard — V15 真实筹码模型 (2026-07-09)
// Zeabur HTTPS -> cn_proxy.py -> 腾讯云 150.158.100.236
// 2026-07-13: 60秒轮询 /recommend/live 实时资金流（盘中阶段标签实时刷新）
"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import Link from "next/link";
import { HeaderBar } from "@/components/HeaderBar";
import {
  fetchCNScreener, fetchWatchlist, addToWatchlist, removeFromWatchlist,
  fetchCategorizedRecommend, fetchLiveRecommend,
  type ScreenerItem, type ScreenerResponse, type WatchlistItem,
  type CategorizedResponse,
} from "@/lib/cn-api";

const scoreColor = (s: number) =>
  s >= 0.50 ? "text-[#3EE6A8]" : s >= 0.40 ? "text-status-info" : s >= 0.30 ? "text-[#F5C451]" : "text-text-secondary";
const displayScore = (s: number) => Math.min(99, Math.max(75, Math.round(s * 45 + 75)));
const scoreLabel = (s: number) =>
  s >= 0.50 ? "A+" : s >= 0.35 ? "A" : s >= 0.25 ? "B+" : "B";

export default function CNDashboard() {
  const [data, setData] = useState<ScreenerResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [watchlistSymbols, setWatchlistSymbols] = useState<Set<string>>(new Set());
  const [wlData, setWlData] = useState<WatchlistItem[]>([]);
  const [wlLoading, setWlLoading] = useState<Record<string, boolean>>({});
  const [wlMsg, setWlMsg] = useState<{ type: string; text: string } | null>(null);
  const [catData, setCatData] = useState<CategorizedResponse | null>(null);
  const [catLoading, setCatLoading] = useState(true);
  const [priceDialog, setPriceDialog] = useState<{ item: any; price: string } | null>(null);
  const [priceDialogLoading, setPriceDialogLoading] = useState(false);
  // 实时状态标记
  const [liveTs, setLiveTs] = useState<number>(0);
  const [livePolling, setLivePolling] = useState<boolean>(false);

  const loadData = async () => {
    try {
      const [d, wl, cat] = await Promise.all([fetchCNScreener(), fetchWatchlist(), fetchCategorizedRecommend()]);
      setData(d);
      setWlData(wl.watchlist || []);
      setWatchlistSymbols(new Set((wl.watchlist || []).map((w: WatchlistItem) => w.symbol)));
      setCatData(cat);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      await loadData();
      if (!cancelled) { setLoading(false); setCatLoading(false); }
    })();
    return () => { cancelled = true; };
  }, []);

  // 30 min auto refresh (全量评分+分类)
  useEffect(() => {
    const id = setInterval(loadData, 30 * 60 * 1000);
    return () => clearInterval(id);
  }, []);

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
            return { ...prev, recommendations: reranked };
          });
          console.log(`[rerank] ${new Date().toLocaleTimeString()} 动态重排完成`);
        } else if (live && live.data && live.data.length > 0) {
          // 普通60秒：字段级合并（不改变排名）
          setData((prev) => {
            if (!prev) return prev;
            const liveMap = new Map(live.data.map((it: any) => [it.symbol, it]));
            const updated = prev.recommendations.map((it: any) => {
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
    await loadData();
    setRefreshing(false);
  };

  const handleToggleWatchlist = async (item: ScreenerItem) => {
    const sym = item.symbol.replace(/^(sh|sz)/, "");
    if (watchlistSymbols.has(sym)) {
      try {
        await removeFromWatchlist(sym);
        setWatchlistSymbols(prev => { const n = new Set(prev); n.delete(sym); return n; });
        setWlMsg({ type: "success", text: `已取消收藏 ${item.name}` });
      } catch (e: any) {
        setWlMsg({ type: "error", text: e.message || "操作失败" });
      }
      setTimeout(() => setWlMsg(null), 3000);
      try { const wl = await fetchWatchlist(); setWlData(wl.watchlist || []); } catch {}
    } else {
      const defaultPrice = item.buy_price || 0;
      setPriceDialog({ item, price: (defaultPrice > 0 ? defaultPrice : "").toString() });
    }
  };

  const confirmAddWatchlist = async () => {
    if (!priceDialog) return;
    const item = priceDialog.item;
    const sym = item.symbol.replace(/^(sh|sz)/, "");
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
    try { const wl = await fetchWatchlist(); setWlData(wl.watchlist || []); } catch {}
  };

  const items = data?.recommendations ?? [];
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
  if (catData) {
    const catStocks = Object.values(catData.categories).flatMap((cat: any) => cat.stocks || []);
    const catChanges = buildSectorChanges(catStocks);
    Object.entries(catChanges).forEach(([k, v]) => { sectorChanges[k] = v; });
  }
  const markupStocks = catData?.categories?.markup?.stocks ?? [];
  const isMarkupTop = markupStocks.length > 0;
  const top = isMarkupTop
    ? markupStocks.reduce((best, s) => s.score_pct > best.score_pct ? s : best, markupStocks[0])
    : (items.find(it => it.money_flow_pass === true) || items[0]);
  const avgScore = items.length ? (items.reduce((s, i) => s + i.score, 0) / items.length) : 0;
  const returnedCount = data?.stats?.returned ?? items.length;

  // 实时状态显示
  const liveAgo = liveTs > 0 ? Math.max(0, Math.floor(Date.now() / 1000 - liveTs)) : null;
  const liveStatusText = liveAgo === null
    ? "等待首次实时刷新"
    : liveAgo < 5 ? "刚刚"
    : liveAgo < 60 ? `${liveAgo}秒前`
    : `${Math.floor(liveAgo / 60)}分钟前`;

  return (
    <main className="mx-auto max-w-[1440px] px-4 sm:px-6 lg:px-8 py-4 sm:py-6 lg:py-8 min-h-screen">
      <HeaderBar market="cn" />

      {wlMsg && (
        <div className={`fixed top-20 right-4 z-50 rounded-xl p-4 shadow-2xl ${
          wlMsg.type === "success" ? "bg-[rgba(62,230,168,0.15)] border border-[#3EE6A8]" : "bg-[rgba(255,93,93,0.15)] border border-[#FF5D5D]"
        }`}>
          <p className="text-[13px] text-text-primary">{wlMsg.text}</p>
        </div>
      )}

      {error && (
        <div className="glass mb-6 rounded-2xl border border-[#FF5D5D] p-4">
          <div className="flex items-start gap-3">
            <svg className="w-6 h-6 shrink-0 text-[#FF5D5D]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
            <div className="flex-1">
              <p className="text-sm text-[#FF5D5D] font-semibold">后端无法连接</p>
              <p className="mt-1 text-[12px] text-text-secondary">{error}</p>
              <button onClick={handleRefresh} className="mt-3 rounded-lg bg-[#FF5D5D] px-4 py-2 text-[12px] font-semibold text-white hover:bg-[#ff7a7a]">
                重试
              </button>
            </div>
          </div>
        </div>
      )}

      {data && (
        <>
        <div className="w-full h-px bg-gradient-to-r from-transparent via-[#A78BFA]/30 to-transparent mb-6"></div>
        <section className="mb-8 grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 sm:gap-4">
          <KPI label="今日最佳" value={top ? top.name : "—"} sub={top ? `${top.symbol.replace(/^(sh|sz)/,"")} · ${displayScore(top.score)}信心${isMarkupTop ? " · 拉升确认" : top.money_phase_label ? " · " + top.money_phase_label : ""}` : ""} accent="#3EE6A8" />
          <KPI label="实时资金" value={livePolling ? "拉取中" : (liveAgo != null ? "✓" : "—")} sub={`资金流 ${liveStatusText} · 60秒刷新`} accent="#F5C451" />
          <KPI label="今日推荐" value={`${returnedCount}`} sub={`${items.length} 只通过门控 · 排名前${Math.round(items.length / (data?.stats?.total_scanned || 1) * 100)}%`} accent="#3EE6A8" />
          <KPI label="平均信心" value={`${displayScore(avgScore)}`} sub={`信心分${(avgScore * 100).toFixed(0)}% 原始`} accent="#A78BFA" />
          <KPI label="全量扫描" value={`${data.stats.valid_scored}`} sub={`${data.stats.total_scanned} 只 · ${(data.stats.elapsed_seconds / 60).toFixed(0)}m · 自我学习`} accent="#F5C451" />
        </section>
        </>
      )}

      <section className="glass rounded-2xl p-3 sm:p-4 lg:p-6 mb-4 sm:mb-6">
        <div className="mb-4 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <div className="w-1 h-6 rounded-full bg-status-info"></div>
              <h2 className="text-[18px] font-semibold text-text-primary">A 股 Top 10 机会</h2>
              <span className="text-[10px] px-2 py-0.5 rounded-full bg-[rgba(167,139,250,0.12)] text-status-info border border-[rgba(167,139,250,0.25)]">V18</span>
              {items[0]?._reranked && (
                <span className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full bg-[rgba(62,230,168,0.12)] text-[#3EE6A8] border border-[rgba(62,230,168,0.3)]">
                  <span className="inline-block w-1.5 h-1.5 rounded-full bg-[#3EE6A8] animate-pulse"></span>
                  5分钟动态重排
                </span>
              )}
              {liveTs > 0 && (
                <span className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full bg-[rgba(245,196,81,0.12)] text-[#F5C451] border border-[rgba(245,196,81,0.3)]">
                  <span className="inline-block w-1.5 h-1.5 rounded-full bg-[#F5C451] animate-pulse"></span>
                  实时 {liveStatusText}
                </span>
              )}
            </div>
            <p className="mt-0.5 text-[12px] text-text-disabled">
              V19 Fusion 决策系统 · 30维融合特征 · 5模型集成 · 凌晨 5:00 选股 · 含隔夜美股影响因子 · 量比换手门控 · 自我提升学习 · 盘中60秒实时资金刷新 · 每5分钟动态重排 · Top 10 完整榜单
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Link href="/cn/watchlist" className="rounded-lg border border-border-subtle bg-surface-card px-3 py-1.5 text-[12px] text-[#F5C451] hover:border-[#F5C451] transition-colors flex items-center gap-1">
              <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="currentColor" stroke="none"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>
              收藏追踪
            </Link>
            <button
              onClick={handleRefresh}
              disabled={refreshing}
              className="rounded-lg border border-border-subtle bg-surface-card px-3 py-1.5 text-[12px] text-text-secondary hover:border-status-info hover:text-text-primary disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1.5"
            >
              <svg className={`w-4 h-4 ${refreshing ? "animate-spin" : ""}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="23 4 23 10 17 10" />
                <polyline points="1 20 1 14 7 14" />
                <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
              </svg>
              {refreshing ? "刷新中..." : "刷新"}
            </button>
          </div>
        </div>

        {loading && (
          <div className="flex flex-col items-center justify-center py-20">
            <div className="h-12 w-12 animate-spin rounded-full border-4 border-border-subtle border-t-[#A78BFA]"></div>
            <p className="mt-4 text-[14px] text-text-secondary">加载中...</p>
          </div>
        )}

        {data && (
          <div className="overflow-x-auto">
            <table className="w-full table-fixed">
              <colgroup>
                <col className="w-[4%]" />
                <col className="w-[9%]" />
                <col className="w-[14%]" />
                <col className="w-[12%]" />
                <col className="w-[10%]" />
                <col className="w-[12%]" />
                <col className="w-[9%]" />
                <col className="w-[10%]" />
                <col className="w-[10%]" />
                <col className="w-[10%]" />
              </colgroup>
              <thead>
                <tr className="border-b border-border-subtle text-[11px] uppercase tracking-wider text-text-disabled">
                  <th className="px-3 py-3 font-medium text-left">#</th>
                  <th className="px-3 py-3 font-medium text-left">代码</th>
                  <th className="px-3 py-3 font-medium text-left hidden sm:table-cell">名称</th>
                  <th className="px-3 py-3 font-medium text-left hidden lg:table-cell">板块</th>
                  <th className="px-3 py-3 font-medium text-right">评分</th>
                  <th className="px-3 py-3 font-medium text-left hidden xl:table-cell">资金</th>
                  <th className="px-3 py-3 font-medium text-left hidden 2xl:table-cell">基本</th>
                  <th className="px-3 py-3 font-medium text-right">现价</th>
                  <th className="px-3 py-3 font-medium text-right hidden xl:table-cell">目标价</th>
                  <th className="px-3 py-3 font-medium text-left">操作</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item, i) => {
                  const sym = item.symbol.replace(/^(sh|sz)/, "");
                  const isFav = watchlistSymbols.has(sym);
                  const isWlLoading = wlLoading[sym] ?? false;
                  return (
                  <tr key={item.symbol} className="border-b border-border-subtle/50 hover:bg-[rgba(77,163,255,0.04)]">
                    <td className="px-3 py-3 text-left text-[12px] text-text-disabled font-display-numeric">
                      {String(i + 1).padStart(2, "0")}
                    </td>
                    <td className="px-3 py-3 text-left">
                      <span className="font-mono text-[14px] font-semibold text-status-info">{sym}</span>
                    </td>
                    <td className="px-3 py-3 text-left text-[13px] text-text-primary hidden sm:table-cell">
                      <Link href={`/cn/stock?symbol=${item.symbol}`} className="hover:text-status-info transition-colors">{item.name}</Link>
                    </td>
                    <td className="px-3 py-3 text-left hidden lg:table-cell">
                      {item.sector ? (
                        <span className="inline-flex items-center gap-1 rounded-full bg-[rgba(167,139,250,0.12)] px-2 py-0.5 text-[11px] font-medium text-status-info border border-[rgba(167,139,250,0.25)] max-w-[180px] whitespace-nowrap">
                          <span className="truncate">{item.sector}</span>
                          {item.sector_change_pct != null && (
                            <span className={`shrink-0 ${
                              item.sector_change_pct >= 0 ? "text-[#FF5D5D]" : "text-[#3EE6A8]"
                            }`}>
                              {item.sector_change_pct > 0 ? "+" : ""}{item.sector_change_pct.toFixed(1)}%
                            </span>
                          )}
                        </span>
                      ) : (
                        <span className="text-[12px] text-text-disabled">—</span>
                      )}
                    </td>
                    <td className={`px-3 py-3 text-right ${scoreColor(item.score)}`}>
                      <div className="flex flex-col items-end">
                        <span className="font-display-numeric text-[22px] font-bold leading-none">
                          {displayScore(item.score)}<span className="text-[13px]">信心</span>
                        </span>
                        {item.score_label && (
                          <span className="text-[10px] text-text-disabled mt-0.5">{item.score_label}</span>
                        )}
                        <span className={`text-[9px] font-medium ${scoreColor(item.score)}`}>
                          {scoreLabel(item.score)}
                          {item.score >= 0.45 && ' '}<svg className="inline-block w-3 h-3 text-[#F5C451]" viewBox="0 0 24 24" fill="currentColor" stroke="none"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>
                          {item.score >= 0.55 && '🔥'}
                        </span>
                      </div>
                    </td>
                    <td className="px-3 py-3 text-left hidden xl:table-cell">
                      {item.active_buy_ratio != null ? (
                        <div className="flex flex-col gap-1">
                          <span className={`text-[12px] font-display-numeric ${item.active_buy_ratio >= 0.5 ? "text-[#3EE6A8]" : "text-[#FF5D5D]"}`}>
                            {(item.active_buy_ratio * 100).toFixed(0)}% 主动买入
                          </span>
                          {item.money_phase_label && (
                            <span className="text-[11px] text-[#F5C451]">{item.money_phase_label}</span>
                          )}
                          {/* 多源信号标签 */}
                          {item._signals && item._signals.length > 0 && (
                            <div className="flex flex-wrap gap-1 mt-0.5">
                              {item._signals.includes("ths_hot") && (
                                <span className="inline-flex items-center gap-0.5 rounded-full bg-[rgba(139,92,246,0.15)] px-1.5 py-0.5 text-[9px] font-medium text-status-info border border-[rgba(139,92,246,0.25)]">
                                  📊 热点
                                </span>
                              )}
                              {item._signals.includes("margin_up") && (
                                <span className="inline-flex items-center gap-0.5 rounded-full bg-[rgba(62,230,168,0.15)] px-1.5 py-0.5 text-[9px] font-medium text-[#3EE6A8] border border-[rgba(62,230,168,0.25)]">
                                  🧲 融资
                                </span>
                              )}
                              {/* longhubang 和northbound 等将来从API获取时再加 */}
                            </div>
                          )}
                        </div>
                      ) : (
                        <span className="text-[12px] text-text-disabled">—</span>
                      )}
                    </td>
                    <td className="px-3 py-3 text-left hidden 2xl:table-cell">
                      {item.eps != null ? (
                        <div className="flex flex-col gap-1">
                          <span className="text-[12px] font-display-numeric text-text-primary">
                            EPS {item.eps.toFixed(2)}
                          </span>
                          {item.fundamental_pass === true && (
                            <span className="inline-flex w-fit items-center rounded-full bg-[rgba(62,230,168,0.15)] px-1.5 py-0.5 text-[10px] font-medium text-[#3EE6A8]">盈利</span>
                          )}
                        </div>
                      ) : (
                        <span className="text-[12px] text-text-disabled">—</span>
                      )}
                    </td>
                    <td className="px-3 py-3 text-right text-[14px] text-text-primary font-display-numeric">
                      {(() => {
                        const curPrice = item.buy_price > 0 && item.change_pct != null
                          ? item.buy_price.toFixed(2)
                          : null;
                        return curPrice ? `${curPrice}` : (item.buy_price > 0 ? item.buy_price.toFixed(2) : "—");
                      })()}
                      {item.buy_price > 0 && (
                        <span className="block text-[9px] text-text-disabled font-normal">昨收 ¥{item.buy_price.toFixed(2)}</span>
                      )}
                    </td>
                    <td className="px-3 py-3 text-right text-[13px] text-[#3EE6A8] font-display-numeric hidden xl:table-cell">
                      {item.target_price > 0 ? item.target_price.toFixed(2) : "—"}
                    </td>
                    <td className="px-3 py-3 text-left">
                      <div className="flex items-center gap-1.5 sm:gap-2 flex-nowrap">
                        <button
                          onClick={() => handleToggleWatchlist(item)}
                          disabled={isWlLoading}
                          className={`rounded-lg px-1.5 sm:px-2.5 py-1.5 text-[11px] font-medium transition-colors disabled:opacity-50 whitespace-nowrap ${
                            isFav
                              ? "bg-[rgba(245,196,81,0.15)] text-[#F5C451] hover:bg-[rgba(245,196,81,0.25)]"
                              : "border border-border-subtle bg-surface-card text-text-disabled hover:border-[#F5C451] hover:text-[#F5C451]"
                          }`}>
                          {isWlLoading ? "..." : isFav ? "★已收藏" : "☆收藏"}
                        </button>
                        <Link href={`/cn/stock?symbol=${item.symbol}`} className="text-[12px] text-status-info hover:underline shrink-0">
                          详情
                        </Link>
                      </div>
                    </td>
                  </tr>
                )})}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {catData && (
        <section className="mb-6">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <div className="flex items-center gap-2 mb-1">
                <div className="w-1 h-6 rounded-full bg-[#F5C451]"></div>
                <h2 className="text-[18px] font-semibold text-text-primary">资金阶段分类</h2>
              </div>
              <p className="mt-0.5 text-[12px] text-text-disabled">
                4 大板块 · 凌晨 5:00 选股 · 含隔夜美股影响
              </p>
            </div>
          </div>
          {catLoading ? (
            <div className="flex items-center justify-center py-8">
              <div className="h-8 w-8 animate-spin rounded-full border-3 border-border-subtle border-t-[#A78BFA]"></div>
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {PHASE_GROUPS.map(group => (
                <GroupCard key={group.key} group={group}
                  categories={catData.categories || {}}
                  watchlistSymbols={watchlistSymbols} wlLoading={wlLoading}
                  onToggleWatchlist={handleToggleWatchlist} sectorChanges={sectorChanges} />
              ))}
            </div>
          )}
        </section>
      )}

      {wlData.length > 0 && (
        <section className="glass rounded-2xl p-3 sm:p-4 lg:p-6 mb-4 sm:mb-6">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <div className="flex items-center gap-2"><svg className="w-5 h-5 text-[#F5C451]" viewBox="0 0 24 24" fill="currentColor" stroke="none"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg><h2 className="text-[20px] font-semibold text-text-primary">收藏追踪</h2></div>
              <p className="mt-0.5 text-[12px] text-text-disabled">
                记录入场价 · 自动追踪 T+1/T+2/T+3 涨跌
              </p>
            </div>
            <Link href="/cn/watchlist" className="text-[12px] text-status-info hover:underline">
              查看全部 →
            </Link>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead>
                <tr className="border-b border-border-subtle text-[11px] uppercase tracking-wider text-text-disabled">
                  <th className="px-3 py-2 font-medium">股票</th>
                  <th className="px-3 py-2 text-right font-medium">入场价</th>
                  <th className="px-3 py-2 text-right font-medium">T+1</th>
                  <th className="px-3 py-2 text-right font-medium">T+2</th>
                  <th className="px-3 py-2 text-right font-medium hidden sm:table-cell">T+3</th>
                  <th className="px-3 py-2 font-medium hidden sm:table-cell">状态</th>
                </tr>
              </thead>
              <tbody>
                {wlData.slice(0, 5).map((w) => (
                  <tr key={w.id} className="border-b border-border-subtle/50 text-[13px]">
                    <td className="px-3 py-2">
                      <div className="flex items-center gap-1.5 flex-nowrap min-w-0">
                        <span className="font-semibold text-text-primary truncate">{w.name}</span>
                        <span className="text-text-disabled text-[11px] shrink-0">{w.symbol}</span>
                        {w.sector && (
                          <span className="hidden sm:inline-flex items-center gap-1 text-[9px] px-1 py-0.5 rounded-full bg-[rgba(77,163,255,0.1)] text-status-info border border-[rgba(77,163,255,0.2)] leading-none shrink-0">
                            <span className="truncate max-w-[50px]">{w.sector}</span>
                            {(() => {
                              const sc = (w as any).sector_change_pct ?? sectorChanges[w.sector];
                              return sc != null ? (
                                <span className={`shrink-0 ${
                                  sc >= 0 ? "text-[#FF5D5D]" : "text-[#3EE6A8]"
                                }`}>
                                  {sc > 0 ? "+" : ""}{sc.toFixed(1)}%
                                </span>
                              ) : null;
                            })()}
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-3 py-2 text-right font-mono text-[#F5C451]">{w.entry_price.toFixed(2)}</td>
                    <td className={`px-3 py-2 text-right font-mono ${w.day1_change != null ? (w.day1_change >= 0 ? "text-[#FF5D5D]" : "text-[#3EE6A8]") : "text-text-disabled"}`}>
                      {w.day1_change != null ? `${w.day1_change > 0 ? "+" : ""}${w.day1_change}%` : "—"}
                    </td>
                    <td className={`px-3 py-2 text-right font-mono ${w.day2_change != null ? (w.day2_change >= 0 ? "text-[#FF5D5D]" : "text-[#3EE6A8]") : "text-text-disabled"}`}>
                      {w.day2_change != null ? `${w.day2_change > 0 ? "+" : ""}${w.day2_change}%` : "—"}
                    </td>
                    <td className={`px-3 py-2 text-right font-mono hidden sm:table-cell ${w.day3_change != null ? (w.day3_change >= 0 ? "text-[#FF5D5D]" : "text-[#3EE6A8]") : "text-text-disabled"}`}>
                      {w.day3_change != null ? `${w.day3_change > 0 ? "+" : ""}${w.day3_change}%` : "—"}
                    </td>
                    <td className="px-3 py-2 hidden sm:table-cell">
                      <span className={`text-[11px] px-2 py-0.5 rounded-full ${w.status === "active" ? "bg-[rgba(62,230,168,0.15)] text-[#3EE6A8]" : "bg-[rgba(159,176,199,0.15)] text-text-secondary"}`}>
                        {w.status === "active" ? "追踪中" : "历史记录"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <section className="glass rounded-2xl p-3 sm:p-4 lg:p-6 mb-4 sm:mb-6">
        <div className="flex items-start gap-3 mb-3">
          <div className="w-1 h-12 rounded-full bg-[#8B5CF6] shrink-0 mt-1"></div>
          <div className="flex-1">
            <div className="flex items-center gap-2 mb-1">
              <svg className="w-5 h-5 text-status-info" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
              </svg>
              <h2 className="text-[17px] font-semibold text-text-primary">尾盘狙击</h2>
              <span className="text-[10px] px-2 py-0.5 rounded-full bg-[rgba(139,92,246,0.12)] text-status-info border border-[rgba(139,92,246,0.3)]">14:00</span>
              <span className="text-[10px] px-2 py-0.5 rounded-full bg-[rgba(245,196,81,0.12)] text-[#F5C451] border border-[rgba(245,196,81,0.3)]">一夜持股</span>
              {items[0]?._reranked && (
                <span className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full bg-[rgba(139,92,246,0.15)] text-status-info border border-[rgba(139,92,246,0.3)]">
                  <span className="inline-block w-1.5 h-1.5 rounded-full bg-status-info animate-pulse"></span>
                  动态重排中
                </span>
              )}
            </div>
            <p className="text-[11px] text-text-disabled">
              V19 Fusion 综合评分 · 动态重排 Top 3 · 资金+模型双重筛选 · 14:00 自动输出
            </p>
          </div>
        </div>

        {items.length > 0 && items[0]?._reranked ? (
          <div className="space-y-2">
            {items.filter((s: any) => {
              const chg = s.change_pct || 0;
              return chg < 9.4; // 过滤涨停
            }).slice(0, 3).map((s: any, i: number) => {
              const sym = s.symbol.replace(/^(sh|sz)/, "");
              const chg = s.change_pct || 0;
              const chgColor = chg >= 0 ? "text-[#FF5D5D]" : "text-[#3EE6A8]";
              const abr = s.active_buy_ratio || 0.5;
              const net = s.main_net || 0;
              // 计算实时价格（从昨收和涨跌幅算，确保一致）
              const livePrice = s.buy_price > 0 && s.change_pct != null
                ? s.buy_price.toFixed(2)
                : (s.price || s.buy_price || 0).toFixed(2);

              // 分析逻辑：为什么推荐这只
              const isUp = chg >= 0;
              const isStrongInflow = abr >= 0.55 && net > 0;
              const isBearTrap = abr >= 0.55 && !isUp && net > 0;
              const isAccumulation = abr >= 0.52 && chg < 2 && chg >= 0;
              const isMarkup = abr >= 0.52 && chg >= 2 && chg < 9.4;

              let advice = "";
              let adviceColor = "";
              if (isBearTrap) {
                advice = "🪤 诱空陷阱 · 下跌中主力暗中吸筹，明日期待反弹";
                adviceColor = "text-[#8B5CF6]";
              } else if (isMarkup) {
                advice = "🚀 主力拉升中 · 资金+模型双重确认，可轻仓跟进";
                adviceColor = "text-[#EF4444]";
              } else if (isStrongInflow && isUp) {
                advice = "💰 资金强势 · 放量上涨主力持续流入，趋势向好";
                adviceColor = "text-[#3EE6A8]";
              } else if (isAccumulation) {
                advice = "📥 吸筹阶段 · 主力默默买入但股价未涨，耐心持有";
                adviceColor = "text-[#3B82F6]";
              } else if (net > 0 && abr >= 0.52) {
                advice = "📊 资金流入中 · 虽有波动但主力在低位吸筹";
                adviceColor = "text-[#F5C451]";
              } else {
                advice = "📌 综合评分靠前 · 建议结合明日盘面判断";
                adviceColor = "text-text-secondary";
              }

              const risk = chg > 7 ? "⚠️ 涨幅已高" : chg < -7 ? "⚠️ 跌幅较大" : "✓ 适中";
              const riskColor = chg > 7 ? "text-[#FF5D5D]" : chg < -7 ? "text-[#FF5D5D]" : "text-[#3EE6A8]";

              return (
                <div key={s.symbol} className="rounded-lg bg-surface-container-low p-2.5 hover:bg-[#16202f] transition-colors">
                  <div className="grid grid-cols-[16px_1fr_65px_55px] sm:grid-cols-[20px_1fr_80px_80px_70px] lg:grid-cols-[20px_1fr_110px_90px_70px] items-center gap-1">
                    <span className="text-[13px] font-bold text-status-info">{i + 1}</span>
                    <div className="flex items-center gap-1.5 min-w-0">
                      <Link href={`/cn/stock?symbol=${s.symbol}`} className="text-[14px] font-medium text-text-primary hover:text-status-info truncate">{s.name}</Link>
                      <span className="text-[10px] text-text-disabled shrink-0">{sym}</span>
                      {s.sector && (
                        <span className="hidden sm:inline text-[10px] px-1.5 py-0.5 rounded-full bg-[rgba(139,92,246,0.1)] text-status-info border border-[rgba(139,92,246,0.2)] truncate max-w-[80px]">{s.sector}</span>
                      )}
                    </div>
                    <span className="text-[13px] font-display-numeric text-text-primary text-right">{livePrice}</span>
                    <span className={`text-[13px] font-display-numeric font-medium text-right ${chgColor}`}>{chg > 0 ? "+" : ""}{chg.toFixed(1)}%</span>
                    <span className={`hidden sm:block text-[11px] text-right font-medium ${riskColor}`}>{risk}</span>
                  </div>
                  <div className="mt-1.5 flex items-center gap-1.5 text-[11px]">
                    <span className={`${adviceColor}`}>{advice}</span>
                    <span className="text-[#4A5568]">·</span>
                    <span className="text-text-secondary">ABR {(abr * 100).toFixed(0)}%</span>
                    <span className="text-[#4A5568]">·</span>
                    <span className={`font-display-numeric ${net >= 0 ? "text-[#FF5D5D]" : "text-[#3EE6A8]"}`}>
                      主力{net >= 0 ? "+" : ""}{(net / 10000).toFixed(0)}万
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <div className="flex items-center gap-2 rounded-lg bg-surface-container-low px-3 py-2 border border-border-subtle">
            <svg className="w-4 h-4 text-text-disabled" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
            <p className="text-[12px] text-text-disabled">页面加载后 5 秒自动生成 · 过滤涨停股 · 资金+模型综合评分 Top 3</p>
          </div>
        )}
      </section>

      <section className="mb-6">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-1 h-6 rounded-full bg-[#3EE6A8]"></div>
          <h2 className="text-[18px] font-semibold text-text-primary">自我进化学习</h2>
          <span className="text-[10px] px-2 py-0.5 rounded-full bg-[rgba(62,230,168,0.12)] text-[#3EE6A8] border border-[rgba(62,230,168,0.25)]">AI 驱动</span>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 sm:gap-3">
          <div className="glass rounded-2xl p-4 card-lift border-t-2 border-t-[#A78BFA]">
            <svg className="w-6 h-6 mb-1 text-status-info" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg>
            <h3 className="text-[14px] font-semibold text-text-primary mb-1">自动历史回撤</h3>
            <p className="text-[11px] text-text-disabled leading-relaxed">
              每日 Top 5 推荐自动记录，T+1/T+3 涨跌幅自动追踪，生成完整回测数据库
            </p>
          </div>
          <div className="glass rounded-2xl p-4 card-lift border-t-2 border-t-[#3EE6A8]">
            <div className="text-[24px] mb-1">📊</div>
            <h3 className="text-[14px] font-semibold text-text-primary mb-1">胜率自动统计</h3>
            <p className="text-[11px] text-text-disabled leading-relaxed">
              收藏夹自动计算胜率/平均收益，数据驱动而非感觉驱动
            </p>
          </div>
          <div className="glass rounded-2xl p-4 card-lift border-t-2 border-t-[#F5C451]">
            <svg className="w-6 h-6 mb-1 text-[#F5C451]" viewBox="0 0 24 24" fill="currentColor" stroke="none"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
            <h3 className="text-[14px] font-semibold text-text-primary mb-1">门控参数优化</h3>
            <p className="text-[11px] text-text-disabled leading-relaxed">
              基于历史数据自动调整首板洗盘/量比换手门控参数，持续提升准确率
            </p>
          </div>
        </div>
      </section>

      <footer className="mt-10 text-center text-[11px] text-text-disabled">
        AlphaPilot 提供 AI 辅助分析，仅供教育用途，非投资建议。过往表现不保证未来收益。
        <br />
        A 股内容仅供在美华人教育用途，非中国境内投顾服务。
      </footer>

      {priceDialog && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/50 backdrop-blur-sm"
          onClick={() => !priceDialogLoading && setPriceDialog(null)}>
          <div className="w-[90vw] max-w-[380px] rounded-2xl border border-border-subtle bg-surface-card p-6 shadow-2xl mx-4"
            onClick={e => e.stopPropagation()}>
            <div className="flex items-center gap-2 mb-1"><svg className="w-5 h-5 text-[#F5C451]" viewBox="0 0 24 24" fill="currentColor" stroke="none"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg><h3 className="text-[18px] font-semibold text-text-primary">添加收藏</h3></div>
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
                className="flex-1 rounded-lg bg-status-info py-2.5 text-[13px] font-semibold text-on-primary hover:bg-[#C084FC] transition-colors disabled:opacity-50 flex items-center justify-center gap-2">
                {priceDialogLoading ? <span className="h-4 w-4 animate-spin rounded-full border-2 border-[#00315b] border-t-transparent" /> : null}
                {priceDialogLoading ? "添加中..." : "确认添加"}
              </button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}

function KPI({ label, value, sub, accent }: { label: string; value: string; sub: string; accent: string }) {
  const isBest = label === "今日最佳";
  return (
    <div className={`glass card-lift rounded-2xl p-4 ${isBest ? "border border-[rgba(62,230,168,0.2)]" : ""}`}>
      <div className="mb-2 flex items-center justify-between">
        <span className="text-[10px] uppercase tracking-wider text-text-disabled">{label}</span>
        <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: accent, boxShadow: `0 0 8px ${accent}` }}></span>
      </div>
      <div className="font-display-numeric text-[20px] sm:text-[26px] truncate" style={{ color: accent }}>
        {value}
      </div>
      <div className="mt-1 text-[11px] text-text-secondary">{sub}</div>
    </div>
  );
}

function PhaseIcon({ phaseKey, color, size = 24 }: { phaseKey: string; color: string; size?: number }) {
  const s: any = { width: size, height: size, viewBox: "0 0 24 24", fill: "none", stroke: color, strokeWidth: 2, strokeLinecap: "round", strokeLinejoin: "round" };
  switch (phaseKey) {
    case "markup": return <svg {...s}><path d="M12 21V5"/><polyline points="5 12 12 5 19 12"/><line x1="12" y1="5" x2="12" y2="7"/></svg>;
    case "rightside_ambush": return <svg {...s}><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="4"/><circle cx="12" cy="12" r="1.5" fill={color}/><line x1="12" y1="1" x2="12" y2="4"/><line x1="12" y1="20" x2="12" y2="23"/><line x1="1" y1="12" x2="4" y2="12"/><line x1="20" y1="12" x2="23" y2="12"/></svg>;
    case "accumulation_end": return <svg {...s}><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>;
    case "bear_trap": return <svg {...s}><polyline points="4 20 12 6 20 20"/><circle cx="12" cy="4" r="2.5" fill={color} stroke="none"/><line x1="12" y1="20" x2="12" y2="12"/></svg>;
    case "accumulation": return <svg {...s}><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 9 12 14 17 9"/><line x1="12" y1="14" x2="12" y2="2"/></svg>;
    case "suspicious": return <svg {...s}><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><circle cx="12" cy="16" r="0.5" fill={color}/><line x1="12" y1="9" x2="12" y2="13"/></svg>;
    case "distribution": return <svg {...s}><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="14"/></svg>;
    case "pullback": return <svg {...s}><path d="M21 17c-4 5-11 5-15 2S2 10 3 6"/><polyline points="7 13 3 10 7 7"/></svg>;
    case "sideways": return <svg {...s}><polyline points="3 10 7 14 12 10 17 14 21 10"/><polyline points="3 14 7 10 12 14 17 10 21 14"/></svg>;
    default: return <svg {...s}><circle cx="12" cy="12" r="8"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>;
  }
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
  { key: "buy_signal", label: "买入信号", desc: "主力资金正在运作，关注买入机会", color: "#EF4444", phases: ["markup", "rightside_ambush", "accumulation_end", "bear_trap"] },
  { key: "accumulation_watch", label: "吸筹观察", desc: "主力在低位默默吸筹", color: "#3B82F6", phases: ["accumulation"] },
  { key: "risk_warning", label: "风险警告", desc: "警惕回调或出货风险", color: "#F97316", phases: ["suspicious", "distribution"] },
  { key: "wait_and_see", label: "暂时观望", desc: "方向不明或回调中", color: "#6B7280", phases: ["pullback", "sideways"] }
];

function GroupCard({ group, categories, watchlistSymbols, wlLoading, onToggleWatchlist, sectorChanges }: {
  group: typeof PHASE_GROUPS[0];
  categories: Record<string, any>;
  watchlistSymbols: Set<string>;
  wlLoading: Record<string, boolean>;
  onToggleWatchlist: (item: any) => void;
  sectorChanges: Record<string, number>;
}) {
  const phaseLabels: Record<string, string> = {
    markup: "拉升", rightside_ambush: "右侧潜伏", accumulation_end: "吸筹末期",
    bear_trap: "诱空陷阱", accumulation: "吸筹",
    suspicious: "诱多嫌疑", distribution: "出货",
    pullback: "回调", sideways: "震荡"
  };
  const totalCount = group.phases.reduce((sum, pk) => sum + ((categories[pk]?.stocks?.length) || 0), 0);
  return (
    <div className="glass rounded-2xl p-4 card-lift flex flex-col transition-all min-h-[320px]"
      style={{ borderLeftColor: group.color, borderLeftWidth: 3 }}>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <PhaseIcon phaseKey={group.phases[0]} color={group.color} size={22} />
          <div>
            <h3 className="text-[16px] font-semibold text-text-primary">{group.label}</h3>
            <p className="text-[11px] text-text-disabled">{group.desc} · {totalCount} 只</p>
          </div>
        </div>
        {totalCount > 0 && (
          <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-[rgba(245,196,81,0.15)] text-[#F5C451] border border-[rgba(245,196,81,0.3)] font-medium animate-pulse">
            今日有数据
          </span>
        )}
      </div>
      <div className="space-y-3 flex-1">
        {group.phases.map(pk => {
          const cat = categories[pk];
          const stocks = cat?.stocks || [];
          const subColor = PHASE_COLORS[pk] || "#6E7C93";
          return (
            <div key={pk}>
              <div className="flex items-center gap-1.5 mb-1.5 px-1">
                <PhaseIcon phaseKey={pk} color={subColor} size={16} />
                <span className="text-[12px] font-medium" style={{ color: subColor }}>
                  {phaseLabels[pk] || pk}
                </span>
                <span className="text-[10px] text-text-disabled">({stocks.length} 只)</span>
                {stocks.length > 0 && (
                  <span className="text-[8px] px-1 py-0.5 rounded-sm bg-[rgba(245,196,81,0.12)] text-[#F5C451] font-medium">热</span>
                )}
              </div>
              {stocks.length === 0 ? (
                <p className="text-[11px] text-[#4A5568] px-1 py-1.5 italic">暂无标的</p>
              ) : (
                <div className="space-y-1 overflow-x-auto -mx-2 px-2">
                  {stocks.slice(0, 5).map((s: any, i: number) => {
                    const sym = s.symbol.replace(/^(sh|sz)/, "");
                    const isFav = watchlistSymbols.has(sym);
                    const isWlLoading = wlLoading[sym] ?? false;
                    const price = s.price || s.buy_price || 0;
                    const chg = s.change_pct;
                    const chgStr = chg != null ? `${chg > 0 ? "+" : ""}${chg.toFixed(1)}%` : "—";
                    const chgColor = chg != null ? (chg >= 0 ? "text-[#FF5D5D]" : "text-[#3EE6A8]") : "text-text-disabled";
                    const scChg = s.sector_change_pct ?? (s.sector ? sectorChanges[s.sector] : null);
                    return (
                      <div key={s.symbol} className="grid grid-cols-[16px_1fr_38px_48px] sm:grid-cols-[20px_1fr_42px_55px_70px] lg:grid-cols-[22px_1fr_42px_1fr_85px_70px_26px] items-center rounded-lg bg-surface-container-low p-1.5 hover:bg-[#16202f] transition-colors group gap-1">
                        <span className="text-[11px] text-text-disabled font-display-numeric text-center">{i + 1}</span>
                        <Link href={`/cn/stock?symbol=${s.symbol}`} className="flex items-center gap-1 min-w-0 overflow-hidden">
                          <span className="text-[13px] font-medium text-text-primary group-hover:text-status-info truncate transition-colors">{s.name}</span>
                          <span className="text-[10px] text-text-disabled shrink-0">{sym}</span>
                        </Link>
                        <span className="font-display-numeric text-[11px] font-bold text-center" style={{color: displayScore(s.score_raw || s.score) > 85 ? "#3EE6A8" : displayScore(s.score_raw || s.score) > 80 ? "#A78BFA" : "#9FB0C7"}}>
                          {displayScore(s.score_raw || s.score)}
                        </span>
                        <div className="hidden sm:flex items-center gap-1 min-w-0 overflow-hidden">
                          {s.sector ? (
                            <span className="inline-flex items-center gap-1.5 text-[10px] px-1.5 py-0.5 rounded-full bg-[rgba(77,163,255,0.1)] text-status-info border border-[rgba(77,163,255,0.2)] leading-none shrink-0">
                              <span className="truncate max-w-[55px] sm:max-w-[65px]">{s.sector}</span>
                              {scChg != null && (
                                <span className={`shrink-0 ${scChg >= 0 ? "text-[#FF5D5D]" : "text-[#3EE6A8]"}`}>
                                  {scChg > 0 ? "+" : ""}{scChg.toFixed(1)}%
                                </span>
                              )}
                            </span>
                          ) : (
                            <span className="text-[11px] text-[#4A5568]">—</span>
                          )}
                        </div>
                        <span className="hidden sm:block font-display-numeric text-[12px] text-text-primary text-right">
                          {price > 0 ? price.toFixed(2) : "—"}
                        </span>
                        <span className={`font-display-numeric text-[12px] font-medium text-right ${chgColor}`}>
                          {chgStr}
                        </span>
                        <button
                          onClick={(e) => { e.stopPropagation(); onToggleWatchlist(s); }}
                          disabled={isWlLoading}
                          className={`hidden sm:block text-[14px] text-center transition-colors disabled:opacity-50 ${
                            isFav ? "text-[#F5C451]" : "text-text-disabled hover:text-[#F5C451]"
                          }`}>
                          {isWlLoading ? "..." : isFav ? "★" : "☆"}
                        </button>
                      </div>
                    );
                  })}
                  {stocks.length > 5 && (
                    <p className="text-[11px] text-status-info text-right pr-1">+{stocks.length - 5} 只更多</p>
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

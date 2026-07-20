// AlphaPilot A 股 Dashboard — V3.1 硬门控 + VM2.5
// Zeabur HTTPS -> cn_proxy.py -> 腾讯云 150.158.100.236
// 2026-07-19: 浅色 UI 统一 · 信心分展示 · 版本文案对齐
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
  s >= 0.50 ? "text-status-success" : s >= 0.40 ? "text-status-info" : s >= 0.30 ? "text-status-warning" : "text-text-secondary";
const displayScore = (s: number) => Math.min(99, Math.max(75, Math.round(Number(s || 0) * 45 + 75)));
const formatModelProba = (s: number) => Number(s || 0).toFixed(2);

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
  const [overnightData, setOvernightData] = useState<any>(null);
  const [s2Data, setS2Data] = useState<any>(null);

  const loadData = async (wlRefresh = false) => {
    try {
      const [d, wl, cat, s2] = await Promise.all([
        fetchCNScreener(),
        fetchWatchlist(wlRefresh),
        fetchCategorizedRecommend(),
        fetch("/api/v1/cn/recommend/eod-s2").then(r => r.json()).catch(() => null)
      ]);
      setData(d);
      setWlData(wl.watchlist || []);
      setWatchlistSymbols(new Set((wl.watchlist || []).map((w: WatchlistItem) => String(w.symbol || "").replace(/\D/g, "").slice(-6))));
      setCatData(cat);
      setS2Data(s2);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  
  useEffect(() => {
    fetch("/api/v1/cn/overnight")
      .then(r => r.json())
      .then(d => setOvernightData(d))
      .catch(() => {});
  }, []);
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    loadData(true).finally(() => {
      if (!cancelled) { setLoading(false); setCatLoading(false); }
    });
    return () => { cancelled = true; };
  }, []);

  // 30 min auto refresh (全量评分+分类)

  useEffect(() => {
    const id = setInterval(() => loadData(false), 30 * 60 * 1000);
    return () => clearInterval(id);
  }, []);

  // 收藏追踪与收藏页同源：交易时段每 60s 刷新一次
  useEffect(() => {
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
    await loadData(true);
    setRefreshing(false);
  };

  const bareSym = (s?: string) => String(s || "").replace(/\D/g, "").slice(-6);

  const handleToggleWatchlist = async (item: ScreenerItem) => {
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

      {/* 数据状态卡片 - 盘后数据更新时间 + 一键刷新 */}
      <DataStatusCard />

      {wlMsg && (
        <div className={`fixed top-20 right-4 z-50 rounded-xl p-4 shadow-2xl ${
          wlMsg.type === "success" ? "bg-status-success/15 border border-status-success" : "bg-status-danger/15 border border-status-danger"
        }`}>
          <p className="text-[13px] text-text-primary">{wlMsg.text}</p>
        </div>
      )}

      {error && (
        <div className="card-lift mb-6 rounded-2xl border border-status-danger bg-surface-card p-4 shadow-sm">
          <div className="flex items-start gap-3">
            <svg className="w-6 h-6 shrink-0 text-status-danger" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
            <div className="flex-1">
              <p className="text-sm text-status-danger font-semibold">后端无法连接</p>
              <p className="mt-1 text-[12px] text-text-secondary">{error}</p>
              <button onClick={handleRefresh} className="mt-3 rounded-lg bg-status-danger px-4 py-2 text-[12px] font-semibold text-white hover:bg-status-danger/70">
                重试
              </button>
            </div>
          </div>
        </div>
      )}

      {data && (
        <>
        <div className="w-full h-px bg-gradient-to-r from-transparent via-purple-primary/25 to-transparent mb-6" />
        <section className="mb-8 grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 sm:gap-4">
          <KPI
            label="今日最佳"
            value={top ? top.name : "—"}
            sub={
              top
                ? `${top.symbol.replace(/^(sh|sz)/, "")} · 信心${displayScore(top.score)}${
                    isMarkupTop ? " · 拉升确认" : top.money_phase_label ? " · " + top.money_phase_label : ""
                  }`
                : ""
            }
            accent="var(--color-status-success)"
          />
          <KPI
            label="实时资金"
            value={livePolling ? "拉取中" : liveAgo != null ? "已同步" : "—"}
            sub={`资金流 ${liveStatusText} · 60秒刷新`}
            accent="var(--color-status-warning)"
          />
          <KPI
            label="今日推荐"
            value={`${returnedCount}`}
            sub={`${items.length} 只通过门控`}
            accent="var(--color-status-success)"
          />
          <KPI
            label="平均信心"
            value={`${displayScore(avgScore)}`}
            sub={`模型概率 ${formatModelProba(avgScore)} · 非百分制`}
            accent="var(--color-purple-primary)"
          />
          <KPI
            label="全量扫描"
            value={`${data.stats.valid_scored}`}
            sub={`${data.stats.total_scanned} 只 · ${((data.stats.elapsed_seconds || 0) / 60).toFixed(0)}m`}
            accent="var(--color-status-info)"
          />
        </section>
        </>
      )}

      <section className="rounded-2xl border border-border-subtle bg-surface-card shadow-sm p-3 sm:p-4 lg:p-6 mb-4 sm:mb-6">
        <div className="mb-4 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 scan-line">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <div className="w-1 h-6 rounded-full bg-status-info"></div>
              <h2 className="text-[18px] font-semibold text-text-primary">A 股 Top 10 机会</h2>
              <span className="text-[10px] px-2 py-0.5 rounded-full bg-purple-light text-purple-primary border border-purple-primary/20">
                V3.1 · VM2.5
              </span>
              {items[0]?._reranked && (
                <span className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full bg-status-success/12 text-status-success border border-status-success/25">
                  <span className="inline-block w-1.5 h-1.5 rounded-full bg-status-success animate-pulse" />
                  5分钟动态重排
                </span>
              )}
              {liveTs > 0 && (
                <span className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full bg-status-warning/12 text-status-warning border border-status-warning/25">
                  <span className="inline-block w-1.5 h-1.5 rounded-full bg-status-warning animate-pulse" />
                  实时 {liveStatusText}
                </span>
              )}
            </div>
            <p className="mt-0.5 text-[12px] text-text-secondary max-w-2xl">
              V3.1 硬门控漏斗 · VM2.5 打分 · 资金门控 · 大盘暴露 · 盘中 60 秒刷新
            </p>
          </div>
          <div className="flex flex-row items-center gap-2 shrink-0">
            <Link href="/cn/watchlist" className="rounded-lg border border-border-subtle bg-surface-card px-2.5 sm:px-3 py-1.5 text-[11px] sm:text-[12px] text-status-warning hover:border-status-warning transition-colors whitespace-nowrap">
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
            <div className="h-12 w-12 animate-spin rounded-full border-4 border-border-subtle border-t-purple-primary"></div>
            <p className="mt-4 text-[14px] text-text-secondary">加载中...</p>
          </div>
        )}

        {data && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 animate-fade-in">
            {items.map((item, i) => {
              const sym = bareSym(item.symbol);
              const isFav = watchlistSymbols.has(sym);
              const isWlLoading = wlLoading[sym] ?? false;
              const changePct = item.change_pct ?? 0;
              const isUp = changePct >= 0;
              return (
              <div key={item.symbol} className="card-lift rounded-xl border border-border-subtle bg-surface-card p-4 shadow-sm">
                {/* Row 1: Rank + Symbol + Name + Sector + Change% */}
                <div className="flex items-center justify-between gap-2 mb-2.5">
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="text-[12px] font-display-numeric text-text-disabled shrink-0 w-[24px]">
                      {String(i + 1).padStart(2, "0")}
                    </span>
                    <span className="font-mono text-[13px] font-semibold text-status-info shrink-0">{sym}</span>
                    <Link href={`/cn/stock?symbol=${item.symbol}`} className="text-[15px] font-semibold text-text-primary hover:text-status-info truncate transition-colors">
                      {item.name}
                    </Link>
                    {item.sector && (
                      <span className="hidden sm:inline-flex items-center gap-1 rounded-full bg-primary/10 px-2 py-0.5 text-[10px] font-medium text-primary border border-primary/20 shrink-0">
                        {item.sector}
                        {item.sector_change_pct != null && (
                          <span className={`${item.sector_change_pct >= 0 ? "text-status-danger" : "text-status-success"}`}>
                            {item.sector_change_pct > 0 ? "+" : ""}{item.sector_change_pct.toFixed(1)}%
                          </span>
                        )}
                      </span>
                    )}
                  </div>
                  <div className="flex flex-col items-end shrink-0">
                    {/* Change % badge */}
                    <span className={`text-[13px] font-bold font-display-numeric ${isUp ? "text-status-danger" : "text-status-success"}`}>
                      {changePct > 0 ? "+" : ""}{changePct.toFixed(2)}%
                    </span>
                    {/* Price below change % */}
                    {(() => {
                      const pl = getPriceLabel();
                      const mainPrice = item.live_price || item.buy_price || 0;
                      return (
                        <>
                          <div className="text-[18px] font-bold font-display-numeric text-text-primary leading-tight mt-0.5">
                            ¥{mainPrice > 0 ? mainPrice.toFixed(2) : "—"}
                          </div>
                          <div className="text-[10px] text-text-disabled">{pl.label} ¥{mainPrice > 0 ? mainPrice.toFixed(2) : "—"}</div>
                          {item.buy_price > 0 && (
                            <div className="text-[9px] text-text-disabled mt-0.5">推荐价 ¥{item.buy_price.toFixed(2)}</div>
                          )}
                        </>
                      );
                    })()}
                  </div>
                </div>

                {/* Row 2: Score bar + Price + Signal tags */}
                <div className="flex items-end justify-between gap-4">
                  {/* Left: Score bar + signal tags */}
                  <div className="flex-1 min-w-0">
                    {/* Score bar */}
                    <div className="flex items-center gap-2 mb-2">
                      <div className="flex-1 h-1.5 rounded-full bg-surface-container-high overflow-hidden">
                        <div className="h-full rounded-full bg-gradient-to-r from-primary/60 to-primary" style={{ width: `${displayScore(item.score)}%` }} />
                      </div>
                      <span className={`font-display-numeric text-[15px] font-bold ${scoreColor(item.score)}`}>
                        {displayScore(item.score)}
                      </span>
                      {item.score_label && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-primary/10 text-primary border border-primary/20">{item.score_label}</span>
                      )}
                    </div>
                    {/* Signal tags */}
                    <div className="flex flex-wrap items-center gap-1.5">
                      {item.money_phase_label && (
                        <span className="inline-flex items-center gap-1 rounded-full bg-status-warning/12 px-2 py-0.5 text-[10px] font-medium text-status-warning border border-status-warning/20">
                          {item.money_phase_label}
                        </span>
                      )}
                      {item.active_buy_ratio != null && (
                        <span className="inline-flex items-center gap-1 rounded-full bg-status-success/12 px-2 py-0.5 text-[10px] font-medium text-status-success border border-status-success/20">
                          {(item.active_buy_ratio * 100).toFixed(0)}% 主动买入
                        </span>
                      )}
                      {/* Multi-source signal badges */}
                      {item._signals?.includes("ths_hot") && (
                        <span className="inline-flex items-center gap-0.5 rounded-full bg-status-info/15 px-1.5 py-0.5 text-[9px] font-medium text-status-info border border-status-info/25">热点</span>
                      )}
                      {item._signals?.includes("margin_up") && (
                        <span className="inline-flex items-center gap-0.5 rounded-full bg-status-success/15 px-1.5 py-0.5 text-[9px] font-medium text-status-success border border-status-success/25">融资</span>
                      )}
                    </div>
                  </div>

                  {/* Right: Actions only */}
                  <div className="flex flex-col items-end justify-end gap-2 shrink-0">
                    <div className="flex items-center gap-1.5">
                      <button
                        onClick={() => handleToggleWatchlist(item)}
                        disabled={isWlLoading}
                        className={`rounded-lg px-2.5 py-1.5 text-[11px] font-medium transition-colors disabled:opacity-50 ${
                          isFav
                            ? "bg-status-warning/15 text-status-warning hover:bg-status-warning/25"
                            : "border border-border-subtle bg-surface-card text-text-disabled hover:border-status-warning hover:text-status-warning"
                        }`}>
                        {isWlLoading ? "..." : isFav ? "已收藏" : "收藏"}
                      </button>
                      <Link href={`/cn/stock?symbol=${item.symbol}`} className="rounded-lg bg-surface-container-high px-2.5 py-1.5 text-[11px] font-medium text-text-secondary hover:text-text-primary transition-colors">
                        详情
                      </Link>
                    </div>
                  </div>
                </div>
              </div>
            )})}
          </div>
        )}
      </section>

      {catData && (
        <section className="mb-6">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <div className="flex items-center gap-2 mb-1">
                <div className="w-1 h-6 rounded-full bg-status-warning"></div>
                <h2 className="text-[18px] font-semibold text-text-primary">资金阶段分类</h2>
              </div>
              <p className="mt-0.5 text-[12px] text-text-disabled">
                4 大板块 · 凌晨 5:00 选股 · 含隔夜美股影响
              </p>
            </div>
          </div>
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
                  onToggleWatchlist={handleToggleWatchlist} sectorChanges={sectorChanges} />
              ))}
            </div>
          )}
        </section>
      )}

      {(() => {
        const activeWl = wlData.filter((w) => w.status === "active");
        const histWl = wlData.filter((w) => w.status !== "active");
        // 与收藏页一致：优先展示追踪中，不足再用历史补齐预览
        const wlPreview = [...activeWl, ...histWl].slice(0, 8);
        if (wlPreview.length === 0) return null;
        return (
        <section className="rounded-2xl border border-border-subtle bg-surface-card shadow-sm p-4 sm:p-6 mb-4 sm:mb-6">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <div className="flex items-center gap-2 mb-1">
                <div className="w-1 h-6 rounded-full bg-status-warning"></div>
                <h2 className="text-[18px] font-semibold text-text-primary">收藏追踪</h2>
              </div>
              <p className="text-[12px] text-text-disabled">
                与收藏页同源 · 追踪中 {activeWl.length} · 历史 {histWl.length} · T+1/T+2/T+3 自动更新
              </p>
            </div>
            <Link href="/cn/watchlist" className="text-[12px] text-status-info hover:underline shrink-0">查看全部 →</Link>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {wlPreview.map((w) => {
              const day1 = w.day1_change;
              const day2 = w.day2_change;
              const day3 = w.day3_change;
              const latestChg = day3 ?? day2 ?? day1;
              const isPositive = latestChg != null ? latestChg >= 0 : null;
              return (
              <div key={w.id} className="bg-surface-card rounded-xl p-3 border border-border-subtle/50 card-lift">
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
                  <span className={`ml-auto text-[10px] px-2 py-0.5 rounded-full ${w.status === "active" ? "bg-status-success/15 text-status-success" : "bg-text-secondary/15 text-text-secondary"}`}>
                    {w.status === "active" ? "追踪中" : "历史"}
                  </span>
                </div>
              </div>
            )})}
          </div>
        </section>
        );
      })()}

      <section className="rounded-2xl border border-border-subtle bg-surface-card shadow-sm p-3 sm:p-4 lg:p-6 mb-4 sm:mb-6">
        <div className="flex items-start gap-3 mb-3">
          <div className="w-1 h-12 rounded-full bg-primary shrink-0 mt-1"></div>
          <div className="flex-1">
            <div className="flex items-center gap-2 mb-1">
              <h2 className="text-[17px] font-semibold text-text-primary">尾盘狙击</h2>
              <span className="text-[10px] px-2 py-0.5 rounded-full bg-primary/12 text-primary border border-primary/30">14:45</span>
              <span className="text-[10px] px-2 py-0.5 rounded-full bg-status-warning/12 text-status-warning border border-status-warning/30">一夜持股</span>
              <span className="text-[10px] px-2 py-0.5 rounded-full bg-purple-light text-purple-primary border border-purple-primary/25">S2 规则引擎</span>
            </div>
            <p className="text-[11px] text-text-disabled">
              S2最优版 8步法 · 涨幅1~7% · 均线多头 · 量比&gt;1.5 · 收盘近最高 · 波动率排序 Top1 · +筹码峰加分
            </p>
          </div>
        </div>

        {s2Data && s2Data.picks && s2Data.picks.length > 0 ? (
          <div className="space-y-2">
            {s2Data.picks.slice(0, 3).map((s: any, i: number) => {
              const sym = s.symbol ? s.symbol.replace(/^(sh|sz)/, "") : "";
              const chg = s.change_pct || 0;
              const chgColor = chg >= 0 ? "text-status-danger" : "text-status-success";
              return (
                <div key={s.symbol || i} className="rounded-lg bg-surface-container-low p-2.5 hover:bg-surface-card transition-colors">
                  <div className="grid grid-cols-[16px_1fr_55px_55px] sm:grid-cols-[20px_1fr_80px_80px_70px] items-center gap-1">
                    <span className="text-[13px] font-bold text-status-info">{i + 1}</span>
                    <div className="flex items-center gap-1.5 min-w-0">
                      <Link href={s.symbol ? `/cn/stock?symbol=${s.symbol}` : "#"} className="text-[14px] font-medium text-text-primary hover:text-status-info truncate">{s.name || "?"}</Link>
                      <span className="text-[10px] text-text-disabled shrink-0">{sym}</span>
                    </div>
                    <span className="text-[13px] font-display-numeric text-text-primary text-right">
                      ¥{(s.price || 0).toFixed(2)}
                    </span>
                    <span className={`text-[13px] font-display-numeric font-medium text-right ${chgColor}`}>
                      {chg > 0 ? "+" : ""}{chg.toFixed(1)}%
                    </span>
                    <span className="hidden sm:block text-[11px] text-right font-medium text-text-secondary">
                      量比 {s.volume_ratio ? s.volume_ratio.toFixed(1) : "?"}
                    </span>
                  </div>
                  <div className="mt-1 flex items-center gap-2 text-[11px] text-text-disabled">
                    <span className="text-text-secondary">波动率 {s.volatility_20d ? (s.volatility_20d * 100).toFixed(2) : "?"}%</span>
                    {s.chip_bonus && s.chip_bonus > 0 && (
                      <>
                        <span className="text-text-disabled">·</span>
                        <span className="text-status-success">筹码加分 +{s.chip_bonus.toFixed(1)}</span>
                      </>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <div className="flex items-center gap-2 rounded-lg bg-surface-container-low px-3 py-2 border border-border-subtle">
            <p className="text-[12px] text-text-disabled">
              {s2Data ? "今日无符合 S2最优版 条件的标的" : "14:45 自动生成 · S2规则引擎尾盘狙击"}
            </p>
          </div>
        )}
      </section>

      <section className="mb-6">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-1 h-6 rounded-full bg-status-success"></div>
          <h2 className="text-[18px] font-semibold text-text-primary">自我进化学习</h2>
          <span className="text-[10px] px-2 py-0.5 rounded-full bg-status-success/12 text-status-success border border-[rgba(62,230,168,0.25)]">AI 驱动</span>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 sm:gap-3">
          <div className="rounded-2xl border border-border-subtle bg-surface-card p-4 card-lift shadow-sm border-t-2 border-t-purple-primary">
            <h3 className="text-[14px] font-semibold text-text-primary mb-1">自动历史回撤</h3>
            <p className="text-[11px] text-text-disabled leading-relaxed">
              每日 Top 5 推荐自动记录，T+1/T+3 涨跌幅自动追踪，生成完整回测数据库
            </p>
          </div>
          <div className="rounded-2xl border border-border-subtle bg-surface-card p-4 card-lift shadow-sm border-t-2 border-t-status-success">
            <h3 className="text-[14px] font-semibold text-text-primary mb-1">胜率自动统计</h3>
            <p className="text-[11px] text-text-disabled leading-relaxed">
              收藏夹自动计算胜率/平均收益，数据驱动而非感觉驱动
            </p>
          </div>
          <div className="rounded-2xl border border-border-subtle bg-surface-card p-4 card-lift shadow-sm border-t-2 border-t-status-warning">
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

function KPI({ label, value, sub, accent }: { label: string; value: string; sub: string; accent: string }) {
  const isBest = label === "今日最佳";
  return (
    <div
      className={`card-lift rounded-2xl border bg-surface-card p-4 shadow-sm ${
        isBest ? "border-status-success/30" : "border-border-subtle"
      }`}
    >
      <div className="mb-2 flex items-center justify-between">
        <span className="text-[10px] uppercase tracking-wider text-text-tertiary">{label}</span>
        <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: accent }} />
      </div>
      <div className="font-display-numeric text-[20px] sm:text-[26px] truncate" style={{ color: accent }}>
        {value}
      </div>
      <div className="mt-1 text-[11px] text-text-secondary">{sub}</div>
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
    <div className="rounded-2xl border border-border-subtle bg-surface-card shadow-sm p-4 card-lift flex flex-col transition-all min-h-[320px]"
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
                    const price = s.price || s.buy_price || 0;
                    const chg = s.change_pct;
                    const chgStr = chg != null ? `${chg > 0 ? "+" : ""}${chg.toFixed(1)}%` : "—";
                    const chgColor = chg != null ? (chg >= 0 ? "text-status-danger" : "text-status-success") : "text-text-disabled";
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
                        <span className="text-[10px] font-display-numeric text-text-secondary w-[52px] text-right shrink-0">
                          ¥{(s.live_price || s.price || s.buy_price || 0).toFixed(2)}
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

  return (
    <div className="mb-4 flex flex-wrap items-center gap-2 rounded-xl border border-border-subtle/50 bg-surface-card/60 backdrop-blur-sm px-3 py-2">
      <div className="flex flex-wrap items-center gap-2 text-[10px] text-text-secondary">
        {dataStatus ? (
          <>
            <span className="flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-status-success" />
              筹码: {dataStatus.chip_data?.updated_at || "无"}
            </span>
            <span className="text-text-disabled">|</span>
            <span className="flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-status-info" />
              资金流: {dataStatus.fund_flow?.updated_at || "无"}
            </span>
            <span className="text-text-disabled">|</span>
            <span className="flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-status-warning" />
              推荐: {dataStatus.daily_recommend?.updated_at || "无"}
            </span>
          </>
        ) : (
          <span className="text-text-disabled">加载数据状态...</span>
        )}
        {refreshStatus && refreshStatus.step !== "idle" && (
          <span className="text-status-info ml-1">
            {stepLabels[refreshStatus.step]}: {refreshStatus.progress}%
          </span>
        )}
      </div>
      <button
        onClick={handleRefresh}
        disabled={refreshing}
        className="ml-auto rounded-lg px-3 py-1 text-[11px] font-medium transition-all
          bg-status-info/10 text-status-info border border-status-info/20 hover:bg-status-info/20
          disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1 whitespace-nowrap"
      >
        <svg className={`w-3.5 h-3.5 ${refreshing ? "animate-spin" : ""}`}
          viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <polyline points="23 4 23 10 17 10" /><polyline points="1 20 1 14 7 14" />
          <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
        </svg>
        {refreshing ? "刷新中..." : "刷新盘后数据"}
      </button>
    </div>
  );
}

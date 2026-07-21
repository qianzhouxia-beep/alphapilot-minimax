// AlphaPilot 收藏追踪页面 — V2 历史记录版
// 永久保存模型选股战绩，自动追踪 T+1/T+2/T+3
"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { HeaderBar } from "@/components/HeaderBar";
import { useAuth } from "@/lib/auth";
import {
  fetchWatchlist, removeFromWatchlist, updateWatchlistEntry, addToWatchlist,
  type WatchlistItem,
} from "@/lib/cn-api";

/** 按 T+3 收盘盈亏%打标（历史记录唯一结算口径） */
function resultLabel(profitPct: number | null): { text: string; color: string; bg: string } {
  if (profitPct == null) {
    return { text: "待定", color: "var(--color-text-tertiary)", bg: "rgba(0,0,0,0.06)" };
  }
  if (profitPct > 0) {
    return { text: "盈利", color: "var(--color-red-negative)", bg: "rgba(255,59,48,0.10)" };
  }
  if (profitPct < 0) {
    return { text: "亏损", color: "var(--color-green-positive)", bg: "rgba(52,199,89,0.12)" };
  }
  return { text: "持平", color: "var(--color-text-tertiary)", bg: "rgba(0,0,0,0.06)" };
}

/**
 * 历史结算：严格 T+3 收盘。
 * 有 day3_change 则 % 以其为准；价优先 day3_price，否则由入场价反推。
 * 无 T+3 则未结算（不回退实时价 / T+1 / T+2）。
 */
function settleAtT3(w: WatchlistItem): {
  settled: boolean;
  price: number | null;
  pct: number | null;
  date: string | null;
} {
  const entry = Number(w.entry_price) || 0;
  if (w.day3_change == null && w.day3_price == null) {
    return { settled: false, price: null, pct: null, date: w.day3_date ?? null };
  }
  let pct: number | null = w.day3_change != null ? Number(w.day3_change) : null;
  let price: number | null = w.day3_price != null ? Number(w.day3_price) : null;
  if (pct == null && price != null && entry > 0) {
    pct = ((price - entry) / entry) * 100;
  }
  if (price == null && pct != null && entry > 0) {
    price = entry * (1 + pct / 100);
  }
  if (pct == null || price == null || entry <= 0) {
    return { settled: false, price: null, pct: null, date: w.day3_date ?? null };
  }
  return {
    settled: true,
    price: Math.round(price * 100) / 100,
    pct: Math.round(pct * 100) / 100,
    date: w.day3_date ?? null,
  };
}

export default function WatchlistPage() {
  const { session, ready, openAuth } = useAuth();
  const [items, setItems] = useState<WatchlistItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [removing, setRemoving] = useState<string | null>(null);
  // 价格弹窗
  const [priceDialog, setPriceDialog] = useState<{ symbol: string; name: string; value: string } | null>(null);
  const [priceLoading, setPriceLoading] = useState(false);
  const [editLoading, setEditLoading] = useState(false);
  const [retracking, setRetracking] = useState<string | null>(null);

  const load = async (refresh = true) => {
    try {
      const wl = await fetchWatchlist(refresh);
      setItems(wl.watchlist || []);
      setError(null);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      if (/\b401\b|未登录/.test(msg)) {
        openAuth("login", "/cn/watchlist");
        return;
      }
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!ready) return;
    if (!session) {
      openAuth("login", "/cn/watchlist");
      return;
    }
    load(true);
    const id = setInterval(() => load(false), 60_000);
    return () => clearInterval(id);
  }, [ready, session, openAuth]);

  const handleRemove = async (symbol: string) => {
    setRemoving(symbol);
    try {
      await removeFromWatchlist(symbol);
      setItems(prev => prev.filter(i => i.symbol !== symbol));
    } catch {}
    setRemoving(null);
  };

  const handleEditPrice = async () => {
    if (!priceDialog) return;
    const price = parseFloat(priceDialog.value);
    if (isNaN(price) || price <= 0) return;
    setPriceLoading(true);
    try {
      await updateWatchlistEntry(priceDialog.symbol, { entry_price: price });
      setItems(prev => prev.map(i => i.symbol === priceDialog!.symbol ? { ...i, entry_price: price } : i));
      setPriceDialog(null);
    } catch {}
    setPriceLoading(false);
  };

  const handleRetrack = async (w: WatchlistItem) => {
    setRetracking(w.symbol);
    // 用当前实时价重新追踪
    const price = w.current_price || w.day3_price || w.day2_price || w.day1_price || w.entry_price;
    try {
      await removeFromWatchlist(w.symbol);
      await addToWatchlist(w.symbol, w.name, price, w.model_score);
      await load(); // 刷新
    } catch (e: any) {
      console.error("retrack failed", e);
    }
    setRetracking(null);
  };

  const activeItems = items.filter(i => i.status === "active");
  const completedItems = items.filter(i => i.status === "completed");
  // 真正的 T+1：day1_date 与 added_at 不是同一天，且是交易日
  const isTradingDay = (s: string) => {
    const d = new Date(s.substring(0, 10));
    const day = d.getDay();
    return day !== 0 && day !== 6;
  };
  const trackedItems = items.filter(i => {
    if ((i.day1_change ?? null) === null) return false;
    const addDate = (i.added_at || "").substring(0, 10);
    const d1Date = (i.day1_date || "").substring(0, 10);
    return d1Date !== addDate && isTradingDay(d1Date);
  });

  // Stats
  const totalCompleted = completedItems.length;
  const totalTracked = trackedItems.length;
  const hitCount = trackedItems.filter(i => (i.day1_change ?? 0) >= 3).length;
  const winRate = totalTracked > 0 ? ((hitCount / totalTracked) * 100) : 0;
  const avgReturn = totalTracked > 0
    ? trackedItems.reduce((sum, i) => sum + (i.day1_change ?? 0), 0) / totalTracked
    : 0;
  const d2Items = trackedItems.filter(i => i.day2_change != null);
  const hit2Count = d2Items.filter(i => (i.day2_change ?? 0) >= 3).length;
  const winRate2 = d2Items.length > 0 ? ((hit2Count / d2Items.length) * 100) : 0;
  const avgReturn2 = d2Items.length > 0
    ? d2Items.reduce((sum, i) => sum + (i.day2_change ?? 0), 0) / d2Items.length
    : 0;
  const d3Items = trackedItems.filter(i => i.day3_change != null);
  const hit3Count = d3Items.filter(i => (i.day3_change ?? 0) >= 3).length;
  const winRate3 = d3Items.length > 0 ? ((hit3Count / d3Items.length) * 100) : 0;
  const avgReturn3 = d3Items.length > 0
    ? d3Items.reduce((sum, i) => sum + (i.day3_change ?? 0), 0) / d3Items.length
    : 0;

  return (
    <>
    <main className="mx-auto max-w-[1200px] px-4 sm:px-6 lg:px-8 py-4 sm:py-6 lg:py-8 min-h-screen">
      <HeaderBar market="cn" />

      {error && !/401|未登录/.test(error) && (
        <div className="glass mb-6 rounded-2xl border border-status-danger p-4 text-[13px] text-status-danger">
          {error}
        </div>
      )}
      {error && /401|未登录/.test(error) && (
        <div className="glass mb-6 rounded-2xl border border-status-warning p-4">
          <p className="text-[13px] text-status-warning font-semibold">请先登录后查看个人收藏</p>
          <button
            type="button"
            onClick={() => openAuth("login", "/cn/watchlist")}
            className="mt-3 inline-block rounded-lg bg-status-info px-4 py-2 text-[12px] font-semibold text-white"
          >
            去登录
          </button>
        </div>
      )}

      <section className="mb-8">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h1 className="text-[28px] font-semibold">收藏追踪</h1>
            <p className="mt-2 text-[13px] text-text-secondary">
              自动追踪 T+1/T+2/T+3 · 历史盈亏一律按 T+3 收盘结算
            </p>
          </div>
          <Link href="/cn" className="rounded-lg border border-border-subtle bg-surface-panel px-4 py-2 text-[13px] text-text-secondary hover:border-status-info hover:text-text-primary">
            ← 返回工作台
          </Link>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-3 sm:grid-cols-6 gap-3 mb-8">
          <StatCard label="追踪中" value={activeItems.length} accent="#3EE6A8" />
          <StatCard label="历史记录" value={totalCompleted} accent="#A78BFA" />
          <StatCard label="T+1" value={totalTracked > 0 ? "胜率 " + winRate.toFixed(0) + "%" : "—"} sub={totalTracked > 0 ? "均收益 " + (avgReturn > 0 ? "+" : "") + avgReturn.toFixed(2) + "%" : ""} accent="#F5C451" />
          <StatCard label="T+2" value={totalTracked > 0 ? "胜率 " + winRate2.toFixed(0) + "%" : "—"} sub={totalTracked > 0 ? "均收益 " + (avgReturn2 > 0 ? "+" : "") + avgReturn2.toFixed(2) + "%" : ""} accent="#A78BFA" />
          <StatCard label="T+3" value={totalTracked > 0 ? "胜率 " + winRate3.toFixed(0) + "%" : "—"} sub={totalTracked > 0 ? "均收益 " + (avgReturn3 > 0 ? "+" : "") + avgReturn3.toFixed(2) + "%" : ""} accent="#9FB0C7" />
          <StatCard label="总收录" value={items.length} accent="#9FB0C7" />
        </div>

        {loading && (
          <div className="flex flex-col items-center justify-center py-20">
            <div className="h-12 w-12 animate-spin rounded-full border-4 border-border-subtle border-t-status-info"></div>
            <p className="mt-4 text-[14px] text-text-secondary">加载中...</p>
          </div>
        )}

        {!loading && items.length === 0 && (
          <div className="glass rounded-2xl p-12 text-center">
            <p className="text-lg font-semibold text-text-disabled">暂无收藏股票</p>
            <p className="mt-4 text-[16px] text-text-primary">还没有收藏任何股票</p>
            <p className="mt-2 text-[13px] text-text-secondary">
              在工作台点击收藏按钮添加，系统会自动追踪后续涨跌
            </p>
            <Link href="/cn" className="mt-6 inline-block rounded-lg bg-status-info px-6 py-2.5 text-[13px] font-semibold text-on-primary hover:bg-status-info/70">
              去选股
            </Link>
          </div>
        )}

        {/* 追踪中 section */}
        {activeItems.length > 0 && (
          <div className="glass card-lift rounded-2xl p-4 sm:p-6 mb-6">
            <h2 className="section-header mb-4 flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-status-success"></span>
              追踪中 ({activeItems.length})
            </h2>
            <WatchlistTable items={activeItems} onRemove={handleRemove} removing={removing}
              onRetrack={null} retracking={null}
              onPriceClick={(w) => setPriceDialog({ symbol: w.symbol, name: w.name, value: (w.entry_price || 0).toFixed(2) })} />
          </div>
        )}

        {/* 历史记录 section */}
        {completedItems.length > 0 && (
          <div className="glass rounded-2xl p-4 sm:p-6">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="section-header flex items-center gap-2">
                <span className="h-2 w-2 rounded-full bg-text-secondary"></span>
                历史记录 ({completedItems.length})
              </h2>
              <span className="text-[11px] text-text-disabled">按周归类 · T+3收盘结算盈亏</span>
            </div>
            <HistoryTable items={completedItems} onRemove={handleRemove} removing={removing}
              onRetrack={handleRetrack} retracking={retracking}
              onPriceClick={(w) => setPriceDialog({ symbol: w.symbol, name: w.name, value: (w.entry_price || 0).toFixed(2) })} />
          </div>
        )}
      </section>
    </main>

      {/* ═══ 价格修改弹窗 ═══ */}
      {priceDialog && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-bg-primary/50 backdrop-blur-sm"
          onClick={() => !priceLoading && setPriceDialog(null)}>
          <div className="w-[90vw] max-w-[360px] rounded-2xl border border-border-subtle bg-surface-panel p-6 shadow-2xl mx-4"
            onClick={e => e.stopPropagation()}>
            <h3 className="text-[18px] font-semibold text-text-primary mb-1">修改入场价</h3>
            <p className="text-[13px] text-text-secondary mb-4">{priceDialog.name} · {priceDialog.symbol}</p>
            <label className="block mb-1 text-[12px] text-text-disabled">买入价格（¥）</label>
            <input type="number" step="0.01" min="0.01"
              value={priceDialog.value}
              onChange={e => setPriceDialog(prev => prev ? { ...prev, value: e.target.value } : null)}
              className="w-full rounded-lg border border-border-subtle bg-background px-3 py-2.5 text-[16px] text-text-primary font-mono outline-none focus:border-status-info transition-colors"
              placeholder="输入买入价"
              autoFocus
              disabled={priceLoading} />
            <div className="mt-4 flex gap-2">
              <button onClick={handleEditPrice} disabled={priceLoading}
                className="flex-1 rounded-lg bg-status-info px-4 py-2.5 text-[14px] font-semibold text-on-primary hover:bg-status-info/70 disabled:opacity-50 transition-colors">
                {priceLoading ? "保存中..." : "确认修改"}
              </button>
              <button onClick={() => setPriceDialog(null)} disabled={priceLoading}
                className="flex-1 rounded-lg border border-border-subtle px-4 py-2.5 text-[14px] text-text-secondary hover:border-status-info hover:text-text-primary disabled:opacity-50 transition-colors">
                取消
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

// ═══ 追踪中表格（CSS Grid 替代 table，完全避免对齐问题）═══

function WatchlistTable({ items, onRemove, removing, onRetrack, retracking, onPriceClick }: {
  items: WatchlistItem[];
  onRemove: (symbol: string) => void;
  removing: string | null;
  onRetrack: ((w: WatchlistItem) => void) | null;
  retracking: string | null;
  onPriceClick?: (w: WatchlistItem) => void;
}) {
  return (
    <div className="overflow-x-auto -mx-4 sm:mx-0">
      {/* Header */}
      <div className="grid grid-cols-[10fr_6fr_5fr_5fr_4fr_4fr_4fr_4fr_4fr_4fr] gap-0 text-[11px] uppercase tracking-wider text-text-disabled border-b border-border-subtle">
        <div className="px-2 py-2.5 font-medium text-left">股票</div>
        <div className="px-2 py-2.5 font-medium text-left whitespace-nowrap">添加时间</div>
        <div className="px-2 py-2.5 font-medium text-right whitespace-nowrap">入场</div>
        <div className="px-2 py-2.5 font-medium text-right whitespace-nowrap">实时</div>
        <div className="px-2 py-2.5 font-medium text-right whitespace-nowrap">浮动</div>
        <div className="px-2 py-2.5 font-medium text-right whitespace-nowrap">评分</div>
        <div className="px-2 py-2.5 font-medium text-right whitespace-nowrap">T+1</div>
        <div className="px-2 py-2.5 font-medium text-right whitespace-nowrap">T+2</div>
        <div className="px-2 py-2.5 font-medium text-right whitespace-nowrap">T+3</div>
        <div className="px-2 py-2.5 font-medium text-center">操作</div>
      </div>
      {/* Data rows */}
      {items.map((w) => {
        const isRemoving = removing === w.symbol;
        const chg = w.current_change_pct;
        const fmtTime = (t?: string) => {
          if (!t) return "—";
          const d = new Date(t);
          return String(d.getMonth()+1).padStart(2,"0") + "/" + String(d.getDate()).padStart(2,"0") + " " + String(d.getHours()).padStart(2,"0") + ":" + String(d.getMinutes()).padStart(2,"0");
        };
        return (
        <div key={w.id} className="grid grid-cols-[10fr_6fr_5fr_5fr_4fr_4fr_4fr_4fr_4fr_4fr] gap-0 text-[13px] border-b border-border-subtle/30 hover:bg-primary/4 transition-colors">
          <div className="px-2 py-3 flex items-center gap-2">
            <div>
              <div className="text-[14px] font-semibold text-text-primary">{w.name}</div>
              <div className="text-[10px] text-text-disabled font-mono">{w.symbol}</div>
            </div>
          </div>
          <div className="px-2 py-3 text-[11px] text-text-disabled whitespace-nowrap">{fmtTime(w.added_at)}</div>
          <div className="px-2 py-3 text-right font-mono whitespace-nowrap">
            <span className="text-status-warning cursor-pointer hover:text-status-warning/80 transition-colors" onClick={() => onPriceClick?.(w)}>
              ¥{(w.entry_price || 0).toFixed(2)}
            </span>
          </div>
          <div className={"px-2 py-3 text-right font-mono whitespace-nowrap " + (w.current_price != null ? "text-text-primary" : "text-text-disabled")}>
            {w.current_price != null ? "¥" + w.current_price.toFixed(2) : "—"}
          </div>
          <div className={"px-2 py-3 text-right font-mono font-semibold whitespace-nowrap " + (chg != null ? (chg >= 0 ? "text-status-danger" : "text-status-success") : "text-text-disabled")}>
            {chg != null ? (chg > 0 ? "+" : "") + chg + "%" : "—"}
          </div>
          <div className="px-2 py-3 text-right font-mono text-text-secondary whitespace-nowrap">{(w.model_score * 100).toFixed(0)}%</div>
          <div className={"px-2 py-3 text-right font-mono whitespace-nowrap " + (w.day1_change != null ? (w.day1_change >= 0 ? "text-status-danger" : "text-status-success") : "text-text-disabled")}>
            {w.day1_change != null ? (w.day1_change > 0 ? "+" : "") + w.day1_change + "%" : "—"}
          </div>
          <div className={"px-2 py-3 text-right font-mono whitespace-nowrap " + (w.day2_change != null ? (w.day2_change >= 0 ? "text-status-danger" : "text-status-success") : "text-text-disabled")}>
            {w.day2_change != null ? (w.day2_change > 0 ? "+" : "") + w.day2_change + "%" : "—"}
          </div>
          <div className={"px-2 py-3 text-right font-mono whitespace-nowrap " + (w.day3_change != null ? (w.day3_change >= 0 ? "text-status-danger" : "text-status-success") : "text-text-disabled")}>
            {w.day3_change != null ? (w.day3_change > 0 ? "+" : "") + w.day3_change + "%" : "—"}
          </div>
          <div className="px-2 py-3 text-center">
            <button onClick={() => onRemove(w.symbol)} disabled={isRemoving}
              className="rounded-lg px-2.5 py-1.5 text-[11px] text-status-danger hover:bg-status-danger/10 disabled:opacity-50 transition-colors">
              {isRemoving ? "..." : "删除"}
            </button>
          </div>
        </div>
      )})}
    </div>
  );
}

// ═══ 历史记录表格（按周归类，每条 completed 单独一行，不按股票去重）═══
const DEFAULT_QTY = 100; // 默认买入数量（股）

function loadQtyMap(): Record<string, number> {
  if (typeof window === "undefined") return {};
  try {
    const raw = localStorage.getItem("watchlist_qty_map");
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
}
function saveQtyMap(map: Record<string, number>) {
  if (typeof window === "undefined") return;
  localStorage.setItem("watchlist_qty_map", JSON.stringify(map));
}

function pad2(n: number) {
  return String(n).padStart(2, "0");
}

function fmtMd(d: Date) {
  return `${pad2(d.getMonth() + 1)}/${pad2(d.getDate())}`;
}

/** 自然周（周一～周日），key=该周周一 YYYY-MM-DD */
function weekMeta(iso?: string): { key: string; label: string; sortKey: string } {
  const d = iso ? new Date(iso) : new Date();
  const day = d.getDay(); // 0=Sun
  const mondayOffset = day === 0 ? -6 : 1 - day;
  const monday = new Date(d);
  monday.setHours(0, 0, 0, 0);
  monday.setDate(d.getDate() + mondayOffset);
  const sunday = new Date(monday);
  sunday.setDate(monday.getDate() + 6);
  const y = monday.getFullYear();
  // ISO 周序号（相对该年 1 月 4 日所在周）
  const jan4 = new Date(y, 0, 4);
  const jan4Day = jan4.getDay() || 7;
  const week1Mon = new Date(jan4);
  week1Mon.setDate(jan4.getDate() - (jan4Day - 1));
  const weekNo = Math.floor((monday.getTime() - week1Mon.getTime()) / (7 * 86400000)) + 1;
  const key = `${y}-${pad2(monday.getMonth() + 1)}-${pad2(monday.getDate())}`;
  return {
    key,
    sortKey: key,
    label: `${y} 第${weekNo}周 · ${fmtMd(monday)}–${fmtMd(sunday)}`,
  };
}

/** @deprecated 保留别名，历史一律走 settleAtT3 */
function historyExitPrice(w: WatchlistItem): number {
  return settleAtT3(w).price ?? 0;
}
function historyProfitPct(w: WatchlistItem): number | null {
  return settleAtT3(w).pct;
}

function HistoryTable({
  items,
  onRemove,
  removing,
  onRetrack,
  retracking,
  onPriceClick,
}: {
  items: WatchlistItem[];
  onRemove: (symbol: string) => void;
  removing: string | null;
  onRetrack: (w: WatchlistItem) => void;
  retracking: string | null;
  onPriceClick?: (w: WatchlistItem) => void;
}) {
  const [qtyMap, setQtyMap] = useState<Record<string, number>>({});
  const [editingQty, setEditingQty] = useState<string | null>(null);
  const [qtyInput, setQtyInput] = useState("");
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});

  useEffect(() => {
    setQtyMap(loadQtyMap());
  }, []);

  const getQty = (symbol: string) => qtyMap[symbol] ?? DEFAULT_QTY;
  const handleQtySave = (symbol: string) => {
    const q = parseInt(qtyInput, 10);
    if (!isNaN(q) && q > 0) {
      const next = { ...qtyMap, [symbol]: q };
      setQtyMap(next);
      saveQtyMap(next);
    }
    setEditingQty(null);
  };

  // 每条历史独立保留，按添加时间倒序，再按周归类
  const sorted = [...items].sort((a, b) =>
    String(b.added_at || "").localeCompare(String(a.added_at || ""))
  );
  const weekGroups: { key: string; label: string; rows: WatchlistItem[] }[] = [];
  const weekIndex = new Map<string, number>();
  for (const w of sorted) {
    const meta = weekMeta(w.added_at);
    let idx = weekIndex.get(meta.key);
    if (idx == null) {
      idx = weekGroups.length;
      weekIndex.set(meta.key, idx);
      weekGroups.push({ key: meta.key, label: meta.label, rows: [] });
    }
    weekGroups[idx].rows.push(w);
  }

  // 股票 | 买入 | T+3收盘 | T+1 | T+2 | T+3 | 数量 | 盈余 | 盈亏% | 结果 | 操作
  const gridCols = "grid-cols-[10fr_4fr_4fr_4fr_4fr_4fr_4fr_5fr_4fr_4fr_5fr]";

  const fmtDayChg = (v: number | null | undefined) => {
    if (v == null) return { text: "—", cls: "text-text-disabled" };
    return {
      text: `${v > 0 ? "+" : ""}${v}%`,
      cls: v >= 0 ? "text-status-danger" : "text-status-success",
    };
  };
  const fmtDayDate = (iso?: string | null) => {
    if (!iso) return "";
    const d = new Date(iso.substring(0, 10) + "T12:00:00");
    if (Number.isNaN(d.getTime())) return "";
    return fmtMd(d);
  };

  return (
    <div className="space-y-4 -mx-4 sm:mx-0">
      {weekGroups.map((group) => {
        const isCollapsed = !!collapsed[group.key];
        const settles = group.rows.map((w) => settleAtT3(w));
        const pcts = settles.filter((s) => s.settled && s.pct != null).map((s) => s.pct as number);
        const wins = pcts.filter((p) => p > 0).length;
        const avg = pcts.length ? pcts.reduce((a, b) => a + b, 0) / pcts.length : 0;

        return (
          <div key={group.key} className="rounded-xl border border-border-subtle/60 overflow-hidden">
            <button
              type="button"
              onClick={() =>
                setCollapsed((prev) => ({ ...prev, [group.key]: !prev[group.key] }))
              }
              className="w-full flex items-center justify-between gap-3 px-3 py-2.5 bg-surface-panel/60 hover:bg-surface-panel transition-colors text-left"
            >
              <div className="min-w-0">
                <div className="text-[13px] font-semibold text-text-primary">{group.label}</div>
                <div className="text-[11px] text-text-disabled mt-0.5">
                  {group.rows.length} 条 · T+3已结算 {pcts.length}/{group.rows.length}
                  {pcts.length > 0
                    ? ` · 盈利 ${wins}/${pcts.length} · 均盈亏 ${avg >= 0 ? "+" : ""}${avg.toFixed(2)}%`
                    : ""}
                </div>
              </div>
              <span className="text-[11px] text-text-disabled shrink-0">
                {isCollapsed ? "展开 ▾" : "收起 ▴"}
              </span>
            </button>

            {!isCollapsed && (
              <div className="overflow-x-auto">
                <div
                  className={
                    "grid " +
                    gridCols +
                    " gap-0 text-[11px] uppercase tracking-wider text-text-disabled border-b border-border-subtle min-w-[860px]"
                  }
                >
                  <div className="px-2 py-2.5 font-medium text-left">股票</div>
                  <div className="px-2 py-2.5 font-medium text-right whitespace-nowrap">买入价</div>
                  <div className="px-2 py-2.5 font-medium text-right whitespace-nowrap">T+3收盘</div>
                  <div className="px-2 py-2.5 font-medium text-right whitespace-nowrap">T+1</div>
                  <div className="px-2 py-2.5 font-medium text-right whitespace-nowrap">T+2</div>
                  <div className="px-2 py-2.5 font-medium text-right whitespace-nowrap">T+3</div>
                  <div className="px-2 py-2.5 font-medium text-right whitespace-nowrap">数量</div>
                  <div className="px-2 py-2.5 font-medium text-right whitespace-nowrap">盈余</div>
                  <div className="px-2 py-2.5 font-medium text-right whitespace-nowrap">盈亏%</div>
                  <div className="px-2 py-2.5 font-medium text-right whitespace-nowrap">结果</div>
                  <div className="px-2 py-2.5 font-medium text-center">操作</div>
                </div>

                {group.rows.map((w) => {
                  const entryPrice = w.entry_price || 0;
                  const settle = settleAtT3(w);
                  const qty = getQty(w.symbol);
                  const costTotal = entryPrice * qty;
                  // 盈余严格跟 T+3%：避免价四舍五入与%不一致
                  const profitPct = settle.pct;
                  const profitAmt =
                    settle.settled && profitPct != null
                      ? (costTotal * profitPct) / 100
                      : 0;
                  const exitPrice = settle.price;
                  const rowKey = String(w.id ?? `${w.symbol}-${w.added_at}`);
                  const isRemoving = removing === w.symbol;
                  const isRetracking = retracking === w.symbol;
                  const rl = resultLabel(settle.settled ? profitPct : null);
                  const isEditingQty = editingQty === rowKey;
                  const d1 = fmtDayChg(w.day1_change);
                  const d2 = fmtDayChg(w.day2_change);
                  const d3 = fmtDayChg(w.day3_change);

                  return (
                    <div
                      key={rowKey}
                      className={
                        "grid " +
                        gridCols +
                        " gap-0 text-[13px] border-b border-border-subtle/30 hover:bg-primary/4 transition-colors min-w-[860px]"
                      }
                    >
                      <div className="px-2 py-3 flex items-center gap-2">
                        <div>
                          <div className="text-[14px] font-semibold text-text-primary">
                            {w.name}
                          </div>
                          <div className="text-[10px] text-text-disabled font-mono">
                            {w.symbol}
                          </div>
                          <div className="text-[10px] text-text-disabled">
                            {w.added_at
                              ? (() => {
                                  const d = new Date(w.added_at);
                                  return `${fmtMd(d)} ${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
                                })()
                              : ""}
                          </div>
                        </div>
                      </div>
                      <div className="px-2 py-3 text-right font-mono text-status-warning">
                        <span
                          className="cursor-pointer hover:text-status-warning/80 transition-colors"
                          onClick={() => onPriceClick?.(w)}
                        >
                          ¥{entryPrice.toFixed(2)}
                        </span>
                      </div>
                      <div
                        className={
                          "px-2 py-3 text-right font-mono " +
                          (settle.settled ? "text-text-primary" : "text-text-disabled")
                        }
                      >
                        {settle.settled && exitPrice != null ? "¥" + exitPrice.toFixed(2) : "—"}
                      </div>
                      <div className={"px-2 py-3 text-right font-mono whitespace-nowrap " + d1.cls}>
                        <div>{d1.text}</div>
                        {w.day1_date ? (
                          <div className="text-[10px] text-text-disabled font-normal">{fmtDayDate(w.day1_date)}</div>
                        ) : null}
                      </div>
                      <div className={"px-2 py-3 text-right font-mono whitespace-nowrap " + d2.cls}>
                        <div>{d2.text}</div>
                        {w.day2_date ? (
                          <div className="text-[10px] text-text-disabled font-normal">{fmtDayDate(w.day2_date)}</div>
                        ) : null}
                      </div>
                      <div className={"px-2 py-3 text-right font-mono whitespace-nowrap " + d3.cls}>
                        <div>{d3.text}</div>
                        {w.day3_date ? (
                          <div className="text-[10px] text-text-disabled font-normal">{fmtDayDate(w.day3_date)}</div>
                        ) : null}
                      </div>
                      <div className="px-2 py-3 text-right font-mono whitespace-nowrap">
                        {isEditingQty ? (
                          <input
                            type="number"
                            min="1"
                            step="1"
                            value={qtyInput}
                            onChange={(e) => setQtyInput(e.target.value)}
                            onBlur={() => handleQtySave(w.symbol)}
                            onKeyDown={(e) => {
                              if (e.key === "Enter") handleQtySave(w.symbol);
                              if (e.key === "Escape") setEditingQty(null);
                            }}
                            className="w-[60px] rounded border border-border-subtle bg-background px-1 py-0.5 text-right text-[12px] font-mono outline-none focus:border-status-info"
                            autoFocus
                          />
                        ) : (
                          <span
                            className="cursor-pointer hover:text-status-info transition-colors"
                            onClick={() => {
                              setEditingQty(rowKey);
                              setQtyInput(String(qty));
                            }}
                          >
                            {qty.toLocaleString()}股
                          </span>
                        )}
                      </div>
                      <div
                        className={
                          "px-2 py-3 text-right font-mono font-semibold " +
                          (!settle.settled
                            ? "text-text-disabled"
                            : profitAmt >= 0
                              ? "text-status-danger"
                              : "text-status-success")
                        }
                      >
                        {settle.settled
                          ? `${profitAmt >= 0 ? "+" : ""}¥${profitAmt.toFixed(2)}`
                          : "—"}
                      </div>
                      <div
                        className={
                          "px-2 py-3 text-right font-mono font-semibold " +
                          (!settle.settled
                            ? "text-text-disabled"
                            : (profitPct ?? 0) >= 0
                              ? "text-status-danger"
                              : "text-status-success")
                        }
                      >
                        {settle.settled && profitPct != null
                          ? `${profitPct >= 0 ? "+" : ""}${profitPct.toFixed(2)}%`
                          : "—"}
                      </div>
                      <div className="px-2 py-3 text-right">
                        <span
                          className="text-[11px] px-2 py-0.5 rounded-full inline-block"
                          style={{ backgroundColor: rl.bg, color: rl.color }}
                        >
                          {rl.text}
                        </span>
                      </div>
                      <div className="px-2 py-3 text-center">
                        <div className="flex items-center justify-center gap-1.5">
                          <button
                            onClick={() => onRetrack(w)}
                            disabled={isRemoving || isRetracking}
                            className="rounded-lg px-2 py-1.5 text-[11px] text-primary hover:bg-primary/10 disabled:opacity-50 transition-colors"
                          >
                            {isRetracking ? "..." : "再追踪"}
                          </button>
                          <button
                            onClick={() => onRemove(w.symbol)}
                            disabled={isRemoving}
                            className="rounded-lg px-2 py-1.5 text-[11px] text-status-danger hover:bg-status-danger/10 disabled:opacity-50 transition-colors"
                          >
                            {isRemoving ? "..." : "删除"}
                          </button>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function StatCard({ label, value, sub, accent }: { label: string; value: string | number; sub?: string; accent: string }) {
  return (
    <div className="glass card-lift rounded-2xl p-4">
      <div className="mb-1 text-[10px] uppercase tracking-wider text-text-disabled">{label}</div>
      <div className="font-display-numeric text-[20px]" style={{ color: accent }}>
        {value}
      </div>
      {sub && <div className="mt-0.5 text-[11px] font-display-numeric" style={{ color: accent }}>{sub}</div>}
    </div>
  );
}

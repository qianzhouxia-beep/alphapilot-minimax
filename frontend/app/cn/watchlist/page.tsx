// AlphaPilot 收藏追踪页面 — V2 历史记录版
// 永久保存模型选股战绩，自动追踪 T+1/T+2/T+3
"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { HeaderBar } from "@/components/HeaderBar";
import {
  fetchWatchlist, removeFromWatchlist, updateWatchlistEntry, addToWatchlist,
  type WatchlistItem,
} from "@/lib/cn-api";

function resultLabel(chg: number | null): { text: string; color: string; bg: string } {
  if (chg == null) return { text: "待定", color: "#9FB0C7", bg: "rgba(159,176,199,0.15)" };
  if (chg >= 3) return { text: "达标🔥", color: "#FF5D5D", bg: "rgba(255,93,93,0.15)" };
  if (chg > 0) return { text: "微盈", color: "#FF8A8A", bg: "rgba(255,138,138,0.12)" };
  return { text: "亏损", color: "#3EE6A8", bg: "rgba(62,230,168,0.15)" };
}

function totalReturn(w: WatchlistItem): number | null {
  if (w.day3_change != null) return w.day3_change;
  if (w.day2_change != null) return w.day2_change;
  if (w.day1_change != null) return w.day1_change;
  return null;
}

export default function WatchlistPage() {
  const [items, setItems] = useState<WatchlistItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [removing, setRemoving] = useState<string | null>(null);
  // 价格弹窗
  const [priceDialog, setPriceDialog] = useState<{ symbol: string; name: string; value: string } | null>(null);
  const [priceLoading, setPriceLoading] = useState(false);
  const [editLoading, setEditLoading] = useState(false);
  const [retracking, setRetracking] = useState<string | null>(null);

  const load = async () => {
    try {
      const wl = await fetchWatchlist();
      setItems(wl.watchlist || []);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

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

      {error && (
        <div className="glass mb-6 rounded-2xl border border-status-danger p-4 text-[13px] text-status-danger">
          {error}
        </div>
      )}

      <section className="mb-8">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h1 className="text-[28px] font-semibold">⭐ 收藏追踪</h1>
            <p className="mt-2 text-[13px] text-text-secondary">
              自动追踪 T+1/T+2/T+3 涨跌 · 历史记录永久保存
            </p>
          </div>
          <Link href="/cn" className="rounded-lg border border-border-subtle bg-surface-panel px-4 py-2 text-[13px] text-text-secondary hover:border-status-info hover:text-text-primary">
            ← 返回 Dashboard
          </Link>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-3 sm:grid-cols-6 gap-3 mb-8">
          <StatCard label="追踪中" value={activeItems.length} accent="#3EE6A8" />
          <StatCard label="历史记录" value={totalCompleted} accent="#A78BFA" />
          <StatCard label="T+1" value={totalTracked > 0 ? `胜率 ${winRate.toFixed(0)}%` : "—"} sub={totalTracked > 0 ? `均收益 ${avgReturn > 0 ? "+" : ""}${avgReturn.toFixed(2)}%` : ""} accent="#F5C451" />
          <StatCard label="T+2" value={totalTracked > 0 ? `胜率 ${winRate2.toFixed(0)}%` : "—"} sub={totalTracked > 0 ? `均收益 ${avgReturn2 > 0 ? "+" : ""}${avgReturn2.toFixed(2)}%` : ""} accent="#A78BFA" />
          <StatCard label="T+3" value={totalTracked > 0 ? `胜率 ${winRate3.toFixed(0)}%` : "—"} sub={totalTracked > 0 ? `均收益 ${avgReturn3 > 0 ? "+" : ""}${avgReturn3.toFixed(2)}%` : ""} accent="#9FB0C7" />
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
            <p className="text-[48px]">⭐</p>
            <p className="mt-4 text-[16px] text-text-primary">还没有收藏任何股票</p>
            <p className="mt-2 text-[13px] text-text-secondary">
              在 Dashboard 点击 ☆ 按钮添加收藏，系统会自动追踪后续涨跌
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
              <span className="text-[11px] text-text-disabled">永久保存 · 模型选股战绩</span>
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
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/50 backdrop-blur-sm"
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

// ═══ 追踪中表格 ═══
const W_GRID = { gridTemplateColumns: 'minmax(130px,1.5fr) 72px 72px 72px 56px 78px 78px 78px 64px' };
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
      <div className="w-full min-w-[750px]">
        {/* Header */}
        <div className="grid text-[11px] uppercase tracking-wider text-text-disabled border-b border-border-subtle" style={W_GRID}>
          <div className="px-3 py-2.5 font-medium text-left">股票</div>
          <div className="px-3 py-2.5 font-medium text-right">入场</div>
          <div className="px-3 py-2.5 font-medium text-right">实时</div>
          <div className="px-3 py-2.5 font-medium text-right">浮动</div>
          <div className="px-3 py-2.5 font-medium text-right">评分</div>
          <div className="px-3 py-2.5 font-medium text-right">T+1</div>
          <div className="px-3 py-2.5 font-medium text-right">T+2</div>
          <div className="px-3 py-2.5 font-medium text-right">T+3</div>
          <div className="px-3 py-2.5 font-medium text-center">操作</div>
        </div>
        {/* Data rows */}
        {items.map((w) => {
          const isRemoving = removing === w.symbol;
          const d1Hit = (w.day1_change ?? 0) >= 3;
          const chg = w.current_change_pct;
          return (
          <div key={w.id} className="grid text-[13px] border-b border-border-subtle/30 hover:bg-primary/4 transition-colors" style={W_GRID}>
            <div className="px-3 py-2.5 overflow-hidden">
              <div className="text-[14px] font-semibold text-text-primary truncate">{w.name}</div>
              <div className="text-[10px] text-text-disabled truncate">{w.symbol}</div>
            </div>
            <div className="px-3 py-2.5 text-right font-mono">
              <span className="text-status-warning cursor-pointer hover:text-status-warning/80 transition-colors" onClick={() => onPriceClick?.(w)}>
                ¥{(w.entry_price || 0).toFixed(2)}
              </span>
            </div>
            <div className={`px-3 py-2.5 text-right font-mono truncate ${w.current_price != null ? "text-text-primary" : "text-text-disabled"}`}>
              {w.current_price != null ? `¥${w.current_price.toFixed(2)}` : "—"}
            </div>
            <div className={`px-3 py-2.5 text-right font-mono font-semibold truncate ${chg != null ? (chg > 0 ? "text-[#FF5D5D]" : chg < 0 ? "text-[#3EE6A8]" : "text-text-secondary") : "text-text-disabled"}`}>
              {chg != null ? `${chg > 0 ? "+" : ""}${chg}%` : "—"}
            </div>
            <div className="px-3 py-2.5 text-right font-mono text-text-secondary truncate">{(w.model_score * 100).toFixed(0)}%</div>
            <div className={`px-3 py-2.5 text-right font-mono font-semibold truncate ${w.day1_change != null ? (w.day1_change >= 3 ? "text-[#FF5D5D]" : w.day1_change > 0 ? "text-[#FF8A8A]" : w.day1_change < 0 ? "text-[#3EE6A8]" : "text-text-secondary") : "text-text-disabled"}`}>
              {w.day1_change != null ? `${w.day1_change > 0 ? "+" : ""}${w.day1_change}%${(w.day1_change ?? 0) >= 3 ? " 🎯" : ""}` : "—"}
            </div>
            <div className={`px-3 py-2.5 text-right font-mono truncate ${w.day2_change != null ? (w.day2_change > 0 ? "text-[#FF8A8A]" : w.day2_change < 0 ? "text-[#3EE6A8]" : "text-text-secondary") : "text-text-disabled"}`}>
              {w.day2_change != null ? `${w.day2_change > 0 ? "+" : ""}${w.day2_change}%` : "—"}
            </div>
            <div className={`px-3 py-2.5 text-right font-mono truncate ${w.day3_change != null ? (w.day3_change > 0 ? "text-[#FF8A8A]" : w.day3_change < 0 ? "text-[#3EE6A8]" : "text-text-secondary") : "text-text-disabled"}`}>
              {w.day3_change != null ? `${w.day3_change > 0 ? "+" : ""}${w.day3_change}%` : "—"}
            </div>
            <div className="px-3 py-2.5 text-center">
              <button onClick={() => onRemove(w.symbol)} disabled={isRemoving}
                className="rounded-lg px-2.5 py-1.5 text-[11px] text-status-danger hover:bg-status-danger/10 disabled:opacity-50 transition-colors">
                {isRemoving ? "..." : "删除"}
              </button>
            </div>
          </div>
        )})}
      </div>
    </div>
  );
}

// ═══ 历史记录表格 ═══
const H_GRID = { gridTemplateColumns: 'minmax(130px,1.5fr) 72px 78px 78px 78px 78px 64px 90px' };
function HistoryTable({ items, onRemove, removing, onRetrack, retracking, onPriceClick }: {
  items: WatchlistItem[];
  onRemove: (symbol: string) => void;
  removing: string | null;
  onRetrack: (w: WatchlistItem) => void;
  retracking: string | null;
  onPriceClick?: (w: WatchlistItem) => void;
}) {
  return (
    <div className="overflow-x-auto -mx-4 sm:mx-0">
      <div className="w-full min-w-[650px]">
        {/* Header */}
        <div className="grid text-[11px] uppercase tracking-wider text-text-disabled border-b border-border-subtle" style={H_GRID}>
          <div className="px-3 py-2.5 font-medium text-left">股票</div>
          <div className="px-3 py-2.5 font-medium text-right">入场</div>
          <div className="px-3 py-2.5 font-medium text-right">T+1</div>
          <div className="px-3 py-2.5 font-medium text-right">T+2</div>
          <div className="px-3 py-2.5 font-medium text-right">T+3</div>
          <div className="px-3 py-2.5 font-medium text-right">总收益</div>
          <div className="px-3 py-2.5 font-medium text-left">结果</div>
          <div className="px-3 py-2.5 font-medium text-center">操作</div>
        </div>
        {/* Data rows */}
        {items.map((w) => {
          const isRemoving = removing === w.symbol;
          const isRetracking = retracking === w.symbol;
          const tr = totalReturn(w);
          const rl = resultLabel(w.day1_change);
          return (
          <div key={w.id} className="grid text-[13px] border-b border-border-subtle/30 hover:bg-primary/4 transition-colors" style={H_GRID}>
            <div className="px-3 py-2.5 overflow-hidden">
              <div className="text-[14px] font-semibold text-text-primary truncate">{w.name}</div>
              <div className="text-[10px] text-text-disabled truncate">{w.symbol}</div>
            </div>
            <div className="px-3 py-2.5 text-right font-mono text-status-warning truncate">
              <span className="cursor-pointer hover:text-status-warning/80 transition-colors" onClick={() => onPriceClick?.({ ...w, symbol: w.symbol, name: w.name, entry_price: w.entry_price || 0 } as any)}>
                ¥{(w.entry_price || 0).toFixed(2)}
              </span>
            </div>
            <div className={`px-3 py-2.5 text-right font-mono font-semibold truncate ${w.day1_change != null ? (w.day1_change >= 3 ? "text-[#FF5D5D]" : w.day1_change > 0 ? "text-[#FF8A8A]" : w.day1_change < 0 ? "text-[#3EE6A8]" : "text-text-secondary") : "text-text-disabled"}`}>
              {w.day1_change != null ? `${w.day1_change > 0 ? "+" : ""}${w.day1_change}%` : "—"}
            </div>
            <div className={`px-3 py-2.5 text-right font-mono truncate ${w.day2_change != null ? (w.day2_change > 0 ? "text-[#FF8A8A]" : w.day2_change < 0 ? "text-[#3EE6A8]" : "text-text-secondary") : "text-text-disabled"}`}>
              {w.day2_change != null ? `${w.day2_change > 0 ? "+" : ""}${w.day2_change}%` : "—"}
            </div>
            <div className={`px-3 py-2.5 text-right font-mono truncate ${w.day3_change != null ? (w.day3_change > 0 ? "text-[#FF8A8A]" : w.day3_change < 0 ? "text-[#3EE6A8]" : "text-text-secondary") : "text-text-disabled"}`}>
              {w.day3_change != null ? `${w.day3_change > 0 ? "+" : ""}${w.day3_change}%` : "—"}
            </div>
            <div className={`px-3 py-2.5 text-right font-mono font-semibold truncate ${tr != null ? (tr > 0 ? "text-[#FF5D5D]" : tr < 0 ? "text-[#3EE6A8]" : "text-text-secondary") : "text-text-disabled"}`}>
              {tr != null ? `${tr > 0 ? "+" : ""}${tr.toFixed(2)}%` : "—"}
            </div>
            <div className="px-3 py-2.5">
              <span className="text-[11px] px-2 py-0.5 rounded-full inline-block" style={{ backgroundColor: rl.bg, color: rl.color }}>
                {rl.text}
              </span>
            </div>
            <div className="px-3 py-2.5">
              <div className="flex items-center justify-center gap-1">
                <button onClick={() => onRetrack(w)} disabled={isRetracking}
                  className="rounded-lg px-2 py-1 text-[11px] text-primary hover:bg-primary/10 disabled:opacity-50 transition-colors">
                  {isRetracking ? "..." : "再追踪"}
                </button>
                <button onClick={() => onRemove(w.symbol)} disabled={isRemoving}
                  className="rounded-lg px-2 py-1 text-[11px] text-[#FF5D5D] hover:bg-[rgba(255,93,93,0.1)] disabled:opacity-50 transition-colors">
                  {isRemoving ? "..." : "删除"}
                </button>
              </div>
            </div>
          </div>
        )})}
      </div>
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

// AlphaPilot A 股 Stock Detail — 个股详情 + 板块/概念/新闻 (2026-07-10)
"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { HeaderBar } from "@/components/HeaderBar";
import { fetchStockNews, fetchWatchlist, addToWatchlist, removeFromWatchlist, type StockNewsItem } from "@/lib/cn-api";

// ---------- types ----------
type StockDetail = {
  symbol: string;
  name: string;
  score: number;
  lgb_score: number;
  sector_heat: number;
  buy_price: number;
  target_price: number;
  stop_price: number;
  price: number | null;
  change_pct: number | null;
  open: number | null;
  high: number | null;
  low: number | null;
  prev_close: number | null;
  volume: number | null;
  turnover: number | null;
  pe: number | null;
  market_cap: number | null;
  source: string;
  sector?: string | null;
  region?: string | null;
};

const scoreColor = (s: number) =>
  s >= 0.75 ? "text-status-success" : s >= 0.70 ? "text-status-info" : s >= 0.65 ? "text-status-warning" : "text-text-secondary";

const chgColor = (v: number | null) =>
  v != null ? (v >= 0 ? "text-status-danger" : "text-status-success") : "text-text-disabled";
const chgSign = (v: number | null) => (v != null ? (v > 0 ? "+" : "") : "");

async function fetchStockDetail(symbol: string): Promise<StockDetail> {
  const clean = symbol.replace(/\.(SH|SZ|sh|sz)$/, "");
  const res = await fetch(`/api/v1/cn/stock/${clean}`, { cache: "no-store" });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`Backend ${res.status}: ${body.slice(0, 200)}`);
  }
  return res.json();
}

// ---------- component ----------
export default function CNStockDetail() {
  const [symbol, setSymbol] = useState<string>("");
  const [stock, setStock] = useState<StockDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [news, setNews] = useState<StockNewsItem[]>([]);
  const [newsLoading, setNewsLoading] = useState(false);
  const [wlSymbols, setWlSymbols] = useState<Set<string>>(new Set());
  const [wlMsg, setWlMsg] = useState<string | null>(null);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const sym = params.get("symbol") || "";
    let cleanSym = sym.replace(/\.(SH|SZ|sh|sz)$/, "").toUpperCase();
    setSymbol(cleanSym);
    
    // Load watchlist state
    fetchWatchlist().then(wl => {
      setWlSymbols(new Set((wl.watchlist || []).map((w: any) => w.symbol)));
    }).catch(() => {});

    if (!cleanSym) {
      setLoading(false);
      setError("缺少股票代码");
      return;
    }

    (async () => {
      setLoading(true);
      try {
        const s = await fetchStockDetail(cleanSym);
        setStock(s);
        setError(null);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setLoading(false);
      }
    })();

    // 异步加载新闻
    (async () => {
      setNewsLoading(true);
      try {
        const n = await fetchStockNews(cleanSym);
        setNews(n.slice(0, 8));
      } catch { /* ignore news errors */ }
      setNewsLoading(false);
    })();
  }, []);

  // Lazy load sector peers
  const [peers, setPeers] = useState<{ symbol: string; name: string; change_pct: number | null }[]>([]);
  const [peersLoading, setPeersLoading] = useState(false);
  useEffect(() => {
    if (!stock?.sector) return;
    setPeersLoading(true);
    fetch(`/api/v1/cn/stock/${symbol}/peers`)
      .then(r => r.json())
      .then(d => setPeers(d.peers || []))
      .catch(() => {})
      .finally(() => setPeersLoading(false));
  }, [stock?.sector]);

  const handleRefresh = async () => {
    if (!symbol) return;
    try {
      const s = await fetchStockDetail(symbol);
      setStock(s);
      setError(null);
      // Also refresh news
      try {
        const n = await fetchStockNews(symbol);
        setNews(n.slice(0, 8));
      } catch {}
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  if (loading) return <LoadingSkeleton />;
  if (error && !stock) return <ErrorState error={error} symbol={symbol} onRefresh={handleRefresh} />;

  const code = symbol;
  const score = stock?.score ?? 0;
  const change = stock?.change_pct;
  const price = stock?.price;
  const isWatched = wlSymbols.has(symbol);
  
  const toggleWatchlist = async () => {
    if (!symbol || !stock) return;
    try {
      if (isWatched) {
        await removeFromWatchlist(symbol);
        setWlSymbols(prev => { const n = new Set(prev); n.delete(symbol); return n; });
        setWlMsg("已移除收藏");
      } else {
        await addToWatchlist(symbol, stock.name, stock.buy_price || 0, stock.score || 0);
        setWlSymbols(prev => new Set(prev).add(symbol));
        setWlMsg("已添加收藏");
      }
    } catch { setWlMsg("操作失败"); }
    setTimeout(() => setWlMsg(null), 2000);
  };
  const sector = stock?.sector || null;
  const region = stock?.region || null;

  return (
    <main className="mx-auto max-w-[1440px] px-4 sm:px-6 lg:px-8 py-4 sm:py-6 lg:py-8 min-h-screen">
      <HeaderBar market="cn" />

      {/* Back button + refresh */}
      <div className="mb-4 flex items-center justify-between">
        <Link href="/cn" className="inline-flex items-center gap-1 text-[12px] text-text-secondary hover:text-status-info">
          ← 返回 Dashboard
        </Link>
        <button onClick={handleRefresh} className="rounded-lg border border-border-subtle bg-surface-panel px-3 py-1.5 text-[12px] text-text-secondary hover:border-status-info hover:text-text-primary transition-colors">
          刷新
        </button>
      </div>

      {/* ═══ Stock Header ═══ */}
      <header className="glass-strong info-card card-lift rounded-2xl p-5 mb-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex items-baseline gap-3">
              <h1 className="font-mono text-[28px] sm:text-[36px] font-bold leading-none tracking-tight text-status-info">
                {code}
              </h1>
              <span className="text-[20px] sm:text-[24px] text-text-primary font-semibold">{stock?.name ?? code}</span>
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-3">
              {sector && (
                <span className="tag-badge text-status-info">
                  {sector}
                </span>
              )}
              {region && (
                <span className="tag-badge text-status-success">
                  📍 {region}
                </span>
              )}
              <span className="text-[11px] text-text-disabled">数据源: {stock?.source ?? "—"}</span>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {/* Price */}
            <div className="text-right mr-4">
              <div className="font-display-numeric text-[36px] sm:text-[42px] font-bold text-text-primary leading-none">
                ¥{price?.toFixed(2) ?? "—"}
              </div>
              <div className={`font-display-numeric text-[18px] font-semibold ${chgColor(change)}`}>
                {chgSign(change)}{change?.toFixed(2) ?? "—"}%
              </div>
              {stock?.prev_close && (
                <div className="text-[11px] text-text-disabled mt-0.5">昨收 ¥{stock.prev_close.toFixed(2)}</div>
              )}
            </div>
            <button onClick={toggleWatchlist}
              className={`rounded-lg px-3 py-1.5 text-[12px] font-medium transition-colors ${
                isWatched ? "bg-[rgba(245,196,81,0.15)] text-status-warning hover:bg-[rgba(245,196,81,0.25)]"
                : "border border-border-subtle text-text-disabled hover:border-[#F5C451] hover:text-status-warning"
              }`}>
              {isWatched ? "★ 收藏中" : "☆ 添加收藏"}
            </button>
          </div>
        </div>

        {wlMsg && (
          <div className="mb-4 rounded-xl bg-[rgba(62,230,168,0.1)] border border-[rgba(62,230,168,0.3)] px-4 py-2 text-[13px] text-status-success">{wlMsg}</div>
        )}

        {/* OHLC mini bar */}
        {(stock?.open || stock?.high) && (
          <div className="mt-4 flex flex-wrap gap-4 text-[12px] text-text-secondary border-t border-border-subtle pt-3">
            <span>开 <span className="text-text-primary font-mono">{stock?.open?.toFixed(2) ?? "—"}</span></span>
            <span>高 <span className="text-text-primary font-mono">{stock?.high?.toFixed(2) ?? "—"}</span></span>
            <span>低 <span className="text-text-primary font-mono">{stock?.low?.toFixed(2) ?? "—"}</span></span>
            <span>量 <span className="text-text-primary font-mono">{stock?.volume != null ? (stock.volume / 10000).toFixed(1) + "万" : "—"}</span></span>
            <span>换手 <span className="text-text-primary font-mono">{stock?.turnover != null ? stock.turnover.toFixed(2) + "%" : "—"}</span></span>
            <span>PE <span className="text-text-primary font-mono">{stock?.pe?.toFixed(1) ?? "—"}</span></span>
          </div>
        )}
      </header>

      {/* ═══ Main Content Grid ═══ */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

        {/* ─── Left Column: Score + Targets ─── */}
        <div className="col-span-1 space-y-6">

          {/* AI Score Card */}
          <section className="glass-strong info-card card-lift rounded-2xl p-5">
            <div className="mb-3 flex items-center justify-between">
              <span className="text-[11px] uppercase tracking-wider text-text-disabled">🤖 AI 评分决策卡</span>
              <span className="rounded-full bg-[rgba(77,163,255,0.12)] px-2 py-0.5 text-[10px] font-semibold text-status-info border border-[rgba(77,163,255,0.3)]">
                V1.9 Fusion
              </span>
            </div>

            <div className="mb-4 text-center">
              <div className="mb-1 text-[11px] uppercase tracking-wider text-text-disabled">综合评分</div>
              <div className={`font-display-numeric text-[56px] leading-none ${scoreColor(score)}`}>
                {(score * 100).toFixed(0)}
              </div>
              <div className="mt-2 text-[12px] text-text-secondary">
                LGB <span className="text-text-primary">{((stock?.lgb_score ?? 0) * 100).toFixed(0)}</span>
                {" · "}板块热度 <span className="text-text-primary">{((stock?.sector_heat ?? 0.5) * 100).toFixed(0)}</span>
              </div>
            </div>

            {/* Score breakdown bars */}
            <div className="space-y-3 mb-4">
              <BarMeter label="XGBoost 概率" value={stock?.lgb_score ?? score} color="#A78BFA" />
              <BarMeter label="板块热度" value={stock?.sector_heat ?? 0.5} color="#3EE6A8" />
              <BarMeter label="综合评分" value={score} color={score >= 0.7 ? "#3EE6A8" : score >= 0.65 ? "#F5C451" : "#9FB0C7"} />
            </div>

            <div className="rounded-xl border border-border-subtle bg-surface-panel p-3">
              <div className="mb-2 text-[10px] uppercase tracking-wider text-text-disabled">🎯 ATR 价格目标</div>
              <div className="space-y-1 text-[13px]">
                <div className="flex items-center justify-between">
                  <span className="text-text-disabled">买入价</span>
                  <span className="font-display-numeric text-[16px] text-text-primary">¥{stock?.buy_price && stock.buy_price > 0 ? stock.buy_price.toFixed(2) : "—"}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-text-disabled">目标价</span>
                  <span className="font-display-numeric text-[16px] text-status-success">¥{stock?.target_price && stock.target_price > 0 ? stock.target_price.toFixed(2) : "—"}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-text-disabled">止损价</span>
                  <span className="font-display-numeric text-[16px] text-status-danger">¥{stock?.stop_price && stock.stop_price > 0 ? stock.stop_price.toFixed(2) : "—"}</span>
                </div>
              </div>
            </div>

            {stock?.target_price && stock?.buy_price && stock?.stop_price && stock.buy_price > stock.stop_price && (
              <div className="mt-3 rounded-xl border border-border-subtle bg-surface-panel p-3">
                <div className="mb-1 text-[10px] uppercase tracking-wider text-text-disabled">盈亏比</div>
                <div className="text-[22px] font-semibold text-status-success">
                  {((stock.target_price - stock.buy_price) / (stock.buy_price - stock.stop_price)).toFixed(2)}<span className="text-[13px] text-text-secondary"> : 1</span>
                </div>
              </div>
            )}
          </section>
        </div>

        {/* ─── Middle Column: Sector + Peers ─── */}
        <div className="col-span-1 space-y-6">

          {/* Sector Card */}
          <section className="glass rounded-2xl p-5">
            <h3 className="mb-3 text-[14px] font-semibold flex items-center gap-2">
              🏭 主力板块
            </h3>
            {sector ? (
              <div>
                <div className="flex items-center gap-2 mb-3">
                  <span className="text-[20px] font-semibold text-status-info">{sector}</span>
                </div>
                {/* Sector peers */}
                <div className="border-t border-border-subtle pt-3">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-[11px] text-text-disabled">同板块股票</span>
                  </div>
                  {peersLoading ? (
                    <div className="flex items-center gap-2 text-[12px] text-text-disabled">
                      <span className="h-3 w-3 animate-spin rounded-full border-2 border-border-subtle border-t-[#A78BFA]" />
                      加载中...
                    </div>
                  ) : peers.length > 0 ? (
                    <div className="space-y-1.5">
                      {peers.map((p, i) => (
                        <Link key={p.symbol} href={`/cn/stock?symbol=${p.symbol}`}
                          className="flex items-center justify-between rounded-lg bg-surface-container-low px-3 py-2 hover:bg-[#16202f] transition-colors group">
                          <div className="flex items-center gap-2 min-w-0">
                            <span className="text-[10px] text-text-disabled w-4">{i + 1}</span>
                            <span className="text-[12px] text-text-primary group-hover:text-status-info truncate">{p.name}</span>
                            <span className="text-[10px] text-text-disabled">{p.symbol}</span>
                          </div>
                          <span className={`font-display-numeric text-[12px] font-medium ${chgColor(p.change_pct)}`}>
                            {chgSign(p.change_pct)}{p.change_pct?.toFixed(2) ?? "—"}%
                          </span>
                        </Link>
                      ))}
                    </div>
                  ) : (
                    <p className="text-[12px] text-text-disabled text-center py-3">暂无板块数据</p>
                  )}
                </div>
              </div>
            ) : (
              <p className="text-[12px] text-text-disabled text-center py-4">暂无板块信息</p>
            )}
          </section>

          {/* Strategy Performance */}
          <section className="glass rounded-2xl p-5">
            <h3 className="mb-3 text-[14px] font-semibold">📊 策略表现</h3>
            <div className="space-y-2 text-[12px] text-text-secondary">
              <div className="flex items-center justify-between"><span>Sharpe</span><span className="text-status-success font-semibold">5.16</span></div>
              <div className="flex items-center justify-between"><span>累计收益</span><span className="text-status-success font-semibold">+164.4%</span></div>
              <div className="flex items-center justify-between"><span>最大回撤</span><span className="text-status-danger font-semibold">-6.4%</span></div>
              <div className="flex items-center justify-between"><span>正收益期数</span><span className="text-text-primary font-semibold">15/19 (79%)</span></div>
            </div>
          </section>
        </div>

        {/* ─── Right Column: News ─── */}
        <div className="col-span-1 space-y-6">

          {/* News Card */}
          <section className="glass rounded-2xl p-5">
            <h3 className="mb-3 text-[14px] font-semibold flex items-center gap-2">
              📰 相关新闻
            </h3>
            {newsLoading ? (
              <div className="flex items-center justify-center py-8">
                <div className="h-6 w-6 animate-spin rounded-full border-3 border-border-subtle border-t-[#A78BFA]" />
              </div>
            ) : news.length > 0 ? (
              <div className="space-y-2">
                {news.map((item, i) => (
                  <a key={i} href={item.url} target="_blank" rel="noopener noreferrer"
                    className="block rounded-lg bg-surface-container-low p-3 hover:bg-[#16202f] transition-colors group">
                    <p className="text-[13px] text-text-primary group-hover:text-status-info transition-colors line-clamp-2 leading-snug">
                      {item.title}
                    </p>
                    <div className="mt-1.5 flex items-center gap-2 text-[10px] text-text-disabled">
                      <span>{item.source || "东方财富"}</span>
                      <span>·</span>
                      <span>{item.time}</span>
                    </div>
                  </a>
                ))}
              </div>
            ) : (
              <div className="text-center py-8">
                <p className="text-[13px] text-text-disabled">暂无相关新闻</p>
                <p className="text-[11px] text-text-disabled mt-1">新闻抓取源暂不可用</p>
              </div>
            )}
          </section>
        </div>
      </div>

      <footer className="mt-10 text-center text-[11px] text-text-disabled">
        AlphaPilot 提供 AI 辅助分析，仅供教育用途，非投资建议。
      </footer>
    </main>
  );
}

// ═══ Helper Components ═══

function BarMeter({ label, value, color }: { label: string; value: number; color: string }) {
  const pct = Math.round(value * 100);
  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-[12px]">
        <span className="text-text-secondary">{label}</span>
        <span className="font-display-numeric font-semibold" style={{ color }}>{pct}</span>
      </div>
      <div className="h-2 rounded-full bg-border-subtle overflow-hidden">
        <div className="h-full rounded-full transition-all duration-500" style={{ width: `${pct}%`, backgroundColor: color }} />
      </div>
    </div>
  );
}

function LoadingSkeleton() {
  return (
    <main className="mx-auto max-w-[1440px] px-4 sm:px-6 lg:px-8 py-4 sm:py-6 lg:py-8 min-h-screen">
      <HeaderBar market="cn" />
      <div className="flex flex-col items-center justify-center py-40">
        <div className="h-12 w-12 animate-spin rounded-full border-4 border-border-subtle border-t-[#A78BFA]" />
        <p className="mt-4 text-[14px] text-text-secondary">加载中...</p>
      </div>
    </main>
  );
}

function ErrorState({ error, symbol, onRefresh }: { error: string; symbol: string; onRefresh: () => void }) {
  return (
    <main className="mx-auto max-w-[1440px] px-4 sm:px-6 lg:px-8 py-4 sm:py-6 lg:py-8 min-h-screen">
      <HeaderBar market="cn" />
      <div className="glass rounded-2xl border border-[#FF5D5D] p-8 text-center mt-20">
        <p className="text-status-danger font-semibold text-lg mb-2">无法加载个股数据</p>
        <p className="text-[12px] text-text-secondary mb-4">{error}</p>
        <div className="flex items-center justify-center gap-3">
          <Link href="/cn" className="rounded-lg border border-border-subtle bg-surface-panel px-4 py-2 text-[12px] text-text-secondary hover:text-text-primary">
            ← 返回首页
          </Link>
          <button onClick={onRefresh} className="rounded-lg bg-status-info px-4 py-2 text-[12px] font-semibold text-on-primary hover:bg-[#C084FC]">
            重试
          </button>
        </div>
      </div>
    </main>
  );
}

// AlphaPilot A 股 Stock Detail — 个股详情 + 资金/板块/新闻
"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { HeaderBar } from "@/components/HeaderBar";
import { fetchStockNews, fetchWatchlist, addToWatchlist, removeFromWatchlist, type StockNewsItem } from "@/lib/cn-api";
import {
  HEAT_MAX_ADJUST,
  combinedPct as calcCombinedPct,
  combinedScore,
  toUnitProba,
} from "@/lib/score-display";

// ---------- types ----------
type FundBar = { date: string; main_net: number };

type StockDetail = {
  symbol: string;
  name: string;
  score: number;
  lgb_score: number;
  model_proba?: number;
  score_pct?: number;
  sector_heat: number;
  buy_price: number;
  target_price: number;
  stop_price: number;
  price: number | null;
  change_pct: number | null;
  live_price?: number | null;
  live_change_pct?: number | null;
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
  industry?: string | null;
  industry_l1?: string | null;
  industry_path?: string | null;
  money_phase?: string | null;
  money_phase_label?: string | null;
  main_net?: number | null;
  main_net_3d?: number | null;
  main_net_5d?: number | null;
  main_net_10d?: number | null;
  fund_pos_days_5?: number | null;
  fund_soft_bonus?: number | null;
  fund_series_5d?: FundBar[];
  money_warning?: string | null;
  soft_demote_reasons?: string[] | string | null;
  exposure?: number | null;
  position_exposure?: number | null;
  active_buy_ratio?: number | null;
  money_flow_pass?: boolean | null;
  note?: string | null;
};

const scoreColor = (pct: number) =>
  pct >= 80
    ? "text-status-success"
    : pct >= 70
      ? "text-status-info"
      : pct >= 60
        ? "text-status-warning"
        : "text-text-secondary";

const chgColor = (v: number | null | undefined) =>
  v != null ? (v >= 0 ? "text-status-danger" : "text-status-success") : "text-text-disabled";
const chgSign = (v: number | null | undefined) => (v != null ? (v > 0 ? "+" : "") : "");

function fmtYi(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return "—";
  const yi = v / 1e8;
  const sign = yi > 0 ? "+" : "";
  if (Math.abs(yi) >= 0.01) return `${sign}${yi.toFixed(2)}亿`;
  const wan = v / 1e4;
  return `${wan > 0 ? "+" : ""}${wan.toFixed(0)}万`;
}

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

    (async () => {
      setNewsLoading(true);
      try {
        const n = await fetchStockNews(cleanSym);
        setNews(n.slice(0, 8));
      } catch { /* ignore */ }
      setNewsLoading(false);
    })();
  }, []);

  const [peers, setPeers] = useState<{ symbol: string; name: string; change_pct: number | null }[]>([]);
  const [peersLoading, setPeersLoading] = useState(false);
  useEffect(() => {
    if (!symbol) return;
    setPeersLoading(true);
    fetch(`/api/v1/cn/stock/${symbol}/peers`)
      .then(r => r.json())
      .then(d => setPeers(d.peers || []))
      .catch(() => {})
      .finally(() => setPeersLoading(false));
  }, [symbol, stock?.sector, stock?.industry]);

  const handleRefresh = async () => {
    if (!symbol) return;
    try {
      const s = await fetchStockDetail(symbol);
      setStock(s);
      setError(null);
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
  const modelProba = toUnitProba(stock?.model_proba ?? stock?.lgb_score ?? score);
  const heat = Math.min(1, Math.max(0, Number(stock?.sector_heat ?? 0.5)));
  const combined = combinedScore(modelProba, heat);
  const modelPct = Math.round(modelProba * 100);
  const heatPct = Math.round(heat * 100);
  const combinedPct = calcCombinedPct(modelProba, heat);
  const change = stock?.live_change_pct ?? stock?.change_pct;
  const price = stock?.live_price ?? stock?.price ?? stock?.buy_price;
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

  const sector = stock?.sector || stock?.industry || null;
  const region = stock?.region || stock?.industry_l1 || null;
  const series = stock?.fund_series_5d || [];
  const maxAbs = Math.max(...series.map((s) => Math.abs(s.main_net || 0)), 1);
  const rawDemote = stock?.soft_demote_reasons;
  let demoteList: string[] = [];
  if (Array.isArray(rawDemote)) {
    demoteList = rawDemote.map(String);
  } else if (rawDemote) {
    demoteList = [String(rawDemote)];
  }
  const expo = stock?.position_exposure ?? stock?.exposure;

  return (
    <main className="mx-auto max-w-[1440px] px-4 sm:px-6 lg:px-8 py-4 sm:py-6 lg:py-8 min-h-screen">
      <HeaderBar market="cn" />

      <div className="mb-4 flex items-center justify-between">
        <Link href="/cn" className="inline-flex items-center gap-1 text-[12px] text-text-secondary hover:text-status-info">
          ← 返回工作台
        </Link>
        <button onClick={handleRefresh} className="rounded-lg border border-border-subtle bg-surface-panel px-3 py-1.5 text-[12px] text-text-secondary hover:border-[#4DA3FF] hover:text-text-primary transition-colors">
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
                <span className="tag-badge text-status-info">{sector}</span>
              )}
              {region && region !== sector && (
                <span className="tag-badge text-status-success">{region}</span>
              )}
              {stock?.money_phase_label && (
                <span className="tag-badge text-status-warning">{stock.money_phase_label}</span>
              )}
              <span className="text-[11px] text-text-disabled">
                {stock?.industry_path || (stock?.source ? `数据源: ${stock.source}` : "")}
              </span>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <div className="text-right mr-4">
              <div className="font-display-numeric text-[36px] sm:text-[42px] font-bold text-text-primary leading-none">
                ¥{price != null ? Number(price).toFixed(2) : "—"}
              </div>
              <div className={`font-display-numeric text-[18px] font-semibold ${chgColor(change)}`}>
                {chgSign(change)}{change != null ? Number(change).toFixed(2) : "—"}%
              </div>
              {stock?.prev_close != null && (
                <div className="text-[11px] text-text-disabled mt-0.5">
                  {stock.live_price ? "实时" : "昨收"} ¥{Number(stock.prev_close).toFixed(2)}
                </div>
              )}
            </div>
            <button onClick={toggleWatchlist}
              className={`rounded-lg px-3 py-1.5 text-[12px] font-medium transition-colors ${
                isWatched ? "bg-[rgba(245,196,81,0.15)] text-status-warning hover:bg-[rgba(245,196,81,0.25)]"
                : "border border-border-subtle text-text-disabled hover:border-[#F5C451] hover:text-status-warning"
              }`}>
              {isWatched ? "收藏中" : "添加收藏"}
            </button>
          </div>
        </div>

        {wlMsg && (
          <div className="mb-4 rounded-xl bg-[rgba(62,230,168,0.1)] border border-[rgba(62,230,168,0.3)] px-4 py-2 text-[13px] text-status-success">{wlMsg}</div>
        )}

        {(stock?.open || stock?.high || stock?.turnover != null) && (
          <div className="mt-4 flex flex-wrap gap-4 text-[12px] text-text-secondary border-t border-border-subtle pt-3">
            <span>开 <span className="text-text-primary font-mono">{stock?.open != null ? Number(stock.open).toFixed(2) : "—"}</span></span>
            <span>高 <span className="text-text-primary font-mono">{stock?.high != null ? Number(stock.high).toFixed(2) : "—"}</span></span>
            <span>低 <span className="text-text-primary font-mono">{stock?.low != null ? Number(stock.low).toFixed(2) : "—"}</span></span>
            <span>量 <span className="text-text-primary font-mono">{stock?.volume != null ? (Number(stock.volume) / 10000).toFixed(1) + "万" : "—"}</span></span>
            <span>换手 <span className="text-text-primary font-mono">{stock?.turnover != null ? Number(stock.turnover).toFixed(2) + "%" : "—"}</span></span>
            <span>PE <span className="text-text-primary font-mono">{stock?.pe != null ? Number(stock.pe).toFixed(1) : "—"}</span></span>
            {stock?.active_buy_ratio != null && (
              <span>主动买 <span className="text-text-primary font-mono">{(Number(stock.active_buy_ratio) * 100).toFixed(0)}%</span></span>
            )}
          </div>
        )}
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

        {/* ─── Left: Score + Targets ─── */}
        <div className="col-span-1 space-y-6">
          <section className="glass-strong info-card card-lift rounded-2xl p-5">
            <div className="mb-3 flex items-center justify-between">
              <span className="text-[11px] uppercase tracking-wider text-text-disabled">AI 评分决策卡</span>
              <span className="rounded-full bg-[rgba(77,163,255,0.12)] px-2 py-0.5 text-[10px] font-semibold text-status-info border border-[rgba(77,163,255,0.3)]">
                Permission · Soft
              </span>
            </div>

            <div className="mb-4 text-center">
              <div className="mb-1 text-[11px] uppercase tracking-wider text-text-disabled">综合评分</div>
              <div className={`font-display-numeric text-[56px] leading-none ${scoreColor(combinedPct)}`}>
                {combinedPct}
              </div>
              <div className="mt-2 text-[12px] text-text-secondary">
                模型概率 <span className="text-text-primary">{modelPct}</span>
                {" · "}板块热度 <span className="text-text-primary">{heatPct}</span>
                {expo != null && (
                  <>
                    {" · "}仓位敞口{" "}
                    <span className="text-text-primary">{Number(expo).toFixed(2)}</span>
                  </>
                )}
              </div>
              <p className="mt-2 text-[11px] text-text-disabled">
                综合≈模型分；热度中性不加减（最多 ±{Math.round(HEAT_MAX_ADJUST * 100)}）
              </p>
            </div>

            <div className="space-y-3 mb-4">
              <BarMeter label="XGBoost 概率" value={modelProba} color="#4DA3FF" />
              <BarMeter label="板块热度" value={heat} color="#3EE6A8" />
              <BarMeter
                label="综合评分"
                value={combined}
                color={combined >= 0.8 ? "#3EE6A8" : combined >= 0.7 ? "#F5C451" : "#9FB0C7"}
              />
            </div>

            <div className="rounded-xl border border-border-subtle bg-surface-panel p-3">
              <div className="mb-2 text-[10px] uppercase tracking-wider text-text-disabled">ATR 价格目标</div>
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

            {stock?.target_price && stock?.buy_price && stock?.stop_price
              && stock.target_price > stock.buy_price
              && stock.buy_price > stock.stop_price && (
              <div className="mt-3 rounded-xl border border-border-subtle bg-surface-panel p-3">
                <div className="mb-1 text-[10px] uppercase tracking-wider text-text-disabled">盈亏比</div>
                <div className="text-[22px] font-semibold text-status-success">
                  {((stock.target_price - stock.buy_price) / (stock.buy_price - stock.stop_price)).toFixed(2)}
                  <span className="text-[13px] text-text-secondary"> : 1</span>
                </div>
              </div>
            )}
          </section>
        </div>

        {/* ─── Middle: Fund + Sector ─── */}
        <div className="col-span-1 space-y-6">
          {/* Fund flow: 3d tip + 5d spine */}
          <section className="glass rounded-2xl p-5">
            <h3 className="mb-1 text-[14px] font-semibold">资金概况</h3>
            <p className="mb-3 text-[11px] text-text-disabled">近端流入与中期资金强度</p>

            <div className="grid grid-cols-3 gap-2 mb-4">
              <FundStat label="近3日" value={stock?.main_net_3d} />
              <FundStat label="近5日" value={stock?.main_net_5d} highlight />
              <FundStat label="近10日" value={stock?.main_net_10d} />
            </div>

            {stock?.fund_pos_days_5 != null && (
              <div className="flex items-center justify-between text-[12px] text-text-secondary mb-3">
                <span>近5日正流入</span>
                <span className="text-text-primary font-semibold">
                  {`${stock.fund_pos_days_5}/5`}
                </span>
              </div>
            )}

            {series.length > 0 ? (
              <>
                <div className="mb-2 flex items-center gap-3 text-[10px] text-text-disabled">
                  <span className="inline-flex items-center gap-1">
                    <span className="inline-block h-2 w-2 rounded-sm bg-[rgba(255,93,93,0.85)]" />
                    红=流入(+)
                  </span>
                  <span className="inline-flex items-center gap-1">
                    <span className="inline-block h-2 w-2 rounded-sm bg-[rgba(62,230,168,0.85)]" />
                    绿=流出(-)
                  </span>
                </div>
                <div className="flex items-end gap-1.5 h-28 mt-1">
                  {[...series].reverse().map((b) => {
                    const h = Math.max(10, Math.round((Math.abs(b.main_net) / maxAbs) * 64));
                    const inflow = b.main_net >= 0;
                    return (
                      <div
                        key={b.date}
                        className="flex-1 flex flex-col items-center justify-end gap-1"
                        title={`${b.date} 主力净额 ${fmtYi(b.main_net)}`}
                      >
                        <span
                          className={`text-[9px] font-mono leading-none ${
                            inflow ? "text-status-danger" : "text-status-success"
                          }`}
                        >
                          {fmtYi(b.main_net)}
                        </span>
                        <div
                          className="w-full rounded-t-sm"
                          style={{
                            height: h,
                            backgroundColor: inflow
                              ? "rgba(255,93,93,0.75)"
                              : "rgba(62,230,168,0.75)",
                          }}
                        />
                        <span className="text-[9px] text-text-disabled">{b.date.slice(5)}</span>
                      </div>
                    );
                  })}
                </div>
              </>
            ) : (
              <p className="text-[12px] text-text-disabled text-center py-4">暂无多日资金序列</p>
            )}

            {stock?.money_warning && (
              <p className="mt-3 text-[11px] text-status-warning leading-snug">{stock.money_warning}</p>
            )}
          </section>

          {/* Sector + peers */}
          <section className="glass rounded-2xl p-5">
            <h3 className="mb-3 text-[14px] font-semibold">所属板块</h3>
            {sector || region ? (
              <div>
                <div className="flex flex-wrap items-center gap-2 mb-3">
                  {sector && <span className="text-[18px] font-semibold text-status-info">{sector}</span>}
                  {region && <span className="text-[12px] text-text-secondary">{region}</span>}
                </div>
                <div className="border-t border-border-subtle pt-3">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-[11px] text-text-disabled">同板块股票</span>
                    <Link href="/cn/sectors" className="text-[11px] text-status-info hover:underline">板块看板</Link>
                  </div>
                  {peersLoading ? (
                    <div className="flex items-center gap-2 text-[12px] text-text-disabled">
                      <span className="h-3 w-3 animate-spin rounded-full border-2 border-border-subtle border-t-[#4DA3FF]" />
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
                            {chgSign(p.change_pct)}{p.change_pct != null ? p.change_pct.toFixed(2) : "—"}%
                          </span>
                        </Link>
                      ))}
                    </div>
                  ) : (
                    <p className="text-[12px] text-text-disabled text-center py-3">暂无同板块报价</p>
                  )}
                </div>
              </div>
            ) : (
              <p className="text-[12px] text-text-disabled text-center py-4">行业映射暂不可用</p>
            )}
          </section>
        </div>

        {/* ─── Right: Decision context + News ─── */}
        <div className="col-span-1 space-y-6">
          <section className="glass rounded-2xl p-5">
            <h3 className="mb-3 text-[14px] font-semibold">决策上下文</h3>
            <div className="space-y-2 text-[12px] text-text-secondary">
              <div className="flex items-center justify-between">
                <span>资金阶段</span>
                <span className="text-text-primary font-semibold">{stock?.money_phase_label || stock?.money_phase || "—"}</span>
              </div>
              <div className="flex items-center justify-between">
                <span>资金筛选</span>
                <span className="text-text-primary font-semibold">已通过</span>
              </div>
              <div className="flex items-center justify-between">
                <span>仓位建议</span>
                <span className="text-text-primary font-semibold">{expo != null ? Number(expo).toFixed(2) : "—"}</span>
              </div>
              {demoteList.length > 0 && (
                <div className="pt-2 border-t border-border-subtle">
                  <div className="text-[11px] text-text-disabled mb-1">风险提示</div>
                  <ul className="space-y-1">
                    {demoteList.map((d, i) => (
                      <li key={i} className="text-[11px] text-status-warning leading-snug">· {d}</li>
                    ))}
                  </ul>
                </div>
              )}
              {stock?.note && (
                <p className="pt-2 text-[11px] text-text-disabled border-t border-border-subtle">{stock.note}</p>
              )}
            </div>
            <p className="mt-3 text-[10px] text-text-disabled leading-relaxed">
              此处展示当日管线决策信号，非历史回测 KPI。系统级策略表现请看「回测 / 量化模拟」。
            </p>
          </section>

          <section className="glass rounded-2xl p-5">
            <h3 className="mb-3 text-[14px] font-semibold flex items-center justify-between">
              <span>相关新闻</span>
              <a
                href={`https://finance.eastmoney.com/a/${code}.html`}
                target="_blank"
                rel="noopener noreferrer"
                className="text-[11px] font-normal text-status-info hover:underline"
              >
                东财更多 →
              </a>
            </h3>
            {newsLoading ? (
              <div className="flex items-center justify-center py-8">
                <div className="h-6 w-6 animate-spin rounded-full border-3 border-border-subtle border-t-[#4DA3FF]" />
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
              <div className="text-center py-6">
                <p className="text-[13px] text-text-disabled">暂无抓取到新闻</p>
                <a
                  href={`https://guba.eastmoney.com/list,${code}.html`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-block mt-2 text-[12px] text-status-info hover:underline"
                >
                  查看股吧讨论
                </a>
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

function FundStat({ label, value, highlight }: { label: string; value?: number | null; highlight?: boolean }) {
  const up = value != null && value > 0;
  const down = value != null && value < 0;
  return (
    <div className={`rounded-xl border px-2 py-2 text-center ${highlight ? "border-[rgba(77,163,255,0.35)] bg-[rgba(77,163,255,0.06)]" : "border-border-subtle bg-surface-panel"}`}>
      <div className="text-[10px] text-text-disabled mb-1">{label}</div>
      <div className={`font-display-numeric text-[13px] font-semibold ${up ? "text-status-danger" : down ? "text-status-success" : "text-text-primary"}`}>
        {fmtYi(value)}
      </div>
    </div>
  );
}

function BarMeter({ label, value, color }: { label: string; value: number; color: string }) {
  const pct = Math.round(Math.max(0, Math.min(1, value)) * 100);
  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-[12px]">
        <span className="text-text-secondary">{label}</span>
        <span className="font-display-numeric font-semibold" style={{ color }}>{pct}</span>
      </div>
      <div className="h-2 rounded-full bg-[#1D2A42] overflow-hidden">
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
        <div className="h-12 w-12 animate-spin rounded-full border-4 border-border-subtle border-t-[#4DA3FF]" />
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
          <button onClick={onRefresh} className="rounded-lg bg-status-info px-4 py-2 text-[12px] font-semibold text-[#00315b] hover:bg-[#7ddeff]">
            重试
          </button>
        </div>
      </div>
    </main>
  );
}

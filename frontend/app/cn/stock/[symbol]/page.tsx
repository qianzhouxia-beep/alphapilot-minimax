// AlphaPilot A 股 Stock Detail — 腾讯云 V12 管线单只详情 (2026-07-04)
// Zeabur HTTPS -> cn_proxy.py -> 腾讯云 stock 端点
"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { HeaderBar } from "@/components/HeaderBar";
import { fetchWatchlist, addToWatchlist, removeFromWatchlist } from "@/lib/cn-api";

// ---------- types ----------
type StockDetail = {
  symbol: string;
  name: string;
  score: number;
  lgb_score: number;
  confidence_score?: number;
  model_proba?: number;
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
};

function toUnitProba(v: number | null | undefined): number {
  const x = Number(v ?? 0);
  if (!Number.isFinite(x) || x <= 0) return 0;
  if (x <= 1) return x;
  return 1 / (1 + Math.exp(-x / 2));
}

const MODEL_WEIGHT = 0.8;
const HEAT_WEIGHT = 0.2;

function combinedScore(modelProba: number, heat: number): number {
  return modelProba * MODEL_WEIGHT + heat * HEAT_WEIGHT;
}

const scoreColor = (pct: number) =>
  pct >= 80
    ? "text-[#3EE6A8]"
    : pct >= 70
      ? "text-status-info"
      : pct >= 60
        ? "text-[#F5C451]"
        : "text-text-secondary";

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
export default function CNStockDetail({ params }: { params: Promise<{ symbol: string }> }) {
  const [symbol, setSymbol] = useState<string>("");
  const [stock, setStock] = useState<StockDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [wlSymbols, setWlSymbols] = useState<Set<string>>(new Set());
  const [wlMsg, setWlMsg] = useState<string | null>(null);

  useEffect(() => {
    fetchWatchlist().then(wl => {
      setWlSymbols(new Set((wl.watchlist || []).map((w: any) => w.symbol)));
    }).catch(() => {});
  }, []);

  const isWatched = wlSymbols.has(symbol);
  const handleToggleWl = async () => {
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

  useEffect(() => {
    params.then((p) => {
      let sym = p.symbol;
      // 6 digit code -> strip possible .SH/.SZ suffix
      sym = sym.replace(/\.(SH|SZ|sh|sz)$/, "").toUpperCase();
      setSymbol(sym);

      (async () => {
        setLoading(true);
        try {
          const s = await fetchStockDetail(sym);
          setStock(s);
          setError(null);
        } catch (e) {
          setError(e instanceof Error ? e.message : String(e));
        } finally {
          setLoading(false);
        }
      })();
    });
  }, [params]);

  const handleRefresh = async () => {
    if (!symbol) return;
    try {
      const s = await fetchStockDetail(symbol);
      setStock(s);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  if (loading) {
    return (
      <main className="mx-auto max-w-[1440px] px-4 sm:px-6 lg:px-8 py-4 sm:py-6 lg:py-8 min-h-screen">
        <HeaderBar market="cn" />
        <div className="flex flex-col items-center justify-center py-40">
          <div className="h-12 w-12 animate-spin rounded-full border-4 border-border-subtle border-t-[#A78BFA]"></div>
          <p className="mt-4 text-[14px] text-text-secondary">加载中...</p>
        </div>
      </main>
    );
  }

  if (error && !stock) {
    return (
      <main className="mx-auto max-w-[1440px] px-4 sm:px-6 lg:px-8 py-4 sm:py-6 lg:py-8 min-h-screen">
        <HeaderBar market="cn" />
        <div className="glass rounded-2xl border border-[#FF5D5D] p-8 text-center mt-20">
          <p className="text-[#FF5D5D] font-semibold text-lg mb-2">无法加载个股数据</p>
          <p className="text-[12px] text-text-secondary mb-4">{error}</p>
          <div className="flex items-center justify-center gap-3">
            <Link href="/cn" className="rounded-lg border border-border-subtle bg-surface-card px-4 py-2 text-[12px] text-text-secondary hover:text-text-primary">
              ← 返回首页
            </Link>
            <button onClick={handleRefresh} className="rounded-lg bg-status-info px-4 py-2 text-[12px] font-semibold text-on-primary hover:bg-[#C084FC]">
              重试
            </button>
          </div>
        </div>
      </main>
    );
  }

  const code = symbol;
  const score = stock?.score ?? 0;
  const modelProba = toUnitProba(stock?.model_proba ?? stock?.lgb_score ?? score);
  const sectorHeat = Math.min(1, Math.max(0, Number(stock?.sector_heat ?? 0.5)));
  const combined = combinedScore(modelProba, sectorHeat);
  const modelPct = Math.round(modelProba * 100);
  const heatPct = Math.round(sectorHeat * 100);
  const combinedPct = Math.round(combined * 100);
  const buyPrice = stock?.buy_price ?? 0;
  const targetPrice = stock?.target_price ?? 0;
  const stopPrice = stock?.stop_price ?? 0;

  return (
    <main className="mx-auto max-w-[1440px] px-4 sm:px-6 lg:px-8 py-4 sm:py-6 lg:py-8 min-h-screen">
      <HeaderBar market="cn" />

      {/* Header */}
      <header className="mb-8 flex flex-wrap items-start justify-between gap-4">
        <div>
          <Link href="/cn" className="mb-2 inline-flex items-center gap-1 text-[12px] text-text-secondary hover:text-status-info">
            ← 返回首页
          </Link>
          <div className="flex items-baseline gap-4">
            <h1 className="font-mono text-[32px] font-semibold leading-none tracking-tight text-status-info">
              {code}
            </h1>
            <span className="text-[18px] text-text-primary">{stock?.name ?? code}</span>
          </div>
          {/* 实时行情条 */}
          <div className="mt-2 flex items-center gap-3">
            <span className="font-display-numeric text-[28px] font-bold text-text-primary">
              ¥{stock?.price != null ? stock.price.toFixed(2) : (buyPrice > 0 ? buyPrice.toFixed(2) : "—")}
            </span>
            {stock?.change_pct != null && (
              <span className={`font-display-numeric text-[16px] font-medium ${stock.change_pct >= 0 ? "text-[#FF5D5D]" : "text-[#3EE6A8]"}`}>
                {stock.change_pct > 0 ? "+" : ""}{stock.change_pct.toFixed(2)}%
              </span>
            )}
          <span className="text-[12px] text-text-disabled">数据源: {stock?.source ?? "—"}</span>
          </div>
        </div>
        <button onClick={handleToggleWl}
          className={`rounded-lg px-3 py-1.5 text-[12px] font-medium transition-colors ${
            isWatched ? "bg-[rgba(245,196,81,0.15)] text-[#F5C451] hover:bg-[rgba(245,196,81,0.25)]"
            : "border border-border-subtle text-text-disabled hover:border-[#F5C451] hover:text-[#F5C451]"
          }`}>
          {isWatched ? "收藏中" : "添加收藏"}
        </button>
      </header>

      {wlMsg && (
        <div className="mb-4 rounded-xl bg-[rgba(62,230,168,0.1)] border border-[rgba(62,230,168,0.3)] px-4 py-2 text-[13px] text-[#3EE6A8]">{wlMsg}</div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* LEFT: 决策卡 */}
        <section className="col-span-1 glass-strong rounded-2xl p-6">
          <div className="mb-4 flex items-center justify-between">
            <span className="text-[11px] uppercase tracking-wider text-text-disabled">V12 集成决策卡</span>
            <span className="rounded-full bg-[rgba(77,163,255,0.12)] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-status-info border border-[rgba(77,163,255,0.3)]">
              5 模型投票
            </span>
          </div>

          <div className="mb-4 text-center">
            <div className="mb-1 text-[11px] uppercase tracking-wider text-text-disabled">综合评分</div>
            <div className={`font-display-numeric text-[64px] leading-none ${scoreColor(combinedPct)}`}>
              {combinedPct}
            </div>
            <div className="mt-2 text-[12px] text-text-secondary">
              XGBoost <span className="text-text-primary">{modelPct}</span> · 板块热度{" "}
              <span className="text-text-primary">{heatPct}</span>
            </div>
          </div>

          <div className="mb-4 rounded-xl border border-border-subtle bg-surface-card p-3">
            <div className="mb-2 text-[10px] uppercase tracking-wider text-text-disabled">ATR 价格目标</div>
            <div className="space-y-1 text-[13px]">
              <div className="flex items-center justify-between">
                <span className="text-text-disabled">买入价</span>
                <span className="font-display-numeric text-[16px] text-text-primary">¥{buyPrice > 0 ? buyPrice.toFixed(2) : "—"}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-text-disabled">目标价</span>
                <span className="font-display-numeric text-[16px] text-[#3EE6A8]">¥{targetPrice > 0 ? targetPrice.toFixed(2) : "—"}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-text-disabled">止损价</span>
                <span className="font-display-numeric text-[16px] text-[#FF5D5D]">¥{stopPrice > 0 ? stopPrice.toFixed(2) : "—"}</span>
              </div>
            </div>
          </div>

          {targetPrice > 0 && buyPrice > 0 && (
            <div className="mb-4 rounded-xl border border-border-subtle bg-surface-card p-3">
              <div className="mb-2 text-[10px] uppercase tracking-wider text-text-disabled">盈亏比</div>
              <div className="text-[24px] font-semibold text-[#3EE6A8]">
                {((targetPrice - buyPrice) / (buyPrice - stopPrice)).toFixed(2)} : 1
              </div>
            </div>
          )}

          <div className="flex gap-2">
            <button className="flex-1 rounded-lg bg-status-info py-2 text-[13px] font-semibold text-on-primary hover:bg-[#C084FC]">
              加入观察
            </button>
            <button onClick={handleRefresh} className="rounded-lg border border-border-subtle px-4 py-2 text-[13px] text-text-secondary hover:border-status-info hover:text-text-primary">
              刷新
            </button>
          </div>
        </section>

        {/* MIDDLE: 评分详情 */}
        <section className="col-span-1 glass rounded-2xl p-6">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-[16px] font-semibold">评分分解</h2>
            <span className="text-[11px] text-text-disabled">V12 集成</span>
          </div>
          <div className="space-y-4">
            <BarMeter label="XGBoost 概率" value={modelProba} color="#A78BFA" />
              <BarMeter label="板块热度" value={sectorHeat} color="#3EE6A8" />
              <BarMeter
                label="综合评分"
                value={combined}
                color={combined >= 0.8 ? "#3EE6A8" : combined >= 0.7 ? "#F5C451" : "#9FB0C7"}
              />
          </div>
          <p className="mt-6 text-[11px] text-text-disabled">
            综合评分 = 模型概率 × {MODEL_WEIGHT} + 板块热度 × {HEAT_WEIGHT}
            （例：{modelPct}×{MODEL_WEIGHT} + {heatPct}×{HEAT_WEIGHT} ≈ {combinedPct}）。
            <br />
            V12 集成：AUC 0.681, 53 维特征, 2 天持有, 4%+ 目标涨幅。
          </p>
        </section>

        {/* RIGHT: 历史表现 */}
        <section className="col-span-1 space-y-6">
          <div className="glass rounded-2xl p-5">
            <h3 className="mb-3 text-[14px] font-semibold">策略表现</h3>
            <div className="space-y-2 text-[12px] text-text-secondary">
              <div className="flex items-center justify-between">
                <span>Sharpe</span>
                <span className="text-[#3EE6A8] font-semibold">5.16</span>
              </div>
              <div className="flex items-center justify-between">
                <span>累计收益</span>
                <span className="text-[#3EE6A8] font-semibold">+164.4%</span>
              </div>
              <div className="flex items-center justify-between">
                <span>最大回撤</span>
                <span className="text-[#FF5D5D] font-semibold">-6.4%</span>
              </div>
              <div className="flex items-center justify-between">
                <span>正收益期数</span>
                <span className="text-text-primary font-semibold">15/19 (79%)</span>
              </div>
            </div>
            <Link href="/cn" className="mt-4 inline-flex items-center gap-1 text-[12px] text-status-info hover:underline">
              查看全部推荐 →
            </Link>
          </div>

          {stock?.source && (
            <div className="glass rounded-2xl p-5">
              <h3 className="mb-3 text-[14px] font-semibold">数据信息</h3>
              <div className="space-y-1 text-[12px] text-text-secondary">
                <p>数据源: {stock.source}</p>
                <p>符号: {stock.symbol}</p>
              </div>
            </div>
          )}
        </section>
      </div>

      <section className="mt-6 glass rounded-2xl p-6">
        <h2 className="mb-4 text-[16px] font-semibold">关于 V1.9 评分</h2>
        <p className="text-[12px] text-text-secondary leading-relaxed">
          V1.9 多模型集成方案使用 35 维融合特征（量价 + 趋势 + 筹码 + 资金流指标）训练 5 个 XGBoost 模型，
          输出平均概率与板块热度评分加权，最终选出综合评分最高的前 20 只股票。
          持有期 2 天，目标涨幅 4%+，每日全 A 股并行扫描。
          特征矩阵基于新浪日 K 线 + 同花顺板块数据实时计算，辅以 8 Agent 辩论投票系统。
        </p>
      </section>

      <footer className="mt-10 text-center text-[11px] text-text-disabled">
        AlphaPilot 提供 AI 辅助分析，仅供教育用途，非投资建议。
      </footer>
    </main>
  );
}

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

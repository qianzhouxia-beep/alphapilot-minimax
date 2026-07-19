"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { fetchPaperTrading, fetchLiveRecommend, type PaperTradingData, type LiveRecommendResponse, type TradeLogEntry } from "@/lib/cn-api";

export default function PaperTradingPage() {
  const [data, setData] = useState<PaperTradingData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [liveData, setLiveData] = useState<LiveRecommendResponse | null>(null);
  const [lastUpdate, setLastUpdate] = useState<Date>(new Date());

  const load = async () => {
    try {
      const [pt, live] = await Promise.all([
        fetchPaperTrading(),
        fetchLiveRecommend(100, true).catch(() => null),
      ]);
      setData(pt);
      if (live) setLiveData(live);
      setLastUpdate(new Date());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    const id = setInterval(load, 60000); // refresh every 60s
    return () => clearInterval(id);
  }, []);

  if (loading && !data) {
    return (
      <main className="mx-auto max-w-[1440px] px-4 sm:px-6 lg:px-8 py-8 min-h-screen">
        <div className="flex items-center justify-center py-20">
          <div className="h-12 w-12 animate-spin rounded-full border-4 border-border-subtle border-t-status-info"></div>
        </div>
      </main>
    );
  }

  if (error) {
    return (
      <main className="mx-auto max-w-[1440px] px-4 sm:px-6 lg:px-8 py-8 min-h-screen">
        <div className="glass rounded-2xl border border-status-danger p-6">
          <p className="text-sm text-status-danger font-semibold">加载失败</p>
          <p className="mt-2 text-[12px] text-text-secondary">{error}</p>
          <button onClick={load} className="mt-4 rounded-lg bg-status-info px-4 py-2 text-[12px] font-semibold text-text-primary">
            重试
          </button>
        </div>
      </main>
    );
  }

  if (!data) return null;

  const acc = data.account;
  const totalPnlColor = acc.total_pnl_pct >= 0 ? "text-status-danger" : "text-status-success";
  const dailyPnlColor = acc.daily_pnl_pct >= 0 ? "text-status-danger" : "text-status-success";

  return (
    <main className="mx-auto max-w-[1440px] px-4 sm:px-6 lg:px-8 py-4 sm:py-6 lg:py-8 min-h-screen">
      {/* 导航栏 */}
      <div className="mb-6 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Link href="/cn" className="flex items-center gap-1.5 rounded-lg border border-border-subtle bg-surface-panel px-3 py-1.5 text-[12px] text-text-secondary hover:border-status-info hover:text-text-primary transition-colors">
            <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="15 18 9 12 15 6"/>
            </svg>
            返回 A 股
          </Link>
          <div>
            <h1 className="text-[24px] font-semibold text-text-primary flex items-center gap-2">
            <svg className="w-6 h-6 text-status-info" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect x="2" y="3" width="20" height="14" rx="2"/>
              <line x1="8" y1="21" x2="16" y2="21"/>
              <line x1="12" y1="17" x2="12" y2="21"/>
            </svg>
            量化模拟盘
            <span className="tag-badge tag-badge bg-status-info/10 text-status-info border border-status-info/30">Beta</span>
          </h1>
          <p className="mt-1 text-[12px] text-text-disabled">
            V19 Fusion 日频量化 · 尾盘狙击+双策略并行 · 动态止损止盈
          </p>
        </div>
        </div>
        <div className="flex items-center gap-2 text-[11px] text-text-disabled">
          <span className="inline-block w-1.5 h-1.5 rounded-full bg-status-success animate-pulse"></span>
          自动刷新 60s · 最近 {lastUpdate.toLocaleTimeString()}
        </div>
      </div>

      {/* 账户总览 */}
      <section className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 mb-6">
        <KPICard label="总资产" value={`￥${(acc.total_assets / 10000).toFixed(2)}万`} sub={`持仓市值 ${(acc.market_value / 10000).toFixed(2)}万`} color="#A78BFA" />
        <KPICard label="可用现金" value={`￥${(acc.cash / 10000).toFixed(2)}万`} sub={`剩余资金`} color="#3EE6A8" />
        <KPICard label="当日收益" value={`${acc.daily_pnl_pct >= 0 ? "+" : ""}${acc.daily_pnl_pct.toFixed(2)}%`} sub={`今日浮盈`} color={acc.daily_pnl_pct >= 0 ? "#FF5D5D" : "#3EE6A8"} />
        <KPICard label="累计收益" value={`${acc.total_pnl_pct >= 0 ? "+" : ""}${acc.total_pnl_pct.toFixed(2)}%`} sub={`总盈亏 ￥${acc.total_pnl_amount.toFixed(0)}`} color={acc.total_pnl_pct >= 0 ? "#FF5D5D" : "#3EE6A8"} />
        <KPICard label="交易次数" value={`${acc.trade_count}`} sub={`胜率 ${acc.win_rate.toFixed(0)}%`} color="#F5C451" />
        <KPICard label="最大回撤" value={`${acc.max_drawdown.toFixed(2)}%`} sub="风险指标" color={acc.max_drawdown < -10 ? "#FF5D5D" : "#3EE6A8"} />
      </section>

      {/* 策略详情 */}
      <div className="space-y-6">
        {data.strategies.map((strategy) => (
          <StrategyCard key={strategy.id} strategy={strategy} nextExecution={data.next_execution} />
        ))}
      </div>

      {/* 交易记录 */}
      {data.trade_log && data.trade_log.length > 0 && (
        <section className="glass card-lift rounded-2xl p-4 sm:p-6 mt-6">
          <h2 className="text-[18px] font-semibold text-text-primary mb-4 flex items-center gap-2">
            <span className="w-1 h-5 rounded-full bg-status-warning"></span>
            交易记录
          </h2>
          <TradeLogTable tradeLog={data.trade_log} />
        </section>
      )}

      <footer className="mt-10 text-center text-[11px] text-text-disabled">
        AlphaPilot 量化模拟盘仅供参考和教育用途，非投资建议。过往表现不保证未来收益。
      </footer>
    </main>
  );
}

function KPICard({ label, value, sub, color }: { label: string; value: string; sub: string; color: string }) {
  return (
    <div className="glass card-lift rounded-2xl p-4">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-[10px] uppercase tracking-wider text-text-disabled">{label}</span>
        <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: color, boxShadow: `0 0 8px ${color}` }}></span>
      </div>
      <div className="font-display-numeric text-[18px] sm:text-[22px] truncate" style={{ color }}>{value}</div>
      <div className="mt-1 text-[11px] text-text-secondary">{sub}</div>
    </div>
  );
}

function StrategyCard({ strategy, nextExecution }: { strategy: PaperTradingData["strategies"][0]; nextExecution: Record<string, string> }) {
  const pnlColor = (strategy.pnl_pct ?? 0) >= 0 ? "text-status-danger" : "text-status-success";
  return (
    <section className="glass card-lift rounded-2xl p-4 sm:p-6">
      <div className="flex items-center justify-between mb-4">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-[18px] font-semibold text-text-primary">{strategy.name}</h2>
            <span className={`tag-badge tag-badge ${
              strategy.status === "active" ? "bg-[rgba(62,230,168,0.15)] text-status-success" : "bg-text-disabled/20 text-text-disabled"
            }`}>
              {strategy.status === "active" ? "运行中" : "已停止"}
            </span>
          </div>
          <p className="mt-1 text-[12px] text-text-disabled">
            分配 ￥{(strategy.allocated / 10000).toFixed(0)}万 · 已用 ￥{(strategy.used / 10000).toFixed(2)}万 · 可用 ￥{((strategy.allocated - strategy.used) / 10000).toFixed(2)}万
          </p>
        </div>
        <div className="text-right">
          <div className={`font-display-numeric text-[20px] ${pnlColor}`}>
            {(strategy.pnl_pct ?? 0) >= 0 ? "+" : ""}{(strategy.pnl_pct ?? 0).toFixed(2)}%
          </div>
          <div className="text-[11px] text-text-disabled">策略收益</div>
        </div>
      </div>

      {strategy.positions.length > 0 ? (
        <div className="overflow-x-auto">
          <div className="grid grid-cols-[2.5fr_1.5fr_1.5fr_2fr_1.5fr] gap-0 text-[11px] uppercase tracking-wider text-text-disabled border-b border-border-subtle">
            <div className="px-3 py-2.5 font-medium text-left">股票</div>
            <div className="px-3 py-2.5 font-medium text-right">入场价</div>
            <div className="px-3 py-2.5 font-medium text-right">现价</div>
            <div className="px-3 py-2.5 font-medium text-right">盈亏</div>
            <div className="px-3 py-2.5 font-medium text-right">止损</div>
          </div>
          {strategy.positions.map((p) => {
            const pnl = p.pnl_pct || 0;
            const pColor = pnl >= 0 ? "text-status-danger" : "text-status-success";
            return (
              <div key={p.symbol} className="grid grid-cols-[2.5fr_1.5fr_1.5fr_2fr_1.5fr] gap-0 text-[13px] border-b border-border-subtle/30 hover:bg-primary/4 transition-colors">
                <div className="px-3 py-2.5 flex items-center gap-1.5">
                  <span className="font-semibold text-text-primary">{p.name}</span>
                  <span className="text-text-disabled text-[11px]">{p.symbol}</span>
                </div>
                <div className="px-3 py-2.5 text-right font-display-numeric text-text-primary">￥{p.entry_price.toFixed(2)}</div>
                <div className="px-3 py-2.5 text-right font-display-numeric text-status-warning">￥{(p.current_price || p.entry_price).toFixed(2)}</div>
                <div className={`px-3 py-2.5 text-right font-display-numeric ${pColor}`}>
                  {pnl >= 0 ? "+" : ""}{pnl.toFixed(2)}%
                  <div className="text-[10px] text-text-disabled mt-0.5">
                    ￥{p.pnl_amount >= 0 ? "+" : ""}{p.pnl_amount.toFixed(0)}
                  </div>
                </div>
                <div className="px-3 py-2.5 text-right font-display-numeric text-status-danger">￥{p.stop_loss.toFixed(2)}</div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="text-center py-8 text-text-disabled text-[13px]">
          <svg className="w-10 h-10 mx-auto mb-2 opacity-30" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
            <rect x="3" y="3" width="18" height="18" rx="2"/>
            <line x1="9" y1="9" x2="15" y2="9"/>
          </svg>
          暂无可信仓
          <p className="text-[11px] mt-1">下次执行时间: {nextExecution?.[strategy.id] || strategy.id === "v16_daily" ? "每日 14:55 尾盘" : "等待调度"}</p>
        </div>
      )}

      {strategy.signals && strategy.signals.length > 0 && (
        <div className="mt-4 pt-4 border-t border-border-subtle">
          <div className="text-[12px] text-text-disabled mb-2">今日买入信号</div>
          <div className="space-y-1.5">
            {strategy.signals.slice(0, 3).map((s, i) => (
              <div key={i} className="flex items-center justify-between text-[12px] bg-background rounded-lg p-2 border border-border-subtle">
                <div className="flex items-center gap-2 min-w-0">
                  <span className="text-status-danger font-semibold">{s.name}</span>
                  <span className="text-text-disabled">{s.symbol}</span>
                </div>
                <div className="flex items-center gap-3 shrink-0">
                  <span className="text-text-disabled text-[10px] truncate max-w-[240px]">{s.reason}</span>
                  <span className="text-status-success font-display-numeric">￥{s.price.toFixed(2)}</span>
                  <span className="text-text-secondary text-[11px]">×{s.quantity}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}


// ═══ 交易记录表格（合并买入卖出，含盈余/盈亏%）═══
function TradeLogTable({ tradeLog }: { tradeLog: TradeLogEntry[] }) {
  // 按 symbol 分组，同一只股票的买入和卖出配对
  type MergedRow = {
    symbol: string;
    name: string;
    buyLog: TradeLogEntry | null;
    sellLog: TradeLogEntry | null;
    strategyId: string;
  };

  const grouped = new Map<string, MergedRow>();
  // 倒序遍历（最新的在前面）
  for (const log of tradeLog) {
    const key = log.symbol + "|" + log.strategy_id;
    if (!grouped.has(key)) {
      grouped.set(key, { symbol: log.symbol, name: log.name, buyLog: null, sellLog: null, strategyId: log.strategy_id });
    }
    const row = grouped.get(key)!;
    if (log.action === "买入") {
      // 如果已经有 buyLog，说明是新一轮买入，创建新行
      if (row.buyLog) {
        // 已有买入记录，这条作为新行
        const newKey = log.symbol + "|" + log.strategy_id + "|" + log.time;
        grouped.set(newKey, { symbol: log.symbol, name: log.name, buyLog: log, sellLog: null, strategyId: log.strategy_id });
      } else {
        row.buyLog = log;
      }
    } else {
      // 卖出/止损/止盈 — 找到对应的买入行
      if (row.buyLog && !row.sellLog) {
        row.sellLog = log;
      } else {
        // 没有对应买入，单独记录
        const newKey = log.symbol + "|" + log.strategy_id + "|" + log.time;
        grouped.set(newKey, { symbol: log.symbol, name: log.name, buyLog: null, sellLog: log, strategyId: log.strategy_id });
      }
    }
  }

  // 按时间倒序排列（用卖出时间或买入时间）
  const rows = Array.from(grouped.values()).sort((a, b) => {
    const ta = a.sellLog?.time || a.buyLog?.time || "";
    const tb = b.sellLog?.time || b.buyLog?.time || "";
    return tb.localeCompare(ta);
  });

  // 7 列：股票 | 买入价 | 卖出价 | 数量 | 盈余 | 盈亏% | 操作类型
  const gridCols = "grid-cols-[3fr_3fr_3fr_3fr_4fr_4fr_3fr]";

  const fmtTime = (t: string) => {
    if (!t) return "";
    // 取 MM/DD HH:MM
    const parts = t.split(/[ -]/);
    if (parts.length >= 3) return parts[1] + "/" + parts[2] + " " + (parts[3] || "").slice(0, 5);
    return t;
  };

  return (
    <div className="overflow-x-auto">
      {/* Header */}
      <div className={"grid " + gridCols + " gap-0 text-[11px] uppercase tracking-wider text-text-disabled border-b border-border-subtle"}>
        <div className="px-3 py-2.5 font-medium text-left">股票</div>
        <div className="px-3 py-2.5 font-medium text-right">买入价</div>
        <div className="px-3 py-2.5 font-medium text-right">卖出价</div>
        <div className="px-3 py-2.5 font-medium text-right">数量</div>
        <div className="px-3 py-2.5 font-medium text-right">盈余</div>
        <div className="px-3 py-2.5 font-medium text-right">盈亏%</div>
        <div className="px-3 py-2.5 font-medium text-center">操作</div>
      </div>
      {rows.map((row, idx) => {
        const buy = row.buyLog;
        const sell = row.sellLog;
        const hasBuy = !!buy;
        const hasSell = !!sell;
        const buyPrice = buy?.price ?? 0;
        const sellPrice = sell?.price ?? 0;
        const qty = sell?.quantity ?? buy?.quantity ?? 0;
        const costTotal = buyPrice * qty;
        const exitTotal = sellPrice * qty;
        const profitAmt = hasBuy && hasSell ? exitTotal - costTotal : 0;
        const profitPct = hasBuy && hasSell && costTotal > 0 ? ((exitTotal - costTotal) / costTotal * 100) : (sell?.pnl_pct ?? 0);

        // 操作类型标签
        let actionLabel = "—";
        let actionBg = "rgba(148,163,184,0.15)";
        let actionColor = "#94A3B8";
        if (hasBuy && hasSell) {
          if (sell!.action === "止损") {
            actionLabel = "止损卖出";
            actionBg = "rgba(255,93,93,0.15)";
            actionColor = "#FF5D5D";
          } else if (sell!.action === "止盈") {
            actionLabel = "止盈卖出";
            actionBg = "rgba(62,230,168,0.15)";
            actionColor = "#3EE6A8";
          } else {
            actionLabel = "已卖出";
            actionBg = "rgba(62,230,168,0.15)";
            actionColor = "#3EE6A8";
          }
        } else if (hasBuy && !hasSell) {
          actionLabel = "持仓中";
          actionBg = "rgba(245,196,81,0.15)";
          actionColor = "#F5C451";
        } else if (!hasBuy && hasSell) {
          actionLabel = sell!.action;
          actionBg = "rgba(148,163,184,0.15)";
          actionColor = "#94A3B8";
        }

        return (
          <div key={idx} className={"grid " + gridCols + " gap-0 text-[13px] border-b border-border-subtle/30 hover:bg-primary/4 transition-colors"}>
            {/* 股票 */}
            <div className="px-3 py-2.5">
              <div className="flex items-center gap-1.5">
                <span className="font-semibold text-text-primary">{row.name}</span>
                <span className="text-text-disabled text-[11px]">{row.symbol}</span>
              </div>
              <div className="text-[10px] text-text-disabled mt-0.5">
                {buy && <span>买入 {fmtTime(buy.time)}</span>}
                {buy && sell && <span className="mx-1">→</span>}
                {sell && <span>卖出 {fmtTime(sell.time)}</span>}
              </div>
            </div>
            {/* 买入价 */}
            <div className="px-3 py-2.5 text-right font-display-numeric text-status-danger">
              {hasBuy ? "￥" + buyPrice.toFixed(2) : "—"}
            </div>
            {/* 卖出价 */}
            <div className={"px-3 py-2.5 text-right font-display-numeric " + (hasSell ? "text-status-success" : "text-text-disabled")}>
              {hasSell ? "￥" + sellPrice.toFixed(2) : "—"}
            </div>
            {/* 数量 */}
            <div className="px-3 py-2.5 text-right font-display-numeric text-text-secondary">
              {qty > 0 ? qty.toLocaleString() : "—"}
            </div>
            {/* 盈余 */}
            <div className={"px-3 py-2.5 text-right font-display-numeric font-semibold " + (hasBuy && hasSell ? (profitAmt >= 0 ? "text-status-danger" : "text-status-success") : "text-text-disabled")}>
              {hasBuy && hasSell ? (profitAmt >= 0 ? "+" : "") + "￥" + profitAmt.toFixed(2) : "—"}
            </div>
            {/* 盈亏% */}
            <div className={"px-3 py-2.5 text-right font-display-numeric font-semibold " + (hasBuy && hasSell ? (profitPct >= 0 ? "text-status-danger" : "text-status-success") : "text-text-disabled")}>
              {hasBuy && hasSell ? (profitPct >= 0 ? "+" : "") + profitPct.toFixed(2) + "%" : "—"}
            </div>
            {/* 操作类型 */}
            <div className="px-3 py-2.5 text-center">
              <span className="tag-badge" style={{ backgroundColor: actionBg, color: actionColor }}>
                {actionLabel}
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

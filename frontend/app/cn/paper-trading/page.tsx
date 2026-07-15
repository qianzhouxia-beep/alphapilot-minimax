﻿"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { fetchPaperTrading, fetchLiveRecommend, type PaperTradingData, type LiveRecommendResponse } from "@/lib/cn-api";

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
          <button onClick={load} className="mt-4 rounded-lg bg-status-info px-4 py-2 text-[12px] font-semibold text-white">
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
        <KPICard label="总资产" value={`¥${(acc.total_assets / 10000).toFixed(2)}万`} sub={`持仓市值 ${(acc.market_value / 10000).toFixed(2)}万`} color="#A78BFA" />
        <KPICard label="可用现金" value={`¥${(acc.cash / 10000).toFixed(2)}万`} sub={`剩余资金`} color="#3EE6A8" />
        <KPICard label="当日收益" value={`${acc.daily_pnl_pct >= 0 ? "+" : ""}${acc.daily_pnl_pct.toFixed(2)}%`} sub={`今日浮盈`} color={acc.daily_pnl_pct >= 0 ? "#FF5D5D" : "#3EE6A8"} />
        <KPICard label="累计收益" value={`${acc.total_pnl_pct >= 0 ? "+" : ""}${acc.total_pnl_pct.toFixed(2)}%`} sub={`总盈亏 ¥${acc.total_pnl_amount.toFixed(0)}`} color={acc.total_pnl_pct >= 0 ? "#FF5D5D" : "#3EE6A8"} />
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
          <div className="overflow-x-auto">
            <table className="w-full text-left data-table">
              <thead>
                <tr className="border-b border-border-subtle text-[11px] uppercase tracking-wider text-text-disabled">
                  <th className="px-3 py-2.5 font-medium text-left">时间</th>
                  <th className="px-3 py-2.5 font-medium text-left">股票</th>
                  <th className="px-3 py-2.5 font-medium text-center">操作</th>
                  <th className="px-3 py-2.5 font-medium text-right">价格</th>
                  <th className="px-3 py-2.5 font-medium text-right">数量</th>
                </tr>
              </thead>
              <tbody>
                {data.trade_log.slice(0, 20).map((log, i) => (
                  <tr key={i} className="border-b border-border-subtle/30 text-[13px]">
                    <td className="px-3 py-2.5 align-middle text-text-secondary font-mono text-[11px]">{log.time}</td>
                    <td className="px-3 py-2.5 align-middle">
                      <span className="font-semibold text-text-primary">{log.name}</span>
                      <span className="ml-2 text-text-disabled text-[11px]">{log.symbol}</span>
                    </td>
                    <td className="px-3 py-2.5 align-middle text-center">
                      <span className={`tag-badge tag-badge ${
                        log.action === "买入" ? "bg-[rgba(255,93,93,0.15)] text-status-danger" : "bg-[rgba(62,230,168,0.15)] text-status-success"
                      }`}>{log.action}</span>
                    </td>
                    <td className="px-3 py-2.5 align-middle text-right font-display-numeric text-text-primary">¥{log.price.toFixed(2)}</td>
                    <td className="px-3 py-2.5 align-middle text-right font-display-numeric text-text-secondary">{log.quantity}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
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
            分配 ¥{(strategy.allocated / 10000).toFixed(0)}万 · 已用 ¥{(strategy.used / 10000).toFixed(2)}万 · 可用 ¥{((strategy.allocated - strategy.used) / 10000).toFixed(2)}万
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
          <table className="w-full text-left data-table">
            <thead>
              <tr className="border-b border-border-subtle text-[11px] uppercase tracking-wider text-text-disabled">
                <th className="px-3 py-2.5 font-medium text-left">股票</th>
                <th className="px-3 py-2.5 font-medium text-right">入场价</th>
                <th className="px-3 py-2.5 font-medium text-right">现价</th>
                <th className="px-3 py-2.5 font-medium text-right">盈亏</th>
                <th className="px-3 py-2.5 font-medium text-right">止损</th>
              </tr>
            </thead>
            <tbody>
              {strategy.positions.map((p) => {
                const pnl = p.pnl_pct || 0;
                const pColor = pnl >= 0 ? "text-status-danger" : "text-status-success";
                return (
                  <tr key={p.symbol} className="border-b border-border-subtle/30 text-[13px]">
                    <td className="px-3 py-2.5 align-middle">
                      <div className="flex items-center gap-1.5">
                        <span className="font-semibold text-text-primary">{p.name}</span>
                        <span className="text-text-disabled text-[11px]">{p.symbol}</span>
                      </div>
                    </td>
                    <td className="px-3 py-2.5 align-middle text-right font-display-numeric text-text-primary">¥{p.entry_price.toFixed(2)}</td>
                    <td className="px-3 py-2.5 align-middle text-right font-display-numeric text-status-warning">¥{(p.current_price || p.entry_price).toFixed(2)}</td>
                    <td className={`px-3 py-2.5 align-middle text-right font-display-numeric ${pColor}`}>
                      {pnl >= 0 ? "+" : ""}{pnl.toFixed(2)}%
                      <div className="text-[10px] text-text-disabled mt-0.5">
                        ¥{p.pnl_amount >= 0 ? "+" : ""}{p.pnl_amount.toFixed(0)}
                      </div>
                    </td>
                    <td className="px-3 py-2.5 align-middle text-right font-display-numeric text-status-danger">¥{p.stop_loss.toFixed(2)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
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
                  <span className="text-status-success font-display-numeric">¥{s.price.toFixed(2)}</span>
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

// AlphaPilot A 股智能选股 — 展示每日推荐池（05:00 漏斗 + 09:35 盘中资金重排）
"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { HeaderBar } from "@/components/HeaderBar";
import { fetchCNScreener, type ScreenerItem, type ScreenerResponse } from "@/lib/cn-api";

type Row = ScreenerItem & {
  score_pct?: number;
  confidence_score?: number;
  industry?: string | null;
  industry_l1?: string | null;
  live_main_net?: number | null;
  main_net?: number | null;
  money_phase_label?: string | null;
  change_pct?: number | null;
};

function displayScore(item: Row): number {
  if (item.confidence_score != null) return Number(item.confidence_score);
  if (item.score_pct != null && item.score_pct > 1) return Number(item.score_pct);
  const s = Number(item.score || 0);
  return s <= 1.5 ? Math.round(s * 100) : Math.round(s);
}

function fmtYi(v: number | null | undefined): string {
  if (v == null || Number.isNaN(Number(v))) return "—";
  const n = Number(v);
  const yi = n / 1e8;
  if (Math.abs(yi) >= 0.01) return `${yi > 0 ? "+" : ""}${yi.toFixed(2)}亿`;
  return `${n > 0 ? "+" : ""}${(n / 1e4).toFixed(0)}万`;
}

const scoreColor = (s: number) =>
  s >= 90 ? "text-status-success" : s >= 80 ? "text-status-info" : s >= 70 ? "text-status-warning" : "text-text-secondary";

const chgColor = (v: number | null | undefined) =>
  v == null ? "text-text-disabled" : v >= 0 ? "text-status-danger" : "text-status-success";

export default function CNScreener() {
  const [data, setData] = useState<ScreenerResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeSector, setActiveSector] = useState<string | null>(null);

  const loadData = async () => {
    try {
      const d = await fetchCNScreener();
      setData(d);
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
      if (!cancelled) setLoading(false);
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const id = setInterval(loadData, 60_000);
    return () => clearInterval(id);
  }, []);

  // 后端字段是 recommendations，不是 items（此前读错导致一直显示 0 只）
  const items = ((data as any)?.recommendations ?? (data as any)?.items ?? []) as Row[];
  const sectors = Array.from(
    new Set(items.map((i) => i.sector || i.industry || i.industry_l1 || "其他"))
  ).sort();
  const filtered = activeSector
    ? items.filter((i) => (i.sector || i.industry || i.industry_l1 || "其他") === activeSector)
    : items;

  const sourceLabel =
    (data as any)?.morning_live_mode ||
    (data as any)?.pipeline_version ||
    (data as any)?.source ||
    "daily_recommend";

  return (
    <main className="mx-auto max-w-[1440px] px-4 sm:px-6 lg:px-8 py-4 sm:py-6 lg:py-8 min-h-screen">
      <HeaderBar market="cn" />

      <header className="mb-6">
        <Link
          href="/cn"
          className="mb-2 inline-flex items-center gap-1 text-[12px] text-text-secondary hover:text-status-info"
        >
          ← 返回 A 股首页
        </Link>
        <h1 className="text-[28px] font-semibold tracking-tight">A 股智能选股</h1>
        <p className="mt-1 text-[13px] text-text-secondary">
          {items.length} 只 · 推荐池排序 · 数据源: {sourceLabel} · 60s 自动刷新
          {error && <span className="ml-3 text-status-danger font-medium">错误: {error}</span>}
        </p>
        <p className="mt-2 text-[12px] text-text-disabled leading-relaxed max-w-3xl">
          这里展示的是每日漏斗产出的推荐池（凌晨 05:00 评分+门控；交易日 09:35
          用实时资金对池子重排）。不是盘中全市场实时扫票。模拟盘 09:36
          再从池中按资金流入取 Top2 下单。
        </p>
      </header>

      {loading && (
        <div className="flex flex-col items-center justify-center py-20">
          <div className="h-12 w-12 animate-spin rounded-full border-4 border-[#1D2A42] border-t-[#4DA3FF]" />
          <p className="mt-4 text-[14px] text-text-secondary">加载中...</p>
        </div>
      )}

      {!loading && !error && data && items.length === 0 && (
        <div className="glass rounded-2xl p-8 text-center">
          <p className="text-[15px] text-text-primary font-medium mb-2">今日推荐池为空</p>
          <p className="text-[12px] text-text-secondary leading-relaxed">
            常见原因：nuclear 空仓（expo=0）、金叉/资金门后无幸存、或凌晨管线尚未跑完。
            可先看工作台 / 量化模拟的仓位敞口说明。
          </p>
          <button
            onClick={loadData}
            className="mt-4 rounded-lg bg-status-info px-4 py-2 text-[12px] font-semibold text-[#00315b] hover:bg-[#7ddeff]"
          >
            刷新
          </button>
        </div>
      )}

      {!loading && !error && data && items.length > 0 && (
        <>
          <div className="glass rounded-2xl p-4 card-lift mb-6 flex flex-wrap items-center gap-2">
            <span className="text-[11px] uppercase tracking-wider text-text-disabled mr-2">行业</span>
            <button
              onClick={() => setActiveSector(null)}
              className={`rounded-full border px-3 py-1 text-[12px] transition-colors ${
                !activeSector
                  ? "border-status-info bg-status-info/15 text-status-info"
                  : "border-border-subtle bg-surface-panel text-text-secondary hover:border-status-info hover:text-text-primary"
              }`}
            >
              全部 ({items.length})
            </button>
            {sectors.map((s) => (
              <button
                key={s}
                onClick={() => setActiveSector(s)}
                className={`rounded-full border px-3 py-1 text-[12px] transition-colors ${
                  activeSector === s
                    ? "border-status-info bg-status-info/15 text-status-info"
                    : "border-border-subtle bg-surface-panel text-text-secondary hover:border-status-info hover:text-text-primary"
                }`}
              >
                {s} ({items.filter((i) => (i.sector || i.industry || i.industry_l1 || "其他") === s).length})
              </button>
            ))}
          </div>

          <section className="data-table grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {filtered.map((item, idx) => {
              const sc = displayScore(item);
              const sector = item.sector || item.industry || item.industry_l1 || "—";
              const net = item.live_main_net ?? item.main_net;
              const phase = item.money_phase_label || item.money_phase || "—";
              return (
                <Link
                  key={item.symbol}
                  href={`/cn/stock?symbol=${String(item.symbol).replace(/\D/g, "").slice(-6)}`}
                  className="glass card-lift block rounded-2xl p-5 transition-all hover:border-status-info/30"
                >
                  <div className="mb-3 flex items-start justify-between">
                    <div>
                      <div className="text-[10px] text-text-disabled mb-0.5">#{idx + 1}</div>
                      <div className="font-mono text-[18px] font-semibold text-status-info">
                        {String(item.symbol).replace(/\D/g, "").slice(-6)}
                      </div>
                      <div className="mt-0.5 text-[12px] text-text-secondary">{item.name}</div>
                    </div>
                    <div className={`font-display-numeric text-[32px] leading-none ${scoreColor(sc)}`}>
                      {sc}
                    </div>
                  </div>
                  <div className="mb-3 flex items-center justify-between text-[11px]">
                    <span className="text-text-secondary truncate max-w-[55%]">{sector}</span>
                    <span className={`font-display-numeric font-medium ${chgColor(item.change_pct)}`}>
                      {item.change_pct != null
                        ? `${item.change_pct > 0 ? "+" : ""}${Number(item.change_pct).toFixed(2)}%`
                        : "—"}
                    </span>
                  </div>
                  <div className="flex items-center justify-between border-t border-border-subtle pt-3 text-[11px]">
                    <span className="text-text-secondary truncate max-w-[50%]">{phase}</span>
                    <span
                      className={`font-mono ${
                        net != null && Number(net) >= 0 ? "text-status-danger" : "text-status-success"
                      }`}
                    >
                      {fmtYi(net)}
                    </span>
                  </div>
                </Link>
              );
            })}
          </section>
        </>
      )}

      {!loading && error && (
        <div className="glass rounded-2xl border border-status-danger p-8 text-center">
          <p className="text-status-danger font-semibold mb-2">后端未连接</p>
          <p className="text-[12px] text-text-secondary mb-4">{error}</p>
          <button
            onClick={loadData}
            className="rounded-lg bg-status-info px-4 py-2 text-[12px] font-semibold text-[#00315b] hover:bg-[#7ddeff]"
          >
            重试
          </button>
        </div>
      )}

      <footer className="mt-10 text-center text-[11px] text-text-disabled">
        AlphaPilot 提供 AI 辅助分析,仅供教育用途,非投资建议。
      </footer>
    </main>
  );
}

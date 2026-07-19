// AlphaPilot A 股 Screener (2026-06-30)
// 替换 M2 mock 25 只, 调后端 /v1/cn/screener/top, 行业筛选, 60s 自动刷新

"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { HeaderBar } from "@/components/HeaderBar";
import { fetchCNScreener, type ScreenerItem, type ScreenerResponse } from "@/lib/cn-api";

const sectorStyles: Record<string, string> = {
  "白酒": "text-status-warning", "银行": "text-status-success", "保险": "text-status-success",
  "新能源": "text-status-info", "新能源车": "text-status-info", "光伏": "text-status-info",
  "医药": "text-status-success", "医疗器械": "text-status-success", "家电": "text-status-info",
  "食品饮料": "text-text-secondary", "旅游零售": "text-status-info", "AI": "text-status-info",
  "消费电子": "text-status-info", "券商": "text-status-warning", "石油石化": "text-status-danger",
  "农牧": "text-status-success",
};

const RISK_ZH = { low: "低", medium: "中", high: "高" } as const;
const MAIN_FORCE_ZH: Record<string, string> = {
  accumulation: "吸筹", markup: "拉升", distribution: "出货",
  washout: "洗盘", reaccumulation: "二次吸筹",
  bull_trap: "诱多", bear_trap: "诱空",
};

const scoreColor = (s: number) =>
  s >= 90 ? "text-status-success" : s >= 80 ? "text-status-info" : s >= 70 ? "text-status-warning" : "text-text-secondary";

const riskStyles = (r: ScreenerItem["risk"]) => {
  switch (r) {
    case "low":
      return "bg-status-success/12 text-status-success border border-status-success/30";
    case "medium":
      return "bg-status-warning/12 text-status-warning border border-status-warning/30";
    case "high":
      return "bg-status-danger/12 text-status-danger border border-status-danger/30";
  }
};

export default function CNScreener() {
  const [data, setData] = useState<ScreenerResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeSector, setActiveSector] = useState<string | null>(null);

  const loadData = async () => {
    try {
      const d = await fetchCNScreener(100);
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
    return () => { cancelled = true; };
  }, []);

  // 60s 自动刷新
  useEffect(() => {
    const id = setInterval(loadData, 60_000);
    return () => clearInterval(id);
  }, []);

  const items = data?.items ?? [];
  const sectors = Array.from(new Set(items.map((i) => i.sector ?? "其他"))).sort();
  const filtered = activeSector ? items.filter((i) => (i.sector ?? "其他") === activeSector) : items;

  return (
    <main className="mx-auto max-w-[1440px] px-4 sm:px-6 lg:px-8 py-4 sm:py-6 lg:py-8 min-h-screen">
      <HeaderBar market="cn" />

      <header className="mb-6">
        <Link href="/cn" className="mb-2 inline-flex items-center gap-1 text-[12px] text-text-secondary hover:text-status-info">
          ← 返回 A 股首页
        </Link>
        <h1 className="text-[28px] font-semibold tracking-tight">A 股智能选股</h1>
        <p className="mt-1 text-[13px] text-text-secondary">
          {items.length} 只 A 股 AI 评分排序 · 数据源: {data?.source ?? "—"} · 60s 自动刷新
          {error && <span className="ml-3 text-status-danger font-medium">错误: {error}</span>}
        </p>
      </header>

      {loading && (
        <div className="flex flex-col items-center justify-center py-20">
          <div className="h-12 w-12 animate-spin rounded-full border-4 border-[#1D2A42] border-t-[#4DA3FF]"></div>
          <p className="mt-4 text-[14px] text-text-secondary">加载中...</p>
        </div>
      )}

      {!loading && !error && data && (
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
                {s} ({items.filter((i) => (i.sector ?? "其他") === s).length})
              </button>
            ))}
          </div>

          <section className="data-table grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {filtered.map((item) => (
              <Link
                key={item.symbol}
                href={`/cn/stock/${item.symbol}`}
                className={`glass card-lift block rounded-2xl p-5 transition-all hover:border-status-info/30 ${
                  item.sector && sectorStyles[item.sector] ? "" : ""
                }`}
              >
                <div className="mb-3 flex items-start justify-between">
                  <div>
                    <div className="font-mono text-[18px] font-semibold text-status-info">
                      {item.symbol.replace(/\..*/, "")}
                    </div>
                    <div className="mt-0.5 text-[12px] text-text-secondary">{item.name}</div>
                  </div>
                  <div className={`font-display-numeric text-[36px] ${scoreColor(item.score)}`}>
                    {item.score}
                  </div>
                </div>
                <div className="mb-3 flex items-center justify-between text-[11px]">
                  <span className={`uppercase tracking-wider ${sectorStyles[item.sector ?? ""] ?? "text-text-disabled"}`}>
                    {item.sector}
                  </span>
                  <span className="text-text-secondary">
                    上涨 <span className="text-text-primary font-display-numeric">{item.up_probability}%</span>
                  </span>
                </div>
                <div className="flex items-center justify-between border-t border-border-subtle pt-3 text-[11px]">
                  <span className="text-text-secondary">{MAIN_FORCE_ZH[item.main_force]}</span>
                  <span
                    className={
                      item.risk === "low"
                        ? "text-status-success"
                        : item.risk === "medium"
                          ? "text-status-warning"
                          : "text-status-danger"
                    }
                  >
                    {RISK_ZH[item.risk]} 风险
                  </span>
                </div>
              </Link>
            ))}
          </section>
        </>
      )}

      {!loading && error && (
        <div className="glass rounded-2xl border border-status-danger p-8 text-center">
          <p className="text-status-danger font-semibold mb-2">后端未连接</p>
          <p className="text-[12px] text-text-secondary mb-4">{error}</p>
          <button onClick={loadData} className="rounded-lg bg-status-info px-4 py-2 text-[12px] font-semibold text-[#00315b] hover:bg-[#7ddeff]">
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

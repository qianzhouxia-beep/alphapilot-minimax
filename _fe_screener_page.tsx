// AlphaPilot A 股 Screener (2026-06-30)
// 替换 M2 mock 25 只, 调后端 /v1/cn/screener/top, 行业筛选, 60s 自动刷新

"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { HeaderBar } from "@/components/HeaderBar";
import { fetchCNScreener, type ScreenerItem, type ScreenerResponse } from "@/lib/cn-api";

const sectorStyles: Record<string, string> = {
  "白酒": "text-[#F5C451]", "银行": "text-[#35e0a3]", "保险": "text-[#35e0a3]",
  "新能源": "text-[#4DA3FF]", "新能源车": "text-[#4DA3FF]", "光伏": "text-[#4DA3FF]",
  "医药": "text-[#3EE6A8]", "医疗器械": "text-[#3EE6A8]", "家电": "text-[#7ddeff]",
  "食品饮料": "text-[#9FB0C7]", "旅游零售": "text-[#7ddeff]", "AI": "text-[#4DA3FF]",
  "消费电子": "text-[#4DA3FF]", "券商": "text-[#F5C451]", "石油石化": "text-[#FF5D5D]",
  "农牧": "text-[#3EE6A8]",
};

const RISK_ZH = { low: "低", medium: "中", high: "高" } as const;
const MAIN_FORCE_ZH: Record<string, string> = {
  accumulation: "吸筹", markup: "拉升", distribution: "出货",
  washout: "洗盘", reaccumulation: "二次吸筹",
  bull_trap: "诱多", bear_trap: "诱空",
};

const scoreColor = (s: number) =>
  s >= 90 ? "text-[#3EE6A8]" : s >= 80 ? "text-[#4DA3FF]" : s >= 70 ? "text-[#F5C451]" : "text-[#9FB0C7]";

const riskStyles = (r: ScreenerItem["risk"]) => {
  switch (r) {
    case "low":
      return "bg-[rgba(62,230,168,0.12)] text-[#3EE6A8] border border-[rgba(62,230,168,0.3)]";
    case "medium":
      return "bg-[rgba(245,196,81,0.12)] text-[#F5C451] border border-[rgba(245,196,81,0.3)]";
    case "high":
      return "bg-[rgba(255,93,93,0.12)] text-[#FF5D5D] border border-[rgba(255,93,93,0.3)]";
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
        <Link href="/cn" className="mb-2 inline-flex items-center gap-1 text-[12px] text-[#9FB0C7] hover:text-[#4DA3FF]">
          ← 返回 A 股首页
        </Link>
        <h1 className="text-[28px] font-semibold tracking-tight">A 股智能选股</h1>
        <p className="mt-1 text-[13px] text-[#9FB0C7]">
          {items.length} 只 A 股 AI 评分排序 · 数据源: {data?.source ?? "—"} · 60s 自动刷新
          {error && <span className="ml-3 text-[#FF5D5D]">⚠ {error}</span>}
        </p>
      </header>

      {loading && (
        <div className="flex flex-col items-center justify-center py-20">
          <div className="h-12 w-12 animate-spin rounded-full border-4 border-[#1D2A42] border-t-[#4DA3FF]"></div>
          <p className="mt-4 text-[14px] text-[#9FB0C7]">加载中...</p>
        </div>
      )}

      {!loading && !error && data && (
        <>
          <div className="mb-6 flex flex-wrap items-center gap-2">
            <span className="text-[11px] uppercase tracking-wider text-[#6E7C93] mr-2">行业</span>
            <button
              onClick={() => setActiveSector(null)}
              className={`rounded-full border px-3 py-1 text-[12px] transition-colors ${
                !activeSector
                  ? "border-[#4DA3FF] bg-[rgba(77,163,255,0.15)] text-[#4DA3FF]"
                  : "border-[#1D2A42] bg-[#0C1728] text-[#9FB0C7] hover:border-[#4DA3FF] hover:text-[#EAF2FF]"
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
                    ? "border-[#4DA3FF] bg-[rgba(77,163,255,0.15)] text-[#4DA3FF]"
                    : "border-[#1D2A42] bg-[#0C1728] text-[#9FB0C7] hover:border-[#4DA3FF] hover:text-[#EAF2FF]"
                }`}
              >
                {s} ({items.filter((i) => (i.sector ?? "其他") === s).length})
              </button>
            ))}
          </div>

          <section className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {filtered.map((item) => (
              <Link
                key={item.symbol}
                href={`/cn/stock/${item.symbol}`}
                className={`glass card-lift block rounded-2xl p-5 transition-all hover:border-[rgba(77,163,255,0.3)] ${
                  item.sector && sectorStyles[item.sector] ? "" : ""
                }`}
              >
                <div className="mb-3 flex items-start justify-between">
                  <div>
                    <div className="font-mono text-[18px] font-semibold text-[#4DA3FF]">
                      {item.symbol.replace(/\..*/, "")}
                    </div>
                    <div className="mt-0.5 text-[12px] text-[#9FB0C7]">{item.name}</div>
                  </div>
                  <div className={`font-display-numeric text-[36px] ${scoreColor(item.score)}`}>
                    {item.score}
                  </div>
                </div>
                <div className="mb-3 flex items-center justify-between text-[11px]">
                  <span className={`uppercase tracking-wider ${sectorStyles[item.sector ?? ""] ?? "text-[#6E7C93]"}`}>
                    {item.sector}
                  </span>
                  <span className="text-[#9FB0C7]">
                    上涨 <span className="text-[#EAF2FF] font-display-numeric">{item.up_probability}%</span>
                  </span>
                </div>
                <div className="flex items-center justify-between border-t border-[#1D2A42] pt-3 text-[11px]">
                  <span className="text-[#9FB0C7]">{MAIN_FORCE_ZH[item.main_force]}</span>
                  <span
                    className={
                      item.risk === "low"
                        ? "text-[#3EE6A8]"
                        : item.risk === "medium"
                          ? "text-[#F5C451]"
                          : "text-[#FF5D5D]"
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
        <div className="glass rounded-2xl border border-[#FF5D5D] p-8 text-center">
          <p className="text-[#FF5D5D] font-semibold mb-2">后端未连接</p>
          <p className="text-[12px] text-[#9FB0C7] mb-4">{error}</p>
          <button onClick={loadData} className="rounded-lg bg-[#4DA3FF] px-4 py-2 text-[12px] font-semibold text-[#00315b] hover:bg-[#7ddeff]">
            重试
          </button>
        </div>
      )}

      <footer className="mt-10 text-center text-[11px] text-[#6E7C93]">
        AlphaPilot 提供 AI 辅助分析,仅供教育用途,非投资建议。
      </footer>
    </main>
  );
}

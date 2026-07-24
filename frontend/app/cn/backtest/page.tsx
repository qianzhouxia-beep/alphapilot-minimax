// AlphaPilot A 股回测工具 (2026-07-09)
// - Top N 回测 + 指定股票回测（支持代码/名称/拼音搜索）
"use client";

import { useEffect, useState, useMemo, useCallback, useRef } from "react";
import { HeaderBar } from "@/components/HeaderBar";
import {
  fetchCNScreener, postCNBacktest, postStockBacktest, searchStocksPinyin,
  type ScreenerItem, type ScreenerResponse, type BacktestResponse, type BacktestItem,
  type StockSearchResult, type StockBacktestResponse,
} from "@/lib/cn-api";

// ---------- types ----------
type BacktestConfig = { startDate: string; endDate: string; holdingDays: number; topN: number; minScore: number };

type BacktestResult = {
  stockResults: {
    symbol: string; name: string; score: number | null; actualReturn: number | null;
    win: boolean | null; entry_date?: string; exit_date?: string; entry_price?: number; exit_price?: number;
  }[];
  totalReturn: number; winRate: number; avgReturn: number; maxReturn: number; minReturn: number;
  positiveCount: number; negativeCount: number; method: string; warning?: string;
};

function mapTopNBacktest(resp: BacktestResponse): BacktestResult {
  const stockResults = resp.results.map((r: BacktestItem) => ({
    symbol: r.symbol, name: r.name, score: r.score,
    actualReturn: r.return, win: r.win,
    entry_date: r.entry_date, exit_date: r.exit_date, entry_price: r.entry_price, exit_price: r.exit_price,
  }));
  const k = resp.kpi ?? {};
  return {
    stockResults, method: "Top N 回测", warning: resp.warning,
    totalReturn: k.avg_return ?? 0, winRate: k.win_rate ?? 0, avgReturn: k.avg_return ?? 0,
    maxReturn: k.max_return ?? 0, minReturn: k.min_return ?? 0,
    positiveCount: k.positive_count ?? 0, negativeCount: k.negative_count ?? 0,
  };
}

function mapStockBacktest(resp: StockBacktestResponse): BacktestResult {
  const stockResults = resp.results.map((r) => ({
    symbol: r.symbol, name: r.name, score: r.score,
    actualReturn: r.return, win: r.win,
    entry_date: r.entry_date, exit_date: r.exit_date, entry_price: r.entry_price, exit_price: r.exit_price,
  }));
  const k = resp.kpi ?? {};
  return {
    stockResults, method: resp.method,
    totalReturn: k.avg_return ?? 0, winRate: k.win_rate ?? 0, avgReturn: k.avg_return ?? 0,
    maxReturn: k.max_return ?? 0, minReturn: k.min_return ?? 0,
    positiveCount: k.positive_count ?? 0, negativeCount: k.negative_count ?? 0,
  };
}

// ---------- component ----------
export default function BacktestPage() {
  const [data, setData] = useState<ScreenerResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 模式
  const [mode, setMode] = useState<"topn" | "stock">("topn");

  // Top N 配置
  const [cfg, setCfg] = useState<BacktestConfig>({
    startDate: "2026-06-01", endDate: "2026-07-06", holdingDays: 2, topN: 10, minScore: 0.6,
  });

  // 指定股票回测
  const [searchKw, setSearchKw] = useState("");
  const [searchResults, setSearchResults] = useState<StockSearchResult[]>([]);
  const [showDropdown, setShowDropdown] = useState(false);
  const [selectedStocks, setSelectedStocks] = useState<StockSearchResult[]>([]);
  const searchTimer = useRef<ReturnType<typeof setTimeout>>();
  const [stockCfg, setStockCfg] = useState({ startDate: "2026-06-01", endDate: "2026-07-06", holdingDays: 2 });

  // 结果
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [ran, setRan] = useState(false);
  const [sortField, setSortField] = useState<"score" | "actualReturn">("actualReturn");
  const [sortAsc, setSortAsc] = useState(false);

  // 加载数据
  useEffect(() => {
    (async () => {
      try { setData(await fetchCNScreener()); } catch { /* optional */ }
    })();
  }, []);

  // 拼音搜索
  const handleSearch = useCallback((kw: string) => {
    setSearchKw(kw);
    if (kw.length < 1) { setSearchResults([]); setShowDropdown(false); return; }
    if (searchTimer.current) clearTimeout(searchTimer.current);
    searchTimer.current = setTimeout(async () => {
      try {
        const res = await searchStocksPinyin(kw);
        setSearchResults(res.results || []);
        setShowDropdown(res.results?.length > 0);
      } catch { setSearchResults([]); setShowDropdown(false); }
    }, 200);
  }, []);

  const addStock = (s: StockSearchResult) => {
    if (selectedStocks.find(x => x.symbol === s.symbol)) return;
    setSelectedStocks(prev => [...prev, s]);
    setSearchKw(""); setSearchResults([]); setShowDropdown(false);
  };

  const removeStock = (sym: string) => {
    setSelectedStocks(prev => prev.filter(x => x.symbol !== sym));
  };

  // 运行回测
  const handleRun = async () => {
    setLoading(true); setError(null);
    try {
      if (mode === "topn") {
        const resp = await postCNBacktest({
          startDate: cfg.startDate, endDate: cfg.endDate,
          holdingDays: cfg.holdingDays, topN: cfg.topN, minScore: cfg.minScore,
        });
        setResult(mapTopNBacktest(resp));
      } else {
        if (selectedStocks.length === 0) {
          setError("请至少选择一只股票"); setLoading(false); return;
        }
        const resp = await postStockBacktest({
          symbols: selectedStocks.map(s => s.symbol),
          startDate: stockCfg.startDate, endDate: stockCfg.endDate,
          holdingDays: stockCfg.holdingDays,
        });
        setResult(mapStockBacktest(resp));
      }
      setRan(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  const handleSort = (field: "score" | "actualReturn") => {
    if (sortField === field) { setSortAsc(!sortAsc); return; }
    setSortField(field); setSortAsc(field === "actualReturn");
  };

  const sortedResults = useMemo(() => {
    if (!result) return [];
    const list = [...result.stockResults];
    list.sort((a, b) => {
      const av = a[sortField] ?? -Infinity;
      const bv = b[sortField] ?? -Infinity;
      return sortAsc ? av - bv : bv - av;
    });
    return list;
  }, [result, sortField, sortAsc]);

  return (
    <main className="mx-auto max-w-[1440px] px-4 sm:px-6 lg:px-8 py-4 sm:py-6 lg:py-8 min-h-screen">
      <HeaderBar market="cn" />

      <div className="mb-6">
        <h1 className="text-[28px] font-bold text-text-primary">选股回测工具</h1>
        <p className="mt-1 text-[13px] text-text-secondary">基于真实历史 K 线模拟持有期收益</p>
      </div>

      {error && (
        <div className="glass mb-6 rounded-2xl border border-[#FF5D5D] p-4">
          <p className="text-[13px] text-status-danger">{error}</p>
        </div>
      )}

      {ran && result?.method === "Top N 回测" && (
        <div className="mb-6 rounded-2xl border border-[#F5C451] bg-[rgba(245,196,81,0.08)] p-4">
          <div className="flex items-start gap-3">
            <span className="text-status-warning text-[16px] font-bold">!</span>
            <div>
              <p className="text-[13px] font-semibold text-status-warning">前视偏差提醒</p>
              <p className="mt-1 text-[12px] text-text-secondary">
                回测使用今日评分选择股票后回溯历史 K 线，存在前视偏差，结果仅供参考。
                建议使用「指定股票回测」模式验证特定标的。
              </p>
            </div>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        {/* ── 左侧配置面板 ── */}
        <section className="lg:col-span-1">
          <div className="glass card-lift rounded-2xl p-5 space-y-5">
            <h2 className="text-[16px] font-semibold text-text-primary">回测配置</h2>

            {/* 模式切换 */}
            <div className="flex rounded-lg border border-border-subtle overflow-hidden">
              <button onClick={() => { setMode("topn"); setRan(false); }}
                className={`flex-1 py-2 text-[12px] font-medium transition-colors ${
                  mode === "topn"
                    ? "bg-status-info text-on-primary"
                    : "bg-surface-panel text-text-disabled hover:text-text-primary"
                }`}>Top N</button>
              <button onClick={() => { setMode("stock"); setRan(false); }}
                className={`flex-1 py-2 text-[12px] font-medium transition-colors ${
                  mode === "stock"
                    ? "bg-status-info text-on-primary"
                    : "bg-surface-panel text-text-disabled hover:text-text-primary"
                }`}>指定股票</button>
            </div>

            {/* Top N 配置 */}
            {mode === "topn" && (
              <>
                <div>
                  <label className="block text-[12px] text-text-secondary mb-1.5">持有天数</label>
                  <select value={cfg.holdingDays} onChange={e => setCfg({...cfg, holdingDays: Number(e.target.value)})}
                    className="w-full rounded-lg border border-border-subtle bg-surface-panel px-3 py-2 text-[13px] text-text-primary outline-none focus:border-status-info">
                    {[1,2,3,5,7,10,14,21].map(d => <option key={d} value={d}>{d} 天</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-[12px] text-text-secondary mb-1.5">选取前 N 只</label>
                  <select value={cfg.topN} onChange={e => setCfg({...cfg, topN: Number(e.target.value)})}
                    className="w-full rounded-lg border border-border-subtle bg-surface-panel px-3 py-2 text-[13px] text-text-primary outline-none focus:border-status-info">
                    {[5,10,15,20,30,50].map(n => <option key={n} value={n}>Top {n}</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-[12px] text-text-secondary mb-1.5">最低评分: {(cfg.minScore * 100).toFixed(0)}</label>
                  <input type="range" min={0.3} max={0.9} step={0.05} value={cfg.minScore}
                    onChange={e => setCfg({...cfg, minScore: Number(e.target.value)})}
                    className="w-full accent-[#A78BFA]" />
                  <div className="flex justify-between text-[11px] text-text-disabled mt-1">
                    <span>30</span><span>90</span>
                  </div>
                </div>
                <div className="rounded-xl bg-[rgba(245,196,81,0.08)] border border-[#F5C451]/30 p-3">
                  <p className="text-[11px] text-status-warning">
                    此模式使用今日评分筛选后回溯历史，存在前视偏差，结果仅供参考
                  </p>
                </div>
              </>
            )}

            {/* 指定股票配置 */}
            {mode === "stock" && (
              <>
                <div className="relative">
                  <label className="block text-[12px] text-text-secondary mb-1.5">
                    搜索股票（代码/名称/拼音首字母）
                  </label>
                  <input value={searchKw} onChange={e => handleSearch(e.target.value)}
                    placeholder="如 002979 / 茅台 / zgd"
                    className="w-full rounded-lg border border-border-subtle bg-surface-panel px-3 py-2 text-[13px] text-text-primary outline-none placeholder:text-text-disabled focus:border-status-info" />
                  {showDropdown && searchResults.length > 0 && (
                    <div className="absolute z-50 mt-1 w-full rounded-xl border border-border-subtle bg-surface-panel shadow-2xl max-h-48 overflow-y-auto">
                      {searchResults.map(s => (
                        <button key={s.symbol} onClick={() => addStock(s)}
                          className="w-full flex items-center gap-3 px-3 py-2.5 text-left hover:bg-[rgba(77,163,255,0.1)] transition-colors">
                          <span className="text-[13px] font-semibold text-text-primary">{s.name}</span>
                          <span className="text-[11px] text-status-info font-mono">{s.symbol}</span>
                          <span className="text-[10px] text-text-disabled ml-auto">{s.pinyin}</span>
                        </button>
                      ))}
                    </div>
                  )}
                </div>

                {selectedStocks.length > 0 && (
                  <div>
                    <label className="block text-[12px] text-text-secondary mb-1.5">
                      已选 {selectedStocks.length} 只
                    </label>
                    <div className="flex flex-wrap gap-1.5">
                      {selectedStocks.map(s => (
                        <span key={s.symbol}
                          className="inline-flex items-center gap-1 rounded-full border border-border-subtle bg-surface-panel px-2.5 py-1 text-[12px] text-text-primary">
                          {s.name}
                          <span className="text-[10px] text-text-disabled">{s.symbol}</span>
                          <button onClick={() => removeStock(s.symbol)}
                            className="ml-0.5 text-status-danger hover:text-[#ff7a7a] text-[14px] leading-none">×</button>
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                <div>
                  <label className="block text-[12px] text-text-secondary mb-1.5">持有天数</label>
                  <select value={stockCfg.holdingDays}
                    onChange={e => setStockCfg({...stockCfg, holdingDays: Number(e.target.value)})}
                    className="w-full rounded-lg border border-border-subtle bg-surface-panel px-3 py-2 text-[13px] text-text-primary outline-none focus:border-status-info">
                    {[1,2,3,5,7,10,14,21].map(d => <option key={d} value={d}>{d} 天</option>)}
                  </select>
                </div>
              </>
            )}

            {/* 日期 */}
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-[12px] text-text-secondary mb-1.5">开始</label>
                <input type="date" value={mode === "topn" ? cfg.startDate : stockCfg.startDate}
                  onChange={e => mode === "topn"
                    ? setCfg({...cfg, startDate: e.target.value})
                    : setStockCfg({...stockCfg, startDate: e.target.value})}
                  className="w-full rounded-lg border border-border-subtle bg-surface-panel px-3 py-2 text-[13px] text-text-primary outline-none focus:border-status-info" />
              </div>
              <div>
                <label className="block text-[12px] text-text-secondary mb-1.5">结束</label>
                <input type="date" value={mode === "topn" ? cfg.endDate : stockCfg.endDate}
                  onChange={e => mode === "topn"
                    ? setCfg({...cfg, endDate: e.target.value})
                    : setStockCfg({...stockCfg, endDate: e.target.value})}
                  className="w-full rounded-lg border border-border-subtle bg-surface-panel px-3 py-2 text-[13px] text-text-primary outline-none focus:border-status-info" />
              </div>
            </div>

            {/* 执行按钮 */}
            <button onClick={handleRun}
              disabled={loading || (mode === "stock" && selectedStocks.length === 0)}
              className="w-full rounded-xl bg-gradient-to-r from-status-info to-[#35e0a3] px-4 py-3 text-[14px] font-bold text-background hover:shadow-lg hover:shadow-[#A78BFA]/50 transition-all disabled:opacity-50 disabled:cursor-not-allowed">
              {loading ? "计算中..." : "运行回测"}
            </button>
          </div>
        </section>

        {/* ── 右侧结果 ── */}
        <section className="lg:col-span-3 space-y-6">
          {/* KPI */}
          {ran && result && (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
              <KpiCard label="平均收益" value={`${result.avgReturn > 0 ? "+" : ""}${result.avgReturn}%`}
                accent={result.avgReturn >= 0 ? "#3EE6A8" : "#FF5D5D"} />
              <KpiCard label="胜率" value={`${result.winRate}%`}
                accent={result.winRate >= 50 ? "#3EE6A8" : "#F5C451"} />
              <KpiCard label="最高收益" value={`${result.maxReturn > 0 ? "+" : ""}${result.maxReturn}%`} accent="#A78BFA" />
              <KpiCard label="最低收益" value={`${result.minReturn > 0 ? "+" : ""}${result.minReturn}%`}
                accent={result.minReturn >= 0 ? "#3EE6A8" : "#FF5D5D"} />
            </div>
          )}

          {/* 收益分布 */}
          {ran && result && result.stockResults.length > 0 && (
            <div className="glass card-lift rounded-2xl p-5">
              <h3 className="text-[14px] font-semibold text-text-primary mb-4">
                收益分布 {result.method && <span className="text-[11px] text-text-disabled font-normal">· {result.method}</span>}
              </h3>
              <ResultChart results={result.stockResults} />
            </div>
          )}

          {/* 表格 */}
          <div className="glass card-lift rounded-2xl p-5">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-[14px] font-semibold text-text-primary">
                {ran ? "回测明细" : mode === "topn" ? "可选股票池" : "选择股票开始回测"}
              </h3>
              {ran && result && (
                <span className="text-[11px] text-text-disabled">共 {result.stockResults.length} 只</span>
              )}
            </div>

            {loading ? (
              <div className="flex items-center justify-center py-16">
                <div className="h-10 w-10 animate-spin rounded-full border-4 border-border-subtle border-t-[#A78BFA]" />
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="data-table w-full text-left">
                  <thead>
                    <tr className="border-b border-border-subtle text-[11px] uppercase tracking-wider text-text-disabled">
                      <th className="px-3 py-3 font-medium">#</th>
                      <th className="px-3 py-3 font-medium">代码</th>
                      <th className="px-3 py-3 font-medium">名称</th>
                      {!ran && <th className="px-3 py-3 text-right font-medium">评分</th>}
                      {ran && (
                        <>
                          <th className="px-3 py-3 text-right font-medium cursor-pointer hover:text-text-primary"
                            onClick={() => handleSort("actualReturn")}>
                            收益 {sortField === "actualReturn" ? (sortAsc ? "↑" : "↓") : ""}
                          </th>
                          <th className="px-3 py-3 text-right font-medium">买入价</th>
                          <th className="px-3 py-3 text-right font-medium">卖出价</th>
                          <th className="px-3 py-3 text-center font-medium">结果</th>
                        </>
                      )}
                    </tr>
                  </thead>
                  <tbody>
                    {(ran ? sortedResults : (data?.recommendations || []).slice(0, 50)).map((item: any, i: number) => (
                      <tr key={item.symbol} className="border-b border-border-subtle/50 hover:bg-[rgba(77,163,255,0.04)]">
                        <td className="px-3 py-3 text-[12px] text-text-disabled">{i + 1}</td>
                        <td className="px-3 py-3 font-mono text-[13px] font-semibold text-status-info">
                          {item.symbol.replace(/^(sh|sz)/i, "")}
                        </td>
                        <td className="px-3 py-3 text-[13px] text-text-primary">{item.name}</td>
                        {!ran && (
                          <td className={`px-3 py-3 text-right text-[18px] font-semibold ${
                            item.score >= 0.75 ? "text-status-success" : item.score >= 0.65 ? "text-status-warning" : "text-text-secondary"
                          }`}>{item.score != null ? item.score.toFixed(1) : '—'}</td>
                        )}
                        {ran && (
                          <>
                            <td className={`px-3 py-3 text-right text-[14px] font-semibold ${
                              item.actualReturn == null ? "text-text-secondary"
                                : item.actualReturn >= 0 ? "text-status-success" : "text-status-danger"
                            }`}>
                              {item.actualReturn == null ? "无数据" : `${item.actualReturn > 0 ? "+" : ""}${item.actualReturn}%`}
                            </td>
                            <td className="px-3 py-3 text-right text-[13px] text-text-primary font-mono">
                              {item.entry_price != null ? "¥" + item.entry_price.toFixed(2) : "—"}
                            </td>
                            <td className="px-3 py-3 text-right text-[13px] text-text-primary font-mono">
                              {item.exit_price != null ? "¥" + item.exit_price.toFixed(2) : "—"}
                            </td>
                            <td className="px-3 py-3 text-center">
                              <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] ${
                                item.win ? "bg-[rgba(62,230,168,0.12)] text-status-success"
                                  : item.win === false ? "bg-[rgba(255,93,93,0.12)] text-status-danger"
                                  : "bg-[rgba(159,176,199,0.12)] text-text-secondary"
                              }`}>
                                {item.win ? "盈利" : item.win === false ? "亏损" : "—"}
                              </span>
                            </td>
                          </>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </section>
      </div>

      <footer className="mt-10 text-center text-[11px] text-text-disabled">
        AlphaPilot 提供 AI 辅助分析，仅供教育用途，非投资建议。
      </footer>
    </main>
  );
}

// ---------- sub-components ----------
function KpiCard({ label, value, accent }: { label: string; value: string; accent: string }) {
  return (
    <div className="glass card-lift rounded-2xl p-5">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-[11px] uppercase tracking-wider text-text-disabled">{label}</span>
        <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: accent, boxShadow: `0 0 8px ${accent}` }} />
      </div>
      <div className="font-display-numeric text-[28px] leading-none" style={{ color: accent }}>{value}</div>
    </div>
  );
}

function ResultChart({ results }: { results: { symbol: string; actualReturn: number | null; win: boolean | null }[] }) {
  const valid = results.filter((r): r is { symbol: string; actualReturn: number; win: boolean | null } => r.actualReturn != null);
  if (valid.length === 0) return <p className="text-[12px] text-text-disabled text-center py-8">暂无有效数据</p>;
  const barW = Math.max(12, Math.min(40, 520 / Math.max(valid.length, 1)));
  const maxAbs = Math.max(Math.abs(Math.min(...valid.map(r => r.actualReturn))), Math.abs(Math.max(...valid.map(r => r.actualReturn))), 1);
  const chartH = 180;

  return (
    <div className="relative" style={{ height: chartH + 40 }}>
      <div className="absolute left-0 top-0 bottom-8 w-10 flex flex-col justify-between text-[10px] text-text-disabled">
        <span>+{maxAbs.toFixed(0)}%</span>
        <span>0%</span>
        <span>-{maxAbs.toFixed(0)}%</span>
      </div>
      <div className="ml-12 mr-2 flex items-end gap-1" style={{ height: chartH }}>
        {valid.map((r, i) => {
          const h = Math.abs(r.actualReturn) / maxAbs * (chartH - 20);
          return (
            <div key={i} className="relative flex flex-col items-center justify-end flex-1">
              <div className="w-full rounded-t-sm transition-all duration-300"
                style={{ height: Math.max(h, 2), backgroundColor: r.win ? "rgba(62,230,168,0.6)" : "rgba(255,93,93,0.6)" }}
                title={`${r.symbol}: ${r.actualReturn > 0 ? "+" : ""}${r.actualReturn.toFixed(1)}%`} />
            </div>
          );
        })}
      </div>
      <div className="ml-12 mr-2 border-t border-border-subtle relative" style={{ top: -16 }} />
    </div>
  );
}
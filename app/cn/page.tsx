// AlphaPilot A 股 Dashboard — V15 真实筹码模型 (2026-07-09)
// Zeabur HTTPS -> cn_proxy.py -> 腾讯云 150.158.100.236
// 2026-07-13: 60秒轮询 /recommend/live 实时资金流（盘中阶段标签实时刷新）
"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import Link from "next/link";
import { HeaderBar } from "@/components/HeaderBar";
import {
  fetchCNScreener, fetchWatchlist, addToWatchlist, removeFromWatchlist,
  fetchCategorizedRecommend, fetchLiveRecommend,
  type ScreenerItem, type ScreenerResponse, type WatchlistItem,
  type CategorizedResponse,
} from "@/lib/cn-api";

const scoreColor = (s: number) =>
  s >= 0.50 ? "text-[#3EE6A8]" : s >= 0.40 ? "text-status-info" : s >= 0.30 ? "text-[#F5C451]" : "text-text-secondary";
const displayScore = (s: number) => Math.min(99, Math.max(75, Math.round(s * 45 + 75)));
const scoreLabel = (s: number) =>
  s >= 0.50 ? "A+" : s >= 0.35 ? "A" : s >= 0.25 ? "B+" : "B";

export default function CNDashboard() {
  const [data, setData] = useState<ScreenerResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [watchlistSymbols, setWatchlistSymbols] = useState<Set<string>>(new Set());
  const [wlData, setWlData] = useState<WatchlistItem[]>([]);
  const [wlLoading, setWlLoading] = useState<Record<string, boolean>>({});
  const [wlMsg, setWlMsg] = useState<{ type: string; text: string } | null>(null);
  const [catData, setCatData] = useState<CategorizedResponse | null>(null);
  const [catLoading, setCatLoading] = useState(true);
  const [priceDialog, setPriceDialog] = useState<{ item: any; price: string } | null>(null);
  const [priceDialogLoading, setPriceDialogLoading] = useState(false);
  // 实时状态标记
  const [liveTs, setLiveTs] = useState<number>(0);
  const [livePolling, setLivePolling] = useState<boolean>(false);

  const loadData = async () => {
    try {
      const [d, wl, cat] = await Promise.all([fetchCNScreener(), fetchWatchlist(), fetchCategorizedRecommend()]);
      setData(d);
      setWlData(wl.watchlist || []);
      setWatchlistSymbols(new Set((wl.watchlist || []).map((w: WatchlistItem) => w.symbol)));
      setCatData(cat);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  
  useEffect(() => {
            })}
          </div>
        ) : (
          <div className="flex items-center gap-2 rounded-lg bg-surface-container-low px-3 py-2 border border-border-subtle">
            <svg className="w-4 h-4 text-text-disabled" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
            <p className="text-[12px] text-text-disabled">页面加载后 5 秒自动生成 · 过滤涨停股 · 资金+模型综合评分 Top 3</p>
          </div>
        )}
      </section>

      <section className="mb-6">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-1 h-6 rounded-full bg-[#3EE6A8]"></div>
          <h2 className="text-[18px] font-semibold text-text-primary">自我进化学习</h2>
          <span className="text-[10px] px-2 py-0.5 rounded-full bg-[rgba(62,230,168,0.12)] text-[#3EE6A8] border border-[rgba(62,230,168,0.25)]">AI 驱动</span>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 sm:gap-3">
          <div className="glass rounded-2xl p-4 card-lift border-t-2 border-t-[#A78BFA]">
            <svg className="w-6 h-6 mb-1 text-status-info" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg>
            <h3 className="text-[14px] font-semibold text-text-primary mb-1">自动历史回撤</h3>
            <p className="text-[11px] text-text-disabled leading-relaxed">
              每日 Top 5 推荐自动记录，T+1/T+3 涨跌幅自动追踪，生成完整回测数据库
            </p>
          </div>
          <div className="glass rounded-2xl p-4 card-lift border-t-2 border-t-[#3EE6A8]">
            <div className="text-[24px] mb-1">📊</div>
            <h3 className="text-[14px] font-semibold text-text-primary mb-1">胜率自动统计</h3>
            <p className="text-[11px] text-text-disabled leading-relaxed">
              收藏夹自动计算胜率/平均收益，数据驱动而非感觉驱动
            </p>
          </div>
          <div className="glass rounded-2xl p-4 card-lift border-t-2 border-t-[#F5C451]">
            <svg className="w-6 h-6 mb-1 text-[#F5C451]" viewBox="0 0 24 24" fill="currentColor" stroke="none"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
            <h3 className="text-[14px] font-semibold text-text-primary mb-1">门控参数优化</h3>
            <p className="text-[11px] text-text-disabled leading-relaxed">
              基于历史数据自动调整首板洗盘/量比换手门控参数，持续提升准确率
            </p>
          </div>
        </div>
      </section>

      <footer className="mt-10 text-center text-[11px] text-text-disabled">
        AlphaPilot 提供 AI 辅助分析，仅供教育用途，非投资建议。过往表现不保证未来收益。
        <br />
        A 股内容仅供在美华人教育用途，非中国境内投顾服务。
      </footer>

      {priceDialog && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/50 backdrop-blur-sm"
          onClick={() => !priceDialogLoading && setPriceDialog(null)}>
          <div className="w-[90vw] max-w-[380px] rounded-2xl border border-border-subtle bg-surface-card p-6 shadow-2xl mx-4"
            onClick={e => e.stopPropagation()}>
            <div className="flex items-center gap-2 mb-1"><svg className="w-5 h-5 text-[#F5C451]" viewBox="0 0 24 24" fill="currentColor" stroke="none"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg><h3 className="text-[18px] font-semibold text-text-primary">添加收藏</h3></div>
            <p className="text-[13px] text-text-secondary mb-4">
              {priceDialog.item.name} · {priceDialog.item.symbol?.replace(/^(sh|sz)/, "")}
            </p>
            <label className="block mb-1 text-[12px] text-text-disabled">买入价格（¥）</label>
            <input
              type="number"
              step="0.01"
              min="0.01"
              value={priceDialog.price}
              onChange={e => setPriceDialog(prev => prev ? { ...prev, price: e.target.value } : null)}
              className="w-full rounded-lg border border-border-subtle bg-background px-3 py-2.5 text-[16px] text-text-primary font-mono outline-none focus:border-status-info transition-colors"
              placeholder="输入买入价"
              autoFocus
              disabled={priceDialogLoading}
            />
            <div className="mt-4 flex gap-2">
              <button onClick={() => setPriceDialog(null)} disabled={priceDialogLoading}
                className="flex-1 rounded-lg border border-border-subtle bg-background py-2.5 text-[13px] text-text-secondary hover:border-status-info hover:text-text-primary transition-colors disabled:opacity-50">
                取消
              </button>
              <button onClick={confirmAddWatchlist} disabled={priceDialogLoading}
                className="flex-1 rounded-lg bg-status-info py-2.5 text-[13px] font-semibold text-on-primary hover:bg-[#C084FC] transition-colors disabled:opacity-50 flex items-center justify-center gap-2">
                {priceDialogLoading ? <span className="h-4 w-4 animate-spin rounded-full border-2 border-[#00315b] border-t-transparent" /> : null}
                {priceDialogLoading ? "添加中..." : "确认添加"}
              </button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}

function KPI({ label, value, sub, accent }: { label: string; value: string; sub: string; accent: string }) {
  const isBest = label === "今日最佳";
  return (
    <div className={`glass card-lift rounded-2xl p-4 ${isBest ? "border border-[rgba(62,230,168,0.2)]" : ""}`}>
      <div className="mb-2 flex items-center justify-between">
        <span className="text-[10px] uppercase tracking-wider text-text-disabled">{label}</span>
        <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: accent, boxShadow: `0 0 8px ${accent}` }}></span>
      </div>
      <div className="font-display-numeric text-[20px] sm:text-[26px] truncate" style={{ color: accent }}>
        {value}
      </div>
      <div className="mt-1 text-[11px] text-text-secondary">{sub}</div>
    </div>
  );
}

function PhaseIcon({ phaseKey, color, size = 24 }: { phaseKey: string; color: string; size?: number }) {
  const s: any = { width: size, height: size, viewBox: "0 0 24 24", fill: "none", stroke: color, strokeWidth: 2, strokeLinecap: "round", strokeLinejoin: "round" };
  switch (phaseKey) {
    case "markup": return <svg {...s}><path d="M12 21V5"/><polyline points="5 12 12 5 19 12"/><line x1="12" y1="5" x2="12" y2="7"/></svg>;
    case "rightside_ambush": return <svg {...s}><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="4"/><circle cx="12" cy="12" r="1.5" fill={color}/><line x1="12" y1="1" x2="12" y2="4"/><line x1="12" y1="20" x2="12" y2="23"/><line x1="1" y1="12" x2="4" y2="12"/><line x1="20" y1="12" x2="23" y2="12"/></svg>;
    case "accumulation_end": return <svg {...s}><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>;
    case "bear_trap": return <svg {...s}><polyline points="4 20 12 6 20 20"/><circle cx="12" cy="4" r="2.5" fill={color} stroke="none"/><line x1="12" y1="20" x2="12" y2="12"/></svg>;
    case "accumulation": return <svg {...s}><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 9 12 14 17 9"/><line x1="12" y1="14" x2="12" y2="2"/></svg>;
    case "suspicious": return <svg {...s}><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><circle cx="12" cy="16" r="0.5" fill={color}/><line x1="12" y1="9" x2="12" y2="13"/></svg>;
    case "distribution": return <svg {...s}><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="14"/></svg>;
    case "pullback": return <svg {...s}><path d="M21 17c-4 5-11 5-15 2S2 10 3 6"/><polyline points="7 13 3 10 7 7"/></svg>;
    case "sideways": return <svg {...s}><polyline points="3 10 7 14 12 10 17 14 21 10"/><polyline points="3 14 7 10 12 14 17 10 21 14"/></svg>;
    default: return <svg {...s}><circle cx="12" cy="12" r="8"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>;
  }
}

const PHASE_COLORS: Record<string, string> = {
  bear_trap: "#8B5CF6",
  rightside_ambush: "#F59E0B",
  accumulation_end: "#10B981",
  markup: "#EF4444",
  accumulation: "#3B82F6",
  suspicious: "#F97316",
  distribution: "#DC2626",
  pullback: "#6B7280",
  sideways: "#9CA3AF",
};

const PHASE_GROUPS = [
  { key: "buy_signal", label: "买入信号", desc: "主力资金正在运作，关注买入机会", color: "#EF4444", phases: ["markup", "rightside_ambush", "accumulation_end", "bear_trap"] },
  { key: "accumulation_watch", label: "吸筹观察", desc: "主力在低位默默吸筹", color: "#3B82F6", phases: ["accumulation"] },
  { key: "risk_warning", label: "风险警告", desc: "警惕回调或出货风险", color: "#F97316", phases: ["suspicious", "distribution"] },
  { key: "wait_and_see", label: "暂时观望", desc: "方向不明或回调中", color: "#6B7280", phases: ["pullback", "sideways"] }
];

function GroupCard({ group, categories, watchlistSymbols, wlLoading, onToggleWatchlist, sectorChanges }: {
  group: typeof PHASE_GROUPS[0];
  categories: Record<string, any>;
  watchlistSymbols: Set<string>;
  wlLoading: Record<string, boolean>;
  onToggleWatchlist: (item: any) => void;
  sectorChanges: Record<string, number>;
}) {
  const phaseLabels: Record<string, string> = {
    markup: "拉升", rightside_ambush: "右侧潜伏", accumulation_end: "吸筹末期",
    bear_trap: "诱空陷阱", accumulation: "吸筹",
    suspicious: "诱多嫌疑", distribution: "出货",
    pullback: "回调", sideways: "震荡"
  };
  const totalCount = group.phases.reduce((sum, pk) => sum + ((categories[pk]?.stocks?.length) || 0), 0);
  return (
    <div className="glass rounded-2xl p-4 card-lift flex flex-col transition-all min-h-[320px]"
      style={{ borderLeftColor: group.color, borderLeftWidth: 3 }}>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <PhaseIcon phaseKey={group.phases[0]} color={group.color} size={22} />
          <div>
            <h3 className="text-[16px] font-semibold text-text-primary">{group.label}</h3>
            <p className="text-[11px] text-text-disabled">{group.desc} · {totalCount} 只</p>
          </div>
        </div>
        {totalCount > 0 && (
          <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-[rgba(245,196,81,0.15)] text-[#F5C451] border border-[rgba(245,196,81,0.3)] font-medium animate-pulse">
            今日有数据
          </span>
        )}
      </div>
      <div className="space-y-3 flex-1">
        {group.phases.map(pk => {
          const cat = categories[pk];
          const stocks = cat?.stocks || [];
          const subColor = PHASE_COLORS[pk] || "#6E7C93";
          return (
            <div key={pk}>
              <div className="flex items-center gap-1.5 mb-1.5 px-1">
                <PhaseIcon phaseKey={pk} color={subColor} size={16} />
                <span className="text-[12px] font-medium" style={{ color: subColor }}>
                  {phaseLabels[pk] || pk}
                </span>
                <span className="text-[10px] text-text-disabled">({stocks.length} 只)</span>
                {stocks.length > 0 && (
                  <span className="text-[8px] px-1 py-0.5 rounded-sm bg-[rgba(245,196,81,0.12)] text-[#F5C451] font-medium">热</span>
                )}
              </div>
              {stocks.length === 0 ? (
                <p className="text-[11px] text-[#4A5568] px-1 py-1.5 italic">暂无标的</p>
              ) : (
                <div className="space-y-1 overflow-x-auto -mx-2 px-2">
                  {stocks.slice(0, 5).map((s: any, i: number) => {
                    const sym = s.symbol.replace(/^(sh|sz)/, "");
                    const isFav = watchlistSymbols.has(sym);
                    const isWlLoading = wlLoading[sym] ?? false;
                    const price = s.price || s.buy_price || 0;
                    const chg = s.change_pct;
                    const chgStr = chg != null ? `${chg > 0 ? "+" : ""}${chg.toFixed(1)}%` : "—";
                    const chgColor = chg != null ? (chg >= 0 ? "text-[#FF5D5D]" : "text-[#3EE6A8]") : "text-text-disabled";
                    const scChg = s.sector_change_pct ?? (s.sector ? sectorChanges[s.sector] : null);
                    return (
                      <div key={s.symbol} className="grid grid-cols-[16px_1fr_38px_48px] sm:grid-cols-[20px_1fr_42px_55px_70px] lg:grid-cols-[22px_1fr_42px_1fr_85px_70px_26px] items-center rounded-lg bg-surface-container-low p-1.5 hover:bg-[#16202f] transition-colors group gap-1">
                        <span className="text-[11px] text-text-disabled font-display-numeric text-center">{i + 1}</span>
                        <Link href={`/cn/stock?symbol=${s.symbol}`} className="flex items-center gap-1 min-w-0 overflow-hidden">
                          <span className="text-[13px] font-medium text-text-primary group-hover:text-status-info truncate transition-colors">{s.name}</span>
                          <span className="text-[10px] text-text-disabled shrink-0">{sym}</span>
                        </Link>
                        <span className="font-display-numeric text-[11px] font-bold text-center" style={{color: displayScore(s.score_raw || s.score) > 85 ? "#3EE6A8" : displayScore(s.score_raw || s.score) > 80 ? "#A78BFA" : "#9FB0C7"}}>
                          {displayScore(s.score_raw || s.score)}
                        </span>
                        <div className="hidden sm:flex items-center gap-1 min-w-0 overflow-hidden">
                          {s.sector ? (
                            <span className="inline-flex items-center gap-1.5 text-[10px] px-1.5 py-0.5 rounded-full bg-[rgba(77,163,255,0.1)] text-status-info border border-[rgba(77,163,255,0.2)] leading-none shrink-0">
                              <span className="truncate max-w-[55px] sm:max-w-[65px]">{s.sector}</span>
                              {scChg != null && (
                                <span className={`shrink-0 ${scChg >= 0 ? "text-[#FF5D5D]" : "text-[#3EE6A8]"}`}>
                                  {scChg > 0 ? "+" : ""}{scChg.toFixed(1)}%
                                </span>
                              )}
                            </span>
                          ) : (
                            <span className="text-[11px] text-[#4A5568]">—</span>
                          )}
                        </div>
                        <span className="hidden sm:block font-display-numeric text-[12px] text-text-primary text-right">
                          {price > 0 ? price.toFixed(2) : "—"}
                        </span>
                        <span className={`font-display-numeric text-[12px] font-medium text-right ${chgColor}`}>
                          {chgStr}
                        </span>
                        <button
                          onClick={(e) => { e.stopPropagation(); onToggleWatchlist(s); }}
                          disabled={isWlLoading}
                          className={`hidden sm:block text-[14px] text-center transition-colors disabled:opacity-50 ${
                            isFav ? "text-[#F5C451]" : "text-text-disabled hover:text-[#F5C451]"
                          }`}>
                          {isWlLoading ? "..." : isFav ? "★" : "☆"}
                        </button>
                      </div>
                    );
                  })}
                  {stocks.length > 5 && (
                    <p className="text-[11px] text-status-info text-right pr-1">+{stocks.length - 5} 只更多</p>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

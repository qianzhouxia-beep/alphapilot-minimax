'use client';

// 资金阶段分类卡片 — 新版 v3 设计 (2026-07-13)
// 左侧信号色条 · 子阶段标签 · 对仗排版 · SVG 收藏

import Link from "next/link";

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

const phaseLabels: Record<string, string> = {
  markup: "拉升", rightside_ambush: "右侧潜伏", accumulation_end: "吸筹末期",
  bear_trap: "诱空陷阱", accumulation: "吸筹",
  suspicious: "诱多嫌疑", distribution: "出货",
  pullback: "回调", sideways: "震荡"
};

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

export const PHASE_GROUPS = [
  { key: "buy_signal", label: "买入信号", desc: "主力资金正在运作", color: "#EF4444", phases: ["markup", "rightside_ambush", "accumulation_end", "bear_trap"] },
  { key: "accumulation_watch", label: "吸筹观察", desc: "主力在低位默默吸筹", color: "#3B82F6", phases: ["accumulation"] },
  { key: "risk_warning", label: "风险警告", desc: "警惕回调或出货风险", color: "#F97316", phases: ["suspicious", "distribution"] },
  { key: "wait_and_see", label: "暂时观望", desc: "方向不明或回调中", color: "#6B7280", phases: ["pullback", "sideways"] },
];

export default function PhaseGroupCard({
  group, categories, watchlistSymbols, wlLoading, onToggleWatchlist, sectorChanges
}: {
  group: typeof PHASE_GROUPS[0];
  categories: Record<string, any>;
  watchlistSymbols: Set<string>;
  wlLoading: Record<string, boolean>;
  onToggleWatchlist: (item: any) => void;
  sectorChanges: Record<string, number>;
}) {
  const totalCount = group.phases.reduce((sum, pk) => sum + ((categories[pk]?.stocks?.length) || 0), 0);

  return (
    <div
      className="phase-group glass rounded-2xl p-4 min-h-[280px]"
      style={{ borderLeftColor: group.color }}
    >
      {/* 头部 */}
      <div className="phase-group-header">
        <div className="flex items-center gap-2">
          <PhaseIcon phaseKey={group.phases[0]} color={group.color} size={20} />
          <div>
            <h3 className="text-[15px] font-semibold text-[#EAF2FF]">{group.label}</h3>
            <p className="text-[11px] text-[#6E7C93]">{group.desc} · {totalCount} 只</p>
          </div>
        </div>
      </div>

      {/* 子阶段标签 */}
      <div className="phase-sub-tags">
        {group.phases.map(pk => {
          const cat = categories[pk];
          const sc = PHASE_COLORS[pk] || "#6E7C93";
          const cnt = cat?.stocks?.length || 0;
          return (
            <span
              key={pk}
              className="phase-sub-tag"
              style={{ color: sc, background: `${sc}18` }}
            >
              {phaseLabels[pk] || pk} ({cnt})
            </span>
          );
        })}
      </div>

      <div className="phase-divider" />

      {/* 股票列表 */}
      <div className="space-y-0.5 flex-1">
        {group.phases.map(pk => {
          const stocks = (categories[pk]?.stocks || []).slice(0, 5);
          if (stocks.length === 0) return null;
          return stocks.map((s: any, i: number) => {
            const sym = s.symbol.replace(/^(sh|sz)/, "");
            const isFav = watchlistSymbols.has(sym);
            const isWlLoading = wlLoading[sym] ?? false;
            const price = s.price || s.buy_price || 0;
            const chg = s.change_pct;
            const chgStr = chg != null ? `${chg > 0 ? "+" : ""}${chg.toFixed(1)}%` : "—";
            const chgColor = chg != null ? (chg >= 0 ? "text-[#FF5D5D]" : "text-[#3EE6A8]") : "text-[#6E7C93]";
            return (
              <div key={s.symbol} className="phase-stock-row">
                <div className="phase-stock-row-left">
                  <span className="phase-stock-rank">#{i + 1}</span>
                  <Link
                    href={`/cn/stock?symbol=${s.symbol}`}
                    className="phase-stock-name hover:text-[#4DA3FF] transition-colors"
                  >
                    {s.name}
                  </Link>
                  <span className="phase-stock-code">{sym}</span>
                </div>
                <div className="phase-stock-row-right">
                  {s.sector && <span className="phase-stock-sector-tag">{s.sector}</span>}
                  <span className="phase-stock-price">¥{price > 0 ? price.toFixed(2) : "—"}</span>
                  <span className={`phase-stock-change ${chgColor}`}>{chgStr}</span>
                  <button
                    onClick={(e) => { e.stopPropagation(); onToggleWatchlist(s); }}
                    disabled={isWlLoading}
                    className="phase-star-btn"
                    title="收藏"
                  >
                    {isWlLoading ? "..." : (
                      <svg width="11" height="11" viewBox="0 0 24 24" fill={isFav ? "currentColor" : "none"} stroke="currentColor" strokeWidth="2">
                        <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
                      </svg>
                    )}
                  </button>
                </div>
              </div>
            );
          });
        })}

        {/* 更多提示 */}
        {(() => {
          const totalInView = group.phases.reduce((sum, pk) => sum + Math.min((categories[pk]?.stocks?.length) || 0, 5), 0);
          const totalStocks = group.phases.reduce((sum, pk) => sum + ((categories[pk]?.stocks?.length) || 0), 0);
          const more = totalStocks - totalInView;
          return more > 0 ? (
            <p className="text-[11px] text-[#4DA3FF] text-right pt-1 pr-1">+{more} 只更多</p>
          ) : null;
        })()}
      </div>
    </div>
  );
}

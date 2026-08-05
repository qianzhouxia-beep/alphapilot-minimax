"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/lib/auth";
import { fetchPaperTrading, fetchLiveRecommend, type PaperTradingData, type LiveRecommendResponse, type TradeLogEntry } from "@/lib/cn-api";

export default function PaperTradingPage() {
  const { session, ready, openAuth } = useAuth();
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
      const msg = e instanceof Error ? e.message : String(e);
      if (/\b401\b|未登录/.test(msg)) {
        openAuth("login", "/cn/paper-trading");
        return;
      }
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!ready) return;
    if (!session) {
      openAuth("login", "/cn/paper-trading");
      return;
    }
    load();
    const id = setInterval(load, 60000);
    return () => clearInterval(id);
  }, [ready, session, openAuth]);

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
    const needLogin = /\b401\b|未登录/.test(error);
    return (
      <main className="mx-auto max-w-[1440px] px-4 sm:px-6 lg:px-8 py-8 min-h-screen">
        <div className={`glass rounded-2xl border p-6 ${needLogin ? "border-status-warning" : "border-status-danger"}`}>
          <p className={`text-sm font-semibold ${needLogin ? "text-status-warning" : "text-status-danger"}`}>
            {needLogin ? "请先登录后查看模拟盘" : "加载失败"}
          </p>
          {!needLogin && <p className="mt-2 text-[12px] text-text-secondary">{error}</p>}
          <div className="mt-4 flex gap-2">
            {needLogin ? (
              <button
                type="button"
                onClick={() => openAuth("login", "/cn/paper-trading")}
                className="rounded-lg bg-status-info px-4 py-2 text-[12px] font-semibold text-white"
              >
                去登录
              </button>
            ) : (
              <button onClick={load} className="rounded-lg bg-status-info px-4 py-2 text-[12px] font-semibold text-text-primary">
                重试
              </button>
            )}
          </div>
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
            <span className="inline-flex items-center rounded-full px-2.5 py-0.5 text-[11px] font-semibold tracking-wide bg-status-info/10 text-status-info border border-status-info/25">
              Beta
            </span>
          </h1>
          <p className="mt-1 text-[12px] text-text-disabled">
            日频模拟交易 · 尾盘机会 · 盘中风控
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

      {/* 策略详情：日频独立；尾盘狙击策略 + S2 合并同一板块 */}
      <div className="space-y-6">
        {groupStrategies(data.strategies).map((group) => (
          <StrategyGroupCard
            key={group.key}
            group={group}
            nextExecution={data.next_execution}
            accountCash={Number(acc.cash || 0)}
            accountEquity={Number(acc.total_assets || (acc.cash || 0) + (acc.market_value || 0))}
            capitalMode={
              (data as any).capital_mode ||
              group.strategies.find((s: any) => s.capital_mode)?.capital_mode ||
              "shared"
            }
          />
        ))}
      </div>

      {/* 交易记录 */}
      {data.trade_log && data.trade_log.length > 0 && (
        <section className="glass card-lift rounded-2xl p-4 sm:p-6 mt-6">
          <div className="mb-4 flex items-center justify-between gap-3">
            <h2 className="text-[18px] font-semibold text-text-primary flex items-center gap-2">
              <span className="w-1 h-5 rounded-full bg-status-warning"></span>
              交易记录
            </h2>
            <span className="text-[11px] text-text-disabled">按周归类 · 与收藏历史一致</span>
          </div>
          <TradeLogTable
            tradeLog={data.trade_log}
            heldSymbols={new Set(
              (data.strategies || []).flatMap((s) =>
                (s.positions || []).map((p) => p.symbol).filter(Boolean)
              )
            )}
          />
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

/** 尾盘相关策略合并展示（eod_sniper / s2_eod） */
const EOD_STRATEGY_IDS = new Set(["eod_sniper", "s2_eod", "eod_s2"]);

type StrategyGroup = {
  key: string;
  title: string;
  subtitle: string;
  strategies: PaperTradingData["strategies"];
  merged: boolean;
};

function groupStrategies(strategies: PaperTradingData["strategies"]): StrategyGroup[] {
  const eod: PaperTradingData["strategies"] = [];
  const others: PaperTradingData["strategies"] = [];
  for (const s of strategies) {
    const id = (s.id || "").toLowerCase();
    const name = s.name || "";
    if (
      EOD_STRATEGY_IDS.has(id) ||
      name.includes("尾盘狙击") ||
      name.includes("S2尾盘") ||
      name.includes("S2 尾盘")
    ) {
      eod.push(s);
    } else {
      others.push(s);
    }
  }
  const groups: StrategyGroup[] = others.map((s) => ({
    key: s.id,
    title:
      s.id === "v19_daily" || /VM2\.5|v19|模型 Top/i.test(s.name || "")
        ? "日频精选"
        : s.name,
    subtitle: "",
    strategies: [s],
    merged: false,
  }));
  if (eod.length > 0) {
    groups.push({
      key: "eod_group",
      title: "尾盘狙击",
      subtitle: "",
      strategies: eod,
      merged: true,
    });
  }
  return groups;
}

function StrategyGroupCard({
  group,
  nextExecution,
  accountCash = 0,
  accountEquity = 0,
  capitalMode,
}: {
  group: StrategyGroup;
  nextExecution: Record<string, string> | string;
  accountCash?: number;
  accountEquity?: number;
  capitalMode?: string;
}) {
  const strategies = group.strategies;
  // 默认共用账户现金；仅明确 split 时才走旧「分配/可用」
  const shared = capitalMode !== "split";
  const used = strategies.reduce((a, s) => a + (s.used || 0), 0);
  // 策略展示名：对外不暴露内部模型代号
  const title =
    group.key === "v19_daily" || /VM2\.5|v19/i.test(group.title)
      ? "日频精选"
      : group.title;
const positions = strategies.flatMap((s) =>
  (s.positions || []).map((p) => ({ ...p, _strategyId: s.id, _strategyName: s.name }))
);
const signals = strategies.flatMap((s) =>
  (s.signals || []).map((sig) => ({ ...sig, _strategyName: s.name }))
);
// 买入成交方式徽标
const ENTRY_MODE_LABEL: Record<string, string> = {
  vwap_dip: "低吸·VWAP回踩",
  hybrid_relax: "低吸·放宽",
  force_eod: "尾盘现价",
  direct: "信号价",
};
  const active = strategies.some((s) => s.status === "active");
  // 按已用资金加权策略收益；无持仓时取均值
  const weightedPnl = (() => {
    const withUsed = strategies.filter((s) => (s.used || 0) > 0);
    if (withUsed.length === 0) {
      const vals = strategies.map((s) => s.pnl_pct ?? 0);
      return vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : 0;
    }
    const sumUsed = withUsed.reduce((a, s) => a + s.used, 0);
    return withUsed.reduce((a, s) => a + (s.pnl_pct ?? 0) * s.used, 0) / sumUsed;
  })();
  const pnlColor = weightedPnl >= 0 ? "text-status-danger" : "text-status-success";
  const nextMap = typeof nextExecution === "string" ? {} : nextExecution || {};
  const nextHint =
    nextMap["s2_eod"] ||
    nextMap["eod_sniper"] ||
    nextMap[strategies[0]?.id] ||
    (typeof nextExecution === "string" ? nextExecution : null) ||
    "每日 14:45 尾盘";

  const gridCols =
    "grid-cols-[2.2fr_1fr_1fr_1fr_1.3fr_1.3fr_1.4fr_1.1fr]";

  return (
    <section className="glass card-lift rounded-2xl p-4 sm:p-6">
      <div className="flex items-center justify-between mb-4">
        <div>
          <div className="flex items-center gap-2 flex-wrap">
            <h2 className="text-[18px] font-semibold text-text-primary">{title}</h2>
            <span
              className={`tag-badge ${
                active
                  ? "bg-[rgba(62,230,168,0.15)] text-status-success"
                  : "bg-text-disabled/20 text-text-disabled"
              }`}
            >
              {active ? "运行中" : "已停止"}
            </span>
            {group.merged && (
              <span className="text-[11px] text-text-disabled border border-border-subtle rounded-full px-2 py-0.5">
                {strategies.length} 个子策略
              </span>
            )}
          </div>
          <p className="mt-1 text-[12px] text-text-disabled">
            {group.merged && group.subtitle ? `${group.subtitle} · ` : ""}
            {shared
              ? `共用资金 · 本策略占用 ￥${(used / 10000).toFixed(2)}万 · 账户现金 ￥${(accountCash / 10000).toFixed(2)}万可买`
              : `分配 ￥${((accountEquity || strategies.reduce((a, s) => a + (s.allocated || 0), 0)) / 10000).toFixed(0)}万 · 已用 ￥${(used / 10000).toFixed(2)}万`}
          </p>
        </div>
        <div className="text-right">
          <div className={`font-display-numeric text-[20px] ${pnlColor}`}>
            {weightedPnl >= 0 ? "+" : ""}
            {weightedPnl.toFixed(2)}%
          </div>
          <div className="text-[11px] text-text-disabled">策略收益</div>
        </div>
      </div>

      {positions.length > 0 ? (
        <div className="overflow-x-auto">
          <div
            className={`grid ${gridCols} gap-0 text-[11px] uppercase tracking-wider text-text-disabled border-b border-border-subtle min-w-[720px]`}
          >
            <div className="px-3 py-2.5 font-medium text-left">股票</div>
            <div className="px-3 py-2.5 font-medium text-right">股数</div>
            <div className="px-3 py-2.5 font-medium text-right">入场价</div>
            <div className="px-3 py-2.5 font-medium text-right">现价</div>
            <div className="px-3 py-2.5 font-medium text-right">买入金额</div>
            <div className="px-3 py-2.5 font-medium text-right">当前市值</div>
            <div className="px-3 py-2.5 font-medium text-right">盈亏</div>
            <div className="px-3 py-2.5 font-medium text-right">止损</div>
          </div>
          {positions.map((p) => {
            const pnl = p.pnl_pct || 0;
            const pColor = pnl >= 0 ? "text-status-danger" : "text-status-success";
            const qty = p.quantity || 0;
            const entry = p.entry_price || 0;
            const cur = p.current_price || entry;
            const costAmt = entry * qty;
            const mktAmt = cur * qty;
            const subTag = group.merged
              ? (p._strategyName || "").replace(/策略$/, "")
              : "";
            return (
              <div
                key={`${p._strategyId}-${p.symbol}`}
                className={`grid ${gridCols} gap-0 text-[13px] border-b border-border-subtle/30 hover:bg-primary/4 transition-colors min-w-[720px]`}
              >
                <div className="px-3 py-2.5">
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <span className="font-semibold text-text-primary">{p.name}</span>
                    <span className="text-text-disabled text-[11px]">{p.symbol}</span>
                  </div>
                  {subTag ? (
                    <div className="text-[10px] text-text-disabled mt-0.5">{subTag}</div>
                  ) : null}
                </div>
                <div className="px-3 py-2.5 text-right font-display-numeric text-text-primary">
                  {qty > 0 ? qty.toLocaleString() : "—"}
                </div>
                <div className="px-3 py-2.5 text-right font-display-numeric text-text-primary">
                  ￥{entry.toFixed(2)}
                  {p.entry_mode && ENTRY_MODE_LABEL[p.entry_mode] ? (
                    <div className="text-[10px] text-text-disabled font-normal mt-0.5">
                      {ENTRY_MODE_LABEL[p.entry_mode]}
                    </div>
                  ) : null}
                </div>
                <div className="px-3 py-2.5 text-right font-display-numeric text-status-warning">
                  ￥{cur.toFixed(2)}
                </div>
                <div className="px-3 py-2.5 text-right font-display-numeric text-text-secondary">
                  ￥{costAmt.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                </div>
                <div className="px-3 py-2.5 text-right font-display-numeric text-text-primary">
                  ￥{mktAmt.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                </div>
                <div className={`px-3 py-2.5 text-right font-display-numeric ${pColor}`}>
                  {pnl >= 0 ? "+" : ""}
                  {pnl.toFixed(2)}%
                  <div className="text-[10px] text-text-disabled mt-0.5">
                    ￥{p.pnl_amount >= 0 ? "+" : ""}
                    {(p.pnl_amount || 0).toFixed(0)}
                  </div>
                </div>
                <div className="px-3 py-2.5 text-right font-display-numeric text-status-danger">
                  ￥{(p.stop_loss || 0).toFixed(2)}
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="text-center py-8 text-text-disabled text-[13px]">
          <svg className="w-10 h-10 mx-auto mb-2 opacity-30" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
            <rect x="3" y="3" width="18" height="18" rx="2" />
            <line x1="9" y1="9" x2="15" y2="9" />
          </svg>
          暂无持仓
          <p className="text-[11px] mt-1">下次执行时间: {nextHint}</p>
        </div>
      )}

      {signals.length > 0 && (
        <div className="mt-4 pt-4 border-t border-border-subtle">
          <div className="text-[12px] text-text-disabled mb-2">今日买入信号（盘中低吸 · 回踩 VWAP 后成交）</div>
          <div className="space-y-1.5">
            {signals.slice(0, 6).map((s, i) => (
              <div
                key={i}
                className="flex items-center justify-between text-[12px] bg-background rounded-lg p-2 border border-border-subtle"
              >
                <div className="flex items-center gap-2 min-w-0">
                  <span className="text-status-danger font-semibold">{s.name}</span>
                  <span className="text-text-disabled">{s.symbol}</span>
                  <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-status-warning/10 text-status-warning border border-status-warning/20">
                    等待低吸
                  </span>
                  {group.merged && s._strategyName ? (
                    <span className="text-[10px] text-text-disabled">{s._strategyName}</span>
                  ) : null}
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


// ═══ 交易记录：按股票 FIFO；整段清仓合并一行；再按自然周归类（同收藏历史）═══
function isBuyAction(action: string) {
  return (action || "").startsWith("买入");
}
function isSellAction(action: string) {
  const a = action || "";
  // 勿用 includes("止盈")，避免误伤其它文案；只认卖出*/止损/止盈
  return a.startsWith("卖出") || a === "止损" || a === "止盈";
}

function pad2(n: number) {
  return String(n).padStart(2, "0");
}

function fmtMd(d: Date) {
  return `${pad2(d.getMonth() + 1)}/${pad2(d.getDate())}`;
}

/** 自然周（周一～周日），key=该周周一 YYYY-MM-DD */
function weekMeta(iso?: string): { key: string; label: string; sortKey: string } {
  const raw = (iso || "").trim();
  // trade_log 常见 "2026-07-21 14:36" / ISO
  const d = raw
    ? new Date(raw.includes("T") ? raw : raw.replace(" ", "T"))
    : new Date();
  const safe = Number.isNaN(d.getTime()) ? new Date() : d;
  const day = safe.getDay(); // 0=Sun
  const mondayOffset = day === 0 ? -6 : 1 - day;
  const monday = new Date(safe);
  monday.setHours(0, 0, 0, 0);
  monday.setDate(safe.getDate() + mondayOffset);
  const sunday = new Date(monday);
  sunday.setDate(monday.getDate() + 6);
  const y = monday.getFullYear();
  const jan4 = new Date(y, 0, 4);
  const jan4Day = jan4.getDay() || 7;
  const week1Mon = new Date(jan4);
  week1Mon.setDate(jan4.getDate() - (jan4Day - 1));
  const weekNo = Math.floor((monday.getTime() - week1Mon.getTime()) / (7 * 86400000)) + 1;
  const key = `${y}-${pad2(monday.getMonth() + 1)}-${pad2(monday.getDate())}`;
  return {
    key,
    sortKey: key,
    label: `${y} 第${weekNo}周 · ${fmtMd(monday)}–${fmtMd(sunday)}`,
  };
}

function dedupeTrades(tradeLog: TradeLogEntry[]): TradeLogEntry[] {
  const seen = new Set<string>();
  const out: TradeLogEntry[] = [];
  for (const t of tradeLog) {
    const key = [t.time, t.symbol, t.action, t.price, t.quantity, t.strategy_id || ""].join("|");
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(t);
  }
  return out;
}

function TradeLogTable({
  tradeLog,
  heldSymbols,
}: {
  tradeLog: TradeLogEntry[];
  heldSymbols: Set<string>;
}) {
  type MergedRow = {
    symbol: string;
    name: string;
    buyTime: string;
    sellTime: string;
    buyPrice: number;
    sellPrice: number;
    quantity: number;
    sellAction: string;
    buyActions: string[];
    open: boolean;
    legs?: number;
  };

  type Lot = {
    time: string;
    price: number;
    qtyLeft: number;
    action: string;
    name: string;
  };

  type Wave = {
    buyTime: string;
    buyActions: string[];
    costSum: number;
    buyQty: number;
    sellSum: number;
    sellQty: number;
    sellTime: string;
    sellActions: string[];
  };

  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});

  const chrono = dedupeTrades(tradeLog).sort((a, b) => (a.time || "").localeCompare(b.time || ""));
  // 只按股票配对（eod_sniper / s2_eod 历史策略 id 不一致）
  const openLots = new Map<string, Lot[]>();
  const waves = new Map<string, Wave>(); // 进行中的未完全平仓卖出波段
  const closed: MergedRow[] = [];

  const flushWave = (symbol: string, name: string) => {
    const w = waves.get(symbol);
    if (!w || w.sellQty <= 0) {
      waves.delete(symbol);
      return;
    }
    closed.push({
      symbol,
      name,
      buyTime: w.buyTime,
      sellTime: w.sellTime,
      buyPrice: w.buyQty > 0 ? w.costSum / w.buyQty : 0,
      sellPrice: w.sellSum / w.sellQty,
      quantity: w.sellQty,
      sellAction:
        w.sellActions.length === 1
          ? w.sellActions[0]
          : `已清仓(${w.sellActions.length}笔)`,
      buyActions: w.buyActions,
      open: false,
      legs: w.sellActions.length,
    });
    waves.delete(symbol);
  };

  for (const log of chrono) {
    const action = log.action || "";
    if (!isBuyAction(action) && !isSellAction(action)) continue;
    const symbol = log.symbol;
    const name = log.name;

    if (isBuyAction(action)) {
      const q = Number(log.quantity) || 0;
      if (q <= 0) continue;
      const list = openLots.get(symbol) || [];
      list.push({
        time: log.time,
        price: Number(log.price) || 0,
        qtyLeft: q,
        action,
        name,
      });
      openLots.set(symbol, list);
      continue;
    }

    let remain = Number(log.quantity) || 0;
    if (remain <= 0) continue;
    const list = openLots.get(symbol) || [];
    let matchedQty = 0;
    let costSum = 0;
    let firstBuyTime = "";
    const buyActions: string[] = [];
    while (remain > 0 && list.length > 0) {
      const lot = list[0];
      const take = Math.min(lot.qtyLeft, remain);
      matchedQty += take;
      costSum += take * lot.price;
      if (!firstBuyTime) firstBuyTime = lot.time;
      if (!buyActions.includes(lot.action)) buyActions.push(lot.action);
      lot.qtyLeft -= take;
      remain -= take;
      if (lot.qtyLeft <= 0) list.shift();
    }
    openLots.set(symbol, list);

    if (matchedQty <= 0) continue; // 无买入对应的孤儿卖出不展示，避免重复脏行

    let w = waves.get(symbol);
    if (!w) {
      w = {
        buyTime: firstBuyTime,
        buyActions: [...buyActions],
        costSum: 0,
        buyQty: 0,
        sellSum: 0,
        sellQty: 0,
        sellTime: log.time,
        sellActions: [],
      };
      waves.set(symbol, w);
    }
    w.costSum += costSum;
    w.buyQty += matchedQty;
    w.sellSum += matchedQty * (Number(log.price) || 0);
    w.sellQty += matchedQty;
    w.sellTime = log.time;
    if (!w.sellActions.includes(action)) w.sellActions.push(action);
    for (const ba of buyActions) {
      if (!w.buyActions.includes(ba)) w.buyActions.push(ba);
    }
    if (!w.buyTime) w.buyTime = firstBuyTime;

    const stillOpen = (openLots.get(symbol) || []).some((l) => l.qtyLeft > 0);
    if (!stillOpen) flushWave(symbol, name);
  }

  // 若还有未 flush 的波段（半仓卖出后仍持仓）→ 作为已实现盈亏行
  for (const [symbol] of [...waves.entries()]) {
    const w = waves.get(symbol);
    if (w && w.sellQty > 0) {
      const name = (openLots.get(symbol) || [])[0]?.name || symbol;
      flushWave(symbol, name);
    }
  }

  // 持仓中：仅展示账户里仍有的标的，同票合并一行
  const opens: MergedRow[] = [];
  for (const [symbol, lots] of openLots) {
    if (!heldSymbols.has(symbol)) continue;
    const alive = lots.filter((l) => l.qtyLeft > 0);
    if (!alive.length) continue;
    const qty = alive.reduce((s, l) => s + l.qtyLeft, 0);
    const costSum = alive.reduce((s, l) => s + l.qtyLeft * l.price, 0);
    opens.push({
      symbol,
      name: alive[0].name,
      buyTime: alive[0].time,
      sellTime: "",
      buyPrice: costSum / qty,
      sellPrice: 0,
      quantity: qty,
      sellAction: "",
      buyActions: [...new Set(alive.map((l) => l.action))],
      open: true,
    });
  }

  const rows = [...closed, ...opens].sort((a, b) => {
    const ta = a.sellTime || a.buyTime || "";
    const tb = b.sellTime || b.buyTime || "";
    return tb.localeCompare(ta);
  });

  // 按周归类：已平仓用卖出日，持仓中用买入日
  const weekGroups: { key: string; label: string; rows: MergedRow[] }[] = [];
  const weekIndex = new Map<string, number>();
  for (const row of rows) {
    const meta = weekMeta(row.sellTime || row.buyTime);
    let idx = weekIndex.get(meta.key);
    if (idx == null) {
      idx = weekGroups.length;
      weekIndex.set(meta.key, idx);
      weekGroups.push({ key: meta.key, label: meta.label, rows: [] });
    }
    weekGroups[idx].rows.push(row);
  }

  const gridCols = "grid-cols-[3fr_3fr_3fr_3fr_4fr_4fr_3fr]";

  const fmtTime = (t: string) => {
    if (!t) return "";
    const parts = t.split(/[ -]/);
    if (parts.length >= 3) return parts[1] + "/" + parts[2] + " " + (parts[3] || "").slice(0, 5);
    return t;
  };

  const sellLabel = (row: MergedRow) => {
    if (row.open) return row.buyActions.some((a) => a.includes("补仓")) ? "持仓中·已补仓" : "持仓中";
    if (row.legs && row.legs > 1) return row.sellAction;
    const action = row.sellAction;
    if (action === "止损" || action === "卖出(止损)") return "止损卖出";
    if (action === "止盈" || action === "卖出(止盈)") return "止盈卖出";
    if (action.startsWith("卖出(")) return action;
    if (action.startsWith("卖出")) return "已卖出";
    return action || "已卖出";
  };

  const rowProfit = (row: MergedRow) => {
    const hasBuy = row.buyPrice > 0;
    const hasSell = !row.open && row.sellPrice > 0;
    const qty = row.quantity;
    const costTotal = row.buyPrice * qty;
    const exitTotal = row.sellPrice * qty;
    const profitAmt = hasBuy && hasSell ? exitTotal - costTotal : 0;
    const profitPct = hasBuy && hasSell && costTotal > 0 ? (profitAmt / costTotal) * 100 : 0;
    return { hasBuy, hasSell, qty, costTotal, exitTotal, profitAmt, profitPct };
  };

  const renderRow = (row: MergedRow, idx: number) => {
    const { hasBuy, hasSell, qty, profitAmt, profitPct } = rowProfit(row);
    const scaledIn = row.buyActions.some((a) => a.includes("补仓"));
    const actionLabel = sellLabel(row);
    let actionBg = "rgba(148,163,184,0.15)";
    let actionColor = "#94A3B8";
    if (row.open) {
      actionBg = "rgba(245,196,81,0.15)";
      actionColor = "#F5C451";
    } else if (
      row.sellAction.includes("止盈") ||
      row.sellAction.includes("减半") ||
      row.sellAction.includes("清仓") ||
      row.sellAction === "已卖出"
    ) {
      actionBg = "rgba(255,93,93,0.15)";
      actionColor = "#FF5D5D";
    } else if (row.sellAction.includes("止损")) {
      actionBg = "rgba(62,230,168,0.15)";
      actionColor = "#3EE6A8";
    } else if (hasSell) {
      if (profitAmt >= 0) {
        actionBg = "rgba(255,93,93,0.15)";
        actionColor = "#FF5D5D";
      } else {
        actionBg = "rgba(62,230,168,0.15)";
        actionColor = "#3EE6A8";
      }
    }

    return (
      <div
        key={`${row.symbol}-${row.buyTime}-${row.sellTime}-${row.open}-${idx}`}
        className={"grid " + gridCols + " gap-0 text-[13px] border-b border-border-subtle/30 hover:bg-primary/4 transition-colors"}
      >
        <div className="px-3 py-2.5">
          <div className="flex items-center gap-1.5">
            <span className="font-semibold text-text-primary">{row.name}</span>
            <span className="text-text-disabled text-[11px]">{row.symbol}</span>
          </div>
          <div className="text-[10px] text-text-disabled mt-0.5">
            {row.buyTime && <span>买入 {fmtTime(row.buyTime)}</span>}
            {scaledIn && row.open && <span className="ml-1 text-status-warning">含补仓</span>}
            {row.buyTime && hasSell && <span className="mx-1">→</span>}
            {hasSell && <span>卖出 {fmtTime(row.sellTime)}</span>}
            {row.legs && row.legs > 1 && (
              <span className="ml-1">· {row.sellAction.replace(/^已清仓/, "")}</span>
            )}
          </div>
        </div>
        <div className="px-3 py-2.5 text-right font-display-numeric text-status-danger">
          {hasBuy ? "￥" + row.buyPrice.toFixed(2) : "—"}
        </div>
        <div className={"px-3 py-2.5 text-right font-display-numeric " + (hasSell ? "text-status-success" : "text-text-disabled")}>
          {hasSell ? "￥" + row.sellPrice.toFixed(2) : "—"}
        </div>
        <div className="px-3 py-2.5 text-right font-display-numeric text-text-secondary">
          {qty > 0 ? qty.toLocaleString() : "—"}
        </div>
        <div className={"px-3 py-2.5 text-right font-display-numeric font-semibold " + (hasBuy && hasSell ? (profitAmt >= 0 ? "text-status-danger" : "text-status-success") : "text-text-disabled")}>
          {hasBuy && hasSell ? (profitAmt >= 0 ? "+" : "") + "￥" + profitAmt.toFixed(2) : "—"}
        </div>
        <div className={"px-3 py-2.5 text-right font-display-numeric font-semibold " + (hasBuy && hasSell ? (profitPct >= 0 ? "text-status-danger" : "text-status-success") : "text-text-disabled")}>
          {hasBuy && hasSell ? (profitPct >= 0 ? "+" : "") + profitPct.toFixed(2) + "%" : "—"}
        </div>
        <div className="px-3 py-2.5 text-center">
          <span className="tag-badge" style={{ backgroundColor: actionBg, color: actionColor }}>
            {actionLabel}
          </span>
        </div>
      </div>
    );
  };

  if (weekGroups.length === 0) {
    return (
      <div className="py-8 text-center text-[13px] text-text-disabled">暂无交易记录</div>
    );
  }

  return (
    <div className="space-y-4 -mx-4 sm:mx-0">
      {weekGroups.map((group) => {
        const isCollapsed = !!collapsed[group.key];
        const closedRows = group.rows.filter((r) => !r.open);
        const pcts = closedRows
          .map((r) => rowProfit(r))
          .filter((p) => p.hasBuy && p.hasSell)
          .map((p) => p.profitPct);
        const wins = pcts.filter((p) => p > 0).length;
        const avg = pcts.length ? pcts.reduce((a, b) => a + b, 0) / pcts.length : 0;
        const openCount = group.rows.filter((r) => r.open).length;

        return (
          <div key={group.key} className="rounded-xl border border-border-subtle/60 overflow-hidden">
            <button
              type="button"
              onClick={() =>
                setCollapsed((prev) => ({ ...prev, [group.key]: !prev[group.key] }))
              }
              className="w-full flex items-center justify-between gap-3 px-3 py-2.5 bg-surface-panel/60 hover:bg-surface-panel transition-colors text-left"
            >
              <div className="min-w-0">
                <div className="text-[13px] font-semibold text-text-primary">{group.label}</div>
                <div className="text-[11px] text-text-disabled mt-0.5">
                  {group.rows.length} 条
                  {closedRows.length > 0
                    ? ` · 已平 ${closedRows.length} · 盈利 ${wins}/${closedRows.length}`
                    : ""}
                  {pcts.length > 0
                    ? ` · 均盈亏 ${avg >= 0 ? "+" : ""}${avg.toFixed(2)}%`
                    : ""}
                  {openCount > 0 ? ` · 持仓中 ${openCount}` : ""}
                </div>
              </div>
              <span className="text-[11px] text-text-disabled shrink-0">
                {isCollapsed ? "展开 ▾" : "收起 ▴"}
              </span>
            </button>

            {!isCollapsed && (
              <div className="overflow-x-auto">
                <div
                  className={
                    "grid " +
                    gridCols +
                    " gap-0 text-[11px] uppercase tracking-wider text-text-disabled border-b border-border-subtle"
                  }
                >
                  <div className="px-3 py-2.5 font-medium text-left">股票</div>
                  <div className="px-3 py-2.5 font-medium text-right">买入价</div>
                  <div className="px-3 py-2.5 font-medium text-right">卖出价</div>
                  <div className="px-3 py-2.5 font-medium text-right">数量</div>
                  <div className="px-3 py-2.5 font-medium text-right">盈余</div>
                  <div className="px-3 py-2.5 font-medium text-right">盈亏%</div>
                  <div className="px-3 py-2.5 font-medium text-center">操作</div>
                </div>
                {group.rows.map((row, idx) => renderRow(row, idx))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

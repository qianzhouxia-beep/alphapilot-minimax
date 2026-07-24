// AlphaPilot 模拟交易看板
"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { HeaderBar } from "@/components/HeaderBar";
import {
  fetchPaperTrading,
  fetchFeatureFlags,
  fetchCNScreener,
  updateAllocationConfig,
  fetchLiveOrders,
  approveLiveOrders,
  rejectLiveOrders,
  fetchBrokerConnection,
  saveBrokerConnection,
} from "@/lib/cn-api";

function formatMoney(n) {
  if (n >= 10000) return "¥" + (n / 10000).toFixed(2) + "万";
  return "¥" + n.toFixed(2);
}

function pctStr(pct) {
  if (pct == null) return "-";
  return (pct > 0 ? "+" : "") + pct.toFixed(2) + "%";
}

function pctColor(pct) {
  if (pct > 0) return "#FF5D5D";
  if (pct < 0) return "#3EE6A8";
  return "#9FB0C7";
}

const STRAT_COLORS = { v16_daily: "#4DA3FF", eod_sniper: "#8B5CF6" };

function StatCard(props) {
  return (
    <div className="glass rounded-2xl p-4 card-lift">
      <div className="flex items-center justify-between mb-2">
        <span className="text-[10px] uppercase tracking-wider text-[#6E7C93]">{props.label}</span>
        {props.accent && <span className="h-1.5 w-1.5 rounded-full" style={{backgroundColor: props.accent, boxShadow: "0 0 8px " + props.accent}} />}
      </div>
      <div className="font-display-numeric text-[20px] truncate" style={{color: props.accent || "#EAF2FF"}}>{props.value}</div>
      {props.sub && <div className="mt-1 text-[11px] text-[#9FB0C7]">{props.sub}</div>}
    </div>
  );
}

export default function PaperTradingPage() {
  const [data, setData] = useState(null);
  const [features, setFeatures] = useState(null);
  const [v18Signals, setV16Signals] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState("v16_daily");
  const [showConfig, setShowConfig] = useState(false);
  const [savingConfig, setSavingConfig] = useState(false);
  const [localConfig, setLocalConfig] = useState({
    total_allocatable: 1000000,
    ratios: { v16_daily: 50, eod_sniper: 50 },
    reserved: 0,
  });
  const [pendingOrders, setPendingOrders] = useState([]);
  const [expiredOrders, setExpiredOrders] = useState([]);
  const [expireHint, setExpireHint] = useState("14:55");
  const [selectedIds, setSelectedIds] = useState({});
  const [orderBusy, setOrderBusy] = useState(false);
  const [orderMsg, setOrderMsg] = useState(null);
  const [showBroker, setShowBroker] = useState(false);
  const [broker, setBroker] = useState(null);
  const [brokerForm, setBrokerForm] = useState({
    adapter: "paper_only",
    enabled: false,
    account_id: "",
    trade_host: "",
    trade_port: "",
    quote_host: "",
    quote_port: "",
    qmt_userdata_path: "",
    agent_token: "",
  });

  const loadData = useCallback(async () => {
    try {
      const [pt, ff] = await Promise.all([fetchPaperTrading(), fetchFeatureFlags()]);
      setData(pt);
      setFeatures(ff);
      try { const s = await fetchCNScreener(); setV16Signals(s.recommendations ? s.recommendations.slice(0, 3) : []); } catch {}
      try {
        const lo = await fetchLiveOrders({ today_only: true });
        setPendingOrders(lo.pending || []);
        setExpiredOrders(lo.expired || []);
        if (lo.expire_hhmm) setExpireHint(lo.expire_hhmm);
        const sel = {};
        (lo.pending || []).forEach(function (t) { sel[t.id] = true; });
        setSelectedIds(sel);
      } catch (e) {
        // 未登录或旧后端：回退 paper 内嵌字段
        setPendingOrders((pt && pt.pending_orders) || []);
        setExpiredOrders([]);
      }
      try {
        const b = await fetchBrokerConnection();
        setBroker(b);
        setBrokerForm({
          adapter: b.adapter || "paper_only",
          enabled: !!b.enabled,
          account_id: (b.config && b.config.account_id) || "",
          trade_host: (b.config && b.config.trade_host) || "",
          trade_port: (b.config && b.config.trade_port) || "",
          quote_host: (b.config && b.config.quote_host) || "",
          quote_port: (b.config && b.config.quote_port) || "",
          qmt_userdata_path: (b.config && b.config.qmt_userdata_path) || "",
          agent_token: "",
        });
      } catch {}
      setError(null);
    } catch (e) {
      setError(e.message || String(e));
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      await loadData();
      if (!cancelled) setLoading(false);
    })();
    return () => { cancelled = true; };
  }, [loadData]);

  useEffect(() => {
    if (data && data.allocation_config) {
      setLocalConfig({
        total_allocatable: data.allocation_config.total_allocatable || 1000000,
        ratios: data.allocation_config.ratios || { v16_daily: 50, eod_sniper: 50 },
        reserved: data.allocation_config.reserved || 0,
      });
    }
  }, [data]);

  // Auto-refresh every 30 seconds
  useEffect(function() {
    var t = setInterval(function() { loadData(); }, 30000);
    return function() { clearInterval(t); };
  }, [loadData]);

  const handleSaveConfig = async () => {
    setSavingConfig(true);
    try {
      await updateAllocationConfig(localConfig);
      await loadData();
      setShowConfig(false);
    } catch (e) {
      console.error(e);
    }
    setSavingConfig(false);
  };

  const selectedList = Object.keys(selectedIds).filter(function (k) { return selectedIds[k]; });

  const handleApprove = async (executeNow) => {
    if (!selectedList.length) return;
    setOrderBusy(true);
    setOrderMsg(null);
    try {
      const r = await approveLiveOrders({
        ticket_ids: selectedList,
        execute_now: !!executeNow,
      });
      setOrderMsg("已确认 " + (r.approved ? r.approved.length : selectedList.length) + " 只" + (executeNow ? "，并触发模拟执行" : "，等待执行器"));
      await loadData();
    } catch (e) {
      setOrderMsg(e.message || String(e));
    }
    setOrderBusy(false);
  };

  const handleReject = async () => {
    if (!selectedList.length) return;
    setOrderBusy(true);
    setOrderMsg(null);
    try {
      await rejectLiveOrders({ ticket_ids: selectedList, reason: "user_reject" });
      setOrderMsg("已拒绝 " + selectedList.length + " 只");
      await loadData();
    } catch (e) {
      setOrderMsg(e.message || String(e));
    }
    setOrderBusy(false);
  };

  const handleSaveBroker = async () => {
    setOrderBusy(true);
    try {
      const config = {
        account_id: brokerForm.account_id,
        trade_host: brokerForm.trade_host,
        trade_port: brokerForm.trade_port,
        quote_host: brokerForm.quote_host,
        quote_port: brokerForm.quote_port,
        qmt_userdata_path: brokerForm.qmt_userdata_path,
      };
      if (brokerForm.agent_token) config.agent_token = brokerForm.agent_token;
      await saveBrokerConnection({
        adapter: brokerForm.adapter,
        enabled: brokerForm.enabled,
        config: config,
      });
      setOrderMsg("券商连接配置已保存（真仓对接后期启用）");
      setShowBroker(false);
      await loadData();
    } catch (e) {
      setOrderMsg(e.message || String(e));
    }
    setOrderBusy(false);
  };

  const ptFeature = features && features.features && features.features.paper_trading;
  const hasAccess = ptFeature ? ptFeature.has_access !== false : true;

  if (loading) {
    return (
      <main className="mx-auto max-w-[1440px] px-4 sm:px-6 lg:px-8 py-4 sm:py-6 lg:py-8 min-h-screen">
        <HeaderBar market="cn" />
        <div className="flex flex-col items-center justify-center py-20">
          <div className="h-12 w-12 animate-spin rounded-full border-4 border-[#1D2A42] border-t-[#4DA3FF]"></div>
          <p className="mt-4 text-[14px] text-[#9FB0C7]">加载中...</p>
        </div>
      </main>
    );
  }

  if (error) {
    return (
      <main className="mx-auto max-w-[1440px] px-4 sm:px-6 lg:px-8 py-4 sm:py-6 lg:py-8 min-h-screen">
        <HeaderBar market="cn" />
        <div className="glass mb-6 rounded-2xl border border-[#FF5D5D] p-4">
          <p className="text-[14px] text-[#FF5D5D] font-semibold">加载失败</p>
          <p className="mt-1 text-[12px] text-[#9FB0C7]">{error}</p>
          <button onClick={loadData} className="mt-3 rounded-lg bg-[#FF5D5D] px-4 py-2 text-[12px] font-semibold text-white">重试</button>
        </div>
      </main>
    );
  }

  if (!hasAccess) {
    return (
      <main className="mx-auto max-w-[1440px] px-4 sm:px-6 lg:px-8 py-4 sm:py-6 lg:py-8 min-h-screen">
        <HeaderBar market="cn" />
        <div className="flex flex-col items-center justify-center py-20">
          <h2 className="text-[20px] font-semibold text-[#EAF2FF] mb-2">功能暂未开放</h2>
          <p className="text-[13px] text-[#9FB0C7]">升级账户后可解锁此功能。</p>
          <Link href="/signup" className="mt-6 rounded-lg bg-[#4DA3FF] px-6 py-3 text-[14px] font-semibold text-[#00315b]">升级账户</Link>
        </div>
      </main>
    );
  }

  const account = data ? data.account : null;
  const strategies = data ? data.strategies : [];
  const activeStrat = strategies.find(function(s) { return s.id === activeTab; });
  const tradeLog = data ? data.trade_log : [];

  return (
    <main className="mx-auto max-w-[1440px] px-4 sm:px-6 lg:px-8 py-4 sm:py-6 lg:py-8 min-h-screen">
      <HeaderBar market="cn" />

      {/* Header */}
      <div className="mb-6 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <svg className="w-6 h-6 text-[#4DA3FF]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect x="2" y="3" width="20" height="14" rx="2" /><line x1="8" y1="21" x2="16" y2="21" /><line x1="12" y1="17" x2="12" y2="21" />
            </svg>
            <h1 className="text-[22px] font-semibold text-[#EAF2FF]">量化模拟盘</h1>
            <span className="text-[10px] px-2 py-0.5 rounded-full bg-[rgba(62,230,168,0.12)] text-[#3EE6A8] border border-[rgba(62,230,168,0.3)]">Beta</span>
          </div>
          <p className="mt-0.5 text-[12px] text-[#6E7C93]">V18 Fusion 日频量化 · 尾盘狙击量化 · 双策略并行 · 动态止盈止损</p>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-[#6E7C93] font-display-numeric flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-[#3EE6A8] animate-pulse"></span>
            自动刷新·30s
          </span>
          <button onClick={function() { setShowBroker(true); }} className="rounded-lg border border-[#1D2A42] bg-[#0C1728] px-3 py-1.5 text-[11px] text-[#F5C451] hover:border-[#F5C451] hover:text-[#EAF2FF] transition-colors cursor-pointer">
            券商连接
          </button>
          <button onClick={function() { setShowConfig(true); }} className="rounded-lg border border-[#1D2A42] bg-[#0C1728] px-3 py-1.5 text-[11px] text-[#A78BFA] hover:border-[#A78BFA] hover:text-[#EAF2FF] transition-colors flex items-center gap-1 cursor-pointer">
            <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
            </svg>
            配置
          </button>
          <button onClick={loadData} className="rounded-lg border border-[#1D2A42] bg-[#0C1728] px-3 py-1.5 text-[11px] text-[#9FB0C7] hover:border-[#4DA3FF] hover:text-[#EAF2FF] transition-colors cursor-pointer">刷新</button>
        </div>
      </div>

      {/* 今日待确认 */}
      <div className="glass rounded-2xl p-4 sm:p-6 mb-6 border border-[rgba(245,196,81,0.25)]">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-3">
          <div>
            <h2 className="text-[16px] font-semibold text-[#EAF2FF]">今日待确认</h2>
            <p className="text-[11px] text-[#6E7C93]">
              入口：顶部导航「量化模拟盘」。09:36 出票后需在 {expireHint} 前确认，逾期自动作废。
            </p>
          </div>
          <span className="text-[11px] px-2 py-1 rounded-full bg-[rgba(245,196,81,0.12)] text-[#F5C451] border border-[rgba(245,196,81,0.3)]">
            待确认 {pendingOrders.length} 只
          </span>
        </div>
        {orderMsg && <p className="mb-3 text-[12px] text-[#4DA3FF]">{orderMsg}</p>}
        {pendingOrders.length === 0 ? (
          <p className="text-[13px] text-[#6E7C93] py-4 text-center">
            暂无待确认订单。
            {expiredOrders.length > 0
              ? `今日有 ${expiredOrders.length} 只已过期未确认（见下方）。`
              : `工作日 09:36 出票后会出现在这里，请于 ${expireHint} 前处理。`}
          </p>
        ) : (
          <>
            <div className="overflow-x-auto mb-4">
              <table className="w-full text-left">
                <thead>
                  <tr className="border-b border-[#1D2A42] text-[11px] uppercase tracking-wider text-[#6E7C93]">
                    <th className="px-3 py-2 font-medium">选</th>
                    <th className="px-3 py-2 font-medium">股票</th>
                    <th className="px-3 py-2 text-right font-medium">评分</th>
                    <th className="px-3 py-2 text-right font-medium">建议价</th>
                    <th className="px-3 py-2 font-medium">阶段</th>
                    <th className="px-3 py-2 font-medium">过期</th>
                  </tr>
                </thead>
                <tbody>
                  {pendingOrders.map(function (t) {
                    return (
                      <tr key={t.id} className="border-b border-[#1D2A42]/50 text-[13px]">
                        <td className="px-3 py-2">
                          <input type="checkbox" className="cursor-pointer" checked={!!selectedIds[t.id]}
                            onChange={function (e) {
                              var checked = e.target.checked;
                              setSelectedIds(function (prev) {
                                var n = Object.assign({}, prev);
                                n[t.id] = checked;
                                return n;
                              });
                            }} />
                        </td>
                        <td className="px-3 py-2">
                          <span className="font-semibold text-[#EAF2FF]">{t.name || "-"}</span>
                          <span className="text-[11px] text-[#6E7C93] ml-1">{t.symbol}</span>
                          {t.research_tier === "prefer" && <span className="ml-1 text-[10px] text-[#3EE6A8]">prefer</span>}
                        </td>
                        <td className="px-3 py-2 text-right font-mono text-[#F5C451]">{t.score != null ? Number(t.score).toFixed(3) : "-"}</td>
                        <td className="px-3 py-2 text-right font-mono text-[#EAF2FF]">{t.suggest_price ? Number(t.suggest_price).toFixed(2) : "-"}</td>
                        <td className="px-3 py-2 text-[11px] text-[#9FB0C7]">{t.money_phase_label || "-"}</td>
                        <td className="px-3 py-2 text-[11px] text-[#6E7C93]">{t.expire_at || "-"}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <div className="flex flex-wrap gap-2">
              <button disabled={orderBusy || !selectedList.length} onClick={function () { handleApprove(false); }}
                className="rounded-lg bg-[#4DA3FF] px-4 py-2 text-[12px] font-semibold text-[#00315b] hover:bg-[#7ddeff] disabled:opacity-40 cursor-pointer">
                确认选中
              </button>
              <button disabled={orderBusy || !selectedList.length} onClick={function () { handleApprove(true); }}
                className="rounded-lg border border-[#3EE6A8] px-4 py-2 text-[12px] text-[#3EE6A8] hover:bg-[rgba(62,230,168,0.1)] disabled:opacity-40 cursor-pointer">
                确认并立即模拟下单
              </button>
              <button disabled={orderBusy || !selectedList.length} onClick={handleReject}
                className="rounded-lg border border-[#FF5D5D] px-4 py-2 text-[12px] text-[#FF5D5D] hover:bg-[rgba(255,93,93,0.1)] disabled:opacity-40 cursor-pointer">
                拒绝选中
              </button>
            </div>
          </>
        )}
        {expiredOrders.length > 0 && (
          <div className="mt-4 pt-4 border-t border-[#1D2A42]">
            <p className="text-[12px] text-[#6E7C93] mb-2">今日已过期未确认（不可再确认）</p>
            <ul className="space-y-1">
              {expiredOrders.map(function (t) {
                return (
                  <li key={t.id} className="text-[12px] text-[#9FB0C7] flex flex-wrap gap-2">
                    <span className="text-[#EAF2FF]">{t.name || "-"}</span>
                    <span className="text-[#6E7C93]">{t.symbol}</span>
                    <span>截止 {t.expire_at || "-"}</span>
                    <span className="text-[#FF5D5D]/80">expired</span>
                  </li>
                );
              })}
            </ul>
          </div>
        )}
      </div>

      {/* KPI Cards */}
      {account && (
        <div className="mb-6 grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
          <StatCard label="总资产" value={formatMoney(account.total_assets)} sub="含持仓市值" accent="#4DA3FF" />
          <StatCard label="可用现金" value={formatMoney(account.cash)} sub={"持仓 " + formatMoney(account.market_value)} accent="#3EE6A8" />
          <StatCard label="当日收益" value={pctStr(account.daily_pnl_pct)} sub={account.daily_pnl_pct > 0 ? "今日盈利中" : "今日持平"} accent={account.daily_pnl_pct >= 0 ? "#FF5D5D" : "#3EE6A8"} />
          <StatCard label="累计收益" value={pctStr(account.total_pnl_pct)} sub={"¥" + account.total_pnl_amount.toFixed(2)} accent={account.total_pnl_pct >= 0 ? "#FF5D5D" : "#3EE6A8"} />
          <StatCard label="交易次数" value={"" + account.trade_count} sub={"胜率 " + (account.win_rate * 100).toFixed(0) + "%"} accent="#F5C451" />
          <StatCard label="最大回撤" value={account.max_drawdown.toFixed(1) + "%"} sub="风险指标" accent={account.max_drawdown < 5 ? "#3EE6A8" : "#FF5D5D"} />
        </div>
      )}

      {/* Strategy Selector */}
      <div className="mb-6 flex gap-2">
        {strategies.map(function(s) {
          var isActive = s.id === activeTab;
          return (
            <button key={s.id} onClick={function() { setActiveTab(s.id); }}
              className={"rounded-lg px-4 py-2 text-[13px] font-medium transition-colors " + (isActive
                ? "bg-[rgba(77,163,255,0.15)] text-[#4DA3FF] border border-[rgba(77,163,255,0.4)]"
                : "border border-[#1D2A42] bg-[#0C1728] text-[#9FB0C7] hover:border-[#4DA3FF] hover:text-[#EAF2FF]")}>
              <span className="inline-block w-2 h-2 rounded-full mr-1.5" style={{backgroundColor: STRAT_COLORS[s.id] || "#4DA3FF"}} />
              {s.name}
              <span className="ml-2 text-[11px] text-[#6E7C93]">{s.positions.length}仓 · {pctStr(s.pnl_pct)}</span>
            </button>
          );
        })}
      </div>

      {/* Active Strategy */}
      {activeStrat && (
        <div className="glass rounded-2xl p-4 sm:p-6 mb-6" style={{borderLeftWidth: 3, borderLeftColor: STRAT_COLORS[activeStrat.id] || "#4DA3FF"}}>
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="text-[18px] font-semibold text-[#EAF2FF]">{activeStrat.name}</h2>
              <p className="text-[11px] text-[#6E7C93]">
                分配 {formatMoney(activeStrat.allocated)} · 已用 {formatMoney(activeStrat.used)} · 可用 {formatMoney(activeStrat.allocated - activeStrat.used)}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-[10px] px-2 py-1 rounded-full bg-[rgba(62,230,168,0.12)] text-[#3EE6A8] border border-[rgba(62,230,168,0.3)]">
                {activeStrat.status === "active" ? "运行中" : "已暂停"}
              </span>
              <span className="font-display-numeric text-[20px] font-bold" style={{color: pctColor(activeStrat.pnl_pct)}}>{pctStr(activeStrat.pnl_pct)}</span>
            </div>
          </div>

          {/* Positions */}
          {activeStrat.positions.length > 0 ? (
            <div className="overflow-x-auto mb-4">
              <table className="w-full text-left">
                <thead>
                  <tr className="border-b border-[#1D2A42] text-[11px] uppercase tracking-wider text-[#6E7C93]">
                    <th className="px-3 py-2 font-medium">股票</th>
                    <th className="px-3 py-2 text-right font-medium">入场价</th>
                    <th className="px-3 py-2 text-right font-medium">现价</th>
                    <th className="px-3 py-2 text-right font-medium">盈亏</th>
                    <th className="px-3 py-2 text-right font-medium">止损</th>
                  </tr>
                </thead>
                <tbody>
                  {activeStrat.positions.map(function(p, i) {
                    return (
                      <tr key={i} className="border-b border-[#1D2A42]/50 text-[13px]">
                        <td className="px-3 py-2">
                          <span className="font-semibold text-[#EAF2FF]">{p.name}</span>
                          <span className="text-[#6E7C93] text-[11px] ml-1">{p.symbol}</span>
                          <span className="text-[10px] text-[#6E7C93] ml-1">{p.quantity}股</span>
                        </td>
                        <td className="px-3 py-2 text-right font-mono text-[#F5C451]">{p.entry_price.toFixed(2)}</td>
                        <td className="px-3 py-2 text-right font-mono" style={{color: pctColor(p.pnl_pct)}}>{p.current_price.toFixed(2)}</td>
                        <td className="px-3 py-2 text-right font-mono" style={{color: pctColor(p.pnl_pct)}}>
                          <div>{pctStr(p.pnl_pct)}</div>
                          {p.pnl_amount !== 0 && <div className="text-[10px] text-[#6E7C93]">{(p.pnl_amount > 0 ? "+" : "") + "¥" + Math.abs(p.pnl_amount).toFixed(0)}</div>}
                        </td>
                        <td className="px-3 py-2 text-right font-mono text-[#FF5D5D]">{p.stop_loss > 0 ? p.stop_loss.toFixed(2) : "-"}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="flex flex-col items-center py-10 text-center">
              <p className="text-[14px] text-[#9FB0C7] mb-1">暂无持仓</p>
              <p className="text-[11px] text-[#6E7C93]">下个执行时间：{data && data.next_execution ? data.next_execution[activeStrat.id] || "待定" : "待定"}</p>
            </div>
          )}

          {/* Today Signals */}
          {activeStrat.id === "v16_daily" && v18Signals.length > 0 && (
            <div className="mt-4 border-t border-[#1D2A42] pt-4">
              <h3 className="text-[13px] font-medium text-[#EAF2FF] mb-3">今日买入信号</h3>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                {v18Signals.map(function(s, i) {
                  var phaseLabel = s.money_phase_label || "";
                  var phaseColor = phaseLabel.indexOf("拉升") >= 0 ? "#FF5D5D" : (phaseLabel.indexOf("吸筹") >= 0 ? "#3B82F6" : "#9FB0C7");
                  return (
                    <div key={s.symbol} className="rounded-lg bg-[#121c2a] p-3 border border-[#1D2A42] flex items-center justify-between">
                      <div>
                        <span className="text-[13px] font-semibold text-[#EAF2FF]">{s.name}</span>
                        <span className="text-[10px] text-[#6E7C93] ml-1">{s.symbol.replace(/^(sh|sz)/, "")}</span>
                        <div className="flex items-center gap-2 mt-0.5">
                          <span className="text-[11px] text-[#F5C451]">{(s.buy_price > 0 ? "¥" + s.buy_price.toFixed(2) : "")}</span>
                          {phaseLabel && <span className="text-[10px] px-1 py-0.5 rounded-sm" style={{backgroundColor: phaseColor + "20", color: phaseColor}}>{phaseLabel}</span>}
                        </div>
                      </div>
                      <span className="text-[9px] px-1.5 py-0.5 rounded-full" style={{backgroundColor: "rgba(255,93,93,0.12)", color: "#FF5D5D", border: "1px solid rgba(255,93,93,0.3)"}}>{"#" + (i + 1)}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Config Modal */}
      {showConfig && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/50 backdrop-blur-sm"
          onClick={function() { if (!savingConfig) setShowConfig(false); }}>
          <div className="w-[90vw] max-w-[440px] rounded-2xl border border-[#1D2A42] bg-[#0C1728] p-6 shadow-2xl mx-auto"
            onClick={function(e) { e.stopPropagation(); }}>
            <div className="flex items-center justify-between mb-5">
              <h3 className="text-[18px] font-semibold text-[#EAF2FF]">资金配置</h3>
              <button onClick={function() { setShowConfig(false); }} className="text-[#6E7C93] hover:text-[#EAF2FF] cursor-pointer">
                <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
                </svg>
              </button>
            </div>

            <p className="text-[12px] text-[#6E7C93] mb-4">调整各策略的分配比例。比例之和不必等于 100%，剩余资金自动保留为闲置资金。</p>

            <div className="mb-4">
              <label className="text-[12px] text-[#9FB0C7] block mb-1">总可分配资金</label>
              <input type="number" value={localConfig.total_allocatable}
                onChange={function(e) { setLocalConfig(function(prev) { return Object.assign({}, prev, {total_allocatable: parseFloat(e.target.value) || 0}); }); }}
                className="w-full rounded-lg border border-[#1D2A42] bg-[#0a1422] px-3 py-2.5 text-[14px] text-[#EAF2FF] font-mono outline-none focus:border-[#4DA3FF]" />
            </div>

            <div className="space-y-4 mb-5">
              {strategies.map(function(s) {
                var ratio = localConfig.ratios[s.id] || 0;
                return (
                  <div key={s.id}>
                    <div className="flex items-center justify-between mb-1">
                      <div className="flex items-center gap-2">
                        <span className="w-2 h-2 rounded-full" style={{backgroundColor: STRAT_COLORS[s.id] || "#4DA3FF"}} />
                        <span className="text-[13px] text-[#EAF2FF]">{s.name}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <input type="number" min="0" max="100" step="5" value={ratio}
                          onChange={function(e) {
                            var val = Math.min(100, Math.max(0, parseFloat(e.target.value) || 0));
                            setLocalConfig(function(prev) {
                              var newRatios = Object.assign({}, prev.ratios);
                              newRatios[s.id] = val;
                              return Object.assign({}, prev, {ratios: newRatios});
                            });
                          }}
                          className="w-16 rounded-lg border border-[#1D2A42] bg-[#0a1422] px-2 py-1 text-[13px] text-[#EAF2FF] font-mono text-center outline-none focus:border-[#4DA3FF]" />
                        <span className="text-[11px] text-[#6E7C93]">%</span>
                      </div>
                    </div>
                    <input type="range" min="0" max="100" step="5" value={ratio}
                      onChange={function(e) {
                        var val = parseFloat(e.target.value);
                        setLocalConfig(function(prev) {
                          var newRatios = Object.assign({}, prev.ratios);
                          newRatios[s.id] = val;
                          return Object.assign({}, prev, {ratios: newRatios});
                        });
                      }}
                      className="w-full h-1.5 rounded-full cursor-pointer bg-[#1D2A42]"
                      style={{accentColor: STRAT_COLORS[s.id] || "#4DA3FF"}} />
                  </div>
                );
              })}

              <div>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-[13px] text-[#9FB0C7]">预留现金</span>
                  <span className="text-[13px] text-[#3EE6A8] font-mono">{"¥" + (localConfig.reserved || 0).toLocaleString()}</span>
                </div>
                <input type="range" min="0" max={localConfig.total_allocatable || 1000000} step="10000"
                  value={localConfig.reserved || 0}
                  onChange={function(e) {
                    setLocalConfig(function(prev) { return Object.assign({}, prev, {reserved: parseFloat(e.target.value) || 0}); });
                  }}
                  className="w-full h-1.5 rounded-full cursor-pointer bg-[#1D2A42] accent-[#3EE6A8]" />
              </div>
            </div>

            <button onClick={handleSaveConfig} disabled={savingConfig}
              className="w-full rounded-lg bg-[#4DA3FF] py-3 text-[14px] font-semibold text-[#00315b] hover:bg-[#7ddeff] transition-colors disabled:opacity-50 flex items-center justify-center gap-2 cursor-pointer">
              {savingConfig ? "保存中..." : "保存配置"}
            </button>
          </div>
        </div>
      )}

      {/* Broker Connection Modal — 多租户网页配置（真连后期） */}
      {showBroker && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/50 backdrop-blur-sm"
          onClick={function () { if (!orderBusy) setShowBroker(false); }}>
          <div className="w-[90vw] max-w-[520px] rounded-2xl border border-[#1D2A42] bg-[#0C1728] p-6 shadow-2xl mx-auto max-h-[90vh] overflow-y-auto"
            onClick={function (e) { e.stopPropagation(); }}>
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-[18px] font-semibold text-[#EAF2FF]">券商连接</h3>
              <button onClick={function () { setShowBroker(false); }} className="text-[#6E7C93] hover:text-[#EAF2FF] cursor-pointer">关闭</button>
            </div>
            <p className="text-[12px] text-[#6E7C93] mb-4">
              每个客户在网页填写自己的 QMT/交易端口与账号。云端只存配置；真仓由客户本机 Agent 连接各自券商软件（如国金 QMT）。P0 默认「仅模拟」。
            </p>
            <div className="space-y-3 mb-4">
              <label className="block text-[12px] text-[#9FB0C7]">适配器
                <select value={brokerForm.adapter}
                  onChange={function (e) { setBrokerForm(Object.assign({}, brokerForm, { adapter: e.target.value })); }}
                  className="mt-1 w-full rounded-lg border border-[#1D2A42] bg-[#0a1422] px-3 py-2 text-[13px] text-[#EAF2FF]">
                  <option value="paper_only">仅模拟盘</option>
                  <option value="qmt_xtquant">迅投 QMT / 国金等定制 QMT</option>
                </select>
              </label>
              <label className="flex items-center gap-2 text-[13px] text-[#EAF2FF] cursor-pointer">
                <input type="checkbox" checked={brokerForm.enabled}
                  onChange={function (e) { setBrokerForm(Object.assign({}, brokerForm, { enabled: e.target.checked })); }} />
                启用真仓对接（确认后标记 live，供本机 Agent 拉取）
              </label>
              <label className="block text-[12px] text-[#9FB0C7]">资金账号
                <input value={brokerForm.account_id} onChange={function (e) { setBrokerForm(Object.assign({}, brokerForm, { account_id: e.target.value })); }}
                  className="mt-1 w-full rounded-lg border border-[#1D2A42] bg-[#0a1422] px-3 py-2 text-[13px] text-[#EAF2FF]" placeholder="国金资金账号" />
              </label>
              <div className="grid grid-cols-2 gap-2">
                <label className="block text-[12px] text-[#9FB0C7]">交易主机
                  <input value={brokerForm.trade_host} onChange={function (e) { setBrokerForm(Object.assign({}, brokerForm, { trade_host: e.target.value })); }}
                    className="mt-1 w-full rounded-lg border border-[#1D2A42] bg-[#0a1422] px-3 py-2 text-[13px] text-[#EAF2FF]" placeholder="127.0.0.1" />
                </label>
                <label className="block text-[12px] text-[#9FB0C7]">交易端口
                  <input value={brokerForm.trade_port} onChange={function (e) { setBrokerForm(Object.assign({}, brokerForm, { trade_port: e.target.value })); }}
                    className="mt-1 w-full rounded-lg border border-[#1D2A42] bg-[#0a1422] px-3 py-2 text-[13px] text-[#EAF2FF]" placeholder="例如 58610" />
                </label>
                <label className="block text-[12px] text-[#9FB0C7]">行情主机
                  <input value={brokerForm.quote_host} onChange={function (e) { setBrokerForm(Object.assign({}, brokerForm, { quote_host: e.target.value })); }}
                    className="mt-1 w-full rounded-lg border border-[#1D2A42] bg-[#0a1422] px-3 py-2 text-[13px] text-[#EAF2FF]" />
                </label>
                <label className="block text-[12px] text-[#9FB0C7]">行情端口
                  <input value={brokerForm.quote_port} onChange={function (e) { setBrokerForm(Object.assign({}, brokerForm, { quote_port: e.target.value })); }}
                    className="mt-1 w-full rounded-lg border border-[#1D2A42] bg-[#0a1422] px-3 py-2 text-[13px] text-[#EAF2FF]" />
                </label>
              </div>
              <label className="block text-[12px] text-[#9FB0C7]">QMT userdata 路径
                <input value={brokerForm.qmt_userdata_path} onChange={function (e) { setBrokerForm(Object.assign({}, brokerForm, { qmt_userdata_path: e.target.value })); }}
                  className="mt-1 w-full rounded-lg border border-[#1D2A42] bg-[#0a1422] px-3 py-2 text-[13px] text-[#EAF2FF]" placeholder="D:\\国金证券QMT交易端\\userdata_mini" />
              </label>
              <label className="block text-[12px] text-[#9FB0C7]">本机 Agent Token（留空不改）
                <input type="password" value={brokerForm.agent_token} onChange={function (e) { setBrokerForm(Object.assign({}, brokerForm, { agent_token: e.target.value })); }}
                  className="mt-1 w-full rounded-lg border border-[#1D2A42] bg-[#0a1422] px-3 py-2 text-[13px] text-[#EAF2FF]" placeholder="Agent 拉取订单用" />
              </label>
            </div>
            <button onClick={handleSaveBroker} disabled={orderBusy}
              className="w-full rounded-lg bg-[#F5C451] py-3 text-[14px] font-semibold text-[#0C1728] hover:opacity-90 disabled:opacity-50 cursor-pointer">
              保存连接配置
            </button>
            {broker && broker.status && (
              <p className="mt-2 text-[11px] text-[#6E7C93]">当前状态：{broker.status} · 适配器 {broker.adapter}</p>
            )}
          </div>
        </div>
      )}

      {/* Trade Log */}
      <div className="glass rounded-2xl p-4 sm:p-6 mb-6">
        <h2 className="text-[16px] font-semibold text-[#EAF2FF] mb-4">交易记录</h2>
        {tradeLog.length === 0 ? (
          <p className="text-[13px] text-[#6E7C93] italic py-4 text-center">暂无交易记录</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead>
                <tr className="border-b border-[#1D2A42] text-[11px] uppercase tracking-wider text-[#6E7C93]">
                  <th className="px-3 py-2 font-medium">时间</th>
                  <th className="px-3 py-2 font-medium">股票</th>
                  <th className="px-3 py-2 font-medium">操作</th>
                  <th className="px-3 py-2 text-right font-medium">价格</th>
                  <th className="px-3 py-2 text-right font-medium">数量</th>
                </tr>
              </thead>
              <tbody>
                {tradeLog.slice(-20).reverse().map(function(t, i) {
                  var actionColor = t.action === "买入" ? "bg-[rgba(62,230,168,0.12)] text-[#3EE6A8]"
                    : t.action === "卖出" ? "bg-[rgba(77,163,255,0.12)] text-[#4DA3FF]"
                    : t.action === "止损" ? "bg-[rgba(255,93,93,0.12)] text-[#FF5D5D]"
                    : "bg-[rgba(245,196,81,0.12)] text-[#F5C451]";
                  return (
                    <tr key={i} className="border-b border-[#1D2A42]/50 text-[13px]">
                      <td className="px-3 py-2 text-[11px] text-[#6E7C93] font-display-numeric">{t.time}</td>
                      <td className="px-3 py-2"><span className="font-medium text-[#EAF2FF]">{t.name}</span><span className="text-[10px] text-[#6E7C93] ml-1">{t.symbol}</span></td>
                      <td className="px-3 py-2"><span className={"text-[11px] px-1.5 py-0.5 rounded-full " + actionColor}>{t.action}</span></td>
                      <td className="px-3 py-2 text-right font-mono text-[#F5C451]">{t.price.toFixed(2)}</td>
                      <td className="px-3 py-2 text-right font-mono text-[#EAF2FF]">{t.quantity}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Footer */}
      <footer className="mt-10 text-center text-[11px] text-[#6E7C93]">
        AlphaPilot 量化模拟盘仅供参考和教育用途，非投资建议。
      </footer>
    </main>
  );
}

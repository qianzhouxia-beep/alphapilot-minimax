// AlphaPilot 板块研报 — 通达信资金 · 图表为主
"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { HeaderBar } from "@/components/HeaderBar";
import {
  fetchSectorDashboard,
  fetchSectorResearchArchive,
  sectorResearchUrl,
  type SectorDashboard,
  type SectorFlowItem,
  type SectorResearchEntry,
} from "@/lib/cn-api";

const PERIODS = [
  { id: "today", label: "今日" },
  { id: "5day", label: "5日" },
  { id: "10day", label: "10日" },
  { id: "20day", label: "20日" },
  { id: "60day", label: "60日" },
] as const;

function fmtYi(n: number) {
  const abs = Math.abs(n);
  const s = abs >= 100 ? abs.toFixed(0) : abs.toFixed(1);
  return `${n >= 0 ? "+" : "-"}${s}亿`;
}

function statusColor(st?: string) {
  if (st === "allow") return "#FF3B30";
  if (st === "deny") return "#34C759";
  return "#8E8E93";
}

/** 双向资金条：名称 | 左流出/右流入 | 固定右侧数值（避免重叠） */
function FlowBarChart({
  items,
  selected,
  onSelect,
}: {
  items: SectorFlowItem[];
  selected?: string | null;
  onSelect: (name: string) => void;
}) {
  const maxAbs = Math.max(1, ...items.map((x) => Math.abs(x.net_yi || 0)));
  const rowH = 24;
  const labelW = 72;
  const chartW = 280;
  const valueW = 72;
  const pad = 8;
  const h = items.length * rowH + 8;
  const mid = labelW + pad + chartW / 2;
  const totalW = labelW + pad + chartW + pad + valueW;

  return (
    <svg viewBox={`0 0 ${totalW} ${h}`} className="w-full h-auto" role="img">
      <line x1={mid} y1={0} x2={mid} y2={h} stroke="rgba(0,0,0,0.08)" strokeWidth={1} />
      {items.map((it, i) => {
        const y = i * rowH + 3;
        const half = chartW / 2 - 6;
        const w = Math.min(half, (Math.abs(it.net_yi) / maxAbs) * half);
        const isIn = it.net_yi >= 0;
        const barX = isIn ? mid + 2 : mid - 2 - w;
        const active = selected === it.name;
        const label = it.name.length > 5 ? it.name.slice(0, 5) + "…" : it.name;
        return (
          <g
            key={it.name}
            className="cursor-pointer"
            onClick={() => onSelect(it.name)}
            opacity={selected && !active ? 0.4 : 1}
          >
            <rect
              x={0}
              y={y - 1}
              width={totalW}
              height={rowH}
              fill={active ? "rgba(124,92,252,0.08)" : "transparent"}
              rx={4}
            />
            <text x={labelW - 4} y={y + 14} textAnchor="end" fontSize={11} fill="#3A3A40">
              {label}
            </text>
            <rect
              x={barX}
              y={y + 5}
              width={Math.max(2, w)}
              height={12}
              rx={3}
              fill={isIn ? "#FF3B30" : "#34C759"}
              opacity={0.85}
            />
            <text
              x={totalW - 4}
              y={y + 14}
              textAnchor="end"
              fontSize={10}
              fontWeight={600}
              fill={isIn ? "#FF3B30" : "#34C759"}
            >
              {fmtYi(it.net_yi)}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

/** 资金 × 强弱（无涨跌时用 rank_score） */
function ScatterChart({
  items,
  selected,
  onSelect,
}: {
  items: (SectorFlowItem & { rank_score?: number })[];
  selected?: string | null;
  onSelect: (name: string) => void;
}) {
  const W = 520;
  const H = 220;
  const pad = { l: 44, r: 16, t: 12, b: 32 };
  const nets = items.map((x) => x.net_yi);
  const ys = items.map((x) =>
    x.change_pct != null && !Number.isNaN(x.change_pct) ? x.change_pct : x.rank_score ?? 0
  );
  const minX = Math.min(...nets, -1);
  const maxX = Math.max(...nets, 1);
  const minY = Math.min(...ys, -1);
  const maxY = Math.max(...ys, 1);
  const xScale = (v: number) => pad.l + ((v - minX) / (maxX - minX || 1)) * (W - pad.l - pad.r);
  const yScale = (v: number) => pad.t + (1 - (v - minY) / (maxY - minY || 1)) * (H - pad.t - pad.b);
  const zx = xScale(0);
  const zy = yScale(0);
  const yLabel = items.some((x) => x.change_pct != null) ? "涨跌幅 %" : "资金强弱分";

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto" role="img">
      <rect x={pad.l} y={pad.t} width={W - pad.l - pad.r} height={H - pad.t - pad.b} fill="#FAFAFA" rx={8} />
      <line x1={zx} y1={pad.t} x2={zx} y2={H - pad.b} stroke="rgba(0,0,0,0.12)" strokeDasharray="4 3" />
      <line x1={pad.l} y1={zy} x2={W - pad.r} y2={zy} stroke="rgba(0,0,0,0.12)" strokeDasharray="4 3" />
      <text x={W / 2} y={H - 6} textAnchor="middle" fontSize={11} fill="#7A7A80">
        主力净流入（亿）→
      </text>
      <text x={14} y={H / 2} textAnchor="middle" fontSize={11} fill="#7A7A80" transform={`rotate(-90 14 ${H / 2})`}>
        {yLabel}
      </text>
      {items.map((it) => {
        const yv = it.change_pct != null && !Number.isNaN(it.change_pct) ? it.change_pct : it.rank_score ?? 0;
        const cx = xScale(it.net_yi);
        const cy = yScale(yv);
        const active = selected === it.name;
        return (
          <g key={it.name} className="cursor-pointer" onClick={() => onSelect(it.name)}>
            <circle
              cx={cx}
              cy={cy}
              r={active ? 7 : 5}
              fill={statusColor(it.status)}
              opacity={selected && !active ? 0.25 : 0.85}
              stroke={active ? "#7C5CFC" : "white"}
              strokeWidth={active ? 2 : 1}
            />
            {active && (
              <text x={cx + 10} y={cy - 6} fontSize={11} fontWeight={600} fill="#1D1D1F">
                {it.name}
              </text>
            )}
          </g>
        );
      })}
    </svg>
  );
}

function StatusDonut({ allow, deny, neutral }: { allow: number; deny: number; neutral: number }) {
  const total = Math.max(1, allow + deny + neutral);
  const R = 48;
  const C = 2 * Math.PI * R;
  const segs = [
    { n: allow, color: "#FF3B30", label: "流入锋面" },
    { n: deny, color: "#34C759", label: "流出回避" },
    { n: neutral, color: "#C7C7CC", label: "中性" },
  ];
  let offset = 0;
  return (
    <div className="flex items-center gap-4">
      <svg width={120} height={120} viewBox="0 0 120 120">
        <g transform="translate(60,60) rotate(-90)">
          {segs.map((s) => {
            const len = (s.n / total) * C;
            const el = (
              <circle
                key={s.label}
                r={R}
                fill="none"
                stroke={s.color}
                strokeWidth={16}
                strokeDasharray={`${len} ${C - len}`}
                strokeDashoffset={-offset}
              />
            );
            offset += len;
            return el;
          })}
        </g>
        <text x={60} y={56} textAnchor="middle" fontSize={16} fontWeight={700} fill="#1D1D1F">
          {total}
        </text>
        <text x={60} y={72} textAnchor="middle" fontSize={10} fill="#7A7A80">
          行业
        </text>
      </svg>
      <div className="space-y-1.5 text-[12px]">
        {segs.map((s) => (
          <div key={s.label} className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full" style={{ background: s.color }} />
            <span className="text-text-secondary w-16">{s.label}</span>
            <span className="font-semibold tabular-nums">{s.n}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function AnalysisBlock({ data }: { data: SectorDashboard }) {
  const a = data.analysis;
  if (!a) return null;
  return (
    <div className="mt-3 pt-3 border-t border-border-subtle">
      <div className="text-[13px] font-semibold text-text-primary leading-snug">{a.headline}</div>
      <ul className="mt-2 space-y-1">
        {(a.bullets || []).map((b, i) => (
          <li key={i} className="text-[12px] text-text-secondary leading-relaxed pl-3 relative before:content-[''] before:absolute before:left-0 before:top-2 before:w-1.5 before:h-1.5 before:rounded-full before:bg-purple-primary/60">
            {b}
          </li>
        ))}
      </ul>
      <div className="mt-3 grid grid-cols-2 gap-2">
        <div className="rounded-xl bg-status-danger/5 px-3 py-2">
          <div className="text-[10px] text-status-danger font-medium mb-1">关注流入</div>
          <div className="flex flex-wrap gap-1">
            {(a.watch || []).map((x) => (
              <span key={x.name} className="text-[11px] tabular-nums text-text-primary">
                {x.name} {fmtYi(x.net_yi)}
              </span>
            ))}
          </div>
        </div>
        <div className="rounded-xl bg-status-success/5 px-3 py-2">
          <div className="text-[10px] text-status-success font-medium mb-1">回避流出</div>
          <div className="flex flex-wrap gap-1">
            {(a.avoid || []).map((x) => (
              <span key={x.name} className="text-[11px] tabular-nums text-text-primary">
                {x.name} {fmtYi(x.net_yi)}
              </span>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

export default function SectorsPage() {
  const [tab, setTab] = useState<"board" | "research">("board");
  const [period, setPeriod] = useState<string>("today");
  const [data, setData] = useState<SectorDashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [archive, setArchive] = useState<SectorResearchEntry[]>([]);
  const [archiveErr, setArchiveErr] = useState<string | null>(null);
  const [archiveLoading, setArchiveLoading] = useState(false);
  const [activeDate, setActiveDate] = useState<string | null>(null);
  const [activeSession, setActiveSession] = useState<"morning" | "afternoon" | null>(null);

  useEffect(() => {
    try {
      const q = new URLSearchParams(window.location.search);
      if (q.get("tab") === "research") setTab("research");
    } catch {
      /* ignore */
    }
  }, []);

  const load = useCallback(async (refresh = false, p = period) => {
    setLoading(true);
    try {
      const d = await fetchSectorDashboard(refresh, p);
      setData(d);
      setError(null);
      setSelected((prev) => {
        if (prev && d.industries?.some((x) => x.name === prev)) return prev;
        return d.today_top10?.[0]?.name || d.industries?.[0]?.name || null;
      });
      if (refresh) {
        const asof = d.ts || d.meta?.asof || "—";
        setToast(`已重算 ${d.period_label || p} · 资金截至 ${String(asof).slice(0, 10)}（通达信本地聚合）`);
        window.setTimeout(() => setToast(null), 4000);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      if (refresh) {
        setToast("刷新失败，请稍后重试");
        window.setTimeout(() => setToast(null), 4000);
      }
    } finally {
      setLoading(false);
    }
  }, [period]);

  const loadArchive = useCallback(async () => {
    setArchiveLoading(true);
    setArchiveErr(null);
    try {
      const list = await fetchSectorResearchArchive();
      setArchive(list);
      if (list.length > 0) {
        setActiveDate((prev) => prev || list[0].date);
        setActiveSession((prev) => {
          if (prev) return prev;
          const first = list[0];
          return first.sessions.includes("afternoon")
            ? "afternoon"
            : first.sessions[0] || null;
        });
      }
    } catch (e) {
      setArchiveErr(e instanceof Error ? e.message : String(e));
    } finally {
      setArchiveLoading(false);
    }
  }, []);

  useEffect(() => {
    load(false, period);
  }, [period]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (tab === "research") loadArchive();
  }, [tab, loadArchive]);

  useEffect(() => {
    const url = new URL(window.location.href);
    if (tab === "research") url.searchParams.set("tab", "research");
    else url.searchParams.delete("tab");
    window.history.replaceState({}, "", url.pathname + url.search);
  }, [tab]);

  const selectedItem = useMemo(() => {
    if (!data || !selected) return null;
    return data.industries?.find((x) => x.name === selected) || null;
  }, [data, selected]);

  const activeSessions = useMemo(() => {
    if (!activeDate) return [] as Array<"morning" | "afternoon">;
    return archive.find((x) => x.date === activeDate)?.sessions || [];
  }, [archive, activeDate]);

  const reportSrc =
    activeDate && activeSession ? sectorResearchUrl(activeDate, activeSession) : null;

  return (
    <main className="mx-auto max-w-[1200px] px-4 sm:px-6 lg:px-8 py-4 sm:py-6 lg:py-8 min-h-screen">
      <HeaderBar market="cn" />

      {toast && (
        <div className="fixed top-4 left-1/2 -translate-x-1/2 z-50 rounded-xl bg-text-primary text-white px-4 py-2.5 text-[13px] shadow-lg max-w-[90vw]">
          {toast}
        </div>
      )}

      <div className="mt-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-[26px] sm:text-[28px] font-bold tracking-tight text-text-primary">板块研报</h1>
          <p className="mt-1 text-[13px] text-text-secondary">
            {tab === "board" ? (
              <>
                通达信一级行业资金 · {data?.period_label || "今日"}
                {data?.ts ? ` · 资金截至 ${String(data.ts).slice(0, 10)}` : ""}
                {data?.generated_at ? ` · 页面重算 ${String(data.generated_at).replace("T", " ").slice(0, 19)}` : ""}
              </>
            ) : (
              <>盘中/盘后深度研报（ECharts）· 与资金看板合并于本页</>
            )}
          </p>
        </div>
        {tab === "board" ? (
          <button
            type="button"
            onClick={() => load(true, period)}
            disabled={loading}
            className="rounded-xl border border-border-subtle bg-bg-secondary px-4 py-2 text-[13px] font-medium text-text-primary hover:border-purple-primary/40 disabled:opacity-50 cursor-pointer"
          >
            {loading ? "重算中…" : "刷新数据"}
          </button>
        ) : (
          <button
            type="button"
            onClick={() => loadArchive()}
            disabled={archiveLoading}
            className="rounded-xl border border-border-subtle bg-bg-secondary px-4 py-2 text-[13px] font-medium text-text-primary hover:border-purple-primary/40 disabled:opacity-50 cursor-pointer"
          >
            {archiveLoading ? "加载中…" : "刷新研报列表"}
          </button>
        )}
      </div>

      {/* 资金看板 | 深度研报 */}
      <div className="mt-4 inline-flex rounded-xl border border-border-subtle bg-bg-secondary p-0.5 shadow-sm">
        {(
          [
            { id: "board", label: "资金看板" },
            { id: "research", label: "深度研报" },
          ] as const
        ).map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setTab(t.id)}
            className={`rounded-lg px-4 py-2 text-[13px] font-medium cursor-pointer transition-colors ${
              tab === t.id
                ? "bg-purple-primary text-white"
                : "text-text-secondary hover:text-text-primary"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "board" && (
        <>
          {/* 周期切换 */}
          <div className="mt-4 flex flex-wrap gap-2">
            {PERIODS.map((p) => (
              <button
                key={p.id}
                type="button"
                onClick={() => setPeriod(p.id)}
                className={`rounded-full px-3.5 py-1.5 text-[12px] font-medium cursor-pointer transition-colors ${
                  period === p.id
                    ? "bg-purple-primary text-white"
                    : "bg-bg-secondary text-text-secondary border border-border-subtle"
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>

          {error && !data && (
            <section className="card mt-6 p-8 text-center text-status-danger text-[14px]">{error}</section>
          )}
          {loading && !data && (
            <div className="mt-16 flex justify-center">
              <div className="h-8 w-8 animate-spin rounded-full border-2 border-purple-primary border-t-transparent" />
            </div>
          )}

          {data && (
            <>
              <section className="mt-4 grid grid-cols-2 sm:grid-cols-4 gap-3">
                {[
                  { label: `${data.period_label}流入`, value: fmtYi(data.summary.inflow_yi), tone: "text-red-negative" },
                  { label: `${data.period_label}流出`, value: fmtYi(data.summary.outflow_yi), tone: "text-green-positive" },
                  {
                    label: "净额",
                    value: fmtYi(data.summary.net_yi),
                    tone: data.summary.net_yi >= 0 ? "text-red-negative" : "text-green-positive",
                  },
                  { label: "锋面 / 回避", value: `${data.summary.allow} / ${data.summary.deny}`, tone: "text-text-primary" },
                ].map((k) => (
                  <div key={k.label} className="card px-4 py-3">
                    <div className="text-[11px] text-text-tertiary">{k.label}</div>
                    <div className={`mt-1 text-[20px] font-bold tabular-nums ${k.tone}`}>{k.value}</div>
                  </div>
                ))}
              </section>

              <div className="mt-4 grid lg:grid-cols-2 gap-4">
                <section className="card p-4 sm:p-5">
                  <div className="flex items-baseline justify-between mb-2">
                    <h2 className="text-[15px] font-semibold text-text-primary">主力净流入 / 流出</h2>
                    <span className="text-[11px] text-text-tertiary">通达信 · 红入绿出</span>
                  </div>
                  <FlowBarChart items={data.flow_bars} selected={selected} onSelect={setSelected} />
                </section>

                <section className="card p-4 sm:p-5 flex flex-col">
                  <div className="flex items-baseline justify-between mb-2">
                    <h2 className="text-[15px] font-semibold text-text-primary">资金强弱分布</h2>
                    <span className="text-[11px] text-text-tertiary">点选查看</span>
                  </div>
                  <ScatterChart items={data.scatter as any} selected={selected} onSelect={setSelected} />
                  <AnalysisBlock data={data} />
                </section>
              </div>

              <div className="mt-4 grid lg:grid-cols-[260px_1fr] gap-4">
                <section className="card p-4 sm:p-5">
                  <h2 className="text-[15px] font-semibold text-text-primary mb-3">轮动结构</h2>
                  <StatusDonut allow={data.summary.allow} deny={data.summary.deny} neutral={data.summary.neutral} />
                </section>

                <section className="card p-4 sm:p-5">
                  <div className="flex flex-wrap items-start justify-between gap-3 mb-3">
                    <h2 className="text-[15px] font-semibold text-text-primary">{selectedItem?.name || "选择板块"}</h2>
                    {selectedItem && (
                      <span
                        className="text-[12px] px-2.5 py-1 rounded-full font-semibold"
                        style={{
                          background: `${statusColor(selectedItem.status)}22`,
                          color: statusColor(selectedItem.status),
                        }}
                      >
                        {selectedItem.status === "allow" ? "流入锋面" : selectedItem.status === "deny" ? "流出回避" : "中性"}
                      </span>
                    )}
                  </div>
                  {selectedItem ? (
                    <div className="grid sm:grid-cols-3 gap-3">
                      <div className="rounded-xl bg-bg-tertiary px-4 py-3">
                        <div className="text-[11px] text-text-tertiary">{data.period_label}净流入</div>
                        <div className={`mt-1 text-[22px] font-bold tabular-nums ${selectedItem.net_yi >= 0 ? "text-red-negative" : "text-green-positive"}`}>
                          {fmtYi(selectedItem.net_yi)}
                        </div>
                      </div>
                      <div className="rounded-xl bg-bg-tertiary px-4 py-3">
                        <div className="text-[11px] text-text-tertiary">行业内股票数</div>
                        <div className="mt-1 text-[22px] font-bold tabular-nums text-text-primary">
                          {(selectedItem as any).stock_count ?? "—"}
                        </div>
                      </div>
                      <div className="rounded-xl bg-bg-tertiary px-4 py-3">
                        <div className="text-[11px] text-text-tertiary">资金排名</div>
                        <div className="mt-1 text-[22px] font-bold tabular-nums text-text-primary">
                          #{selectedItem.rank ?? "—"}
                        </div>
                      </div>
                    </div>
                  ) : (
                    <div className="h-20 flex items-center justify-center text-[13px] text-text-tertiary">点击图表选择板块</div>
                  )}
                </section>
              </div>

              <section className="mt-4 rounded-2xl border border-border-subtle bg-bg-tertiary/50 px-4 py-3 text-[11px] text-text-tertiary leading-relaxed">
                <div>
                  <span className="font-medium text-text-secondary">数据源</span> 通达信 tdxhub 个股资金 × F10 一级行业 · 不经过东财
                </div>
                <div className="mt-1">
                  <span className="font-medium text-text-secondary">更新频率</span>{" "}
                  {data.meta?.update_cadence || "盘后 pull_fundflow_tdx 更新资金历史；看板刷新=本地重算"}
                </div>
                <div className="mt-1">
                  <span className="font-medium text-text-secondary">手动刷新</span>{" "}
                  {data.meta?.refresh_effect || "即时按当前周期重算聚合"}
                  {data.meta?.fund_flow_mtime ? ` · 资金文件 ${data.meta.fund_flow_mtime}` : ""}
                </div>
                {data.meta?.ports && (
                  <div className="mt-1">
                    <span className="font-medium text-text-secondary">链路</span>{" "}
                    {data.meta.ports.zeabur_proxy || ""} · API {data.meta.ports.api_uvicorn}
                  </div>
                )}
              </section>
            </>
          )}
        </>
      )}

      {tab === "research" && (
        <section className="mt-4 card p-4 sm:p-5">
          <div className="flex flex-wrap items-start justify-between gap-3 mb-4">
            <div>
              <h2 className="text-[15px] font-semibold text-text-primary">深度研报</h2>
              <p className="mt-1 text-[12px] text-text-tertiary">
                上海机定时生成 · 上午/下午场 · 内嵌展示，不再单独开黑页入口
              </p>
            </div>
          </div>

          {archiveLoading && archive.length === 0 && (
            <div className="py-12 flex justify-center">
              <div className="h-8 w-8 animate-spin rounded-full border-2 border-purple-primary border-t-transparent" />
            </div>
          )}
          {archiveErr && (
            <div className="rounded-xl bg-status-danger/5 px-4 py-3 text-[13px] text-status-danger">{archiveErr}</div>
          )}
          {!archiveLoading && !archiveErr && archive.length === 0 && (
            <div className="py-10 text-center text-[13px] text-text-tertiary">暂无研报，等待盘后/盘中任务生成</div>
          )}

          {archive.length > 0 && (
            <>
              <div className="flex flex-wrap gap-2 mb-3">
                {archive.map((e) => (
                  <button
                    key={e.date}
                    type="button"
                    onClick={() => {
                      setActiveDate(e.date);
                      setActiveSession(
                        e.sessions.includes("afternoon") ? "afternoon" : e.sessions[0] || null
                      );
                    }}
                    className={`rounded-full px-3.5 py-1.5 text-[12px] font-medium cursor-pointer transition-colors ${
                      activeDate === e.date
                        ? "bg-purple-primary text-white"
                        : "bg-bg-tertiary text-text-secondary border border-border-subtle"
                    }`}
                  >
                    {e.date}
                  </button>
                ))}
              </div>
              <div className="flex flex-wrap gap-2 mb-4">
                {activeSessions.map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => setActiveSession(s)}
                    className={`rounded-xl px-3.5 py-1.5 text-[12px] font-medium cursor-pointer transition-colors ${
                      activeSession === s
                        ? "bg-purple-light text-purple-primary border border-purple-primary/30"
                        : "bg-bg-secondary text-text-secondary border border-border-subtle"
                    }`}
                  >
                    {s === "afternoon" ? "下午场" : "上午场"}
                  </button>
                ))}
              </div>
              {reportSrc ? (
                <div className="rounded-2xl border border-border-subtle overflow-hidden bg-bg-tertiary">
                  <iframe
                    title={`板块深度研报 ${activeDate} ${activeSession}`}
                    src={reportSrc}
                    className="w-full min-h-[70vh] bg-white"
                  />
                </div>
              ) : (
                <div className="py-10 text-center text-[13px] text-text-tertiary">请选择日期与场次</div>
              )}
            </>
          )}
        </section>
      )}

      <p className="mt-8 text-center text-[11px] text-text-tertiary">通达信板块资金仅供研究，非投资建议</p>
    </main>
  );
}

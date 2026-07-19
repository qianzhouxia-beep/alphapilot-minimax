// AlphaPilot 板块研报 — 图表为主的 A 股板块资金 / 趋势看板
"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { HeaderBar } from "@/components/HeaderBar";
import {
  fetchSectorDashboard,
  type SectorDashboard,
  type SectorFlowItem,
} from "@/lib/cn-api";

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

/** 双向水平资金条 */
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
  const rowH = 22;
  const labelW = 88;
  const chartW = 320;
  const h = items.length * rowH + 8;
  const mid = labelW + chartW / 2;

  return (
    <svg viewBox={`0 0 ${labelW + chartW + 56} ${h}`} className="w-full h-auto" role="img">
      <line x1={mid} y1={0} x2={mid} y2={h} stroke="rgba(0,0,0,0.08)" strokeWidth={1} />
      {items.map((it, i) => {
        const y = i * rowH + 4;
        const w = (Math.abs(it.net_yi) / maxAbs) * (chartW / 2 - 8);
        const isIn = it.net_yi >= 0;
        const x = isIn ? mid : mid - w;
        const active = selected === it.name;
        return (
          <g
            key={it.name}
            className="cursor-pointer"
            onClick={() => onSelect(it.name)}
            opacity={selected && !active ? 0.45 : 1}
          >
            <rect x={0} y={y - 1} width={labelW + chartW + 56} height={rowH} fill={active ? "rgba(124,92,252,0.06)" : "transparent"} />
            <text
              x={labelW - 6}
              y={y + 13}
              textAnchor="end"
              fontSize={11}
              fill="#3A3A40"
            >
              {it.name.length > 7 ? it.name.slice(0, 7) + "…" : it.name}
            </text>
            <rect
              x={x}
              y={y + 4}
              width={Math.max(2, w)}
              height={12}
              rx={3}
              fill={isIn ? "#FF3B30" : "#34C759"}
              opacity={0.85}
            />
            <text
              x={isIn ? x + w + 4 : x - 4}
              y={y + 13}
              textAnchor={isIn ? "start" : "end"}
              fontSize={10}
              fill="#55555B"
            >
              {fmtYi(it.net_yi)}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

/** 资金 × 涨跌散点 */
function ScatterChart({
  items,
  selected,
  onSelect,
}: {
  items: SectorFlowItem[];
  selected?: string | null;
  onSelect: (name: string) => void;
}) {
  const W = 520;
  const H = 300;
  const pad = { l: 44, r: 16, t: 16, b: 36 };
  const nets = items.map((x) => x.net_yi);
  const chgs = items.map((x) => x.change_pct || 0);
  const minX = Math.min(...nets, -1);
  const maxX = Math.max(...nets, 1);
  const minY = Math.min(...chgs, -1);
  const maxY = Math.max(...chgs, 1);
  const xScale = (v: number) =>
    pad.l + ((v - minX) / (maxX - minX || 1)) * (W - pad.l - pad.r);
  const yScale = (v: number) =>
    pad.t + (1 - (v - minY) / (maxY - minY || 1)) * (H - pad.t - pad.b);
  const zx = xScale(0);
  const zy = yScale(0);

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto" role="img">
      <rect x={pad.l} y={pad.t} width={W - pad.l - pad.r} height={H - pad.t - pad.b} fill="#FAFAFA" rx={8} />
      <line x1={zx} y1={pad.t} x2={zx} y2={H - pad.b} stroke="rgba(0,0,0,0.12)" strokeDasharray="4 3" />
      <line x1={pad.l} y1={zy} x2={W - pad.r} y2={zy} stroke="rgba(0,0,0,0.12)" strokeDasharray="4 3" />
      <text x={W / 2} y={H - 8} textAnchor="middle" fontSize={11} fill="#7A7A80">
        主力净流入（亿）→
      </text>
      <text
        x={14}
        y={H / 2}
        textAnchor="middle"
        fontSize={11}
        fill="#7A7A80"
        transform={`rotate(-90 14 ${H / 2})`}
      >
        涨跌幅 %
      </text>
      {items.map((it) => {
        const cx = xScale(it.net_yi);
        const cy = yScale(it.change_pct || 0);
        const active = selected === it.name;
        return (
          <g key={it.name} className="cursor-pointer" onClick={() => onSelect(it.name)}>
            <circle
              cx={cx}
              cy={cy}
              r={active ? 7 : 5}
              fill={statusColor(it.status)}
              opacity={selected && !active ? 0.25 : 0.8}
              stroke={active ? "#7C5CFC" : "white"}
              strokeWidth={active ? 2 : 1}
            />
            {active && (
              <text x={cx + 10} y={cy - 8} fontSize={11} fontWeight={600} fill="#1D1D1F">
                {it.name}
              </text>
            )}
          </g>
        );
      })}
    </svg>
  );
}

/** 轮动状态环图 */
function StatusDonut({ allow, deny, neutral }: { allow: number; deny: number; neutral: number }) {
  const total = Math.max(1, allow + deny + neutral);
  const R = 54;
  const C = 2 * Math.PI * R;
  const segs = [
    { n: allow, color: "#FF3B30", label: "流入锋面" },
    { n: deny, color: "#34C759", label: "流出回避" },
    { n: neutral, color: "#C7C7CC", label: "中性" },
  ];
  let offset = 0;
  return (
    <div className="flex items-center gap-5">
      <svg width={140} height={140} viewBox="0 0 140 140">
        <g transform="translate(70,70) rotate(-90)">
          {segs.map((s) => {
            const len = (s.n / total) * C;
            const el = (
              <circle
                key={s.label}
                r={R}
                fill="none"
                stroke={s.color}
                strokeWidth={18}
                strokeDasharray={`${len} ${C - len}`}
                strokeDashoffset={-offset}
                strokeLinecap="butt"
              />
            );
            offset += len;
            return el;
          })}
        </g>
        <text x={70} y={66} textAnchor="middle" fontSize={18} fontWeight={700} fill="#1D1D1F">
          {total}
        </text>
        <text x={70} y={84} textAnchor="middle" fontSize={11} fill="#7A7A80">
          行业
        </text>
      </svg>
      <div className="space-y-2 text-[12px]">
        {segs.map((s) => (
          <div key={s.label} className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full" style={{ background: s.color }} />
            <span className="text-text-secondary w-16">{s.label}</span>
            <span className="font-semibold text-text-primary tabular-nums">{s.n}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

/** 概念迷你柱 */
function ConceptMiniBars({ items }: { items: SectorFlowItem[] }) {
  const maxAbs = Math.max(1, ...items.map((x) => Math.abs(x.net_yi || 0)));
  const W = 400;
  const barW = Math.min(28, (W - 20) / Math.max(items.length, 1) - 6);
  return (
    <svg viewBox={`0 0 ${W} 140`} className="w-full h-auto">
      <line x1={10} y1={100} x2={W - 10} y2={100} stroke="rgba(0,0,0,0.08)" />
      {items.map((it, i) => {
        const h = (Math.abs(it.net_yi) / maxAbs) * 70;
        const x = 20 + i * ((W - 40) / items.length);
        const y = it.net_yi >= 0 ? 100 - h : 100;
        return (
          <g key={it.name}>
            <rect x={x} y={y} width={barW} height={Math.max(2, h)} rx={3} fill={it.net_yi >= 0 ? "#FF3B30" : "#34C759"} opacity={0.85} />
            <text
              x={x + barW / 2}
              y={132}
              textAnchor="middle"
              fontSize={9}
              fill="#7A7A80"
              transform={`rotate(-35 ${x + barW / 2} 132)`}
            >
              {it.name.slice(0, 4)}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

export default function SectorsPage() {
  const [data, setData] = useState<SectorDashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [tab, setTab] = useState<"industry" | "concept">("industry");

  const load = useCallback(async (refresh = false) => {
    setLoading(true);
    try {
      const d = await fetchSectorDashboard(refresh);
      setData(d);
      setError(null);
      if (!selected && d.today_top10?.[0]?.name) {
        setSelected(d.today_top10[0].name);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [selected]);

  useEffect(() => {
    load(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const selectedItem = useMemo(() => {
    if (!data || !selected) return null;
    return (
      data.industries.find((x) => x.name === selected) ||
      data.flow_bars.find((x) => x.name === selected) ||
      data.scatter.find((x) => x.name === selected) ||
      null
    );
  }, [data, selected]);

  return (
    <main className="mx-auto max-w-[1200px] px-4 sm:px-6 lg:px-8 py-4 sm:py-6 lg:py-8 min-h-screen">
      <HeaderBar market="cn" />

      <div className="mt-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-[26px] sm:text-[28px] font-bold tracking-tight text-text-primary">
            板块研报
          </h1>
          <p className="mt-1 text-[13px] text-text-secondary">
            A 股行业 / 概念资金与趋势 · 以图为主
            {data?.ts ? ` · 快照 ${data.ts.replace("T", " ").slice(0, 16)}` : ""}
          </p>
        </div>
        <button
          type="button"
          onClick={() => load(true)}
          disabled={loading}
          className="rounded-xl border border-border-subtle bg-bg-secondary px-4 py-2 text-[13px] font-medium text-text-primary hover:border-purple-primary/40 disabled:opacity-50 cursor-pointer"
        >
          {loading ? "更新中…" : "刷新数据"}
        </button>
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
          {/* KPI 条 — 极简数字，不堆文案 */}
          <section className="mt-5 grid grid-cols-2 sm:grid-cols-4 gap-3">
            {[
              { label: "行业流入合计", value: fmtYi(data.summary.inflow_yi), tone: "text-red-negative" },
              { label: "行业流出合计", value: fmtYi(data.summary.outflow_yi), tone: "text-green-positive" },
              { label: "净额", value: fmtYi(data.summary.net_yi), tone: data.summary.net_yi >= 0 ? "text-red-negative" : "text-green-positive" },
              { label: "锋面 / 回避", value: `${data.summary.allow} / ${data.summary.deny}`, tone: "text-text-primary" },
            ].map((k) => (
              <div key={k.label} className="card px-4 py-3">
                <div className="text-[11px] text-text-tertiary">{k.label}</div>
                <div className={`mt-1 text-[20px] font-bold tabular-nums ${k.tone}`}>{k.value}</div>
              </div>
            ))}
          </section>

          <div className="mt-4 flex gap-2">
            {(
              [
                ["industry", "行业资金"],
                ["concept", "概念锋面"],
              ] as const
            ).map(([id, label]) => (
              <button
                key={id}
                type="button"
                onClick={() => setTab(id)}
                className={`rounded-full px-3.5 py-1.5 text-[12px] font-medium cursor-pointer transition-colors ${
                  tab === id
                    ? "bg-purple-primary text-white"
                    : "bg-bg-secondary text-text-secondary border border-border-subtle"
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          {tab === "industry" ? (
            <div className="mt-4 grid lg:grid-cols-[1.15fr_1fr] gap-4">
              <section className="card p-4 sm:p-5">
                <div className="flex items-baseline justify-between mb-2">
                  <h2 className="text-[15px] font-semibold text-text-primary">主力净流入 / 流出</h2>
                  <span className="text-[11px] text-text-tertiary">红=流入 · 绿=流出</span>
                </div>
                <FlowBarChart items={data.flow_bars} selected={selected} onSelect={setSelected} />
              </section>

              <section className="card p-4 sm:p-5">
                <div className="flex items-baseline justify-between mb-2">
                  <h2 className="text-[15px] font-semibold text-text-primary">资金 × 涨跌</h2>
                  <span className="text-[11px] text-text-tertiary">点选查看</span>
                </div>
                <ScatterChart items={data.scatter} selected={selected} onSelect={setSelected} />
              </section>
            </div>
          ) : (
            <section className="card mt-4 p-4 sm:p-5">
              <div className="flex items-baseline justify-between mb-2">
                <h2 className="text-[15px] font-semibold text-text-primary">概念资金 Top</h2>
                <span className="text-[11px] text-text-tertiary">轮动锋面</span>
              </div>
              {data.concept_top10?.length ? (
                <ConceptMiniBars items={data.concept_top10} />
              ) : (
                <p className="text-[13px] text-text-tertiary py-8 text-center">暂无概念资金数据</p>
              )}
            </section>
          )}

          <div className="mt-4 grid lg:grid-cols-[280px_1fr] gap-4">
            <section className="card p-4 sm:p-5">
              <h2 className="text-[15px] font-semibold text-text-primary mb-3">轮动结构</h2>
              <StatusDonut
                allow={data.summary.allow}
                deny={data.summary.deny}
                neutral={data.summary.neutral}
              />
            </section>

            <section className="card p-4 sm:p-5">
              <div className="flex flex-wrap items-start justify-between gap-3 mb-3">
                <div>
                  <h2 className="text-[15px] font-semibold text-text-primary">
                    {selectedItem?.name || "选择板块"}
                  </h2>
                  <p className="mt-0.5 text-[12px] text-text-tertiary">
                    图表点选后在此聚焦 · 少文字
                  </p>
                </div>
                {selectedItem && (
                  <div className="flex gap-2 text-[12px]">
                    <span
                      className="px-2.5 py-1 rounded-full font-semibold"
                      style={{
                        background: `${statusColor(selectedItem.status)}22`,
                        color: statusColor(selectedItem.status),
                      }}
                    >
                      {selectedItem.status === "allow"
                        ? "流入锋面"
                        : selectedItem.status === "deny"
                          ? "流出回避"
                          : "中性"}
                    </span>
                  </div>
                )}
              </div>

              {selectedItem ? (
                <div className="grid sm:grid-cols-3 gap-3">
                  <div className="rounded-xl bg-bg-tertiary px-4 py-3">
                    <div className="text-[11px] text-text-tertiary">今日净流入</div>
                    <div
                      className={`mt-1 text-[22px] font-bold tabular-nums ${
                        selectedItem.net_yi >= 0 ? "text-red-negative" : "text-green-positive"
                      }`}
                    >
                      {fmtYi(selectedItem.net_yi)}
                    </div>
                  </div>
                  <div className="rounded-xl bg-bg-tertiary px-4 py-3">
                    <div className="text-[11px] text-text-tertiary">板块涨跌</div>
                    <div
                      className={`mt-1 text-[22px] font-bold tabular-nums ${
                        (selectedItem.change_pct || 0) >= 0 ? "text-red-negative" : "text-green-positive"
                      }`}
                    >
                      {(selectedItem.change_pct || 0) >= 0 ? "+" : ""}
                      {(selectedItem.change_pct || 0).toFixed(2)}%
                    </div>
                  </div>
                  <div className="rounded-xl bg-bg-tertiary px-4 py-3">
                    <div className="text-[11px] text-text-tertiary">近 3 日净额</div>
                    <div className="mt-1 text-[22px] font-bold tabular-nums text-text-primary">
                      {selectedItem.net3_yi == null ? "—" : fmtYi(selectedItem.net3_yi)}
                    </div>
                  </div>
                  {/* 迷你对比条：相对全市场 */}
                  <div className="sm:col-span-3 pt-1">
                    <MiniRankBar
                      value={selectedItem.net_yi}
                      peers={data.industries}
                      label="在行业资金榜中的位置"
                    />
                  </div>
                </div>
              ) : (
                <div className="h-28 flex items-center justify-center text-[13px] text-text-tertiary">
                  点击左侧柱状或散点查看板块
                </div>
              )}
            </section>
          </div>

          {/* 热力条：涨跌色块，几乎无字 */}
          <section className="card mt-4 p-4 sm:p-5">
            <div className="flex items-baseline justify-between mb-3">
              <h2 className="text-[15px] font-semibold text-text-primary">行业涨跌热力</h2>
              <span className="text-[11px] text-text-tertiary">按今日涨跌 · 点击选择</span>
            </div>
            <HeatStrip
              items={[...data.industries]
                .sort((a, b) => (b.change_pct || 0) - (a.change_pct || 0))
                .slice(0, 48)}
              selected={selected}
              onSelect={setSelected}
            />
          </section>
        </>
      )}

      <p className="mt-8 text-center text-[11px] text-text-tertiary">
        数据来自 V3 板块轮动快照 · 仅供研究，非投资建议
      </p>
    </main>
  );
}

function MiniRankBar({
  value,
  peers,
  label,
}: {
  value: number;
  peers: SectorFlowItem[];
  label: string;
}) {
  const sorted = [...peers].sort((a, b) => b.net_yi - a.net_yi);
  const idx = sorted.findIndex((x) => x.net_yi === value);
  const pct = sorted.length > 1 ? (idx / (sorted.length - 1)) * 100 : 50;
  return (
    <div>
      <div className="flex justify-between text-[11px] text-text-tertiary mb-1.5">
        <span>{label}</span>
        <span>第 {idx >= 0 ? idx + 1 : "—"} / {sorted.length}</span>
      </div>
      <div className="relative h-2 rounded-full bg-gradient-to-r from-red-negative via-[#C7C7CC] to-green-positive opacity-90">
        <div
          className="absolute top-1/2 -translate-y-1/2 w-3 h-3 rounded-full bg-purple-primary border-2 border-white shadow"
          style={{ left: `calc(${pct}% - 6px)` }}
        />
      </div>
    </div>
  );
}

function HeatStrip({
  items,
  selected,
  onSelect,
}: {
  items: SectorFlowItem[];
  selected?: string | null;
  onSelect: (n: string) => void;
}) {
  const maxAbs = Math.max(1, ...items.map((x) => Math.abs(x.change_pct || 0)));
  return (
    <div className="grid grid-cols-4 sm:grid-cols-6 md:grid-cols-8 gap-1.5">
      {items.map((it) => {
        const chg = it.change_pct || 0;
        const intensity = Math.min(1, Math.abs(chg) / maxAbs);
        const bg =
          chg >= 0
            ? `rgba(255, 59, 48, ${0.15 + intensity * 0.7})`
            : `rgba(52, 199, 89, ${0.15 + intensity * 0.7})`;
        const active = selected === it.name;
        return (
          <button
            key={it.name}
            type="button"
            onClick={() => onSelect(it.name)}
            title={`${it.name} ${chg.toFixed(2)}% ${fmtYi(it.net_yi)}`}
            className={`rounded-lg px-1.5 py-2 text-left cursor-pointer transition-transform hover:scale-[1.03] ${
              active ? "ring-2 ring-purple-primary" : ""
            }`}
            style={{ background: bg }}
          >
            <div className="text-[10px] font-medium text-text-primary truncate leading-tight">
              {it.name}
            </div>
            <div className="text-[11px] font-bold tabular-nums text-text-primary mt-0.5">
              {chg >= 0 ? "+" : ""}
              {chg.toFixed(1)}%
            </div>
          </button>
        );
      })}
    </div>
  );
}

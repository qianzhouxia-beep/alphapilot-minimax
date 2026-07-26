// AlphaPilot 智能选股：今日推荐 + 评分榜分栏对照
"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { HeaderBar } from "@/components/HeaderBar";
import {
  fetchCNScreener,
  fetchScoreTop10,
  type ScreenerResponse,
  type ScoreTop10Item,
  type ScoreTop10Response,
  type TradePlan,
} from "@/lib/cn-api";

type RecRow = {
  symbol: string;
  name?: string;
  score?: number;
  confidence_score?: number;
  score_pct?: number;
  change_pct?: number | null;
  price?: number | null;
  pe_ttm?: number | null;
  pe?: number | null;
  sector?: string | null;
  industry?: string | null;
  industry_l1?: string | null;
  money_phase_label?: string | null;
  money_phase?: string | null;
  live_main_net?: number | null;
  main_net?: number | null;
};

const PE_TTM_MAX = 30;

type PeFilter = "all" | "le_30" | "gt_30";

function peTtmOf(item: { pe_ttm?: number | null; pe?: number | null }): number | null {
  const v = item.pe_ttm ?? item.pe;
  if (v == null || Number.isNaN(Number(v))) return null;
  return Number(v);
}

/** le_30: 0 < PE ≤ 30；gt_30: PE > 30；na: 缺失/亏损 */
function peBucketOf(item: { pe_ttm?: number | null; pe?: number | null }): "le_30" | "gt_30" | "na" {
  const pe = peTtmOf(item);
  if (pe == null || pe <= 0) return "na";
  return pe > PE_TTM_MAX ? "gt_30" : "le_30";
}

function passPeFilter(
  item: { pe_ttm?: number | null; pe?: number | null },
  filter: PeFilter
): boolean {
  if (filter === "all") return true;
  return peBucketOf(item) === filter;
}

function displayScore(item: {
  score?: number;
  model_proba?: number;
  lgb_score?: number;
  score_pct?: number;
}): number {
  const raw = item.model_proba ?? item.lgb_score ?? item.score;
  const x = Number(raw ?? 0);
  if (Number.isFinite(x) && x > 0) {
    if (x <= 1) return Math.round(x * 100);
    // 综合/z 分 >1：压到 0–100，勿再用 75–99 信心分
    return Math.round((1 / (1 + Math.exp(-x / 2))) * 100);
  }
  const pct = Number(item.score_pct);
  if (Number.isFinite(pct) && pct > 0 && pct <= 100) return Math.round(pct);
  return 0;
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

function symCode(s?: string) {
  return String(s || "").replace(/\D/g, "").slice(-6);
}

export default function CNScreener() {
  const [recData, setRecData] = useState<ScreenerResponse | null>(null);
  const [top10, setTop10] = useState<ScoreTop10Response | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  // 客户自选：全部 / PE≤30 / PE>30（系统不再硬淘 PE）
  const [peFilter, setPeFilter] = useState<PeFilter>("all");

  const loadData = async () => {
    try {
      const [r, t] = await Promise.all([
        fetchCNScreener().catch((e) => {
          throw e;
        }),
        fetchScoreTop10().catch(() => null),
      ]);
      setRecData(r);
      setTop10(t);
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

  const recommendationsRaw = ((recData as any)?.recommendations ?? []) as RecRow[];
  const scoreItemsRaw = (top10?.items ?? []) as ScoreTop10Item[];
  const recCompareRaw = (
    top10?.recommend_compare?.length ? top10.recommend_compare : recommendationsRaw
  ) as RecRow[];

  const peCounts = useMemo(() => {
    const pool = [...recommendationsRaw, ...scoreItemsRaw];
    const c = { all: pool.length, le_30: 0, gt_30: 0, na: 0 };
    pool.forEach((x) => {
      const b = peBucketOf(x);
      if (b === "le_30") c.le_30 += 1;
      else if (b === "gt_30") c.gt_30 += 1;
      else c.na += 1;
    });
    return c;
  }, [recommendationsRaw, scoreItemsRaw]);

  const recommendations = recommendationsRaw.filter((x) => passPeFilter(x, peFilter));
  const scoreItems = scoreItemsRaw.filter((x) => passPeFilter(x, peFilter));
  const recCompare = recCompareRaw.filter((x) => passPeFilter(x, peFilter));

  const scoreCodes = new Set(scoreItems.map((x) => symCode(x.symbol)));
  const overlap = recCompare.filter((x) => scoreCodes.has(symCode(x.symbol)));
  const peFilterLabel =
    peFilter === "le_30" ? `PE≤${PE_TTM_MAX}` : peFilter === "gt_30" ? `PE>${PE_TTM_MAX}` : "全部";

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
          今日交易指令 + 评分榜与推荐池 · 60s 自动刷新
          {error && <span className="ml-3 text-status-danger font-medium">错误: {error}</span>}
        </p>
        <p className="mt-2 text-[12px] text-text-disabled leading-relaxed max-w-3xl">
          <span className="text-text-secondary">今日交易指令</span>
          ：买不买、买谁、买多少、出场规则。{" "}
          <span className="text-text-secondary">今日推荐 / 评分榜</span>
          ：研究对照层。
        </p>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <span className="text-[12px] text-text-secondary">市盈率筛选</span>
          <div
            className="inline-flex items-center gap-0.5 rounded-lg border border-border-subtle bg-bg-elevated p-0.5"
            role="group"
            aria-label="市盈率筛选"
          >
            {(
              [
                { key: "all" as PeFilter, label: "全部", n: peCounts.all },
                { key: "le_30" as PeFilter, label: `PE≤${PE_TTM_MAX}`, n: peCounts.le_30 },
                { key: "gt_30" as PeFilter, label: `PE>${PE_TTM_MAX}`, n: peCounts.gt_30 },
              ] as const
            ).map((opt) => (
              <button
                key={opt.key}
                type="button"
                onClick={() => setPeFilter(opt.key)}
                className={`rounded-md px-2.5 py-1.5 text-[12px] transition-colors cursor-pointer ${
                  peFilter === opt.key
                    ? "bg-[rgba(77,163,255,0.18)] text-text-primary border border-[rgba(77,163,255,0.35)]"
                    : "text-text-secondary hover:text-text-primary border border-transparent"
                }`}
              >
                {opt.label}
                <span className="ml-1 text-[10px] text-text-disabled">{opt.n}</span>
              </button>
            ))}
          </div>
          <span className="text-[11px] text-text-disabled">
            系统已关闭 PE 硬淘 · 亏损/无 PE 仅在「全部」
          </span>
        </div>
      </header>

      {loading && (
        <div className="flex flex-col items-center justify-center py-20">
          <div className="h-12 w-12 animate-spin rounded-full border-4 border-[#1D2A42] border-t-[#4DA3FF]" />
          <p className="mt-4 text-[14px] text-text-secondary">加载中...</p>
        </div>
      )}

      {!loading && (
        <div className="space-y-8">
          <TradePlanCard plan={(recData as ScreenerResponse | null)?.trade_plan ?? null} />

          {/* 对照摘要 */}
          <section className="glass rounded-2xl p-5">
            <h2 className="text-[15px] font-semibold mb-2">评分榜 vs 推荐 · 今日对照</h2>
            <p className="text-[12px] text-text-disabled mb-3">
              重叠 {overlap.length} 只 · 当前筛选 {peFilterLabel}
              {top10?.asof ? ` · 评分榜更新 ${top10.asof}` : ""}
              {(recData as any)?.generated_at ? ` · 推荐更新 ${(recData as any).generated_at}` : ""}
            </p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-[12px]">
              <div>
                <div className="text-text-disabled mb-1">今日推荐 今日涨跌（均值）</div>
                <AvgChg items={recCompare} />
              </div>
              <div>
                <div className="text-text-disabled mb-1">评分 Top10 今日涨跌（均值）</div>
                <AvgChg items={scoreItems} />
              </div>
            </div>
          </section>

          {/* 今日推荐 */}
          <section>
            <div className="mb-3 flex items-end justify-between gap-3">
              <div>
                <h2 className="text-[18px] font-semibold">今日推荐</h2>
                <p className="text-[12px] text-text-disabled mt-0.5">
                  当日交易候选 · 与评分榜独立
                  {peFilter !== "all" ? ` · 已套用 ${peFilterLabel}` : ""}
                </p>
              </div>
              <button
                onClick={loadData}
                className="rounded-lg border border-border-subtle px-3 py-1.5 text-[12px] text-text-secondary hover:text-text-primary"
              >
                刷新
              </button>
            </div>
            {recommendations.length === 0 ? (
              <EmptyBox
                text={
                  peFilter !== "all" && recommendationsRaw.length > 0
                    ? `今日推荐在「${peFilterLabel}」下无标的，可切换筛选`
                    : "今日推荐池为空，请稍后再看"
                }
              />
            ) : (
              <StockGrid
                items={recommendations.map((it, i) => ({
                  ...it,
                  rank: i + 1,
                  sector: it.sector || it.industry || it.industry_l1,
                  money_phase_label: it.money_phase_label || it.money_phase,
                  main_net: it.live_main_net ?? it.main_net,
                  pe_ttm: peTtmOf(it),
                }))}
                showRank
                showFund
              />
            )}
          </section>

          {/* 评分 Top10 */}
          <section>
            <div className="mb-3">
              <h2 className="text-[18px] font-semibold">评分 Top10（无门槛）</h2>
              <p className="text-[12px] text-text-disabled mt-0.5">
                按 score 降序第 1→10 · {top10?.mode || "score_only"}
                {peFilter !== "all" ? ` · 已套用 ${peFilterLabel}` : ""}
              </p>
            </div>
            {scoreItems.length === 0 ? (
              <EmptyBox
                text={
                  peFilter !== "all" && scoreItemsRaw.length > 0
                    ? `评分 Top10 在「${peFilterLabel}」下无标的，可切换筛选`
                    : "暂无评分榜（等待管线写入 score_top10）"
                }
              />
            ) : (
              <StockGrid
                items={scoreItems.map((it, i) => ({
                  ...it,
                  rank: it.rank ?? i + 1,
                  sector: it.sector || it.industry || it.industry_l1,
                  pe_ttm: peTtmOf(it),
                }))}
                showRank
              />
            )}
          </section>
        </div>
      )}

      {!loading && error && (
        <div className="glass rounded-2xl border border-status-danger p-8 text-center mt-6">
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

function statusTone(code?: string) {
  switch (code) {
    case "buy":
      return "border-[rgba(62,230,168,0.35)] bg-[rgba(62,230,168,0.08)] text-[#3EE6A8]";
    case "half":
    case "light":
      return "border-[rgba(77,163,255,0.35)] bg-[rgba(77,163,255,0.08)] text-[#4DA3FF]";
    case "awaiting":
      return "border-[rgba(255,184,77,0.4)] bg-[rgba(255,184,77,0.1)] text-[#FFB84D]";
    case "empty":
    case "no_picks":
      return "border-[rgba(255,92,122,0.35)] bg-[rgba(255,92,122,0.08)] text-[#FF5C7A]";
    default:
      return "border-border-subtle bg-bg-elevated text-text-secondary";
  }
}

function TradePlanCard({ plan }: { plan: TradePlan | null }) {
  if (!plan) {
    return (
      <section className="glass rounded-2xl p-5 border border-border-subtle">
        <h2 className="text-[18px] font-semibold">今日交易指令</h2>
        <p className="mt-2 text-[13px] text-text-disabled">指令尚未就绪，请稍后再刷新</p>
      </section>
    );
  }

  const status = plan.status || { code: "unknown", label: "—", detail: "" };
  const buys = (plan.buys || []).filter((b) => b.action !== "skip");
  const expo = Number(plan.position_exposure ?? 0);
  const layers = plan.exit_layers || [];

  return (
    <section className="glass rounded-2xl p-5 sm:p-6 border border-[rgba(77,163,255,0.22)]">
      <div className="flex flex-wrap items-start justify-between gap-3 mb-4">
        <div>
          <h2 className="text-[18px] font-semibold tracking-tight">今日交易指令</h2>
          <p className="mt-1 text-[12px] text-text-disabled">
            决策层 · {plan.arm || "A1_permission"}
            {plan.asof ? ` · 信号 ${plan.asof}` : ""}
          </p>
        </div>
        <div
          className={`rounded-lg border px-3 py-1.5 text-[13px] font-semibold ${statusTone(status.code)}`}
        >
          {status.label}
        </div>
      </div>

      {status.detail && (
        <p className="mb-4 text-[13px] text-text-secondary leading-relaxed">{status.detail}</p>
      )}
      {plan.empty_reason_label && status.code === "awaiting" && (
        <p className="mb-4 text-[12px] text-[#FFB84D]">
          {plan.empty_reason_label}
          {" · "}
          <Link href="/cn/paper-trading" className="underline underline-offset-2 hover:text-text-primary">
            去模拟盘确认
          </Link>
        </p>
      )}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5 text-[12px]">
        <div>
          <div className="text-text-disabled mb-0.5">仓位曝光</div>
          <div className="font-display-numeric text-[20px] font-semibold text-text-primary">
            {(expo * 100).toFixed(0)}%
          </div>
        </div>
        <div>
          <div className="text-text-disabled mb-0.5">买入只数</div>
          <div className="font-display-numeric text-[20px] font-semibold text-text-primary">
            Top {plan.trade_top_n ?? buys.length}
          </div>
        </div>
        <div>
          <div className="text-text-disabled mb-0.5">执行窗口</div>
          <div className="text-[13px] font-medium text-text-primary leading-snug">
            {plan.execution_window || "09:37 后"}
          </div>
        </div>
        <div>
          <div className="text-text-disabled mb-0.5">入场</div>
          <div className="text-[13px] font-medium text-text-primary">
            {plan.entry_mode || "gap_soft"}
          </div>
        </div>
      </div>

      <div className="mb-5">
        <div className="text-[13px] font-semibold text-text-primary mb-2">买谁 · 买多少</div>
        {buys.length === 0 ? (
          <p className="text-[13px] text-text-disabled">今日无新开仓标的</p>
        ) : (
          <ul className="space-y-2">
            {buys.map((b) => {
              const code = symCode(b.symbol);
              return (
                <li
                  key={code}
                  className="flex flex-wrap items-center justify-between gap-2 border-t border-border-subtle pt-2 first:border-0 first:pt-0"
                >
                  <div className="min-w-0">
                    <Link
                      href={`/cn/stock?symbol=${code}`}
                      className="font-mono text-[14px] font-semibold text-status-info hover:underline"
                    >
                      {code}
                    </Link>
                    <span className="ml-2 text-[13px] text-text-secondary">{b.name || "—"}</span>
                    {b.sector ? (
                      <span className="ml-2 text-[11px] text-text-disabled">{b.sector}</span>
                    ) : null}
                  </div>
                  <div className="flex items-center gap-3 text-[12px] font-display-numeric">
                    <span className="text-text-secondary">
                      {b.buy_price != null ? `参考 ${Number(b.buy_price).toFixed(2)}` : "—"}
                    </span>
                    <span className="rounded-md border border-[rgba(77,163,255,0.3)] px-2 py-0.5 text-[#4DA3FF] font-semibold">
                      {(b.weight_pct ?? 0).toFixed(1)}% 仓
                    </span>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
        {plan.entry && (
          <p className="mt-3 text-[11px] text-text-disabled leading-relaxed">入场：{plan.entry}</p>
        )}
      </div>

      <div>
        <div className="text-[13px] font-semibold text-text-primary mb-2">出场规则（生产 peel 四层）</div>
        <ol className="space-y-2">
          {layers.map((layer) => (
            <li key={layer.id} className="flex gap-2 text-[12px] leading-relaxed">
              <span className="font-mono text-text-disabled shrink-0">{layer.id}.</span>
              <span>
                <span className="text-text-primary font-medium">{layer.name}</span>
                <span className="text-text-secondary"> — {layer.rule}</span>
              </span>
            </li>
          ))}
        </ol>
      </div>

      {plan.note && (
        <p className="mt-4 text-[11px] text-text-disabled border-t border-border-subtle pt-3">
          {plan.note}
        </p>
      )}
    </section>
  );
}

function AvgChg({ items }: { items: { change_pct?: number | null }[] }) {
  const vals = items.map((x) => x.change_pct).filter((v): v is number => v != null && !Number.isNaN(Number(v)));
  if (!vals.length) return <span className="text-text-disabled">暂无报价</span>;
  const avg = vals.reduce((a, b) => a + Number(b), 0) / vals.length;
  return (
    <span className={`font-display-numeric text-[22px] font-semibold ${chgColor(avg)}`}>
      {avg > 0 ? "+" : ""}
      {avg.toFixed(2)}%
      <span className="ml-2 text-[11px] text-text-disabled font-normal">
        ({vals.length} 只有报价)
      </span>
    </span>
  );
}

function EmptyBox({ text }: { text: string }) {
  return (
    <div className="glass rounded-2xl p-8 text-center text-[13px] text-text-disabled">{text}</div>
  );
}

function StockGrid({
  items,
  showRank,
  showFund,
}: {
  items: Array<{
    rank?: number;
    symbol: string;
    name?: string;
    score?: number;
    confidence_score?: number;
    score_pct?: number;
    change_pct?: number | null;
    pe_ttm?: number | null;
    sector?: string | null;
    money_phase_label?: string | null;
    main_net?: number | null;
  }>;
  showRank?: boolean;
  showFund?: boolean;
}) {
  return (
    <section className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
      {items.map((item) => {
        const sc = displayScore(item);
        const code = symCode(item.symbol);
        const pe = peTtmOf(item);
        return (
          <Link
            key={`${code}-${item.rank}`}
            href={`/cn/stock?symbol=${code}`}
            className="glass card-lift block rounded-2xl p-4 transition-all hover:border-status-info/30"
          >
            <div className="mb-2 flex items-start justify-between">
              <div>
                {showRank && (
                  <div className="text-[10px] text-text-disabled mb-0.5">#{item.rank}</div>
                )}
                <div className="font-mono text-[16px] font-semibold text-status-info">{code}</div>
                <div className="mt-0.5 text-[12px] text-text-secondary truncate">{item.name}</div>
              </div>
              <div className={`font-display-numeric text-[28px] leading-none ${scoreColor(sc)}`}>
                {sc}
              </div>
            </div>
            <div className="flex items-center justify-between text-[11px]">
              <span className="text-text-secondary truncate max-w-[50%]">{item.sector || "—"}</span>
              <span className={`font-display-numeric font-medium ${chgColor(item.change_pct)}`}>
                {item.change_pct != null
                  ? `${item.change_pct > 0 ? "+" : ""}${Number(item.change_pct).toFixed(2)}%`
                  : "—"}
              </span>
            </div>
            <div className="mt-1 text-[11px] text-text-disabled">
              PE-TTM {pe != null ? pe.toFixed(1) : "—"}
            </div>
            {showFund && (
              <div className="mt-2 flex items-center justify-between border-t border-border-subtle pt-2 text-[11px]">
                <span className="text-text-secondary truncate max-w-[50%]">
                  {item.money_phase_label || "—"}
                </span>
                <span
                  className={`font-mono ${
                    item.main_net != null && Number(item.main_net) >= 0
                      ? "text-status-danger"
                      : "text-status-success"
                  }`}
                >
                  {fmtYi(item.main_net)}
                </span>
              </div>
            )}
          </Link>
        );
      })}
    </section>
  );
}

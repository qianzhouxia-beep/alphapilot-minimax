// AlphaPilot 深度研报 — 输入股票 → 详细买卖研究报告
// 2026-07-19: 由问股聊天改为研报生成（TradingAgents / DeepSeek 多角色）
"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { HeaderBar } from "@/components/HeaderBar";
import {
  searchStocksPinyin,
  startDeepReport,
  getDeepReport,
  listDeepReports,
  type StockSearchResult,
  type DeepReportJob,
  type DeepReportListItem,
} from "@/lib/cn-api";

function decisionTone(decision?: string | null) {
  if (!decision) return "text-text-secondary bg-bg-tertiary";
  if (/不建议|减持|卖出|回避/.test(decision)) return "text-green-positive bg-status-success/10";
  if (/观望/.test(decision)) return "text-status-warning bg-status-warning/10";
  if (/买入|强烈/.test(decision)) return "text-red-negative bg-status-danger/10";
  return "text-purple-primary bg-purple-light";
}

/** 轻量 Markdown → HTML（标题/列表/加粗/代码块） */
function renderMarkdown(md: string): string {
  const escaped = md
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
  const lines = escaped.split("\n");
  const out: string[] = [];
  let inList = false;
  let inCode = false;

  const flushList = () => {
    if (inList) {
      out.push("</ul>");
      inList = false;
    }
  };

  for (const raw of lines) {
    const line = raw;
    if (line.startsWith("```")) {
      if (inCode) {
        out.push("</code></pre>");
        inCode = false;
      } else {
        flushList();
        out.push('<pre class="md-pre"><code>');
        inCode = true;
      }
      continue;
    }
    if (inCode) {
      out.push(line + "\n");
      continue;
    }
    if (/^### /.test(line)) {
      flushList();
      out.push(`<h3 class="md-h3">${line.slice(4)}</h3>`);
      continue;
    }
    if (/^## /.test(line)) {
      flushList();
      out.push(`<h2 class="md-h2">${line.slice(3)}</h2>`);
      continue;
    }
    if (/^# /.test(line)) {
      flushList();
      out.push(`<h1 class="md-h1">${line.slice(2)}</h1>`);
      continue;
    }
    if (/^[-*] /.test(line)) {
      if (!inList) {
        out.push('<ul class="md-ul">');
        inList = true;
      }
      const item = line.slice(2).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
      out.push(`<li>${item}</li>`);
      continue;
    }
    flushList();
    if (!line.trim()) {
      out.push("<br/>");
      continue;
    }
    const p = line.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
    out.push(`<p class="md-p">${p}</p>`);
  }
  flushList();
  if (inCode) out.push("</code></pre>");
  return out.join("\n");
}

export default function DeepReportPage() {
  const [query, setQuery] = useState("");
  const [showSearch, setShowSearch] = useState(false);
  const [results, setResults] = useState<StockSearchResult[]>([]);
  const [symbol, setSymbol] = useState("");
  const [name, setName] = useState("");
  const [job, setJob] = useState<DeepReportJob | null>(null);
  const [recent, setRecent] = useState<DeepReportListItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const refreshRecent = useCallback(async () => {
    try {
      const r = await listDeepReports(12);
      setRecent(r.items || []);
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    refreshRecent();
  }, [refreshRecent]);

  // 轮询任务
  useEffect(() => {
    if (!job?.job_id) return;
    if (job.status === "done" || job.status === "error") return;
    const id = setInterval(async () => {
      try {
        const j = await getDeepReport(job.job_id);
        setJob(j);
        if (j.status === "done" || j.status === "error") {
          refreshRecent();
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      }
    }, 2500);
    return () => clearInterval(id);
  }, [job?.job_id, job?.status, refreshRecent]);

  const onSearch = async (kw: string) => {
    setQuery(kw);
    if (kw.trim().length < 1) {
      setShowSearch(false);
      setResults([]);
      return;
    }
    try {
      const res = await searchStocksPinyin(kw.trim());
      const list = res.results || [];
      setResults(list.slice(0, 8));
      setShowSearch(list.length > 0);
    } catch {
      setResults([]);
      setShowSearch(false);
    }
  };

  const pickStock = (s: StockSearchResult) => {
    const code = s.symbol.replace(/^(sh|sz)/i, "");
    setSymbol(code);
    setName(s.name);
    setQuery(`${s.name} ${code}`);
    setShowSearch(false);
  };

  const start = async () => {
    const code = (symbol || query).replace(/[^0-9]/g, "");
    if (code.length !== 6) {
      setError("请输入 6 位 A 股代码，或从搜索结果中选择股票");
      return;
    }
    setError(null);
    setSubmitting(true);
    setJob(null);
    try {
      const started = await startDeepReport(code);
      setSymbol(started.symbol);
      setName(started.name || name);
      const j = await getDeepReport(started.job_id);
      setJob(j);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSubmitting(false);
    }
  };

  const html = useMemo(
    () => (job?.report_markdown ? renderMarkdown(job.report_markdown) : ""),
    [job?.report_markdown]
  );

  const running = job && (job.status === "queued" || job.status === "running");

  return (
    <main className="mx-auto max-w-[1100px] px-4 sm:px-6 lg:px-8 py-4 sm:py-6 lg:py-8 min-h-screen">
      <HeaderBar market="cn" />

      <section className="mt-4 card p-6 sm:p-8">
        <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-3 mb-6">
          <div>
            <h1 className="text-[26px] sm:text-[28px] font-bold tracking-tight text-text-primary">
              深度研报
            </h1>
            <p className="mt-2 text-[14px] text-text-secondary max-w-xl">
              输入一只 A 股，生成多角色详细研究报告，明确给出买 / 不买 / 观望结论。
              非闲聊问答；单次通常需要 1–3 分钟。
            </p>
          </div>
          <span className="text-[11px] px-2.5 py-1 rounded-full bg-purple-light text-purple-primary border border-purple-primary/20 self-start">
            TradingAgents 风格 · DeepSeek
          </span>
        </div>

        <div className="relative">
          <div className="flex flex-col sm:flex-row gap-3">
            <input
              value={query}
              onChange={(e) => onSearch(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") start();
              }}
              placeholder="输入代码或名称，例如：000524 或 岭南控股"
              className="flex-1 rounded-xl border border-border-subtle bg-bg-secondary px-4 py-3 text-[15px] text-text-primary outline-none focus:border-purple-primary/50 focus:ring-2 focus:ring-purple-primary/20"
            />
            <button
              type="button"
              onClick={start}
              disabled={submitting || !!running}
              className="rounded-xl bg-purple-primary px-6 py-3 text-[14px] font-semibold text-white hover:opacity-90 disabled:opacity-50 cursor-pointer transition-opacity"
            >
              {submitting || running ? "生成中…" : "生成研报"}
            </button>
          </div>

          {showSearch && results.length > 0 && (
            <div className="absolute z-20 left-0 right-0 sm:right-40 mt-2 rounded-xl border border-border-subtle bg-surface-card shadow-lg overflow-hidden">
              {results.map((s) => (
                <button
                  key={s.symbol}
                  type="button"
                  onClick={() => pickStock(s)}
                  className="w-full text-left px-4 py-2.5 text-[13px] hover:bg-purple-light/60 flex justify-between gap-3 cursor-pointer"
                >
                  <span className="font-medium text-text-primary">{s.name}</span>
                  <span className="font-mono text-text-tertiary">
                    {s.symbol.replace(/^(sh|sz)/i, "")}
                  </span>
                </button>
              ))}
            </div>
          )}
        </div>

        {error && (
          <div className="mt-4 rounded-xl border border-status-danger/30 bg-status-danger/10 px-4 py-3 text-[13px] text-status-danger">
            {error}
          </div>
        )}

        {job && (
          <div className="mt-6 rounded-xl border border-border-subtle bg-bg-tertiary/60 px-4 py-3 flex flex-wrap items-center gap-3 text-[13px]">
            <span className="text-text-secondary">
              {job.name || name || "—"}{" "}
              <span className="font-mono text-text-tertiary">{job.symbol || symbol}</span>
            </span>
            <span className="text-text-tertiary">·</span>
            <span className="text-text-secondary">{job.progress || job.status}</span>
            {job.decision && (
              <span className={`ml-auto text-[12px] font-semibold px-2.5 py-1 rounded-full ${decisionTone(job.decision)}`}>
                {job.decision}
              </span>
            )}
            {running && (
              <span className="inline-block w-4 h-4 rounded-full border-2 border-purple-primary/30 border-t-purple-primary animate-spin" />
            )}
          </div>
        )}
      </section>

      {job?.status === "error" && (
        <section className="mt-4 card p-6 text-[14px] text-status-danger">
          研报生成失败：{job.error || "未知错误"}
        </section>
      )}

      {job?.status === "done" && job.report_markdown && (
        <section className="mt-4 card p-6 sm:p-8">
          <div className="flex flex-wrap items-center justify-between gap-3 mb-6 pb-4 border-b border-border-subtle">
            <div>
              <h2 className="text-[20px] font-bold text-text-primary">
                {job.name}（{job.symbol}）研报
              </h2>
              <p className="mt-1 text-[12px] text-text-tertiary">
                引擎 {job.engine || "—"} · 耗时 {job.elapsed_seconds ?? "—"}s · 仅供研究，非投资建议
              </p>
            </div>
            {job.decision && (
              <div className={`text-[14px] font-bold px-3 py-1.5 rounded-full ${decisionTone(job.decision)}`}>
                {job.decision}
              </div>
            )}
          </div>
          <article
            className="deep-report prose-report"
            dangerouslySetInnerHTML={{ __html: html }}
          />
        </section>
      )}

      {recent.length > 0 && (
        <section className="mt-6">
          <h3 className="text-[15px] font-semibold text-text-primary mb-3">最近研报</h3>
          <div className="grid sm:grid-cols-2 gap-3">
            {recent.map((r) => (
              <button
                key={r.job_id}
                type="button"
                onClick={async () => {
                  try {
                    const j = await getDeepReport(r.job_id);
                    setJob(j);
                    setSymbol(j.symbol || "");
                    setName(j.name || "");
                    setQuery(`${j.name || ""} ${j.symbol || ""}`.trim());
                  } catch (e) {
                    setError(e instanceof Error ? e.message : String(e));
                  }
                }}
                className="card p-4 text-left hover:border-purple-primary/30 cursor-pointer transition-colors"
              >
                <div className="flex justify-between gap-2">
                  <span className="font-medium text-text-primary">
                    {r.name || "—"}{" "}
                    <span className="font-mono text-text-tertiary text-[12px]">{r.symbol}</span>
                  </span>
                  <span className={`text-[11px] px-2 py-0.5 rounded-full ${decisionTone(r.decision)}`}>
                    {r.decision || r.status}
                  </span>
                </div>
                <div className="mt-1 text-[11px] text-text-tertiary">
                  {r.created_at ? new Date(r.created_at).toLocaleString("zh-CN") : ""}
                </div>
              </button>
            ))}
          </div>
        </section>
      )}

      <style jsx global>{`
        .prose-report .md-h1 {
          font-size: 1.35rem;
          font-weight: 700;
          margin: 1.25rem 0 0.75rem;
          color: var(--color-text-primary);
        }
        .prose-report .md-h2 {
          font-size: 1.15rem;
          font-weight: 700;
          margin: 1.5rem 0 0.6rem;
          color: var(--color-text-primary);
          padding-bottom: 0.35rem;
          border-bottom: 1px solid var(--color-border-light);
        }
        .prose-report .md-h3 {
          font-size: 1rem;
          font-weight: 600;
          margin: 1rem 0 0.4rem;
          color: var(--color-text-primary);
        }
        .prose-report .md-p {
          font-size: 0.925rem;
          line-height: 1.75;
          color: var(--color-text-secondary);
          margin: 0.4rem 0;
        }
        .prose-report .md-ul {
          margin: 0.5rem 0 0.75rem 1.25rem;
          list-style: disc;
          color: var(--color-text-secondary);
          font-size: 0.925rem;
          line-height: 1.7;
        }
        .prose-report .md-pre {
          background: var(--color-bg-tertiary);
          border: 1px solid var(--color-border-light);
          border-radius: 12px;
          padding: 12px 14px;
          overflow-x: auto;
          font-size: 12px;
          margin: 0.75rem 0;
        }
        .prose-report strong {
          color: var(--color-text-primary);
          font-weight: 650;
        }
      `}</style>

      <p className="mt-8 text-center text-[12px] text-text-tertiary">
        深度研报仅供研究讨论，不构成投资建议。市场有风险，决策需独立判断。
      </p>
    </main>
  );
}

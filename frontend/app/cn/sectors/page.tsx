// AlphaPilot 板块研报 — 深度研报归档（整页打开）
"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { HeaderBar } from "@/components/HeaderBar";
import {
  fetchSectorResearchArchive,
  sectorResearchUrl,
  type SectorResearchEntry,
} from "@/lib/cn-api";

export default function SectorsPage() {
  const [researchLoading, setResearchLoading] = useState(true);
  const [researchErr, setResearchErr] = useState<string | null>(null);
  const [researchArchive, setResearchArchive] = useState<SectorResearchEntry[]>([]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setResearchLoading(true);
      setResearchErr(null);
      try {
        const list = await fetchSectorResearchArchive();
        if (cancelled) return;
        setResearchArchive(list);
      } catch (e) {
        if (!cancelled) {
          setResearchErr(e instanceof Error ? e.message : "研报加载失败");
        }
      } finally {
        if (!cancelled) setResearchLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <main className="mx-auto max-w-[1200px] px-4 sm:px-6 lg:px-8 py-4 sm:py-6 lg:py-8 min-h-screen">
      <HeaderBar market="cn" />

      <header className="mt-4">
        <Link
          href="/cn"
          className="mb-2 inline-flex items-center gap-1 text-[12px] text-text-secondary hover:text-status-info"
        >
          ← 返回工作台
        </Link>
        <h1 className="text-[26px] sm:text-[28px] font-bold tracking-tight text-text-primary">
          板块研报
        </h1>
        <p className="mt-1 text-[13px] text-text-secondary">盘中/盘后深度研报 · 整页打开</p>
      </header>

      <section className="mt-4 card p-6 sm:p-8">
        {researchLoading && (
          <div className="py-16 flex flex-col items-center gap-3">
            <div className="h-8 w-8 animate-spin rounded-full border-2 border-purple-primary border-t-transparent" />
            <p className="text-[13px] text-text-secondary">正在加载深度研报归档…</p>
          </div>
        )}
        {researchErr && (
          <div className="rounded-xl bg-status-danger/5 px-4 py-3 text-[13px] text-status-danger">
            {researchErr}
          </div>
        )}
        {!researchLoading && !researchErr && researchArchive.length === 0 && (
          <div className="py-10 text-center text-[13px] text-text-tertiary">
            暂无研报，等待盘中/盘后任务生成
          </div>
        )}
        {!researchLoading && researchArchive.length > 0 && (
          <div>
            <h2 className="text-[15px] font-semibold text-text-primary mb-1">
              深度研报归档
            </h2>
            <p className="text-[12px] text-text-tertiary mb-4">
              选择日期与场次，整页查看完整研报
            </p>
            <ul className="space-y-2">
              {researchArchive.flatMap((e) =>
                e.sessions.map((s) => (
                  <li key={${e.date}-}>
                    <a
                      href={sectorResearchUrl(e.date, s)}
                      className="flex items-center justify-between rounded-xl border border-border-subtle bg-bg-secondary px-4 py-3 text-[13px] text-text-primary no-underline hover:border-purple-primary/40 hover:bg-purple-light/40 transition-colors"
                    >
                      <span>
                        {e.date} · {s === "afternoon" ? "下午场" : "上午场"}
                      </span>
                      <span className="text-purple-primary text-[12px] font-medium">打开 →</span>
                    </a>
                  </li>
                ))
              )}
            </ul>
          </div>
        )}
      </section>

      <p className="mt-8 text-center text-[11px] text-text-tertiary">
        板块研报仅供研究，非投资建议
      </p>
    </main>
  );
}

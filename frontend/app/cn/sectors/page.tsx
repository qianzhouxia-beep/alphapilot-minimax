// AlphaPilot 板块研报 — 每日复盘（主）+ 每日复盘报告归档（次）
"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { HeaderBar } from "@/components/HeaderBar";
import {
  fetchDailyReviewArchive,
  dailyReviewUrl,
  type DailyReviewEntry,
} from "@/lib/cn-api";

// 每日复盘报告（自动化任务每日收盘后生成并刷新 latest.html）
const DAILY_REVIEW_URL = "/api/v1/cn/daily-review/latest.html";

export default function SectorsPage() {
  const [archiveLoading, setArchiveLoading] = useState(true);
  const [archiveErr, setArchiveErr] = useState<string | null>(null);
  const [archive, setArchive] = useState<DailyReviewEntry[]>([]);
  const [iframeFailed, setIframeFailed] = useState(false);
  const iframeRef = useRef<HTMLIFrameElement>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setArchiveLoading(true);
      setArchiveErr(null);
      try {
        const list = await fetchDailyReviewArchive();
        if (cancelled) return;
        setArchive(list);
      } catch (e) {
        if (!cancelled) {
          setArchiveErr(e instanceof Error ? e.message : "归档加载失败");
        }
      } finally {
        if (!cancelled) setArchiveLoading(false);
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
          板块研报 · 每日复盘
        </h1>
        <p className="mt-1 text-[13px] text-text-secondary">
          A 股每日收盘三维复盘 · 历史复盘报告归档
        </p>
      </header>

      {/* 主区块：A股每日复盘 */}
      <section className="mt-4 card p-6 sm:p-8">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-[17px] font-semibold text-text-primary">A 股每日复盘</h2>
            <p className="mt-1 text-[12px] text-text-tertiary">
              收盘后自动生成 · 每日更新 · 技术面三维分析（风险 / 进攻 / 情绪 / 主线）
            </p>
          </div>
          <a
            href={DAILY_REVIEW_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex shrink-0 items-center gap-1 rounded-xl bg-purple-primary px-4 py-2 text-[13px] font-medium text-white no-underline transition-opacity hover:opacity-90"
          >
            打开今日完整复盘 →
          </a>
        </div>

        <div className="mt-4 overflow-hidden rounded-xl border border-border-subtle bg-bg-secondary">
          {iframeFailed ? (
            <div className="flex flex-col items-center gap-2 py-16 text-[13px] text-text-tertiary">
              <p>预览加载失败，请直接打开完整报告。</p>
              <a
                href={DAILY_REVIEW_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="text-purple-primary underline"
              >
                打开今日完整复盘报告 →
              </a>
            </div>
          ) : (
            <iframe
              ref={iframeRef}
              src={DAILY_REVIEW_URL}
              title="A股每日复盘报告"
              className="block w-full"
              style={{ height: "1600px", border: "none" }}
              onError={() => setIframeFailed(true)}
            />
          )}
        </div>
        <p className="mt-3 text-[11px] text-text-tertiary">
          报告由自动化任务在每交易日收盘后生成，最新一期通过{" "}
          <code className="rounded bg-bg-tertiary px-1">latest.html</code>{" "}
          自动指向，无需手动更新。
        </p>
      </section>

      {/* 次区块：每日复盘报告归档 */}
      <section className="mt-6 card p-6 sm:p-8">
        <h2 className="mb-1 text-[15px] font-semibold text-text-primary">每日复盘报告归档</h2>
        <p className="mb-4 text-[12px] text-text-tertiary">
          收盘后自动生成 · 按日期归档 · 点击查看完整复盘
        </p>
        {archiveLoading && (
          <div className="flex flex-col items-center gap-3 py-16">
            <div className="h-8 w-8 animate-spin rounded-full border-2 border-purple-primary border-t-transparent" />
            <p className="text-[13px] text-text-secondary">正在加载复盘归档…</p>
          </div>
        )}
        {archiveErr && (
          <div className="rounded-xl bg-status-danger/5 px-4 py-3 text-[13px] text-status-danger">
            {archiveErr}
          </div>
        )}
        {!archiveLoading && !archiveErr && archive.length === 0 && (
          <div className="py-10 text-center text-[13px] text-text-tertiary">
            暂无归档，等待收盘后任务生成
          </div>
        )}
        {!archiveLoading && archive.length > 0 && (
          <ul className="space-y-2">
            {archive.map((e) => (
              <li key={e.file}>
                <a
                  href={dailyReviewUrl(e.file)}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center justify-between rounded-xl border border-border-subtle bg-bg-secondary px-4 py-3 text-[13px] text-text-primary no-underline transition-colors hover:border-purple-primary/40 hover:bg-purple-light/40"
                >
                  <span>{e.date}</span>
                  <span className="text-[12px] font-medium text-purple-primary">打开 →</span>
                </a>
              </li>
            ))}
          </ul>
        )}
      </section>

      <p className="mt-8 text-center text-[11px] text-text-tertiary">
        板块研报与每日复盘仅供研究，非投资建议
      </p>
    </main>
  );
}

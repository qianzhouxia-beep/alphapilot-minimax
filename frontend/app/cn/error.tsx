"use client";

// /cn/* 全局错误兜底：任何页面渲染异常（例如接口返回了意料之外的结构）
// 都显示友好提示 + 重试，而不是整页白屏 / 开发态报错。
import Link from "next/link";
import { useEffect } from "react";

export default function CNError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("[cn error boundary]", error);
  }, [error]);

  return (
    <main className="mx-auto flex min-h-[70vh] max-w-[560px] flex-col items-center justify-center px-6 text-center">
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-purple-light text-purple-primary" aria-hidden>
        <svg viewBox="0 0 24 24" className="h-6 w-6" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="10" />
          <path d="M12 8v4M12 16h.01" />
        </svg>
      </div>
      <h1 className="mt-5 text-[20px] font-semibold text-text-primary">页面暂时无法显示</h1>
      <p className="mt-2 text-[13px] leading-relaxed text-text-secondary">
        可能是数据返回异常或网络波动，我们已记录这个问题。请重试，或先回到首页。
      </p>
      <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
        <button
          type="button"
          onClick={reset}
          className="rounded-full bg-purple-primary px-6 py-2.5 text-[13px] font-semibold text-white hover:opacity-90"
        >
          重试
        </button>
        <Link href="/" className="text-[13px] font-medium text-text-secondary hover:text-text-primary">
          返回首页
        </Link>
      </div>
      <details className="mt-6 text-xs text-text-tertiary">
        <summary className="cursor-pointer select-none">查看技术详情</summary>
        <p className="mt-1 break-all">{error.message}</p>
      </details>
    </main>
  );
}

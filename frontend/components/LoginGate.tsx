// 登录后可见内容的占位组件（具体买入价 / 目标价 / 止损价 / 参考仓位 / 参考价 / 退出规则）。
// ⚠️ 这里只做前端展示层的隐藏；数据是否仍随接口返回由后端决定，请勿把它当作权限控制。
"use client";

import { usePathname } from "next/navigation";
import { useAuth } from "@/lib/auth";

export const LOCK_LABEL = "登录后查看参考价格";

/** 是否已登录（ready=false 表示还在读取本地会话，此时不要闪出"请登录"） */
export function useUnlocked(): { unlocked: boolean; ready: boolean } {
  const { session, ready } = useAuth();
  return { unlocked: !!session, ready };
}

function LockIcon({ className = "h-3.5 w-3.5" }: { className?: string }) {
  return (
    <svg aria-hidden viewBox="0 0 24 24" className={className} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="4" y="11" width="16" height="10" rx="2" />
      <path d="M8 11V8a4 4 0 0 1 8 0v3" />
    </svg>
  );
}

/**
 * 登录占位。
 * - inline：行内小胶囊，用于卡片里的价格位置
 * - block：整块提示，用于详情页价格区、今日计划规则区
 */
export function LockedHint({
  variant = "inline",
  label = LOCK_LABEL,
  note,
  className = "",
}: {
  variant?: "inline" | "block";
  label?: string;
  note?: string;
  className?: string;
}) {
  const { openAuth, ready } = useAuth();
  const pathname = usePathname();
  if (!ready) {
    return <span className={`text-text-disabled ${className}`} aria-hidden>—</span>;
  }
  const go = () => openAuth("login", pathname || "/cn");
  if (variant === "block") {
    return (
      <div className={`rounded-xl border border-dashed border-purple-primary/30 bg-purple-light/40 px-4 py-4 text-center ${className}`}>
        <div className="mx-auto mb-2 flex h-8 w-8 items-center justify-center rounded-full bg-white text-purple-primary shadow-sm">
          <LockIcon className="h-4 w-4" />
        </div>
        <p className="text-[13px] font-medium text-text-primary">{label}</p>
        {note && <p className="mt-1 text-[12px] leading-relaxed text-text-secondary">{note}</p>}
        <button
          type="button"
          onClick={go}
          className="mt-3 inline-flex cursor-pointer items-center rounded-full bg-purple-primary px-4 py-1.5 text-[12px] font-semibold text-on-primary transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-primary/50"
        >
          登录 / 注册
        </button>
      </div>
    );
  }
  return (
    <button
      type="button"
      onClick={go}
      className={`inline-flex cursor-pointer items-center gap-1 rounded-full border border-purple-primary/25 bg-purple-light/60 px-2 py-0.5 text-[11px] text-purple-primary transition-colors hover:bg-purple-light focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-primary/50 ${className}`}
    >
      <LockIcon className="h-3 w-3" />
      {label}
    </button>
  );
}

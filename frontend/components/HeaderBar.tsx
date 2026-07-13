// HeaderBar — client component, auth + nav
// 2026-07-09: 添加收藏追踪入口

"use client";

import Link from "next/link";
import Image from "next/image";
import { useI18n } from "@/lib/i18n";
import { useAuth } from "@/lib/auth";

export function HeaderBar({ market = "us" }: { market?: "us" | "cn" }) {
  const { t } = useI18n();
  const { session, logout } = useAuth();

  return (
    <header className="mb-4 sm:mb-6 flex flex-wrap items-center justify-between gap-3">
      <Link href="/" className="flex items-center gap-3">
        <Image src="/logo.png" alt="AlphaPilot" className="h-10 w-auto" width={120} height={40} priority />
        <p className="text-[12px] text-[#9FB0C7] hidden md:block">
          {t("site.subtitle")}
        </p>
      </Link>

      <div className="flex flex-wrap items-center gap-2 sm:gap-3">
        {/* Navigation */}
        <div className="flex items-center gap-1 rounded-lg border border-[#1D2A42]/50 bg-[#0C1728] p-0.5">
          <Link
            href="/cn"
            className="rounded-md px-2.5 py-1.5 text-[11px] text-[#9FB0C7] hover:text-[#EAF2FF] hover:bg-[rgba(77,163,255,0.1)] transition-colors"
          >
            Dashboard
          </Link>
          <Link
            href="/cn/watchlist"
            className="rounded-md px-2.5 py-1.5 text-[11px] text-[#F5C451] hover:text-[#EAF2FF] hover:bg-[rgba(245,196,81,0.15)] transition-colors flex items-center gap-1"
          >
            <svg className="w-4 h-4" viewBox="0 0 24 24" fill="currentColor" stroke="none"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg> 收藏追踪
          </Link>
          <Link
            href="/cn/backtest"
            className="rounded-md px-2.5 py-1.5 text-[11px] text-[#9FB0C7] hover:text-[#EAF2FF] hover:bg-[rgba(77,163,255,0.1)] transition-colors"
          >
            选股回测
          </Link>
          <Link
            href="/cn/paper-trading"
            className="rounded-md px-2.5 py-1.5 text-[11px] text-[#A78BFA] hover:text-[#EAF2FF] hover:bg-[rgba(139,92,246,0.15)] transition-colors flex items-center gap-1"
          >
            <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <rect x="2" y="3" width="20" height="14" rx="2" ry="2" /><line x1="8" y1="21" x2="16" y2="21" /><line x1="12" y1="17" x2="12" y2="21" />
            </svg>
            量化模拟盘
            <span className="text-[8px] px-1 py-0.5 rounded-sm bg-[rgba(139,92,246,0.15)] text-[#A78BFA] font-medium">量化</span>
          </Link>
          <Link
            href="/cn/chat"
            className="rounded-md px-2.5 py-1.5 text-[11px] text-[#9FB0C7] hover:text-[#EAF2FF] hover:bg-[rgba(77,163,255,0.1)] transition-colors"
          >
            AI 问股
          </Link>
          <Link
            href="/cn/news"
            className="rounded-md px-2.5 py-1.5 text-[11px] text-[#9FB0C7] hover:text-[#EAF2FF] hover:bg-[rgba(77,163,255,0.1)] transition-colors"
          >
            投资资讯
          </Link>
        </div>

        {/* Market status pill */}
        <div className="hidden items-center gap-2 rounded-lg border border-[#1D2A42] bg-[#0C1728] px-3 py-2 md:flex">
          <span className="h-2 w-2 rounded-full bg-[#3EE6A8]"></span>
          <span className="text-[11px] text-[#9FB0C7]">
            A 股交易中
          </span>
        </div>

        {/* Auth state */}
        {session ? (
          <div className="flex items-center gap-2 rounded-lg border border-[#1D2A42] bg-[#0C1728] px-2 sm:px-3 py-2">
            <div className="flex h-7 w-7 items-center justify-center rounded-full bg-gradient-to-br from-[#4DA3FF] to-[#7ddeff] text-[11px] font-semibold text-[#00315b]">
              {session.user.full_name.charAt(0).toUpperCase()}
            </div>
            <div className="text-left hidden sm:block">
              <div className="text-[12px] text-[#EAF2FF]">{session.user.full_name}</div>
              <div className="text-[10px] uppercase tracking-wider text-[#6E7C93]">
                {session.user.plan} · {session.user.credits || 0} credits
              </div>
            </div>
            <button
              onClick={logout}
              className="ml-2 text-[11px] text-[#6E7C93] hover:text-[#FF5D5D] hidden sm:inline"
            >
              {t("auth.signout")}
            </button>
          </div>
        ) : (
          <>
            <Link
              href="/login"
              className="rounded-lg border border-[#1D2A42] bg-[#0C1728] px-2 sm:px-3 py-2 text-[12px] text-[#9FB0C7] hover:border-[#4DA3FF] hover:text-[#EAF2FF] focus:outline-none focus:ring-2 focus:ring-[#4DA3FF]/50 transition-colors"
            >
              {t("auth.signin")}
            </Link>
            <Link
              href="/signup"
              className="rounded-lg bg-[#4DA3FF] px-2 sm:px-3 py-2 text-[12px] font-semibold text-[#00315b] hover:bg-[#7ddeff] focus:outline-none focus:ring-2 focus:ring-[#4DA3FF]/50 transition-colors"
            >
              {t("auth.signup")}
            </Link>
          </>
        )}
      </div>
    </header>
  );
}

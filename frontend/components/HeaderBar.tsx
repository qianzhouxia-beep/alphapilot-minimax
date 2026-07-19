// HeaderBar — client component, auth + nav
// 2026-07-15: 移动端导航优化 — 折叠为 Dashboard + 菜单按钮
"use client";

import { useState, useEffect, useRef } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import Image from "next/image";
import { useI18n } from "@/lib/i18n";
import { useAuth } from "@/lib/auth";

type NavItem = {
  href: string;
  label: string;
  colorClass: string;
  hoverClass: string;
  badge?: string;
  badgeClass?: string;
};

const NAV_ITEMS: NavItem[] = [
  {
    href: "/cn/screener",
    label: "智能选股",
    colorClass: "text-text-secondary",
    hoverClass: "hover:bg-[rgba(77,163,255,0.1)]",
  },
  {
    href: "/cn/watchlist",
    label: "收藏追踪",
    colorClass: "text-[#F5C451]",
    hoverClass: "hover:bg-[rgba(245,196,81,0.15)]",
  },
  {
    href: "/cn/backtest",
    label: "选股回测",
    colorClass: "text-text-secondary",
    hoverClass: "hover:bg-[rgba(77,163,255,0.1)]",
  },
  {
    href: "/cn/paper-trading",
    label: "量化模拟盘",
    colorClass: "text-status-info",
    hoverClass: "hover:bg-[rgba(139,92,246,0.15)]",
    badge: "量化",
    badgeClass: "bg-[rgba(139,92,246,0.15)] text-status-info",
  },
  {
    href: "/cn/chat",
    label: "AI 问股",
    colorClass: "text-text-secondary",
    hoverClass: "hover:bg-[rgba(77,163,255,0.1)]",
  },
  {
    href: "/cn/news",
    label: "投资资讯",
    colorClass: "text-text-secondary",
    hoverClass: "hover:bg-[rgba(77,163,255,0.1)]",
  },
];

export function HeaderBar({ market = "us" }: { market?: "us" | "cn" }) {
  const { t } = useI18n();
  const { session, logout } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const pathname = usePathname();

  // 点击外部关闭
  useEffect(() => {
    if (!menuOpen) return;
    function handleClick(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    }
    function handleEsc(e: KeyboardEvent) {
      if (e.key === "Escape") setMenuOpen(false);
    }
    document.addEventListener("mousedown", handleClick);
    document.addEventListener("keydown", handleEsc);
    return () => {
      document.removeEventListener("mousedown", handleClick);
      document.removeEventListener("keydown", handleEsc);
    };
  }, [menuOpen]);

  // 路由变化时关闭菜单
  useEffect(() => {
    setMenuOpen(false);
  }, [pathname]);

  const isActive = (href: string) => pathname === href || pathname?.startsWith(href + "/");

  return (
    <header className="mb-4 sm:mb-6 flex flex-wrap items-center justify-between gap-3">
      <Link href="/" className="flex items-center gap-3">
        <Image src="/logo.png?v=20260719" alt="AlphaPilot" className="h-9 sm:h-10 w-auto" width={180} height={40} priority />
        <p className="text-[12px] text-text-secondary hidden md:block">
          {t("site.subtitle")}
        </p>
      </Link>

      <div className="flex flex-wrap items-center gap-2 sm:gap-3">
        {/* ============ Desktop nav (md+) ============ */}
        <div className="hidden md:flex items-center gap-1 rounded-lg border border-border-subtle/50 bg-surface-card p-0.5">
          <Link
            href="/cn"
            className={`rounded-md px-2.5 py-1.5 text-[11px] transition-colors ${
              pathname === "/cn"
                ? "bg-[rgba(167,139,250,0.15)] text-text-primary"
                : "text-text-secondary hover:text-text-primary hover:bg-[rgba(77,163,255,0.1)]"
            }`}
          >
            Dashboard
          </Link>
          {NAV_ITEMS.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={`rounded-md px-2.5 py-1.5 text-[11px] transition-colors ${item.colorClass} hover:text-text-primary ${item.hoverClass}`}
            >
              {item.label}
              {item.badge && (
                <span className={`text-[8px] px-1 py-0.5 rounded-sm ${item.badgeClass} font-medium`}>
                  {item.badge}
                </span>
              )}
            </Link>
          ))}
        </div>

        {/* ============ Mobile nav (<md) — Dashboard + 菜单按钮 ============ */}
        <div ref={menuRef} className="md:hidden relative flex items-center gap-1 rounded-lg border border-border-subtle/50 bg-surface-card p-0.5">
          <Link
            href="/cn"
            className={`rounded-md px-2.5 py-1.5 text-[11px] transition-colors ${
              pathname === "/cn"
                ? "bg-[rgba(167,139,250,0.15)] text-text-primary"
                : "text-text-secondary hover:text-text-primary hover:bg-[rgba(77,163,255,0.1)]"
            }`}
          >
            Dashboard
          </Link>
          <button
            onClick={() => setMenuOpen(!menuOpen)}
            aria-label="打开菜单"
            aria-expanded={menuOpen}
            className={`rounded-md px-2 py-1.5 text-text-secondary hover:text-text-primary hover:bg-[rgba(77,163,255,0.1)] transition-colors flex items-center gap-1 ${
              menuOpen ? "bg-[rgba(167,139,250,0.15)]" : ""
            }`}
          >
            <span className="text-[11px]">{menuOpen ? "关闭" : "菜单"}</span>
          </button>

          {/* 下拉菜单面板 */}
          {menuOpen && (
            <div
              className="absolute top-full left-0 right-0 mt-2 mx-3 z-50 rounded-xl border border-border-subtle bg-surface-card/95 backdrop-blur-md shadow-2xl shadow-black/40 overflow-hidden"
              style={{ left: "auto", right: "12px", width: "max-content", minWidth: "180px" }}
            >
              <div className="px-3 py-2 border-b border-border-subtle/50">
                <p className="text-[10px] uppercase tracking-wider text-text-disabled">导航菜单</p>
              </div>
              <div className="py-1">
                {NAV_ITEMS.map((item) => (
                  <Link
                    key={item.href}
                    href={item.href}
                    onClick={() => setMenuOpen(false)}
                    className={`flex items-center gap-2 px-3 py-2.5 text-[13px] transition-colors ${item.colorClass} hover:bg-[rgba(255,255,255,0.05)] hover:text-text-primary ${
                      isActive(item.href) ? "bg-[rgba(167,139,250,0.1)] text-text-primary" : ""
                    }`}
                  >
                    <span className="flex-1">{item.label}</span>
                    {item.badge && (
                      <span className={`text-[8px] px-1.5 py-0.5 rounded ${item.badgeClass}`}>{item.badge}</span>
                    )}
                  </Link>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Market status pill */}
        <div className="hidden items-center gap-2 rounded-lg border border-border-subtle bg-surface-card px-3 py-2 md:flex">
          <span className="h-2 w-2 rounded-full bg-[#3EE6A8]"></span>
          <span className="text-[11px] text-text-secondary">
            A 股交易中
          </span>
        </div>

        {/* Auth state */}
        {session ? (
          <div className="flex items-center gap-2 rounded-lg border border-border-subtle bg-surface-card px-2 sm:px-3 py-2">
            <div className="text-left">
              <div className="text-[12px] text-text-primary font-medium">{session.user.full_name}</div>
              <div className="text-[10px] uppercase tracking-wider text-text-disabled">
                {session.user.plan}
              </div>
            </div>
            <button
              onClick={logout}
              className="ml-2 text-[11px] text-text-disabled hover:text-[#FF5D5D] hidden sm:inline"
            >
              {t("auth.signout")}
            </button>
          </div>
        ) : (
          <>
            <Link
              href="/login"
              className="rounded-lg border border-border-subtle bg-surface-card px-2 sm:px-3 py-2 text-[12px] text-text-secondary hover:border-status-info hover:text-text-primary focus:outline-none focus:ring-2 focus:ring-[#A78BFA]/50 transition-colors"
            >
              {t("auth.signin")}
            </Link>
            <Link
              href="/signup"
              className="rounded-lg bg-status-info px-2 sm:px-3 py-2 text-[12px] font-semibold text-on-primary hover:bg-[#C084FC] focus:outline-none focus:ring-2 focus:ring-[#A78BFA]/50 transition-colors"
            >
              {t("auth.signup")}
            </Link>
          </>
        )}
      </div>
    </header>
  );
}

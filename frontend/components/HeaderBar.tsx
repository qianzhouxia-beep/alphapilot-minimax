// HeaderBar — client component, auth + nav
// 2026-07-19: 浅色 token 统一 · 中文导航 · 可见 focus
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
  badge?: string;
};

const NAV_ITEMS: NavItem[] = [
  { href: "/cn/screener", label: "智能选股" },
  { href: "/cn/watchlist", label: "收藏追踪" },
  { href: "/cn/backtest", label: "选股回测" },
  { href: "/cn/paper-trading", label: "量化模拟盘", badge: "模拟" },
  { href: "/cn/chat", label: "深度研报" },
  { href: "/cn/sectors", label: "板块研报" },
];

const navIdle =
  "text-text-secondary hover:text-text-primary hover:bg-purple-light/80";
const navActive = "bg-purple-light text-purple-primary font-medium";
const focusRing =
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-primary/40 focus-visible:ring-offset-2 focus-visible:ring-offset-bg-primary";

export function HeaderBar({ market = "us" }: { market?: "us" | "cn" }) {
  const { t } = useI18n();
  const { session, logout, openAuth } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const pathname = usePathname();

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

  useEffect(() => {
    setMenuOpen(false);
  }, [pathname]);

  const isActive = (href: string) =>
    pathname === href || pathname?.startsWith(href + "/");
  const isHome = pathname === "/cn" || pathname === "/cn/";

  return (
    <header className="mb-4 sm:mb-6 flex flex-wrap items-center justify-between gap-3">
      <Link href="/" className={`flex items-center gap-3 rounded-lg ${focusRing}`}>
        <Image
          src="/logo.png?v=20260719"
          alt="AlphaPilot"
          className="h-8 w-auto"
          width={180}
          height={40}
          priority
        />
        <p className="text-[12px] text-text-secondary hidden lg:block">
          {t("site.subtitle")}
        </p>
      </Link>

      <div className="flex flex-wrap items-center gap-2 sm:gap-3">
        <div className="hidden md:flex items-center gap-0.5 rounded-xl border border-border-subtle bg-surface-card p-0.5 shadow-sm">
          <Link
            href="/cn"
            className={`rounded-lg px-2.5 py-1.5 text-[11px] transition-colors cursor-pointer ${focusRing} ${
              isHome ? navActive : navIdle
            }`}
          >
            工作台
          </Link>
          {NAV_ITEMS.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={`rounded-lg px-2.5 py-1.5 text-[11px] transition-colors cursor-pointer inline-flex items-center gap-1 ${focusRing} ${
                isActive(item.href) ? navActive : navIdle
              }`}
            >
              {item.label}
              {item.badge && (
                <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-purple-light text-purple-primary font-medium leading-none">
                  {item.badge}
                </span>
              )}
            </Link>
          ))}
        </div>

        <div
          ref={menuRef}
          className="md:hidden relative flex items-center gap-0.5 rounded-xl border border-border-subtle bg-surface-card p-0.5 shadow-sm"
        >
          <Link
            href="/cn"
            className={`rounded-lg px-2.5 py-1.5 text-[11px] transition-colors cursor-pointer ${focusRing} ${
              isHome ? navActive : navIdle
            }`}
          >
            工作台
          </Link>
          <button
            type="button"
            onClick={() => setMenuOpen(!menuOpen)}
            aria-label="打开菜单"
            aria-expanded={menuOpen}
            className={`rounded-lg px-2 py-1.5 text-[11px] transition-colors cursor-pointer ${focusRing} ${
              menuOpen ? navActive : navIdle
            }`}
          >
            {menuOpen ? "关闭" : "菜单"}
          </button>

          {menuOpen && (
            <div className="absolute top-full mt-2 z-50 rounded-xl border border-border-subtle bg-surface-card shadow-lg overflow-hidden"
              style={{ right: 0, width: "max-content", minWidth: "180px" }}
            >
              <div className="px-3 py-2 border-b border-border-subtle">
                <p className="text-[10px] uppercase tracking-wider text-text-tertiary">
                  导航
                </p>
              </div>
              <div className="py-1">
                {NAV_ITEMS.map((item) => (
                  <Link
                    key={item.href}
                    href={item.href}
                    onClick={() => setMenuOpen(false)}
                    className={`flex items-center gap-2 px-3 py-2.5 text-[13px] transition-colors cursor-pointer ${focusRing} ${
                      isActive(item.href) ? navActive : navIdle
                    }`}
                  >
                    <span className="flex-1">{item.label}</span>
                    {item.badge && (
                      <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-purple-light text-purple-primary font-medium leading-none">
                        {item.badge}
                      </span>
                    )}
                  </Link>
                ))}
              </div>
            </div>
          )}
        </div>

        <div className="hidden items-center gap-2 rounded-xl border border-border-subtle bg-surface-card px-3 py-2 md:flex shadow-sm">
          <span className="h-2 w-2 rounded-full bg-status-success" aria-hidden />
          <span className="text-[11px] text-text-secondary">A 股交易中</span>
        </div>

        {session ? (
          <div className="flex items-center gap-2 rounded-xl border border-border-subtle bg-surface-card px-2 sm:px-3 py-2 shadow-sm">
            <div className="text-left">
              <div className="text-[12px] text-text-primary font-medium">
                {session.user.full_name}
              </div>
              <div className="text-[10px] uppercase tracking-wider text-text-tertiary">
                {session.user.plan}
              </div>
            </div>
            <button
              type="button"
              onClick={logout}
              className={`ml-2 text-[11px] text-text-tertiary hover:text-status-danger hidden sm:inline cursor-pointer ${focusRing} rounded`}
            >
              {t("auth.signout")}
            </button>
          </div>
        ) : (
          <>
            <button
              type="button"
              onClick={() => openAuth("login", pathname || "/cn")}
              className={`rounded-xl border border-border-subtle bg-surface-card px-2 sm:px-3 py-2 text-[12px] text-text-secondary hover:border-purple-primary/40 hover:text-text-primary transition-colors cursor-pointer ${focusRing}`}
            >
              {t("auth.signin")}
            </button>
            <button
              type="button"
              onClick={() => openAuth("signup", pathname || "/cn")}
              className={`rounded-xl bg-purple-primary px-2 sm:px-3 py-2 text-[12px] font-semibold text-on-primary hover:opacity-90 transition-opacity cursor-pointer ${focusRing}`}
            >
              {t("auth.signup")}
            </button>
          </>
        )}
      </div>
    </header>
  );
}

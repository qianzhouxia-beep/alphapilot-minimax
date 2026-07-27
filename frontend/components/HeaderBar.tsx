// HeaderBar — client component, auth + nav
// 2026-07-21: 公私分层主航 — 工作台 / 选股▾ / 研报▾ / 我的▾
"use client";

import { useState, useEffect, useRef } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import Image from "next/image";
import { useI18n } from "@/lib/i18n";
import { useAuth } from "@/lib/auth";

type NavLink = {
  href: string;
  label: string;
  badge?: string;
  requireAuth?: boolean;
};

type NavGroup = {
  id: string;
  label: string;
  items: NavLink[];
};

const SELECT_ITEMS: NavLink[] = [
  { href: "/cn/screener", label: "智能选股" },
  { href: "/cn/backtest", label: "选股回测" },
];

const RESEARCH_ITEMS: NavLink[] = [
  { href: "/cn/chat", label: "深度研报" },
  { href: "/cn/sectors", label: "板块研报" },
];

const MINE_ITEMS: NavLink[] = [
  { href: "/cn/watchlist", label: "收藏追踪", requireAuth: true },
  { href: "/cn/paper-trading", label: "量化模拟盘", badge: "模拟", requireAuth: true },
];

const NAV_GROUPS: NavGroup[] = [
  { id: "select", label: "选股", items: SELECT_ITEMS },
  { id: "research", label: "研报", items: RESEARCH_ITEMS },
  { id: "mine", label: "我的", items: MINE_ITEMS },
];

const navIdle =
  "text-text-secondary hover:text-text-primary hover:bg-purple-light/80";
const navActive = "bg-purple-light text-purple-primary font-medium";
const focusRing =
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-primary/40 focus-visible:ring-offset-2 focus-visible:ring-offset-bg-primary";

function Chevron({ open }: { open: boolean }) {
  return (
    <svg
      aria-hidden
      viewBox="0 0 12 12"
      className={`h-2.5 w-2.5 opacity-60 transition-transform ${open ? "rotate-180" : ""}`}
    >
      <path
        d="M2.5 4.5 L6 8 L9.5 4.5"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function HeaderBar({ market = "us" }: { market?: "us" | "cn" }) {
  const { t } = useI18n();
  const { session, logout, openAuth } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);
  const [openGroup, setOpenGroup] = useState<string | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const desktopRef = useRef<HTMLDivElement>(null);
  const pathname = usePathname();

  useEffect(() => {
    if (!menuOpen && !openGroup) return;
    function handleClick(e: MouseEvent) {
      const t = e.target as Node;
      if (menuRef.current && !menuRef.current.contains(t)) setMenuOpen(false);
      if (desktopRef.current && !desktopRef.current.contains(t)) setOpenGroup(null);
    }
    function handleEsc(e: KeyboardEvent) {
      if (e.key === "Escape") {
        setMenuOpen(false);
        setOpenGroup(null);
      }
    }
    document.addEventListener("mousedown", handleClick);
    document.addEventListener("keydown", handleEsc);
    return () => {
      document.removeEventListener("mousedown", handleClick);
      document.removeEventListener("keydown", handleEsc);
    };
  }, [menuOpen, openGroup]);

  useEffect(() => {
    setMenuOpen(false);
    setOpenGroup(null);
  }, [pathname]);

  const isActive = (href: string) =>
    pathname === href || pathname?.startsWith(href + "/");
  const isHome = pathname === "/cn" || pathname === "/cn/";
  const isGroupActive = (items: NavLink[]) => items.some((it) => isActive(it.href));

  function handleMineClick(item: NavLink, close?: () => void) {
    if (item.requireAuth && !session) {
      openAuth("login", item.href);
      close?.();
      return;
    }
    close?.();
  }

  function renderDropdownItem(
    item: NavLink,
    opts?: { onNavigate?: () => void; dense?: boolean }
  ) {
    const locked = Boolean(item.requireAuth && !session);
    const active = isActive(item.href);
    const className = `flex items-center gap-2 px-3 ${
      opts?.dense ? "py-2 text-[12px]" : "py-2.5 text-[13px]"
    } transition-colors cursor-pointer ${focusRing} ${
      active ? navActive : navIdle
    }`;

    if (locked) {
      return (
        <button
          key={item.href}
          type="button"
          onClick={() => handleMineClick(item, opts?.onNavigate)}
          className={`${className} w-full text-left`}
        >
          <span className="flex-1">{item.label}</span>
          {item.badge && (
            <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-purple-light text-purple-primary font-medium leading-none">
              {item.badge}
            </span>
          )}
          <span className="text-[10px] text-text-tertiary">登录</span>
        </button>
      );
    }

    return (
      <Link
        key={item.href}
        href={item.href}
        onClick={() => opts?.onNavigate?.()}
        className={className}
      >
        <span className="flex-1">{item.label}</span>
        {item.badge && (
          <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-purple-light text-purple-primary font-medium leading-none">
            {item.badge}
          </span>
        )}
      </Link>
    );
  }

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
        {/* Desktop: 工作台 + 三个下拉 */}
        <div
          ref={desktopRef}
          className="hidden md:flex items-center gap-0.5 rounded-xl border border-border-subtle bg-surface-card p-0.5 shadow-sm"
        >
          <Link
            href="/cn"
            className={`rounded-lg px-2.5 py-1.5 text-[11px] transition-colors cursor-pointer ${focusRing} ${
              isHome ? navActive : navIdle
            }`}
          >
            工作台
          </Link>
          <a
            href="/api/v1/cn/framework"
            className={`rounded-lg px-2.5 py-1.5 text-[11px] transition-colors cursor-pointer ${focusRing} ${navIdle}`}
            target="_blank" rel="noopener noreferrer"
          >
            策略全景
          </a>

          {NAV_GROUPS.map((group) => {
            const open = openGroup === group.id;
            const active = isGroupActive(group.items);
            return (
              <div key={group.id} className="relative">
                <button
                  type="button"
                  aria-expanded={open}
                  aria-haspopup="menu"
                  onClick={() => setOpenGroup(open ? null : group.id)}
                  className={`rounded-lg px-2.5 py-1.5 text-[11px] transition-colors cursor-pointer inline-flex items-center gap-1 ${focusRing} ${
                    active || open ? navActive : navIdle
                  }`}
                >
                  {group.label}
                  <Chevron open={open} />
                </button>
                {open && (
                  <div
                    role="menu"
                    className="absolute top-full left-0 mt-2 z-50 min-w-[168px] rounded-xl border border-border-subtle bg-surface-card shadow-lg overflow-hidden"
                  >
                    {group.id === "mine" && !session && (
                      <div className="px-3 py-2 border-b border-border-subtle">
                        <p className="text-[10px] text-text-tertiary leading-snug">
                          登录后同步个人数据
                        </p>
                      </div>
                    )}
                    <div className="py-1">
                      {group.items.map((item) =>
                        renderDropdownItem(item, {
                          dense: true,
                          onNavigate: () => setOpenGroup(null),
                        })
                      )}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* Mobile: 工作台 + 菜单 */}
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
            className={`rounded-lg px-2 py-1.5 text-[11px] transition-colors cursor-pointer inline-flex items-center gap-1 ${focusRing} ${
              menuOpen ? navActive : navIdle
            }`}
          >
            {menuOpen ? "关闭" : "菜单"}
            <Chevron open={menuOpen} />
          </button>

          {menuOpen && (
            <div
              className="absolute top-full mt-2 z-50 rounded-xl border border-border-subtle bg-surface-card shadow-lg overflow-y-auto"
              style={{ right: 0, maxWidth: "calc(100vw - 32px)", maxHeight: "70vh", minWidth: "180px" }}
            >
              <div className="py-1 border-b border-border-subtle">
                <a
                  href="/api/v1/cn/framework"
                  target="_blank"
                  rel="noopener noreferrer"
                  onClick={() => setMenuOpen(false)}
                  className={`block px-3 py-2.5 text-[12px] transition-colors ${navIdle}`}
                >
                  策略全景
                </a>
              </div>
              {NAV_GROUPS.map((group) => (
                <div key={group.id}>
                  <div className="px-3 py-2 border-b border-border-subtle bg-surface-panel/60">
                    <p className="text-[10px] uppercase tracking-wider text-text-tertiary">
                      {group.label}
                    </p>
                  </div>
                  <div className="py-1">
                    {group.id === "mine" && !session && (
                      <p className="px-3 py-1.5 text-[10px] text-text-tertiary">
                        登录后同步个人数据
                      </p>
                    )}
                    {group.items.map((item) =>
                      renderDropdownItem(item, {
                        onNavigate: () => setMenuOpen(false),
                      })
                    )}
                  </div>
                </div>
              ))}
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

// HeaderBar — client component, auth + nav
// 2026-07-21: 公私分层主航 — 工作台 / 策略全景 / 选股回测 / 研报▾ / 我的▾
// 2026-08-11: 选股▾ 仅剩回测一项，取消下拉直接展示「选股回测」
// 2026-10-02: 重做：sticky + 轻模糊、分组下拉(键盘/aria)、移动端面板、右侧状态/用户/套餐/退出收拢
"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import Image from "next/image";
import { useI18n } from "@/lib/i18n";
import { useAuth } from "@/lib/auth";
import { MARKET_STATUS_NOTE, useMarketStatus } from "@/lib/market-status";

type NavLink = {
  href: string;
  label: string;
  badge?: string;
  requireAuth?: boolean;
  hint?: string;
};

type NavGroup = {
  id: string;
  label: string;
  items: NavLink[];
};

const DIRECT_LINKS: NavLink[] = [
  { href: "/cn", label: "工作台" },
  { href: "/cn/framework", label: "策略全景" },
  { href: "/cn/backtest", label: "选股回测" },
  { href: "/cn/forum", label: "社区" },
];

const NAV_GROUPS: NavGroup[] = [
  {
    id: "research",
    label: "研报",
    items: [
      { href: "/cn/chat", label: "深度研报", hint: "个股研究报告" },
      { href: "/cn/sectors", label: "板块研报", hint: "行业板块观察" },
    ],
  },
  {
    id: "flow",
    label: "资金",
    items: [{ href: "/cn/funds", label: "资金流向看板", hint: "主力资金与阶段" }],
  },
  {
    id: "mine",
    label: "我的",
    items: [
      { href: "/cn/watchlist", label: "收藏追踪", requireAuth: true, hint: "我关注的股票" },
      { href: "/cn/paper-trading", label: "量化模拟盘", badge: "模拟", requireAuth: true, hint: "虚拟资金演练" },
    ],
  },
];

const focusRing =
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-primary/50";
const pillBase = `rounded-full px-2.5 xl:px-3 py-1.5 text-[13px] leading-5 whitespace-nowrap transition-colors cursor-pointer select-none ${focusRing}`;
const pillIdle = "text-text-secondary hover:text-text-primary hover:bg-black/[0.04]";
const pillActive = "bg-purple-light text-purple-primary font-semibold";
const itemIdle = "text-text-secondary hover:text-text-primary hover:bg-black/[0.04]";
const itemActive = "bg-purple-light/70 text-purple-primary font-medium";

function Chevron({ open }: { open: boolean }) {
  return (
    <svg
      aria-hidden
      viewBox="0 0 12 12"
      className={`h-2.5 w-2.5 opacity-60 transition-transform ${open ? "rotate-180" : ""}`}
    >
      <path d="M2.5 4.5 L6 8 L9.5 4.5" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function Badge({ children }: { children: React.ReactNode }) {
  return (
    <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-purple-light text-purple-primary font-medium leading-none">
      {children}
    </span>
  );
}

function PlanBadge({ plan }: { plan: string }) {
  const free = !plan || plan.toLowerCase() === "free";
  return (
    <span
      className={`inline-flex items-center rounded-full px-1.5 py-[1px] text-[10px] font-semibold uppercase leading-4 tracking-wide ${
        free ? "bg-black/[0.06] text-text-tertiary" : "bg-purple-light text-purple-primary"
      }`}
    >
      {plan || "free"}
    </span>
  );
}

function StatusPill({ compact = false }: { compact?: boolean }) {
  const s = useMarketStatus();
  const dot =
    !s ? "bg-black/20" : s.tone === "live" ? "bg-status-success" : s.tone === "wait" ? "bg-status-warning" : "bg-black/30";
  return (
    <div
      className={`inline-flex items-center gap-1.5 rounded-full border border-border-subtle bg-white/70 px-2.5 py-1.5 text-[12px] text-text-secondary whitespace-nowrap ${
        compact ? "" : "shadow-sm"
      }`}
      role="status"
      title={s ? `${s.label} · 北京时间 ${s.clock}。${MARKET_STATUS_NOTE}` : undefined}
    >
      <span className="relative flex h-2 w-2" aria-hidden>
        {s?.tone === "live" && (
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-status-success opacity-50 motion-reduce:hidden" />
        )}
        <span className={`relative inline-flex h-2 w-2 rounded-full ${dot}`} />
      </span>
      <span>{s ? s.label : "A 股"}</span>
    </div>
  );
}

export function HeaderBar({ market = "us" }: { market?: "us" | "cn" }) {
  void market;
  const { t } = useI18n();
  const { session, logout, openAuth } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);
  const [openGroup, setOpenGroup] = useState<string | null>(null);
  const pathname = usePathname();
  const rootRef = useRef<HTMLElement>(null);
  const toggleRef = useRef<HTMLButtonElement>(null);
  const groupBtnRefs = useRef<Record<string, HTMLButtonElement | null>>({});
  const focusFirstItem = useRef(false);

  const closeAll = useCallback(() => {
    setMenuOpen(false);
    setOpenGroup(null);
  }, []);

  // 点击外部 / Esc 关闭；Esc 后焦点回到触发按钮
  useEffect(() => {
    if (!menuOpen && !openGroup) return;
    function onDown(e: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) closeAll();
    }
    function onKey(e: KeyboardEvent) {
      if (e.key !== "Escape") return;
      if (openGroup) groupBtnRefs.current[openGroup]?.focus();
      else if (menuOpen) toggleRef.current?.focus();
      closeAll();
    }
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [menuOpen, openGroup, closeAll]);

  // 路由变化 / 视口放大到桌面宽度时收起
  useEffect(() => {
    closeAll();
  }, [pathname, closeAll]);
  useEffect(() => {
    const mq = window.matchMedia("(min-width: 1024px)");
    const onChange = () => mq.matches && closeAll();
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [closeAll]);

  // 下拉打开后（键盘触发）聚焦第一项
  useEffect(() => {
    if (openGroup && focusFirstItem.current) {
      focusFirstItem.current = false;
      rootRef.current
        ?.querySelector<HTMLElement>(`[data-menu="${openGroup}"] [role="menuitem"]`)
        ?.focus();
    }
  }, [openGroup]);

  const isActive = (href: string) =>
    pathname === href || pathname === href + "/" || pathname?.startsWith(href + "/");
  const isHome = pathname === "/cn" || pathname === "/cn/";
  const linkActive = (l: NavLink) => (l.href === "/cn" ? isHome : isActive(l.href));
  const isGroupActive = (items: NavLink[]) => items.some((it) => isActive(it.href));

  function onMenuKey(e: React.KeyboardEvent<HTMLDivElement>, groupId: string) {
    const items = Array.from(
      e.currentTarget.querySelectorAll<HTMLElement>('[role="menuitem"]')
    );
    const idx = items.indexOf(document.activeElement as HTMLElement);
    if (e.key === "ArrowDown") {
      e.preventDefault();
      items[(idx + 1) % items.length]?.focus();
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      items[(idx - 1 + items.length) % items.length]?.focus();
    } else if (e.key === "Home") {
      e.preventDefault();
      items[0]?.focus();
    } else if (e.key === "End") {
      e.preventDefault();
      items[items.length - 1]?.focus();
    } else if (e.key === "Tab") {
      setOpenGroup((g) => (g === groupId ? null : g));
    }
  }

  function onGroupBtnKey(e: React.KeyboardEvent, groupId: string) {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      focusFirstItem.current = true;
      if (openGroup === groupId) {
        rootRef.current
          ?.querySelector<HTMLElement>(`[data-menu="${groupId}"] [role="menuitem"]`)
          ?.focus();
        focusFirstItem.current = false;
      } else setOpenGroup(groupId);
    }
  }

  function renderItem(item: NavLink, variant: "menu" | "panel") {
    const locked = Boolean(item.requireAuth && !session);
    const active = isActive(item.href);
    const cls = `flex w-full items-center gap-2 text-left transition-colors cursor-pointer ${focusRing} ${
      variant === "menu" ? "rounded-lg px-3 py-2 text-[13px]" : "rounded-xl px-3 py-3 text-[14px]"
    } ${active ? itemActive : itemIdle}`;
    const inner = (
      <>
        <span className="flex-1 min-w-0">
          <span className="block truncate">{item.label}</span>
          {variant === "menu" && (locked || item.hint) && (
            <span className="block truncate text-[11px] font-normal text-text-tertiary">
              {locked ? "登录后使用" : item.hint}
            </span>
          )}
        </span>
        {item.badge && <Badge>{item.badge}</Badge>}
        {locked && variant === "panel" && (
          <span className="text-[11px] text-text-tertiary whitespace-nowrap">登录后使用</span>
        )}
      </>
    );
    if (locked) {
      return (
        <button
          key={item.href}
          type="button"
          role={variant === "menu" ? "menuitem" : undefined}
          onClick={() => {
            closeAll();
            openAuth("login", item.href);
          }}
          className={cls}
        >
          {inner}
        </button>
      );
    }
    return (
      <Link
        key={item.href}
        href={item.href}
        role={variant === "menu" ? "menuitem" : undefined}
        aria-current={active ? "page" : undefined}
        onClick={closeAll}
        className={cls}
      >
        {inner}
      </Link>
    );
  }

  const initial = (session?.user.full_name || session?.user.email || "?").trim().charAt(0).toUpperCase();

  return (
    <header ref={rootRef} className="sticky top-2 z-40 mb-4 sm:mb-6">
      <div className="flex h-14 items-center gap-2 rounded-2xl border border-border-subtle bg-white/80 px-3 shadow-[0_1px_3px_rgba(0,0,0,0.05)] backdrop-blur-md supports-[backdrop-filter]:bg-white/65 sm:px-4">
        {/* 左：Logo + 标语 */}
        <Link href="/" aria-label="AlphaPilot 首页" className={`flex shrink-0 items-center gap-3 rounded-lg ${focusRing}`}>
          <Image
            src="/logo.png?v=20260719"
            alt="AlphaPilot"
            className="h-8 w-auto"
            width={180}
            height={40}
            priority
          />
          <p className="hidden whitespace-nowrap border-l border-border-subtle pl-3 text-[12px] text-text-secondary xl:block">
            {t("site.subtitle")}
          </p>
        </Link>

        {/* 中：桌面主导航 */}
        <nav aria-label="主导航" className="hidden min-w-0 flex-1 items-center justify-center lg:flex">
          <ul className="flex items-center gap-0.5 rounded-full bg-black/[0.035] p-1">
            {DIRECT_LINKS.map((l) => {
              const active = linkActive(l);
              return (
                <li key={l.href}>
                  <Link
                    href={l.href}
                    aria-current={active ? "page" : undefined}
                    className={`${pillBase} block ${active ? pillActive : pillIdle}`}
                  >
                    {l.label}
                  </Link>
                </li>
              );
            })}
            {NAV_GROUPS.map((group) => {
              const open = openGroup === group.id;
              const active = isGroupActive(group.items);
              const menuId = `nav-menu-${group.id}`;
              return (
                <li key={group.id} className="relative">
                  <button
                    ref={(el) => {
                      groupBtnRefs.current[group.id] = el;
                    }}
                    type="button"
                    aria-expanded={open}
                    aria-haspopup="menu"
                    aria-controls={open ? menuId : undefined}
                    onClick={() => setOpenGroup(open ? null : group.id)}
                    onKeyDown={(e) => onGroupBtnKey(e, group.id)}
                    className={`${pillBase} inline-flex items-center gap-1 ${
                      active ? pillActive : open ? "bg-black/[0.06] text-text-primary" : pillIdle
                    }`}
                  >
                    {group.label}
                    <Chevron open={open} />
                  </button>
                  {open && (
                    <div
                      id={menuId}
                      data-menu={group.id}
                      role="menu"
                      aria-label={group.label}
                      onKeyDown={(e) => onMenuKey(e, group.id)}
                      className="absolute left-1/2 top-full z-50 mt-2 min-w-[220px] -translate-x-1/2 rounded-2xl border border-border-subtle bg-white p-1.5 shadow-lg"
                    >
                      {group.id === "mine" && !session && (
                        <p className="px-3 pb-1.5 pt-1 text-[11px] text-text-tertiary">登录后同步个人数据</p>
                      )}
                      {group.items.map((it) => renderItem(it, "menu"))}
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        </nav>

        {/* 右：状态 / 用户 / 登录 / 汉堡 */}
        <div className="ml-auto flex shrink-0 items-center gap-2">
          <div className="hidden sm:block">
            <StatusPill />
          </div>

          {session ? (
            <div className="flex items-center gap-2 rounded-full border border-border-subtle bg-white/70 py-1 pl-1 pr-1 sm:pr-3">
              <span
                aria-hidden
                className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-purple-primary text-[13px] font-semibold text-white"
              >
                {initial}
              </span>
              <div className="hidden min-w-0 flex-col leading-tight sm:flex">
                <span className="max-w-[96px] truncate text-[13px] font-medium text-text-primary">
                  {session.user.full_name}
                </span>
                <span className="mt-0.5">
                  <PlanBadge plan={session.user.plan} />
                </span>
              </div>
              <span aria-hidden className="mx-0.5 hidden h-5 w-px bg-border-subtle sm:block" />
              <button
                type="button"
                onClick={logout}
                className={`hidden rounded-full px-1.5 py-1 text-[12px] text-text-tertiary transition-colors hover:text-status-danger sm:inline cursor-pointer ${focusRing}`}
              >
                {t("auth.signout")}
              </button>
            </div>
          ) : (
            <>
              <button
                type="button"
                onClick={() => openAuth("login", pathname || "/cn")}
                className={`rounded-full border border-border-subtle bg-white/70 px-3.5 py-1.5 text-[13px] text-text-secondary transition-colors hover:border-purple-primary/40 hover:text-text-primary cursor-pointer ${focusRing}`}
              >
                {t("auth.signin")}
              </button>
              <button
                type="button"
                onClick={() => openAuth("signup", pathname || "/cn")}
                className={`hidden rounded-full bg-purple-primary px-3.5 py-1.5 text-[13px] font-semibold text-on-primary transition-opacity hover:opacity-90 sm:inline-block cursor-pointer ${focusRing}`}
              >
                {t("auth.signup")}
              </button>
            </>
          )}

          <button
            ref={toggleRef}
            type="button"
            aria-label={menuOpen ? "关闭菜单" : "打开菜单"}
            aria-expanded={menuOpen}
            aria-controls="mobile-nav"
            onClick={() => {
              setOpenGroup(null);
              setMenuOpen((v) => !v);
            }}
            className={`flex h-10 w-10 items-center justify-center rounded-full text-text-primary transition-colors hover:bg-black/[0.05] lg:hidden cursor-pointer ${focusRing} ${
              menuOpen ? "bg-purple-light text-purple-primary" : ""
            }`}
          >
            <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden>
              {menuOpen ? <path d="M6 6l12 12M18 6L6 18" /> : <path d="M4 7h16M4 12h16M4 17h16" />}
            </svg>
          </button>
        </div>
      </div>

      {/* 移动端面板（<1024px） */}
      {menuOpen && (
        <nav
          id="mobile-nav"
          aria-label="移动端导航"
          className="absolute inset-x-0 top-full z-50 mt-2 max-h-[calc(100dvh-5rem)] overflow-y-auto overscroll-contain rounded-2xl border border-border-subtle bg-white p-3 shadow-xl lg:hidden"
        >
          <div className="grid gap-0.5">
            {DIRECT_LINKS.map((l) => {
              const active = linkActive(l);
              return (
                <Link
                  key={l.href}
                  href={l.href}
                  aria-current={active ? "page" : undefined}
                  onClick={closeAll}
                  className={`rounded-xl px-3 py-3 text-[14px] transition-colors ${focusRing} ${active ? itemActive : itemIdle}`}
                >
                  {l.label}
                </Link>
              );
            })}
          </div>
          {NAV_GROUPS.map((group) => (
            <div key={group.id} className="mt-2 border-t border-border-subtle pt-2" role="group" aria-label={group.label}>
              <p className="px-3 pb-1 pt-1 text-[11px] font-medium tracking-wider text-text-tertiary">{group.label}</p>
              <div className="grid gap-0.5">
                {group.items.map((it) => renderItem(it, "panel"))}
              </div>
            </div>
          ))}

          <div className="mt-3 border-t border-border-subtle pt-3">
            <div className="flex items-center justify-between gap-3 px-1">
              <StatusPill compact />
              {session ? (
                <div className="flex min-w-0 items-center gap-2">
                  <span className="max-w-[120px] truncate text-[13px] font-medium text-text-primary">
                    {session.user.full_name}
                  </span>
                  <PlanBadge plan={session.user.plan} />
                </div>
              ) : null}
            </div>
            <div className="mt-3 grid gap-2">
              {session ? (
                <button
                  type="button"
                  onClick={() => {
                    closeAll();
                    logout();
                  }}
                  className={`w-full rounded-xl border border-border-subtle py-2.5 text-[14px] text-text-secondary transition-colors hover:text-status-danger cursor-pointer ${focusRing}`}
                >
                  {t("auth.signout")}
                </button>
              ) : (
                <div className="grid grid-cols-2 gap-2">
                  <button
                    type="button"
                    onClick={() => {
                      closeAll();
                      openAuth("login", pathname || "/cn");
                    }}
                    className={`rounded-xl border border-border-subtle py-2.5 text-[14px] text-text-secondary cursor-pointer ${focusRing}`}
                  >
                    {t("auth.signin")}
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      closeAll();
                      openAuth("signup", pathname || "/cn");
                    }}
                    className={`rounded-xl bg-purple-primary py-2.5 text-[14px] font-semibold text-on-primary cursor-pointer ${focusRing}`}
                  >
                    {t("auth.signup")}
                  </button>
                </div>
              )}
            </div>
          </div>
        </nav>
      )}
    </header>
  );
}

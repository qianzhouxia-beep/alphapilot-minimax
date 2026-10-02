"use client";

import { useState, useEffect, useRef } from "react";
import Image from "next/image";
import Link from "next/link";
import {
  FaqSection,
  HowItWorks,
  PerformanceSection,
  RiskNotice,
  SampleCard,
  SectionHead,
  SiteFooter,
} from "@/components/landing/Sections";
import { RISK_SHORT } from "@/lib/landing-content";

// 指数数据类型
interface IndexData {
  name: string;
  value: string;
  change: string;
  isUp: boolean;
  /** 无数据时的占位（不着红绿色、不画走势线） */
  empty?: boolean;
}

// 指数默认占位（API 失败时显示）
const PLACEHOLDER_INDICES: IndexData[] = [
  { name: "上证指数", value: "—", change: "—", isUp: true, empty: true },
  { name: "深证成指", value: "—", change: "—", isUp: true, empty: true },
  { name: "创业板指", value: "—", change: "—", isUp: true, empty: true },
];

// 从价格数组构建 SVG 分时线路径
function buildSparklinePath(prices: number[], w: number, h: number): string {
  if (!prices || prices.length < 2) return "";
  const min = Math.min(...prices);
  const max = Math.max(...prices);
  const range = max - min || 1;
  const stepX = w / (prices.length - 1);
  return prices
    .map((p, i) => {
      const x = i * stepX;
      const y = h - ((p - min) / range) * h;
      return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
}

// Sparkline SVG 组件：仅在有真实分时数据时绘制（不再用假折线占位）
function Sparkline({ isUp, prices }: { isUp: boolean; prices?: number[] }) {
  if (!prices || prices.length < 2) return null;
  const color = isUp ? "#FF3B30" : "#34C759"; // 红涨绿跌
  return (
    <svg
      className="absolute right-5 top-1/2 -translate-y-1/2 w-20 h-10 opacity-30"
      viewBox="0 0 80 40"
      fill="none"
      stroke={color}
      strokeWidth="1.5"
      aria-hidden
    >
      <path d={buildSparklinePath(prices, 80, 40)} />
    </svg>
  );
}

// 导航栏：页内锚点（了解产品）+ 站内页面（进入使用）两组
const NAV_ANCHORS = [
  { name: "工作原理", href: "/#how", id: "how" },
  { name: "模型指标", href: "/#performance", id: "performance" },
  { name: "常见问题", href: "/#faq", id: "faq" },
];
const NAV_PAGES = [
  { name: "工作台", href: "/cn/" },
  { name: "策略全景", href: "/cn/framework/" },
  { name: "选股回测", href: "/cn/backtest/" },
  { name: "板块研报", href: "/cn/sectors/" },
];

const navFocus =
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-primary/50";

function Navbar() {
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);
  const [activeId, setActiveId] = useState<string | null>(null);
  const headerRef = useRef<HTMLElement>(null);
  const toggleRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const handleScroll = () => setScrolled(window.scrollY > 10);
    handleScroll();
    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  // 页内锚点高亮（scroll-spy）
  useEffect(() => {
    if (typeof IntersectionObserver === "undefined") return;
    const els = NAV_ANCHORS.map((a) => document.getElementById(a.id)).filter(
      (el): el is HTMLElement => !!el
    );
    if (!els.length) return;
    const io = new IntersectionObserver(
      (entries) => {
        const hit = entries.filter((e) => e.isIntersecting).sort((x, y) => y.intersectionRatio - x.intersectionRatio)[0];
        if (hit) setActiveId(hit.target.id);
      },
      { rootMargin: "-30% 0px -55% 0px", threshold: [0, 0.2, 0.5] }
    );
    els.forEach((el) => io.observe(el));
    return () => io.disconnect();
  }, []);

  // Esc / 点击外部关闭；宽屏时自动收起
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        toggleRef.current?.focus();
      }
    };
    const onDown = (e: MouseEvent) => {
      if (headerRef.current && !headerRef.current.contains(e.target as Node)) setOpen(false);
    };
    const mq = window.matchMedia("(min-width: 1024px)");
    const onMq = () => mq.matches && setOpen(false);
    window.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onDown);
    mq.addEventListener("change", onMq);
    return () => {
      window.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onDown);
      mq.removeEventListener("change", onMq);
    };
  }, [open]);

  const pill = (active: boolean) =>
    `block rounded-full px-3 py-1.5 text-[13px] leading-5 whitespace-nowrap transition-colors ${navFocus} ${
      active
        ? "bg-purple-light text-purple-primary font-semibold"
        : "text-text-secondary hover:text-text-primary hover:bg-black/[0.04]"
    }`;

  return (
    <header
      ref={headerRef}
      className={`fixed top-0 left-0 right-0 z-50 transition-all duration-300 ${
        scrolled || open ? "glass-nav shadow-sm" : "bg-transparent"
      }`}
    >
      <nav aria-label="主导航" className="max-w-[1200px] mx-auto flex items-center justify-between gap-3 px-4 sm:px-6 h-[56px]">
        <Link href="/" aria-label="AlphaPilot 首页" className={`flex shrink-0 items-center rounded-lg ${navFocus}`}>
          <Image src="/logo.png?v=20260719" alt="AlphaPilot" width={180} height={40} className="h-8 w-auto" priority />
        </Link>
        <ul className="hidden lg:flex items-center gap-0.5 rounded-full bg-black/[0.035] p-1">
          {NAV_ANCHORS.map((item) => (
            <li key={item.name}>
              <Link
                href={item.href}
                aria-current={activeId === item.id ? "location" : undefined}
                className={pill(activeId === item.id)}
              >
                {item.name}
              </Link>
            </li>
          ))}
          <li aria-hidden className="mx-1 h-4 w-px bg-black/10" />
          {NAV_PAGES.map((item) => (
            <li key={item.name}>
              <Link href={item.href} className={pill(false)}>
                {item.name}
              </Link>
            </li>
          ))}
        </ul>
        <div className="flex shrink-0 items-center gap-1 sm:gap-2">
          <Link
            href="/cn/"
            className={`bg-text-primary text-white px-4 py-2 rounded-full text-[13px] font-semibold whitespace-nowrap hover:opacity-90 transition-opacity inline-block ${navFocus}`}
          >
            进入工作台
          </Link>
          <button
            ref={toggleRef}
            type="button"
            className={`lg:hidden w-10 h-10 flex items-center justify-center rounded-full text-text-primary hover:bg-black/[0.05] ${navFocus} ${open ? "bg-purple-light text-purple-primary" : ""}`}
            aria-label={open ? "关闭菜单" : "打开菜单"}
            aria-expanded={open}
            aria-controls="mobile-menu"
            onClick={() => setOpen((v) => !v)}
          >
            <svg viewBox="0 0 24 24" className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden>
              {open ? <path d="M6 6l12 12M18 6L6 18" /> : <path d="M4 7h16M4 12h16M4 17h16" />}
            </svg>
          </button>
        </div>
      </nav>
      {open && (
        <div
          id="mobile-menu"
          className="lg:hidden max-h-[calc(100dvh-56px)] overflow-y-auto overscroll-contain px-4 sm:px-6 pb-4 pt-1 border-t border-border-light"
        >
          <div className="max-w-[1200px] mx-auto">
            <p className="px-3 pt-2 pb-1 text-[11px] font-medium tracking-wider text-text-tertiary">了解 AlphaPilot</p>
            <ul className="grid gap-0.5">
              {NAV_ANCHORS.map((item) => (
                <li key={item.name}>
                  <Link
                    href={item.href}
                    onClick={() => setOpen(false)}
                    aria-current={activeId === item.id ? "location" : undefined}
                    className={`block rounded-xl px-3 py-3 text-[15px] ${navFocus} ${
                      activeId === item.id ? "bg-purple-light/70 text-purple-primary font-medium" : "text-text-secondary hover:bg-black/[0.04]"
                    }`}
                  >
                    {item.name}
                  </Link>
                </li>
              ))}
            </ul>
            <p className="px-3 pt-3 pb-1 mt-2 border-t border-border-light text-[11px] font-medium tracking-wider text-text-tertiary">进入使用</p>
            <ul className="grid gap-0.5">
              {NAV_PAGES.map((item) => (
                <li key={item.name}>
                  <Link
                    href={item.href}
                    onClick={() => setOpen(false)}
                    className={`block rounded-xl px-3 py-3 text-[15px] text-text-secondary hover:bg-black/[0.04] ${navFocus}`}
                  >
                    {item.name}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </header>
  );
}

function IconShield() {
  return (
    <svg className="w-5 h-5 text-purple-primary" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
    </svg>
  );
}
function IconGauge() {
  return (
    <svg className="w-5 h-5 text-green-positive" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z" />
      <path d="M19.4 15a8 8 0 1 0-14.8 0" />
      <path d="M12 9V4" />
    </svg>
  );
}
function IconLayers() {
  return (
    <svg className="w-5 h-5 text-status-warning" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M12 2 2 7l10 5 10-5-10-5z" />
      <path d="m2 17 10 5 10-5" />
      <path d="m2 12 10 5 10-5" />
    </svg>
  );
}
function IconSliders() {
  return (
    <svg className="w-5 h-5 text-status-info" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <line x1="4" y1="21" x2="4" y2="14" />
      <line x1="4" y1="10" x2="4" y2="3" />
      <line x1="12" y1="21" x2="12" y2="12" />
      <line x1="12" y1="8" x2="12" y2="3" />
      <line x1="20" y1="21" x2="20" y2="16" />
      <line x1="20" y1="12" x2="20" y2="3" />
      <line x1="1" y1="14" x2="7" y2="14" />
      <line x1="9" y1="8" x2="15" y2="8" />
      <line x1="17" y1="16" x2="23" y2="16" />
    </svg>
  );
}

// Hero 区域：价值主张 + 主/次 CTA + 示例清单卡片
function Hero() {
  return (
    <section className="relative w-full overflow-hidden">
      {/* 纯 CSS 背景光晕（取代原先的第三方背景视频，减少首屏流量与外部依赖） */}
      <div aria-hidden className="absolute inset-0 z-0 pointer-events-none">
        <div className="absolute -top-[180px] left-1/2 -translate-x-1/2 w-[900px] h-[520px] rounded-full bg-purple-glow blur-3xl max-sm:w-[420px]" />
      </div>
      <div className="relative z-10 pt-[120px] pb-14 px-6 max-w-[1200px] mx-auto max-sm:pt-[96px] grid grid-cols-[1.1fr_0.9fr] gap-12 items-center max-lg:grid-cols-1 max-lg:gap-10">
        <div className="max-lg:text-center">
          <div className="badge-purple mb-6">
            <span className="w-1.5 h-1.5 rounded-full bg-purple-primary animate-pulse-dot" />
            A 股 · 每个交易日更新
          </div>
          <h1 className="text-[52px] font-bold tracking-tight leading-[1.15] mb-5 text-gradient max-lg:text-[44px] max-md:text-[36px] max-sm:text-[30px]">
            全 A 股每日扫描，
            <br />
            筛出今天值得关注的几只
          </h1>
          <p className="text-lg text-text-secondary font-normal max-w-[540px] max-lg:mx-auto mb-8 leading-relaxed max-sm:text-base">
            综合成交、资金流向与大盘环境，把几千只股票收窄成一份可读、可比较的观察清单——帮你省下盯盘和选股的时间，而不是替你做决定。
          </p>
          <div className="flex gap-3 max-lg:justify-center flex-wrap max-sm:flex-col">
            <Link
              href="/cn/"
              className="btn-primary hover:btn-primary-hover inline-block text-center"
            >
              免费查看今日清单
            </Link>
            <a
              href="#how"
              className="btn-secondary hover:btn-secondary-hover inline-block text-center"
            >
              了解筛选逻辑
            </a>
          </div>
          <p className="mt-3 text-[13px] text-text-secondary max-lg:text-center">
            注册后可保存收藏、使用模拟盘
          </p>
          <p className="mt-4 text-xs text-text-tertiary">{RISK_SHORT}</p>
        </div>
        <SampleCard />
      </div>
    </section>
  );
}

// 指数卡片（实时拉取）
function TickerSection() {
  const [indices, setIndices] = useState<IndexData[]>(PLACEHOLDER_INDICES);
  const [intraday, setIntraday] = useState<Record<string, number[]>>({});
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/v1/cn/indices")
      .then((r) => r.json())
      .then((d) => {
        if (cancelled) return;
        const list = d?.indices || [];
        const mapped: IndexData[] = list.slice(0, 3).map((it: any) => {
          const pct = Number(it.change_pct) || 0;
          return {
            name: it.name,
            value: Number(it.price).toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
            change: `${pct >= 0 ? "+" : ""}${pct.toFixed(2)}%`,
            isUp: pct >= 0,
          };
        });
        if (mapped.length) setIndices(mapped);
      })
      .catch(() => { if (!cancelled) setFailed(true); });
    return () => { cancelled = true; };
  }, []);

  // 异步拉取日内分时数据用于真实分时线
  useEffect(() => {
    fetch("/api/v1/cn/indices/intraday")
      .then((r) => r.json())
      .then((d) => {
        const parsed: Record<string, number[]> = {};
        for (const [name, data] of Object.entries(d)) {
          const points = (data as any).points || [];
          parsed[name] = points.map((p: any) => p.price);
        }
        setIntraday(parsed);
      })
      .catch(() => {});
  }, []);

  return (
    <section aria-label="大盘指数" className="max-w-[1200px] mx-auto mb-20 max-sm:mb-14 px-6">
      <div className="grid grid-cols-3 gap-4 max-md:grid-cols-1">
        {indices.map((idx) => (
          <div
            key={idx.name}
            className="card p-6 max-sm:p-5 relative overflow-hidden group hover:card-hover"
          >
            <div className="absolute top-0 left-0 right-0 h-[3px] bg-gradient-to-r from-purple-primary to-[#A78BFA] opacity-0 group-hover:opacity-100 transition-opacity" />
            <div className="text-[13px] text-text-tertiary font-medium mb-2 tracking-wide">
              {idx.name}
            </div>
            <div className="text-[32px] max-sm:text-[28px] font-bold tracking-tight mb-2 tabular-nums">
              {idx.value}
            </div>
            {idx.empty ? (
              <span className="text-sm text-text-disabled">{failed ? "暂无行情数据" : "行情加载中…"}</span>
            ) : (
              <span className={idx.isUp ? "ticker-up" : "ticker-down"}>{idx.change}</span>
            )}
            {!idx.empty && <Sparkline isUp={idx.isUp} prices={intraday[idx.name]} />}
          </div>
        ))}
      </div>
      <p className="mt-3 text-center text-xs text-text-tertiary">行情数据可能存在延迟，仅供参考。红涨绿跌。</p>
    </section>
  );
}

/** 功能大卡插图：浅色金融风漏斗，填满空白区域 */
function MoneyGateArt() {
  return (
    <div
      className="relative mt-5 mb-2 flex-1 min-h-[200px] rounded-2xl overflow-hidden border border-border-subtle bg-gradient-to-br from-[#F8F7FF] via-bg-secondary to-[#EEF8F3]"
      aria-hidden
    >
      <svg
        className="absolute inset-0 w-full h-full"
        viewBox="0 0 560 280"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        preserveAspectRatio="xMidYMid slice"
      >
        <defs>
          <linearGradient id="mgBar" x1="0" y1="1" x2="0" y2="0">
            <stop offset="0%" stopColor="#7C5CFC" stopOpacity="0.15" />
            <stop offset="100%" stopColor="#7C5CFC" stopOpacity="0.55" />
          </linearGradient>
          <linearGradient id="mgGate" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="#7C5CFC" />
            <stop offset="100%" stopColor="#34C759" />
          </linearGradient>
          <linearGradient id="mgFunnel" x1="0.5" y1="0" x2="0.5" y2="1">
            <stop offset="0%" stopColor="#7C5CFC" stopOpacity="0.18" />
            <stop offset="100%" stopColor="#7C5CFC" stopOpacity="0.04" />
          </linearGradient>
          <filter id="mgSoft" x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="8" result="b" />
            <feMerge>
              <feMergeNode in="b" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {/* soft orbs */}
        <circle cx="80" cy="60" r="56" fill="#7C5CFC" opacity="0.07" />
        <circle cx="480" cy="200" r="70" fill="#34C759" opacity="0.08" />

        {/* inflow bars (left) */}
        {[
          [48, 150, 72],
          [78, 120, 102],
          [108, 95, 127],
          [138, 135, 87],
          [168, 110, 112],
          [198, 160, 62],
        ].map(([x, y, h], i) => (
          <rect
            key={i}
            x={x}
            y={y}
            width="18"
            height={h}
            rx="6"
            fill="url(#mgBar)"
            className="origin-bottom transition-transform duration-500 group-hover:scale-y-105"
          />
        ))}

        {/* funnel gate */}
        <path
          d="M250 48 H420 L360 210 H310 Z"
          fill="url(#mgFunnel)"
          stroke="#7C5CFC"
          strokeOpacity="0.35"
          strokeWidth="1.5"
        />
        <rect x="288" y="118" width="84" height="28" rx="14" fill="url(#mgGate)" opacity="0.92" filter="url(#mgSoft)" />
        <text x="330" y="137" textAnchor="middle" fill="white" fontSize="12" fontWeight="700" fontFamily="Inter, system-ui, sans-serif">
          PASS
        </text>

        {/* output chips */}
        <rect x="390" y="198" width="120" height="36" rx="12" fill="white" stroke="rgba(124,92,252,0.2)" />
        <circle cx="410" cy="216" r="5" fill="#34C759" />
        <text x="424" y="221" fill="#1D1D1F" fontSize="12" fontWeight="600" fontFamily="Inter, system-ui, sans-serif">
          可执行名单
        </text>

        {/* flow arrows */}
        <path d="M220 170 H242" stroke="#7C5CFC" strokeWidth="2" strokeLinecap="round" opacity="0.45" />
        <path d="M242 170 L250 166 L250 174 Z" fill="#7C5CFC" opacity="0.55" />
        <path d="M360 170 H382" stroke="#34C759" strokeWidth="2" strokeLinecap="round" opacity="0.55" />
        <path d="M382 170 L390 166 L390 174 Z" fill="#34C759" opacity="0.65" />
      </svg>

      <div className="absolute left-4 bottom-3 flex flex-wrap gap-2">
        {["主动买入", "换手过滤", "量比带", "资金流"].map((t) => (
          <span
            key={t}
            className="text-[11px] font-medium px-2.5 py-1 rounded-full bg-white/90 text-text-secondary border border-border-subtle shadow-sm"
          >
            {t}
          </span>
        ))}
      </div>
    </div>
  );
}

// Bento 功能网格
function FeaturesSection() {
  return (
    <section aria-labelledby="features-title" className="max-w-[1200px] mx-auto mb-24 max-sm:mb-16 px-6">
      <SectionHead
        eyebrow="核心能力"
        id="features-title"
        title="先看资金，再看分数"
        desc="综合量化筛选 · 评分排序 · 行情不配合时主动降低曝光"
      />
      <div className="grid grid-cols-4 grid-rows-2 gap-4 max-md:grid-cols-2 max-sm:grid-cols-1 max-md:auto-rows-auto">
        <div className="card p-7 col-span-2 row-span-2 flex flex-col group hover:card-hover relative overflow-hidden max-md:col-span-2 max-sm:col-span-1">
          <div className="w-11 h-11 rounded-xl bg-purple-light flex items-center justify-center mb-4 shrink-0">
            <IconShield />
          </div>
          <div className="text-[17px] font-semibold mb-2 tracking-tight">资金强弱筛选</div>
          <p className="text-sm text-text-secondary leading-relaxed">
            优先关注有资金承接的标的，弱资金票更靠后，让名单先过「钱在不在」这一关。
          </p>
          <p className="text-sm text-text-secondary leading-relaxed mt-2">
            盘中持续跟踪买盘强弱：退潮的往下排，有承接的才更容易留在可执行清单里。
          </p>
          <MoneyGateArt />
          <div className="text-xs font-semibold text-purple-primary pt-1 shrink-0">
            先看资金 <span className="opacity-50">·</span> 再看分数
          </div>
        </div>

        <div className="card p-7 flex flex-col group hover:card-hover">
          <div className="w-11 h-11 rounded-xl bg-status-success/10 flex items-center justify-center mb-4">
            <IconGauge />
          </div>
          <div className="text-[17px] font-semibold mb-2 tracking-tight">综合评分排序</div>
          <div className="text-sm text-text-secondary leading-relaxed flex-1">
            对入选标的给出信心分与排名，方便横向比较。
          </div>
          <div className="text-xs font-semibold text-status-success mt-auto pt-3">信心分可读</div>
        </div>

        <div className="card p-7 flex flex-col group hover:card-hover">
          <div className="w-11 h-11 rounded-xl bg-status-warning/10 flex items-center justify-center mb-4">
            <IconLayers />
          </div>
          <div className="text-[17px] font-semibold mb-2 tracking-tight">资金阶段识别</div>
          <div className="text-sm text-text-secondary leading-relaxed flex-1">
            区分吸筹、拉升等阶段，辅助判断当前更像潜伏阶段还是已经走高。
          </div>
          <div className="text-xs font-semibold text-status-warning mt-auto pt-3">阶段标签</div>
        </div>

        <div className="card p-7 col-span-2 flex flex-col group hover:card-hover max-md:col-span-2 max-sm:col-span-1">
          <div className="w-11 h-11 rounded-xl bg-status-info/10 flex items-center justify-center mb-4">
            <IconSliders />
          </div>
          <div className="text-[17px] font-semibold mb-2 tracking-tight">行情偏弱时少选</div>
          <div className="text-sm text-text-secondary leading-relaxed flex-1">
            行情偏弱时系统会缩短名单甚至留空，而不是为了凑数硬推标的。
          </div>
          <div className="text-xs font-semibold text-status-info mt-auto pt-3">少选，不硬凑</div>
        </div>
      </div>
    </section>
  );
}

// 信号表格
function getPhaseColor(phase: string): string {
  // 接口返回的标签可能带 emoji 前缀（如“🚀 拉升”），因此用 includes 匹配
  if (/拉升|主升/.test(phase)) return "#FF9500";
  if (/吸筹|潜伏/.test(phase)) return "var(--color-purple-primary)";
  if (/出货|派发/.test(phase)) return "#FF3B30";
  return "var(--color-text-tertiary)";
}

/** 展示评分：与原逻辑一致（>1 视为 logit 分，做 sigmoid 映射；否则按 0-1 概率）。仅用于名单内相对排序。 */
function toDisplayScore(sig: any): number {
  const raw = Number(sig.model_proba ?? sig.lgb_score ?? sig.score ?? 0);
  return raw > 1
    ? Math.round((1 / (1 + Math.exp(-raw / 2))) * 100)
    : Math.round(Math.min(1, Math.max(0, raw)) * 100);
}

function SignalShell({ children }: { children: React.ReactNode }) {
  return (
    <section id="today" aria-labelledby="today-title" className="max-w-[1200px] mx-auto mb-24 max-sm:mb-16 px-6 scroll-mt-20">
      <div className="card p-10 relative overflow-hidden max-sm:p-5">
        <div className="absolute -top-[100px] -right-[100px] w-[300px] h-[300px] bg-purple-glow rounded-full pointer-events-none" aria-hidden />
        {children}
      </div>
    </section>
  );
}

function SignalHead({ sub, badge }: { sub: string; badge?: string }) {
  return (
    <div className="relative flex justify-between items-start mb-6 max-sm:flex-col max-sm:gap-3">
      <div>
        <h2 id="today-title" className="text-2xl font-bold tracking-tight max-sm:text-xl">今日名单</h2>
        <div className="text-sm text-text-secondary mt-1">{sub}</div>
      </div>
      <div className="badge-purple">{badge ?? "实时数据"}</div>
    </div>
  );
}

function SignalSection() {
  const [signals, setSignals] = useState<any[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [runAt, setRunAt] = useState("");

  useEffect(() => {
    fetch("/api/v1/cn/recommend")
      .then((r) => {
        if (!r.ok) throw new Error(String(r.status));
        return r.json();
      })
      .then((d) => {
        setSignals(d.recommendations || []);
        setRunAt(d.generated_at || d.run_at || "");
        setLoading(false);
      })
      .catch(() => {
        setFailed(true);
        setLoading(false);
      });
  }, []);

  if (loading) {
    return (
      <SignalShell>
        <SignalHead sub="正在加载今日名单…" />
        <div className="space-y-3 animate-pulse" aria-hidden>
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-10 rounded-xl bg-bg-primary" />
          ))}
        </div>
      </SignalShell>
    );
  }

  if (failed) {
    return (
      <SignalShell>
        <SignalHead sub="暂时无法获取数据" badge="稍后重试" />
        <div className="py-10 text-center text-sm text-text-tertiary">
          名单暂时加载失败，请稍后刷新页面，或直接进入
          <Link href="/cn/" className="text-purple-primary font-medium mx-1">工作台</Link>
          查看。
        </div>
      </SignalShell>
    );
  }

  if (!signals || signals.length === 0) {
    return (
      <SignalShell>
        <SignalHead sub="综合量化筛选 · 当日名单" />
        <div className="py-12 text-center">
          <div className="text-lg font-semibold text-text-secondary mb-2">今日空仓 / 暂无合适标的</div>
          <div className="text-sm text-text-tertiary max-w-sm mx-auto">
            行情偏弱或暂无合适标的时，系统会主动留空，而不是硬凑名单。下一交易日开盘后重新扫描。
          </div>
        </div>
      </SignalShell>
    );
  }

  return (
    <SignalShell>
      <SignalHead sub={runAt ? `更新于 ${runAt}` : "综合量化筛选 · 当日名单"} />
      <div className="relative overflow-x-auto">
        <table className="w-full border-collapse">
          <caption className="sr-only">今日量化筛选名单，按评分排序</caption>
          <thead>
            <tr>
              {["股票", "评分", "资金阶段", "关注等级"].map((h) => (
                <th
                  key={h}
                  scope="col"
                  className="text-left text-xs font-semibold text-text-tertiary tracking-wider py-3 px-4 max-sm:px-2 border-b border-border-light whitespace-nowrap"
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {signals.slice(0, 10).map((sig: any) => {
              const pct = toDisplayScore(sig);
              return (
                <tr key={sig.symbol} className="group hover:bg-[rgba(124,92,252,0.02)] transition-colors">
                  <td className="py-4 px-4 max-sm:px-2 border-b border-border-light">
                    <Link
                      href={`/cn/stock/?symbol=${sig.symbol}`}
                      className="font-semibold text-text-primary hover:text-purple-primary transition-colors whitespace-nowrap"
                    >
                      {sig.name}
                    </Link>
                    <span className="text-xs text-text-tertiary ml-1">{sig.symbol}</span>
                  </td>
                  <td className="py-4 px-4 max-sm:px-2 border-b border-border-light">
                    <div className="flex items-center gap-2.5">
                      <span className="score-pill tabular-nums">{pct}</span>
                      <div className="w-[60px] h-1 rounded bg-border-light overflow-hidden max-sm:hidden" aria-hidden>
                        <div
                          className="h-full rounded bg-gradient-to-r from-purple-primary to-[#A78BFA]"
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                    </div>
                  </td>
                  <td className="py-4 px-4 max-sm:px-2 border-b border-border-light">
                    <span className="font-semibold whitespace-nowrap" style={{ color: getPhaseColor(sig.money_phase_label || sig.money_phase || "") }}>
                      {sig.money_phase_label || sig.money_phase || "—"}
                    </span>
                  </td>
                  <td className="py-4 px-4 max-sm:px-2 border-b border-border-light">
                    <span
                      className="font-semibold"
                      style={{ color: pct >= 80 ? "var(--color-purple-primary)" : "var(--color-text-tertiary)" }}
                    >
                      {pct >= 80 ? "重点关注" : pct >= 65 ? "观察" : "—"}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="relative mt-5 flex flex-wrap items-center justify-between gap-3">
        <p className="text-xs text-text-tertiary leading-relaxed max-w-[640px]">
          评分仅用于名单内相对排序，不代表上涨概率；名单为模型输出，仅供研究参考，不构成投资建议。
        </p>
        <Link href="/cn/" className="text-sm font-semibold text-purple-primary hover:underline">
          在工作台查看完整明细 →
        </Link>
      </div>
    </SignalShell>
  );
}

// 主页面
export default function LandingPage() {
  return (
    <>
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-[60] focus:rounded-full focus:bg-text-primary focus:px-4 focus:py-2 focus:text-sm focus:text-white"
      >
        跳到主要内容
      </a>
      <Navbar />
      <main id="main" className="min-h-screen bg-bg-primary">
        <Hero />
        <TickerSection />
        <HowItWorks />
        <FeaturesSection />
        <SignalSection />
        <PerformanceSection />
        <FaqSection />
        <RiskNotice />
      </main>
      <SiteFooter />
    </>
  );
}

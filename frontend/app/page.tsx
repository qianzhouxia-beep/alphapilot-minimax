"use client";

import { useState, useEffect } from "react";
import Image from "next/image";

// 指数数据类型
interface IndexData {
  name: string;
  value: string;
  change: string;
  isUp: boolean;
}

// 指数默认占位（API 失败时显示）
const PLACEHOLDER_INDICES: IndexData[] = [
  { name: "上证指数", value: "—", change: "—", isUp: true },
  { name: "深证成指", value: "—", change: "—", isUp: true },
  { name: "创业板指", value: "—", change: "—", isUp: true },
];

const stats = [
  { value: "全 A", label: "每日扫描覆盖", highlight: true },
  { value: "多层", label: "综合量化筛选", highlight: false },
  { value: "评分", label: "横向可比排序", highlight: false },
  { value: "Top N", label: "可执行精选", highlight: false },
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

// Sparkline SVG 组件（支持真实分时数据）
function Sparkline({ isUp, prices }: { isUp: boolean; prices?: number[] }) {
  const color = isUp ? "#FF3B30" : "#34C759";
  // 有真实数据则绘制实际路径，否则回退到模拟折线
  const path =
    prices && prices.length >= 2
      ? buildSparklinePath(prices, 80, 40)
      : isUp
        ? "M0 35 L10 32 L20 28 L30 30 L40 25 L50 22 L60 18 L70 15 L80 10"
        : "M0 10 L10 15 L20 12 L30 18 L40 20 L50 22 L60 25 L70 28 L80 30";
  return (
    <svg
      className="absolute right-5 top-1/2 -translate-y-1/2 w-20 h-10 opacity-30"
      viewBox="0 0 80 40"
      fill="none"
      stroke={color}
      strokeWidth="1.5"
    >
      <path d={path} />
    </svg>
  );
}

// 导航栏
function Navbar() {
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const handleScroll = () => setScrolled(window.scrollY > 10);
    window.addEventListener("scroll", handleScroll);
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  return (
    <nav
      className={`fixed top-0 left-0 right-0 z-50 transition-all duration-300 ${
        scrolled ? "glass-nav shadow-sm" : "bg-transparent"
      }`}
    >
      <div className="max-w-[1200px] mx-auto flex items-center justify-between px-6 h-[52px]">
        <a href="/" className="flex items-center gap-2.5 font-bold text-lg tracking-tight text-text-primary">
          <Image src="/logo.png?v=20260719" alt="AlphaPilot" width={180} height={40} className="h-8 w-auto" priority />
        </a>
        <div className="hidden md:flex gap-8">
          {[
            { name: "首页", href: "/" },
            { name: "选股", href: "/cn/screener" },
            { name: "回测", href: "/cn/backtest" },
            { name: "资讯", href: "/cn/news" },
          ].map((item, i) => (
            <a
              key={item.name}
              href={item.href}
              className={`text-[13px] font-medium transition-colors relative ${
                i === 0
                  ? "text-purple-primary"
                  : "text-text-secondary hover:text-text-primary"
              }`}
            >
              {item.name}
              {i === 0 && (
                <span className="absolute -bottom-4 left-1/2 -translate-x-1/2 w-1 h-1 rounded-full bg-purple-primary" />
              )}
            </a>
          ))}
        </div>
        <a
          href="/cn/"
          className="bg-text-primary text-white border-none px-[18px] py-[7px] rounded-full text-[13px] font-semibold hover:scale-[1.03] hover:opacity-90 transition-all cursor-pointer inline-block"
        >
          打开终端
        </a>
      </div>
    </nav>
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

// Hero 区域 — 首屏只保留品牌叙事 + CTA
function Hero() {
  return (
    <section className="pt-[120px] pb-16 px-6 text-center max-w-[1200px] mx-auto">
      <div className="badge-purple mb-6">
        <span className="w-1.5 h-1.5 rounded-full bg-purple-primary animate-pulse-dot" />
        今日精选 · 在线
      </div>
      <h1 className="text-[56px] font-bold tracking-tight leading-[1.1] mb-5 text-gradient max-md:text-[40px] max-sm:text-[32px]">
        把建仓信号
        <br />
        收成可执行清单
      </h1>
      <p className="text-xl text-text-secondary font-normal max-w-[560px] mx-auto mb-10 leading-relaxed max-sm:text-base">
        从全 A 出发，综合量价、资金与行情环境，筛出当日值得关注的标的。
      </p>
      <div className="flex gap-4 justify-center flex-wrap">
        <a href="/cn/" className="btn-primary hover:btn-primary-hover inline-block text-center focus-visible:ring-2 focus-visible:ring-purple-primary/40">
          查看今日信号
        </a>
        <a href="/cn/backtest" className="btn-secondary hover:btn-secondary-hover inline-block text-center focus-visible:ring-2 focus-visible:ring-purple-primary/30">
          查看历史表现
        </a>
      </div>
    </section>
  );
}

// 指数卡片（实时拉取）
function TickerSection() {
  const [indices, setIndices] = useState<IndexData[]>(PLACEHOLDER_INDICES);
  const [intraday, setIntraday] = useState<Record<string, number[]>>({});

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
      .catch(() => { /* keep placeholder */ });
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
    <section className="max-w-[1200px] mx-auto mb-10 mt-4 px-6">
      <div className="grid grid-cols-3 gap-4 max-md:grid-cols-1">
        {indices.map((idx) => (
          <div
            key={idx.name}
            className="card p-6 relative overflow-hidden group hover:card-hover"
          >
            <div className="absolute top-0 left-0 right-0 h-[3px] bg-gradient-to-r from-purple-primary to-[#A78BFA] opacity-0 group-hover:opacity-100 transition-opacity" />
            <div className="text-[13px] text-text-tertiary font-medium mb-2 tracking-wide">
              {idx.name}
            </div>
            <div className="text-[32px] font-bold tracking-tight mb-2">
              {idx.value}
            </div>
            <span className={idx.isUp ? "ticker-up" : "ticker-down"}>
              {idx.change}
            </span>
            <Sparkline isUp={idx.isUp} prices={intraday[idx.name]} />
          </div>
        ))}
      </div>
    </section>
  );
}

// 统计栏
function StatsBar() {
  return (
    <section className="max-w-[1200px] mx-auto mb-16 px-6">
      <div className="card p-8 px-12 flex justify-around items-center max-md:flex-col max-md:gap-6">
        {stats.map((stat, i) => (
          <div key={stat.label} className="text-center">
            <div
              className={`text-4xl font-bold tracking-tight mb-1 ${
                stat.highlight ? "text-purple-primary" : "text-text-primary"
              }`}
            >
              {stat.value}
            </div>
            <div className="text-[13px] text-text-secondary font-medium">
              {stat.label}
            </div>
            {i < stats.length - 1 && (
              <div className="hidden md:block absolute w-px h-10 bg-border-light" />
            )}
          </div>
        ))}
      </div>
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
    <section className="max-w-[1200px] mx-auto mb-20 px-6">
      <div className="text-center mb-12">
        <h2 className="text-4xl font-bold tracking-tight mb-3 max-sm:text-[28px]">
          层层筛选，给出可执行名单
        </h2>
        <p className="text-lg text-text-secondary">
          综合量化筛选 · 评分排序 · 仓位随行情调整
        </p>
      </div>
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
            区分吸筹、拉升等阶段，帮你判断现在更像潜伏还是追高。
          </div>
          <div className="text-xs font-semibold text-status-warning mt-auto pt-3">阶段标签</div>
        </div>

        <div className="card p-7 col-span-2 flex flex-col group hover:card-hover max-md:col-span-2 max-sm:col-span-1">
          <div className="w-11 h-11 rounded-xl bg-status-info/10 flex items-center justify-center mb-4">
            <IconSliders />
          </div>
          <div className="text-[17px] font-semibold mb-2 tracking-tight">仓位随行情调整</div>
          <div className="text-sm text-text-secondary leading-relaxed flex-1">
            弱市自动降仓或空仓，避免行情不配合时硬推满仓名单。
          </div>
          <div className="text-xs font-semibold text-status-info mt-auto pt-3">风险优先</div>
        </div>
      </div>
    </section>
  );
}

// 信号表格
function getPhaseColor(phase: string): string {
  switch (phase) {
    case "拉升": case "主升":   return "#FF9500";
    case "吸筹": case "潜伏":  return "var(--color-purple-primary)";
    case "出货": case "派发":  return "#FF3B30";
    default:                  return "var(--color-text-tertiary)";
  }
}

function SignalSection() {
  const [signals, setSignals] = useState<any[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [runAt, setRunAt] = useState("");

  useEffect(() => {
    fetch("/api/v1/cn/recommend")
      .then((r) => r.json())
      .then((d) => {
        setSignals(d.recommendations || []);
        setRunAt(d.generated_at || d.run_at || "");
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  // 加载中骨架屏
  if (loading) {
    return (
      <section className="max-w-[1200px] mx-auto mb-20 px-6">
        <div className="card p-10">
          <div className="flex justify-between items-start mb-8 max-sm:flex-col max-sm:gap-4">
            <div>
              <div className="text-2xl font-bold tracking-tight">今日精选信号</div>
              <div className="text-sm text-text-secondary mt-1">正在加载今日精选…</div>
            </div>
            <div className="badge-purple">今日精选</div>
          </div>
        </div>
      </section>
    );
  }

  // 无信号
  if (!signals || signals.length === 0) {
    return (
      <section className="max-w-[1200px] mx-auto mb-20 px-6">
        <div className="card p-10 relative overflow-hidden max-sm:p-6 text-center">
          <div className="absolute -top-[100px] -right-[100px] w-[300px] h-[300px] bg-purple-glow rounded-full pointer-events-none" />
          <div className="flex justify-between items-start mb-4 max-sm:flex-col max-sm:gap-4">
            <div>
              <div className="text-2xl font-bold tracking-tight">今日精选信号</div>
              <div className="text-sm text-text-secondary mt-1">综合量化筛选 · 当日名单</div>
            </div>
            <div className="badge-purple">今日精选</div>
          </div>
          <div className="py-16">
            <div className="text-lg font-semibold text-text-secondary mb-2">今日空仓 / 暂无信号</div>
            <div className="text-sm text-text-tertiary max-w-sm mx-auto">
              行情偏弱或暂无合适标的时，系统会主动留空，而不是硬凑名单。下一交易日开盘后重新扫描。
            </div>
          </div>
        </div>
      </section>
    );
  }

  // 有信号 → 显示
  return (
    <section className="max-w-[1200px] mx-auto mb-20 px-6">
      <div className="card p-10 relative overflow-hidden max-sm:p-6">
        <div className="absolute -top-[100px] -right-[100px] w-[300px] h-[300px] bg-purple-glow rounded-full pointer-events-none" />

        <div className="flex justify-between items-start mb-8 max-sm:flex-col max-sm:gap-4">
          <div>
            <div className="text-2xl font-bold tracking-tight">今日精选信号</div>
            <div className="text-sm text-text-secondary mt-1">
              {runAt ? `更新于 ${runAt}` : "综合量化筛选 · 当日名单"}
            </div>
          </div>
          <div className="badge-purple">今日精选</div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full border-collapse">
            <thead>
              <tr>
                {["股票", "信心分", "资金阶段", "建议操作"].map((h) => (
                  <th key={h} className="text-left text-xs font-semibold text-text-tertiary uppercase tracking-wider py-3 px-4 border-b border-border-light">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {signals.slice(0, 10).map((sig: any) => (
                <tr key={sig.symbol} className="group hover:bg-[rgba(124,92,252,0.02)] transition-colors">
                  <td className="py-4 px-4 border-b border-border-light">
                    <a href={`/cn/stock?symbol=${sig.symbol}`} className="font-semibold text-text-primary hover:text-purple-primary transition-colors">
                      {sig.name}
                    </a>
                    <span className="text-xs text-text-tertiary ml-1">{sig.symbol}</span>
                  </td>
                  <td className="py-4 px-4 border-b border-border-light">
                    {(() => {
                      const conf =
                        typeof sig.confidence_score === "number"
                          ? sig.confidence_score
                          : Math.min(99, Math.max(75, Math.round(Number(sig.score || 0) * 45 + 75)));
                      return (
                        <div className="flex items-center gap-2.5">
                          <span className="score-pill">{conf}</span>
                          <div className="w-[60px] h-1 rounded bg-border-light overflow-hidden">
                            <div
                              className="h-full rounded bg-gradient-to-r from-purple-primary to-[#A78BFA]"
                              style={{ width: `${((conf - 75) / 24) * 100}%` }}
                            />
                          </div>
                        </div>
                      );
                    })()}
                  </td>
                  <td className="py-4 px-4 border-b border-border-light">
                    <span className="font-semibold" style={{ color: getPhaseColor(sig.money_phase_label || sig.money_phase || "") }}>
                      {sig.money_phase_label || sig.money_phase || "—"}
                    </span>
                  </td>
                  <td className="py-4 px-4 border-b border-border-light">
                    {(() => {
                      const conf =
                        typeof sig.confidence_score === "number"
                          ? sig.confidence_score
                          : Math.min(99, Math.max(75, Math.round(Number(sig.score || 0) * 45 + 75)));
                      return (
                        <span
                          className="font-semibold"
                          style={{
                            color:
                              conf >= 90
                                ? "var(--color-purple-primary)"
                                : "var(--color-text-tertiary)",
                          }}
                        >
                          {conf >= 90 ? "关注" : conf >= 82 ? "观察" : "—"}
                        </span>
                      );
                    })()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}

// 页脚
function Footer() {
  return (
    <footer className="bg-bg-secondary border-t border-border-light py-12 px-6 mt-[60px]">
      <div className="max-w-[1200px] mx-auto flex justify-between items-center max-sm:flex-col max-sm:gap-4">
        <a href="/" className="flex items-center gap-2.5 font-bold text-base text-text-primary">
          <Image src="/logo.png?v=20260719" alt="AlphaPilot" width={180} height={40} className="h-7 w-auto" />
        </a>
        <div className="text-[13px] text-text-tertiary">
          AlphaPilot · A 股智能决策 · 非投资建议
        </div>
      </div>
    </footer>
  );
}

// 主页面
export default function Home() {
  return (
    <main className="min-h-screen bg-bg-primary">
      <Navbar />
      <Hero />
      <TickerSection />
      <StatsBar />
      <FeaturesSection />
      <SignalSection />
      <Footer />
    </main>
  );
}

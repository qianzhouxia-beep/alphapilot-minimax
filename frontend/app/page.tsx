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
  { value: "84%", label: "波段胜率", highlight: true },
  { value: "3.2:1", label: "平均盈亏比", highlight: false },
  { value: "500+", label: "每日信号", highlight: false },
  { value: "5ms", label: "行情延迟", highlight: false },
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
          <Image src="/logo.png" alt="AlphaPilot" width={321} height={264} className="h-8 w-auto" priority />
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
          进入终端
        </a>
      </div>
    </nav>
  );
}

// Hero 区域
function Hero() {
  return (
    <section className="pt-[140px] pb-20 px-6 text-center max-w-[1200px] mx-auto">
      <div className="badge-purple mb-6">
        <span className="w-1.5 h-1.5 rounded-full bg-purple-primary animate-pulse-dot" />
        V2.2 评分引擎在线
      </div>
      <h1 className="text-[56px] font-bold tracking-tight leading-[1.1] mb-5 text-gradient max-md:text-[40px] max-sm:text-[32px]">
        用 AI 穿透
        <br />
        市场迷雾
      </h1>
      <p className="text-xl text-text-secondary font-normal max-w-[560px] mx-auto mb-10 leading-relaxed max-sm:text-base">
        AlphaPilot V2.2 融合 43 维特征，从量价行为到资金流向，
        用机构级视角锁定每一个建仓信号。
      </p>
      <div className="flex gap-4 justify-center">
        <a href="/cn/screener" className="btn-primary hover:btn-primary-hover inline-block text-center">查看今日信号</a>
        <a href="/cn/backtest" className="btn-secondary hover:btn-secondary-hover inline-block text-center">了解策略原理</a>
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
    <section className="max-w-[1200px] mx-auto mb-[60px] px-6">
      <div className="grid grid-cols-3 gap-4 max-md:grid-cols-1">
        {indices.map((idx) => (
          <div
            key={idx.name}
            className="card-glass p-6 relative overflow-hidden group hover:card-hover"
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
    <section className="max-w-[1200px] mx-auto mb-[60px] px-6">
      <div className="card-glass p-8 px-12 flex justify-around items-center max-md:flex-col max-md:gap-6">
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

// Bento 功能网格
function FeaturesSection() {
  return (
    <section className="max-w-[1200px] mx-auto mb-20 px-6">
      <div className="text-center mb-12">
        <h2 className="text-4xl font-bold tracking-tight mb-3 max-sm:text-[28px]">
          全维度决策分析
        </h2>
        <p className="text-lg text-text-secondary">
          V2.2 · 43 维特征 · XGBoost 集成 · 动态风控
        </p>
      </div>
      <div className="grid grid-cols-4 grid-rows-2 gap-4 max-md:grid-cols-2 max-sm:grid-cols-1 max-md:auto-rows-auto">
        {/* 大卡片 - 主力行为雷达 */}
        <div className="card-glass p-7 col-span-2 row-span-2 flex flex-col group hover:card-hover relative overflow-hidden max-md:col-span-2 max-sm:col-span-1">
          <div className="w-11 h-11 rounded-xl bg-purple-light text-purple-primary flex items-center justify-center text-xl mb-4">
            &#9679;
          </div>
          <div className="text-[17px] font-semibold mb-2 tracking-tight">
            主力行为雷达
          </div>
          <div className="text-sm text-text-secondary leading-relaxed flex-1">
            实时追踪 61 维融合特征穿透式监控主力资金动向，结合多模型集成数据验证持仓分布。识别机构持续流入、短期过热等关键信号。
          </div>
          <div className="text-xs font-semibold text-purple-primary mt-auto pt-3">
            机构持续流入 <span className="opacity-50">·</span> 极高
          </div>
          <svg
            className="absolute bottom-0 right-0 w-[180px] h-[100px] opacity-[0.06] pointer-events-none"
            viewBox="0 0 180 100"
            fill="none"
            stroke="#7C5CFC"
            strokeWidth="2"
          >
            <path d="M0 80 Q30 60 60 70 T120 40 T180 20" />
          </svg>
        </div>

        {/* 量化信号 */}
        <div className="card-glass p-7 flex flex-col group hover:card-hover">
          <div className="w-11 h-11 rounded-xl bg-[rgba(52,199,89,0.1)] text-green-positive flex items-center justify-center text-xl mb-4">
            &#9670;
          </div>
          <div className="text-[17px] font-semibold mb-2 tracking-tight">
            量化信号筛选
          </div>
          <div className="text-sm text-text-secondary leading-relaxed flex-1">
            基于 XGBoost 集成模型，对全市场 5000+ 标的进行多维度穿透评分。
          </div>
          <div className="text-xs font-semibold text-green-positive mt-auto pt-3">
            Top 1%
          </div>
        </div>

        {/* 资金阶段 */}
        <div className="card-glass p-7 flex flex-col group hover:card-hover">
          <div className="w-11 h-11 rounded-xl bg-[rgba(255,149,0,0.1)] text-[#FF9500] flex items-center justify-center text-xl mb-4">
            &#9671;
          </div>
          <div className="text-[17px] font-semibold mb-2 tracking-tight">
            资金阶段识别
          </div>
          <div className="text-sm text-text-secondary leading-relaxed flex-1">
            智能识别吸筹、拉升、出货等 9 种资金运作阶段。
          </div>
          <div className="text-xs font-semibold text-[#FF9500] mt-auto pt-3">
            拉升期
          </div>
        </div>

        {/* 风控引擎 - 宽卡片 */}
        <div className="card-glass p-7 col-span-2 flex flex-col group hover:card-hover max-md:col-span-2 max-sm:col-span-1">
          <div className="w-11 h-11 rounded-xl bg-[rgba(0,122,255,0.1)] text-[#007AFF] flex items-center justify-center text-xl mb-4">
            &#9632;
          </div>
          <div className="text-[17px] font-semibold mb-2 tracking-tight">
            动态风控引擎
          </div>
          <div className="text-sm text-text-secondary leading-relaxed flex-1">
            动态追踪止盈 · 自动硬止损 · 单票仓位上限 30% · 最大回撤 -8% 暂停交易。
          </div>
          <div className="text-xs font-semibold text-[#007AFF] mt-auto pt-3">
            硬止损 -3% / -5%
          </div>
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
        <div className="card-glass p-10">
          <div className="flex justify-between items-start mb-8 max-sm:flex-col max-sm:gap-4">
            <div>
              <div className="text-2xl font-bold tracking-tight">今日精选信号</div>
              <div className="text-sm text-text-secondary mt-1">正在加载信号数据…</div>
            </div>
            <div className="badge-purple">V2.2 评分引擎</div>
          </div>
        </div>
      </section>
    );
  }

  // 无信号
  if (!signals || signals.length === 0) {
    return (
      <section className="max-w-[1200px] mx-auto mb-20 px-6">
        <div className="card-glass p-10 relative overflow-hidden max-sm:p-6 text-center">
          <div className="absolute -top-[100px] -right-[100px] w-[300px] h-[300px] bg-purple-glow rounded-full pointer-events-none" />
          <div className="flex justify-between items-start mb-4 max-sm:flex-col max-sm:gap-4">
            <div>
              <div className="text-2xl font-bold tracking-tight">今日精选信号</div>
              <div className="text-sm text-text-secondary mt-1">基于 V2.2 全量扫描</div>
            </div>
            <div className="badge-purple">V2.2 评分引擎</div>
          </div>
          <div className="py-16">
            <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-[rgba(124,92,252,0.08)] flex items-center justify-center text-2xl text-purple-primary">◇</div>
            <div className="text-lg font-semibold text-text-secondary mb-2">暂无信号</div>
            <div className="text-sm text-text-tertiary max-w-sm mx-auto">
              上一个交易日未生成符合条件的信号，下一个交易日凌晨 5:00 重新扫描
            </div>
          </div>
        </div>
      </section>
    );
  }

  // 有信号 → 显示
  return (
    <section className="max-w-[1200px] mx-auto mb-20 px-6">
      <div className="card-glass p-10 relative overflow-hidden max-sm:p-6">
        <div className="absolute -top-[100px] -right-[100px] w-[300px] h-[300px] bg-purple-glow rounded-full pointer-events-none" />

        <div className="flex justify-between items-start mb-8 max-sm:flex-col max-sm:gap-4">
          <div>
            <div className="text-2xl font-bold tracking-tight">今日精选信号</div>
            <div className="text-sm text-text-secondary mt-1">
              {runAt ? `更新于 ${runAt}` : '基于 V2.2 全量扫描'}
            </div>
          </div>
          <div className="badge-purple">V2.2 评分引擎</div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full border-collapse">
            <thead>
              <tr>
                {["股票", "评分", "资金阶段", "建议操作"].map((h) => (
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
                    <div className="flex items-center gap-2.5">
                      <span className="score-pill">{sig.score?.toFixed(1)}</span>
                      <div className="w-[60px] h-1 rounded bg-border-light overflow-hidden">
                        <div className="h-full rounded bg-gradient-to-r from-purple-primary to-[#A78BFA]" style={{ width: `${sig.score || 0}%` }} />
                      </div>
                    </div>
                  </td>
                  <td className="py-4 px-4 border-b border-border-light">
                    <span className="font-semibold" style={{ color: getPhaseColor(sig.money_phase_label || sig.money_phase || "") }}>
                      {sig.money_phase_label || sig.money_phase || "—"}
                    </span>
                  </td>
                  <td className="py-4 px-4 border-b border-border-light">
                    <span className="font-semibold" style={{ color: sig.score && sig.score >= 85 ? "var(--color-purple-primary)" : "var(--color-text-tertiary)" }}>
                      {sig.score && sig.score >= 85 ? "关注" : sig.score && sig.score >= 75 ? "观察" : "—"}
                    </span>
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
          <Image src="/logo.png" alt="AlphaPilot" width={321} height={264} className="h-7 w-auto" />
        </a>
        <div className="text-[13px] text-text-tertiary">
          AlphaPilot V2.2 · AI 股票智能评分
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

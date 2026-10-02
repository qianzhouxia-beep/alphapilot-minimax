// 首页静态分区：工作原理 / 示例清单 / 模型指标 / FAQ / 风险提示 / 页脚
// 不含 hooks，可在服务端渲染（静态导出）。
import Image from "next/image";
import Link from "next/link";
import {
  FAQS,
  MODEL_METRICS,
  MODEL_METRICS_NOTE,
  RISK_FULL,
  RISK_FOOTER,
  SAMPLE_LIST,
  SITE_URL,
  STEPS,
} from "@/lib/landing-content";

/** 统一的分区标题 */
export function SectionHead({
  eyebrow,
  title,
  desc,
  id,
}: {
  eyebrow?: string;
  title: string;
  desc?: string;
  id?: string;
}) {
  return (
    <div className="text-center mb-10 max-sm:mb-8">
      {eyebrow && (
        <div className="text-[13px] font-semibold text-purple-primary tracking-wide mb-2">{eyebrow}</div>
      )}
      <h2 id={id} className="text-[36px] font-bold tracking-tight leading-tight max-sm:text-[26px]">
        {title}
      </h2>
      {desc && (
        <p className="text-base text-text-secondary mt-3 max-w-[620px] mx-auto leading-relaxed">{desc}</p>
      )}
    </div>
  );
}

/** 红涨绿跌（A 股惯例，勿对调） */
function Chg({ v }: { v: number }) {
  const up = v >= 0;
  return (
    <span className={up ? "ticker-up" : "ticker-down"}>
      {up ? "+" : ""}
      {v.toFixed(2)}%
    </span>
  );
}

/** Hero 右侧：示例清单卡片（假数据，醒目标注） */
export function SampleCard() {
  return (
    <div className="card relative p-6 max-sm:p-5 text-left" role="group" aria-label="今日清单界面示例（演示数据）">
      <div className="flex items-start justify-between gap-3 mb-4">
        <div>
          <div className="text-[17px] font-bold tracking-tight">今日清单 · 界面示例</div>
          <div className="text-xs text-text-tertiary mt-1">按评分排序 · 附资金阶段标签</div>
        </div>
        <span className="shrink-0 rounded-full border border-status-warning/40 bg-status-warning/10 px-2.5 py-1 text-[11px] font-semibold text-status-warning">
          示例数据
        </span>
      </div>
      <ul className="divide-y divide-border-light">
        {SAMPLE_LIST.map((s) => (
          <li key={s.rank} className="flex items-center gap-3 py-3">
            <span className="w-5 text-sm font-semibold text-text-tertiary tabular-nums">{s.rank}</span>
            <div className="min-w-0 flex-1">
              <div className="text-[15px] font-semibold truncate">{s.name}</div>
              <div className="text-xs text-text-tertiary mt-0.5">资金阶段：{s.phase}</div>
            </div>
            <div className="flex items-center gap-2 max-[380px]:hidden">
              <div className="w-14 h-1 rounded bg-border-light overflow-hidden" aria-hidden>
                <div className="h-full rounded bg-gradient-to-r from-purple-primary to-[#A78BFA]" style={{ width: `${s.score}%` }} />
              </div>
            </div>
            <span className="score-pill tabular-nums" aria-label={`评分 ${s.score}`}>{s.score}</span>
            <Chg v={s.chg} />
          </li>
        ))}
      </ul>
      <p className="mt-4 text-[11px] leading-relaxed text-text-tertiary">
        以上为演示用的虚构数据，不对应任何真实证券，不构成投资建议。
      </p>
    </div>
  );
}

/** 3 步工作原理 */
export function HowItWorks() {
  return (
    <section id="how" aria-labelledby="how-title" className="max-w-[1200px] mx-auto mb-24 max-sm:mb-16 px-6 scroll-mt-20">
      <SectionHead
        eyebrow="工作原理"
        id="how-title"
        title="三步，把几千只股票收成一份短名单"
        desc="省下盯盘和翻股票的时间；最终是否参与，由你自己决定。"
      />
      <ol className="grid grid-cols-3 gap-4 max-md:grid-cols-1">
        {STEPS.map((s, i) => (
          <li key={s.n} className="card p-7 relative">
            <div className="flex items-center gap-3 mb-4">
              <span className="w-9 h-9 rounded-full bg-purple-light text-purple-primary text-sm font-bold flex items-center justify-center tabular-nums">
                {s.n}
              </span>
              {i < STEPS.length - 1 && (
                <span aria-hidden className="hidden md:block flex-1 h-px bg-gradient-to-r from-purple-primary/30 to-transparent" />
              )}
            </div>
            <h3 className="text-[19px] font-semibold tracking-tight mb-2">{s.title}</h3>
            <p className="text-sm text-text-secondary leading-relaxed">{s.body}</p>
          </li>
        ))}
      </ol>
    </section>
  );
}

/** 模型质量指标（客观指标，不含收益/胜率） */
export function PerformanceSection() {
  return (
    <section id="performance" aria-labelledby="perf-title" className="max-w-[1200px] mx-auto mb-24 max-sm:mb-16 px-6 scroll-mt-20">
      <SectionHead
        eyebrow="模型指标"
        id="perf-title"
        title="先看模型本身的质量"
        desc="这里只披露模型层面的客观指标及其口径，不展示收益数字。"
      />
      <div className="card p-8 max-sm:p-5 relative overflow-hidden">
        <dl className="grid grid-cols-4 gap-4 max-md:grid-cols-2">
          {MODEL_METRICS.map((m) => (
            <div key={m.label} className="rounded-2xl bg-bg-primary p-5 max-sm:p-4">
              <dt className="text-[13px] text-text-secondary font-medium">{m.label}</dt>
              <dd className="mt-2 text-[32px] max-sm:text-[26px] font-bold tracking-tight tabular-nums text-text-primary">
                {m.value}
                {m.unit && <span className="ml-1 text-[15px] font-semibold text-text-secondary">{m.unit}</span>}
              </dd>
              <div className="text-xs text-text-tertiary mt-1.5 leading-relaxed">{m.hint}</div>
            </div>
          ))}
        </dl>

        <div className="mt-6 flex flex-wrap items-center justify-between gap-3">
          <p className="text-xs text-text-tertiary leading-relaxed max-w-[640px]">
            {MODEL_METRICS_NOTE}。评分不代表上涨概率，历史表现不代表未来收益。
          </p>
          <Link href="/cn/backtest/" className="btn-secondary hover:btn-secondary-hover inline-block text-center !py-2.5 !px-5 !text-sm">
            打开回测工具
          </Link>
        </div>
      </div>
    </section>
  );
}

/** FAQ —— 原生 details，无需 JS，键盘可达；同时输出 FAQPage JSON-LD */
export function FaqSection() {
  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: FAQS.map((f) => ({
      "@type": "Question",
      name: f.q,
      acceptedAnswer: { "@type": "Answer", text: f.a },
    })),
  };
  return (
    <section id="faq" aria-labelledby="faq-title" className="max-w-[820px] mx-auto mb-24 max-sm:mb-16 px-6 scroll-mt-20">
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }} />
      <SectionHead eyebrow="常见问题" id="faq-title" title="开始之前，你可能想知道" />
      <div className="card divide-y divide-border-light overflow-hidden">
        {FAQS.map((f) => (
          <details key={f.q} className="group px-6 max-sm:px-4">
            <summary className="flex cursor-pointer list-none items-center justify-between gap-4 py-5 text-[16px] font-semibold [&::-webkit-details-marker]:hidden">
              {f.q}
              <svg aria-hidden viewBox="0 0 12 12" className="h-3 w-3 shrink-0 text-text-tertiary transition-transform group-open:rotate-180">
                <path d="M2.5 4.5 L6 8 L9.5 4.5" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </summary>
            <p className="pb-5 text-sm text-text-secondary leading-relaxed">{f.a}</p>
          </details>
        ))}
      </div>
    </section>
  );
}

/** 醒目的风险提示 */
export function RiskNotice() {
  return (
    <section id="risk" aria-labelledby="risk-title" className="max-w-[1200px] mx-auto mb-16 px-6 scroll-mt-20">
      <div className="rounded-[20px] border border-status-warning/30 bg-[#FFF8EC] p-7 max-sm:p-5">
        <div className="flex items-center gap-2.5 mb-3">
          <svg aria-hidden viewBox="0 0 24 24" className="w-5 h-5 text-status-warning" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 3 2 21h20L12 3z" />
            <path d="M12 10v5M12 18.5v.01" />
          </svg>
          <h2 id="risk-title" className="text-[17px] font-bold tracking-tight">风险提示与免责声明</h2>
        </div>
        <div className="space-y-2 text-[13px] leading-relaxed text-text-secondary">
          {RISK_FULL.map((t) => (
            <p key={t}>{t}</p>
          ))}
        </div>
      </div>
    </section>
  );
}

const FOOTER_COLS = [
  {
    title: "产品",
    links: [
      { name: "工作台", href: "/cn/" },
      { name: "选股回测", href: "/cn/backtest/" },
      { name: "资金流向", href: "/cn/funds/" },
      { name: "板块研报", href: "/cn/sectors/" },
      { name: "策略全景", href: "/cn/framework/" },
    ],
  },
  {
    title: "了解更多",
    links: [
      { name: "工作原理", href: "/#how" },
      { name: "模型指标", href: "/#performance" },
      { name: "常见问题", href: "/#faq" },
      { name: "风险提示", href: "/#risk" },
    ],
  },
] as const;

export function SiteFooter() {
  return (
    <footer className="bg-bg-secondary border-t border-border-light pt-12 pb-8 px-6">
      <div className="max-w-[1200px] mx-auto">
        <div className="grid grid-cols-[1.6fr_1fr_1fr] gap-10 max-md:grid-cols-2 max-sm:grid-cols-1">
          <div className="max-md:col-span-2 max-sm:col-span-1">
            <Link href="/" aria-label="AlphaPilot 首页" className="inline-block">
              <Image src="/logo.png?v=20260719" alt="AlphaPilot" width={180} height={40} className="h-7 w-auto" />
            </Link>
            <p className="mt-3 text-[13px] text-text-secondary leading-relaxed max-w-[360px]">
              面向 A 股投资者的量化筛选与研究辅助工具：全 A 扫描、资金流与评分排序，把候选池收窄成一份可读的观察清单。
            </p>
          </div>
          {FOOTER_COLS.map((col) => (
            <nav key={col.title} aria-label={col.title}>
              <div className="text-[13px] font-semibold mb-3">{col.title}</div>
              <ul className="space-y-2">
                {col.links.map((l) => (
                  <li key={l.name}>
                    <Link href={l.href} className="text-[13px] text-text-secondary hover:text-purple-primary transition-colors">{l.name}</Link>
                  </li>
                ))}
              </ul>
            </nav>
          ))}
        </div>
        <div className="mt-10 pt-6 border-t border-border-light flex flex-col gap-2 text-xs text-text-tertiary leading-relaxed">
          <p className="font-medium text-text-secondary">{RISK_FOOTER}</p>
          <p>
            © {new Date().getFullYear()} AlphaPilot · {SITE_URL.replace("https://", "")}
          </p>
          {/* TODO: 如已完成 ICP 备案，请在此处补充备案号 */}
        </div>
      </div>
    </footer>
  );
}

// 策略全景：站内原生页面（取代原先指向后端 /api/v1/cn/framework 的外链）。
// 内容基于原“策略全景”页面精简改写：只讲筛选逻辑，不透露具体权重/阈值，也不做收益承诺。
"use client";

import Link from "next/link";
import { HeaderBar } from "@/components/HeaderBar";

const FUNNEL = [
  { t: "全市场", d: "沪深全部 A 股" },
  { t: "因子评分", d: "多维因子 + 模型打分" },
  { t: "多层门控", d: "7 道风控过滤" },
  { t: "融合排序", d: "模型 · 资金流 · 板块热度" },
  { t: "短名单", d: "Top 10 候选" },
];

const DATA_DOMAINS = [
  {
    t: "基本面与因子",
    d: "技术、基本面、事件、资金流、集合竞价量价等多类因子，由收盘数据、季度财报与业绩预告计算；因子权重会根据历史有效性定期校准。",
  },
  {
    t: "实时资金流",
    d: "约 60 秒刷新的全市场资金流向，关注机构净流入、主动买入占比、换手率与量比等信号。",
  },
  {
    t: "板块资金流",
    d: "全天跟踪行业级资金动向，把板块划分为“偏好 / 观察 / 回避”，避开资金持续流出的方向。",
  },
];

const GATES = [
  { n: 1, t: "标的池门", d: "剔除 ST、流动性不足和有退市风险的股票" },
  { n: 2, t: "业绩门", d: "排除净利润大幅下滑的股票" },
  { n: 3, t: "资金门", d: "资金流明显偏弱的标的被剔除或降权" },
  { n: 4, t: "板块偏好门", d: "资金偏好的板块加权，机构流出的板块回避" },
  { n: 5, t: "环境门", d: "按大盘状态调节名单规模与整体风险暴露" },
  { n: 6, t: "板块轮动门", d: "连续数日资金流出的板块直接剔除" },
  { n: 7, t: "盘中巡检", d: "盘中持续监测板块资金反转并给出预警" },
];

const TIMELINE = [
  { time: "05:00", t: "隔夜先验", d: "全市场因子计算与模型评分，形成隔夜候选池（不作为最终名单）" },
  { time: "09:25", t: "集合竞价门控", d: "竞价结束后读取开盘价量，剔除接近涨停与明显低开的标的" },
  { time: "09:35", t: "生成当日名单", d: "结合实时资金流与板块热度重新排序，得到当日 Top 10 候选" },
  { time: "盘中", t: "持续巡检", d: "10:00 / 11:00 / 13:30 等时点复核板块资金变化" },
  { time: "收盘前", t: "收盘复核", d: "14:30 前后进行当日收盘前的风险复核" },
];

function SectionTitle({ n, children }: { n: number; children: React.ReactNode }) {
  return (
    <div className="mb-4 flex items-center gap-3">
      <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-purple-primary text-[13px] font-bold text-white">{n}</span>
      <h2 className="text-[20px] font-bold tracking-tight text-text-primary max-sm:text-[18px]">{children}</h2>
    </div>
  );
}

export default function FrameworkPage() {
  return (
    <main className="mx-auto max-w-[1100px] px-4 sm:px-6 lg:px-8 py-4 sm:py-6 lg:py-8 min-h-screen">
      <HeaderBar market="cn" />

      <header className="mt-6 mb-10 text-center max-sm:mt-2 max-sm:mb-8">
        <div className="badge-purple mb-4">策略全景</div>
        <h1 className="text-[40px] font-bold tracking-tight leading-tight max-sm:text-[28px]">
          名单是怎么<span className="text-purple-primary">筛</span>出来的
        </h1>
        <p className="mx-auto mt-3 max-w-[640px] text-[15px] leading-relaxed text-text-secondary max-sm:text-[14px]">
          多维因子评分、实时资金流、板块热度和多层风控门，逐层把全市场收窄成一份可读的观察清单。
          这里只介绍筛选逻辑，不涉及具体参数。
        </p>
        <dl className="mx-auto mt-8 grid max-w-[760px] grid-cols-3 gap-3 max-sm:grid-cols-1">
          {[
            ["5,000+", "每日扫描的 A 股数量"],
            ["7 层", "风控门过滤"],
            ["60 秒", "全市场资金流刷新"],
          ].map(([v, l]) => (
            <div key={l} className="card p-5">
              <dd className="text-[28px] font-bold tracking-tight text-purple-primary">{v}</dd>
              <dt className="mt-1 text-[12px] text-text-secondary">{l}</dt>
            </div>
          ))}
        </dl>
      </header>

      <div className="space-y-12 max-sm:space-y-10">
        <section aria-labelledby="fw-1">
          <SectionTitle n={1}><span id="fw-1">架构总览：分层漏斗</span></SectionTitle>
          <p className="mb-5 text-[14px] leading-relaxed text-text-secondary">
            每个阶段都是一层质量控制：先做因子评分，再经过多层门控，最后融合排序。某一数据源或某一层暂时失效时，其余层仍可独立运作；盘中则用实时资金流和板块资金数据刷新判断。
          </p>
          <ol className="grid grid-cols-5 gap-2 max-md:grid-cols-1">
            {FUNNEL.map((f, i) => (
              <li key={f.t} className="card relative p-4 text-center max-md:flex max-md:items-center max-md:gap-3 max-md:text-left">
                <span className="mx-auto mb-2 flex h-7 w-7 items-center justify-center rounded-full bg-purple-light text-[12px] font-bold text-purple-primary max-md:mx-0 max-md:mb-0 max-md:shrink-0">{i + 1}</span>
                <div>
                  <div className="text-[14px] font-semibold text-text-primary">{f.t}</div>
                  <div className="mt-0.5 text-[12px] text-text-secondary">{f.d}</div>
                </div>
              </li>
            ))}
          </ol>
        </section>

        <section aria-labelledby="fw-2">
          <SectionTitle n={2}><span id="fw-2">三类数据来源</span></SectionTitle>
          <div className="grid grid-cols-3 gap-4 max-md:grid-cols-1">
            {DATA_DOMAINS.map((d) => (
              <div key={d.t} className="card p-5">
                <h3 className="text-[15px] font-semibold text-text-primary">{d.t}</h3>
                <p className="mt-2 text-[13px] leading-relaxed text-text-secondary">{d.d}</p>
              </div>
            ))}
          </div>
        </section>

        <section aria-labelledby="fw-3">
          <SectionTitle n={3}><span id="fw-3">评分与融合排序</span></SectionTitle>
          <div className="card p-5 sm:p-6">
            <p className="text-[14px] leading-relaxed text-text-secondary">
              最终排序综合三类信息：<strong className="text-text-primary">模型评分</strong>（全市场横向比较）、
              <strong className="text-text-primary">实时资金流</strong>（是否有真实承接）和
              <strong className="text-text-primary">板块热度</strong>（所在方向是否被资金认可）。
              一只股票需要同时在这三个维度上表现不差，才更容易排在前面。
            </p>
            <p className="mt-3 rounded-xl bg-bg-primary px-4 py-3 text-[13px] leading-relaxed text-text-secondary">
              <strong className="text-text-primary">关于“评分”：</strong>
              评分只用于同一份名单内的相对排序，方便横向比较；它不是上涨概率，也不是收益预测。
            </p>
          </div>
        </section>

        <section aria-labelledby="fw-4">
          <SectionTitle n={4}><span id="fw-4">七道风控门</span></SectionTitle>
          <ol className="grid grid-cols-2 gap-3 max-sm:grid-cols-1">
            {GATES.map((g) => (
              <li key={g.n} className="card flex gap-3 p-4">
                <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-purple-light text-[12px] font-bold text-purple-primary">{g.n}</span>
                <div>
                  <div className="text-[14px] font-semibold text-text-primary">{g.t}</div>
                  <div className="mt-0.5 text-[12px] leading-relaxed text-text-secondary">{g.d}</div>
                </div>
              </li>
            ))}
          </ol>
        </section>

        <section aria-labelledby="fw-5">
          <SectionTitle n={5}><span id="fw-5">一个交易日的节奏</span></SectionTitle>
          <ol className="card divide-y divide-border-light">
            {TIMELINE.map((t) => (
              <li key={t.time} className="flex gap-4 p-4 max-sm:flex-col max-sm:gap-1">
                <span className="w-16 shrink-0 text-[14px] font-bold tabular-nums text-purple-primary">{t.time}</span>
                <div>
                  <div className="text-[14px] font-semibold text-text-primary">{t.t}</div>
                  <div className="mt-0.5 text-[12px] leading-relaxed text-text-secondary">{t.d}</div>
                </div>
              </li>
            ))}
          </ol>
        </section>

        <section aria-labelledby="fw-6">
          <SectionTitle n={6}><span id="fw-6">风险控制的三个层面</span></SectionTitle>
          <div className="grid grid-cols-3 gap-4 max-md:grid-cols-1">
            {[
              ["组合层", "根据大盘状态调整名单规模与整体风险暴露；行情偏弱时宁可少选或留空。"],
              ["个股层", "设有止盈、止损与时间维度的复核规则，用于控制单一标的的不利波动。"],
              ["板块层", "限制对单一行业的过度集中，并监测板块资金反转。"],
            ].map(([t, d]) => (
              <div key={t} className="card p-5">
                <h3 className="text-[15px] font-semibold text-text-primary">{t}</h3>
                <p className="mt-2 text-[13px] leading-relaxed text-text-secondary">{d}</p>
              </div>
            ))}
          </div>
        </section>

        <section aria-labelledby="fw-risk" className="rounded-[20px] border border-status-warning/30 bg-[#FFF8EC] p-6 max-sm:p-5">
          <h2 id="fw-risk" className="text-[16px] font-bold text-text-primary">局限与风险提示</h2>
          <ul className="mt-3 list-disc space-y-1.5 pl-5 text-[13px] leading-relaxed text-text-secondary">
            <li>任何模型都有局限：市场风格切换、突发事件、数据延迟或缺失都可能让筛选结果失效。</li>
            <li>名单、评分与阶段标签均为模型输出，仅供研究参考，不构成投资建议或收益承诺。</li>
            <li>历史表现不代表未来；回测存在样本局限，部分模式还可能存在前视偏差。</li>
            <li>投资有风险，入市需谨慎，请结合自身风险承受能力独立决策。</li>
          </ul>
        </section>

        <div className="flex flex-wrap items-center justify-center gap-3 pb-6">
          <Link href="/cn/" className="btn-primary hover:btn-primary-hover inline-block text-center">查看今日名单</Link>
          <Link href="/cn/backtest/" className="btn-secondary hover:btn-secondary-hover inline-block text-center">试试选股回测</Link>
        </div>
      </div>
    </main>
  );
}

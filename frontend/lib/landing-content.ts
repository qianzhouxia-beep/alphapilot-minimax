// 首页文案 / 配置集中管理。
// 「模型质量指标」（MODEL_METRICS）为站长提供并确认的客观指标，不含胜率/收益/回撤；
// 如需修改数字或口径，只改这里，且不得加入未经站长确认的内容。
import { DISCLAIMER_FULL, DISCLAIMER_SHORT } from "@/lib/disclaimer";

export const SITE_URL = "https://alphapilot.api-tokenmaster.com";

export const STEPS = [
  {
    n: "01",
    title: "全 A 每日扫描",
    body: "每个交易日扫描沪深全部 A 股，先剔除不满足基础条件的标的，把几千只缩小到一个候选池。",
  },
  {
    n: "02",
    title: "多维度逐层筛选",
    body: "结合成交活跃度、资金流向、量价形态与大盘环境逐层过滤：资金承接弱的往后排，行情不配合时宁可少选。",
  },
  {
    n: "03",
    title: "评分排序，输出短名单",
    body: "对入选标的打分并附上资金阶段标签，形成一份便于横向比较的观察清单。是否参与、仓位多少，始终由你自己决定。",
  },
] as const;

/** 首页示例清单 —— 纯演示数据，不对应任何真实证券 */
export const SAMPLE_LIST = [
  { rank: 1, name: "示例股票 A", score: 86, phase: "拉升", chg: 2.35 },
  { rank: 2, name: "示例股票 B", score: 78, phase: "吸筹", chg: 0.82 },
  { rank: 3, name: "示例股票 C", score: 71, phase: "潜伏", chg: -0.46 },
  { rank: 4, name: "示例股票 D", score: 66, phase: "吸筹", chg: -1.12 },
] as const;

/** 首页「模型质量」指标（站长确认；仅描述模型本身，不涉及收益） */
export const MODEL_METRICS: ReadonlyArray<{
  label: string;
  value: string;
  unit?: string;
  hint: string;
}> = [
  { label: "每日扫描范围", value: "5000+", unit: "只", hint: "全 A 股，每个交易日扫描" },
  { label: "集成模型", value: "106", unit: "维", hint: "V25 集成模型" },
  { label: "样本外 AUC", value: "0.631", hint: "预测次日收盘涨幅超 3%，2026 年中评估窗口" },
  { label: "每日终选", value: "Top10", hint: "每日 09:35 终选" },
];

export const MODEL_METRICS_NOTE = "以上为模型质量指标，不构成收益承诺";

export const FAQS = [
  {
    q: "AlphaPilot 是在推荐股票吗？",
    a: "不是。AlphaPilot 是基于公开行情数据的量化筛选与研究辅助工具，页面上的名单、评分和阶段标签都是模型输出，仅供学习与研究参考，不构成任何投资建议或收益承诺。买不买、买多少，请结合自身情况独立判断。",
  },
  {
    q: "每天的名单是怎么得出来的？",
    a: "系统每个交易日对全部 A 股做多维度逐层筛选（成交活跃度、资金流向、量价形态、大盘环境等），再对入选标的评分排序。你可以在「工作台」查看每只标的的明细。",
  },
  {
    q: "“评分”代表上涨概率吗？",
    a: "不代表。评分只用于同一天名单内的相对排序，方便横向比较，不是上涨概率，也不是收益预测。",
  },
  {
    q: "为什么有时候名单很短，甚至为空？",
    a: "行情偏弱或没有满足条件的标的时，系统会主动少选或留空，而不是为了凑数硬推名单。",
  },
  {
    q: "历史回测结果可靠吗？",
    a: "回测只反映历史数据上的模拟结果，存在样本局限，部分模式还可能存在前视偏差，并且未必能完全还原真实成交。过往表现不代表未来，请只作参考。",
  },
  {
    q: "需要付费吗？",
    a: "目前可免费使用。如后续有收费或会员安排，会提前在站内说明。",
  },
] as const;

export const RISK_SHORT = DISCLAIMER_SHORT;
export const RISK_FOOTER = DISCLAIMER_FULL;

export const RISK_FULL = [
  "AlphaPilot 是基于公开行情数据的量化筛选与研究辅助工具。本站展示的名单、评分、资金阶段标签及回测结果均为模型输出，仅供学习与研究参考，不构成任何投资建议、要约或收益承诺。",
  "历史表现不代表未来收益。回测存在样本局限、前视偏差以及与真实成交不一致等风险；示例数据仅用于展示界面，并非真实标的。",
  "投资有风险，入市需谨慎。请结合自身风险承受能力独立决策，盈亏自负。",
];

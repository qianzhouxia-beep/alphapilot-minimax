"use client";

// 仅保留中文，移除英文
// 2026-07-06: 纯 A 股市场，不需要多语言

import { createContext, useContext } from "react";

export type Locale = "zh-CN";

type Dict = Record<string, string>;
const zhCN: Dict = {
  "site.title": "AlphaPilot — AI 股票智能决策平台",
  "site.subtitle": "AI 智能选股 · A 股全市场",
  "market.us": "美股",
  "market.cn": "A 股",
  "market.status.open": "美股交易中",
  "market.status.open.cn": "A 股交易中",
  "kpi.top": "最佳机会",
  "kpi.avg": "平均评分",
  "kpi.bullish": "看多信号",
  "kpi.bearish": "看空信号",
  "kpi.score": "评分",
  "kpi.top20": "Top 20",
  "kpi.bullish.sub": "吸筹 + 拉升",
  "kpi.bearish.sub": "出货 + 洗盘",
  "table.title": "Top 20 机会",
  "table.subtitle": "AI 评分 A 股 · 数据源:",
  "table.fullScreener": "完整选股 →",
  "table.col.rank": "#",
  "table.col.symbol": "代码",
  "table.col.name": "名称",
  "table.col.score": "评分",
  "table.col.up": "上涨%",
  "table.col.risk": "风险",
  "table.col.mainforce": "主力状态",
  "table.col.sector": "行业",
  "table.col.action": "操作",
  "table.details": "详情 →",
  "risk.low": "低",
  "risk.medium": "中",
  "risk.high": "高",
  "auth.signin": "登录",
  "auth.signup": "注册",
  "auth.signout": "退出",
  "auth.plan": "套餐",
  "auth.signup.title": "创建账户",
  "auth.signup.subtitle": "7 天免费试用开始",
  "auth.signin.title": "登录",
  "auth.signin.subtitle": "欢迎回来",
  "auth.field.name": "姓名",
  "auth.field.email": "邮箱",
  "auth.field.password": "密码",
  "auth.field.password.signup": "密码 (8+ 字符)",
  "auth.submit.signup": "创建账户",
  "auth.submit.signin": "登录",
  "auth.toSignup": "还没有账户?",
  "auth.toSignin": "已有账户?",
  "auth.create": "立即注册",
  "auth.signin.link": "去登录",
  "auth.mock.note": "M2 模拟登录 (localStorage)",
  "screener.title": "AI 智能选股",
  "screener.subtitle": "只股票 AI 评分排序",
  "screener.filter.sectors": "行业筛选",
  "screener.empty": "后端未连接",
  "stock.back": "← 返回",
  "stock.tabs.decision": "AI 决策卡",
  "stock.tabs.ai": "AI 评分",
  "stock.tabs.radar": "主力意图",
  "stock.tabs.evidence": "证据链",
  "stock.tabs.risk": "风险",
  "stock.tabs.multi": "多周期",
  "stock.decision.score": "综合评分",
  "stock.decision.confidence": "置信度",
  "stock.decision.up": "上涨概率",
  "stock.decision.mainforce": "主力状态",
  "stock.decision.next": "下一步",
  "stock.decision.buyzone": "买入区间",
  "stock.decision.stoploss": "止损位",
  "stock.decision.target1": "目标 1",
  "stock.decision.target2": "目标 2",
  "stock.decision.position": "建议仓位",
  "stock.decision.buy": "买入",
  "stock.decision.watch": "加自选",
  "stock.risk.level": "风险等级",
  "stock.risk.invalidation": "失效条件",
  "stock.risk.earnings": "财报",
  "stock.risk.beta": "行业 Beta",
  "stock.multi.alignment": "周期共振",
  "stock.multi.bullish": "看多",
  "stock.multi.neutral": "中性",
  "stock.multi.caution": "谨慎",
  "footer.disclaimer":
    "AlphaPilot 提供 AI 辅助分析,仅供教育用途,非投资建议。过往表现不保证未来收益。所有概率为估计值,非保证。",
  "error.backend": "后端无法连接",
  "error.backend.tip": "提示:请确认后端运行在 localhost:8002",
  "tab.us": "美股",
  "tab.cn": "A 股",
  "tab.home": "首页",
  "tab.screener": "选股",
  "mainforce.accumulation": "吸筹",
  "mainforce.markup": "拉升",
  "mainforce.distribution": "出货",
  "mainforce.washout": "洗盘",
  "mainforce.reaccumulation": "二次吸筹",
  "mainforce.bull_trap": "诱多",
  "mainforce.bear_trap": "诱空",
  "loading": "加载中…",
};

type I18nState = {
  t: (key: keyof Dict | string) => string;
};

const I18nContext = createContext<I18nState | null>(null);

export function LocaleProvider({ children }: { children: React.ReactNode }) {
  const t = (key: string) => zhCN[key] || key;

  return (
    <I18nContext.Provider value={{ t }}>
      {children}
    </I18nContext.Provider>
  );
}

export function useI18n(): I18nState {
  const ctx = useContext(I18nContext);
  if (!ctx) {
    return { t: (k: string) => zhCN[k] || k };
  }
  return ctx;
}

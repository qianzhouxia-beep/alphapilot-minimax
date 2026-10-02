// 站点级 SEO 常量（layout 与首页共用；Next 的 openGraph 在页面级会整体覆盖，需要重复完整字段）
export const SEO_TITLE = "AlphaPilot｜A 股量化选股工具：全 A 每日扫描，评分排序";
export const SEO_DESC =
  "AlphaPilot 是面向 A 股投资者的量化筛选与研究辅助工具：每个交易日扫描全 A，结合成交、资金流向与大盘环境逐层筛选，输出评分排序的观察清单。仅供研究参考，不构成投资建议。";

export const OG_BASE = {
  type: "website" as const,
  locale: "zh_CN",
  siteName: "AlphaPilot",
  title: SEO_TITLE,
  description: SEO_DESC,
  images: [{ url: "/og.png", width: 1200, height: 630, alt: "AlphaPilot — A 股量化选股工具" }],
};

---
name: data-report
zh_name: "数据可视化报告"
en_name: "Data Visualization Report"
emoji: "📊"
description: "Turns CSV, Excel, or JSON data into a polished visual report page."
zh_description: "把 CSV/Excel/JSON 数据转成漂亮的可视化报告页"
en_description: "Turns CSV, Excel, or JSON data into a polished visual report page."
category: data
scenario: finance
aspect_hint: "桌面长页面"
featured: 10
tags: ["data", "report", "chart", "数据", "报告"]
example_id: sample-data-weekly-report
example_name: "数据报告 · 周报"
example_format: csv
example_tagline: "KPI 卡 + Chart.js 图表 + 表格"
example_desc: "9 个月增长数据自动渲染成可视化报告, 内联 Chart.js"
od:
  mode: prototype
  surface: web
  platform: desktop
  scenario: finance
  upstream: "https://github.com/nexu-io/html-anything"
  preview:
    type: html
    entry: index.html
    reload: debounce-100
  design_system:
    requires: false
  example_prompt: "Use the Data Visualization Report template to turn my CSV, Excel, or JSON data into a polished visual report page. Preserve the template's visual signature, use real content and data, and avoid lorem ipsum or placeholder images."
  example_prompt_i18n:
    zh-CN: "用「数据可视化报告」模板把我的内容做成一份「把 CSV/Excel/JSON 数据转成漂亮的可视化报告页」。保持模板的视觉签名，使用真实内容和数据，避免 lorem ipsum 和占位图片。"
---

【模板: 数据可视化报告】

## AlphaPilot 适配规则（必须遵守）

1. **视觉基线**：遵循项目根目录 `DESIGN.md` 与 `tokens.css`。浅色主题，禁止深色模式；系统字体栈（`-apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif`），**禁止加载 Google Fonts**。
2. **Token 引用**：所有样式用 `var(--ap-*)` 变量，不写裸色值。参考 `tokens.css` 的三层结构（primitive → semantic → component）。
3. **涨跌色（中国股市惯例）**：涨/正/流入用红（`--ap-semantic-up` / `#C62828`），跌/负/流出用绿（`--ap-semantic-down` / `#1E7A35`），平/中性用灰。数值必须配 ▲/▼ 方向符号，不单独靠颜色。
4. **等宽数字**：价格、涨跌幅、百分比、成交量等所有数值用 `--ap-semantic-data-font`（等宽字体 + `font-feature-settings:'tnum'`），保证表格列竖排对齐。
5. **图表容器必须有固定高度**：每个 `<canvas>` 外层包一个 `<div style="position:relative;height:NNNpx">`（KPI 迷你图 ~40px，主图表 ~240–280px，AlphaPilot 大盘面图表可用 400px）。Chart.js/ECharts 用 `responsive:true, maintainAspectRatio:false` 时若父容器没有显式高度，会陷入 ResizeObserver 死循环，图表无限增高直至卡死浏览器。**绝对不要**直接给 canvas 写 `height=` 属性当布局，那个只是初始值。
6. **数据刷新纪律**（如做实时指标）：刷新过渡 100ms，新值替换前保留旧值至少一帧；禁止数字逐个翻滚动画。
7. **必须解析用户提供的实际数据**，不要捏造。缺失数据用 "not provided" 标注而非编造。

## 结构

- 头部: 报告标题 + 时间区间 + 数据来源说明。
- KPI 卡片网格: 3-5 个最重要指标, 每个卡片显示数值 + 同比变化 + 微型趋势线。
- 主图表区: 至少 2 个图表 (柱状 / 折线 / 饼 / 散点), 使用 Chart.js 或 ECharts (jsdelivr CDN 引入), 数据从用户输入解析得到。
- 数据表格: 用户原始数据节选, 使用 `<table>` + 现代化样式 (zebra stripe, hover, sticky header)。
- 洞察块: 3-5 条文字洞察, 用 emoji 开头, 像产品周报。
- 底部"方法论"折叠区。
- 配色克制专业: 主色 1 + 中性色阶, 图表用调色板。

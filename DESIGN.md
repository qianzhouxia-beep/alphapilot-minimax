---
name: AlphaPilot
description: A股量化选股与模拟交易工作台
design_tokens: tokens.css
tokens_version: 1
colors:
  primary: "#7C5CFC"
  primary-light: "#EDE9FE"
  primary-on-light: "#5B21B6"
  red: "#c62828"
  red-light: "rgba(198,40,40,0.04)"
  green: "#1e7a35"
  green-light: "#D1FAE5"
  green-on-light: "#166534"
  yellow: "#B45309"
  yellow-light: "#FEF3C7"
  blue: "#1a6fc4"
  blue-light: "#DBEAFE"
  blue-on-light: "#1E40AF"
  purple: "#7C5CFC"
  purple-light: "#EDE9FE"
  purple-on-light: "#5B21B6"
  purple-hero: "#6D3AEA"
  bg: "#F5F5F7"
  card: "#FFFFFF"
  bg-tertiary: "#FAFAFA"
  text: "#1D1D1F"
  text-secondary: "#3A3A40"
  text-tertiary: "#86868B"
  border: "rgba(0,0,0,0.06)"
  button-bg: "#7C3AED"
  decorative-overlay: "rgba(30,136,229,0.06)"
typography:
  fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif"
  display:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif"
    fontSize: "28px"
    fontWeight: 700
    lineHeight: 1.6
  heading:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif"
    fontSize: "20px"
    fontWeight: 700
    lineHeight: 1.6
  subheading:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif"
    fontSize: "17px"
    fontWeight: 600
  body:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif"
    fontSize: "14px"
    lineHeight: 1.85
  meta:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif"
    fontSize: "13px"
    color: "#55555B"
  stat-value:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif"
    fontSize: "22px"
    fontWeight: 700
  hero-title:
    fontSize: "44px"
    fontWeight: 800
  hero-cta:
    fontSize: "15px"
    fontWeight: 600
  section-h2:
    fontSize: "28px"
    fontWeight: 700
  section-h3:
    fontSize: "18px"
    fontWeight: 700
  card-h3:
    fontSize: "16px"
    fontWeight: 700
  cta-h2:
    fontSize: "24px"
    fontWeight: 700
  badge:
    fontSize: "12px"
    fontWeight: 600
  card-tag:
    fontSize: "11px"
    fontWeight: 600
rounded:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  full: "20px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "20px"
  xxl: "24px"
  section: "28px 32px"
components:
  stat-card:
    backgroundColor: "#FAFAFA"
    rounded: "{rounded.md}"
    padding: "12px"
  section-card:
    backgroundColor: "{colors.card}"
    rounded: "{rounded.lg}"
    padding: "{spacing.section}"
    border: "1px solid rgba(0,0,0,0.06)"
  highlight-box:
    backgroundColor: "{colors.primary-light}"
    rounded: "{rounded.md}"
    padding: "14px 18px"
---

## Overview

AlphaPilot 是一个浅色主题的 A 股量化金融数据工作台。设计目标是**干净、高效、数据密集**，优先展示指标而非装饰。整体风格受苹果人机界面指南影响：大量留白、圆角卡片、层级分明的字体系统。

所有页面使用系统原生字体回退链 `-apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif`，不引入外部字体。

## Design Tokens

`tokens.css` 是本设计系统的**机器可读单一事实来源**，本文件是规范文档。所有页面/组件样式**必须**通过 CSS 变量引用 token，禁止硬编码色值、字号、间距、圆角。

### 三层结构

- **`--ap-primitive-*`（原始层）**：色板、字号刻度、间距基数、圆角、阴影、过渡时长。命名即含义，不直接用于组件。
- **`--ap-semantic-*`（语义层）**：角色化的 token（涨/跌/品牌/文本/边框/焦点）。组件只消费语义层。
- **`--ap-comp-*`（组件层）**：stat-card、section-card、highlight-box、按钮、表格、徽章等现成组件的完整样式。

### 使用规则

- 页面内联 `<style>` 或独立 CSS 一律写 `var(--ap-*)`，不写裸色值。
- 涨跌语义用 `--ap-semantic-up` / `--ap-semantic-down` / `--ap-semantic-flat`，不要直接引用红绿原始色板。
- 数据数值（价格、涨跌幅、成交量）字体用 `--ap-semantic-data-font`（等宽字体保证竖排对齐）。
- 数据刷新过渡用 `--ap-semantic-data-sync`（100ms），交互 hover 用 `--ap-primitive-motion-fast`（150ms）。

### 快速换算表

| 语义 | 原始层 | 十六进制 |
|------|--------|----------|
| 品牌紫 | `--ap-primitive-violet-brand` | `#7C5CFC` |
| 品牌紫深 | `--ap-primitive-violet-700` | `#6D3AEA` |
| 品牌紫浅底 | `--ap-primitive-violet-50` | `#EDE9FE` |
| 涨（红） | `--ap-primitive-red-700` | `#C62828` |
| 跌（绿） | `--ap-primitive-green-800` | `#1E7A35` |
| 警告（琥珀） | `--ap-primitive-amber-700` | `#B45309` |
| 页面背景 | `--ap-primitive-gray-100` | `#F5F5F7` |
| 卡片背景 | `--ap-primitive-white` | `#FFFFFF` |
| 主文本 | `--ap-primitive-gray-800` | `#1D1D1F` |
| 二级文本 | `--ap-primitive-gray-700` | `#3A3A40` |
| 三级文本 | `--ap-primitive-gray-600` | `#55555B` |

## Financial Data Display Principles

AlphaPilot 是金融数据界面，遵循交易终端级的数据呈现纪律（借鉴 Bloomberg 终端风格）：

- **等宽数字**：所有价格、涨跌幅、成交量、百分比等数值用 `--ap-semantic-data-font`（等宽字体），保证同一列的数值竖排严格对齐，扫读时不跳动。
- **涨跌色不单独承载信息**：涨/跌必须同时配方向符号（▲/▼）或 +/- 前缀，纯色盲不可辨。
- **数值刷新防闪烁**：实时数据刷新过渡用 100ms，且新值替换前保留旧值至少一帧（避免闪白/闪黑）。禁止数字逐个翻滚动画——交易者需要瞬间稳定读数。
- **不做装饰性动效**：禁止对数据值做 bounce/elastic/滚动数字等装饰动画，hover 卡片的位移 ≤2px。
- **过渡时长克制**：hover/焦点状态 150ms，数据更新 100ms，页面转场 250ms。全部用 `ease` 或 `cubic-bezier(0.2, 0, 0, 1)`，禁止弹跳缓动。
- **颜色编码统一**：涨=红、跌=绿、平/中性=灰、警告=琥珀。深色背景上用浅色变体（`--ap-primitive-red-100`/`--ap-primitive-green-100`）保证对比度。
- **数据密度优先**：信息层级由字号与字重表达，不靠装饰分隔线；表格行 hover 高亮即可，不加斑马纹噪音。

## Colors

### 语义色

- **红色** `#c62828` — 上涨、正值、净流入、关注（深红色确保白色背景 5.0:1 AA 对比）
- **绿色** `#1e7a35` — 下跌、负值、净流出、回避（深绿色确保 AA 对比）
- **紫色** `#7C5CFC` — 品牌色、按钮、链接、活跃状态、徽章
- **黄色** `#B45309` — 警告、中性/震荡标注（深琥珀色确保 AA 对比）

### 中性色

- 背景 `#F5F5F7` — 页面底色
- 卡片 `#FFFFFF` — 深色模式下可能反色
- 背景三级 `#FAFAFA` — 数据卡片、统计块的底色
- 边框 `rgba(0,0,0,0.06)` — 极浅分割线
- 文字 `#1D1D1F` — 主标题
- 文字二级 `#3A3A40` — 正文
- 文字三级 `#55555B` — 辅助信息、时间戳、数据来源

### 数值颜色规则

- **涨/正/流入**：红色（与中国股市红色=涨一致）
- **跌/负/流出**：绿色（与中国股市绿色=跌一致）
- **中性/震荡**：黄色或文字三级

## Typography

层级：

- **h1 / 页面标题**：28px / 700 weight / 大标题
- **h2 / 区块标题**：20px / 700 weight / 带下边框分割
- **h3 / 子标题**：17px / 600 weight
- **正文**：14px / 常规 / 行高 1.85
- **辅助文字**：13px / 灰色 `#86868B`
- **统计数值**：22px / 700 weight / 居中对齐

### Typography 层级覆盖

基础层级上文已定义。以下为 cn_quant_page.html 的特殊覆盖（全在系统字体栈内）：

| 用途 | 字号 | 字重 | 说明 |
|------|------|------|------|
| Hero 标题 | 44px | 800 | 着陆页大标题 |
| Hero 副标题 | 17px | 常规 | 着陆页描述 |
| Hero CTA 按钮 | 15px | 600 | 主/次按钮 |
| 区块 h2 | 28px | 700 | section-header h2 |
| 区块 h3 | 18px | 700 | pas-block 内标题 |
| 卡内 h3 | 16px | 700 | card 内标题 |
| CTA 区块 h2 | 24px | 700 | cta-block 标题 |
| 徽章/标签 | 12px | 600 | hero-badge, pill, tag |
| 辅助/元信息 | 12px | 500 | kpi-label, step-desc, tl-time |

所有字体使用系统原生栈，不引用 Google Fonts 或其他外部字体服务。

## Layout

### 页面布局

- 最大宽度 **1200px**，居中，两侧 `24px 16px` padding
- 内容以圆角卡片（section）纵向堆叠，卡片间距 `20px`
- @media max-width: 640px 时卡片 padding 缩为 20px 16px
- 图表容器固定高度 400px（桌面）/ 300px（移动）

### 数据卡片（stat-row）

- CSS Grid 布局：`grid-template-columns: repeat(auto-fit, minmax(200px, 1fr))`
- 间距 `16px`，每个 stat 居中对齐
- 移动端折叠为单列

## Elevation & Depth

- 卡片阴影：`0 1px 2px rgba(0,0,0,0.04), 0 1px 3px rgba(0,0,0,0.02)`
- 不使用深色渐变、发光、毛玻璃效果
- 不使用卡片嵌套卡片（避免视觉噪音）

## Shapes

- 卡片圆角：16px（section）、12px（stat/data card）、8px（highlight box）、4px（小标签/标记）
- 徽章（badge）：圆角 20px（pill 形状）
- 头像/编号标记：24px 圆形（`border-radius: 50%`）

## Components

### Section Card
白色背景，16px 圆角，1px 极浅边框，28px 32px 内边距，带柔和阴影。

### Stat Card
浅灰背景 `#FAFAFA`，12px 圆角，12px 内边距，居中对齐。含 label（12px 灰色）+ value（22px 加粗）。

### Highlight Box
紫色浅底 `#EDE9FE`，12px 圆角，14px 18px 内边距。用于突出展示板块偏好、轮动信号等。

### Data Table
    全宽无边框表格，14px 字号。th 灰色文字浅灰底，td 底部 1px 分割线，hover 行高亮。

### 趋势/PE 过滤器按钮组
水平排列的按钮组，选中态紫色 `#7C5CFC`，非选中浅灰边框。

### 卡片列表（今日推荐/评分榜）
纵向堆叠的列表卡，每卡按 rank 编号，含股票名、代码、评分、行业、涨跌幅、PE、趋势标签。

## Do's and Don'ts

- ✅ 使用紫色 `#7C5CFC` 作为唯一的强调色和品牌色
- ✅ 上涨用红色、下跌用绿色（遵循中国股市惯例）
- ✅ 数据密集页面保持字体层级清晰
- ✅ 数据来源标注时间和来源文字
- ✅ 所有数值用等宽字体（`--ap-semantic-data-font`）竖排对齐
- ✅ 涨跌必须配 ▲/▼ 或 +/- 方向符号，不单独靠颜色
- ✅ 实时数据刷新 100ms 过渡并保留旧值一帧防闪烁
- ❌ 不使用渐变、发光、毛玻璃等装饰效果
- ❌ 不使用非系统字体（不加载 Google Fonts）
- ❌ 不使用深色模式（AlphaPilot 保持浅色）
- ❌ 不在彩色背景上放灰色文字
- ❌ 避免卡片嵌套卡片
- ❌ 避免使用 bounce/elastic 缓动函数
- ❌ 禁止硬编码色值/字号/间距，一律引用 `var(--ap-*)` token
- ❌ 禁止数字逐个翻滚动画与装饰性动效

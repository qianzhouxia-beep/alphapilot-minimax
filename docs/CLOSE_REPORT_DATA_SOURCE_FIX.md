# 收盘研报数据源重构

**核心逻辑**: 收盘报告只分析今日交易数据，不混入上周数据。

---

## 改前问题

| 报告部分 | 数据源 | 实际日期 | 问题 |
|---|---|---|---|
| 主力净流入(主卡) | THS Dashboard `net_yi` | **07-24(周五)** ❌ | 收盘报告用周五数据 |
| 行业流入/流出Top | THS `today_top10` | **07-24(周五)** ❌ | 同上 |
| 放行/拦截板块 | THS `allow/deny` | **07-24(周五)** ❌ | 同上 |
| 上涨/下跌家数 | market-overview API | 实时(但返回0) ❌ | 已坏 |
| 〇节(Wind) | Wind `all_a` | **07-27(今日)** ✅ | 正确但被降级为附加节 |

## 改后逻辑

```
收盘报告(15:45)
├─ 主报告体(全部用今日数据)
│   ├─ 主力净流入 → Wind all_a.main_net ✅
│   ├─ 行业资金流Top → Wind consult.industry_top_inflow ✅
│   ├─ 板块偏好 → Wind consult.prefer/avoid ✅
│   ├─ 全A 4档归因 → Wind all_a.inst_net/large_net/mid_net/retail_net ✅
│   ├─ 三大指数 → 新浪实时 ✅
│   └─ 上涨/下跌家数 → (修复market-overview或转用Wind)
│
├─ 多周期对比(用历史数据，标日期)
│   └─ THS Dashboard: 5/10/20/60日对比表
│       表头标注: "(数据截至 07/24 收盘)"
│
└─ 报告尾部
    └─ 数据来源说明 + 免责
```

## 具体变更

### 1. 主 stat 卡 (HTML 570-595行)

```
改前:
  主力净流入 = THS summary.net_yi
  放行/拦截 = THS summary.allow/deny

改后:
  主力净流入 = Wind all_a.main_net (+938亿)
  4档归因卡片: 机构+452亿 / 大户+487亿 / 中户+279亿 / 散户+151亿
  上涨/下跌 = (修复market-overview或用Wind涨停统计)
  数据来源文字: "数据来源：万得行业资金流(今日收盘) + 新浪实时指数"
```

### 2. 行业资金流 (原THS today_top10 → 改用Wind)

```
改前:
  today_top10 / today_bottom10 来自THS Dashboard

改后:
  行业流入Top = Wind consult.industry_top_inflow
    显示: 名称 + 主力净流入 + 连续流入天数 + 标签(fresh_inflow/rotation_watch)
  行业流出Top = Wind consult.industry_top_outflow
    显示: 名称 + 主力净流出
  板块偏好 = Wind consult.prefer + avoid
```

### 3. 全A情绪段

```
改前:
  只有〇节有全A 4档

改后:
  主报告体增加全A情绪段:
  机构+452亿 / 大户+487亿 / 中户+279亿 / 散户+151亿
  判断: 机构+大户双买入 → "偏多"; 机构卖大户买 → "分歧"; 双卖出 → "偏空"
```

### 4. 多周期对比表 (保留THS，标日期)

```
位置: 报告尾部
内容: THS Dashboard 5/10/20/60日对比
表头标注: "(通达信行业资金流，截至 07/24 收盘)"
```

### 5. 上涨/下跌家数

当前 `market-overview` API 返回 0/0 (pct_chg列缺失)。两个方案：
- **方案A**: 修 `market-overview` API → 从 kline 算
- **方案B**: 先用 Wind 涨停统计 `CNT_RED/CNT_GREEN`（通过westock MCP）

**推荐**: 方案B，Wind数据今天可用。把westock `data_market_overview` type=updown 的结果写入 `wind_board_flow.json` 的 `all_a` 下。

## 验收标准

1. 主力净流入 = **+938亿**（今日Wind，非周五THS）
2. 行业流入Top = **电子 +180亿**, **电力设备 +103亿**, **医药生物 +91亿**（今日Wind）
3. 板块偏好 = **prefer: 电子/电力设备/医药生物**（今日Wind）
4. 多周期表有日期标注 "(截至 07/24)"
5. 上涨/下跌 > 0 (不再是 0/0)
